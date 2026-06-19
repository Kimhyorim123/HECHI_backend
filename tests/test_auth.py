import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.api import auth as auth_api
from app.core.config import get_settings
from app.database import get_db
from app.models import Base

# In-memory SQLite for tests (shared across threads/connections)
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

# Ensure all tables are created before tests run
Base.metadata.create_all(bind=test_engine)

settings = get_settings()
settings.smtp_host = None
settings.smtp_username = None
settings.smtp_password = None
settings.smtp_from_email = None


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture
def registered_user():
    payload = {
        "email": "tester@example.com",
        "login_id": "tester01",
        "password": "secretpw",
        "name": "Tester",
        "nickname": "testnick",
    }
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201
    return payload


def test_login_and_me_flow(registered_user):
    # Login
    r = client.post("/auth/login", json={"login_id": registered_user["login_id"], "password": registered_user["password"]})
    assert r.status_code == 200
    tokens = r.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    # /auth/me with Bearer
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me_r = client.get("/auth/me", headers=headers)
    assert me_r.status_code == 200
    me = me_r.json()
    assert me["email"] == registered_user["email"]
    assert me["login_id"] == registered_user["login_id"]

    # Refresh
    ref_r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert ref_r.status_code == 200
    new_tokens = ref_r.json()
    assert new_tokens["access_token"] != tokens["access_token"]


def test_me_unauthorized():
    r = client.get("/auth/me")
    assert r.status_code == 403 or r.status_code == 401  # HTTPBearer auto_error True gives 403


def test_invalid_token():
    r = client.get("/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
    # Should fail with 401
    assert r.status_code == 401


def test_email_verification_flow(monkeypatch):
    settings.smtp_host = "smtp.gmail.com"
    settings.smtp_username = "test@example.com"
    settings.smtp_password = "app-password"
    settings.smtp_from_email = "test@example.com"
    monkeypatch.setattr(auth_api, "generate_verification_code", lambda: "123456")
    monkeypatch.setattr(auth_api, "send_verification_email", lambda email, code: None)

    payload = {
        "email": "verify@example.com",
        "login_id": "verify_user",
        "password": "secretpw",
        "name": "Verifier",
        "nickname": "verify",
    }
    reg = client.post("/auth/register", json=payload)
    assert reg.status_code == 201
    assert reg.json()["email_verified"] is False

    blocked = client.post("/auth/login", json={"login_id": payload["login_id"], "password": payload["password"]})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Email not verified"

    verified = client.post("/auth/verify-email", json={"email": payload["email"], "code": "123456"})
    assert verified.status_code == 200
    assert verified.json()["email_verified"] is True

    allowed = client.post("/auth/login", json={"login_id": payload["login_id"], "password": payload["password"]})
    assert allowed.status_code == 200

    settings.smtp_host = None
    settings.smtp_username = None
    settings.smtp_password = None
    settings.smtp_from_email = None
