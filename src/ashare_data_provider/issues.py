from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def load_known_issues() -> dict[str, list[dict[str, Any]]]:
    data_path = files("ashare_data_provider").joinpath("known_issues.json")
    return json.loads(data_path.read_text(encoding="utf-8"))


def known_issues(api_name: str) -> list[dict[str, Any]]:
    return list(load_known_issues().get(api_name, []))
