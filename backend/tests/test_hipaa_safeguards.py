"""End-to-end checks for the HIPAA technical safeguards.

Run from the backend/ directory:

    .venv/bin/python -m pytest tests/ -q

Each test drives the real FastAPI app against a throwaway SQLite database and
media directory, so it verifies behaviour rather than restating the
implementation. These are the controls an auditor would ask to see evidence
for, which is exactly why they are worth asserting in CI.
"""
import base64
import importlib
import os
import shutil
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

STRONG_PASSWORD = "Fieldwork2026x"
ADMIN_PASSWORD = "AdminPass2026x"


@pytest.fixture()
def app_env(monkeypatch):
    """A fresh app instance with an isolated database and media volume."""
    tmp = tempfile.mkdtemp(prefix="crist-test-")
    media = os.path.join(tmp, "media")
    os.makedirs(media, exist_ok=True)

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp}/test.db")
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    monkeypatch.setenv("MEDIA_DIR", media)
    monkeypatch.setenv(
        "MEDIA_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode()
    )
    monkeypatch.setenv("MAX_LOGIN_ATTEMPTS", "3")
    monkeypatch.setenv("LOCKOUT_MINUTES", "15")
    monkeypatch.setenv("MIN_PASSWORD_LENGTH", "10")
    monkeypatch.setenv("REQUIRE_ADMIN_MFA", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "")

    # Re-import the whole app graph so the new environment is picked up.
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]

    from app import audit, crypto, models  # noqa: F401
    from app.database import SessionLocal
    from app.main import app

    yield {
        "client": TestClient(app),
        "media": media,
        "SessionLocal": SessionLocal,
        "models": models,
        "crypto": crypto,
        "audit": audit,
    }
    shutil.rmtree(tmp, ignore_errors=True)


def _register(client, phone="9876500001", password=STRONG_PASSWORD):
    return client.post("/auth/register", json={
        "name": "Test Collector",
        "phone": phone,
        "password": password,
        "upi_address": "test@bank",
    })


def _login(client, username, password):
    return client.post(
        "/auth/login", data={"username": username, "password": password}
    )


# --------------------------------------------------------------- passwords
def test_weak_password_is_rejected(app_env):
    res = _register(app_env["client"], password="pass1234")
    assert res.status_code == 400
    assert "at least 10 characters" in res.json()["detail"]


def test_common_password_is_rejected(app_env):
    res = _register(app_env["client"], password="password1")
    assert res.status_code == 400


