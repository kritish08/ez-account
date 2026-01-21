from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from jose import JWTError, jwt
from passlib.context import CryptContext
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

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

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app = FastAPI(title="EZ Accounts API", version="1.0.0")
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============== MODELS ==============

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
    balance_type: str = "debit"  # debit = they owe us, credit = we owe them / advance

class LineItem(BaseModel):
    description: str
    quantity: float
    rate: float

class InvoiceCreate(BaseModel):
    customer_id: str
    items: List[LineItem]
    notes: Optional[str] = None
    date: Optional[str] = None

class PaymentCreate(BaseModel):
    customer_id: str
    amount: float
    mode: str  # cash or bank
    date: Optional[str] = None
    notes: Optional[str] = None

class ExpenseCreate(BaseModel):
    description: str
    amount: float
    mode: str  # cash or bank
    category: Optional[str] = None
    date: Optional[str] = None

# ============== AUTH HELPERS ==============

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

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
    last_invoice = await db.invoices.find_one({}, {"_id": 0, "invoice_number": 1}, sort=[("invoice_number", -1)])
    if last_invoice:
        try:
            last_num = int(last_invoice["invoice_number"].replace("INV-", ""))
            return f"INV-{str(last_num + 1).zfill(5)}"
        except:
            pass
    return "INV-00001"

async def apply_payment_fifo(customer_id: str, amount: float, payment_id: str):
    """Apply payment to oldest unpaid invoices first (FIFO)"""
    remaining = amount
    
    # Get unpaid invoices sorted by date (oldest first)
    invoices = await db.invoices.find(
        {"customer_id": customer_id, "status": {"$ne": "paid"}},
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
        
        # Record allocation
        await db.payment_allocations.insert_one({
            "id": str(uuid.uuid4()),
            "payment_id": payment_id,
            "invoice_id": invoice["id"],
            "amount": apply_amount,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        remaining -= apply_amount
    
    return remaining  # Returns excess if any

async def get_customer_credit(customer_id: str) -> float:
    """Get customer's available credit (advance/overpayment)"""
    return await get_account_balance(f"customer_credit:{customer_id}")

async def apply_credit_to_invoice(customer_id: str, invoice_id: str, invoice_total: float) -> float:
    """Apply available credit to new invoice. Returns amount still due."""
    credit = await get_customer_credit(customer_id)
    if credit <= 0:
        return invoice_total
    
    apply_amount = min(credit, invoice_total)
    
    # Reduce credit
    await create_ledger_entry(
        account=f"customer_credit:{customer_id}",
        debit=apply_amount,
        credit=0,
        narration=f"Credit applied to invoice",
        ref_type="invoice",
        ref_id=invoice_id
    )
    
    # Update invoice
    new_paid = apply_amount
    new_status = "paid" if new_paid >= invoice_total else "partially_paid"
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"paid_amount": new_paid, "status": new_status, "credit_applied": apply_amount}}
    )
    
    return invoice_total - apply_amount

# ============== AUTH ROUTES ==============

@api_router.post("/auth/register", response_model=Token)
async def register(user: UserCreate):
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
        
        # Initialize ledger with opening balances
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
    
    # Create opening balance ledger entry
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if customer.opening_balance > 0:
        if customer.balance_type == "debit":
            # Customer owes us
            await create_ledger_entry(f"customer:{customer_id}", customer.opening_balance, 0, "Opening balance", "setup", customer_id, today)
        else:
            # We owe customer (advance)
            await create_ledger_entry(f"customer_credit:{customer_id}", 0, customer.opening_balance, "Opening credit balance", "setup", customer_id, today)
    
    return {"message": "Customer created", "id": customer_id}

