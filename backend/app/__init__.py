import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from app.routes import api


def create_app(config: dict | None = None) -> Flask:
    load_dotenv()

    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
    )
    if config:
        app.config.update(config)

    CORS(app, resources={r"/api/*": {"origins": os.environ.get("CORS_ORIGINS", "*")}})
    app.register_blueprint(api, url_prefix="/api")

    return app
