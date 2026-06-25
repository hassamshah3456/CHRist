/* UsmleWise CHRIST — management dashboard (vanilla JS, same-origin API). */
"use strict";

// Same origin as the API (served by FastAPI at /admin). Override only for
// local testing against a remote API.
const API = "";
const TOKEN_KEY = "uw_token";
const USER_KEY = "uw_user";

const $ = (sel) => document.querySelector(sel);
const charts = {};
let map, markersLayer;
let lastCollections = [];
let allCollectors = [];
let groups = [];
let selectedGroup = null;

/* ---------- helpers ---------- */
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function api(path, opts = {}) {
  const headers = opts.headers || {};
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { logout(); throw new Error("Session expired"); }
  if (res.status === 403) throw new Error("Admin access required.");
  if (!res.ok) {
    let msg = "Request failed (" + res.status + ")";
    try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (e) {}
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) +
    ", " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : "—"; }
function fmtAge(years, months) {
  const parts = [];
  if (years != null) parts.push(`${years}y`);
  if (months != null && months > 0) parts.push(`${months}m`);
  return parts.length ? parts.join(" ") : "—";
}
function fmtDuration(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  if (hours) return `${hours}h ${mins}m`;
  return `${mins}m`;
}
function collectorLocation(c) {
  return c.last_address
    || (c.last_lat != null ? `${c.last_lat.toFixed(4)}, ${c.last_lng.toFixed(4)}` : "—");
}

/* ---------- auth ---------- */
async function login(email, password) {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(API + "/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    let msg = "Incorrect email or password.";
    try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (e) {}
    throw new Error(msg);
  }
  const data = await res.json();
  if (!data.user || !data.user.is_admin) {
    throw new Error("This account is not an admin. Dashboard access denied.");
  }
  setSession(data.access_token, data.user);
  return data.user;
}

function logout() {
  clearSession();
  $("#app-view").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
}

function showApp(user) {
  $("#login-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#user-chip").textContent = user.name || user.email;
  initMap();
  refreshAll();
}

/* ---------- data load ---------- */
function currentPeriod() { return $("#period").value; }

async function refreshAll() {
  try {
    await Promise.all([loadStats(), loadCollections(), loadCollectors()]);
  } catch (e) {
    console.error(e);
  }
}

async function loadStats() {
  const s = await api("/api/stats");
  renderKpis(s);
  renderTrend(s.daily);
  renderConsent(s.consent_yes, s.consent_no);
  renderBreakdown("chart-sex", s.sex_breakdown, ["#1e4db7", "#00b8a9", "#7a5af8", "#e2574c"]);
  renderBreakdown("chart-responder", s.responder_breakdown, ["#1e4db7", "#00b8a9", "#f0a500", "#7a5af8", "#e2574c"]);
  renderAgeBars(s.age_breakdown || []);
  renderPositivity(s.question_stats || []);
}

async function loadCollections() {
  const data = await api("/api/collections?period=" + currentPeriod());
  lastCollections = data;
  renderCollections(data);
  renderMapCollections(data);
}

async function loadCollectors() {
  const data = await api("/api/collectors");
  allCollectors = data;
  renderCollectors(data);
  renderMapSignups(data);
}

/* ---------- renderers ---------- */
function renderKpis(s) {
  const consentTotal = (s.consent_yes || 0) + (s.consent_no || 0);
  const consentRate = consentTotal
    ? Math.round((s.consent_yes / consentTotal) * 100) + "%"
    : "—";
  const items = [
    { label: "Total", value: s.total, color: "#2ba84a" },
    { label: "Today", value: s.today, color: "#1e4db7" },
    { label: "This week", value: s.this_week, color: "#00b8a9" },
    { label: "This month", value: s.this_month, color: "#7a5af8" },
    { label: "Collectors", value: s.collectors_count, color: "#f0a500" },
    { label: "Avg age", value: s.avg_age != null ? s.avg_age + " yrs" : "—", color: "#e2574c" },
    { label: "Consent rate", value: consentRate, color: "#2ba84a" },
  ];
  $("#kpi-grid").innerHTML = items.map((i) => `
    <div class="kpi">
      <div class="label">${i.label}</div>
      <div class="value">${i.value}</div>
      <div class="bar" style="background:${i.color}"></div>
    </div>`).join("");
}