@api_router.get("/customers")
async def list_customers(current_user: dict = Depends(get_current_user)):
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)
    
    # Add outstanding and credit info
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
    """Get customer ledger with simple language descriptions"""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get all ledger entries for this customer
    entries = await db.ledger.find(
        {"account": {"$in": [f"customer:{customer_id}", f"customer_credit:{customer_id}"]}},
        {"_id": 0}
    ).sort("date", 1).to_list(1000)
    
    # Format for simple understanding
    ledger = []
    running_balance = 0
    
    for entry in entries:
        if entry["account"].startswith("customer:"):
            # Regular outstanding account
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
            # Credit account
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
    
    # Calculate totals
    items = [item.model_dump() for item in invoice.items]
    for item in items:
        item["amount"] = item["quantity"] * item["rate"]
    total = sum(item["amount"] for item in items)
    
    invoice_date = invoice.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    invoice_doc = {
        "id": invoice_id,
        "invoice_number": invoice_number,
        "customer_id": invoice.customer_id,
        "customer_name": customer["name"],
        "items": items,
        "total": total,
        "paid_amount": 0,
        "credit_applied": 0,
        "status": "unpaid",
        "notes": invoice.notes,
        "date": invoice_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.invoices.insert_one(invoice_doc)
    
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
    
    # Auto-apply customer credit if available
    amount_due = await apply_credit_to_invoice(invoice.customer_id, invoice_id, total)
    
    # Refresh invoice doc
    invoice_doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    
    return {"message": "Invoice created", "id": invoice_id, "invoice_number": invoice_number, "amount_due": amount_due}

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
    
    # Generate PDF using reportlab
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#4338ca'), spaceAfter=20)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#64748b'), spaceAfter=10)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#0f172a'))
    
    # Business Name
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
    
    # Invoice Header
    elements.append(Paragraph(f"INVOICE: {invoice['invoice_number']}", ParagraphStyle('InvNum', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#0f172a'))))
    elements.append(Paragraph(f"Date: {invoice['date']}", normal_style))
    elements.append(Paragraph(f"Status: {invoice['status'].replace('_', ' ').title()}", normal_style))
    
    elements.append(Spacer(1, 20))
    
    # Bill To
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
    
    # Items Table
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
    
    # Totals
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
    
    # Notes
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
    
    # Ledger: Debit Cash/Bank, Credit Customer
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
    
    # Apply payment to invoices (FIFO)
    excess = await apply_payment_fifo(payment.customer_id, payment.amount, payment_id)
    
    # If excess, store as customer credit
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
    
    # Ledger: Credit Cash/Bank (money going out)
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
    
    # Get balances
    cash_balance = await get_account_balance("cash")
    bank_balance = await get_account_balance("bank")
    
    # Customer totals
    customers = await db.customers.find({}, {"_id": 0, "id": 1}).to_list(1000)
    total_outstanding = 0
    total_credit = 0
    for c in customers:
        total_outstanding += max(0, await get_account_balance(f"customer:{c['id']}"))
        total_credit += max(0, await get_customer_credit(c["id"]))
    
    # Today's sales
    today_invoices = await db.invoices.find({"date": today}, {"_id": 0, "total": 1}).to_list(1000)
    today_sales = sum(inv["total"] for inv in today_invoices)
    
    # Monthly sales
    month_invoices = await db.invoices.find({"date": {"$gte": month_start}}, {"_id": 0, "total": 1}).to_list(1000)
    monthly_sales = sum(inv["total"] for inv in month_invoices)
    
    # Recent activity
    recent_invoices = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(5)
    recent_payments = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(5)
    
    return {
        "cash_balance": cash_balance,
        "bank_balance": bank_balance,
        "total_outstanding": total_outstanding,
        "total_credit": total_credit,
        "today_sales": today_sales,
        "monthly_sales": monthly_sales,
        "recent_invoices": recent_invoices,
        "recent_payments": recent_payments
    }

# ============== REPORTS ==============

@api_router.get("/reports/outstanding")
async def report_outstanding(current_user: dict = Depends(get_current_user)):
    """Customer outstanding report"""
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
    """Customer credit/advance report"""
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
    """Sales report"""
    query = {}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date
    
    invoices = await db.invoices.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    total = sum(inv["total"] for inv in invoices)
    collected = sum(inv.get("paid_amount", 0) for inv in invoices)
    
    return {"invoices": invoices, "total_sales": total, "total_collected": collected, "pending": total - collected}

@api_router.get("/reports/expenses")
async def report_expenses(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Expenses report"""
    query = {}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date
    
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    total = sum(exp["amount"] for exp in expenses)
    
    # Group by category
    by_category = {}
    for exp in expenses:
        cat = exp.get("category") or "Other"
        by_category[cat] = by_category.get(cat, 0) + exp["amount"]
    
    return {"expenses": expenses, "total": total, "by_category": by_category}

@api_router.get("/reports/cash-bank")
async def report_cash_bank(current_user: dict = Depends(get_current_user)):
    """Cash and bank summary"""
    cash_balance = await get_account_balance("cash")
    bank_balance = await get_account_balance("bank")
    
    # Recent cash transactions
    cash_entries = await db.ledger.find({"account": "cash"}, {"_id": 0}).sort("date", -1).to_list(50)
    bank_entries = await db.ledger.find({"account": "bank"}, {"_id": 0}).sort("date", -1).to_list(50)
    
    return {
        "cash_balance": cash_balance,
        "bank_balance": bank_balance,
        "total_balance": cash_balance + bank_balance,
        "cash_transactions": cash_entries,
        "bank_transactions": bank_entries
    }

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
