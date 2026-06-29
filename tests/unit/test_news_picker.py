"""Unit tests for news_picker scoring/filtering (pure functions, no network)."""
import base64
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


def test_score_respects_custom_max_age_window():
    # 30h old: discarded under the default 20h window, kept under a 48h window.
    art = _recent(published=datetime.now(timezone.utc) - timedelta(hours=30),
                  title="Fed rate cut")
    assert np._score(art) == -1
    assert np._score(art, max_age_hours=48) > 0


def test_score_rejects_article_older_than_two_days_even_with_wide_window():
    art = _recent(published=datetime.now(timezone.utc) - timedelta(hours=60),
                  title="Fed rate cut")
    assert np._score(art, max_age_hours=48, require_dated=True) == -1


def test_require_dated_discards_undated_article():
    undated = _recent(title="Fed rate cut", published=None)
    # Without require_dated the article is still scorable on keywords...
    assert np._score(undated) > 0
    # ...but the daily feature insists on a confirmable date.
    assert np._score(undated, max_age_hours=48, require_dated=True) == -1


def test_require_dated_keeps_recent_dated_article():
    fresh = _recent(published=datetime.now(timezone.utc) - timedelta(hours=10),
                    title="Fed rate cut")
    assert np._score(fresh, max_age_hours=48, require_dated=True) > 0


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


# ── Google News URL resolution ────────────────────────────────────────────────

def test_resolve_passes_through_non_google_url():
    url = "https://www.reuters.com/markets/fed-rate-cut"
    assert np._resolve_google_news_url(url) == url


def test_decode_gnews_base64_extracts_publisher_url():
    target = "https://www.reuters.com/markets/us/fed-holds-rates-2026-06-29"
    # Mimic the protobuf payload: a field tag, the URL, then a control byte that
    # terminates the URL match — exactly what the real decoder must stop on.
    payload = b'\x08\x13\x22' + bytes([len(target)]) + target.encode() + b'\x1a\x04abcd'
    blob = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    url = f"https://news.google.com/rss/articles/{blob}?oc=5"
    assert np._decode_gnews_base64(url) == target


def test_decode_gnews_base64_rejects_google_self_link():
    payload = b'\x08\x13\x22' + b"https://news.google.com/foo"
    blob = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    url = f"https://news.google.com/rss/articles/{blob}"
    assert np._decode_gnews_base64(url) is None


# ── Headline ⇄ body relevance guard ───────────────────────────────────────────

def test_body_matches_headline_accepts_on_topic_body():
    title = "Fed signals a rate cut as inflation cools"
    body = "The Federal Reserve signals a possible rate cut after inflation data cooled."
    assert np._body_matches_headline(title, body)


def test_body_matches_headline_rejects_off_topic_body():
    title = "Fed signals a rate cut as inflation cools"
    body = "SoftBank dethrones Toyota to become Japan's most valuable company on AI bets."
    assert not np._body_matches_headline(title, body)


def test_headline_keywords_keeps_short_finance_terms_drops_stopwords():
    kws = np._headline_keywords("The Fed and the ECB will act")
    assert "fed" in kws and "ecb" in kws and "act" in kws
    assert "the" not in kws and "and" not in kws and "will" not in kws
