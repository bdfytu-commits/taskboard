"""Админ-панель: роли, обзор данных всех пользователей."""
import pytest

from conftest import Api
from app.db import get_db


def promote(app, username: str) -> None:
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
        db.commit()


@pytest.fixture
def admin_api(app):
    """Отдельный клиент с аккаунтом root, уже вошедшим как администратор."""
    a = Api(app.test_client())
    assert a.register("root", "secret123").status_code == 201
    promote(app, "root")
    return a


def test_anonymous_denied(client):
    for path in ("/api/admin/summary", "/api/admin/users", "/api/admin/tasks"):
        assert client.get(path).status_code == 401


def test_regular_user_gets_403(authed_api):
    for path in ("/api/admin/summary", "/api/admin/users", "/api/admin/tasks"):
        res = authed_api.get(path)
        assert res.status_code == 403
        assert "администратор" in res.get_json()["error"]


def test_me_returns_role(authed_api, app):
    me = authed_api.get("/api/auth/me").get_json()
    assert me["role"] == "user"

    authed_api.logout()
    assert authed_api.register("boss", "secret123").status_code == 201
    promote(app, "boss")
    assert authed_api.get("/api/auth/me").get_json()["role"] == "admin"


def test_summary_counts(admin_api, authed_api, board):
    authed_api.post(f"/api/boards/{board['id']}/tasks", json={"title": "Задача"})
    res = admin_api.get("/api/admin/summary")
    assert res.status_code == 200
    summary = res.get_json()["summary"]
    assert summary["users"] >= 1
    assert summary["admins"] >= 1
    assert summary["boards"] >= 1
    assert summary["tasks"] >= 1
    assert summary["columns"] >= 1
    assert summary["done_tasks"] <= summary["tasks"]
    assert summary["subtasks_done"] <= summary["subtasks"]


def test_users_list_includes_other_accounts(admin_api, authed_api, board):
    """Админ видит всех пользователей и их счётчики."""
    authed_api.post(f"/api/boards/{board['id']}/tasks", json={"title": "Задача юзера"})
    authed_api.logout()

    admin_api.login("root", "secret123")
    res = admin_api.get("/api/admin/users")
    assert res.status_code == 200
    data = res.get_json()
    names = {u["username"] for u in data["users"]}
    assert {"ivan", "root"} <= names
    assert data["count"] == len(data["users"])

    ivan = next(u for u in data["users"] if u["username"] == "ivan")
    assert ivan["role"] == "user"
    assert ivan["boards"] >= 1
    assert ivan["tasks"] >= 1
    root = next(u for u in data["users"] if u["username"] == "root")
    assert root["role"] == "admin"


def test_user_detail_exposes_full_data(admin_api, app, api):
    """Админ видит доски, колонки, задачи, подзадачи и комментарии юзера."""
    user_api = api
    assert user_api.register("alice", "secret123").status_code == 201
    board = user_api.post("/api/boards", json={"name": "Доска Алисы"}).get_json()["board"]
    task = user_api.post(
        f"/api/boards/{board['id']}/tasks",
        json={"title": "Секретная задача", "priority": "high", "tags": ["x"]},
    ).get_json()["task"]
    user_api.post(f"/api/tasks/{task['id']}/comments", json={"body": "важно"})
    user_id = user_api.get("/api/auth/me").get_json()["id"]
    user_api.logout()

    res = admin_api.get(f"/api/admin/users/{user_id}")
    assert res.status_code == 200
    data = res.get_json()

    assert data["user"]["username"] == "alice"
    assert data["user"]["boards"] == 1
    assert data["user"]["tasks"] == 1
    assert data["user"]["comments"] == 1
    assert len(data["boards"]) == 1

    first = data["boards"][0]
    assert first["name"] == "Доска Алисы"
    assert first["tasks_count"] == 1
    tasks = [t for col in first["columns"] for t in col["tasks"]]
    assert [t["title"] for t in tasks] == ["Секретная задача"]
    assert tasks[0]["comments"] == 1
    assert tasks[0]["tags"] == ["x"]


def test_user_detail_missing(admin_api):
    assert admin_api.get("/api/admin/users/99999").status_code == 404


