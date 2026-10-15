"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const token = document.querySelector('meta[name="pllm-token"]').content;
  const state = { services: [], selected: "model", expanded: false, pending: new Set(), outputs: new Map(), connected: false, closed: false, stateBusy: false, outputBusy: false, actionError: "" };
  const icons = {
    model: '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 1v3m6-3v3M9 20v3m6-3v3M1 9h3m-3 6h3m16-6h3m-3 6h3"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>',
    webui: '<svg viewBox="0 0 24 24"><path d="M20 11.5a8 8 0 0 1-8 8 9 9 0 0 1-3.5-.7L4 20l1.2-4.5a8 8 0 1 1 14.8-4Z"/><path d="M8 10h8M8 13h5"/></svg>',
    sharing: '<svg viewBox="0 0 24 24"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M10 5h4m-3 14h2M3 8c-2 2-2 6 0 8m18-8c2 2 2 6 0 8"/></svg>',
    shell: '<svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m6 9 4 3-4 3m7 0h4"/></svg>',
  };
  const notes = {
    model: "Runs Qwen on your GPU. Keep it running while chatting; the context setting takes effect on the next start.",
    webui: "Your chat website. Conversations stay saved when it stops. The Qwen engine must also be running to generate answers.",
    sharing: "Makes the chat website available to your Tailscale devices. If sudo asks for a password, open Terminal and use Hide input before sending it.",
    shell: "An optional shell in this workspace. Start it when you need to run a command. Commands use your normal account permissions.",
  };
  const labels = { stopped: "Stopped", starting: "Starting", running: "Running", stopping: "Stopping", failed: "Exited with error", external: "Detected outside app" };

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", "X-PLLM-Token": token, ...(options.headers || {}) }, signal: controller.signal, cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.error === "string" ? body.error : body.error?.message || body.message || `Request failed (HTTP ${response.status}).`);
      return body;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("The control app took too long to respond. Try again.");
      throw error;
    } finally { clearTimeout(timer); }
  }
  function post(path, data = {}) { return api(path, { method: "POST", body: JSON.stringify(data) }); }
  function selected() { return state.services.find((service) => service.id === state.selected); }
  function outputFor(id) {
    if (!state.outputs.has(id)) state.outputs.set(id, { next: 0, text: "", seen: false });
    return state.outputs.get(id);
  }
  function isLive(service) { return ["starting", "running", "stopping", "external"].includes(service.status); }
  function formatUptime(seconds) {
    if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return "—";
    const total = Math.max(0, Math.floor(Number(seconds)));
    if (total < 60) return `${total}s`;
    if (total < 3600) return `${Math.floor(total / 60)}m ${total % 60}s`;
    return `${Math.floor(total / 3600)}h ${Math.floor(total % 3600 / 60)}m`;
  }
  function setMessage(message = "", error = false) {
    state.actionError = error ? message : "";
    $("action-message").textContent = error ? "" : message;
    $("action-message").hidden = error || !message;
    renderDetails();
  }
  function connect(ok, message = "") {
    state.connected = ok;
    $("connection").className = `connection ${ok ? "connected" : "disconnected"}`;
    $("connection-label").textContent = state.closed ? "Control app stopped" : ok ? "Local control connected" : "Connection lost";
    $("connection-error").textContent = message;
    $("connection-error").hidden = !message;
  }
  function renderList() {
    const list = $("instance-list");
    if (!list.querySelector(".instance-card")) list.replaceChildren();
    for (const service of state.services) {
      let card = list.querySelector(`[data-service="${service.id}"]`);
      if (!card) {
        card = document.createElement("button");
        card.type = "button";
        card.className = "instance-card";
        card.dataset.service = service.id;
        const icon = document.createElement("span");
        icon.className = "instance-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.innerHTML = icons[service.id] || icons.shell;
        const copy = document.createElement("span");
        copy.className = "card-copy";
        const name = document.createElement("span");
        name.className = "card-name";
        const status = document.createElement("span");
        status.className = "card-status";
        const dot = document.createElement("span");
        dot.className = "status-dot";
        dot.setAttribute("aria-hidden", "true");
        const statusText = document.createElement("span");
        statusText.className = "card-status-text";
        status.append(dot, statusText);
        copy.append(name, status);
        const arrow = document.createElement("span");
        arrow.className = "card-arrow";
        arrow.textContent = "›";
        arrow.setAttribute("aria-hidden", "true");
        card.append(icon, copy, arrow);
        card.addEventListener("click", () => selectService(service.id));
        list.append(card);
      }
      card.setAttribute("aria-current", String(service.id === state.selected));
      card.querySelector(".card-name").textContent = service.name;
      card.querySelector(".card-status").className = `card-status ${service.status}`;
      card.querySelector(".card-status-text").textContent = labels[service.status] || service.status;
    }
    const active = state.services.filter(isLive).length;
    $("running-summary").textContent = `${active} of ${state.services.length} active`;
  }
  function renderDetails() {
    const service = selected();
    if (!service) return;
    $("instance-panel").hidden = false;
    $("instance-icon").innerHTML = icons[service.id] || icons.shell;
    $("instance-name").textContent = service.name;
    $("instance-description").textContent = service.description || "";
    $("instance-status").textContent = labels[service.status] || service.status;
    $("instance-status").className = `status-badge ${service.status}`;
    $("instance-note").textContent = service.status === "external" ? "An existing service or sharing route was detected outside this app. Its original terminal may no longer be open. Stop the external process before starting it here." : notes[service.id] || "";
    $("model-config").hidden = service.id !== "model";
    const pending = state.pending.has(service.id);
    const canStart = ["stopped", "failed"].includes(service.status);
    $("start-button").disabled = !state.connected || pending || !canStart;
    $("start-button").lastChild.textContent = service.status === "starting" ? " Starting…" : " Start instance";
    $("stop-button").disabled = !state.connected || pending || !service.managed || !["starting", "running"].includes(service.status);
    $("context-select").disabled = pending || isLive(service);
    $("process-id").textContent = service.pid ? `PID ${service.pid}` : "—";
    $("process-uptime").textContent = isLive(service) && service.status !== "external" ? formatUptime(service.uptime) : "—";
    $("process-control").textContent = service.status === "external" ? "Outside this app" : service.managed ? "This app" : "Ready to start";
    const error = state.actionError || service.error || "";
    $("instance-error").textContent = error;
    $("instance-error").hidden = !error;
    const link = $("open-chat");
    let url;
    try { url = service.url ? new URL(service.url, window.location.href) : null; } catch { url = null; }
    const safeURL = url && ["http:", "https:"].includes(url.protocol);
    link.hidden = service.id !== "webui" || !service.ready || !safeURL;
    if (safeURL) link.href = url.href;
    const canInput = state.connected && service.terminal_available && service.managed && ["starting", "running"].includes(service.status) && !pending;
    $("terminal-input").disabled = !canInput;
    $("send-button").disabled = !canInput;
    $("interrupt-button").disabled = !canInput;
    $("eof-button").disabled = !canInput;
    $("terminal-input").placeholder = service.status === "external" ? "Terminal belongs to another session" : canInput ? "Send a line to this instance…" : isLive(service) ? "Input is unavailable for this instance" : "Start this instance to send input";
    $("terminal-caption").textContent = service.pid ? `Process transcript · PID ${service.pid}` : "Process transcript";
    if (service.echo === false && !$("hide-input").checked) {
      $("hide-input").checked = true;
      $("terminal-input").type = "password";
    }
    $("terminal-empty").textContent = service.status === "external" ? "This instance was started elsewhere; its terminal output is unavailable here." : isLive(service) ? "Waiting for process output…" : "Output will appear here when this instance starts.";
  }
  function selectService(id) {
    state.selected = id;
    state.actionError = "";
    $("action-message").hidden = true;
    $("terminal-input").value = "";
    $("hide-input").checked = false;
    $("terminal-input").type = "text";
    renderList();
    renderDetails();
    renderOutput(true);
    if (state.expanded) pollOutput();
  }
  async function pollState() {
    if (state.closed || state.stateBusy) return;
    state.stateBusy = true;
    try {
      const payload = await api("/api/state");
      state.services = payload.services || [];
      if (!selected() && state.services.length) state.selected = state.services[0].id;
      connect(true);
      renderList();
      renderDetails();
    } catch (error) {
      connect(false, "Cannot reach the local control app. It may have stopped. " + error.message);
      renderDetails();
    } finally {
      state.stateBusy = false;
      if (!state.closed) setTimeout(pollState, 1500);
    }
  }
  function plainTranscript(text) {
    return text.replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "").replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").replace(/\x1b[@-_]/g, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/[^\x09\x0a\x20-\uffff]/g, "");
  }
  function renderOutput(force = false) {
    const output = outputFor(state.selected);
    const pane = $("terminal-output");
    const wasAtBottom = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 45;
    if (force || $("terminal-text").textContent !== output.text) $("terminal-text").textContent = output.text;
    $("terminal-empty").hidden = Boolean(output.text);
    if ($("auto-scroll").checked && (force || wasAtBottom)) pane.scrollTop = pane.scrollHeight;
  }
  async function pollOutput() {
    if (!state.expanded || state.closed || state.outputBusy || !selected()) return;
    state.outputBusy = true;
    const id = state.selected;
    const output = outputFor(id);
    try {
      const payload = await api(`/api/services/${encodeURIComponent(id)}/output?after=${output.next}`);
      if (payload.reset) output.text = "";
      for (const chunk of payload.chunks || []) output.text += plainTranscript(chunk.text || "");
      output.text = output.text.slice(-300000);
      output.next = payload.next ?? output.next;
      output.seen = true;
      if (state.selected === id) renderOutput();
    } catch (error) {
      if (state.selected === id) setMessage("Could not read terminal output: " + error.message, true);
    } finally { state.outputBusy = false; }
  }
  async function action(kind, data = {}) {
    const service = selected();
    if (!service || state.pending.has(service.id)) return false;
    const id = service.id;
    state.pending.add(id);
    setMessage(kind === "start" ? "Starting instance…" : kind === "stop" ? "Stopping instance…" : "");
    renderDetails();
    try {
      await post(`/api/services/${encodeURIComponent(id)}/${kind}`, data);
      if (state.selected === id) setMessage(kind === "start" ? "Start requested. Status and output will update here." : kind === "stop" ? "Stop requested." : "");
      const payload = await api("/api/state");
      state.services = payload.services || state.services;
      renderList();
      return true;
    } catch (error) { if (state.selected === id) setMessage(error.message, true); return false; }
    finally { state.pending.delete(id); renderDetails(); if (state.expanded) pollOutput(); }
  }

  $("start-button").addEventListener("click", () => action("start", state.selected === "model" ? { context: Number($("context-select").value) } : {}));
  $("stop-button").addEventListener("click", () => action("stop"));
  $("terminal-toggle").addEventListener("click", () => {
    state.expanded = !state.expanded;
    $("terminal-toggle").setAttribute("aria-expanded", String(state.expanded));
    $("terminal-content").hidden = !state.expanded;
    $("terminal-toggle-label").textContent = state.expanded ? "Hide terminal" : "Show output & input";
    if (state.expanded) { renderOutput(true); pollOutput(); }
  });
  $("hide-input").addEventListener("change", () => { $("terminal-input").type = $("hide-input").checked ? "password" : "text"; });
  $("terminal-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const field = $("terminal-input");
    const id = state.selected;
    const value = field.value;
    if (field.disabled) return;
    field.value = "";
    if (!(await action("input", { data: value + "\n" })) && id === state.selected && !$("hide-input").checked) field.value = value;
    if (id === state.selected) field.focus();
  });
  $("interrupt-button").addEventListener("click", () => action("interrupt"));
  $("eof-button").addEventListener("click", () => action("input", { data: "\x04" }));
  $("terminal-input").addEventListener("keydown", (event) => {
    const input = $("terminal-input");
    const hasSelection = input.selectionStart !== input.selectionEnd || Boolean(window.getSelection()?.toString());
    if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === "c" && !hasSelection) { event.preventDefault(); action("interrupt"); }
    if (event.ctrlKey && event.key.toLowerCase() === "d") { event.preventDefault(); action("input", { data: "\x04" }); }
  });
  $("auto-scroll").addEventListener("change", () => { if ($("auto-scroll").checked) $("terminal-output").scrollTop = $("terminal-output").scrollHeight; });
  $("quit-button").addEventListener("click", async () => {
    const active = state.services.filter((service) => service.managed && isLive(service));
    const stopServices = active.length > 0;
    const question = stopServices ? `Stop ${active.length} managed instance${active.length === 1 ? "" : "s"} and quit the control app? Saved chats and settings will be kept. Instances started elsewhere will stay running.` : "Quit the control app? You can launch it again later. Instances started elsewhere will stay running.";
    if (!window.confirm(question)) return;
    $("quit-button").disabled = true;
    try {
      await post("/api/shutdown", { stop_services: stopServices });
      state.closed = true;
      connect(false, "The control app has stopped. You can close this tab and launch it again when you need it.");
      $("running-summary").textContent = "Control app stopped";
      renderDetails();
      $("terminal-toggle").disabled = true;
    } catch (error) {
      $("connection-error").textContent = "Could not quit the control app: " + error.message;
      $("connection-error").hidden = false;
      $("quit-button").disabled = false;
    }
  });
  setInterval(pollOutput, 1000);
  pollState();
})();
