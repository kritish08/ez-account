"""MongoDB client + `db` handle.

Single import surface so every service / router talks to the same client.
The client is created at module import time, matching the prior behaviour
in `server.py` — Motor connects lazily, so this is cheap.
"""

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import MONGO_URL, DB_NAME

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
