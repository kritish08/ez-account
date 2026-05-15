"""Shared holder for the voice WebSocket session manager.

The manager itself can't be constructed at module-import time because
its __init__ schedules a background task and needs a running event
loop, so we build it inside the FastAPI lifespan and stash it here.
Both server.py (lifespan) and app/routers/voice.py (handler) import
this module to set/read the singleton.
"""

from typing import Optional

# Holds the active WebSocketSessionManager instance once lifespan starts it.
# Voice endpoints check this for None before processing — if lifespan hasn't
# finished, requests are rejected rather than crashing on attribute access.
manager: Optional[object] = None


def set_manager(m: object) -> None:
    global manager
    manager = m


def get_manager() -> Optional[object]:
    return manager
