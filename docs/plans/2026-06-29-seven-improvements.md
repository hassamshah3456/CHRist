# Plan: Seven Improvements (2026-06-29)

Validated via the brainstorming skill. Execution via the executing-plans skill
(batches of ~3 tasks, verify between batches).

## Understanding Summary

Seven targeted improvements across the Flutter collector app (`lib/`), the
FastAPI backend (`backend/app/`), and the vanilla-JS admin dashboard
(`dashboard/`). Goals: correct age entry (allow 0), admin-editable collector
contact/UPI info, server-computed anomaly flags surfaced in the admin Groups
view, a collector Profile screen housing Logout, accurate worked-time counting
that includes offline foreground time, an IST/US-Eastern timezone toggle on the
admin dashboard, and hardened, blocking location handling in the field.

Constraint: only `is_admin` exists — there is **no team-lead login**, so flags
appear in the admin dashboard Groups view. Collections store both `collected_at`
(device, offline-safe) and a server-received timestamp.

## Decision Log

1. Age: add `0` quick-pick chip for years and months; keep typed `0` valid.
2. Edit collector: Edit button -> modal in collectors table; editable = name,
   phone, email, upi_address, upi_name. Admin only.
3. Red flag: flag red in Groups view when consecutive entries are `<60s` apart,
   measured by device `collected_at`.
4. Profile/logout: header logout icon becomes a profile icon -> new Profile
   screen containing name/phone/email/UPI/language switch + Logout.
5. Offline time: count foreground app-open time, accumulate locally, flush to
   `/auth/heartbeat` `app_seconds` on reconnect; per-flush cap retained.
6. Timezone: admin dashboard defaults IST, toggle to US Eastern, applied to all
   dashboard timestamps (client-side display; backend keeps UTC). Collector app
   keeps local/India time.
7. Location: hard-block collecting until enabled; persistent banner + button to
   the exact OS setting (location settings if services off, app settings if
   permission deniedForever); re-prompt every attempt. GPS offline, geocode later.

## Assumptions

- A1: Flags are server-computed and rendered in the admin Groups view only.
- A2: Edit reuses the existing admin modal styling + new `PUT /api/collectors/{id}`.
- A3: Offline time uses local elapsed-time accounting (foreground only), flushed
  via heartbeat; per-interval caps tolerate clock changes/suspends.
- A4: Timezone toggle is client-side in `dashboard/app.js`, persisted in
  `localStorage`; backend stores UTC.
- A5: "Exact OS setting" = `Geolocator.openLocationSettings()` (services off) and
  `Geolocator.openAppSettings()` (permission deniedForever).

## Tasks

### Item 1 — Allow age 0
1. In `lib/screens/collect/collect_form_screen.dart`, add `0` to the years
   quick-picks (`const [0, 1, 2, 3, 4, 5]`) and months quick-picks
   (`const [0, 2, 4, 6, 8, 10, 11]`). Confirm `_validate()` still accepts 0.
   - Verify: `flutter analyze` clean; manual: 0 selectable & saves.

### Item 4 — Profile screen + header icon (app)
2. Create `lib/screens/profile_screen.dart`: shows name, phone, email, UPI
   address/name, a language-change action, and a Logout button (move the
   existing `_confirmLogout` flow here).
3. In `lib/screens/dashboard_screen.dart`, replace the header logout `IconButton`
   with a profile `IconButton` (`Icons.person_rounded`) that pushes
   `ProfileScreen`. Keep the language icon. Add i18n keys as needed.
   - Verify: `flutter analyze`; manual: profile opens, logout works from profile.

### Item 7 — Harden location (app)
4. Extend `lib/services/location_service.dart`: add `permissionState()` returning
   an enum (serviceOff / denied / deniedForever / granted) so the UI can pick the
   right settings deep-link.
5. Strengthen the `LocationGate`/`LocationBanner` (in `lib/widgets/common.dart`):
   re-check permission on app resume and before every collection; show a
   persistent banner with an "Enable location" button that calls
   `openLocationSettings()` (services off) or `openAppSettings()` (deniedForever);
   keep Start Collecting disabled until a fix is obtainable.
   - Verify: `flutter analyze`; manual: toggling GPS off blocks collecting and the
     button opens the correct OS screen.

### Item 5 — Offline time tracking (app + backend)
6. App: add a foreground stopwatch (a `WidgetsBindingObserver`, likely in
   `PresenceService` or a small `AppTimeTracker`) that accumulates foreground
   seconds, persisting the running total to local DB (`local_database.dart`) so it
   survives restarts. Track `unsynced_seconds`.
7. App: include `offline_seconds: <unsynced>` in the heartbeat payload
   (`presence_service.dart` + `HeartbeatRequest` send); on a successful 2xx, reset
   the local unsynced counter.
8. Backend: extend `schemas.HeartbeatRequest` with `offline_seconds: int = 0`
   (bounded) and in `auth_router.heartbeat` add it to `user.app_seconds` (cap the
   per-request contribution to a sane max, e.g. <= 3600).
   - Verify: backend imports/tests run; manual: airplane-mode usage then reconnect
     increases `app_seconds`.

### Item 2 — Edit collector info (backend + dashboard)
9. Backend: add `PUT /api/collectors/{id}` in `admin_router.py` (admin-only)
   accepting name, phone, email, upi_address, upi_name; add the request schema in
   `schemas.py`; validate phone/email/UPI minimally; return updated
   `CollectorSummary`.
10. Dashboard: add an "Edit" button to the collectors table row(s) in
    `dashboard/app.js`; open a modal (reuse group-modal markup/CSS) pre-filled with
    current values; on save, `PUT` then refresh the table.
    - Verify: edit persists and re-renders; invalid input shows an error.

### Item 3 — Red-flag anomalies (backend + dashboard)
11. Backend: in `_collector_summaries` (`admin_router.py`), for each collector
    sort their `collected_at` values and count consecutive pairs `< 60s` apart;
    add `flagged_count: int` and `flagged: bool` to `CollectorSummary`
    (`schemas.py`).
12. Dashboard: in the Groups view rendering (`dashboard/app.js`), render flagged
    members in red with a badge/tooltip showing `flagged_count`.
    - Verify: a seeded rapid pair shows red in Groups; normal collectors don't.

### Item 6 — Timezone toggle (dashboard)
13. Dashboard: add a tz preference (`localStorage`, default `IST`) and a header
    toggle (IST <-> US Eastern) in `dashboard/index.html` + `app.js`.
14. Dashboard: update `fmtDate`/`fmtDateTime` (and any direct date formatting) to
    convert UTC -> selected zone using `Intl.DateTimeFormat` with
    `timeZone: 'Asia/Kolkata'` or `'America/New_York'`; re-render on toggle.
    - Verify: timestamps shift correctly when toggling; default is IST.

## Out of Scope / Non-goals

- No team-lead role/auth. No OS background location tracking. Collector app
  timezone unchanged (local/India).
