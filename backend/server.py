import os
import sys
import shutil
import uuid
import json
import base64
import secrets
import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, APIRouter, Header, Query, Request, status, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from pydantic import BaseModel, Field, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, DESCENDING
from jose import jwt, JWTError
import bcrypt
import boto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv

# Internal imports
from services.ai_service import parse_invoice_image

# Load environment variables
load_dotenv()

# Configuration
MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "BlitzerDB")
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
MASTER_ENCRYPTION_KEY = os.getenv("MASTER_ENCRYPTION_KEY")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Setup
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server starting up...")
    
    # Create compound indexes for production queries
    try:
        await db.ledger.create_index([("account", ASCENDING), ("date", DESCENDING)])
        await db.stock_movements.create_index([("product_id", ASCENDING), ("date", DESCENDING)])
        await db.invoices.create_index([("customer_id", ASCENDING), ("status", ASCENDING), ("date", DESCENDING)])
        await db.production_orders.create_index([("status", ASCENDING), ("product_id", ASCENDING)])
        logger.info("MongoDB indexes verified/created.")
    except Exception as e:
        logger.warning(f"Failed to create indexes: {e}")
        
    yield
    logger.info("Server shutting down...")
    client.close()

app = FastAPI(title="EZ Accounts by Kyrex API", version="2.0.0", lifespan=lifespan)

# CORS
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth Scheme
security = HTTPBearer()

# Static Files
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=uploads_dir), name="uploads")

api_router = APIRouter(prefix="/api")

# ... existing code ...

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    hsn: Optional[str] = None
    unit: str = "pcs"
    category: Optional[str] = None
    item_type: str = "FINISHED_GOOD"  # RAW_MATERIAL | SEMI_FINISHED | FINISHED_GOOD | CONSUMABLE | SERVICE
    selling_price: float
    cost_price: float = 0
    stock_quantity: float = 0
    opening_stock: float = 0
    low_stock_threshold: float = 10
    reorder_point: float = 0
    track_batches: bool = False
    track_serials: bool = False

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    hsn: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    item_type: Optional[str] = None
    selling_price: Optional[float] = None
    cost_price: Optional[float] = None
    stock_quantity: Optional[float] = None
    low_stock_threshold: Optional[float] = None
    reorder_point: Optional[float] = None
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

class CustomerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    opening_balance: float = 0
    balance_type: Optional[str] = "debit"

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None

class SupplierCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    opening_balance: float = 0

class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class ModulesSettings(BaseModel):
    enable_credit_notes: bool = True
    enable_debit_notes: bool = True
    enable_advanced_ims: bool = False
    enable_production: bool = False

# BOM and Production Order schemas
class BOMComponent(BaseModel):
    material_id: str
    quantity: float
    unit: Optional[str] = None

class BOMCreate(BaseModel):
    version: str = "1.0"
    components: List[BOMComponent]

class ProductionOrderCreate(BaseModel):
    product_id: str
    quantity: float
    batch_id: Optional[str] = None
    notes: Optional[str] = None
    planned_start_date: Optional[str] = None

class ProductionOrderUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    batch_id: Optional[str] = None
    ingredient_overrides: Optional[List[dict]] = None  # [{material_id, batch_id}]

class TokenData(BaseModel):
    username: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class BusinessSetup(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    opening_cash: float = 0
    opening_bank: float = 0

class PurchaseItem(BaseModel):
    product_id: Optional[str] = None
    quantity: float
    cost_price: float
    batch_id: Optional[str] = None
    serial_numbers: Optional[List[str]] = None

class PurchaseCreate(BaseModel):
    supplier_id: Optional[str] = None
    items: List[PurchaseItem]
    payment_status: str = "unpaid"  # cash, bank, unpaid
    date: Optional[str] = None
    notes: Optional[str] = None
    attachment_url: Optional[str] = None
    apply_debit: bool = False

class PurchaseUpdate(BaseModel):
    supplier_id: Optional[str] = None
    items: List[PurchaseItem]
    payment_status: str = "unpaid"
    date: Optional[str] = None
    notes: Optional[str] = None
    attachment_url: Optional[str] = None
    apply_debit: bool = False

class InvoiceLineItem(BaseModel):
    product_id: Optional[str] = None  # None for free-text items
    description: str
    quantity: float
    rate: float
    batch_id: Optional[str] = None
    serial_numbers: Optional[List[str]] = None

class InvoiceCreate(BaseModel):
    customer_id: str
    items: List[InvoiceLineItem]
    notes: Optional[str] = None
    date: Optional[str] = None
    is_draft: bool = False
    attachment_url: Optional[str] = None
    apply_credit: bool = False

class InvoiceUpdate(BaseModel):
    items: List[InvoiceLineItem]
    notes: Optional[str] = None
    date: Optional[str] = None
    attachment_url: Optional[str] = None
    apply_credit: bool = False

class PaymentCreate(BaseModel):
    customer_id: str
    amount: float
    mode: str
    date: Optional[str] = None
    notes: Optional[str] = None
    use_credit: bool = False
    invoice_id: Optional[str] = None
    credit_note_id: Optional[str] = None  # CN to apply when recording payment
    advance_payment_id: Optional[str] = None # Advance Payment to apply

class PaymentUpdate(BaseModel):
    amount: float
    mode: str
    date: Optional[str] = None
    notes: Optional[str] = None

class ExpenseCreate(BaseModel):
    description: str
    amount: float
    mode: str
    category: Optional[str] = None
    date: Optional[str] = None
    attachment_url: Optional[str] = None

class ExpenseUpdate(BaseModel):
    description: str
    amount: float
    mode: str
    category: Optional[str] = None
    date: Optional[str] = None
    attachment_url: Optional[str] = None

class CreditNoteItem(BaseModel):
    product_id: Optional[str] = None
    description: str
    quantity: float
    rate: float

class CreditNoteCreate(BaseModel):
    customer_id: str
    invoice_id: Optional[str] = None
    items: List[CreditNoteItem]
    reason: Optional[str] = None
    date: Optional[str] = None

class CreditNoteUpdate(BaseModel):
    items: List[CreditNoteItem]
    reason: Optional[str] = None
    date: Optional[str] = None
    invoice_id: Optional[str] = None

class DebitNoteItem(BaseModel):
    product_id: str
    quantity: float
    cost_price: float

class DebitNoteCreate(BaseModel):
    supplier_id: str
    purchase_id: Optional[str] = None
    items: List[DebitNoteItem]
    reason: Optional[str] = None
    date: Optional[str] = None

class DebitNoteUpdate(BaseModel):
    items: List[DebitNoteItem]
    reason: Optional[str] = None
    date: Optional[str] = None
    purchase_id: Optional[str] = None

class S3Settings(BaseModel):
    aws_access_key_id: str
    aws_secret_access_key: str
    bucket_name: str
    region: str = "us-east-1"

class SystemSettings(BaseModel):
    registration_enabled: bool = False
    company_name: Optional[str] = None
    company_email: Optional[str] = None
    company_phone: Optional[str] = None
    company_address: Optional[str] = None
    tax_id: Optional[str] = None
    default_currency: Optional[str] = "₹"

# ============== AUTH HELPERS ==============

import bcrypt

# ============== AUTH HELPERS ==============

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user is None:
        raise credentials_exception
    return user

# ============== ENCRYPTION HELPERS ==============

def encrypt_data(data: bytes, mek: str) -> dict:
    """Encrypt data using envelope encryption (AES-256-GCM)"""
    # Generate a random DEK (Data Encryption Key)
    dek = secrets.token_bytes(32)  # 256-bit key
    nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
    
    # Encrypt data with DEK
    aesgcm = AESGCM(dek)
    encrypted_data = aesgcm.encrypt(nonce, data, None)
    
    # Encrypt DEK with MEK
    mek_bytes = bytes.fromhex(mek)
    mek_nonce = secrets.token_bytes(12)
    mek_aesgcm = AESGCM(mek_bytes)
    encrypted_dek = mek_aesgcm.encrypt(mek_nonce, dek, None)
    
    return {
        "encrypted_data": base64.b64encode(encrypted_data).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "encrypted_dek": base64.b64encode(encrypted_dek).decode(),
        "mek_nonce": base64.b64encode(mek_nonce).decode()
    }

def decrypt_data(encrypted_package: dict, mek: str) -> bytes:
    """Decrypt data using envelope encryption"""
    encrypted_data = base64.b64decode(encrypted_package["encrypted_data"])
    nonce = base64.b64decode(encrypted_package["nonce"])
    encrypted_dek = base64.b64decode(encrypted_package["encrypted_dek"])
    mek_nonce = base64.b64decode(encrypted_package["mek_nonce"])
    
    # Decrypt DEK with MEK
    mek_bytes = bytes.fromhex(mek)
    mek_aesgcm = AESGCM(mek_bytes)
    dek = mek_aesgcm.decrypt(mek_nonce, encrypted_dek, None)
    
    # Decrypt data with DEK
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, encrypted_data, None)

# ============== LEDGER HELPERS ==============

async def create_ledger_entry(account: str, debit: float, credit: float, narration: str, ref_type: str, ref_id: str, date: str = None):
    """Create a double-entry ledger record"""
    entry = {
        "id": str(uuid.uuid4()),
        "account": account,
        "debit": debit,
        "credit": credit,
        "narration": narration,
        "ref_type": ref_type,
        "ref_id": ref_id,
        "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.ledger.insert_one(entry)
    return entry

async def delete_ledger_entries(ref_type: str, ref_id: str):
    """Delete all ledger entries for a reference"""
    await db.ledger.delete_many({"ref_type": ref_type, "ref_id": ref_id})

async def get_account_balance(account: str) -> float:
    """Get current balance for an account (debits - credits)"""
    pipeline = [
        {"$match": {"account": account}},
        {"$group": {"_id": None, "total_debit": {"$sum": "$debit"}, "total_credit": {"$sum": "$credit"}}}
    ]
    result = await db.ledger.aggregate(pipeline).to_list(1)
    if result:
        return result[0]["total_debit"] - result[0]["total_credit"]
    return 0

async def get_next_invoice_number() -> str:
    """Generate next invoice number"""
    last_invoice = await db.invoices.find_one({"invoice_number": {"$regex": "^INV-"}}, {"_id": 0, "invoice_number": 1}, sort=[("invoice_number", -1)])
    if last_invoice:
        try:
            last_num = int(last_invoice["invoice_number"].replace("INV-", ""))
            return f"INV-{str(last_num + 1).zfill(5)}"
        except:
            pass
    return "INV-00001"

async def get_next_purchase_number() -> str:
    """Generate next purchase number"""
    last_purchase = await db.purchases.find_one({}, {"_id": 0, "purchase_number": 1}, sort=[("purchase_number", -1)])
    if last_purchase:
        try:
            last_num = int(last_purchase["purchase_number"].replace("PUR-", ""))
            return f"PUR-{str(last_num + 1).zfill(5)}"
        except:
            pass
    return "PUR-00001"

async def apply_payment_fifo(customer_id: str, amount: float, payment_id: str):
    """Apply payment to oldest unpaid invoices first (FIFO)"""
    remaining = amount
    
    invoices = await db.invoices.find(
        {"customer_id": customer_id, "status": {"$nin": ["paid", "draft"]}},
        {"_id": 0}
    ).sort("date", 1).to_list(1000)
    
    for invoice in invoices:
        if remaining <= 0:
            break
        
        outstanding = invoice["total"] - invoice.get("paid_amount", 0)
        if outstanding <= 0:
            continue
        
        apply_amount = min(remaining, outstanding)
        new_paid = invoice.get("paid_amount", 0) + apply_amount
        new_status = "paid" if new_paid >= invoice["total"] else "partially_paid"
        
        await db.invoices.update_one(
            {"id": invoice["id"]},
            {"$set": {"paid_amount": new_paid, "status": new_status}}
        )
        
        await db.payment_allocations.insert_one({
            "id": str(uuid.uuid4()),
            "payment_id": payment_id,
            "invoice_id": invoice["id"],
            "amount": apply_amount,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        remaining -= apply_amount
    
    return remaining

async def get_customer_credit(customer_id: str) -> float:
    """Get customer's available credit from Credit Notes (single source of truth)."""
    pipeline = [
        {"$match": {"customer_id": customer_id, "total": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}}
    ]
    result = await db.credit_notes.aggregate(pipeline).to_list(1)
    if result:
        return round(result[0]["total"], 2)
    return 0.0


async def apply_debit_to_purchase(supplier_id: str, purchase_id: str, purchase_total: float) -> tuple:
    """
    Calculate usage of Supplier Debit/Advance using Single Account logic.
    Returns (amount_due, debit_applied).
    """
    # 1. Get current balance (Post-Purchase-Entry)
    # Supplier Account: Credit = Payable (Liability), Debit = Advance (Asset)
    # Balance = Debits - Credits.
    # If Balance < 0, we owe money (Payable).
    current_balance = await get_account_balance(f"supplier:{supplier_id}")
    
    # 2. Calculate Pre-Transaction Balance to find what was available BEFORE this purchase
    # Purchase Entry was: Cr Supplier (credit += purchase_total)
    # So Balance DECREASED by purchase_total.
    # pre_balance = current_balance + purchase_total
    # Example: 
    #   Open: Dr 500 (Advance). Bal = 500.
    #   Purchase: Cr 200.
    #   Current Bal = 500 - 200 = 300.
    #   Pre Bal = 300 + 200 = 500. (Correct)
    
    # Example 2:
    #   Open: Dr 100.
    #   Purchase: Cr 300.
    #   Current Bal = 100 - 300 = -200 (Payable).
    #   Pre Bal = -200 + 300 = 100. (Available Advance)
    
    pre_balance = current_balance + purchase_total
    
    # 3. Determine Available Debit (Advance)
    available_debit = max(0, pre_balance)
    
    # 4. Calculate Applied Amount
    debit_applied = min(available_debit, purchase_total)
    
    # 5. Determine New Status
    amount_due = purchase_total - debit_applied
    
    if amount_due <= 0:
        new_status = "paid"
    elif amount_due < purchase_total:
        new_status = "partially_paid"
    else:
        new_status = "unpaid"
            
    # 6. Update Purchase Record
    await db.purchases.update_one(
        {"id": purchase_id},
        {"$set": {
            "payment_status": new_status, 
            "debit_used": debit_applied,
            "amount_due": amount_due
        }}
    )
    
    return amount_due, debit_applied

async def apply_credit_to_invoice(customer_id: str, invoice_id: str, invoice_total: float) -> tuple:
    """
    Apply available ledger credit to invoice.
    Returns (amount_due, credit_applied).
    """
    current_balance = await get_account_balance(f"customer:{customer_id}")
    pre_balance = current_balance - invoice_total
    available_credit = max(0, -pre_balance)
    
    if available_credit <= 0:
        return invoice_total, 0
    
    allocations = await db.payment_allocations.find({"invoice_id": invoice_id}).to_list(1000)
    cash_paid = sum(a["amount"] for a in allocations)
    needed_amount = max(0, invoice_total - cash_paid)
    credit_applied = min(available_credit, needed_amount)
    
    total_paid = cash_paid + credit_applied
    amount_due = invoice_total - total_paid
    new_status = "paid" if amount_due <= 0 else "partially_paid"
    
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "paid_amount": total_paid, 
            "status": new_status, 
            "credit_applied": credit_applied
        }}
    )
    
    return amount_due, credit_applied


