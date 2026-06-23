"""Unit tests for html_carousel pure helpers + translate_script (mocked Claude)."""
import json

import pytest

import html_carousel as hc


# ── _slugify ────────────────────────────────────────────────────────────────────

def test_slugify_basic():
    assert hc._slugify("The Inflation Monster Returns: CPI Hits 3.8%") == \
        "the-inflation-monster-returns-cpi-hits-38"


def test_slugify_strips_and_collapses_whitespace():
    assert hc._slugify("  Hello   World  ") == "hello-world"


def test_slugify_respects_max_len():
    out = hc._slugify("a" * 100, max_len=10)
    assert len(out) == 10


# ── _save_caption ─────────────────────────────────────────────────────────────

def test_save_caption_appends_hashtags(tmp_path):
    path = tmp_path / "caption.txt"
    hc._save_caption({"caption": "Hello world", "hashtags": ["cpi", "wisuno"]}, path)
    text = path.read_text(encoding="utf-8")
    assert "Hello world" in text
    assert "#cpi #wisuno" in text


def test_save_caption_without_hashtags(tmp_path):
    path = tmp_path / "caption.txt"
    hc._save_caption({"caption": "Just text"}, path)
    assert path.read_text(encoding="utf-8") == "Just text"


# ── translate_script (Claude mocked) ──────────────────────────────────────────

def test_translate_script_plain_json(monkeypatch, fake_anthropic):
    translated = {"title": "通膨", "slides": []}
    client = fake_anthropic([json.dumps(translated, ensure_ascii=False)])
    monkeypatch.setattr(hc, "_anthropic_client", lambda: client)

    result = hc.translate_script({"title": "Inflation", "slides": []}, "zh-TW")
    assert result == translated
    assert len(client.messages.calls) == 1


def test_translate_script_strips_markdown_fence(monkeypatch, fake_anthropic):
    wrapped = "```json\n" + json.dumps({"title": "X", "slides": []}) + "\n```"
    client = fake_anthropic([wrapped])
    monkeypatch.setattr(hc, "_anthropic_client", lambda: client)

    result = hc.translate_script({"title": "X", "slides": []}, "th")
    assert result["title"] == "X"


def test_translate_script_repairs_invalid_json_on_retry(monkeypatch, fake_anthropic):
    monkeypatch.setattr(hc.time, "sleep", lambda *a, **k: None)  # no real backoff wait
    good = json.dumps({"title": "ok", "slides": []})
    client = fake_anthropic(["{bad json,,}", good])
    monkeypatch.setattr(hc, "_anthropic_client", lambda: client)

    result = hc.translate_script({"title": "ok", "slides": []}, "th", retries=2)
    assert result["title"] == "ok"
    assert len(client.messages.calls) == 2  # one failed + one repair


def test_translate_script_raises_after_exhausting_retries(monkeypatch, fake_anthropic):
    monkeypatch.setattr(hc.time, "sleep", lambda *a, **k: None)
    client = fake_anthropic(["{nope", "still {bad"])
    monkeypatch.setattr(hc, "_anthropic_client", lambda: client)

    with pytest.raises(ValueError):
        hc.translate_script({"title": "x", "slides": []}, "th", retries=1)
