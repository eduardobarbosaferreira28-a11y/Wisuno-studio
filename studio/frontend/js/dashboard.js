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
        </div>
      `;
    }
  },

  async fetchHistory() {
    const list = document.getElementById('history-list');
    if (!list) return;

    try {
      const data = await apiFetch('/api/history');
      const history = data.history || [];
      
      if (history.length === 0) {
        list.innerHTML = `<div class="text-muted" style="padding:20px;text-align:center;">No recent runs found.</div>`;
        return;
      }

      let html = `<div style="display:flex;flex-direction:column;gap:8px;">`;
      for (const entry of history) {
        const time = new Date(entry.timestamp).toLocaleString();
        const typeIcon = entry.job_type === 'carousel' ? '🗂️' : '🎬';
        const typeName = entry.job_type === 'carousel' ? 'Carousel' : 'Video';
        const badgeClass = entry.status === 'done' ? 'badge-green' : 'badge-red';
        const badgeText = entry.status === 'done' ? 'Done' : 'Failed';
        
        let linksHtml = '';
        if (entry.status === 'done') {
            if (entry.job_type === 'carousel' && entry.details.files) {
                entry.details.files.forEach(f => {
                    linksHtml += `<a href="${f.url}" target="_blank" class="btn btn-ghost btn-sm" style="font-size:11px;padding:2px 6px;">⬇ ${f.lang}</a>`;
                });
            } else if (entry.job_type === 'video' && entry.details.file) {
                linksHtml += `<a href="${entry.details.file}" target="_blank" class="btn btn-secondary btn-sm" style="font-size:11px;padding:2px 6px;">⬇ Download</a>`;
            }
        } else {
            const errStr = entry.details.error || 'Unknown error';
            linksHtml = `<span style="font-size:11px;color:var(--text-danger);">${errStr.substring(0,50)}${errStr.length>50?'...':''}</span>`;
        }

        html += `
          <div style="background:var(--surface-2);border-radius:6px;padding:12px;display:flex;align-items:center;justify-content:space-between;border:1px solid var(--border);">
            <div style="display:flex;align-items:center;gap:12px;">
              <div style="font-size:20px;opacity:0.8">${typeIcon}</div>
              <div>
                <div style="font-weight:600;font-size:14px;color:var(--text-primary);">${typeName} Run <span style="opacity:0.5;font-weight:normal;font-size:12px;font-family:monospace;margin-left:4px;">${entry.job_id}</span></div>
                <div style="font-size:12px;color:var(--text-secondary);margin-top:2px;">${time}</div>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:12px;">
              <div style="display:flex;gap:4px;flex-wrap:wrap;max-width:200px;justify-content:flex-end;">${linksHtml}</div>
              <span class="badge ${badgeClass}" style="min-width:50px;text-align:center;">${badgeText}</span>
            </div>
          </div>
        `;
      }
      html += `</div>`;
      list.innerHTML = html;
    } catch (err) {
      list.innerHTML = `<div class="text-danger" style="padding:20px;text-align:center;">Failed to load history.</div>`;
    }
  }
};
