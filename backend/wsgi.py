"""Local Flask entry point.

The deterministic analysis module remains shared with ``data_pipeline/``;
adding the repository root here lets ``python wsgi.py`` from ``backend/`` use
that canonical implementation without a second installed package or copy.
The Lambda build mirrors the same package into its deployment root.
"""

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
