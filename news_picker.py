"""
news_picker.py
==============
Fetches top financial headlines from multiple public sources and uses a
weighted keyword + recency score — plus a final Claude confirmation —
to select the single most market-impactful article for the day.

Sources (in priority order):
  1. Google News RSS — financial markets / forex / central-bank queries
  2. Investing.com RSS — forex news + commodities
  3. yfinance SPY / QQQ ticker news (Yahoo Finance unofficial API)

Usage:
  from news_picker import pick_top_article
  article = pick_top_article()
  print(article["url"], article["title"], article["rationale"])

  # CLI test
  python news_picker.py
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import TypedDict

import feedparser
import requests
import yfinance as yf

# ── Config ────────────────────────────────────────────────────────────────────

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WisunoBot/1.0; +https://wisuno.com)"}
TIMEOUT = 12        # seconds per HTTP request
MAX_PER_FEED = 15   # headlines per RSS feed
MAX_AGE_HOURS = 20  # ignore articles older than this

RSS_FEEDS = [
    # Google News — broad financial markets
    "https://news.google.com/rss/search?q=financial+markets+economy&hl=en-US&gl=US&ceid=US:en",
    # Google News — central banks / monetary policy (highest-impact for CFDs)
    "https://news.google.com/rss/search?q=fed+interest+rate+inflation+ecb+central+bank&hl=en-US&gl=US&ceid=US:en",
    # Google News — forex / currency
    "https://news.google.com/rss/search?q=forex+currency+dollar+euro+gbp+yen&hl=en-US&gl=US&ceid=US:en",
    # Investing.com — forex news
    "https://www.investing.com/rss/news_1.rss",
    # Investing.com — commodities (oil, gold)
    "https://www.investing.com/rss/news_11.rss",
]

YFINANCE_TICKERS = ["SPY", "QQQ"]   # broad market proxies

# Domains whose article pages are known to return 403 / hard-paywall.
# Their RSS *headlines* are fine for scoring but we cannot fetch the body.
BLOCKED_DOMAINS: set[str] = {
    "investing.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "barrons.com",
    "seekingalpha.com",
    "thestreet.com",
}

# Impact weights for CFD/forex trading audience
KEYWORD_WEIGHTS: dict[str, int] = {
    # Central bank / monetary policy — highest priority
    "fed":           10, "fomc":          10, "federal reserve": 10,
    "interest rate": 10, "rate hike":     10, "rate cut":        10,
    "powell":        10, "lagarde":       10, "boe":              9,
    "bank of england": 9, "boj":           9, "ecb":              9,
    # Macro data releases
    "inflation":      9, "cpi":            9, "pce":              9,
    "nfp":            9, "jobs report":    9, "non-farm":         9,
    "gdp":            8, "unemployment":   8, "retail sales":     8,
    # Market-moving events
    "recession":      9, "default":        9, "crash":            9,
    "tariff":         8, "sanction":       8, "correction":       7,
    "earnings":       7, "rally":          6, "surge":            6,
    # CFD / forex instruments
    "dollar":         7, "usd":            7, "euro":             7,
    "eur":            7, "gbp":            7, "yen":              7,
    "yuan":           7, "oil":            7, "crude":            7,
    "gold":           7, "silver":         6, "bitcoin":          6,
    "nasdaq":         6, "s&p":            6, "dow":              6,
    # High-profile names
    "trump":          7, "biden":          6, "yellen":           9,
    "musk":           6, "apple":          5, "nvidia":           5,
    # Source-quality signals (if in headline)
    "breaking":       3, "alert":          3, "flash":            3,
}

# ── Types ─────────────────────────────────────────────────────────────────────

class Article(TypedDict):
    title: str
    url: str
    source: str
    published: str
    score: int
    rationale: str


# ── Fetchers ─────────────────────────────────────────────────────────────────

def _parse_published(entry: dict) -> datetime | None:
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def fetch_rss_articles() -> list[dict]:
    articles: list[dict] = []
    for feed_url in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            source_name = feed.feed.get("title", feed_url)
            for entry in feed.entries[:MAX_PER_FEED]:
                title = entry.get("title", "").strip()
                link  = entry.get("link", "").strip()
                if not title or not link:
                    continue
                pub_dt = _parse_published(entry)
                articles.append({
                    "title":     title,
                    "url":       link,
                    "source":    source_name,
                    "published": pub_dt,
                })
        except Exception as exc:
            print(f"  [news_picker] RSS fetch failed ({feed_url[:60]}…): {exc}")
        time.sleep(0.3)
    return articles


def fetch_yfinance_articles() -> list[dict]:
    articles: list[dict] = []
    for symbol in YFINANCE_TICKERS:
        try:
            ticker = yf.Ticker(symbol)
            news_items = ticker.news or []
            for item in news_items[:MAX_PER_FEED]:
                content = item.get("content", item)   # yfinance ≥0.2 nests under "content"
                title = content.get("title") or item.get("title", "")
                link  = (
                    content.get("canonicalUrl", {}).get("url")
                    or content.get("clickThroughUrl", {}).get("url")
                    or item.get("link", "")
                )
                pub_ts = content.get("pubDate") or item.get("providerPublishTime")
                pub_dt: datetime | None = None
                if isinstance(pub_ts, (int, float)):
                    pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
                elif isinstance(pub_ts, str):
                    try:
                        pub_dt = datetime.fromisoformat(pub_ts.replace("Z", "+00:00"))
                    except Exception:
                        pass

                if title and link:
                    articles.append({
                        "title":     title.strip(),
                        "url":       link.strip(),
                        "source":    f"Yahoo Finance / {symbol}",
                        "published": pub_dt,
                    })
        except Exception as exc:
            print(f"  [news_picker] yfinance fetch failed ({symbol}): {exc}")
    return articles


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(article: dict) -> int:
    title_lower = article["title"].lower()
    score = 0

    for kw, weight in KEYWORD_WEIGHTS.items():
        if kw in title_lower:
            score += weight

    # Recency bonus
    pub_dt: datetime | None = article.get("published")
    if isinstance(pub_dt, datetime):
        try:
            age_h = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
            if age_h > MAX_AGE_HOURS:
                return -1          # too old — discard
            if age_h < 1:
                score += 6
            elif age_h < 3:
                score += 4
            elif age_h < 6:
                score += 2
        except Exception:
            pass

    return score


def _is_blocked(url: str) -> bool:
    """Return True if the URL's domain is on the blocked list."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip("www.")
        return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)
    except Exception:
        return False


