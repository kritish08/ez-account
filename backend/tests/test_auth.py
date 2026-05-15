"""Authentication critical path."""

import time

import pytest


@pytest.mark.asyncio
async def test_login_with_correct_password_returns_token(http_client, test_user):
    resp = await http_client.post(
        "/api/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body.get("token_type", "bearer") == "bearer"


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(http_client, test_user):
    resp = await http_client.post(
        "/api/auth/login",
        json={"email": test_user["email"], "password": "definitely-not-it"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_with_unknown_email_returns_401(http_client):
    resp = await http_client.post(
        "/api/auth/login",
        json={"email": "nobody@nowhere.example", "password": "anything"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_timing_is_email_agnostic(http_client, test_user):
    """Bcrypt-verify against a dummy hash on unknown-email paths so timing
    can't be used to enumerate registered accounts. Tolerance is loose
    because CI is jittery; we only fail when there's an order-of-magnitude
    skew (which is what an unguarded bcrypt path looks like)."""
    runs = 5

    known_durations = []
    for _ in range(runs):
        t0 = time.perf_counter()
        await http_client.post(
            "/api/auth/login",
            json={"email": test_user["email"], "password": "wrong-password"},
        )
        known_durations.append(time.perf_counter() - t0)

    unknown_durations = []
    for _ in range(runs):
        t0 = time.perf_counter()
        await http_client.post(
            "/api/auth/login",
            json={"email": "ghost@example.com", "password": "wrong-password"},
        )
        unknown_durations.append(time.perf_counter() - t0)

    known_med = sorted(known_durations)[runs // 2]
    unknown_med = sorted(unknown_durations)[runs // 2]
    # Both should be in the same order of magnitude. An unguarded
    # implementation skips bcrypt for unknown emails (~ms) but runs it
    # for known ones (~80ms), producing a 10–50x gap.
    ratio = max(known_med, unknown_med) / max(min(known_med, unknown_med), 1e-6)
    assert ratio < 5.0, f"login timing leaks: known={known_med:.3f}s vs unknown={unknown_med:.3f}s"


@pytest.mark.asyncio
async def test_me_endpoint_requires_token(http_client):
    resp = await http_client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_endpoint_returns_user(http_client, auth_headers, test_user):
    resp = await http_client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == test_user["email"]
