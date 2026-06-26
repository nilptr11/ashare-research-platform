from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .schemas import EvidenceRecord
from .store import EvidenceStore


class EvidenceProfiler:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def profile(
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
        limit: int = 20,
    ) -> dict[str, Any]:
        records = self.store.search(
            topic=topic,
            industry=industry,
            company=company,
            product=product,
            metric=metric,
            period=period,
            confidence=confidence,
            dataset_id=dataset_id,
        )
        return evidence_profile(
            records,
            filters={
                "topic": topic,
                "industry": industry,
                "company": company,
                "product": product,
                "metric": metric,
                "period": period,
                "confidence": confidence,
                "dataset_id": dataset_id,
            },
            limit=limit,
        )

    def source_candidates(
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
        min_records: int = 3,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        records = self.store.search(
            topic=topic,
            industry=industry,
            company=company,
            product=product,
            metric=metric,
            period=period,
            confidence=confidence,
            dataset_id=dataset_id,
        )
        return evidence_source_candidates(records, min_records=min_records, limit=limit)


def evidence_profile(records: list[EvidenceRecord], *, filters: dict[str, Any] | None = None, limit: int = 20) -> dict[str, Any]:
    bounded_limit = max(limit, 0)
    topics = _group(records, lambda record: record.topic)
    sources = _group(records, lambda record: f"{record.source.source_type}:{record.source.source_name}")
    datasets = _group(records, lambda record: record.dataset_id or "")
    industries = _group(records, lambda record: record.industry or "")
    companies = _group(records, lambda record: record.company or "")
    metrics = _group(records, lambda record: record.metric or "")
    quality_flags = Counter(flag for record in records for flag in record.quality_flags)
    confidence_counts = Counter(record.confidence for record in records)
    periods = sorted({str(record.period) for record in records if record.period})
    published = sorted({record.source.published_at for record in records if record.source.published_at})
    return {
        "schema": "rdf.evidence_profile.v1",
        "filters": _clean_filters(filters or {}),
        "records": len(records),
        "unique_counts": {
            "topics": _non_empty_count(topics),
            "sources": _non_empty_count(sources),
            "datasets": _non_empty_count(datasets),
            "industries": _non_empty_count(industries),
            "companies": _non_empty_count(companies),
            "metrics": _non_empty_count(metrics),
        },
        "confidence": dict(sorted(confidence_counts.items())),
        "period_range": {"min": periods[0], "max": periods[-1]} if periods else None,
        "latest_published_at": published[-1] if published else "",
        "topics": _group_rows(topics, key_name="topic", limit=bounded_limit),
        "sources": _source_rows(records, limit=bounded_limit),
        "datasets": _group_rows(datasets, key_name="dataset_id", limit=bounded_limit),
        "industries": _group_rows(industries, key_name="industry", limit=bounded_limit),
        "companies": _group_rows(companies, key_name="company", limit=bounded_limit),
        "metrics": _group_rows(metrics, key_name="metric", limit=bounded_limit),
        "quality_flags": [
            {"flag": flag, "records": count}
            for flag, count in quality_flags.most_common(bounded_limit or None)
        ],
    }


def evidence_source_candidates(records: list[EvidenceRecord], *, min_records: int = 3, limit: int = 50) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str, str, str], list[EvidenceRecord]] = defaultdict(list)
    for record in records:
        if not _is_numerical_candidate_record(record):
            continue
        key = (
            record.source.source_type,
            record.source.source_name,
            record.topic,
            record.market_scope or "",
            record.industry or "",
            record.metric or "",
            record.unit or "",
        )
        groups[key].append(record)

    candidates: list[dict[str, Any]] = []
    for key, grouped in groups.items():
        if len(grouped) < min_records:
            continue
        source_type, source_name, topic, market_scope, industry, metric, unit = key
        periods = sorted({str(record.period) for record in grouped if record.period})
        published = sorted({record.source.published_at for record in grouped if record.source.published_at})
        evidence_ids = [record.evidence_id for record in grouped if record.evidence_id]
        source_urls = sorted({record.source.source_url for record in grouped if record.source.source_url})
        supports = sorted({support for record in grouped for support in record.supports})
        confidence_counts = Counter(record.confidence for record in grouped)
        candidates.append(
            {
                "schema": "rdf.evidence_source_candidate.v1",
                "source_type": source_type,
                "source_name": source_name,
                "topic": topic,
                "market_scope": market_scope or None,
                "industry": industry or None,
                "metric": metric,
                "unit": unit or None,
                "records": len(grouped),
                "periods": periods,
                "period_count": len(periods),
                "latest_published_at": published[-1] if published else "",
                "source_urls": source_urls[:5],
                "confidence": dict(sorted(confidence_counts.items())),
                "supports": supports,
                "sample_claim": grouped[0].claim,
                "evidence_ids": evidence_ids[:20],
                "evidence_ids_total": len(evidence_ids),
            }
        )
    candidates.sort(key=lambda row: (row["records"], row["period_count"], row["latest_published_at"]), reverse=True)
    return candidates[:limit] if limit and limit > 0 else candidates


def _group(records: list[EvidenceRecord], key_func) -> dict[str, list[EvidenceRecord]]:
    groups: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for record in records:
        groups[str(key_func(record) or "")].append(record)
    return groups


def _group_rows(groups: dict[str, list[EvidenceRecord]], *, key_name: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, records in groups.items():
        if not key:
            continue
        published = sorted({record.source.published_at for record in records if record.source.published_at})
        rows.append(
            {
                key_name: key,
                "records": len(records),
                "confidence": dict(sorted(Counter(record.confidence for record in records).items())),
                "latest_published_at": published[-1] if published else "",
            }
        )
    rows.sort(key=lambda row: (row["records"], row["latest_published_at"], str(row[key_name])), reverse=True)
    return rows[:limit] if limit and limit > 0 else rows


def _source_rows(records: list[EvidenceRecord], *, limit: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[EvidenceRecord]] = defaultdict(list)
    for record in records:
        groups[(record.source.source_type, record.source.source_name)].append(record)
    rows: list[dict[str, Any]] = []
    for (source_type, source_name), grouped in groups.items():
        published = sorted({record.source.published_at for record in grouped if record.source.published_at})
        urls = sorted({record.source.source_url for record in grouped if record.source.source_url})
        rows.append(
            {
                "source_type": source_type,
                "source_name": source_name,
                "records": len(grouped),
                "confidence": dict(sorted(Counter(record.confidence for record in grouped).items())),
                "latest_published_at": published[-1] if published else "",
                "source_urls": urls[:3],
            }
        )
    rows.sort(key=lambda row: (row["records"], row["latest_published_at"], row["source_name"]), reverse=True)
    return rows[:limit] if limit and limit > 0 else rows


def _non_empty_count(groups: dict[str, list[EvidenceRecord]]) -> int:
    return sum(1 for key in groups if key)


def _clean_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in filters.items() if value not in {None, ""}}


def _is_numerical_candidate_record(record: EvidenceRecord) -> bool:
    return bool(record.metric and record.period and record.value is not None and not record.dataset_id)
