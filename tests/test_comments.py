"""Комментарии к задачам."""


def make_task(api, board_id, **payload):
    payload.setdefault("title", "Задача с обсуждением")
    res = api.post(f"/api/boards/{board_id}/tasks", json=payload)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["task"]


def test_add_and_list_comments(authed_api, board):
    task = make_task(authed_api, board["id"])

    res = authed_api.post(
        f"/api/tasks/{task['id']}/comments", json={"body": "Привет, обсуждаем!"}
    )
    assert res.status_code == 201
    comment = res.get_json()["comment"]
    assert comment["body"] == "Привет, обсуждаем!"
    assert comment["username"] == "ivan"
    assert comment["task_id"] == task["id"]

    authed_api.post(f"/api/tasks/{task['id']}/comments", json={"body": "Второй"})

    res = authed_api.get(f"/api/tasks/{task['id']}/comments")
    data = res.get_json()
    assert data["count"] == 2
    assert [c["body"] for c in data["comments"]] == ["Привет, обсуждаем!", "Второй"]
    assert data["comments"][0]["created_at"] <= data["comments"][1]["created_at"]


def test_comment_validation(authed_api, board):
    task = make_task(authed_api, board["id"])
    tid = task["id"]

    assert authed_api.post(f"/api/tasks/{tid}/comments", json={"body": "   "}).status_code == 400
    assert authed_api.post(f"/api/tasks/{tid}/comments", json={}).status_code == 400
    assert authed_api.post(
        f"/api/tasks/{tid}/comments", json={"body": "x" * 2001}
    ).status_code == 400
    assert authed_api.post("/api/tasks/999999/comments", json={"body": "а"}).status_code == 404


def test_comment_requires_csrf(client, authed_api, board):
    task = make_task(authed_api, board["id"])
    # без CSRF-заголовка запрос должен быть отвергнут
    res = client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"body": "без токена"},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert res.status_code == 403


def test_delete_comment(authed_api, board):
    task = make_task(authed_api, board["id"])
    cid = authed_api.post(
        f"/api/tasks/{task['id']}/comments", json={"body": "удали меня"}
    ).get_json()["comment"]["id"]

    assert authed_api.delete(f"/api/comments/{cid}").status_code == 200
    assert authed_api.get(f"/api/tasks/{task['id']}/comments").get_json()["count"] == 0
    assert authed_api.delete(f"/api/comments/{cid}").status_code == 404


def test_comment_ownership(authed_api, board):
    task = make_task(authed_api, board["id"])
    cid = authed_api.post(
        f"/api/tasks/{task['id']}/comments", json={"body": "мой коммент"}
    ).get_json()["comment"]["id"]

    other = authed_api.__class__(authed_api.client)
    assert other.register("spammer", "secret123").status_code == 201
    assert other.get(f"/api/tasks/{task['id']}/comments").status_code == 404
    assert other.post(f"/api/tasks/{task['id']}/comments", json={"body": "спам"}).status_code == 404
    assert other.delete(f"/api/comments/{cid}").status_code == 404


def test_comments_cascade_with_task(authed_api, board):
    task = make_task(authed_api, board["id"])
    authed_api.post(f"/api/tasks/{task['id']}/comments", json={"body": "до удаления"})
    assert authed_api.delete(f"/api/tasks/{task['id']}").status_code == 200
    assert authed_api.get(f"/api/tasks/{task['id']}/comments").status_code == 404


def test_task_payload_includes_comment_count(authed_api, board):
    task = make_task(authed_api, board["id"])
    assert task["comments"] == 0

    authed_api.post(f"/api/tasks/{task['id']}/comments", json={"body": "раз"})
    authed_api.post(f"/api/tasks/{task['id']}/comments", json={"body": "два"})

    board_data = authed_api.get(f"/api/boards/{board['id']}").get_json()["board"]
    loaded = board_data["columns"][0]["tasks"][0]
    assert loaded["comments"] == 2
