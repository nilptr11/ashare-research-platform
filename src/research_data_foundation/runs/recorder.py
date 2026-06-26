from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..core.paths import default_data_dir
from .quality_gates import evaluate_quality_gates
from .schemas import RunRecord, RunRecordError, validate_run_record


class RunRecorder:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.root = self.data_dir / "runs"

    def record(
        self,
        *,
        question: str,
        as_of: str,
        mart_refs: list[str] | tuple[str, ...] = (),
        feature_refs: list[str] | tuple[str, ...] = (),
        evidence_ids: list[str] | tuple[str, ...] = (),
        relation_ids: list[str] | tuple[str, ...] = (),
        model_output_file: str | None = None,
        validated_output_file: str | None = None,
        run_id: str | None = None,
        notes: str = "",
    ) -> RunRecord:
        created_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
        resolved_run_id = run_id or make_run_id(question=question, as_of=as_of, created_at=created_at)
        model_output = file_ref(model_output_file)
        validated_output = load_json_file(validated_output_file) if validated_output_file else {}
        quality = evaluate_quality_gates(
            data_dir=self.data_dir,
            as_of=as_of,
            mart_refs=tuple(mart_refs),
            feature_refs=tuple(feature_refs),
            evidence_ids=tuple(evidence_ids),
            relation_ids=tuple(relation_ids),
            validated_output=validated_output,
        )
        record = validate_run_record(
            RunRecord(
                run_id=resolved_run_id,
                question=question,
                as_of=as_of,
                created_at=created_at,
                mart_refs=tuple(mart_refs),
                feature_refs=tuple(feature_refs),
                evidence_ids=tuple(evidence_ids),
                relation_ids=tuple(relation_ids),
                model_output=model_output,
                validated_output=validated_output,
                quality=quality,
                notes=notes,
            )
        )
        path = self.run_path(record.run_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "manifest.json").write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        if validated_output:
            (path / "validated_output.json").write_text(
                json.dumps(validated_output, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return record

    def read(self, run_id: str) -> RunRecord:
        path = self.run_path(run_id) / "manifest.json"
        if not path.exists():
            raise RunRecordError(f"missing run manifest: {path}")
        return RunRecord.from_file(path)

    def run_path(self, run_id: str) -> Path:
        return self.root / run_id


def replay_run(run_id: str, *, data_dir: Path | str | None = None) -> dict[str, Any]:
    record = RunRecorder(data_dir).read(run_id)
    return {
        "schema": "rdf.run_replay.v1",
        "run_id": record.run_id,
        "question": record.question,
        "as_of": record.as_of,
        "refs": {
            "mart_refs": list(record.mart_refs),
            "feature_refs": list(record.feature_refs),
            "evidence_ids": list(record.evidence_ids),
            "relation_ids": list(record.relation_ids),
        },
        "quality": dict(record.quality),
    }


def file_ref(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    source = Path(path)
    if not source.exists():
        raise RunRecordError(f"model output file not found: {source}")
    content = source.read_bytes()
    return {
        "path": str(source),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def load_json_file(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    source = Path(path)
    if not source.exists():
        raise RunRecordError(f"validated output file not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RunRecordError("validated output must be a JSON object")
    return payload


def make_run_id(*, question: str, as_of: str, created_at: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", question.lower()).strip("-")[:32] or "run"
    digest = hashlib.sha256(f"{question}|{as_of}|{created_at}".encode("utf-8")).hexdigest()[:8]
    return f"{as_of}-{slug}-{digest}"
