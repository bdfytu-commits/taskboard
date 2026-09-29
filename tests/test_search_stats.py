"""Search, tags listing and board statistics."""
from datetime import date, timedelta

from conftest import column_ids


def post_task(api, board_id, **payload):
    payload.setdefault("title", "Задача")
    res = api.post(f"/api/boards/{board_id}/tasks", json=payload)
    assert res.status_code == 201
    return res.get_json()["task"]


def test_search_by_title_description_and_tag(authed_api, board):
    bid = board["id"]
    post_task(authed_api, bid, title="Починить авторизацию", description="падает логин")
    post_task(authed_api, bid, title="Обновить зависимости", tags=["infra"])
    post_task(authed_api, bid, title="Написать тесты", description="покрытие 80%")

    res = authed_api.get("/api/search", params={"q": "авторизац"})
    assert res.get_json()["count"] == 1

    res = authed_api.get("/api/search", params={"q": "падает"})
    assert res.get_json()["count"] == 1

    res = authed_api.get("/api/search", params={"q": "INFRA"})
    data = res.get_json()
    assert data["count"] == 1
    assert data["results"][0]["title"] == "Обновить зависимости"
    assert data["results"][0]["board_name"] == board["name"]
    assert data["results"][0]["column_name"] == "Бэклог"

    res = authed_api.get("/api/search", params={"q": "точно нет такого"})
    assert res.get_json()["count"] == 0


def test_search_filters(authed_api, board):
    bid = board["id"]
    post_task(authed_api, bid, title="Срочное", priority="urgent")
    post_task(authed_api, bid, title="Спокойное", priority="low")

    res = authed_api.get("/api/search", params={"priority": "urgent"})
    data = res.get_json()
    assert data["count"] == 1
    assert data["results"][0]["title"] == "Срочное"

    assert authed_api.get("/api/search", params={"priority": "alien"}).status_code == 400


def test_tags_endpoint(authed_api, board):
    bid = board["id"]
    post_task(authed_api, bid, title="a", tags=["bug", "ui"])
    post_task(authed_api, bid, title="b", tags=["bug"])

    res = authed_api.get("/api/tags")
    tags = {t["name"]: t["usage"] for t in res.get_json()["tags"]}
    assert tags == {"bug": 2, "ui": 1}


def test_stats(authed_api, board):
    bid = board["id"]
    cols = column_ids(board)
    today = date.today()

    post_task(authed_api, bid, title="готово", column_id=cols[2])
    post_task(authed_api, bid, title="просрочено", column_id=cols[1],
              due_date=(today - timedelta(days=2)).isoformat())
    post_task(authed_api, bid, title="скоро", column_id=cols[1],
              due_date=(today + timedelta(days=1)).isoformat())
    post_task(authed_api, bid, title="без срока", column_id=cols[0], priority="urgent")

    s = authed_api.get(f"/api/boards/{bid}/stats").get_json()
    assert s["total"] == 4
    assert s["overdue"] == 1
    assert s["due_soon"] == 1
    assert s["without_due"] == 2  # «готово» и «без срока»
    assert s["done"] == 1
    assert s["done_percent"] == 25.0
    assert s["by_priority"]["urgent"] == 1
    assert s["by_priority"]["medium"] == 3
    assert [c["count"] for c in s["by_column"]] == [1, 2, 1]


def test_stats_empty_board(authed_api, board):
    s = authed_api.get(f"/api/boards/{board['id']}/stats").get_json()
    assert s["total"] == 0
    assert s["done_percent"] == 0.0
    assert s["overdue"] == 0


def test_done_tasks_are_not_overdue(authed_api, board):
    """Просроченный срок у уже выполненной задачи не считается просрочкой."""
    cols = column_ids(board)
    past = (date.today() - timedelta(days=10)).isoformat()
    post_task(authed_api, board["id"], title="сделано вовремя",
              column_id=cols[2], due_date=past)
    s = authed_api.get(f"/api/boards/{board['id']}/stats").get_json()
    assert s["total"] == 1
    assert s["overdue"] == 0
    assert s["due_soon"] == 0
    assert s["done"] == 1


def test_stats_requires_own_board(authed_api, board):
    other = authed_api.__class__(authed_api.client)
    assert other.register("eve", "secret123").status_code == 201
    assert other.get(f"/api/boards/{board['id']}/stats").status_code == 404
