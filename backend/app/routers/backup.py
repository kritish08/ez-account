"""Manual backup ops + cron schedule.

The schedule endpoints persist their config under
`db.settings({"type":"backup_schedule"})` and re-register the cron job via
`services.backup.apply_backup_schedule` synchronously so the response
reflects reality (the job is or isn't running before we reply).

Manual `/backup/create` is the same pipeline as the scheduled job —
snapshot every business collection, envelope-encrypt, upload to S3 —
just triggered by a user action instead of by APScheduler. `boto3` is
synchronous so the upload goes through `asyncio.to_thread` to keep the
FastAPI event loop responsive during a multi-second upload.

Restore deliberately excludes the `settings` and `users` collections so
a stale backup can't overwrite the live S3 config or trample current
logins.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import boto3
from fastapi import APIRouter, Depends, HTTPException

from app.config import MASTER_ENCRYPTION_KEY
from app.database import db
from app.deps import get_current_user, require_admin
from app.schemas.settings import BackupRestoreRequest, BackupScheduleSettings
from app.services.auth import verify_password
from app.services.backup import apply_backup_schedule
from app.services.crypto import decrypt_data, decrypt_secret, encrypt_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["backup"])


@router.get("/settings/backup/schedule")
async def get_backup_schedule(current_user: dict = Depends(get_current_user)):
    """Return the saved backup-schedule config (disabled if none stored)."""
    doc = await db.settings.find_one({"type": "backup_schedule"}, {"_id": 0, "type": 0, "updated_at": 0})
    if not doc:
        return BackupScheduleSettings().model_dump()
    return doc


@router.put("/settings/backup/schedule")
async def update_backup_schedule(
    schedule: BackupScheduleSettings,
    current_user: dict = Depends(get_current_user),
):
    """Persist a new backup-schedule and (re-)register the cron job."""
    config = schedule.model_dump()
    config_doc = {
        "type": "backup_schedule",
        **config,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.settings.update_one({"type": "backup_schedule"}, {"$set": config_doc}, upsert=True)
    # Re-register the cron job synchronously so the response reflects reality.
    apply_backup_schedule(config)
    return {"message": "Backup schedule updated", "schedule": config}


@router.post("/backup/create")
async def create_backup(current_user: dict = Depends(get_current_user)):
    """Create encrypted backup and upload to S3."""
    if not MASTER_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Master encryption key not configured")

    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        raise HTTPException(status_code=400, detail="S3 not configured. Please configure S3 in settings.")

    collections = [
        "users", "business", "customers", "products", "suppliers", "invoices",
        "payments", "expenses", "purchases", "ledger", "stock_movements",
        "payment_allocations", "supplier_payments",
        "credit_notes", "debit_notes", "batches", "serial_numbers",
        "bill_of_materials", "production_orders", "advance_payments", "settings"
    ]

    backup_data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": "2.0",
        "collections": {}
    }

    # `to_list(None)` to match the scheduled job in services/backup.py.
    # The previous cap of 10000 silently truncated any collection larger
    # than that — a backup that quietly drops data is worse than no backup.
    # Read all 21 collections in parallel; the previous sequential loop
    # paid one round-trip per collection.
    collection_docs = await asyncio.gather(*[
        db[c].find({}, {"_id": 0}).to_list(None) for c in collections
    ])
    for c, docs in zip(collections, collection_docs):
        backup_data["collections"][c] = docs

    json_data = json.dumps(backup_data).encode()
    encrypted_package = encrypt_data(json_data, MASTER_ENCRYPTION_KEY)

    # boto3 is synchronous; route the upload through asyncio.to_thread so a
    # multi-second upload doesn't block the FastAPI event loop.
    try:
        backup_filename = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.enc"

        def _s3_upload():
            s3_client = boto3.client(
                's3',
                aws_access_key_id=s3_settings["aws_access_key_id"],
                aws_secret_access_key=decrypt_secret(s3_settings["aws_secret_access_key"], MASTER_ENCRYPTION_KEY),
                region_name=s3_settings.get("region", "us-east-1"),
            )
            s3_client.put_object(
                Bucket=s3_settings["bucket_name"],
                Key=f"ez-accounts-backups/{backup_filename}",
                Body=json.dumps(encrypted_package).encode(),
                ContentType="application/json",
            )

        await asyncio.to_thread(_s3_upload)

        await db.backup_logs.insert_one({
            "id": str(uuid.uuid4()),
            "filename": backup_filename,
            "size_bytes": len(json_data),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "success"
        })

        return {"message": "Backup created successfully", "filename": backup_filename}
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.get("/backup/list")
async def list_backups(current_user: dict = Depends(get_current_user)):
    """List available backups from S3."""
    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        return {"backups": [], "message": "S3 not configured"}

    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_settings["aws_access_key_id"],
            aws_secret_access_key=decrypt_secret(s3_settings["aws_secret_access_key"], MASTER_ENCRYPTION_KEY),
            region_name=s3_settings.get("region", "us-east-1")
        )

        response = s3_client.list_objects_v2(
            Bucket=s3_settings["bucket_name"],
            Prefix="ez-accounts-backups/"
        )

        backups = []
        for obj in response.get("Contents", []):
            backups.append({
                "filename": obj["Key"].replace("ez-accounts-backups/", ""),
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat()
            })

        backups.sort(key=lambda x: x["last_modified"], reverse=True)
        return {"backups": backups}
    except Exception as e:
        return {"backups": [], "error": str(e)}


# Required confirmation phrase, mirroring the factory reset. Verbose on
# purpose so a single stolen token or a stray click can't trigger it.
RESTORE_CONFIRMATION_PHRASE = "RESTORE AND OVERWRITE ALL DATA"

# In-memory cooldown, user_id -> last-attempt epoch. Restores are rare and
# catastrophic when wrong; one per 10 minutes is generous.
_restore_cooldown_seconds = 10 * 60
_last_restore_by_user: dict = {}


@router.post("/backup/restore/{filename}")
async def restore_backup(
    filename: str,
    req: BackupRestoreRequest,
    current_user: dict = Depends(require_admin),
):
    """Restore from encrypted backup.

    This deletes every document in each collection present in the archive
    and re-inserts the archived ones — the most destructive operation in
    the product. It previously required nothing but a valid session, so
    any logged-in user, or anyone holding a stolen 24-hour token, could
    roll the live books back to an arbitrary point.

    Now requires the same three factors as the factory reset:
      1. Valid authenticated session, with an administrator role
      2. Re-entered password (which a stolen token alone cannot supply)
      3. Verbatim confirmation phrase
    plus a per-user cooldown that counts failures.

    These checks run BEFORE any S3 or key configuration lookup, so a
    misconfigured deployment can't mask a missing credential check.
    """
    user_id = current_user.get("id") or current_user.get("email")
    now = time.time()
    last = _last_restore_by_user.get(user_id, 0)
    if now - last < _restore_cooldown_seconds:
        remaining = int(_restore_cooldown_seconds - (now - last))
        raise HTTPException(
            status_code=429,
            detail=f"Restore rate-limited. Try again in {remaining // 60}m {remaining % 60}s.",
        )

    if req.confirmation != RESTORE_CONFIRMATION_PHRASE:
        _last_restore_by_user[user_id] = now
        raise HTTPException(
            status_code=400,
            detail=(
                f"Confirmation phrase mismatch. To proceed, the `confirmation` "
                f"field must be exactly: '{RESTORE_CONFIRMATION_PHRASE}'."
            ),
        )

    user = await db.users.find_one({"email": current_user.get("email")})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed = user.get("password_hash") or user.get("password")
    if not hashed or not verify_password(req.password, hashed):
        _last_restore_by_user[user_id] = now
        raise HTTPException(status_code=401, detail="Incorrect password. Restore forbidden.")

    logger.warning(
        f"BACKUP RESTORE initiated by user_id={user_id} "
        f"email={current_user.get('email')} filename={filename}"
    )
    _last_restore_by_user[user_id] = now

    if not MASTER_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Master encryption key not configured")

    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        raise HTTPException(status_code=400, detail="S3 not configured")

    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_settings["aws_access_key_id"],
            aws_secret_access_key=decrypt_secret(s3_settings["aws_secret_access_key"], MASTER_ENCRYPTION_KEY),
            region_name=s3_settings.get("region", "us-east-1")
        )

        response = s3_client.get_object(
            Bucket=s3_settings["bucket_name"],
            Key=f"ez-accounts-backups/{filename}"
        )

        encrypted_package = json.loads(response["Body"].read().decode())
        decrypted_data = decrypt_data(encrypted_package, MASTER_ENCRYPTION_KEY)
        backup_data = json.loads(decrypted_data.decode())

        # Restore collections in parallel.
        # 'settings' is excluded to preserve current S3/system config.
        # 'users' is excluded so a stale backup can't overwrite live logins.
        restore_exempt = {"settings", "users"}

        async def _restore_one(coll_name: str, docs: list) -> None:
            # delete-then-insert MUST be sequential within a single
            # collection, but across collections they're independent.
            await db[coll_name].delete_many({})
            await db[coll_name].insert_many(docs)

        await asyncio.gather(*[
            _restore_one(name, docs)
            for name, docs in backup_data["collections"].items()
            if name not in restore_exempt and docs
        ])

        return {"message": "Backup restored successfully", "restored_at": backup_data.get("created_at")}
    except Exception as e:
        logger.error(f"Restore failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")
