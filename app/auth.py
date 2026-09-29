"""Registration / login endpoints and the ``login_required`` decorator."""
import re
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
MIN_PASSWORD = 6
MAX_PASSWORD = 128


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


def _user_payload(username: str) -> dict:
    return {"username": username, "csrf_token": get_csrf_token()}


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not USERNAME_RE.match(username):
        return jsonify(
            error="Имя пользователя: 3-32 символа, латиница, цифры, точка, дефис, подчёркивание"
        ), 400
    if not (MIN_PASSWORD <= len(password) <= MAX_PASSWORD):
        return jsonify(error=f"Пароль должен быть от {MIN_PASSWORD} до {MAX_PASSWORD} символов"), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        db.commit()
    except db.IntegrityError:
        return jsonify(error="Это имя пользователя уже занято"), 409

    session.clear()
    session["user_id"] = cur.lastrowid
    return jsonify(_user_payload(username)), 201


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    user = get_db().execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Неверное имя пользователя или пароль"), 401

    session.clear()
    session["user_id"] = user["id"]
    return jsonify(_user_payload(user["username"]))


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
        "SELECT id, username FROM users WHERE id = ?", (uid,)
    ).fetchone()
    if user is None:
        session.clear()
        return jsonify(error="Требуется вход"), 401
    return jsonify(id=user["id"], username=user["username"], csrf_token=get_csrf_token())
