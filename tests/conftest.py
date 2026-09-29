import pathlib
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from app import create_app
from app.auth import limiter


@pytest.fixture
def app(tmp_path):
    limiter.clear()  # rate-limit состояние не должно протекать между тестами
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "DATABASE": str(tmp_path / "test.sqlite"),
            "SESSION_COOKIE_SAMESITE": "Lax",
        }
    )
    yield application
    limiter.clear()


@pytest.fixture
def client(app):
    return app.test_client()


class Api:
    """Thin wrapper around the test client that handles CSRF automatically."""

    def __init__(self, client):
        self.client = client
        self.csrf = None

    def _ensure_anonymous(self):
        """Drop any existing session so register/login start from scratch."""
        res = self.client.get("/api/auth/me")
        if res.status_code == 200:
            token = res.get_json()["csrf_token"]
            self.client.post(
                "/api/auth/logout", json={}, headers={"X-CSRF-Token": token}
            )
        self.csrf = None

    def request(self, method, path, json=None, params=None, **kwargs):
        if params:
            path = f"{path}?{urlencode(params)}"
        headers = dict(kwargs.pop("headers", {}))
        if self.csrf and "X-CSRF-Token" not in headers:
            headers["X-CSRF-Token"] = self.csrf
        return self.client.open(path, method=method, json=json, headers=headers, **kwargs)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, json=None, **kw):
        return self.request("POST", path, json=json, **kw)

    def patch(self, path, json=None, **kw):
        return self.request("PATCH", path, json=json, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def register(self, username="ivan", password="secret123"):
        self._ensure_anonymous()
        res = self.post(
            "/api/auth/register", json={"username": username, "password": password}
        )
        if res.status_code in (200, 201):
            self.csrf = res.get_json()["csrf_token"]
        return res

    def login(self, username="ivan", password="secret123"):
        self._ensure_anonymous()
        res = self.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        if res.status_code == 200:
            self.csrf = res.get_json()["csrf_token"]
        return res

    def logout(self):
        res = self.post("/api/auth/logout", json={})
        self.csrf = None
        return res


@pytest.fixture
def api(client):
    return Api(client)


@pytest.fixture
def authed_api(api):
    assert api.register().status_code == 201
    return api


@pytest.fixture
def board(authed_api):
    res = authed_api.post("/api/boards", json={"name": "Проект X", "color": "#ff0000"})
    assert res.status_code == 201
    return res.get_json()["board"]


def column_ids(board):
    return [c["id"] for c in board["columns"]]
