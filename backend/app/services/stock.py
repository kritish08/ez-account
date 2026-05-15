"""Stock-movement helpers.

`create_stock_movement` is the single chokepoint for every inventory
change — purchases, invoices, production orders, debit/credit notes,
manual adjustments. It writes the movement, posts the matching COGS /
inventory-asset ledger pair when applicable, and (when Advanced IMS is
on) maintains batch quantities and serial-number statuses.

See IMS-BATCH-FROM-PURCHASE and SN-BATCH-UNIQUE in FIXES.md for the
correctness fixes wired in here.
"""

import uuid
from datetime import datetime, timezone

from app.database import db
from app.services.ledger import create_ledger_entry


async def get_product_stock(product_id: str) -> float:
    """Current stock = total_in - total_out across all stock_movements."""
    pipeline = [
        {"$match": {"product_id": product_id}},
        {"$group": {
            "_id": None,
            "total_in": {"$sum": "$quantity_in"},
            "total_out": {"$sum": "$quantity_out"},
        }},
    ]
    result = await db.stock_movements.aggregate(pipeline).to_list(1)
    if result:
        return result[0]["total_in"] - result[0]["total_out"]
    return 0


async def create_stock_movement(
    product_id: str,
    quantity_in: float,
    quantity_out: float,
    ref_type: str,
    ref_id: str,
    date: str = None,
    batch_id: str = None,
    serial_numbers: list = None,
):
    """Record a stock movement (and its ledger / batch / serial side effects)."""
    movement = {
        "id": str(uuid.uuid4()),
        "product_id": product_id,
        "quantity_in": quantity_in,
        "quantity_out": quantity_out,
        "ref_type": ref_type,
        "ref_id": ref_id,
        "batch_id": batch_id,
        "serial_numbers": serial_numbers or [],
        "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.stock_movements.insert_one(movement)

    # Outbound for a sale or production consumption → COGS + inventory asset.
    if quantity_out > 0 and ref_type in ["invoice", "PRODUCTION_CONSUMED"]:
        product = await db.products.find_one({"id": product_id}, {"_id": 0, "cost_price": 1})
        cost = quantity_out * product.get("cost_price", 0) if product else 0
        if cost > 0:
            entry_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await create_ledger_entry("cogs", cost, 0, f"COGS for {ref_type} {ref_id}", ref_type, ref_id, entry_date)
            await create_ledger_entry("inventory_asset", 0, cost, f"Inventory reduction for {ref_type} {ref_id}", ref_type, ref_id, entry_date)

    # Inbound for a sales return or production output → inventory asset back, COGS reversal.
    if quantity_in > 0 and ref_type in ["credit_note", "PRODUCTION_OUTPUT"]:
        product = await db.products.find_one({"id": product_id}, {"_id": 0, "cost_price": 1})
        cost = quantity_in * product.get("cost_price", 0) if product else 0
        if cost > 0:
            entry_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await create_ledger_entry("inventory_asset", cost, 0, f"Inventory capitalization for {ref_type} {ref_id}", ref_type, ref_id, entry_date)
            await create_ledger_entry("cogs", 0, cost, f"COGS offset for {ref_type} {ref_id}", ref_type, ref_id, entry_date)

    # Advanced IMS side-effects (batches + serial numbers).
    settings = await db.settings.find_one({"type": "modules"}) or {}
    if settings.get("enable_advanced_ims", False):
        product = await db.products.find_one({"id": product_id})
        if product:
            # Batch tracking — fires for ANY inbound stock movement with a
            # batch_id (purchases, production output, manual adjustments).
            if quantity_in > 0 and product.get("track_batches") and batch_id:
                await db.batches.update_one(
                    {"product_id": product_id, "batch_number": batch_id},
                    {
                        "$inc": {"quantity": quantity_in},
                        "$setOnInsert": {
                            "id": str(uuid.uuid4()),
                            "product_id": product_id,
                            "batch_number": batch_id,
                            "source": ref_type,
                            "source_id": ref_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    },
                    upsert=True,
                )
            if quantity_out > 0 and product.get("track_batches") and batch_id:
                await db.batches.update_one(
                    {"product_id": product_id, "batch_number": batch_id},
                    {"$inc": {"quantity": -quantity_out}},
                )

            if quantity_in > 0 and product.get("track_serials") and serial_numbers:
                for sn in serial_numbers:
                    await db.serial_numbers.insert_one({
                        "id": str(uuid.uuid4()),
                        "product_id": product_id,
                        "batch_id": batch_id,
                        "serial_number": sn,
                        "status": "IN_STOCK",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
            if quantity_out > 0 and product.get("track_serials") and serial_numbers:
                await db.serial_numbers.update_many(
                    {"serial_number": {"$in": serial_numbers}, "product_id": product_id},
                    {"$set": {"status": "SOLD"}},
                )
    return movement


async def delete_stock_movements(ref_type: str, ref_id: str):
    """Delete all stock movements that referenced the given source row."""
    await db.stock_movements.delete_many({"ref_type": ref_type, "ref_id": ref_id})
