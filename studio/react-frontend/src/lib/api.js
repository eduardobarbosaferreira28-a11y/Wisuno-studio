import { supabase } from './supabase'
import { toast } from 'sonner'

export async function apiFetch(endpoint, options = {}) {
  const { data: { session } } = await supabase.auth.getSession();
  
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };

  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`;
  }

  try {
    const r = await fetch(endpoint, {
      ...options,
      headers
    });
    
    if (!r.ok) {
      if (r.status === 401 || r.status === 403) {
        supabase.auth.signOut();
        window.location.href = '/login';
        throw new Error('Session expired');
      }
      const body = await r.text();
      throw new Error(`Server error ${r.status}: ${body}`);
    }

    // Attempt to parse JSON, or return text if not JSON
    const contentType = r.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await r.json();
    }
    return await r.text();
  } catch (err) {
    const msg = err.message || '';
    if (msg.toLowerCase().includes('failed to fetch') || msg.includes('NetworkError') || msg.includes('ERR_CONNECTION')) {
      toast.error('Server offline. Please ensure FastAPI is running.');
    } else {
      toast.error(msg);
    }
    throw err;
  }
}
