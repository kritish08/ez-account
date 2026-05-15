"""Business setup / profile.

Single-tenant — there's only one business doc. Setup is idempotent: on
re-save, the existing id is preserved so foreign references don't break.
Opening cash / opening bank balances post their counter-entry to the
`capital` account at first save only.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.database import db
from app.deps import get_current_user
from app.schemas.business import BusinessSetup
from app.services.ledger import create_ledger_entry

router = APIRouter(prefix="/api", tags=["business"])


@router.post("/business/setup")
async def setup_business(business: BusinessSetup, current_user: dict = Depends(get_current_user)):
    existing = await db.business.find_one({}, {"_id": 0})

    # Preserve the existing id on update. The previous code generated a fresh
    # UUID on every save, breaking any record that references the business id.
    business_id = existing["id"] if existing and existing.get("id") else str(uuid.uuid4())

    business_doc = {
        "id": business_id,
        **business.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing:
        await db.business.update_one({}, {"$set": business_doc})
    else:
        business_doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.business.insert_one(business_doc)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Gather up to four opening-balance ledger entries — all independent
        # (different account names, same ref). Built as a list to avoid
        # passing empty gather()s when only one of cash/bank is set.
        opening_entries = []
        if business.opening_cash > 0:
            opening_entries.append(create_ledger_entry("cash", business.opening_cash, 0, "Opening cash balance", "setup", business_id, today))
            opening_entries.append(create_ledger_entry("capital", 0, business.opening_cash, "Opening capital (cash)", "setup", business_id, today))
        if business.opening_bank > 0:
            opening_entries.append(create_ledger_entry("bank", business.opening_bank, 0, "Opening bank balance", "setup", business_id, today))
            opening_entries.append(create_ledger_entry("capital", 0, business.opening_bank, "Opening capital (bank)", "setup", business_id, today))
        if opening_entries:
            await asyncio.gather(*opening_entries)

    return {"message": "Business setup complete", "id": business_id}


@router.get("/business")
async def get_business(current_user: dict = Depends(get_current_user)):
    business = await db.business.find_one({}, {"_id": 0})
    # Previously returned `null` 200 when unset, which crashed any frontend
    # that tried to destructure the response. Return an explicit shape so
    # the frontend can distinguish "not configured yet" from "request failed".
    if not business:
        return {"configured": False}
    return {**business, "configured": True}
