/* CRIST Tool — management dashboard (vanilla JS, same-origin API). */
"use strict";

// Same origin as the API (served by FastAPI at /admin). Override only for
// local testing against a remote API.
const API = "";
const TOKEN_KEY = "uw_token";
const USER_KEY = "uw_user";
const GEOCODE_CACHE_KEY = "uw_geocode_cache";

const $ = (sel) => document.querySelector(sel);
const charts = {};
let map, markersLayer;
let lastCollections = [];
let allCollectors = [];
let currentPositiveFilter = "all";
let primaryYesNoCodes = null;
let submissionsPage = 1;
let submissionsPageSize = 25;
let submissionsTotal = 0;
let submissionsPages = 1;
let searchDebounce = null;
let groups = [];
let selectedGroup = null;
let groupMap;
let groupMarkersLayer;
let groupRefreshTimer;

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

/* ---------- timezone ---------- */
const TZ_KEY = "dash_tz";
const TZONES = { IST: "Asia/Kolkata", ET: "America/New_York" };
function currentTz() {
  const v = localStorage.getItem(TZ_KEY);
  return TZONES[v] ? v : "IST";
}
function tzName() { return TZONES[currentTz()]; }

/* The backend emits naive UTC timestamps (no offset). Without this, the browser
   would parse them as local time and the timezone conversion would be wrong. */
function parseUtc(iso) {
  if (!iso) return null;
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : iso + "Z");
  return isNaN(d.getTime()) ? null : d;
}

function fmtDate(iso) {
  const d = parseUtc(iso);
  if (!d) return "—";
  const timeZone = tzName();
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone }) +
    ", " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", timeZone });
}
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : "—"; }
function collectorContact(c) { return c.phone || c.email || "—"; }
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
  return displayLocation(c.last_address, c.last_lat, c.last_lng);
}
function googleMapsUrl(lat, lng) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${lat},${lng}`)}`;
}
function coordinatesKey(lat, lng) {
  if (lat == null || lng == null) return "";
  return `${Number(lat).toFixed(5)},${Number(lng).toFixed(5)}`;
}
function loadGeocodeCache() {
  try {
    return JSON.parse(localStorage.getItem(GEOCODE_CACHE_KEY) || "{}");
  } catch (e) {
    return {};
  }
}
const geocodeCache = loadGeocodeCache();
const geocodePending = new Map();
let nominatimQueue = Promise.resolve();

function saveGeocodeCache() {
  try { localStorage.setItem(GEOCODE_CACHE_KEY, JSON.stringify(geocodeCache)); } catch (e) {}
}
function queuedNominatimFetch(url) {
  const run = nominatimQueue.then(() =>
    fetch(url).finally(() => new Promise((resolve) => setTimeout(resolve, 1100))));
  nominatimQueue = run.catch(() => {});
  return run;
}
function addressFromBigDataCloud(data) {
  const parts = [
    data.locality,
    data.city,
    data.postcode,
    data.principalSubdivision,
    data.countryName,
  ].filter(Boolean);
  return [...new Set(parts)].join(", ");
}
async function reverseGeocode(lat, lng) {
  const key = coordinatesKey(lat, lng);
  if (!key) return "";
  if (geocodeCache[key]) return geocodeCache[key];
  if (geocodePending.has(key)) return geocodePending.get(key);

  const nominatimUrl = "https://nominatim.openstreetmap.org/reverse"
    + `?format=jsonv2&lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lng)}&zoom=18&addressdetails=1`;
  const fallbackUrl = "https://api.bigdatacloud.net/data/reverse-geocode-client"
    + `?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lng)}&localityLanguage=en`;
  const pending = queuedNominatimFetch(nominatimUrl)
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => data && data.display_name ? data.display_name : "")
    .then((address) => {
      if (address) return address;
      return fetch(fallbackUrl)
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => data ? addressFromBigDataCloud(data) : "");
    })
    .then((address) => {
      if (address) {
        geocodeCache[key] = address;
        saveGeocodeCache();
      }
      return address;
    })
    .catch(() => "")
    .finally(() => geocodePending.delete(key));
  geocodePending.set(key, pending);
  return pending;
}
function displayLocation(address, lat, lng, precision = 4) {
  if (address) return address;
  const cached = geocodeCache[coordinatesKey(lat, lng)];
  if (cached) return cached;
  return lat != null && lng != null
    ? `${Number(lat).toFixed(precision)}, ${Number(lng).toFixed(precision)}`
    : "—";
}
function locationSpan(address, lat, lng, precision = 4) {
  if (lat == null || lng == null) return escapeHtml(address || "—");
  return `<span class="js-address" data-lat="${lat}" data-lng="${lng}" data-precision="${precision}">
    ${escapeHtml(displayLocation(address, lat, lng, precision))}
  </span>`;
}
function hydrateAddressSpans(root = document) {
  root.querySelectorAll(".js-address").forEach(async (el) => {
    const lat = Number(el.dataset.lat);
    const lng = Number(el.dataset.lng);
    const precision = Number(el.dataset.precision || 4);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const current = displayLocation("", lat, lng, precision);
    if (!el.textContent.trim() || el.textContent.trim() === current) {
      const address = await reverseGeocode(lat, lng);
      if (address && el.isConnected) el.textContent = address;
    }
  });
}
function locationCell(c) {
  const label = locationSpan(c.last_address, c.last_lat, c.last_lng);
  if (c.last_lat == null || c.last_lng == null) return label;
  return `${label}<a class="map-link" href="${googleMapsUrl(c.last_lat, c.last_lng)}"
    target="_blank" rel="noopener">Google Maps ↗</a>`;
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
  $("#user-chip").textContent = user.name || user.email || user.phone;
  initMap();
  refreshAll();
}

/* ---------- data load ---------- */
function currentPeriod() { return $("#period").value; }

async function refreshAll() {
  try {
    await Promise.all([loadStats(), loadCollections(1), loadMapCollections(), loadCollectors()]);
  } catch (e) {
    console.error(e);
  }
}

