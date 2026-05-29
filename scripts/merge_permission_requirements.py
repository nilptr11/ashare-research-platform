from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_permission_note(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text or "", flags=re.IGNORECASE)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="把权限/积分报告合并进 interfaces.json")
    parser.add_argument("--interfaces", required=True, type=Path)
    parser.add_argument("--permissions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--checked-at", default=date.today().isoformat())
    args = parser.parse_args()

    payload = load_json(args.interfaces)
    permission_payload = load_json(args.permissions)
    permissions = {
        item["key"]: item
        for item in permission_payload.get("results", [])
    }

    for item in payload["interfaces"]:
        permission = permissions.get(item["key"], {})
        item["eligibility"] = permission.get("eligibility", item.get("eligibility", "unknown"))
        item["required_points"] = permission.get("required_points", item.get("required_points"))
        item.pop("current_points", None)
        item["permission_note"] = clean_permission_note(permission.get("requirement_text", item.get("permission_note", "")))
        item["permission_checked_at"] = args.checked_at

    payload["permission_source"] = str(args.permissions)
    payload["permission_checked_at"] = args.checked_at
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
