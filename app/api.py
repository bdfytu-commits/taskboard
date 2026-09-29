"""REST API: boards, columns, tasks, tags, search and stats."""
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from .auth import current_user_id, get_csrf_token, login_required
from .db import get_db

api = Blueprint("api", __name__, url_prefix="/api")

PRIORITIES = ("low", "medium", "high", "urgent")
DEFAULT_COLUMNS = ("Бэклог", "В работе", "Готово")
MAX_TITLE = 200
MAX_DESCRIPTION = 5000
MAX_NAME = 100
MAX_TAG = 32


# --------------------------------------------------------------------------- helpers
def bad(message: str, status: int = 400):
    return jsonify(error=message), status


def get_board_or_404(board_id: int):
    row = get_db().execute(
        "SELECT * FROM boards WHERE id = ? AND user_id = ?",
        (board_id, current_user_id()),
    ).fetchone()
    if row is None:
        return None
    return row


def serialize_task(row, tags: list[str] | None = None) -> dict:
    return {
        "id": row["id"],
        "board_id": row["board_id"],
        "column_id": row["column_id"],
        "title": row["title"],
        "description": row["description"],
        "priority": row["priority"],
        "due_date": row["due_date"],
        "position": row["position"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "tags": tags or [],
    }


def load_tasks(board_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE board_id = ? ORDER BY column_id, position",
        (board_id,),
    ).fetchall()
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    tag_rows = db.execute(
        f"""SELECT tt.task_id, t.name
              FROM task_tags tt
              JOIN tags t ON t.id = tt.tag_id
             WHERE tt.task_id IN ({marks})
             ORDER BY t.name""",
        ids,
    ).fetchall()
    by_task: dict[int, list[str]] = {}
    for r in tag_rows:
        by_task.setdefault(r["task_id"], []).append(r["name"])
    return [serialize_task(r, by_task.get(r["id"], [])) for r in rows]


def load_columns(board_id: int) -> list[dict]:
    rows = get_db().execute(
        "SELECT * FROM board_columns WHERE board_id = ? ORDER BY position",
        (board_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def parse_due_date(value):
    """Validate an ISO date string; ``None``/``""`` clears the value."""
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValueError("due_date должен быть в формате ГГГГ-ММ-ДД") from None


def replace_task_tags(task_id: int, names) -> list[str]:
    db = get_db()
    uid = current_user_id()
    db.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    cleaned = []
    for raw in names:
        name = str(raw).strip()[:MAX_TAG]
        if not name or name in cleaned:
            continue
        cleaned.append(name)
    for name in cleaned:
        db.execute(
            "INSERT OR IGNORE INTO tags (user_id, name) VALUES (?, ?)", (uid, name)
        )
        tag_id = db.execute(
            "SELECT id FROM tags WHERE user_id = ? AND name = ?", (uid, name)
        ).fetchone()["id"]
        db.execute(
            "INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)",
            (task_id, tag_id),
        )
    return cleaned


def task_tags(task_id: int) -> list[str]:
    rows = get_db().execute(
        """SELECT t.name FROM task_tags tt JOIN tags t ON t.id = tt.tag_id
            WHERE tt.task_id = ? ORDER BY t.name""",
        (task_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def move_task(task_id: int, column_id: int, index: int | None) -> None:
    """Place ``task_id`` at ``index`` (0-based) inside ``column_id``.

    Positions of the destination column are renumbered densely; the source
    column keeps a harmless gap but its relative order stays intact.
    """
    db = get_db()
    rows = db.execute(
        "SELECT id FROM tasks WHERE column_id = ? AND id <> ? ORDER BY position",
        (column_id, task_id),
    ).fetchall()
    order = [r["id"] for r in rows]
    if index is None or index > len(order):
        index = len(order)
    index = max(index, 0)
    order.insert(index, task_id)
    for pos, tid in enumerate(order):
        db.execute("UPDATE tasks SET position = ? WHERE id = ?", (pos, tid))
    db.execute(
        "UPDATE tasks SET column_id = ?, updated_at = datetime('now') WHERE id = ?",
        (column_id, task_id),
    )


# --------------------------------------------------------------------------- health
@api.get("/health")
def health():
    return jsonify(status="ok", csrf_token=get_csrf_token())


# --------------------------------------------------------------------------- boards
@api.get("/boards")
@login_required
def list_boards():
    rows = get_db().execute(
        """SELECT b.*, COUNT(DISTINCT c.id) AS column_count,
                  COUNT(DISTINCT t.id) AS task_count
             FROM boards b
             LEFT JOIN board_columns c ON c.board_id = b.id
             LEFT JOIN tasks t ON t.board_id = b.id
            WHERE b.user_id = ?
            GROUP BY b.id
            ORDER BY b.id""",
        (current_user_id(),),
    ).fetchall()
    return jsonify(boards=[dict(r) for r in rows])


@api.post("/boards")
@login_required
def create_board():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    color = str(data.get("color", "#6366f1")).strip()
    if not name or len(name) > MAX_NAME:
        return bad(f"Название доски: 1-{MAX_NAME} символов")

    db = get_db()
    cur = db.execute(
        "INSERT INTO boards (user_id, name, color) VALUES (?, ?, ?)",
        (current_user_id(), name, color),
    )
    board_id = cur.lastrowid
    for pos, col_name in enumerate(DEFAULT_COLUMNS):
        db.execute(
            "INSERT INTO board_columns (board_id, name, position) VALUES (?, ?, ?)",
            (board_id, col_name, pos),
        )
    db.commit()
    board = dict(db.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone())
    board["columns"] = load_columns(board_id)
    return jsonify(board=board), 201


@api.get("/boards/<int:board_id>")
@login_required
def get_board(board_id):
    board = get_board_or_404(board_id)
    if board is None:
        return bad("Доска не найдена", 404)
    columns = load_columns(board_id)
    tasks = load_tasks(board_id)
    by_column: dict[int, list[dict]] = {}
    for task in tasks:
        by_column.setdefault(task["column_id"], []).append(task)
    for col in columns:
        col["tasks"] = by_column.get(col["id"], [])
    payload = dict(board)
    payload["columns"] = columns
    return jsonify(board=payload)


@api.patch("/boards/<int:board_id>")
@login_required
def update_board(board_id):
    board = get_board_or_404(board_id)
    if board is None:
        return bad("Доска не найдена", 404)
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    color = data.get("color")
    fields, values = [], []
    if name is not None:
        name = str(name).strip()
        if not name or len(name) > MAX_NAME:
            return bad(f"Название доски: 1-{MAX_NAME} символов")
        fields.append("name = ?")
        values.append(name)
    if color is not None:
        color = str(color).strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            return bad("color должен быть в формате #RGB или #RRGGBB")
        fields.append("color = ?")
        values.append(color)
    if not fields:
        return bad("Нет полей для обновления")
    db = get_db()
    values.append(board_id)
    db.execute(f"UPDATE boards SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    row = db.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
    return jsonify(board=dict(row))


@api.delete("/boards/<int:board_id>")
@login_required
def delete_board(board_id):
    board = get_board_or_404(board_id)
    if board is None:
        return bad("Доска не найдена", 404)
    db = get_db()
    db.execute("DELETE FROM boards WHERE id = ?", (board_id,))
    db.commit()
    return jsonify(ok=True)


# --------------------------------------------------------------------------- columns
@api.post("/boards/<int:board_id>/columns")
@login_required
def create_column(board_id):
    board = get_board_or_404(board_id)
    if board is None:
        return bad("Доска не найдена", 404)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 60:
        return bad("Название колонки: 1-60 символов")

    db = get_db()
    pos = db.execute(
        "SELECT COALESCE(MAX(position) + 1, 0) AS p FROM board_columns WHERE board_id = ?",
        (board_id,),
    ).fetchone()["p"]
    cur = db.execute(
        "INSERT INTO board_columns (board_id, name, position) VALUES (?, ?, ?)",
        (board_id, name, pos),
    )
    db.commit()
    row = db.execute("SELECT * FROM board_columns WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(column=dict(row)), 201


@api.patch("/columns/<int:column_id>")
@login_required
def update_column(column_id):
    db = get_db()
    col = db.execute(
        """SELECT c.* FROM board_columns c
             JOIN boards b ON b.id = c.board_id
            WHERE c.id = ? AND b.user_id = ?""",
        (column_id, current_user_id()),
    ).fetchone()
    if col is None:
        return bad("Колонка не найдена", 404)

    data = request.get_json(silent=True) or {}
    fields, values = [], []
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 60:
            return bad("Название колонки: 1-60 символов")
        fields.append("name = ?")
        values.append(name)
    if "position" in data:
        try:
            new_pos = int(data["position"])
        except (TypeError, ValueError):
            return bad("position должен быть целым числом")
        siblings = db.execute(
            "SELECT id FROM board_columns WHERE board_id = ? ORDER BY position",
            (col["board_id"],),
        ).fetchall()
        ids = [r["id"] for r in siblings if r["id"] != column_id]
        new_pos = max(0, min(new_pos, len(ids)))
        ids.insert(new_pos, column_id)
        for pos, cid in enumerate(ids):
            db.execute("UPDATE board_columns SET position = ? WHERE id = ?", (pos, cid))
        db.commit()
        row = db.execute("SELECT * FROM board_columns WHERE id = ?", (column_id,)).fetchone()
        return jsonify(column=dict(row))

    if not fields:
        return bad("Нет полей для обновления")
    values.append(column_id)
    db.execute(f"UPDATE board_columns SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    row = db.execute("SELECT * FROM board_columns WHERE id = ?", (column_id,)).fetchone()
    return jsonify(column=dict(row))


@api.delete("/columns/<int:column_id>")
@login_required
def delete_column(column_id):
    db = get_db()
    col = db.execute(
        """SELECT c.* FROM board_columns c
             JOIN boards b ON b.id = c.board_id
            WHERE c.id = ? AND b.user_id = ?""",
        (column_id, current_user_id()),
    ).fetchone()
    if col is None:
        return bad("Колонка не найдена", 404)
    count = db.execute(
        "SELECT COUNT(*) AS n FROM board_columns WHERE board_id = ?", (col["board_id"],)
    ).fetchone()["n"]
    if count <= 1:
        return bad("Нельзя удалить единственную колонку")
    db.execute("DELETE FROM board_columns WHERE id = ?", (column_id,))
    rows = db.execute(
        "SELECT id FROM board_columns WHERE board_id = ? ORDER BY position",
        (col["board_id"],),
    ).fetchall()
    for pos, row in enumerate(rows):
        db.execute("UPDATE board_columns SET position = ? WHERE id = ?", (pos, row["id"]))
    db.commit()
    return jsonify(ok=True)


# --------------------------------------------------------------------------- tasks
@api.post("/boards/<int:board_id>/tasks")
@login_required
def create_task(board_id):
    board = get_board_or_404(board_id)
    if board is None:
        return bad("Доска не найдена", 404)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title or len(title) > MAX_TITLE:
        return bad(f"Название задачи: 1-{MAX_TITLE} символов")
    description = str(data.get("description", "") or "")
    if len(description) > MAX_DESCRIPTION:
        return bad(f"Описание слишком длинное (макс. {MAX_DESCRIPTION})")
    priority = str(data.get("priority", "medium"))
    if priority not in PRIORITIES:
        return bad(f"priority должен быть одним из: {', '.join(PRIORITIES)}")
    try:
        due_date = parse_due_date(data.get("due_date"))
    except ValueError as exc:
        return bad(str(exc))

    db = get_db()
    column_id = data.get("column_id")
    if column_id is None:
        cols = load_columns(board_id)
        if not cols:
            return bad("На доске нет колонок")
        column_id = cols[0]["id"]
    else:
        col = db.execute(
            "SELECT id FROM board_columns WHERE id = ? AND board_id = ?",
            (int(column_id), board_id),
        ).fetchone()
        if col is None:
            return bad("Колонка не найдена", 404)
        column_id = col["id"]

    pos = db.execute(
        "SELECT COALESCE(MAX(position) + 1, 0) AS p FROM tasks WHERE column_id = ?",
        (column_id,),
    ).fetchone()["p"]
    cur = db.execute(
        """INSERT INTO tasks (board_id, column_id, title, description, priority, due_date, position)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (board_id, column_id, title, description, priority, due_date, pos),
    )
    task_id = cur.lastrowid
    tags = replace_task_tags(task_id, data.get("tags", []) or [])
    db.commit()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return jsonify(task=serialize_task(row, task_tags(task_id))), 201


@api.patch("/tasks/<int:task_id>")
@login_required
def update_task(task_id):
    db = get_db()
    row = db.execute(
        """SELECT t.* FROM tasks t
             JOIN boards b ON b.id = t.board_id
            WHERE t.id = ? AND b.user_id = ?""",
        (task_id, current_user_id()),
    ).fetchone()
    if row is None:
        return bad("Задача не найдена", 404)
    data = request.get_json(silent=True) or {}
    if not data:
        return bad("Нет полей для обновления")

    fields, values = [], []
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > MAX_TITLE:
            return bad(f"Название задачи: 1-{MAX_TITLE} символов")
        fields.append("title = ?")
        values.append(title)
    if "description" in data:
        description = str(data["description"] or "")
        if len(description) > MAX_DESCRIPTION:
            return bad(f"Описание слишком длинное (макс. {MAX_DESCRIPTION})")
        fields.append("description = ?")
        values.append(description)
    if "priority" in data:
        if data["priority"] not in PRIORITIES:
            return bad(f"priority должен быть одним из: {', '.join(PRIORITIES)}")
        fields.append("priority = ?")
        values.append(data["priority"])
    if "due_date" in data:
        try:
            due_date = parse_due_date(data["due_date"])
        except ValueError as exc:
            return bad(str(exc))
        fields.append("due_date = ?")
        values.append(due_date)

    if fields:
        fields.append("updated_at = datetime('now')")
        values.append(task_id)
        db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)

    if "column_id" in data or "index" in data:
        column_id = data.get("column_id", row["column_id"])
        col = db.execute(
            "SELECT id FROM board_columns WHERE id = ? AND board_id = ?",
            (int(column_id), row["board_id"]),
        ).fetchone()
        if col is None:
            return bad("Колонка не найдена", 404)
        index = data.get("index")
        if index is not None:
            try:
                index = int(index)
            except (TypeError, ValueError):
                return bad("index должен быть целым числом")
        move_task(task_id, col["id"], index)

    if "tags" in data:
        tags_raw = data["tags"]
        if not isinstance(tags_raw, list):
            return bad("tags должен быть массивом")
        replace_task_tags(task_id, tags_raw)

    db.commit()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return jsonify(task=serialize_task(row, task_tags(task_id)))


@api.post("/tasks/<int:task_id>/move")
@login_required
def move_task_endpoint(task_id):
    db = get_db()
    row = db.execute(
        """SELECT t.* FROM tasks t
             JOIN boards b ON b.id = t.board_id
            WHERE t.id = ? AND b.user_id = ?""",
        (task_id, current_user_id()),
    ).fetchone()
    if row is None:
        return bad("Задача не найдена", 404)
    data = request.get_json(silent=True) or {}
    column_id = data.get("column_id", row["column_id"])
    col = db.execute(
        "SELECT id FROM board_columns WHERE id = ? AND board_id = ?",
        (int(column_id), row["board_id"]),
    ).fetchone()
    if col is None:
        return bad("Колонка не найдена", 404)
    index = data.get("index")
    if index is not None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return bad("index должен быть целым числом")
    move_task(task_id, col["id"], index)
    db.commit()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return jsonify(task=serialize_task(row, task_tags(task_id)))


@api.delete("/tasks/<int:task_id>")
@login_required
def delete_task(task_id):
    db = get_db()
    row = db.execute(
        """SELECT t.id FROM tasks t
             JOIN boards b ON b.id = t.board_id
            WHERE t.id = ? AND b.user_id = ?""",
        (task_id, current_user_id()),
    ).fetchone()
    if row is None:
        return bad("Задача не найдена", 404)
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return jsonify(ok=True)


# --------------------------------------------------------------------------- tags / search / stats
@api.get("/tags")
@login_required
def list_tags():
    rows = get_db().execute(
        """SELECT t.id, t.name, COUNT(tt.task_id) AS usage
             FROM tags t
             LEFT JOIN task_tags tt ON tt.tag_id = t.id
             LEFT JOIN tasks tk ON tk.id = tt.task_id
             LEFT JOIN boards b ON b.id = tk.board_id
            WHERE t.user_id = ?
            GROUP BY t.id
            ORDER BY t.name""",
        (current_user_id(),),
    ).fetchall()
    return jsonify(tags=[dict(r) for r in rows])


@api.get("/search")
@login_required
def search():
    args = request.args
    q = str(args.get("q", "")).strip().lower()
    board_id = args.get("board_id", type=int)
    priority = args.get("priority")
    sql = [
        """SELECT t.*, b.name AS board_name, c.name AS column_name
             FROM tasks t
             JOIN boards b ON b.id = t.board_id
             JOIN board_columns c ON c.id = t.column_id
            WHERE b.user_id = ?"""
    ]
    params: list = [current_user_id()]
    if board_id:
        sql.append("AND t.board_id = ?")
        params.append(board_id)
    if priority:
        if priority not in PRIORITIES:
            return bad(f"priority должен быть одним из: {', '.join(PRIORITIES)}")
        sql.append("AND t.priority = ?")
        params.append(priority)
    if q:
        sql.append(
            """AND (LOWER(t.title) LIKE ? OR LOWER(t.description) LIKE ?
                    OR EXISTS (SELECT 1 FROM task_tags tt
                                 JOIN tags g ON g.id = tt.tag_id
                                WHERE tt.task_id = t.id AND LOWER(g.name) LIKE ?))"""
        )
        like = f"%{q}%"
        params.extend([like, like, like])
    sql.append("ORDER BY b.id, t.column_id, t.position LIMIT 200")
    rows = get_db().execute(" ".join(sql), params).fetchall()
    results = []
    for r in rows:
        item = serialize_task(r, task_tags(r["id"]))
        item["board_name"] = r["board_name"]
        item["column_name"] = r["column_name"]
        results.append(item)
    return jsonify(results=results, count=len(results))


@api.get("/boards/<int:board_id>/stats")
@login_required
def board_stats(board_id):
    board = get_board_or_404(board_id)
    if board is None:
        return bad("Доска не найдена", 404)
    db = get_db()
    columns = load_columns(board_id)
    tasks = load_tasks(board_id)

    by_column = {c["id"]: 0 for c in columns}
    by_priority = {p: 0 for p in PRIORITIES}
    today = date.today()
    soon = today + timedelta(days=3)
    done_id = columns[-1]["id"] if columns else None

    overdue = due_soon = without_due = 0
    for t in tasks:
        by_column[t["column_id"]] = by_column.get(t["column_id"], 0) + 1
        by_priority[t["priority"]] += 1
        if not t["due_date"]:
            without_due += 1
            continue
        try:
            due = date.fromisoformat(t["due_date"])
        except ValueError:
            continue
        # сроки «горят» только для задач, которые ещё не сделаны
        if t["column_id"] == done_id:
            continue
        if due < today:
            overdue += 1
        elif due <= soon:
            due_soon += 1

    done = by_column.get(done_id, 0) if done_id else 0
    return jsonify(
        board_id=board_id,
        total=len(tasks),
        by_column=[
            {"column_id": c["id"], "name": c["name"], "count": by_column.get(c["id"], 0)}
            for c in columns
        ],
        by_priority=by_priority,
        overdue=overdue,
        due_soon=due_soon,
        without_due=without_due,
        done=done,
        done_percent=round(done * 100 / len(tasks), 1) if tasks else 0.0,
    )
