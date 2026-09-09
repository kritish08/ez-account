"""Where the OpenAI credential comes from, and which model to use with it.

Two sources, in order:

1. `db.settings` — pasted into Settings → AI by an admin. Encrypted at
   rest with the MEK, exactly like the S3 secret.
2. The `OPENAI_*` environment variables — how the key used to be supplied
   and how deployments that never open the UI still work.

The point of the first is that a key can be replaced without a redeploy,
so nothing may cache the resolved value indefinitely: reads are cached for
`_TTL_SECONDS` (cheap under load, and picks up a change made by another
worker within half a minute) and the writing path calls `invalidate()` so
the process that made the change sees it immediately.
"""

import os
import time
from dataclasses import dataclass
from typing import Literal, Optional

from app.config import MASTER_ENCRYPTION_KEY
from app.database import db
from app.services.crypto import decrypt_secret

# Sensible current defaults, used only when neither settings nor env speak.
DEFAULT_MODEL = "gpt-5.6"
DEFAULT_VISION_MODEL = "gpt-5.6"
DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-transcribe"

_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class AICredentials:
    api_key: str
    base_url: Optional[str]
    model: str
    vision_model: str
    transcribe_model: str
    transcribe_language: Optional[str]
    source: Literal["settings", "env"]


_cached: Optional[AICredentials] = None
_cached_at: float = 0.0


def invalidate() -> None:
    """Drop the cache. Called whenever the stored credential changes."""
    global _cached, _cached_at
    _cached = None
    _cached_at = 0.0


def _env(name: str) -> Optional[str]:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


async def resolve(*, use_cache: bool = True) -> Optional[AICredentials]:
    """The credential the app should use right now, or None if unconfigured."""
    global _cached, _cached_at

    if use_cache and _cached is not None and (time.monotonic() - _cached_at) < _TTL_SECONDS:
        return _cached

    doc = await db.settings.find_one({"type": "openai"}, {"_id": 0}) or {}

    stored_key = doc.get("api_key")
    if stored_key:
        api_key = decrypt_secret(stored_key, MASTER_ENCRYPTION_KEY)
        source: Literal["settings", "env"] = "settings"
    else:
        api_key = _env("OPENAI_API_KEY")
        source = "env"

    if not api_key:
        _cached, _cached_at = None, 0.0
        return None

    def pick(field: str, env_name: str, default: Optional[str]) -> Optional[str]:
        return doc.get(field) or _env(env_name) or default

    creds = AICredentials(
        api_key=api_key,
        # Only for OpenAI-compatible gateways; unset means api.openai.com.
        base_url=pick("base_url", "OPENAI_BASE_URL", None),
        model=pick("model", "OPENAI_MODEL", DEFAULT_MODEL),
        vision_model=pick("vision_model", "OPENAI_VISION_MODEL", None)
        or pick("model", "OPENAI_MODEL", DEFAULT_VISION_MODEL),
        transcribe_model=pick(
            "transcribe_model", "OPENAI_TRANSCRIBE_MODEL", DEFAULT_TRANSCRIBE_MODEL
        ),
        # ISO-639-1 hint for transcription; Hinglish benefits from naming it.
        transcribe_language=pick("transcribe_language", "OPENAI_TRANSCRIBE_LANGUAGE", None),
        source=source,
    )
    _cached, _cached_at = creds, time.monotonic()
    return creds


async def is_configured() -> bool:
    return await resolve() is not None


async def require() -> AICredentials:
    """Same as resolve(), but says what to do about it when there's no key."""
    creds = await resolve()
    if creds is None:
        raise RuntimeError(
            "No OpenAI API key configured. Add one in Settings → AI, "
            "or set OPENAI_API_KEY in the environment."
        )
    return creds


def key_hint(api_key: str) -> str:
    """A tail the user can match against their dashboard, and nothing more."""
    tail = api_key[-4:] if len(api_key) >= 4 else ""
    return f"…{tail}"
