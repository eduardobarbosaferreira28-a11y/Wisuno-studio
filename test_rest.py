import urllib.request
import json

SUPABASE_URL = "https://wkfwjdwjpavgzugwcgte.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_ch--T1W0Vpg1ULGdQH8e2g_U-rNgiiF"

url = f"{SUPABASE_URL}/rest/v1/jobs?select=*"
req = urllib.request.Request(url, headers={
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json"
})

try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print("Rows found in Supabase:", len(data))
        for i, row in enumerate(data[:5]):
            print(f"Row {i}: id={row.get('id')}, type={row.get('job_type')}, status={row.get('status')}")
            print(f"       details={row.get('details')}")
except Exception as e:
    print("Error querying Supabase:", e)
    if hasattr(e, 'read'):
        print(e.read().decode())
