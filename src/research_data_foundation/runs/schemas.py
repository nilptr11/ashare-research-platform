from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class RunRecordError(ValueError):
    """Raised when a run record is invalid or missing."""


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    question: str
    as_of: str
    created_at: str
    mart_refs: tuple[str, ...] = ()
    feature_refs: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    relation_ids: tuple[str, ...] = ()
    model_output: dict[str, Any] = field(default_factory=dict)
    validated_output: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRecord":
        normalized = dict(payload)
        normalized.pop("schema", None)
        for key in ("mart_refs", "feature_refs", "evidence_ids", "relation_ids"):
            normalized[key] = tuple(str(item) for item in normalized.get(key) or ())
        normalized["model_output"] = dict(normalized.get("model_output") or {})
        normalized["validated_output"] = dict(normalized.get("validated_output") or {})
        normalized["quality"] = dict(normalized.get("quality") or {})
        return cls(**normalized)

    @classmethod
    def from_file(cls, path: Path) -> "RunRecord":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.run_record.v1",
            "run_id": self.run_id,
            "question": self.question,
            "as_of": self.as_of,
            "created_at": self.created_at,
            "mart_refs": list(self.mart_refs),
            "feature_refs": list(self.feature_refs),
            "evidence_ids": list(self.evidence_ids),
            "relation_ids": list(self.relation_ids),
            "model_output": dict(self.model_output),
            "validated_output": dict(self.validated_output),
            "quality": dict(self.quality),
            "notes": self.notes,
        }


def validate_run_record(record: RunRecord) -> RunRecord:
    if not record.run_id:
        raise RunRecordError("run_id is required")
    if not record.question:
        raise RunRecordError("question is required")
    if not record.as_of:
        raise RunRecordError("as_of is required")
    return record
