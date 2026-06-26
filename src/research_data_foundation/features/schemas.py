from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core import UsagePolicy


class FeatureError(ValueError):
    """Raised when a feature cannot be declared, built, or read."""


@dataclass(frozen=True)
class FeatureInputSpec:
    dataset_id: str
    role: str = "required"
    columns: tuple[str, ...] = ()
    supports: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in {"required", "degrade_if_missing", "optional"}:
            raise FeatureError(f"{self.dataset_id}: invalid feature input role {self.role!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "role": self.role,
            "columns": list(self.columns),
            "supports": list(self.supports),
        }


@dataclass(frozen=True)
class FeatureSpec:
    id: str
    title: str
    domain: str
    version: str
    role: str
    inputs: tuple[FeatureInputSpec, ...]
    partition_keys: tuple[str, ...] = ("as_of", "window")
    primary_key: tuple[str, ...] = ()
    analysis_columns: tuple[str, ...] = ()
    analysis_min_non_null: float = 0.8
    recommended_windows: tuple[int, ...] = (20,)
    usage: UsagePolicy = field(default_factory=lambda: UsagePolicy(allowed_uses=("context",)))
    description: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise FeatureError("FeatureSpec.id is required")
        if not self.domain:
            raise FeatureError(f"{self.id}: domain is required")
        if not self.partition_keys:
            raise FeatureError(f"{self.id}: partition_keys is required")
        if self.analysis_min_non_null < 0 or self.analysis_min_non_null > 1:
            raise FeatureError(f"{self.id}: invalid analysis_min_non_null {self.analysis_min_non_null!r}")
        if not self.recommended_windows or any(window <= 0 for window in self.recommended_windows):
            raise FeatureError(f"{self.id}: recommended_windows must contain positive integers")

    def permits(self, use: str) -> bool:
        return self.usage.permits(use)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "domain": self.domain,
            "version": self.version,
            "role": self.role,
            "inputs": [item.to_dict() for item in self.inputs],
            "partition_keys": list(self.partition_keys),
            "primary_key": list(self.primary_key),
            "analysis_columns": list(self.analysis_columns),
            "analysis_min_non_null": self.analysis_min_non_null,
            "recommended_windows": list(self.recommended_windows),
            "usage": self.usage.to_dict(),
            "description": self.description,
        }


@dataclass(frozen=True)
class FeatureBuildResult:
    feature_id: str
    version: str
    domain: str
    as_of: str
    window: int
    rows: int
    path: str
    inputs: tuple[dict[str, Any], ...] = ()
    quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.feature_build_result.v1",
            "feature_id": self.feature_id,
            "version": self.version,
            "domain": self.domain,
            "as_of": self.as_of,
            "window": self.window,
            "rows": self.rows,
            "path": self.path,
            "inputs": list(self.inputs),
            "quality": dict(self.quality),
        }


@dataclass(frozen=True)
class FeaturePartitionMeta:
    feature_id: str
    version: str
    domain: str
    partition: dict[str, str]
    rows: int
    columns: tuple[str, ...]
    inputs: tuple[dict[str, Any], ...] = ()
    quality: dict[str, Any] = field(default_factory=dict)
    schema: str = "rdf.feature_partition.v1"
    generated_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeaturePartitionMeta":
        return cls(
            schema=str(payload.get("schema", "rdf.feature_partition.v1")),
            feature_id=str(payload["feature_id"]),
            version=str(payload["version"]),
            domain=str(payload["domain"]),
            partition={str(key): str(value) for key, value in payload.get("partition", {}).items()},
            rows=int(payload.get("rows", 0)),
            columns=tuple(str(column) for column in payload.get("columns", [])),
            inputs=tuple(dict(item) for item in payload.get("inputs", [])),
            quality=dict(payload.get("quality", {})),
            generated_at=payload.get("generated_at"),
        )

    @classmethod
    def from_file(cls, path: Path) -> "FeaturePartitionMeta":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "feature_id": self.feature_id,
            "version": self.version,
            "domain": self.domain,
            "partition": dict(self.partition),
            "rows": self.rows,
            "columns": list(self.columns),
            "inputs": list(self.inputs),
            "quality": dict(self.quality),
            "generated_at": self.generated_at,
        }
