"""Startup log of the Supabase project ref: shows the ref only, never the URL or a key."""

import logging

import app as studio_app
import pytest

import config


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://devref123.supabase.co", "devref123"),
        ("https://devref123.supabase.co/", "devref123"),
        ("  https://devref123.supabase.co/rest/v1?apikey=secret  ", "devref123"),
        ("", None),
        (None, None),
        ("not-a-url", None),
    ],
)
def test_supabase_project_ref(url, expected):
    assert studio_app.supabase_project_ref(url) == expected


def test_startup_logs_ref_only_and_no_key(monkeypatch, caplog):
    secret_anon = "sb_publishable_TEST_ANON_VALUE"
    secret_service = "TEST_SERVICE_ROLE_VALUE"
    monkeypatch.setattr(config, "SUPABASE_URL", "https://devref123.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", secret_anon)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", secret_service)

    with caplog.at_level(logging.INFO, logger=studio_app.logger.name):
        studio_app.log_supabase_project_ref()

    assert "Supabase project ref in use: devref123" in caplog.text
    assert "supabase.co" not in caplog.text
    assert secret_anon not in caplog.text
    assert secret_service not in caplog.text


def test_startup_warns_when_url_missing(monkeypatch, caplog):
    monkeypatch.setattr(config, "SUPABASE_URL", "")

    with caplog.at_level(logging.INFO, logger=studio_app.logger.name):
        studio_app.log_supabase_project_ref()

    assert any(r.levelno == logging.WARNING and "SUPABASE_URL not set" in r.message for r in caplog.records)
