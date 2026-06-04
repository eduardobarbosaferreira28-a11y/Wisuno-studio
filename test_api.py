import urllib.request
import json
import sys

try:
    with urllib.request.urlopen("https://wisuno-carousel-production.up.railway.app/api/history") as response:
        data = json.loads(response.read().decode())
        print("API returned history items:", len(data.get("history", [])))
        for i, h in enumerate(data.get("history", [])[:5]):
            print(f"[{i}] {h['job_id']} - {h.get('details', {}).get('topic')}")
except Exception as e:
    print("API Error:", e)
