/**
 * carousel.js — Wisuno Carousel Studio
 * Full implementation for Phase 2
 */

const LANGUAGES = [
  { code: 'en',    name: 'English',            flag: '🇬🇧', locked: true  },
  { code: 'zh-TW', name: 'Traditional Chinese', flag: '🇹🇼', locked: false },
  { code: 'zh-CN', name: 'Simplified Chinese',  flag: '🇨🇳', locked: false },
  { code: 'th',    name: 'Thai',                flag: '🇹🇭', locked: false },
  { code: 'sw',    name: 'Kiswahili',           flag: '🇰🇪', locked: false },
  { code: 'pt-BR', name: 'Portuguese (Brazil)', flag: '🇧🇷', locked: false },
];

const CONTENT_TYPES = [
  { value: 'market_insight', label: 'Market Insight'  },
  { value: 'promotional',    label: 'Promotional'     },
  { value: 'market_update',  label: 'Market Update'   },
  { value: 'educational',    label: 'Educational'     },
];

const STEP_LABELS = [
  'Fetch & extract article',
  'Generate script with AI',
  'Generate images',
  'Translate to selected languages',
  'Build carousel files',
];

const STEP_SUBS = [
  'Reading the article from URL or pasted text…',
  'Claude is writing slide content…',
  'Gemini is generating background images…',
  'Translating slides to each language…',
  'Assembling the final HTML carousel files…',
];

/* ── State ────────────────────────────────────────────────────────────────── */
const state = {
  inputMode:    'url',           // 'url' | 'text'
  numSlides:    6,
  contentType:  'market_insight',
  skipImages:   false,
  languages:    new Set(['en']), // always en
  jobId:        null,
  pollTimer:    null,
};