function makeOrReplace(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), config);
}

function renderTrend(daily) {
  makeOrReplace("chart-trend", {
    type: "line",
    data: {
      labels: daily.map((d) => d.date.slice(5)),
      datasets: [{
        data: daily.map((d) => d.count),
        borderColor: "#1e4db7",
        backgroundColor: "rgba(30,77,183,.12)",
        fill: true, tension: .35, pointRadius: 0, borderWidth: 2,
      }],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
    },
  });
}

function renderConsent(yes, no) {
  makeOrReplace("chart-consent", {
    type: "doughnut",
    data: {
      labels: ["Yes", "No"],
      datasets: [{ data: [yes, no], backgroundColor: ["#2ba84a", "#e2574c"] }],
    },
    options: { plugins: { legend: { position: "bottom" } }, cutout: "62%" },
  });
}

function renderBreakdown(id, items, colors) {
  makeOrReplace(id, {
    type: "doughnut",
    data: {
      labels: items.map((i) => cap(i.label)),
      datasets: [{ data: items.map((i) => i.count), backgroundColor: colors }],
    },
    options: { plugins: { legend: { position: "bottom" } }, cutout: "62%" },
  });
}

function renderAgeBars(items) {
  makeOrReplace("chart-age", {
    type: "bar",
    data: {
      labels: items.map((i) => i.label),
      datasets: [{
        data: items.map((i) => i.count),
        backgroundColor: "#1e4db7",
        borderRadius: 6,
        maxBarThickness: 46,
      }],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
    },
  });
}

function renderPositivity(stats) {
  const wrap = $("#positivity");
  if (!stats.length) {
    wrap.innerHTML = `<div class="empty">No Yes/No answers collected yet.</div>`;
    return;
  }
  wrap.innerHTML = stats.map((q) => {
    const pct = q.total ? Math.round((q.yes / q.total) * 100) : 0;
    return `
      <div class="pos-row">
        <div class="pos-head">
          <span class="pos-label" title="${escapeHtml(q.label)}">${escapeHtml(q.label)}</span>
          <span class="pos-val">${pct}% <small>(${q.yes}/${q.total})</small></span>
        </div>
        <div class="pos-track"><div class="pos-fill" style="width:${pct}%"></div></div>
      </div>`;
  }).join("");
}

function _rowHtml(r, grouped) {
  const responder = r.responder === "other"
    ? (r.responder_other || "Other") : cap(r.responder);
  const loc = r.location_address
    || (r.location_lat != null ? `${r.location_lat.toFixed(4)}, ${r.location_lng.toFixed(4)}` : "—");
  return `<tr class="clickable ${grouped ? "grouped" : ""}" data-id="${r.id}">
    <td>${fmtDate(r.collected_at)}</td>
    <td>${escapeHtml(r.collector_name || "—")}</td>
    <td>${escapeHtml(r.phone || "—")}</td>
    <td>${escapeHtml(r.child_name || "—")}</td>
    <td>${fmtAge(r.child_age, r.child_age_months)}</td>
    <td>${cap(r.child_sex)}</td>
    <td>${escapeHtml(responder)}</td>
    <td><span class="badge ${r.verbal_consent ? "badge-yes" : "badge-no"}">${r.verbal_consent ? "Yes" : "No"}</span></td>
    <td>${escapeHtml(loc)}</td>
  </tr>`;
}

function renderCollections(rows) {
  const q = ($("#search").value || "").toLowerCase();
  const filtered = q
    ? rows.filter((r) => JSON.stringify(r).toLowerCase().includes(q))
    : rows;
  const tbody = $("#collections-table tbody");
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty">No submissions found.</td></tr>`;
    return;
  }

  // Group children sharing the same phone number (siblings).
  const counts = {};
  filtered.forEach((r) => {
    if (r.phone) counts[r.phone] = (counts[r.phone] || 0) + 1;
  });
  const groups = {};
  const singles = [];
  filtered.forEach((r) => {
    if (r.phone && counts[r.phone] > 1) (groups[r.phone] ||= []).push(r);
    else singles.push(r);
  });

  let html = "";
  Object.entries(groups).forEach(([phone, list]) => {
    html += `<tr class="group-head"><td colspan="9">📞 ${escapeHtml(phone)}
      <span class="group-count">${list.length} children</span></td></tr>`;
    list.forEach((r) => { html += _rowHtml(r, true); });
  });
  singles.forEach((r) => { html += _rowHtml(r, false); });
  tbody.innerHTML = html;
}

