/**
 * Higgsfield Studio UI Controller
 */

window.higgsfieldPage = {
  currentSessionId: null,
  messages: [],
  pendingImages: [],   // uploaded reference image URLs for the next message
  webEnabled: false,   // "Browse web" toggle state

  init() {
    this.setupEventListeners();
    this.loadSessions();
  },

  setupEventListeners() {
    document.getElementById("hf-new-chat").addEventListener("click", () => {
      this.currentSessionId = null;
      this.messages = [];
      this.pendingImages = [];
      this.renderAttachments();
      this.renderMessages();
      document.getElementById("hf-chat-title").innerText = "New Chat";
      document.querySelectorAll(".hf-session-item").forEach(el => el.style.background = "transparent");
    });

    const form = document.getElementById("hf-chat-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      await this.sendMessage();
    });

    const input = document.getElementById("hf-input");
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    // ── Attachment toolbar ──────────────────────────────────────────────
    const fileInput = document.getElementById("hf-file-input");
    document.getElementById("hf-upload-btn").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
      const files = Array.from(fileInput.files || []);
      files.forEach(f => this.uploadImage(f));
      fileInput.value = ""; // allow re-selecting the same file
    });

    document.getElementById("hf-context-btn").addEventListener("click", () => {
      const panel = document.getElementById("hf-context-panel");
      const showing = panel.style.display !== "none";
      panel.style.display = showing ? "none" : "block";
      document.getElementById("hf-context-btn").classList.toggle("active", !showing || !!this.getContext());
      if (!showing) document.getElementById("hf-context").focus();
    });

    document.getElementById("hf-context").addEventListener("input", () => {
      document.getElementById("hf-context-btn").classList.toggle("active", !!this.getContext());
    });

    document.getElementById("hf-web-btn").addEventListener("click", () => {
      this.webEnabled = !this.webEnabled;
      document.getElementById("hf-web-btn").classList.toggle("active", this.webEnabled);
    });
  },

  getContext() {
    const el = document.getElementById("hf-context");
    return el ? el.value.trim() : "";
  },

  // Upload a reference image to the backend and add it to the pending list.
  async uploadImage(file) {
    if (!file.type.startsWith("image/")) {
      toast.error("Only image files can be used as references.");
      return;
    }
    const container = document.getElementById("hf-attachments");
    container.style.display = "flex";
    const chip = document.createElement("div");
    chip.className = "hf-attach-chip uploading";
    chip.innerHTML = `<img src="${URL.createObjectURL(file)}" alt="">`;
    container.appendChild(chip);

    try {
      let authHeader = {};
      const { data: { session } } = await window.supabaseClient.auth.getSession();
      if (session) authHeader = { Authorization: `Bearer ${session.access_token}` };

      const formData = new FormData();
      formData.append("file", file, file.name);
      const res = await fetch("/api/higgsfield/upload", { method: "POST", headers: authHeader, body: formData });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      this.pendingImages.push(data.url);
      this.renderAttachments();
    } catch (e) {
      console.error("Image upload failed", e);
      toast.error("Image upload failed: " + e.message);
      chip.remove();
      if (!container.children.length) container.style.display = "none";
    }
  },

  renderAttachments() {
    const container = document.getElementById("hf-attachments");
    container.innerHTML = "";
    if (!this.pendingImages.length) {
      container.style.display = "none";
      return;
    }
    container.style.display = "flex";
    this.pendingImages.forEach((url, idx) => {
      const chip = document.createElement("div");
      chip.className = "hf-attach-chip";
      chip.innerHTML = `<img src="${url}" alt="reference">
        <button class="hf-attach-remove" title="Remove" onclick="window.higgsfieldPage.removeAttachment(${idx})">✕</button>`;
      container.appendChild(chip);
    });
  },

  removeAttachment(idx) {
    this.pendingImages.splice(idx, 1);
    this.renderAttachments();
  },

  async loadSessions() {
    try {
      const data = await apiFetch("/api/higgsfield/sessions");
      this.renderSessions(data.sessions || []);
    } catch (e) {
      console.error("Failed to load sessions", e);
    }
  },

  renderSessions(sessions) {
    const list = document.getElementById("hf-sessions-list");
    list.innerHTML = "";
    
    sessions.forEach(s => {
      const el = document.createElement("div");
      el.className = "hf-session-item";
      el.style.padding = "12px 16px";
      el.style.cursor = "pointer";
      el.style.borderRadius = "8px";
      el.style.marginBottom = "4px";
      el.style.fontSize = "14px";
      el.style.whiteSpace = "nowrap";
      el.style.overflow = "hidden";
      el.style.textOverflow = "ellipsis";
      
      if (s.id === this.currentSessionId) {
        el.style.background = "rgba(255,255,255,0.05)";
      }

      el.innerText = s.title;
      el.addEventListener("click", () => this.loadChat(s.id, s.title));
      list.appendChild(el);
    });
  },

  async loadChat(sessionId, title) {
    this.currentSessionId = sessionId;
    document.getElementById("hf-chat-title").innerText = title;
    
    document.querySelectorAll(".hf-session-item").forEach(el => el.style.background = "transparent");
    // Background highlight for active will be tricky without re-rendering, just reload sessions list
    this.loadSessions();

    try {
      const data = await apiFetch(`/api/higgsfield/sessions/${sessionId}/messages`);
      this.messages = data.messages || [];
      this.renderMessages();
    } catch (e) {
      console.error("Failed to load messages", e);
    }
  },

  renderMessages() {
    const container = document.getElementById("hf-messages");
    container.innerHTML = "";

    if (this.messages.length === 0) {
      container.innerHTML = `
        <div class="hf-msg assistant" style="align-self:flex-start; max-width:80%; background:var(--bg-lighter); padding:16px 20px; border-radius:12px; border-top-left-radius:2px;">
          Hello! I am the Wisuno AI Director. What would you like to generate today?
        </div>
      `;
      return;
    }

    this.messages.forEach(msg => {
      // Ignore tool results in the UI if they exist as raw JSON
      if (msg.role === "user" && msg.content.includes("tool_result")) {
        return; 
      }

      const div = document.createElement("div");
      div.className = `hf-msg ${msg.role}`;
      div.style.maxWidth = "80%";
      div.style.padding = "16px 20px";
      div.style.borderRadius = "12px";
      div.style.marginBottom = "10px";
      div.style.lineHeight = "1.5";
      
      if (msg.role === "user") {
        div.style.alignSelf = "flex-end";
        div.style.background = "var(--brand-primary)";
        div.style.color = "#fff";
        div.style.borderTopRightRadius = "2px";
      } else {
        div.style.alignSelf = "flex-start";
        div.style.background = "var(--bg-lighter)";
        div.style.borderTopLeftRadius = "2px";
      }

      // Format markdown links to real images/videos if present
      let htmlContent = msg.content
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") // basic escape
        .replace(/\n/g, "<br>"); // newlines

      // Basic regex to find markdown image/video links: ![alt](url)
      htmlContent = htmlContent.replace(/!\[.*?\]\((.*?)\)/g, (match, url) => {
        if (url.endsWith(".mp4") || url.endsWith(".webm") || url.includes("video")) {
          return `<br><video src="${url}" controls autoplay loop style="max-width:100%; border-radius:8px; margin-top:10px;"></video>`;
        }
        return `<br><img src="${url}" style="max-width:100%; border-radius:8px; margin-top:10px;" />`;
      });

      // Parse [Option] syntax
      let optionsHtml = "";
      htmlContent = htmlContent.replace(/\[Option\]\s*(.*?)<br>/gi, (match, p1) => {
        const optionText = p1.trim();
        optionsHtml += `<button class="hf-option-btn" style="display:block; width:100%; text-align:left; background:rgba(255,255,255,0.05); border:1px solid rgba(255,103,0,0.3); border-radius:8px; padding:10px 14px; margin-top:8px; color:#fff; font-family:inherit; cursor:pointer; transition:background 0.2s;" onmouseover="this.style.background='rgba(255,103,0,0.1)'" onmouseout="this.style.background='rgba(255,255,255,0.05)'" onclick="window.higgsfieldPage.submitOption('${optionText.replace(/'/g, "\\\\'")}')">${optionText}</button>`;
        return "";
      });
      // Catch [Option] if it's the very last thing without a <br>
      htmlContent = htmlContent.replace(/\[Option\]\s*(.*?)$/gi, (match, p1) => {
        const optionText = p1.trim();
        optionsHtml += `<button class="hf-option-btn" style="display:block; width:100%; text-align:left; background:rgba(255,255,255,0.05); border:1px solid rgba(255,103,0,0.3); border-radius:8px; padding:10px 14px; margin-top:8px; color:#fff; font-family:inherit; cursor:pointer; transition:background 0.2s;" onmouseover="this.style.background='rgba(255,103,0,0.1)'" onmouseout="this.style.background='rgba(255,255,255,0.05)'" onclick="window.higgsfieldPage.submitOption('${optionText.replace(/'/g, "\\\\'")}')">${optionText}</button>`;
        return "";
      });

      div.innerHTML = htmlContent;

      // Render uploaded reference-image thumbnails on the user's own message.
      if (msg.role === "user" && Array.isArray(msg.images) && msg.images.length) {
        const thumbs = msg.images.map(u =>
          `<img src="${u}" alt="reference" style="width:64px; height:64px; object-fit:cover; border-radius:8px; border:1px solid rgba(255,255,255,0.25);" />`
        ).join("");
        div.innerHTML += `<div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:10px;">${thumbs}</div>`;
      }

      if (optionsHtml && msg.role === "assistant") {
        div.innerHTML += `<div style="margin-top:12px; border-top:1px solid rgba(255,255,255,0.1); padding-top:12px;">${optionsHtml}</div>`;
      }
      container.appendChild(div);
    });

    container.scrollTop = container.scrollHeight;
  },

  submitOption(text) {
    const input = document.getElementById("hf-input");
    input.value = text;
    this.sendMessage();
  },

  // Poll an async Veo video render and swap in the <video> when it's ready.
  pollVideoJob(jobId) {
    const container = document.getElementById("hf-messages");
    const card = document.createElement("div");
    card.className = "hf-msg assistant";
    card.style.alignSelf = "flex-start";
    card.style.maxWidth = "80%";
    card.style.background = "var(--bg-lighter)";
    card.style.padding = "16px 20px";
    card.style.borderRadius = "12px";
    card.style.borderTopLeftRadius = "2px";
    card.style.marginBottom = "10px";
    card.innerHTML = `
      <div style="display:flex; gap:10px; align-items:center;">
        <span class="spinner" style="width:16px;height:16px;border:2px solid rgba(255,255,255,0.2);border-top-color:var(--brand-primary);border-radius:50%;animation:spin 1s linear infinite;"></span>
        <span>Rendering your video with Veo 3… this takes 2-4 minutes.</span>
      </div>`;
    container.appendChild(card);
    container.scrollTop = container.scrollHeight;

    const started = Date.now();
    const TIMEOUT_MS = 12 * 60 * 1000; // 12 minutes

    const tick = async () => {
      try {
        // Attach the Supabase JWT (quietly — no toast on transient poll errors).
        let authHeader = {};
        const { data: { session } } = await window.supabaseClient.auth.getSession();
        if (session) authHeader = { Authorization: `Bearer ${session.access_token}` };
        const res = await fetch(`/api/higgsfield/video_status/${jobId}`, { headers: authHeader });
        const data = await res.json();

        if (data.status === "done" && data.url) {
          card.innerHTML = `<video src="${data.url}" controls autoplay loop style="max-width:100%; border-radius:8px;"></video>`;
          container.scrollTop = container.scrollHeight;
          return; // stop polling
        }
        if (data.status === "error") {
          card.innerHTML = `<span style="color:#EF4444;">Video render failed: ${data.error || "unknown error"}</span>`;
          return;
        }
      } catch (e) {
        console.error("video_status poll failed", e);
      }

      if (Date.now() - started > TIMEOUT_MS) {
        card.innerHTML = `<span style="color:#EF4444;">Video render timed out. Please try again.</span>`;
        return;
      }
      setTimeout(tick, 8000);
    };

    setTimeout(tick, 8000);
  },

  async sendMessage() {
    const input = document.getElementById("hf-input");
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    input.style.height = "auto";

    // Snapshot the attachments/context/web state for this turn, then clear the inputs.
    const turnImages = this.pendingImages.slice();
    const context = this.getContext();
    const webEnabled = this.webEnabled;
    this.pendingImages = [];
    this.renderAttachments();

    // Add user message to UI (with any reference thumbnails)
    this.messages.push({ role: "user", content: text, images: turnImages });
    this.renderMessages();

    // Show loading
    const container = document.getElementById("hf-messages");
    const loadingDiv = document.createElement("div");
    loadingDiv.id = "hf-loading";
    loadingDiv.innerHTML = `
      <div style="align-self:flex-start; max-width:80%; background:var(--bg-lighter); padding:16px 20px; border-radius:12px; border-top-left-radius:2px; display:flex; gap:8px;">
        <span class="spinner" style="width:16px;height:16px;border:2px solid rgba(255,255,255,0.2);border-top-color:#fff;border-radius:50%;animation:spin 1s linear infinite;"></span>
        Generating...
      </div>
    `;
    container.appendChild(loadingDiv);
    container.scrollTop = container.scrollHeight;

    // We only send the text content to the backend. The backend manages the tool result formatting.
    // However, since we send the whole history, we should send it as expected.
    const payload = {
      session_id: this.currentSessionId,
      messages: this.messages.map(m => ({ role: m.role, content: m.content })),
      reference_image_urls: turnImages,
      context: context,
      web_enabled: webEnabled
    };

    try {
      const data = await apiFetch("/api/higgsfield/chat", {
        method: "POST",
        body: JSON.stringify(payload)
      });

      if (loadingDiv) loadingDiv.remove();

      if (data.session_id) {
        this.currentSessionId = data.session_id;
      }

      if (data.reply) {
        this.messages.push({ role: "assistant", content: data.reply });
        this.renderMessages();
      } else {
        throw new Error(data.detail || "Empty reply from backend");
      }

      // Kick off polling for any async video render jobs started this turn.
      if (Array.isArray(data.video_jobs) && data.video_jobs.length) {
        data.video_jobs.forEach(jobId => this.pollVideoJob(jobId));
      }

      this.loadSessions(); // refresh title if it was new

    } catch (e) {
      console.error("Failed to send message", e);
      if (loadingDiv) loadingDiv.remove();
      toast.error("Failed to communicate with AI: " + e.message);
    }
  }
};
