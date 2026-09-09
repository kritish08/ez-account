"""Voice assistant WebSocket + stats.

The session manager singleton is built inside the FastAPI lifespan
(server.py) and stashed in `app.voice_state.manager`. Both endpoints
read it from there.

Auth on the WS handshake supports two paths:
- Path A: legacy `?token=<jwt>` query string — accepted but deprecated
  (logs warning; query strings leak via proxy logs and browser history).
- Path B: token in the first JSON frame — `{"type":"auth","token":"<jwt>"}`.
  Preferred for new clients.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.config import ALGORITHM, SECRET_KEY
from app.deps import security
from app.services import ai_credentials
from app.voice_state import get_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


@router.websocket("/ws/voice")
async def voice_assistant_websocket(websocket: WebSocket, token: Optional[str] = None):
    """WebSocket endpoint for the voice assistant.

    Auth: client opens the socket then sends an auth message as its FIRST
    frame: {"type": "auth", "token": "<jwt>"}.  Query-param token is
    accepted for back-compat but deprecated — query strings get logged
    by proxies and stored in browser history, leaking the JWT.
    """
    await websocket.accept()
    user_id: Optional[str] = None

    # ---- Path A: legacy ?token= query param ----
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
        except JWTError:
            user_id = None
        if not user_id:
            await websocket.send_json({"type": "auth_failed", "message": "Invalid token"})
            await websocket.close(code=1008, reason="Invalid token")
            return
        logger.warning(
            "Voice WS: deprecated query-string token used. "
            "Client should send {type:'auth', token:...} as first message instead."
        )
    else:
        # ---- Path B: token in first-message handshake (preferred) ----
        await websocket.send_json({"type": "auth_required"})
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        except asyncio.TimeoutError:
            await websocket.close(code=1008, reason="Auth timeout")
            return
        except WebSocketDisconnect:
            return
        if not isinstance(first, dict) or first.get("type") != "auth" or not first.get("token"):
            await websocket.send_json({"type": "auth_failed", "message": "Expected {type:'auth', token:...} as first message"})
            await websocket.close(code=1008, reason="Auth required")
            return
        try:
            payload = jwt.decode(first["token"], SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
        except JWTError:
            user_id = None
        if not user_id:
            await websocket.send_json({"type": "auth_failed", "message": "Invalid token"})
            await websocket.close(code=1008, reason="Invalid token")
            return

    # ---- Authenticated — start session ----
    ws_session_manager = get_manager()
    if ws_session_manager is None:
        await websocket.send_json({"type": "error", "message": "Voice subsystem not ready"})
        await websocket.close(code=1011, reason="Voice subsystem not ready")
        return

    # The manager builds without a credential — the key is pasted into
    # Settings, possibly long after boot. Say so here rather than letting
    # the first spoken sentence fail somewhere inside the tool loop.
    if not await ai_credentials.is_configured():
        await websocket.send_json({
            "type": "error",
            "message": "The voice assistant needs an OpenAI API key. "
                       "Add one in Settings → AI.",
        })
        await websocket.close(code=1011, reason="No OpenAI key configured")
        return

    try:
        # The manager's connect() also calls websocket.accept() — that's a
        # no-op on an already-accepted socket. Resume/create the session.
        session = await ws_session_manager.connect(user_id, websocket)
        logger.info(f"Voice assistant connected: user={user_id}, session={session.session_id}")

        while True:
            data = await websocket.receive_json()
            response = await ws_session_manager.process_message(user_id, data)
            await websocket.send_json(response)

    except WebSocketDisconnect:
        logger.info(f"Voice assistant disconnected: user={user_id}")
        await ws_session_manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Voice assistant error: user={user_id}, error={str(e)}")
        await ws_session_manager.disconnect(user_id)
        await websocket.close(code=1011, reason="Internal error")


@router.get("/api/voice/stats")
async def get_voice_stats(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Voice assistant statistics — active sessions, states, etc."""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid authentication")

    ws_session_manager = get_manager()
    if ws_session_manager is None:
        raise HTTPException(status_code=503, detail="Voice subsystem not ready")

    return ws_session_manager.get_session_stats()
