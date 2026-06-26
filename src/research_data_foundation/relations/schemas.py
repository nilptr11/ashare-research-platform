from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .taxonomy import ENTITY_TYPES, PREDICATES


class RelationError(ValueError):
    """Raised when a relation record is invalid."""


CONFIDENCE_VALUES = {"low", "medium", "high"}


@dataclass(frozen=True)
class EntityRef:
    entity_type: str
    entity_id: str
    name: str
    market_scope: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EntityRef":
        return cls(
            entity_type=str(payload["entity_type"]),
            entity_id=str(payload["entity_id"]),
            name=str(payload["name"]),
            market_scope=payload.get("market_scope"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "name": self.name,
            "market_scope": self.market_scope,
        }


@dataclass(frozen=True)
class RelationSource:
    evidence_id: str | None = None
    raw_ref: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    published_at: str | None = None
    query_time: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RelationSource":
        return cls(
            evidence_id=payload.get("evidence_id"),
            raw_ref=payload.get("raw_ref"),
            source_name=payload.get("source_name"),
            source_url=payload.get("source_url"),
            published_at=payload.get("published_at"),
            query_time=payload.get("query_time"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "raw_ref": self.raw_ref,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "published_at": self.published_at,
            "query_time": self.query_time,
        }


@dataclass(frozen=True)
class RelationRecord:
    subject: EntityRef
    predicate: str
    object: EntityRef
    confidence: str
    source: RelationSource
    relation_id: str | None = None
    claim: str | None = None
    market_scope: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    quality_flags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RelationRecord":
        normalized = dict(payload)
        normalized.pop("schema", None)
        if not isinstance(normalized.get("subject"), EntityRef):
            normalized["subject"] = EntityRef.from_dict(dict(normalized["subject"]))
        if not isinstance(normalized.get("object"), EntityRef):
            normalized["object"] = EntityRef.from_dict(dict(normalized["object"]))
        if not isinstance(normalized.get("source"), RelationSource):
            normalized["source"] = RelationSource.from_dict(dict(normalized["source"]))
        normalized["tags"] = tuple(str(item) for item in normalized.get("tags") or ())
        normalized["quality_flags"] = tuple(str(item) for item in normalized.get("quality_flags") or ())
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.relation_record.v1",
            "relation_id": self.relation_id,
            "subject": self.subject.to_dict(),
            "predicate": self.predicate,
            "object": self.object.to_dict(),
            "confidence": self.confidence,
            "claim": self.claim,
            "market_scope": self.market_scope,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "source": self.source.to_dict(),
            "tags": list(self.tags),
            "quality_flags": list(self.quality_flags),
        }

    def with_id(self) -> "RelationRecord":
        if self.relation_id:
            return self
        payload = self.to_dict()
        payload["relation_id"] = compute_relation_id(payload)
        return RelationRecord.from_dict(payload)


def validate_relation(record: RelationRecord) -> RelationRecord:
    if record.subject.entity_type not in ENTITY_TYPES:
        raise RelationError(f"invalid subject entity_type {record.subject.entity_type!r}")
    if record.object.entity_type not in ENTITY_TYPES:
        raise RelationError(f"invalid object entity_type {record.object.entity_type!r}")
    if not record.subject.entity_id:
        raise RelationError("subject.entity_id is required")
    if not record.object.entity_id:
        raise RelationError("object.entity_id is required")
    if not record.subject.name:
        raise RelationError("subject.name is required")
    if not record.object.name:
        raise RelationError("object.name is required")
    if record.predicate not in PREDICATES:
        raise RelationError(f"invalid predicate {record.predicate!r}")
    if record.confidence not in CONFIDENCE_VALUES:
        raise RelationError(f"invalid confidence {record.confidence!r}")
    if not (record.source.evidence_id or record.source.raw_ref or record.source.source_url):
        raise RelationError("source requires evidence_id, raw_ref, or source_url")
    if record.source.source_url and not (
        record.source.source_name and record.source.published_at and record.source.query_time
    ):
        raise RelationError("source_url requires source_name, published_at, and query_time")
    return record.with_id()


def compute_relation_id(payload: dict[str, Any]) -> str:
    source = dict(payload.get("source") or {})
    source.pop("query_time", None)
    source.pop("raw_ref", None)
    canonical = {
        "subject": payload.get("subject"),
        "predicate": payload.get("predicate"),
        "object": payload.get("object"),
        "source": source,
        "valid_from": payload.get("valid_from"),
        "claim": payload.get("claim"),
    }
    blob = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
