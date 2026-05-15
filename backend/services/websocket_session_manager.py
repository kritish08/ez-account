"""
WebSocket Session Manager

Manages multiple concurrent voice assistant sessions.
Each user gets their own isolated session.
"""

from typing import Dict, Optional
from fastapi import WebSocket
from .voice_session import VoiceSession
from .function_executor import FunctionExecutor
from .voice_ai_handler import VoiceAIHandler
from motor.motor_asyncio import AsyncIOMotorDatabase
import asyncio
from datetime import datetime, timedelta, timezone


class WebSocketSessionManager:
    """
    Manages WebSocket connections and voice sessions.
    
    Features:
    - One session per user
    - Auto-cleanup of expired sessions
    - Graceful disconnect handling
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.active_sessions: Dict[str, VoiceSession] = {}
        self.active_websockets: Dict[str, WebSocket] = {}
        self.ai_handler = VoiceAIHandler()
        
        # Start background cleanup task
        asyncio.create_task(self._cleanup_expired_sessions())
    
    async def connect(self, user_id: str, websocket: WebSocket) -> VoiceSession:
        """
        Register a connected & already-accepted WebSocket and create/resume
        the session for this user.

        NOTE: The caller is responsible for calling `await websocket.accept()`
        BEFORE invoking this — auth happens at the route level (so the JWT
        can be verified from a handshake message rather than the URL), and
        the route accepts the socket itself to enable that handshake.
        """
        # If this user already has an open socket (second tab, reconnect
        # without a clean disconnect), close the old one so it doesn't leak
        # an orphan TCP connection. The previous code silently overwrote
        # the dict entry, leaving the old socket open forever.
        existing_ws = self.active_websockets.get(user_id)
        if existing_ws is not None and existing_ws is not websocket:
            try:
                await existing_ws.close(code=1001, reason="Replaced by new connection")
            except Exception:
                pass

        # Resume existing session or create new one
        if user_id in self.active_sessions:
            session = self.active_sessions[user_id]
            # Update last activity
            session.last_activity = datetime.now(timezone.utc)
        else:
            session = VoiceSession(user_id)
            self.active_sessions[user_id] = session

        self.active_websockets[user_id] = websocket
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "session_id": session.session_id,
            "message": "Voice assistant ready! 🎤 Say 'Nayi invoice banao' to start"
        })
        
        return session
    
    async def disconnect(self, user_id: str):
        """
        Handle WebSocket disconnect.
        
        NOTE: We keep the session alive for a while in case user reconnects.
        """
        if user_id in self.active_websockets:
            del self.active_websockets[user_id]
        
        # Session cleanup happens in background task after timeout
    
    async def process_message(self, user_id: str, message_data: dict):
        """
        Process incoming message from WebSocket.
        
        Args:
            user_id: User's ID
            message_data: Message payload
        
        Returns:
            Response to send back to client
        """
        if user_id not in self.active_sessions:
            return {
                "type": "error",
                "error": "no_session",
                "message": "Session not found. Please reconnect."
            }
        
        session = self.active_sessions[user_id]
        executor = FunctionExecutor(self.db, session)
        
        message_type = message_data.get("type")
        
        if message_type == "text":
            # Text message
            text = message_data.get("text", "")
            result = await self.ai_handler.process_message(text, session, executor)
            
            return {
                "type": "response",
                "transcript": text,
                "response": result["message"],
                "function_called": result.get("function_called"),
                "draft": result.get("draft"),
                "state": session.state.value
            }
        
        elif message_type == "audio":
            # Audio chunk (for future implementation)
            # For now, return placeholder
            return {
                "type": "error",
                "error": "not_implemented",
                "message": "Audio streaming coming soon! Use text for now."
            }
        
        else:
            return {
                "type": "error",
                "error": "unknown_type",
                "message": f"Unknown message type: {message_type}"
            }
    
    async def send_to_user(self, user_id: str, data: dict):
        """
        Send a message to a specific user's WebSocket.
        
        Args:
            user_id: Target user
            data: Data to send
        """
        if user_id in self.active_websockets:
            websocket = self.active_websockets[user_id]
            try:
                await websocket.send_json(data)
            except Exception as e:
                # Connection closed, remove it
                await self.disconnect(user_id)
    
    async def _cleanup_expired_sessions(self):
        """
        Background task to clean up expired sessions.
        Runs every 5 minutes.
        """
        while True:
            await asyncio.sleep(300)  # 5 minutes
            
            expired_users = []
            for user_id, session in self.active_sessions.items():
                if session.is_expired(timeout_minutes=30):
                    expired_users.append(user_id)
            
            # Remove expired sessions
            for user_id in expired_users:
                if user_id not in self.active_websockets:
                    # Only cleanup if not connected
                    del self.active_sessions[user_id]
    
    def get_session_stats(self) -> dict:
        """Get statistics about active sessions."""
        return {
            "active_sessions": len(self.active_sessions),
            "connected_websockets": len(self.active_websockets),
            "sessions_by_state": {
                "idle": sum(1 for s in self.active_sessions.values() if s.state.value == "idle"),
                "invoice_draft": sum(1 for s in self.active_sessions.values() if s.state.value == "invoice_draft"),
                "purchase_draft": sum(1 for s in self.active_sessions.values() if s.state.value == "purchase_draft")
            }
        }
