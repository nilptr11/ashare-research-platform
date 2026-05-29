from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROW_PATTERN = re.compile(
    r"^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|?\s*$"
)
DOC_ID_PATTERN = re.compile(r"/(\d+)\.md$")


def clean_text(value: str) -> str:
    value = value.strip()
    if value.lower() in {"<br />", "<br/>", "<br>"}:
        return ""
    return (
        value.replace(r"\~", "~")
        .replace("&nbsp;", " ")
        .replace("**", "")
        .strip()
    )


def parse_markdown(source: Path) -> list[dict[str, str]]:
    interfaces: list[dict[str, str]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        match = ROW_PATTERN.match(line)
        if not match:
            continue

        api_name, doc_url, title, category, description = match.groups()
        doc_id_match = DOC_ID_PATTERN.search(doc_url)
        doc_id = doc_id_match.group(1) if doc_id_match else ""
        api_name = clean_text(api_name)
        interfaces.append(
            {
                "api_name": api_name,
                "title": clean_text(title),
                "category": clean_text(category),
                "description": clean_text(description),
                "doc_url": clean_text(doc_url),
                "doc_id": doc_id,
                "key": f"{api_name}:{doc_id}",
            }
        )
    return interfaces


def main() -> int:
    parser = argparse.ArgumentParser(description="从 Tushare Markdown 索引生成接口 JSON")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    interfaces = parse_markdown(args.source)
    payload = {
        "source": str(args.source),
        "count": len(interfaces),
        "interfaces": interfaces,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