def _is_fetchable(url: str, timeout: int = 10) -> bool:
    """Return True if the URL responds with a 2xx status (HEAD request)."""
    try:
        resp = requests.head(
            url, headers=HEADERS, timeout=timeout, allow_redirects=True
        )
        return resp.status_code < 400
    except Exception:
        return False


def _deduplicate(articles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        key = a["title"][:80].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


# ── Claude final selection ────────────────────────────────────────────────────

def _claude_pick(candidates: list[dict]) -> dict:
    """Ask Claude to confirm the best article from the top-N candidates."""
    try:
        import anthropic
        from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

        numbered = "\n".join(
            f"{i+1}. [{a['source']}] {a['title']}"
            for i, a in enumerate(candidates)
        )
        prompt = f"""\
You are a financial editor for Wisuno, a regulated CFD broker targeting retail traders in Asia and the Middle East.

From the following news headlines, select the SINGLE article that would make the most compelling and market-relevant Instagram carousel for a CFD trading audience today.

Prioritise:
- Central bank decisions or language (Fed, ECB, BoE, BoJ)
- Major macro data surprises (CPI, NFP, GDP)
- Geopolitical shocks (tariffs, sanctions, conflicts)
- Sharp price moves in major assets (forex pairs, indices, oil, gold)

Avoid:
- Company-specific earnings unless index-moving (e.g. Apple, Nvidia)
- Opinion pieces or analysis with no new data
- Duplicate or near-duplicate stories

Headlines:
{numbered}

Reply with ONLY a JSON object — no markdown:
{{
  "choice": <number 1-{len(candidates)}>,
  "rationale": "<one sentence explaining why this is the most impactful for CFD traders>"
}}"""

        client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3, timeout=60.0)
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        data = json.loads(raw)
        idx  = int(data["choice"]) - 1
        chosen = candidates[idx]
        chosen["rationale"] = data.get("rationale", "")
        return chosen

    except Exception as exc:
        print(f"  [news_picker] Claude selection failed: {exc} — falling back to top-scored article.")
        candidates[0]["rationale"] = "Top keyword-scored article (Claude unavailable)."
        return candidates[0]


# ── Public API ────────────────────────────────────────────────────────────────

def pick_top_article(top_n: int = 10, verbose: bool = True) -> Article | None:
    """
    Fetch headlines from all sources, score them, and use Claude to pick
    the single most impactful article.

    Returns an Article dict with keys: title, url, source, published, score, rationale
    Returns None if no suitable articles are found.
    """
    if verbose:
        print("  [news_picker] Fetching RSS feeds…")
    rss_articles = fetch_rss_articles()
    if verbose:
        print(f"  [news_picker] Fetching yfinance news…")
    yf_articles = fetch_yfinance_articles()

    all_articles = _deduplicate(rss_articles + yf_articles)
    if verbose:
        print(f"  [news_picker] {len(all_articles)} unique headlines collected.")

    # Score and filter — skip blocked domains entirely
    scored = []
    for a in all_articles:
        if _is_blocked(a.get("url", "")):
            continue
        s = _score(a)
        if s > 0:
            a["score"] = s
            scored.append(a)

    if not scored:
        print("  [news_picker] No suitable articles found today.")
        return None

    scored.sort(key=lambda x: x["score"], reverse=True)
    candidates = scored[:top_n]

    if verbose:
        print(f"  [news_picker] Top {len(candidates)} candidates (by keyword score):")
        for i, a in enumerate(candidates):
            print(f"    {i+1:2d}. [{a['score']:3d}] {a['title'][:80]}")

    print("  [news_picker] Asking Claude to select the best article…")
    winner = _claude_pick(candidates)

    # Validate the winner is actually fetchable; if not, walk down the list
    ordered = [winner] + [c for c in candidates if c["url"] != winner["url"]]
    final: dict | None = None
    for candidate in ordered:
        url = candidate["url"]
        if verbose:
            print(f"  [news_picker] Checking URL accessibility: {url[:80]}")
        if _is_fetchable(url):
            final = candidate
            break
        else:
            print(f"  [news_picker] ✗ URL not fetchable, trying next candidate…")

    if final is None:
        print("  [news_picker] No fetchable article found among top candidates.")
        return None

    if verbose:
        print(f"\n  [news_picker] ✓ Selected: {final['title']}")
        print(f"               URL: {final['url']}")
        print(f"               Rationale: {final.get('rationale', '')}\n")

    return final


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    article = pick_top_article(verbose=True)
    if article:
        print(json.dumps({
            "title":     article["title"],
            "url":       article["url"],
            "source":    article["source"],
            "score":     article["score"],
            "rationale": article.get("rationale", ""),
        }, ensure_ascii=False, indent=2))
    else:
        sys.exit(1)
