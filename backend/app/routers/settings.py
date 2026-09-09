"""Application settings + factory-reset.

Covers four logical groups under one router:
- `/api/settings/modules`   — feature flags (CN / DN / Advanced IMS / Production)
- `/api/settings/s3`        — S3 creds for encrypted backups (with test endpoint)
- `/api/settings/system`    — registration_enabled and other system toggles
- `/api/auth/config`        — public subset (no auth required) for the login page
- `/api/system/reset`       — factory reset, gated by password + verbatim
                              confirmation phrase + 1-hour rate limit per user

S3 endpoints inline `botocore.exceptions` so failures surface as clean
400s instead of the NameError they hit in the pre-refactor inline code.
"""

import logging
import time
from datetime import datetime, timezone

import boto3
from fastapi import APIRouter, Depends, HTTPException

from app.config import MASTER_ENCRYPTION_KEY
from app.database import db
from app.deps import get_current_user, require_admin
from app.schemas.settings import (
    OPENAI_KEY_MASK, ModulesSettings, OpenAISettings, S3Settings,
    SystemResetRequest, SystemSettings,
)
from app.services import ai_credentials
from app.services.auth import verify_password
from app.services.crypto import decrypt_secret, encrypt_secret
from services.ai_service import reset_client as reset_ai_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings/modules")
async def get_modules_settings(current_user: dict = Depends(get_current_user)):
    settings = await db.settings.find_one({"type": "modules"}, {"_id": 0})
    if not settings:
        return {
            "enable_credit_notes": True,
            "enable_debit_notes":  True,
            "enable_advanced_ims": False,
            "enable_production":   False,
            "enable_gst":          False,
        }
    # Ensure new boolean flags have defaults if missing from DB (migration safety)
    return {
        "enable_credit_notes": settings.get("enable_credit_notes", True),
        "enable_debit_notes":  settings.get("enable_debit_notes",  True),
        "enable_advanced_ims": settings.get("enable_advanced_ims", False),
        "enable_production":   settings.get("enable_production",   False),
        # Absent for every business that predates the GST module — default
        # off so enabling it stays a deliberate act.
        "enable_gst":          settings.get("enable_gst",          False),
    }


@router.put("/settings/modules")
async def update_modules_settings(settings: ModulesSettings, current_user: dict = Depends(get_current_user)):
    settings_doc = {
        "type": "modules",
        **settings.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.settings.update_one({"type": "modules"}, {"$set": settings_doc}, upsert=True)
    return {"message": "Module settings updated successfully"}


# Placeholder shown in place of the real S3 secret in GET responses. When
# the client POSTs back this exact string, the server treats it as "keep
# the existing secret" rather than persisting the mask.
_S3_SECRET_MASK = "********"


@router.get("/settings/s3")
async def get_s3_settings(current_user: dict = Depends(get_current_user)):
    settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if settings:
        settings["aws_secret_access_key"] = _S3_SECRET_MASK if settings.get("aws_secret_access_key") else ""
    return settings or {"configured": False}


@router.post("/settings/s3")
async def save_s3_settings(settings: S3Settings, current_user: dict = Depends(get_current_user)):
    # botocore exception types — imported inline so the rest of the module
    # doesn't drag botocore in at import time.
    from botocore.exceptions import ClientError, NoCredentialsError  # noqa: PLC0415

    # If the client sent back the mask, they're editing other fields and
    # want to keep the previously-saved secret. Look it up; refuse if
    # there's no prior secret to preserve.
    secret = settings.aws_secret_access_key
    if secret == _S3_SECRET_MASK:
        existing = await db.settings.find_one({"type": "s3"}, {"_id": 0, "aws_secret_access_key": 1})
        if not existing or not existing.get("aws_secret_access_key"):
            raise HTTPException(status_code=400, detail="Cannot save: no existing secret to preserve. Provide aws_secret_access_key.")
        # Stored value may be encrypted (or plaintext, if written before
        # encryption at rest). Decrypt so the live-credential check below
        # runs against the real secret.
        secret = decrypt_secret(existing["aws_secret_access_key"], MASTER_ENCRYPTION_KEY)

    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=secret,
            region_name=settings.region
        )
        s3_client.head_bucket(Bucket=settings.bucket_name)
    except NoCredentialsError:
        raise HTTPException(status_code=400, detail="Invalid AWS credentials")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            raise HTTPException(status_code=400, detail="Bucket not found")
        if error_code == '403':
            raise HTTPException(status_code=400, detail="Access denied to bucket")
        raise HTTPException(status_code=400, detail=f"S3 error: {str(e)}")

    settings_doc = {
        "type": "s3",
        **settings.model_dump(),
        # Encrypted at rest. The `settings` collection is included in every
        # backup archive, so a plaintext secret here meant each backup
        # shipped the credentials that created it.
        "aws_secret_access_key": encrypt_secret(secret, MASTER_ENCRYPTION_KEY),
        "configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.settings.update_one({"type": "s3"}, {"$set": settings_doc}, upsert=True)
    return {"message": "S3 settings saved and validated successfully"}


@router.post("/settings/s3/test")
async def test_s3_connection(settings: S3Settings, current_user: dict = Depends(get_current_user)):
    """Test S3 connection without saving."""
    from botocore.exceptions import ClientError, NoCredentialsError  # noqa: PLC0415

    # Same mask handling as save: testing with the masked secret means
    # "test the currently-stored creds with these other field values".
    secret = settings.aws_secret_access_key
    if secret == _S3_SECRET_MASK:
        existing = await db.settings.find_one({"type": "s3"}, {"_id": 0, "aws_secret_access_key": 1})
        if not existing or not existing.get("aws_secret_access_key"):
            return {"success": False, "message": "No stored secret to test against. Provide aws_secret_access_key."}
        secret = decrypt_secret(existing["aws_secret_access_key"], MASTER_ENCRYPTION_KEY)

    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=secret,
            region_name=settings.region
        )
        s3_client.head_bucket(Bucket=settings.bucket_name)
        return {"success": True, "message": "Connection successful"}
    except NoCredentialsError:
        return {"success": False, "message": "Invalid AWS credentials"}
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            return {"success": False, "message": "Bucket not found"}
        if error_code == '403':
            return {"success": False, "message": "Access denied to bucket"}
        return {"success": False, "message": f"Error: {str(e)}"}


