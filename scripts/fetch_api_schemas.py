from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tushare_fastcli.defaults import load_api_defaults  # noqa: E402
from tushare_fastcli.registry import InterfaceEntry, load_registry  # noqa: E402


CALL_PATTERN = re.compile(r"\bpro\.([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)", re.DOTALL)


def fetch_text(url: str, timeout: int, retries: int) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": "tushare-fastcli/0.1"})
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except (OSError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
    raise last_error or RuntimeError(f"无法抓取文档：{url}")


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("<br>", " ").replace("<br />", " ").replace("<br/>", " ")).strip()


def split_table_row(line: str) -> list[str]:
    line = line.strip().strip("|")
    return [clean_cell(cell) for cell in line.split("|")]


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells)


def normalized_heading(line: str) -> str:
    return line.strip().strip("#").strip().strip("*").strip()


def is_input_heading(line: str) -> bool:
    heading = normalized_heading(line)
    if "输出" in heading:
        return False
    return heading == "接口参数" or heading.endswith("输入参数")


def is_section_heading(line: str) -> bool:
    heading = normalized_heading(line)
    if is_input_heading(line):
        return True
    return heading in {"输出参数", "接口使用", "接口示例", "数据样例", "说明"} or heading.endswith("输出参数")


def input_section_lines(text: str) -> list[str]:
    lines = text.splitlines()
    start_index: int | None = None
    for index, line in enumerate(lines):
        if is_input_heading(line):
            start_index = index + 1
            break
    if start_index is None:
        return []

    section: list[str] = []
    for line in lines[start_index:]:
        stripped = line.strip()
        if stripped and is_section_heading(stripped):
            break
        section.append(line)
    return section


def parse_input_params(text: str) -> tuple[list[dict[str, str]], str]:
    rows: list[dict[str, str]] = []
    saw_header = False
    for line in input_section_lines(text):
        if "|" not in line:
            continue
        cells = split_table_row(line)
        if len(cells) < 4:
            continue
        if is_separator_row(cells):
            continue
        if cells[0] in {"名称", "参数", "字段"}:
            saw_header = True
            continue
        if not saw_header:
            continue

        required_text = cells[2].upper()
        rows.append(
            {
                "name": cells[0],
                "type": cells[1],
                "required": "Y" if required_text == "Y" else "N",
                "raw_required": cells[2],
                "description": " | ".join(cells[3:]),
            }
        )

    if rows:
        return rows, "ok"
    if input_section_lines(text):
        return [], "no_input_table"
    return [], "no_input_section"


def literal_keywords(call_args: str) -> dict[str, Any]:
    try:
        expression = ast.parse(f"f({call_args})", mode="eval")
    except SyntaxError:
        return {}
    if not isinstance(expression.body, ast.Call):
        return {}

    params: dict[str, Any] = {}
    for keyword in expression.body.keywords:
        if keyword.arg is None:
            continue
        try:
            params[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, SyntaxError):
            continue
    return params


def parse_examples(text: str, api_name: str) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for match in CALL_PATTERN.finditer(text):
        if match.group(1) != api_name:
            continue
        call_args = match.group(2).strip()
        params = {} if not call_args else literal_keywords(call_args)
        if (params or not call_args) and params not in examples:
            examples.append(params)
    return examples


def default_params_for(entry: InterfaceEntry, defaults: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str]:
    if entry.key in defaults:
        return dict(defaults[entry.key]), "key"
    if entry.api_name in defaults:
        return dict(defaults[entry.api_name]), "api_name"
    return {}, "none"


