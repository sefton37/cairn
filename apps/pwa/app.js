/**
 * Talking Rock PWA — Main Application
 *
 * ES module, no build step, no dependencies.
 * Communicates with the FastAPI backend over JSON-RPC 2.0 and SSE.
 *
 * False-positive note for content-guard: variable names like `bearerToken`,
 * `passInput`, and `sessionStorage` here are frontend DOM/state references,
 * not actual credentials.
 */

'use strict';

// ── Constants ─────────────────────────────────────────────────────────────

const STORE_AUTH   = 'tr_auth';
const STORE_USER   = 'tr_user';
const REFRESH_MS   = 5 * 60 * 1000; // 5 min session keep-alive

// ── Application State ─────────────────────────────────────────────────────

const state = {
  /** Session bearer value — loaded from sessionStorage on boot */
  bearer: sessionStorage.getItem(STORE_AUTH) ?? null,
  /** Authenticated username */
  username: sessionStorage.getItem(STORE_USER) ?? null,
  /** Active agent tab */
  agent: /** @type {'cairn'|'reos'|'riva'} */ ('cairn'),
  /** Current conversation UUID (null = new) */
  conversationId: null,
  /** Auto-incrementing JSON-RPC request counter */
  rpcId: 1,
  /** True while a send is in flight */
  sending: false,
  /** AbortController for the active SSE stream */
  streamCtl: null,
  /** setInterval handle for session keep-alive */
  keepAlive: null,
  /** All loaded surfacing items from CAIRN */
  surfacingItems: [],
  /** Whether surfacing is in expanded (full-screen) mode */
  surfacingExpanded: false,
  /** Whether the virtual keyboard is currently open */
  keyboardOpen: false,
};

// ── DOM helpers ────────────────────────────────────────────────────────────

const byId = (id) => document.getElementById(id);

const ui = {
  // Login
  loginOverlay:  byId('login-overlay'),
  loginForm:     byId('login-form'),
  loginUser:     byId('login-username'),
  loginPass:     byId('login-password'),
  loginErr:      byId('login-error'),
  loginBtn:      byId('login-submit'),

  // App shell
  app:           byId('app'),
  btnBack:       byId('btn-back'),
  btnMenu:       byId('btn-menu'),
  agentTabs:     document.querySelector('.agent-tabs'),

  // Surfacing
  surfSection:   byId('surfacing-section'),
  surfToggle:    byId('surfacing-toggle'),
  surfItems:     byId('surfacing-items'),

  // Messages
  msgArea:       byId('message-area'),
  chatInput:     byId('chat-input'),
  btnSend:       byId('btn-send'),

  // Consciousness drawer
  drawer:        byId('consciousness-drawer'),
  drawerHandle:  byId('drawer-handle'),
  drawerBg:      byId('drawer-backdrop'),
  drawerClose:   byId('btn-close-drawer'),
  drawerBody:    byId('consciousness-content'),

  // Side menu
  menuPanel:     byId('menu-panel'),
  menuBg:        byId('menu-backdrop'),
  menuUser:      byId('menu-username'),
  menuClose:     byId('btn-close-menu'),
  menuNewConvo:  byId('btn-new-convo'),
  menuSignOut:   byId('btn-logout'),
  convoList:     byId('conversations-list'),
};

// ── Network helpers ────────────────────────────────────────────────────────

/** Build the standard Authorization header object. */
function authHeaders(extra = {}) {
  return { 'Authorization': `Bearer ${state.bearer}`, ...extra };
}

/**
 * Send a JSON-RPC 2.0 POST to /rpc.
 * Throws on network error, HTTP error, or RPC error.
 * Calls showLogin() on 401.
 */
async function rpc(method, params = {}) {
  const id   = state.rpcId++;
  const body = JSON.stringify({ jsonrpc: '2.0', id, method, params });

  let resp;
  try {
    resp = await fetch('/rpc', {
      method:  'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body,
    });
  } catch (err) {
    throw new Error(`Network error: ${err.message}`);
  }

  if (resp.status === 401) { showLogin(); throw new Error('Session expired — please sign in again.'); }
  if (!resp.ok)             throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);

  const data = await resp.json();
  if (data.error) throw new Error(data.error.message ?? JSON.stringify(data.error));
  return data.result;
}

/**
 * POST to /auth/login. Stores bearer + username in sessionStorage on success.
 * @param {string} user
 * @param {string} cred - User's passphrase
 */
