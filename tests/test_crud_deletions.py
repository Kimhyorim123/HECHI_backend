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


def setup_user():
    email = f"crud_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Pw123456!"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": pw, "name": "C", "nickname": "D"},
    )
    assert r.status_code in (200, 201)
    login = client.post("/auth/login", json={"email": email, "password": pw})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_book(headers):
    r = client.post(
        "/books",
        json={"title": "CrudBook", "authors": [], "total_pages": 50},
        headers=headers,
    )
    assert r.status_code == 200
    return r.json()["id"]


def test_note_update_and_delete():
    headers = setup_user()
    book_id = create_book(headers)

    # create note
    rn = client.post("/notes/", json={"book_id": book_id, "page": 3, "content": "first"}, headers=headers)
    assert rn.status_code == 200
    note_id = rn.json()["id"]

    # update
    up = client.put(f"/notes/{note_id}", json={"content": "updated"}, headers=headers)
    assert up.status_code == 200
    assert up.json()["content"] == "updated"

    # delete
    dl = client.delete(f"/notes/{note_id}", headers=headers)
    assert dl.status_code == 204

    # fetch list should be empty
    lst = client.get(f"/notes/books/{book_id}", headers=headers)
    assert lst.status_code == 200
    assert lst.json() == []


def test_highlight_update_and_delete():
    headers = setup_user()
    book_id = create_book(headers)

    rh = client.post(
        "/highlights/",
        json={"book_id": book_id, "page": 5, "sentence": "abc", "is_public": True},
        headers=headers,
    )
    assert rh.status_code == 200
    hid = rh.json()["id"]

    up = client.put(
        f"/highlights/{hid}",
        json={"sentence": "changed", "is_public": False},
        headers=headers,
    )
    assert up.status_code == 200
    body = up.json()
    assert body["sentence"] == "changed"
    assert body["is_public"] is False

    dl = client.delete(f"/highlights/{hid}", headers=headers)
    assert dl.status_code == 204

    lst = client.get(f"/highlights/books/{book_id}", headers=headers)
    assert lst.status_code == 200
    assert lst.json() == []


def test_bookmark_delete():
    headers = setup_user()
    book_id = create_book(headers)

    rbm = client.post(
        "/bookmarks/",
        json={"book_id": book_id, "page": 10, "memo": "mark"},
        headers=headers,
    )
    assert rbm.status_code == 200
    bid = rbm.json()["id"]

    dl = client.delete(f"/bookmarks/{bid}", headers=headers)
    assert dl.status_code == 204

    lst = client.get(f"/bookmarks/books/{book_id}", headers=headers)
    assert lst.status_code == 200
    assert lst.json() == []
