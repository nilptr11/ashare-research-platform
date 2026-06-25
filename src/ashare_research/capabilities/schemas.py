from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schemas import AShareResearchError


class CapabilityError(AShareResearchError):
    """Raised when capability specs are invalid or unavailable."""


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    name: str
    version: str
    category: str
    description: str
    questions: tuple[str, ...]
    inputs: dict[str, tuple[str, ...]]
    commands: tuple[str, ...]
    can_support: tuple[str, ...]
    cannot_support: tuple[str, ...]
    freshness: dict[str, Any] = field(default_factory=dict)
    quality_requirements: tuple[str, ...] = ()
    suggested_protocols: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CapabilitySpec":
        normalized = dict(payload)
        normalized.pop("schema", None)
        return cls(
            capability_id=str(normalized["capability_id"]),
            name=str(normalized["name"]),
            version=str(normalized.get("version", "v1")),
            category=str(normalized["category"]),
            description=str(normalized.get("description", "")),
            questions=tuple(str(item) for item in normalized.get("questions", ())),
            inputs={
                str(key): tuple(str(item) for item in value)
                for key, value in normalized.get("inputs", {}).items()
            },
            commands=tuple(str(item) for item in normalized.get("commands", ())),
            can_support=tuple(str(item) for item in normalized.get("can_support", ())),
            cannot_support=tuple(str(item) for item in normalized.get("cannot_support", ())),
            freshness=dict(normalized.get("freshness", {})),
            quality_requirements=tuple(str(item) for item in normalized.get("quality_requirements", ())),
            suggested_protocols=tuple(str(item) for item in normalized.get("suggested_protocols", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ashare.capability_spec.v1",
            "capability_id": self.capability_id,
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "questions": list(self.questions),
            "inputs": {key: list(value) for key, value in self.inputs.items()},
            "commands": list(self.commands),
            "can_support": list(self.can_support),
            "cannot_support": list(self.cannot_support),
            "freshness": dict(self.freshness),
            "quality_requirements": list(self.quality_requirements),
            "suggested_protocols": list(self.suggested_protocols),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "inputs": {key: list(value) for key, value in self.inputs.items()},
            "suggested_protocols": list(self.suggested_protocols),
        }


def validate_capability(spec: CapabilitySpec) -> CapabilitySpec:
    if not spec.capability_id:
        raise CapabilityError("capability_id is required")
    if not spec.name:
        raise CapabilityError(f"{spec.capability_id}: name is required")
    if not spec.category:
        raise CapabilityError(f"{spec.capability_id}: category is required")
    if not spec.questions:
        raise CapabilityError(f"{spec.capability_id}: questions are required")
    if not spec.inputs:
        raise CapabilityError(f"{spec.capability_id}: inputs are required")
    if not spec.commands:
        raise CapabilityError(f"{spec.capability_id}: commands are required")
    if not spec.can_support:
        raise CapabilityError(f"{spec.capability_id}: can_support is required")
    if not spec.cannot_support:
        raise CapabilityError(f"{spec.capability_id}: cannot_support is required")
    return spec