async function loadStats() {
  const s = await api("/api/stats");
  renderKpis(s);
  renderTrend(s.daily);
  renderResponderBars(s.responder_breakdown || []);
  renderAgeBars(s.age_breakdown || []);
  renderPositivityMix(s);
  renderDiarrhea(s);
  renderPositivity(s.question_stats || []);
}

async function loadCollections(page = submissionsPage) {
  const searchVal = ($("#search").value || "").trim();
  const params = new URLSearchParams({
    period: currentPeriod(),
    page: String(page),
    page_size: String(submissionsPageSize),
    positive: currentPositiveFilter,
  });
  if (searchVal) params.set("search", searchVal);
  const data = await api("/api/collections?" + params.toString());
  lastCollections = data.items || [];
  submissionsPage = data.page || 1;
  submissionsTotal = data.total || 0;
  submissionsPages = data.pages || 1;
  submissionsPageSize = data.page_size || submissionsPageSize;
  await ensureQuestionCodes();
  renderCollections(lastCollections);
  renderPagination();
}

async function loadMapCollections() {
  const data = await api("/api/collections/map?period=" + currentPeriod());
  renderMapCollections(data);
}

// The set of top-level yes/no question codes, used to score "positivity".
// Follow-up questions are excluded (they only appear after a parent "Yes"),
// mirroring the field app's triple-positive rule.
async function ensureQuestionCodes() {
  try {
    if (!questions.length) questions = await api("/api/questions");
  } catch (e) { /* keep whatever we have */ }
  primaryYesNoCodes = new Set(
    (questions || [])
      .filter((q) => q && q.qtype === "yes_no")
      .map((q) => q.code)
  );
}

// Number of "Yes" answers to top-level yes/no screening questions.
function positiveCount(r) {
  let yes = 0;
  (r.answers || []).forEach((a) => {
    if (a.value_bool !== true) return;
    if (primaryYesNoCodes && primaryYesNoCodes.size) {
      if (primaryYesNoCodes.has(a.question_code)) yes++;
    } else if (a.qtype === "yes_no") {
      yes++;
    }
  });
  return yes;
}

function positiveBadge(n) {
  if (n >= 4) return `<span class="badge badge-quad" title="${n} positive answers">Quadruple · ${n}</span>`;
  if (n >= 3) return `<span class="badge badge-triple" title="${n} positive answers">Triple · ${n}</span>`;
  return `<span class="pos-count">${n} Yes</span>`;
}

async function loadCollectors() {
  const data = await api("/api/collectors");
  allCollectors = data;
  renderCollectors(data);
  renderMapSignups(data);
}

/* ---------- renderers ---------- */
function renderKpis(s) {
  const items = [
    { label: "Total", value: s.total, color: "#2ba84a" },
    { label: "Today", value: s.today, color: "#1e4db7" },
    { label: "This week", value: s.this_week, color: "#00b8a9" },
    { label: "This month", value: s.this_month, color: "#7a5af8" },
    { label: "Triple positive (3+)", value: s.triple_positive ?? 0, color: "#b06a00" },
    { label: "Had diarrhea", value: s.diarrhea_yes ?? 0, color: "#c0392b" },
    { label: "Collectors", value: s.collectors_count, color: "#f0a500" },
    { label: "Avg age", value: s.avg_age != null ? s.avg_age + " yrs" : "—", color: "#e2574c" },
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

function renderResponderBars(items) {
  makeOrReplace("chart-responder", {
    type: "bar",
    data: {
      labels: items.map((i) => cap(i.label)),
      datasets: [{
        data: items.map((i) => i.count),
        backgroundColor: ["#1e4db7", "#00b8a9", "#f0a500", "#7a5af8", "#e2574c"],
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

function renderPositivityMix(s) {
  const normal = s.positivity_normal ?? 0;
  const tripleOnly = s.positivity_triple ?? 0;
  const quad = s.positivity_quadruple ?? 0;
  const triplePlus = tripleOnly + quad;
  const total = normal + triplePlus;
  const pct = (n) => (total ? Math.round((n / total) * 100) : 0);

  makeOrReplace("chart-positivity-mix", {
    type: "bar",
    data: {
      labels: [
        `Normal (<3 Yes)`,
        `Triple positive (3+)`,
        `Quadruple (4+ Yes)`,
      ],
      datasets: [{
        data: [normal, triplePlus, quad],
        backgroundColor: ["#2ba84a", "#b06a00", "#e2574c"],
        borderRadius: 6,
        maxBarThickness: 44,
      }],
    },
    options: {
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const n = ctx.raw;
              let line = `${n} submissions (${pct(n)}%)`;
              if (ctx.dataIndex === 1) {
                line += ` — ${tripleOnly} at exactly 3, ${quad} at 4+`;
              }
              return line;
            },
          },
        },
      },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 } },
        y: { grid: { display: false } },
      },
    },
  });

  const stats = $("#positivity-mix-stats");
  if (stats) {
    stats.innerHTML = `
      <span class="mix-stat normal"><b>${normal}</b> normal (${pct(normal)}%)</span>
      <span class="mix-stat triple"><b>${triplePlus}</b> triple positive (3+, includes quadruple)</span>
      <span class="mix-stat quad"><b>${quad}</b> quadruple only (4+)</span>`;
  }
}

function renderDiarrhea(s) {
  const yes = s.diarrhea_yes ?? 0;
  const answered = s.diarrhea_answered ?? 0;
  const no = Math.max(answered - yes, 0);
  const total = s.total ?? 0;
  const label = s.diarrhea_label || "Diarrhea";
  const pctAnswered = (n) => (answered ? Math.round((n / answered) * 100) : 0);
  const pctTotal = yes && total ? Math.round((yes / total) * 100) : 0;

  const title = $("#diarrhea-section-title");
  if (title) title.textContent = label;

  const stats = $("#diarrhea-stats");
  if (stats) {
    stats.innerHTML = `
      <span class="mix-stat diarrhea-yes"><b>${yes}</b> reported Yes (${pctAnswered(yes)}% of answers)</span>
      <span class="mix-stat diarrhea-no"><b>${no}</b> reported No</span>
      <span class="mix-stat diarrhea-pct"><b>${pctTotal}%</b> of all submissions</span>`;
  }

  makeOrReplace("chart-diarrhea", {
    type: "bar",
    data: {
      labels: ["Reported diarrhea", "No diarrhea", "Not answered"],
      datasets: [{
        data: [yes, no, Math.max(total - answered, 0)],
        backgroundColor: ["#c0392b", "#2ba84a", "#d0d5dd"],
        borderRadius: 6,
        maxBarThickness: 44,
      }],
    },
    options: {
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 } },
        y: { grid: { display: false } },
      },
    },
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
  const n = positiveCount(r);
  return `<tr class="clickable ${grouped ? "grouped" : ""}" data-id="${r.id}">
    <td>${fmtDate(r.collected_at)}</td>
    <td>${escapeHtml(r.collector_name || "—")}</td>
    <td>${fmtAge(r.child_age, r.child_age_months) || "—"}</td>
    <td>${escapeHtml(r.phone || "—")}</td>
    <td><span class="badge ${r.verbal_consent ? "badge-yes" : "badge-no"}">${r.verbal_consent ? "Yes" : "No"}</span></td>
    <td>${positiveBadge(n)}</td>
    <td>${locationSpan(r.location_address, r.location_lat, r.location_lng)}</td>
    <td><button class="row-del" data-del-sub="${r.id}" title="Delete submission">🗑</button></td>
  </tr>`;
}

