from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def load_api_defaults() -> dict[str, dict[str, Any]]:
    data_path = files("tushare_fastcli").joinpath("api_defaults.json")
    return json.loads(data_path.read_text(encoding="utf-8"))


def default_params(api_name: str) -> dict[str, Any]:
    return dict(load_api_defaults().get(api_name, {}))

