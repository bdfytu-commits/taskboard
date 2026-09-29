"""Auth: registration, login, logout, CSRF."""


def test_register_and_me(api):
    res = api.register("alice", "qwerty1")
    assert res.status_code == 201
    data = res.get_json()
    assert data["username"] == "alice"
    assert len(data["csrf_token"]) == 64

    me = api.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["username"] == "alice"


def test_register_rejects_bad_username(api):
    for bad in ("ab", "a b", "юзер", "x" * 33, ""):
        res = api.register(bad, "secret123")
        assert res.status_code == 400, bad


def test_register_rejects_short_password(api):
    res = api.register("bob", "12345")
    assert res.status_code == 400


def test_duplicate_username(api):
    assert api.register("carol", "secret123").status_code == 201
    api.logout()
    res = api.register("carol", "secret123")
    assert res.status_code == 409


def test_login_flow(api):
    api.register("dave", "secret123")
    api.logout()

    assert api.login("dave", "wrong-pass").status_code == 401
    assert api.login("nobody", "secret123").status_code == 401
    assert api.login("dave", "secret123").status_code == 200
    assert api.get("/api/auth/me").status_code == 200

    assert api.logout().status_code == 200
    assert api.get("/api/auth/me").status_code == 401


def test_protected_endpoint_requires_login(api):
    assert api.get("/api/boards").status_code == 401
    res = api.post("/api/boards", json={"name": "x"})
    assert res.status_code == 401


def test_csrf_required_when_authenticated(authed_api):
    res = authed_api.post("/api/boards", json={"name": "без токена"}, headers={"X-CSRF-Token": ""})
    assert res.status_code == 403


def test_index_page_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"TaskBoard" in res.data
    assert b"/static/app.js" in res.data
