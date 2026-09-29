"""Наполняет базу демо-данными: пользователь demo / demo1234.

Запуск:  .venv/bin/python seed.py
Повторный запуск безопасен — существующие данные не дублируются.
"""
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db

USER = "demo"
PASSWORD = "demo1234"

BOARD = "Разработка TaskBoard"

COLUMNS = {
    "Бэклог": [
        ("Исследовать конкурентов", "low", ["research"], 14),
        ("Спроектировать схему БД", "high", ["backend"], 3),
        ("Написать техзадачу", "medium", ["docs"], None),
    ],
    "В работе": [
        ("Реализовать REST API", "urgent", ["backend", "api"], 1),
        ("Сделать drag & drop", "high", ["frontend"], 2),
        ("Покрыть тестами", "medium", ["tests"], None),
    ],
    "Готово": [
        ("Настроить проект", "low", ["infra"], -5),
        ("Выбрать стек", "medium", ["research"], -7),
    ],
}

TASK_DESCRIPTIONS = {
    "Реализовать REST API": "Эндпоинты для досок, колонок и задач. Валидация и JSON-ошибки.",
    "Сделать drag & drop": "HTML5 DnD, оптимистичное обновление UI, откат при ошибке.",
    "Покрыть тестами": "pytest: auth, CRUD, перемещение задач, поиск, статистика.",
}


def main() -> None:
    app = create_app()
    with app.app_context():
        db = get_db()

        user = db.execute("SELECT * FROM users WHERE username = ?", (USER,)).fetchone()
        if user is None:
            cur = db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (USER, generate_password_hash(PASSWORD)),
            )
            user_id = cur.lastrowid
            print(f"Создан пользователь {USER} / {PASSWORD}")
        else:
            user_id = user["id"]
            print(f"Пользователь {USER} уже существует")

        exists = db.execute(
            "SELECT id FROM boards WHERE user_id = ? AND name = ?", (user_id, BOARD)
        ).fetchone()
        if exists:
            print(f"Доска «{BOARD}» уже есть — выходим")
            db.commit()
            return

        cur = db.execute(
            "INSERT INTO boards (user_id, name, color) VALUES (?, ?, ?)",
            (user_id, BOARD, "#6366f1"),
        )
        board_id = cur.lastrowid

        today = date.today()
        for pos, (col_name, tasks) in enumerate(COLUMNS.items()):
            col_cur = db.execute(
                "INSERT INTO board_columns (board_id, name, position) VALUES (?, ?, ?)",
                (board_id, col_name, pos),
            )
            col_id = col_cur.lastrowid
            for t_pos, (title, priority, tags, offset) in enumerate(tasks):
                due = (today + timedelta(days=offset)).isoformat() if offset is not None else None
                task_cur = db.execute(
                    """INSERT INTO tasks
                       (board_id, column_id, title, description, priority, due_date, position)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        board_id,
                        col_id,
                        title,
                        TASK_DESCRIPTIONS.get(title, ""),
                        priority,
                        due,
                        t_pos,
                    ),
                )
                task_id = task_cur.lastrowid
                for tag in tags:
                    db.execute(
                        "INSERT OR IGNORE INTO tags (user_id, name) VALUES (?, ?)",
                        (user_id, tag),
                    )
                    tag_id = db.execute(
                        "SELECT id FROM tags WHERE user_id = ? AND name = ?",
                        (user_id, tag),
                    ).fetchone()["id"]
                    db.execute(
                        "INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)",
                        (task_id, tag_id),
                    )

        db.commit()
        total = db.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE board_id = ?", (board_id,)
        ).fetchone()["n"]
        print(f"Доска «{BOARD}» создана: {len(COLUMNS)} колонки, {total} задач")


if __name__ == "__main__":
    main()
