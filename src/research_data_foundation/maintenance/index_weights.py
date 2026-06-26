from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import FoundationRegistry
from ..domains import default_registry
from ..sources import SourceAdapter, default_source_adapters
from ..storage import MartStore, RawStore, SourceFetchResult, StagingStore, StorageError
from ..storage.tables import now_iso
from .ashare_core import MaintenanceError, compact_date


DEFAULT_INDEX_CODES = ("000016.SH", "000300.SH", "000905.SH", "000852.SH")


class AShareIndexWeightsMaintainer:
    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        registry: FoundationRegistry | None = None,
        adapters: dict[str, SourceAdapter] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.registry = registry or default_registry()
        self.adapters = adapters or default_source_adapters()
        self.raw_store = RawStore(data_dir)
        self.staging_store = StagingStore(data_dir, self.registry)
        self.mart_store = MartStore(data_dir, self.registry)

    def maintain(
        self,
        *,
        snapshot_date: str,
        start_date: str | None = None,
        lookback_days: int = 90,
        index_codes: tuple[str, ...] = (),
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        normalized_snapshot_date = compact_date(snapshot_date)
        normalized_start_date = compact_date(start_date) if start_date else start_date_for(normalized_snapshot_date, lookback_days)
        normalized_index_codes = normalize_index_codes(index_codes or DEFAULT_INDEX_CODES)
        partition = {"snapshot_date": normalized_snapshot_date}
        if self._partition_exists(partition) and not refresh:
            return {
                "schema": "rdf.ashare_index_weights_maintenance_run.v1",
                "snapshot_date": normalized_snapshot_date,
                "start_date": normalized_start_date,
                "index_codes": list(normalized_index_codes),
                "status": "ready",
                "tasks": [],
                "result": {"status": "skipped", "partition": partition},
            }

        adapter = self._adapter("tushare")
        raw_frames: list[pd.DataFrame] = []
        snapshot_frames: list[pd.DataFrame] = []
        tasks: list[dict[str, Any]] = []
        latest_weight_dates: dict[str, str] = {}

        for index_code in normalized_index_codes:
            try:
                frame, page_rows = fetch_index_weight(
                    adapter,
                    index_code=index_code,
                    start_date=normalized_start_date,
                    end_date=normalized_snapshot_date,
                )
                raw_frames.append(frame)
                if frame.empty:
                    tasks.append(task_payload(index_code, status="missing", rows=0, page_rows=page_rows))
                    if not continue_on_error:
                        raise MaintenanceError(f"index_weight returned no rows for {index_code}")
                    continue
                latest_date = str(frame["trade_date"].dropna().astype(str).max())
                latest_weight_dates[index_code] = latest_date
                selected = frame[frame["trade_date"].astype(str) == latest_date].copy()
                snapshot_frames.append(selected)
                tasks.append(task_payload(index_code, status="ready", rows=int(len(selected)), latest_weight_date=latest_date, page_rows=page_rows))
            except Exception as error:
                tasks.append(task_payload(index_code, status="failed", message=str(error)))
                if not continue_on_error:
                    raise

        ready_tasks = [task for task in tasks if task["status"] == "ready"]
        failures = [task for task in tasks if task["status"] in {"failed", "missing"}]
        if not ready_tasks:
            return {
                "schema": "rdf.ashare_index_weights_maintenance_run.v1",
                "snapshot_date": normalized_snapshot_date,
                "start_date": normalized_start_date,
                "index_codes": list(normalized_index_codes),
                "status": "blocked",
                "tasks": tasks,
                "message": "no index weight snapshots were available",
            }

        raw_frame = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()
        normalized = normalize_index_weight_snapshot(
            pd.concat(snapshot_frames, ignore_index=True),
            snapshot_date=normalized_snapshot_date,
        )
        fetch_result = SourceFetchResult(
            source_id="tushare",
            api_name="index_weight",
            params={
                "snapshot_date": normalized_snapshot_date,
                "start_date": normalized_start_date,
                "end_date": normalized_snapshot_date,
                "index_codes": list(normalized_index_codes),
            },
            requested_at=now_iso(),
            frame=raw_frame,
            metadata={
                "adapter": "index_weight_snapshot",
                "latest_weight_dates": latest_weight_dates,
                "tasks": tasks,
            },
        )
        raw_path = self.raw_store.write(fetch_result)
        lineage = {
            "source_id": "tushare",
            "source_api": "index_weight",
            "maintainer": "ashare-index-weights",
            "snapshot_date": normalized_snapshot_date,
            "start_date": normalized_start_date,
            "index_codes": list(normalized_index_codes),
            "latest_weight_dates": latest_weight_dates,
            "raw_path": str(raw_path),
        }
        staging_path = self.staging_store.publish("ashare.index_weights", normalized, partition=partition, lineage=lineage, refresh=refresh)
        mart_lineage = dict(lineage) | {"staging_path": str(staging_path)}
        mart_path = self.mart_store.publish("ashare.index_weights", normalized, partition=partition, lineage=mart_lineage, refresh=refresh)
        status = "warning" if failures else "ready"
        return {
            "schema": "rdf.ashare_index_weights_maintenance_run.v1",
            "snapshot_date": normalized_snapshot_date,
            "start_date": normalized_start_date,
            "index_codes": list(normalized_index_codes),
            "status": status,
            "rows": int(len(normalized)),
            "partition": partition,
            "raw_path": str(raw_path),
            "staging_path": str(staging_path),
            "mart_path": str(mart_path),
            "latest_weight_dates": latest_weight_dates,
            "tasks": tasks,
        }

    def _adapter(self, source_id: str) -> SourceAdapter:
        try:
            return self.adapters[source_id]
        except KeyError as error:
            raise MaintenanceError(f"source adapter not configured: {source_id}") from error

    def _partition_exists(self, partition: dict[str, str]) -> bool:
        try:
            path = self.mart_store.partition_path("ashare.index_weights", partition)
        except StorageError:
            return False
        return (path / "part.parquet").exists() and (path / "_meta.json").exists()


def fetch_index_weight(
    adapter: SourceAdapter,
    *,
    index_code: str,
    start_date: str,
    end_date: str,
    limit: int = 5000,
    max_pages: int = 10,
) -> tuple[pd.DataFrame, list[int]]:
    frames: list[pd.DataFrame] = []
    page_rows: list[int] = []
    fields = ("index_code", "con_code", "trade_date", "weight")
    for page in range(max_pages):
        params = {
            "index_code": index_code,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "offset": page * limit,
        }
        result = adapter.fetch("index_weight", params, fields=fields)
        if result.source_id != "tushare" or result.api_name != "index_weight":
            raise MaintenanceError(f"unexpected source result for index_weight: {result.source_id}/{result.api_name}")
        frames.append(result.frame)
        page_rows.append(result.rows)
        if result.rows < limit:
            break
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=fields), page_rows)