function renderCollections(rows) {
  const tbody = $("#collections-table tbody");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty">No submissions found.</td></tr>`;
    return;
  }

  // Group children sharing the same phone number (siblings) within this page.
  const counts = {};
  rows.forEach((r) => {
    if (r.phone) counts[r.phone] = (counts[r.phone] || 0) + 1;
  });
  const groups = {};
  const singles = [];
  rows.forEach((r) => {
    if (r.phone && counts[r.phone] > 1) (groups[r.phone] ||= []).push(r);
    else singles.push(r);
  });

  let html = "";
  Object.entries(groups).forEach(([phone, list]) => {
    html += `<tr class="group-head"><td colspan="8">📞 ${escapeHtml(phone)}
      <span class="group-count">${list.length} children</span></td></tr>`;
    list.forEach((r) => { html += _rowHtml(r, true); });
  });
  singles.forEach((r) => { html += _rowHtml(r, false); });
  tbody.innerHTML = html;
  hydrateAddressSpans(tbody);
}

function renderPagination() {
  const wrap = $("#collections-pagination");
  if (!wrap) return;
  if (!submissionsTotal) {
    wrap.innerHTML = "";
    return;
  }
  const start = (submissionsPage - 1) * submissionsPageSize + 1;
  const end = Math.min(submissionsPage * submissionsPageSize, submissionsTotal);
  wrap.innerHTML = `
    <span class="page-info">Showing ${start}–${end} of ${submissionsTotal}</span>
    <div class="page-controls">
      <button class="btn-ghost" id="page-first" ${submissionsPage <= 1 ? "disabled" : ""}>«</button>
      <button class="btn-ghost" id="page-prev" ${submissionsPage <= 1 ? "disabled" : ""}>‹ Prev</button>
      <span class="page-num">Page ${submissionsPage} / ${submissionsPages}</span>
      <button class="btn-ghost" id="page-next" ${submissionsPage >= submissionsPages ? "disabled" : ""}>Next ›</button>
      <button class="btn-ghost" id="page-last" ${submissionsPage >= submissionsPages ? "disabled" : ""}>»</button>
      <select id="page-size" class="search" title="Rows per page">
        <option value="25" ${submissionsPageSize === 25 ? "selected" : ""}>25 / page</option>
        <option value="50" ${submissionsPageSize === 50 ? "selected" : ""}>50 / page</option>
        <option value="100" ${submissionsPageSize === 100 ? "selected" : ""}>100 / page</option>
      </select>
    </div>`;
  $("#page-first").addEventListener("click", () => loadCollections(1));
  $("#page-prev").addEventListener("click", () => loadCollections(submissionsPage - 1));
  $("#page-next").addEventListener("click", () => loadCollections(submissionsPage + 1));
  $("#page-last").addEventListener("click", () => loadCollections(submissionsPages));
  $("#page-size").addEventListener("change", (e) => {
    submissionsPageSize = parseInt(e.target.value, 10) || 25;
    loadCollections(1);
  });
}

