"""
WebSocket Session Manager

Manages multiple concurrent voice assistant sessions.
Each user gets their own isolated session.
"""

import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import WebSocket
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.rate_limit import RateLimiter

from .function_executor import FunctionExecutor
from .voice_ai_handler import VoiceAIHandler
from .voice_session import VoiceSession

logger = logging.getLogger(__name__)

# A voice turn costs a transcription plus one or two model calls, and the
# socket previously accepted an unlimited number of them at any size. Both
# limits are spend controls first and abuse controls second.
#
# 4 MB of decoded audio is roughly 8 minutes of Opus at 64 kbps — far longer
# than the push-to-talk utterances this is built for.
MAX_AUDIO_BYTES = 4 * 1024 * 1024
VOICE_MAX_TURNS_PER_HOUR = 240
voice_limiter = RateLimiter(
    max_attempts=VOICE_MAX_TURNS_PER_HOUR, window_seconds=60 * 60
)


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
        
        # Every branch below either transcribes, calls the model, or both, so
        # the spend gate goes here rather than per-branch.
        retry_after = voice_limiter.retry_after(user_id)
        if retry_after:
            return {
                "type": "error",
                "error": "rate_limited",
                "message": (
                    f"Voice limit reached ({VOICE_MAX_TURNS_PER_HOUR} per hour). "
                    f"Please retry in {retry_after // 60}m {retry_after % 60}s."
                ),
                "retry_after": retry_after,
            }
        voice_limiter.record(user_id)

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
            # Client sends a single utterance as base64 in `audio`, with an
            # optional `mime` hint (defaults to audio/webm — what Chrome's
            # MediaRecorder emits). We transcribe, then route the resulting
            # text through the same GPT path as a text message so all the
            # downstream function-calling, draft state, and error handling
            # behaves identically regardless of input modality.
            b64 = message_data.get("audio", "")
            mime = message_data.get("mime", "audio/webm")
            if not b64:
                return {
                    "type": "error",
                    "error": "empty_audio",
                    "message": "No audio payload received."
                }
            # Check the encoded length first so an oversized frame is refused
            # without materialising the decoded bytes.
            if len(b64) > MAX_AUDIO_BYTES * 4 // 3 + 8:
                return {
                    "type": "error",
                    "error": "audio_too_large",
                    "message": (
                        f"Audio clip too large "
                        f"(limit {MAX_AUDIO_BYTES // (1024 * 1024)} MB). "
                        f"Please record a shorter message."
                    ),
                }

            try:
                audio_bytes = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError):
                return {
                    "type": "error",
                    "error": "bad_audio_encoding",
                    "message": "Audio payload was not valid base64."
                }

            if len(audio_bytes) > MAX_AUDIO_BYTES:
                return {
                    "type": "error",
                    "error": "audio_too_large",
                    "message": (
                        f"Audio clip too large "
                        f"(limit {MAX_AUDIO_BYTES // (1024 * 1024)} MB). "
                        f"Please record a shorter message."
                    ),
                }

            try:
                transcript = await self.ai_handler.transcribe_audio(audio_bytes, mime)
            except Exception as e:
                logger.exception("Voice transcription failed for user=%s", user_id)
                return {
                    "type": "transcription_failed",
                    "error": "transcription_error",
                    "message": f"Transcription failed: {e}"
                }

            if not transcript:
                # Empty transcript usually means silence or unintelligible
                # audio — surface that to the client so the UI can prompt
                # the user to retry rather than spinning forever.
                return {
                    "type": "transcription_failed",
                    "error": "empty_transcript",
                    "message": "Couldn't hear anything — please try again."
                }

            result = await self.ai_handler.process_message(transcript, session, executor)
            return {
                "type": "response",
                "transcript": transcript,
                "response": result["message"],
                "function_called": result.get("function_called"),
                "draft": result.get("draft"),
                "state": session.state.value
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
