from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from ...schemas import AShareResearchError


class EvidenceAdapterError(AShareResearchError):
    """Raised when evidence adapter specs are invalid."""


@dataclass(frozen=True)
class EvidenceAdapterSpec:
    adapter_id: str
    status: str
    source_type: str
    source_name: str
    topic: str
    industry: str
    metric: str
    frequency: str
    connector: str
    api_name: str
    params_template: dict[str, Any] = field(default_factory=dict)
    field_mapping: dict[str, str] = field(default_factory=dict)
    claim_template: str = ""
    evidence_ids: tuple[str, ...] = ()
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceAdapterSpec":
        normalized = dict(payload)
        normalized.pop("schema", None)
        return cls(
            adapter_id=str(normalized["adapter_id"]),
            status=str(normalized.get("status", "proposed")),
            source_type=str(normalized["source_type"]),
            source_name=str(normalized["source_name"]),
            topic=str(normalized["topic"]),
            industry=str(normalized["industry"]),
            metric=str(normalized["metric"]),
            frequency=str(normalized.get("frequency", "")),
            connector=str(normalized.get("connector", "")),
            api_name=str(normalized.get("api_name", "")),
            params_template=dict(normalized.get("params_template") or {}),
            field_mapping={str(key): str(value) for key, value in (normalized.get("field_mapping") or {}).items()},
            claim_template=str(normalized.get("claim_template", "")),
            evidence_ids=tuple(str(item) for item in normalized.get("evidence_ids") or ()),
            notes=str(normalized.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ashare.evidence_adapter_spec.v1",
            "adapter_id": self.adapter_id,
            "status": self.status,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "topic": self.topic,
            "industry": self.industry,
            "metric": self.metric,
            "frequency": self.frequency,
            "connector": self.connector,
            "api_name": self.api_name,
            "params_template": dict(self.params_template),
            "field_mapping": dict(self.field_mapping),
            "claim_template": self.claim_template,
            "evidence_ids": list(self.evidence_ids),
            "notes": self.notes,
        }


def validate_adapter_spec(spec: EvidenceAdapterSpec) -> EvidenceAdapterSpec:
    if not spec.adapter_id:
        raise EvidenceAdapterError("adapter_id is required")
    if spec.status not in {"proposed", "accepted", "retired"}:
        raise EvidenceAdapterError(f"{spec.adapter_id}: invalid status {spec.status!r}")
    for field_name in ("source_type", "source_name", "topic", "industry", "metric"):
        if not getattr(spec, field_name):
            raise EvidenceAdapterError(f"{spec.adapter_id}: {field_name} is required")
    if spec.status == "accepted":
        if not spec.connector:
            raise EvidenceAdapterError(f"{spec.adapter_id}: connector is required for accepted adapter")
        if not spec.api_name:
            raise EvidenceAdapterError(f"{spec.adapter_id}: api_name is required for accepted adapter")
        for field_name in ("claim", "source_url", "published_at", "query_time", "value", "unit", "period"):
            if field_name not in spec.field_mapping:
                raise EvidenceAdapterError(f"{spec.adapter_id}: field_mapping.{field_name} is required")
    return spec


def adapter_id_for(payload: dict[str, Any]) -> str:
    parts = [
        str(payload.get("source_type") or ""),
        str(payload.get("source_name") or ""),
        str(payload.get("topic") or ""),
        str(payload.get("industry") or ""),
        str(payload.get("metric") or ""),
        str(payload.get("frequency") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def spec_from_candidate(candidate: dict[str, Any]) -> EvidenceAdapterSpec:
    payload = dict(candidate)
    adapter_id = f"adapter:{adapter_id_for(payload)}"
    return validate_adapter_spec(
        EvidenceAdapterSpec(
            adapter_id=adapter_id,
            status="proposed",
            source_type=str(payload["source_type"]),
            source_name=str(payload["source_name"]),
            topic=str(payload["topic"]),
            industry=str(payload["industry"]),
            metric=str(payload["metric"]),
            frequency=str(payload.get("frequency", "")),
            connector="",
            api_name="",
            params_template={},
            field_mapping={},
            claim_template="",
            evidence_ids=tuple(str(item) for item in payload.get("evidence_ids") or ()),
            notes=json.dumps(
                {
                    "records": payload.get("records"),
                    "periods": payload.get("periods", []),
                    "needs_adapter_count": payload.get("needs_adapter_count", 0),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    )
