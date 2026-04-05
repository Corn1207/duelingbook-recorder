import logging
from pathlib import Path
from flask import Flask, send_from_directory

from app.database import init_db
from app.routes import bp

THUMBNAILS_DIR = Path(__file__).parent.parent / "output" / "thumbnails"
LOG_FILE = Path(__file__).parent.parent / "output" / "app.log"


def _setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(console_handler)
    else:
        root.addHandler(file_handler)


def _recover_stuck_recordings():
    """Resets any replays stuck in 'recording' state from a previous crashed session."""
    from app.database import get_connection
    with get_connection() as conn:
        affected = conn.execute(
            "UPDATE replays SET status='pending', updated_at=datetime('now') WHERE status='recording'"
        ).rowcount
        conn.commit()
    if affected:
        logging.getLogger(__name__).warning(f"Recovered {affected} replay(s) stuck in 'recording' state.")


def create_app() -> Flask:
    _setup_logging()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    init_db()
    _recover_stuck_recordings()
    app.register_blueprint(bp)

    @app.route("/thumbnails/<path:filename>")
    def serve_thumbnail_file(filename):
        return send_from_directory(str(THUMBNAILS_DIR), filename)

    return app
