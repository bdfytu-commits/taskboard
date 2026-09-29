"""Подзадачи (чеклисты) внутри задачи."""
import pytest

from conftest import column_ids


def make_task(api, board_id, **payload):
    payload.setdefault("title", "Задача с чеклистом")
    res = api.post(f"/api/boards/{board_id}/tasks", json=payload)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["task"]


def subtask_texts(task):
    return [s["text"] for s in task["subtasks"]]


def test_create_task_with_subtasks(authed_api, board):
    task = make_task(
        authed_api,
        board["id"],
        subtasks=["нарисовать макет", "сверстать", "проверить"],
    )
    assert subtask_texts(task) == ["нарисовать макет", "сверстать", "проверить"]
    assert [s["position"] for s in task["subtasks"]] == [0, 1, 2]
    assert all(s["done"] is False for s in task["subtasks"])

    detail = authed_api.get(f"/api/boards/{board['id']}").get_json()["board"]
    loaded = detail["columns"][0]["tasks"][0]
    assert subtask_texts(loaded) == ["нарисовать макет", "сверстать", "проверить"]


def test_create_task_with_subtask_objects(authed_api, board):
    task = make_task(
        authed_api,
        board["id"],
        subtasks=[{"text": "готово", "done": True}, {"text": "в работе"}],
    )
    assert [(s["text"], s["done"]) for s in task["subtasks"]] == [
        ("готово", True),
        ("в работе", False),
    ]


def test_add_single_subtask(authed_api, board):
    task = make_task(authed_api, board["id"])
    res = authed_api.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "первый шаг"})
    assert res.status_code == 201
    sub = res.get_json()["subtask"]
    assert sub["text"] == "первый шаг"
    assert sub["position"] == 0
    assert sub["done"] is False

    authed_api.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "второй шаг"})
    task = authed_api.get(f"/api/boards/{board['id']}").get_json()["board"]["columns"][0]["tasks"][0]
    assert subtask_texts(task) == ["первый шаг", "второй шаг"]


def test_subtask_validation(authed_api, board):
    task = make_task(authed_api, board["id"])
    tid = task["id"]

    assert authed_api.post(f"/api/tasks/{tid}/subtasks", json={"text": ""}).status_code == 400
    assert authed_api.post(
        f"/api/tasks/{tid}/subtasks", json={"text": "x" * 201}
    ).status_code == 400
    assert authed_api.post(f"/api/tasks/{tid}/subtasks", json={}).status_code == 400

    assert authed_api.patch(
        f"/api/tasks/{tid}", json={"subtasks": "не массив"}
    ).status_code == 400
    assert authed_api.patch(
        f"/api/tasks/{tid}", json={"subtasks": [""]}
    ).status_code == 400
    assert authed_api.patch(
        f"/api/tasks/{tid}", json={"subtasks": [42]}
    ).status_code == 400
    too_many = [{"text": f"пункт {i}"} for i in range(51)]
    assert authed_api.patch(
        f"/api/tasks/{tid}", json={"subtasks": too_many}
    ).status_code == 400


def test_subtask_limit(authed_api, board):
    task = make_task(authed_api, board["id"])
    tid = task["id"]
    for i in range(50):
        res = authed_api.post(f"/api/tasks/{tid}/subtasks", json={"text": f"пункт {i}"})
        assert res.status_code == 201
    res = authed_api.post(f"/api/tasks/{tid}/subtasks", json={"text": "51-й"})
    assert res.status_code == 400


def test_toggle_and_edit_subtask(authed_api, board):
    task = make_task(
        authed_api, board["id"], subtasks=["а", "б"]
    )
    first = task["subtasks"][0]

    done = authed_api.patch(f"/api/subtasks/{first['id']}", json={"done": True})
    assert done.get_json()["subtask"]["done"] is True

    renamed = authed_api.patch(
        f"/api/subtasks/{first['id']}", json={"text": "а переписано"}
    )
    assert renamed.get_json()["subtask"]["text"] == "а переписано"

    assert authed_api.patch(
        f"/api/subtasks/{first['id']}", json={"text": "  "}
    ).status_code == 400
    assert authed_api.patch(
        f"/api/subtasks/{first['id']}", json={}).status_code == 400
    assert authed_api.patch(
        f"/api/subtasks/{first['id']}", json={"position": "раз"}
    ).status_code == 400


