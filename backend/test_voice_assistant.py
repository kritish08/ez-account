"""
Simple test script for voice assistant function calling

Tests the core function calling flow without WebSocket complexity.
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.voice_session import VoiceSession
from services.function_executor import FunctionExecutor
from services.voice_ai_handler import VoiceAIHandler
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


async def test_invoice_creation():
    """Test creating an invoice via voice commands"""
    
    # Connect to MongoDB
    mongo_url = os.environ['MONGO_URL']
    if '?' not in mongo_url:
        mongo_url += '?tlsAllowInvalidCertificates=true'
    elif 'tlsAllowInvalidCertificates' not in mongo_url:
        mongo_url += '&tlsAllowInvalidCertificates=true'
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ['DB_NAME']]
    
    # Create session
    user_id = "test_user_voice"
    session = VoiceSession(user_id)
    executor = FunctionExecutor(db, session)
    ai_handler = VoiceAIHandler()
    
    print("="*60)
    print("Voice Assistant Test - Invoice Creation")
    print("="*60)
    
    # Simulate conversation
    test_messages = [
        "Nayi invoice banao",
        "Ramesh Traders",
        "10 notebooks @ 50 rupees each",
        "5 pens bhi daal do, 20 rupees each",
        "Save kar do"
    ]
    
    for user_message in test_messages:
        print(f"\n👤 USER: {user_message}")
        
        result = await ai_handler.process_message(
            user_message,
            session,
            executor
        )
        
        print(f"🤖 AI: {result['message']}")
        
        if result.get('function_called'):
            print(f"   [Function: {result['function_called']}]")
            print(f"   [Result: {result['function_result'].get('message', 'OK')}]")
        
        if result.get('draft'):
            draft = result['draft']
            print(f"   [Draft: {len(draft.get('items', []))} items, Total: ₹{draft.get('total', 0)}]")
    
    print("\n" + "="*60)
    print("Test Complete!")
    print("="*60)
    
    client.close()


if __name__ == "__main__":
    asyncio.run(test_invoice_creation())
