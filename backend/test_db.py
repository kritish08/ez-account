import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# Connect to MongoDB Atlas
# Using the string provided by the user in backend/.env
MONGO_URL = "mongodb+srv://krizm4onrm3odb:Ox1WxwE4Gxqe3cAM@blitzerdb.jsdb2r8.mongodb.net"

async def test_connection():
    try:
        print(f"Connecting to: {MONGO_URL}")
        client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        # Force a connection verification
        await client.admin.command('ping')
        print("Successfully connected to MongoDB Atlas!")
    except Exception as e:
        print(f"Failed to connect to MongoDB Atlas: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_connection())
