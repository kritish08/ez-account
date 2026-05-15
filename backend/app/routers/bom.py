"""Bill of Materials.

Routes live under `/api/products/{product_id}/bom` for backward compatibility
with the existing frontend, but the persistence is the `bill_of_materials`
collection and BOMs are referenced by their own stable `id` from production
orders. Save is upsert + `$setOnInsert` so the id survives edits.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.bom import BOMCreate
from app.services.stock import get_all_product_stock

router = APIRouter(prefix="/api", tags=["bom"])


@router.get("/products/{product_id}/bom")
async def get_bom(product_id: str, current_user: dict = Depends(get_current_user)):
    bom = await db.bill_of_materials.find_one({"product_id": product_id}, {"_id": 0})
    if not bom:
        return {"bom": None}

    # Batch-fetch every component's product doc + the global stock map in
    # parallel. Was previously 2 round-trips per component (find_one product
    # + per-product stock aggregation).
    component_ids = list({c["material_id"] for c in bom.get("components", []) if c.get("material_id")})

    async def _component_map() -> dict[str, dict]:
        if not component_ids:
            return {}
        return {p["id"]: p async for p in db.products.find(
            {"id": {"$in": component_ids}},
            {"_id": 0, "id": 1, "name": 1, "unit": 1},
        )}

    component_map, stock_map = await asyncio.gather(_component_map(), get_all_product_stock())

    enriched = []
    for comp in bom.get("components", []):
        mat = component_map.get(comp["material_id"])
        stock = stock_map.get(comp["material_id"], 0)
        required = comp["quantity"]
        enriched.append({
            **comp,
            "material_name": mat["name"] if mat else "Unknown",
            "material_unit": mat.get("unit", "pcs") if mat else "pcs",
            "current_stock": stock,
            "sufficient": stock >= required,
        })
    bom["components"] = enriched
    return {"bom": bom}


@router.post("/products/{product_id}/bom")
async def save_bom(product_id: str, bom_data: BOMCreate, current_user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Reject self-reference. A product cannot consume itself as a component:
    # this would cause infinite recursion in any future multi-level BOM expansion
    # and is always a user error.
    seen = set()
    for c in bom_data.components:
        if c.material_id == product_id:
            raise HTTPException(
                status_code=400,
                detail="A product cannot include itself as a BOM component."
            )
        if c.material_id in seen:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate component '{c.material_id}' in BOM. Combine the quantities into one line."
            )
        seen.add(c.material_id)

    # Use $setOnInsert for the id + created_at so an existing BOM keeps its
    # stable id across edits. Production orders reference this id; without
    # a stable id, `bom_id` was always None on every order.
    bom_set = {
        "product_id": product_id,
        "version": bom_data.version,
        "components": [c.model_dump() for c in bom_data.components],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    bom_on_insert = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bill_of_materials.update_one(
        {"product_id": product_id},
        {"$set": bom_set, "$setOnInsert": bom_on_insert},
        upsert=True,
    )
    return {"message": "BOM saved successfully"}
