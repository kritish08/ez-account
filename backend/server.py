from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import base64
import secrets
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Union
import uuid
from datetime import datetime, timezone, timedelta
from jose import JWTError, jwt
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from openpyxl import Workbook
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import csv
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
SECRET_KEY = os.environ.get('JWT_SECRET', 'ez-accounts-secret-key-change-in-production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Master Encryption Key for backups
MASTER_ENCRYPTION_KEY = os.environ.get('MASTER_ENCRYPTION_KEY', '')

# Password hashing
security = HTTPBearer()

app = FastAPI(title="EZ Accounts by Kyrex API", version="2.0.0")
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============== PYDANTIC MODELS ==============

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class BusinessSetup(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    gstin: Optional[str] = None
    financial_year_start: str = "April"
    opening_cash: float = 0
    opening_bank: float = 0

class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    opening_balance: float = 0
    balance_type: str = "debit"

class ProductCreate(BaseModel):
    name: str
    sku: Optional[str] = None
    selling_price: float
    cost_price: float = 0
    opening_stock: float = 0
    low_stock_threshold: float = 10

class SupplierCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    opening_balance: float = 0

class PurchaseItem(BaseModel):
    product_id: str
    quantity: float
    cost_price: float

class PurchaseCreate(BaseModel):
    supplier_id: Optional[str] = None
    items: List[PurchaseItem]
    payment_status: str = "unpaid"  # cash, bank, unpaid
    date: Optional[str] = None
    notes: Optional[str] = None

class InvoiceLineItem(BaseModel):
    product_id: Optional[str] = None  # None for free-text items
    description: str
    quantity: float
    rate: float

class InvoiceCreate(BaseModel):
    customer_id: str
    items: List[InvoiceLineItem]
    notes: Optional[str] = None
    date: Optional[str] = None
    is_draft: bool = False

class InvoiceUpdate(BaseModel):
    items: List[InvoiceLineItem]
    notes: Optional[str] = None
    date: Optional[str] = None

class PaymentCreate(BaseModel):
    customer_id: str
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

class S3Settings(BaseModel):
    aws_access_key_id: str
    aws_secret_access_key: str
    bucket_name: str
    region: str = "us-east-1"

class SystemSettings(BaseModel):
    registration_enabled: bool = False

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
    """Get customer's available credit (advance/overpayment)"""
    balance = await get_account_balance(f"customer_credit:{customer_id}")
    return max(0, -balance)  # Credit is stored as negative (credit side)

async def apply_credit_to_invoice(customer_id: str, invoice_id: str, invoice_total: float) -> tuple:
    """Apply available credit to invoice. Returns (amount_due, credit_applied)."""
    credit = await get_customer_credit(customer_id)
    if credit <= 0:
        return invoice_total, 0
    
    apply_amount = min(credit, invoice_total)
    
    # Reduce credit (debit the credit account)
    await create_ledger_entry(
        account=f"customer_credit:{customer_id}",
        debit=apply_amount,
        credit=0,
        narration=f"Credit applied to invoice",
        ref_type="invoice_credit",
        ref_id=invoice_id
    )
    
    # Update invoice
    new_paid = apply_amount
    new_status = "paid" if new_paid >= invoice_total else "partially_paid"
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"paid_amount": new_paid, "status": new_status, "credit_applied": apply_amount}}
    )
    
    return invoice_total - apply_amount, apply_amount

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