def inspect_entry(entry: InterfaceEntry, defaults: dict[str, dict[str, Any]], timeout: int, retries: int) -> dict[str, Any]:
    try:
        text = fetch_text(entry.doc_url, timeout=timeout, retries=retries)
        fetch_status = "ok"
        error_message = ""
    except Exception as exc:  # noqa: BLE001
        text = ""
        fetch_status = "fetch_failed"
        error_message = str(exc)

    input_params, parse_status = parse_input_params(text)
    example_params = parse_examples(text, entry.api_name)
    if parse_status == "no_input_table" and {} in example_params:
        parse_status = "ok"
    default_params, default_source = default_params_for(entry, defaults)
    required_params = [param["name"] for param in input_params if param["required"] == "Y"]
    optional_params = [param["name"] for param in input_params if param["required"] != "Y"]

    return {
        "key": entry.key,
        "api_name": entry.api_name,
        "doc_id": entry.doc_id,
        "title": entry.title,
        "category": entry.category,
        "doc_url": entry.doc_url,
        "fetch_status": fetch_status,
        "parse_status": parse_status,
        "input_params": input_params,
        "required_params": required_params,
        "optional_params": optional_params,
        "example_params": example_params,
        "default_params": default_params,
        "default_params_source": default_source,
        "error_message": error_message,
    }


def write_schema(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_reports(rows: list[dict[str, Any]], output_dir: Path, timestamp: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"tushare_api_schemas_{timestamp}.json"
    csv_path = output_dir / f"tushare_api_schemas_{timestamp}.csv"
    summary = {
        "generated_at": timestamp,
        "total": len(rows),
        "fetch_failed": sum(1 for row in rows if row["fetch_status"] != "ok"),
        "parse_status_counts": {
            status: sum(1 for row in rows if row["parse_status"] == status)
            for status in sorted({str(row["parse_status"]) for row in rows})
        },
        "results": rows,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    columns = [
        "key",
        "api_name",
        "doc_id",
        "title",
        "category",
        "fetch_status",
        "parse_status",
        "required_params",
        "optional_params",
        "default_params_source",
        "default_params",
        "example_params",
        "error_message",
        "doc_url",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            for key in ["required_params", "optional_params", "default_params", "example_params"]:
                csv_row[key] = json.dumps(csv_row.get(key), ensure_ascii=False)
            writer.writerow({column: csv_row.get(column, "") for column in columns})
    return json_path, csv_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取 Tushare 官方文档中的接口入参 schema")
    parser.add_argument("--output", default=ROOT / "src/tushare_fastcli/api_schemas.json", type=Path)
    parser.add_argument("--output-dir", default=ROOT / "reports", type=Path, help="报告输出目录")
    parser.add_argument("--timeout", default=15, type=int, help="单个文档抓取超时秒数")
    parser.add_argument("--retries", default=2, type=int, help="单个文档抓取重试次数")
    parser.add_argument("--delay", default=0.08, type=float, help="文档抓取间隔秒数")
    parser.add_argument("--limit", default=0, type=int, help="最多抓取多少条，0 表示全部")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    entries = load_registry().entries
    if args.limit > 0:
        entries = entries[: args.limit]
    defaults = load_api_defaults()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    rows: list[dict[str, Any]] = []
    total = len(entries)
    print(f"开始抓取 {total} 条接口入参文档", flush=True)
    for index, entry in enumerate(entries, start=1):
        row = inspect_entry(entry, defaults=defaults, timeout=args.timeout, retries=args.retries)
        rows.append(row)
        print(
            f"[{index}/{total}] {entry.api_name}:{entry.doc_id} "
            f"{row['fetch_status']} {row['parse_status']} params={len(row['input_params'])}",
            flush=True,
        )
        if args.delay > 0 and index != total:
            time.sleep(args.delay)

    payload = {
        "generated_at": timestamp,
        "source": "https://tushare.pro/wctapi/documents/{doc_id}.md",
        "count": len(rows),
        "schemas": {row["key"]: row for row in rows},
    }
    write_schema(payload, args.output)
    json_path, csv_path = write_reports(rows, args.output_dir, timestamp)
    print(f"schema：{args.output}", flush=True)
    print(f"JSON 报告：{json_path}", flush=True)
    print(f"CSV 报告：{csv_path}", flush=True)
    print(
        "汇总："
        f"fetch_failed={sum(1 for row in rows if row['fetch_status'] != 'ok')} "
        + " ".join(
            f"{status}={sum(1 for row in rows if row['parse_status'] == status)}"
            for status in sorted({str(row["parse_status"]) for row in rows})
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
