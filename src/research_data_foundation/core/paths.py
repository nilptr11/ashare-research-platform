from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_data_dir() -> Path:
    configured = os.environ.get("RDF_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return project_root() / "data"
