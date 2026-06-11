/**
 * app.js — Wisuno Studio client-side router & global utilities
 */

// Use dynamic environment variables injected by FastAPI backend
const SUPABASE_URL = window.ENV?.SUPABASE_URL || "https://wkfwjdwjpavgzugwcgte.supabase.co";
const SUPABASE_ANON_KEY = window.ENV?.SUPABASE_ANON_KEY || "sb_publishable_ch--T1W0Vpg1ULGdQH8e2g_U-rNgiiF";
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
  isAdmin: undefined,   // resolved from /api/me after auth

  pages: ['dashboard', 'setup', 'carousel', 'video', 'higgsfield'],

  navigate(page) {
    if (!this.pages.includes(page)) page = 'dashboard';
    // Settings is admin-only; non-admins (or before role is known) get the dashboard.
    if (page === 'setup' && this.isAdmin !== true) page = 'dashboard';
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
    if (page === 'setup' && typeof setupPage !== 'undefined') setupPage.onShow();
    if (page === 'dashboard' && typeof dashboardPage !== 'undefined') dashboardPage.onShow();
    if (page === 'higgsfield' && typeof higgsfieldPage !== 'undefined') {
      if (!higgsfieldPage._initialized) {
        higgsfieldPage.init();
        higgsfieldPage._initialized = true;
      }
    }
  },

  init() {
    // Hide the admin-only Settings nav until /api/me confirms the role (no flash).
    const navSetup = document.getElementById('nav-setup');
    if (navSetup) navSetup.style.display = 'none';

    // Wire nav clicks
    document.querySelectorAll('.nav-item[data-page]').forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        this.navigate(item.dataset.page);
      });
    });

    // Read initial hash (remembered so an admin deep-linking to #setup still lands there)
    this._pendingHash = location.hash.replace('#', '').trim();
    this.navigate(this._pendingHash || 'dashboard');

    // Server health ping
    this._pingServer();

    // Auth Check
    this._checkAuth();
  },

  async _checkAuth() {
    const { data: { session } } = await window.supabaseClient.auth.getSession();
    if (!session) {
      window.location.href = "login.html?v=3";
      return;
    }

    // Wire logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', async () => {
        await window.supabaseClient.auth.signOut();
        window.location.href = "login.html?v=3";
      });
    }

    // Resolve role and gate admin-only UI (Settings nav + the setup banner).
    await this._applyAccessControl();
  },

  async _applyAccessControl() {
    let isAdmin = false;
    try {
      const me = await apiFetch('/api/me');
      isAdmin = !!me.is_admin;
    } catch (e) {
      isAdmin = false;
    }
    this.isAdmin = isAdmin;

    const navSetup = document.getElementById('nav-setup');
    if (isAdmin) {
      if (navSetup) navSetup.style.display = '';
      // Run the dependency/key check (populates the Settings badge + the banner).
      if (typeof setupPage !== 'undefined') setupPage.check();
      // Honour an admin deep-link to #setup that was blocked before the role was known.
      if (this._pendingHash === 'setup') this.navigate('setup');
    } else {
      if (navSetup) navSetup.style.display = 'none';
      const banner = document.getElementById('setup-banner');
      if (banner) banner.classList.remove('visible');
      if (this.currentPage === 'setup') this.navigate('dashboard');
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
