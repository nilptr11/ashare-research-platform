from __future__ import annotations

from .schemas import OFFICIAL_SOURCE_TYPES, EvidenceRecord


def score_confidence(record: EvidenceRecord) -> float:
    base = {"high": 0.85, "medium": 0.6, "low": 0.35}[record.confidence]
    if record.source_type in OFFICIAL_SOURCE_TYPES:
        base += 0.1
    if "cross" in record.verification or "multi" in record.verification:
        base += 0.05
    return round(max(0.0, min(base, 0.98)), 4)
