from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...paths import default_data_dir
from .schemas import EvidenceAdapterError, EvidenceAdapterSpec, spec_from_candidate, validate_adapter_spec


class EvidenceAdapterRegistry:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.adapters_dir = self.data_dir / "evidence" / "adapters"

    def list(self, *, status: str | None = None) -> list[EvidenceAdapterSpec]:
        if not self.adapters_dir.exists():
            return []
        specs: list[EvidenceAdapterSpec] = []
        for path in sorted(self.adapters_dir.glob("*.json")):
            spec = validate_adapter_spec(EvidenceAdapterSpec.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            if status and spec.status != status:
                continue
            specs.append(spec)
        return specs

    def require(self, adapter_id: str) -> EvidenceAdapterSpec:
        for spec in self.list():
            if spec.adapter_id == adapter_id:
                return spec
        raise EvidenceAdapterError(f"adapter spec not found: {adapter_id}")

    def write(self, spec: EvidenceAdapterSpec, *, overwrite: bool = False) -> Path:
        spec = validate_adapter_spec(spec)
        self.adapters_dir.mkdir(parents=True, exist_ok=True)
        path = self.adapters_dir / f"{_safe_filename(spec.adapter_id)}.json"
        if path.exists() and not overwrite:
            raise EvidenceAdapterError(f"adapter spec already exists: {path}")
        path.write_text(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def propose_from_candidates(self, candidates: list[dict[str, Any]], *, overwrite: bool = False) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for candidate in candidates:
            spec = spec_from_candidate(candidate)
            path = self.write(spec, overwrite=overwrite)
            rows.append(spec.to_dict() | {"path": str(path)})
        return rows


def _safe_filename(value: str) -> str:
    return value.replace(":", "_").replace("/", "_")
