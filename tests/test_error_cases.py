import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.config import get_settings
from app.database import get_db
from app.models import Base

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base.metadata.create_all(bind=engine)

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


def register(email: str, login_id: str, password: str = "Pw123456!"):
    r = client.post(
        "/auth/register",
        json={"email": email, "login_id": login_id, "password": password, "name": "U", "nickname": "N"},
    )
    return r


def login(login_id: str, password: str):
    r = client.post("/auth/login", json={"login_id": login_id, "password": password})
    return r


def auth_headers(login_id: str, password: str):
    lg = login(login_id, password)
    assert lg.status_code == 200
    token = lg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_duplicate_registration():
    email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    login_id = f"dup_{uuid.uuid4().hex[:8]}"
    first = register(email, login_id)
    assert first.status_code in (200, 201)
    second = register(email, f"dup2_{uuid.uuid4().hex[:8]}")
    assert second.status_code == 400
    assert second.json()["detail"] == "Email already registered"


def test_unauthorized_protected_endpoint():
    # try to create note without auth
    r = client.post("/notes/", json={"book_id": 1, "page": 1, "content": "test"})
    assert r.status_code in (401, 403)


def test_duplicate_review_and_invalid_book_view():
    email = f"rev_{uuid.uuid4().hex[:8]}@example.com"
    login_id = f"rev_{uuid.uuid4().hex[:8]}"
    password = "Pw123456!"
    reg = register(email, login_id, password)
    assert reg.status_code in (200, 201)
    headers = auth_headers(login_id, password)

    # create a book
    rb = client.post(
        "/books",
        json={"title": "ErrBook", "authors": [], "total_pages": 10},
        headers=headers,
    )
    assert rb.status_code == 200
    book_id = rb.json()["id"]

    # first review
    rv1 = client.post(
        "/reviews/",
        json={"book_id": book_id, "rating": 5, "content": "great", "is_spoiler": False},
        headers=headers,
    )
    assert rv1.status_code == 200

    # duplicate review should 400
    rv2 = client.post(
        "/reviews/",
        json={"book_id": book_id, "rating": 4, "content": "second", "is_spoiler": False},
        headers=headers,
    )
    assert rv2.status_code == 400
    assert rv2.json()["detail"].startswith("이미 리뷰")

    # invalid book view
    view = client.post(
        "/analytics/views",
        json={"book_id": book_id + 999},
        headers=headers,
    )
    assert view.status_code == 404
    assert view.json()["detail"] == "Book not found"
