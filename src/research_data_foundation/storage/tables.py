from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..core.paths import default_data_dir
from ..core.registry import FoundationRegistry
from ..core.schemas import DatasetContract
from ..domains import default_registry


class StorageError(ValueError):
    """Raised when table storage cannot publish or read a partition."""


class TableStore:
    def __init__(self, layer: str, data_dir: Path | str | None = None, registry: FoundationRegistry | None = None) -> None:
        if layer not in {"staging", "mart"}:
            raise StorageError(f"unsupported table layer: {layer}")
        self.layer = layer
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.registry = registry or default_registry()
        self.root = self.data_dir / layer

    def publish(
        self,
        dataset_id: str,
        frame: pd.DataFrame,
        *,
        partition: dict[str, str],
        lineage: dict[str, Any],
        refresh: bool = False,
    ) -> Path:
        contract = self.registry.require_dataset(dataset_id)
        quality = quality_payload(contract, frame, partition)
        if quality["status"] in {"schema_mismatch", "empty", "partition_mismatch", "primary_key_violation"}:
            raise StorageError(f"{dataset_id}: {quality['reason']}")
        path = self.partition_path(dataset_id, partition)
        if path.exists() and not refresh:
            raise StorageError(f"table partition already exists: {path}; pass refresh=True to overwrite")
        path.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path / "part.parquet", index=False)
        meta = {
            "schema": "rdf.table_partition.v1",
            "layer": self.layer,
            "dataset_id": dataset_id,
            "domain": contract.domain,
            "partition": dict(partition),
            "rows": int(len(frame)),
            "columns": [str(column) for column in frame.columns],
            "lineage": dict(lineage),
            "temporal": {
                "temporal_mode": contract.temporal.temporal_mode,
                "finality": contract.temporal.finality,
                "available_after": contract.temporal.available_after,
                "as_of_policy": contract.temporal.as_of_policy,
            },
            "quality": quality,
            "published_at": now_iso(),
        }
        (path / "_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def read(self, dataset_id: str, partition: dict[str, str], columns: list[str] | None = None) -> pd.DataFrame:
        path = self.partition_path(dataset_id, partition) / "part.parquet"
        if not path.exists():
            raise StorageError(f"missing table partition: {path}")
        return pd.read_parquet(path, columns=columns)

    def read_matching(
        self,
        dataset_id: str,
        partition_filter: dict[str, str],
        *,
        columns: list[str] | None = None,
        partition_limit: int | None = None,
    ) -> pd.DataFrame:
        partitions = self.matching_partitions(dataset_id, partition_filter)
        if partition_limit and partition_limit > 0:
            partitions = partitions[:partition_limit]
        if not partitions:
            raise StorageError(f"{dataset_id}: no partitions match {partition_filter}")
        frames = [self.read(dataset_id, partition, columns=columns) for partition in partitions]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def read_meta(self, dataset_id: str, partition: dict[str, str]) -> dict[str, Any]:
        path = self.partition_path(dataset_id, partition) / "_meta.json"
        if not path.exists():
            raise StorageError(f"missing table metadata: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_partitions(self, dataset_id: str) -> list[dict[str, str]]:
        contract = self.registry.require_dataset(dataset_id)
        root = self.root / contract.domain / dataset_id
        if not root.exists():
            return []
        partitions: list[dict[str, str]] = []
        for path in sorted(root.glob("/".join(["*"] * len(contract.partition_keys)))):
            if not path.is_dir() or not (path / "part.parquet").exists():
                continue
            values: dict[str, str] = {}
            for piece in path.relative_to(root).parts:
                if "=" not in piece:
                    values = {}
                    break
                key, value = piece.split("=", 1)
                values[key] = value
            if all(key in values for key in contract.partition_keys):
                partitions.append({key: values[key] for key in contract.partition_keys})
        return partitions

    def matching_partitions(self, dataset_id: str, partition_filter: dict[str, str]) -> list[dict[str, str]]:
        contract = self.registry.require_dataset(dataset_id)
        unknown_keys = [key for key in partition_filter if key not in contract.partition_keys]
        if unknown_keys:
            raise StorageError(f"{dataset_id}: unknown partition keys {unknown_keys}")
        partitions = [
            partition
            for partition in self.list_partitions(dataset_id)
            if all(str(partition.get(key, "")) == str(value) for key, value in partition_filter.items())
        ]
        return sorted(
            partitions,
            key=lambda partition: tuple(str(partition.get(key, "")) for key in contract.partition_keys),
            reverse=True,
        )

    def read_window(
        self,
        dataset_id: str,
        *,
        as_of: str,
        count: int,
        partition_key: str | None = None,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        contract = self.registry.require_dataset(dataset_id)
        key = partition_key or (contract.partition_keys[0] if len(contract.partition_keys) == 1 else "")
        if not key:
            raise StorageError(f"{dataset_id}: read_window requires partition_key for multi-key datasets")
        if key not in contract.partition_keys:
            raise StorageError(f"{dataset_id}: unknown partition_key {key!r}")
        partitions = [
            partition
            for partition in self.list_partitions(dataset_id)
            if key in partition and str(partition[key]) <= str(as_of)
        ]
        selected = sorted(partitions, key=lambda item: item[key], reverse=True)[: max(count, 0)]
        if not selected:
            raise StorageError(f"{dataset_id}: no partitions at or before {as_of}")
        frames = [self.read(dataset_id, partition, columns=columns) for partition in reversed(selected)]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def partition_path(self, dataset_id: str, partition: dict[str, str]) -> Path:
        contract = self.registry.require_dataset(dataset_id)
        parts = [f"{key}={partition[key]}" for key in contract.partition_keys if key in partition]
        if len(parts) != len(contract.partition_keys):
            missing = [key for key in contract.partition_keys if key not in partition]
            raise StorageError(f"{dataset_id}: partition missing keys {missing}")
        return self.root / contract.domain / dataset_id / Path(*parts)


class StagingStore(TableStore):
    def __init__(self, data_dir: Path | str | None = None, registry: FoundationRegistry | None = None) -> None:
        super().__init__("staging", data_dir=data_dir, registry=registry)


class MartStore(TableStore):
    def __init__(self, data_dir: Path | str | None = None, registry: FoundationRegistry | None = None) -> None:
        super().__init__("mart", data_dir=data_dir, registry=registry)


def quality_payload(contract: DatasetContract, frame: pd.DataFrame, partition: dict[str, str]) -> dict[str, Any]:
    missing_partition_keys = [key for key in contract.partition_keys if key not in partition]
    missing_columns = [column for column in contract.required_columns if column not in frame.columns]
    partition_value_mismatches = partition_value_mismatch_counts(frame, partition)
    base = {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "missing_partition_keys": missing_partition_keys,
        "missing_columns": missing_columns,
        "partition_value_mismatches": partition_value_mismatches,
        "duplicate_primary_key_rows": duplicate_primary_key_rows(contract, frame),
        "missing_analysis_columns": [],
        "non_null_ratios": {},
        "empty_policy": contract.empty_policy,
    }
    if missing_partition_keys:
        return base | {"status": "partition_mismatch", "reason": "missing partition keys"}
    if partition_value_mismatches:
        return base | {"status": "partition_mismatch", "reason": "partition column values do not match partition"}
    if missing_columns:
        return base | {"status": "schema_mismatch", "reason": "missing required columns"}
    if base["duplicate_primary_key_rows"]:
        return base | {"status": "primary_key_violation", "reason": "duplicate primary key rows"}
    if frame.empty and contract.empty_policy == "forbid_empty":
        return base | {"status": "empty", "reason": "empty partition is forbidden"}
    analysis = analysis_quality(contract, frame)
    if analysis["status"] != "ok":
        return base | analysis
    return base | {"status": "ok", "reason": ""}


def duplicate_primary_key_rows(contract: DatasetContract, frame: pd.DataFrame) -> int:
    if frame.empty or any(column not in frame.columns for column in contract.primary_key):
        return 0
    return int(frame.duplicated(list(contract.primary_key), keep=False).sum())


def partition_value_mismatch_counts(frame: pd.DataFrame, partition: dict[str, str]) -> dict[str, int]:
    if frame.empty:
        return {}
    mismatches: dict[str, int] = {}
    for key, expected in partition.items():
        if key not in frame.columns:
            continue
        actual = frame[key].fillna("").astype(str)
        mismatch_count = int((actual != str(expected)).sum())
        if mismatch_count:
            mismatches[key] = mismatch_count
    return mismatches


def analysis_quality(contract: DatasetContract, frame: pd.DataFrame) -> dict[str, Any]:
    if not contract.analysis_columns or frame.empty:
        return {"status": "ok", "reason": "", "missing_analysis_columns": [], "non_null_ratios": {}}
    missing = [column for column in contract.analysis_columns if column not in frame.columns]
    if missing:
        return {
            "status": "degraded",
            "reason": "missing analysis columns",
            "missing_analysis_columns": missing,
            "non_null_ratios": {},
        }
    ratios = {column: float(frame[column].notna().sum() / len(frame)) for column in contract.analysis_columns}
    return {
        "status": "ok",
        "reason": "",
        "missing_analysis_columns": [],
        "non_null_ratios": ratios,
    }


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
