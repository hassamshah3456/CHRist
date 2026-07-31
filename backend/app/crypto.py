"""Envelope encryption for medical-record photographs at rest.

HIPAA §164.312(a)(2)(iv) makes encryption of stored PHI an addressable
implementation specification. Photographs of OPD and immunisation cards are the
most sensitive artefacts in this system — a single image can carry a child's
name, a guardian's name, a clinic, dates and diagnoses — so they are encrypted
with AES-256-GCM before they ever touch the filesystem.

File format (all binary, single file per photo):

    magic  "CRIST1"   6 bytes
    nonce            12 bytes
    ciphertext+tag    n bytes   (GCM tag is appended by the AEAD construction)

GCM is authenticated, so a tampered or truncated file fails to decrypt rather
than silently returning corrupt bytes.

Encryption is keyed by MEDIA_ENCRYPTION_KEY (base64, 32 bytes) held only in the
server environment. Because the key never lives on the media volume, destroying
the key destroys the photographs — that is the "crypto-shredding" disposal path
described in compliance/data-retention-and-disposal.md.

Legacy files written before encryption was introduced do not carry the magic
prefix; `decrypt_bytes` detects that and returns them unchanged so existing
deployments keep working. Use `manage.py encrypt-media` to convert them.
"""
import base64
import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"CRIST1"
NONCE_BYTES = 12
KEY_BYTES = 32


class MediaCryptoError(Exception):
    """Raised when a stored photo cannot be decrypted."""


def key_is_valid(raw: str) -> bool:
    """True if `raw` is a base64-encoded 32-byte key."""
    try:
        return len(base64.b64decode(raw, validate=True)) == KEY_BYTES
    except Exception:
        return False


def generate_key() -> str:
    """A fresh base64 key, for `manage.py generate-media-key`."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode()


def _load_key() -> Optional[bytes]:
    """The configured key, or None when encryption is not enabled.

    Imported lazily so that config validation can call `key_is_valid` without
    a circular import at module load.
    """
    from .config import settings

    raw = settings.MEDIA_ENCRYPTION_KEY
    if not raw:
        return None
    if not key_is_valid(raw):
        raise MediaCryptoError(
            "MEDIA_ENCRYPTION_KEY is not a base64-encoded 32-byte value."
        )
    return base64.b64decode(raw)


def encryption_enabled() -> bool:
    from .config import settings
    return bool(settings.MEDIA_ENCRYPTION_KEY)


def is_encrypted(blob: bytes) -> bool:
    return blob[: len(MAGIC)] == MAGIC


def encrypt_bytes(plaintext: bytes) -> bytes:
    """Encrypt for storage. Returns the plaintext untouched if no key is set,
    so development environments keep working without ceremony (production
    start-up refuses to boot without a key — see config.validate_production)."""
    key = _load_key()
    if key is None:
        return plaintext
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return MAGIC + nonce + ciphertext


def decrypt_bytes(blob: bytes) -> bytes:
    """Decrypt a stored photo. Files without the magic prefix predate
    encryption and are returned as-is."""
    if not is_encrypted(blob):
        return blob
    key = _load_key()
    if key is None:
        raise MediaCryptoError(
            "This photo is encrypted but MEDIA_ENCRYPTION_KEY is not set."
        )
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_BYTES]
    ciphertext = blob[len(MAGIC) + NONCE_BYTES :]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise MediaCryptoError(
            "Photo failed authentication — wrong key, or the file was altered."
        ) from exc


def write_encrypted(path: str, plaintext: bytes) -> None:
    """Write atomically so a crash cannot leave a half-written photo."""
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(encrypt_bytes(plaintext))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def read_decrypted(path: str) -> bytes:
    with open(path, "rb") as fh:
        return decrypt_bytes(fh.read())
