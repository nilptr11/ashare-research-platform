from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class AShareResearchError(Exception):
    """Base error for the research platform."""


class DatasetContractError(AShareResearchError):
    """Raised when a dataset violates its declared contract."""


class MartDataError(AShareResearchError):
    """Raised when mart data cannot be found or read."""


class ConnectorError(AShareResearchError):
    """Raised when a source connector cannot fetch data."""


class RawStoreError(AShareResearchError):
    """Raised when raw source data cannot be stored."""


class FeatureError(AShareResearchError):
    """Raised when a feature cannot be built or read."""


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    title: str
    source: str
    source_api: str
    partition_keys: tuple[str, ...]
    primary_key: tuple[str, ...] = ()
    required_columns: tuple[str, ...] = ()
    units: dict[str, str] = field(default_factory=dict)
    empty_policy: str = "forbid_empty"
    freshness: dict[str, Any] = field(default_factory=dict)
    default_fields: tuple[str, ...] = ()
    analysis_columns: tuple[str, ...] = ()
    analysis_min_non_null: float = 0.8
    source_variants: tuple[dict[str, Any], ...] = ()
    group: str = ""
    min_profile: str = "basic"
    maintenance_kind: str = "trade_date"
    date_param: str | None = None
    page_limit: int | None = None
    max_pages: int = 20
    requires_stock_pool: bool = False
    driver_dataset: str | None = None
    driver_code_param: str = "ts_code"
    driver_code_columns: tuple[str, ...] = ("ts_code", "index_code", "code")
    driver_name_columns: tuple[str, ...] = ("name", "index_name", "industry_name", "concept_name")
    range_lookback_days: int = 370

    def __post_init__(self) -> None:
        if not self.name:
            raise DatasetContractError("DatasetSpec.name is required")
        if not self.partition_keys:
            raise DatasetContractError(f"{self.name}: partition_keys is required")
        if self.empty_policy not in {"forbid_empty", "allow_empty"}:
            raise DatasetContractError(f"{self.name}: invalid empty_policy {self.empty_policy!r}")
        if self.min_profile not in {"basic", "standard", "full"}:
            raise DatasetContractError(f"{self.name}: invalid min_profile {self.min_profile!r}")
        if self.analysis_min_non_null < 0 or self.analysis_min_non_null > 1:
            raise DatasetContractError(f"{self.name}: invalid analysis_min_non_null {self.analysis_min_non_null!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "source": self.source,
            "source_api": self.source_api,
            "partition_keys": list(self.partition_keys),
            "primary_key": list(self.primary_key),
            "required_columns": list(self.required_columns),
            "units": dict(self.units),
            "empty_policy": self.empty_policy,
            "freshness": dict(self.freshness),
            "default_fields": list(self.default_fields),
            "analysis_columns": list(self.analysis_columns),
            "analysis_min_non_null": self.analysis_min_non_null,
            "source_variants": [dict(variant) for variant in self.source_variants],
            "group": self.group,
            "min_profile": self.min_profile,
            "maintenance_kind": self.maintenance_kind,
            "date_param": self.date_param,
            "page_limit": self.page_limit,
            "max_pages": self.max_pages,
            "requires_stock_pool": self.requires_stock_pool,
            "driver_dataset": self.driver_dataset,
            "driver_code_param": self.driver_code_param,
            "driver_code_columns": list(self.driver_code_columns),
            "driver_name_columns": list(self.driver_name_columns),
            "range_lookback_days": self.range_lookback_days,
        }


@dataclass(frozen=True)
class SourceResponse:
    source: str
    api_name: str
    params: dict[str, Any]
    fields: tuple[str, ...]
    rows: int
    columns: tuple[str, ...]
    requested_at: str
    frame: Any

    def request_fingerprint(self) -> str:
        payload = {
            "source": self.source,
            "api_name": self.api_name,
            "params": self.params,
            "fields": list(self.fields),
            "requested_at": self.requested_at,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class MartPartition:
    dataset: str
    values: dict[str, str]
    path: Path

    @property
    def id(self) -> str:
        pieces = [f"{key}={value}" for key, value in sorted(self.values.items())]
        return "/".join([self.dataset, *pieces])


@dataclass(frozen=True)
class MartPartitionMeta:
    dataset: str
    partition: dict[str, str]
    rows: int
    columns: tuple[str, ...]
    source: dict[str, Any] = field(default_factory=dict)
    schema: str = "ashare.mart_partition.v1"
    published_at: str | None = None
    quality_status: str | None = None
    quality: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MartPartitionMeta":
        return cls(
            schema=str(payload.get("schema", "ashare.mart_partition.v1")),
            dataset=str(payload["dataset"]),
            partition={str(key): str(value) for key, value in payload.get("partition", {}).items()},
            rows=int(payload.get("rows", 0)),
            columns=tuple(str(column) for column in payload.get("columns", [])),
            source=dict(payload.get("source", {})),
            published_at=payload.get("published_at"),
            quality_status=payload.get("quality_status"),
            quality=dict(payload.get("quality", {})),
        )

    @classmethod
    def from_file(cls, path: Path) -> "MartPartitionMeta":
        with path.open("r", encoding="utf-8") as file:
            return cls.from_dict(json.load(file))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "dataset": self.dataset,
            "partition": dict(self.partition),
            "rows": self.rows,
            "columns": list(self.columns),
            "source": dict(self.source),
            "published_at": self.published_at,
            "quality_status": self.quality_status,
            "quality": dict(self.quality),
        }


