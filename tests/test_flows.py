import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
import uuid
from app.database import get_db
from app.models import Base

# Shared in-memory SQLite for this test module
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


@pytest.fixture
def auth_headers():
    # register
    reg = {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "pw123456",
        "name": "User1",
        "nickname": "u1",
    }
    r = client.post("/auth/register", json=reg)
    assert r.status_code in (200, 201)
    # login
    r = client.post("/auth/login", json={"email": reg["email"], "password": reg["password"]})
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_book_note_highlight_bookmark_review_and_overview(auth_headers):
    # create a book
    book_payload = {
        "isbn": "1234567890123",
        "title": "테스트 북",
        "publisher": "테스트 출판사",
        "category": "Fiction / Romance / Contemporary",
        "total_pages": 200,
        "authors": ["홍길동"],
    }
    rb = client.post("/books", json=book_payload, headers=auth_headers)
    assert rb.status_code == 200
    book = rb.json()
    book_id = book["id"]

    # note
    rn = client.post("/notes/", json={"book_id": book_id, "page": 5, "content": "메모"}, headers=auth_headers)
    assert rn.status_code == 200

    # highlight
    rh = client.post(
        "/highlights/",
        json={"book_id": book_id, "page": 10, "sentence": "문장", "is_public": True},
        headers=auth_headers,
    )
    assert rh.status_code == 200

    # bookmark
    rbm = client.post(
        "/bookmarks/",
        json={"book_id": book_id, "page": 15, "memo": "표시"},
        headers=auth_headers,
    )
    assert rbm.status_code == 200

    # review
    rr = client.post(
        "/reviews/",
        json={"book_id": book_id, "rating": 5, "content": "좋아요", "is_spoiler": False},
        headers=auth_headers,
    )
    assert rr.status_code == 200

    # taste overview reflects 1 review and rating dist
    to = client.get("/taste/overview", headers=auth_headers)
    assert to.status_code == 200
    data = to.json()
    assert data["total_reviews"] == 1
    assert data["rating_distribution"]["5"] == 1


def test_reading_sessions_status_summary_and_analytics(auth_headers):
    # create book
    rb = client.post(
        "/books",
        json={"title": "Another", "authors": [], "total_pages": 100},
        headers=auth_headers,
    )
    book_id = rb.json()["id"]

    # start reading session
    rs = client.post("/reading/sessions", json={"book_id": book_id, "start_page": 1}, headers=auth_headers)
    assert rs.status_code == 200
    session_id = rs.json()["id"]

    # add event
    ev = client.post(
        f"/reading/sessions/{session_id}/events",
        json={"event_type": "PAGE_TURN", "page": 2},
        headers=auth_headers,
    )
    assert ev.status_code == 200

    # end session with total_seconds
    re = client.post(
        f"/reading/sessions/{session_id}/end",
        json={"end_page": 10, "total_seconds": 120},
        headers=auth_headers,
    )
    assert re.status_code == 200

    # update reading status
    us = client.post(
        "/reading-status/update",
        json={"book_id": book_id, "status": "READING"},
        headers=auth_headers,
    )
    assert us.status_code == 200

    # summary
    sm = client.get(f"/reading-status/summary/{book_id}", headers=auth_headers)
    assert sm.status_code == 200
    js = sm.json()
    assert js["total_time_seconds"] >= 120

    # analytics logs
    a1 = client.post("/analytics/search", json={"query": "Another"}, headers=auth_headers)
    assert a1.status_code == 201
    a2 = client.post("/analytics/views", json={"book_id": book_id}, headers=auth_headers)
    assert a2.status_code == 201
