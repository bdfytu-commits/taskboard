"""Вкладка «Мои задачи» — агрегация по всем доскам."""
from datetime import date, timedelta

from conftest import column_ids


def make_board(api, name="Доска"):
    res = api.post("/api/boards", json={"name": name, "color": "#22c55e"})
    assert res.status_code == 201
    return res.get_json()["board"]


def add_task(api, board, column_id=None, **payload):
    payload.setdefault("title", "Задача")
    payload.setdefault("column_id", column_id or board["columns"][0]["id"])
    res = api.post(f"/api/boards/{board['id']}/tasks", json=payload)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["task"]


def iso(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def test_my_tasks_aggregates_boards(authed_api):
    b1 = make_board(authed_api, "А")
    b2 = make_board(authed_api, "Б")
    add_task(authed_api, b1, title="первая", due_date=iso(-1))
    add_task(authed_api, b2, title="вторая", due_date=iso(0))
    add_task(authed_api, b2, title="третья", due_date=None)

    res = authed_api.get("/api/my-tasks")
    assert res.status_code == 200
    data = res.get_json()
    titles = [t["title"] for t in data["results"]]
    assert titles == ["первая", "вторая", "третья"]  # просроченное впереди
    assert data["summary"] == {
        "overdue": 1, "today": 1, "week": 0, "later": 0, "none": 1,
        "done": 0, "total": 3,
    }
    assert data["results"][0]["board_name"] == "А"
    assert data["results"][1]["bucket"] == "today"


def test_my_tasks_search_and_priority(authed_api):
    b = make_board(authed_api)
    add_task(authed_api, b, title="Написать отчёт", priority="urgent", due_date=iso(1))
    add_task(authed_api, b, title="Помыть посуду", priority="low")
    add_task(authed_api, b, title="Отчёт по бюджету", priority="medium", due_date=iso(2))

    data = authed_api.get("/api/my-tasks", params={"q": "отчёт"}).get_json()
    assert data["count"] == 2

    data = authed_api.get("/api/my-tasks", params={"priority": "urgent"}).get_json()
    assert data["count"] == 1
    assert data["results"][0]["title"] == "Написать отчёт"

    assert authed_api.get("/api/my-tasks", params={"priority": "zzz"}).status_code == 400
    assert authed_api.get("/api/my-tasks", params={"period": "zzz"}).status_code == 400


def test_my_tasks_period_filters(authed_api):
    b = make_board(authed_api)
    add_task(authed_api, b, title="просрочена", due_date=iso(-3))
    add_task(authed_api, b, title="сегодня", due_date=iso(0))
    add_task(authed_api, b, title="на неделе", due_date=iso(5))
    add_task(authed_api, b, title="потом", due_date=iso(30))
    add_task(authed_api, b, title="без срока", due_date=None)

    def titles(period):
        return [t["title"] for t in authed_api.get(
            "/api/my-tasks", params={"period": period}).get_json()["results"]]

    assert titles("overdue") == ["просрочена"]
    assert titles("today") == ["сегодня"]
    assert titles("week") == ["на неделе"]
    assert titles("later") == ["потом"]
    assert titles("none") == ["без срока"]
    assert len(titles("all")) == 5
    assert len(titles("")) == 5


def test_my_tasks_excludes_done_when_filtering(authed_api):
    b = make_board(authed_api)
    last_col = column_ids(b)[-1]
    add_task(authed_api, b, title="в работе", due_date=iso(-1))
    add_task(authed_api, b, title="готово", column_id=last_col, due_date=iso(-1))

    data = authed_api.get("/api/my-tasks", params={"period": "overdue"}).get_json()
    assert [t["title"] for t in data["results"]] == ["в работе"]
    assert data["summary"]["overdue"] == 1
    assert data["summary"]["done"] == 1
    assert data["summary"]["total"] == 2

    # «все» показывает только активные
    data = authed_api.get("/api/my-tasks", params={"period": "all"}).get_json()
    assert [t["title"] for t in data["results"]] == ["в работе"]


def test_my_tasks_requires_auth(client, authed_api):
    authed_api.logout()
    assert client.get("/api/my-tasks").status_code == 401


def test_my_tasks_includes_subtasks_and_comments(authed_api):
    b = make_board(authed_api)
    task = add_task(authed_api, b, title="богатая задача",
                    subtasks=[{"text": "шаг", "done": True}])
    authed_api.post(f"/api/tasks/{task['id']}/comments", json={"body": "обсудили"})

    data = authed_api.get("/api/my-tasks").get_json()
    item = data["results"][0]
    assert item["subtasks"][0]["done"] is True
    assert item["comments"] == 1
    assert item["board_color"].startswith("#")
