from __future__ import annotations

import csv
import json
import sys
from collections.abc import Sequence
from io import StringIO
from typing import Any

import pandas as pd


def emit(payload: Any, *, fmt: str = "json") -> None:
    text = render(payload, fmt=fmt)
    if text:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


def render(payload: Any, *, fmt: str = "json") -> str:
    if isinstance(payload, pd.DataFrame):
        return _render_frame(payload, fmt)
    if fmt == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if fmt == "jsonl":
        rows = payload if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, dict)) else [payload]
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if fmt == "table":
        rows = payload if isinstance(payload, list) else payload.get("datasets", [payload])
        return _render_table(rows)
    if fmt == "csv":
        rows = payload if isinstance(payload, list) else payload.get("datasets", [payload])
        return _render_csv(rows)
    raise ValueError(f"Unsupported output format: {fmt}")


def _render_frame(frame: pd.DataFrame, fmt: str) -> str:
    if fmt == "json":
        return frame.to_json(orient="records", force_ascii=False, indent=2)
    if fmt == "jsonl":
        return frame.to_json(orient="records", force_ascii=False, lines=True)
    if fmt == "csv":
        return frame.to_csv(index=False)
    if fmt == "table":
        if frame.empty:
            return "(empty)"
        return frame.to_string(index=False)
    raise ValueError(f"Unsupported dataframe output format: {fmt}")


def _render_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(empty)"
    normalized = [_flatten(row) for row in rows]
    columns = sorted({column for row in normalized for column in row})
    widths = {column: max(len(column), *(len(str(row.get(column, ""))) for row in normalized)) for column in columns}
    lines = [
        "  ".join(column.ljust(widths[column]) for column in columns),
        "  ".join("-" * widths[column] for column in columns),
    ]
    for row in normalized:
        lines.append("  ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns))
    return "\n".join(lines)


def _render_csv(rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    if not rows:
        return ""
    normalized = [_flatten(row) for row in rows]
    columns = sorted({column for row in normalized for column in row})
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(normalized)
    return output.getvalue()


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple)):
            flattened[key] = json.dumps(value, ensure_ascii=False)
        else:
            flattened[key] = "" if value is None else value
    return flattened
