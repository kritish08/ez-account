"""Access control on the destructive backup endpoints.

POST /backup/restore does `delete_many({})` then `insert_many` across
every collection in the archive. It is the single most destructive
operation in the product — more so than the factory reset, which at
least preserves nothing worth preserving. It must be defended at least
as well.
"""

import uuid
from datetime import datetime, timezone

import bcrypt
import pytest


async def _login(http_client, email, password):
    resp = await http_client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed_user(db, email, password, role=None):
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": email.split("@")[0],
        "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if role is not None:
        doc["role"] = role
    await db.users.insert_one(doc)
    return doc


@pytest.mark.asyncio
async def test_restore_requires_a_confirmation_body(http_client, auth_headers):
    """A bare authenticated POST must not be able to wipe the database.

    Regression: restore took no body at all. Any logged-in user — or
    anyone holding a stolen 24-hour token — could roll the live books
    back to an arbitrary archive, or wipe collections absent from it,
    with a single request and no confirmation of any kind.
    """
    resp = await http_client.post(
        "/api/backup/restore/some-backup.enc", headers=auth_headers
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_restore_rejects_a_wrong_password(http_client, auth_headers):
    """Re-entering the password is what a stolen token cannot do."""
    resp = await http_client.post(
        "/api/backup/restore/some-backup.enc",
        headers=auth_headers,
        json={
            "password": "not-the-right-password",
            "confirmation": "RESTORE AND OVERWRITE ALL DATA",
        },
    )
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_restore_rejects_a_wrong_confirmation_phrase(
    http_client, auth_headers, test_user
):
    """The verbatim phrase stops an accidental click."""
    resp = await http_client.post(
        "/api/backup/restore/some-backup.enc",
        headers=auth_headers,
        json={"password": test_user["password"], "confirmation": "yes"},
    )
    assert resp.status_code == 400, resp.text
    # Assert on the reason too — "S3 not configured" is also a 400, so a
    # bare status check here would pass without the gate existing at all.
    assert "confirmation" in resp.json()["detail"].lower(), resp.text


@pytest.mark.asyncio
async def test_restore_is_refused_for_non_admin_users(http_client, db):
    """A staff login must not be able to restore, even with the password."""
    await _seed_user(db, "staff@example.com", "staff_password_123", role="staff")
    headers = await _login(http_client, "staff@example.com", "staff_password_123")

    resp = await http_client.post(
        "/api/backup/restore/some-backup.enc",
        headers=headers,
        json={
            "password": "staff_password_123",
            "confirmation": "RESTORE AND OVERWRITE ALL DATA",
        },
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_factory_reset_is_refused_for_non_admin_users(http_client, db):
    """Same gate on the other destructive endpoint."""
    await _seed_user(db, "staff2@example.com", "staff_password_123", role="staff")
    headers = await _login(http_client, "staff2@example.com", "staff_password_123")

    resp = await http_client.post(
        "/api/system/reset",
        headers=headers,
        json={
            "password": "staff_password_123",
            "confirmation": "DELETE ALL ACCOUNTING DATA",
        },
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_users_without_an_explicit_role_keep_admin_access(http_client, db):
    """Back-compat: existing single-tenant deployments must not lock out.

    No code ever wrote a `role` onto a user except the provisioning
    scripts, so live databases contain users with no role at all.
    Treating those as non-admin would lock the owner out of their own
    backups on upgrade.
    """
    await _seed_user(db, "legacy@example.com", "legacy_password_123", role=None)
    headers = await _login(http_client, "legacy@example.com", "legacy_password_123")

    resp = await http_client.post(
        "/api/backup/restore/some-backup.enc",
        headers=headers,
        json={
            "password": "legacy_password_123",
            "confirmation": "RESTORE AND OVERWRITE ALL DATA",
        },
    )
    # Passes the auth gate; fails later on unconfigured S3, not on 403.
    assert resp.status_code != 403, resp.text
