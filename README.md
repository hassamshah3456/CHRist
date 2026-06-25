# UsmleWise CHRIST

A field **data-collection app** (Flutter, Android + iOS) backed by a **FastAPI**
server. Collectors register, capture child/responder data with verbal consent,
and everything is **geo-tagged** and **auto-synced** to the server whenever the
device is online. Works fully offline — records queue locally and push on
reconnect.

```
datcollectionapp/
├── lib/                  # Flutter app
├── backend/              # FastAPI + SQLAlchemy server
├── android_overrides/    # AndroidManifest with location/internet permissions
└── .github/workflows/    # Cloud APK build (GitHub Actions)
```

---

## 1. Backend (FastAPI)

### Run locally
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive API docs: http://localhost:8000/docs

By default it uses a local **SQLite** file (`usmlewise.db`). For production set
`DATABASE_URL` to a Postgres URL and a strong `SECRET_KEY` (see `.env.example`).

### Deploy (so the phone can reach it)
- **Render** (easiest): push this repo, then *New → Blueprint* using
  `backend/render.yaml`. You get a public URL like
  `https://usmlewise-christ-api.onrender.com`.
- Any Docker host works — `backend/Dockerfile` is self-contained.

### Endpoints
| Method | Path                  | Purpose                                  |
|--------|-----------------------|------------------------------------------|
| POST   | `/auth/register`      | Create collector (name, email, password, UPI, signup location) |
| POST   | `/auth/login`         | Email + password → JWT                   |
| GET    | `/me`                 | Current user                             |
| POST   | `/collections/sync`   | Upsert queued collections (idempotent)   |
| GET    | `/collections?period=`| List by `today\|yesterday\|week\|month\|all` |
| GET    | `/stats`              | Dashboard counters                       |

---

## 2. App → server connection

The app reads its server URL from `lib/config.dart`, overridable at build time:

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://your-server.com
```

- Android **emulator** talking to a local server: use `http://10.0.2.2:8000`.
- **Real phone**: it must be your **deployed HTTPS URL** (a phone can't reach
  your laptop's `localhost`).

---

## 3. Build the APK (no local toolchain needed)

A GitHub Actions workflow builds a release APK in the cloud:

1. Push this project to a GitHub repo.
2. (Recommended) Settings → *Secrets and variables → Actions → Variables* →
   add `API_BASE_URL` = your deployed server URL.
3. Actions tab → **Build Android APK** → *Run workflow*.
4. Download the `usmlewise-christ-apk` artifact → install
   `app-release.apk` on the device (enable "Install unknown apps").

The workflow runs `flutter create` to generate the Android project, applies
`android_overrides/AndroidManifest.xml` (location + internet permissions), then
`flutter build apk --release`. The release build is signed with the standard
debug key, so it installs directly — fine for distributing test APKs. For a
Play Store release you'd add a proper upload keystore.

### Building locally instead
If you have Flutter installed:
```bash
flutter create --org com.usmlewise --project-name usmlewise_christ --platforms=android,ios .
cp android_overrides/AndroidManifest.xml android/app/src/main/AndroidManifest.xml
flutter pub get
flutter build apk --release --dart-define=API_BASE_URL=https://your-server.com
```

> iOS: same codebase. After `flutter create ... --platforms=ios` add the
> `NSLocationWhenInUseUsageDescription` key to `ios/Runner/Info.plist`, then
> build in Xcode / `flutter build ipa`.

---

## 4. App flow

1. **Welcome** → *Registration* or *Sign in*.
2. **Register**: name, email, password, UPI ID (+ optional different UPI name).
   Location permission is requested and the **sign-up location is recorded**.
3. **Dashboard**: greets the collector, shows stats (today / week / month /
   total + consent yes/no), a **Start Collecting** button and **See past
   collections**. A banner appears if location is off; a chip shows records
   waiting to sync.
4. **Past Collections**: count + date filters (*Today / Yesterday / Last week
   (default) / Last month*) and a **Start Collecting** button.
5. **Collect — Step 1 (Consent)**: collector name shown automatically; location
   captured silently in the background; **Verbal Consent** Yes/No dropdown.
6. **Collect — Step 2 (About the child)**: Age, Sex, Responder
   (Father / Mother / Others → free-text). Saving stores locally and syncs.

## 5. Offline & sync behaviour
- Every collection is written to on-device SQLite immediately.
- `connectivity_plus` watches the network; when internet returns the queued
  records are pushed automatically (also retried on app open and screen loads).
- Sync is **idempotent** (client-generated UUIDs), so retries never duplicate.
