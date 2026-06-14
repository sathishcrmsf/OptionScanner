// alerts.js — Market Event Alerts page
// Polls /api/events, manages alert rules, settings, and test alerts.

const POLL_MS = 10000;
let activeType = "";
let pollTimer = null;

const EVENT_ICON = {
  economic: "📅", news: "📰", unusual_move: "📈", political: "🗣️", test: "🧪",
};

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

// ── Event feed ────────────────────────────────────────────────────────────

function renderEvents(events) {
  const feed = document.getElementById("event-feed");
  if (!events.length) {
    feed.innerHTML = `<div class="empty">No events yet. The monitor checks every poll interval.</div>`;
    return;
  }
  feed.innerHTML = events.map((e) => {
    const icon = EVENT_ICON[e.event_type] || "•";
    const sym = e.symbol ? `<span class="chip">${esc(e.symbol)}</span>` : "";
    const url = e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">source ↗</a>` : "";
    const body = e.body ? `<div class="event-body">${esc(e.body)}</div>` : "";
    return `
      <div class="event-card sev-${esc(e.severity)} ${e.seen ? "" : "unseen"}" data-id="${esc(e.id)}">
        <div class="event-top">
          <div>
            <div class="event-title">${icon} ${esc(e.title)}</div>
            <div class="event-meta">${esc(e.event_type)} · ${esc(e.severity)} · ${timeAgo(e.detected_at)}</div>
          </div>
          ${sym}
        </div>
        ${body}
        <div class="event-actions">
          ${url}
          <a href="/scanner" >open scanner →</a>
          ${e.seen ? "" : `<button class="mark-seen" data-id="${esc(e.id)}">mark read</button>`}
        </div>
      </div>`;
  }).join("");

  feed.querySelectorAll(".mark-seen").forEach((btn) => {
    btn.addEventListener("click", () => markSeen(btn.dataset.id));
  });
}

function loadEvents() {
  const q = activeType ? `?type=${encodeURIComponent(activeType)}` : "";
  fetch(`/api/events${q}`)
    .then((r) => r.json())
    .then((d) => renderEvents(d.events || []))
    .catch(() => {});
}

function markSeen(id) {
  fetch(`/api/events/${id}/seen`, { method: "POST" })
    .then(() => loadEvents())
    .catch(() => {});
}

// ── Monitor status ────────────────────────────────────────────────────────

function loadStatus() {
  fetch("/api/monitor/status")
    .then((r) => r.json())
    .then((s) => {
      const pill = document.getElementById("monitor-pill");
      if (s.running) {
        pill.textContent = `monitor: live · ${s.events_today || 0} today`;
        pill.classList.add("live");
      } else {
        pill.textContent = "monitor: idle (configure a source)";
        pill.classList.remove("live");
      }
      const ch = s.channels || {};
      const prov = s.providers || {};
      document.getElementById("channel-hint").innerHTML =
        `Channels — in-app ✓ · telegram ${ch.telegram ? "✓" : "✗"} · desktop ${ch.desktop ? "✓" : "✗"}<br>` +
        `Sources — finnhub ${prov.finnhub ? "✓" : "✗"} · alpaca ${prov.alpaca ? "✓" : "✗"} · political ${prov.political ? "✓" : "✗"}`;
    })
    .catch(() => {});
}

// ── Rules ─────────────────────────────────────────────────────────────────

function loadRules() {
  fetch("/api/alert-rules")
    .then((r) => r.json())
    .then((d) => {
      const list = document.getElementById("rules-list");
      const rules = d.rules || [];
      if (!rules.length) {
        list.innerHTML = `<div class="empty">No rules yet.</div>`;
        return;
      }
      list.innerHTML = rules.map((r) => {
        const syms = r.symbols.length ? r.symbols.join(", ") : "any symbol";
        const kws = r.keywords.length ? ` · kw: ${r.keywords.join(", ")}` : "";
        const types = r.source_filter.length ? r.source_filter.join("/") : "all types";
        return `
          <div class="rule-item">
            <div class="rule-head">
              <strong>${esc(r.name)}</strong>
              <span>
                <button class="toggle-rule" data-id="${esc(r.id)}" data-enabled="${r.enabled}"
                  style="background:none;border:none;cursor:pointer;color:${r.enabled ? "#22c55e" : "#94a3b8"};">
                  ${r.enabled ? "● on" : "○ off"}
                </button>
                <button class="del-rule" data-id="${esc(r.id)}"
                  style="background:none;border:none;cursor:pointer;color:#ef4444;">✕</button>
              </span>
            </div>
            <div class="muted">${esc(types)} · ≥${esc(r.min_severity)} · ${esc(syms)}${esc(kws)}</div>
            <div class="muted">→ ${r.channels.join(", ")}</div>
          </div>`;
      }).join("");

      list.querySelectorAll(".del-rule").forEach((b) =>
        b.addEventListener("click", () => deleteRule(b.dataset.id)));
      list.querySelectorAll(".toggle-rule").forEach((b) =>
        b.addEventListener("click", () => toggleRule(b.dataset.id, b.dataset.enabled !== "true")));
    })
    .catch(() => {});
}