def test_strong_password_is_accepted(app_env):
    res = _register(app_env["client"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"]
    # The client is told how long an idle session may live.
    assert body["idle_lock_minutes"] == 15


# ------------------------------------------------------------------ lockout
def test_account_locks_after_repeated_failures(app_env):
    client = app_env["client"]
    _register(client)

    for _ in range(2):
        assert _login(client, "9876500001", "WrongPassword1").status_code == 401

    # Third failure trips the configured threshold of 3.
    locked = _login(client, "9876500001", "WrongPassword1")
    assert locked.status_code == 423

    # And the correct password is refused while the lock stands — otherwise
    # the lockout would be trivially bypassable.
    assert _login(client, "9876500001", STRONG_PASSWORD).status_code == 423


def test_unknown_account_does_not_leak_existence(app_env):
    client = app_env["client"]
    _register(client)
    unknown = _login(client, "9999999999", "WhateverPass1")
    wrong = _login(client, "9876500001", "WrongPassword1")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


# --------------------------------------------------------- session revocation
def test_logout_revokes_the_token(app_env):
    client = app_env["client"]
    token = _register(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/me", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 200

    # The same token must now be dead — this is the property that plain JWT
    # expiry cannot provide.
    after = client.get("/me", headers=headers)
    assert after.status_code == 401


def test_password_change_revokes_other_sessions(app_env):
    client = app_env["client"]
    token = _register(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/auth/change-password", headers=headers, json={
        "current_password": STRONG_PASSWORD,
        "new_password": "BrandNewPass99",
    })
    assert res.status_code == 200
    assert client.get("/me", headers=headers).status_code == 401


# ------------------------------------------------------- encryption at rest
def test_uploaded_photo_is_encrypted_on_disk(app_env):
    client, media = app_env["client"], app_env["media"]
    token = _register(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    plaintext = b"\xff\xd8\xff\xe0 pretend JPEG with a child's name on it"
    res = client.post(
        "/collections/photo",
        headers=headers,
        files={"file": ("card.jpg", plaintext, "image/jpeg")},
    )
    assert res.status_code == 200, res.text
    stored = os.path.join(media, res.json()["filename"])

    with open(stored, "rb") as fh:
        raw = fh.read()

    # The bytes on disk must be ciphertext, not the image.
    assert raw.startswith(b"CRIST1")
    assert plaintext not in raw
    # ...and must round-trip back to the original.
    assert app_env["crypto"].read_decrypted(stored) == plaintext


def test_tampered_photo_fails_authentication(app_env):
    client, media = app_env["client"], app_env["media"]
    token = _register(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/collections/photo", headers=headers,
        files={"file": ("card.jpg", b"original bytes", "image/jpeg")},
    )
    path = os.path.join(media, res.json()["filename"])

    with open(path, "r+b") as fh:
        fh.seek(-1, os.SEEK_END)
        last = fh.read(1)
        fh.seek(-1, os.SEEK_END)
        fh.write(bytes([last[0] ^ 0xFF]))

    # AES-GCM is authenticated, so a flipped bit is detected rather than
    # silently returning corrupt data.
    with pytest.raises(app_env["crypto"].MediaCryptoError):
        app_env["crypto"].read_decrypted(path)


# ------------------------------------------------------------------ RBAC
def test_collector_cannot_reach_admin_endpoints(app_env):
    client = app_env["client"]
    token = _register(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/api/collections", "/api/export.csv", "/api/audit",
                 "/api/collectors"):
        assert client.get(path, headers=headers).status_code == 403, path


def test_admin_without_mfa_is_blocked_from_phi(app_env):
    """An admin who has not enrolled a second factor gets a token but must not
    be able to read participant data."""
    client = app_env["client"]
    SessionLocal, models = app_env["SessionLocal"], app_env["models"]
    from app.auth import hash_password

    db = SessionLocal()
    db.add(models.User(
        name="Admin", email="admin@example.org",
        password_hash=hash_password(ADMIN_PASSWORD),
        upi_address="-", is_admin=True,
    ))
    db.commit()
    db.close()

    challenge = _login(client, "admin@example.org", ADMIN_PASSWORD)
    assert challenge.status_code == 200
    body = challenge.json()
    # Password alone yields a challenge, never a token.
    assert body.get("mfa_required") is True
    assert body.get("enrollment_required") is True
    assert "access_token" not in body


# ------------------------------------------------------------------- audit
def test_phi_actions_are_audited(app_env):
    client = app_env["client"]
    SessionLocal, models = app_env["SessionLocal"], app_env["models"]
    token = _register(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/collections/photo", headers=headers,
        files={"file": ("c.jpg", b"bytes", "image/jpeg")},
    )
    _login(client, "9876500001", "WrongPassword1")

    db = SessionLocal()
    actions = {r.action for r in db.query(models.AuditLog).all()}
    db.close()

    assert "phi.upload_photo" in actions
    assert "login.failure" in actions
    assert "login.success" in actions


def test_audit_log_never_stores_the_search_term(app_env):
    """A search box is a PHI vector: administrators type children's names into
    it. The audit detail must record that a search happened, not what it was."""
    client = app_env["client"]
    SessionLocal, models = app_env["SessionLocal"], app_env["models"]
    from app.auth import hash_password

    db = SessionLocal()
    db.add(models.User(
        name="Admin2", email="a2@example.org",
        password_hash=hash_password(ADMIN_PASSWORD),
        upi_address="-", is_admin=True, mfa_enabled=True, mfa_secret="X" * 16,
    ))
    db.commit()
    db.close()

    # Bypass the MFA exchange by minting a token directly — this test is about
    # what the audit row contains, not about the login flow.
    db = SessionLocal()
    admin = db.query(models.User).filter(
        models.User.email == "a2@example.org"
    ).first()
    from app.auth import create_access_token
    token = create_access_token(admin)
    db.close()

    res = client.get(
        "/api/collections?search=Aarav",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    db = SessionLocal()
    rows = db.query(models.AuditLog).filter(
        models.AuditLog.action == "phi.view_collections"
    ).all()
    db.close()

    assert rows, "the listing should have been audited"
    for r in rows:
        assert "Aarav" not in (r.detail or "")
        assert "search=yes" in (r.detail or "")


def test_audit_purge_refuses_short_retention(app_env, monkeypatch):
    """A stray environment variable must not be able to quietly destroy the
    six-year trail."""
    from app.config import settings

    monkeypatch.setattr(settings, "AUDIT_RETENTION_DAYS", 30)
    db = app_env["SessionLocal"]()
    with pytest.raises(ValueError):
        app_env["audit"].purge_expired(db)
    db.close()


# ------------------------------------------------------- de-identified export
def test_deidentified_export_drops_identifiers(app_env):
    client = app_env["client"]
    SessionLocal, models = app_env["SessionLocal"], app_env["models"]
    from app.auth import create_access_token, hash_password

    token = _register(client).json()["access_token"]
    client.post("/collections/sync", headers={"Authorization": f"Bearer {token}"},
                json={"collections": [{
                    "id": "11111111-1111-1111-1111-111111111111",
                    "verbal_consent": True,
                    "phone": "9998887777",
                    "child_name": "Aarav Sharma",
                    "child_age": 4,
                    "child_sex": "male",
                    "location_lat": 12.971598,
                    "location_lng": 77.594566,
                    "location_address": "12 Church Street, Bengaluru",
                    "answers": [],
                }]})

    db = SessionLocal()
    db.add(models.User(
        name="Admin3", email="a3@example.org",
        password_hash=hash_password(ADMIN_PASSWORD),
        upi_address="-", is_admin=True, mfa_enabled=True, mfa_secret="Y" * 16,
    ))
    db.commit()
    admin = db.query(models.User).filter(
        models.User.email == "a3@example.org"
    ).first()
    admin_token = create_access_token(admin)
    db.close()
    headers = {"Authorization": f"Bearer {admin_token}"}

    identified = client.get("/api/export.csv", headers=headers).text
    assert "Aarav Sharma" in identified
    assert "9998887777" in identified
    assert "12.971598" in identified

    deid = client.get("/api/export.csv?deidentified=true", headers=headers).text
    assert "Aarav Sharma" not in deid
    assert "9998887777" not in deid
    assert "Church Street" not in deid
    assert "12.971598" not in deid
    # Coarsened to one decimal place (~11 km).
    assert "13.0" in deid or "12.9" in deid
    # Clinical content survives, which is the point of the mode.
    assert "male" in deid


# ------------------------------------------------- production configuration
def test_production_refuses_placeholder_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me-in-production-please")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@h/db")
    monkeypatch.setenv("MEDIA_ENCRYPTION_KEY",
                       base64.b64encode(os.urandom(32)).decode())
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    import app.config as cfg
    importlib.reload(cfg)
    with pytest.raises(SystemExit):
        cfg.validate_production()


def test_production_refuses_missing_media_key(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "b" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@h/db")
    monkeypatch.setenv("MEDIA_ENCRYPTION_KEY", "")
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    import app.config as cfg
    importlib.reload(cfg)
    with pytest.raises(SystemExit):
        cfg.validate_production()


def test_production_refuses_sqlite_and_wildcard_cors(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "c" * 64)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./prod.db")
    monkeypatch.setenv("MEDIA_ENCRYPTION_KEY",
                       base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    import app.config as cfg
    importlib.reload(cfg)
    with pytest.raises(SystemExit):
        cfg.validate_production()
