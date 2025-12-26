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


def auth_headers():
    email = f"pag_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Pw123456!"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": pw, "name": "P", "nickname": "G"},
    )
    assert r.status_code in (200, 201)
    lg = client.post("/auth/login", json={"email": email, "password": pw})
    token = lg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_book(headers):
    r = client.post(
        "/books",
        json={"title": "PagBook", "authors": [], "total_pages": 99},
        headers=headers,
    )
    assert r.status_code == 200
    return r.json()["id"]


def bulk_create(headers, book_id):
    # Create 5 highlights, bookmarks with ordered pages; notes are book-level (no page)
    for i in range(1, 6):
        rn = client.post(
            "/notes/",
            json={"book_id": book_id, "content": f"n{i}"},
            headers=headers,
        )
        assert rn.status_code == 200
        rh = client.post(
            "/highlights/",
            json={"book_id": book_id, "page": i, "sentence": f"h{i}", "is_public": False},
            headers=headers,
        )
        assert rh.status_code == 200
        rbm = client.post(
            "/bookmarks/",
            json={"book_id": book_id, "page": i, "memo": f"b{i}"},
            headers=headers,
        )
        assert rbm.status_code == 200


def slice_pages(items):
    return [it["page"] for it in items]


def test_pagination_lists():
    headers = auth_headers()
    book_id = create_book(headers)
    bulk_create(headers, book_id)

    # notes pagination no longer based on pages; basic retrieval
    n1 = client.get(f"/notes/books/{book_id}?limit=2&offset=0", headers=headers)
    assert n1.status_code == 200
    assert isinstance(n1.json(), list)

    # highlights limit 3 offset 0 => pages [1,2,3]
    h1 = client.get(f"/highlights/books/{book_id}?limit=3&offset=0", headers=headers)
    assert h1.status_code == 200
    assert slice_pages(h1.json()) == [1, 2, 3]

    h2 = client.get(f"/highlights/books/{book_id}?limit=3&offset=3", headers=headers)
    assert h2.status_code == 200
    assert slice_pages(h2.json()) == [4, 5]

    # bookmarks limit 4 offset 0 => pages [1,2,3,4]
    b1 = client.get(f"/bookmarks/books/{book_id}?limit=4&offset=0", headers=headers)
    assert b1.status_code == 200
    assert slice_pages(b1.json()) == [1, 2, 3, 4]

    b2 = client.get(f"/bookmarks/books/{book_id}?limit=4&offset=4", headers=headers)
    assert b2.status_code == 200
    assert slice_pages(b2.json()) == [5]
