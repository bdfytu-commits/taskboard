"""Экспорт доски в JSON и Markdown."""


def make_tasks(api, board):
    data = [
        {"title": "Сделать фичу", "priority": "urgent", "due_date": "2026-10-05",
         "tags": ["feature"], "description": "первая строка\nвторая строка"},
        {"title": "Починить баг", "priority": "low", "tags": []},
    ]
    ids = []
    for payload in data:
        res = api.post(f"/api/boards/{board['id']}/tasks", json=payload)
        assert res.status_code == 201
        ids.append(res.get_json()["task"]["id"])
    return ids


def test_export_json(authed_api, board):
    make_tasks(authed_api, board)
    res = authed_api.get(f"/api/boards/{board['id']}/export", params={"format": "json"})

    assert res.status_code == 200
    assert "attachment" in res.headers["Content-Disposition"]
    data = res.get_json()
    assert data["name"] == board["name"]
    assert data["exported_at"]
    assert len(data["columns"]) == 3
    titles = [t["title"] for c in data["columns"] for t in c["tasks"]]
    assert titles == ["Сделать фичу", "Починить баг"]
    # теги и описание сохраняются
    first = data["columns"][0]["tasks"][0]
    assert first["tags"] == ["feature"]
    assert first["description"] == "первая строка\nвторая строка"


def test_export_json_is_default(authed_api, board):
    plain = authed_api.get(f"/api/boards/{board['id']}/export")
    assert plain.status_code == 200
    assert plain.get_json()["columns"]


def test_export_markdown(authed_api, board):
    make_tasks(authed_api, board)
    res = authed_api.get(f"/api/boards/{board['id']}/export", params={"format": "md"})

    assert res.status_code == 200
    assert res.headers["Content-Type"].startswith("text/markdown")
    assert "attachment" in res.headers["Content-Disposition"]
    text = res.get_data(as_text=True)

    assert text.startswith("# Проект X")
    assert "## Бэклог" in text
    assert "## Готово" in text
    assert "- [ ] **Сделать фичу** · срочный 📅 2026-10-05 `#feature`" in text
    assert "> первая строка" in text
    assert "_пусто_" in text  # колонка без задач


def test_export_format_validation(authed_api, board):
    res = authed_api.get(f"/api/boards/{board['id']}/export", params={"format": "pdf"})
    assert res.status_code == 400


def test_export_ownership(authed_api, board):
    other = authed_api.__class__(authed_api.client)
    assert other.register("hacker", "secret123").status_code == 201
    for fmt in ("json", "md"):
        res = other.get(f"/api/boards/{board['id']}/export", params={"format": fmt})
        assert res.status_code == 404
