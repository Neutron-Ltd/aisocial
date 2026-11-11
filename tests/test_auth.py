from fastapi.testclient import TestClient

from tests.conftest import BASE, signup


def test_signup_login_logout(client):
    user = signup(client)
    assert user["email"] == "ana@example.com" and user["timezone"] == "Asia/Tokyo"
    assert client.get("/api/auth/me").json()["name"] == "Ana"
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "ANA@example.com", "password": "wrong password!"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "ANA@example.com", "password": "correct horse battery"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_session_cookie_flags(client):
    r = client.post("/api/auth/signup", json={"email": "b@example.com", "password": "long enough pw"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie


def test_duplicate_and_weak(client):
    signup(client)
    assert client.post("/api/auth/signup", json={"email": "ana@example.com", "password": "another long pw"}).status_code == 409
    assert client.post("/api/auth/signup", json={"email": "c@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/auth/signup", json={"email": "not-an-email", "password": "long enough pw"}).status_code == 422


def test_csrf_header_required(client, user):
    bare = TestClient(client.app, base_url=BASE, cookies=client.cookies)
    r = bare.patch("/api/auth/me", json={"name": "Mallory"})
    assert r.status_code == 403
    assert client.get("/api/auth/me").json()["name"] == "Ana"


def test_profile_and_defaults(client, user):
    r = client.patch("/api/auth/me", json={"name": "Ana B", "timezone": "Europe/Berlin", "default_hashtags": "#ai",
                                            "default_platforms": ["x", "tiktok"], "default_time": "09:30"})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["timezone"] == "Europe/Berlin" and me["default_platforms"] == ["tiktok", "x"]
    assert client.patch("/api/auth/me", json={"timezone": "Mars/Base"}).status_code == 422
    assert client.patch("/api/auth/me", json={"default_platforms": ["myspace"]}).status_code == 422


def test_password_change_signs_out_other_sessions(client, user):
    other = TestClient(client.app, base_url=BASE)
    other.headers["X-NEUTX"] = "1"
    assert other.post("/api/auth/login", json={"email": "ana@example.com", "password": "correct horse battery"}).status_code == 200
    assert len(client.get("/api/auth/sessions").json()) == 2
    assert client.post("/api/auth/password", json={"current_password": "nope nope nope",
                                                   "new_password": "brand new password"}).status_code == 403
    assert client.post("/api/auth/password", json={"current_password": "correct horse battery",
                                                   "new_password": "brand new password"}).status_code == 204
    assert other.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 200


def test_export_and_delete_account(client, user):
    r = client.get("/api/auth/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert r.json()["user"]["email"] == "ana@example.com"
    assert client.post("/api/auth/delete-account", json={"password": "wrong wrong"}).status_code == 403
    assert client.post("/api/auth/delete-account", json={"password": "correct horse battery"}).status_code == 204
    assert client.post("/api/auth/login", json={"email": "ana@example.com",
                                                "password": "correct horse battery"}).status_code == 401


def test_security_headers_and_static(client):
    r = client.get("/index.html")
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert client.get("/../README.md").status_code == 404
    assert client.get("/%2e%2e/README.md").status_code == 404
    assert client.get("/api/auth/me").status_code == 401
