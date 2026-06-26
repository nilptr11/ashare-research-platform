from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..core import FoundationRegistry
from ..domains import default_registry
from ..ingestion import IngestionRunner
from ..sources import SourceAdapter
from ..storage import MartStore
from .ashare_core import compact_date


class IndustryReportIndexMaintainer:
    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        registry: FoundationRegistry | None = None,
        adapters: dict[str, SourceAdapter] | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.runner = IngestionRunner(data_dir=data_dir, registry=self.registry, adapters=adapters)
        self.mart_store = MartStore(data_dir, self.registry)

    def maintain(
        self,
        *,
        query_date: str,
        begin: str | None = None,
        lookback_days: int = 30,
        max_pages: int = 1,
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        normalized_query_date = compact_date(query_date)
        if lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        begin_date = normalize_hyphen_date(begin) if begin else query_begin_date(normalized_query_date, lookback_days)
        end_date = compact_to_hyphen(normalized_query_date)
        partition = {"query_date": normalized_query_date}
        params = {"begin": begin_date, "end": end_date, "max_pages": str(max_pages)}

        if self._partition_exists("industry.eastmoney_report_index", partition) and not refresh:
            task = task_payload(partition, status="skipped")
            status = "ready"
        else:
            try:
                result = self.runner.run_recipe(
                    "eastmoney.reportapi.industry_reports.to_report_index",
                    partition=partition,
                    params=params,
                    refresh=refresh,
                )
                task = task_payload(partition, status="ready", rows=result.rows, result=result.to_dict())
                status = "ready"
            except Exception as error:
                task = task_payload(partition, status="failed", message=str(error))
                status = "blocked"
                if not continue_on_error:
                    raise

        return {
            "schema": "rdf.industry_report_index_maintenance_run.v1",
            "query_date": normalized_query_date,
            "begin": begin_date,
            "end": end_date,
            "max_pages": max_pages,
            "status": status,
            "boundary": "Eastmoney report index is an evidence seed and triage input, not company business exposure proof.",
            "tasks": [task],
        }

    def _partition_exists(self, dataset_id: str, partition: dict[str, str]) -> bool:
        try:
            path = self.mart_store.partition_path(dataset_id, partition)
        except Exception:
            return False
        return (path / "part.parquet").exists() and (path / "_meta.json").exists()


def query_begin_date(query_date: str, lookback_days: int) -> str:
    value = datetime.strptime(compact_date(query_date), "%Y%m%d").date() - timedelta(days=lookback_days)
    return value.isoformat()


def compact_to_hyphen(value: str) -> str:
    normalized = compact_date(value)
    return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:]}"


def normalize_hyphen_date(value: str | None) -> str:
    if not value:
        raise ValueError("date value is required")
    return compact_to_hyphen(value)


def task_payload(
    partition: dict[str, str],
    *,
    status: str,
    rows: int | None = None,
    result: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": "industry.eastmoney_report_index",
        "recipe_id": "eastmoney.reportapi.industry_reports.to_report_index",
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
