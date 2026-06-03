"""
Script generation — calls Claude API to produce structured carousel slide JSON.
"""
import json
import re
import anthropic

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    PROMPTS_DIR,
    MIN_SLIDES,
    MAX_SLIDES,
    DEFAULT_SLIDES,
    DISCLAIMER,
)


VALID_SLIDE_TYPES_MARKET = {
    "cover", "data_slide", "analysis_slide", "quote_slide", "chart_slide", "cta_slide",
}
VALID_SLIDE_TYPES_EDUCATIONAL = {
    "cover", "concept_slide", "steps_slide", "comparison_slide", "example_slide", "cta_slide",
}
# Backward-compat alias pointing at market types
VALID_SLIDE_TYPES = VALID_SLIDE_TYPES_MARKET


def generate_script(article_text: str, content_type: str = "market_insight") -> dict:
    """
    Send article text to Claude and return a validated carousel script dict.
    content_type: "market_insight" | "market_update" | "educational"
    """
    prompt_file = (
        "educational_prompt.txt" if content_type == "educational" else "script_prompt.txt"
    )
    prompt_template = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{min_slides}", str(MIN_SLIDES))
        .replace("{max_slides}", str(MAX_SLIDES))
        .replace("{default_slides}", str(DEFAULT_SLIDES))
        .replace("{disclaimer}", DISCLAIMER)
        .replace("{article_text}", article_text)
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip accidental markdown code fences if Claude adds them
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        script = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw output:\n{raw}") from e

    script.setdefault("content_type", content_type)
    _validate_script(script, content_type=content_type)
    return script


def _validate_script(script: dict, content_type: str = "market_insight") -> None:
    """Lightweight validation — raises ValueError on obvious schema violations."""
    required_top = {"title", "asset_tag", "caption", "hashtags", "slides"}
    missing = required_top - script.keys()
    if missing:
        raise ValueError(f"Script JSON missing fields: {missing}")

    slides = script["slides"]
    if not (MIN_SLIDES <= len(slides) <= MAX_SLIDES):
        raise ValueError(
            f"Expected {MIN_SLIDES}–{MAX_SLIDES} slides, got {len(slides)}"
        )

    types = [s.get("type") for s in slides]
    if types[0] != "cover":
        raise ValueError("First slide must be type 'cover'")
    if types[-1] != "cta_slide":
        raise ValueError("Last slide must be type 'cta_slide'")

    valid_types = (
        VALID_SLIDE_TYPES_EDUCATIONAL if content_type == "educational"
        else VALID_SLIDE_TYPES_MARKET
    )
    invalid = set(types) - valid_types
    if invalid:
        raise ValueError(f"Unknown slide type(s): {invalid}. Valid types: {valid_types}")