function renderCollectors(rows) {
  const tbody = $("#collectors-table tbody");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty">No collectors yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((c) => `
    <tr class="${c.flagged ? "flagged-row" : ""}">
      <td class="col-collector">
        <div class="collector-cell">
          <div>${escapeHtml(c.name)}${flagBadge(c)}</div>
          <button type="button" class="btn-ghost btn-sm" data-edit-collector="${c.id}">Edit</button>
        </div>
      </td>
      <td>${escapeHtml(collectorContact(c))}</td>
      <td>${escapeHtml(c.upi_address || "—")}</td>
      <td><b>${c.total}</b></td>
      <td><span class="presence ${c.online ? "online" : ""}">${c.online ? "Online" : "Offline"}</span></td>
      <td>${fmtDate(c.last_seen || c.last_collection)}</td>
      <td class="col-location">${locationCell(c)}</td>
      <td>${fmtDuration(c.app_seconds)}</td>
    </tr>`).join("");
  hydrateAddressSpans(tbody);
  tbody.querySelectorAll("[data-edit-collector]").forEach((b) =>
    b.addEventListener("click", () => {
      const c = (allCollectors || []).find((x) => x.id === b.dataset.editCollector);
      if (c) openCollectorModal(c);
    }));
}

function collectorForm(c) {
  return `
    <h3>Edit collector</h3>
    <label>Full name</label>
    <input type="text" id="col-name" value="${escapeHtml(c.name || "")}" />
    <label>Phone</label>
    <input type="text" id="col-phone" value="${escapeHtml(c.phone || "")}"
      placeholder="Digits only" />
    <label>Email</label>
    <input type="email" id="col-email" value="${escapeHtml(c.email || "")}"
      placeholder="optional" />
    <label>UPI ID</label>
    <input type="text" id="col-upi" value="${escapeHtml(c.upi_address || "")}"
      placeholder="name@bank" />
    <label>UPI account holder name</label>
    <input type="text" id="col-upi-name" value="${escapeHtml(c.upi_name || "")}"
      placeholder="optional" />
    <div class="modal-actions">
      <button class="cancel" id="col-cancel">Cancel</button>
      <button class="btn-primary" id="col-save">Save changes</button>
    </div>`;
}

function openCollectorModal(c, { fromGroupPicker = false, group = null } = {}) {
  if (fromGroupPicker) captureGroupModalState(group);
  openModal(collectorForm(c));
  $("#col-cancel").addEventListener("click", () => {
    closeModal();
    restoreGroupModalIfPending();
  });
  $("#col-save").addEventListener("click", () => saveCollector(c.id));
}

async function saveCollector(id) {
  const name = $("#col-name").value.trim();
  const upi = $("#col-upi").value.trim();
  if (!name) { alert("Enter the collector's name."); return; }
  if (!upi) { alert("Enter a UPI ID."); return; }
  try {
    await api(`/api/collectors/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        phone: $("#col-phone").value.trim() || null,
        email: $("#col-email").value.trim() || null,
        upi_address: upi,
        upi_name: $("#col-upi-name").value.trim() || null,
      }),
    });
    closeModal();
    await loadCollectors();
    if (typeof selectedGroup !== "undefined" && selectedGroup) {
      await refreshGroupLive(selectedGroup.id);
    }
    restoreGroupModalIfPending();
  } catch (e) { alert(e.message); }
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
        Age ${fmtAge(r.child_age, r.child_age_months)}<br>
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
let pendingGroupModal = null;

function captureGroupModalState(group) {
  if (!$("#member-picker")) return;
  pendingGroupModal = {
    group,
    name: $("#group-name").value,
    checked: [...document.querySelectorAll("#member-picker input:checked")]
      .map((input) => input.value),
  };
}

function restoreGroupModalIfPending() {
  if (!pendingGroupModal) return;
  const ctx = pendingGroupModal;
  pendingGroupModal = null;
  openGroupModal(ctx.group);
  $("#group-name").value = ctx.name;
  ctx.checked.forEach((id) => {
    const el = document.querySelector(`#member-picker input[value="${CSS.escape(id)}"]`);
    if (el) el.checked = true;
  });
}

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
  $("#view-instructions").classList.toggle("hidden", view !== "instructions");
  if (view === "groups") loadGroups();
  else {
    stopGroupLiveRefresh();
    if (view === "questionnaire") loadQuestions();
    else if (view === "payments") loadPayments();
    else if (view === "instructions") loadInstructions();
    else setTimeout(() => map && map.invalidateSize(), 100);
  }
}

/* ---------- instructions (per language) ---------- */
let _instrLang = "en";
function _instrEditor(lang) { return $("#instr-" + lang); }

async function loadInstructions() {
  try {
    const data = await api("/api/instructions");
    ["en", "hi", "kn"].forEach((l) => {
      _instrEditor(l).innerHTML = (data && data[l]) || "";
    });
  } catch (e) { alert(e.message); }
}

async function saveInstructions() {
  const body = {
    en: _instrEditor("en").innerHTML,
    hi: _instrEditor("hi").innerHTML,
    kn: _instrEditor("kn").innerHTML,
  };
  try {
    await api("/api/instructions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("#instructions-saved").textContent = "Saved ✓";
    setTimeout(() => { $("#instructions-saved").textContent = ""; }, 2000);
  } catch (e) { alert(e.message); }
}

document.querySelectorAll(".rt-langs button").forEach((b) =>
  b.addEventListener("click", () => {
    _instrLang = b.dataset.lang;
    document.querySelectorAll(".rt-langs button").forEach((x) =>
      x.classList.toggle("active", x === b));
    ["en", "hi", "kn"].forEach((l) =>
      _instrEditor(l).classList.toggle("hidden", l !== _instrLang));
    _instrEditor(_instrLang).focus();
  }));

document.querySelectorAll(".rt-toolbar button").forEach((b) =>
  b.addEventListener("click", (e) => {
    e.preventDefault();
    _instrEditor(_instrLang).focus();
    document.execCommand(b.dataset.cmd, false, b.dataset.arg || null);
  }));
const _saveInstrBtn = $("#save-instructions-btn");
if (_saveInstrBtn) _saveInstrBtn.addEventListener("click", saveInstructions);
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

async function openGroup(id, manageRefresh = true) {
  selectedGroup = await api(`/api/groups/${id}?period=${currentPeriod()}`);
  renderGroups();
  $("#group-detail-card").classList.remove("hidden");
  $("#group-detail-name").textContent = selectedGroup.name;
  $("#group-detail-summary").textContent =
    `${selectedGroup.members_count} collectors · ${selectedGroup.collections_count} collections · ${selectedGroup.online_count} online`;
  renderGroupLiveMap(selectedGroup.members);
  if (manageRefresh) startGroupLiveRefresh();
  renderGroupMembers(selectedGroup.members);
  renderGroupPayments(selectedGroup);
}

function renderGroupMembers(members) {
  const tbody = $("#group-members-table tbody");
  if (!members.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">This group has no collectors.</td></tr>`;
    return;
  }
  tbody.innerHTML = members.map((c) => `
    <tr class="${c.flagged ? "flagged-row" : ""}">
      <td><span class="presence ${c.online ? "online" : ""}">${c.online ? "Online" : "Offline"}</span></td>
      <td class="col-collector">
        <div class="collector-cell">
          <div><b>${escapeHtml(c.name)}</b>${flagBadge(c)}<br><small>${escapeHtml(collectorContact(c))}</small></div>
          <button type="button" class="btn-ghost btn-sm" data-edit-collector="${c.id}">Edit</button>
        </div>
      </td>
      <td><b>${c.total}</b></td>
      <td>${fmtDate(c.last_seen)}</td>
      <td class="col-location">${locationCell(c)}</td>
      <td>${fmtDuration(c.app_seconds)}</td>
    </tr>`).join("");
  hydrateAddressSpans(tbody);
  tbody.querySelectorAll("[data-edit-collector]").forEach((b) =>
    b.addEventListener("click", () => {
      const c = (members || []).find((x) => x.id === b.dataset.editCollector);
      if (c) openCollectorModal(c);
    }));
}

/* Red anomaly badge for collectors who submitted more than 4 forms in a minute. */
function flagBadge(c) {
  if (!c.flagged) return "";
  const n = c.flagged_count || 0;
  return `<span class="flag-badge" title="${n} submissions within one minute (more than 4/min is flagged)">⚠ ${n}/min</span>`;
}

function renderGroupPayments(group) {
  if (group.currency) payCurrency = group.currency;
  renderPaymentsSummary(group.total_due ?? 0, group.total_paid ?? 0, $("#group-payments-summary"));
  renderPaymentTableRows(group.payments || [], $("#group-payments-table tbody"), {
    emptyMessage: "No collectors in this group.",
  });
}

async function refreshGroupLive(id) {
  const data = await api(`/api/groups/${id}?period=${currentPeriod()}`);
  selectedGroup.members = data.members;
  selectedGroup.collections_count = data.collections_count;
  selectedGroup.online_count = data.online_count;
  $("#group-detail-summary").textContent =
    `${data.members_count} collectors · ${data.collections_count} collections · ${data.online_count} online`;
  renderGroupLiveMap(data.members);
  renderGroupMembers(data.members);
}

function clearGroupDetail() {
  stopGroupLiveRefresh();
  selectedGroup = null;
  $("#group-detail-card").classList.add("hidden");
  renderGroups();
}

function initGroupMap() {
  if (groupMap) return;
  groupMap = L.map("group-live-map", { scrollWheelZoom: false })
    .setView([20.5937, 78.9629], 4);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap", maxZoom: 19,
  }).addTo(groupMap);
  groupMarkersLayer = L.layerGroup().addTo(groupMap);
}