def normalize_index_weight_snapshot(frame: pd.DataFrame, *, snapshot_date: str) -> pd.DataFrame:
    output = frame.rename(columns={"index_code": "index_id", "con_code": "security_id", "trade_date": "weight_trade_date"}).copy()
    output["snapshot_date"] = snapshot_date
    columns = ["snapshot_date", "index_id", "security_id", "weight_trade_date", "weight"]
    return output[columns].sort_values(["index_id", "weight", "security_id"], ascending=[True, False, True]).reset_index(drop=True)


def normalize_index_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    output: list[str] = []
    for value in values:
        text = str(value).strip().upper()
        if text and text not in output:
            output.append(text)
    return tuple(output)


def start_date_for(snapshot_date: str, lookback_days: int) -> str:
    if lookback_days <= 0:
        raise MaintenanceError("lookback_days must be positive")
    date = datetime.strptime(snapshot_date, "%Y%m%d").date()
    return (date - timedelta(days=lookback_days)).strftime("%Y%m%d")


def task_payload(
    index_code: str,
    *,
    status: str,
    rows: int | None = None,
    latest_weight_date: str | None = None,
    page_rows: list[int] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"index_code": index_code, "status": status}
    if rows is not None:
        payload["rows"] = rows
    if latest_weight_date:
        payload["latest_weight_date"] = latest_weight_date
    if page_rows is not None:
        payload["page_rows"] = page_rows
    if message:
        payload["message"] = message
    return payload
