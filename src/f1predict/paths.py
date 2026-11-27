"""Filesystem layout for downloaded (raw) and cleaned (processed) data.

Everything lives under ``data/`` at the repository root unless the
``F1PREDICT_DATA`` environment variable points elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("F1PREDICT_DATA", REPO_ROOT / "data"))

RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = REPO_ROOT / "reports"

JOLPICA_RAW = RAW_DIR / "jolpica"
OPENF1_RAW = RAW_DIR / "openf1"
FASTF1_CACHE = DATA_DIR / "fastf1-cache"

JOLPICA_OUT = PROCESSED_DIR / "jolpica"
OPENF1_OUT = PROCESSED_DIR / "openf1"
FASTF1_OUT = PROCESSED_DIR / "fastf1"


def ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
