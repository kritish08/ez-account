import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
async def test():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client[os.getenv("DB_NAME", "BlitzerDB")]
    print("Testing find_one...")
    user = await db.users.find_one()
    print("User found:", user is not None)

asyncio.run(test())
