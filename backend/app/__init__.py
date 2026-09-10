import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

# The audit API reuses the canonical structured-analysis module from the
# repository's data_pipeline namespace. Tests and local Flask commands run
# with backend/ as their working directory, whereas Lambda packages the same
# namespace beside app/. Locate that shared root before importing routes.
for _candidate in Path(__file__).resolve().parents:
    if (_candidate / "data_pipeline" / "analysis" / "investigator_skeptic.py").is_file():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

from app import firms_live
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

    # On Lambda this runs in the init phase, which has a full CPU; the first
    # cold request then finds the S3 client built and its connection open,
    # instead of paying for both on the handler's fraction of one (#251).
    # After load_dotenv, so a local run with the bucket set warms too.
    firms_live.warm_shared_cache()

    return app