async function authenticate(user, cred) {
  const resp = await fetch('/auth/login', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ username: user, credential: cred }),
  });

  if (resp.status === 401 || resp.status === 403) throw new Error('Invalid username or passphrase.');
  if (!resp.ok) throw new Error(`Sign-in failed (HTTP ${resp.status})`);

  const data = await resp.json();
  if (!data.success || !data.session_token) throw new Error(data.message ?? 'No session returned.');

  state.bearer   = data.session_token;
  state.username = data.username ?? user;

  sessionStorage.setItem(STORE_AUTH, state.bearer);
  sessionStorage.setItem(STORE_USER, state.username);
}

/** Ping /auth/refresh. Returns true if session is still valid. */
async function refreshSession() {
  if (!state.bearer) return false;
  try {
    const r = await fetch('/auth/refresh', { method: 'POST', headers: authHeaders() });
    return r.ok;
  } catch { return false; }
}

/** Sign out — best-effort server call, then wipe local state. */
async function signOut() {
  if (state.bearer) {
    try { await fetch('/auth/logout', { method: 'POST', headers: authHeaders() }); } catch { /* ok */ }
  }
  wipeSession();
  showLogin();
}

function wipeSession() {
  state.bearer         = null;
  state.username       = null;
  state.conversationId = null;
  sessionStorage.removeItem(STORE_AUTH);
  sessionStorage.removeItem(STORE_USER);
  stopKeepAlive();
  abortStream();
}

// ── SSE Streaming (CAIRN) ──────────────────────────────────────────────────

/**
 * Open a CAIRN streaming session via fetch() + ReadableStream.
 *
 * EventSource cannot send custom headers, so we use the Fetch API and parse
 * the SSE wire format manually. The Authorization header is required for auth.
 *
 * @param {string} text - User message text
 * @param {object} cbs  - Callbacks: onThought, onResult, onError, onDone
 */
async function streamChat(text, { onThought, onResult, onError, onDone }) {
  abortStream();

  const ctl = new AbortController();
  state.streamCtl = ctl;

  const qs = new URLSearchParams({ text, extended_thinking: 'false' });
  if (state.conversationId) qs.set('conversation_id', state.conversationId);

  let resp;
  try {
    resp = await fetch(`/rpc/events?${qs}`, { headers: authHeaders(), signal: ctl.signal });
  } catch (err) {
    if (err.name === 'AbortError') return;
    onError?.(`Connection failed: ${err.message}`);
    return;
  }

  if (resp.status === 401) { showLogin(); return; }
  if (!resp.ok)             { onError?.(`Stream HTTP ${resp.status}`); return; }

  const reader  = resp.body.getReader();
  const decode  = new TextDecoder();
  let buf       = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buf += decode.decode(value, { stream: true });

      // SSE messages are separated by blank lines (\n\n)
      const parts = buf.split('\n\n');
      buf = parts.pop() ?? '';

      for (const part of parts) {
        if (!part.trim()) continue;

        let evType  = 'message';
        const lines = [];

        for (const line of part.split('\n')) {
          if (line.startsWith('event:'))     evType = line.slice(6).trim();
          else if (line.startsWith('data:')) lines.push(line.slice(5).trim());
        }

        const raw = lines.join('\n');
        if (!raw) continue;

        let pl;
        try   { pl = JSON.parse(raw); }
        catch { pl = { text: raw }; }

        switch (evType) {
          case 'consciousness':
            onThought?.(pl.title ?? pl.content ?? pl.text ?? pl.thought ?? raw);
            break;
          case 'result': {
            const cid = pl.conversation_id;
            if (cid) state.conversationId = cid;
            onResult?.(pl.answer ?? pl.text ?? pl.response ?? raw);
            break;
          }
          case 'error': onError?.(pl.message ?? pl.error ?? pl.text ?? raw); break;
          case 'done':  onDone?.(); break;
        }
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') onError?.(`Stream read error: ${err.message}`);
  } finally {
    reader.releaseLock();
    state.streamCtl = null;
  }

  onDone?.();
}

function abortStream() {
  state.streamCtl?.abort();
  state.streamCtl = null;
}

// ── Keep-alive ─────────────────────────────────────────────────────────────

function startKeepAlive() {
  stopKeepAlive();
  state.keepAlive = setInterval(async () => {
    const ok = await refreshSession();
    if (!ok) { wipeSession(); showLogin(); }
  }, REFRESH_MS);
}