function renderCollectors(rows) {
  const tbody = $("#collectors-table tbody");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty">No collectors yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((c) => `
    <tr>
      <td>${escapeHtml(c.name)}</td>
      <td>${escapeHtml(c.email)}</td>
      <td>${escapeHtml(c.upi_address || "—")}</td>
      <td><b>${c.total}</b></td>
      <td><span class="presence ${c.online ? "online" : ""}">${c.online ? "Online" : "Offline"}</span></td>
      <td>${fmtDate(c.last_seen || c.last_collection)}</td>
      <td>${escapeHtml(collectorLocation(c))}</td>
      <td>${fmtDuration(c.app_seconds)}</td>
    </tr>`).join("");
}

/* ---------- map ---------- */
function initMap() {
  if (map) return;
  map = L.map("map", { scrollWheelZoom: false }).setView([20.5937, 78.9629], 4);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap", maxZoom: 19,
  }).addTo(map);
  markersLayer = L.layerGroup().addTo(map);
}

let collectionMarkers = [];
let signupMarkers = [];

function blueIcon(color) {
  return L.divIcon({
    className: "",
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 0 0 1px ${color}"></div>`,
    iconSize: [14, 14], iconAnchor: [7, 7],
  });
}

function renderMapCollections(rows) {
  collectionMarkers.forEach((m) => markersLayer.removeLayer(m));
  collectionMarkers = [];
  rows.forEach((r) => {
    if (r.location_lat == null || r.location_lng == null) return;
    const m = L.marker([r.location_lat, r.location_lng], { icon: blueIcon("#1e4db7") })
      .bindPopup(`<b>${escapeHtml(r.child_name || r.collector_name || "Child")}</b><br>
        Age ${fmtAge(r.child_age, r.child_age_months)} · ${cap(r.child_sex)}<br>
        Consent: ${r.verbal_consent ? "Yes" : "No"}<br>
        <small>${fmtDate(r.collected_at)}</small>`);
    m.addTo(markersLayer); collectionMarkers.push(m);
  });
  fitMap();
}

function renderMapSignups(rows) {
  signupMarkers.forEach((m) => markersLayer.removeLayer(m));
  signupMarkers = [];
  rows.forEach((c) => {
    if (c.signup_lat == null || c.signup_lng == null) return;
    const m = L.marker([c.signup_lat, c.signup_lng], { icon: blueIcon("#00b8a9") })
      .bindPopup(`<b>${c.name}</b> (sign-up)<br><small>${c.signup_address || ""}</small>`);
    m.addTo(markersLayer); signupMarkers.push(m);
  });
  fitMap();
}

function fitMap() {
  const all = [...collectionMarkers, ...signupMarkers];
  if (!all.length) return;
  const group = L.featureGroup(all);
  try { map.fitBounds(group.getBounds().pad(0.2)); } catch (e) {}
}

/* ---------- export ---------- */
async function exportCsv() {
  const res = await fetch(API + "/api/export.csv?period=" + currentPeriod(), {
    headers: { Authorization: "Bearer " + getToken() },
  });
  if (!res.ok) { alert("Export failed."); return; }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "collections_" + currentPeriod() + ".csv";
  a.click();
  URL.revokeObjectURL(url);
}

/* ---------- modal ---------- */
function openModal(html) {
  $("#modal").innerHTML = html;
  $("#modal-backdrop").classList.remove("hidden");
}
function closeModal() {
  $("#modal-backdrop").classList.add("hidden");
  $("#modal").innerHTML = "";
}
$("#modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "modal-backdrop") closeModal();
});

