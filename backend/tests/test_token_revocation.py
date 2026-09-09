"""Token revocation.

Logout was client-side only — it deleted the token from localStorage and
the server never heard about it. A token that leaked (XSS, a stolen
device, a shared machine) stayed valid for its full lifetime with no way
to kill it short of rotating JWT_SECRET and signing everybody out.
"""

import pytest


async def _login(http_client, email, password):
    resp = await http_client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_a_fresh_token_works(http_client, test_user):
    token = await _login(http_client, test_user["email"], test_user["password"])
    resp = await http_client.get("/api/auth/me", headers=_hdr(token))
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_logout_revokes_the_presented_token(http_client, test_user):
    """After logout the same token must stop working server-side."""
    token = await _login(http_client, test_user["email"], test_user["password"])

    out = await http_client.post("/api/auth/logout", headers=_hdr(token))
    assert out.status_code == 200, out.text

    resp = await http_client.get("/api/auth/me", headers=_hdr(token))
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_logout_does_not_affect_other_sessions(http_client, test_user):
    """Signing out of one device must not sign out the others."""
    phone = await _login(http_client, test_user["email"], test_user["password"])
    counter = await _login(http_client, test_user["email"], test_user["password"])

    await http_client.post("/api/auth/logout", headers=_hdr(phone))

    assert (await http_client.get("/api/auth/me", headers=_hdr(phone))).status_code == 401
    assert (await http_client.get("/api/auth/me", headers=_hdr(counter))).status_code == 200


@pytest.mark.asyncio
async def test_logout_all_revokes_every_session(http_client, test_user):
    """The incident-response lever: kill every token for this account."""
    phone = await _login(http_client, test_user["email"], test_user["password"])
    counter = await _login(http_client, test_user["email"], test_user["password"])

    out = await http_client.post("/api/auth/logout-all", headers=_hdr(phone))
    assert out.status_code == 200, out.text

    assert (await http_client.get("/api/auth/me", headers=_hdr(phone))).status_code == 401
    assert (await http_client.get("/api/auth/me", headers=_hdr(counter))).status_code == 401


@pytest.mark.asyncio
async def test_a_new_login_after_logout_all_still_works(http_client, test_user):
    """Revoke-all must not brick the account."""
    old = await _login(http_client, test_user["email"], test_user["password"])
    await http_client.post("/api/auth/logout-all", headers=_hdr(old))

    fresh = await _login(http_client, test_user["email"], test_user["password"])
    resp = await http_client.get("/api/auth/me", headers=_hdr(fresh))
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_revoked_token_is_refused_everywhere_not_just_on_auth_me(
    http_client, test_user
):
    """Revocation belongs in the shared dependency, not one endpoint."""
    token = await _login(http_client, test_user["email"], test_user["password"])
    await http_client.post("/api/auth/logout", headers=_hdr(token))

    for path in ("/api/customers", "/api/products", "/api/dashboard"):
        resp = await http_client.get(path, headers=_hdr(token))
        assert resp.status_code == 401, f"{path} accepted a revoked token"


@pytest.mark.asyncio
async def test_tokens_carry_a_unique_id(http_client, test_user):
    """Per-session revocation needs a per-token identifier."""
    from jose import jwt

    from app.config import ALGORITHM, SECRET_KEY

    a = await _login(http_client, test_user["email"], test_user["password"])
    b = await _login(http_client, test_user["email"], test_user["password"])

    claims_a = jwt.decode(a, SECRET_KEY, algorithms=[ALGORITHM])
    claims_b = jwt.decode(b, SECRET_KEY, algorithms=[ALGORITHM])

    assert claims_a["jti"] != claims_b["jti"]
    assert "iat" in claims_a
