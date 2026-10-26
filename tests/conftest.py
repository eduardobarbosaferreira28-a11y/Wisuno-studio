"""
tests/conftest.py
=================
Shared fixtures + import-path setup for the Wisuno Studio test suite.

All tests run fully offline — no fixture here makes a real Anthropic/Gemini/HTTP
call. Tests that exercise AI code paths inject a FakeAnthropicClient.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── Import-path setup ──────────────────────────────────────────────────────────
# Mirror app.py / carousel_service.py: project root (for html_carousel, config,
# the `studio.backend.*` package) AND studio/backend (for `routers`, `services`,
# `dependencies` short imports) both need to be importable.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "studio" / "backend"
for _p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Fake Anthropic client ───────────────────────────────────────────────────────


class _FakeContentBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeContentBlock(text)]


class FakeMessages:
    """Returns queued responses in order; records each create() call."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeAnthropicClient ran out of queued responses")
        return _FakeMessage(self._responses.pop(0))


class FakeAnthropicClient:
    def __init__(self, responses: list[str]):
        self.messages = FakeMessages(responses)


@pytest.fixture
def fake_anthropic():
    """Factory: fake_anthropic([resp1, resp2, ...]) -> FakeAnthropicClient."""

    def _make(responses: list[str]) -> FakeAnthropicClient:
        return FakeAnthropicClient(responses)

    return _make


# ── Sample carousel script (covers the core slide types) ─────────────────────────


@pytest.fixture
def sample_script() -> dict:
    return {
        "title": "The Inflation Monster Returns: CPI Hits 3.8%",
        "caption": "April CPI just came in at 3.8% — hotter than expected.",
        "hashtags": ["inflation", "CPI", "wisuno"],
        "content_type": "market_insight",
        "slides": [
            {
                "slide_number": 1,
                "type": "cover",
                "headline": "THE INFLATION MONSTER RETURNS",
                "subheadline": "April CPI hits 3.8%.",
                "asset_tag": "US CPI",
                "background_image_description": "Dark cinematic dollar bill in flames.",
            },
            {
                "slide_number": 2,
                "type": "data_slide",
                "asset_tag": "US CPI",
                "section_headline": "By The Numbers",
                "data_points": [
                    {"label": "April CPI (YoY)", "value": "3.8%", "direction": "UP"},
                    {"label": "Core CPI", "value": "2.8%", "direction": "UP"},
                    {"label": "Rate cut odds", "value": "~2%", "direction": "DOWN"},
                ],
                "takeaway_line": "The heat is spreading beyond the pump.",
            },
            {
                "slide_number": 3,
                "type": "analysis_slide",
                "asset_tag": "MARKET ANALYSIS",
                "analysis_paragraphs": [
                    "Energy accounted for 40% of the total CPI increase.",
                    "Core CPI still ticked up to 2.8%.",
                ],
            },
            {
                "slide_number": 4,
                "type": "quote_slide",
                "asset_tag": "FED CHAIR",
                "quote_text": "The era of compounding supply shocks is here.",
                "quote_attribution": "Wisuno Market Desk",
                "rhetorical_question": "Can the Fed navigate this?",
            },
            {
                "slide_number": 5,
                "type": "chart_slide",
                "asset_tag": "PRICE ACTION",
                "chart_asset": "US CPI",
                "chart_type": "line_chart",
                "chart_caption": "CPI trending higher since January.",
            },
            {
                "slide_number": 6,
                "type": "cta_slide",
            },
        ],
    }


# ── Network guard ───────────────────────────────────────────────────────────────
# Tests must never make live calls (AGENTS.md rule 3). Any connection or DNS lookup
# to a non-loopback host fails the test, even if the code under test swallows the
# error, because the attempt is recorded and asserted on at teardown. Tests of the
# guard itself request `network_attempts` and clear it after asserting.

_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "0.0.0.0", "testserver"}


class NetworkBlockedError(RuntimeError):
    """Raised when a test tries to reach a non-loopback host."""


def _is_local(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    if host is None:
        return True
    return host in _LOCAL_HOSTS or str(host).startswith("127.")


@pytest.fixture(autouse=True)
def network_attempts(monkeypatch):
    import socket

    attempts: list[str] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def _check(address) -> None:
        # AF_UNIX addresses are str paths; AF_INET/INET6 are tuples (host, port, ...).
        host = address[0] if isinstance(address, tuple) else None
        if isinstance(address, tuple) and not _is_local(host):
            attempts.append(str(host))
            raise NetworkBlockedError(f"Test attempted a live network call to {host!r}; mock it.")

    def guarded_connect(self, address):
        _check(address)
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        _check(address)
        return real_connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not _is_local(host):
            attempts.append(str(host))
            raise NetworkBlockedError(f"Test attempted a DNS lookup for {host!r}; mock it.")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield attempts
    assert not attempts, f"Live network access attempted during test: {attempts}"