async def create_stock_movement(product_id: str, quantity_in: float, quantity_out: float, ref_type: str, ref_id: str, date: str = None):
    """Record stock movement"""
    movement = {
        "id": str(uuid.uuid4()),
        "product_id": product_id,
        "quantity_in": quantity_in,
        "quantity_out": quantity_out,
        "ref_type": ref_type,
        "ref_id": ref_id,
        "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.stock_movements.insert_one(movement)
    return movement

async def delete_stock_movements(ref_type: str, ref_id: str):
    """Delete all stock movements for a reference"""
    await db.stock_movements.delete_many({"ref_type": ref_type, "ref_id": ref_id})

# ============== AUTH ROUTES ==============

@api_router.post("/auth/register", response_model=Token)
async def register(user: UserCreate):
    # Check if registration is enabled
    settings = await db.settings.find_one({"type": "system"})
    if not settings or not settings.get("registration_enabled", False):
        raise HTTPException(status_code=403, detail="Registration is currently closed")

    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": user.email,
        "password_hash": get_password_hash(user.password),
        "name": user.name,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user_doc)
    
    access_token = create_access_token(data={"sub": user_id})
    return {"access_token": access_token, "token_type": "bearer"}

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
        if business.opening_bank > 0:
            await create_ledger_entry("bank", business.opening_bank, 0, "Opening bank balance", "setup", business_doc["id"], today)
    
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
async def list_products(current_user: dict = Depends(get_current_user)):
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    
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
    
    return {"message": "Supplier created", "id": supplier_id}

@api_router.get("/suppliers")
async def list_suppliers(current_user: dict = Depends(get_current_user)):
    suppliers = await db.suppliers.find({}, {"_id": 0}).to_list(1000)
    
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
        await create_stock_movement(item.product_id, item.quantity, 0, "purchase", purchase_id, purchase_date)
    
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
    
    return {"message": "Purchase recorded", "id": purchase_id, "purchase_number": purchase_number}

@api_router.get("/purchases")
async def list_purchases(current_user: dict = Depends(get_current_user)):
    purchases = await db.purchases.find({}, {"_id": 0}).sort("date", -1).to_list(1000)
    return purchases

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
        else:
            await create_ledger_entry(f"customer_credit:{customer_id}", 0, customer.opening_balance, "Opening credit balance", "setup", customer_id, today)
    
    return {"message": "Customer created", "id": customer_id}

@api_router.get("/customers")
async def list_customers(current_user: dict = Depends(get_current_user)):
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)
    
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
    
    update_data = customer.model_dump()
    del update_data["opening_balance"]
    del update_data["balance_type"]
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.customers.update_one({"id": customer_id}, {"$set": update_data})
    return {"message": "Customer updated"}

