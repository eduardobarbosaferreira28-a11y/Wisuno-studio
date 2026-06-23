"""Unit tests for news_picker scoring/filtering (pure functions, no network)."""
from datetime import datetime, timedelta, timezone

import news_picker as np


def _recent(**kw):
    base = {"title": "x", "url": "https://example.com/a", "source": "s",
            "published": datetime.now(timezone.utc)}
    base.update(kw)
    return base


# ── _score ────────────────────────────────────────────────────────────────────

def test_score_sums_keyword_weights():
    # "fed" (10) + "rate cut" (10) + recency (<1h → +6)
    art = _recent(title="Fed signals a rate cut")
    assert np._score(art) == 26


def test_score_higher_for_more_impactful_headline():
    strong = np._score(_recent(title="Fed inflation cpi rate hike"))
    weak = np._score(_recent(title="Company announces new logo"))
    assert strong > weak


def test_score_discards_stale_articles():
    old = _recent(published=datetime.now(timezone.utc) - timedelta(hours=48),
                  title="Fed rate cut")
    assert np._score(old) == -1


# ── _deduplicate ──────────────────────────────────────────────────────────────

def test_deduplicate_removes_same_title_prefix():
    items = [
        {"title": "Fed cuts rates today", "url": "u1"},
        {"title": "Fed cuts rates today", "url": "u2"},
        {"title": "Different story", "url": "u3"},
    ]
    out = np._deduplicate(items)
    assert len(out) == 2
    assert out[0]["url"] == "u1"  # first occurrence kept


# ── _is_blocked ───────────────────────────────────────────────────────────────

def test_is_blocked_matches_domain_and_subdomain():
    assert np._is_blocked("https://www.bloomberg.com/news/article")
    assert np._is_blocked("https://markets.ft.com/data")


def test_is_blocked_allows_unlisted_domain():
    assert not np._is_blocked("https://news.google.com/rss/articles/x")
