"""
Article content extraction — supports URL fetch or raw text passthrough.
"""
import re
import httpx
from bs4 import BeautifulSoup
from config import MAX_ARTICLE_CHARS, REQUEST_TIMEOUT
from retry_utils import retry


def extract_from_url(url: str) -> str:
    """Fetch a web page and return cleaned article body text."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def _fetch() -> httpx.Response:
        resp = httpx.get(url, headers=headers, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return resp

    try:
        # Retry only transient network errors; HTTPStatusError (4xx/5xx with a
        # response) fails fast since a 404/403 won't fix itself on retry.
        response = retry(_fetch, attempts=3, base_delay=1.0, exceptions=(httpx.RequestError,))
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code} fetching article: {url}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"Network error fetching article: {e}") from e

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "form", "noscript", "iframe", "figure"]):
        tag.decompose()

    # Prefer article/main content containers
    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"class": re.compile(r"article|content|story|post", re.I)})
        or soup.find("body")
    )

    text = article.get_text(separator="\n") if article else soup.get_text(separator="\n")
    return _clean(text)


def extract_from_text(raw: str) -> str:
    """Clean and truncate raw pasted text."""
    return _clean(raw)


def _clean(text: str) -> str:
    """Normalise whitespace and cap length."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if len(ln) > 20]   # drop short/empty lines
    cleaned = "\n".join(lines)
    if len(cleaned) > MAX_ARTICLE_CHARS:
        cleaned = cleaned[:MAX_ARTICLE_CHARS] + "\n[...truncated]"
    return cleaned.strip()
