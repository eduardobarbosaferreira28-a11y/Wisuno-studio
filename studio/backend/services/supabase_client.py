import os
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_ANON_KEY

# Initialize Supabase client
# We use the ANON KEY because all operations will be authenticated via user JWT headers
if SUPABASE_URL and SUPABASE_ANON_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
else:
    supabase = None

# Trusted server-side work (storage uploads, writing the `jobs` history table) uses
# the SERVICE ROLE key, which bypasses row-level-security. The anon client above runs
# as the Postgres `anon` role and carries no user JWT, so anything it writes is at the
# mercy of whatever RLS policies happen to be on the table. Fall back to the anon
# client only if the service role key isn't configured.
_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if SUPABASE_URL and _SERVICE_ROLE_KEY:
    admin_supabase: Client = create_client(SUPABASE_URL, _SERVICE_ROLE_KEY)
else:
    admin_supabase = supabase

# Back-compat alias — this client is no longer storage-specific.
storage_supabase = admin_supabase


def upload_to_storage(bucket: str, destination_path: str, local_file_path: str, content_type: str) -> str:
    """Uploads a file to Supabase Storage and returns the public URL."""
    supabase = admin_supabase
    if not supabase:
        return ""
    try:
        with open(local_file_path, "rb") as f:
            supabase.storage.from_(bucket).upload(destination_path, f, file_options={"content-type": content_type, "upsert": "true"})
        public_url = supabase.storage.from_(bucket).get_public_url(destination_path)
        
        import urllib.parse
        from pathlib import Path
        filename = Path(local_file_path).name
        encoded_name = urllib.parse.quote(filename)
        return f"{public_url}?download={encoded_name}"
    except Exception as e:
        print(f"[supabase_client] Failed to upload {local_file_path}: {e}")
        return ""
