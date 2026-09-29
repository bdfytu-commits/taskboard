"""Наполняет базу демо-данными.

Аккаунты: demo / demo1234 (демо-доски) и admin / admin1234 (админ-панель).

Запуск:  .venv/bin/python seed.py
Повторный запуск безопасен — существующие данные не дублируются.
"""
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db

USER = "demo"
PASSWORD = "demo1234"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin1234"

# Админская доска — чтобы админ-панель не была пустой.
ADMIN_BOARD = {
    "name": "Администрирование TaskBoard",
    "color": "#ef4444",
    "columns": {
        "Запросы": [
            ("Проверить регистрацию новых пользователей", "medium", ["moderation"], 2,
             "Смотреть журнал в админ-панели, жалобы обрабатывать в течение суток."),
            ("Разобраться с жалобой на спам", "high", ["moderation"], 1,
             "Проверить доску автора и при необходимости удалить аккаунт."),
        ],
        "В работе": [
            ("Настроить бэкапы базы", "high", ["infra"], 3,
             "Ежедневный дамп SQLite в объектное хранилище."),
        ],
        "Готово": [
            ("Поднять админ-панель", "high", ["infra"], -1,
             "Обзор пользователей, досок, задач и комментариев."),
        ],
    },
}

# Порядок важен: первая доска открывается по умолчанию.
# Задача: (название, приоритет, теги, сдвиг срока в днях, описание)
BOARDS = [
    {
        "name": "Разработка TaskBoard",
        "color": "#6366f1",
        "columns": {
            "Бэклог": [
                ("Исследовать конкурентов", "low", ["research"], 14,
                 "Обзор досок: Trello, Notion, Linear, YouTrack."),
                ("Спроектировать схему БД", "high", ["backend"], 3,
                 "users, boards, board_columns, tasks, tags, subtasks, comments."),
                ("Написать техзадачу", "medium", ["docs"], None,
                 "Описать требования и критерии готовности."),
                ("Сделать онбординг", "medium", ["ux"], 6,
                 "Пустые состояния с подсказками и демо-аккаунтом."),
                ("Реализовать темы оформления", "low", ["frontend"], 21,
                 "Светлая и тёмная тема, сохранение выбора в браузере."),
                ("Настроить CI", "medium", ["infra"], None,
                 "pytest и Playwright на каждый push."),
            ],
            "В работе": [
                ("Реализовать REST API", "urgent", ["backend", "api"], 1,
                 "Эндпоинты для досок, колонок и задач. Валидация и JSON-ошибки."),
                ("Сделать drag & drop", "high", ["frontend"], 2,
                 "HTML5 DnD, оптимистичное обновление UI, откат при ошибке."),
                ("Покрыть тестами", "medium", ["tests"], None,
                 "pytest: auth, CRUD, перемещение задач, поиск, статистика."),
                ("Добавить комментарии", "high", ["backend", "ux"], 0,
                 "Обсуждение прямо в карточке задачи."),
                ("Экспорт доски в Markdown", "low", ["api"], 4,
                 "Чеклист по колонкам для вставки в конфу."),
            ],
            "Готово": [
                ("Настроить проект", "low", ["infra"], -5, "Flask, SQLite, venv, Makefile."),
                ("Выбрать стек", "medium", ["research"], -7,
                 "Python + Flask + vanilla JS без сборки."),
                ("Сделать авторизацию", "high", ["backend"], -3,
                 "Регистрация, вход, scrypt-хэши, CSRF-заголовок."),
                ("Перетаскивание колонок", "medium", ["frontend"], -1,
                 "Порядок колонок сохраняется на сервере."),
            ],
        },
        "subtasks": {
            "Реализовать REST API": [
                ("спроектировать эндпоинты", True),
                ("написать хендлеры", True),
                ("покрыть тестами", False),
            ],
            "Сделать drag & drop": [
                ("карточки между колонками", True),
                ("перестановка колонок", False),
            ],
            "Покрыть тестами": [
                ("auth и CSRF", True),
                ("CRUD досок", False),
                ("перемещение задач", False),
            ],
            "Добавить комментарии": [("таблица и API", True), ("интерфейс", False)],
        },
        "comments": {
            "Реализовать REST API": [
                "Эндпоинты согласованы, swagger-описание не нужно — хватит README.",
                "Добавил валидацию даты, смотри tests/test_tasks.py.",
            ],
            "Сделать drag & drop": [
                "Оптимистичное обновление выглядит живо, оставляем.",
            ],
            "Настроить CI": [
                "Не забыть кэш pip и npm, иначе прогон полторы минуты.",
            ],
        },
    },
    {
        "name": "Продукт и исследования",
        "color": "#14b8a6",
        "columns": {
            "Идеи": [
                ("Интерактивный тур по доске", "low", ["ux"], 30,
                 "Пошаговая подсказка при первом входе."),
                ("Шаблоны досок", "medium", ["product"], 18,
                 "Команда, спринт, личные цели — готовые раскладки."),
                ("Уведомления о сроках", "high", ["product"], 12,
                 "Напоминание о задачах, срок которых горит."),
            ],
            "Исследуем": [
                ("Опрос 10 пользователей", "high", ["research"], 2,
                 "Понять, как люди планируют неделю."),
                ("Анализ отзывов конкурентов", "medium", ["research"], 5,
                 "Собрать жалобы на канбаны из маркетплейсов."),
                ("Прототип мобильной версии", "medium", ["ux"], None,
                 "Нарисовать ключевые экраны в фигме."),
            ],
            "Выводы": [
                ("Карта болей пользователей", "medium", ["research"], -6,
                 "Топ-5 проблем: шум, потеря задач, нет сроков."),
                ("Гипотезы на квартал", "high", ["product"], -2,
                 "Приоритизация по ICE."),
            ],
        },
        "subtasks": {
            "Опрос 10 пользователей": [
                ("список вопросов", True),
                ("найти респондентов", False),
                ("свести результаты", False),
            ],
        },
        "comments": {
            "Опрос 10 пользователей": [
                "Начали с 3 человек, вопросы ужесточить.",
            ],
        },
    },
    {
        "name": "Маркетинг",
        "color": "#ec4899",
        "columns": {
            "План": [
                ("Контент-план на месяц", "high", ["content"], 4,
                 "12 постов: 4 кейса, 4 туториала, 4 анонса."),
                ("Лендинг с демо", "urgent", ["web"], 1,
                 "Первый экран: живая доска вместо скриншота."),
                ("Письмо для рассылки", "medium", ["email"], 9,
                 "Анонс обновления с чеклистами и комментариями."),
            ],
            "В работе": [
                ("Снять короткое видео", "high", ["video"], 3,
                 "60 секунд: создание задачи, драг-энд-дроп, статистика."),
                ("Собрать логотипы клиентов", "low", ["pr"], None,
                 "Согласовать использование на лендинге."),
            ],
            "Готово": [
                ("Оформить аватарки соцсетей", "low", ["brand"], -4,
                 "Единый стиль, светлая и тёмная версии."),
                ("Завести блог", "medium", ["content"], -9,
                 "Первая статья про канбан-антипаттерны."),
                ("Настроить аналитику", "medium", ["web"], -1,
                 "Счётчики на ключевых экранах."),
            ],
        },
        "subtasks": {
            "Контент-план на месяц": [
                ("темы", True), ("даты", True), ("ответственные", False),
            ],
            "Снять короткое видео": [("сценарий", True), ("запись", False), ("монтаж", False)],
        },
        "comments": {},
    },
    {
        "name": "Личные цели",
        "color": "#f59e0b",
        "columns": {
            "Хочу": [
                ("Пробежать 10 км", "medium", ["спорт"], 25, "План: 3 тренировки в неделю."),
                ("Прочитать 12 книг", "low", ["книги"], None, "По книге в месяц."),
                ("Курс по типографике", "low", ["учёба"], 40, "Разбор сеток и иерархии."),
            ],
            "В процессе": [
                ("Утренняя рутина", "medium", ["спорт"], 0,
                 "Стакан воды, 10 минут растяжки, план дня."),
                ("Отпуск: билеты и жильё", "urgent", ["путешествия"], 7,
                 "Забронировать до подорожания."),
            ],
            "Сделано": [
                ("Собрать чемодан", "low", ["быт"], -2, ""),
                ("Позвонить стоматологу", "medium", ["быт"], -3, ""),
                ("Купить новые кроссовки", "low", ["быт"], -8, ""),
            ],
        },
        "subtasks": {
            "Отпуск: билеты и жильё": [
                ("выбрать даты", True), ("билеты", False), ("жильё", False),
            ],
        },
        "comments": {},
    },
]


