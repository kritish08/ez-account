"""Product CRUD + sub-resources (stock movements, batches, serial numbers, labels).

`/products/{id}/bom` is intentionally not here — it lives under the BOM
router (Phase 2 batch 3) even though the URL is rooted at products,
because it operates on bill_of_materials docs, not on the product itself.

The `current_stock` and `is_low_stock` derived fields are computed via
`services.stock.get_product_stock` so any per-product list/detail call
reflects movements in real time.
"""

import base64
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.product import ProductCreate
from app.services.stock import create_stock_movement, get_all_product_stock, get_product_stock

router = APIRouter(prefix="/api", tags=["products"])


@router.post("/products")
async def create_product(product: ProductCreate, current_user: dict = Depends(get_current_user)):
    product_id = str(uuid.uuid4())
    product_doc = {
        "id": product_id,
        **product.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.products.insert_one(product_doc)

    # Create opening stock movement
    if product.opening_stock > 0:
        await create_stock_movement(product_id, product.opening_stock, 0, "opening", product_id)

    return {"message": "Product created", "id": product_id}


@router.get("/products")
async def list_products(
    item_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {}
    if item_type:
        # Support comma separated if multiple types needed
        types = [t.strip() for t in item_type.split(",")]
        query["item_type"] = {"$in": types} if len(types) > 1 else types[0]

    if search:
        # Case-insensitive match against name OR sku — used by the
        # SearchableProductSelect dropdown for fast type-to-find on
        # invoice / purchase / production-order line items.
        # `re.escape` so users can paste raw input without breaking the regex.
        import re as _re
        safe = _re.escape(search)
        query["$or"] = [
            {"name": {"$regex": safe, "$options": "i"}},
            {"sku":  {"$regex": safe, "$options": "i"}},
        ]

    cursor = db.products.find(query, {"_id": 0}).sort("name", 1)
    # When the dropdown calls us, it doesn't need every product — cap to 50.
    products = await cursor.to_list(limit if limit and limit > 0 else None)
    if not products:
        return []

    # Single stock-map aggregation instead of N per-product aggregations.
    # /products is hit on every page load that has a product picker.
    stock_map = await get_all_product_stock()
    for product in products:
        product["current_stock"] = stock_map.get(product["id"], 0)
        product["is_low_stock"] = product["current_stock"] < product.get("low_stock_threshold", 10)

    return products


@router.get("/products/{product_id}")
async def get_product(product_id: str, current_user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product["current_stock"] = await get_product_stock(product_id)
    product["is_low_stock"] = product["current_stock"] < product.get("low_stock_threshold", 10)
    return product


@router.put("/products/{product_id}")
async def update_product(product_id: str, product: ProductCreate, current_user: dict = Depends(get_current_user)):
    existing = await db.products.find_one({"id": product_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = product.model_dump()
    del update_data["opening_stock"]
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.products.update_one({"id": product_id}, {"$set": update_data})
    return {"message": "Product updated"}


@router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.products.find_one({"id": product_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check ALL dependencies. Previously only invoices and purchases were
    # checked; deleting a raw material referenced by a BOM or an in-flight
    # production order left orphan ingredient references and broke stock
    # deduction at /production-orders/{id}/start (looked up a now-deleted
    # product → silent failure).
    invoice_usage = await db.invoices.find_one({"items.product_id": product_id})
    if invoice_usage:
        raise HTTPException(status_code=400, detail="Cannot delete: product is used in invoices")
    purchase_usage = await db.purchases.find_one({"items.product_id": product_id})
    if purchase_usage:
        raise HTTPException(status_code=400, detail="Cannot delete: product is used in purchases")
    bom_usage = await db.bill_of_materials.find_one({"components.material_id": product_id})
    if bom_usage:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete: product is a component of a Bill of Materials. "
                   "Remove it from the BOM first."
        )
    po_usage = await db.production_orders.find_one({
        "ingredients.material_id": product_id,
        "status": {"$in": ["PLANNED", "IN_PROGRESS", "QC"]},
    })
    if po_usage:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: product is referenced by an active production order "
                   f"({po_usage.get('order_number', po_usage.get('id'))})."
        )

    # Remove stock movements and the product
    await db.stock_movements.delete_many({"product_id": product_id})
    await db.products.delete_one({"id": product_id})
    return {"message": "Product deleted"}


@router.get("/products/{product_id}/stock-movements")
async def get_product_stock_movements(product_id: str, current_user: dict = Depends(get_current_user)):
    movements = await db.stock_movements.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(None)
    return movements


@router.get("/products/{product_id}/batches")
async def get_product_batches(product_id: str, current_user: dict = Depends(get_current_user)):
    batches = await db.batches.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(None)
    return batches


@router.get("/products/{product_id}/serial-numbers")
async def get_product_serial_numbers(product_id: str, current_user: dict = Depends(get_current_user)):
    serials = await db.serial_numbers.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(None)
    return serials


@router.get("/products/{product_id}/labels")
async def generate_product_labels(
    product_id: str,
    batch_id: Optional[str] = None,
    serial_numbers: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # qrcode is only needed for this endpoint — keep the import inline so the
    # rest of the routes don't drag it in at import time.
    import qrcode  # noqa: PLC0415

    serials_list = []
    if serial_numbers:
        serials_list = [s.strip() for s in serial_numbers.split(",") if s.strip()]

    # If no specific serials requested but batch is, or just product
    if not serials_list:
        serials_list = [""]

    labels = []
    for sn in serials_list:
        payload = f"EZ|PRD:{product_id}"
        if batch_id:
            payload += f"|BAT:{batch_id}"
        if sn:
            payload += f"|SER:{sn}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        labels.append({
            "payload": payload,
            "serial_number": sn or None,
            "batch_id": batch_id,
            "qr_code": f"data:image/png;base64,{img_str}"
        })

    return {"labels": labels}
