"""Light integration test for the carousel router.

Mounts only the carousel router on a throwaway FastAPI app, overrides auth, and
stubs the job layer so no AI/network call happens. Verifies request wiring:
/run starts a job and /status surfaces the new `warnings` field.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.carousel as carousel_router
from dependencies.auth import get_current_user


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(carousel_router.router)
    # Bypass real Supabase JWT verification.
    app.dependency_overrides[get_current_user] = lambda: {"id": "test_user", "role": "admin"}
    return TestClient(app)


def test_run_starts_job_and_forces_english(client, monkeypatch):
    captured = {}

    def fake_start_job(**kwargs):
        captured.update(kwargs)
        return "job-123"

    monkeypatch.setattr(carousel_router, "start_job", fake_start_job)

    resp = client.post("/api/carousel/run", json={"url": "https://x", "languages": ["th"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "job-123"
    assert body["languages"] == ["en", "th"]
    assert captured["languages"] == ["en", "th"]
    assert captured["user_id"] == "test_user"


def test_run_rejects_missing_source(client):
    resp = client.post("/api/carousel/run", json={"languages": ["en"]})
    assert resp.status_code == 400


def test_daily_picks_article_and_starts_job(client, monkeypatch):
    import news_picker

    fake_article = {
        "title": "Fed holds rates steady",
        "url": "https://news.example.com/fed",
        "source": "Example News",
        "score": 26,
        "rationale": "Central-bank decision is the day's top driver for CFD traders.",
    }
    monkeypatch.setattr(news_picker, "pick_top_article", lambda *a, **k: fake_article)

    captured = {}

    def fake_start_job(**kwargs):
        captured.update(kwargs)
        return "daily-job-1"

    monkeypatch.setattr(carousel_router, "start_job", fake_start_job)

    resp = client.post("/api/carousel/daily", json={"languages": ["pt-BR"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "daily-job-1"
    assert body["languages"] == ["en", "pt-BR"]
    assert body["article"]["title"] == fake_article["title"]
    # The job is built from the picked article's URL.
    assert captured["url"] == fake_article["url"]


def test_daily_returns_404_when_no_article(client, monkeypatch):
    import news_picker
    monkeypatch.setattr(news_picker, "pick_top_article", lambda *a, **k: None)

    resp = client.post("/api/carousel/daily", json={"languages": ["en"]})
    assert resp.status_code == 404


def test_today_previews_article(client, monkeypatch):
    import news_picker
    fake_article = {"title": "CPI hot", "url": "https://x/cpi", "source": "Src",
                    "score": 18, "rationale": "Inflation surprise."}
    monkeypatch.setattr(news_picker, "pick_top_article", lambda *a, **k: fake_article)

    resp = client.get("/api/carousel/today")
    assert resp.status_code == 200
    assert resp.json()["article"]["title"] == "CPI hot"


def test_daily_forbidden_for_non_admin(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(carousel_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u2", "role": "user"}
    non_admin = TestClient(app)

    resp = non_admin.post("/api/carousel/daily", json={"languages": ["en"]})
    assert resp.status_code == 403


def test_status_exposes_warnings_field(client, monkeypatch):
    done_job = {
        "status": "done",
        "current_step": 4,
        "steps": [],
        "languages": ["en"],
        "error": None,
        "warnings": ["Cloud upload failed for one or more files — available via local download only."],
        "files": {},
        "user_id": "test_user",
    }
    monkeypatch.setattr(carousel_router, "get_job", lambda job_id: done_job)

    resp = client.get("/api/carousel/status/job-123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["warnings"] == done_job["warnings"]