async def _probe_openai(api_key: str, base_url: str | None) -> list[str]:
    """One cheap authenticated call, to prove the key works before it's saved.

    Listing models is the smallest request that exercises authentication
    without spending tokens. Patched out in tests — nothing here should
    reach the network during a test run.
    """
    from openai import AsyncOpenAI  # noqa: PLC0415

    client = AsyncOpenAI(api_key=api_key, base_url=base_url or None, timeout=15.0)
    try:
        page = await client.models.list()
        return [m.id for m in page.data]
    finally:
        await client.close()


async def _stored_openai_key() -> str | None:
    doc = await db.settings.find_one({"type": "openai"}, {"_id": 0, "api_key": 1})
    if not doc or not doc.get("api_key"):
        return None
    return decrypt_secret(doc["api_key"], MASTER_ENCRYPTION_KEY)


@router.get("/settings/openai")
async def get_openai_settings(current_user: dict = Depends(get_current_user)):
    """Everything about the AI credential except the credential.

    `source` is the useful part: it tells you whether the app is running on
    the key you pasted or on one baked into the deployment's environment.
    """
    doc = await db.settings.find_one({"type": "openai"}, {"_id": 0}) or {}
    creds = await ai_credentials.resolve(use_cache=False)

    return {
        "configured": creds is not None,
        "source": creds.source if creds else "none",
        "key_hint": ai_credentials.key_hint(creds.api_key) if creds else "",
        # Echo the chosen models so the form shows what is actually in force,
        # including the values inherited from env or left at their defaults.
        "model": creds.model if creds else None,
        "vision_model": creds.vision_model if creds else None,
        "transcribe_model": creds.transcribe_model if creds else None,
        "transcribe_language": creds.transcribe_language if creds else None,
        "base_url": creds.base_url if creds else None,
        # Whether *this* record exists, as opposed to an env fallback.
        "saved_in_settings": bool(doc.get("api_key")),
        "updated_at": doc.get("updated_at"),
    }


