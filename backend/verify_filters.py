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

async def verify_filters():
    print(f"Connecting to {MONGO_URL}...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # 1. Setup Data
    cust_id = str(uuid.uuid4())
    await db.customers.insert_one({"id": cust_id, "name": "Filter Test Customer", "email": "filter@test.com"})
    
    inv_id = str(uuid.uuid4())
    # Create an invoice with credit applied
    await db.invoices.insert_one({
        "id": inv_id,
        "invoice_number": f"INV-{uuid.uuid4().hex[:4]}",
        "customer_id": cust_id,
        "total": 1000,
        "credit_applied": 200, # KEY FIELD
        "status": "partially_paid",
        "date": datetime.now().isoformat()
    })
    
    inv_id_no_credit = str(uuid.uuid4())
    # Create an invoice WITHOUT credit applied
    await db.invoices.insert_one({
        "id": inv_id_no_credit,
        "invoice_number": f"INV-{uuid.uuid4().hex[:4]}",
        "customer_id": cust_id,
        "total": 1000,
        "credit_applied": 0,
        "status": "unpaid",
        "date": datetime.now().isoformat()
    })
    
    print("Created test data.")
    
    # 2. Test Filters (Simulating the query logic used in server.py)
    # query["credit_applied"] = {"$gt": 0}
    
    print("Testing credit_applied_only filter...")
    query = {"customer_id": cust_id, "credit_applied": {"$gt": 0}}
    results = await db.invoices.find(query).to_list(100)
    
    if len(results) == 1 and results[0]["id"] == inv_id:
        print("✅ Credit Applied Filter Passed: Returned only the correct invoice.")
    else:
        print(f"❌ Credit Applied Filter Failed. Returned {len(results)} items.")
        for r in results: print(f" - {r['id']} (Credit: {r.get('credit_applied')})")

    # 3. Cleanup
    await db.customers.delete_one({"id": cust_id})
    await db.invoices.delete_one({"id": inv_id})
    await db.invoices.delete_one({"id": inv_id_no_credit})
    print("Cleanup done.")

if __name__ == "__main__":
    asyncio.run(verify_filters())
