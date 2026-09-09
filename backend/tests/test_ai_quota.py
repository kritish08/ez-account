"""Spend controls on the AI endpoint.

/api/ai/parse-invoice calls a vision model on every request, so an
authenticated user could previously run up an unbounded bill. Rate
limiting here is a cost control first and an abuse control second.
"""

import io

import pytest

from app.routers import ai as ai_router


SMALL_LIMIT = 3


@pytest.fixture(autouse=True)
def small_ai_quota(monkeypatch):
    """Swap in a tiny quota.

    The real limit is 60/hour; driving that end-to-end means ~120 uploads
    per test and dominates the suite runtime. The wiring under test — gate,
    key, 429 shape — is identical at any limit.
    """
    from app.services.rate_limit import RateLimiter

    monkeypatch.setattr(ai_router, "PARSE_MAX_PER_HOUR", SMALL_LIMIT)
    monkeypatch.setattr(
        ai_router,
        "parse_limiter",
        RateLimiter(max_attempts=SMALL_LIMIT, window_seconds=60 * 60),
    )
    yield


def _image_upload():
    return {"file": ("bill.jpg", io.BytesIO(b"\xff\xd8\xff" + b"0" * 64), "image/jpeg")}


@pytest.mark.asyncio
async def test_parse_requests_are_capped_per_user(http_client, auth_headers):
    """Past the hourly quota the endpoint must refuse before spending money."""
    limit = ai_router.PARSE_MAX_PER_HOUR

    for _ in range(limit):
        resp = await http_client.post(
            "/api/ai/parse-invoice", headers=auth_headers, files=_image_upload()
        )
        # Without a real API key the call fails downstream — what matters is
        # that it got PAST the quota gate rather than being refused by it.
        assert resp.status_code != 429, resp.text

    resp = await http_client.post(
        "/api/ai/parse-invoice", headers=auth_headers, files=_image_upload()
    )
    assert resp.status_code == 429, resp.text
    assert "retry" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_quota_is_per_user_not_global(http_client, auth_headers, db):
    """One user exhausting their quota must not block everyone else."""
    import uuid
    from datetime import datetime, timezone

    import bcrypt

    await db.users.insert_one({
        "id": str(uuid.uuid4()),
        "email": "second@example.com",
        "name": "Second",
        "password_hash": bcrypt.hashpw(b"second_password_123", bcrypt.gensalt()).decode(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    login = await http_client.post(
        "/api/auth/login",
        json={"email": "second@example.com", "password": "second_password_123"},
    )
    assert login.status_code == 200, login.text
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for _ in range(ai_router.PARSE_MAX_PER_HOUR + 1):
        await http_client.post(
            "/api/ai/parse-invoice", headers=auth_headers, files=_image_upload()
        )

    resp = await http_client.post(
        "/api/ai/parse-invoice", headers=other_headers, files=_image_upload()
    )
    assert resp.status_code != 429, resp.text
