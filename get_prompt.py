import sys
import json
from pathlib import Path
sys.path.append(r"C:\Users\Eduardo\Desktop\Triache\Marketing\wisuno-carousel")
from canva_builder import generate_canva_prompt, CanvaDesignSpec, SlideSpec

spec_path = Path("C:/Users/Eduardo/Desktop/Triache/Marketing/wisuno-carousel/output/iran-ceasefire-shakes-global-markets/canva_spec.json")
with open(spec_path, "r", encoding="utf-8") as f:
    d = json.load(f)

slides = []
for s in d["slides"]:
    slides.append(SlideSpec(
        slide_number=s["slide_number"],
        slide_type=s["type"],
        text_elements=s["text_elements"],
        background_asset_url=s["background_asset_url"],
        slide_image={"local_path": s["slide_image_path"], "url": s["slide_image_url"]} if s.get("slide_image_path") else None,
        layout={}
    ))

spec = CanvaDesignSpec(
    title=d["title"],
    market_tag=d["market_tag"],
    num_pages=d["num_pages"],
    canvas_width=1080,
    canvas_height=1350,
    meme_local_path=d.get("meme_path"),
    meme_url=d.get("meme_url"),
    slides=slides
)

canva_prompt = generate_canva_prompt(spec)
print(">>>BEGIN<<<")
print(canva_prompt)
print(">>>END<<<")