def test_admin_task_search_across_users(admin_api, authed_api, board):
    authed_api.post(
        f"/api/boards/{board['id']}/tasks",
        json={"title": "Общая задача команды", "priority": "urgent"},
    )
    authed_api.post(f"/api/boards/{board['id']}/tasks", json={"title": "Другая тема"})
    authed_api.logout()

    admin_api.login("root", "secret123")
    res = admin_api.get("/api/admin/tasks", params={"q": "команды"})
    data = res.get_json()
    assert data["count"] == 1
    row = data["results"][0]
    assert row["username"] == "ivan"
    assert row["board_name"] == "Проект X"
    assert row["priority"] == "urgent"

    assert admin_api.get("/api/admin/tasks").get_json()["count"] == 2
    assert admin_api.get(
        "/api/admin/tasks", params={"priority": "urgent"}
    ).get_json()["count"] == 1
    bad = admin_api.get("/api/admin/tasks", params={"priority": "nope"})
    assert bad.status_code == 400


def test_role_toggle(admin_api, authed_api):
    user_id = authed_api.get("/api/auth/me").get_json()["id"]

    res = admin_api.post(f"/api/admin/users/{user_id}/role", json={"role": "admin"})
    assert res.status_code == 200
    assert res.get_json()["role"] == "admin"

    authed_api.logout()
    assert authed_api.login().status_code == 200
    assert authed_api.get("/api/admin/summary").status_code == 200

    assert admin_api.post(
        f"/api/admin/users/{user_id}/role", json={"role": "nope"}
    ).status_code == 400
    assert admin_api.post("/api/admin/users/99999/role", json={"role": "user"}).status_code == 404


def test_admin_cannot_change_own_role_or_delete_self(admin_api):
    me = admin_api.get("/api/auth/me").get_json()
    assert admin_api.post(
        f"/api/admin/users/{me['id']}/role", json={"role": "user"}
    ).status_code == 400
    assert admin_api.delete(f"/api/admin/users/{me['id']}").status_code == 400


def test_delete_user_removes_their_data(admin_api, authed_api, board):
    authed_api.post(f"/api/boards/{board['id']}/tasks", json={"title": "Уходит вместе с юзером"})
    user_id = authed_api.get("/api/auth/me").get_json()["id"]
    authed_api.logout()

    admin_api.login("root", "secret123")
    res = admin_api.delete(f"/api/admin/users/{user_id}")
    assert res.status_code == 200

    with admin_api.client.application.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) AS n FROM users WHERE id = ?", (user_id,)).fetchone()["n"] == 0
        assert db.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE title = 'Уходит вместе с юзером'"
        ).fetchone()["n"] == 0

    assert authed_api.login().status_code == 401


def test_admin_task_detail(admin_api, authed_api, board):
    """Полные параметры любой задачи: владелец, доска, чеклист, обсуждение."""
    task = authed_api.post(
        f"/api/boards/{board['id']}/tasks",
        json={
            "title": "Задача для админа",
            "description": "Подробное описание задачи",
            "priority": "high",
            "due_date": "2030-01-15",
            "tags": ["backend", "api"],
        },
    ).get_json()["task"]
    tid = task["id"]
    authed_api.post(f"/api/tasks/{tid}/subtasks", json={"text": "первый шаг"})
    authed_api.post(f"/api/tasks/{tid}/comments", json={"body": "заметка для команды"})
    authed_api.logout()

    res = admin_api.get(f"/api/admin/tasks/{tid}")
    assert res.status_code == 200
    t = res.get_json()["task"]
    assert t["title"] == "Задача для админа"
    assert t["description"] == "Подробное описание задачи"
    assert t["owner"] == "ivan"
    assert t["board_name"] == "Проект X"
    assert t["column_name"] == "Бэклог"
    assert t["priority"] == "high"
    assert t["due_date"] == "2030-01-15"
    assert sorted(t["tags"]) == ["api", "backend"]
    assert t["subtasks_total"] == 1
    assert t["subtasks_done"] == 0
    assert t["subtasks"][0]["text"] == "первый шаг"
    assert t["comments_count"] == 1
    assert t["comments"][0]["username"] == "ivan"
    assert t["finished"] is False
    assert t["created_at"] and t["updated_at"]


def test_admin_task_detail_permissions(admin_api, authed_api):
    assert authed_api.get("/api/admin/tasks/1").status_code == 403
    assert admin_api.get("/api/admin/tasks/99999").status_code == 404


def test_admin_task_detail_marks_finished(admin_api, authed_api, board):
    """Задача в последней колонке помечена как выполненная."""
    task = authed_api.post(
        f"/api/boards/{board['id']}/tasks", json={"title": "Готовая задача"}
    ).get_json()["task"]
    done_col = board["columns"][-1]
    authed_api.post(f"/api/tasks/{task['id']}/move", json={"column_id": done_col["id"], "index": 0})
    authed_api.logout()

    t = admin_api.get(f"/api/admin/tasks/{task['id']}").get_json()["task"]
    assert t["finished"] is True
    assert t["column_name"] == "Готово"
