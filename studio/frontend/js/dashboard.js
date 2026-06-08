/**
 * dashboard.js — Dashboard & History view for Wisuno Studio
 */

const dashboardPage = {
  async onShow() {
    this.render();
    await this.fetchHistory();
  },

  render() {
    const page = document.getElementById('page-dashboard');
    if (!page.innerHTML.trim()) {
      page.innerHTML = `
        <div class="page-header">
          <div class="header-tag">Home</div>
          <h1>Dashboard</h1>
          <p>Recent carousel and video production runs.</p>
        </div>
        
        <div class="card">
          <div class="flex justify-between items-center mb-16">
            <div class="card-title" style="margin-bottom:0">Job History</div>
            <button class="btn btn-ghost btn-sm" onclick="dashboardPage.fetchHistory()">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M23 4v6h-6M1 20v-6h6"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              Refresh
            </button>
          </div>
          <div id="history-list" class="history-list">
            <div class="text-muted" style="padding:20px;text-align:center;">Loading history...</div>
          </div>
          <div id="debug-panel" style="margin-top:20px;padding:10px;background:#111;color:#0f0;font-family:monospace;font-size:11px;border-radius:4px;white-space:pre-wrap;">[Debug Panel Ready]</div>
        </div>
      `;
    }
  },

  async fetchHistory() {
    const list = document.getElementById('history-list');
    const dbg = document.getElementById('debug-panel');
    const log = (msg) => { if(dbg) dbg.innerHTML += '\\n' + msg; };
    if (!list) return;

    try {
      const ts = new Date().getTime();
      log(`Fetching /api/history?t=${ts}...`);
      const data = await apiFetch(`/api/history?t=${ts}`);
      log(`Raw data received: ${JSON.stringify(data).substring(0, 200)}...`);
      const history = data.history || [];
      log(`Parsed history array (${history.length} items)`);
      
      if (history.length === 0) {
        list.innerHTML = `<div class="text-muted" style="padding:20px;text-align:center;">No recent runs found.</div>`;
        return;
      }

      let groups = {};
      for (const entry of history) {
        const dateObj = new Date(entry.timestamp);
        // e.g. "June 4, 2026"
        const dateStr = dateObj.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });
        if (!groups[dateStr]) groups[dateStr] = [];
        groups[dateStr].push(entry);
      }

      let html = `<div style="display:flex;flex-direction:column;gap:24px;">`;
      for (const [dateStr, entries] of Object.entries(groups)) {
        html += `<div>`;
        html += `<div style="font-size:13px;font-weight:600;color:var(--text-muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px;padding-left:4px;">${dateStr}</div>`;
        html += `<div style="display:flex;flex-direction:column;gap:8px;">`;
        
        for (const entry of entries) {
            const time = new Date(entry.timestamp).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
            const details = entry.details || {};
            const topic = details.topic || (entry.job_type === 'carousel' ? 'Carousel Generation' : 'Video Generation');
            const typeIcon = entry.job_type === 'carousel' ? '🗂️' : '🎬';
            const badgeClass = entry.status === 'done' ? 'badge-green' : 'badge-red';
            const badgeText = entry.status === 'done' ? 'Done' : 'Failed';
            
            let linksHtml = '';
            if (entry.status === 'done') {
                if (entry.job_type === 'carousel' && details.files) {
                    details.files.forEach(f => {
                        linksHtml += `<a href="${f.url}" download class="btn btn-ghost btn-sm" style="font-size:11px;padding:4px 8px;text-decoration:none;background:var(--surface-3);">⬇ ${f.lang}</a>`;
                    });
                } else if (entry.job_type === 'video' && details.file) {
                    linksHtml += `<a href="${details.file}" download class="btn btn-secondary btn-sm" style="font-size:11px;padding:4px 10px;text-decoration:none;">⬇ Download</a>`;
                }
            } else {
                const errStr = details.error || 'Unknown error';
                linksHtml = `<span style="font-size:11px;color:var(--text-danger);background:rgba(239,68,68,0.1);padding:4px 8px;border-radius:4px;">${errStr.substring(0,50)}${errStr.length>50?'...':''}</span>`;
            }

            html += `
              <div style="background:var(--surface-2);border-radius:8px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;border:1px solid var(--border);transition:border-color 0.2s;">
                <div style="display:flex;align-items:center;gap:16px;">
                  <div style="font-size:20px;background:var(--surface-3);border-radius:8px;width:40px;height:40px;display:flex;align-items:center;justify-content:center;box-shadow:inset 0 1px 2px rgba(0,0,0,0.1);">${typeIcon}</div>
                  <div>
                    <div style="font-weight:600;font-size:15px;color:var(--text-primary);margin-bottom:4px;">${topic}</div>
                    <div style="font-size:12px;color:var(--text-secondary);display:flex;align-items:center;gap:8px;">
                      <span>${time}</span>
                      <span style="opacity:0.3;">•</span>
                      <span style="font-family:monospace;opacity:0.6;">ID: ${entry.job_id.substring(0, 8)}</span>
                    </div>
                  </div>
                </div>
                <div style="display:flex;align-items:center;gap:16px;">
                  <div style="display:flex;gap:6px;flex-wrap:wrap;max-width:280px;justify-content:flex-end;">${linksHtml}</div>
                  <span class="badge ${badgeClass}" style="min-width:60px;text-align:center;">${badgeText}</span>
                </div>
              </div>
            `;
        }
        html += `</div></div>`;
      }
      html += `</div>`;
      list.innerHTML = html;
    } catch (err) {
      list.innerHTML = `<div class="text-danger" style="padding:20px;text-align:center;">Failed to load history.</div>`;
    }
  }
};
