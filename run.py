"""Development entry point: ``python run.py`` or ``flask --app run run``."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    cfg = app.config
    app.run(
        host="127.0.0.1",
        port=cfg.get("PORT", 5000),
        debug=cfg.get("DEBUG", False),
    )
