import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.models import Base

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_password_reset_flow_success():
    email = f"pwreset_{uuid.uuid4().hex[:8]}@example.com"
    original_pw = "OldPassword123!"
    new_pw = "NewPassword456!"

    # register
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": original_pw,
            "name": "ResetUser",
            "nickname": "ru",
        },
    )
    assert r.status_code in (200, 201)

    # request reset (exists true)
    req = client.post("/auth/password-reset/request", json={"email": email})
    assert req.status_code == 200
    assert req.json()["exists"] is True

    # confirm reset
    conf = client.post(
        "/auth/password-reset/confirm",
        json={"email": email, "new_password": new_pw},
    )
    assert conf.status_code == 200
    assert conf.json()["ok"] is True

    # login with old password should fail
    old_login = client.post("/auth/login", json={"email": email, "password": original_pw})
    assert old_login.status_code == 401

    # login with new password succeeds
    new_login = client.post("/auth/login", json={"email": email, "password": new_pw})
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()


def test_password_reset_nonexistent_email():
    email = f"noexist_{uuid.uuid4().hex[:8]}@example.com"

    # request reset (exists false)
    req = client.post("/auth/password-reset/request", json={"email": email})
    assert req.status_code == 200
    assert req.json()["exists"] is False

    # confirm reset should 404
    conf = client.post(
        "/auth/password-reset/confirm",
        json={"email": email, "new_password": "Whatever123!"},
    )
    assert conf.status_code == 404
