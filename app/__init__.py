"""TaskBoard — Flask application factory."""
import secrets
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from . import db
from .admin import bp as admin_bp
from .api import api
from .auth import bp as auth_bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=None,
        DATABASE=str(Path(app.instance_path) / "taskboard.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=512 * 1024,  # 512 KiB per request
    )

    if test_config is None:
        secret_file = Path(app.instance_path) / "secret_key"
        if not secret_file.exists():
            secret_file.write_text(secrets.token_hex(32), encoding="utf-8")
        app.config["SECRET_KEY"] = secret_file.read_text(encoding="utf-8").strip()
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping(test_config)

    db.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.init_db()

    @app.before_request
    def csrf_protect():
        """Require the session CSRF token for state-changing API calls."""
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        if not request.path.startswith("/api/"):
            return None
        from .auth import current_user_id, get_csrf_token
        import hmac

        if current_user_id() is None:
            return None  # auth endpoints themselves (401 will be returned anyway)
        expected = get_csrf_token()
        supplied = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(expected, supplied):
            return jsonify(error="Неверный CSRF-токен, обновите страницу"), 403
        return None

    @app.errorhandler(404)
    def not_found(err):
        if request.path.startswith("/api/"):
            return jsonify(error="Не найдено"), 404
        return render_template("index.html"), 404

    @app.errorhandler(400)
    def bad_request(err):
        if request.path.startswith("/api/"):
            return jsonify(error="Некорректный запрос"), 400
        return err

    @app.errorhandler(413)
    def too_large(_err):
        return jsonify(error="Слишком большой запрос"), 413

    @app.errorhandler(500)
    def server_error(_err):
        if request.path.startswith("/api/"):
            return jsonify(error="Внутренняя ошибка сервера"), 500
        return "Внутренняя ошибка сервера", 500

    @app.get("/")
    def index():
        return render_template("index.html")

    return app
