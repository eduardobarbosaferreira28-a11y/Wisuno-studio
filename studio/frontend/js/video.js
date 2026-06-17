/**
 * video.js — Wisuno Video Studio (Phase 3)
 * Upload → Transcribe → AI Cuts → Review → Render
 */

const VIDEO_STEP_LABELS = [
  'Probe video',
  'Transcribe audio (ElevenLabs Scribe)',
  'Pack transcript',
  'AI cut analysis (Claude)',
  'Waiting for your approval',
  'Render final video',
];

const VIDEO_STEP_SUBS = [
  'Reading resolution, duration and frame rate…',
  'Uploading audio to ElevenLabs Scribe for word-level transcription…',
  'Grouping transcript into phrase-level timeline…',
  'Claude is reading the transcript and selecting the best cuts…',
  'Review and approve the proposed cuts below…',
  'FFmpeg is extracting, grading and concatenating segments…',
];

const GRADE_PRESETS = [
  { value: 'neutral_punch',  label: 'Neutral Punch — light contrast, clean'   },
  { value: 'warm_cinematic', label: 'Warm Cinematic — retro, teal/orange'      },
  { value: 'subtle',         label: 'Subtle — barely perceptible cleanup'      },
  { value: 'none',           label: 'No Grade — straight copy'                 },
  { value: 'auto',           label: 'Auto — per-segment data-driven correction' },
];

const BEAT_COLORS = {
  HOOK:       '#FF6700',
  POINT:      '#3b82f6',
  EXAMPLE:    '#22c55e',
  INSIGHT:    '#a855f7',
  TRANSITION: '#64748b',
  CTA:        '#f59e0b',
  CLOSING:    '#ec4899',
};

/* ── State ─────────────────────────────────────────────────────────────────── */
const vState = {
  jobId:        null,
  pollTimer:    null,
  proposedCuts: [],   // from AI
  editedCuts:   [],   // user-editable copy
  failedStep:   null, // index of failed step
};

