from __future__ import annotations

from pathlib import Path


def parse_partition_dir(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in path.parts:
        parsed = parse_partition_name(part)
        if parsed:
            key, value = parsed
            values[key] = value
    return values


def parse_partition_name(name: str) -> tuple[str, str] | None:
    if "=" not in name:
        return None
    key, value = name.split("=", 1)
    if not key:
        return None
    return key, value
