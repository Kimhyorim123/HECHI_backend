from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.core.auth import get_admin_user
from app.models import Base, FAQ
import io

# In-memory DB for this test
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

client = TestClient(app)


def register_and_login(email_suffix: str = "cs"):
    reg = {
        "email": f"{email_suffix}@example.com",
        "password": "Pw123456!",
        "name": "User",
        "nickname": "u",
    }
    r = client.post("/auth/register", json=reg)
    assert r.status_code in (200, 201)
    r = client.post("/auth/login", json={"email": reg["email"], "password": reg["password"]})
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_customer_service_flow():
    # Apply overrides locally for this test only
    prev_db = app.dependency_overrides.get(get_db)
    prev_admin = app.dependency_overrides.get(get_admin_user)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = lambda: object()
    
    # Seed 8 FAQs via API (admin override active)
    for i in range(8):
        cr = client.post(
            "/support/faqs",
            json={"question": f"Q{i}", "answer": f"A{i}", "is_pinned": True},
        )
        assert cr.status_code == 200

    r = client.get("/customer-service/faqs")
    assert r.status_code == 200
    body = r.json()
    assert "faqs" in body and isinstance(body["faqs"], list)
    assert len(body["faqs"]) == 7

    headers = register_and_login("user_cs")

    # Create inquiry with a tiny PNG-like payload
    fake_png = io.BytesIO(b"\x89PNG\r\n\x1a\n")
    files = {"inquiryFile": ("x.png", fake_png, "image/png")}
    data = {
        "inquiryTitle": "앱 문의",
        "inquiryDescription": "버튼이 동작하지 않아요",
    }
    cr = client.post("/customer-service/my", headers=headers, files=files, data=data)
    assert cr.status_code in (200, 201)
    created = cr.json()
    assert created["inquiryTitle"] == data["inquiryTitle"]
    assert created["status"] == "waiting"

    lr = client.get("/customer-service/my", headers=headers)
    assert lr.status_code == 200
    lst = lr.json()
    assert "inquiries" in lst and isinstance(lst["inquiries"], list)
    assert len(lst["inquiries"]) == 1
    assert lst["inquiries"][0]["inquiryTitle"] == data["inquiryTitle"]

    # Restore overrides so other tests get a clean in-memory DB
    if prev_db is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev_db
    if prev_admin is None:
        app.dependency_overrides.pop(get_admin_user, None)
    else:
        app.dependency_overrides[get_admin_user] = prev_admin
