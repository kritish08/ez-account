"""Product, stock-movement, batch and serial-number schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    hsn: Optional[str] = None
    # GST slab for this item. Copied onto the invoice line at billing
    # time so a later rate change doesn't retroactively alter issued
    # invoices. Ignored entirely when the GST module is off.
    gst_rate: float = Field(default=0, ge=0, le=100)
    unit: str = "pcs"
    category: Optional[str] = None
    item_type: str = "FINISHED_GOOD"  # RAW_MATERIAL | SEMI_FINISHED | FINISHED_GOOD | CONSUMABLE | SERVICE
    # All price/stock fields are non-negative. Free items (price=0) are
    # allowed; negative prices/stock are nonsense and would corrupt every
    # downstream report.
    selling_price: float = Field(..., ge=0)
    cost_price: float = Field(default=0, ge=0)
    stock_quantity: float = Field(default=0, ge=0)
    opening_stock: float = Field(default=0, ge=0)
    low_stock_threshold: float = Field(default=10, ge=0)
    reorder_point: float = Field(default=0, ge=0)
    track_batches: bool = False
    track_serials: bool = False


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    hsn: Optional[str] = None
    gst_rate: Optional[float] = Field(default=None, ge=0, le=100)
    unit: Optional[str] = None
    category: Optional[str] = None
    item_type: Optional[str] = None
    selling_price: Optional[float] = Field(default=None, ge=0)
    cost_price: Optional[float] = Field(default=None, ge=0)
    stock_quantity: Optional[float] = Field(default=None, ge=0)
    low_stock_threshold: Optional[float] = Field(default=None, ge=0)
    reorder_point: Optional[float] = Field(default=None, ge=0)
    track_batches: Optional[bool] = None
    track_serials: Optional[bool] = None


class StockMovementCreate(BaseModel):
    product_id: str
    quantity: float  # Positive for IN, Negative for OUT
    type: str  # 'SALE', 'PURCHASE', 'ADJUSTMENT', 'RETURN'
    source_id: Optional[str] = None  # Invoice ID, Purchase ID, etc.
    notes: Optional[str] = None
    date: Optional[str] = None


class BatchCreate(BaseModel):
    product_id: str
    batch_number: str
    quantity: float
    manufacturing_date: Optional[str] = None
    expiry_date: Optional[str] = None


class SerialNumberCreate(BaseModel):
    product_id: str
    batch_id: Optional[str] = None
    serial_number: str
    status: str = "IN_STOCK"  # IN_STOCK, SOLD, LOST
