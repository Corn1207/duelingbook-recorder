from pathlib import Path
from flask import Flask, send_from_directory

from app.database import init_db
from app.routes import bp

THUMBNAILS_DIR = Path(__file__).parent.parent / "output" / "thumbnails"


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    init_db()
    app.register_blueprint(bp)

    @app.route("/thumbnails/<path:filename>")
    def serve_thumbnail_file(filename):
        return send_from_directory(str(THUMBNAILS_DIR), filename)

    return app