@dataclass(frozen=True)
class DatasetCheck:
    dataset: str
    status: str
    registered: bool
    partition: dict[str, str] = field(default_factory=dict)
    requested_partition: dict[str, str] = field(default_factory=dict)
    rows: int | None = None
    missing_columns: tuple[str, ...] = ()
    analysis_columns: tuple[str, ...] = ()
    missing_analysis_columns: tuple[str, ...] = ()
    non_null_ratios: dict[str, float] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    path: str | None = None
    message: str = ""
    partition_mode: str = "exact"
    historical_precision: str = "exact"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "status": self.status,
            "registered": self.registered,
            "partition": dict(self.partition),
            "requested_partition": dict(self.requested_partition),
            "rows": self.rows,
            "missing_columns": list(self.missing_columns),
            "analysis_columns": list(self.analysis_columns),
            "missing_analysis_columns": list(self.missing_analysis_columns),
            "non_null_ratios": dict(self.non_null_ratios),
            "quality": dict(self.quality),
            "path": self.path,
            "message": self.message,
            "partition_mode": self.partition_mode,
            "historical_precision": self.historical_precision,
        }


@dataclass(frozen=True)
class FeatureInputSpec:
    dataset: str
    component: str
    role: str = "required"
    supports: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in {"required", "degrade_if_missing", "optional"}:
            raise FeatureError(f"{self.dataset}: invalid feature input role {self.role!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "component": self.component,
            "role": self.role,
            "supports": list(self.supports),
        }


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    title: str
    version: str
    inputs: tuple[str, ...]
    partition_keys: tuple[str, ...]
    primary_key: tuple[str, ...]
    description: str = ""
    analysis_columns: tuple[str, ...] = ()
    analysis_min_non_null: float = 0.8
    input_specs: tuple[FeatureInputSpec, ...] = ()
    supports: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "version": self.version,
            "inputs": list(self.inputs),
            "partition_keys": list(self.partition_keys),
            "primary_key": list(self.primary_key),
            "description": self.description,
            "analysis_columns": list(self.analysis_columns),
            "analysis_min_non_null": self.analysis_min_non_null,
            "input_specs": [spec.to_dict() for spec in self.input_specs],
            "supports": list(self.supports),
        }


@dataclass(frozen=True)
class FeatureBuildResult:
    feature: str
    version: str
    as_of: str
    window: int
    rows: int
    path: str
    inputs: tuple[dict[str, Any], ...] = ()
    scoring: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "version": self.version,
            "as_of": self.as_of,
            "window": self.window,
            "rows": self.rows,
            "path": self.path,
            "inputs": list(self.inputs),
            "scoring": dict(self.scoring),
        }


@dataclass(frozen=True)
class FeaturePartitionMeta:
    feature: str
    version: str
    partition: dict[str, str]
    rows: int
    columns: tuple[str, ...]
    inputs: tuple[dict[str, Any], ...] = ()
    scoring: dict[str, Any] = field(default_factory=dict)
    schema: str = "ashare.feature_partition.v1"
    generated_at: str | None = None
    quality_status: str | None = None
    quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "feature": self.feature,
            "version": self.version,
            "partition": dict(self.partition),
            "rows": self.rows,
            "columns": list(self.columns),
            "inputs": list(self.inputs),
            "scoring": dict(self.scoring),
            "generated_at": self.generated_at,
            "quality_status": self.quality_status,
            "quality": dict(self.quality),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeaturePartitionMeta":
        return cls(
            schema=str(payload.get("schema", "ashare.feature_partition.v1")),
            feature=str(payload["feature"]),
            version=str(payload["version"]),
            partition={str(key): str(value) for key, value in payload.get("partition", {}).items()},
            rows=int(payload.get("rows", 0)),
            columns=tuple(str(column) for column in payload.get("columns", [])),
            inputs=tuple(dict(item) for item in payload.get("inputs", [])),
            scoring=dict(payload.get("scoring", {})),
            generated_at=payload.get("generated_at"),
            quality_status=payload.get("quality_status"),
            quality=dict(payload.get("quality", {})),
        )

    @classmethod
    def from_file(cls, path: Path) -> "FeaturePartitionMeta":
        with path.open("r", encoding="utf-8") as file:
            return cls.from_dict(json.load(file))
