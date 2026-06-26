from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..core.paths import default_data_dir
from .schemas import EvidenceRecord, validate_evidence


@dataclass(frozen=True)
class EvidenceIngestResult:
    inserted: int
    skipped_duplicates: int
    evidence_ids: tuple[str, ...]
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.evidence_ingest_result.v1",
            "inserted": self.inserted,
            "skipped_duplicates": self.skipped_duplicates,
            "evidence_ids": list(self.evidence_ids),
            "path": self.path,
        }


class EvidenceStore:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.root = self.data_dir / "evidence"
        self.records_path = self.root / "records.jsonl"
        self.meta_path = self.root / "_meta.json"

    def ingest(self, records: list[EvidenceRecord] | list[dict[str, Any]]) -> EvidenceIngestResult:
        existing = {record.evidence_id for record in self.read_records() if record.evidence_id}
        inserted_ids: list[str] = []
        skipped = 0
        self.root.mkdir(parents=True, exist_ok=True)
        with self.records_path.open("a", encoding="utf-8") as file:
            for raw in records:
                record = raw if isinstance(raw, EvidenceRecord) else EvidenceRecord.from_dict(raw)
                normalized = validate_evidence(record)
                if normalized.evidence_id in existing:
                    skipped += 1
                    continue
                file.write(json.dumps(normalized.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
                existing.add(normalized.evidence_id)
                if normalized.evidence_id:
                    inserted_ids.append(normalized.evidence_id)
        self._write_meta(record_count=len(existing))
        return EvidenceIngestResult(
            inserted=len(inserted_ids),
            skipped_duplicates=skipped,
            evidence_ids=tuple(inserted_ids),
            path=str(self.records_path),
        )

    def read_records(self) -> list[EvidenceRecord]:
        if not self.records_path.exists():
            return []
        records: list[EvidenceRecord] = []
        with self.records_path.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    records.append(EvidenceRecord.from_dict(json.loads(line)))
        return records

    def search(
        self,
        *,
        topic: str | None = None,
        industry: str | None = None,
        company: str | None = None,
        product: str | None = None,
        metric: str | None = None,
        period: str | None = None,
        confidence: str | None = None,
        dataset_id: str | None = None,
        limit: int | None = None,
    ) -> list[EvidenceRecord]:
        records = [
            record
            for record in self.read_records()
            if _match(record.topic, topic)
            and _match(record.industry, industry)
            and _match(record.company, company)
            and _match(record.product, product)
            and _match(record.metric, metric)
            and _match(record.period, period)
            and _match(record.confidence, confidence)
            and _match(record.dataset_id, dataset_id)
        ]
        records.sort(key=lambda record: (record.source.published_at, record.evidence_id or ""), reverse=True)
        return records[:limit] if limit and limit > 0 else records

    def export_jsonl(self, output_path: Path | str, records: list[EvidenceRecord]) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def _write_meta(self, *, record_count: int) -> None:
        payload = {
            "schema": "rdf.evidence_store_meta.v1",
            "records": record_count,
            "records_path": str(self.records_path),
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        }
        self.meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _match(actual: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if actual is None:
        return False
    return expected.lower() in actual.lower()
