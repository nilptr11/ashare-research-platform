from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..schemas import AShareResearchError


class KnowledgeError(AShareResearchError):
    """Raised when knowledge records are invalid or cannot be stored."""


CONFIDENCE_VALUES = {"low", "medium", "high"}
PROPOSAL_STATUS_VALUES = {"proposed", "accepted", "rejected"}


@dataclass(frozen=True)
class KnowledgeEntityRef:
    type: str
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeEntityRef":
        aliases = payload.get("aliases") or ()
        return cls(
            type=str(payload["type"]),
            id=str(payload["id"]),
            name=str(payload["name"]),
            aliases=tuple(str(alias) for alias in aliases),
            attributes=dict(payload.get("attributes") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "aliases": list(self.aliases),
            "attributes": dict(self.attributes),
        }

    def searchable_terms(self) -> tuple[str, ...]:
        return (self.type, self.id, self.name, *self.aliases)


@dataclass(frozen=True)
class KnowledgeSource:
    source_type: str
    source_url: str | None = None
    evidence_id: str | None = None
    source_name: str | None = None
    published_at: str | None = None
    query_time: str | None = None
    raw_ref: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeSource":
        return cls(
            source_type=str(payload["source_type"]),
            source_url=_optional_str(payload.get("source_url")),
            evidence_id=_optional_str(payload.get("evidence_id")),
            source_name=_optional_str(payload.get("source_name")),
            published_at=_optional_str(payload.get("published_at")),
            query_time=_optional_str(payload.get("query_time")),
            raw_ref=_optional_str(payload.get("raw_ref")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_url": self.source_url,
            "evidence_id": self.evidence_id,
            "source_name": self.source_name,
            "published_at": self.published_at,
            "query_time": self.query_time,
            "raw_ref": self.raw_ref,
        }


@dataclass(frozen=True)
class KnowledgeRecord:
    id: str
    subject: KnowledgeEntityRef
    predicate: str
    object_ref: KnowledgeEntityRef
    confidence: str
    source: KnowledgeSource
    valid_from: str
    valid_to: str | None = None
    updated_at: str | None = None
    tags: tuple[str, ...] = ()
    note: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeRecord":
        normalized = dict(payload)
        normalized.pop("schema", None)
        return cls(
            id=str(normalized["id"]),
            subject=KnowledgeEntityRef.from_dict(dict(normalized["subject"])),
            predicate=str(normalized["predicate"]),
            object_ref=KnowledgeEntityRef.from_dict(dict(normalized["object"])),
            confidence=str(normalized["confidence"]),
            source=KnowledgeSource.from_dict(dict(normalized["source"])),
            valid_from=str(normalized["valid_from"]),
            valid_to=_optional_str(normalized.get("valid_to")),
            updated_at=_optional_str(normalized.get("updated_at")) or _now_iso(),
            tags=tuple(str(tag) for tag in normalized.get("tags") or ()),
            note=_optional_str(normalized.get("note")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ashare.knowledge_record.v1",
            "id": self.id,
            "subject": self.subject.to_dict(),
            "predicate": self.predicate,
            "object": self.object_ref.to_dict(),
            "confidence": self.confidence,
            "source": self.source.to_dict(),
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "updated_at": self.updated_at,
            "tags": list(self.tags),
            "note": self.note,
        }


@dataclass(frozen=True)
class KnowledgeProposal:
    proposal_id: str
    record: KnowledgeRecord
    proposed_by: str
    proposed_at: str
    reason: str | None = None
    status: str = "proposed"
    decided_by: str | None = None
    decided_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeProposal":
        normalized = dict(payload)
        normalized.pop("schema", None)
        return cls(
            proposal_id=str(normalized["proposal_id"]),
            record=KnowledgeRecord.from_dict(dict(normalized["record"])),
            proposed_by=str(normalized["proposed_by"]),
            proposed_at=str(normalized["proposed_at"]),
            reason=_optional_str(normalized.get("reason")),
            status=str(normalized.get("status", "proposed")),
            decided_by=_optional_str(normalized.get("decided_by")),
            decided_at=_optional_str(normalized.get("decided_at")),
        )

    def with_decision(self, decision: "KnowledgeDecision") -> "KnowledgeProposal":
        return KnowledgeProposal(
            proposal_id=self.proposal_id,
            record=self.record,
            proposed_by=self.proposed_by,
            proposed_at=self.proposed_at,
            reason=self.reason,
            status=decision.status,
            decided_by=decision.decided_by,
            decided_at=decision.decided_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ashare.knowledge_proposal.v1",
            "proposal_id": self.proposal_id,
            "status": self.status,
            "record": self.record.to_dict(),
            "proposed_by": self.proposed_by,
            "proposed_at": self.proposed_at,
            "reason": self.reason,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
        }


@dataclass(frozen=True)
class KnowledgeDecision:
    proposal_id: str
    record_id: str
    status: str
    decided_by: str
    decided_at: str
    reason: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeDecision":
        normalized = dict(payload)
        normalized.pop("schema", None)
        return cls(
            proposal_id=str(normalized["proposal_id"]),
            record_id=str(normalized["record_id"]),
            status=str(normalized["status"]),
            decided_by=str(normalized["decided_by"]),
            decided_at=str(normalized["decided_at"]),
            reason=_optional_str(normalized.get("reason")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ashare.knowledge_decision.v1",
            "proposal_id": self.proposal_id,
            "record_id": self.record_id,
            "status": self.status,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason,
        }


def validate_knowledge_record(record: KnowledgeRecord) -> KnowledgeRecord:
    if not record.id:
        raise KnowledgeError("KnowledgeRecord.id is required")
    if not record.predicate:
        raise KnowledgeError(f"{record.id}: predicate is required")
    if record.confidence not in CONFIDENCE_VALUES:
        raise KnowledgeError(f"{record.id}: invalid confidence {record.confidence!r}")
    _validate_entity(record.id, "subject", record.subject)
    _validate_entity(record.id, "object", record.object_ref)
    _validate_source(record)
    if not record.valid_from:
        raise KnowledgeError(f"{record.id}: valid_from is required")
    return record


def validate_proposal(proposal: KnowledgeProposal) -> KnowledgeProposal:
    if not proposal.proposal_id:
        raise KnowledgeError("proposal_id is required")
    if proposal.status not in PROPOSAL_STATUS_VALUES:
        raise KnowledgeError(f"{proposal.proposal_id}: invalid proposal status {proposal.status!r}")
    if not proposal.proposed_by:
        raise KnowledgeError(f"{proposal.proposal_id}: proposed_by is required")
    validate_knowledge_record(proposal.record)
    return proposal


def compute_proposal_id(record: KnowledgeRecord, proposed_at: str, proposed_by: str) -> str:
    payload = {
        "record": record.to_dict(),
        "proposed_at": proposed_at,
        "proposed_by": proposed_by,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def records_digest(records: list[KnowledgeRecord]) -> str:
    payload = [record.to_dict() for record in sorted(records, key=lambda item: item.id)]
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_entity(record_id: str, role: str, entity: KnowledgeEntityRef) -> None:
    if not entity.type or not entity.id or not entity.name:
        raise KnowledgeError(f"{record_id}: {role} requires type/id/name")


def _validate_source(record: KnowledgeRecord) -> None:
    source = record.source
    if not source.source_type:
        raise KnowledgeError(f"{record.id}: source.source_type is required")
    if not source.source_url and not source.evidence_id:
        raise KnowledgeError(f"{record.id}: source requires source_url or evidence_id")
    if source.source_url and not source.published_at:
        raise KnowledgeError(f"{record.id}: source.published_at is required when source_url is provided")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
