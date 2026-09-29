# 🗂️ TaskBoard

[![CI](https://github.com/bdfytu-commits/taskboard/actions/workflows/ci.yml/badge.svg)](https://github.com/bdfytu-commits/taskboard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Веб-приложение-канбан для управления задачами: доски, колонки, карточки с
drag & drop, чеклисты, теги, приоритеты, сроки, поиск, статистика и экспорт.

**Стек:** Python 3.14 · Flask 3 · SQLite · vanilla JS (без сборки и фронтенд-фреймворков)

**Демо (постоянная ссылка):** https://bdfytu-commits.github.io/taskboard/ —
переадаптует на живое приложение · исходники: [GitHub](https://github.com/bdfytu-commits/taskboard)

---

## Возможности

- 🔐 Регистрация / вход, сессии, CSRF-защита изменяющих запросов, rate limiting (429)
- 📋 Несколько досок, колонки (добавление, переименование, **перетаскивание порядка**, удаление)
- 🃏 Задачи: название, описание, 4 уровня приоритета, срок, теги
- ✅ **Подзадачи-чеклисты** внутри задачи: прогресс на карточке и в статистике
- 💬 **Комментарии к задачам** — обсуждение прямо в карточке
- 🎯 **Вкладка «Мои задачи»** — поток по всем доскам с группами: просрочено,
  сегодня, неделя, позже, без срока, и сводкой по корзинам
- 🌗 **Светлая и тёмная тема**, выбор сохраняется в браузере
- 🛡 **Админ-панель** — обзор всех пользователей, их досок, задач и комментариев,
  **карточка параметров любой задачи** (владелец, доска, колонка, приоритет, срок,
  теги, чеклист, обсуждение), поиск задач по всем аккаунтам, смена роли и удаление аккаунта
- 🖱 Drag & drop карточек между колонками и внутри колонки (оптимистичный UI)
- 🔎 Живой поиск по названию, описанию и тегам + фильтр по приоритету
- 📊 Статистика доски: выполнено, просрочено, горящие сроки, подзадачи, разбивки
- ⬇️ Экспорт доски: **Markdown**-чеклист или полный **JSON**-дамп
- ⌨️ Горячие клавиши: `/` — поиск, `N` — новая задача, `Esc` — закрыть
- 🛡 Изоляция данных: каждый пользователь видит только свои доски (проверяется тестами)

## Быстрый старт

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py          # http://127.0.0.1:5000
```

Демо-аккаунты (после `seed.py`):

| Роль | Логин | Пароль | Что внутри |
| --- | --- | --- | --- |
| Пользователь | `demo` | `demo1234` | 4 доски, 39 задач, чеклисты, комментарии |
| Администратор | `admin` | `admin1234` | Админ-панель + доска «Администрирование TaskBoard» |

```bash
.venv/bin/python seed.py
```

Тесты (82 шт.):

```bash
.venv/bin/python -m pytest -q
```

E2E-тесты интерфейса (Playwright, headless Chromium, 22 проверки):

```bash
npm install && npx playwright install chromium
make test-ui        # свежая база -> сервер -> seed -> скрипт -> скриншоты в docs/
```

CI на GitHub Actions гоняет оба набора на каждый push.

## Структура

```
taskboard/
├── run.py               # точка входа
├── seed.py              # наполнение демо-данными
├── Makefile             # install / run / test / test-ui / seed
├── package.json         # playwright для E2E-тестов
├── app/
│   ├── __init__.py      # фабрика приложения, CSRF, обработчики ошибок
│   ├── db.py            # подключение SQLite, инициализация схемы
│   ├── schema.sql       # users(+role), boards, board_columns, tasks, subtasks,
│   │                    #   comments, tags
│   ├── auth.py          # /api/auth/* , login_required, admin_required, rate limiting
│   ├── api.py           # /api/* — доски, колонки, задачи, подзадачи,
│   │                    #   комментарии, «мои задачи», поиск, статистика, экспорт
│   ├── admin.py         # /api/admin/* — админ-панель: сводка, пользователи,
│   │                    #   данные аккаунта, поиск задач, роли, удаление
│   ├── templates/index.html
│   └── static/          # app.js, style.css
├── tests/
│   ├── conftest.py      # фикстуры: клиент с CSRF, пользователи, доски
│   ├── test_auth.py     # регистрация, вход, CSRF, rate limiting
│   ├── test_boards.py   # доски и колонки, права доступа
│   ├── test_tasks.py    # задачи, валидация, перемещение и порядок
│   ├── test_subtasks.py # чеклисты: CRUD, лимиты, права, статистика
│   ├── test_comments.py # комментарии: CRUD и права
│   ├── test_my_tasks.py # поток «Мои задачи»: корзины, фильтры, сводка
│   ├── test_admin.py    # роли, админ-эндпоинты, 403 для обычных юзеров
│   ├── test_export.py   # экспорт в JSON и Markdown
│   ├── test_search_stats.py
│   └── ui/ui_test.mjs   # E2E: вход, CRUD, чеклисты, drag & drop, поиск,
│                        #   статистика, колонки, экспорт, диалоги, клавиши,
│                        #   темы, комментарии, «Мои задачи», админ-панель
└── docs/                # скриншоты E2E-прогона
```

## API

| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/auth/register` | регистрация `{username, password}` |
| POST | `/api/auth/login` | вход |
| POST | `/api/auth/logout` | выход |
| GET | `/api/auth/me` | текущий пользователь + CSRF-токен |
| GET / POST | `/api/boards` | список / создание доски |
| GET / PATCH / DELETE | `/api/boards/{id}` | доска с колонками и задачами |
| POST | `/api/boards/{id}/columns` | новая колонка |
| PATCH / DELETE | `/api/columns/{id}` | переименовать/переставить/удалить |
| POST | `/api/boards/{id}/tasks` | создать задачу |
| PATCH / DELETE | `/api/tasks/{id}` | изменить/удалить задачу |
| POST | `/api/tasks/{id}/move` | переместить `{column_id, index}` |
| POST | `/api/tasks/{id}/subtasks` | добавить подзадачу |
| PATCH / DELETE | `/api/subtasks/{id}` | отметить/переименовать/удалить подзадачу |
| GET / POST | `/api/tasks/{id}/comments` | комментарии задачи / новый комментарий |
| DELETE | `/api/comments/{id}` | удалить свой комментарий |
| GET | `/api/my-tasks?q=&priority=&period=` | все задачи пользователя + сводка |
| GET | `/api/admin/summary` | сводка по всем данным (только admin) |
| GET | `/api/admin/users` | пользователи со счётчиками досок/задач/комментариев |
| GET | `/api/admin/users/{id}` | доски, колонки, задачи, чеклисты аккаунта |
| GET | `/api/admin/tasks?q=&priority=` | поиск задач по всем аккаунтам |
| GET | `/api/admin/tasks/{id}` | полные параметры задачи: владелец, доска, срок, чеклист, комментарии |
| POST | `/api/admin/users/{id}/role` | выдать/забрать роль администратора |
| DELETE | `/api/admin/users/{id}` | удалить аккаунт и все его данные |
| GET | `/api/search?q=&priority=&board_id=` | поиск задач |
| GET | `/api/boards/{id}/export?format=json\|md` | выгрузка доски |
| GET | `/api/tags` | теги пользователя со счётчиком использования |
| GET | `/api/boards/{id}/stats` | статистика доски |
| GET | `/api/health` | проверка работоспособности |

Все ответы — JSON. Ошибки: `{"error": "..."}` со статусом 400/401/403/404/409/429.

## Безопасность

- Пароли — `werkzeug.security` (scrypt), не хранятся открытым текстом
- Запросы `POST/PATCH/DELETE` требуют заголовок `X-CSRF-Token` из сессии
- Rate limiting: 10 неудачных попыток входа/регистрации за минуту → 429
- Каждый SQL-запрос к доскам/задачам фильтруется по `user_id`
- Параметры запросов всегда идут через плейсхолдеры (`?`) — SQL-инъекции исключены
- Секретный ключ генерируется в `instance/secret_key` при первом запуске

## Запуск в проде

Встроенного сервера Flask достаточно для разработки. Для продакшена:

```bash
.venv/bin/pip install gunicorn
gunicorn -w 4 -b 127.0.0.1:8000 "run:app"
```