def test_reorder_subtasks(authed_api, board):
    task = make_task(authed_api, board["id"], subtasks=["1", "2", "3"])
    ids = [s["id"] for s in task["subtasks"]]

    res = authed_api.patch(f"/api/subtasks/{ids[2]}", json={"position": 0})
    assert res.get_json()["subtask"]["position"] == 0

    task = authed_api.get(f"/api/boards/{board['id']}").get_json()["board"]["columns"][0]["tasks"][0]
    assert subtask_texts(task) == ["3", "1", "2"]


def test_replace_subtasks_via_task_patch(authed_api, board):
    task = make_task(authed_api, board["id"], subtasks=["старая 1", "старая 2"])
    keep = task["subtasks"][0]["id"]

    res = authed_api.patch(
        f"/api/tasks/{task['id']}",
        json={"subtasks": [{"id": keep, "text": "старая 1", "done": True}, {"text": "новая"}]},
    )
    assert res.status_code == 200
    subs = res.get_json()["task"]["subtasks"]
    assert [(s["text"], s["done"]) for s in subs] == [("старая 1", True), ("новая", False)]

    # полная очистка
    res = authed_api.patch(f"/api/tasks/{task['id']}", json={"subtasks": []})
    assert res.get_json()["task"]["subtasks"] == []
    assert authed_api.get(f"/api/boards/{board['id']}").get_json()["board"]["columns"][0]["tasks"][0]["subtasks"] == []


def test_delete_subtask_and_renumber(authed_api, board):
    task = make_task(authed_api, board["id"], subtasks=["а", "б", "в"])
    middle = task["subtasks"][1]

    assert authed_api.delete(f"/api/subtasks/{middle['id']}").status_code == 200
    task = authed_api.get(f"/api/boards/{board['id']}").get_json()["board"]["columns"][0]["tasks"][0]
    assert subtask_texts(task) == ["а", "в"]
    assert [s["position"] for s in task["subtasks"]] == [0, 1]
    assert authed_api.delete(f"/api/subtasks/{middle['id']}").status_code == 404


def test_deleting_task_removes_subtasks(authed_api, board):
    task = make_task(authed_api, board["id"], subtasks=["а", "б"])
    assert authed_api.delete(f"/api/tasks/{task['id']}").status_code == 200
    # повторная операция над подзадачами невозможна
    sub_id = task["subtasks"][0]["id"]
    assert authed_api.delete(f"/api/subtasks/{sub_id}").status_code == 404


def test_subtask_ownership(authed_api, board):
    task = make_task(authed_api, board["id"], subtasks=["секрет"])
    sub_id = task["subtasks"][0]["id"]

    other = authed_api.__class__(authed_api.client)
    assert other.register("spammer", "secret123").status_code == 201

    assert other.get(f"/api/boards/{board['id']}").status_code == 404
    assert other.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "x"}).status_code == 404
    assert other.patch(f"/api/subtasks/{sub_id}", json={"done": True}).status_code == 404
    assert other.delete(f"/api/subtasks/{sub_id}").status_code == 404
    assert other.patch(f"/api/tasks/{task['id']}", json={"subtasks": []}).status_code == 404


def test_stats_include_subtasks(authed_api, board):
    make_task(authed_api, board["id"], subtasks=["1", "2", "3"])
    make_task(authed_api, board["id"], subtasks=[{"text": "готово", "done": True}])

    s = authed_api.get(f"/api/boards/{board['id']}/stats").get_json()
    assert s["subtasks_total"] == 4
    assert s["subtasks_done"] == 1


def test_search_returns_subtasks(authed_api, board):
    make_task(authed_api, board["id"], title="уникальная задача", subtasks=["шаг один"])
    res = authed_api.get("/api/search", params={"q": "уникальная"})
    data = res.get_json()
    assert data["count"] == 1
    assert subtask_texts(data["results"][0]) == ["шаг один"]
