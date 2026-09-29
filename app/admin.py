"""Админ-панель: обзор данных всех пользователей на сервере.

Доступно только пользователям с ролью ``admin`` (см. ``role`` в таблице
``users``). Все ответы — read-only, кроме смены роли и удаления аккаунта.
"""
from flask import Blueprint, jsonify, request

from .auth import admin_required, current_user_id
from .db import get_db

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

PRIORITIES = ("low", "medium", "high", "urgent")
MAX_USER_BOARDS = 100
MAX_BOARD_TASKS = 500
MAX_SEARCH = 200


def _count(sql: str, *params) -> int:
    return get_db().execute(sql, params).fetchone()["n"]


def _summary() -> dict:
    db = get_db()

    def n(sql: str) -> int:
        return db.execute(sql).fetchone()["n"]

    active = db.execute(
        """SELECT COUNT(*) AS n FROM users u
            WHERE EXISTS (SELECT 1 FROM boards b WHERE b.user_id = u.id)
               OR EXISTS (SELECT 1 FROM comments c WHERE c.user_id = u.id)"""
    ).fetchone()["n"]
    return {
        "users": n("SELECT COUNT(*) AS n FROM users"),
        "admins": n("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'"),
        "active_users": active,
        "boards": n("SELECT COUNT(*) AS n FROM boards"),
        "columns": n("SELECT COUNT(*) AS n FROM board_columns"),
        "tasks": n("SELECT COUNT(*) AS n FROM tasks"),
        "done_tasks": n(
            """SELECT COUNT(*) AS n FROM tasks t
                JOIN board_columns c ON c.id = t.column_id
                JOIN (SELECT board_id, MAX(position) AS pos
                        FROM board_columns GROUP BY board_id) last
                  ON last.board_id = t.board_id AND last.pos = c.position"""
        ),
        "subtasks": n("SELECT COUNT(*) AS n FROM subtasks"),
        "subtasks_done": n("SELECT COUNT(*) AS n FROM subtasks WHERE done = 1"),
        "comments": n("SELECT COUNT(*) AS n FROM comments"),
        "tags": n("SELECT COUNT(*) AS n FROM tags"),
    }


@bp.get("/summary")
@admin_required
def summary():
    return jsonify(summary=_summary())


@bp.get("/users")
@admin_required
def users():
    rows = get_db().execute(
        """SELECT u.id, u.username, u.role, u.created_at,
                  (SELECT COUNT(*) FROM boards b WHERE b.user_id = u.id) AS boards,
                  (SELECT COUNT(*) FROM tasks t JOIN boards b ON b.id = t.board_id
                    WHERE b.user_id = u.id) AS tasks,
                  (SELECT COUNT(*) FROM comments c WHERE c.user_id = u.id) AS comments,
                  (SELECT MAX(t.updated_at) FROM tasks t JOIN boards b ON b.id = t.board_id
                    WHERE b.user_id = u.id) AS last_activity
             FROM users u
            ORDER BY u.role = 'admin' DESC, u.id"""
    ).fetchall()
    return jsonify(users=[dict(r) for r in rows], count=len(rows))


