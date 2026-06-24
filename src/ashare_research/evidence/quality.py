from __future__ import annotations

from typing import Any

from .schemas import ALLOWED_SOURCE_TYPES, CONFIDENCE_VALUES, MATURITY_VALUES, EvidenceError, EvidenceRecord


REQUIRED_FIELDS = (
    "claim",
    "topic",
    "industry",
    "source_type",
    "source_name",
    "source_url",
    "published_at",
    "query_time",
    "confidence",
    "verification",
)


def validate_evidence(payload: dict[str, Any]) -> EvidenceRecord:
    missing = [field for field in REQUIRED_FIELDS if not payload.get(field)]
    if missing:
        raise EvidenceError(f"Evidence missing required fields: {', '.join(missing)}")

    confidence = str(payload["confidence"])
    if confidence not in CONFIDENCE_VALUES:
        raise EvidenceError(f"Invalid confidence {confidence!r}; expected one of {sorted(CONFIDENCE_VALUES)}")
    maturity = str(payload.get("maturity", "curated"))
    if maturity not in MATURITY_VALUES:
        raise EvidenceError(f"Invalid maturity {maturity!r}; expected one of {sorted(MATURITY_VALUES)}")
    payload["maturity"] = maturity

    numerical_fields = ("metric", "value", "unit", "period")
    has_numerical_hint = any(payload.get(field) is not None for field in numerical_fields)
    if has_numerical_hint:
        missing_numerical = [field for field in numerical_fields if payload.get(field) is None or payload.get(field) == ""]
        if missing_numerical:
            raise EvidenceError(f"Numerical evidence missing fields: {', '.join(missing_numerical)}")

    source_type = str(payload["source_type"])
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise EvidenceError(f"Invalid source_type {source_type!r}; expected one of {sorted(ALLOWED_SOURCE_TYPES)}")
    quality_flags = list(payload.get("quality_flags") or [])

    record = EvidenceRecord.from_dict(payload)
    if quality_flags:
        record = EvidenceRecord.from_dict(record.to_dict() | {"quality_flags": quality_flags})
    return record
