"""Смена собственного пароля."""


def test_change_password_success(authed_api):
    res = authed_api.post(
        "/api/auth/change-password",
        json={"current_password": "secret123", "new_password": "newpass456"},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    authed_api.csrf = res.get_json().get("csrf_token") or authed_api.csrf

    authed_api.logout()
    assert authed_api.login("ivan", "newpass456").status_code == 200
    authed_api.logout()
    assert authed_api.login("ivan", "secret123").status_code == 401


def test_change_password_wrong_current(authed_api):
    res = authed_api.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-pass", "new_password": "newpass456"},
    )
    assert res.status_code == 403
    assert "неверен" in res.get_json()["error"]
    # пароль не изменился
    authed_api.logout()
    assert authed_api.login("ivan", "secret123").status_code == 200


def test_change_password_validation(authed_api):
    base = {"current_password": "secret123"}

    short = authed_api.post(
        "/api/auth/change-password", json={**base, "new_password": "12345"}
    )
    assert short.status_code == 400
    assert "6" in short.get_json()["error"]

    same = authed_api.post(
        "/api/auth/change-password", json={**base, "new_password": "secret123"}
    )
    assert same.status_code == 400
    assert "отличаться" in same.get_json()["error"]

    empty = authed_api.post("/api/auth/change-password", json={})
    assert empty.status_code == 400

    too_long = authed_api.post(
        "/api/auth/change-password", json={**base, "new_password": "x" * 129}
    )
    assert too_long.status_code == 400


def test_change_password_requires_login(client, api):
    res = client.post(
        "/api/auth/change-password",
        json={"current_password": "a", "new_password": "bbbbbb"},
    )
    assert res.status_code == 401


def test_change_password_requires_csrf(client, api):
    api.register("ivan", "secret123")
    res = client.post(
        "/api/auth/change-password",
        json={"current_password": "secret123", "new_password": "newpass456"},
    )
    assert res.status_code == 403
    assert "CSRF" in res.get_json()["error"]


def test_change_password_rate_limited(authed_api, app):
    """10 неверных текущих паролей за минуту → 429."""
    for _ in range(10):
        authed_api.post(
            "/api/auth/change-password",
            json={"current_password": "nope", "new_password": "newpass456"},
        )
    res = authed_api.post(
        "/api/auth/change-password",
        json={"current_password": "nope", "new_password": "newpass456"},
    )
    assert res.status_code == 429
