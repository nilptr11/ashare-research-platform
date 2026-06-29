from __future__ import annotations

from typing import Any

from ..core.registry import FoundationRegistry
from ..core.schemas import DatasetContract
from ..storage import MartStore, StorageError


DATE_PARTITION_KEYS = ("trade_date", "query_date", "publish_date", "snapshot_date")


def feature_input_partition_key(contract: DatasetContract) -> str | None:
    for key in DATE_PARTITION_KEYS:
        if key in contract.partition_keys:
            return key
    return contract.partition_keys[0] if len(contract.partition_keys) == 1 else None


def feature_window_coverage(
    *,
    mart_store: MartStore,
    registry: FoundationRegistry,
    dataset_id: str,
    as_of: str,
    window: int,
    partition_key: str | None = None,
) -> dict[str, Any]:
    try:
        contract = registry.require_dataset(dataset_id)
    except Exception as error:
        return _coverage_payload(status="missing", reason=str(error), required_window=window)

    key = partition_key or feature_input_partition_key(contract)
    if not key:
        return _coverage_payload(
            status="missing",
            reason=f"{dataset_id}: read_window requires partition_key for multi-key datasets",
            required_window=window,
        )
    if key not in contract.partition_keys:
        return _coverage_payload(
            status="missing",
            reason=f"{dataset_id}: unknown partition_key {key!r}",
            required_window=window,
            partition_key=key,
        )

    normalized_as_of = compact_date(as_of)
    try:
        partitions = [
            partition
            for partition in mart_store.list_partitions(dataset_id)
            if key in partition and compact_date(str(partition[key])) <= normalized_as_of
        ]
    except Exception as error:
        return _coverage_payload(status="missing", reason=str(error), required_window=window, partition_key=key)

    if key == "trade_date":
        return _strict_trade_date_coverage(
            mart_store=mart_store,
            dataset_id=dataset_id,
            key=key,
            as_of=normalized_as_of,
            window=window,
            partitions=partitions,
        )
    return _available_partition_coverage(
        mart_store=mart_store,
        dataset_id=dataset_id,
        key=key,
        as_of=normalized_as_of,
        window=window,
        partitions=partitions,
    )


def compact_date(value: str) -> str:
    return str(value).strip().replace("-", "")


def _strict_trade_date_coverage(
    *,
    mart_store: MartStore,
    dataset_id: str,
    key: str,
    as_of: str,
    window: int,
    partitions: list[dict[str, str]],
) -> dict[str, Any]:
    expected_dates, calendar_reason = _trade_calendar_window(mart_store, as_of=as_of, window=window)
    if not expected_dates:
        return _coverage_payload(
            status="missing",
            reason=calendar_reason or "trade calendar has no open dates for requested feature window",
            required_window=window,
            partition_key=key,
            calendar_status="missing",
        )

    by_date = {compact_date(str(partition[key])): partition for partition in partitions}
    selected = [by_date[date] for date in expected_dates if date in by_date]
    missing_dates = [date for date in expected_dates if date not in by_date]
    quality_statuses = _quality_statuses(mart_store, dataset_id, selected)
    available = len(selected)
    calendar_shortfall = max(window - len(expected_dates), 0)

    if available == 0:
        status = "missing"
        reason = f"no {dataset_id} partitions in required trading window {expected_dates[0]}..{expected_dates[-1]}"
    elif missing_dates or calendar_shortfall:
        status = "partial_window"
        pieces = []
        if missing_dates:
            pieces.append(f"missing {len(missing_dates)} partitions in required trading window: {missing_dates[:20]}")
        if calendar_shortfall:
            pieces.append(f"trade calendar has only {len(expected_dates)} open dates for requested window {window}")
        reason = "; ".join(pieces)
    elif any(status and status != "ok" for status in quality_statuses):
        status = "degraded_input"
        reason = "one or more input partitions are degraded"
    else:
        status = "ok"
        reason = ""

    return _coverage_payload(
        status=status,
        reason=reason,
        required_window=window,
        partition_key=key,
        available_partitions=available,
        selected_range={"start": expected_dates[0], "end": expected_dates[-1]},
        expected_partitions=[{key: date} for date in expected_dates],
        missing_partitions=[{key: date} for date in missing_dates],
        calendar_status="strict_trade_calendar",
        read_partitions=selected,
    )


def _available_partition_coverage(
    *,
    mart_store: MartStore,
    dataset_id: str,
    key: str,
    as_of: str,
    window: int,
    partitions: list[dict[str, str]],
) -> dict[str, Any]:
    selected_desc = sorted(partitions, key=lambda item: item[key], reverse=True)[:window]
    selected = list(reversed(selected_desc))
    available = len(selected)
    if available == 0:
        return _coverage_payload(
            status="missing",
            reason=f"no {dataset_id} partitions at or before {as_of}",
            required_window=window,
            partition_key=key,
        )
    quality_statuses = _quality_statuses(mart_store, dataset_id, selected)
    if available < window:
        status = "partial_window"
        reason = f"only {available} partitions available for requested window {window}"
    elif any(status and status != "ok" for status in quality_statuses):
        status = "degraded_input"
        reason = "one or more input partitions are degraded"
    else:
        status = "ok"
        reason = ""
    return _coverage_payload(
        status=status,
        reason=reason,
        required_window=window,
        partition_key=key,
        available_partitions=available,
        selected_range={"start": selected[0][key], "end": selected[-1][key]},
        read_partitions=selected,
    )


def _trade_calendar_window(mart_store: MartStore, *, as_of: str, window: int) -> tuple[list[str], str]:
    try:
        frame = mart_store.read("ashare.trade_calendar", {"exchange": "SSE"}, columns=["cal_date", "is_open"])
    except StorageError as error:
        return [], f"trade calendar unavailable: {error}"
    if frame.empty or "cal_date" not in frame.columns or "is_open" not in frame.columns:
        return [], "trade calendar is empty or missing cal_date/is_open columns"
    working = frame.copy()
    working["cal_date"] = working["cal_date"].astype(str).map(compact_date)
    dates = sorted(
        {
            date
            for date, is_open in zip(working["cal_date"], working["is_open"], strict=False)
            if date <= as_of and str(is_open) == "1"
        }
    )
    if not dates:
        return [], f"trade calendar has no open dates at or before {as_of}"
    return dates[-window:], ""


def _quality_statuses(mart_store: MartStore, dataset_id: str, partitions: list[dict[str, str]]) -> list[str]:
    quality_statuses: list[str] = []
    for partition in partitions:
        try:
            meta = mart_store.read_meta(dataset_id, partition)
        except Exception:
            quality_statuses.append("missing_meta")
            continue
        quality = meta.get("quality", {})
        quality_statuses.append(str(quality.get("status", "")) if isinstance(quality, dict) else "")
    return quality_statuses


def _coverage_payload(
    *,
    status: str,
    reason: str,
    required_window: int,
    partition_key: str | None = None,
    available_partitions: int = 0,
    selected_range: dict[str, Any] | None = None,
    expected_partitions: list[dict[str, str]] | None = None,
    missing_partitions: list[dict[str, str]] | None = None,
    calendar_status: str = "not_applicable",
    read_partitions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "coverage_status": status,
        "reason": reason,
        "partition_key": partition_key,
        "required_window": required_window,
        "available_partitions": available_partitions,
        "selected_range": selected_range or {"start": None, "end": None},
        "expected_partitions": expected_partitions or [],
        "missing_partitions": missing_partitions or [],
        "calendar_status": calendar_status,
        "_read_partitions": read_partitions or [],
    }
