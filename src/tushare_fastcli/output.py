from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any


def _is_dataframe(value: Any) -> bool:
    return all(hasattr(value, attr) for attr in ["to_dict", "to_json", "to_csv", "to_string"])


def _is_records(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _records_to_csv(records: list[dict[str, Any]]) -> str:
    columns: list[str] = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)
    if not columns:
        return ""

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue()


def limit_rows(value: Any, max_rows: int | None) -> Any:
    if max_rows is None or max_rows <= 0:
        return value
    if _is_dataframe(value):
        return value.head(max_rows)
    if isinstance(value, list):
        return value[:max_rows]
    return value


def render(value: Any, output_format: str) -> str:
    if _is_dataframe(value):
        if output_format == "json":
            return value.to_json(orient="records", force_ascii=False, date_format="iso")
        if output_format == "jsonl":
            return value.to_json(orient="records", lines=True, force_ascii=False, date_format="iso")
        if output_format == "csv":
            return value.to_csv(index=False)
        return value.to_string(index=False)

    if output_format == "jsonl" and isinstance(value, list):
        return "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in value)
    if output_format == "csv" and _is_records(value):
        return _records_to_csv(value)
    if output_format == "csv":
        raise ValueError("CSV 输出要求 Tushare 返回 DataFrame")
    if output_format == "table":
        return str(value)
    return json.dumps(value, ensure_ascii=False, default=str)


def emit(text: str, output: str | Path | None = None) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
        return
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
