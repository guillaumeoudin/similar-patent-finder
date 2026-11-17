"""Entry point for a Vercel deployment: it exposes the FastAPI app of the package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from priorart.api import app  # noqa: E402,F401
