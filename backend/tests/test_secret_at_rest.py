"""The S3 secret must not sit in the database in plaintext.

Every backup archive includes the `settings` collection, so a plaintext
secret there meant each backup carried the credentials that created it —
alongside the users collection. Anyone reaching the database got working
AWS keys and the bucket name.
"""

import pytest

from app.services.crypto import decrypt_secret, encrypt_secret, is_encrypted_secret

MEK = "0" * 64


def test_round_trip():
    blob = encrypt_secret("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", MEK)
    assert decrypt_secret(blob, MEK) == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


def test_ciphertext_does_not_contain_the_plaintext():
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    blob = encrypt_secret(secret, MEK)
    assert secret not in blob


def test_ciphertext_is_tagged_so_it_can_be_recognised():
    blob = encrypt_secret("some-secret", MEK)
    assert is_encrypted_secret(blob)
    assert not is_encrypted_secret("some-secret")


def test_encryption_is_randomised():
    """Same input twice must not produce the same ciphertext."""
    a = encrypt_secret("same-secret", MEK)
    b = encrypt_secret("same-secret", MEK)
    assert a != b
    assert decrypt_secret(a, MEK) == decrypt_secret(b, MEK) == "same-secret"


def test_legacy_plaintext_values_are_passed_through():
    """Secrets stored before this change must keep working.

    Live databases hold plaintext secrets. Decrypt has to recognise an
    untagged value and hand it back rather than failing, or configured
    backups break on upgrade.
    """
    assert decrypt_secret("legacy-plaintext-secret", MEK) == "legacy-plaintext-secret"


def test_empty_values_round_trip_safely():
    assert encrypt_secret("", MEK) == ""
    assert decrypt_secret("", MEK) == ""


def test_wrong_key_cannot_decrypt():
    blob = encrypt_secret("some-secret", MEK)
    with pytest.raises(Exception):
        decrypt_secret(blob, "1" * 64)


@pytest.mark.asyncio
async def test_saved_s3_secret_is_encrypted_in_the_database(
    http_client, auth_headers, db, monkeypatch
):
    """End-to-end: what lands in db.settings must not be readable."""
    import app.routers.settings as settings_router

    class FakeS3:
        def head_bucket(self, Bucket):
            return {}

    monkeypatch.setattr(settings_router.boto3, "client", lambda *a, **k: FakeS3())

    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    resp = await http_client.post(
        "/api/settings/s3",
        headers=auth_headers,
        json={
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": secret,
            "bucket_name": "ez-backups",
            "region": "ap-south-1",
        },
    )
    assert resp.status_code == 200, resp.text

    stored = await db.settings.find_one({"type": "s3"})
    assert stored["aws_secret_access_key"] != secret
    assert is_encrypted_secret(stored["aws_secret_access_key"])
    assert decrypt_secret(stored["aws_secret_access_key"], MEK) == secret


@pytest.mark.asyncio
async def test_get_still_masks_the_secret(http_client, auth_headers, db, monkeypatch):
    """Encryption at rest must not change what the API returns."""
    import app.routers.settings as settings_router

    class FakeS3:
        def head_bucket(self, Bucket):
            return {}

    monkeypatch.setattr(settings_router.boto3, "client", lambda *a, **k: FakeS3())

    await http_client.post(
        "/api/settings/s3",
        headers=auth_headers,
        json={
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "bucket_name": "ez-backups",
            "region": "ap-south-1",
        },
    )

    resp = await http_client.get("/api/settings/s3", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["aws_secret_access_key"] == "********"