@router.post("/settings/openai")
async def save_openai_settings(
    settings: OpenAISettings, current_user: dict = Depends(require_admin)
):
    api_key = settings.api_key
    if api_key == OPENAI_KEY_MASK:
        api_key = await _stored_openai_key()
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="No stored key to keep. Paste your OpenAI API key.",
            )

    doc = {
        "type": "openai",
        # Encrypted at rest: the settings collection travels inside every
        # backup archive, so a plaintext key here would ship with them.
        "api_key": encrypt_secret(api_key, MASTER_ENCRYPTION_KEY),
        "base_url": settings.base_url,
        "model": settings.model,
        "vision_model": settings.vision_model,
        "transcribe_model": settings.transcribe_model,
        "transcribe_language": settings.transcribe_language,
        "configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.settings.update_one({"type": "openai"}, {"$set": doc}, upsert=True)

    # The whole point of storing it here is that it takes effect now.
    ai_credentials.invalidate()
    reset_ai_client()

    logger.info("OpenAI credential updated by %s", current_user.get("email"))
    return {"message": "OpenAI settings saved"}


@router.delete("/settings/openai")
async def delete_openai_settings(current_user: dict = Depends(require_admin)):
    """Forget the stored key and fall back to the environment, if any."""
    await db.settings.delete_one({"type": "openai"})
    ai_credentials.invalidate()
    reset_ai_client()

    creds = await ai_credentials.resolve(use_cache=False)
    logger.info("OpenAI credential removed by %s", current_user.get("email"))
    return {
        "message": "OpenAI key removed",
        "source": creds.source if creds else "none",
    }


@router.post("/settings/openai/test")
async def test_openai_credential(
    settings: OpenAISettings, current_user: dict = Depends(require_admin)
):
    """Check a key against OpenAI without saving it."""
    api_key = settings.api_key
    if api_key == OPENAI_KEY_MASK:
        api_key = await _stored_openai_key()
        if not api_key:
            return {"success": False, "message": "No stored key to test. Paste one first."}

    try:
        models = await _probe_openai(api_key, settings.base_url)
    except Exception as e:  # noqa: BLE001 — surfaced to the user, never raised
        # Never echo the key: OpenAI's own 401 body quotes it back verbatim,
        # and this response is rendered in a browser and pasted into chats.
        message = str(e).replace(api_key, "…") if api_key else str(e)
        if "401" in message or "Incorrect API key" in message or "invalid_api_key" in message:
            message = "OpenAI rejected that key. Check it hasn't been revoked or rotated."
        elif "429" in message:
            message = "The key works, but the account is rate-limited or out of quota."
        return {"success": False, "message": message[:300]}

    wanted = settings.model
    return {
        "success": True,
        "message": f"Key works — {len(models)} models available.",
        "models": sorted(models)[:50],
        "requested_model_available": (wanted in models) if wanted else None,
    }


@router.get("/auth/config")
async def get_auth_config():
    """Public authentication configuration (no auth required)."""
    settings = await db.settings.find_one({"type": "system"}, {"_id": 0})
    return {
        "registration_enabled": settings.get("registration_enabled", False) if settings else False
    }


@router.get("/settings/system")
async def get_system_settings(current_user: dict = Depends(get_current_user)):
    """Get system settings."""
    settings = await db.settings.find_one({"type": "system"}, {"_id": 0})
    if not settings:
        return {"registration_enabled": False}
    return settings


@router.post("/settings/system")
async def update_system_settings(settings: SystemSettings, current_user: dict = Depends(get_current_user)):
    """Update system settings."""
    settings_doc = {
        "type": "system",
        **settings.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.settings.update_one({"type": "system"}, {"$set": settings_doc}, upsert=True)
    return {"message": "System settings updated successfully"}


# Required confirmation phrase. Deliberately verbose so it can't be triggered
# by an accidental click or a single stolen token.
RESET_CONFIRMATION_PHRASE = "DELETE ALL ACCOUNTING DATA"

# In-memory rate limiter for /system/reset. Maps user_id -> last-reset epoch.
# A successful reset is permitted at most once per hour per user — enough to
# slow down an attacker that has compromised a token, while still allowing
# legitimate re-resets during testing.
_reset_cooldown_seconds = 60 * 60
_last_reset_by_user: dict = {}


@router.post("/system/reset")
async def reset_system(req: SystemResetRequest, current_user: dict = Depends(require_admin)):
    """Wipe all accounting data.

    Requires three independent factors:
      1. Valid authenticated session, with an administrator role
      2. Re-entered password
      3. Verbatim confirmation phrase
    Plus a 1-hour rate limit per user, regardless of success.
    """
    user_id = current_user.get("id") or current_user.get("email")
    now = time.time()
    last = _last_reset_by_user.get(user_id, 0)
    if now - last < _reset_cooldown_seconds:
        remaining = int(_reset_cooldown_seconds - (now - last))
        raise HTTPException(
            status_code=429,
            detail=f"Factory reset rate-limited. Try again in {remaining // 60}m {remaining % 60}s."
        )

    # Confirmation phrase check — failure also counts toward the cooldown so
    # repeated guesses can't bypass the rate limiter.
    if req.confirmation != RESET_CONFIRMATION_PHRASE:
        _last_reset_by_user[user_id] = now
        raise HTTPException(
            status_code=400,
            detail=(
                f"Confirmation phrase mismatch. To proceed, the `confirmation` "
                f"field must be exactly: '{RESET_CONFIRMATION_PHRASE}'."
            )
        )

    user = await db.users.find_one({"email": current_user.get("email")})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed = user.get("password_hash") or user.get("password")
    if not hashed or not verify_password(req.password, hashed):
        _last_reset_by_user[user_id] = now
        raise HTTPException(status_code=401, detail="Incorrect password. Factory reset forbidden.")

    logger.warning(
        f"FACTORY RESET initiated by user_id={user_id} email={current_user.get('email')}"
    )
    _last_reset_by_user[user_id] = now

    cols = await db.list_collection_names()
    # Keep logins, config, backups, and atomic counters.
    exempt = ["users", "settings", "backup_logs", "s3", "counters"]

    deleted = {}
    for c in cols:
        if c not in exempt:
            res = await db[c].delete_many({})
            deleted[c] = res.deleted_count

    logger.warning(f"FACTORY RESET completed by user_id={user_id} deleted_counts={deleted}")
    return {"message": "Factory reset complete. All accounting data has been permanently deleted.", "details": deleted}
