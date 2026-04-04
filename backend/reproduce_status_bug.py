import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
import uuid
from datetime import datetime

# Configuration
try:
    with open("backend/.env", "r") as f:
        for line in f:
            if line.startswith("MONGO_URL="):
                MONGO_URL = line.strip().split("=", 1)[1].strip('"')
            if line.startswith("DB_NAME="):
                DB_NAME = line.strip().split("=", 1)[1].strip('"')
except FileNotFoundError:
    print(".env not found, using defaults")
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    DB_NAME = "ezaccount"

async def reproduce_bug():
    print(f"Connecting to {MONGO_URL}...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # 1. Setup Data: New Customer with Credit
    cust_id = str(uuid.uuid4())
    print(f"Creating Customer {cust_id}...")
    await db.customers.insert_one({"id": cust_id, "name": "Status Bug Test Customer"})
    
    # 2. Add Credit (Advance Payment) - Credit Customer 1000
    # Ledger: Dr Bank 1000, Cr Customer 1000.
    # Customer Balance = -1000.
    await db.ledger.insert_many([
        {
            "account": "bank",
            "debit": 1000,
            "credit": 0,
            "ref_type": "payment",
            "ref_id": "advance_payment",
            "date": datetime.now().isoformat()
        },
        {
            "account": f"customer:{cust_id}",
            "debit": 0,
            "credit": 1000,
            "ref_type": "payment",
            "ref_id": "advance_payment",
            "date": datetime.now().isoformat()
        }
    ])
    
    print("Added Credit of 1000.")
    
    # 3. Create Invoice of 400 with apply_credit=True
    # We will simulate calling the backend functions directly or mimicking the API logic.
    # Since we can't call API easily without running server, we'll import functions if possible,
    # OR simpler: Replicate the 'apply_credit_to_invoice' logic here to see if math works.
    # BUT better: We should check what happens in the DB.
    
    # Let's use `apply_credit_to_invoice` logic manually to verify the math.
    
    # Simulate Step 1 of create_invoice: Insert Invoice
    inv_id = str(uuid.uuid4())
    invoice_total = 400
    
    await db.invoices.insert_one({
        "id": inv_id,
        "invoice_number": "INV-BUG-001",
        "customer_id": cust_id,
        "total": invoice_total,
        "status": "unpaid", # Default status
        "paid_amount": 0,
        "credit_applied": 0,
        "date": datetime.now().isoformat()
    })
    
    # Simulate Step 2 of create_invoice: Debit Customer
    await db.ledger.insert_one({
        "account": f"customer:{cust_id}",
        "debit": invoice_total,
        "credit": 0,
        "ref_type": "invoice",
        "ref_id": inv_id,
        "date": datetime.now().isoformat()
    })
    
    print("Created Invoice 400 and Debited Customer.")
    
    # 4. Now RUN the Logic we suspect is failing
    # Logic from apply_credit_to_invoice
    
    pipeline = [
        {"$match": {"account": f"customer:{cust_id}"}},
        {"$group": {"_id": None, "total_debit": {"$sum": "$debit"}, "total_credit": {"$sum": "$credit"}}}
    ]
    result = await db.ledger.aggregate(pipeline).to_list(1)
    current_balance = 0
    if result:
        current_balance = result[0]["total_debit"] - result[0]["total_credit"]
    
    print(f"Current Balance (Should be -600): {current_balance}")
    
    pre_balance = current_balance - invoice_total
    print(f"Pre Balance (Should be -1000): {pre_balance}")
    
    available_credit = max(0, -pre_balance)
    print(f"Available Credit: {available_credit}")
    
    credit_applied = min(available_credit, invoice_total)
    print(f"Credit Applied: {credit_applied}")
    
    amount_due = invoice_total - credit_applied
    print(f"Amount Due: {amount_due}")
    
    new_status = "paid" if amount_due <= 0 else "partially_paid"
    print(f"Calculated New Status: {new_status}")
    
    # 5. Cleanup
    await db.customers.delete_one({"id": cust_id})
    await db.ledger.delete_many({"account": f"customer:{cust_id}"})
    await db.invoices.delete_one({"id": inv_id})
    print("Cleanup done.")

if __name__ == "__main__":
    asyncio.run(reproduce_bug())
