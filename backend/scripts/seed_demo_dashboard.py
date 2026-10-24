#!/usr/bin/env python3
"""Wrapper to run scripts/seed_demo_dashboard.py from backend/scripts/."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.seed_demo_dashboard import seed_demo_data

if __name__ == "__main__":
    force_seed = "--force" in sys.argv
    seed_demo_data(force=force_seed)