/* ---------- views ---------- */
function switchView(view) {
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === view));
  $("#view-dashboard").classList.toggle("hidden", view !== "dashboard");
  $("#view-groups").classList.toggle("hidden", view !== "groups");
  $("#view-questionnaire").classList.toggle("hidden", view !== "questionnaire");
  $("#view-payments").classList.toggle("hidden", view !== "payments");
  if (view === "groups") loadGroups();
  else if (view === "questionnaire") loadQuestions();
  else if (view === "payments") loadPayments();
  else setTimeout(() => map && map.invalidateSize(), 100);
}
document.querySelectorAll(".nav-btn").forEach((b) =>
  b.addEventListener("click", () => switchView(b.dataset.view)));

/* ---------- collector groups ---------- */
async function loadGroups() {
  try {
    if (!allCollectors.length) allCollectors = await api("/api/collectors");
    groups = await api("/api/groups?period=" + currentPeriod());
    renderGroups();
    if (selectedGroup) {
      const stillExists = groups.some((g) => g.id === selectedGroup.id);
      if (stillExists) await openGroup(selectedGroup.id);
      else clearGroupDetail();
    }
  } catch (e) { alert(e.message); }
}

function renderGroups() {
  const wrap = $("#groups-grid");
  if (!groups.length) {
    wrap.innerHTML = `<div class="empty">No groups yet. Create one and select its collectors.</div>`;
    return;
  }
  wrap.innerHTML = groups.map((g) => `
    <article class="group-card ${selectedGroup && selectedGroup.id === g.id ? "active" : ""}"
      data-group-id="${g.id}">
      <h4>${escapeHtml(g.name)}</h4>
      <div class="group-metrics">
        <div class="group-metric"><b>${g.members_count}</b>Collectors</div>
        <div class="group-metric"><b>${g.collections_count}</b>Collections</div>
        <div class="group-metric"><b>${g.online_count}</b>Online</div>
      </div>
    </article>`).join("");
}

async function openGroup(id) {
  selectedGroup = await api(`/api/groups/${id}?period=${currentPeriod()}`);
  renderGroups();
  $("#group-detail-card").classList.remove("hidden");
  $("#group-detail-name").textContent = selectedGroup.name;
  $("#group-detail-summary").textContent =
    `${selectedGroup.members_count} collectors · ${selectedGroup.collections_count} collections · ${selectedGroup.online_count} online`;
  const tbody = $("#group-members-table tbody");
  if (!selectedGroup.members.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">This group has no collectors.</td></tr>`;
    return;
  }
  tbody.innerHTML = selectedGroup.members.map((c) => `
    <tr>
      <td><span class="presence ${c.online ? "online" : ""}">${c.online ? "Online" : "Offline"}</span></td>
      <td><b>${escapeHtml(c.name)}</b><br><small>${escapeHtml(c.email)}</small></td>
      <td><b>${c.total}</b></td>
      <td>${fmtDate(c.last_seen)}</td>
      <td>${escapeHtml(collectorLocation(c))}</td>
      <td>${fmtDuration(c.app_seconds)}</td>
    </tr>`).join("");
}

function clearGroupDetail() {
  selectedGroup = null;
  $("#group-detail-card").classList.add("hidden");
  renderGroups();
}

function groupForm(group) {
  const selected = new Set(group ? group.members.map((m) => m.id) : []);
  const options = allCollectors.length
    ? allCollectors.map((c) => `
      <label class="member-option">
        <input type="checkbox" value="${c.id}" ${selected.has(c.id) ? "checked" : ""}>
        <span>${escapeHtml(c.name)}<small>${escapeHtml(c.email)} · ${c.total} collections</small></span>
      </label>`).join("")
    : `<div class="empty">No collectors available.</div>`;
  return `
    <h3>${group ? "Edit collector group" : "Create collector group"}</h3>
    <label>Group name</label>
    <input type="text" id="group-name" value="${escapeHtml(group ? group.name : "")}"
      placeholder="e.g. North Zone Team" />
    <label>Select collectors</label>
    <div class="member-picker" id="member-picker">${options}</div>
    <div class="modal-actions">
      <button class="cancel" id="group-cancel">Cancel</button>
      <button class="btn-primary" id="group-save">${group ? "Save changes" : "Create group"}</button>
    </div>`;
}

