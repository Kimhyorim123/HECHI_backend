import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.models import Base, Book

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


def seed_books(db):
    # Insert minimal seed books across categories to ensure results
    categories = [
        "Fiction / Contemporary",
        "Self-Help / Motivation",
        "Business / Investment",
        "Mystery / Thriller",
        "Essay / Short Stories",
        "Science Fiction",
    ]
    for i in range(40):
        c = categories[i % len(categories)]
        b = Book(title=f"Seed {i}", total_pages=100 + i, category=c)
        db.add(b)
    db.commit()


def test_curations_20_each():
    # Prepare DB
    with TestingSessionLocal() as db:
        seed_books(db)

    res = client.get("/recommend/curations?limit=20")
    assert res.status_code == 200
    js = res.json()
    assert "curations" in js
    curations = js["curations"]
    # Expect 6 themes
    assert len(curations) == 6
    # Each curation should have up to 20 items and include title
    for cur in curations:
        assert "title" in cur and isinstance(cur["title"], str)
        assert "items" in cur and isinstance(cur["items"], list)
        assert len(cur["items"]) <= 20
        # Items should have basic book fields
        if cur["items"]:
            itm = cur["items"][0]
            assert "title" in itm
            assert "total_pages" in itm
