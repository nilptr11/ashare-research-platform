from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import FoundationRegistry
from ..domains import default_registry
from ..ingestion import IngestionRunner
from ..sources import SourceAdapter
from ..storage import MartStore, StorageError
from .ashare_core import MaintenanceError, compact_date


class AShareMainBusinessMaintainer:
    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        registry: FoundationRegistry | None = None,
        adapters: dict[str, SourceAdapter] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.registry = registry or default_registry()
        self.runner = IngestionRunner(data_dir=data_dir, registry=self.registry, adapters=adapters)
        self.mart_store = MartStore(data_dir, self.registry)

    def maintain(
        self,
        *,
        period: str,
        security_ids: tuple[str, ...] = (),
        stock_snapshot_date: str | None = None,
        segment_types: tuple[str, ...] = ("P", "D"),
        limit: int = 0,
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        normalized_period = compact_date(period)
        normalized_segments = normalize_segment_types(segment_types)
        securities = normalize_security_ids(security_ids)
        if not securities:
            if not stock_snapshot_date:
                raise MaintenanceError("security_ids or stock_snapshot_date is required")
            securities = self._stock_pool(compact_date(stock_snapshot_date))
        if limit and limit > 0:
            securities = securities[:limit]
        if not securities:
            return {
                "schema": "rdf.ashare_main_business_maintenance_run.v1",
                "period": normalized_period,
                "stock_snapshot_date": stock_snapshot_date,
                "segment_types": list(normalized_segments),
                "securities": [],
                "status": "blocked",
                "message": "no securities to maintain",
                "tasks": [],
            }

        tasks: list[dict[str, Any]] = []
        for security_id in securities:
            for segment_type in normalized_segments:
                partition = {"period": normalized_period, "security_id": security_id, "segment_type": segment_type}
                if self._partition_exists("ashare.main_business", partition) and not refresh:
                    tasks.append(task_payload(partition, status="skipped"))
                    continue
                try:
                    result = self.runner.run_recipe(
                        "tushare.fina_mainbz.to_ashare_main_business",
                        partition=partition,
                        refresh=refresh,
                    )
                    tasks.append(task_payload(partition, status="ready", rows=result.rows, result=result.to_dict()))
                except Exception as error:
                    tasks.append(task_payload(partition, status="failed", message=str(error)))
                    if not continue_on_error:
                        raise

        failures = [task for task in tasks if task["status"] == "failed"]
        ready = [task for task in tasks if task["status"] in {"ready", "skipped"}]
        status = "blocked" if failures and not ready else "warning" if failures else "ready"
        return {
            "schema": "rdf.ashare_main_business_maintenance_run.v1",
            "period": normalized_period,
            "stock_snapshot_date": stock_snapshot_date,
            "segment_types": list(normalized_segments),
            "securities": list(securities),
            "status": status,
            "tasks": tasks,
        }

    def _stock_pool(self, snapshot_date: str) -> tuple[str, ...]:
        try:
            frame = self.mart_store.read("ashare.stock_basic", {"snapshot_date": snapshot_date}, columns=["security_id"])
        except StorageError as error:
            raise MaintenanceError(f"missing stock_basic snapshot: {snapshot_date}") from error
        if frame.empty or "security_id" not in frame.columns:
            return ()
        return normalize_security_ids(tuple(str(value) for value in frame["security_id"].dropna()))

    def _partition_exists(self, dataset_id: str, partition: dict[str, str]) -> bool:
        try:
            path = self.mart_store.partition_path(dataset_id, partition)
        except Exception:
            return False
        return (path / "part.parquet").exists() and (path / "_meta.json").exists()


def normalize_segment_types(values: tuple[str, ...]) -> tuple[str, ...]:
    output: list[str] = []
    for value in values:
        for item in str(value).split(","):
            text = item.strip().upper()
            if not text:
                continue
            if text not in {"P", "D"}:
                raise MaintenanceError(f"invalid segment_type {text!r}; expected P or D")
            if text not in output:
                output.append(text)
    if not output:
        raise MaintenanceError("at least one segment type is required")
    return tuple(output)


def normalize_security_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    output: list[str] = []
    for value in values:
        text = str(value).strip().upper()
        if not text:
            continue
        if "." not in text and len(text) == 6 and text.isdigit():
            if text.startswith("6"):
                text = f"{text}.SH"
            elif text.startswith(("0", "3")):
                text = f"{text}.SZ"
            elif text.startswith(("4", "8")):
                text = f"{text}.BJ"
        if text not in output:
            output.append(text)
    return tuple(output)


def task_payload(
    partition: dict[str, str],
    *,
    status: str,
    rows: int | None = None,
    result: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": "ashare.main_business",
        "recipe_id": "tushare.fina_mainbz.to_ashare_main_business",
        "partition": dict(partition),
        "status": status,
    }
    if rows is not None:
        payload["rows"] = rows
    if result is not None:
        payload["result"] = result
    if message:
        payload["message"] = message
    return payload
