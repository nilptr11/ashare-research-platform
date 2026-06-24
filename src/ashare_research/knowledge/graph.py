from __future__ import annotations

from .schemas import KnowledgeRecord


def build_edge_list(records: list[KnowledgeRecord]) -> list[dict[str, str]]:
    return [
        {
            "subject_type": record.subject.type,
            "subject_id": record.subject.id,
            "subject_name": record.subject.name,
            "predicate": record.predicate,
            "object_type": record.object_ref.type,
            "object_id": record.object_ref.id,
            "object_name": record.object_ref.name,
            "record_id": record.id,
            "confidence": record.confidence,
        }
        for record in records
    ]


def outgoing(records: list[KnowledgeRecord], entity_id: str) -> list[dict[str, str]]:
    return [edge for edge in build_edge_list(records) if edge["subject_id"] == entity_id]


def incoming(records: list[KnowledgeRecord], entity_id: str) -> list[dict[str, str]]:
    return [edge for edge in build_edge_list(records) if edge["object_id"] == entity_id]
