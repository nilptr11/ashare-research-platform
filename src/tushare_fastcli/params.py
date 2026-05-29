from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class ParameterError(ValueError):
    pass


def parse_json_object(raw: str, source: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParameterError(f"{source} 不是合法 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ParameterError(f"{source} 必须是 JSON object")
    return value


def parse_param_pair(raw: str) -> tuple[str, Any]:
    if ":=" in raw:
        key, value = raw.split(":=", 1)
        key = key.strip()
        if not key:
            raise ParameterError(f"参数缺少名称：{raw}")
        try:
            return key, json.loads(value)
        except json.JSONDecodeError as exc:
            raise ParameterError(f"参数 {key} 的 JSON 值不合法：{exc}") from exc

    if "=" not in raw:
        raise ParameterError(f"参数必须是 key=value 或 key:=JSON：{raw}")

    key, value = raw.split("=", 1)
    key = key.strip()
    if not key:
        raise ParameterError(f"参数缺少名称：{raw}")
    return key, value


def merge_params(
    json_params: str | None = None,
    params_file: str | Path | None = None,
    pairs: Iterable[str] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}

    if json_params:
        merged.update(parse_json_object(json_params, "--params"))

    if params_file:
        path = Path(params_file)
        merged.update(parse_json_object(path.read_text(encoding="utf-8"), str(path)))

    for pair in pairs or []:
        key, value = parse_param_pair(pair)
        merged[key] = value

    return merged

