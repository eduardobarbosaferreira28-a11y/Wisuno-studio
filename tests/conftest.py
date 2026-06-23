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
