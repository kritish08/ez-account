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

# Utils
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def setup_user():
    print(f"Connecting to MongoDB at {MONGO_URL}...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    # hashed = pwd_context.hash(password)
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
    print("Login Custom Success")

    # 2. Create Customer
    print("\n2. Creating Customer...")
    ud = uuid.uuid4().hex[:4]
    resp = session.post(f"{BASE_URL}/customers", json={"name": f"Cust {ud}", "phone": "1234567890"})
    cid = resp.json()["id"]
    print(f"Customer Created: {cid}")

    # 3. Create Credit Note (Original: 1000)
    print("\n3. Creating Credit Note (1000)...")
    resp = session.post(f"{BASE_URL}/credit-notes", json={
        "customer_id": cid,
        "items": [{"description": "Return", "quantity": 1, "rate": 1000}],
        "date": "2023-10-01",
        "reason": "Initial Return"
    })
    if resp.status_code != 200:
        print("CN Creation Failed:", resp.text)
        return
    cn_id = resp.json()["id"]
    print(f"CN Created: {cn_id}")

    # 4. Check Balance (Should be -1000)
    print("\n4. Checking Balance (Expect -1000)...")
    resp = session.get(f"{BASE_URL}/customers/{cid}/ledger")
    # print(f"Ledger Response: {resp.text}")
    data = resp.json()
    if "ledger" in data:
        txns = data["ledger"]
    else: 
        # Fallback or error
        print("Error: 'ledger' key not found in response:", data)
        return

    balance = txns[-1]["balance"] if txns else 0
    print(f"Current Balance: {balance}")
    if balance != -1000:
        print("ERROR: Balance incorrect!")
    
    # 5. Create Invoice (Amount 400, Apply Credit=True)
    print("\n5. Creating Invoice (400) with Credit Application...")
    resp = session.post(f"{BASE_URL}/invoices", json={
        "customer_id": cid,
        "items": [{"description": "Item", "quantity": 1, "rate": 400}],
        "date": "2023-10-02",
        "is_draft": True
    })
    if resp.status_code != 200:
        print("Invoice Creation Failed:", resp.text)
        return

    inv_id = resp.json()["id"]
    # Publish with apply_credit
    resp = session.post(f"{BASE_URL}/invoices/{inv_id}/publish?apply_credit=true")
    if resp.status_code != 200:
        print("Invoice Publish Failed:", resp.text)
    else:
        inv_data = resp.json()
        print(f"Invoice Published. Paid Amount: {inv_data.get('credit_applied')}")
        if inv_data.get('credit_applied') != 400:
            print("ERROR: Credit applied incorrect!")

    # 6. Check Balance (Should be -600)
    # CN (-1000) + Inv (400) = -600
    print("\n6. Checking Balance (Expect -600)...")
    resp = session.get(f"{BASE_URL}/customers/{cid}/ledger")
    data = resp.json()
    if "ledger" in data:
        txns = data["ledger"]
    else:
        print("Error: 'ledger' key not found in response:", data)
        return

    balance = txns[-1]["balance"] if txns else 0
    print(f"Current Balance: {balance}")
    if balance != -600:
        print("ERROR: Balance incorrect!")

    # 7. Update Credit Note (Change to 1500)
    # New Balance should be: -600 - (1500-1000) = -1100
    # Steps: Reversal of CN -> Bal = -600 + 1000 = 400.
    # New CN -> Bal = 400 - 1500 = -1100.
    print(f"\n7. Updating Credit Note {cn_id} (Change to 1500)...")
    resp = session.put(f"{BASE_URL}/credit-notes/{cn_id}", json={
        "items": [{"description": "Return Adjusted", "quantity": 1, "rate": 1500}],
        "reason": "Updated Return"
    })
    if resp.status_code != 200:
        print("Update Failed:", resp.text)
        return
    print("Update Success.")

    # 8. Check Balance (Expect -1100)
    print("\n8. Checking Balance (Expect -1100)...")
    resp = session.get(f"{BASE_URL}/customers/{cid}/ledger")
    data = resp.json()
    if "ledger" in data:
        txns = data["ledger"]
    else:
        print("Error: 'ledger' key not found in response:", data)
        return

    balance = txns[-1]["balance"] if txns else 0
    print(f"Final Balance: {balance}")
    
    if balance != -1100:
        print(f"ERROR: Final Balance incorrect! Expected -1100, got {balance}")
    else:
        print("\nSUCCESS: All tests passed!")


if __name__ == "__main__":
    email, password = asyncio.run(setup_user())
    run_api_tests(email, password)
