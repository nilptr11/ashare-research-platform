from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..core import FoundationRegistry
from ..domains import default_registry
from ..features import FeatureBuilder, FeatureRegistry, FeatureStore
from ..ingestion import IngestionRunner
from ..sources import SourceAdapter
from ..storage import MartStore, StorageError


class MaintenanceError(RuntimeError):
    """Raised when maintenance cannot proceed."""


DEFAULT_WINDOWS = (5, 20, 60)
ASHARE_CORE_FEATURE_IDS = (
    "ashare.daily_momentum",
    "ashare.market_strength",
    "ashare.industry_strength",
    "ashare.concept_strength",
    "ashare.limit_sentiment",
)


@dataclass(frozen=True)
class MaintenanceTask:
    dataset_id: str
    recipe_id: str
    group: str
    partition_kind: str
    required: bool = False


ASHARE_CORE_TASKS = (
    MaintenanceTask("ashare.trade_calendar", "tushare.trade_cal.to_ashare_trade_calendar", "calendar", "exchange", required=True),
    MaintenanceTask("ashare.stock_basic", "tushare.stock_basic.to_ashare_stock_basic", "identity", "snapshot_date", required=True),
    MaintenanceTask("ashare.daily", "tushare.daily.to_ashare_daily", "stock_daily", "trade_date", required=True),
    MaintenanceTask("ashare.daily_basic", "tushare.daily_basic.to_ashare_daily_basic", "stock_daily", "trade_date", required=True),
    MaintenanceTask("ashare.index_daily", "tushare.index_daily.to_ashare_index_daily", "index", "trade_date", required=True),
    MaintenanceTask("ashare.index_daily_basic", "tushare.index_dailybasic.to_ashare_index_daily_basic", "index", "trade_date", required=True),
    MaintenanceTask("ashare.sw_daily", "tushare.sw_daily.to_ashare_sw_daily", "industry", "trade_date", required=True),
    MaintenanceTask("ashare.ci_daily", "tushare.ci_daily.to_ashare_ci_daily", "industry", "trade_date", required=True),
    MaintenanceTask("ashare.dc_index", "tushare.dc_index.to_ashare_dc_index", "theme", "trade_date", required=True),
    MaintenanceTask("ashare.limit_list_d", "tushare.limit_list_d.to_ashare_limit_list_d", "short_term", "trade_date"),
    MaintenanceTask("ashare.limit_list_ths", "tushare.limit_list_ths.to_ashare_limit_list_ths", "short_term", "trade_date"),
    MaintenanceTask("ashare.adj_factor", "tushare.adj_factor.to_ashare_adj_factor", "stock_daily", "trade_date"),
    MaintenanceTask("ashare.price_limits", "tushare.stk_limit.to_ashare_price_limits", "stock_daily", "trade_date"),
    MaintenanceTask("ashare.moneyflow_dc", "tushare.moneyflow_dc.to_ashare_moneyflow_dc", "moneyflow", "trade_date"),
    MaintenanceTask("ashare.top_list", "tushare.top_list.to_ashare_top_list", "short_term", "trade_date"),
    MaintenanceTask("ashare.hsgt_top10", "tushare.hsgt_top10.to_ashare_hsgt_top10", "northbound", "trade_date"),
    MaintenanceTask("ashare.northbound_eligible", "tushare.stock_hsgt.to_ashare_northbound_eligible", "northbound", "trade_date"),
    MaintenanceTask("ashare.margin_detail", "tushare.margin_detail.to_ashare_margin_detail", "leverage", "trade_date"),
)


