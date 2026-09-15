"""
Pytest configuration for the backend test suite.

The live backend lives in backend-api-test/backend/ (gcode_service.py, app.py).
It is not an installed package, so we add its directory to sys.path here to
make `import gcode_service` work regardless of the directory pytest is
invoked from.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