function openGroupModal(group = null) {
  openModal(groupForm(group));
  $("#group-cancel").addEventListener("click", closeModal);
  $("#group-save").addEventListener("click", () => saveGroup(group && group.id));
}

async function saveGroup(id) {
  const name = $("#group-name").value.trim();
  if (!name) { alert("Enter a group name."); return; }
  const member_ids = [...document.querySelectorAll("#member-picker input:checked")]
    .map((input) => input.value);
  try {
    const saved = await api(id ? `/api/groups/${id}` : "/api/groups", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, member_ids }),
    });
    closeModal();
    selectedGroup = saved;
    await loadGroups();
  } catch (e) { alert(e.message); }
}

async function deleteSelectedGroup() {
  if (!selectedGroup) return;
  if (!confirm(`Delete the group “${selectedGroup.name}”? Collectors and submissions will not be deleted.`)) return;
  try {
    await api(`/api/groups/${selectedGroup.id}`, { method: "DELETE" });
    clearGroupDetail();
    await loadGroups();
  } catch (e) { alert(e.message); }
}

$("#groups-grid").addEventListener("click", (e) => {
  const card = e.target.closest("[data-group-id]");
  if (card) openGroup(card.dataset.groupId);
});
$("#add-group-btn").addEventListener("click", () => openGroupModal());
$("#edit-group-btn").addEventListener("click", () => {
  if (selectedGroup) openGroupModal(selectedGroup);
});
$("#delete-group-btn").addEventListener("click", deleteSelectedGroup);

/* ---------- payments ---------- */
let payCurrency = "₹";
function fmtMoney(v) {
  const n = Number(v) || 0;
  return payCurrency + (n % 1 === 0 ? n : n.toFixed(2));
}

async function loadPayments() {
  try {
    const data = await api("/api/payments");
    payCurrency = (data.config && data.config.currency) || "₹";
    $("#rate-per-entry").value = data.config ? data.config.per_entry : 0;
    $("#rate-training").value = data.config ? data.config.training : 0;
    renderPayments(data.collectors || []);
  } catch (e) { alert(e.message); }
}

function renderPayments(rows) {
  const tbody = $("#payments-table tbody");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty">No collectors yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((r) => {
    const last = r.last_payout
      ? `${fmtMoney(r.last_payout.amount)} · ${fmtDate(r.last_payout.created_at)}`
      : "—";
    const training = r.training_paid
      ? `<span class="badge badge-yes">Paid</span>`
      : `<span class="badge badge-no">Due</span>`;
    return `<tr>
      <td>${escapeHtml(r.name)}</td>
      <td>${escapeHtml(r.upi_address || "—")}</td>
      <td>${r.total_entries}</td>
      <td>${r.unpaid_entries}</td>
      <td>${training}</td>
      <td><b>${fmtMoney(r.due)}</b></td>
      <td>${last}</td>
      <td><button class="btn-primary pay-btn" data-pay="${r.id}"
            data-name="${escapeHtml(r.name)}" data-due="${fmtMoney(r.due)}"
            ${r.due > 0 ? "" : "disabled"}>Mark paid</button></td>
    </tr>`;
  }).join("");
  tbody.querySelectorAll("[data-pay]").forEach((b) =>
    b.addEventListener("click", () =>
      markPaid(b.dataset.pay, b.dataset.name, b.dataset.due)));
}

async function saveRates() {
  const per_entry = parseFloat($("#rate-per-entry").value) || 0;
  const training = parseFloat($("#rate-training").value) || 0;
  try {
    await api("/api/payment-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ per_entry, training }),
    });
    $("#rates-saved").textContent = "Saved ✓";
    setTimeout(() => { $("#rates-saved").textContent = ""; }, 2000);
    loadPayments();
  } catch (e) { alert(e.message); }
}

async function markPaid(id, name, due) {
  if (!confirm(`Mark ${name} as paid ${due}?\nThis resets their counter; they'll see it in the app.`)) return;
  try {
    await api(`/api/collectors/${id}/pay`, { method: "POST" });
    loadPayments();
  } catch (e) { alert(e.message); }
}