def ensure_user(db, username: str, password: str, role: str = "user") -> int:
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
        )
        print(f"Создан пользователь {username} / {password} (роль: {role})")
        return cur.lastrowid
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user["id"]))
    print(f"Пользователь {username} уже существует (роль: {role})")
    return user["id"]


def seed_board(db, user_id: int, spec: dict, today: date) -> bool:
    """Создаёт одну доску со всеми колонками/задачами. False — уже есть."""
    exists = db.execute(
        "SELECT id FROM boards WHERE user_id = ? AND name = ?",
        (user_id, spec["name"]),
    ).fetchone()
    if exists:
        return False

    cur = db.execute(
        "INSERT INTO boards (user_id, name, color) VALUES (?, ?, ?)",
        (user_id, spec["name"], spec["color"]),
    )
    board_id = cur.lastrowid
    total = 0

    for pos, (col_name, tasks) in enumerate(spec["columns"].items()):
        col_cur = db.execute(
            "INSERT INTO board_columns (board_id, name, position) VALUES (?, ?, ?)",
            (board_id, col_name, pos),
        )
        col_id = col_cur.lastrowid

        for t_pos, (title, priority, tags, offset, description) in enumerate(tasks):
            due = (
                (today + timedelta(days=offset)).isoformat()
                if offset is not None
                else None
            )
            task_cur = db.execute(
                """INSERT INTO tasks
                   (board_id, column_id, title, description, priority,
                    due_date, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (board_id, col_id, title, description, priority, due, t_pos),
            )
            task_id = task_cur.lastrowid
            total += 1

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

            for s_pos, (text, done) in enumerate(spec.get("subtasks", {}).get(title, [])):
                db.execute(
                    """INSERT INTO subtasks (task_id, text, done, position)
                       VALUES (?, ?, ?, ?)""",
                    (task_id, text, int(done), s_pos),
                )

            for body in spec.get("comments", {}).get(title, []):
                db.execute(
                    "INSERT INTO comments (task_id, user_id, body) VALUES (?, ?, ?)",
                    (task_id, user_id, body),
                )

    print(f"  Доска «{spec['name']}»: {len(spec['columns'])} колонки, {total} задач")
    return True


def main() -> None:
    app = create_app()
    with app.app_context():
        db = get_db()
        today = date.today()

        user_id = ensure_user(db, USER, PASSWORD)
        admin_id = ensure_user(db, ADMIN_USER, ADMIN_PASSWORD, role="admin")

        created = 0
        for spec in BOARDS:
            if seed_board(db, user_id, spec, today):
                created += 1
        if seed_board(db, admin_id, ADMIN_BOARD, today):
            created += 1

        db.commit()
        if not created:
            print("Все доски уже есть — выходим")
            return

        stats = db.execute(
            """SELECT (SELECT COUNT(*) FROM boards WHERE user_id = ?) AS boards,
                      (SELECT COUNT(*) FROM tasks t JOIN boards b ON b.id = t.board_id
                        WHERE b.user_id = ?) AS tasks,
                      (SELECT COUNT(*) FROM subtasks s
                         JOIN tasks t ON t.id = s.task_id
                         JOIN boards b ON b.id = t.board_id WHERE b.user_id = ?) AS subs,
                      (SELECT COUNT(*) FROM comments c
                         JOIN tasks t ON t.id = c.task_id
                         JOIN boards b ON b.id = t.board_id WHERE b.user_id = ?) AS cmts""",
            (user_id, user_id, user_id, user_id),
        ).fetchone()
        print(
            f"Готово: {stats['boards']} доски, {stats['tasks']} задач, "
            f"{stats['subs']} подзадач, {stats['cmts']} комментариев"
        )


if __name__ == "__main__":
    main()
