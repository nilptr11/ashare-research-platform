from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schemas import AShareResearchError


class ProtocolError(AShareResearchError):
    """Raised when protocol specs are invalid or unavailable."""


QUALITY_GATES = {"schema_gate", "freshness_gate", "gap_gate", "source_gate", "confidence_gate"}


@dataclass(frozen=True)
class ProtocolSpec:
    protocol_id: str
    title: str
    version: str
    status: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...] = ()
    required_sections: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    output_schema: str | None = None
    gap_policy: dict[str, str] = field(default_factory=dict)
    quality_gates: tuple[str, ...] = ()
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProtocolSpec":
        normalized = dict(payload)
        normalized.pop("schema", None)
        return cls(
            protocol_id=str(normalized["protocol_id"]),
            title=str(normalized["title"]),
            version=str(normalized.get("version", "v1")),
            status=str(normalized.get("status", "registered_protocol")),
            required_inputs=tuple(str(item) for item in normalized.get("required_inputs", ())),
            optional_inputs=tuple(str(item) for item in normalized.get("optional_inputs", ())),
            required_sections=tuple(str(item) for item in normalized.get("required_sections", ())),
            forbidden=tuple(str(item) for item in normalized.get("forbidden", ())),
            output_schema=normalized.get("output_schema"),
            gap_policy={str(key): str(value) for key, value in normalized.get("gap_policy", {}).items()},
            quality_gates=tuple(str(item) for item in normalized.get("quality_gates", ())),
            description=str(normalized.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ashare.protocol_spec.v1",
            "protocol_id": self.protocol_id,
            "title": self.title,
            "version": self.version,
            "status": self.status,
            "description": self.description,
            "required_inputs": list(self.required_inputs),
            "optional_inputs": list(self.optional_inputs),
            "required_sections": list(self.required_sections),
            "forbidden": list(self.forbidden),
            "output_schema": self.output_schema,
            "gap_policy": dict(self.gap_policy),
            "quality_gates": list(self.quality_gates),
        }


def validate_protocol(spec: ProtocolSpec) -> ProtocolSpec:
    if not spec.protocol_id:
        raise ProtocolError("protocol_id is required")
    if not spec.title:
        raise ProtocolError(f"{spec.protocol_id}: title is required")
    if spec.status not in {"ad_hoc_protocol", "prompt_backed_protocol", "registered_protocol"}:
        raise ProtocolError(f"{spec.protocol_id}: invalid status {spec.status!r}")
    if not spec.required_inputs:
        raise ProtocolError(f"{spec.protocol_id}: at least one required input is required")
    if not spec.required_sections:
        raise ProtocolError(f"{spec.protocol_id}: required_sections is required")
    if not spec.output_schema:
        raise ProtocolError(f"{spec.protocol_id}: output_schema is required")
    unknown_gates = sorted(set(spec.quality_gates) - QUALITY_GATES)
    if unknown_gates:
        raise ProtocolError(f"{spec.protocol_id}: unknown quality gates {unknown_gates}")
    for key, value in spec.gap_policy.items():
        if value not in {"block", "degrade_with_gap", "warn", "state_no_realtime"}:
            raise ProtocolError(f"{spec.protocol_id}: invalid gap policy {key}={value}")
    return spec
