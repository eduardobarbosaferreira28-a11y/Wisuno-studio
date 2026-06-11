/**
 * setup.js — Dependency checker & API key manager for Wisuno Studio
 */

const setupPage = {
  data: null,

  // Called by app.js when Setup tab is shown
  onShow() {
    if (!this.data) this.check();
  },

  async check() {
    const list = document.getElementById('dep-list');
    const keyGrid = document.getElementById('key-grid');
    const badge = document.getElementById('nav-setup-badge');

    // Show loading state
    list.innerHTML = `
      <div class="dep-item loading">
        <div class="dep-icon">⏳</div>
        <div class="dep-info"><div class="dep-name">Checking dependencies…</div></div>
        <div class="dep-status"><div class="spinner"></div></div>
      </div>`;
    badge.textContent = '…';
    badge.className = 'nav-badge';

    try {
      const data = await apiFetch('/api/setup/check');
      this.data = data;
      this._renderTools(data.tools);
      this._renderKeys(data.api_keys);
      this._updateBanner(data.summary);
    } catch {
      list.innerHTML = `<div class="dep-item fail">
        <div class="dep-icon">❌</div>
        <div class="dep-info"><div class="dep-name">Could not reach server</div>
        <div class="dep-detail">Make sure the FastAPI server is running.</div></div>
      </div>`;
    }
  },

  _renderTools(tools) {
    const list = document.getElementById('dep-list');
    const badge = document.getElementById('nav-setup-badge');

    const ICONS = {
      ffmpeg:      '🎞️',
      nodejs:      '⬡',
      hyperframes: '🎬',
      video_use:   '🎛️',
    };

    const LABELS = {
      ffmpeg:      'FFmpeg',
      nodejs:      'Node.js',
      hyperframes: 'HyperFrames',
      video_use:   'video-use (render.py)',
    };

    let allOk = true;
    let html = '';

    for (const [key, info] of Object.entries(tools)) {
      const ok = info.installed;
      if (!ok) allOk = false;

      const statusClass = ok ? 'ok' : 'fail';
      const versionLine = info.version
        ? `<div class="dep-detail">Version: <code style="font-family:monospace;font-size:11px;">${info.version.slice(0, 60)}</code></div>`
        : `<div class="dep-detail">${info.install_hint}</div>`;

      const installBtn = (!ok && info.can_auto_install)
        ? `<button class="btn btn-secondary btn-sm" onclick="setupPage.installHyperframes(this)">
             Install
           </button>`
        : (!ok ? `<a class="btn btn-ghost btn-sm" href="${this._installUrl(key)}" target="_blank">How to install</a>` : '');

      html += `
        <div class="dep-item ${statusClass}" id="dep-${key}">
          <div class="dep-icon">${ICONS[key] || '📦'}</div>
          <div class="dep-info">
            <div class="dep-name">${LABELS[key] || key}</div>
            ${versionLine}
            <div class="dep-detail" style="margin-top:4px;opacity:0.65;">Used for: ${info.required_for}</div>
          </div>
          <div class="dep-status">
            ${ok
              ? `<span class="badge badge-green">Installed</span>`
              : `<span class="badge badge-red">Missing</span>`}
            ${installBtn}
          </div>
        </div>`;
    }

    list.innerHTML = html;

    // Badge
    const totalOk = Object.values(tools).filter(t => t.installed).length;
    const total   = Object.keys(tools).length;
    badge.textContent = `${totalOk}/${total}`;
    badge.className = `nav-badge ${allOk ? 'ok' : 'warn'}`;
  },

  _renderKeys(apiKeys) {
    const grid = document.getElementById('key-grid');

    let html = '';
    for (const [key, info] of Object.entries(apiKeys)) {
      const dotClass = info.set ? 'set' : 'unset';
      const preview  = info.set
        ? `<span class="key-preview">${info.preview || '••••••••'}</span>`
        : `<span class="badge badge-red" style="font-size:10px;">Not set</span>`;

      html += `
        <div class="key-row" id="keyrow-${key}">
          <div class="key-dot ${dotClass}"></div>
          <div style="flex:1;min-width:0;">
            <div class="key-label">${info.label}</div>
            <div class="key-sub">${info.required_for}</div>
          </div>
          ${preview}
          <div class="key-input-wrap">
            <input type="password"
                   id="input-${key}"
                   placeholder="${info.set ? 'Update key…' : 'Paste key here…'}"
                   autocomplete="off"
                   spellcheck="false">
            <button class="btn btn-secondary btn-sm"
                    onclick="setupPage.saveKey('${key}')">
              Save
            </button>
          </div>
        </div>`;
    }

    grid.innerHTML = html;
  },

  _updateBanner(summary) {
    const banner = document.getElementById('setup-banner');
    const text   = document.getElementById('setup-banner-text');

    if (summary.all_tools_ok && summary.carousel_ready) {
      if (summary.video_ready) {
        banner.className = 'setup-banner all-ok visible';
        text.textContent = '✓ All systems ready — Carousel Studio and Video Studio are fully configured.';
      } else {
        banner.className = 'setup-banner visible';
        text.textContent = '⚠ Carousel Studio ready. Video Studio needs FFmpeg, Node.js, HyperFrames, and video-use.';
      }
    } else if (summary.carousel_ready) {
      banner.className = 'setup-banner visible';
      text.textContent = '⚠ Carousel Studio ready. Video Studio setup incomplete — check below.';
    } else {
      banner.className = 'setup-banner visible';
      text.textContent = '⚠ Setup incomplete — some tools or API keys are missing. See Setup page.';
    }
  },

  async saveKey(key) {
    const input = document.getElementById(`input-${key}`);
    const value = (input ? input.value : '').trim();
    if (!value) {
      toast.error('Please paste a value before saving.');
      return;
    }

    const btn = input.nextElementSibling;
    btn.disabled = true;
    btn.textContent = 'Saving…';

    try {
      await apiFetch('/api/setup/save-key', {
        method: 'POST',
        body: JSON.stringify({ key, value }),
      });
      toast.success(`${key} saved!`);
      input.value = '';
      // Refresh the display
      await this.check();
    } catch {
      btn.disabled = false;
      btn.textContent = 'Save';
    }
  },

  async installHyperframes(btn) {
    btn.disabled = true;
    btn.textContent = 'Installing…';
    toast.info('Installing HyperFrames via npm… this may take a minute.');

    try {
      await apiFetch('/api/setup/install-hyperframes', { method: 'POST' });

      // Poll for completion
      const poll = setInterval(async () => {
        try {
          const status = await apiFetch('/api/setup/install-hyperframes/status');
          if (status.state === 'done') {
            clearInterval(poll);
            toast.success('HyperFrames installed!');
            await this.check();
          } else if (status.state === 'error') {
            clearInterval(poll);
            toast.error('HyperFrames install failed. Check the console log.');
            btn.disabled = false;
            btn.textContent = 'Retry';
          }
        } catch {
          clearInterval(poll);
        }
      }, 2000);
    } catch {
      btn.disabled = false;
      btn.textContent = 'Install';
    }
  },

  _installUrl(key) {
    const urls = {
      ffmpeg:   'https://ffmpeg.org/download.html',
      nodejs:   'https://nodejs.org',
      video_use:'https://github.com/browser-use/video-use',
    };
    return urls[key] || '#';
  },
};

// The setup dependency/key check (and its banner) is triggered by app.js only for
// admins — see app._applyAccessControl(). Non-admins never run it, so the banner
// and Settings page stay hidden for them.
