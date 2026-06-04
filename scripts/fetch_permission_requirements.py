from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashare_data_provider.registry import InterfaceEntry, load_registry  # noqa: E402


POINT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:万)?\s*积分")
PERMISSION_KEYWORDS = ["权限", "积分", "调取说明", "限量", "每分钟", "每次", "单独开权限"]


def fetch_text(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": "ashare-data-provider/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def extract_relevant_text(text: str) -> str:
    compact = clean_requirement_text(text)
    snippets: list[str] = []
    for keyword in PERMISSION_KEYWORDS:
        start = compact.find(keyword)
        if start == -1:
            continue
        end_candidates = [
            position
            for marker in ["**输入参数**", "**输出参数**", "输入参数", "输出参数", "**接口", "接口示例"]
            if (position := compact.find(marker, start)) > start
        ]
        end = min(end_candidates) if end_candidates else min(len(compact), start + 260)
        snippet = clean_requirement_text(compact[start:end].strip(" ：:-"))
        if snippet and not any(snippet in existing or existing in snippet for existing in snippets):
            snippets.append(snippet)
    return " | ".join(snippets)


def clean_requirement_text(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    segments = [segment.strip(" ：:-") for segment in text.split("|")]
    deduped: list[str] = []
    for segment in segments:
        if not segment:
            continue
        if any(segment == existing or segment in existing for existing in deduped):
            continue
        deduped = [existing for existing in deduped if existing not in segment]
        deduped.append(segment)
    return " | ".join(deduped)


def extract_point_values(text: str) -> list[int]:
    values: list[int] = []
    for match in POINT_PATTERN.finditer(text):
        raw_number = float(match.group(1))
        unit_window = text[match.start() : match.end()]
        point_value = int(raw_number * 10000) if "万" in unit_window else int(raw_number)
        values.append(point_value)
    return values


def classify(requirement_text: str, current_points: int) -> tuple[str, int | None]:
    point_values = extract_point_values(requirement_text)
    required_points = max(point_values) if point_values else None
    if required_points is not None and required_points <= current_points and "或有" in requirement_text:
        return "points_ok", required_points
    if "单独开权限" in requirement_text or "跟积分没关系" in requirement_text:
        return "needs_separate_permission", required_points
    if required_points is None:
        return "unknown", None
    if required_points <= current_points:
        return "points_ok", required_points
    return "points_insufficient", required_points


def inspect_entry(entry: InterfaceEntry, current_points: int, timeout: int) -> dict[str, object]:
    try:
        text = fetch_text(entry.doc_url, timeout=timeout)
        requirement_text = extract_relevant_text(text)
        status = "ok"
        error_message = ""
    except (OSError, URLError, TimeoutError) as exc:
        requirement_text = ""
        status = "fetch_failed"
        error_message = str(exc)

    eligibility, required_points = classify(requirement_text, current_points)
    return {
        "key": entry.key,
        "api_name": entry.api_name,
        "doc_id": entry.doc_id,
        "title": entry.title,
        "category": entry.category,
        "doc_url": entry.doc_url,
        "fetch_status": status,
        "eligibility": eligibility,
        "required_points": required_points,
        "current_points": current_points,
        "requirement_text": clean_requirement_text(requirement_text),
        "error_message": error_message,
    }


def write_reports(rows: list[dict[str, object]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"tushare_permission_requirements_{timestamp}.json"
    csv_path = output_dir / f"tushare_permission_requirements_{timestamp}.csv"

    summary = {
        "generated_at": timestamp,
        "total": len(rows),
        "counts": {
            status: sum(1 for row in rows if row["eligibility"] == status)
            for status in sorted({str(row["eligibility"]) for row in rows})
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
        "eligibility",
        "required_points",
        "current_points",
        "fetch_status",
        "requirement_text",
        "error_message",
        "doc_url",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})

    return json_path, csv_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取 Tushare 文档中的接口积分/权限要求")
    parser.add_argument("--current-points", type=int, default=15000, help="当前账号积分")
    parser.add_argument("--output-dir", default="reports", type=Path, help="报告输出目录")
    parser.add_argument("--timeout", type=int, default=12, help="单个文档抓取超时秒数")
    parser.add_argument("--delay", type=float, default=0.15, help="文档抓取间隔秒数")
    parser.add_argument("--limit", type=int, default=0, help="最多抓取多少条，0 表示全部")
    return parser


def selected_entries(limit: int) -> list[InterfaceEntry]:
    entries = load_registry().entries
    if limit > 0:
        return entries[:limit]
    return entries


def main() -> int:
    args = build_parser().parse_args()
    entries = selected_entries(args.limit)
    rows: list[dict[str, object]] = []
    total = len(entries)
    print(f"开始抓取 {total} 条接口文档；当前积分：{args.current_points}", flush=True)
    for index, entry in enumerate(entries, start=1):
        row = inspect_entry(entry, current_points=args.current_points, timeout=args.timeout)
        rows.append(row)
        print(
            f"[{index}/{total}] {entry.api_name}:{entry.doc_id} "
            f"{row['eligibility']} required={row['required_points']}",
            flush=True,
        )
        if args.delay > 0 and index != total:
            time.sleep(args.delay)

    json_path, csv_path = write_reports(rows, args.output_dir)
    print(f"JSON 报告：{json_path}", flush=True)
    print(f"CSV 报告：{csv_path}", flush=True)
    print(
        "汇总："
        + " ".join(
            f"{status}={sum(1 for row in rows if row['eligibility'] == status)}"
            for status in sorted({str(row["eligibility"]) for row in rows})
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
