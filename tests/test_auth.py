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


def test_login_rate_limited(api):
    """После 10 неудачных попыток вход блокируется на окно (429)."""
    api.register("frank", "secret123")
    api.logout()

    statuses = []
    for _ in range(11):
        statuses.append(api.login("frank", "wrong-pass").status_code)
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429

    # даже с верным паролем вход пока закрыт
    assert api.login("frank", "secret123").status_code == 429


def test_successful_login_resets_counter(api):
    api.register("grace", "secret123")
    api.logout()
    for _ in range(9):
        assert api.login("grace", "nope").status_code == 401
    assert api.login("grace", "secret123").status_code == 200
    api.logout()
    # счётчик обнулён — снова доступны неудачные попытки
    assert api.login("grace", "nope").status_code == 401


def test_register_spam_limited(api):
    for _ in range(10):
        assert api.register("bad name!", "secret123").status_code == 400
    assert api.register("bad name!", "secret123").status_code == 429
