"""Lightweight liveness probe.

Mounted at both `/api/health` and `/health` so Docker, Traefik, and any
external uptime monitor can pick whichever path matches their conventions.
Does NOT touch the database — if the process is up enough to serve HTTP,
this returns 200.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
@router.get("/health")
async def health_check():
    return {"status": "ok"}
