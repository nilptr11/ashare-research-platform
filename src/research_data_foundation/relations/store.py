from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..core.paths import default_data_dir
from .schemas import RelationRecord, validate_relation


@dataclass(frozen=True)
class RelationIngestResult:
    inserted: int
    skipped_duplicates: int
    relation_ids: tuple[str, ...]
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.relation_ingest_result.v1",
            "inserted": self.inserted,
            "skipped_duplicates": self.skipped_duplicates,
            "relation_ids": list(self.relation_ids),
            "path": self.path,
        }


class RelationStore:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.root = self.data_dir / "relations"
        self.records_path = self.root / "records.jsonl"
        self.meta_path = self.root / "_meta.json"

    def ingest(self, records: list[RelationRecord] | list[dict[str, Any]]) -> RelationIngestResult:
        existing = {record.relation_id for record in self.read_records() if record.relation_id}
        inserted_ids: list[str] = []
        skipped = 0
        self.root.mkdir(parents=True, exist_ok=True)
        with self.records_path.open("a", encoding="utf-8") as file:
            for raw in records:
                record = raw if isinstance(raw, RelationRecord) else RelationRecord.from_dict(raw)
                normalized = validate_relation(record)
                if normalized.relation_id in existing:
                    skipped += 1
                    continue
                file.write(json.dumps(normalized.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
                existing.add(normalized.relation_id)
                if normalized.relation_id:
                    inserted_ids.append(normalized.relation_id)
        self._write_meta(record_count=len(existing))
        return RelationIngestResult(
            inserted=len(inserted_ids),
            skipped_duplicates=skipped,
            relation_ids=tuple(inserted_ids),
            path=str(self.records_path),
        )

    def read_records(self) -> list[RelationRecord]:
        if not self.records_path.exists():
            return []
        records: list[RelationRecord] = []
        with self.records_path.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    records.append(RelationRecord.from_dict(json.loads(line)))
        return records

    def search(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        evidence_id: str | None = None,
        tag: str | None = None,
        confidence: str | None = None,
        limit: int | None = None,
    ) -> list[RelationRecord]:
        records = [
            record
            for record in self.read_records()
            if _entity_match(record.subject, subject)
            and _match(record.predicate, predicate)
            and _entity_match(record.object, object)
            and _match(record.source.evidence_id, evidence_id)
            and (not tag or tag in record.tags)
            and _match(record.confidence, confidence)
        ]
        records.sort(key=lambda record: (record.valid_from or "", record.relation_id or ""), reverse=True)
        return records[:limit] if limit and limit > 0 else records

    def snapshot(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        evidence_id: str | None = None,
        tag: str | None = None,
        confidence: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        records = self.search(
            subject=subject,
            predicate=predicate,
            object=object,
            evidence_id=evidence_id,
            tag=tag,
            confidence=confidence,
            limit=limit,
        )
        return {
            "schema": "rdf.relation_snapshot.v1",
            "filters": {
                "subject": subject,
                "predicate": predicate,
                "object": object,
                "evidence_id": evidence_id,
                "tag": tag,
                "confidence": confidence,
                "limit": limit,
            },
            "records": [record.to_dict() for record in records],
            "record_count": len(records),
            "alias_index": alias_index(records),
        }

    def _write_meta(self, *, record_count: int) -> None:
        payload = {
            "schema": "rdf.relation_store_meta.v1",
            "records": record_count,
            "records_path": str(self.records_path),
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        }
        self.meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _entity_match(entity: Any, expected: str | None) -> bool:
    if not expected:
        return True
    return _match(entity.entity_id, expected) or _match(entity.name, expected)


def _match(actual: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if actual is None:
        return False
    return expected.lower() in actual.lower()


def alias_index(records: list[RelationRecord]) -> dict[str, list[dict[str, str | None]]]:
    index: dict[str, list[dict[str, str | None]]] = {}
    for record in records:
        for entity in (record.subject, record.object):
            payload = {
                "entity_type": entity.entity_type,
                "entity_id": entity.entity_id,
                "name": entity.name,
                "market_scope": entity.market_scope,
            }
            terms = {entity.entity_id, entity.name}
            if ":" in entity.entity_id:
                terms.add(entity.entity_id.rsplit(":", 1)[-1])
            for term in terms:
                if not term:
                    continue
                key = term.lower()
                bucket = index.setdefault(key, [])
                if payload not in bucket:
                    bucket.append(payload)
    return index
