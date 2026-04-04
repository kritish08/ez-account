import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
mongo_url = os.getenv("MONGO_URL")
print("Connecting to:", mongo_url)
try:
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print("Connection failed:", e)