class AShareCoreMaintainer:
    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        registry: FoundationRegistry | None = None,
        adapters: dict[str, SourceAdapter] | None = None,
        tasks: tuple[MaintenanceTask, ...] = ASHARE_CORE_TASKS,
    ) -> None:
        self.data_dir = data_dir
        self.registry = registry or default_registry()
        self.tasks = tasks
        self.runner = IngestionRunner(data_dir=data_dir, registry=self.registry, adapters=adapters)
        self.mart_store = MartStore(data_dir, self.registry)

    def maintain(
        self,
        *,
        as_of: str,
        lookback_trading_days: int = 60,
        refresh: bool = False,
        continue_on_error: bool = False,
        build_features: bool = True,
        windows: tuple[int, ...] = DEFAULT_WINDOWS,
    ) -> dict[str, Any]:
        normalized_as_of = compact_date(as_of)
        calendar_start_date = calendar_fetch_start(normalized_as_of, lookback_trading_days)
        results: list[dict[str, Any]] = []

        calendar_task = self._task_by_kind("exchange")
        try:
            results.append(
                self._run_calendar_task(
                    calendar_task,
                    start_date=calendar_start_date,
                    as_of=normalized_as_of,
                    refresh=refresh,
                )
            )
        except Exception as error:
            results.append(failed_task(calendar_task, {"exchange": "SSE"}, error))
            if not continue_on_error:
                raise

        trade_dates = self.trade_dates(as_of=normalized_as_of, lookback_trading_days=lookback_trading_days)
        if len(trade_dates) < lookback_trading_days:
            message = (
                f"trade calendar has {len(trade_dates)} open dates in requested window; "
                f"expected {lookback_trading_days}"
            )
            if not continue_on_error:
                raise MaintenanceError(message)
            status_payload = self.status(as_of=normalized_as_of, lookback_trading_days=lookback_trading_days, windows=windows)
            return {
                "schema": "rdf.ashare_core_maintenance_run.v1",
                "as_of": normalized_as_of,
                "lookback_trading_days": lookback_trading_days,
                "calendar_start_date": calendar_start_date,
                "start_date": trade_dates[0] if trade_dates else None,
                "trade_dates": trade_dates,
                "status": "blocked",
                "refresh": refresh,
                "message": message,
                "tasks": results,
                "features": [],
                "status_check": status_payload,
            }

        for task in self.tasks:
            if task.partition_kind == "exchange":
                continue
            partitions = self._partitions_for_task(task, as_of=normalized_as_of, trade_dates=trade_dates)
            for partition in partitions:
                if self._partition_exists(task.dataset_id, partition) and not refresh:
                    results.append(skipped_task(task, partition))
                    continue
                try:
                    result = self.runner.run_recipe(
                        task.recipe_id,
                        partition=partition,
                        refresh=refresh,
                    )
                    results.append(
                        {
                            "dataset_id": task.dataset_id,
                            "recipe_id": task.recipe_id,
                            "group": task.group,
                            "required": task.required,
                            "partition": dict(partition),
                            "status": "ready",
                            "rows": result.rows,
                            "result": result.to_dict(),
                        }
                    )
                except Exception as error:
                    results.append(failed_task(task, partition, error))
                    if task.required and not continue_on_error:
                        raise

        feature_results = []
        if build_features:
            feature_results = self._build_features(as_of=normalized_as_of, windows=windows, refresh=refresh, continue_on_error=continue_on_error)

        status_payload = self.status(as_of=normalized_as_of, lookback_trading_days=lookback_trading_days, windows=windows)
        run_failures = [item for item in results if item["status"] == "failed"]
        payload_status = "blocked" if any(item.get("required") for item in run_failures) or status_payload["status"] == "blocked" else status_payload["status"]
        return {
            "schema": "rdf.ashare_core_maintenance_run.v1",
            "as_of": normalized_as_of,
            "lookback_trading_days": lookback_trading_days,
            "calendar_start_date": calendar_start_date,
            "start_date": trade_dates[0],
            "trade_dates": trade_dates,
            "status": payload_status,
            "refresh": refresh,
            "tasks": results,
            "features": feature_results,
            "status_check": status_payload,
        }

    def status(
        self,
        *,
        as_of: str,
        lookback_trading_days: int = 60,
        windows: tuple[int, ...] = DEFAULT_WINDOWS,
    ) -> dict[str, Any]:
        normalized_as_of = compact_date(as_of)
        calendar_start_date = calendar_fetch_start(normalized_as_of, lookback_trading_days)
        trade_dates = self.trade_dates(as_of=normalized_as_of, lookback_trading_days=lookback_trading_days, fallback_to_natural=True)
        dataset_checks = [self._check_task(task, as_of=normalized_as_of, trade_dates=trade_dates) for task in self.tasks]
        feature_checks = self._feature_checks(as_of=normalized_as_of, windows=windows)

        coverage_blocking = []
        if len(trade_dates) < lookback_trading_days:
            coverage_blocking.append(
                {
                    "dataset_id": "ashare.trade_calendar",
                    "recipe_id": "tushare.trade_cal.to_ashare_trade_calendar",
                    "group": "calendar",
                    "required": True,
                    "status": "partial",
                    "expected_trade_dates": lookback_trading_days,
                    "ready_trade_dates": len(trade_dates),
                    "missing_count": lookback_trading_days - len(trade_dates),
                    "missing_partitions": [],
                    "degraded_count": 0,
                    "degraded_partitions": [],
                    "rows": len(trade_dates),
                }
            )
        blocking = [item for item in dataset_checks if item["required"] and item["status"] in {"missing", "partial", "failed"}]
        degraded = [item for item in dataset_checks if item["status"] == "degraded"]
        warnings = [item for item in dataset_checks if not item["required"] and item["status"] in {"missing", "partial", "failed"}]
        feature_warnings = [item for item in feature_checks if item["status"] != "ready"]
        blocking = [*coverage_blocking, *blocking]
        if blocking:
            status = "blocked"
        elif degraded or feature_warnings:
            status = "degraded"
        elif warnings:
            status = "warning"
        else:
            status = "ready"
        return {
            "schema": "rdf.ashare_core_maintenance_status.v1",
            "as_of": normalized_as_of,
            "lookback_trading_days": lookback_trading_days,
            "calendar_start_date": calendar_start_date,
            "start_date": trade_dates[0] if trade_dates else None,
            "trade_dates": trade_dates,
            "status": status,
            "datasets": dataset_checks,
            "features": feature_checks,
            "blocking": blocking,
            "degraded": degraded,
            "warnings": [*warnings, *feature_warnings],
        }

    def trade_dates(self, *, as_of: str, lookback_trading_days: int, fallback_to_natural: bool = False) -> list[str]:
        normalized_as_of = compact_date(as_of)
        require_positive_lookback(lookback_trading_days)
        try:
            frame = self.mart_store.read("ashare.trade_calendar", {"exchange": "SSE"})
        except StorageError:
            return natural_lookback_dates(normalized_as_of, lookback_trading_days) if fallback_to_natural else []
        if frame.empty or "cal_date" not in frame.columns or "is_open" not in frame.columns:
            return natural_lookback_dates(normalized_as_of, lookback_trading_days) if fallback_to_natural else []
        working = frame.copy()
        working["cal_date"] = working["cal_date"].astype(str).map(compact_date)
        values = [
            date
            for date, is_open in zip(working["cal_date"], working["is_open"], strict=False)
            if date <= normalized_as_of and str(is_open) == "1"
        ]
        return sorted(set(values))[-lookback_trading_days:]

    def _run_calendar_task(self, task: MaintenanceTask, *, start_date: str, as_of: str, refresh: bool) -> dict[str, Any]:
        partition = {"exchange": "SSE"}
        if self._partition_exists(task.dataset_id, partition) and not refresh and self._calendar_covers(start_date=start_date, as_of=as_of):
            return skipped_task(task, partition)
        result = self.runner.run_recipe(
            task.recipe_id,
            partition=partition,
            params={"start_date": start_date, "end_date": as_of},
            refresh=refresh or self._partition_exists(task.dataset_id, partition),
        )
        return {
            "dataset_id": task.dataset_id,
            "recipe_id": task.recipe_id,
            "group": task.group,
            "required": task.required,
            "partition": partition,
            "status": "ready",
            "rows": result.rows,
            "result": result.to_dict(),
        }

    def _calendar_covers(self, *, start_date: str, as_of: str) -> bool:
        try:
            frame = self.mart_store.read("ashare.trade_calendar", {"exchange": "SSE"}, columns=["cal_date"])
        except StorageError:
            return False
        if frame.empty:
            return False
        dates = sorted(compact_date(str(value)) for value in frame["cal_date"].dropna())
        return bool(dates) and dates[0] <= start_date and dates[-1] >= as_of

    def _build_features(
        self,
        *,
        as_of: str,
        windows: tuple[int, ...],
        refresh: bool,
        continue_on_error: bool,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        registry = FeatureRegistry.builtin()
        store = FeatureStore(self.data_dir)
        builder = FeatureBuilder(data_dir=self.data_dir, registry=self.registry, feature_registry=registry, feature_store=store)
        for feature_id in ASHARE_CORE_FEATURE_IDS:
            spec = registry.require(feature_id)
            for window in windows:
                if self._feature_exists(spec.id, domain=spec.domain, as_of=as_of, window=window) and not refresh:
                    output.append({"feature_id": feature_id, "window": window, "status": "skipped"})
                    continue
                try:
                    result = builder.build(feature_id, as_of=as_of, window=window, refresh=refresh)
                    output.append({"feature_id": feature_id, "window": window, "status": "ready", "result": result.to_dict()})
                except Exception as error:
                    output.append({"feature_id": feature_id, "window": window, "status": "failed", "message": str(error)})
                    if not continue_on_error:
                        raise
        return output

    def _feature_checks(self, *, as_of: str, windows: tuple[int, ...]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        registry = FeatureRegistry.builtin()
        store = FeatureStore(self.data_dir)
        for feature_id in ASHARE_CORE_FEATURE_IDS:
            spec = registry.require(feature_id)
            for window in windows:
                try:
                    meta = store.load_meta(feature_id, domain=spec.domain, as_of=as_of, window=window)
                    quality = dict(meta.quality or {})
                    output.append(
                        {
                            "feature_id": feature_id,
                            "window": window,
                            "status": "ready" if quality.get("status") == "ok" else str(quality.get("status", "degraded")),
                            "rows": meta.rows,
                            "quality": quality,
                        }
                    )
                except Exception as error:
                    output.append({"feature_id": feature_id, "window": window, "status": "missing", "message": str(error)})
        return output

    def _check_task(self, task: MaintenanceTask, *, as_of: str, trade_dates: list[str]) -> dict[str, Any]:
        partitions = self._partitions_for_task(task, as_of=as_of, trade_dates=trade_dates)
        missing: list[dict[str, str]] = []
        degraded: list[dict[str, Any]] = []
        rows = 0
        for partition in partitions:
            if not self._partition_exists(task.dataset_id, partition):
                missing.append(partition)
                continue
            try:
                meta = self.mart_store.read_meta(task.dataset_id, partition)
                rows += int(meta.get("rows", 0) or 0)
                if meta.get("quality", {}).get("status") != "ok":
                    degraded.append({"partition": partition, "quality": meta.get("quality", {})})
            except Exception as error:
                missing.append(partition | {"error": str(error)})
        expected = len(partitions)
        ready = expected - len(missing)
        if missing and ready:
            status = "partial"
        elif missing:
            status = "missing"
        elif degraded:
            status = "degraded"
        else:
            status = "ready"
        return {
            "dataset_id": task.dataset_id,
            "recipe_id": task.recipe_id,
            "group": task.group,
            "required": task.required,
            "status": status,
            "expected_partitions": expected,
            "ready_partitions": ready,
            "missing_partitions": missing[:20],
            "missing_count": len(missing),
            "degraded_partitions": degraded[:20],
            "degraded_count": len(degraded),
            "rows": rows,
        }

    def _partitions_for_task(self, task: MaintenanceTask, *, as_of: str, trade_dates: list[str]) -> list[dict[str, str]]:
        if task.partition_kind == "exchange":
            return [{"exchange": "SSE"}]
        if task.partition_kind == "snapshot_date":
            return [{"snapshot_date": as_of}]
        if task.partition_kind == "trade_date":
            return [{"trade_date": date} for date in trade_dates]
        raise MaintenanceError(f"unsupported partition kind: {task.partition_kind}")

    def _task_by_kind(self, partition_kind: str) -> MaintenanceTask:
        for task in self.tasks:
            if task.partition_kind == partition_kind:
                return task
        raise MaintenanceError(f"maintenance task not found for partition kind {partition_kind!r}")

    def _partition_exists(self, dataset_id: str, partition: dict[str, str]) -> bool:
        try:
            path = self.mart_store.partition_path(dataset_id, partition)
        except Exception:
            return False
        return (path / "part.parquet").exists() and (path / "_meta.json").exists()

    def _feature_exists(self, feature_id: str, *, domain: str, as_of: str, window: int) -> bool:
        path = FeatureStore(self.data_dir).partition_path(feature_id, domain=domain, as_of=as_of, window=window)
        return (path / "part.parquet").exists() and (path / "_meta.json").exists()


def skipped_task(task: MaintenanceTask, partition: dict[str, str]) -> dict[str, Any]:
    return {
        "dataset_id": task.dataset_id,
        "recipe_id": task.recipe_id,
        "group": task.group,
        "required": task.required,
        "partition": dict(partition),
        "status": "skipped",
    }


def failed_task(task: MaintenanceTask, partition: dict[str, str], error: Exception) -> dict[str, Any]:
    return {
        "dataset_id": task.dataset_id,
        "recipe_id": task.recipe_id,
        "group": task.group,
        "required": task.required,
        "partition": dict(partition),
        "status": "failed",
        "message": str(error),
    }


def compact_date(value: str) -> str:
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y%m%d")
    if len(text) >= 8:
        return datetime.strptime(text[:8], "%Y%m%d").strftime("%Y%m%d")
    raise MaintenanceError(f"invalid date {value!r}")


def calendar_fetch_start(as_of: str, lookback_trading_days: int) -> str:
    require_positive_lookback(lookback_trading_days)
    end = datetime.strptime(compact_date(as_of), "%Y%m%d")
    natural_days = max(lookback_trading_days * 3, lookback_trading_days + 30)
    return (end - timedelta(days=natural_days - 1)).strftime("%Y%m%d")


def natural_lookback_dates(as_of: str, lookback_trading_days: int) -> list[str]:
    require_positive_lookback(lookback_trading_days)
    end = datetime.strptime(compact_date(as_of), "%Y%m%d").date()
    start = end - timedelta(days=lookback_trading_days - 1)
    return natural_dates(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))


def require_positive_lookback(lookback_trading_days: int) -> None:
    if lookback_trading_days <= 0:
        raise MaintenanceError("lookback_trading_days must be positive")


def natural_dates(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(compact_date(start_date), "%Y%m%d").date()
    end = datetime.strptime(compact_date(end_date), "%Y%m%d").date()
    if start > end:
        return []
    output: list[str] = []
    current = start
    while current <= end:
        output.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return output
