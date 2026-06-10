/**
 * Higgsfield Studio UI Controller
 */

window.higgsfieldPage = {
  currentSessionId: null,
  messages: [],

  init() {
    this.setupEventListeners();
    this.loadSessions();
  },

  setupEventListeners() {
    document.getElementById("hf-new-chat").addEventListener("click", () => {
      this.currentSessionId = null;
      this.messages = [];
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
  },

  async loadSessions() {
    try {
      const res = await fetch("/api/higgsfield/sessions");
      const data = await res.json();
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
      const res = await fetch(`/api/higgsfield/sessions/${sessionId}/messages`);
      const data = await res.json();
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
        optionsHtml += `<button class="hf-option-btn" style="display:block; width:100%; text-align:left; background:rgba(255,255,255,0.05); border:1px solid rgba(255,107,0,0.3); border-radius:8px; padding:10px 14px; margin-top:8px; color:#fff; font-family:inherit; cursor:pointer; transition:background 0.2s;" onmouseover="this.style.background='rgba(255,107,0,0.1)'" onmouseout="this.style.background='rgba(255,255,255,0.05)'" onclick="window.higgsfieldPage.submitOption('${optionText.replace(/'/g, "\\\\'")}')">${optionText}</button>`;
        return "";
      });
      // Catch [Option] if it's the very last thing without a <br>
      htmlContent = htmlContent.replace(/\[Option\]\s*(.*?)$/gi, (match, p1) => {
        const optionText = p1.trim();
        optionsHtml += `<button class="hf-option-btn" style="display:block; width:100%; text-align:left; background:rgba(255,255,255,0.05); border:1px solid rgba(255,107,0,0.3); border-radius:8px; padding:10px 14px; margin-top:8px; color:#fff; font-family:inherit; cursor:pointer; transition:background 0.2s;" onmouseover="this.style.background='rgba(255,107,0,0.1)'" onmouseout="this.style.background='rgba(255,255,255,0.05)'" onclick="window.higgsfieldPage.submitOption('${optionText.replace(/'/g, "\\\\'")}')">${optionText}</button>`;
        return "";
      });

      div.innerHTML = htmlContent;
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

  async sendMessage() {
    const input = document.getElementById("hf-input");
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    input.style.height = "auto";

    // Add user message to UI
    this.messages.push({ role: "user", content: text });
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
      messages: this.messages.map(m => ({ role: m.role, content: m.content }))
    };

    try {
      const res = await fetch("/api/higgsfield/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      
      if (loadingDiv) loadingDiv.remove();

      if (data.session_id) {
        this.currentSessionId = data.session_id;
      }

      this.messages.push({ role: "assistant", content: data.reply });
      this.renderMessages();
      this.loadSessions(); // refresh title if it was new

    } catch (e) {
      console.error("Failed to send message", e);
      if (loadingDiv) loadingDiv.remove();
      app.showToast("Failed to communicate with AI.", "error");
    }
  }
};