function renderGroupLiveMap(members) {
  initGroupMap();
  groupMarkersLayer.clearLayers();
  const markers = [];
  members.forEach((c) => {
    if (c.last_lat == null || c.last_lng == null) return;
    const color = c.online ? "#2ba84a" : "#8c94a5";
    const marker = L.marker([c.last_lat, c.last_lng], { icon: blueIcon(color) })
      .bindPopup(`<b>${escapeHtml(c.name)}</b><br>
        ${c.online ? "Online" : "Offline"} · ${fmtDate(c.last_seen)}<br>
        <small>${escapeHtml(collectorLocation(c))}</small><br>
        <a href="${googleMapsUrl(c.last_lat, c.last_lng)}" target="_blank"
          rel="noopener">Open in Google Maps</a>`);
    marker.addTo(groupMarkersLayer);
    markers.push(marker);
  });
  setTimeout(() => groupMap.invalidateSize(), 0);
  if (markers.length) {
    try {
      groupMap.fitBounds(L.featureGroup(markers).getBounds().pad(0.25), {
        maxZoom: 16,
      });
    } catch (e) {}
  }
  $("#group-live-updated").textContent =
    `Last refreshed ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: tzName() })}`;
}

function startGroupLiveRefresh() {
  stopGroupLiveRefresh();
  groupRefreshTimer = setInterval(async () => {
    if (!selectedGroup || $("#view-groups").classList.contains("hidden")) return;
    try {
      await refreshGroupLive(selectedGroup.id);
    } catch (e) {
      console.error("Live group refresh failed", e);
    }
  }, 15000);
}

function stopGroupLiveRefresh() {
  if (groupRefreshTimer) clearInterval(groupRefreshTimer);
  groupRefreshTimer = null;
}

