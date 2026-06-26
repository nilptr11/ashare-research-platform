from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class EvidenceError(ValueError):
    """Raised when an evidence record is invalid."""


CONFIDENCE_VALUES = {"low", "medium", "high"}
SOURCE_TYPES = {
    "regulator",
    "exchange",
    "company_filing",
    "company_ir",
    "official",
    "official_platform",
    "industry_association",
    "gov_policy",
    "price_index",
    "tender_platform",
    "vendor",
    "media",
    "research_report",
    "other",
}
MATURITY_VALUES = {"fetched", "curated", "inferred"}


@dataclass(frozen=True)
class EvidenceSourceRef:
    source_type: str
    source_name: str
    source_url: str
    published_at: str
    query_time: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceSourceRef":
        return cls(
            source_type=str(payload["source_type"]),
            source_name=str(payload["source_name"]),
            source_url=str(payload["source_url"]),
            published_at=str(payload["published_at"]),
            query_time=str(payload["query_time"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "published_at": self.published_at,
            "query_time": self.query_time,
        }


@dataclass(frozen=True)
class EvidenceRecord:
    claim: str
    topic: str
    source: EvidenceSourceRef
    confidence: str
    verification: str
    evidence_id: str | None = None
    dataset_id: str | None = None
    row_ref: str | None = None
    market_scope: str | None = None
    industry: str | None = None
    company: str | None = None
    product: str | None = None
    metric: str | None = None
    value: Any = None
    unit: str | None = None
    period: str | None = None
    supports: tuple[str, ...] = ()
    maturity: str = "fetched"
    quality_flags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceRecord":
        normalized = dict(payload)
        normalized.pop("schema", None)
        source = normalized.get("source")
        if not isinstance(source, EvidenceSourceRef):
            normalized["source"] = EvidenceSourceRef.from_dict(dict(source))
        normalized["supports"] = tuple(str(item) for item in normalized.get("supports") or ())
        normalized["quality_flags"] = tuple(str(item) for item in normalized.get("quality_flags") or ())
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.evidence_record.v1",
            "evidence_id": self.evidence_id,
            "claim": self.claim,
            "topic": self.topic,
            "dataset_id": self.dataset_id,
            "row_ref": self.row_ref,
            "market_scope": self.market_scope,
            "industry": self.industry,
            "company": self.company,
            "product": self.product,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "period": self.period,
            "source": self.source.to_dict(),
            "confidence": self.confidence,
            "verification": self.verification,
            "supports": list(self.supports),
            "maturity": self.maturity,
            "quality_flags": list(self.quality_flags),
        }

    def with_id(self) -> "EvidenceRecord":
        if self.evidence_id:
            return self
        payload = self.to_dict()
        payload["evidence_id"] = compute_evidence_id(payload)
        return EvidenceRecord.from_dict(payload)


def validate_evidence(record: EvidenceRecord) -> EvidenceRecord:
    if not record.claim:
        raise EvidenceError("claim is required")
    if not record.topic:
        raise EvidenceError("topic is required")
    if record.confidence not in CONFIDENCE_VALUES:
        raise EvidenceError(f"invalid confidence {record.confidence!r}")
    if record.source.source_type not in SOURCE_TYPES:
        raise EvidenceError(f"invalid source_type {record.source.source_type!r}")
    if record.maturity not in MATURITY_VALUES:
        raise EvidenceError(f"invalid maturity {record.maturity!r}")
    for field_name, value in record.source.to_dict().items():
        if not value:
            raise EvidenceError(f"source.{field_name} is required")
    return record.with_id()


def compute_evidence_id(payload: dict[str, Any]) -> str:
    source = dict(payload.get("source") or {})
    source.pop("query_time", None)
    canonical = {
        "claim": payload.get("claim"),
        "topic": payload.get("topic"),
        "source": source,
        "metric": payload.get("metric"),
        "period": payload.get("period"),
        "value": payload.get("value"),
    }
    blob = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
