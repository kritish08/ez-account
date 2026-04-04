import os
import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt

load_dotenv()

async def main():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client[os.getenv("DB_NAME", "BlitzerDB")]
    
    email = "test@best.com"
    password = "password_123"
    
    # Hash password using bcrypt
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    result = await db.users.update_one(
        {"email": email},
        {"$set": {"password_hash": password_hash}}
    )
    
    if result.matched_count > 0:
        print(f"Successfully updated password for {email}")
    else:
        print(f"User {email} not found. Creating user...")
        from datetime import datetime, timezone
        import uuid
        
        user_doc = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": "Test User",
            "password_hash": password_hash,
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(user_doc)
        print("User created successfully!")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
