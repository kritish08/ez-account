"""Production orders (work orders).

Lifecycle: PLANNED → IN_PROGRESS → QC → COMPLETED, or CANCELLED from any
non-terminal state. Status transitions are atomic via `find_one_and_update`
with a status guard so two concurrent callers can't double-consume raw
materials or double-credit finished goods.

Stock side-effects flow through `services.stock.create_stock_movement`,
which also handles batch tracking and posts the matching COGS / inventory
ledger entries when ref_type is one of `PRODUCTION_CONSUMED` or
`PRODUCTION_OUTPUT`.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pymongo import ReturnDocument

from app.database import db
from app.deps import get_current_user
from app.schemas.production import ProductionOrderCreate
from app.services.counters import _next_seq
from app.services.stock import create_stock_movement, get_product_stock

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["production"])


@router.get("/production-orders")
async def list_production_orders(
    status: Optional[str] = None,
    product_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if status:
        query["status"] = status
    if product_id:
        query["product_id"] = product_id

    orders = await db.production_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(None)

    # Enrich with product names
    for o in orders:
        p = await db.products.find_one({"id": o["product_id"]}, {"_id": 0})
        o["product_name"] = p["name"] if p else "Unknown"

    return orders


@router.post("/production-orders")
async def create_production_order(order: ProductionOrderCreate, current_user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": order.product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    bom = await db.bill_of_materials.find_one({"product_id": order.product_id}, {"_id": 0})

    # Generate order number atomically (count_documents is racy and reuses
    # numbers when orders are deleted).
    order_number = f"WO-{str(await _next_seq('production_order')).zfill(4)}"

    # Calculate ingredients needed
    ingredients = []
    if bom:
        for comp in bom.get("components", []):
            ingredients.append({
                "material_id": comp["material_id"],
                "quantity_required": comp["quantity"] * order.quantity,
                "quantity_consumed": 0,
                "batch_id": None
            })

    order_doc = {
        "id": str(uuid.uuid4()),
        "order_number": order_number,
        "product_id": order.product_id,
        "bom_id": bom["id"] if bom and "id" in bom else None,
        "quantity": order.quantity,
        "batch_id": order.batch_id,
        "status": "PLANNED",
        "notes": order.notes or "",
        "planned_start_date": order.planned_start_date,
        "started_at": None,
        "completed_at": None,
        "ingredients": ingredients,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.get("email", "")
    }
    await db.production_orders.insert_one(order_doc)
    order_doc.pop("_id", None)
    return {"message": "Production order created", "order": order_doc}


@router.get("/production-orders/{order_id}")
async def get_production_order(order_id: str, current_user: dict = Depends(get_current_user)):
    order = await db.production_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Enrich
    p = await db.products.find_one({"id": order["product_id"]}, {"_id": 0})
    order["product_name"] = p["name"] if p else "Unknown"

    for ing in order.get("ingredients", []):
        mat = await db.products.find_one({"id": ing["material_id"]}, {"_id": 0})
        ing["material_name"] = mat["name"] if mat else "Unknown"
        ing["current_stock"] = await get_product_stock(ing["material_id"])

    return order


@router.put("/production-orders/{order_id}/start")
async def start_production_order(order_id: str, current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Atomically claim the PLANNED -> IN_PROGRESS transition so two concurrent
    # callers can't both consume the same raw materials.
    order = await db.production_orders.find_one_and_update(
        {"id": order_id, "status": "PLANNED"},
        {"$set": {"status": "IN_PROGRESS", "started_at": now_iso}},
        return_document=ReturnDocument.BEFORE,
    )
    if not order:
        existing = await db.production_orders.find_one({"id": order_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Order not found")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start order in status: {existing['status']}"
        )

    # Verify ALL ingredients sufficient before consuming any. If anything is
    # short, roll the status back so the user can retry after restocking.
    for ing in order.get("ingredients", []):
        available = await get_product_stock(ing["material_id"])
        if available < ing["quantity_required"]:
            mat = await db.products.find_one({"id": ing["material_id"]}, {"_id": 0})
            name = mat["name"] if mat else ing["material_id"]
            await db.production_orders.update_one(
                {"id": order_id},
                {"$set": {"status": "PLANNED"}, "$unset": {"started_at": ""}}
            )
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for '{name}': need {ing['quantity_required']}, have {round(available, 4)}"
            )

    # Consume — if anything below raises, leave the order IN_PROGRESS so an
    # operator can investigate rather than silently double-consuming on retry.
    for ing in order.get("ingredients", []):
        await create_stock_movement(
            product_id=ing["material_id"],
            quantity_in=0,
            quantity_out=ing["quantity_required"],
            ref_type="PRODUCTION_CONSUMED",
            ref_id=order_id,
            date=today,
            batch_id=ing.get("batch_id")
        )
        await db.production_orders.update_one(
            {"id": order_id, "ingredients.material_id": ing["material_id"]},
            {"$set": {"ingredients.$.quantity_consumed": ing["quantity_required"]}}
        )
    return {"message": "Production order started. Raw materials consumed from stock."}


@router.put("/production-orders/{order_id}/qc")
async def send_to_qc(order_id: str, current_user: dict = Depends(get_current_user)):
    """Move a started work order into QC review before final completion."""
    order = await db.production_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != "IN_PROGRESS":
        raise HTTPException(status_code=400, detail=f"Only IN_PROGRESS orders can be sent to QC (current: {order['status']})")
    await db.production_orders.update_one(
        {"id": order_id},
        {"$set": {"status": "QC", "qc_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Order moved to QC. Review and then mark as Completed."}


@router.put("/production-orders/{order_id}/complete")
async def complete_production_order(order_id: str, current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Atomically flip the status. If anyone else already completed/cancelled
    # this order (network retry, second tab), find_one_and_update returns None
    # so we don't double-credit finished goods.
    order = await db.production_orders.find_one_and_update(
        {"id": order_id, "status": {"$in": ["IN_PROGRESS", "QC"]}},
        {"$set": {"status": "COMPLETED", "completed_at": now_iso}},
        return_document=ReturnDocument.BEFORE,
    )
    if not order:
        existing = await db.production_orders.find_one({"id": order_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Order not found")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot complete order in status: {existing['status']}"
        )

    # Add finished goods to stock via canonical create_stock_movement.
    # If this fails after we've already flipped status, roll the status back
    # so the user can retry instead of being stuck in COMPLETED with no output.
    try:
        await create_stock_movement(
            product_id=order["product_id"],
            quantity_in=order["quantity"],
            quantity_out=0,
            ref_type="PRODUCTION_OUTPUT",
            ref_id=order_id,
            date=today,
            batch_id=order.get("batch_id")
        )
    except Exception as e:
        await db.production_orders.update_one(
            {"id": order_id},
            {"$set": {"status": order["status"]}, "$unset": {"completed_at": ""}}
        )
        logger.error(f"Rolled back production order {order_id} completion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record finished goods: {e}")

    # Batch record is now created inside `create_stock_movement` (gated on
    # `product.track_batches`). Doing it here too would double-count the
    # finished-good batch quantity.
    return {"message": f"Production order completed. {order['quantity']} units added to finished goods stock."}


@router.put("/production-orders/{order_id}/cancel")
async def cancel_production_order(order_id: str, current_user: dict = Depends(get_current_user)):
    order = await db.production_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] == "COMPLETED":
        raise HTTPException(status_code=400, detail="Cannot cancel a completed order")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Return already-consumed materials to stock
    if order["status"] in ["IN_PROGRESS", "QC"]:
        for ing in order.get("ingredients", []):
            consumed = ing.get("quantity_consumed", 0)
            if consumed > 0:
                await create_stock_movement(
                    product_id=ing["material_id"],
                    quantity_in=consumed,
                    quantity_out=0,
                    ref_type="PRODUCTION_RETURN",
                    ref_id=order["id"],
                    date=today,
                    batch_id=ing.get("batch_id")
                )

    await db.production_orders.update_one(
        {"id": order["id"]},
        {"$set": {"status": "CANCELLED", "cancelled_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Production order cancelled. Materials returned to stock."}
