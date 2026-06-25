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
}

async function loadCollections() {
  const data = await api("/api/collections?period=" + currentPeriod());
  lastCollections = data;
  renderCollections(data);
  renderMapCollections(data);
}

async function loadCollectors() {
  const data = await api("/api/collectors");
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
    { label: "Collectors", value: s.collectors_count, color: "#f0a500" },
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

function renderCollections(rows) {
  const q = ($("#search").value || "").toLowerCase();
  const filtered = q
    ? rows.filter((r) => JSON.stringify(r).toLowerCase().includes(q))
    : rows;
  const tbody = $("#collections-table tbody");
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty">No submissions found.</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map((r) => {
    const responder = r.responder === "other"
      ? (r.responder_other || "Other") : cap(r.responder);
    const loc = r.location_address
      || (r.location_lat != null ? `${r.location_lat.toFixed(4)}, ${r.location_lng.toFixed(4)}` : "—");
    return `<tr>
      <td>${fmtDate(r.collected_at)}</td>
      <td>${r.collector_name || "—"}</td>
      <td>${r.child_age ?? "—"}</td>
      <td>${cap(r.child_sex)}</td>
      <td>${responder}</td>
      <td><span class="badge ${r.verbal_consent ? "badge-yes" : "badge-no"}">${r.verbal_consent ? "Yes" : "No"}</span></td>
      <td>${loc}</td>
    </tr>`;
  }).join("");
}

function renderCollectors(rows) {
  const tbody = $("#collectors-table tbody");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">No collectors yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((c) => `
    <tr>
      <td>${c.name}</td>
      <td>${c.email}</td>
      <td>${c.upi_address || "—"}</td>
      <td><b>${c.total}</b></td>
      <td>${fmtDate(c.last_collection)}</td>
      <td>${c.signup_address || (c.signup_lat != null ? `${c.signup_lat.toFixed(4)}, ${c.signup_lng.toFixed(4)}` : "—")}</td>
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
      .bindPopup(`<b>${r.collector_name || "Collector"}</b><br>
        Age ${r.child_age ?? "—"} · ${cap(r.child_sex)}<br>
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
$("#period").addEventListener("change", () => { loadStats(); loadCollections(); });
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
