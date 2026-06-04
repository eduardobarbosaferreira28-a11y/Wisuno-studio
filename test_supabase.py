import os
from supabase import create_client

SUPABASE_URL = "https://wkfwjdwjpavgzugwcgte.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_ch--T1W0Vpg1ULGdQH8e2g_U-rNgiiF"

client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

try:
    print("Testing select...")
    res = client.table("jobs").select("*").limit(5).execute()
    print("Select successful:", res.data)
except Exception as e:
    print("Select failed:", e)

try:
    print("\nTesting insert...")
    import uuid
    job_id = str(uuid.uuid4())
    res = client.table("jobs").insert({
        "id": job_id,
        "job_type": "carousel",
        "status": "done",
        "details": {"topic": "Test Topic"}
    }).execute()
    print("Insert successful:", res.data)
except Exception as e:
    print("Insert failed:", e)
