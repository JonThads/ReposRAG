import os
import sys
from pathlib import Path

# Required (no default) since RAG-26 removed the hardcoded credential — a
# placeholder is enough for unit tests, which mock `get_conn` rather than
# opening a real connection.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