/* ── Page controller ───────────────────────────────────────────────────────── */
const videoPage = {

  init() {
    const page = document.getElementById('page-video');
    if (!page) return;
    page.innerHTML = this._buildHTML();
    this._bindEvents();
  },

  /* ── HTML ─────────────────────────────────────────────────────────────────── */

  _buildHTML() {
    const gradeHTML = GRADE_PRESETS.map(g =>
      `<option value="${g.value}" ${g.value === 'neutral_punch' ? 'selected' : ''}>${g.label}</option>`
    ).join('');

    const stepsHTML = VIDEO_STEP_LABELS.map((lbl, i) => `
      <div class="p-step" id="vp-step-${i}">
        <div class="p-dot">${i + 1}</div>
        <div class="p-body">
          <div class="p-label">${lbl}</div>
          <div class="p-sub" id="vp-sub-${i}">Waiting…</div>
        </div>
      </div>`).join('');

    return `
      <div class="page-header">
        <div class="header-tag">Tool</div>
        <h1>Video Studio</h1>
        <p>Upload a raw talking-head MP4 → AI proposes cuts → you approve → polished reel rendered.</p>
      </div>

      <!-- ── Upload card ───────────────────────────────────────────────────── -->
      <div class="card" id="video-upload-card">
        <div class="card-title mb-12">Upload Video</div>

        <!-- Drop zone -->
        <div class="drop-zone" id="video-drop-zone">
          <div class="drop-icon">🎬</div>
          <div class="drop-label">Drop your MP4 here</div>
          <div class="drop-sub">or click to browse · MP4, MOV, M4V, MKV supported</div>
          <input type="file" id="video-file-input" accept=".mp4,.mov,.m4v,.avi,.mkv" style="display:none">
        </div>

        <!-- File selected preview -->
        <div id="file-preview" style="display:none;" class="file-preview">
          <span class="file-icon">🎞️</span>
          <div class="file-info">
            <div class="file-name" id="file-name">video.mp4</div>
            <div class="file-size" id="file-size">—</div>
          </div>
          <button class="btn btn-ghost btn-sm" onclick="videoPage.clearFile()">✕ Clear</button>
        </div>

        <div class="divider"></div>

        <!-- Render options -->
        <div class="card-title mb-12">Render Options</div>
        <div class="options-grid">
          <div class="option-item">
            <label>Color Grade</label>
            <select id="v-grade" class="form-select">${gradeHTML}</select>
          </div>
          <div class="option-item">
            <label>Speaker Name <span style="color:var(--text-muted);font-weight:400;">(optional)</span></label>
            <input type="text" id="v-speaker-name" class="form-input" placeholder="e.g. Eduardo Leite" style="margin-top:6px;">
          </div>
          <div class="option-item">
            <label>Speaker Title <span style="color:var(--text-muted);font-weight:400;">(optional)</span></label>
            <input type="text" id="v-speaker-title" class="form-input" placeholder="e.g. CEO, Wisuno" style="margin-top:6px;">
          </div>
          <div class="option-item">
            <label>Slide Duration</label>
            <select id="v-slide-dur" class="form-select" style="margin-top:6px;">
              <option value="3">3 seconds</option>
              <option value="4" selected>4 seconds</option>
              <option value="5">5 seconds</option>
              <option value="6">6 seconds</option>
            </select>
          </div>
        </div>

        <!-- Render toggles -->
        <div class="toggles-list" style="margin-top:12px;">
          <div class="toggle-row">
            <div>
              <div class="toggle-label">🗂 AI graphic slides</div>
              <div class="toggle-sub">Claude extracts 3 data points → HyperFrames animated cards inserted mid-video</div>
            </div>
            <label class="toggle"><input type="checkbox" id="v-graphics" checked><div class="toggle-track"></div></label>
          </div>
          <div class="toggle-row">
            <div>
              <div class="toggle-label">🎵 Background music</div>
              <div class="toggle-sub">ElevenLabs AI-generated news-style instrumental, mixed at −18 dB</div>
            </div>
            <label class="toggle"><input type="checkbox" id="v-music" checked><div class="toggle-track"></div></label>
          </div>
        </div>

        <p style="font-size:11px;color:var(--text-muted);margin-top:10px;line-height:1.5;">
          ℹ️ Karaoke captions, rotating disclaimer and branded outro are always included automatically.
        </p>

        <button class="btn btn-primary" id="btn-analyse" style="width:100%;padding:14px;"
                onclick="videoPage.startUpload()" disabled>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          Upload &amp; Analyse
        </button>
      </div>

      <!-- ── Progress card ─────────────────────────────────────────────────── -->
      <div class="card" id="video-progress-card" style="display:none;">
        <div class="flex justify-between items-center mb-20">
          <div>
            <div class="card-title" style="margin-bottom:4px;" id="vp-title">Analysing…</div>
            <div style="font-size:12px;color:var(--text-muted);" id="vp-subtitle">This may take a few minutes depending on video length.</div>
          </div>
        </div>
        <div class="progress-steps">${stepsHTML}</div>
      </div>

      <!-- ── Cut Review card ───────────────────────────────────────────────── -->
      <div class="card" id="video-review-card" style="display:none;">
        <div class="flex justify-between items-center mb-20">
          <div>
            <div class="card-title" style="margin-bottom:4px;">✂ Review Proposed Cuts</div>
            <div style="font-size:12px;color:var(--text-muted);">
              Claude analysed your transcript and proposed these cuts. Remove any you don't want, then click <strong>Approve & Render</strong>.
            </div>
          </div>
          <div style="text-align:right;flex-shrink:0;margin-left:16px;">
            <div style="font-size:20px;font-weight:900;font-family:'Urbanist',sans-serif;" id="cuts-total-dur">—</div>
            <div style="font-size:11px;color:var(--text-muted);">total duration</div>
          </div>
        </div>

        <!-- Probe info bar -->
        <div class="probe-bar" id="probe-bar"></div>

        <!-- Cut list -->
        <div id="cut-list" class="cut-list"></div>

        <!-- Approve button -->
        <div style="margin-top:20px;display:flex;gap:12px;align-items:center;">
          <button class="btn btn-primary" id="btn-approve" style="flex:1;padding:14px;"
                  onclick="videoPage.approveAndRender()">
            ✅ Approve & Render
          </button>
          <button class="btn btn-secondary" onclick="videoPage.reset()">↩ Start Over</button>
        </div>
      </div>

      <!-- ── Rendering card ────────────────────────────────────────────────── -->
      <div class="card" id="video-rendering-card" style="display:none;">
        <div class="card-title mb-20">🎬 Rendering…</div>
        <div class="progress-steps">
          <div class="p-step" id="vp-render-step">
            <div class="p-dot running" style="animation:pulse 1.5s infinite;">6</div>
            <div class="p-body">
              <div class="p-label">Render final video</div>
              <div class="p-sub" id="vp-render-sub">Extracting segments, grading, concatenating…</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Done card ─────────────────────────────────────────────────────── -->
      <div class="card" id="video-done-card" style="display:none;">
        <div class="card-title" style="color:var(--green);margin-bottom:12px;">✅ Video Ready</div>
        <div style="font-size:13px;color:var(--text-muted);margin-bottom:20px;">
          Your polished video is ready. The file includes graded cuts, burned-in subtitles, and loudness-normalized audio (−14 LUFS).
        </div>
        <div class="video-player-wrap">
          <video id="video-preview-player" controls playsinline>
            <source src="" type="video/mp4">
            Your browser does not support the video tag.
          </video>
        </div>
        <a id="btn-download-video" class="btn btn-primary" href="#" download
           style="display:inline-flex;width:100%;justify-content:center;padding:14px;text-decoration:none;">
          ⬇ Download final.mp4
        </a>
        <div id="video-metadata-panel" style="display:none; margin-top:20px; padding:16px; background:var(--surface-2); border-radius:8px; border:1px solid var(--border);">
          <div style="font-weight:600; font-size:14px; margin-bottom:12px; color:var(--text-primary); display:flex; justify-content:space-between; align-items:center;">
            📝 AI Metadata
            <button class="btn btn-ghost btn-sm" onclick="videoPage.copyMetadata()" style="padding:4px 8px; font-size:11px;">📋 Copy All</button>
          </div>
          <div style="font-size:13px; color:var(--text-primary); margin-bottom:8px;"><strong>Title:</strong> <span id="vm-title"></span></div>
          <div style="font-size:13px; color:var(--text-secondary); margin-bottom:8px; white-space:pre-wrap;" id="vm-caption"></div>
          <div style="font-size:13px; color:var(--accent); font-weight:500;" id="vm-hashtags"></div>
        </div>
        <button class="btn btn-secondary" style="width:100%;margin-top:20px;" onclick="videoPage.reset()">
          ↩ Process Another Video
        </button>
      </div>

      <div class="card" id="video-error-card" style="display:none;">
        <div class="card-title" style="color:var(--red);margin-bottom:12px;">⚠ Pipeline Failed</div>
        <div class="error-panel" style="margin-bottom:16px;">
          <strong id="v-error-msg"></strong>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <button class="btn btn-primary" id="btn-retry-step" style="flex:1;" onclick="videoPage.retryFailedStep()">
            🔄 Retry Failed Step
          </button>
          <button class="btn btn-secondary" onclick="videoPage.retryRender()">
            ✂ Edit Cuts &amp; Re-render
          </button>
          <button class="btn btn-secondary" onclick="videoPage.reset()">↩ Start Over</button>
        </div>
      </div>
    `;
  },

  /* ── Events ───────────────────────────────────────────────────────────────── */

  _bindEvents() {
    const dropZone = document.getElementById('video-drop-zone');
    const fileInput = document.getElementById('video-file-input');

    if (!dropZone || !fileInput) return;

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
      const file = e.dataTransfer?.files?.[0];
      if (file) this._setFile(file);
    });

    fileInput.addEventListener('change', () => {
      const file = fileInput.files?.[0];
      if (file) this._setFile(file);
    });
  },

  _setFile(file) {
    const dropZone = document.getElementById('video-drop-zone');
    const preview  = document.getElementById('file-preview');
    document.getElementById('file-name').textContent = file.name;
    document.getElementById('file-size').textContent = `${(file.size / (1024*1024)).toFixed(1)} MB`;
    dropZone.style.display = 'none';
    preview.style.display  = 'flex';
    document.getElementById('btn-analyse').disabled = false;
    this._selectedFile = file;
  },

  clearFile() {
    this._selectedFile = null;
    document.getElementById('video-drop-zone').style.display = '';
    document.getElementById('file-preview').style.display = 'none';
    document.getElementById('btn-analyse').disabled = true;
    document.getElementById('video-file-input').value = '';
  },

  /* ── Upload & analyse ─────────────────────────────────────────────────────── */

  async startUpload() {
    const file = this._selectedFile;
    if (!file) { toast.error('Please select a video file first.'); return; }

    const btn = document.getElementById('btn-analyse');
    btn.disabled = true;
    btn.textContent = 'Uploading…';

    this._showCard('progress');
    this._resetSteps();

    try {
      let authHeader = {};
      const { data: { session } } = await window.supabaseClient.auth.getSession();
      if (session) {
        authHeader = { 'Authorization': `Bearer ${session.access_token}` };
      }

      // 1. Chunked Upload setup (20MB chunks)
      const chunkSize = 20 * 1024 * 1024;
      const totalChunks = Math.ceil(file.size / chunkSize);
      const uploadId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2);

      // 2. Upload each chunk sequentially, retrying transient failures so a
      //    single network blip or auth hiccup doesn't abort the whole upload.
      const MAX_CHUNK_ATTEMPTS = 4;
      for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        const chunk = file.slice(start, end);

        btn.textContent = `Uploading… ${Math.round(((i) / totalChunks) * 100)}%`;

        let lastErr = null;
        let uploaded = false;
        for (let attempt = 1; attempt <= MAX_CHUNK_ATTEMPTS; attempt++) {
          // FormData must be rebuilt per attempt — the stream is consumed once.
          const formData = new FormData();
          formData.append('upload_id', uploadId);
          formData.append('chunk_index', i);
          formData.append('file', chunk, file.name);

          try {
            const resp = await fetch('/api/video/upload_chunk', {
              method: 'POST',
              headers: authHeader,
              body: formData
            });
            if (resp.ok) { uploaded = true; break; }
            lastErr = new Error(`HTTP ${resp.status}`);
          } catch (e) {
            lastErr = e; // network error — retry
          }

          if (attempt < MAX_CHUNK_ATTEMPTS) {
            btn.textContent = `Retrying chunk ${i + 1}/${totalChunks}… (${attempt}/${MAX_CHUNK_ATTEMPTS - 1})`;
            await new Promise(r => setTimeout(r, 1000 * attempt)); // linear backoff
          }
        }

        if (!uploaded) {
          throw new Error(`Upload failed at chunk ${i + 1}/${totalChunks}${lastErr ? ` (${lastErr.message})` : ''}`);
        }
      }

      btn.textContent = 'Processing…';

      // 3. Finalize upload
      const completeData = new FormData();
      completeData.append('upload_id', uploadId);
      completeData.append('filename', file.name);
      completeData.append('total_chunks', totalChunks);

      const completeResp = await fetch('/api/video/upload_complete', {
        method: 'POST',
        headers: authHeader,
        body: completeData
      });

      if (!completeResp.ok) {
        const err = await completeResp.json().catch(() => ({}));
        throw new Error(err.detail || 'Upload completion failed');
      }

      const result = await completeResp.json();
      vState.jobId = result.job_id;
      toast.info(`Uploaded ${file.name} · Analysis started`);
      this._startPolling();

    } catch (err) {
      toast.error(err.message || 'Upload failed');
      this._showCard('upload');
      btn.disabled = false;
      btn.textContent = 'Upload & Analyse';
    }
  },

  /* ── Polling ──────────────────────────────────────────────────────────────── */

  _startPolling() {
    this._stopPolling();
    vState.pollTimer = setInterval(() => this._poll(), 2000);
  },

  _stopPolling() {
    if (vState.pollTimer) { clearInterval(vState.pollTimer); vState.pollTimer = null; }
  },

  async _poll() {
    if (!vState.jobId) return;
    try {
      const data = await apiFetch(`/api/video/status/${vState.jobId}`);

      this._updateSteps(data.steps || []);

      if (data.status === 'awaiting_approval') {
        this._stopPolling();
        this._showReview(data.proposed_cuts, data.probe);
      } else if (data.status === 'rendering') {
        this._showCard('rendering');
        const sub = document.getElementById('vp-render-sub');
        if (sub) sub.textContent = data.steps?.[5]?.note || 'Rendering…';
      } else if (data.status === 'done') {
        this._stopPolling();
        this._showDone(data.download_url, data.metadata);
      } else if (data.status === 'error') {
        this._stopPolling();
        const failedStepIndex = (data.steps || []).findIndex(s => s.status === 'error');
        vState.failedStep = failedStepIndex >= 0 ? failedStepIndex : null;
        this._showError(data.error);
      }
      // 'pending' / 'analysing' — keep polling, progress steps already updated
    } catch {
      // keep polling on network errors
    }
  },

  /* ── Step display ─────────────────────────────────────────────────────────── */

  _resetSteps() {
    VIDEO_STEP_LABELS.forEach((_, i) => {
      const el  = document.getElementById(`vp-step-${i}`);
      const sub = document.getElementById(`vp-sub-${i}`);
      if (el)  el.className = 'p-step';
      if (sub) sub.textContent = 'Waiting…';
    });
  },

  _updateSteps(steps) {
    steps.forEach((step, i) => {
      const el  = document.getElementById(`vp-step-${i}`);
      const sub = document.getElementById(`vp-sub-${i}`);
      if (!el) return;
      el.className = `p-step ${step.status}`;
      if (sub) {
        if (step.status === 'running')  sub.textContent = VIDEO_STEP_SUBS[i] || '…';
        else if (step.status === 'done') sub.textContent = step.note || '✓ Done';
        else if (step.status === 'error') sub.textContent = step.error || 'Failed';
        else sub.textContent = 'Waiting…';
      }
    });
  },

  /* ── Review UI ────────────────────────────────────────────────────────────── */

  _showReview(cuts, probe) {
    vState.proposedCuts = cuts || [];
    vState.editedCuts   = cuts.map(c => ({ ...c }));
    vState._probe       = probe;
    this._renderProbeBar(probe);
    this._renderCutList();
    this._showCard('review');
    const kept    = cuts.reduce((s, c) => s + (c.end - c.start), 0);
    const orig    = probe?.duration || 0;
    const removed = orig > 0 ? Math.round((1 - kept / orig) * 100) : 0;
    toast.success(`AI proposed ${cuts.length} cuts keeping ${kept.toFixed(0)}s of ${orig.toFixed(0)}s — ${removed}% removed.`);
  },

  _renderProbeBar(probe) {
    const bar = document.getElementById('probe-bar');
    if (!bar || !probe) return;
    bar.innerHTML = `
      <span class="probe-item">📐 ${probe.width}×${probe.height}</span>
      <span class="probe-item">⏱ ${probe.duration?.toFixed(1)}s</span>
      <span class="probe-item">🎞 ${probe.fps} fps</span>
      <span class="probe-item">💾 ${probe.size_mb} MB</span>
      <span class="probe-item">🎬 ${probe.codec || 'h264'}</span>
    `;
  },

  _renderCutList() {
    const list = document.getElementById('cut-list');
    if (!list) return;

    const cuts = vState.editedCuts;
    let totalDur = cuts.reduce((s, c) => s + (c.end - c.start), 0);
    const durEl = document.getElementById('cuts-total-dur');
    if (durEl) durEl.textContent = `${totalDur.toFixed(1)}s`;

    if (!cuts.length) {
      list.innerHTML = '<div style="color:var(--text-muted);font-size:13px;padding:20px 0;text-align:center;">No cuts remaining.</div>';
      return;
    }

    list.innerHTML = cuts.map((cut, idx) => {
      const dur   = (cut.end - cut.start).toFixed(1);
      const color = BEAT_COLORS[cut.beat] || 'var(--text-muted)';
      return `
        <div class="cut-row" id="cut-row-${idx}">
          <div class="cut-beat" style="color:${color};">${cut.beat || '—'}</div>
          <div class="cut-times">
            <input type="number" class="cut-time-input" step="0.01" min="0"
                   value="${cut.start.toFixed(2)}"
                   onchange="videoPage.updateCut(${idx}, 'start', +this.value)"
                   title="Start time (seconds)">
            <span style="color:var(--text-muted);font-size:11px;">→</span>
            <input type="number" class="cut-time-input" step="0.01" min="0"
                   value="${cut.end.toFixed(2)}"
                   onchange="videoPage.updateCut(${idx}, 'end', +this.value)"
                   title="End time (seconds)">
            <span class="cut-dur">${dur}s</span>
          </div>
          <div class="cut-quote" style="margin-top: 8px;">
            <textarea class="form-input" style="width:100%;resize:vertical;min-height:50px;font-size:13px;padding:8px;font-family:inherit;" onchange="videoPage.updateCut(${idx}, 'quote', this.value)" placeholder="Caption text...">${cut.quote || ''}</textarea>
          </div>
          <div class="cut-reason">${cut.reason || ''}</div>
          <button class="cut-remove-btn" onclick="videoPage.removeCut(${idx})" title="Remove this cut">✕</button>
        </div>
      `;
    }).join('');
  },

  updateCut(idx, field, value) {
    if (vState.editedCuts[idx]) {
      vState.editedCuts[idx][field] = value;
      this._renderCutList();
    }
  },

  removeCut(idx) {
    vState.editedCuts.splice(idx, 1);
    this._renderCutList();
    if (!vState.editedCuts.length) toast.info('All cuts removed — add at least one before approving.');
  },

  /* ── Approve & Render ─────────────────────────────────────────────────────── */

  async approveAndRender() {
    if (!vState.editedCuts.length) {
      toast.error('Add at least one cut before approving.');
      return;
    }

    const btn = document.getElementById('btn-approve');
    btn.disabled = true;
    btn.textContent = 'Starting render…';

    const grade    = document.getElementById('v-grade')?.value    || 'neutral_punch';
    const graphics = document.getElementById('v-graphics')?.checked ?? true;
    const music    = document.getElementById('v-music')?.checked    ?? true;

    try {
      const result = await apiFetch(`/api/video/approve/${vState.jobId}`, {
        method:  'POST',
        body:    JSON.stringify({
          cuts:             vState.editedCuts,
          grade,
          include_graphics: graphics,
          include_music:    music,
        }),
      });
      toast.success(`Rendering ${result.cuts} cuts (${result.total_s}s) with ${grade} grade…`);
      this._showCard('rendering');
      this._startPolling();
    } catch (err) {
      toast.error(err.message || 'Failed to start render');
      // Reset approve button so user can try again
      const btn = document.getElementById('btn-approve');
      if (btn) { btn.disabled = false; btn.textContent = '✅ Approve & Render'; }
    }
  },

  /* ── Done ─────────────────────────────────────────────────────────────────── */

  _showDone(downloadUrl, metadata = null) {
    console.log("[video.js] _showDone called", { downloadUrl, metadata });
    
    const btn = document.getElementById('btn-download-video');
    if (btn && downloadUrl) btn.href = downloadUrl;
    
    // Metadata
    const metaPanel = document.getElementById('video-metadata-panel');
    if (!metaPanel) {
      toast.error("UI ERROR: video-metadata-panel missing from DOM!");
    }
    
    if (metadata && metaPanel) {
      metaPanel.style.display = 'block';
      document.getElementById('vm-title').textContent = metadata.title || '';
      document.getElementById('vm-caption').textContent = metadata.caption || '';
      document.getElementById('vm-hashtags').textContent = (metadata.hashtags || []).join(' ');
      vState.lastMetadata = metadata;
      toast.success("Metadata loaded successfully");
    } else if (metaPanel) {
      metaPanel.style.display = 'none';
      toast.info("No metadata returned from server.");
    }

    // Load video player source
    const player = document.getElementById('video-preview-player');
    if (player && vState.jobId) {
      player.src = `/api/video/stream/${vState.jobId}`;
      player.load();
    }
    
    // Always re-enable approve button so next session works
    const appBtn = document.getElementById('btn-approve');
    if (appBtn) { appBtn.disabled = false; appBtn.textContent = '✅ Approve & Render'; }
    this._showCard('done');
    toast.success('Your video is ready!');
  },

  copyMetadata() {
    if (!vState.lastMetadata) return;
    const { title, caption, hashtags } = vState.lastMetadata;
    const tags = (hashtags || []).join(' ');
    const text = `${title}\n\n${caption}\n\n${tags}`;
    navigator.clipboard.writeText(text).then(() => {
      toast.success('Metadata copied to clipboard!');
    }).catch(() => {
      toast.error('Failed to copy metadata');
    });
  },

  /* ── Error ────────────────────────────────────────────────────────────────── */

  _showError(msg) {
    const el = document.getElementById('v-error-msg');
    if (el) el.textContent = msg || 'An unexpected error occurred.';
    // Reset approve button in case it's stuck
    const btn = document.getElementById('btn-approve');
    if (btn) { btn.disabled = false; btn.textContent = '✅ Approve & Render'; }
    this._showCard('error');
    toast.error('Render failed — click "Edit Cuts & Re-render" to try again.', 8000);
  },

  /* ── Retry render (go back to review panel) ─────────────────────────────── */

  retryRender() {
    // Go back to the review panel with the same cuts — no re-upload needed
    this._renderCutList();
    this._showCard('review');
  },

  async retryFailedStep() {
    if (vState.failedStep === null || !vState.jobId) return;
    
    const btn = document.getElementById('btn-retry-step');
    btn.disabled = true;
    btn.textContent = 'Retrying...';

    const grade    = document.getElementById('v-grade')?.value    || 'neutral_punch';
    const graphics = document.getElementById('v-graphics')?.checked ?? true;
    const music    = document.getElementById('v-music')?.checked    ?? true;

    try {
      await apiFetch(`/api/video/retry/${vState.jobId}`, {
        method: 'POST',
        body: JSON.stringify({
          step_index: vState.failedStep,
          grade,
          include_graphics: graphics,
          include_music: music
        })
      });
      toast.info('Retrying failed step...');
      
      // Update UI back to running state
      this._showCard(vState.failedStep === 5 ? 'rendering' : 'progress');
      this._startPolling();
    } catch (err) {
      toast.error(err.message || 'Failed to retry step');
    } finally {
      btn.disabled = false;
      btn.textContent = '🔄 Retry Failed Step';
    }
  },

  /* ── Music options panel ──────────────────────────────────────────────────── */

  toggleMusicOptions(on) {
    const el = document.getElementById('music-options');
    if (el) el.style.display = on ? 'flex' : 'none';
  },

  /* ── Helpers ──────────────────────────────────────────────────────────────── */

  _showCard(which) {
    ['upload', 'progress', 'review', 'rendering', 'done', 'error'].forEach(n => {
      const el = document.getElementById(`video-${n}-card`);
      if (el) el.style.display = n === which ? '' : 'none';
    });
  },

  reset() {
    this._stopPolling();
    vState.jobId = null;
    vState.proposedCuts = [];
    vState.editedCuts   = [];
    this._selectedFile  = null;
    this._showCard('upload');
    // Reset upload area
    const dz = document.getElementById('video-drop-zone');
    const fp = document.getElementById('file-preview');
    if (dz) dz.style.display = '';
    if (fp) fp.style.display = 'none';
    const btn = document.getElementById('btn-analyse');
    if (btn) { btn.disabled = true; btn.textContent = 'Upload & Analyse'; }
    const fi = document.getElementById('video-file-input');
    if (fi) fi.value = '';
    // Always re-enable approve button for next run
    const appBtn = document.getElementById('btn-approve');
    if (appBtn) { appBtn.disabled = false; appBtn.textContent = '✅ Approve & Render'; }
  },
};

/* ── Register with app router ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  videoPage.init();
});
