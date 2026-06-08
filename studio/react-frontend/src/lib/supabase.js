import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  window.ENV?.SUPABASE_URL || import.meta.env.VITE_SUPABASE_URL || 'https://wkfwjdwjpavgzugwcgte.supabase.co',
  window.ENV?.SUPABASE_ANON_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_ch--T1W0Vpg1ULGdQH8e2g_U-rNgiiF'
)
