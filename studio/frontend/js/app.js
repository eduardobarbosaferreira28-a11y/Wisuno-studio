/**
 * app.js — Wisuno Studio client-side router & global utilities
 */

// Fallback keys if the backend setup page hasn't fully loaded them yet
const SUPABASE_URL = "https://wkfwjdwjpavgzugwcgte.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_ch--T1W0Vpg1ULGdQH8e2g_U-rNgiiF";
window.supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

/* ── Toast notifications ──────────────────────────────────── */
const toast = {
  show(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<div class="toast-dot"></div><span>${message}</span>`;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add('out');
      setTimeout(() => el.remove(), 300);
    }, duration);
  },
  success: (msg, dur) => toast.show(msg, 'success', dur),
  error:   (msg, dur) => toast.show(msg, 'error',   dur || 6000),
  info:    (msg, dur) => toast.show(msg, 'info',     dur),
};

/* ── Client-side router ───────────────────────────────────── */
const app = {
  currentPage: 'dashboard',

  pages: ['dashboard', 'setup', 'carousel', 'video'],

  navigate(page) {
    if (!this.pages.includes(page)) page = 'dashboard';
    this.currentPage = page;

    // Update page views
    document.querySelectorAll('.page-view').forEach(v => v.classList.remove('active'));
    const view = document.getElementById(`page-${page}`);
    if (view) view.classList.add('active');

    // Update nav items
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const navItem = document.getElementById(`nav-${page}`);
    if (navItem) navItem.classList.add('active');

    // Update URL hash (no reload)
    history.replaceState(null, '', `#${page}`);

    // Trigger page-specific init hooks if available
    if (page === 'setup' && window.setupPage) setupPage.onShow();
    if (page === 'dashboard' && window.dashboardPage) dashboardPage.onShow();
  },

  init() {
    // Wire nav clicks
    document.querySelectorAll('.nav-item[data-page]').forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        this.navigate(item.dataset.page);
      });
    });

    // Read initial hash
    const hash = location.hash.replace('#', '').trim();
    this.navigate(hash || 'dashboard');

    // Server health ping
    this._pingServer();
    
    // Auth Check
    this._checkAuth();
  },

  async _checkAuth() {
    const { data: { session } } = await window.supabaseClient.auth.getSession();
    if (!session) {
      window.location.href = "login.html";
    }
    
    // Wire logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', async () => {
        await window.supabaseClient.auth.signOut();
        window.location.href = "login.html";
      });
    }
  },

  async _pingServer() {
    const el = document.getElementById('server-status');
    const check = async () => {
      try {
        const r = await fetch('/health', { cache: 'no-store' });
        if (r.ok) {
          el.textContent = '● Server running';
          el.style.color = 'var(--green)';
        } else {
          el.textContent = '● Server error';
          el.style.color = 'var(--red)';
        }
      } catch {
        el.textContent = '● Offline — restart start.bat';
        el.style.color = 'var(--red)';
      }
    };
    check(); // immediate
    setInterval(check, 10000); // every 10s
  },
};

/* ── Global fetch wrapper ─────────────────────────────────── */
async function apiFetch(path, options = {}) {
  // Pull headers out separately so ...rest doesn't overwrite Content-Type
  const { headers: extraHeaders, ...rest } = options;
  
  // Attach Supabase JWT
  let authHeader = {};
  const { data: { session } } = await window.supabaseClient.auth.getSession();
  if (session) {
    authHeader = { 'Authorization': `Bearer ${session.access_token}` };
  }

  try {
    const r = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...authHeader, ...extraHeaders },
      ...rest,
    });
    if (!r.ok) {
      const body = await r.text();
      throw new Error(`Server error ${r.status}: ${body}`);
    }
    return await r.json();
  } catch (err) {
    // Distinguish "server is offline" from a real API error
    const msg = err.message || '';
    if (msg.toLowerCase().includes('failed to fetch') || msg.includes('NetworkError') || msg.includes('ERR_CONNECTION')) {
      toast.error('⚠ Server offline — please restart start.bat and refresh the page.', 8000);
    } else {
      toast.error(msg || 'Network error');
    }
    throw err;
  }
}

/* ── Init ─────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => app.init());
