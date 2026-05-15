"""Environment & runtime configuration.

Centralises every `os.getenv` lookup that used to live at the top of
`server.py`. Runs the startup-time validation gates (JWT_SECRET strength,
MASTER_ENCRYPTION_KEY format) at module import so a misconfigured deploy
fails fast instead of crashing on the first request.
"""

import os
from dotenv import load_dotenv

# Load .env BEFORE reading any env vars — server.py used to do this and
# downstream modules expect the env to already be populated when imported.
load_dotenv()


# ---- Core ----
MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "BlitzerDB")

# ---- JWT / auth ----
SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# ---- Backup encryption (AES-256) ----
MASTER_ENCRYPTION_KEY = os.getenv("MASTER_ENCRYPTION_KEY")

# ---- WebAuthn / Passkey ----
# RP_ID must match the host the browser sees (no scheme, no port for normal
# hostnames). For localhost dev this is "localhost"; for production it would
# be e.g. "ezaccounts.zerp.me".
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "EZ Accounts")


# ---- Startup gates (fail fast on misconfigured deploy) ----
if not SECRET_KEY or SECRET_KEY in ("supersecretkey", "changeme", "secret"):
    raise RuntimeError(
        "JWT_SECRET environment variable must be set to a strong random value. "
        "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
    )

if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable must be set")

# MASTER_ENCRYPTION_KEY is optional (backup feature only), but if set, it must
# be a valid 64-char hex string (32 bytes for AES-256). Catching a malformed
# value at startup is much better than a 500 traceback at /backup/create time.
if MASTER_ENCRYPTION_KEY:
    try:
        _key_bytes = bytes.fromhex(MASTER_ENCRYPTION_KEY)
        if len(_key_bytes) != 32:
            raise ValueError(f"expected 32 bytes, got {len(_key_bytes)}")
    except ValueError as _e:
        raise RuntimeError(
            f"MASTER_ENCRYPTION_KEY must be a 64-char hex string (32 bytes for AES-256). "
            f"Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'. "
            f"Validation error: {_e}"
        )