@bp.get("/users/<int:user_id>")
@admin_required
def user_detail(user_id):
    db = get_db()
    user = db.execute(
        "SELECT id, username, role, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if user is None:
        return jsonify(error="Пользователь не найден"), 404

    boards = db.execute(
        """SELECT id, name, color, created_at,
                  (SELECT COUNT(*) FROM tasks WHERE board_id = boards.id) AS tasks
             FROM boards WHERE user_id = ?
            ORDER BY id LIMIT ?""",
        (user_id, MAX_USER_BOARDS),
    ).fetchall()

    result = []
    for b in boards:
        cols = db.execute(
            "SELECT id, name, position FROM board_columns WHERE board_id = ?"
            " ORDER BY position",
            (b["id"],),
        ).fetchall()
        tasks = db.execute(
            """SELECT t.id, t.title, t.description, t.priority, t.due_date,
                      t.column_id, t.position, t.created_at, t.updated_at,
                      (SELECT COUNT(*) FROM subtasks s WHERE s.task_id = t.id) AS sub_total,
                      (SELECT COUNT(*) FROM subtasks s
                        WHERE s.task_id = t.id AND s.done = 1) AS sub_done,
                      (SELECT COUNT(*) FROM comments c WHERE c.task_id = t.id) AS comments
                 FROM tasks t WHERE t.board_id = ?
                ORDER BY t.column_id, t.position LIMIT ?""",
            (b["id"], MAX_BOARD_TASKS),
        ).fetchall()

        tags = db.execute(
            """SELECT tg.task_id, g.name FROM task_tags tg
                 JOIN tags g ON g.id = tg.tag_id
                 JOIN tasks t ON t.id = tg.task_id
                WHERE t.board_id = ?""",
            (b["id"],),
        ).fetchall()
        tags_by_task: dict[int, list[str]] = {}
        for t in tags:
            tags_by_task.setdefault(t["task_id"], []).append(t["name"])

        by_col: dict[int, list[dict]] = {c["id"]: [] for c in cols}
        for t in tasks:
            item = dict(t)
            item["tags"] = tags_by_task.get(t["id"], [])
            by_col.setdefault(t["column_id"], []).append(item)

        result.append(
            {
                "id": b["id"],
                "name": b["name"],
                "color": b["color"],
                "created_at": b["created_at"],
                "tasks_count": b["tasks"],
                "columns": [
                    {
                        "id": c["id"],
                        "name": c["name"],
                        "position": c["position"],
                        "tasks": by_col.get(c["id"], []),
                    }
                    for c in cols
                ],
            }
        )

    stats = dict(user)
    stats.update(
        boards=len(result),
        tasks=_count(
            "SELECT COUNT(*) AS n FROM tasks t JOIN boards b ON b.id = t.board_id"
            " WHERE b.user_id = ?",
            user_id,
        ),
        comments=_count("SELECT COUNT(*) AS n FROM comments WHERE user_id = ?", user_id),
    )
    return jsonify(user=stats, boards=result)


@bp.get("/tasks")
@admin_required
def search_tasks():
    """Поиск задач по всем пользователям."""
    args = request.args
    q = str(args.get("q", "")).strip().lower()
    priority = args.get("priority")
    if priority and priority not in PRIORITIES:
        return jsonify(error=f"priority должен быть одним из: {', '.join(PRIORITIES)}"), 400

    sql = [
        """SELECT t.id, t.title, t.description, t.priority, t.due_date,
                  t.updated_at, b.id AS board_id, b.name AS board_name,
                  b.color AS board_color, c.name AS column_name,
                  u.id AS user_id, u.username,
                  (SELECT COUNT(*) FROM comments cm WHERE cm.task_id = t.id) AS comments
             FROM tasks t
             JOIN boards b ON b.id = t.board_id
             JOIN users u ON u.id = b.user_id
             JOIN board_columns c ON c.id = t.column_id
            WHERE 1 = 1"""
    ]
    params: list = []
    if q:
        sql.append(
            " AND (lower(t.title) LIKE ? OR lower(t.description) LIKE ?)"
        )
        like = f"%{q}%"
        params += [like, like]
    if priority:
        sql.append(" AND t.priority = ?")
        params.append(priority)
    sql.append(" ORDER BY t.updated_at DESC LIMIT ?")
    params.append(MAX_SEARCH)

    rows = get_db().execute("".join(sql), params).fetchall()
    return jsonify(results=[dict(r) for r in rows], count=len(rows))


@bp.post("/users/<int:user_id>/role")
@admin_required
def set_role(user_id):
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    if role not in ("user", "admin"):
        return jsonify(error="Роль должна быть 'user' или 'admin'"), 400
    if user_id == current_user_id():
        return jsonify(error="Нельзя изменить собственную роль"), 400

    db = get_db()
    user = db.execute(
        "SELECT id, username FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if user is None:
        return jsonify(error="Пользователь не найден"), 404
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()
    return jsonify(ok=True, user_id=user_id, username=user["username"], role=role)


@bp.delete("/users/<int:user_id>")
@admin_required
def delete_user(user_id):
    if user_id == current_user_id():
        return jsonify(error="Нельзя удалить собственный аккаунт"), 400

    db = get_db()
    user = db.execute(
        "SELECT id, username FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if user is None:
        return jsonify(error="Пользователь не найден"), 404
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    return jsonify(ok=True, user_id=user_id, username=user["username"])
