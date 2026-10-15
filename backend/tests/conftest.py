"""Test fixtures and path initialization for Project EUREKA."""

import sys
from pathlib import Path

# Add project-eureka/src to sys.path
eureka_src = Path(__file__).resolve().parent.parent / "src"
if str(eureka_src) not in sys.path:
    sys.path.insert(0, str(eureka_src))
