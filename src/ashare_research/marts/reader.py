from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..datasets.catalog import DatasetCatalog
from ..paths import default_data_dir
from ..schemas import DatasetCheck, MartDataError, MartPartition, MartPartitionMeta
from .partitions import parse_partition_name


class MartReader:
    def __init__(self, data_dir: Path | str | None = None, catalog: DatasetCatalog | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.mart_root = self.data_dir / "mart"
        self.catalog = catalog or DatasetCatalog.builtin()

    def list_datasets(self) -> list[dict[str, object]]:
        return self.catalog.discover(self.mart_root)

    def list_partitions(self, dataset: str) -> list[MartPartition]:
        dataset_dir = self.mart_root / dataset
        if not dataset_dir.exists():
            return []
        partitions: list[MartPartition] = []
        for path in sorted(dataset_dir.iterdir()):
            if not path.is_dir():
                continue
            parsed = parse_partition_name(path.name)
            if parsed is None:
                continue
            key, value = parsed
            partitions.append(MartPartition(dataset=dataset, values={key: value}, path=path))
        return partitions

    def latest_partition(self, dataset: str, partition_key: str | None = None) -> MartPartition | None:
        partitions = self.list_partitions(dataset)
        if partition_key:
            partitions = [partition for partition in partitions if partition_key in partition.values]
        if not partitions:
            return None
        return sorted(partitions, key=lambda partition: tuple(partition.values.values()))[-1]

    def partition_path(self, dataset: str, partition: dict[str, str]) -> Path:
        if not partition:
            latest = self.latest_partition(dataset)
            if latest is None:
                raise MartDataError(f"{dataset}: no mart partition found")
            return latest.path
        if len(partition) != 1:
            raise MartDataError("Only single-key mart partitions are supported in phase 1")
        key, value = next(iter(partition.items()))
        return self.mart_root / dataset / f"{key}={value}"

    def load_meta(self, dataset: str, partition: dict[str, str]) -> MartPartitionMeta:
        path = self.partition_path(dataset, partition) / "_meta.json"
        if not path.exists():
            raise MartDataError(f"Missing mart metadata: {path}")
        return MartPartitionMeta.from_file(path)

    def read_partition(
        self,
        dataset: str,
        partition: dict[str, str] | None = None,
        *,
        columns: list[str] | None = None,
        limit: int | None = None,
        require_registered: bool = True,
    ) -> pd.DataFrame:
        if require_registered:
            self.catalog.require(dataset)
        path = self.partition_path(dataset, partition or {})
        parquet_path = path / "part.parquet"
        if not parquet_path.exists():
            raise MartDataError(f"Missing mart parquet: {parquet_path}")
        frame = pd.read_parquet(parquet_path, columns=columns)
        if limit is not None and limit > 0:
            return frame.head(limit)
        return frame

    def read_window(
        self,
        dataset: str,
        *,
        as_of: str,
        trade_days: int,
        partition_key: str = "trade_date",
        columns: list[str] | None = None,
        require_registered: bool = True,
    ) -> pd.DataFrame:
        if require_registered:
            self.catalog.require(dataset)
        partitions = [
            partition
            for partition in self.list_partitions(dataset)
            if partition_key in partition.values and partition.values[partition_key] <= as_of
        ]
        selected = sorted(partitions, key=lambda partition: partition.values[partition_key])[-trade_days:]
        if not selected:
            raise MartDataError(f"{dataset}: no {partition_key} partition found before {as_of}")
        frames = [
            self.read_partition(dataset, partition.values, columns=columns, require_registered=require_registered)
            for partition in selected
        ]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def check_dataset(self, dataset: str, as_of: str | None = None, *, allow_latest_snapshot: bool = False) -> DatasetCheck:
        spec = self.catalog.get(dataset)
        if spec is None:
            return DatasetCheck(dataset=dataset, status="unregistered", registered=False, message="dataset has no contract")

        partition: dict[str, str] = {}
        if as_of and "trade_date" in spec.partition_keys:
            partition = {"trade_date": as_of}
        elif as_of and "snapshot_date" in spec.partition_keys:
            partition = {"snapshot_date": as_of}
        elif as_of and "publish_date" in spec.partition_keys:
            partition = {"publish_date": _iso_date(as_of)}
        else:
            latest = self.latest_partition(dataset, spec.partition_keys[0])
            if latest:
                partition = latest.values

        try:
            meta = self.load_meta(dataset, partition)
        except MartDataError as error:
            if allow_latest_snapshot and as_of and "snapshot_date" in spec.partition_keys:
                latest = self.latest_partition(dataset, "snapshot_date")
                if latest is not None:
                    try:
                        meta = self.load_meta(dataset, latest.values)
                    except MartDataError:
                        pass
                    else:
                        return self._check_meta(
                            spec,
                            meta,
                            requested_partition=partition,
                            partition_mode="latest_available",
                            historical_precision="approximate",
                            message=f"using latest_available snapshot {latest.values} for requested {partition}",
                        )
            return DatasetCheck(
                dataset=dataset,
                status="missing",
                registered=True,
                partition=partition,
                requested_partition=partition,
                message=str(error),
            )

        return self._check_meta(spec, meta, requested_partition=partition)

    def _check_meta(
        self,
        spec,
        meta: MartPartitionMeta,
        *,
        requested_partition: dict[str, str] | None = None,
        partition_mode: str = "exact",
        historical_precision: str = "exact",
        message: str = "",
    ) -> DatasetCheck:
        missing_columns = tuple(column for column in spec.required_columns if column not in meta.columns)
        analysis = self._analysis_quality(spec, meta)
        if meta.rows == 0 and spec.empty_policy == "allow_empty":
            status = "ready"
            status_message = message
            missing_columns = ()
        elif missing_columns:
            status = "schema_mismatch"
            status_message = "missing required columns"
        elif meta.rows == 0 and spec.empty_policy == "forbid_empty":
            status = "empty"
            status_message = "empty partition is forbidden"
        elif analysis["status"] != "ok":
            status = "degraded"
            status_message = analysis["reason"]
        else:
            status = "ready"
            status_message = message

        return DatasetCheck(
            dataset=spec.name,
            status=status,
            registered=True,
            partition=meta.partition,
            requested_partition=requested_partition or meta.partition,
            rows=meta.rows,
            missing_columns=missing_columns,
            analysis_columns=tuple(spec.analysis_columns),
            missing_analysis_columns=tuple(analysis["missing_analysis_columns"]),
            non_null_ratios=dict(analysis["non_null_ratios"]),
            quality={
                "status": analysis["status"],
                "analysis_columns": list(spec.analysis_columns),
                "analysis_min_non_null": spec.analysis_min_non_null,
                "missing_analysis_columns": list(analysis["missing_analysis_columns"]),
                "non_null_ratios": dict(analysis["non_null_ratios"]),
                "reason": analysis["reason"],
                "partition_mode": partition_mode,
                "historical_precision": historical_precision,
            },
            path=str(self.partition_path(spec.name, meta.partition)),
            message=status_message,
            partition_mode=partition_mode,
            historical_precision=historical_precision,
        )

    def dump_meta_json(self, dataset: str, partition: dict[str, str]) -> str:
        meta = self.load_meta(dataset, partition)
        return json.dumps(meta.to_dict(), ensure_ascii=False, indent=2)

    def check(self, datasets: list[str] | None = None, as_of: str | None = None) -> dict[str, Any]:
        names = datasets or [spec.name for spec in self.catalog.list()]
        checks = [self.check_dataset(name, as_of=as_of).to_dict() for name in names]
        blocking_statuses = {"missing", "schema_mismatch", "empty", "unregistered", "read_error"}
        if any(check["status"] in blocking_statuses for check in checks):
            status = "blocked"
        elif any(check["status"] == "degraded" for check in checks):
            status = "degraded"
        else:
            status = "ready"
        return {
            "schema": "ashare.data_check.v1",
            "status": status,
            "as_of": as_of,
            "datasets": checks,
        }

    def _analysis_quality(self, spec, meta: MartPartitionMeta) -> dict[str, Any]:
        if not spec.analysis_columns or meta.rows == 0:
            return {"status": "ok", "reason": "", "missing_analysis_columns": [], "non_null_ratios": {}}
        missing = [column for column in spec.analysis_columns if column not in meta.columns]
        if missing:
            return {
                "status": "degraded",
                "reason": "missing analysis columns",
                "missing_analysis_columns": missing,
                "non_null_ratios": {},
            }
        try:
            frame = self.read_partition(spec.name, meta.partition, columns=list(spec.analysis_columns))
        except Exception as error:
            return {
                "status": "degraded",
                "reason": f"analysis quality check failed: {error}",
                "missing_analysis_columns": [],
                "non_null_ratios": {},
            }
        ratios = {column: float(frame[column].notna().sum() / len(frame)) for column in spec.analysis_columns}
        low_columns = [column for column, ratio in ratios.items() if ratio < spec.analysis_min_non_null]
        if low_columns:
            return {
                "status": "degraded",
                "reason": "analysis columns below non-null threshold",
                "missing_analysis_columns": [],
                "non_null_ratios": ratios,
            }
        return {"status": "ok", "reason": "", "missing_analysis_columns": [], "non_null_ratios": ratios}


def _iso_date(value: str) -> str:
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text
