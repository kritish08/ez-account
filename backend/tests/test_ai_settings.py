"""Bring-your-own-key for OpenAI: the key lives in Settings, not only in env.

The deployment env var still works — an existing install must not break —
but a key saved through the UI takes precedence, is encrypted at rest like
the S3 secret, and is never returned to the client. Changing it takes
effect without a restart, which is the whole point of moving it out of the
environment.
"""

import uuid
from datetime import datetime, timezone

import bcrypt
import pytest

from app.config import MASTER_ENCRYPTION_KEY
from app.services.crypto import decrypt_secret, is_encrypted_secret

REAL_LOOKING_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH"


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


@pytest.fixture(autouse=True)
def _clear_credential_cache():
    """The resolver caches; every test starts from a cold one."""
    from app.services import ai_credentials

    ai_credentials.invalidate()
    yield
    ai_credentials.invalidate()


# ---------------------------------------------------------------- endpoints


@pytest.mark.asyncio
async def test_unconfigured_reports_the_env_fallback(http_client, auth_headers, monkeypatch):
    """With nothing saved, the page must say where the key is coming from."""
    monkeypatch.setenv("OPENAI_API_KEY", REAL_LOOKING_KEY)

    resp = await http_client.get("/api/settings/openai", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True
    assert body["source"] == "env"


@pytest.mark.asyncio
async def test_reports_unconfigured_when_there_is_no_key_anywhere(
    http_client, auth_headers, monkeypatch
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    resp = await http_client.get("/api/settings/openai", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is False
    assert body["source"] == "none"


@pytest.mark.asyncio
async def test_saving_a_key_encrypts_it_at_rest(http_client, auth_headers, db):
    """The settings collection ships inside every backup archive."""
    resp = await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": REAL_LOOKING_KEY},
    )
    assert resp.status_code == 200, resp.text

    doc = await db.settings.find_one({"type": "openai"})
    stored = doc["api_key"]
    assert is_encrypted_secret(stored), stored[:16]
    assert REAL_LOOKING_KEY not in str(doc)
    assert decrypt_secret(stored, MASTER_ENCRYPTION_KEY) == REAL_LOOKING_KEY


@pytest.mark.asyncio
async def test_the_key_is_never_returned_to_the_client(http_client, auth_headers):
    await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": REAL_LOOKING_KEY},
    )

    resp = await http_client.get("/api/settings/openai", headers=auth_headers)

    body = resp.json()
    assert REAL_LOOKING_KEY not in resp.text
    assert body["configured"] is True
    assert body["source"] == "settings"
    # A hint is fine — it is how you tell two keys apart — but only the tail.
    assert body["key_hint"].endswith(REAL_LOOKING_KEY[-4:])
    assert REAL_LOOKING_KEY[:20] not in body["key_hint"]


@pytest.mark.asyncio
async def test_editing_other_fields_keeps_the_stored_key(http_client, auth_headers, db):
    """The client sends back the mask when it isn't changing the key."""
    await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": REAL_LOOKING_KEY},
    )

    resp = await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": "********", "model": "gpt-5.6-mini"},
    )
    assert resp.status_code == 200, resp.text

    doc = await db.settings.find_one({"type": "openai"})
    assert decrypt_secret(doc["api_key"], MASTER_ENCRYPTION_KEY) == REAL_LOOKING_KEY
    assert doc["model"] == "gpt-5.6-mini"


@pytest.mark.asyncio
async def test_a_masked_save_with_nothing_stored_is_refused(http_client, auth_headers):
    resp = await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": "********"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_an_obviously_malformed_key_is_refused(http_client, auth_headers):
    """Catch the paste error at the door rather than on the first invoice."""
    resp = await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": "not-a-key"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_staff_cannot_change_the_key(http_client, db):
    """An API key is spend authority — it belongs behind the admin gate."""
    await _seed_user(db, "aistaff@example.com", "staff_password_123", role="staff")
    headers = await _login(http_client, "aistaff@example.com", "staff_password_123")

    resp = await http_client.post(
        "/api/settings/openai", headers=headers, json={"api_key": REAL_LOOKING_KEY}
    )
    assert resp.status_code == 403

    resp = await http_client.delete("/api/settings/openai", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_removing_the_key_falls_back_to_env(
    http_client, auth_headers, monkeypatch, db
):
    monkeypatch.setenv("OPENAI_API_KEY", REAL_LOOKING_KEY)
    await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": "sk-proj-zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"},
    )

    resp = await http_client.delete("/api/settings/openai", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    body = (await http_client.get("/api/settings/openai", headers=auth_headers)).json()
    assert body["source"] == "env"
    assert await db.settings.find_one({"type": "openai"}) is None


# ---------------------------------------------------------------- resolver


@pytest.mark.asyncio
async def test_a_saved_key_beats_the_environment(http_client, auth_headers, monkeypatch):
    from app.services import ai_credentials

    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-env000000000000000000000000000000000000")
    await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": REAL_LOOKING_KEY},
    )

    creds = await ai_credentials.resolve()

    assert creds.api_key == REAL_LOOKING_KEY
    assert creds.source == "settings"


@pytest.mark.asyncio
async def test_the_environment_is_used_when_nothing_is_saved(monkeypatch):
    from app.services import ai_credentials

    monkeypatch.setenv("OPENAI_API_KEY", REAL_LOOKING_KEY)
    ai_credentials.invalidate()

    creds = await ai_credentials.resolve()

    assert creds.api_key == REAL_LOOKING_KEY
    assert creds.source == "env"


