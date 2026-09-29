"""Boards and columns CRUD + ownership checks."""
from conftest import column_ids


def test_create_board_has_default_columns(authed_api):
    res = authed_api.post("/api/boards", json={"name": "Моя доска"})
    assert res.status_code == 201
    board = res.get_json()["board"]
    assert board["name"] == "Моя доска"
    names = [c["name"] for c in board["columns"]]
    assert names == ["Бэклог", "В работе", "Готово"]
    assert [c["position"] for c in board["columns"]] == [0, 1, 2]


def test_create_board_validation(authed_api):
    assert authed_api.post("/api/boards", json={"name": "   "}).status_code == 400
    assert authed_api.post("/api/boards", json={"name": "x" * 101}).status_code == 400
    assert authed_api.post("/api/boards", json={}).status_code == 400


def test_list_and_get_board(authed_api, board):
    res = authed_api.get("/api/boards")
    boards = res.get_json()["boards"]
    assert len(boards) == 1
    assert boards[0]["column_count"] == 3
    assert boards[0]["task_count"] == 0

    detail = authed_api.get(f"/api/boards/{board['id']}").get_json()["board"]
    assert len(detail["columns"]) == 3
    assert all(c["tasks"] == [] for c in detail["columns"])


def test_task_count_is_not_inflated_by_join(authed_api, board):
    """Счётчик задач не должен умножаться на число колонок (fan-out JOIN)."""
    for i in range(2):
        res = authed_api.post(
            f"/api/boards/{board['id']}/tasks", json={"title": f"задача {i}"}
        )
        assert res.status_code == 201
    boards = authed_api.get("/api/boards").get_json()["boards"]
    assert boards[0]["column_count"] == 3
    assert boards[0]["task_count"] == 2  # а не 6


def test_rename_board(authed_api, board):
    res = authed_api.patch(f"/api/boards/{board['id']}", json={"name": "Новое имя"})
    assert res.status_code == 200
    assert res.get_json()["board"]["name"] == "Новое имя"

    assert authed_api.patch(f"/api/boards/{board['id']}", json={"name": ""}).status_code == 400
    assert authed_api.patch(f"/api/boards/{board['id']}", json={"color": "red"}).status_code == 400
    assert authed_api.patch(f"/api/boards/{board['id']}", json={}).status_code == 400

    ok = authed_api.patch(f"/api/boards/{board['id']}", json={"color": "#00ff00"})
    assert ok.get_json()["board"]["color"] == "#00ff00"


def test_delete_board(authed_api, board):
    assert authed_api.delete(f"/api/boards/{board['id']}").status_code == 200
    assert authed_api.get(f"/api/boards/{board['id']}").status_code == 404
    assert authed_api.get("/api/boards").get_json()["boards"] == []


def test_board_ownership(authed_api, board):
    other = authed_api.__class__(authed_api.client)
    # второй пользователь на том же клиенте (сессия заменяется)
    assert other.login("intruder", "secret123").status_code in (200, 401)
    other.logout()
    assert other.register("intruder", "secret123").status_code == 201

    assert other.get(f"/api/boards/{board['id']}").status_code == 404
    assert other.patch(f"/api/boards/{board['id']}", json={"name": "хак"}).status_code == 404
    assert other.delete(f"/api/boards/{board['id']}").status_code == 404
    assert other.get("/api/boards").get_json()["boards"] == []


def test_column_crud(authed_api, board):
    bid = board["id"]

    res = authed_api.post(f"/api/boards/{bid}/columns", json={"name": "Ревью"})
    assert res.status_code == 201
    col_id = res.get_json()["column"]["id"]

    assert authed_api.post(f"/api/boards/{bid}/columns", json={"name": ""}).status_code == 400

    renamed = authed_api.patch(f"/api/columns/{col_id}", json={"name": "QA"})
    assert renamed.get_json()["column"]["name"] == "QA"

    # перемещение последней колонки на первую позицию
    moved = authed_api.patch(f"/api/columns/{col_id}", json={"position": 0})
    assert moved.get_json()["column"]["position"] == 0
    detail = authed_api.get(f"/api/boards/{bid}").get_json()["board"]
    assert detail["columns"][0]["id"] == col_id

    assert authed_api.delete(f"/api/columns/{col_id}").status_code == 200
    detail = authed_api.get(f"/api/boards/{bid}").get_json()["board"]
    assert len(detail["columns"]) == 3


def test_cannot_delete_last_column(authed_api):
    board = authed_api.post("/api/boards", json={"name": "Одна колонка"}).get_json()["board"]
    ids = column_ids(board)
    # удаляем, пока не останется одна
    for cid in ids[:-1]:
        assert authed_api.delete(f"/api/columns/{cid}").status_code == 200
    assert authed_api.delete(f"/api/columns/{ids[-1]}").status_code == 400