async def apply_credit_note_to_invoice(credit_note_id: str, invoice_id: str) -> float:
    """
    Apply a Credit Note to an invoice.
    Reduces CN total, updates invoice paid_amount, creates ledger entries.
    Returns amount applied.
    """
    cn = await db.credit_notes.find_one({"id": credit_note_id})
    if not cn or cn["total"] <= 0:
        return 0

    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        return 0

    invoice_due = invoice["total"] - invoice.get("paid_amount", 0)
    if invoice_due <= 0:
        return 0

    apply_amount = round(min(cn["total"], invoice_due), 2)
    new_cn_total = round(cn["total"] - apply_amount, 2)
    new_paid = round(invoice.get("paid_amount", 0) + apply_amount, 2)
    new_status = "paid" if new_paid >= invoice["total"] else "partially_paid"

    # Update Credit Note balance
    await db.credit_notes.update_one(
        {"id": credit_note_id},
        {"$set": {"total": new_cn_total}}
    )

    # Update Invoice
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"paid_amount": new_paid, "status": new_status,
                  "credit_note_applied": invoice.get("credit_note_applied", 0) + apply_amount}}
    )

    # No ledger entry needed here! The customer ledger was already credited 
    # when the Credit Note was first generated.

    return apply_amount

async def apply_advance_payment_to_invoice(advance_payment_id: str, invoice_id: str) -> float:
    """
    Apply an Advance Payment to an invoice.
    Reduces remaining_amount, updates invoice paid_amount, creates ledger entries.
    """
    adv = await db.advance_payments.find_one({"id": advance_payment_id})
    if not adv or adv.get("remaining_amount", 0) <= 0:
        return 0

    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        return 0

    invoice_due = invoice["total"] - invoice.get("paid_amount", 0)
    if invoice_due <= 0:
        return 0

    apply_amount = round(min(adv["remaining_amount"], invoice_due), 2)
    new_adv_remaining = round(adv["remaining_amount"] - apply_amount, 2)
    new_paid = round(invoice.get("paid_amount", 0) + apply_amount, 2)
    new_status = "paid" if new_paid >= invoice["total"] else "partially_paid"

    # Update Advance Payment balance
    await db.advance_payments.update_one(
        {"id": advance_payment_id},
        {"$set": {"remaining_amount": new_adv_remaining}}
    )

    # Update Invoice
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"paid_amount": new_paid, "status": new_status,
                  "advance_payment_applied": invoice.get("advance_payment_applied", 0) + apply_amount}}
    )

    # Link the original payment to this invoice for rollback support
    await db.payment_allocations.insert_one({
        "id": str(uuid.uuid4()),
        "payment_id": adv["payment_id"],
        "invoice_id": invoice_id,
        "amount": apply_amount,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # No ledger entry needed here! The customer ledger was already credited 
    # when the Advance Payment was first recorded (cash received).
    
    return apply_amount

# ============== STOCK HELPERS ==============

async def get_product_stock(product_id: str) -> float:
    """Calculate current stock from movements"""
    pipeline = [
        {"$match": {"product_id": product_id}},
        {"$group": {"_id": None, "total_in": {"$sum": "$quantity_in"}, "total_out": {"$sum": "$quantity_out"}}}
    ]
    result = await db.stock_movements.aggregate(pipeline).to_list(1)
    if result:
        return result[0]["total_in"] - result[0]["total_out"]
    return 0

async def create_stock_movement(product_id: str, quantity_in: float, quantity_out: float, ref_type: str, ref_id: str, date: str = None, batch_id: str = None, serial_numbers: list = None):
    """Record stock movement"""
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
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.stock_movements.insert_one(movement)

    if quantity_out > 0 and ref_type in ["invoice", "PRODUCTION_CONSUMED"]:
        product = await db.products.find_one({"id": product_id}, {"_id": 0, "cost_price": 1})
        cost = quantity_out * product.get("cost_price", 0) if product else 0
        if cost > 0:
            await create_ledger_entry(
                account="cogs",
                debit=cost,
                credit=0,
                narration=f"COGS for {ref_type} {ref_id}",
                ref_type=ref_type,
                ref_id=ref_id,
                date=date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )
            await create_ledger_entry(
                account="inventory_asset",
                debit=0,
                credit=cost,
                narration=f"Inventory reduction for {ref_type} {ref_id}",
                ref_type=ref_type,
                ref_id=ref_id,
                date=date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )

    if quantity_in > 0 and ref_type in ["credit_note", "PRODUCTION_OUTPUT"]:
        product = await db.products.find_one({"id": product_id}, {"_id": 0, "cost_price": 1})
        cost = quantity_in * product.get("cost_price", 0) if product else 0
        if cost > 0:
            await create_ledger_entry(
                account="inventory_asset",
                debit=cost,
                credit=0,
                narration=f"Inventory capitalization for {ref_type} {ref_id}",
                ref_type=ref_type,
                ref_id=ref_id,
                date=date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )
            await create_ledger_entry(
                account="cogs",
                debit=0,
                credit=cost,
                narration=f"COGS offset for {ref_type} {ref_id}",
                ref_type=ref_type,
                ref_id=ref_id,
                date=date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )

    # Process Advanced IMS properties if enabled
    settings = await db.settings.find_one({"type": "modules"}) or {}
    if settings.get("enable_advanced_ims", False):
        product = await db.products.find_one({"id": product_id})
        if product:
            if quantity_in > 0 and product.get("track_serials") and serial_numbers:
                for sn in serial_numbers:
                    await db.serial_numbers.insert_one({
                        "id": str(uuid.uuid4()),
                        "product_id": product_id,
                        "batch_id": batch_id,
                        "serial_number": sn,
                        "status": "IN_STOCK",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    })
            if quantity_out > 0 and product.get("track_serials") and serial_numbers:
                await db.serial_numbers.update_many(
                    {"serial_number": {"$in": serial_numbers}, "product_id": product_id},
                    {"$set": {"status": "SOLD"}}
                )
    return movement

async def delete_stock_movements(ref_type: str, ref_id: str):
    """Delete all stock movements for a reference"""
    await db.stock_movements.delete_many({"ref_type": ref_type, "ref_id": ref_id})

# ============== AUTH ROUTES ==============

@api_router.post("/auth/login", response_model=Token)
async def login(user: UserLogin):
    db_user = await db.users.find_one({"email": user.email}, {"_id": 0})
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": db_user["id"]})
    return {"access_token": access_token, "token_type": "bearer"}

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["id"], "email": current_user["email"], "name": current_user["name"]}

# ============== BUSINESS SETUP ==============

@api_router.post("/business/setup")
async def setup_business(business: BusinessSetup, current_user: dict = Depends(get_current_user)):
    existing = await db.business.find_one({}, {"_id": 0})
    
    business_doc = {
        "id": str(uuid.uuid4()),
        **business.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if existing:
        await db.business.update_one({}, {"$set": business_doc})
    else:
        business_doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.business.insert_one(business_doc)
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if business.opening_cash > 0:
            await create_ledger_entry("cash", business.opening_cash, 0, "Opening cash balance", "setup", business_doc["id"], today)
            await create_ledger_entry("capital", 0, business.opening_cash, "Opening capital (cash)", "setup", business_doc["id"], today)
            
        if business.opening_bank > 0:
            await create_ledger_entry("bank", business.opening_bank, 0, "Opening bank balance", "setup", business_doc["id"], today)
            await create_ledger_entry("capital", 0, business.opening_bank, "Opening capital (bank)", "setup", business_doc["id"], today)
    
    return {"message": "Business setup complete", "id": business_doc["id"]}

@api_router.get("/business")
async def get_business(current_user: dict = Depends(get_current_user)):
    business = await db.business.find_one({}, {"_id": 0})
    return business

# ============== PRODUCTS ==============

@api_router.post("/products")
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

@api_router.get("/products")
async def list_products(item_type: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if item_type:
        # Support comma separated if multiple types needed
        types = [t.strip() for t in item_type.split(",")]
        query["item_type"] = {"$in": types} if len(types) > 1 else types[0]
        
    products = await db.products.find(query, {"_id": 0}).sort("name", 1).to_list(1000)
    
    for product in products:
        product["current_stock"] = await get_product_stock(product["id"])
        product["is_low_stock"] = product["current_stock"] < product.get("low_stock_threshold", 10)
    
    return products

@api_router.get("/products/{product_id}")
async def get_product(product_id: str, current_user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product["current_stock"] = await get_product_stock(product_id)
    product["is_low_stock"] = product["current_stock"] < product.get("low_stock_threshold", 10)
    return product

@api_router.put("/products/{product_id}")
async def update_product(product_id: str, product: ProductCreate, current_user: dict = Depends(get_current_user)):
    existing = await db.products.find_one({"id": product_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = product.model_dump()
    del update_data["opening_stock"]
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.products.update_one({"id": product_id}, {"$set": update_data})
    return {"message": "Product updated"}

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.products.find_one({"id": product_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check for usage in invoices or purchases
    invoice_usage = await db.invoices.find_one({"items.product_id": product_id})
    if invoice_usage:
        raise HTTPException(status_code=400, detail="Cannot delete: product is used in invoices")
    purchase_usage = await db.purchases.find_one({"items.product_id": product_id})
    if purchase_usage:
        raise HTTPException(status_code=400, detail="Cannot delete: product is used in purchases")
    
    # Remove stock movements and the product
    await db.stock_movements.delete_many({"product_id": product_id})
    await db.products.delete_one({"id": product_id})
    return {"message": "Product deleted"}

@api_router.get("/products/{product_id}/stock-movements")
async def get_product_stock_movements(product_id: str, current_user: dict = Depends(get_current_user)):
    movements = await db.stock_movements.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return movements

@api_router.get("/products/{product_id}/batches")
async def get_product_batches(product_id: str, current_user: dict = Depends(get_current_user)):
    batches = await db.batches.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return batches

@api_router.get("/products/{product_id}/serial-numbers")
async def get_product_serial_numbers(product_id: str, current_user: dict = Depends(get_current_user)):
    serials = await db.serial_numbers.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return serials

@api_router.get("/products/{product_id}/labels")
async def generate_product_labels(
    product_id: str,
    batch_id: Optional[str] = None,
    serial_numbers: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    import qrcode
    import base64
    from io import BytesIO
        
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

# ============== BILL OF MATERIALS ==============

@api_router.get("/products/{product_id}/bom")
async def get_bom(product_id: str, current_user: dict = Depends(get_current_user)):
    bom = await db.bill_of_materials.find_one({"product_id": product_id}, {"_id": 0})
    if not bom:
        return {"bom": None}
    
    # Enrich components with product info and current stock
    enriched = []
    for comp in bom.get("components", []):
        mat = await db.products.find_one({"id": comp["material_id"]}, {"_id": 0})
        stock = await get_product_stock(comp["material_id"])
        required = comp["quantity"]
        enriched.append({
            **comp,
            "material_name": mat["name"] if mat else "Unknown",
            "material_unit": mat.get("unit", "pcs") if mat else "pcs",
            "current_stock": stock,
            "sufficient": stock >= required
        })
    bom["components"] = enriched
    return {"bom": bom}

@api_router.post("/products/{product_id}/bom")
async def save_bom(product_id: str, bom_data: BOMCreate, current_user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    bom_doc = {
        "product_id": product_id,
        "version": bom_data.version,
        "components": [c.model_dump() for c in bom_data.components],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.bill_of_materials.update_one(
        {"product_id": product_id},
        {"$set": bom_doc},
        upsert=True
    )
    return {"message": "BOM saved successfully"}

# ============== PRODUCTION ORDERS ==============

@api_router.get("/production-orders")
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
    
    orders = await db.production_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    # Enrich with product names
    for o in orders:
        p = await db.products.find_one({"id": o["product_id"]}, {"_id": 0})
        o["product_name"] = p["name"] if p else "Unknown"
    
    return orders

@api_router.post("/production-orders")
async def create_production_order(order: ProductionOrderCreate, current_user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": order.product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    bom = await db.bill_of_materials.find_one({"product_id": order.product_id}, {"_id": 0})
    
    # Generate order number
    count = await db.production_orders.count_documents({})
    order_number = f"WO-{str(count + 1).zfill(4)}"
    
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

@api_router.get("/production-orders/{order_id}")
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

@api_router.put("/production-orders/{order_id}/start")
async def start_production_order(order_id: str, current_user: dict = Depends(get_current_user)):
    order = await db.production_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != "PLANNED":
        raise HTTPException(status_code=400, detail=f"Cannot start order in status: {order['status']}")
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Consume raw materials — verify ALL sufficient before touching any stock
    for ing in order.get("ingredients", []):
        available = await get_product_stock(ing["material_id"])
        if available < ing["quantity_required"]:
            mat = await db.products.find_one({"id": ing["material_id"]}, {"_id": 0})
            name = mat["name"] if mat else ing["material_id"]
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for '{name}': need {ing['quantity_required']}, have {round(available, 4)}"
            )

    # All materials sufficient — deduct via canonical create_stock_movement
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

    await db.production_orders.update_one(
        {"id": order_id},
        {"$set": {"status": "IN_PROGRESS", "started_at": now_iso}}
    )
    return {"message": "Production order started. Raw materials consumed from stock."}

@api_router.put("/production-orders/{order_id}/qc")
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

@api_router.put("/production-orders/{order_id}/complete")
async def complete_production_order(order_id: str, current_user: dict = Depends(get_current_user)):
    order = await db.production_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] not in ["IN_PROGRESS", "QC"]:
        raise HTTPException(status_code=400, detail=f"Cannot complete order in status: {order['status']}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Add finished goods to stock via canonical create_stock_movement
    await create_stock_movement(
        product_id=order["product_id"],
        quantity_in=order["quantity"],
        quantity_out=0,
        ref_type="PRODUCTION_OUTPUT",
        ref_id=order_id,
        date=today,
        batch_id=order.get("batch_id")
    )

    # If a batch_id is set, upsert the batch record
    if order.get("batch_id"):
        existing_batch = await db.batches.find_one({"product_id": order["product_id"], "batch_number": order["batch_id"]})
        if existing_batch:
            await db.batches.update_one(
                {"product_id": order["product_id"], "batch_number": order["batch_id"]},
                {"$inc": {"quantity": order["quantity"]}}
            )
        else:
            await db.batches.insert_one({
                "id": str(uuid.uuid4()),
                "product_id": order["product_id"],
                "batch_number": order["batch_id"],
                "quantity": order["quantity"],
                "source": "production_order",
                "source_id": order_id,
                "created_at": now_iso
            })

    await db.production_orders.update_one(
        {"id": order_id},
        {"$set": {"status": "COMPLETED", "completed_at": now_iso}}
    )
    return {"message": f"Production order completed. {order['quantity']} units added to finished goods stock."}

@api_router.put("/production-orders/{order_id}/cancel")
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

# ============== SUPPLIERS ==============

@api_router.post("/suppliers")
async def create_supplier(supplier: SupplierCreate, current_user: dict = Depends(get_current_user)):
    supplier_id = str(uuid.uuid4())
    supplier_doc = {
        "id": supplier_id,
        **supplier.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.suppliers.insert_one(supplier_doc)
    
    # Create opening balance ledger entry for supplier payable
    if supplier.opening_balance > 0:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await create_ledger_entry(f"supplier:{supplier_id}", 0, supplier.opening_balance, "Opening balance payable", "setup", supplier_id, today)
        # Debit Capital (Liability reduces Equity)
        await create_ledger_entry("capital", supplier.opening_balance, 0, "Opening capital (supplier)", "setup", supplier_id, today)
    
    return {"message": "Supplier created", "id": supplier_id}

@api_router.get("/suppliers")
async def list_suppliers(current_user: dict = Depends(get_current_user)):
    suppliers = await db.suppliers.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    
    for supplier in suppliers:
        # Payable = credits - debits (we owe them)
        balance = await get_account_balance(f"supplier:{supplier['id']}")
        supplier["payable"] = max(0, -balance)
    
    return suppliers

@api_router.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str, current_user: dict = Depends(get_current_user)):
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    balance = await get_account_balance(f"supplier:{supplier_id}")
    supplier["payable"] = max(0, -balance)
    return supplier

@api_router.get("/suppliers/{supplier_id}/ledger")
async def get_supplier_ledger(supplier_id: str, current_user: dict = Depends(get_current_user)):
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    # Logic similar to customer ledger but for supplier (liability)
    # Account: supplier:{id}
    # Debit = Payment Made / Purchase Return (Reduces Liability)
    # Credit = Purchase / Debit Note? (Increases Liability)
    
    entries = await db.ledger.find(
        {"account": f"supplier:{supplier_id}"},
        {"_id": 0}
    ).sort("date", 1).to_list(1000)
    
    ledger = []
    running_balance = 0
    
    for entry in entries:
        # Supplier is Liability: Credit increases, Debit decreases
        # Balance = Credits - Debits
        running_balance += entry["credit"] - entry["debit"]
        
        if entry["credit"] > 0:
            description = f"Purchase - {entry['narration']}"
            amount = entry["credit"]
            type_ = "purchase"
        else:
            description = f"Payment Made - {entry['narration']}"
            amount = entry["debit"]
            type_ = "payment"
            
        ledger.append({
            "date": entry["date"],
            "description": description,
            "amount": amount,
            "type": type_,
            "balance": running_balance
        })
    
    return {"supplier": supplier, "ledger": ledger, "current_balance": running_balance}

@api_router.put("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, supplier: SupplierUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.suppliers.find_one({"id": supplier_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    update_data = supplier.model_dump()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.suppliers.update_one({"id": supplier_id}, {"$set": update_data})
    return {"message": "Supplier updated"}

@api_router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.suppliers.find_one({"id": supplier_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Supplier not found")
        
    # Check for dependencies
    purchases = await db.purchases.count_documents({"supplier_id": supplier_id})
    if purchases > 0:
        raise HTTPException(status_code=400, detail="Cannot delete supplier with existing purchases")
        
    await db.suppliers.delete_one({"id": supplier_id})
    return {"message": "Supplier deleted"}

# ============== PURCHASES ==============

@api_router.post("/purchases")
async def create_purchase(purchase: PurchaseCreate, current_user: dict = Depends(get_current_user)):
    purchase_id = str(uuid.uuid4())
    purchase_number = await get_next_purchase_number()
    purchase_date = purchase.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Process items
    items = []
    total = 0
    stock_warnings = []
    
    for item in purchase.items:
        product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")
        
        amount = item.quantity * item.cost_price
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
        # Restrict batch/serial validation here? (Wait, I just need to call it)
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
        # Create supplier payable
        await create_ledger_entry(f"supplier:{purchase.supplier_id}", 0, total, f"Purchase {purchase_number}", "purchase", purchase_id, purchase_date)

    # Debit Inventory Asset Account (not Purchases expense directly, for accrual accuracy)
    await create_ledger_entry("inventory_asset", total, 0, f"Purchase {purchase_number}", "purchase", purchase_id, purchase_date)

    # Check for Supplier Debit Balance (Advance/Debit Note) and update status/ledger awareness if needed
    debit_used = 0
    if purchase.supplier_id and purchase.payment_status == "unpaid" and purchase.apply_debit:
         amount_due, debit_used = await apply_debit_to_purchase(purchase.supplier_id, purchase_id, total)
         # apply_debit_to_purchase updates the purchase status and debit_used field
         if debit_used > 0:
             return {"message": "Purchase recorded", "id": purchase_id, "purchase_number": purchase_number, "debit_used": debit_used}
    
    return {"message": "Purchase recorded", "id": purchase_id, "purchase_number": purchase_number, "debit_used": 0}

@api_router.get("/purchases")
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
    
    purchases = await db.purchases.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return purchases

@api_router.get("/purchases/{purchase_id}")
async def get_purchase(purchase_id: str, current_user: dict = Depends(get_current_user)):
    purchase = await db.purchases.find_one({"id": purchase_id}, {"_id": 0})
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return purchase

@api_router.put("/purchases/{purchase_id}")
async def update_purchase(purchase_id: str, purchase: PurchaseUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.purchases.find_one({"id": purchase_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Purchase not found")
    
    # Reverse previous entries
    await delete_stock_movements("purchase", purchase_id)
    await delete_ledger_entries("purchase", purchase_id)
    
    # Process items
    items = []
    total = 0
    purchase_date = purchase.date or existing["date"]
    
    for item in purchase.items:
        product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")
        
        amount = item.quantity * item.cost_price
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
            item.product_id, 0, item.quantity, "purchase", purchase_id, purchase_date,
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
    
    # Create ledger entries based on payment status
    purchase_number = existing["purchase_number"]
    if purchase.payment_status == "cash":
        await create_ledger_entry("cash", 0, total, f"Purchase {purchase_number} (updated)", "purchase", purchase_id, purchase_date)
    elif purchase.payment_status == "bank":
        await create_ledger_entry("bank", 0, total, f"Purchase {purchase_number} (updated)", "purchase", purchase_id, purchase_date)
    elif purchase.payment_status == "unpaid" and purchase.supplier_id:
        await create_ledger_entry(f"supplier:{purchase.supplier_id}", 0, total, f"Purchase {purchase_number} (updated)", "purchase", purchase_id, purchase_date)

    # Debit Inventory Asset Account (consistent with create_purchase)
    await create_ledger_entry("inventory_asset", total, 0, f"Purchase {purchase_number} (updated)", "purchase", purchase_id, purchase_date)

    # Check for Supplier Debit Balance (Advance/Debit Note) if requested
    if purchase.supplier_id and purchase.payment_status == "unpaid" and purchase.apply_debit:
         await apply_debit_to_purchase(purchase.supplier_id, purchase_id, total)
        
    return {"message": "Purchase updated"}

@api_router.delete("/purchases/{purchase_id}")
async def delete_purchase(purchase_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.purchases.find_one({"id": purchase_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Purchase not found")
        
    await delete_stock_movements("purchase", purchase_id)
    await delete_ledger_entries("purchase", purchase_id)
    
    await db.purchases.delete_one({"id": purchase_id})
    return {"message": "Purchase deleted and effects reversed"}

# ============== CUSTOMERS ==============

@api_router.post("/customers")
async def create_customer(customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    customer_id = str(uuid.uuid4())
    customer_doc = {
        "id": customer_id,
        **customer.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.customers.insert_one(customer_doc)
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if customer.opening_balance > 0:
        if customer.balance_type == "debit":
            await create_ledger_entry(f"customer:{customer_id}", customer.opening_balance, 0, "Opening balance", "setup", customer_id, today)
            # Credit Capital (Asset increases Equity)
            await create_ledger_entry("capital", 0, customer.opening_balance, "Opening capital (customer)", "setup", customer_id, today)
        else:
            await create_ledger_entry(f"customer_credit:{customer_id}", 0, customer.opening_balance, "Opening credit balance", "setup", customer_id, today)
            # Debit Capital (Liability reduces Equity)
            await create_ledger_entry("capital", customer.opening_balance, 0, "Opening capital (customer)", "setup", customer_id, today)
    
    return {"message": "Customer created", "id": customer_id}

@api_router.get("/customers")
async def list_customers(current_user: dict = Depends(get_current_user)):
    customers = await db.customers.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    
    for customer in customers:
        customer["outstanding"] = await get_account_balance(f"customer:{customer['id']}")
        customer["credit"] = await get_customer_credit(customer["id"])
    
    return customers

@api_router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    customer["outstanding"] = await get_account_balance(f"customer:{customer_id}")
    customer["credit"] = await get_customer_credit(customer_id)
    return customer

@api_router.put("/customers/{customer_id}")
async def update_customer(customer_id: str, customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    existing = await db.customers.find_one({"id": customer_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    update_data = customer.model_dump(exclude_unset=True)
    update_data.pop("opening_balance", None)
    update_data.pop("balance_type", None)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.customers.update_one({"id": customer_id}, {"$set": update_data})
    return {"message": "Customer updated"}

@api_router.get("/customers/{customer_id}/ledger")
async def get_customer_ledger(
    customer_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = []

    # ---- Invoices (Debit) ----
    inv_query = {"customer_id": customer_id}
    if start_date:
        inv_query.setdefault("date", {})["$gte"] = start_date
    if end_date:
        inv_query.setdefault("date", {})["$lte"] = end_date

    invoices = await db.invoices.find(inv_query, {"_id": 0}).to_list(1000)
    for inv in invoices:
        rows.append({
            "timestamp": inv.get("created_at", inv.get("date", "") + "T00:00:00Z"),
            "date": inv.get("date", ""),
            "type": "invoice",
            "ref_number": inv.get("invoice_number", ""),
            "ref_id": inv.get("id", ""),
            "narration": f"Invoice — {inv.get('invoice_number', '')}",
            "debit": inv.get("total", 0),
            "credit": 0,
            "status": inv.get("status", ""),
        })

    # ---- Payments (Credit) ----
    pay_query = {"customer_id": customer_id}
    if start_date:
        pay_query.setdefault("date", {})["$gte"] = start_date
    if end_date:
        pay_query.setdefault("date", {})["$lte"] = end_date

    payments = await db.payments.find(pay_query, {"_id": 0}).to_list(1000)
    for pay in payments:
        # To avoid double counting, we only want the payment amount applied to invoices
        # as a credit against the customer's outstanding balance.
        # Let's read the actual ledger entries for this payment to get the applied amount.
        pay_ledger = await db.ledger.find_one({
            "ref_type": "payment", 
            "ref_id": pay.get("id"), 
            "account": f"customer:{customer_id}"
        })
        
        applied_credit = pay_ledger["credit"] if pay_ledger else 0
        
        # Don't show payment row in ledger if 0 was applied (e.g. 100% went to CN)
        # UNLESS they want to see it. Usually, we show the cash receipt, but since 
        # it doesn't affect outstanding balance, showing 0 credit is weird. Let's show the applied credit.
        rows.append({
            "timestamp": pay.get("created_at", pay.get("date", "") + "T00:00:00Z"),
            "date": pay.get("date", ""),
            "type": "payment",
            "ref_number": "",
            "ref_id": pay.get("id", ""),
            "narration": f"Payment — {pay.get('mode', '').capitalize()}{(' · ' + pay['notes']) if pay.get('notes') else ''}",
            "debit": 0,
            "credit": applied_credit,
            "status": "",
        })

    # ---- Credit Notes created (Credit, but doesn't reduce outstanding yet) ----
    cn_query = {"customer_id": customer_id}
    if start_date:
        cn_query.setdefault("date", {})["$gte"] = start_date
    if end_date:
        cn_query.setdefault("date", {})["$lte"] = end_date

    credit_notes = await db.credit_notes.find(cn_query, {"_id": 0}).to_list(1000)
    for cn in credit_notes:
        rows.append({
            "timestamp": cn.get("created_at", cn.get("date", "") + "T00:00:00Z"),
            "date": cn.get("date", ""),
            "type": "credit_note",
            "ref_number": cn.get("credit_note_number", ""),
            "ref_id": cn.get("id", ""),
            "narration": f"Credit Note {cn.get('credit_note_number', '')} — {cn.get('reason', '')}",
            "debit": 0,
            "credit": 0,  # CN Creation DOES NOT reduce outstanding
            "cn_total": cn.get("total", 0),
            "cn_original_total": cn.get("total", 0),
            "status": "active" if cn.get("total", 0) > 0 else "exhausted",
        })

    # ---- Credit Note Applications (Credit - reduces outstanding) ----
    cn_app_query = {
        "account": f"customer:{customer_id}",
        "ref_type": "credit_note_application"
    }
    if start_date:
        cn_app_query.setdefault("date", {})["$gte"] = start_date
    if end_date:
        cn_app_query.setdefault("date", {})["$lte"] = end_date
        
    cn_applications = await db.ledger.find(cn_app_query, {"_id": 0}).to_list(1000)
    for cn_app in cn_applications:
        # Look up the timestamp of the actual invoice or CN to place it correctly, 
        # or use a synthetic exact time since ledger doesn't track created_at currently.
        # We will append an arbitrary time to ensure it sorts after the invoice it applies to.
        rows.append({
            "timestamp": cn_app.get("date", "") + "T23:59:59Z", 
            "date": cn_app.get("date", ""),
            "type": "credit_note_application",
            "ref_number": "",
            "ref_id": cn_app.get("ref_id", ""),
            "narration": cn_app.get("narration", "Credit Note Applied"),
            "debit": 0,
            "credit": cn_app.get("credit", 0),
            "status": "",
        })

    # ---- Opening Balance ----
    opening_bal_query = {
        "account": f"customer:{customer_id}",
        "ref_type": "setup"
    }
    opening_bals = await db.ledger.find(opening_bal_query, {"_id": 0}).to_list(10)
    for ob in opening_bals:
        rows.append({
            "timestamp": ob.get("date", "") + "T00:00:00Z",
            "date": ob.get("date", ""),
            "type": "opening_balance",
            "ref_number": "",
            "ref_id": ob.get("ref_id", ""),
            "narration": "Opening Balance",
            "debit": ob.get("debit", 0),
            "credit": ob.get("credit", 0),
            "status": "",
        })

    # Sort all rows strictly by exact timestamp, then by type priority if timestamps match
    type_priority = {"opening_balance": 0, "invoice": 1, "payment": 2, "credit_note": 3, "credit_note_application": 4}
    rows.sort(key=lambda r: (r.get("timestamp", ""), type_priority.get(r["type"], 99)))

    # Compute running balance chronologically
    running_balance = 0
    ledger = []
    
    total_invoiced = 0
    total_paid = 0
    
    for row in rows:
        running_balance += row["debit"] - row["credit"]
        entry = {**row, "balance": round(running_balance, 2)}
        ledger.append(entry)
        
        if row["type"] == "invoice":
            total_invoiced += row["debit"]
        elif row["type"] == "payment" or row["type"] == "credit_note_application":
            total_paid += row["credit"]
            
    # For opening balance, if debit, it acts like invoiced, if credit, acts like paid
    for ob in opening_bals:
        total_invoiced += ob.get("debit", 0)
        total_paid += ob.get("credit", 0)

    cn_balance = await get_customer_credit(customer_id)

    # Compute advance balance
    adv_cursor = db.advance_payments.find({"customer_id": customer_id, "remaining_amount": {"$gt": 0}})
    advance_payments = await adv_cursor.to_list(100)
    adv_balance = sum([a["remaining_amount"] for a in advance_payments])

    return {
        "customer": {
            **customer,
            "outstanding": round(running_balance, 2),
            "credit": cn_balance,
            "advance_balance": adv_balance
        },
        "ledger": ledger,
        "summary": {
            "total_invoiced": round(total_invoiced, 2),
            "total_paid": round(total_paid, 2),
            "outstanding": round(running_balance, 2),
            "cn_balance": cn_balance,
            "adv_balance": round(adv_balance, 2)
        },
        "credit_notes": credit_notes,
        "advance_payments": advance_payments
    }


@api_router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.customers.find_one({"id": customer_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    # Check dependencies
    invoices = await db.invoices.count_documents({"customer_id": customer_id})
    if invoices > 0:
         raise HTTPException(status_code=400, detail="Cannot delete customer with existing invoices")
         
    payments = await db.payments.count_documents({"customer_id": customer_id})
    if payments > 0:
         raise HTTPException(status_code=400, detail="Cannot delete customer with existing payments")
         
    await db.customers.delete_one({"id": customer_id})
    return {"message": "Customer deleted"}

# ============== INVOICES ==============

@api_router.post("/invoices")
async def create_invoice(invoice: InvoiceCreate, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": invoice.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    invoice_id = str(uuid.uuid4())
    invoice_number = await get_next_invoice_number()
    invoice_date = invoice.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Process items and calculate totals
    items = []
    total = 0
    total_cost = 0
    stock_warnings = []
    
    for item in invoice.items:
        amount = item.quantity * item.rate
        item_doc = {
            "product_id": item.product_id,
            "description": item.description,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amount
        }
        
        if item.product_id:
            product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
            if product:
                item_doc["cost_price"] = product.get("cost_price", 0)
                total_cost += item.quantity * product.get("cost_price", 0)
                
                # Check stock only for non-draft
                if not invoice.is_draft:
                    current_stock = await get_product_stock(item.product_id)
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
    
    # Only create ledger and stock entries for non-draft invoices
    credit_applied = 0
    amount_due = total
    
    if not invoice.is_draft:
        # Create ledger entry for sale
        await create_ledger_entry(
            account=f"customer:{invoice.customer_id}",
            debit=total,
            credit=0,
            narration=f"Invoice {invoice_number}",
            ref_type="invoice",
            ref_id=invoice_id,
            date=invoice_date
        )

        # Credit Sales Account
        await create_ledger_entry(
            account="sales",
            debit=0,
            credit=total,
            narration=f"Invoice {invoice_number}",
            ref_type="invoice",
            ref_id=invoice_id,
            date=invoice_date
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

@api_router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, invoice_update: InvoiceUpdate, current_user: dict = Depends(get_current_user)):
    """Update an invoice - handles both draft and published invoices"""
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    invoice_date = invoice_update.date or existing["date"]
    is_draft = existing["status"] == "draft"
    
    # Reverse previous entries if not a draft
    if not is_draft:
        # Reverse ledger entries
        await delete_ledger_entries("invoice", invoice_id)
        await delete_ledger_entries("invoice_credit", invoice_id)
        
        # Reverse stock movements
        await delete_stock_movements("invoice", invoice_id)
        
        # Reset payment allocations that applied credit
        await db.payment_allocations.delete_many({"invoice_id": invoice_id})
        await db.invoices.update_one({"id": invoice_id}, {"$set": {"credit_applied": 0, "paid_amount": 0}})
    
    # Process new items
    items = []
    total = 0
    total_cost = 0
    stock_warnings = []
    
    for item in invoice_update.items:
        amount = item.quantity * item.rate
        item_doc = {
            "product_id": item.product_id,
            "description": item.description,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amount
        }
        
        if item.product_id:
            product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
            if product:
                item_doc["cost_price"] = product.get("cost_price", 0)
                total_cost += item.quantity * product.get("cost_price", 0)
                
                if not is_draft:
                    current_stock = await get_product_stock(item.product_id)
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
    
    # Apply new entries if not draft
    credit_applied = 0
    amount_due = total
    
    # If transitioning FROM draft TO finalized (via update? usually publish is preferred, but update can do it too if status changes)
    # Actually, update_invoice preserves status unless it creates new entries.
    # If it WAS draft, and we are updating, it STAYS draft unless we explicitly publish.
    # BUT, if it was NOT draft, we re-apply entries.
    
    if not is_draft:
        # Create new ledger entry
        await create_ledger_entry(
            account=f"customer:{existing['customer_id']}",
            debit=total,
            credit=0,
            narration=f"Invoice {existing['invoice_number']} (updated)",
            ref_type="invoice",
            ref_id=invoice_id,
            date=invoice_date
        )

        # Credit Sales Account (New)
        await create_ledger_entry(
            account="sales",
            debit=0,
            credit=total,
            narration=f"Invoice {existing['invoice_number']} (updated)",
            ref_type="invoice",
            ref_id=invoice_id,
            date=invoice_date
        )
        
        # Create new stock movements
        for item in items:
            if item.get("product_id"):
                await create_stock_movement(
                    item["product_id"], 0, item["quantity"], "invoice", invoice_id, invoice_date,
                    batch_id=item.get("batch_id"),
                    serial_numbers=item.get("serial_numbers")
                )
        
        # Re-apply customer credit if requested OR if it was previously applied
        # We should probably respect the flag if provided, or preserve previous behavior?
        # Simpler: If apply_credit is True, try to apply.
        if invoice_update.apply_credit:
             amount_due, credit_applied = await apply_credit_to_invoice(existing["customer_id"], invoice_id, total)
        
        # Recalculate status based on payments received

        allocations = await db.payment_allocations.find({"invoice_id": invoice_id}, {"_id": 0}).to_list(1000)
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

@api_router.post("/invoices/{invoice_id}/publish")
async def publish_invoice(invoice_id: str, apply_credit: bool = False, current_user: dict = Depends(get_current_user)):
    """Publish a draft invoice"""
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice["status"] != "draft":
        raise HTTPException(status_code=400, detail="Invoice is not a draft")
    
    invoice_date = invoice["date"]
    
    # Create ledger entry
    await create_ledger_entry(
        account=f"customer:{invoice['customer_id']}",
        debit=invoice["total"],
        credit=0,
        narration=f"Invoice {invoice['invoice_number']}",
        ref_type="invoice",
        ref_id=invoice_id,
        date=invoice_date
    )

    # Credit Sales Account
    await create_ledger_entry(
        account="sales",
        debit=0,
        credit=invoice["total"],
        narration=f"Invoice {invoice['invoice_number']}",
        ref_type="invoice",
        ref_id=invoice_id,
        date=invoice_date
    )
    
    # Create stock movements
    stock_warnings = []
    for item in invoice["items"]:
        if item.get("product_id"):
            current_stock = await get_product_stock(item["product_id"])
            if current_stock < item["quantity"]:
                product = await db.products.find_one({"id": item["product_id"]}, {"_id": 0})
                stock_warnings.append({
                    "product": product["name"] if product else item["description"],
                    "current_stock": current_stock,
                    "required": item["quantity"]
                })
            await create_stock_movement(
                item["product_id"], 0, item["quantity"], "invoice", invoice_id, invoice_date,
                batch_id=item.get("batch_id"),
                serial_numbers=item.get("serial_numbers")
            )
    
    # Apply customer credit if requested
    amount_due = invoice["total"]
    credit_applied = 0
    
    if apply_credit:
        amount_due, credit_applied = await apply_credit_to_invoice(invoice["customer_id"], invoice_id, invoice["total"])
    
    # Update status
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

@api_router.get("/invoices")
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
    
    invoices = await db.invoices.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return invoices

@api_router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, current_user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice

@api_router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(invoice_id: str, current_user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    customer = await db.customers.find_one({"id": invoice["customer_id"]}, {"_id": 0})
    business = await db.business.find_one({}, {"_id": 0})
    
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

# ============== INVOICE DELETE ==============

@api_router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, current_user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # If published (not draft), reverse all effects
    if invoice["status"] != "draft":
        # Reverse stock movements
        await delete_stock_movements("invoice", invoice_id)
        # Reverse ledger entries (sale and COGS)
        await delete_ledger_entries("invoice", invoice_id)
        # Reverse credit applied entries
        await delete_ledger_entries("invoice_credit", invoice_id)
        
        # Reverse payment allocations for this invoice ONLY.
        # We do NOT delete the parent payment — a payment may have been split across multiple invoices
        # via FIFO. Deleting the payment would corrupt all other invoices it was applied to.
        # Instead: remove the allocation records and reduce paid_amount on affected payments/invoices.
        allocations = await db.payment_allocations.find({"invoice_id": invoice_id}).to_list(1000)
        for alloc in allocations:
            # Reduce paid_amount on any OTHER invoices that shared this payment (rare but possible)
            # For this invoice specifically, it's being deleted so no update needed.
            # Just clean up the allocation record.
            pass
        await db.payment_allocations.delete_many({"invoice_id": invoice_id})
    
    await db.invoices.delete_one({"id": invoice_id})
    return {"message": "Invoice deleted and all effects reversed"}

# ============== PAYMENTS ==============

@api_router.post("/payments")
async def record_payment(payment: PaymentCreate, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": payment.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    payment_id = str(uuid.uuid4())
    payment_date = payment.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    payment_doc = {
        "id": payment_id,
        "customer_id": payment.customer_id,
        "customer_name": customer["name"],
        "amount": payment.amount,
        "mode": payment.mode,
        "notes": payment.notes,
        "date": payment_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.payments.insert_one(payment_doc)
    
    await create_ledger_entry(
        account=payment.mode,
        debit=payment.amount,
        credit=0,
        narration=f"Payment from {customer['name']}",
        ref_type="payment",
        ref_id=payment_id,
        date=payment_date
    )
    

    excess = 0
    credit_note_applied_amount = 0

    # Step 1: Apply any existing Credit Note to the invoice FIRST (before cash payment)
    if payment.credit_note_id and payment.invoice_id:
        credit_note_applied_amount = await apply_credit_note_to_invoice(payment.credit_note_id, payment.invoice_id)
        
    advance_applied_amount = 0
    if payment.advance_payment_id and payment.invoice_id:
        advance_applied_amount = await apply_advance_payment_to_invoice(payment.advance_payment_id, payment.invoice_id)

    # Step 2: Determine how much cash actually needs to go to invoices
    applied_to_invoices = 0  # track actual invoice allocation for ledger entry

    if payment.invoice_id:
        invoice = await db.invoices.find_one({"id": payment.invoice_id})
        if invoice:
            outstanding = invoice["total"] - invoice.get("paid_amount", 0)
            apply_amt = min(payment.amount, outstanding)
            if apply_amt > 0:
                new_paid = invoice.get("paid_amount", 0) + apply_amt
                new_status = "paid" if new_paid >= invoice["total"] else "partially_paid"

                await db.invoices.update_one(
                    {"id": payment.invoice_id},
                    {"$set": {"paid_amount": new_paid, "status": new_status}}
                )

                await db.payment_allocations.insert_one({
                    "id": str(uuid.uuid4()),
                    "payment_id": payment_id,
                    "invoice_id": payment.invoice_id,
                    "amount": apply_amt,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })

                applied_to_invoices = apply_amt
                excess = round(payment.amount - apply_amt, 2)
            else:
                # Invoice already fully paid — full cash amount becomes excess/CN
                excess = payment.amount
        else:
            # Invoice not found — treat all as excess (Advance Payment)
            excess = payment.amount
            applied_to_invoices = 0
    else:
        # No specific invoice — apply FIFO across outstanding invoices
        excess = await apply_payment_fifo(payment.customer_id, payment.amount, payment_id)
        applied_to_invoices = payment.amount - excess

    # KEY ARCHITECTURAL FIX:
    # Only credit the customer ledger for the amount applied to invoices.
    # The excess is captured ONLY in the Credit Note document — NOT in the ledger.
    # This eliminates the double-counting between ledger credit and Credit Note.
    await create_ledger_entry(
        account=f"customer:{payment.customer_id}",
        debit=0,
        credit=applied_to_invoices,
        narration=f"Payment applied to invoices",
        ref_type="payment",
        ref_id=payment_id,
        date=payment_date
    )

    # Step 3: Create Advance Payment for overpayment instead of Credit Note
    advance_payment_id = None
    if excess > 0.009:  # avoid floating point noise
        adv_id = str(uuid.uuid4())
        
        adv_doc = {
            "id": adv_id,
            "customer_id": payment.customer_id,
            "customer_name": customer["name"],
            "payment_id": payment_id,
            "source_invoice_id": payment.invoice_id,
            "amount": excess,
            "remaining_amount": excess,
            "date": payment_date,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.advance_payments.insert_one(adv_doc)
        advance_payment_id = adv_id
        
        # Advance payments sit on the customer's ledger as credit!
        await create_ledger_entry(
            account=f"customer:{payment.customer_id}",
            debit=0,
            credit=excess,
            narration=f"Advance payment received via payment ...{payment_id[-8:]}",
            ref_type="payment", # Use payment type so it rolls back with the payment
            ref_id=payment_id,
            date=payment_date
        )

    return {
        "message": "Payment recorded",
        "id": payment_id,
        "excess_as_advance": excess,
        "advance_payment_id": advance_payment_id,
        "credit_note_applied": credit_note_applied_amount,
        "advance_payment_applied": advance_applied_amount
    }

@api_router.get("/payments")
async def list_payments(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    
    payments = await db.payments.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return payments

@api_router.delete("/payments/{payment_id}")
async def delete_payment(payment_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.payments.find_one({"id": payment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Payment not found")
        
    # Reverse Ledger
    await delete_ledger_entries("payment", payment_id)
    
    # Reverse effects on invoices (re-open them)
    allocations = await db.payment_allocations.find({"payment_id": payment_id}).to_list(1000)
    for alloc in allocations:
        invoice_id = alloc["invoice_id"]
        amount = alloc["amount"]
        
        # Reduce paid_amount on invoice
        invoice = await db.invoices.find_one({"id": invoice_id})
        if invoice:
            new_paid = max(0, invoice.get("paid_amount", 0) - amount)
            # Simple status logic
            new_status = "partially_paid" if new_paid > 0 else "unpaid"
            if new_paid >= invoice["total"]:
                 new_status = "paid"
            
            await db.invoices.update_one(
                {"id": invoice_id},
                {"$set": {"paid_amount": new_paid, "status": new_status}}
            )
            
    await db.payment_allocations.delete_many({"payment_id": payment_id})
        
    # Remove auto-generated credit notes and Advance Payments
    await db.credit_notes.delete_many({"payment_id": payment_id, "is_auto_generated": True})
    await db.advance_payments.delete_many({"payment_id": payment_id})
        
    await db.payments.delete_one({"id": payment_id})
    return {"message": "Payment voided and invoice balances reverted"}

# ============== SUPPLIER PAYMENTS ==============

@api_router.post("/supplier-payments")
async def record_supplier_payment(supplier_id: str, amount: float, mode: str, date: Optional[str] = None, notes: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    payment_id = str(uuid.uuid4())
    payment_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    payment_doc = {
        "id": payment_id,
        "supplier_id": supplier_id,
        "supplier_name": supplier["name"],
        "amount": amount,
        "mode": mode,
        "notes": notes,
        "date": payment_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.supplier_payments.insert_one(payment_doc)
    
    # Credit cash/bank
    await create_ledger_entry(
        account=mode,
        debit=0,
        credit=amount,
        narration=f"Payment to {supplier['name']}",
        ref_type="supplier_payment",
        ref_id=payment_id,
        date=payment_date
    )
    
    # Debit supplier account (reduce payable)
    await create_ledger_entry(
        account=f"supplier:{supplier_id}",
        debit=amount,
        credit=0,
        narration=f"Payment made",
        ref_type="supplier_payment",
        ref_id=payment_id,
        date=payment_date
    )

    # Check for overpayment (Debit Note)
    balance = await get_account_balance(f"supplier:{supplier_id}")
    # Balance is usually negative (credit balance) because we owe them.
    # If balance > 0, it means we paid more than we bought (Debit Balance).
    
    debit_note_id = None
    if balance > 0:
        # We have a debit balance (they owe us / we overpaid)
        # Create a "Visual" Debit Note for the positive balance amount
        # Note: 'balance' here is the accumulated debit balance. 
        # But we should only create a debit note for the *current transaction's* contribution to that?
        # Simpler: If the payment caused the balance to flip or increase in debit, capture that?
        # Actually, let's look at the specific context: 
        # User wants "Debit Note" for the *excess* of this specific payment vs what was owed?
        # But "what was owed" is hard to track without "bill-by-bill" matching for suppliers (which we might not have fully).
        # Let's assume if the *Total Supplier Balance* is now Positive (Debit), we generate a Debit Note?
        # No, that might duplicate old debit notes.
        # Strategy: Logic similar to Customer. 
        # Customers have 'invoices'. Suppliers have 'purchases'.
        # Do we have FIFO for suppliers? "apply_payment_fifo" exists for customers.
        # We don't seem to have "apply_supplier_payment_fifo".
        # So we can't easily calculate "excess against specific bills".
        # However, we can calculate "Amount Unapplied"? 
        # If we just implemented simple "Create Debit Note if Total Balance > 0", it would be annoying.
        
        # User request: "recorded a invoice of 50k and a customer paid 100k... same with debit note".
        # Implicitly, they want the specific *excess* of this transaction.
        # Since we don't have supplier bill validation yet, we'll approximate:
        # If the user *manually* creates a payment, they probably know what they are paying.
        # Ideally, we should check if they are paying against a specific Purchase?
        # The `record_supplier_payment` API logic assumes "On Account" payment (no purchase_id arg).
        
        # For now, to satisfy the specific "User Experience" request without full bill-tracking:
        # We will check if the Supplier's Balance *before* this payment was X.
        # (We can fetch it before inserting the ledger entry or calc it back).
        # But simpler: The prompt implies "Overpayment".
        # Let's just create a Debit Note if the user implies it? No, automatic.
        # Let's stick to: If `balance > 0` (Debit Balance) AFTER payment.
        # AND we haven't already created a Debit Note for this balance?
        # This is tricky for Suppliers without Bill-by-Bill.
        
        # fallback: For Suppliers, we will just create the Debit Note equal to the *entire* positive balance 
        # if it transitioned from Credit to Debit? 
        # No, that might duplicate old debit notes.
        
        # Let's go with: Simple "Excess" logic based on "Payable".
        # We need "Payable" BEFORE this payment.
        # Payable = max(0, - (current_balance - amount)) ? No. 
        # Ledger entry: Debit `amount`.
        # So `current_balance` = `old_balance` + `amount`.
        # `old_balance` = `current_balance` - `amount`.
        
        old_balance = current_balance - amount 
        # If old_balance was -100 (We owed 100).
        # Payment 150.
        # current_balance = +50.
        # Excess = 50.
        
        # If old_balance was +10 (They owed us 10).
        # Payment 150.
        # current_balance = +160.
        # Excess = 150. (The whole payment is an "advance").
        
        excess = 0
        if old_balance < 0: # We owed money
             if amount > abs(old_balance):
                 excess = amount - abs(old_balance)
        else: # We didn't owe, or they owed us
             excess = amount

        if excess > 0:
             # robust dn number generation logic
             last_dn = await db.debit_notes.find_one({}, {"_id": 0, "debit_note_number": 1}, sort=[("debit_note_number", -1)])
             dn_number = "DN-00001"
             if last_dn:
                 try:
                     last_num = int(last_dn["debit_note_number"].replace("DN-", ""))
                     dn_number = f"DN-{str(last_num + 1).zfill(5)}"
                 except:
                     pass

             dn_id = str(uuid.uuid4())
             dn_doc = {
                "id": dn_id,
                "debit_note_number": dn_number,
                "supplier_id": supplier_id,
                "supplier_name": supplier["name"],
                "purchase_id": None,
                "payment_id": payment_id,
                "items": [{
                    "product_id": "OVERPAYMENT",
                    "description": "Overpayment / Advance",
                    "quantity": 1,
                    "cost_price": excess,
                     # DebitNoteItem model requires cost_price. 
                     # Also validation on FE might require product_id to exist? 
                     # Backend doesn't strictly enforce foreign key on product_id string in model validation for logic, only in creating stock movement?
                     # Let's check DebitNoteItem definition.
                }], 
                "total": excess,
                "reason": f"Auto-generated from Payment {payment_id.split('-')[0]}",
                "date": payment_date,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_auto_generated": True
             }
             await db.debit_notes.insert_one(dn_doc)
             debit_note_id = dn_id

    return {"message": "Supplier payment recorded", "id": payment_id}

@api_router.delete("/supplier-payments/{payment_id}")
async def delete_supplier_payment(payment_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.supplier_payments.find_one({"id": payment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Supplier payment not found")
        
    # Reverse Ledger
    await delete_ledger_entries("supplier_payment", payment_id)
    
    # Remove associated Advance Payments
    await db.advance_payments.delete_many({"payment_id": payment_id})
    
    # Remove auto-generated Debit Notes created from overpayment detection
    await db.debit_notes.delete_many({"payment_id": payment_id, "is_auto_generated": True})
        
    await db.supplier_payments.delete_one({"id": payment_id})
    return {"message": "Supplier payment voided and balances reverted"}

# ============== EXPENSES ==============

@api_router.post("/expenses")
async def create_expense(expense: ExpenseCreate, current_user: dict = Depends(get_current_user)):
    expense_id = str(uuid.uuid4())
    expense_date = expense.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    expense_doc = {
        "id": expense_id,
        **expense.model_dump(),
        "date": expense_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.expenses.insert_one(expense_doc)
    
    await create_ledger_entry(
        account=expense.mode,
        debit=0,
        credit=expense.amount,
        narration=f"Expense: {expense.description}",
        ref_type="expense",
        ref_id=expense_id,
        date=expense_date
    )

    # Debit Expense Account
    await create_ledger_entry(
        account=f"expense:{expense.category}",
        debit=expense.amount,
        credit=0,
        narration=f"Expense: {expense.description}",
        ref_type="expense",
        ref_id=expense_id,
        date=expense_date
    )
    
    return {"message": "Expense recorded", "id": expense_id}

@api_router.get("/expenses")
async def list_expenses(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return expenses

@api_router.put("/expenses/{expense_id}")
async def update_expense(expense_id: str, expense: ExpenseUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.expenses.find_one({"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")
        
    # Reverse Ledger
    await delete_ledger_entries("expense", expense_id)
    
    # Update Doc
    update_data = expense.model_dump()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.expenses.update_one({"id": expense_id}, {"$set": update_data})
    
    # Re-create Ledger
    expense_date = expense.date or existing["date"]
    await create_ledger_entry(
        account=expense.mode,
        debit=0,
        credit=expense.amount,
        narration=f"Expense: {expense.description} (updated)",
        ref_type="expense",
        ref_id=expense_id,
        date=expense_date
    )

    # Debit Expense Account (New)
    await create_ledger_entry(
        account=f"expense:{expense.category}",
        debit=expense.amount,
        credit=0,
        narration=f"Expense: {expense.description} (updated)",
        ref_type="expense",
        ref_id=expense_id,
        date=expense_date
    )
    
    return {"message": "Expense updated"}

@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.expenses.find_one({"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")
        
    await delete_ledger_entries("expense", expense_id)
    await db.expenses.delete_one({"id": expense_id})
    return {"message": "Expense deleted"}

# ============== CREDIT NOTES (Sales Returns) ==============

async def get_next_credit_note_number() -> str:
    last = await db.credit_notes.find_one({}, {"_id": 0, "credit_note_number": 1}, sort=[("credit_note_number", -1)])
    if last:
        try:
            last_num = int(last["credit_note_number"].replace("CN-", ""))
            return f"CN-{str(last_num + 1).zfill(5)}"
        except:
            pass
    return "CN-00001"

@api_router.post("/credit-notes")
async def create_credit_note(cn: CreditNoteCreate, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": cn.customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    cn_id = str(uuid.uuid4())
    cn_number = await get_next_credit_note_number()
    cn_date = cn.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    items = []
    total = 0
    for item in cn.items:
        product_name = item.description
        if item.product_id:
            product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
            if product:
                product_name = product["name"]
            # Return stock (stock in)
            await create_stock_movement(item.product_id, item.quantity, 0, "credit_note", cn_id, cn_date)
        
        amount = item.quantity * item.rate
        items.append({
            "product_id": item.product_id,
            "description": product_name,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amount
        })
        total += amount
    
    cn_doc = {
        "id": cn_id,
        "credit_note_number": cn_number,
        "customer_id": cn.customer_id,
        "customer_name": customer["name"],
        "invoice_id": cn.invoice_id,
        "items": items,
        "total": total,
        "reason": cn.reason,
        "date": cn_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.credit_notes.insert_one(cn_doc)
    
    # Reduce customer outstanding (credit the customer account)
    await create_ledger_entry(
        f"customer:{cn.customer_id}", 0, total,
        f"Credit Note {cn_number}", "credit_note", cn_id, cn_date
    )
    
    # Debit Sales Returns (reduce revenue)
    await create_ledger_entry(
        "sales_returns", total, 0,
        f"Credit Note {cn_number}", "credit_note", cn_id, cn_date
    )
    
    return {"message": "Credit Note created", "id": cn_id, "credit_note_number": cn_number}

@api_router.put("/credit-notes/{cn_id}")
async def update_credit_note(cn_id: str, cn_update: CreditNoteUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.credit_notes.find_one({"id": cn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Credit Note not found")
        
    # Reverse existing effects
    await delete_stock_movements("credit_note", cn_id)
    await delete_ledger_entries("credit_note", cn_id)
    
    # Process new data
    cn_date = cn_update.date or existing["date"]
    
    items = []
    total = 0
    for item in cn_update.items:
        product_name = item.description
        if item.product_id:
            product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
            if product:
                product_name = product["name"]
            # Return stock (stock in)
            await create_stock_movement(item.product_id, item.quantity, 0, "credit_note", cn_id, cn_date)
        
        amount = item.quantity * item.rate
        items.append({
            "product_id": item.product_id,
            "description": product_name,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amount
        })
        total += amount
        
    # Update document
    update_data = {
        "items": items,
        "total": total,
        "reason": cn_update.reason,
        "date": cn_date,
        "invoice_id": cn_update.invoice_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.credit_notes.update_one({"id": cn_id}, {"$set": update_data})
    
    # Re-create ledger entries (both sides — fixes missing sales_returns on update)
    await create_ledger_entry(
        f"customer:{existing['customer_id']}", 0, total,
        f"Credit Note {existing['credit_note_number']}", "credit_note", cn_id, cn_date
    )
    await create_ledger_entry(
        "sales_returns", total, 0,
        f"Credit Note {existing['credit_note_number']}", "credit_note", cn_id, cn_date
    )
    
    return {"message": "Credit Note updated"}

@api_router.get("/credit-notes")
async def list_credit_notes(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}

    notes = await db.credit_notes.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return notes

@api_router.get("/credit-notes/{cn_id}")
async def get_credit_note(cn_id: str, current_user: dict = Depends(get_current_user)):
    cn = await db.credit_notes.find_one({"id": cn_id}, {"_id": 0})
    if not cn:
        raise HTTPException(status_code=404, detail="Credit Note not found")
    return cn

@api_router.delete("/credit-notes/{cn_id}")
async def delete_credit_note(cn_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.credit_notes.find_one({"id": cn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Credit Note not found")
    
    # Reverse the CN amount already applied to any linked invoice.
    # When a CN is applied to an invoice via apply_credit_note_to_invoice, the invoice's
    # paid_amount is increased and the CN's total is decreased. Deleting the CN must undo this.
    if existing.get("invoice_id"):
        linked_invoice = await db.invoices.find_one({"id": existing["invoice_id"]})
        if linked_invoice:
            cn_applied = linked_invoice.get("credit_note_applied", 0)
            if cn_applied > 0:
                new_paid = max(0, linked_invoice.get("paid_amount", 0) - cn_applied)
                new_status = "paid" if new_paid >= linked_invoice["total"] else ("partially_paid" if new_paid > 0 else "unpaid")
                await db.invoices.update_one(
                    {"id": existing["invoice_id"]},
                    {"$set": {"paid_amount": new_paid, "status": new_status, "credit_note_applied": 0}}
                )
    
    await delete_stock_movements("credit_note", cn_id)
    await delete_ledger_entries("credit_note", cn_id)
    await db.credit_notes.delete_one({"id": cn_id})
    
    return {"message": "Credit Note deleted and effects reversed"}

# ============== DEBIT NOTES (Purchase Returns) ==============

async def get_next_debit_note_number() -> str:
    last = await db.debit_notes.find_one({}, {"_id": 0, "debit_note_number": 1}, sort=[("debit_note_number", -1)])
    if last:
        try:
            last_num = int(last["debit_note_number"].replace("DN-", ""))
            return f"DN-{str(last_num + 1).zfill(5)}"
        except:
            pass
    return "DN-00001"

@api_router.post("/debit-notes")
async def create_debit_note(dn: DebitNoteCreate, current_user: dict = Depends(get_current_user)):
    supplier = await db.suppliers.find_one({"id": dn.supplier_id})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    dn_id = str(uuid.uuid4())
    dn_number = await get_next_debit_note_number()
    dn_date = dn.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    items = []
    total = 0
    for item in dn.items:
        product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")
        
        amount = item.quantity * item.cost_price
        items.append({
            "product_id": item.product_id,
            "product_name": product["name"],
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "amount": amount
        })
        total += amount
        
        # Return stock to supplier (stock out)
        await create_stock_movement(item.product_id, 0, item.quantity, "debit_note", dn_id, dn_date)
    
    dn_doc = {
        "id": dn_id,
        "debit_note_number": dn_number,
        "supplier_id": dn.supplier_id,
        "supplier_name": supplier["name"],
        "purchase_id": dn.purchase_id,
        "items": items,
        "total": total,
        "reason": dn.reason,
        "date": dn_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.debit_notes.insert_one(dn_doc)
    
    # Reduce supplier payable (debit the supplier account)
    await create_ledger_entry(
        f"supplier:{dn.supplier_id}", total, 0,
        f"Debit Note {dn_number}", "debit_note", dn_id, dn_date
    )
    
    # Credit Purchases Returns (reduce expense)
    await create_ledger_entry(
        "purchases_returns", 0, total,
        f"Debit Note {dn_number}", "debit_note", dn_id, dn_date
    )
    
    return {"message": "Debit Note created", "id": dn_id, "debit_note_number": dn_number}

@api_router.put("/debit-notes/{dn_id}")
async def update_debit_note(dn_id: str, dn_update: DebitNoteUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.debit_notes.find_one({"id": dn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Debit Note not found")
        
    # Reverse existing effects
    await delete_stock_movements("debit_note", dn_id)
    await delete_ledger_entries("debit_note", dn_id)
    
    # Process new data
    dn_date = dn_update.date or existing["date"]
    
    items = []
    total = 0
    for item in dn_update.items:
        product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
        if not product:
             # Just warn or skip? Better to fail if product missing in update? 
             # Or assume it exists. Let's fail for safety.
             raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")
        
        amount = item.quantity * item.cost_price
        items.append({
            "product_id": item.product_id,
            "product_name": product["name"],
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "amount": amount
        })
        total += amount
        
        # Return stock to supplier (stock out)
        await create_stock_movement(item.product_id, 0, item.quantity, "debit_note", dn_id, dn_date)
            
    # Update document
    update_data = {
        "items": items,
        "total": total,
        "reason": dn_update.reason,
        "date": dn_date,
        "purchase_id": dn_update.purchase_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.debit_notes.update_one({"id": dn_id}, {"$set": update_data})
    
    # Re-create ledger entry (Debit Supplier)
    await create_ledger_entry(
        f"supplier:{existing['supplier_id']}", total, 0,
        f"Debit Note {existing['debit_note_number']}", "debit_note", dn_id, dn_date
    )
    
    return {"message": "Debit Note updated"}

@api_router.get("/debit-notes")
async def list_debit_notes(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    
    notes = await db.debit_notes.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return notes

@api_router.get("/debit-notes/{dn_id}")
async def get_debit_note(dn_id: str, current_user: dict = Depends(get_current_user)):
    dn = await db.debit_notes.find_one({"id": dn_id}, {"_id": 0})
    if not dn:
        raise HTTPException(status_code=404, detail="Debit Note not found")
    return dn

@api_router.delete("/debit-notes/{dn_id}")
async def delete_debit_note(dn_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.debit_notes.find_one({"id": dn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Debit Note not found")
    
    await delete_stock_movements("debit_note", dn_id)
    await delete_ledger_entries("debit_note", dn_id)
    await db.debit_notes.delete_one({"id": dn_id})
    
    return {"message": "Debit Note deleted and effects reversed"}

# ============== DASHBOARD ==============

@api_router.get("/dashboard")
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_start = datetime.now(timezone.utc).replace(day=1).strftime("%Y-%m-%d")
    
    cash_balance = await get_account_balance("cash")
    bank_balance = await get_account_balance("bank")
    
    customers = await db.customers.find({}, {"_id": 0, "id": 1}).to_list(1000)
    total_outstanding = 0
    total_credit = 0
    for c in customers:
        total_outstanding += max(0, await get_account_balance(f"customer:{c['id']}"))
        total_credit += await get_customer_credit(c["id"])
    
    # Supplier payables
    suppliers = await db.suppliers.find({}, {"_id": 0, "id": 1}).to_list(1000)
    total_payable = 0
    for s in suppliers:
        balance = await get_account_balance(f"supplier:{s['id']}")
        total_payable += max(0, -balance)
    
    today_invoices = await db.invoices.find({"date": today, "status": {"$ne": "draft"}}, {"_id": 0, "total": 1}).to_list(1000)
    today_sales = sum(inv["total"] for inv in today_invoices)
    
    month_invoices = await db.invoices.find({"date": {"$gte": month_start}, "status": {"$ne": "draft"}}, {"_id": 0, "total": 1}).to_list(1000)
    monthly_sales = sum(inv["total"] for inv in month_invoices)
    
    # Low stock products
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    low_stock_count = 0
    low_stock_products = []
    for p in products:
        stock = await get_product_stock(p["id"])
        if stock < p.get("low_stock_threshold", 10):
            low_stock_count += 1
            if len(low_stock_products) < 5:
                low_stock_products.append({
                    "id": p["id"],
                    "name": p["name"],
                    "current_stock": stock,
                    "low_stock_threshold": p.get("low_stock_threshold", 10)
                })
    
    # Recent activity
    recent_invoices = await db.invoices.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_payments = await db.payments.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_purchases = await db.purchases.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_expenses = await db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    
    # Overdue invoices (unpaid or partially_paid with date before today)
    overdue_invoices = await db.invoices.find(
        {"status": {"$in": ["unpaid", "partially_paid"]}, "date": {"$lt": today}},
        {"_id": 0, "id": 1}
    ).to_list(1000)
    overdue_count = len(overdue_invoices)
    
    # Monthly expenses
    month_expenses = await db.expenses.find(
        {"date": {"$gte": month_start}},
        {"_id": 0, "amount": 1}
    ).to_list(1000)
    monthly_expenses = sum(exp["amount"] for exp in month_expenses)
    
    # Entity counts
    total_customers = await db.customers.count_documents({})
    total_suppliers = await db.suppliers.count_documents({})
    total_products = len(products)
    
    # Production Data
    active_work_orders = await db.production_orders.count_documents({"status": "in_progress"})
    planned_work_orders = await db.production_orders.count_documents({"status": "planned"})
    completed_work_orders = await db.production_orders.count_documents({"status": "completed", "end_date": {"$gte": month_start}})
    
    return {
        "cash_balance": cash_balance,
        "bank_balance": bank_balance,
        "total_outstanding": total_outstanding,
        "total_credit": total_credit,
        "total_payable": total_payable,
        "today_sales": today_sales,
        "monthly_sales": monthly_sales,
        "monthly_expenses": monthly_expenses,
        "low_stock_count": low_stock_count,
        "low_stock_products": low_stock_products,
        "overdue_count": overdue_count,
        "total_customers": total_customers,
        "total_suppliers": total_suppliers,
        "total_products": total_products,
        "recent_invoices": recent_invoices,
        "recent_payments": recent_payments,
        "recent_purchases": recent_purchases,
        "recent_expenses": recent_expenses,
        "active_work_orders": active_work_orders,
        "planned_work_orders": planned_work_orders,
        "completed_work_orders": completed_work_orders
    }

# ============== REPORTS ==============

@api_router.get("/reports/outstanding")
async def report_outstanding(current_user: dict = Depends(get_current_user)):
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)
    report = []
    
    for customer in customers:
        outstanding = await get_account_balance(f"customer:{customer['id']}")
        if outstanding > 0:
            report.append({
                "customer_id": customer["id"],
                "customer_name": customer["name"],
                "phone": customer.get("phone"),
                "outstanding": outstanding
            })
    
    report.sort(key=lambda x: x["outstanding"], reverse=True)
    total = sum(r["outstanding"] for r in report)
    
    return {"report": report, "total": total}

@api_router.get("/reports/credit")
async def report_credit(current_user: dict = Depends(get_current_user)):
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)
    report = []
    
    for customer in customers:
        credit = await get_customer_credit(customer["id"])
        if credit > 0:
            report.append({
                "customer_id": customer["id"],
                "customer_name": customer["name"],
                "phone": customer.get("phone"),
                "credit": credit
            })
    
    report.sort(key=lambda x: x["credit"], reverse=True)
    total = sum(r["credit"] for r in report)
    
    return {"report": report, "total": total}

@api_router.get("/reports/sales")
async def report_sales(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"status": {"$ne": "draft"}}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date
    
    invoices = await db.invoices.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    total = sum(inv["total"] for inv in invoices)
    collected = sum(inv.get("paid_amount", 0) for inv in invoices)
    total_cost = sum(inv.get("total_cost", 0) for inv in invoices)
    
    # Deduct credit notes in the same period
    cn_query = {}
    if start_date:
        cn_query["date"] = {"$gte": start_date}
    if end_date:
        cn_query.setdefault("date", {})["$lte"] = end_date
    credit_notes = await db.credit_notes.find(cn_query, {"_id": 0, "total": 1}).to_list(1000)
    total_returns = sum(cn["total"] for cn in credit_notes)
    
    profit = (total - total_returns) - total_cost
    
    return {
        "invoices": invoices,
        "total_sales": total,
        "total_returns": total_returns,
        "net_sales": total - total_returns,
        "total_collected": collected,
        "pending": (total - total_returns) - collected,
        "total_cost": total_cost,
        "profit": profit
    }

@api_router.get("/reports/expenses")
async def report_expenses(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date
    
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    total = sum(exp["amount"] for exp in expenses)
    
    by_category = {}
    for exp in expenses:
        cat = exp.get("category") or "Other"
        by_category[cat] = by_category.get(cat, 0) + exp["amount"]
    
    return {"expenses": expenses, "total": total, "by_category": by_category}

@api_router.get("/reports/cash-bank")
async def report_cash_bank(current_user: dict = Depends(get_current_user)):
    cash_balance = await get_account_balance("cash")
    bank_balance = await get_account_balance("bank")
    
    cash_entries = await db.ledger.find({"account": "cash"}, {"_id": 0}).sort("date", -1).to_list(50)
    bank_entries = await db.ledger.find({"account": "bank"}, {"_id": 0}).sort("date", -1).to_list(50)
    
    return {
        "cash_balance": cash_balance,
        "bank_balance": bank_balance,
        "total_balance": cash_balance + bank_balance,
        "cash_transactions": cash_entries,
        "bank_transactions": bank_entries
    }

@api_router.get("/reports/inventory")
async def report_inventory(current_user: dict = Depends(get_current_user)):
    """Product stock report"""
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    report = []
    total_value = 0
    
    for product in products:
        stock = await get_product_stock(product["id"])
        value = stock * product.get("cost_price", 0)
        report.append({
            "product_id": product["id"],
            "product_name": product["name"],
            "sku": product.get("sku"),
            "current_stock": stock,
            "cost_price": product.get("cost_price", 0),
            "selling_price": product.get("selling_price", 0),
            "value": value,
            "low_stock_threshold": product.get("low_stock_threshold", 10),
            "is_low_stock": stock < product.get("low_stock_threshold", 10)
        })
        total_value += value
    
    return {"report": report, "total_value": total_value}

@api_router.get("/reports/inventory-by-type")
async def report_inventory_by_type(current_user: dict = Depends(get_current_user)):
    """Inventory grouped by item type (Raw Material, WIP, Finished Good)"""
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    summary = {}
    details = []
    total_value = 0
    
    for product in products:
        stock = await get_product_stock(product["id"])
        item_type = product.get("item_type", "FINISHED_GOOD")
        value = stock * product.get("cost_price", 0)
        
        detail = {
            "product_id": product["id"],
            "product_name": product["name"],
            "sku": product.get("sku"),
            "item_type": item_type,
            "current_stock": stock,
            "cost_price": product.get("cost_price", 0),
            "value": value
        }
        details.append(detail)
        
        if item_type not in summary:
            summary[item_type] = {"count": 0, "total_stock": 0, "total_value": 0}
            
        summary[item_type]["count"] += 1
        summary[item_type]["total_stock"] += stock
        summary[item_type]["total_value"] += value
        total_value += value
        
    return {"summary": summary, "details": details, "total_value": total_value}


@api_router.get("/reports/low-stock")
async def report_low_stock(current_user: dict = Depends(get_current_user)):
    """Low stock report"""
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    report = []
    
    for product in products:
        stock = await get_product_stock(product["id"])
        threshold = product.get("low_stock_threshold", 10)
        if stock < threshold:
            report.append({
                "product_id": product["id"],
                "product_name": product["name"],
                "sku": product.get("sku"),
                "current_stock": stock,
                "threshold": threshold,
                "shortage": threshold - stock
            })
    
    report.sort(key=lambda x: x["shortage"], reverse=True)
    return {"report": report, "count": len(report)}

@api_router.get("/reports/stock-movement")
async def report_stock_movement(product_id: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Stock movement report"""
    query = {}
    if product_id:
        query["product_id"] = product_id
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date
    
    movements = await db.stock_movements.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    
    # Batch-fetch product names to avoid N+1 query
    product_ids = list({m["product_id"] for m in movements if m.get("product_id")})
    products_map = {}
    if product_ids:
        prods = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(product_ids))
        products_map = {p["id"]: p["name"] for p in prods}
    for m in movements:
        m["product_name"] = products_map.get(m.get("product_id"), "Unknown")
    
    return {"movements": movements}

@api_router.get("/reports/batch-traceability")
async def report_batch_traceability(current_user: dict = Depends(get_current_user)):
    """Batch Traceability & Expiry Report"""
    products = await db.products.find({"track_batches": True}, {"_id": 0}).to_list(1000)
    report = []
    for product in products:
        batches = await db.batches.find({"product_id": product["id"], "current_stock": {"$gt": 0}}, {"_id": 0}).to_list(100)
        for b in batches:
            report.append({
                "product_id": product["id"],
                "product_name": product["name"],
                "batch_number": b["batch_number"],
                "expiry_date": b.get("expiry_date"),
                "current_stock": b["current_stock"]
            })
    report.sort(key=lambda x: str(x.get("expiry_date") or "9999-12-31"))
    return {"report": report}

@api_router.get("/reports/production-yield")
async def report_production_yield(current_user: dict = Depends(get_current_user)):
    """Production Yield / COGS Report"""
    orders = await db.production_orders.find({"status": "completed"}, {"_id": 0}).sort("end_date", -1).to_list(100)
    report = []
    for order in orders:
        product = await db.products.find_one({"id": order["output_product_id"]}, {"_id": 0, "name": 1, "cost_price": 1})
        if not product: continue
        qty = order.get("actual_output_qty") or order.get("target_output_qty", 0)
        fg_value = qty * product.get("cost_price", 0)
        raw_material_cost = sum((ing.get("consumed_qty") or ing.get("qty", 0)) * ing.get("unit_cost", 0) for ing in order.get("ingredients", []))
        report.append({
            "order_number": order["order_number"],
            "product_name": product["name"],
            "end_date": order.get("end_date"),
            "qty_produced": qty,
            "materials_cost": raw_material_cost,
            "fg_value": fg_value,
            "yield_variance": fg_value - raw_material_cost
        })
    return {"report": report}

@api_router.get("/reports/supplier-payables")
async def report_supplier_payables(current_user: dict = Depends(get_current_user)):
    """Supplier payables report"""
    suppliers = await db.suppliers.find({}, {"_id": 0}).to_list(1000)
    
    # Batch-compute supplier balances via aggregation (avoid N+1 per-supplier ledger calls)
    balance_pipeline = [
        {"$match": {"account": {"$regex": "^supplier:"}}},
        {"$group": {"_id": "$account", "total_debit": {"$sum": "$debit"}, "total_credit": {"$sum": "$credit"}}}
    ]
    balance_results = await db.ledger.aggregate(balance_pipeline).to_list(1000)
    balance_map = {r["_id"]: r["total_debit"] - r["total_credit"] for r in balance_results}
    
    report = []
    for supplier in suppliers:
        account_key = f"supplier:{supplier['id']}"
        balance = balance_map.get(account_key, 0.0)
        payable = max(0, -balance)
        if payable > 0:
            report.append({
                "supplier_id": supplier["id"],
                "supplier_name": supplier["name"],
                "phone": supplier.get("phone"),
                "payable": payable
            })
    
    report.sort(key=lambda x: x["payable"], reverse=True)
    total = sum(r["payable"] for r in report)
    
    return {"report": report, "total": total}

@api_router.get("/reports/profit")
async def report_profit(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Profit report"""
    query = {"status": {"$ne": "draft"}}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date
    
    invoices = await db.invoices.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    
    total_sales = sum(inv["total"] for inv in invoices)
    total_cost = sum(inv.get("total_cost", 0) for inv in invoices)
    gross_profit = total_sales - total_cost
    
    # Get expenses in same period
    exp_query = {}
    if start_date:
        exp_query["date"] = {"$gte": start_date}
    if end_date:
        exp_query.setdefault("date", {})["$lte"] = end_date
    
    expenses = await db.expenses.find(exp_query, {"_id": 0}).sort("date", -1).to_list(1000)
    total_expenses = sum(exp["amount"] for exp in expenses)
    
    net_profit = gross_profit - total_expenses
    
    return {
        "total_sales": total_sales,
        "total_cost": total_cost,
        "gross_profit": gross_profit,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "invoice_count": len(invoices),
        "margin_percent": (gross_profit / total_sales * 100) if total_sales > 0 else 0
    }

@api_router.get("/reports/profit-loss")
async def report_profit_loss(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Detailed Profit & Loss statement with category breakdown"""
    date_filter = {}
    if start_date:
        date_filter["$gte"] = start_date
    if end_date:
        date_filter["$lte"] = end_date
    
    inv_query = {"status": {"$ne": "draft"}}
    exp_query = {}
    cn_query = {}
    dn_query = {}
    if date_filter:
        inv_query["date"] = date_filter
        exp_query["date"] = date_filter
        cn_query["date"] = date_filter
        dn_query["date"] = date_filter
    
    # Income: invoices
    invoices = await db.invoices.find(inv_query, {"_id": 0}).sort("date", -1).to_list(1000)
    total_sales = sum(inv["total"] for inv in invoices)
    total_cost_of_goods = sum(inv.get("total_cost", 0) for inv in invoices)
    
    # Returns: credit notes (reduce income) & debit notes (reduce purchases cost)
    credit_notes = await db.credit_notes.find(cn_query, {"_id": 0}).sort("date", -1).to_list(1000)
    total_credit_notes = sum(cn["total"] for cn in credit_notes)
    
    debit_notes = await db.debit_notes.find(dn_query, {"_id": 0}).sort("date", -1).to_list(1000)
    total_debit_notes = sum(dn["total"] for dn in debit_notes)
    
    net_sales = total_sales - total_credit_notes
    net_cost = total_cost_of_goods - total_debit_notes
    gross_profit = net_sales - net_cost
    
    # Expenses grouped by category
    expenses = await db.expenses.find(exp_query, {"_id": 0}).sort("date", -1).to_list(1000)
    expense_categories = {}
    for exp in expenses:
        cat = exp.get("category", "Other") or "Other"
        expense_categories[cat] = expense_categories.get(cat, 0) + exp["amount"]
    
    total_expenses = sum(expense_categories.values())
    net_profit = gross_profit - total_expenses
    
    return {
        "income": {
            "total_sales": total_sales,
            "credit_notes": total_credit_notes,
            "net_sales": net_sales,
            "invoice_count": len(invoices)
        },
        "cost_of_goods": {
            "total_cost": total_cost_of_goods,
            "debit_notes": total_debit_notes,
            "net_cost": net_cost
        },
        "gross_profit": gross_profit,
        "expenses": {
            "categories": expense_categories,
            "total": total_expenses
        },
        "net_profit": net_profit,
        "margin_percent": (gross_profit / net_sales * 100) if net_sales > 0 else 0
    }

# ============== EXPORT ENDPOINTS ==============

def create_csv_response(data: list, filename: str, fieldnames: list) -> StreamingResponse:
    """Create CSV file response"""
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

def create_excel_response(data: list, filename: str, headers: list) -> StreamingResponse:
    """Create Excel file response"""
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

@api_router.get("/export/outstanding")
async def export_outstanding(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_outstanding(current_user)
    data = report["report"]
    
    if format == "excel":
        return create_excel_response(data, "outstanding_report.xlsx", ["customer_name", "phone", "outstanding"])
    return create_csv_response(data, "outstanding_report.csv", ["customer_name", "phone", "outstanding"])

@api_router.get("/export/credit")
async def export_credit(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_credit(current_user)
    data = report["report"]
    
    if format == "excel":
        return create_excel_response(data, "credit_report.xlsx", ["customer_name", "phone", "credit"])
    return create_csv_response(data, "credit_report.csv", ["customer_name", "phone", "credit"])

@api_router.get("/export/sales")
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
        return create_excel_response(data, "sales_report.xlsx", ["invoice_number", "customer_name", "date", "total", "paid_amount", "status"])
    return create_csv_response(data, "sales_report.csv", ["invoice_number", "customer_name", "date", "total", "paid_amount", "status"])

@api_router.get("/export/expenses")
async def export_expenses(start_date: Optional[str] = None, end_date: Optional[str] = None, format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_expenses(start_date, end_date, current_user)
    data = report["expenses"]
    
    if format == "excel":
        return create_excel_response(data, "expenses_report.xlsx", ["description", "category", "date", "amount", "mode"])
    return create_csv_response(data, "expenses_report.csv", ["description", "category", "date", "amount", "mode"])

@api_router.get("/export/inventory")
async def export_inventory(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_inventory(current_user)
    data = report["report"]
    
    if format == "excel":
        return create_excel_response(data, "inventory_report.xlsx", ["product_name", "sku", "current_stock", "cost_price", "selling_price", "value"])
    return create_csv_response(data, "inventory_report.csv", ["product_name", "sku", "current_stock", "cost_price", "selling_price", "value"])

@api_router.get("/export/profit")
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
        return create_excel_response(data, "profit_report.xlsx", ["metric", "value"])
    return create_csv_response(data, "profit_report.csv", ["metric", "value"])

# ============== SETTINGS & BACKUP ==============

@api_router.get("/settings/modules")
async def get_modules_settings(current_user: dict = Depends(get_current_user)):
    settings = await db.settings.find_one({"type": "modules"}, {"_id": 0})
    if not settings:
        return {
            "enable_credit_notes": True,
            "enable_debit_notes":  True,
            "enable_advanced_ims": False,
            "enable_production":   False,
        }
    # Ensure new boolean flags have defaults if missing from DB (migration safety)
    return {
        "enable_credit_notes": settings.get("enable_credit_notes", True),
        "enable_debit_notes":  settings.get("enable_debit_notes",  True),
        "enable_advanced_ims": settings.get("enable_advanced_ims", False),
        "enable_production":   settings.get("enable_production",   False),
    }

@api_router.put("/settings/modules")
async def update_modules_settings(settings: ModulesSettings, current_user: dict = Depends(get_current_user)):
    settings_doc = {
        "type": "modules",
        **settings.model_dump(),          # persist ALL fields from ModulesSettings
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.settings.update_one({"type": "modules"}, {"$set": settings_doc}, upsert=True)
    return {"message": "Module settings updated successfully"}

@api_router.get("/settings/s3")
async def get_s3_settings(current_user: dict = Depends(get_current_user)):
    settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if settings:
        # Mask the secret key
        settings["aws_secret_access_key"] = "********" if settings.get("aws_secret_access_key") else ""
    return settings or {"configured": False}

@api_router.post("/settings/s3")
async def save_s3_settings(settings: S3Settings, current_user: dict = Depends(get_current_user)):
    # Validate S3 connection
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.region
        )
        # Test connection by listing bucket
        s3_client.head_bucket(Bucket=settings.bucket_name)
    except NoCredentialsError:
        raise HTTPException(status_code=400, detail="Invalid AWS credentials")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            raise HTTPException(status_code=400, detail="Bucket not found")
        elif error_code == '403':
            raise HTTPException(status_code=400, detail="Access denied to bucket")
        raise HTTPException(status_code=400, detail=f"S3 error: {str(e)}")
    
    settings_doc = {
        "type": "s3",
        **settings.model_dump(),
        "configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.settings.update_one({"type": "s3"}, {"$set": settings_doc}, upsert=True)
    return {"message": "S3 settings saved and validated successfully"}

@api_router.post("/settings/s3/test")
async def test_s3_connection(settings: S3Settings, current_user: dict = Depends(get_current_user)):
    """Test S3 connection without saving"""
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.region
        )
        s3_client.head_bucket(Bucket=settings.bucket_name)
        return {"success": True, "message": "Connection successful"}
    except NoCredentialsError:
        return {"success": False, "message": "Invalid AWS credentials"}
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            return {"success": False, "message": "Bucket not found"}
        elif error_code == '403':
            return {"success": False, "message": "Access denied to bucket"}
        return {"success": False, "message": f"Error: {str(e)}"}

@api_router.get("/auth/config")
async def get_auth_config():
    """Get public authentication configuration"""
    settings = await db.settings.find_one({"type": "system"}, {"_id": 0})
    return {
        "registration_enabled": settings.get("registration_enabled", False) if settings else False
    }

@api_router.get("/settings/system")
async def get_system_settings(current_user: dict = Depends(get_current_user)):
    """Get system settings"""
    settings = await db.settings.find_one({"type": "system"}, {"_id": 0})
    if not settings:
        return {"registration_enabled": False}
    return settings

@api_router.post("/settings/system")
async def update_system_settings(settings: SystemSettings, current_user: dict = Depends(get_current_user)):
    """Update system settings"""
    settings_doc = {
        "type": "system",
        **settings.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.settings.update_one({"type": "system"}, {"$set": settings_doc}, upsert=True)
    return {"message": "System settings updated successfully"}

class SystemResetRequest(BaseModel):
    password: str

@api_router.post("/system/reset")
async def reset_system(req: SystemResetRequest, current_user: dict = Depends(get_current_user)):
    """Wipe all accounting data after verifying user password."""
    user = await db.users.find_one({"email": current_user.get("email")})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    hashed = user.get("password_hash") or user.get("password")
    if not hashed or not verify_password(req.password, hashed):
        raise HTTPException(status_code=401, detail="Incorrect password. Factory reset forbidden.")
        
    cols = await db.list_collection_names()
    exempt = ["users", "settings", "backup_logs", "s3"] # Keep logins, config, and backup logs
    
    deleted = {}
    for c in cols:
        if c not in exempt:
            res = await db[c].delete_many({})
            deleted[c] = res.deleted_count
            
    return {"message": "Factory reset complete. All accounting data has been permanently deleted.", "details": deleted}

@api_router.post("/backup/create")
async def create_backup(current_user: dict = Depends(get_current_user)):
    """Create encrypted backup and upload to S3"""
    if not MASTER_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Master encryption key not configured")
    
    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        raise HTTPException(status_code=400, detail="S3 not configured. Please configure S3 in settings.")
    
    # Collect all data
    collections = [
        "users", "business", "customers", "products", "suppliers", "invoices", 
        "payments", "expenses", "purchases", "ledger", "stock_movements", 
        "payment_allocations", "supplier_payments",
        "credit_notes", "debit_notes", "batches", "serial_numbers",
        "bill_of_materials", "production_orders", "advance_payments", "settings"
    ]
    
    backup_data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": "2.0",
        "collections": {}
    }
    
    for collection in collections:
        docs = await db[collection].find({}, {"_id": 0}).to_list(10000)
        backup_data["collections"][collection] = docs
    
    # Encrypt the backup
    json_data = json.dumps(backup_data).encode()
    encrypted_package = encrypt_data(json_data, MASTER_ENCRYPTION_KEY)
    
    # Upload to S3
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_settings["aws_access_key_id"],
            aws_secret_access_key=s3_settings["aws_secret_access_key"],
            region_name=s3_settings.get("region", "us-east-1")
        )
        
        backup_filename = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.enc"
        s3_client.put_object(
            Bucket=s3_settings["bucket_name"],
            Key=f"ez-accounts-backups/{backup_filename}",
            Body=json.dumps(encrypted_package).encode(),
            ContentType="application/json"
        )
        
        # Log backup
        await db.backup_logs.insert_one({
            "id": str(uuid.uuid4()),
            "filename": backup_filename,
            "size_bytes": len(json_data),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "success"
        })
        
        return {"message": "Backup created successfully", "filename": backup_filename}
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")

@api_router.get("/backup/list")
async def list_backups(current_user: dict = Depends(get_current_user)):
    """List available backups from S3"""
    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        return {"backups": [], "message": "S3 not configured"}
    
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_settings["aws_access_key_id"],
            aws_secret_access_key=s3_settings["aws_secret_access_key"],
            region_name=s3_settings.get("region", "us-east-1")
        )
        
        response = s3_client.list_objects_v2(
            Bucket=s3_settings["bucket_name"],
            Prefix="ez-accounts-backups/"
        )
        
        backups = []
        for obj in response.get("Contents", []):
            backups.append({
                "filename": obj["Key"].replace("ez-accounts-backups/", ""),
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat()
            })
        
        backups.sort(key=lambda x: x["last_modified"], reverse=True)
        return {"backups": backups}
    except Exception as e:
        return {"backups": [], "error": str(e)}

@api_router.post("/backup/restore/{filename}")
async def restore_backup(filename: str, current_user: dict = Depends(get_current_user)):
    """Restore from encrypted backup"""
    if not MASTER_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Master encryption key not configured")
    
    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        raise HTTPException(status_code=400, detail="S3 not configured")
    
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_settings["aws_access_key_id"],
            aws_secret_access_key=s3_settings["aws_secret_access_key"],
            region_name=s3_settings.get("region", "us-east-1")
        )
        
        response = s3_client.get_object(
            Bucket=s3_settings["bucket_name"],
            Key=f"ez-accounts-backups/{filename}"
        )
        
        encrypted_package = json.loads(response["Body"].read().decode())
        decrypted_data = decrypt_data(encrypted_package, MASTER_ENCRYPTION_KEY)
        backup_data = json.loads(decrypted_data.decode())
        
        # Restore collections.
        # 'settings' is excluded to preserve current S3/system config.
        # 'users' is excluded to prevent restoring stale passwords/accounts over live users.
        restore_exempt = {"settings", "users"}
        for collection, docs in backup_data["collections"].items():
            if collection not in restore_exempt and docs:
                await db[collection].delete_many({})
                await db[collection].insert_many(docs)
        
        return {"message": "Backup restored successfully", "restored_at": backup_data.get("created_at")}
    except Exception as e:
        logger.error(f"Restore failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

# Include the router
# ============== PHASE 3: FINANCIAL REPORTS & MAINTENANCE ==============

@api_router.post("/maintenance/fix-ledger")
async def fix_ledger_data(current_user: dict = Depends(get_current_user)):
    """One-time fix to ensure double-entry bookkeeping for historical data"""
    fixed_counts = {"invoices": 0, "purchases": 0, "expenses": 0}
    
    # 1. Fix Invoices (Credit Sales)
    invoices = await db.invoices.find({"status": {"$ne": "draft"}}).to_list(None)
    for inv in invoices:
        exists = await db.ledger.find_one({
            "ref_id": inv["id"], 
            "account": "sales"
        })
        if not exists:
            await create_ledger_entry(
                account="sales",
                debit=0,
                credit=inv["total"],
                narration=f"Invoice {inv['invoice_number']} (Retroactive Fix)",
                ref_type="invoice",
                ref_id=inv["id"],
                date=inv["date"]
            )
            fixed_counts["invoices"] += 1

    # 2. Fix Purchases (Debit Purchases)
    purchases = await db.purchases.find({}).to_list(None)
    for pur in purchases:
        exists = await db.ledger.find_one({
            "ref_id": pur["id"], 
            "account": "purchases"
        })
        if not exists:
            await create_ledger_entry(
                account="purchases",
                debit=pur["total"],
                credit=0,
                narration=f"Purchase {pur['purchase_number']} (Retroactive Fix)",
                ref_type="purchase",
                ref_id=pur["id"],
                date=pur["date"]
            )
            fixed_counts["purchases"] += 1

    # 3. Fix Expenses (Debit Expense Category)
    expenses = await db.expenses.find({}).to_list(None)
    for exp in expenses:
        exists = await db.ledger.find_one({
            "ref_id": exp["id"], 
            "account": {"$regex": "^expense:"}
        })
        if not exists:
            await create_ledger_entry(
                account=f"expense:{exp['category']}",
                debit=exp["amount"],
                credit=0,
                narration=f"Expense: {exp['description']} (Retroactive Fix)",
                ref_type="expense",
                ref_id=exp["id"],
                date=exp["date"]
            )
            fixed_counts["expenses"] += 1

    # 4. Fix Setup (Credit Capital)
    business = await db.business.find_one({})
    if business:
        # Check cash capital
        if business.get("opening_cash", 0) > 0:
             exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "narration": "Opening capital (cash)"})
             if not exists:
                 await create_ledger_entry("capital", 0, business["opening_cash"], "Opening capital (cash)", "setup", business["id"], business.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
                 fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1
        
        # Check bank capital
        if business.get("opening_bank", 0) > 0:
             exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "narration": "Opening capital (bank)"})
             if not exists:
                 await create_ledger_entry("capital", 0, business["opening_bank"], "Opening capital (bank)", "setup", business["id"], business.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
                 fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1

    # 5. Fix Supplier Opening Balance (Debit Capital)
    suppliers = await db.suppliers.find({"opening_balance": {"$gt": 0}}).to_list(None)
    for sup in suppliers:
        exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "ref_id": sup["id"]})
        if not exists:
            # Liability -> Debit Capital
            await create_ledger_entry("capital", sup["opening_balance"], 0, "Opening capital (supplier)", "setup", sup["id"], sup.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1

    # 6. Fix Customer Opening Balance
    customers = await db.customers.find({"opening_balance": {"$gt": 0}}).to_list(None)
    for cust in customers:
        exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "ref_id": cust["id"]})
        if not exists:
            # Check balance type
            if cust.get("balance_type", "debit") == "debit":
                # Asset -> Credit Capital
                await create_ledger_entry("capital", 0, cust["opening_balance"], "Opening capital (customer)", "setup", cust["id"], cust.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            else:
                # Liability -> Debit Capital
                await create_ledger_entry("capital", cust["opening_balance"], 0, "Opening capital (customer)", "setup", cust["id"], cust.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1
            
    # 7. Fix Payments (Debit Cash/Bank, Credit Customer)
    payments = await db.payments.find({}).to_list(None)
    for pay in payments:
        # Check Debit (Cash/Bank)
        exists_dr = await db.ledger.find_one({"ref_type": "payment", "ref_id": pay["id"], "debit": pay["amount"]})
        if not exists_dr:
             await create_ledger_entry(pay["mode"], pay["amount"], 0, f"Payment from {pay['customer_name']}", "payment", pay["id"], pay["date"])
             fixed_counts["payments"] = fixed_counts.get("payments", 0) + 1
        
        # Check Credit (Customer)
        exists_cr = await db.ledger.find_one({"ref_type": "payment", "ref_id": pay["id"], "credit": pay["amount"]})
        if not exists_cr:
             # Credit Customer
             await create_ledger_entry(f"customer:{pay['customer_id']}", 0, pay["amount"], "Payment received", "payment", pay["id"], pay["date"])
             fixed_counts["payments"] = fixed_counts.get("payments", 0) + 1

    return {"message": "Ledger fixed successfully", "counts": fixed_counts}

@api_router.get("/reports/trial-balance")
async def get_trial_balance(current_user: dict = Depends(get_current_user)):
    """Get Trial Balance (Sum of distinct accounts)"""
    pipeline = [
        {"$group": {
            "_id": "$account",
            "debit": {"$sum": "$debit"},
            "credit": {"$sum": "$credit"}
        }},
        {"$project": {
            "account": "$_id",
            "debit": 1,
            "credit": 1,
            "balance": {"$subtract": ["$debit", "$credit"]},
            "_id": 0
        }},
        {"$sort": {"account": 1}}
    ]
    
    entries = await db.ledger.aggregate(pipeline).to_list(None)
    
    total_debit = sum(e["debit"] for e in entries)
    total_credit = sum(e["credit"] for e in entries)
    
    return {
        "entries": entries,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": abs(total_debit - total_credit) < 0.01
    }

@api_router.get("/reports/balance-sheet")
async def get_balance_sheet(current_user: dict = Depends(get_current_user)):
    """Get Balance Sheet (Assets, Liabilities, Equity)"""
    
    # 1. Calculate Ledger Balances
    pipeline = [
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}}
        }}
    ]
    balances = {doc["_id"]: doc["balance"] for doc in await db.ledger.aggregate(pipeline).to_list(None)}
    
    # helper
    def get_bal(key): return balances.get(key, 0)
    def get_prefix_sum(prefix): return sum(v for k, v in balances.items() if k.startswith(prefix))

    # 2. Assets
    # Cash & Bank
    cash = get_bal("cash")
    bank = get_bal("bank")
    
    # Accounts Receivable (Sum of all customer:* accounts)
    accounts_receivable = get_prefix_sum("customer:")
    
    # Inventory Value (Calculated from Products, not Ledger, for accuracy in this simplified system)
    # Note: In a pure double-entry, we would track this in ledger, but here we use Periodic Inventory for P&L
    # and "Stock on Hand" for Balance Sheet. 
    # To balance the equation, "Closing Stock" affects Equity (Retained Earnings).
    products = await db.products.find({}, {"cost_price": 1, "stock": 1}).to_list(None)
    inventory_value = sum((p.get("cost_price", 0) or 0) * (p.get("stock", 0) or 0) for p in products)

    total_assets = cash + bank + accounts_receivable + inventory_value
    
    # 3. Liabilities
    # Accounts Payable (Sum of all supplier:* accounts)
    # Note: Supplier accounts are usually Credit balance (negative in our logic? No, Ledger logic: Debit - Credit)
    # If using Debit - Credit:
    # Asset (Debit nature): Positive
    # Liability (Credit nature): Negative
    # Income (Credit nature): Negative
    # Expense (Debit nature): Positive
    
    # So AP will be negative. We want to show it as positive Liability.
    accounts_payable_raw = get_prefix_sum("supplier:")
    accounts_payable = -accounts_payable_raw # Flip sign to show as positive liability amount
    
    # Customer Credits (Liability)
    customer_credits_raw = get_prefix_sum("customer_credit:")
    customer_credits = -customer_credits_raw
    
    total_liabilities = accounts_payable + customer_credits
    
    # 4. Equity
    # Net Profit = Income - Expenses
    # Income (Credit nature, so negative)
    sales = -get_bal("sales")
    
    # Expenses (Debit nature, so positive)
    purchases = get_bal("purchases")
    expenses_total = get_prefix_sum("expense:")
    
    # COGS for P&L = Opening Stock + Purchases - Closing Stock
    # For Balance Sheet Equity, we typically add Net Profit.
    # Net Profit = Sales - (Purchases - Change in Inventory) - Expenses
    # Change in Inventory = Closing Stock - Opening Stock
    # Simplified: Net Profit = Sales - Purchases - Expenses + (Closing Stock - Opening Stock)
    # We assume Opening Stock was 0 or handled in Capital. simpler:
    # Equity = Capital + Retained Earnings
    # Retained Earnings = Net Profit
    
    # Let's calculate Net Profit correctly
    # Opening Stock? We don't verify date range here, it's "As of Today".
    # So Opening Stock is effectively 0 (start of time).
    opening_stock = 0 
    closing_stock = inventory_value
    
    cost_of_goods_sold = opening_stock + purchases - closing_stock
    gross_profit = sales - cost_of_goods_sold
    net_profit = gross_profit - expenses_total
    
    # Capital (if we had it). For now, Equity matches Assets - Liabilities
    # Equity = Total Assets - Total Liabilities
    # Check: Does Net Profit match this?
    # Assets = Liab + Equity
    # Equity = Assets - Liab
    # Equity = (Cash + Bank + AR + STOCK) - (AP + Credits)
    # Net Profit = Sales - (Purchases - STOCK) - Expenses
    #            = Sales - Purchases + STOCK - Expenses
    # Ledger Equation:
    # 0 = Cash + Bank + AR + Exp + Pur + AP_raw + Sales_raw + Capital_raw
    # 0 = (Cash+Bank+AR) + (Exp+Pur) + (-AP) + (-Sales)
    # => Cash+Bank+AR = AP + Sales - Exp - Pur
    # Add Stock to both sides?
    # Assets = (Cash+Bank+AR) + Stock
    #        = AP + Sales - Exp - Pur + Stock
    #        = AP + (Sales - Exp - Pur + Stock)
    #        = Liab + Net Profit
    # Yes! It balances!
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    opening_stock = 0 
    closing_stock = inventory_value
    
    cost_of_goods_sold = opening_stock + purchases - closing_stock
    gross_profit = sales - cost_of_goods_sold
    net_profit = gross_profit - expenses_total
    
    # Capital
    capital = -get_bal("capital")
    
    total_equity = net_profit + capital
    
    return {
        "assets": {
            "cash": cash,
            "bank": bank,
            "accounts_receivable": accounts_receivable,
            "inventory": inventory_value,
            "total": total_assets
        },
        "liabilities": {
            "accounts_payable": accounts_payable,
            "customer_credits": customer_credits,
            "total": total_liabilities
        },
        "equity": {
            "net_profit": net_profit,
            "total": total_equity
        },
        "is_balanced": abs(total_assets - (total_liabilities + total_equity)) < 1.0
    }

# ============== AI FEATURES ==============

@api_router.post("/ai/parse-invoice")
async def parse_invoice_endpoint(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    try:
        content_type = file.content_type
        
        # Check if it's an image or PDF
        if content_type not in ["image/jpeg", "image/png", "application/pdf"]:
            # For now, simplistic check. gpt-4o handles images best. PDF needs conversion or preview.
            # If PDF, we might need to convert to image first or extract text. 
            # For this MVP, let's assume Images. If PDF, we might return error or try.
            pass

        data = await parse_invoice_image(file)
        return data

    except Exception as e:
        logger.error(f"AI Parse Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== VOICE ASSISTANT WEBSOCKET ENDPOINT ==============

@app.websocket("/ws/voice")
async def voice_assistant_websocket(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket endpoint for voice assistant.
    
    Handles real-time bidirectional communication for voice commands.
    Supports both text and audio streaming.
    
    Usage:
        ws://localhost:8000/ws/voice?token=<jwt_token>
    """
    # Authenticate user
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return
    
    try:
        # Verify JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008, reason="Invalid token")
            return
    except JWTError:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    # Connect and create/resume session
    try:
        session = await ws_session_manager.connect(user_id, websocket)
        logger.info(f"Voice assistant connected: user={user_id}, session={session.session_id}")
        
        # Main message loop
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            # Process message
            response = await ws_session_manager.process_message(user_id, data)
            
            # Send response back
            await websocket.send_json(response)
            
    except WebSocketDisconnect:
        logger.info(f"Voice assistant disconnected: user={user_id}")
        await ws_session_manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Voice assistant error: user={user_id}, error={str(e)}")
        await ws_session_manager.disconnect(user_id)
        await websocket.close(code=1011, reason="Internal error")


@api_router.get("/voice/stats")
async def get_voice_stats(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get voice assistant statistics.
    
    Returns:
        Active sessions, states, etc.
    """
    # Verify token
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    stats = ws_session_manager.get_session_stats()
    return stats


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

