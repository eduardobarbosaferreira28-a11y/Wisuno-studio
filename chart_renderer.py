"""
chart_renderer.py
=================
Fetch a real, live price series for a Yahoo Finance ticker and render it as a
brand-styled chart SVG (single #FF6700 line on #0A0A0A, faint grid, orange area
gradient) matching the CPI template's chart look.

Returned as a ``data:image/svg+xml;base64,...`` URI so it drops straight into the
carousel's ``slide_images`` map — the same slot the old Gemini chart image used —
and is consumed unchanged by ``swipeable_carousel._render_chart_slide`` via
``<img>`` + ``object-fit:cover``.

On any failure (missing/invalid ticker, empty data, network error) the public
helper returns ``None`` so callers fall back to the existing static SVG.

Public API:
    chart_data_uri_for(symbol, output_path=None) -> str | None
"""
from __future__ import annotations

import base64
from pathlib import Path

from retry_utils import retry

# ── Brand tokens (mirror swipeable_carousel.py) ──────────────────────────────
_BG          = "#0A0A0A"
_ORANGE      = "#FF6700"
_GRID_STROKE = "#222222"

# ── SVG canvas — aspect (~1.1) chosen to match the chart container so
#    object-fit:cover crops as little of the line as possible. ───────────────
_VB_W = 900
_VB_H = 820
_PAD_X = 8       # keep the line just inside the left/right edges
_PAD_TOP = 90    # headroom so the peak isn't clipped by cover-crop
_PAD_BOTTOM = 90
_N_GRID = 4      # horizontal grid lines


def fetch_series(symbol: str, period: str = "6mo", interval: str = "1d") -> list[float]:
    """Return the close-price series for ``symbol`` (most recent last).

    Raises on no data so the caller can fall back. The yfinance network call is
    wrapped in ``retry`` for transient failures.
    """
    import yfinance as yf  # local import: heavy, only needed on the live path

    def _call() -> list[float]:
        hist = yf.Ticker(symbol).history(period=period, interval=interval)
        if hist is None or hist.empty or "Close" not in hist:
            raise ValueError(f"no price data for '{symbol}'")
        closes = [float(v) for v in hist["Close"].tolist() if v == v]  # drop NaN
        if len(closes) < 2:
            raise ValueError(f"insufficient price data for '{symbol}'")
        return closes

    return retry(
        _call,
        attempts=3,
        base_delay=2.0,
        exceptions=(Exception,),
    )


def render_chart_svg(points: list[float], output_path: Path | None = None) -> str:
    """Render ``points`` as a brand-styled chart SVG string.

    Reuses the visual language of the static fallback in
    swipeable_carousel._render_chart_slide (orange line + ``og2`` area gradient +
    faint horizontal grid), but plots the real data instead of a fixed curve.
    """
    n = len(points)
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0  # avoid div-by-zero on a flat series

    plot_top = _PAD_TOP
    plot_bottom = _VB_H - _PAD_BOTTOM
    plot_h = plot_bottom - plot_top
    plot_left = _PAD_X
    plot_w = _VB_W - 2 * _PAD_X

    coords: list[tuple[float, float]] = []
    for i, val in enumerate(points):
        x = plot_left + (plot_w * i / (n - 1))
        # higher price -> smaller y (SVG y grows downward)
        y = plot_bottom - ((val - lo) / span) * plot_h
        coords.append((round(x, 1), round(y, 1)))

    line_d = "M" + " L".join(f"{x},{y}" for x, y in coords)
    area_d = f"{line_d} L{coords[-1][0]},{_VB_H} L{coords[0][0]},{_VB_H} Z"

    grid_lines = ""
    for g in range(1, _N_GRID + 1):
        gy = round(plot_top + plot_h * g / (_N_GRID + 1), 1)
        grid_lines += (
            f'<line x1="0" y1="{gy}" x2="{_VB_W}" y2="{gy}" '
            f'stroke="{_GRID_STROKE}" stroke-width="1"/>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_VB_W} {_VB_H}" '
        f'preserveAspectRatio="xMidYMid slice">'
        f'<defs>'
        f'<linearGradient id="og2" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{_ORANGE}" stop-opacity="0.3"/>'
        f'<stop offset="100%" stop-color="{_ORANGE}" stop-opacity="0"/>'
        f'</linearGradient>'
        f'</defs>'
        f'<rect x="0" y="0" width="{_VB_W}" height="{_VB_H}" fill="{_BG}"/>'
        f'{grid_lines}'
        f'<path d="{area_d}" fill="url(#og2)"/>'
        f'<path d="{line_d}" fill="none" stroke="{_ORANGE}" stroke-width="4" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(svg, encoding="utf-8")
    return svg


def svg_to_data_uri(svg: str) -> str:
    """Encode an SVG string as an inline ``data:image/svg+xml;base64`` URI."""
    b64 = base64.b64encode(svg.encode("utf-8")).decode()
    return f"data:image/svg+xml;base64,{b64}"


def chart_data_uri_for(symbol: str, output_path: Path | None = None) -> str | None:
    """Fetch live data for ``symbol`` and return a brand chart data URI.

    Returns ``None`` on any failure (empty/invalid symbol, no data, network
    error) so callers fall back to the static SVG. Never raises.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return None
    try:
        points = fetch_series(symbol)
        svg = render_chart_svg(points, output_path)
        return svg_to_data_uri(svg)
    except Exception as exc:  # noqa: BLE001 — deliberately swallow; caller falls back
        print(f"        WARNING: live chart for '{symbol}' failed: {exc}")
        return None
