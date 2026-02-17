import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def enable_registration():
    mongo_url = os.environ['MONGO_URL']
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ['DB_NAME']]
    
    await db.settings.update_one(
        {"type": "system"}, 
        {"$set": {"registration_enabled": True}}, 
        upsert=True
    )
    print("Registration Enabled Successfully!")
    client.close()

if __name__ == "__main__":
    asyncio.run(enable_registration())
