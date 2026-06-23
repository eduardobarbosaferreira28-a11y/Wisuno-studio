"""Render tests for swipeable_carousel.build_swipeable_html.

Guards the CLAUDE.md ground-truth rules: every slide carries the disclaimer and
the embedded logo, and all core slide types render without error.
"""
import config
from swipeable_carousel import build_swipeable_html

# Substring of config.DISCLAIMER with no HTML-escapable chars (avoids the "&"
# in "FSA & FSC" which renders as "&amp;").
_DISCLAIMER_FRAGMENT = "CFD trading carries a high level of risk"


def test_disclaimer_fragment_matches_config():
    # The renderer keeps its own per-language disclaimer table; make sure the EN
    # copy still matches config.DISCLAIMER so this test stays meaningful.
    assert _DISCLAIMER_FRAGMENT in config.DISCLAIMER


def test_disclaimer_on_every_slide(sample_script):
    html = build_swipeable_html(sample_script, {})
    n_slides = len(sample_script["slides"])
    assert html.count(_DISCLAIMER_FRAGMENT) == n_slides


def test_logo_embedded_as_data_uri(sample_script):
    html = build_swipeable_html(sample_script, {})
    assert "data:image/png;base64," in html


def test_all_slide_types_render(sample_script):
    html = build_swipeable_html(sample_script, {})
    assert html.lstrip().startswith("<!DOCTYPE html>")
    # One slide frame per slide.
    assert html.count('class="slide-frame"') == len(sample_script["slides"])
    # Content from representative slide types made it into the output.
    assert "THE INFLATION MONSTER RETURNS" in html
    assert "By The Numbers" in html
    assert "Wisuno Market Desk" in html


def test_cover_image_embedded_when_provided(sample_script):
    fake_uri = "data:image/jpeg;base64,AAAA"
    html = build_swipeable_html(sample_script, {1: fake_uri})
    assert fake_uri in html


def test_localized_disclaimer_for_pt_br(sample_script):
    html = build_swipeable_html(sample_script, {}, language="pt-BR")
    assert "O trading de CFDs envolve um alto nível de risco" in html
