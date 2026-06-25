from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from .schemas import CapabilityError, CapabilitySpec, validate_capability


class CapabilityRegistry:
    def __init__(self, specs: list[CapabilitySpec]) -> None:
        self._specs = {spec.capability_id: validate_capability(spec) for spec in specs}

    @classmethod
    def builtin(cls) -> "CapabilityRegistry":
        specs: list[CapabilitySpec] = []
        try:
            specs_root = resources.files("ashare_research.capabilities").joinpath("specs")
            for spec_file in sorted(item for item in specs_root.iterdir() if item.name.endswith(".json")):
                specs.append(CapabilitySpec.from_dict(json.loads(spec_file.read_text(encoding="utf-8"))))
        except FileNotFoundError:
            specs = []
        return cls(specs)

    @classmethod
    def from_directory(cls, path: Path | str) -> "CapabilityRegistry":
        root = Path(path)
        specs = [CapabilitySpec.from_dict(json.loads(item.read_text(encoding="utf-8"))) for item in sorted(root.glob("*.json"))]
        return cls(specs)

    def list(self) -> list[CapabilitySpec]:
        return [self._specs[key] for key in sorted(self._specs)]

    def require(self, capability_id: str) -> CapabilitySpec:
        try:
            return self._specs[capability_id]
        except KeyError as error:
            raise CapabilityError(f"capability not found: {capability_id}") from error

    def validate(self, capability_id: str | None = None) -> dict[str, Any]:
        specs = [self.require(capability_id)] if capability_id else self.list()
        rows: list[dict[str, Any]] = []
        for spec in specs:
            validate_capability(spec)
            rows.append(
                {
                    "capability_id": spec.capability_id,
                    "version": spec.version,
                    "status": "ready",
                    "inputs": {key: list(value) for key, value in spec.inputs.items()},
                    "quality_requirements": list(spec.quality_requirements),
                }
            )
        return {
            "schema": "ashare.capability_validation.v1",
            "status": "ready",
            "capabilities": rows,
        }
