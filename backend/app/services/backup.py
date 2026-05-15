"""Scheduled S3 backup cron job.

Module-level `scheduler` singleton that lifespan starts; `apply_backup_schedule`
re-registers the cron when the user changes settings; `scheduled_backup_job`
mirrors the manual `/backup/create` pipeline so manual and scheduled
backups produce identical encrypted artifacts.

See OPS-BATCH-A (`Auto-backup cron`) in FIXES.md for the original port.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import boto3
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import MASTER_ENCRYPTION_KEY
from app.database import db
from app.services.crypto import encrypt_data

logger = logging.getLogger(__name__)

# Single module-level scheduler. Lifecycle managed by the lifespan handler.
scheduler = AsyncIOScheduler(timezone="UTC")


async def scheduled_backup_job():
    """Snapshot every business collection, envelope-encrypt, upload to S3.

    boto3.put_object is synchronous — runs inside asyncio.to_thread so a
    slow upload doesn't block the FastAPI event loop.
    """
    logger.info("Scheduled backup job triggered.")
    try:
        if not MASTER_ENCRYPTION_KEY:
            logger.error("Scheduled backup ABORTED: MASTER_ENCRYPTION_KEY not set.")
            return

        s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
        if not s3_settings or not s3_settings.get("configured"):
            logger.warning("Scheduled backup SKIPPED: S3 not configured in Settings.")
            return

        collections = [
            "users", "business", "customers", "products", "suppliers", "invoices",
            "payments", "expenses", "purchases", "ledger", "stock_movements",
            "payment_allocations", "supplier_payments",
            "credit_notes", "debit_notes", "batches", "serial_numbers",
            "bill_of_materials", "production_orders", "advance_payments", "settings",
        ]
        backup_data = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": "2.0",
            "collections": {},
        }
        for collection in collections:
            docs = await db[collection].find({}, {"_id": 0}).to_list(None)
            backup_data["collections"][collection] = docs

        json_data = json.dumps(backup_data).encode()
        encrypted_package = encrypt_data(json_data, MASTER_ENCRYPTION_KEY)
        backup_filename = f"auto_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.enc"

        def _s3_upload():
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=s3_settings["aws_access_key_id"],
                aws_secret_access_key=s3_settings.get("aws_secret_access_key", ""),
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
            "status": "success",
            "type": "scheduled",
        })
        logger.info(f"Scheduled backup completed: {backup_filename}")
    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}", exc_info=True)
        try:
            await db.backup_logs.insert_one({
                "id": str(uuid.uuid4()),
                "filename": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "error": str(e),
                "type": "scheduled",
            })
        except Exception:
            pass


def apply_backup_schedule(config: dict):
    """Remove the existing cron job and re-add it with the new config.

    Bad timezone strings fall back to UTC silently rather than 500ing.
    """
    scheduler.remove_all_jobs()
    if not config.get("enabled"):
        logger.info("Backup schedule disabled — no cron job registered.")
        return

    time_str = config.get("time", "00:00")
    try:
        hour, minute = (int(x) for x in time_str.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 0, 0

    tz_str = config.get("timezone", "UTC")
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.utc

    frequency = config.get("frequency", "daily")
    if frequency == "weekly":
        day = config.get("day_of_week", 0)  # 0=Mon ... 6=Sun
        trigger = CronTrigger(day_of_week=day, hour=hour, minute=minute, timezone=tz)
    else:
        trigger = CronTrigger(hour=hour, minute=minute, timezone=tz)

    if not MASTER_ENCRYPTION_KEY:
        logger.warning("Backup scheduled but MASTER_ENCRYPTION_KEY is missing — runs will fail until set.")

    scheduler.add_job(scheduled_backup_job, trigger=trigger, id="auto_backup", replace_existing=True)
    logger.info(f"Backup cron registered: {frequency} at {hour:02d}:{minute:02d} ({tz_str})")
