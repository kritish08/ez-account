#!/usr/bin/env python3
"""
EZ Account — Autonomous Daily Backup
=====================================
Connects directly to MongoDB Atlas using MONGO_URL from environment.
Reads S3 credentials from the app's own settings collection.
Encrypts the full database dump with MASTER_ENCRYPTION_KEY (AES-256-GCM).
Uploads to S3. Zero API login required.

Required env vars (inherited from backend/.env):
  MONGO_URL             — MongoDB Atlas connection string
  DB_NAME               — Database name (default: BlitzerDB)
  MASTER_ENCRYPTION_KEY — 64-char hex key used by the app
"""

import os
import json
import uuid
import struct
import hmac
import hashlib
import base64
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pymongo import MongoClient

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BACKUP] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME   = os.environ.get("DB_NAME", "BlitzerDB")
HEX_KEY   = os.environ.get("MASTER_ENCRYPTION_KEY", "")

COLLECTIONS = [
    "users", "business", "customers", "products", "suppliers",
    "invoices", "payments", "expenses", "purchases", "ledger",
    "stock_movements", "payment_allocations", "supplier_payments",
    "credit_notes", "debit_notes", "batches", "serial_numbers",
    "bill_of_materials", "production_orders", "advance_payments", "settings"
]


def derive_key(hex_key: str) -> bytes:
    """Derive a 32-byte AES key from the hex master key."""
    raw = bytes.fromhex(hex_key)
    return hashlib.sha256(raw).digest()


def encrypt_data(plaintext: bytes, hex_key: str) -> dict:
    """AES-256-GCM encryption — matches the app's encrypt_data() function."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = derive_key(hex_key)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return {
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode()
    }


def main():
    log.info("Connecting to MongoDB...")
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]

    # ── Read S3 settings from the app's settings collection ──
    s3_settings = db.settings.find_one({"type": "s3"})
    if not s3_settings or not s3_settings.get("configured"):
        log.error("S3 not configured in app settings. Skipping backup.")
        log.error("Go to Settings → Cloud Backup in the app and configure S3 first.")
        return

    aws_key    = s3_settings["aws_access_key_id"]
    aws_secret = s3_settings["aws_secret_access_key"]
    bucket     = s3_settings["bucket_name"]
    region     = s3_settings.get("region", "us-east-1")

    # ── Dump all collections ──────────────────────────────────
    log.info("Dumping %d collections...", len(COLLECTIONS))
    backup_data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": "2.0",
        "collections": {}
    }
    total_docs = 0
    for col in COLLECTIONS:
        docs = list(db[col].find({}, {"_id": 0}))
        backup_data["collections"][col] = docs
        total_docs += len(docs)
        log.info("  %-25s %d docs", col, len(docs))

    log.info("Total: %d documents across %d collections", total_docs, len(COLLECTIONS))

    # ── Encrypt ───────────────────────────────────────────────
    if not HEX_KEY:
        log.error("MASTER_ENCRYPTION_KEY not set. Cannot encrypt backup.")
        return

    log.info("Encrypting backup...")
    json_bytes = json.dumps(backup_data).encode("utf-8")
    encrypted  = encrypt_data(json_bytes, HEX_KEY)

    # ── Upload to S3 ──────────────────────────────────────────
    filename = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.enc"
    s3_key   = f"ez-accounts-backups/{filename}"
    payload  = json.dumps(encrypted).encode("utf-8")

    log.info("Uploading %s to s3://%s/%s ...", filename, bucket, s3_key)
    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_key,
        aws_secret_access_key=aws_secret,
        region_name=region
    )
    s3.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=payload,
        ContentType="application/json"
    )

    # ── Log backup record in MongoDB ──────────────────────────
    db.backup_logs.insert_one({
        "id": str(uuid.uuid4()),
        "filename": filename,
        "size_bytes": len(json_bytes),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "source": "cron"
    })

    log.info("✅ Backup complete: %s (%d bytes uncompressed)", filename, len(json_bytes))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error("❌ Backup FAILED: %s", e, exc_info=True)
        raise SystemExit(1)
