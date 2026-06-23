"""Unit tests for the carousel RunRequest language validation."""
from routers.carousel import RunRequest


def test_english_always_first_when_missing():
    req = RunRequest(url="https://x", languages=["th", "zh-TW"])
    assert req.validate_languages() == ["en", "th", "zh-TW"]


def test_english_kept_when_present():
    req = RunRequest(url="https://x", languages=["en", "pt-BR"])
    assert req.validate_languages() == ["en", "pt-BR"]


def test_unknown_languages_are_dropped():
    req = RunRequest(url="https://x", languages=["en", "klingon", "th"])
    assert req.validate_languages() == ["en", "th"]


def test_empty_defaults_to_english():
    req = RunRequest(url="https://x", languages=[])
    assert req.validate_languages() == ["en"]