@pytest.mark.asyncio
async def test_no_key_anywhere_resolves_to_nothing(monkeypatch):
    from app.services import ai_credentials

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ai_credentials.invalidate()

    assert await ai_credentials.resolve() is None
    assert await ai_credentials.is_configured() is False


@pytest.mark.asyncio
async def test_changing_the_key_takes_effect_without_a_restart(
    http_client, auth_headers
):
    """The reason for moving the key out of the environment at all."""
    from app.services import ai_credentials

    await http_client.post(
        "/api/settings/openai", headers=auth_headers, json={"api_key": REAL_LOOKING_KEY}
    )
    assert (await ai_credentials.resolve()).api_key == REAL_LOOKING_KEY

    second = "sk-proj-second000000000000000000000000000000000"
    await http_client.post(
        "/api/settings/openai", headers=auth_headers, json={"api_key": second}
    )

    assert (await ai_credentials.resolve()).api_key == second


@pytest.mark.asyncio
async def test_model_choices_come_from_settings_then_env_then_default(
    http_client, auth_headers, monkeypatch
):
    from app.services import ai_credentials

    monkeypatch.setenv("OPENAI_API_KEY", REAL_LOOKING_KEY)
    monkeypatch.setenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
    ai_credentials.invalidate()

    await http_client.post(
        "/api/settings/openai",
        headers=auth_headers,
        json={"api_key": REAL_LOOKING_KEY, "model": "gpt-5.6-mini"},
    )
    creds = await ai_credentials.resolve()

    assert creds.model == "gpt-5.6-mini"        # from settings
    assert creds.transcribe_model == "whisper-1"  # settings silent, env speaks
    assert creds.vision_model                      # neither: a default, not None


# ---------------------------------------------------------------- consumers


@pytest.mark.asyncio
async def test_the_invoice_parser_uses_the_saved_key(http_client, auth_headers):
    """ai_service must not read os.environ behind the resolver's back."""
    import services.ai_service as ai_service

    await http_client.post(
        "/api/settings/openai", headers=auth_headers, json={"api_key": REAL_LOOKING_KEY}
    )
    ai_service.reset_client()

    client = await ai_service.get_client()

    assert client is not None
    assert client.api_key == REAL_LOOKING_KEY


@pytest.mark.asyncio
async def test_the_voice_handler_uses_the_saved_key(http_client, auth_headers):
    from services.voice_ai_handler import VoiceAIHandler

    await http_client.post(
        "/api/settings/openai", headers=auth_headers, json={"api_key": REAL_LOOKING_KEY}
    )

    # Constructing must not need a key — the manager is built at boot, long
    # before anyone has pasted one in.
    handler = VoiceAIHandler()
    client = await handler.get_client()

    assert client.api_key == REAL_LOOKING_KEY


@pytest.mark.asyncio
async def test_the_voice_handler_can_be_built_with_no_key_at_all(monkeypatch):
    from services.voice_ai_handler import VoiceAIHandler
    from app.services import ai_credentials

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ai_credentials.invalidate()

    handler = VoiceAIHandler()          # boots
    with pytest.raises(RuntimeError):   # and explains itself at use
        await handler.get_client()


# ---------------------------------------------------------------- test button


@pytest.mark.asyncio
async def test_the_test_button_reports_a_bad_key_without_echoing_it(
    http_client, auth_headers, monkeypatch
):
    import app.routers.settings as settings_router

    async def _fail(api_key, base_url):
        raise RuntimeError(f"Incorrect API key provided: {api_key}")

    monkeypatch.setattr(settings_router, "_probe_openai", _fail)

    resp = await http_client.post(
        "/api/settings/openai/test",
        headers=auth_headers,
        json={"api_key": REAL_LOOKING_KEY},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert REAL_LOOKING_KEY not in resp.text


@pytest.mark.asyncio
async def test_the_test_button_reports_success(http_client, auth_headers, monkeypatch):
    import app.routers.settings as settings_router

    async def _ok(api_key, base_url):
        return ["gpt-5.6", "gpt-4o-transcribe"]

    monkeypatch.setattr(settings_router, "_probe_openai", _ok)

    resp = await http_client.post(
        "/api/settings/openai/test",
        headers=auth_headers,
        json={"api_key": REAL_LOOKING_KEY},
    )

    body = resp.json()
    assert body["success"] is True
    assert "gpt-5.6" in body["message"] or "gpt-5.6" in str(body.get("models", ""))


@pytest.mark.asyncio
async def test_the_test_button_can_check_the_stored_key(
    http_client, auth_headers, monkeypatch
):
    """Masked key means 'test what you already have', as S3 does."""
    import app.routers.settings as settings_router

    seen = {}

    async def _capture(api_key, base_url):
        seen["api_key"] = api_key
        return ["gpt-5.6"]

    monkeypatch.setattr(settings_router, "_probe_openai", _capture)
    await http_client.post(
        "/api/settings/openai", headers=auth_headers, json={"api_key": REAL_LOOKING_KEY}
    )

    resp = await http_client.post(
        "/api/settings/openai/test", headers=auth_headers, json={"api_key": "********"}
    )

    assert resp.json()["success"] is True
    assert seen["api_key"] == REAL_LOOKING_KEY
