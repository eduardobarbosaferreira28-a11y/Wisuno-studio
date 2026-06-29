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

import base64
import json
import os
import re
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

def _score(article: dict, max_age_hours: int = MAX_AGE_HOURS,
           require_dated: bool = False) -> int:
    title_lower = article["title"].lower()
    score = 0

    for kw, weight in KEYWORD_WEIGHTS.items():
        if kw in title_lower:
            score += weight

    # Recency: discard anything older than max_age_hours. When require_dated is
    # True we ALSO discard articles whose publish date can't be parsed — without
    # a date we can't guarantee the article falls inside the window.
    pub_dt: datetime | None = article.get("published")
    if isinstance(pub_dt, datetime):
        try:
            age_h = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
            if age_h > max_age_hours:
                return -1          # too old — discard
            if age_h < 1:
                score += 6
            elif age_h < 3:
                score += 4
            elif age_h < 6:
                score += 2
        except Exception:
            if require_dated:
                return -1
    elif require_dated:
        return -1                  # no usable date — can't confirm recency

    return score


def _is_blocked(url: str) -> bool:
    """Return True if the URL's domain is on the blocked list."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip("www.")
        return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)
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


# ── Google News URL resolution ────────────────────────────────────────────────
# Google News RSS `link` values are redirect *wrappers* (news.google.com/rss/
# articles/CBMi…), not the publisher's article. A HEAD request to the wrapper
# returns 200, so the old fetchability check passed — but actually fetching it
# yields a Google interstitial page full of *other* headlines, which then got
# turned into an off-topic carousel. We must resolve the real publisher URL.

def _decode_gnews_base64(url: str) -> str | None:
    """Older-format Google News links embed the target URL in the base64 article
    id. Decode it and pull the publisher URL out of the protobuf payload."""
    m = re.search(r"/articles/([A-Za-z0-9_\-]+)", url)
    if not m:
        return None
    blob = m.group(1)
    blob += "=" * (-len(blob) % 4)          # restore base64 padding
    try:
        raw = base64.urlsafe_b64decode(blob)
    except Exception:
        return None
    text = raw.decode("latin-1", errors="ignore")
    # URL chars only — stops at the next (control-byte) protobuf field tag.
    found = re.search(r"https?://[A-Za-z0-9._~:/?#@!$&()*+,;=%\-]+", text)
    if not found:
        return None
    target = found.group(0)
    if "google.com" in target or "gstatic.com" in target:
        return None
    return target


def _scrape_gnews_target(url: str, timeout: int = 10) -> str | None:
    """Fetch the wrapper page and recover the real article URL from it."""
    from urllib.parse import urlparse
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    except Exception:
        return None
    # If Google bounced us straight to the publisher, the final URL is the article.
    if "news.google.com" not in urlparse(resp.url).netloc.lower():
        return resp.url
    html = resp.text
    # data-n-au carries the canonical target on the article shell.
    m = re.search(r'data-n-au="(https?://[^"]+)"', html)
    if m:
        return m.group(1)
    # <meta http-equiv="refresh" ... url=…>
    m = re.search(r'http-equiv=["\']refresh["\'][^>]*url=(https?://[^"\'>\s]+)', html, re.I)
    if m and "google.com" not in m.group(1):
        return m.group(1)
    # First anchor that points off Google.
    for mm in re.finditer(r'href="(https?://[^"]+)"', html):
        host = urlparse(mm.group(1)).netloc.lower()
        if not any(d in host for d in ("google.com", "gstatic.com", "youtube.com", "google.co")):
            return mm.group(1)
    return None


def _resolve_google_news_url(url: str, timeout: int = 10) -> str | None:
    """Return the real publisher URL for a Google News wrapper link, or the URL
    unchanged if it isn't a Google News link. Returns None if unresolvable."""
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return url
    if "news.google.com" not in host:
        return url                      # already a real publisher URL
    return _decode_gnews_base64(url) or _scrape_gnews_target(url, timeout)


# ── Headline ⇄ body relevance guard ───────────────────────────────────────────
# Even after resolving, the fetched page might be a consent wall, a paywall stub,
# or the wrong article. Confirm the extracted body actually matches the chosen
# headline before we spend the image/translation budget building a carousel.

_RELEVANCE_STOPWORDS: set[str] = {
    "the", "and", "for", "with", "that", "this", "from", "says", "said", "after",
    "over", "into", "amid", "will", "your", "you", "are", "but", "not", "how",
    "why", "what", "when", "who", "its", "has", "have", "was", "were", "been",
    "more", "than", "new", "now", "top", "day", "week", "year", "could", "would",
    "may", "amid", "set", "out", "off", "his", "her", "their", "them", "they",
}


def _headline_keywords(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if len(w) >= 3 and w not in _RELEVANCE_STOPWORDS}


def _body_matches_headline(title: str, body: str, min_ratio: float = 0.4) -> bool:
    """True if at least `min_ratio` of the headline's significant words appear in
    the article body. Empty keyword sets pass (we can't judge — don't block)."""
    kws = _headline_keywords(title)
    if not kws:
        return True
    body_l = body.lower()
    hits = sum(1 for k in kws if k in body_l)
    return hits / len(kws) >= min_ratio


def _resolve_and_validate(candidate: dict, timeout: int = 10,
                          verbose: bool = True) -> str | None:
    """Resolve a candidate's URL to the real article and confirm the fetched body
    matches its headline. Returns the resolved publisher URL, or None to skip."""
    from content_extractor import extract_from_url

    resolved = _resolve_google_news_url(candidate["url"], timeout=timeout)
    if not resolved:
        if verbose:
            print("  [news_picker] ✗ could not resolve Google News redirect — skipping")
        return None
    try:
        body = extract_from_url(resolved)
    except Exception as exc:
        if verbose:
            print(f"  [news_picker] ✗ fetch failed for {resolved[:70]}…: {exc}")
        return None
    if len(body) < 400:
        if verbose:
            print(f"  [news_picker] ✗ body too thin ({len(body)} chars) — skipping")
        return None
    if not _body_matches_headline(candidate["title"], body):
        if verbose:
            print("  [news_picker] ✗ article body doesn't match the headline — skipping")
        return None
    return resolved


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

def pick_top_article(top_n: int = 10, verbose: bool = True,
                     max_age_hours: int = MAX_AGE_HOURS,
                     require_dated: bool = False) -> Article | None:
    """
    Fetch headlines from all sources, score them, and use Claude to pick
    the single most impactful article.

    Args:
        max_age_hours: Discard articles older than this (recency window).
        require_dated: If True, also discard articles whose publish date can't be
                       parsed — guarantees every candidate is within the window.

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
        s = _score(a, max_age_hours=max_age_hours, require_dated=require_dated)
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

    # Resolve each candidate's real publisher URL (Google News links are
    # redirect wrappers) and confirm the fetched body actually matches the
    # headline before committing. Walk down the list until one passes; this
    # guarantees we build the *chosen* story or nothing — never an off-topic one.
    ordered = [winner] + [c for c in candidates if c["url"] != winner["url"]]
    final: dict | None = None
    for candidate in ordered:
        if verbose:
            print(f"  [news_picker] Resolving & validating: {candidate['url'][:80]}")
        resolved = _resolve_and_validate(candidate, verbose=verbose)
        if resolved:
            candidate["url"] = resolved   # hand the real article URL downstream
            final = candidate
            break

    if final is None:
        print("  [news_picker] No valid, on-topic article found among top candidates.")
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
