from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings


def test_auto_login_cookie_refresh_flow():
    settings = get_settings()
    settings.environment = "local"

    client = TestClient(app)

    email = "auto_login_e2e@example.com"
    password = "Test1234!"

    # register
    client.post("/auth/register", json={
        "email": email,
        "name": "Auto",
        "nickname": "Auto",
        "password": password,
    })

    # login with remember_me
    res = client.post("/auth/login", json={
        "email": email,
        "password": password,
        "remember_me": True,
    })
    assert res.status_code == 200
    # cookie set and stored
    set_cookie = res.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    # should not be Secure in local to allow TestClient to send it
    assert "Secure" not in set_cookie
    assert "refresh_token" in client.cookies

    # refresh without body should read cookie
    res2 = client.post("/auth/refresh")
    assert res2.status_code == 200
    js = res2.json()
    assert "access_token" in js and isinstance(js["access_token"], str)

    # logout and ensure refresh fails
    res3 = client.post("/auth/logout")
    assert res3.status_code == 204
    res4 = client.post("/auth/refresh")
    assert res4.status_code in (400, 401)
