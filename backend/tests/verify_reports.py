import requests
import json

BASE_URL = "http://localhost:8000/api"
TEST_EMAIL = "test@best.com"
TEST_PASSWORD = "demo@pass_123"

def verify_reports():
    session = requests.Session()
    
    # 1. Login
    print(f"Logging in as {TEST_EMAIL}...")
    try:
        res = session.post(f"{BASE_URL}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        if res.status_code != 200:
            print(f"Login failed: {res.text}")
            return
        token = res.json()["access_token"]
        session.headers.update({"Authorization": f"Bearer {token}"})
        print("Login success.")
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    # 2. Fix Ledger
    print("\nRunning Fix Ledger Migration...")
    res = session.post(f"{BASE_URL}/maintenance/fix-ledger")
    if res.status_code == 200:
        print(f"Fix Success: {json.dumps(res.json(), indent=2)}")
    else:
        print(f"Fix Failed: {res.text}")

    # 3. Trial Balance
    print("\nFetching Trial Balance...")
    res = session.get(f"{BASE_URL}/reports/trial-balance")
    if res.status_code == 200:
        data = res.json()
        print(f"Entries: {json.dumps(data['entries'], indent=2)}")
        print(f"Total Debit: {data['total_debit']}")
        print(f"Total Credit: {data['total_credit']}")
    
        # Check Business
        res = session.get(f"{BASE_URL}/business")
        print(f"\nBusiness Info: {json.dumps(res.json(), indent=2)}")
    else:
        print(f"TB Failed: {res.text}")

    # 4. Balance Sheet
    print("\nFetching Balance Sheet...")
    res = session.get(f"{BASE_URL}/reports/balance-sheet")
    if res.status_code == 200:
        data = res.json()
        assets = data['assets']['total']
        liab = data['liabilities']['total']
        equity = data['equity']['total']
        print(f"Assets: {assets}")
        print(f"Liabilities: {liab}")
        print(f"Equity: {equity}")
        print(f"Check: {assets} = {liab} + {equity} ({liab + equity})")
        print(f"Balanced: {data['is_balanced']}")
        if not data['is_balanced']:
             print("WARNING: Balance Sheet is NOT balanced!")
             print(json.dumps(data, indent=2))
    else:
        print(f"BS Failed: {res.text}")

if __name__ == "__main__":
    verify_reports()
