"""Spend and payload controls on the voice socket.

process_message is the WebSocket dispatch point. It transcribes and then
runs a model turn, so it costs money per call, and it previously
accepted an audio payload of any size and any number of turns.
"""

import base64

import pytest
import pytest_asyncio

from services.websocket_session_manager import WebSocketSessionManager


@pytest_asyncio.fixture
async def manager(db, monkeypatch):
    """A manager with the AI layer stubbed out.

    These tests are about the gates in front of the model, not the model.
    """
    mgr = WebSocketSessionManager(db)

    class StubAI:
        async def transcribe_audio(self, audio_bytes, mime="audio/webm"):
            return "transcribed text"

        async def process_message(self, message, session, executor):
            return {"success": True, "message": "ok", "function_called": None}

    mgr.ai_handler = StubAI()

    # Seed sessions directly — connect() needs a live WebSocket, and these
    # tests are about what happens after a client is already connected.
    from services.voice_session import VoiceSession

    for uid in ("user-1", "user-2"):
        mgr.active_sessions[uid] = VoiceSession(user_id=uid)
    return mgr


@pytest.mark.asyncio
async def test_oversized_audio_is_rejected_before_transcription(manager):
    """An unbounded payload was a free way to run up a transcription bill."""
    from services import websocket_session_manager as wsm

    too_big = b"\x00" * (wsm.MAX_AUDIO_BYTES + 1)
    payload = base64.b64encode(too_big).decode()

    resp = await manager.process_message(
        "user-1", {"type": "audio", "audio": payload}
    )

    assert resp["type"] == "error"
    assert resp["error"] == "audio_too_large"


@pytest.mark.asyncio
async def test_audio_within_the_cap_is_accepted(manager):
    small = base64.b64encode(b"\x00" * 1024).decode()

    resp = await manager.process_message(
        "user-1", {"type": "audio", "audio": small}
    )

    assert resp.get("error") != "audio_too_large"


@pytest.mark.asyncio
async def test_voice_turns_are_capped_per_user(manager, monkeypatch):
    """Past the quota the socket must stop calling the model."""
    from app.services.rate_limit import RateLimiter
    from services import websocket_session_manager as wsm

    monkeypatch.setattr(wsm, "VOICE_MAX_TURNS_PER_HOUR", 3)
    monkeypatch.setattr(
        wsm, "voice_limiter", RateLimiter(max_attempts=3, window_seconds=3600)
    )

    for _ in range(3):
        resp = await manager.process_message("user-1", {"type": "text", "text": "hi"})
        assert resp.get("error") != "rate_limited", resp

    resp = await manager.process_message("user-1", {"type": "text", "text": "hi"})
    assert resp["error"] == "rate_limited"


@pytest.mark.asyncio
async def test_voice_quota_is_per_user(manager, monkeypatch):
    from app.services.rate_limit import RateLimiter
    from services import websocket_session_manager as wsm

    monkeypatch.setattr(wsm, "VOICE_MAX_TURNS_PER_HOUR", 2)
    monkeypatch.setattr(
        wsm, "voice_limiter", RateLimiter(max_attempts=2, window_seconds=3600)
    )

    for _ in range(3):
        await manager.process_message("user-1", {"type": "text", "text": "hi"})

    resp = await manager.process_message("user-2", {"type": "text", "text": "hi"})
    assert resp.get("error") != "rate_limited", resp