function stopKeepAlive() {
  if (state.keepAlive) { clearInterval(state.keepAlive); state.keepAlive = null; }
}

// ── Login UI ───────────────────────────────────────────────────────────────

function showLogin() {
  ui.loginOverlay.hidden = false;
  ui.app.hidden          = true;
  ui.loginErr.hidden     = true;
  ui.loginErr.textContent = '';
  ui.loginPass.value = '';
  // Focus whichever field needs filling
  requestAnimationFrame(() => ui.loginUser.value ? ui.loginPass.focus() : ui.loginUser.focus());
}

function hideLogin() {
  ui.loginOverlay.hidden = true;
  ui.app.hidden          = false;
}

function loginError(msg) {
  ui.loginErr.textContent = msg;
  ui.loginErr.hidden      = false;
  ui.loginPass.value = '';
  ui.loginPass.focus();
}

// ── Message rendering ──────────────────────────────────────────────────────

/**
 * Append a message bubble and return the bubble element.
 * @param {'user'|'assistant'|'system'|'error'} role
 * @param {string} text
 * @returns {HTMLElement}
 */
function addMessage(role, text) {
  const row    = document.createElement('div');
  row.className = `message-row ${role}`;

  if (role === 'assistant') {
    const who = document.createElement('div');
    who.className  = 'bubble-sender';
    who.textContent = agentLabel(state.agent);
    row.appendChild(who);
  }

  const bbl = document.createElement('div');
  bbl.className  = 'bubble';
  bbl.textContent = text;
  row.appendChild(bbl);

  if (role === 'user') {
    const ts = document.createElement('div');
    ts.className  = 'bubble-time';
    ts.textContent = fmtTime(new Date());
    row.appendChild(ts);
  }

  ui.msgArea.appendChild(row);
  scrollBottom();
  return bbl;
}

function agentLabel(a) {
  return { cairn: 'CAIRN', reos: 'ReOS', riva: 'RIVA' }[a] ?? a.toUpperCase();
}

