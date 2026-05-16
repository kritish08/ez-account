"""Shared pytest fixtures.

Each pytest run gets its own throw-away Mongo database (`ezaccount_test_<rand>`)
so parallel CI shards never collide. Within a session, the autouse
`clean_db` fixture wipes every collection between tests for isolation.

DB_NAME / MONGO_URL / JWT_SECRET / MASTER_ENCRYPTION_KEY are set at
module import time, BEFORE any `app.*` modules are imported — because
`app.database` creates its Motor client at import-time using whatever
DB_NAME is in the env at that moment. Re-importing later won't help.
"""

import os
import uuid

# These two MUST be set before any `app.*` import.
TEST_DB_NAME = f"ezaccount_test_{uuid.uuid4().hex[:8]}"
os.environ["DB_NAME"] = TEST_DB_NAME
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/?directConnection=true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-prod")
os.environ.setdefault("MASTER_ENCRYPTION_KEY", "0" * 64)
os.environ.setdefault("CORS_ORIGINS", "http://localhost")
# Voice creds aren't needed for the suites here, but the lifespan
# tries to construct a VoiceAIHandler — give it stubs so import doesn't
# crash.
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://placeholder.openai.azure.com/")
os.environ.setdefault("AZURE_OPENAI_KEY", "placeholder")

import bcrypt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture
async def db():
    """The Motor DB handle the app is using."""
    from app.database import db as _db
    return _db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Drop every collection between tests so state never leaks."""
    from app.database import db as _db
    for name in await _db.list_collection_names():
        await _db.drop_collection(name)
    yield


@pytest_asyncio.fixture
async def app_instance():
    """Build the FastAPI app on demand so env vars are already set."""
    from server import app
    return app


@pytest_asyncio.fixture
async def http_client(app_instance):
    """Async HTTP client speaking directly to the ASGI app — no socket."""
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def test_user(db):
    """Seed a known user and return its credentials."""
    from datetime import datetime, timezone

    email = "tester@example.com"
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": "Tester",
        "password_hash": password_hash,
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)
    return {"email": email, "password": password, "id": user_doc["id"]}


@pytest_asyncio.fixture
async def auth_token(http_client, test_user):
    """Log the seeded user in and return a bearer token string."""
    resp = await http_client.post(
        "/api/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
