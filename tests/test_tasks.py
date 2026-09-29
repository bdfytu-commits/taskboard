"""Tasks: creation, validation, editing, moving/reordering, tags, deletion."""
from conftest import column_ids


def make_task(api, board_id, **payload):
    payload.setdefault("title", "Задача")
    res = api.post(f"/api/boards/{board_id}/tasks", json=payload)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["task"]


def tasks_by_column(api, board_id):
    board = api.get(f"/api/boards/{board_id}").get_json()["board"]
    return {c["id"]: [t["title"] for t in c["tasks"]] for c in board["columns"]}


def test_create_task_defaults(authed_api, board):
    task = make_task(authed_api, board["id"], title="Первая задача")
    assert task["priority"] == "medium"
    assert task["column_id"] == board["columns"][0]["id"]
    assert task["position"] == 0
    assert task["tags"] == []
    assert task["due_date"] is None


def test_create_task_validation(authed_api, board):
    bid = board["id"]
    assert authed_api.post(f"/api/boards/{bid}/tasks", json={"title": ""}).status_code == 400
    assert authed_api.post(f"/api/boards/{bid}/tasks", json={"title": "x" * 201}).status_code == 400
    assert authed_api.post(
        f"/api/boards/{bid}/tasks", json={"title": "ok", "priority": "super"}
    ).status_code == 400
    assert authed_api.post(
        f"/api/boards/{bid}/tasks", json={"title": "ok", "due_date": "31.12.2026"}
    ).status_code == 400
    assert authed_api.post(
        f"/api/boards/{bid}/tasks", json={"title": "ok", "column_id": 999999}
    ).status_code == 404
    assert authed_api.post(
        f"/api/boards/{bid}/tasks", json={"title": "ok", "description": "d" * 5001}
    ).status_code == 400


def test_create_task_with_due_date_and_tags(authed_api, board):
    task = make_task(
        authed_api,
        board["id"],
        title="Сдача релиза",
        due_date="2026-10-15",
        tags=["release", "backend", "release"],
        priority="urgent",
    )
    assert task["due_date"] == "2026-10-15"
    assert task["priority"] == "urgent"
    assert task["tags"] == ["backend", "release"]  # дубликат убран, отсортировано


def test_update_task(authed_api, board):
    task = make_task(authed_api, board["id"])
    res = authed_api.patch(
        f"/api/tasks/{task['id']}",
        json={"title": "Новое имя", "priority": "high", "description": "детали", "tags": ["a"]},
    )
    assert res.status_code == 200
    updated = res.get_json()["task"]
    assert updated["title"] == "Новое имя"
    assert updated["priority"] == "high"
    assert updated["description"] == "детали"
    assert updated["tags"] == ["a"]

    assert authed_api.patch(f"/api/tasks/{task['id']}", json={}).status_code == 400
    assert authed_api.patch(f"/api/tasks/{task['id']}", json={"title": ""}).status_code == 400
    # очистка срока
    cleared = authed_api.patch(f"/api/tasks/{task['id']}", json={"due_date": None})
    assert cleared.get_json()["task"]["due_date"] is None


def test_move_between_columns(authed_api, board):
    bid = board["id"]
    cols = column_ids(board)
    a, b = cols[0], cols[1]

    t1 = make_task(authed_api, bid, title="t1")
    t2 = make_task(authed_api, bid, title="t2")
    t3 = make_task(authed_api, bid, title="t3")

    assert authed_api.post(
        f"/api/tasks/{t1['id']}/move", json={"column_id": b, "index": 0}
    ).status_code == 200
    assert authed_api.post(
        f"/api/tasks/{t3['id']}/move", json={"column_id": b, "index": 0}
    ).status_code == 200

    state = tasks_by_column(authed_api, bid)
    assert state[a] == ["t2"]
    assert state[b] == ["t3", "t1"]


def test_reorder_within_column(authed_api, board):
    bid = board["id"]
    a = board["columns"][0]["id"]
    for name in ("one", "two", "three"):
        make_task(authed_api, bid, title=name)
    assert tasks_by_column(authed_api, bid)[a] == ["one", "two", "three"]

    task_ids = [
        t["id"]
        for t in authed_api.get(f"/api/boards/{bid}").get_json()["board"]["columns"][0]["tasks"]
    ]
    # последний — в начало
    authed_api.post(f"/api/tasks/{task_ids[2]}/move", json={"column_id": a, "index": 0})
    assert tasks_by_column(authed_api, bid)[a] == ["three", "one", "two"]

    # инекс за пределами — в конец
    authed_api.post(f"/api/tasks/{task_ids[0]}/move", json={"column_id": a, "index": 99})
    assert tasks_by_column(authed_api, bid)[a] == ["three", "two", "one"]

    # отрицательный — в начало
    authed_api.post(f"/api/tasks/{task_ids[0]}/move", json={"column_id": a, "index": -5})
    assert tasks_by_column(authed_api, bid)[a] == ["one", "three", "two"]


def test_move_validates_column(authed_api, board):
    task = make_task(authed_api, board["id"])
    res = authed_api.post(f"/api/tasks/{task['id']}/move", json={"column_id": 999999})
    assert res.status_code == 404
    res = authed_api.post(f"/api/tasks/{task['id']}/move", json={"index": "три"})
    assert res.status_code == 400


def test_delete_task(authed_api, board):
    task = make_task(authed_api, board["id"])
    assert authed_api.delete(f"/api/tasks/{task['id']}").status_code == 200
    assert authed_api.delete(f"/api/tasks/{task['id']}").status_code == 404
    assert authed_api.get(f"/api/boards/{board['id']}").get_json()["board"]["columns"][0]["tasks"] == []


def test_deleting_column_removes_its_tasks(authed_api, board):
    bid = board["id"]
    done_col = board["columns"][2]
    make_task(authed_api, bid, title="Готовая", column_id=done_col["id"])
    make_task(authed_api, bid, title="В работе", column_id=board["columns"][1]["id"])

    assert authed_api.delete(f"/api/columns/{done_col['id']}").status_code == 200
    detail = authed_api.get(f"/api/boards/{bid}").get_json()["board"]
    titles = [t["title"] for c in detail["columns"] for t in c["tasks"]]
    assert titles == ["В работе"]


def test_task_ownership(authed_api, board):
    task = make_task(authed_api, board["id"])
    other = authed_api.__class__(authed_api.client)
    assert other.register("mallory", "secret123").status_code == 201

    assert other.patch(f"/api/tasks/{task['id']}", json={"title": "взлом"}).status_code == 404
    assert other.delete(f"/api/tasks/{task['id']}").status_code == 404
    assert other.post(f"/api/tasks/{task['id']}/move", json={}).status_code == 404
    assert other.post(f"/api/boards/{board['id']}/tasks", json={"title": "x"}).status_code == 404