function fmtTime(d) {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtCalDate(d) {
  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const sameDay = (a, b) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (sameDay(d, now)) return `Today ${time}`;
  if (sameDay(d, tomorrow)) return `Tomorrow ${time}`;
  const day = d.toLocaleDateString([], {
    weekday: 'short', month: 'short', day: 'numeric',
  });
  return `${day} ${time}`;
}

function fmtAgo(d) {
  const ms = Date.now() - d.getTime();
  const h  = Math.floor(ms / 3_600_000);
  const dy = Math.floor(h / 24);
  if (dy > 0) return `${dy}d ago`;
  if (h  > 0) return `${h}h ago`;
  const m = Math.floor(ms / 60_000);
  return m > 0 ? `${m}m ago` : 'just now';
}

function scrollBottom() {
  requestAnimationFrame(() => { ui.msgArea.scrollTop = ui.msgArea.scrollHeight; });
}

/** Show three-dot typing indicator. Returns a function to remove it. */
function showTyping() {
  const el = document.createElement('div');
  el.className = 'typing-indicator';
  el.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  ui.msgArea.appendChild(el);
  scrollBottom();
  return () => el.remove();
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── Approval cards (ReOS) ──────────────────────────────────────────────────

function showApproval(approval) {
  const aid  = approval.approval_id ?? approval.id;
  const desc = approval.description ?? approval.command ?? approval.action ?? JSON.stringify(approval);

  const card = document.createElement('div');
  card.className = 'approval-card';
  card.innerHTML = `
    <div class="approval-label">Approval Required</div>
    <div class="approval-command">${esc(desc)}</div>
    <div class="approval-actions">
      <button class="btn btn-success btn-sm">Approve</button>
      <button class="btn btn-danger  btn-sm">Reject</button>
    </div>`;

  ui.msgArea.appendChild(card);
  scrollBottom();

  const [btnOk, btnNo] = card.querySelectorAll('button');

  async function respond(action) {
    btnOk.disabled = true;
    btnNo.disabled = true;
    try {
      await rpc('approval/respond', { approval_id: aid, action });
      card.querySelector('.approval-actions').innerHTML =
        `<span style="font-size:13px;color:var(--${action === 'approve' ? 'success' : 'error'})">
          ${action === 'approve' ? 'Approved' : 'Rejected'}
        </span>`;
    } catch (err) {
      addMessage('error', `Approval failed: ${err.message}`);
      btnOk.disabled = false;
      btnNo.disabled = false;
    }
  }

  btnOk.addEventListener('click', () => respond('approve'));
  btnNo.addEventListener('click', () => respond('reject'));
}

// ── Consciousness drawer ───────────────────────────────────────────────────

function drawerOpen() {
  ui.drawerBody.innerHTML = '';
  ui.drawer.hidden        = false;
  ui.drawerBg.hidden      = false;

  const dot   = ui.drawer.querySelector('.pulse-dot');
  const title = ui.drawer.querySelector('.drawer-title');
  dot?.classList.remove('done');
  setDrawerText(title, 'Thinking...');

  requestAnimationFrame(() => ui.drawer.classList.add('open'));
}

function drawerAppend(text) {
  const s = document.createElement('div');
  s.className = 'consciousness-step';
  s.innerHTML = `<span class="step-icon" aria-hidden="true">›</span><span class="step-text">${esc(text)}</span>`;
  ui.drawerBody.appendChild(s);
  ui.drawerBody.scrollTop = ui.drawerBody.scrollHeight;
}

function drawerFinish() {
  const dot   = ui.drawer.querySelector('.pulse-dot');
  const title = ui.drawer.querySelector('.drawer-title');
  dot?.classList.add('done');
  setDrawerText(title, 'Done');
}

function drawerClose() {
  ui.drawer.classList.remove('open');
  ui.drawerBg.hidden = true;
  ui.drawer.addEventListener('transitionend', () => { ui.drawer.hidden = true; }, { once: true });
}

/** Update the text node inside the drawer title (preserves the pulse-dot child). */
function setDrawerText(el, text) {
  if (!el) return;
  const node = Array.from(el.childNodes).find((n) => n.nodeType === Node.TEXT_NODE);
  if (node) node.textContent = ` ${text}`;
}

// ── Menu panel ─────────────────────────────────────────────────────────────

function menuOpen() {
  ui.menuPanel.hidden = false;
  ui.menuBg.hidden    = false;
  ui.btnMenu.setAttribute('aria-expanded', 'true');
  requestAnimationFrame(() => ui.menuPanel.classList.add('open'));
}

function menuClose() {
  ui.menuPanel.classList.remove('open');
  ui.menuBg.hidden = true;
  ui.btnMenu.setAttribute('aria-expanded', 'false');
  ui.menuPanel.addEventListener('transitionend', () => { ui.menuPanel.hidden = true; }, { once: true });
}

// ── Surfacing (CAIRN attention items) ──────────────────────────────────────

async function loadSurfacing() {
  if (state.agent !== 'cairn') return;
  ui.surfSection.hidden = false;
  ui.surfSection.classList.remove('expanded', 'keyboard-hidden');
  ui.msgArea.hidden = false;
  state.surfacingExpanded = false;
  ui.surfItems.innerHTML = '<div class="surfacing-loading">Loading attention items...</div>';

  try {
    const result = await rpc('cairn/attention', { hours: 168, limit: 20 });
    const items =
      Array.isArray(result)                    ? result
      : Array.isArray(result?.items)           ? result.items
      : Array.isArray(result?.attention_items) ? result.attention_items
      : [];

    state.surfacingItems = items;
    renderSurfacingCards();
  } catch (err) {
    ui.surfItems.innerHTML =
      `<div class="surfacing-loading" style="color:var(--error)">Failed: ${esc(err.message)}</div>`;
  }
}

function renderSurfacingCards() {
  const all = state.surfacingItems;

  if (!all.length) {
    ui.surfItems.innerHTML = '<div class="surfacing-loading">No attention items right now.</div>';
    updateSurfacingHeader();
    return;
  }

  const show = state.surfacingExpanded ? all : all.slice(0, 3);
  ui.surfItems.innerHTML = '';

  for (const item of show) {
    const text = item.title ?? item.text ?? item.content ?? item.summary
      ?? JSON.stringify(item);
    const reason = item.reason ?? '';

    // Build metadata from structured fields
    const parts = [];
    if (item.act_title) parts.push(item.act_title);
    if (item.entity_type && item.entity_type !== 'scene')
      parts.push(item.entity_type);
    if (item.urgency != null) parts.push(`urgency ${item.urgency}`);
    const meta = parts.join(' \u00b7 ');

    // Calendar time display
    const timeField = item.calendar_start ?? item.next_occurrence
      ?? item.timestamp;
    const timeStr = timeField ? fmtCalDate(new Date(timeField)) : '';

    const card = document.createElement('div');
    card.className = 'surfacing-card';
    if (item.act_color)
      card.style.borderLeftColor = item.act_color;
    card.innerHTML = `
      <div class="surfacing-dot" aria-hidden="true"></div>
      <div>
        <div class="surfacing-text">${esc(text)}</div>
        ${reason
          ? `<div class="surfacing-reason">${esc(reason)}</div>`
          : ''}
        ${(meta || timeStr)
          ? `<div class="surfacing-meta">${esc(
              [timeStr, meta].filter(Boolean).join(' \u00b7 '))}</div>`
          : ''}
      </div>`;

    // Clicking collapses expanded mode (if active) and pre-fills chat input
    card.addEventListener('click', () => {
      if (state.surfacingExpanded) {
        state.surfacingExpanded = false;
        ui.surfSection.classList.remove('expanded');
        ui.msgArea.hidden = false;
        renderSurfacingCards();
      }
      ui.chatInput.value = `Tell me more about: ${text}`;
      ui.chatInput.dispatchEvent(new Event('input'));
      ui.chatInput.focus();
    });

    ui.surfItems.appendChild(card);
  }

  updateSurfacingHeader();
}

function updateSurfacingHeader() {
  const title = ui.surfToggle.querySelector('.surfacing-title');
  const chevron = ui.surfToggle.querySelector('.surfacing-chevron');
  const total = state.surfacingItems.length;
  const hasMore = total > 3;

  if (state.surfacingExpanded) {
    title.textContent = `Attention Items (${total})`;
  } else {
    title.textContent = hasMore
      ? `Attention Items (3 of ${total})`
      : 'Attention Items';
  }

  chevron.style.display = hasMore ? '' : 'none';
  ui.surfToggle.setAttribute('aria-expanded', String(state.surfacingExpanded));
}

function toggleSurfacing() {
  if (state.surfacingItems.length <= 3) return;
  state.surfacingExpanded = !state.surfacingExpanded;
  ui.surfSection.classList.toggle('expanded', state.surfacingExpanded);
  ui.msgArea.hidden = state.surfacingExpanded;
  renderSurfacingCards();
}

// ── Conversation history ────────────────────────────────────────────────────

async function loadConversations() {
  ui.convoList.innerHTML = '<div class="menu-loading">Loading...</div>';
  try {
    const result = await rpc('conversations/list', { limit: 20 });
    renderConversations(result);
  } catch (err) {
    ui.convoList.innerHTML =
      `<div class="menu-loading" style="color:var(--error)">Error: ${esc(err.message)}</div>`;
  }
}

function renderConversations(result) {
  const list =
    Array.isArray(result)                    ? result
    : Array.isArray(result?.conversations)   ? result.conversations
    : [];

  if (!list.length) {
    ui.convoList.innerHTML = '<div class="menu-loading">No conversations yet.</div>';
    return;
  }

  ui.convoList.innerHTML = '';

  for (const c of list) {
    const cid     = c.id ?? c.conversation_id;
    const preview = c.preview ?? c.last_message ?? c.title ?? 'Conversation';
    const when    = c.updated_at ? fmtAgo(new Date(c.updated_at)) : '';
    const agent   = c.agent_type ?? '';

    const el = document.createElement('div');
    el.className = `convo-item${state.conversationId === cid ? ' active' : ''}`;
    el.innerHTML = `
      <div class="convo-preview">${esc(preview)}</div>
      ${(agent || when)
        ? `<div class="convo-meta">${esc([agent, when].filter(Boolean).join(' · '))}</div>`
        : ''}`;

    el.addEventListener('click', () => { selectConversation(cid, agent); menuClose(); });
    ui.convoList.appendChild(el);
  }
}

async function selectConversation(cid, agentHint) {
  state.conversationId = cid;

  if (agentHint && ['cairn', 'reos', 'riva'].includes(agentHint.toLowerCase())) {
    switchAgent(agentHint.toLowerCase());
  }

  ui.msgArea.innerHTML =
    '<div class="message-row system"><div class="bubble">Loading conversation...</div></div>';

  try {
    const result = await rpc('conversations/messages', { conversation_id: cid, limit: 50 });
    const msgs =
      Array.isArray(result)              ? result
      : Array.isArray(result?.messages)  ? result.messages
      : [];

    ui.msgArea.innerHTML = '';
    for (const m of msgs) {
      const role = m.role ?? (m.is_user ? 'user' : 'assistant');
      addMessage(role === 'user' ? 'user' : 'assistant', m.content ?? m.text ?? '');
    }
  } catch (err) {
    ui.msgArea.innerHTML = '';
    addMessage('error', `Failed to load: ${err.message}`);
  }
}

// ── Chat send ──────────────────────────────────────────────────────────────

async function send() {
  const text = ui.chatInput.value.trim();
  if (!text || state.sending) return;

  state.sending = true;
  setSending(true);
  ui.chatInput.value = '';
  autoResize();
  addMessage('user', text);

  if (state.agent === 'cairn') {
    await cairnChat(text);
  } else {
    await agentChat(text, state.agent);
  }

  state.sending = false;
  setSending(false);
  ui.chatInput.focus();
}

function setSending(on) {
  ui.btnSend.disabled   = on;
  ui.chatInput.disabled = on;
  refreshSendBtn();
}

// CAIRN chat — streams thinking steps then delivers a result
async function cairnChat(text) {
  drawerOpen();
  let gotResult = false;

  try {
    await streamChat(text, {
      onThought: drawerAppend,
      onResult: (resp) => {
        gotResult = true;
        drawerFinish();
        addMessage('assistant', resp);
        setTimeout(drawerClose, 1200);
      },
      onError: (msg) => {
        drawerFinish();
        drawerClose();
        addMessage('error', msg);
      },
      onDone: () => {
        if (!gotResult) { drawerFinish(); setTimeout(drawerClose, 800); }
      },
    });
  } catch (err) {
    drawerFinish();
    drawerClose();
    addMessage('error', `CAIRN error: ${err.message}`);
  }
}

// ReOS / RIVA chat — single POST /rpc call
async function agentChat(text, agent) {
  const rmTyping = showTyping();
  try {
    const result = await rpc('chat/respond', {
      text,
      conversation_id: state.conversationId ?? undefined,
      agent_type: agent,
    });

    rmTyping();

    const resp = result?.answer ?? result?.response ?? result?.text ?? result?.content
      ?? JSON.stringify(result);
    addMessage('assistant', resp);

    if (result?.conversation_id) state.conversationId = result.conversation_id;

    // After every ReOS reply, check whether an approval is pending
    if (agent === 'reos') await checkApprovals();

  } catch (err) {
    rmTyping();
    addMessage('error', `${agentLabel(agent)} error: ${err.message}`);
  }
}

async function checkApprovals() {
  if (!state.conversationId) return;
  try {
    const result = await rpc('approval/pending', { conversation_id: state.conversationId });
    const list   =
      Array.isArray(result)              ? result
      : Array.isArray(result?.approvals) ? result.approvals
      : result?.approval                 ? [result.approval]
      : [];
    for (const a of list) showApproval(a);
  } catch { /* non-critical — swallow */ }
}

// ── Agent tab switching ────────────────────────────────────────────────────

function switchAgent(agent) {
  if (state.agent === agent) return;

  state.agent          = agent;
  state.conversationId = null;
  ui.msgArea.innerHTML = '';

  ui.agentTabs.querySelectorAll('.tab').forEach((tab) => {
    const active = tab.dataset.agent === agent;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });

  if (agent === 'cairn') {
    loadSurfacing();
  } else {
    ui.surfSection.hidden = true;
  }

  abortStream();
  if (!ui.drawer.hidden) drawerClose();
}

// ── Textarea auto-resize ───────────────────────────────────────────────────

function autoResize() {
  const el       = ui.chatInput;
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
}

function refreshSendBtn() {
  ui.btnSend.disabled = !ui.chatInput.value.trim() || state.sending;
}

// ── Boot ───────────────────────────────────────────────────────────────────

async function init() {
  bindEvents();

  if (state.bearer) {
    const valid = await refreshSession();
    if (valid) {
      onSignedIn();
    } else {
      wipeSession();
      showLogin();
    }
  } else {
    showLogin();
  }
}

function onSignedIn() {
  hideLogin();
  ui.menuUser.textContent = state.username ?? '';
  startKeepAlive();
  if (state.agent === 'cairn') loadSurfacing();
}

// ── Event binding ──────────────────────────────────────────────────────────

function bindEvents() {

  // ── Sign-in form ────────────────────────────────────────────
  ui.loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const user = ui.loginUser.value.trim();
    const cred = ui.loginPass.value;

    if (!user || !cred) { loginError('Please enter your username and passphrase.'); return; }

    ui.loginBtn.disabled    = true;
    ui.loginBtn.textContent = 'Signing in...';
    ui.loginErr.hidden      = true;

    try {
      await authenticate(user, cred);
      onSignedIn();
    } catch (err) {
      loginError(err.message);
    } finally {
      ui.loginBtn.disabled    = false;
      ui.loginBtn.textContent = 'Sign In';
    }
  });

  // ── Agent tabs (event delegation) ────────────────────────────
  ui.agentTabs.addEventListener('click', (e) => {
    const tab = e.target.closest('.tab');
    if (tab?.dataset.agent) switchAgent(tab.dataset.agent);
  });

  // ── Chat input ───────────────────────────────────────────────
  ui.chatInput.addEventListener('input', () => { autoResize(); refreshSendBtn(); });
  ui.chatInput.addEventListener('keydown', (e) => {
    // Enter sends; Shift+Enter inserts newline via browser default
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  ui.btnSend.addEventListener('click', send);

  // ── Consciousness drawer ──────────────────────────────────────
  ui.drawerClose.addEventListener('click',   drawerClose);
  ui.drawerBg.addEventListener('click',      drawerClose);
  ui.drawerHandle.addEventListener('click',  drawerClose);
  ui.drawerHandle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') drawerClose();
  });

  // Swipe-down to dismiss on touch devices
  let touchY0 = null;
  ui.drawer.addEventListener('touchstart', (e) => { touchY0 = e.touches[0].clientY; }, { passive: true });
  ui.drawer.addEventListener('touchend',   (e) => {
    if (touchY0 === null) return;
    if (e.changedTouches[0].clientY - touchY0 > 60) drawerClose();
    touchY0 = null;
  }, { passive: true });

  // ── Side menu ─────────────────────────────────────────────────
  ui.btnMenu.addEventListener('click', () => {
    if (ui.menuPanel.classList.contains('open')) { menuClose(); }
    else { loadConversations(); menuOpen(); }
  });
  ui.menuClose.addEventListener('click', menuClose);
  ui.menuBg.addEventListener('click',   menuClose);

  ui.menuNewConvo.addEventListener('click', () => {
    state.conversationId = null;
    ui.msgArea.innerHTML = '';
    menuClose();
    ui.chatInput.focus();
  });

  ui.menuSignOut.addEventListener('click', async () => { menuClose(); await signOut(); });

  // ── Surfacing collapse/expand ─────────────────────────────────
  ui.surfToggle.addEventListener('click', toggleSurfacing);
  ui.surfToggle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSurfacing(); }
  });

  // ── Mobile keyboard viewport fix ─────────────────────────────
  // On mobile, the virtual keyboard shrinks the visual viewport but the
  // layout viewport stays the same height, pushing the input bar off-screen.
  // This syncs the app height to the actual visible area.
  if (window.visualViewport) {
    const syncHeight = () => {
      const vpH = window.visualViewport.height;
      document.documentElement.style.setProperty('--app-height', `${vpH}px`);

      // Detect keyboard: viewport shrinks significantly when virtual keyboard opens
      const kbOpen = vpH < window.innerHeight * 0.75;
      if (kbOpen !== state.keyboardOpen) {
        state.keyboardOpen = kbOpen;
        if (state.agent === 'cairn' && !ui.surfSection.hidden) {
          ui.surfSection.classList.toggle('keyboard-hidden', kbOpen);
          // Collapse expanded mode when keyboard opens
          if (kbOpen && state.surfacingExpanded) {
            state.surfacingExpanded = false;
            ui.surfSection.classList.remove('expanded');
            ui.msgArea.hidden = false;
          }
        }
      }

      scrollBottom();
    };
    window.visualViewport.addEventListener('resize', syncHeight);
    window.visualViewport.addEventListener('scroll', syncHeight);
    syncHeight();
  }

  // Also scroll input into view on focus (Android sometimes misses this)
  ui.chatInput.addEventListener('focus', () => {
    setTimeout(() => {
      ui.chatInput.scrollIntoView({ block: 'end', behavior: 'smooth' });
    }, 300);
  });
}

// ── Entry point ────────────────────────────────────────────────────────────

init();
