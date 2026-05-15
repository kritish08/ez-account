"""Sales invoices — full CRUD + draft/publish lifecycle + PDF.

Drafts hold their books-impact until `/publish` (or an update that flips
them out of draft): no ledger, no stock, no credit-application. Once
published, the invoice posts:
- customer-AR debit (Account Receivable goes up)
- sales credit (revenue)
- per-line stock-out movements (with COGS/inventory pairing inside
  `services.stock.create_stock_movement`)
- optional auto-apply of available customer credit (`apply_credit=true`)

Edit and delete both refuse to operate on an invoice that has received
payments/credits — caller must reverse those first so cash never gets
orphaned (FIN-P0-3).

PDF generation uses reportlab and is imported inline at endpoint time
to keep this module light and to match the original layout.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.database import db
from app.deps import get_current_user
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate
from app.services.counters import get_next_invoice_number
from app.services.ledger import create_ledger_entry, delete_ledger_entries
from app.services.money import _money
from app.services.payments_apply import apply_credit_to_invoice
from app.services.stock import (
    create_stock_movement, delete_stock_movements,
    get_all_product_stock,
)

router = APIRouter(prefix="/api", tags=["invoices"])


@router.post("/invoices")
async def create_invoice(invoice: InvoiceCreate, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": invoice.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    invoice_id = str(uuid.uuid4())
    invoice_number = await get_next_invoice_number()
    invoice_date = invoice.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    items = []
    total = 0
    total_cost = 0
    stock_warnings = []

    # Batch-fetch every product referenced by a line item plus (for non-draft
    # invoices) the full stock map in one shot — was previously two queries
    # per line (find_one product + get_product_stock aggregation).
    line_product_ids = list({i.product_id for i in invoice.items if i.product_id})
    product_map: dict[str, dict] = {}
    if line_product_ids:
        async for p in db.products.find(
            {"id": {"$in": line_product_ids}},
            {"_id": 0, "id": 1, "name": 1, "cost_price": 1},
        ):
            product_map[p["id"]] = p
    stock_map = await get_all_product_stock() if not invoice.is_draft and line_product_ids else {}

    for item in invoice.items:
        amount = _money(item.quantity * item.rate)
        item_doc = {
            "product_id": item.product_id,
            "description": item.description,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amount
        }

        if item.product_id:
            product = product_map.get(item.product_id)
            if product:
                item_doc["cost_price"] = product.get("cost_price", 0)
                total_cost += _money(item.quantity * product.get("cost_price", 0))

                if not invoice.is_draft:
                    current_stock = stock_map.get(item.product_id, 0)
                    if current_stock < item.quantity:
                        stock_warnings.append({
                            "product": product["name"],
                            "current_stock": current_stock,
                            "required": item.quantity
                        })

        items.append(item_doc)
        total += amount

    invoice_doc = {
        "id": invoice_id,
        "invoice_number": invoice_number,
        "customer_id": invoice.customer_id,
        "customer_name": customer["name"],
        "items": items,
        "total": total,
        "total_cost": total_cost,
        "profit": total - total_cost,
        "paid_amount": 0,
        "credit_applied": 0,
        "status": "draft" if invoice.is_draft else "unpaid",
        "notes": invoice.notes,
        "date": invoice_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.invoices.insert_one(invoice_doc)

    credit_applied = 0
    amount_due = total

    if not invoice.is_draft:
        # Customer-AR debit + sales credit — independent accounts, gather.
        await asyncio.gather(
            create_ledger_entry(
                account=f"customer:{invoice.customer_id}",
                debit=total,
                credit=0,
                narration=f"Invoice {invoice_number}",
                ref_type="invoice",
                ref_id=invoice_id,
                date=invoice_date,
            ),
            create_ledger_entry(
                account="sales",
                debit=0,
                credit=total,
                narration=f"Invoice {invoice_number}",
                ref_type="invoice",
                ref_id=invoice_id,
                date=invoice_date,
            ),
        )

        # Reduce stock for product items
        for item in items:
            if item.get("product_id"):
                await create_stock_movement(
                    item["product_id"], 0, item["quantity"], "invoice", invoice_id, invoice_date,
                    batch_id=item.get("batch_id"),
                    serial_numbers=item.get("serial_numbers")
                )

        # Auto-apply customer credit ONLY if requested
        if invoice.apply_credit:
            amount_due, credit_applied = await apply_credit_to_invoice(invoice.customer_id, invoice_id, total)

    response = {
        "message": "Invoice created",
        "id": invoice_id,
        "invoice_number": invoice_number,
        "amount_due": amount_due,
        "credit_applied": credit_applied
    }

    if stock_warnings:
        response["stock_warnings"] = stock_warnings
        response["warning_message"] = "Some items have low/negative stock"

    return response


@router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, invoice_update: InvoiceUpdate, current_user: dict = Depends(get_current_user)):
    """Update an invoice — handles both draft and published invoices."""
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Refuse to edit an invoice that has received any payment or credit.
    # The previous behaviour silently deleted payment_allocations and zeroed
    # paid_amount without touching the parent payment documents — money got
    # orphaned and AR inflated. To change a paid invoice the user must first
    # reverse the payments / credit notes that were applied to it.
    if existing.get("paid_amount", 0) > 0 or existing.get("credit_applied", 0) > 0 \
            or existing.get("credit_note_applied", 0) > 0 or existing.get("advance_payment_applied", 0) > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit an invoice that has payments or credits applied. "
                   "Delete the payments / credit-note applications first, then edit."
        )

    invoice_date = invoice_update.date or existing["date"]
    is_draft = existing["status"] == "draft"

    # Reverse previous entries if not a draft
    if not is_draft:
        await delete_ledger_entries("invoice", invoice_id)
        await delete_ledger_entries("invoice_credit", invoice_id)
        await delete_stock_movements("invoice", invoice_id)

        # Reset payment allocations that applied credit
        await db.payment_allocations.delete_many({"invoice_id": invoice_id})
        await db.invoices.update_one({"id": invoice_id}, {"$set": {"credit_applied": 0, "paid_amount": 0}})

    items = []
    total = 0
    total_cost = 0
    stock_warnings = []

    # Batch product + stock lookups (see create_invoice for context).
    line_product_ids = list({i.product_id for i in invoice_update.items if i.product_id})
    product_map: dict[str, dict] = {}
    if line_product_ids:
        async for p in db.products.find(
            {"id": {"$in": line_product_ids}},
            {"_id": 0, "id": 1, "name": 1, "cost_price": 1},
        ):
            product_map[p["id"]] = p
    stock_map = await get_all_product_stock() if not is_draft and line_product_ids else {}

    for item in invoice_update.items:
        amount = _money(item.quantity * item.rate)
        item_doc = {
            "product_id": item.product_id,
            "description": item.description,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amount
        }

        if item.product_id:
            product = product_map.get(item.product_id)
            if product:
                item_doc["cost_price"] = product.get("cost_price", 0)
                total_cost += _money(item.quantity * product.get("cost_price", 0))

                if not is_draft:
                    current_stock = stock_map.get(item.product_id, 0)
                    if current_stock < item.quantity:
                        stock_warnings.append({
                            "product": product["name"],
                            "current_stock": current_stock,
                            "required": item.quantity
                        })

        items.append(item_doc)
        total += amount

    update_data = {
        "items": items,
        "total": total,
        "total_cost": total_cost,
        "profit": total - total_cost,
        "notes": invoice_update.notes,
        "date": invoice_date,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    credit_applied = 0
    amount_due = total

    if not is_draft:
        # Customer-AR debit + sales credit — independent accounts, gather.
        await asyncio.gather(
            create_ledger_entry(
                account=f"customer:{existing['customer_id']}",
                debit=total,
                credit=0,
                narration=f"Invoice {existing['invoice_number']} (updated)",
                ref_type="invoice",
                ref_id=invoice_id,
                date=invoice_date,
            ),
            create_ledger_entry(
                account="sales",
                debit=0,
                credit=total,
                narration=f"Invoice {existing['invoice_number']} (updated)",
                ref_type="invoice",
                ref_id=invoice_id,
                date=invoice_date,
            ),
        )

        for item in items:
            if item.get("product_id"):
                await create_stock_movement(
                    item["product_id"], 0, item["quantity"], "invoice", invoice_id, invoice_date,
                    batch_id=item.get("batch_id"),
                    serial_numbers=item.get("serial_numbers")
                )

        if invoice_update.apply_credit:
            amount_due, credit_applied = await apply_credit_to_invoice(existing["customer_id"], invoice_id, total)

        # Recalculate status based on payments received
        allocations = await db.payment_allocations.find({"invoice_id": invoice_id}, {"_id": 0}).to_list(None)
        payment_received = sum(a["amount"] for a in allocations)
        total_paid = payment_received + credit_applied

        if total_paid >= total:
            update_data["status"] = "paid"
            update_data["paid_amount"] = total
        elif total_paid > 0:
            update_data["status"] = "partially_paid"
            update_data["paid_amount"] = total_paid
        else:
            update_data["status"] = "unpaid"
            update_data["paid_amount"] = credit_applied

    await db.invoices.update_one({"id": invoice_id}, {"$set": update_data})

    response = {
        "message": "Invoice updated",
        "id": invoice_id,
        "amount_due": amount_due,
        "credit_applied": credit_applied
    }

    if stock_warnings:
        response["stock_warnings"] = stock_warnings
        response["warning_message"] = "Some items have low/negative stock"

    return response


@router.post("/invoices/{invoice_id}/publish")
async def publish_invoice(invoice_id: str, apply_credit: bool = False, current_user: dict = Depends(get_current_user)):
    """Publish a draft invoice."""
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice["status"] != "draft":
        raise HTTPException(status_code=400, detail="Invoice is not a draft")

    invoice_date = invoice["date"]

    # Customer-AR debit + sales credit — gather.
    await asyncio.gather(
        create_ledger_entry(
            account=f"customer:{invoice['customer_id']}",
            debit=invoice["total"],
            credit=0,
            narration=f"Invoice {invoice['invoice_number']}",
            ref_type="invoice",
            ref_id=invoice_id,
            date=invoice_date,
        ),
        create_ledger_entry(
            account="sales",
            debit=0,
            credit=invoice["total"],
            narration=f"Invoice {invoice['invoice_number']}",
            ref_type="invoice",
            ref_id=invoice_id,
            date=invoice_date,
        ),
    )

    # Batch product + stock lookups, then iterate. Was previously
    # get_product_stock + find_one per item.
    line_product_ids = list({i["product_id"] for i in invoice["items"] if i.get("product_id")})
    name_map: dict[str, str] = {}
    if line_product_ids:
        async for p in db.products.find(
            {"id": {"$in": line_product_ids}},
            {"_id": 0, "id": 1, "name": 1},
        ):
            name_map[p["id"]] = p["name"]
    stock_map = await get_all_product_stock() if line_product_ids else {}

    stock_warnings = []
    for item in invoice["items"]:
        if item.get("product_id"):
            current_stock = stock_map.get(item["product_id"], 0)
            if current_stock < item["quantity"]:
                stock_warnings.append({
                    "product": name_map.get(item["product_id"], item["description"]),
                    "current_stock": current_stock,
                    "required": item["quantity"]
                })
            await create_stock_movement(
                item["product_id"], 0, item["quantity"], "invoice", invoice_id, invoice_date,
                batch_id=item.get("batch_id"),
                serial_numbers=item.get("serial_numbers")
            )

    amount_due = invoice["total"]
    credit_applied = 0

    if apply_credit:
        amount_due, credit_applied = await apply_credit_to_invoice(invoice["customer_id"], invoice_id, invoice["total"])

    new_status = "paid" if amount_due <= 0 else ("partially_paid" if credit_applied > 0 else "unpaid")
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"status": new_status, "credit_applied": credit_applied, "paid_amount": credit_applied}}
    )

    response = {
        "message": "Invoice published",
        "amount_due": amount_due,
        "credit_applied": credit_applied
    }

    if stock_warnings:
        response["stock_warnings"] = stock_warnings
        response["warning_message"] = "Some items have low/negative stock"

    return response


@router.get("/invoices")
async def list_invoices(
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    customer_id: Optional[str] = None,
    credit_applied_only: bool = False,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if status:
        query["status"] = status
    if customer_id:
        query["customer_id"] = customer_id
    if credit_applied_only:
        query["credit_applied"] = {"$gt": 0}

    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}

    invoices = await db.invoices.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    return invoices


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, current_user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(invoice_id: str, current_user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # customer + business are independent of each other — gather.
    customer, business = await asyncio.gather(
        db.customers.find_one({"id": invoice["customer_id"]}, {"_id": 0}),
        db.business.find_one({}, {"_id": 0}),
    )

    # reportlab + io are only needed here — import inline so the rest of the
    # router doesn't drag them in at import time.
    import io  # noqa: PLC0415

    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.lib.pagesizes import A4  # noqa: PLC0415
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: PLC0415
    from reportlab.platypus import (  # noqa: PLC0415
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#4338ca'), spaceAfter=20)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#64748b'), spaceAfter=10)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#0f172a'))

    business_name = business.get('name', 'Your Business') if business else 'Your Business'
    elements.append(Paragraph(business_name, title_style))

    if business:
        if business.get('address'):
            elements.append(Paragraph(business['address'], normal_style))
        contact_parts = []
        if business.get('phone'):
            contact_parts.append(f"Phone: {business['phone']}")
        if business.get('email'):
            contact_parts.append(f"Email: {business['email']}")
        if contact_parts:
            elements.append(Paragraph(" | ".join(contact_parts), normal_style))
        if business.get('gstin'):
            elements.append(Paragraph(f"GSTIN: {business['gstin']}", normal_style))

    elements.append(Spacer(1, 20))

    status_text = invoice['status'].replace('_', ' ').title()
    if invoice['status'] == 'draft':
        status_text = "DRAFT"
    elements.append(Paragraph(f"INVOICE: {invoice['invoice_number']}", ParagraphStyle('InvNum', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#0f172a'))))
    elements.append(Paragraph(f"Date: {invoice['date']}", normal_style))
    elements.append(Paragraph(f"Status: {status_text}", normal_style))

    elements.append(Spacer(1, 20))

    elements.append(Paragraph("BILL TO", heading_style))
    customer_name = customer.get('name', invoice['customer_name']) if customer else invoice['customer_name']
    elements.append(Paragraph(f"<b>{customer_name}</b>", normal_style))
    if customer:
        if customer.get('address'):
            elements.append(Paragraph(customer['address'], normal_style))
        if customer.get('phone'):
            elements.append(Paragraph(f"Phone: {customer['phone']}", normal_style))
        if customer.get('gstin'):
            elements.append(Paragraph(f"GSTIN: {customer['gstin']}", normal_style))

    elements.append(Spacer(1, 20))

    table_data = [['Description', 'Qty', 'Rate', 'Amount']]
    for item in invoice['items']:
        table_data.append([
            item['description'],
            str(item['quantity']),
            f"₹ {item['rate']:,.2f}",
            f"₹ {item['amount']:,.2f}"
        ])

    table = Table(table_data, colWidths=[250, 60, 100, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#64748b')),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(table)

    elements.append(Spacer(1, 20))

    totals_data = [['Subtotal', f"₹ {invoice['total']:,.2f}"]]
    if invoice.get('credit_applied', 0) > 0:
        totals_data.append(['Credit Applied', f"- ₹ {invoice['credit_applied']:,.2f}"])
    if invoice.get('paid_amount', 0) > 0:
        totals_data.append(['Paid', f"₹ {invoice['paid_amount']:,.2f}"])
    balance_due = invoice['total'] - invoice.get('paid_amount', 0)
    totals_data.append(['Balance Due', f"₹ {balance_due:,.2f}"])

    totals_table = Table(totals_data, colWidths=[400, 110])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (1, -1), (1, -1), colors.HexColor('#4338ca')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#4338ca')),
    ]))
    elements.append(totals_table)

    if invoice.get('notes'):
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("Notes", heading_style))
        elements.append(Paragraph(invoice['notes'], normal_style))

    doc.build(elements)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Invoice-{invoice['invoice_number']}.pdf"}
    )


@router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, current_user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Refuse to delete an invoice that received payments or credits.
    # Previous code had a no-op placeholder that left payment money orphaned
    # (referenced no invoice) — AR/cash drifted apart with no way to reconcile.
    if invoice.get("paid_amount", 0) > 0 or invoice.get("credit_applied", 0) > 0 \
            or invoice.get("credit_note_applied", 0) > 0 or invoice.get("advance_payment_applied", 0) > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete an invoice with payments or credits applied. "
                   "Delete the payments / credit-note applications first."
        )

    # If published (not draft), reverse all effects. Each delete acts on a
    # different collection (or different ref_type within ledger) so they're
    # independent — gather to overlap the round-trips.
    #
    # We do NOT delete the parent payment — a payment may have been split
    # across multiple invoices via FIFO. Deleting the payment would corrupt
    # all other invoices it was applied to. Just clean up allocation rows.
    if invoice["status"] != "draft":
        await asyncio.gather(
            delete_stock_movements("invoice", invoice_id),
            delete_ledger_entries("invoice", invoice_id),
            delete_ledger_entries("invoice_credit", invoice_id),
            db.payment_allocations.delete_many({"invoice_id": invoice_id}),
        )

    await db.invoices.delete_one({"id": invoice_id})
    return {"message": "Invoice deleted and all effects reversed"}
