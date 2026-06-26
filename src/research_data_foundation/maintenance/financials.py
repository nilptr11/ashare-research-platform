from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core import FoundationRegistry
from ..domains import default_registry
from ..ingestion import IngestionRunner
from ..sources import SourceAdapter
from ..storage import MartStore, StorageError
from .ashare_core import MaintenanceError, compact_date
from .main_business import normalize_security_ids


@dataclass(frozen=True)
class FinancialTask:
    dataset_id: str
    recipe_id: str


FINANCIAL_TASKS = (
    FinancialTask("ashare.income_statement", "tushare.income.to_ashare_income_statement"),
    FinancialTask("ashare.balance_sheet", "tushare.balancesheet.to_ashare_balance_sheet"),
    FinancialTask("ashare.cash_flow", "tushare.cashflow.to_ashare_cash_flow"),
    FinancialTask("ashare.financial_indicator", "tushare.fina_indicator.to_ashare_financial_indicator"),
    FinancialTask("ashare.earnings_express", "tushare.express.to_ashare_earnings_express"),
    FinancialTask("ashare.dividend", "tushare.dividend.to_ashare_dividend"),
    FinancialTask("ashare.audit_opinion", "tushare.fina_audit.to_ashare_audit_opinion"),
    FinancialTask("ashare.disclosure_date", "tushare.disclosure_date.to_ashare_disclosure_date"),
    FinancialTask("ashare.earnings_forecast", "tushare.forecast.to_ashare_earnings_forecast"),
)


class AShareFinancialsMaintainer:
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
        period: str | None = None,
        as_of: str | None = None,
        security_ids: tuple[str, ...] = (),
        stock_snapshot_date: str | None = None,
        dataset_ids: tuple[str, ...] = (),
        limit: int = 0,
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        normalized_period = compact_date(period) if period else financial_period_for_as_of(as_of)
        tasks = self._tasks(dataset_ids)
        securities = normalize_security_ids(security_ids)
        if not securities:
            if not stock_snapshot_date:
                raise MaintenanceError("security_ids or stock_snapshot_date is required")
            securities = self._stock_pool(compact_date(stock_snapshot_date))
        if limit and limit > 0:
            securities = securities[:limit]
        if not securities:
            return {
                "schema": "rdf.ashare_financials_maintenance_run.v1",
                "period": normalized_period,
                "as_of": compact_date(as_of) if as_of else None,
                "stock_snapshot_date": stock_snapshot_date,
                "dataset_ids": [task.dataset_id for task in tasks],
                "securities": [],
                "status": "blocked",
                "message": "no securities to maintain",
                "tasks": [],
            }

        results: list[dict[str, Any]] = []
        for security_id in securities:
            for task in tasks:
                partition = {"period": normalized_period, "security_id": security_id}
                if self._partition_exists(task.dataset_id, partition) and not refresh:
                    results.append(task_payload(task, partition, status="skipped"))
                    continue
                try:
                    result = self.runner.run_recipe(task.recipe_id, partition=partition, refresh=refresh)
                    results.append(task_payload(task, partition, status="ready", rows=result.rows, result=result.to_dict()))
                except Exception as error:
                    results.append(task_payload(task, partition, status="failed", message=str(error)))
                    if not continue_on_error:
                        raise

        failures = [item for item in results if item["status"] == "failed"]
        ready = [item for item in results if item["status"] in {"ready", "skipped"}]
        status = "blocked" if failures and not ready else "warning" if failures else "ready"
        return {
            "schema": "rdf.ashare_financials_maintenance_run.v1",
            "period": normalized_period,
            "as_of": compact_date(as_of) if as_of else None,
            "stock_snapshot_date": stock_snapshot_date,
            "dataset_ids": [task.dataset_id for task in tasks],
            "securities": list(securities),
            "status": status,
            "tasks": results,
        }

    def _tasks(self, dataset_ids: tuple[str, ...]) -> tuple[FinancialTask, ...]:
        if not dataset_ids:
            return FINANCIAL_TASKS
        requested = set(dataset_ids)
        tasks = tuple(task for task in FINANCIAL_TASKS if task.dataset_id in requested)
        missing = sorted(requested - {task.dataset_id for task in tasks})
        if missing:
            raise MaintenanceError(f"unknown financial dataset ids: {missing}")
        return tasks

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


def financial_period_for_as_of(as_of: str | None) -> str:
    if not as_of:
        raise MaintenanceError("period or as_of is required")
    normalized = compact_date(as_of)
    value = datetime.strptime(normalized, "%Y%m%d").date()
    year = value.year
    month_day = value.strftime("%m%d")
    if month_day >= "1101":
        return f"{year}0930"
    if month_day >= "0901":
        return f"{year}0630"
    if month_day >= "0501":
        return f"{year}0331"
    return f"{year - 1}0930"


def task_payload(
    task: FinancialTask,
    partition: dict[str, str],
    *,
    status: str,
    rows: int | None = None,
    result: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": task.dataset_id,
        "recipe_id": task.recipe_id,
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
