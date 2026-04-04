import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt
import requests
import uuid

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

BASE_URL = "http://localhost:8000/api"

async def setup_user():
    print(f"Connecting to MongoDB at {MONGO_URL}...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": email,
        "password_hash": hashed,
        "name": "Test User",
        "role": "admin",
        "created_at": "2023-01-01T00:00:00"
    }
    
    await db.users.insert_one(user_doc)
    print(f"Created Test User: {email} / {password}")
    return email, password

def run_api_tests(email, password):
    session = requests.Session()
    
    # 1. Login
    print("\n1. Logging in...")
    resp = session.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        print("Login Failed:", resp.text)
        return
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    session.headers.update(headers)
    print("Login Success")

    # 2. Create Supplier
    print("\n2. Creating Supplier...")
    ud = uuid.uuid4().hex[:4]
    resp = session.post(f"{BASE_URL}/suppliers", json={"name": f"Supp {ud}", "phone": "1234567890"})
    sid = resp.json()["id"]
    print(f"Supplier Created: {sid}")

    # 3. Create Debit Note (1000)
    # This debits supplier (Asset/Advance). Balance should be +1000.
    print("\n3. Creating Debit Note (1000)...")
    # Need a dummy product for DN item
    prod_resp = session.post(f"{BASE_URL}/products", json={"name": "Test Prod", "cost_price": 1000, "selling_price": 1500})
    pid = prod_resp.json()["id"]

    resp = session.post(f"{BASE_URL}/debit-notes", json={
        "supplier_id": sid,
        "items": [{"product_id": pid, "quantity": 1, "cost_price": 1000}],
        "date": "2023-10-01",
        "reason": "Return"
    })
    if resp.status_code != 200:
        print("DN Creation Failed:", resp.text)
        return
    dn_id = resp.json()["id"]
    print(f"DN Created: {dn_id}")

    # 4. Check Balance (Expect -1000)
    print("\n4. Checking Balance (Expect -1000)...")
    resp = session.get(f"{BASE_URL}/suppliers/{sid}/ledger")
    data = resp.json()
    if "ledger" in data:
        txns = data["ledger"]
    else: 
        print("Error: 'ledger' key not found", data)
        return

    balance = txns[-1]["balance"] if txns else 0
    print(f"Current Balance: {balance}")
    if balance != -1000:
        print("ERROR: Balance incorrect!")

    # 5. Create Purchase (400) with Debit Application
    print("\n5. Creating Purchase (400)...")
    resp = session.post(f"{BASE_URL}/purchases", json={
        "supplier_id": sid,
        "items": [{"product_id": pid, "quantity": 1, "cost_price": 400}],
        "date": "2023-10-02",
        "payment_status": "unpaid", # default
        "apply_debit": True
    })
    if resp.status_code != 200:
        print("Purchase Creation Failed:", resp.text)
    else:
        pur_data = resp.json()
        print(f"Purchase Created. Debit Used: {pur_data.get('debit_used')}")
        if pur_data.get('debit_used') != 400:
            print("ERROR: Debit used incorrect!")

    # 6. Check Balance (Expect -600)
    # -1000 (DN) + 400 (Purchase) = -600
    print("\n6. Checking Balance (Expect -600)...")
    resp = session.get(f"{BASE_URL}/suppliers/{sid}/ledger")
    txns = resp.json().get("ledger", [])
    balance = txns[-1]["balance"] if txns else 0
    print(f"Current Balance: {balance}")
    if balance != -600:
        print("ERROR: Balance incorrect!")

    # 7. Update Debit Note (Change to 1500)
    # Reverse DN(1000) -> Bal = 600 - 1000 = -400
    # New DN(1500) -> Bal = -400 + 1500 = 1100
    print(f"\n7. Updating Debit Note {dn_id} (Change to 1500)...")
    resp = session.put(f"{BASE_URL}/debit-notes/{dn_id}", json={
        "items": [{"product_id": pid, "quantity": 1, "cost_price": 1500}],
        "reason": "Updated Return"
    })
    if resp.status_code != 200:
        print("Update Failed:", resp.text)
        return
    print("Update Success.")

    # 8. Check Balance (Expect -1100)
    print("\n8. Checking Balance (Expect -1100)...")
    resp = session.get(f"{BASE_URL}/suppliers/{sid}/ledger")
    txns = resp.json().get("ledger", [])
    balance = txns[-1]["balance"] if txns else 0
    print(f"Final Balance: {balance}")
    
    if balance != -1100:
        print(f"ERROR: Final Balance incorrect! Expected -1100, got {balance}")
    else:
        print("\nSUCCESS: All tests passed!")

if __name__ == "__main__":
    email, password = asyncio.run(setup_user())
    run_api_tests(email, password)
