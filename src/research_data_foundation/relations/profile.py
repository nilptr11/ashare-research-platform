from __future__ import annotations

from collections import Counter
from typing import Any

from .schemas import EntityRef, RelationRecord
from .store import RelationStore, alias_index


class RelationProfiler:
    def __init__(self, store: RelationStore) -> None:
        self.store = store

    def profile(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        evidence_id: str | None = None,
        tag: str | None = None,
        confidence: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        records = self.store.search(
            subject=subject,
            predicate=predicate,
            object=object,
            evidence_id=evidence_id,
            tag=tag,
            confidence=confidence,
        )
        return relation_profile(
            records,
            filters={
                "subject": subject,
                "predicate": predicate,
                "object": object,
                "evidence_id": evidence_id,
                "tag": tag,
                "confidence": confidence,
            },
            limit=limit,
        )

    def neighborhood(
        self,
        *,
        entity: str,
        predicate: str | None = None,
        tag: str | None = None,
        confidence: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        records = [
            record
            for record in self.store.search(predicate=predicate, tag=tag, confidence=confidence)
            if _entity_match(record.subject, entity) or _entity_match(record.object, entity)
        ]
        records.sort(key=lambda record: (record.valid_from or "", record.relation_id or ""), reverse=True)
        limited = records[:limit] if limit and limit > 0 else records
        outgoing = [record for record in limited if _entity_match(record.subject, entity)]
        incoming = [record for record in limited if _entity_match(record.object, entity)]
        return {
            "schema": "rdf.relation_neighborhood.v1",
            "entity": entity,
            "filters": _clean_filters({"predicate": predicate, "tag": tag, "confidence": confidence, "limit": limit}),
            "records": len(limited),
            "total_matches": len(records),
            "incoming_count": len(incoming),
            "outgoing_count": len(outgoing),
            "entities": _matched_entities(records, entity),
            "outgoing": [relation_edge(record) for record in outgoing],
            "incoming": [relation_edge(record) for record in incoming],
            "alias_index": alias_index(limited),
        }


def relation_profile(records: list[RelationRecord], *, filters: dict[str, Any] | None = None, limit: int = 20) -> dict[str, Any]:
    bounded_limit = max(limit, 0)
    subject_types = Counter(record.subject.entity_type for record in records)
    object_types = Counter(record.object.entity_type for record in records)
    predicates = Counter(record.predicate for record in records)
    confidence = Counter(record.confidence for record in records)
    tags = Counter(tag for record in records for tag in record.tags)
    quality_flags = Counter(flag for record in records for flag in record.quality_flags)
    source_refs = Counter(_source_ref_type(record) for record in records)
    valid_from = sorted({record.valid_from for record in records if record.valid_from})
    entities = _unique_entities(records)
    return {
        "schema": "rdf.relation_profile.v1",
        "filters": _clean_filters(filters or {}),
        "records": len(records),
        "unique_counts": {
            "entities": len(entities),
            "subjects": len({record.subject.entity_id for record in records}),
            "objects": len({record.object.entity_id for record in records}),
            "predicates": len(predicates),
            "tags": len(tags),
        },
        "confidence": dict(sorted(confidence.items())),
        "valid_from_range": {"min": valid_from[0], "max": valid_from[-1]} if valid_from else None,
        "predicates": _counter_rows(predicates, "predicate", records, limit=bounded_limit),
        "subject_types": [{"entity_type": key, "records": count} for key, count in subject_types.most_common(bounded_limit or None)],
        "object_types": [{"entity_type": key, "records": count} for key, count in object_types.most_common(bounded_limit or None)],
        "source_refs": [{"source_ref": key, "records": count} for key, count in source_refs.most_common(bounded_limit or None)],
        "tags": [{"tag": key, "records": count} for key, count in tags.most_common(bounded_limit or None)],
        "quality_flags": [{"flag": key, "records": count} for key, count in quality_flags.most_common(bounded_limit or None)],
        "top_entities": _top_entities(records, limit=bounded_limit),
    }


def relation_edge(record: RelationRecord) -> dict[str, Any]:
    return {
        "relation_id": record.relation_id,
        "subject": record.subject.to_dict(),
        "predicate": record.predicate,
        "object": record.object.to_dict(),
        "confidence": record.confidence,
        "claim": record.claim,
        "market_scope": record.market_scope,
        "valid_from": record.valid_from,
        "valid_to": record.valid_to,
        "source": record.source.to_dict(),
        "tags": list(record.tags),
        "quality_flags": list(record.quality_flags),
    }


def _counter_rows(counter: Counter[str], key_name: str, records: list[RelationRecord], *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, count in counter.items():
        subset = [record for record in records if getattr(record, key_name) == key]
        confidence = Counter(record.confidence for record in subset)
        rows.append({key_name: key, "records": count, "confidence": dict(sorted(confidence.items()))})
    rows.sort(key=lambda row: (row["records"], row[key_name]), reverse=True)
    return rows[:limit] if limit and limit > 0 else rows


def _top_entities(records: list[RelationRecord], *, limit: int) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for record in records:
        counts[(record.subject.entity_type, record.subject.entity_id, record.subject.name)] += 1
        counts[(record.object.entity_type, record.object.entity_id, record.object.name)] += 1
    rows = [
        {"entity_type": entity_type, "entity_id": entity_id, "name": name, "records": count}
        for (entity_type, entity_id, name), count in counts.items()
    ]
    rows.sort(key=lambda row: (row["records"], row["entity_id"]), reverse=True)
    return rows[:limit] if limit and limit > 0 else rows


def _unique_entities(records: list[RelationRecord]) -> set[tuple[str, str]]:
    entities: set[tuple[str, str]] = set()
    for record in records:
        entities.add((record.subject.entity_type, record.subject.entity_id))
        entities.add((record.object.entity_type, record.object.entity_id))
    return entities


def _matched_entities(records: list[RelationRecord], entity: str) -> list[dict[str, str | None]]:
    matches: list[dict[str, str | None]] = []
    for record in records:
        for ref in (record.subject, record.object):
            if _entity_match(ref, entity):
                payload = ref.to_dict()
                if payload not in matches:
                    matches.append(payload)
    return matches


def _entity_match(ref: EntityRef, expected: str) -> bool:
    needle = expected.lower()
    return needle in ref.entity_id.lower() or needle in ref.name.lower()


def _source_ref_type(record: RelationRecord) -> str:
    if record.source.evidence_id:
        return "evidence_id"
    if record.source.raw_ref:
        return "raw_ref"
    if record.source.source_url:
        return "source_url"
    return "unknown"


def _clean_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in filters.items() if value not in {None, ""}}
