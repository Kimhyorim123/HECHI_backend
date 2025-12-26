import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.models import Base, User
from app.core.auth import get_current_user

# Shared in-memory DB for this script run
ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)
Base.metadata.create_all(bind=ENGINE)


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def main():
    # register to create user in the same in-memory DB, then override auth
    reg = {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "pw123456",
        "name": "User1",
        "nickname": "u1",
    }
    r = client.post("/auth/register", json=reg)
    assert r.status_code in (200, 201)
    user_json = r.json()

    def _fake_current_user():
        return User(
            id=user_json["id"],
            email=user_json["email"],
            password_hash="x",
            name=user_json["name"],
            nickname=user_json["nickname"],
        )

    app.dependency_overrides[get_current_user] = _fake_current_user
    headers = {}

    # create book
    rb = client.post(
        "/books",
        json={"title": "노트/북마크 스모크", "authors": ["홍길동"], "total_pages": 200},
        headers=headers,
    )
    assert rb.status_code == 200
    book_id = rb.json()["id"]

    # bookmark without memo
    b1 = client.post("/bookmarks/", json={"book_id": book_id, "page": 10}, headers=headers)
    print("bookmark post:", b1.status_code, b1.text)
    assert b1.status_code == 200
    assert b1.json().get("memo") is None

    # bookmark add memo via PUT
    bm_id = b1.json()["id"]
    b2 = client.put(f"/bookmarks/{bm_id}", json={"memo": "페이지 메모"}, headers=headers)
    print("bookmark put:", b2.status_code, b2.text)
    assert b2.status_code == 200
    assert b2.json()["memo"] == "페이지 메모"

    # highlight without memo (no memo field, sentence required)
    h1 = client.post(
        "/highlights/",
        json={"book_id": book_id, "page": 15, "sentence": "문장", "is_public": False},
        headers=headers,
    )
    assert h1.status_code == 200

    # note with page=null (book-level note)
    n1 = client.post("/notes/", json={"book_id": book_id, "page": None, "content": "책 메모"}, headers=headers)
    assert n1.status_code == 200
    assert n1.json().get("page") is None

    # list notes
    ln = client.get(f"/notes/books/{book_id}", headers=headers)
    assert ln.status_code == 200
    assert any(item.get("page") is None for item in ln.json())

    print("Smoke OK: notes page nullable, bookmarks memo optional/update works.")


if __name__ == "__main__":
    main()
