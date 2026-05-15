"""Purchase CRUD.

Every purchase posts:
- One supplier-payable / cash / bank ledger entry depending on `payment_status`
- One inventory-asset debit equal to the bill total
- Per-line stock-in movements (batch & serial side-effects through
  `services.stock.create_stock_movement`)

Edit refuses if a supplier payment / debit-note has already been applied
(FIN-P0-3) — caller must reverse those first so cash and AP stay in sync.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.purchase import PurchaseCreate, PurchaseUpdate
from app.services.ledger import create_ledger_entry, delete_ledger_entries
from app.services.money import _money
from app.services.counters import get_next_purchase_number
from app.services.payments_apply import apply_debit_to_purchase
from app.services.stock import create_stock_movement, delete_stock_movements

router = APIRouter(prefix="/api", tags=["purchases"])


@router.post("/purchases")
async def create_purchase(purchase: PurchaseCreate, current_user: dict = Depends(get_current_user)):
    purchase_id = str(uuid.uuid4())
    purchase_number = await get_next_purchase_number()
    purchase_date = purchase.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    items = []
    total = 0

    for item in purchase.items:
        product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")

        amount = _money(item.quantity * item.cost_price)
        items.append({
            "product_id": item.product_id,
            "product_name": product["name"],
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "amount": amount
        })
        total += amount

        # Update product cost price
        await db.products.update_one({"id": item.product_id}, {"$set": {"cost_price": item.cost_price}})

        # Create stock movement (stock in)
        await create_stock_movement(
            item.product_id, item.quantity, 0, "purchase", purchase_id, purchase_date,
            batch_id=getattr(item, "batch_id", None),
            serial_numbers=getattr(item, "serial_numbers", None)
        )

    supplier_name = None
    if purchase.supplier_id:
        supplier = await db.suppliers.find_one({"id": purchase.supplier_id}, {"_id": 0})
        if supplier:
            supplier_name = supplier["name"]

    purchase_doc = {
        "id": purchase_id,
        "purchase_number": purchase_number,
        "supplier_id": purchase.supplier_id,
        "supplier_name": supplier_name,
        "items": items,
        "total": total,
        "payment_status": purchase.payment_status,
        "notes": purchase.notes,
        "date": purchase_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.purchases.insert_one(purchase_doc)

    # Create ledger entries based on payment status
    if purchase.payment_status == "cash":
        await create_ledger_entry("cash", 0, total, f"Purchase {purchase_number}", "purchase", purchase_id, purchase_date)
    elif purchase.payment_status == "bank":
        await create_ledger_entry("bank", 0, total, f"Purchase {purchase_number}", "purchase", purchase_id, purchase_date)
    elif purchase.payment_status == "unpaid" and purchase.supplier_id:
        await create_ledger_entry(f"supplier:{purchase.supplier_id}", 0, total, f"Purchase {purchase_number}", "purchase", purchase_id, purchase_date)

    # Debit Inventory Asset Account (not Purchases expense directly, for accrual accuracy)
    await create_ledger_entry("inventory_asset", total, 0, f"Purchase {purchase_number}", "purchase", purchase_id, purchase_date)

    # Check for Supplier Debit Balance (Advance/Debit Note) and update status/ledger awareness if needed
    debit_used = 0
    if purchase.supplier_id and purchase.payment_status == "unpaid" and purchase.apply_debit:
        amount_due, debit_used = await apply_debit_to_purchase(purchase.supplier_id, purchase_id, total)
        if debit_used > 0:
            return {"message": "Purchase recorded", "id": purchase_id, "purchase_number": purchase_number, "debit_used": debit_used}

    return {"message": "Purchase recorded", "id": purchase_id, "purchase_number": purchase_number, "debit_used": 0}


@router.get("/purchases")
async def list_purchases(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    supplier_id: Optional[str] = None,
    debit_used_only: bool = False,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if supplier_id:
        query["supplier_id"] = supplier_id
    if debit_used_only:
        query["debit_used"] = {"$gt": 0}

    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}

    purchases = await db.purchases.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    return purchases


@router.get("/purchases/{purchase_id}")
async def get_purchase(purchase_id: str, current_user: dict = Depends(get_current_user)):
    purchase = await db.purchases.find_one({"id": purchase_id}, {"_id": 0})
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return purchase


@router.put("/purchases/{purchase_id}")
async def update_purchase(purchase_id: str, purchase: PurchaseUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.purchases.find_one({"id": purchase_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Purchase not found")

    # Mirror the invoice-update rule (FIN-P0-3): refuse to edit a purchase
    # that already has a supplier payment / debit-note applied. The previous
    # behaviour reversed and re-wrote ledger entries without touching the
    # payment side, orphaning supplier-payment cash.
    if existing.get("debit_used", 0) > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit a purchase that has supplier-debit applied. "
                   "Reverse the debit-note application first.",
        )
    sp_count = await db.supplier_payments.count_documents({"purchase_id": purchase_id})
    if sp_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit a purchase that has supplier payments applied. "
                   "Delete the supplier payment first."
        )

    # Reverse previous entries
    await delete_stock_movements("purchase", purchase_id)
    await delete_ledger_entries("purchase", purchase_id)

    items = []
    total = 0
    purchase_date = purchase.date or existing["date"]

    for item in purchase.items:
        product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")

        amount = _money(item.quantity * item.cost_price)
        items.append({
            "product_id": item.product_id,
            "product_name": product["name"],
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "amount": amount
        })
        total += amount

        await db.products.update_one({"id": item.product_id}, {"$set": {"cost_price": item.cost_price}})

        await create_stock_movement(
            item.product_id, item.quantity, 0, "purchase", purchase_id, purchase_date,
            batch_id=getattr(item, "batch_id", None),
            serial_numbers=getattr(item, "serial_numbers", None)
        )

    supplier_name = None
    if purchase.supplier_id:
        supplier = await db.suppliers.find_one({"id": purchase.supplier_id}, {"_id": 0})
        if supplier:
            supplier_name = supplier["name"]

    update_data = {
        "supplier_id": purchase.supplier_id,
        "supplier_name": supplier_name,
        "items": items,
        "total": total,
        "payment_status": purchase.payment_status,
        "notes": purchase.notes,
        "date": purchase_date,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.purchases.update_one({"id": purchase_id}, {"$set": update_data})

    purchase_number = existing["purchase_number"]
    if purchase.payment_status == "cash":
        await create_ledger_entry("cash", 0, total, f"Purchase {purchase_number} (updated)", "purchase", purchase_id, purchase_date)
    elif purchase.payment_status == "bank":
        await create_ledger_entry("bank", 0, total, f"Purchase {purchase_number} (updated)", "purchase", purchase_id, purchase_date)
    elif purchase.payment_status == "unpaid" and purchase.supplier_id:
        await create_ledger_entry(f"supplier:{purchase.supplier_id}", 0, total, f"Purchase {purchase_number} (updated)", "purchase", purchase_id, purchase_date)

    # Debit Inventory Asset Account (consistent with create_purchase)
    await create_ledger_entry("inventory_asset", total, 0, f"Purchase {purchase_number} (updated)", "purchase", purchase_id, purchase_date)

    if purchase.supplier_id and purchase.payment_status == "unpaid" and purchase.apply_debit:
        await apply_debit_to_purchase(purchase.supplier_id, purchase_id, total)

    return {"message": "Purchase updated"}


@router.delete("/purchases/{purchase_id}")
async def delete_purchase(purchase_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.purchases.find_one({"id": purchase_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Purchase not found")

    await delete_stock_movements("purchase", purchase_id)
    await delete_ledger_entries("purchase", purchase_id)

    await db.purchases.delete_one({"id": purchase_id})
    return {"message": "Purchase deleted and effects reversed"}