function parseList(v) {
  return v.split(",").map((s) => s.trim()).filter(Boolean);
}

function checkedValues(containerId) {
  return Array.from(document.querySelectorAll(`#${containerId} input:checked`)).map((c) => c.value);
}

function saveRule() {
  const name = document.getElementById("rule-name").value.trim();
  if (!name) { toast("Rule name is required"); return; }
  const body = {
    name,
    symbols: parseList(document.getElementById("rule-symbols").value),
    keywords: parseList(document.getElementById("rule-keywords").value),
    source_filter: checkedValues("rule-sources"),
    min_severity: document.getElementById("rule-severity").value,
    channels: checkedValues("rule-channels"),
  };
  fetch("/api/alert-rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.error) { toast(d.error); return; }
      toast("Rule added");
      document.getElementById("rule-name").value = "";
      document.getElementById("rule-symbols").value = "";
      document.getElementById("rule-keywords").value = "";
      loadRules();
    })
    .catch(() => toast("Failed to add rule"));
}

function deleteRule(id) {
  fetch(`/api/alert-rules/${id}`, { method: "DELETE" })
    .then(() => { toast("Rule deleted"); loadRules(); })
    .catch(() => {});
}

function toggleRule(id, enabled) {
  fetch(`/api/alert-rules/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  })
    .then(() => loadRules())
    .catch(() => {});
}

// ── Settings ──────────────────────────────────────────────────────────────

function saveSettings() {
  const payload = {
    finnhub_token: document.getElementById("set-finnhub").value.trim(),
    telegram_bot_token: document.getElementById("set-tg-token").value.trim(),
    telegram_chat_id: document.getElementById("set-tg-chat").value.trim(),
    political_feed_url: document.getElementById("set-political").value.trim(),
    price_move_pct: document.getElementById("set-move").value.trim(),
    poll_interval_seconds: document.getElementById("set-interval").value.trim(),
  };
  // Drop blank values so we don't overwrite existing creds with empties.
  Object.keys(payload).forEach((k) => { if (payload[k] === "") delete payload[k]; });

  fetch("/api/providers/credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((r) => r.json())
    .then(() => {
      toast("Settings saved");
      // Clear secret inputs after save.
      ["set-finnhub", "set-tg-token"].forEach((id) => { document.getElementById(id).value = ""; });
      loadStatus();
    })
    .catch(() => toast("Failed to save settings"));
}

function sendTest() {
  fetch("/api/monitor/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channels: ["in_app", "telegram", "desktop"] }),
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.error) { toast(d.error); return; }
      const res = d.results || {};
      toast(`Test sent — ${Object.entries(res).map(([c, s]) => `${c}:${s}`).join(" · ")}`);
      loadEvents();
    })
    .catch(() => toast("Test failed"));
}

// ── Wiring ────────────────────────────────────────────────────────────────

function init() {
  document.querySelectorAll("#feed-filters button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#feed-filters button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      activeType = b.dataset.type;
      loadEvents();
    });
  });
  document.getElementById("save-rule").addEventListener("click", saveRule);
  document.getElementById("save-settings").addEventListener("click", saveSettings);
  document.getElementById("test-alert").addEventListener("click", sendTest);

  loadEvents();
  loadRules();
  loadStatus();
  pollTimer = setInterval(() => { loadEvents(); loadStatus(); }, POLL_MS);
}

document.addEventListener("DOMContentLoaded", init);
