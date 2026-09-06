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


# ---- CORS ----
def parse_cors_origins(raw: str | None) -> list[str]:
    """Parse CORS_ORIGINS into an explicit allow-list, or refuse to start.

    This used to degrade silently: an unset value started the app with
    `allow_origins=["*"]`. The comment defending that argued the paired
    `allow_credentials=False` made it safe, but this API authenticates
    with an Authorization header rather than cookies, so the credentials
    flag buys nothing — the wildcard simply let any origin read every
    unauthenticated endpoint. A missing origin list is a configuration
    error, and it should fail as loudly as a missing JWT_SECRET.

    `*` is rejected outright: browsers reject it alongside credentialed
    requests anyway, so it can only ever be a mistake here.
    """
    origins = [o.strip() for o in (raw or "").split(",") if o.strip()]
    if not origins:
        raise RuntimeError(
            "CORS_ORIGINS environment variable must be set to a comma-separated "
            "list of allowed origins, e.g. "
            "CORS_ORIGINS=https://app.example.com,http://localhost:8080"
        )
    if "*" in origins:
        raise RuntimeError(
            "CORS_ORIGINS may not contain '*'. Browsers reject a wildcard origin "
            "on credentialed requests, so list the exact origins instead."
        )
    return origins


CORS_ORIGINS = parse_cors_origins(os.getenv("CORS_ORIGINS"))


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
