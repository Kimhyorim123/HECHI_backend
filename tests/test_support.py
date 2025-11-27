import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.models import Base

# Independent in-memory DB for this test module
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


def register_and_login():
    reg = {
        "email": f"support_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Pw123456!",
        "name": "SupportUser",
        "nickname": "sup",
    }
    r = client.post("/auth/register", json=reg)
    assert r.status_code in (200, 201)
    r = client.post("/auth/login", json={"email": reg["email"], "password": reg["password"]})
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_support_faq_limit_and_creation():
    headers = register_and_login()

    # Initially no FAQs
    r = client.get("/support/faqs")
    assert r.status_code == 200
    assert r.json() == []

    # Unauthorized creation should fail
    r_unauth = client.post("/support/faqs", json={"question": "Q1", "answer": "A1", "is_pinned": True})
    assert r_unauth.status_code in (401, 403)

    # Create 8 pinned FAQs (limit should return only 7)
    for i in range(8):
        cr = client.post(
            "/support/faqs",
            json={"question": f"Q{i}", "answer": f"A{i}", "is_pinned": True},
            headers=headers,
        )
        assert cr.status_code == 200
        body = cr.json()
        assert body["question"] == f"Q{i}"

    lr = client.get("/support/faqs")
    assert lr.status_code == 200
    faqs = lr.json()
    assert len(faqs) == 7  # limited to 7 pinned
    # Ensure ordering ascending by id (first created has smallest id)
    ids = [f["id"] for f in faqs]
    assert ids == sorted(ids)


def test_support_tickets_create_and_list():
    headers = register_and_login()

    # Unauthorized ticket create should fail
    r_unauth = client.post(
        "/support/tickets",
        json={"title": "Help", "description": "Need assistance"},
    )
    assert r_unauth.status_code in (401, 403)

    # Create two tickets
    t1 = client.post(
        "/support/tickets",
        json={"title": "Issue1", "description": "Desc1"},
        headers=headers,
    )
    assert t1.status_code == 201
    ticket1 = t1.json()
    # Enum value might be lowercase depending on SQLAlchemy Enum configuration
    assert ticket1["status"].lower() == "open"

    t2 = client.post(
        "/support/tickets",
        json={"title": "Issue2", "description": "Desc2"},
        headers=headers,
    )
    assert t2.status_code == 201
    ticket2 = t2.json()

    # List my tickets (desc order)
    lst = client.get("/support/tickets/me", headers=headers)
    assert lst.status_code == 200
    tickets = lst.json()
    assert len(tickets) == 2
    # First should be most recent (t2)
    assert tickets[0]["id"] == ticket2["id"]
    assert tickets[1]["id"] == ticket1["id"]
