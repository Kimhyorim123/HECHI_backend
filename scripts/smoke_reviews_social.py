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


def main():
    # register & login
    reg = {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "pw123456",
        "name": "User1",
        "nickname": "u1",
    }
    r = client.post("/auth/register", json=reg)
    print("register:", r.status_code, r.text)
    assert r.status_code in (200, 201)
    r = client.post("/auth/login", json={"email": reg["email"], "password": reg["password"]})
    print("login:", r.status_code, r.text)
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # create book
    rb = client.post(
        "/books",
        json={"title": "소셜 테스트", "authors": ["홍길동"], "total_pages": 123},
        headers=headers,
    )
    assert rb.status_code == 200
    book_id = rb.json()["id"]

    # upsert review (rating-only)
    rr = client.post(
        "/reviews/upsert",
        json={"book_id": book_id, "rating": 4.5},
        headers=headers,
    )
    assert rr.status_code == 200
    review = rr.json()
    review_id = review["id"]
    assert review.get("is_my_review") is True

    # list reviews includes is_liked=False initially
    lst = client.get(f"/reviews/books/{book_id}", headers=headers)
    assert lst.status_code == 200
    items = lst.json()
    assert items and items[0]["id"] == review_id
    assert items[0]["is_my_review"] is True
    assert items[0]["is_liked"] is False

    # toggle like -> liked True
    tl = client.post(f"/reviews/{review_id}/like", headers=headers)
    assert tl.status_code == 200
    assert tl.json()["liked"] is True

    # detail shows is_liked True
    dt = client.get(f"/reviews/{review_id}", headers=headers)
    assert dt.status_code == 200
    assert dt.json()["is_liked"] is True

    # comments create & list & delete
    pc = client.post(
        f"/reviews/{review_id}/comments",
        json={"content": "좋은 리뷰네요"},
        headers=headers,
    )
    assert pc.status_code == 200
    comment_id = pc.json()["id"]

    lc = client.get(f"/reviews/{review_id}/comments", headers=headers)
    assert lc.status_code == 200
    assert any(c["id"] == comment_id for c in lc.json())

    dc = client.delete(f"/reviews/comments/{comment_id}", headers=headers)
    print("delete comment:", dc.status_code, dc.text)
    assert dc.status_code == 204

    print("Smoke OK: like toggle, is_liked, comments CRUD all good.")


if __name__ == "__main__":
    main()