const _saveRatesBtn = $("#save-rates-btn");
if (_saveRatesBtn) _saveRatesBtn.addEventListener("click", saveRates);

/* ---------- questionnaire management ---------- */
const QTYPES = [
  ["yes_no", "Yes / No"],
  ["single_choice", "Single choice"],
  ["multi_choice", "Multiple choice"],
  ["number", "Number"],
  ["text", "Free text"],
];
let questions = [];

async function loadQuestions() {
  questions = await api("/api/questions");
  renderQuestions();
}

function renderQuestions() {
  const wrap = $("#questions-list");
  if (!questions.length) {
    wrap.innerHTML = `<div class="empty">No questions yet. Click “Add question”.</div>`;
    return;
  }
  wrap.innerHTML = questions.map((q, i) => {
    const typeLabel = (QTYPES.find((t) => t[0] === q.qtype) || ["", q.qtype])[1];
    return `
    <div class="q-item ${q.is_active ? "" : "inactive"}">
      <div class="q-order">
        <button data-up="${q.id}" ${i === 0 ? "disabled" : ""}>▲</button>
        <button data-down="${q.id}" ${i === questions.length - 1 ? "disabled" : ""}>▼</button>
      </div>
      <div class="q-num">${i + 1}</div>
      <div class="q-body">
        <div class="q-title">${escapeHtml(q.title)}</div>
        ${q.help_text ? `<div class="q-help">${escapeHtml(q.help_text)}</div>` : ""}
        <div class="q-tags">
          <span class="q-tag type">${typeLabel}</span>
          ${q.required ? `<span class="q-tag">Required</span>` : ""}
          ${q.secondary_aim ? `<span class="q-tag secondary">Secondary aim</span>` : ""}
          ${q.photo_on_yes ? `<span class="q-tag photo">Photo on “Yes”</span>` : ""}
          ${q.note_on_yes ? `<span class="q-tag">Note on “Yes”</span>` : ""}
          ${!q.is_active ? `<span class="q-tag">Disabled</span>` : ""}
          ${q.options && q.options.length ? `<span class="q-tag">${q.options.length} options</span>` : ""}
        </div>
      </div>
      <div class="q-actions">
        <button data-edit="${q.id}">Edit</button>
        <button class="del" data-del="${q.id}">Delete</button>
      </div>
    </div>`;
  }).join("");
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function questionForm(q) {
  const isEdit = !!q;
  q = q || { qtype: "yes_no", required: true, is_active: true, options: [] };
  return `
    <h3>${isEdit ? "Edit" : "Add"} question</h3>
    <label>Question text</label>
    <input type="text" id="q-title" value="${escapeHtml(q.title || "")}" placeholder="e.g. Does recovery take longer than two weeks?" />
    <label>Help text (optional)</label>
    <textarea id="q-help" placeholder="Guidance shown under the question">${escapeHtml(q.help_text || "")}</textarea>
    <label>Answer type</label>
    <select id="q-type">
      ${QTYPES.map((t) => `<option value="${t[0]}" ${q.qtype === t[0] ? "selected" : ""}>${t[1]}</option>`).join("")}
    </select>
    <div id="q-options-wrap" class="${["single_choice", "multi_choice"].includes(q.qtype) ? "" : "hidden"}">
      <label>Options (one per line)</label>
      <textarea id="q-options" placeholder="Option A&#10;Option B">${escapeHtml((q.options || []).join("\n"))}</textarea>
    </div>
    <div id="q-yesno-wrap" class="${q.qtype === "yes_no" ? "" : "hidden"}">
      <label class="check"><input type="checkbox" id="q-photo" ${q.photo_on_yes ? "checked" : ""}/> Capture a photo when answered “Yes” (e.g. OPD card)</label>
      <label class="check"><input type="checkbox" id="q-note" ${q.note_on_yes ? "checked" : ""}/> Ask for a text note when answered “Yes”</label>
    </div>
    <label class="check"><input type="checkbox" id="q-required" ${q.required ? "checked" : ""}/> Required</label>
    <label class="check"><input type="checkbox" id="q-secondary" ${q.secondary_aim ? "checked" : ""}/> Secondary aim</label>
    <label class="check"><input type="checkbox" id="q-active" ${q.is_active ? "checked" : ""}/> Active (shown in the app)</label>
    <div class="modal-actions">
      <button class="cancel" id="q-cancel">Cancel</button>
      <button class="btn-primary" id="q-save">${isEdit ? "Save changes" : "Add question"}</button>
    </div>`;
}

function openQuestionModal(q) {
  openModal(questionForm(q));
  const typeSel = $("#q-type");
  typeSel.addEventListener("change", () => {
    const t = typeSel.value;
    $("#q-options-wrap").classList.toggle("hidden", !["single_choice", "multi_choice"].includes(t));
    $("#q-yesno-wrap").classList.toggle("hidden", t !== "yes_no");
  });
  $("#q-cancel").addEventListener("click", closeModal);
  $("#q-save").addEventListener("click", () => saveQuestion(q && q.id));
}

async function saveQuestion(id) {
  const title = $("#q-title").value.trim();
  if (!title) { alert("Enter the question text."); return; }
  const qtype = $("#q-type").value;
  const options = ["single_choice", "multi_choice"].includes(qtype)
    ? $("#q-options").value.split("\n").map((s) => s.trim()).filter(Boolean)
    : [];
  const body = {
    title,
    help_text: $("#q-help").value.trim() || null,
    qtype,
    options,
    required: $("#q-required").checked,
    secondary_aim: $("#q-secondary").checked,
    photo_on_yes: qtype === "yes_no" && $("#q-photo").checked,
    note_on_yes: qtype === "yes_no" && $("#q-note").checked,
    is_active: $("#q-active").checked,
  };
  try {
    await api(id ? `/api/questions/${id}` : "/api/questions", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    closeModal();
    loadQuestions();
  } catch (e) { alert(e.message); }
}

async function deleteQuestion(id) {
  if (!confirm("Delete this question? Existing answers are kept.")) return;
  await api(`/api/questions/${id}`, { method: "DELETE" });
  loadQuestions();
}

async function moveQuestion(id, dir) {
  const i = questions.findIndex((q) => q.id === id);
  const j = i + dir;
  if (j < 0 || j >= questions.length) return;
  [questions[i], questions[j]] = [questions[j], questions[i]];
  renderQuestions();
  await api("/api/questions/reorder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ordered_ids: questions.map((q) => q.id) }),
  });
}

$("#questions-list").addEventListener("click", (e) => {
  const t = e.target;
  if (t.dataset.edit) openQuestionModal(questions.find((q) => q.id === t.dataset.edit));
  else if (t.dataset.del) deleteQuestion(t.dataset.del);
  else if (t.dataset.up) moveQuestion(t.dataset.up, -1);
  else if (t.dataset.down) moveQuestion(t.dataset.down, 1);
});
$("#add-question-btn").addEventListener("click", () => openQuestionModal(null));

/* ---------- submission detail (answers + photos) ---------- */
async function loadPhoto(filename, imgEl) {
  try {
    const res = await fetch(API + "/api/photos/" + encodeURIComponent(filename), {
      headers: { Authorization: "Bearer " + getToken() },
    });
    if (!res.ok) return;
    imgEl.src = URL.createObjectURL(await res.blob());
  } catch (e) {}
}

function openSubmission(id) {
  const r = lastCollections.find((c) => c.id === id);
  if (!r) return;
  const responder = r.responder === "other" ? (r.responder_other || "Other") : cap(r.responder);
  let html = `<h3>Submission detail</h3>
    <div class="ans-row"><div class="ans-q">Collector</div><div class="ans-v">${escapeHtml(r.collector_name || "—")}</div></div>
    <div class="ans-row"><div class="ans-q">Phone</div><div class="ans-v">${escapeHtml(r.phone || "—")}</div></div>
    <div class="ans-row"><div class="ans-q">When</div><div class="ans-v">${fmtDate(r.collected_at)}</div></div>
    <div class="ans-row"><div class="ans-q">Child</div><div class="ans-v">${escapeHtml(r.child_name || "—")} · Age ${fmtAge(r.child_age, r.child_age_months)} · ${cap(r.child_sex)} · Responder: ${escapeHtml(responder)}</div></div>
    <div class="ans-row"><div class="ans-q">Verbal consent</div><div class="ans-v"><span class="${r.verbal_consent ? "yes" : "no"}">${r.verbal_consent ? "Yes" : "No"}</span></div></div>
    <div class="ans-row"><div class="ans-q">Medical record</div><div class="ans-v">${r.medical_record == null ? "—" : `<span class="${r.medical_record ? "yes" : "no"}">${r.medical_record ? "Yes" : "No"}</span>`} · Vaccines: ${fmtVaccines(r.vaccines)}${r.medical_record_photo ? `<br><img class="ans-photo" id="medph" alt="medical record loading…"/>` : ""}</div></div>
    <div class="ans-row"><div class="ans-q">Location</div><div class="ans-v">${escapeHtml(r.location_address || (r.location_lat != null ? r.location_lat.toFixed(5) + ", " + r.location_lng.toFixed(5) : "—"))}</div></div>`;

  const answers = r.answers || [];
  if (answers.length) {
    html += `<h3 style="margin-top:18px">Screening answers</h3>`;
    answers.forEach((a, i) => {
      let v = "—";
      if (a.value_bool != null) v = `<span class="${a.value_bool ? "yes" : "no"}">${a.value_bool ? "Yes" : "No"}</span>`;
      else if (a.value_number != null) v = a.value_number;
      else if (a.value_text) v = escapeHtml(a.value_text);
      html += `<div class="ans-row">
        <div class="ans-q">${escapeHtml(a.question_title || a.question_code)}</div>
        <div class="ans-v">${v}${a.value_text && a.value_bool != null ? " — " + escapeHtml(a.value_text) : ""}</div>
        ${a.photo_filename ? `<img class="ans-photo" id="ph-${i}" alt="photo loading…"/>` : ""}
      </div>`;
    });
  } else {
    html += `<p class="hint" style="margin-top:14px">No screening answers recorded for this submission.</p>`;
  }
  html += `<div class="modal-actions"><button class="cancel" id="sub-close">Close</button></div>`;
  openModal(html);
  $("#sub-close").addEventListener("click", closeModal);
  answers.forEach((a, i) => { if (a.photo_filename) loadPhoto(a.photo_filename, $("#ph-" + i)); });
  if (r.medical_record_photo) loadPhoto(r.medical_record_photo, $("#medph"));
}

function fmtVaccines(csv) {
  if (!csv) return "—";
  return csv.split(",").map((v) => v === "none" ? "None" : v.toUpperCase()).join(", ");
}

$("#collections-table").addEventListener("click", (e) => {
  const tr = e.target.closest("tr.clickable");
  if (tr && tr.dataset.id) openSubmission(tr.dataset.id);
});

/* ---------- events ---------- */
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#login-btn");
  btn.disabled = true; $("#login-error").textContent = "";
  try {
    const user = await login($("#login-email").value.trim(), $("#login-password").value);
    showApp(user);
  } catch (err) {
    $("#login-error").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

$("#logout-btn").addEventListener("click", logout);
$("#refresh-btn").addEventListener("click", refreshAll);
$("#period").addEventListener("change", () => {
  loadStats();
  loadCollections();
  if (!$("#view-groups").classList.contains("hidden")) loadGroups();
});
$("#export-btn").addEventListener("click", exportCsv);
$("#search").addEventListener("input", () => renderCollections(lastCollections));

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const which = tab.dataset.tab;
    $("#tab-collections").classList.toggle("hidden", which !== "collections");
    $("#tab-collectors").classList.toggle("hidden", which !== "collectors");
  });
});

/* ---------- boot ---------- */
(async function boot() {
  const token = getToken();
  const userRaw = localStorage.getItem(USER_KEY);
  if (token && userRaw) {
    try {
      const me = await api("/me");
      if (me && me.is_admin) { showApp(me); return; }
    } catch (e) { /* fall through to login */ }
  }
  logout();
})();
