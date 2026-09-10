"""Put the repository root on sys.path before any test module imports.

`app/__init__.py` does this itself when it is imported, because the audit
routes reuse `data_pipeline.analysis`. A test module that imports from
`data_pipeline` before it imports `app` therefore fails to collect, and
import sorting will put `data_pipeline` first. Doing it here once means the
order in a test file does not matter.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
