"""Ensures the repository root is importable as ``kickminer`` during tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
