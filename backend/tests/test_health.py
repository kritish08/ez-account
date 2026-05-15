"""Smoke: the app boots and the health endpoint responds."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(http_client):
    resp = await http_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
