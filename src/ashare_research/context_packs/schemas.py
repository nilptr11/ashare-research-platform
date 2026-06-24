from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schemas import AShareResearchError


class ContextPackError(AShareResearchError):
    """Raised when a context pack cannot be built."""


@dataclass(frozen=True)
class ContextInput:
    kind: str
    name: str
    status: str
    content_hash: str | None = None
    path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
            "content_hash": self.content_hash,
            "path": self.path,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ContextPack:
    schema: str
    pack_id: str
    pack_type: str
    generated_at: str
    as_of: str
    inputs: tuple[ContextInput, ...]
    sections: dict[str, Any]
    coverage: dict[str, Any]
    data_gaps: tuple[dict[str, Any], ...] = ()
    quality_flags: tuple[str, ...] = ()
    skipped_sources: tuple[dict[str, Any], ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)
    source_policy_summary: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    window: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pack_id": self.pack_id,
            "pack_type": self.pack_type,
            "generated_at": self.generated_at,
            "as_of": self.as_of,
            "window": dict(self.window),
            "inputs": [source.to_dict() for source in self.inputs],
            "sections": dict(self.sections),
            "coverage": dict(self.coverage),
            "data_gaps": list(self.data_gaps),
            "quality_flags": list(self.quality_flags),
            "skipped_sources": list(self.skipped_sources),
            "constraints": dict(self.constraints),
            "source_policy_summary": dict(self.source_policy_summary),
            "provenance": dict(self.provenance),
        }
