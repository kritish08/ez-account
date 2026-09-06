"""Login brute-force protection.

Before this, /api/auth/login had no lockout of any kind — the ~80ms
bcrypt cost was the only brake on credential stuffing, and that
parallelises trivially.
"""

import pytest

from app.routers import auth as auth_router


@pytest.fixture(autouse=True)
def clear_login_throttle():
    """Each test starts with an empty attempt map."""
    auth_router.login_limiter._attempts.clear()
    yield
    auth_router.login_limiter._attempts.clear()


async def _attempt(http_client, email, password):
    return await http_client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


@pytest.mark.asyncio
async def test_repeated_failures_are_eventually_locked_out(http_client, test_user):
    """Guessing must stop returning 401 and start returning 429."""
    limit = auth_router.LOGIN_MAX_ATTEMPTS

    for _ in range(limit):
        resp = await _attempt(http_client, test_user["email"], "wrong-password")
        assert resp.status_code == 401, resp.text

    resp = await _attempt(http_client, test_user["email"], "wrong-password")
    assert resp.status_code == 429, resp.text
    assert "retry" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_lockout_also_blocks_the_correct_password(http_client, test_user):
    """Otherwise the lockout is trivially bypassed by the attacker who wins."""
    for _ in range(auth_router.LOGIN_MAX_ATTEMPTS):
        await _attempt(http_client, test_user["email"], "wrong-password")

    resp = await _attempt(http_client, test_user["email"], test_user["password"])
    assert resp.status_code == 429, resp.text


@pytest.mark.asyncio
async def test_a_successful_login_clears_the_counter(http_client, test_user):
    """A typo or two must not leave a legitimate user near a lockout."""
    for _ in range(auth_router.LOGIN_MAX_ATTEMPTS - 1):
        await _attempt(http_client, test_user["email"], "wrong-password")

    ok = await _attempt(http_client, test_user["email"], test_user["password"])
    assert ok.status_code == 200, ok.text

    # Counter cleared, so the budget is full again.
    for _ in range(auth_router.LOGIN_MAX_ATTEMPTS):
        resp = await _attempt(http_client, test_user["email"], "wrong-password")
        assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_throttling_one_account_does_not_lock_another(http_client, test_user, db):
    """Locking must be per-identity, or one attacker denies service to everyone."""
    import uuid
    from datetime import datetime, timezone

    import bcrypt

    other_password = "other_password_123"
    await db.users.insert_one({
        "id": str(uuid.uuid4()),
        "email": "other@example.com",
        "name": "Other",
        "password_hash": bcrypt.hashpw(other_password.encode(), bcrypt.gensalt()).decode(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    for _ in range(auth_router.LOGIN_MAX_ATTEMPTS + 1):
        await _attempt(http_client, test_user["email"], "wrong-password")

    resp = await _attempt(http_client, "other@example.com", other_password)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_unknown_emails_are_throttled_without_revealing_existence(
    http_client
):
    """An unknown address must throttle the same way a known one does.

    If only known accounts locked out, the 429 itself would become an
    email-enumeration oracle — undoing the constant-time login work.
    """
    limit = auth_router.LOGIN_MAX_ATTEMPTS

    for _ in range(limit):
        resp = await _attempt(http_client, "nobody@example.com", "guess")
        assert resp.status_code == 401, resp.text

    resp = await _attempt(http_client, "nobody@example.com", "guess")
    assert resp.status_code == 429, resp.text
