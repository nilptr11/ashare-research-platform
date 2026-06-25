from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from .schemas import ProtocolError, ProtocolSpec, validate_protocol


class ProtocolRegistry:
    def __init__(self, specs: list[ProtocolSpec]) -> None:
        self._specs = {spec.protocol_id: validate_protocol(spec) for spec in specs}

    @classmethod
    def builtin(cls) -> "ProtocolRegistry":
        specs: list[ProtocolSpec] = []
        try:
            specs_root = resources.files("ashare_research.protocols").joinpath("specs")
            for spec_file in sorted(item for item in specs_root.iterdir() if item.name.endswith(".json")):
                specs.append(ProtocolSpec.from_dict(json.loads(spec_file.read_text(encoding="utf-8"))))
        except FileNotFoundError:
            specs = []
        return cls(specs)

    @classmethod
    def from_directory(cls, path: Path | str) -> "ProtocolRegistry":
        root = Path(path)
        specs = [ProtocolSpec.from_dict(json.loads(item.read_text(encoding="utf-8"))) for item in sorted(root.glob("*.json"))]
        return cls(specs)

    def list(self) -> list[ProtocolSpec]:
        return [self._specs[key] for key in sorted(self._specs)]

    def require(self, protocol_id: str) -> ProtocolSpec:
        try:
            return self._specs[protocol_id]
        except KeyError as error:
            raise ProtocolError(f"protocol not found: {protocol_id}") from error

    def validate(self, protocol_id: str | None = None) -> dict[str, Any]:
        specs = [self.require(protocol_id)] if protocol_id else self.list()
        rows: list[dict[str, Any]] = []
        for spec in specs:
            validate_protocol(spec)
            output_schema = self.output_schema(spec.output_schema or "")
            rows.append(
                {
                    "protocol_id": spec.protocol_id,
                    "version": spec.version,
                    "status": "ready",
                    "output_schema": spec.output_schema,
                    "output_schema_status": "ready" if output_schema else "missing",
                    "required_contexts": list(spec.required_contexts),
                    "suggested_capabilities": list(spec.suggested_capabilities),
                    "quality_gates": list(spec.quality_gates),
                }
            )
        return {
            "schema": "ashare.protocol_validation.v1",
            "status": "ready",
            "protocols": rows,
        }

    def output_schema(self, schema_id: str) -> dict[str, Any]:
        if not schema_id:
            raise ProtocolError("output schema id is required")
        schema_name = _schema_id_to_filename(schema_id)
        try:
            schema_root = resources.files("ashare_research.protocols").joinpath("output_schemas")
            schema_file = schema_root.joinpath(schema_name)
            if not schema_file.is_file():
                raise ProtocolError(f"output schema not found: {schema_id}")
            payload = json.loads(schema_file.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ProtocolError(f"output schema not found: {schema_id}") from error
        if payload.get("$id") != schema_id:
            raise ProtocolError(f"output schema id mismatch: expected {schema_id}, got {payload.get('$id')}")
        return payload


def _schema_id_to_filename(schema_id: str) -> str:
    prefix = "ashare.protocol_output."
    if not schema_id.startswith(prefix):
        raise ProtocolError(f"unsupported output schema id: {schema_id}")
    return f"{schema_id.removeprefix(prefix)}.json"
