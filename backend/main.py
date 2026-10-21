"""Vercel / ASGI server entrypoint for Project EUREKA FastAPI backend."""

import os
import sys
from pathlib import Path

# Ensure backend/src is on sys.path so 'eureka' package is importable
current_dir = Path(__file__).resolve().parent
src_dir = current_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from eureka.api.main import app

__all__ = ["app"]
