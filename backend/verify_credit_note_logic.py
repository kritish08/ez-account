import requests
import json
import uuid

BASE_URL = "http://localhost:8000/api"

def get_token():
    # Try login first
    login_data = {"email": "test@example.com", "password": "password123"}
    res = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if res.status_code == 200:
        return res.json()["access_token"]
    
    # If login fails, try register
    reg_data = {"email": "test@example.com", "password": "password123", "name": "Test User"}
    res = requests.post(f"{BASE_URL}/auth/register", json=reg_data)
    if res.status_code == 200:
        return res.json()["access_token"]
        
    print("Auth failed:", res.text)
    return None

def run_test():
    token = get_token()
    if not token:
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Create a Customer
    unique_name = f"Test Overpayer {uuid.uuid4().hex[:4]}"
    cust_res = requests.post(f"{BASE_URL}/customers", json={
        "name": unique_name,
        "phone": "9999999999"
    }, headers=headers)
    
    if cust_res.status_code != 200:
        print("Failed to create customer:", cust_res.text)
        return
    customer_id = cust_res.json()["id"]
    print(f"Created Customer: {customer_id}")

    # 2. Create an Invoice for 1000
    inv_res = requests.post(f"{BASE_URL}/invoices", json={
        "customer_id": customer_id,
        "items": [{"description": "Service", "quantity": 1, "rate": 1000}],
        "date": "2023-10-01"
    }, headers=headers)
    
    if inv_res.status_code != 200:
        print("Failed to create invoice:", inv_res.text)
        return
    print("Created Invoice for 1000")

    # 3. Pay 1500 (Excess 500)
    pay_res = requests.post(f"{BASE_URL}/payments", json={
        "customer_id": customer_id,
        "amount": 1500,
        "mode": "cash",
        "date": "2023-10-02",
        "notes": "Overpayment Test"
    }, headers=headers)
    
    if pay_res.status_code != 200:
        print("Failed to record payment:", pay_res.text)
        return
    
    pay_data = pay_res.json()
    print("Payment Response:", json.dumps(pay_data, indent=2))
    
    if pay_data.get("excess_as_credit") == 500:
        print("SUCCESS: Excess calculated correctly.")
    else:
        print(f"ERROR: Excess amount wrong. Expected 500, got {pay_data.get('excess_as_credit')}")

    if pay_data.get("credit_note_id"):
        print(f"SUCCESS: Credit Note ID returned: {pay_data['credit_note_id']}")
        
        # 4. Fetch the Credit Note to verify
        cn_res = requests.get(f"{BASE_URL}/credit-notes/{pay_data['credit_note_id']}", headers=headers)
        if cn_res.status_code == 200:
            print("Verified Credit Note exists in DB:", json.dumps(cn_res.json(), indent=2))
        else:
            print("Failed to fetch created Credit Note")
    else:
        print("ERROR: No credit_note_id returned in payment response.")


if __name__ == "__main__":
    run_test()