/* ── Carousel page controller ─────────────────────────────────────────────── */
const carouselPage = {

  init() {
    const page = document.getElementById('page-carousel');
    if (!page) return;
    page.innerHTML = this._buildHTML();
    this._bindEvents();
  },

  onShow() {
    // The daily auto-pick spends a Claude call, so it's admin-only (matches the
    // backend gate on /api/carousel/daily). Reveal it once the role is known.
    const daily = document.getElementById('daily-section');
    if (daily) daily.style.display = (app.isAdmin === true) ? '' : 'none';
  },

  /* ── HTML Template ──────────────────────────────────────────────────────── */

  _buildHTML() {
    const langHTML = LANGUAGES.map(l => `
      <div class="lang-check ${l.locked ? 'locked selected' : 'clickable'}" id="lc-${l.code}" data-lang="${l.code}" title="${l.name}">
        <div class="lang-check-mark">✓</div>
        <span class="lang-flag">${l.flag}</span>
        <span class="lang-code">${l.code}</span>
      </div>`).join('');

    const ctypeHTML = CONTENT_TYPES.map(ct =>
      `<option value="${ct.value}" ${ct.value === 'market_insight' ? 'selected' : ''}>${ct.label}</option>`
    ).join('');

    const stepsHTML = STEP_LABELS.map((lbl, i) => `
      <div class="p-step" id="p-step-${i}">
        <div class="p-dot">${i + 1}</div>
        <div class="p-body">
          <div class="p-label">${lbl}</div>
          <div class="p-sub" id="p-sub-${i}">Waiting…</div>
        </div>
      </div>`).join('');

    return `
      <div class="page-header">
        <div class="header-tag">Tool</div>
        <h1>Carousel Studio</h1>
        <p>Turn any news article or text into a branded Instagram carousel in up to 6 languages.</p>
      </div>

      <!-- ── Input card ────────────────────────────────────── -->
      <div class="card" id="carousel-input-card">

        <!-- Daily auto-pick (admin only — shown by onShow) -->
        <div id="daily-section" style="display:none;">
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:10px;">
            No article handy? Let Wisuno pick today's most market-moving financial story and build a carousel from it — using the options below.
          </div>
          <button class="btn btn-secondary" id="btn-daily" style="width:100%;padding:12px;" onclick="carouselPage.generateDaily()">
            ✨ Generate from today's top story
          </button>
          <div id="daily-article" style="display:none;font-size:12px;color:var(--text-muted);margin-top:10px;line-height:1.5;"></div>
          <div class="divider"></div>
        </div>

        <!-- Input mode tabs -->
        <div class="tabs mb-16">
          <button class="tab active" id="tab-url"  onclick="carouselPage.setMode('url')">🔗 Article URL</button>
          <button class="tab"        id="tab-text" onclick="carouselPage.setMode('text')">📋 Paste Text</button>
        </div>

        <!-- URL panel -->
        <div class="tab-panel active" id="panel-url">
          <div class="form-group">
            <label class="form-label">Article URL</label>
            <input
              id="c-url"
              type="url"
              class="form-input"
              placeholder="https://reuters.com/markets/…"
              autocomplete="off"
            >
          </div>
        </div>

        <!-- Text panel -->
        <div class="tab-panel" id="panel-text">
          <div class="form-group">
            <label class="form-label">Article Text</label>
            <textarea
              id="c-text"
              class="form-input"
              rows="5"
              placeholder="Paste the full article body here. Include the headline and body text for best results…"
              style="resize:vertical; min-height:120px;"
            ></textarea>
          </div>
        </div>

        <div class="divider"></div>

        <!-- Options -->
        <div class="card-title mb-12">Options</div>
        <div class="options-grid">
          <div class="option-item">
            <label>Number of slides</label>
            <div class="slide-stepper">
              <button class="stepper-btn" id="slides-down" onclick="carouselPage.changeSlides(-1)">−</button>
              <div class="stepper-val" id="slides-val">6</div>
              <button class="stepper-btn" id="slides-up" onclick="carouselPage.changeSlides(1)">+</button>
            </div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:6px;">Min 4 · Max 8</div>
          </div>
          <div class="option-item">
            <label>Content type</label>
            <select id="c-content-type" class="form-select" onchange="state.contentType=this.value">
              ${ctypeHTML}
            </select>
          </div>
        </div>

        <div class="toggle-row">
          <div>
            <div class="toggle-label">Skip image generation</div>
            <div class="toggle-sub">Faster — build text-only slides (no Gemini images)</div>
          </div>
          <label class="toggle">
            <input type="checkbox" id="c-skip-images" onchange="state.skipImages=this.checked">
            <div class="toggle-track"></div>
          </label>
        </div>

        <div class="divider"></div>

        <!-- Language selector -->
        <div class="card-title mb-12">Languages
          <span style="font-size:11px;font-weight:400;color:var(--text-muted);margin-left:8px;">English is always included</span>
        </div>
        <div class="lang-grid">${langHTML}</div>

        <!-- Generate button -->
        <button class="btn btn-primary" id="btn-generate" style="width:100%;padding:14px;" onclick="carouselPage.generate()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
          Generate Carousel
        </button>
      </div>

      <!-- ── Progress card ──────────────────────────────────── -->
      <div class="card" id="carousel-progress-card" style="display:none;">
        <div class="flex justify-between items-center mb-20">
          <div class="card-title" style="margin-bottom:0">Generating…</div>
          <button class="btn btn-ghost btn-sm" onclick="carouselPage.cancel()">Cancel</button>
        </div>
        <div class="progress-steps">
          ${stepsHTML}
        </div>
      </div>

      <!-- ── Results card ───────────────────────────────────── -->
      <div class="card" id="carousel-results-card" style="display:none;">
        <div class="flex justify-between items-center mb-20">
          <div>
            <div class="card-title" style="margin-bottom:4px;">✅ Carousel Ready</div>
            <div style="font-size:12px;color:var(--text-muted);">Click "Open Preview" to view in browser, or download the HTML file.</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="carouselPage.reset()">
            ↩ New Carousel
          </button>
        </div>
        <div class="result-grid" id="result-grid"></div>
      </div>

      <!-- ── Error card ──────────────────────────────────────── -->
      <div class="card" id="carousel-error-card" style="display:none;">
        <div class="card-title" style="color:var(--red);margin-bottom:12px;">⚠ Generation Failed</div>
        <div class="error-panel">
          <strong id="error-msg"></strong>
          <pre id="error-detail"></pre>
        </div>
        <button class="btn btn-secondary" style="margin-top:16px;" onclick="carouselPage.reset()">← Try Again</button>
      </div>
    `;
  },

  /* ── Event binding ─────────────────────────────────────────────────────── */

  _bindEvents() {
    // Language tiles — plain divs, no checkbox, no double-fire
    document.querySelectorAll('.lang-check.clickable').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const code = el.dataset.lang;
        if (!code) return;
        if (state.languages.has(code)) {
          state.languages.delete(code);
          el.classList.remove('selected');
        } else {
          state.languages.add(code);
          el.classList.add('selected');
        }
      });
    });
  },

  /* ── Tab switching ─────────────────────────────────────────────────────── */

  setMode(mode) {
    state.inputMode = mode;
    ['url', 'text'].forEach(m => {
      document.getElementById(`tab-${m}`)?.classList.toggle('active', m === mode);
      document.getElementById(`panel-${m}`)?.classList.toggle('active', m === mode);
    });
  },

  /* ── Slide stepper ─────────────────────────────────────────────────────── */

  changeSlides(delta) {
    state.numSlides = Math.min(8, Math.max(4, state.numSlides + delta));
    document.getElementById('slides-val').textContent = state.numSlides;
    document.getElementById('slides-down').disabled = state.numSlides <= 4;
    document.getElementById('slides-up').disabled   = state.numSlides >= 8;
  },

  /* ── Generate ──────────────────────────────────────────────────────────── */

  async generate() {
    const url  = document.getElementById('c-url')?.value.trim();
    const text = document.getElementById('c-text')?.value.trim();

    if (state.inputMode === 'url' && !url) {
      toast.error('Please paste an article URL first.');
      document.getElementById('c-url')?.focus();
      return;
    }
    if (state.inputMode === 'text' && !text) {
      toast.error('Please paste the article text first.');
      document.getElementById('c-text')?.focus();
      return;
    }

    const langs = [...state.languages];

    // Show progress card
    this._showCard('progress');
    this._resetSteps();

    const btn = document.getElementById('btn-generate');
    if (btn) { btn.disabled = true; btn.textContent = 'Generating…'; }

    try {
      const result = await apiFetch('/api/carousel/run', {
        method: 'POST',
        body: JSON.stringify({
          url:          state.inputMode === 'url'  ? url  : null,
          text:         state.inputMode === 'text' ? text : null,
          num_slides:   state.numSlides,
          content_type: state.contentType,
          skip_images:  state.skipImages,
          languages:    langs,
        }),
      });

      state.jobId = result.job_id;
      toast.info(`Job started (${result.job_id}) — generating for ${result.languages.length} language(s)…`);
      this._startPolling();

    } catch {
      this._showCard('input');
      if (btn) { btn.disabled = false; btn.textContent = 'Generate Carousel'; }
    }
  },

  /* ── Daily auto-pick ───────────────────────────────────────────────────── */

  async generateDaily() {
    const langs = [...state.languages];
    const btn = document.getElementById('btn-daily');
    if (btn) { btn.disabled = true; btn.textContent = '🔎 Finding today\'s top story…'; }
    toast.info('Scanning financial headlines and picking the top story…');

    try {
      const result = await apiFetch('/api/carousel/daily', {
        method: 'POST',
        body: JSON.stringify({
          num_slides:   state.numSlides,
          content_type: state.contentType,
          skip_images:  state.skipImages,
          languages:    langs,
        }),
      });

      state.jobId = result.job_id;

      // Surface what was picked, then run the same progress UI as a manual job.
      const a = result.article || {};
      this._showCard('progress');
      this._resetSteps();
      const info = document.getElementById('daily-article');
      if (info && a.title) {
        info.style.display = '';
        info.innerHTML = `📰 <strong>${a.title}</strong><br>${a.source || ''}` +
          (a.rationale ? `<br><em>${a.rationale}</em>` : '');
      }
      toast.success(`Picked: ${a.title || 'top story'} — generating…`);
      this._startPolling();

    } catch {
      // apiFetch already toasts the error (e.g. 404 no article, 403 not admin).
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '✨ Generate from today\'s top story'; }
    }
  },

  /* ── Polling ───────────────────────────────────────────────────────────── */

  _startPolling() {
    this._stopPolling();
    state.pollTimer = setInterval(() => this._poll(), 1500);
  },

  _stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  },

  async _poll() {
    if (!state.jobId) return;
    try {
      const data = await apiFetch(`/api/carousel/status/${state.jobId}`);
      this._updateSteps(data.steps);

      if (data.status === 'done') {
        this._stopPolling();
        this._showResults(data.files);
      } else if (data.status === 'error') {
        this._stopPolling();
        this._showError(data.error || 'Unknown error');
      }
    } catch {
      // network error — keep polling
    }
  },

  /* ── Step display ──────────────────────────────────────────────────────── */

  _resetSteps() {
    STEP_LABELS.forEach((_, i) => {
      const el  = document.getElementById(`p-step-${i}`);
      const sub = document.getElementById(`p-sub-${i}`);
      if (el)  el.className = 'p-step';
      if (sub) sub.textContent = 'Waiting…';
    });
  },

  _updateSteps(steps) {
    steps.forEach((step, i) => {
      const el  = document.getElementById(`p-step-${i}`);
      const sub = document.getElementById(`p-sub-${i}`);
      if (!el) return;
      el.className = `p-step ${step.status}`;
      if (sub) {
        if (step.status === 'running') sub.textContent = STEP_SUBS[i];
        else if (step.status === 'done') sub.textContent = step.note || '✓ Done';
        else if (step.status === 'error') sub.textContent = step.error || 'Failed';
        else sub.textContent = 'Waiting…';
      }
    });
  },

  /* ── Results ───────────────────────────────────────────────────────────── */

  _showResults(files) {
    state._resultFiles = files; // store for preview modal
    const grid = document.getElementById('result-grid');
    if (!grid) return;

    const cards = Object.entries(files).map(([lang, info]) => `
      <div class="result-card">
        <div class="result-card-header">
          <span class="result-flag">${info.flag}</span>
          <div>
            <div class="result-lang-name">${info.language_name}</div>
            <div style="font-size:11px;color:var(--text-muted);">Code: ${lang}</div>
          </div>
          <span class="result-size">${info.size_kb} KB</span>
        </div>
        <div class="result-actions">
          <button class="btn btn-primary" onclick="previewModal.open('${state.jobId}', '${lang}')" style="text-align:center;display:block;width:100%;">
            👁 Preview
          </button>
          <a class="btn btn-secondary" href="${info.carousel_url}" download style="text-align:center;text-decoration:none;display:block;">
            ⬇ Download HTML
          </a>
          <button class="btn btn-ghost btn-copy" onclick="carouselPage.copyCaption('${lang}', '${info.caption_text_url}', this)">
            📋 Copy Caption
          </button>
        </div>
      </div>
    `).join('');

    grid.innerHTML = cards;
    this._showCard('results');
    toast.success('Carousel generated successfully!');
  },

  _showError(msg) {
    const errMsg    = document.getElementById('error-msg');
    const errDetail = document.getElementById('error-detail');
    if (errMsg)    errMsg.textContent    = msg;
    if (errDetail) errDetail.textContent = '';
    this._showCard('error');
    toast.error('Generation failed — see details below.', 8000);
  },

  /* ── Copy caption ─────────────────────────────────────────────────────── */

  async copyCaption(lang, url, btn) {
    try {
      const text = await fetch(url).then(r => r.text());
      await navigator.clipboard.writeText(text);
      btn.textContent = '✓ Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = '📋 Copy Caption';
        btn.classList.remove('copied');
      }, 2500);
    } catch {
      toast.error('Could not copy — try downloading the HTML instead.');
    }
  },

  /* ── Helpers ───────────────────────────────────────────────────────────── */

  _showCard(which) {
    ['input', 'progress', 'results', 'error'].forEach(n => {
      const el = document.getElementById(`carousel-${n}-card`);
      if (el) el.style.display = n === which ? '' : 'none';
    });
  },

  cancel() {
    this._stopPolling();
    state.jobId = null;
    this.reset();
    toast.info('Cancelled.');
  },

  reset() {
    this._stopPolling();
    state.jobId = null;
    const btn = document.getElementById('btn-generate');
    if (btn) { btn.disabled = false; btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      Generate Carousel`; }
    this._showCard('input');
  },
};

/* ── Preview Modal Controller ─────────────────────────────────────────────── */
const previewModal = {
  _jobId: null,
  _activeLang: null,
  _files: null,
  _captionCache: {},

  open(jobId, lang) {
    this._jobId = jobId;
    this._files = state._resultFiles || {};
    this._captionCache = {};
    
    // Build language tabs
    const tabsEl = document.getElementById('preview-lang-tabs');
    if (!tabsEl) return;
    const langs = Object.keys(this._files);
    tabsEl.innerHTML = langs.map(lc => {
      const info = this._files[lc];
      return `<button class="modal-lang-tab ${lc === lang ? 'active' : ''}" onclick="previewModal.switchLang('${lc}')">${info.flag} ${info.language_name}</button>`;
    }).join('');

    this.switchLang(lang);
    const modal = document.getElementById('preview-modal');
    if (modal) modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  },

  async switchLang(lang) {
    this._activeLang = lang;
    
    // Update active tab
    document.querySelectorAll('.modal-lang-tab').forEach(tab => {
      tab.classList.toggle('active', tab.textContent.includes(this._files[lang]?.language_name));
    });

    // Update title
    const title = document.getElementById('preview-modal-title');
    if (title) title.textContent = `Preview — ${this._files[lang]?.language_name || lang}`;

    // Load iframe
    const iframe = document.getElementById('preview-iframe');
    if (iframe) iframe.src = `/api/carousel/preview/${this._jobId}/${lang}`;

    // Load caption
    const captionEl = document.getElementById('preview-caption-text');
    if (captionEl) captionEl.textContent = 'Loading caption...';
    
    try {
      if (!this._captionCache[lang]) {
        const text = await fetch(`/api/carousel/caption/${this._jobId}/${lang}`).then(r => r.text());
        this._captionCache[lang] = text;
      }
      if (captionEl) captionEl.textContent = this._captionCache[lang];
    } catch {
      if (captionEl) captionEl.textContent = 'Could not load caption.';
    }
  },

  async copyCaption() {
    const lang = this._activeLang;
    if (!lang) return;
    try {
      let text = this._captionCache[lang];
      if (!text) {
        text = await fetch(`/api/carousel/caption/${this._jobId}/${lang}`).then(r => r.text());
        this._captionCache[lang] = text;
      }
      await navigator.clipboard.writeText(text);
      toast.success('Caption copied to clipboard!');
    } catch {
      toast.error('Could not copy caption.');
    }
  },

  download() {
    const iframe = document.getElementById('preview-iframe');
    if (iframe && iframe.contentWindow && typeof iframe.contentWindow.downloadAllSlides === 'function') {
      iframe.contentWindow.downloadAllSlides();
    } else {
      toast.error('Preview not fully loaded yet. Please wait a moment.');
    }
  },

  close() {
    const modal = document.getElementById('preview-modal');
    if (modal) modal.classList.remove('active');
    const iframe = document.getElementById('preview-iframe');
    if (iframe) iframe.src = 'about:blank';
    document.body.style.overflow = '';
  },
};

/* ── Register with app router ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  carouselPage.init();
  // Hook into app.navigate so onShow is called when the tab opens
  const origNav = app.navigate.bind(app);
  app.navigate = (page) => {
    origNav(page);
    if (page === 'carousel') carouselPage.onShow();
  };

  // Close modal on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const modal = document.getElementById('preview-modal');
      if (modal && modal.classList.contains('active')) {
        previewModal.close();
      }
    }
  });
});
