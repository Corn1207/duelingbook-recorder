from flask import Flask

from app.database import init_db
from app.routes import bp


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    init_db()
    app.register_blueprint(bp)
    return app
