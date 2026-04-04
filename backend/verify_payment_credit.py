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

async def verify_payment_credit():
    print(f"Connecting to {MONGO_URL}...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # 1. Setup Data: Customer with Credit
    cust_id = str(uuid.uuid4())
    print(f"Creating Customer {cust_id}...")
    await db.customers.insert_one({"id": cust_id, "name": "Payment Credit Test"})
    
    # Add Credit 1000 (Advance)
    await db.ledger.insert_many([
        {"account": "bank", "debit": 1000, "credit": 0, "ref_type": "adv", "ref_id": "setup", "date": datetime.now().isoformat()},
        {"account": f"customer:{cust_id}", "debit": 0, "credit": 1000, "ref_type": "adv", "ref_id": "setup", "date": datetime.now().isoformat()}
    ])
    
    # 2. Create Invoice 600
    inv_id = str(uuid.uuid4())
    await db.invoices.insert_one({
        "id": inv_id,
        "invoice_number": "INV-PAY-001",
        "customer_id": cust_id,
        "total": 600,
        "status": "unpaid",
        "paid_amount": 0,
        "credit_applied": 0,
        "date": datetime.now().isoformat()
    })
    # Debit Customer 600
    await db.ledger.insert_one({
        "account": f"customer:{cust_id}", "debit": 600, "credit": 0, "ref_type": "invoice", "ref_id": inv_id, "date": datetime.now().isoformat()
    })
    
    print("Setup Complete. Cust Bal: -400 (1000 Adv - 600 Inv). Inv Due: 600.")
    
    # 3. Simulate record_payment via API logic
    # Payload: Amount 100, use_credit=True, invoice_id=inv_id
    
    payment_id = str(uuid.uuid4())
    payment_amount = 100
    
    # 3a. Record Payment 100 Cash
    await db.payments.insert_one({
        "id": payment_id, "customer_id": cust_id, "amount": payment_amount, "mode": "cash", "date": datetime.now().isoformat()
    })
    await db.ledger.insert_one({
        "account": "cash", "debit": payment_amount, "credit": 0, "ref_type": "payment", "ref_id": payment_id, "date": datetime.now().isoformat()
    })
    await db.ledger.insert_one({
        "account": f"customer:{cust_id}", "debit": 0, "credit": payment_amount, "ref_type": "payment", "ref_id": payment_id, "date": datetime.now().isoformat()
    })
    
    # 3b. Apply Payment Logic (Specific Invoice)
    # Update Invoice for 100 Cash
    await db.invoices.update_one(
        {"id": inv_id},
        {"$set": {"paid_amount": 100, "status": "partially_paid"}}
    )
    # Allocation
    await db.payment_allocations.insert_one({
        "id": str(uuid.uuid4()), "payment_id": payment_id, "invoice_id": inv_id, "amount": 100
    })
    
    print("Applied 100 Cash. Inv Due should be 500.")
    
    # 3c. Apply Credit Logic (The part we added)
    # apply_credit_to_invoice(cust_id, inv_id, total)
    
    # Re-enact logic:
    # 1. Get Balance
    pipeline = [{"$match": {"account": f"customer:{cust_id}"}}, {"$group": {"_id": None, "total_debit": {"$sum": "$debit"}, "total_credit": {"$sum": "$credit"}}}]
    res = await db.ledger.aggregate(pipeline).to_list(1)
    # Debits: 600 (Inv)
    # Credits: 1000 (Adv) + 100 (Pay) = 1100
    # Balance: 600 - 1100 = -500.
    curr_bal = res[0]["total_debit"] - res[0]["total_credit"] if res else 0
    print(f"Current Bal: {curr_bal} (Should be -500)")
    
    # 2. Pre-Balance
    # Logic in apply_credit_to_invoice subtracts invoice total (600).
    # -500 - 600 = -1100.
    # Available Credit = 1100.
    # Credit Applied = min(1100, 600) = 600?
    # WAIT. If Credit Applied is 600, then Total Paid = 100 + 600 = 700.
    # That exceeds Invoice Total (600).
    
    # BUG DETECTION:
    # apply_credit_to_invoice applies `min(available, invoice_total)`.
    # It overwrites `paid_amount` and `credit_applied`.
    # It does NOT account for `payment_received` (Cash)?
    # Let's check `apply_credit_to_invoice` code again.
    
    # Line 636: "paid_amount": credit_applied
    # IT OVERWRITES PAID AMOUNT!
    # So if we paid 100 Cash, then called apply_credit_to_invoice, 
    # and it calculates credit_applied = 600, it sets paid_amount = 600.
    # BUT wait, does it differentiate between "Credit Part" and "Cash Part"?
    # `apply_credit_to_invoice` assumes `paid_amount` IS `credit_applied`?
    # Or does it ADD to it?
    
    # Line 636: "paid_amount": credit_applied.
    # YES, it OVERWRITES.
    # This is a BUG if we mix Cash + Credit.
    
    # 4. Cleanup
    await db.customers.delete_one({"id": cust_id})
    await db.ledger.delete_many({"account": f"customer:{cust_id}"})
    await db.invoices.delete_one({"id": inv_id})
    print("Cleanup done.")

if __name__ == "__main__":
    asyncio.run(verify_payment_credit())
