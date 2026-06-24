from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..datasets.catalog import DatasetCatalog
from ..paths import default_data_dir
from ..schemas import DatasetContractError, DatasetSpec, MartDataError


class MartPublisher:
    def __init__(self, data_dir: Path | str | None = None, catalog: DatasetCatalog | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.mart_root = self.data_dir / "mart"
        self.catalog = catalog or DatasetCatalog.builtin()

    def publish(
        self,
        dataset: str,
        frame: pd.DataFrame,
        *,
        partition: dict[str, str],
        source: dict[str, Any],
        refresh: bool = False,
    ) -> Path:
        spec = self.catalog.require(dataset)
        self._validate(spec, frame, partition)
        path = self._partition_path(dataset, partition)
        if path.exists() and not refresh:
            raise MartDataError(f"Mart partition already exists: {path}; pass refresh=True to overwrite")
        path.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path / "part.parquet", index=False)
        quality = _quality_payload(spec, frame)
        meta = {
            "schema": "ashare.mart_partition.v1",
            "dataset": dataset,
            "partition": partition,
            "rows": len(frame),
            "columns": [str(column) for column in frame.columns],
            "source": source,
            "quality_status": quality["status"],
            "quality": quality,
            "published_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        }
        (path / "_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _partition_path(self, dataset: str, partition: dict[str, str]) -> Path:
        if len(partition) != 1:
            raise MartDataError("Only single-key mart partitions are supported by MartPublisher phase 1")
        key, value = next(iter(partition.items()))
        return self.mart_root / dataset / f"{key}={value}"

    def _validate(self, spec: DatasetSpec, frame: pd.DataFrame, partition: dict[str, str]) -> None:
        missing_partition_keys = [key for key in spec.partition_keys if key not in partition]
        if missing_partition_keys:
            raise DatasetContractError(f"{spec.name}: partition missing keys {missing_partition_keys}")
        if len(frame) == 0 and spec.empty_policy == "allow_empty":
            return
        missing_columns = [column for column in spec.required_columns if column not in frame.columns]
        if missing_columns:
            raise DatasetContractError(f"{spec.name}: frame missing required columns {missing_columns}")
        if len(frame) == 0 and spec.empty_policy == "forbid_empty":
            raise DatasetContractError(f"{spec.name}: empty frame is forbidden")


def _quality_payload(spec: DatasetSpec, frame: pd.DataFrame) -> dict[str, Any]:
    if len(frame) == 0 and spec.empty_policy == "allow_empty":
        return {
            "status": "ok",
            "empty_policy": spec.empty_policy,
            "rows": 0,
            "columns": len(frame.columns),
            "missing_columns": [],
            "reason": "empty_allowed",
        }
    missing_columns = [column for column in spec.required_columns if column not in frame.columns]
    if missing_columns:
        status = "schema_mismatch"
        reason = "missing required columns"
    elif len(frame) == 0 and spec.empty_policy == "forbid_empty":
        status = "empty"
        reason = "empty partition is forbidden"
    else:
        status = "ok"
        reason = ""
    return {
        "status": status,
        "empty_policy": spec.empty_policy,
        "rows": len(frame),
        "columns": len(frame.columns),
        "missing_columns": missing_columns,
        "reason": reason,
    }
