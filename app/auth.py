"""Registration / login endpoints and the ``login_required`` decorator."""
import re
import threading
import time
from collections import deque
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
MIN_PASSWORD = 6
MAX_PASSWORD = 128


class RateLimiter:
    """Скользящее окно неудачных попыток входа (в памяти процесса)."""

    def __init__(self, max_attempts: int = 10, window: float = 60.0):
        self.max_attempts = max_attempts
        self.window = window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        dq = self._hits.setdefault(key, deque())
        horizon = now - self.window
        while dq and dq[0] < horizon:
            dq.popleft()
        return dq

    def retry_after(self, key: str) -> float | None:
        """Секунды до разрешения новой попытки или ``None``, если лимита нет."""
        now = time.monotonic()
        with self._lock:
            dq = self._prune(key, now)
            if len(dq) < self.max_attempts:
                return None
            return max(1, int(self.window - (now - dq[0]) + 1))

    def hit(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def _limit_key(endpoint: str) -> str:
    return f"{request.remote_addr or '?'}|{endpoint}"


def _rate_limited(key: str):
    wait = limiter.retry_after(key)
    if wait is None:
        return None
    return jsonify(error=f"Слишком много попыток, повторите через {wait} сек."), 429


def current_user_id() -> int | None:
    return session.get("user_id")


def get_csrf_token() -> str:
    """Return the session CSRF token, creating it on first use."""
    token = session.get("csrf_token")
    if not token:
        import secrets

        token = secrets.token_hex(32)
        session["csrf_token"] = token
    return token


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user_id() is None:
            return jsonify(error="Требуется вход"), 401
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        uid = current_user_id()
        if uid is None:
            return jsonify(error="Требуется вход"), 401
        row = get_db().execute(
            "SELECT role FROM users WHERE id = ?", (uid,)
        ).fetchone()
        if row is None or row["role"] != "admin":
            return jsonify(error="Доступ только для администратора"), 403
        return view(*args, **kwargs)

    return wrapped


def user_role(user_id: int) -> str:
    row = get_db().execute(
        "SELECT role FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return row["role"] if row else "user"


def _user_payload(username: str, role: str = "user") -> dict:
    return {"username": username, "role": role, "csrf_token": get_csrf_token()}


@bp.post("/register")
def register():
    key = _limit_key("register")
    limited = _rate_limited(key)
    if limited:
        return limited

    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not USERNAME_RE.match(username):
        limiter.hit(key)
        return jsonify(
            error="Имя пользователя: 3-32 символа, латиница, цифры, точка, дефис, подчёркивание"
        ), 400
    if not (MIN_PASSWORD <= len(password) <= MAX_PASSWORD):
        limiter.hit(key)
        return jsonify(error=f"Пароль должен быть от {MIN_PASSWORD} до {MAX_PASSWORD} символов"), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        db.commit()
    except db.IntegrityError:
        limiter.hit(key)
        return jsonify(error="Это имя пользователя уже занято"), 409

    limiter.reset(key)
    session.clear()
    session["user_id"] = cur.lastrowid
    return jsonify(_user_payload(username)), 201


@bp.post("/login")
def login():
    key = _limit_key("login")
    limited = _rate_limited(key)
    if limited:
        return limited

    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    user = get_db().execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        limiter.hit(key)
        return jsonify(error="Неверное имя пользователя или пароль"), 401

    limiter.reset(key)
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(_user_payload(user["username"], user["role"]))


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
def me():
    uid = current_user_id()
    if uid is None:
        return jsonify(error="Требуется вход"), 401
    user = get_db().execute(
        "SELECT id, username, role FROM users WHERE id = ?", (uid,)
    ).fetchone()
    if user is None:
        session.clear()
        return jsonify(error="Требуется вход"), 401
    return jsonify(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        csrf_token=get_csrf_token(),
    )
