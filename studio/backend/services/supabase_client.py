import os
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_ANON_KEY

# Initialize Supabase client
# We use the ANON KEY because all operations will be authenticated via user JWT headers
if SUPABASE_URL and SUPABASE_ANON_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
else:
    supabase = None
