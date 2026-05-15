"""CSV / Excel exports of the operational reports.

Each export endpoint calls the matching report endpoint from
`app.routers.reports`, then formats the result as either CSV or XLSX.
`io`, `csv`, and `openpyxl.Workbook` are inlined inside the helpers
(the previous inline implementation referenced them at module scope
without ever importing them, so every export call 500'd).
"""

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from app.routers.reports import (
    report_credit, report_expenses, report_inventory, report_outstanding,
    report_profit, report_sales,
)

router = APIRouter(prefix="/api", tags=["exports"])


def _csv_response(data: list, filename: str, fieldnames: list) -> StreamingResponse:
    import csv  # noqa: PLC0415
    import io  # noqa: PLC0415

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(data)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def _excel_response(data: list, filename: str, headers: list) -> StreamingResponse:
    import io  # noqa: PLC0415

    from openpyxl import Workbook  # noqa: PLC0415

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in data:
        ws.append([row.get(h.lower().replace(" ", "_"), row.get(h, "")) for h in headers])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/outstanding")
async def export_outstanding(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_outstanding(current_user)
    data = report["report"]

    if format == "excel":
        return _excel_response(data, "outstanding_report.xlsx", ["customer_name", "phone", "outstanding"])
    return _csv_response(data, "outstanding_report.csv", ["customer_name", "phone", "outstanding"])


@router.get("/export/credit")
async def export_credit(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_credit(current_user)
    data = report["report"]

    if format == "excel":
        return _excel_response(data, "credit_report.xlsx", ["customer_name", "phone", "credit"])
    return _csv_response(data, "credit_report.csv", ["customer_name", "phone", "credit"])


@router.get("/export/sales")
async def export_sales(start_date: Optional[str] = None, end_date: Optional[str] = None, format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_sales(start_date, end_date, current_user)
    data = [{
        "invoice_number": inv["invoice_number"],
        "customer_name": inv["customer_name"],
        "date": inv["date"],
        "total": inv["total"],
        "paid_amount": inv.get("paid_amount", 0),
        "status": inv["status"]
    } for inv in report["invoices"]]

    if format == "excel":
        return _excel_response(data, "sales_report.xlsx", ["invoice_number", "customer_name", "date", "total", "paid_amount", "status"])
    return _csv_response(data, "sales_report.csv", ["invoice_number", "customer_name", "date", "total", "paid_amount", "status"])


@router.get("/export/expenses")
async def export_expenses(start_date: Optional[str] = None, end_date: Optional[str] = None, format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_expenses(start_date, end_date, current_user)
    data = report["expenses"]

    if format == "excel":
        return _excel_response(data, "expenses_report.xlsx", ["description", "category", "date", "amount", "mode"])
    return _csv_response(data, "expenses_report.csv", ["description", "category", "date", "amount", "mode"])


@router.get("/export/inventory")
async def export_inventory(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_inventory(current_user)
    data = report["report"]

    if format == "excel":
        return _excel_response(data, "inventory_report.xlsx", ["product_name", "sku", "current_stock", "cost_price", "selling_price", "value"])
    return _csv_response(data, "inventory_report.csv", ["product_name", "sku", "current_stock", "cost_price", "selling_price", "value"])


@router.get("/export/profit")
async def export_profit(start_date: Optional[str] = None, end_date: Optional[str] = None, format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_profit(start_date, end_date, current_user)
    data = [{
        "metric": "Total Sales",
        "value": report["total_sales"]
    }, {
        "metric": "Cost of Goods",
        "value": report["total_cost"]
    }, {
        "metric": "Gross Profit",
        "value": report["gross_profit"]
    }, {
        "metric": "Total Expenses",
        "value": report["total_expenses"]
    }, {
        "metric": "Net Profit",
        "value": report["net_profit"]
    }, {
        "metric": "Margin %",
        "value": report["margin_percent"]
    }]

    if format == "excel":
        return _excel_response(data, "profit_report.xlsx", ["metric", "value"])
    return _csv_response(data, "profit_report.csv", ["metric", "value"])
