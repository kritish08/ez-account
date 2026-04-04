"""
WebSocket Client Test for Voice Assistant

Tests the WebSocket endpoint for voice assistant functionality.
"""

import asyncio
import websockets
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import requests

load_dotenv()

API_BASE = "http://localhost:8000/api"
WS_BASE = "ws://localhost:8000"


async def test_websocket_voice_assistant():
    """Test the WebSocket voice assistant endpoint"""
    
    print("="*60)
    print("WebSocket Voice Assistant Test")
    print("="*60)
    
    # Step 1: Login to get token
    print("\n[1] Logging in...")
    login_response = requests.post(
        f"{API_BASE}/auth/login",
        json={
            "email": "test@example.com",
            "password": "password123"
        }
    )
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.text}")
        print("\nTrying to register first...")
        
        # Register if login fails
        register_response = requests.post(
            f"{API_BASE}/auth/register",
            json={
                "email": "test@example.com",
                "password": "password123",
                "name": "Test User"
            }
        )
        
        if register_response.status_code == 200:
            login_response = requests.post(
                f"{API_BASE}/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "password123"
                }
            )
        else:
            print(f"❌ Registration failed: {register_response.text}")
            return
    
    token = login_response.json()["access_token"]
    print(f"✅ Logged in! Token: {token[:20]}...")
    
    # Step 2: Connect to WebSocket
    print("\n[2] Connecting to WebSocket...")
    ws_url = f"{WS_BASE}/ws/voice?token={token}"
    
    async with websockets.connect(ws_url) as websocket:
        print("✅ WebSocket connected!")
        
        # Receive welcome message
        welcome = await websocket.recv()
        welcome_data = json.loads(welcome)
        print(f"📨 Server: {welcome_data.get('message')}")
        
        # Test conversation
        test_messages = [
            "Nayi invoice banao",
            "Test Customer ke liye",  # This customer probably doesn't exist
            "Koi bhi customer chalega",
        ]
        
        for msg in test_messages:
            print(f"\n👤 YOU: {msg}")
            
            # Send message
            await websocket.send(json.dumps({
                "type": "text",
                "text": msg
            }))
            
            # Receive response
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("type") == "response":
                print(f"🤖 AI: {response_data.get('response')}")
                
                if response_data.get('function_called'):
                    print(f"   [Function: {response_data['function_called']}]")
                
                if response_data.get('draft'):
                    draft = response_data['draft']
                    print(f"   [Draft State: {response_data['state']}]")
                    print(f"   [Items: {len(draft.get('items', []))}, Total: ₹{draft.get('total', 0)}]")
            
            elif response_data.get("type") == "error":
                print(f"❌ Error: {response_data.get('message')}")
            
            # Small delay
            await asyncio.sleep(1)
        
        print("\n" + "="*60)
        print("✅ WebSocket Test Complete!")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(test_websocket_voice_assistant())
