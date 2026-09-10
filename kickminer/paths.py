"""Where the miner keeps its mutable files.

Everything lives under one root so a container needs only a single volume:

    <root>/config.json
    <root>/logs/kickminer.log
    <root>/data/analytics.sqlite3

``root`` is ``$KICK_MINER_DATA`` (set to ``/data`` in the Docker image), or the
current working directory when that variable is unset - so ``python main.py``
from a checkout keeps writing ``./config.json``, ``./logs`` and ``./data`` as
before.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_ROOT = Path(os.environ.get("KICK_MINER_DATA") or ".").resolve()

CONFIG_PATH = Path(os.environ.get("KICK_MINER_CONFIG") or (DATA_ROOT / "config.json"))
LOG_DIR = DATA_ROOT / "logs"
ANALYTICS_DB = DATA_ROOT / "data" / "analytics.sqlite3"