@api_router.get("/customers/{customer_id}/ledger")
async def get_customer_ledger(customer_id: str, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    entries = await db.ledger.find(
        {"account": {"$in": [f"customer:{customer_id}", f"customer_credit:{customer_id}"]}},
        {"_id": 0}
    ).sort("date", 1).to_list(1000)
    
    ledger = []
    running_balance = 0
    
    for entry in entries:
        if entry["account"].startswith("customer:") and not entry["account"].startswith("customer_credit:"):
            running_balance += entry["debit"] - entry["credit"]
            
            if entry["debit"] > 0:
                description = f"Sale - {entry['narration']}"
                amount = entry["debit"]
                type_ = "sale"
            else:
                description = f"Payment received - {entry['narration']}"
                amount = entry["credit"]
                type_ = "payment"
        else:
            if entry["credit"] > 0:
                description = f"Credit added - {entry['narration']}"
                amount = entry["credit"]
                type_ = "credit_added"
            else:
                description = f"Credit used - {entry['narration']}"
                amount = entry["debit"]
                type_ = "credit_used"
        
        ledger.append({
            "date": entry["date"],
            "description": description,
            "amount": amount,
            "type": type_,
            "balance": running_balance
        })
    
    return {"customer": customer, "ledger": ledger, "current_balance": running_balance}

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
        
        # Reduce stock for product items
        for item in items:
            if item.get("product_id"):
                await create_stock_movement(item["product_id"], 0, item["quantity"], "invoice", invoice_id, invoice_date)
        
        # Auto-apply customer credit
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
        
        # Create new stock movements
        for item in items:
            if item.get("product_id"):
                await create_stock_movement(item["product_id"], 0, item["quantity"], "invoice", invoice_id, invoice_date)
        
        # Re-apply customer credit
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
async def publish_invoice(invoice_id: str, current_user: dict = Depends(get_current_user)):
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
            await create_stock_movement(item["product_id"], 0, item["quantity"], "invoice", invoice_id, invoice_date)
    
    # Apply customer credit
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
async def list_invoices(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if status:
        query["status"] = status
    
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
    
    await create_ledger_entry(
        account=f"customer:{payment.customer_id}",
        debit=0,
        credit=payment.amount,
        narration=f"Payment received",
        ref_type="payment",
        ref_id=payment_id,
        date=payment_date
    )
    
    excess = await apply_payment_fifo(payment.customer_id, payment.amount, payment_id)
    
    if excess > 0:
        await create_ledger_entry(
            account=f"customer_credit:{payment.customer_id}",
            debit=0,
            credit=excess,
            narration="Advance/Overpayment",
            ref_type="payment",
            ref_id=payment_id,
            date=payment_date
        )
    
    return {"message": "Payment recorded", "id": payment_id, "excess_as_credit": excess}

@api_router.get("/payments")
async def list_payments(current_user: dict = Depends(get_current_user)):
    payments = await db.payments.find({}, {"_id": 0}).sort("date", -1).to_list(1000)
    return payments

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
    
    return {"message": "Supplier payment recorded", "id": payment_id}

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
    
    return {"message": "Expense recorded", "id": expense_id}

@api_router.get("/expenses")
async def list_expenses(current_user: dict = Depends(get_current_user)):
    expenses = await db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(1000)
    return expenses

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
    for p in products:
        stock = await get_product_stock(p["id"])
        if stock < p.get("low_stock_threshold", 10):
            low_stock_count += 1
    
    recent_invoices = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(5)
    recent_payments = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(5)
    
    return {
        "cash_balance": cash_balance,
        "bank_balance": bank_balance,
        "total_outstanding": total_outstanding,
        "total_credit": total_credit,
        "total_payable": total_payable,
        "today_sales": today_sales,
        "monthly_sales": monthly_sales,
        "low_stock_count": low_stock_count,
        "recent_invoices": recent_invoices,
        "recent_payments": recent_payments
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
    profit = total - total_cost
    
    return {
        "invoices": invoices,
        "total_sales": total,
        "total_collected": collected,
        "pending": total - collected,
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
    
    # Enrich with product names
    for m in movements:
        product = await db.products.find_one({"id": m["product_id"]}, {"_id": 0, "name": 1})
        m["product_name"] = product["name"] if product else "Unknown"
    
    return {"movements": movements}

@api_router.get("/reports/supplier-payables")
async def report_supplier_payables(current_user: dict = Depends(get_current_user)):
    """Supplier payables report"""
    suppliers = await db.suppliers.find({}, {"_id": 0}).to_list(1000)
    report = []
    
    for supplier in suppliers:
        balance = await get_account_balance(f"supplier:{supplier['id']}")
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
    
    expenses = await db.expenses.find(exp_query, {"_id": 0}).to_list(1000)
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

@api_router.post("/backup/create")
async def create_backup(current_user: dict = Depends(get_current_user)):
    """Create encrypted backup and upload to S3"""
    if not MASTER_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Master encryption key not configured")
    
    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        raise HTTPException(status_code=400, detail="S3 not configured. Please configure S3 in settings.")
    
    # Collect all data
    collections = ["users", "business", "customers", "products", "suppliers", "invoices", 
                   "payments", "expenses", "purchases", "ledger", "stock_movements", 
                   "payment_allocations", "supplier_payments"]
    
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
        
        # Restore collections (except settings to preserve S3 config)
        for collection, docs in backup_data["collections"].items():
            if collection != "settings" and docs:
                await db[collection].delete_many({})
                await db[collection].insert_many(docs)
        
        return {"message": "Backup restored successfully", "restored_at": backup_data.get("created_at")}
    except Exception as e:
        logger.error(f"Restore failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

# Include the router
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
