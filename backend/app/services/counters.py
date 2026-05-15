"""Atomic reference-number generator.

A single MongoDB counter document per series (invoice / purchase /
credit_note / debit_note / production_order) backs every ref-number
issuance. The `find_one_and_update` is the only atomic operation we
need — concurrent callers get distinct, monotonically-increasing
values without locking.

See REF-NUM-ATOMIC in FIXES.md for the bug that motivated this.
"""

from pymongo import ReturnDocument

from app.database import db


async def _next_seq(name: str) -> int:
    """Atomically return a unique monotonically-increasing sequence number.

    The counter is seeded from the existing max value at startup (see
    `app/lifespan.py::_seed_counter_from_max`) so old records aren't
    overwritten on first boot.
    """
    doc = await db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]


async def get_next_invoice_number() -> str:
    return f"INV-{str(await _next_seq('invoice')).zfill(5)}"


async def get_next_purchase_number() -> str:
    return f"PUR-{str(await _next_seq('purchase')).zfill(5)}"


async def get_next_credit_note_number() -> str:
    return f"CN-{str(await _next_seq('credit_note')).zfill(5)}"


async def get_next_debit_note_number() -> str:
    return f"DN-{str(await _next_seq('debit_note')).zfill(5)}"
