"""Ledger helpers — double-entry book-keeping primitives.

All write helpers accept an optional `session=` so callers in a Mongo
multi-document transaction can enrol these writes in the same txn.
Single-node mongods will reject `start_transaction` — Atlas (and the
`mongodb-atlas-local` image we use locally, which is a single-member
replica set) supports it.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClientSession

from app.database import db


async def create_ledger_entry(
    account: str,
    debit: float,
    credit: float,
    narration: str,
    ref_type: str,
    ref_id: str,
    date: str = None,
    session: Optional[AsyncIOMotorClientSession] = None,
):
    """Create a double-entry ledger record."""
    entry = {
        "id": str(uuid.uuid4()),
        "account": account,
        "debit": debit,
        "credit": credit,
        "narration": narration,
        "ref_type": ref_type,
        "ref_id": ref_id,
        "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ledger.insert_one(entry, session=session)
    return entry


async def delete_ledger_entries(
    ref_type: str,
    ref_id: str,
    session: Optional[AsyncIOMotorClientSession] = None,
):
    """Delete all ledger entries that referenced the given source row."""
    await db.ledger.delete_many({"ref_type": ref_type, "ref_id": ref_id}, session=session)


async def get_account_balance(account: str) -> float:
    """Current balance for an account (debits - credits)."""
    pipeline = [
        {"$match": {"account": account}},
        {"$group": {
            "_id": None,
            "total_debit": {"$sum": "$debit"},
            "total_credit": {"$sum": "$credit"},
        }},
    ]
    result = await db.ledger.aggregate(pipeline).to_list(1)
    if result:
        return result[0]["total_debit"] - result[0]["total_credit"]
    return 0
