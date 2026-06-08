import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL || 'https://wkfwjdwjpavgzugwcgte.supabase.co',
  import.meta.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_ch--T1W0Vpg1ULGdQH8e2g_U-rNgiiF'
)