function groupForm(group) {
  const selected = new Set(group ? group.members.map((m) => m.id) : []);
  const options = allCollectors.length
    ? allCollectors.map((c) => `
      <label class="member-option">
        <input type="checkbox" value="${c.id}" ${selected.has(c.id) ? "checked" : ""}>
        <span>${escapeHtml(c.name)}<small>${escapeHtml(collectorContact(c))} · ${c.total} collections</small></span>
        <button type="button" class="btn-ghost btn-sm member-edit-btn" data-edit-collector="${c.id}">Edit</button>
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
  $("#group-cancel").addEventListener("click", () => {
    pendingGroupModal = null;
    closeModal();
  });
  $("#group-save").addEventListener("click", () => saveGroup(group && group.id));
  $("#member-picker").querySelectorAll(".member-edit-btn").forEach((b) => {
    b.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const c = allCollectors.find((x) => x.id === b.dataset.editCollector);
      if (c) openCollectorModal(c, { fromGroupPicker: true, group });
    });
  });
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
let lastPaymentCollectors = [];
let paymentsSearchDebounce = null;

function fmtMoney(v) {
  const n = Number(v) || 0;
  return payCurrency + (n % 1 === 0 ? n : n.toFixed(2));
}

async function loadPayments() {
  try {
    const data = await api("/api/payments");
    payCurrency = (data.config && data.config.currency) || "₹";
    $("#rate-per-entry").value = data.config ? data.config.per_entry : 0;
    $("#rate-card-entry").value = data.config ? data.config.card_entry : 0;
    $("#rate-training").value = data.config ? data.config.training : 0;
    renderPaymentsSummary(data.total_due ?? 0, data.total_paid ?? 0);
    renderPayments(data.collectors || []);
    await loadCardApprovals();
  } catch (e) { alert(e.message); }
}

function renderPaymentsSummary(totalDue, totalPaid, wrap) {
  const el = wrap || $("#payments-summary");
  if (!el) return;
  el.innerHTML = `
    <div class="pay-summary-card due">
      <div class="label">Total due</div>
      <div class="value">${fmtMoney(totalDue)}</div>
    </div>
    <div class="pay-summary-card paid">
      <div class="label">Total paid</div>
      <div class="value">${fmtMoney(totalPaid)}</div>
    </div>`;
}

function paymentRowHtml(r) {
  const last = r.last_payout
    ? `${fmtMoney(r.last_payout.amount)} · ${fmtDate(r.last_payout.created_at)}`
      + ` · ${r.last_payout.entries_count || 0} usual`
      + ` / ${r.last_payout.card_entries_count || 0} card`
    : "—";
  const training = r.training_paid
    ? `<span class="badge badge-yes">Paid</span>`
    : `<span class="badge badge-no">Due</span>`;
  return `<tr>
    <td>${escapeHtml(r.name)}</td>
    <td>${escapeHtml(r.upi_address || "—")}</td>
    <td>${r.total_entries}</td>
    <td>${r.regular_unpaid_entries || 0}</td>
    <td>${r.approved_card_unpaid_entries || 0}</td>
    <td>${r.pending_card_entries || 0}</td>
    <td>${training}</td>
    <td><b>${fmtMoney(r.due)}</b></td>
    <td>${last}</td>
    <td><button class="btn-primary pay-btn" data-pay="${r.id}"
          data-name="${escapeHtml(r.name)}" data-due="${fmtMoney(r.due)}"
          ${r.due > 0 ? "" : "disabled"}>Mark paid</button></td>
  </tr>`;
}

function renderPaymentTableRows(rows, tbody, opts = {}) {
  const emptyMessage = opts.emptyMessage || "No collectors yet.";
  const filtered = opts.filterFn ? opts.filterFn(rows) : rows;
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty">${
      rows.length && opts.filterFn ? "No collectors match your search." : emptyMessage
    }</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map(paymentRowHtml).join("");
  tbody.querySelectorAll("[data-pay]").forEach((b) =>
    b.addEventListener("click", () =>
      markPaid(b.dataset.pay, b.dataset.name, b.dataset.due)));
}

function filterPaymentCollectors(rows) {
  const q = ($("#payments-search")?.value || "").trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) =>
    [r.name, r.phone, r.email, r.upi_address, r.upi_name]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(q)));
}

function renderPayments(rows) {
  lastPaymentCollectors = rows;
  renderPaymentTableRows(rows, $("#payments-table tbody"), {
    filterFn: filterPaymentCollectors,
    emptyMessage: "No collectors yet.",
  });
}

async function loadCardApprovals() {
  const tbody = $("#card-approvals-table tbody");
  if (!tbody) return;
  const rows = await api("/api/card-approvals");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">No card entries waiting for approval.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((r) => `
    <tr>
      <td>${fmtDate(r.collected_at)}</td>
      <td>${escapeHtml(r.collector_name || "—")}<br><small>${escapeHtml(r.collector_phone || r.collector_email || "")}</small></td>
      <td>${escapeHtml(r.child_name || "—")}</td>
      <td>${escapeHtml(r.phone || "—")}</td>
      <td><button class="cancel card-view-btn" data-photo="${escapeHtml(r.medical_record_photo || "")}"
        data-id="${r.id}" data-name="${escapeHtml(r.child_name || r.collector_name || "entry")}">View card</button></td>
      <td><button class="btn-primary card-approve-btn" data-approve-card="${r.id}">Approve</button></td>
    </tr>`).join("");
  tbody.querySelectorAll("[data-photo]").forEach((b) =>
    b.addEventListener("click", () =>
      openCardApproval(b.dataset.id, b.dataset.photo, b.dataset.name)));
  tbody.querySelectorAll("[data-approve-card]").forEach((b) =>
    b.addEventListener("click", () => approveCard(b.dataset.approveCard)));
}

function openCardApproval(id, photo, name) {
  const img = photo ? `<img class="ans-photo" id="card-approval-img" alt="card loading…"/>`
    : `<p class="hint">No card photo found for this entry.</p>`;
  openModal(`<h3>Card approval</h3>
    <p class="hint">${escapeHtml(name || "Entry")}</p>
    ${img}
    <div class="modal-actions">
      <button class="cancel" id="card-close">Close</button>
      <button class="btn-primary" id="card-approve">Approve card</button>
    </div>`);
  $("#card-close").addEventListener("click", closeModal);
  $("#card-approve").addEventListener("click", async () => {
    await approveCard(id);
    closeModal();
  });
  if (photo) loadPhoto(photo, $("#card-approval-img"));
}

async function approveCard(id) {
  try {
    await api(`/api/collections/${id}/approve-card`, { method: "POST" });
    await loadPayments();
  } catch (e) { alert(e.message); }
}

async function saveRates() {
  const per_entry = parseFloat($("#rate-per-entry").value) || 0;
  const card_entry = parseFloat($("#rate-card-entry").value) || 0;
  const training = parseFloat($("#rate-training").value) || 0;
  try {
    await api("/api/payment-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ per_entry, card_entry, training }),
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
    if (selectedGroup && !$("#view-groups").classList.contains("hidden")) {
      await openGroup(selectedGroup.id, false);
    } else {
      loadPayments();
    }
  } catch (e) { alert(e.message); }
}

const _saveRatesBtn = $("#save-rates-btn");
if (_saveRatesBtn) _saveRatesBtn.addEventListener("click", saveRates);
const _paymentsSearch = $("#payments-search");
if (_paymentsSearch) {
  _paymentsSearch.addEventListener("input", () => {
    clearTimeout(paymentsSearchDebounce);
    paymentsSearchDebounce = setTimeout(
      () => renderPayments(lastPaymentCollectors),
      300,
    );
  });
}

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
          ${q.follow_up ? `<span class="q-tag secondary">Follow-up on “Yes”</span>` : ""}
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
    ${followUpBlock(q)}
    <details class="tr-block">
      <summary>Translations (Hindi / Kannada)</summary>
      ${_trFields("hi", "हिन्दी (Hindi)", q)}
      ${_trFields("kn", "ಕನ್ನಡ (Kannada)", q)}
      <p class="hint">Leave blank to fall back to English. For choice options, put one per line in the same order as the English options.</p>
    </details>
    <label class="check"><input type="checkbox" id="q-required" ${q.required ? "checked" : ""}/> Required</label>
    <label class="check"><input type="checkbox" id="q-secondary" ${q.secondary_aim ? "checked" : ""}/> Secondary aim</label>
    <label class="check"><input type="checkbox" id="q-active" ${q.is_active ? "checked" : ""}/> Active (shown in the app)</label>
    <div class="modal-actions">
      <button class="cancel" id="q-cancel">Cancel</button>
      <button class="btn-primary" id="q-save">${isEdit ? "Save changes" : "Add question"}</button>
    </div>`;
}

function _trFields(lang, label, q) {
  const t = (q.translations && q.translations[lang]) || {};
  const opts = Array.isArray(t.options) ? t.options.join("\n") : "";
  return `
    <div class="tr-lang">
      <strong>${label}</strong>
      <input type="text" id="q-title-${lang}" placeholder="Question text" value="${escapeHtml(t.title || "")}" />
      <textarea id="q-help-${lang}" placeholder="Help text (optional)">${escapeHtml(t.help_text || "")}</textarea>
      <textarea id="q-options-${lang}" class="${["single_choice","multi_choice"].includes(q.qtype) ? "" : "hidden"}" placeholder="Options (one per line)">${escapeHtml(opts)}</textarea>
    </div>`;
}

function _trCollect(lang, qtype) {
  const title = $("#q-title-" + lang).value.trim();
  const help = $("#q-help-" + lang).value.trim();
  const options = ["single_choice", "multi_choice"].includes(qtype)
    ? $("#q-options-" + lang).value.split("\n").map((s) => s.trim()).filter(Boolean)
    : [];
  const out = {};
  if (title) out.title = title;
  if (help) out.help_text = help;
  if (options.length) out.options = options;
  return Object.keys(out).length ? out : null;
}

/* ---------- follow-up question (asked when a yes/no is "Yes") ---------- */
function followUpBlock(q) {
  const fu = (q && q.follow_up) || null;
  const enabled = !!fu;
  const f = fu || {};
  const fuType = f.qtype || "yes_no";
  const isChoice = ["single_choice", "multi_choice"].includes(fuType);
  return `
    <div id="q-followup-wrap" class="followup-wrap ${q.qtype === "yes_no" ? "" : "hidden"}">
      <label class="check"><input type="checkbox" id="q-fu-enable" ${enabled ? "checked" : ""}/> Ask a follow-up question when answered “Yes”</label>
      <div id="q-fu-fields" class="fu-fields ${enabled ? "" : "hidden"}">
        <label>Follow-up question text</label>
        <input type="text" id="q-fu-title" value="${escapeHtml(f.title || "")}" placeholder="e.g. Was it treated by a doctor?" />
        <label>Help text (optional)</label>
        <textarea id="q-fu-help" placeholder="Guidance shown under the follow-up">${escapeHtml(f.help_text || "")}</textarea>
        <label>Follow-up answer type</label>
        <select id="q-fu-type">
          ${QTYPES.map((t) => `<option value="${t[0]}" ${fuType === t[0] ? "selected" : ""}>${t[1]}</option>`).join("")}
        </select>
        <div id="q-fu-options-wrap" class="${isChoice ? "" : "hidden"}">
          <label>Options (one per line)</label>
          <textarea id="q-fu-options" placeholder="Option A&#10;Option B">${escapeHtml((f.options || []).join("\n"))}</textarea>
        </div>
        <div id="q-fu-yesno-wrap" class="${fuType === "yes_no" ? "" : "hidden"}">
          <label class="check"><input type="checkbox" id="q-fu-photo" ${f.photo_on_yes ? "checked" : ""}/> Capture a photo when the follow-up is “Yes” (upload)</label>
          <label class="check"><input type="checkbox" id="q-fu-note" ${f.note_on_yes ? "checked" : ""}/> Ask for a text note when the follow-up is “Yes”</label>
        </div>
        <label class="check"><input type="checkbox" id="q-fu-required" ${f.required ? "checked" : ""}/> Follow-up required</label>
        <details class="tr-block">
          <summary>Follow-up translations (Hindi / Kannada)</summary>
          ${_fuTrFields("hi", "हिन्दी (Hindi)", f, isChoice)}
          ${_fuTrFields("kn", "ಕನ್ನಡ (Kannada)", f, isChoice)}
        </details>
      </div>
    </div>`;
}

function _fuTrFields(lang, label, fu, isChoice) {
  const t = (fu.translations && fu.translations[lang]) || {};
  const opts = Array.isArray(t.options) ? t.options.join("\n") : "";
  return `
    <div class="tr-lang">
      <strong>${label}</strong>
      <input type="text" id="q-fu-title-${lang}" placeholder="Follow-up text" value="${escapeHtml(t.title || "")}" />
      <textarea id="q-fu-help-${lang}" placeholder="Help text (optional)">${escapeHtml(t.help_text || "")}</textarea>
      <textarea id="q-fu-options-${lang}" class="${isChoice ? "" : "hidden"}" placeholder="Options (one per line)">${escapeHtml(opts)}</textarea>
    </div>`;
}

function _fuTrCollect(lang, futype) {
  const title = $("#q-fu-title-" + lang).value.trim();
  const help = $("#q-fu-help-" + lang).value.trim();
  const options = ["single_choice", "multi_choice"].includes(futype)
    ? $("#q-fu-options-" + lang).value.split("\n").map((s) => s.trim()).filter(Boolean)
    : [];
  const out = {};
  if (title) out.title = title;
  if (help) out.help_text = help;
  if (options.length) out.options = options;
  return Object.keys(out).length ? out : null;
}

function openQuestionModal(q) {
  openModal(questionForm(q));
  const typeSel = $("#q-type");
  typeSel.addEventListener("change", () => {
    const t = typeSel.value;
    const isChoice = ["single_choice", "multi_choice"].includes(t);
    $("#q-options-wrap").classList.toggle("hidden", !isChoice);
    $("#q-yesno-wrap").classList.toggle("hidden", t !== "yes_no");
    // The follow-up only applies to yes/no parent questions.
    $("#q-followup-wrap").classList.toggle("hidden", t !== "yes_no");
    ["hi", "kn"].forEach((l) =>
      $("#q-options-" + l).classList.toggle("hidden", !isChoice));
  });

  // Follow-up: reveal its fields when enabled, and mirror the option/yes-no
  // toggles based on the follow-up's own answer type.
  $("#q-fu-enable").addEventListener("change", (e) => {
    $("#q-fu-fields").classList.toggle("hidden", !e.target.checked);
  });
  const fuTypeSel = $("#q-fu-type");
  fuTypeSel.addEventListener("change", () => {
    const t = fuTypeSel.value;
    const isChoice = ["single_choice", "multi_choice"].includes(t);
    $("#q-fu-options-wrap").classList.toggle("hidden", !isChoice);
    $("#q-fu-yesno-wrap").classList.toggle("hidden", t !== "yes_no");
    ["hi", "kn"].forEach((l) =>
      $("#q-fu-options-" + l).classList.toggle("hidden", !isChoice));
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
  const translations = {};
  const hi = _trCollect("hi", qtype);
  const kn = _trCollect("kn", qtype);
  if (hi) translations.hi = hi;
  if (kn) translations.kn = kn;

  // Follow-up (only for yes/no parents, when enabled and given a title).
  let follow_up = null;
  if (qtype === "yes_no" && $("#q-fu-enable").checked) {
    const fuTitle = $("#q-fu-title").value.trim();
    if (fuTitle) {
      const futype = $("#q-fu-type").value;
      const fuOptions = ["single_choice", "multi_choice"].includes(futype)
        ? $("#q-fu-options").value.split("\n").map((s) => s.trim()).filter(Boolean)
        : [];
      const fuTr = {};
      const fhi = _fuTrCollect("hi", futype);
      const fkn = _fuTrCollect("kn", futype);
      if (fhi) fuTr.hi = fhi;
      if (fkn) fuTr.kn = fkn;
      follow_up = {
        title: fuTitle,
        help_text: $("#q-fu-help").value.trim() || null,
        qtype: futype,
        options: fuOptions,
        required: $("#q-fu-required").checked,
        photo_on_yes: futype === "yes_no" && $("#q-fu-photo").checked,
        note_on_yes: futype === "yes_no" && $("#q-fu-note").checked,
        translations: fuTr,
      };
    }
  }

  const body = {
    title,
    help_text: $("#q-help").value.trim() || null,
    qtype,
    options,
    translations,
    follow_up,
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
    <div class="ans-row"><div class="ans-q">Child</div><div class="ans-v">${escapeHtml(r.child_name || "—")} · Age ${fmtAge(r.child_age, r.child_age_months)} · Responder: ${escapeHtml(responder)}</div></div>
    <div class="ans-row"><div class="ans-q">Verbal consent</div><div class="ans-v"><span class="${r.verbal_consent ? "yes" : "no"}">${r.verbal_consent ? "Yes" : "No"}</span></div></div>
    <div class="ans-row"><div class="ans-q">Medical record</div><div class="ans-v">${r.medical_record == null ? "—" : `<span class="${r.medical_record ? "yes" : "no"}">${r.medical_record ? "Yes" : "No"}</span>`} · Vaccines: ${fmtVaccines(r.vaccines)}${r.medical_record_photo ? `<br><img class="ans-photo" id="medph" alt="medical record loading…"/>` : ""}</div></div>
    <div class="ans-row"><div class="ans-q">Location</div><div class="ans-v">${locationSpan(r.location_address, r.location_lat, r.location_lng, 5)}</div></div>`;

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
  html += `<div class="modal-actions">
    <button class="btn-danger" id="sub-delete">Delete submission</button>
    <button class="cancel" id="sub-close">Close</button>
  </div>`;
  openModal(html);
  hydrateAddressSpans($("#modal"));
  $("#sub-close").addEventListener("click", closeModal);
  $("#sub-delete").addEventListener("click", async () => {
    if (await deleteSubmission(r.id)) closeModal();
  });
  answers.forEach((a, i) => { if (a.photo_filename) loadPhoto(a.photo_filename, $("#ph-" + i)); });
  if (r.medical_record_photo) loadPhoto(r.medical_record_photo, $("#medph"));
}

async function deleteSubmission(id) {
  if (!confirm(
    "Delete this submission permanently?\n\n" +
    "Its screening answers and any uploaded photos will also be removed. " +
    "This cannot be undone."
  )) return false;
  try {
    await api(`/api/collections/${id}`, { method: "DELETE" });
    const nextPage = lastCollections.length <= 1 && submissionsPage > 1
      ? submissionsPage - 1
      : submissionsPage;
    await Promise.all([loadCollections(nextPage), loadMapCollections(), loadStats()]);
    return true;
  } catch (e) { alert(e.message); return false; }
}

function fmtVaccines(csv) {
  if (!csv) return "—";
  return csv.split(",").map((v) => v === "none" ? "None" : v.toUpperCase()).join(", ");
}

$("#collections-table").addEventListener("click", (e) => {
  const del = e.target.closest("[data-del-sub]");
  if (del) { e.stopPropagation(); deleteSubmission(del.dataset.delSub); return; }
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
  loadCollections(1);
  loadMapCollections();
  if (!$("#view-groups").classList.contains("hidden")) loadGroups();
});
$("#timezone").value = currentTz();
$("#timezone").addEventListener("change", (e) => {
  const v = TZONES[e.target.value] ? e.target.value : "IST";
  localStorage.setItem(TZ_KEY, v);
  refreshAll();
  if (!$("#view-groups").classList.contains("hidden")) loadGroups();
});
$("#export-btn").addEventListener("click", exportCsv);
$("#search").addEventListener("input", () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => loadCollections(1), 350);
});
$("#positive-filter").addEventListener("change", (e) => {
  currentPositiveFilter = e.target.value;
  loadCollections(1);
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const which = tab.dataset.tab;
    $("#tab-collections").classList.toggle("hidden", which !== "collections");
    $("#tab-collectors").classList.toggle("hidden", which !== "collectors");
    // The positivity filter only applies to submissions.
    $("#positive-filter").classList.toggle("hidden", which !== "collections");
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
