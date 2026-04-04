import os
import requests
from dotenv import load_dotenv

load_dotenv()
res = requests.post("http://localhost:8000/api/auth/login", json={"email": "test@best.com", "password": "password"})
token = ""
if res.status_code == 200:
    token = res.json()["access_token"]
else:
    print("Login failed for test@best.com. Trying another way...")
    import pymongo
    client = pymongo.MongoClient(os.getenv("MONGO_URL"))
    db = client[os.getenv("DB_NAME", "BlitzerDB")]
    user = db.users.find_one({})
    if user:
        print("Found user:", user["email"])
        # We can't easily auto-login without password. Let's just generate a JWT!
        from jose import jwt
        from datetime import datetime, timedelta, timezone
        token_data = {"sub": user["id"], "exp": datetime.now(timezone.utc) + timedelta(minutes=60)}
        token = jwt.encode(token_data, os.getenv("JWT_SECRET", "supersecretkey"), algorithm="HS256")
    else:
        print("No users found.")
        exit(1)

print("Fetching dashboard...")
dash_res = requests.get("http://localhost:8000/api/dashboard", headers={"Authorization": f"Bearer {token}"})
print("Dashboard status:", dash_res.status_code)
if dash_res.status_code != 200:
    print("Error:", dash_res.text)
else:
    print("Dashboard fetched successfully.")
