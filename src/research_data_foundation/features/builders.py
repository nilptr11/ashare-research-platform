from __future__ import annotations

import re
from typing import Any

import pandas as pd

from ..core.registry import FoundationRegistry
from ..domains import default_registry
from ..storage import MartStore
from .registry import FeatureRegistry
from .schemas import FeatureBuildResult, FeatureError, FeatureSpec
from .store import FeatureStore
from .windowing import feature_window_coverage


class FeatureBuilder:
    def __init__(
        self,
        *,
        data_dir: str | None = None,
        registry: FoundationRegistry | None = None,
        feature_registry: FeatureRegistry | None = None,
        mart_store: MartStore | None = None,
        feature_store: FeatureStore | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.feature_registry = feature_registry or FeatureRegistry.builtin()
        self.mart_store = mart_store or MartStore(data_dir, self.registry)
        self.feature_store = feature_store or FeatureStore(data_dir)

    def build(self, feature_id: str, *, as_of: str, window: int, refresh: bool = False) -> FeatureBuildResult:
        spec = self.feature_registry.require(feature_id)
        if window <= 0:
            raise FeatureError("window must be positive")
        if feature_id == "ashare.daily_momentum":
            frame, inputs = self._build_ashare_daily_momentum(spec, as_of=as_of, window=window)
        elif feature_id == "ashare.market_strength":
            frame, inputs = self._build_ashare_market_strength(spec, as_of=as_of, window=window)
        elif feature_id == "ashare.industry_strength":
            frame, inputs = self._build_ashare_industry_strength(spec, as_of=as_of, window=window)
        elif feature_id == "ashare.concept_strength":
            frame, inputs = self._build_ashare_concept_strength(spec, as_of=as_of, window=window)
        elif feature_id == "ashare.limit_sentiment":
            frame, inputs = self._build_ashare_limit_sentiment(spec, as_of=as_of, window=window)
        elif feature_id == "industry.report_attention":
            frame, inputs = self._build_industry_report_attention(spec, as_of=as_of, window=window)
        else:
            raise FeatureError(f"No builder registered for feature {feature_id!r}")
        return self.feature_store.write_partition(spec, frame, as_of=as_of, window=window, inputs=inputs, refresh=refresh)

    def _build_ashare_daily_momentum(
        self,
        spec: FeatureSpec,
        *,
        as_of: str,
        window: int,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        daily, summary = self._read_window_input(spec.inputs[0], as_of=as_of, window=window)
        if daily.empty:
            return pd.DataFrame(columns=["as_of", "window", "security_id", "momentum_score", "window_return_pct"]), [summary]
        frame = _daily_momentum(daily, as_of=as_of, window=window)
        return frame, [summary]

    def _build_ashare_market_strength(
        self,
        spec: FeatureSpec,
        *,
        as_of: str,
        window: int,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        index_daily, index_input = self._read_window_input(spec.inputs[0], as_of=as_of, window=window)
        index_basic, basic_input = self._read_window_input(spec.inputs[1], as_of=as_of, window=1)
        if index_daily.empty:
            columns = ["as_of", "window", "source_dataset", "index_id", "strength_score", "window_return_pct"]
            return pd.DataFrame(columns=columns), [index_input, basic_input]
        frame = _window_strength(
            index_daily,
            as_of=as_of,
            window=window,
            source_dataset="ashare.index_daily",
            entity_column="index_id",
            activity_column="amount",
        )
        frame = _attach_latest_columns(frame, index_basic, key="index_id", columns=("total_mv",), prefix="latest_")
        return frame, [index_input, basic_input]

    def _build_ashare_industry_strength(
        self,
        spec: FeatureSpec,
        *,
        as_of: str,
        window: int,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        frames: list[pd.DataFrame] = []
        inputs: list[dict[str, Any]] = []
        for input_spec in spec.inputs:
            daily, summary = self._read_window_input(input_spec, as_of=as_of, window=window)
            inputs.append(summary)
            if daily.empty:
                continue
            frames.append(
                _window_strength(
                    daily,
                    as_of=as_of,
                    window=window,
                    source_dataset=input_spec.dataset_id,
                    entity_column="index_id",
                    activity_column="volume",
                )
            )
        if not frames:
            columns = ["as_of", "window", "source_dataset", "index_id", "strength_score", "window_return_pct"]
            return pd.DataFrame(columns=columns), inputs
        return pd.concat(frames, ignore_index=True).sort_values(["strength_score", "window_return_pct"], ascending=[False, False]).reset_index(drop=True), inputs

    def _build_ashare_concept_strength(
        self,
        spec: FeatureSpec,
        *,
        as_of: str,
        window: int,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        concepts, summary = self._read_window_input(spec.inputs[0], as_of=as_of, window=window)
        if concepts.empty:
            columns = ["as_of", "window", "concept_id", "name", "strength_score", "window_return_pct"]
            return pd.DataFrame(columns=columns), [summary]
        return _concept_strength(concepts, as_of=as_of, window=window), [summary]

    def _build_ashare_limit_sentiment(
        self,
        spec: FeatureSpec,
        *,
        as_of: str,
        window: int,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        limit_d, limit_d_input = self._read_window_input(spec.inputs[0], as_of=as_of, window=window)
        limit_ths, limit_ths_input = self._read_window_input(spec.inputs[1], as_of=as_of, window=window)
        return _limit_sentiment(limit_d, limit_ths, as_of=as_of, window=window), [limit_d_input, limit_ths_input]

    def _build_industry_report_attention(
        self,
        spec: FeatureSpec,
        *,
        as_of: str,
        window: int,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        reports, summary = self._read_window_input(spec.inputs[0], as_of=as_of, window=window, partition_key="query_date")
        if reports.empty:
            return pd.DataFrame(columns=["as_of", "window", "industry_name", "report_count", "attention_score"]), [summary]
        frame = _industry_report_attention(reports, as_of=as_of, window=window)
        return frame, [summary]

    def _read_window_input(
        self,
        input_spec: Any,
        *,
        as_of: str,
        window: int,
        partition_key: str | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        columns = list(input_spec.columns)
        coverage = feature_window_coverage(
            mart_store=self.mart_store,
            registry=self.registry,
            dataset_id=input_spec.dataset_id,
            as_of=as_of,
            window=window,
            partition_key=partition_key,
        )
        read_partitions = [dict(item) for item in coverage.pop("_read_partitions", [])]
        if coverage["coverage_status"] == "missing":
            frame = pd.DataFrame(columns=columns)
            return frame, _input_summary(input_spec.dataset_id, frame, status="missing", message=coverage["reason"]) | coverage
        try:
            frame = self._read_input_partitions(
                input_spec.dataset_id,
                read_partitions,
                as_of=as_of,
                window=window,
                partition_key=partition_key,
                columns=columns or None,
            )
            status = str(coverage["coverage_status"])
            message = str(coverage["reason"])
            return frame, _input_summary(input_spec.dataset_id, frame, status=status, message=message) | coverage
        except Exception as error:
            try:
                frame = self._read_input_partitions(
                    input_spec.dataset_id,
                    read_partitions,
                    as_of=as_of,
                    window=window,
                    partition_key=partition_key,
                )
            except Exception:
                frame = pd.DataFrame(columns=columns)
                return frame, _input_summary(input_spec.dataset_id, frame, status="missing", message=str(error)) | coverage
            missing_columns = [column for column in columns if column not in frame.columns]
            for column in missing_columns:
                frame[column] = pd.NA
            frame = frame[columns] if columns else frame
            status = str(coverage["coverage_status"]) if coverage["coverage_status"] != "ok" else "partial_columns" if missing_columns else "ok"
            messages = [str(coverage["reason"])] if coverage["reason"] else []
            if missing_columns:
                messages.append(f"missing columns: {missing_columns}")
            return frame, _input_summary(input_spec.dataset_id, frame, status=status, message="; ".join(messages)) | coverage

    def _read_input_partitions(
        self,
        dataset_id: str,
        read_partitions: list[dict[str, str]],
        *,
        as_of: str,
        window: int,
        partition_key: str | None = None,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        if read_partitions:
            frames = [self.mart_store.read(dataset_id, partition, columns=columns) for partition in read_partitions]
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self.mart_store.read_window(dataset_id, as_of=as_of, count=window, partition_key=partition_key, columns=columns)


def _daily_momentum(frame: pd.DataFrame, *, as_of: str, window: int) -> pd.DataFrame:
    daily = frame.copy()
    daily["trade_date"] = daily["trade_date"].astype(str)
    daily["pct_chg"] = pd.to_numeric(daily["pct_chg"], errors="coerce").fillna(0.0)
    daily["amount"] = pd.to_numeric(daily["amount"], errors="coerce")
    daily["volume"] = pd.to_numeric(daily["volume"], errors="coerce")
    latest_date = str(daily["trade_date"].max())
    grouped = daily.sort_values("trade_date").groupby("security_id", dropna=False)
    rows: list[dict[str, Any]] = []
    for security_id, group in grouped:
        latest = group[group["trade_date"] == latest_date].tail(1)
        if latest.empty:
            continue
        latest_row = latest.iloc[0]
        window_return = float(((1 + group["pct_chg"] / 100.0).prod() - 1) * 100.0)
        avg_amount = float(group["amount"].mean()) if group["amount"].notna().any() else 0.0
        latest_amount = float(latest_row["amount"]) if pd.notna(latest_row["amount"]) else 0.0
        amount_excess = (latest_amount / avg_amount - 1.0) if avg_amount else 0.0
        rows.append(
            {
                "as_of": as_of,
                "window": window,
                "security_id": str(security_id),
                "latest_trade_date": latest_date,
                "latest_pct_chg": float(latest_row["pct_chg"]),
                "latest_volume": float(latest_row["volume"]) if pd.notna(latest_row["volume"]) else None,
                "latest_amount": latest_amount,
                "avg_amount": avg_amount,
                "amount_excess": amount_excess,
                "window_return_pct": window_return,
                "source_dataset": "ashare.daily",
                "finality": "final",
            }
        )
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    output["return_rank"] = _rank_pct(output["window_return_pct"])
    output["amount_rank"] = _rank_pct(output["amount_excess"])
    output["momentum_score"] = output["return_rank"] * 70.0 + output["amount_rank"] * 30.0
    return output.sort_values(["momentum_score", "window_return_pct"], ascending=[False, False]).reset_index(drop=True)


def _window_strength(
    frame: pd.DataFrame,
    *,
    as_of: str,
    window: int,
    source_dataset: str,
    entity_column: str,
    activity_column: str,
) -> pd.DataFrame:
    working = frame.copy()
    working["trade_date"] = working["trade_date"].astype(str)
    working["pct_chg"] = pd.to_numeric(working.get("pct_chg", 0.0), errors="coerce").fillna(0.0)
    working["close"] = pd.to_numeric(working.get("close"), errors="coerce")
    if activity_column not in working.columns:
        working[activity_column] = pd.NA
    working[activity_column] = pd.to_numeric(working[activity_column], errors="coerce")
    latest_date = str(working["trade_date"].max())
    rows: list[dict[str, Any]] = []
    for entity_id, group in working.sort_values("trade_date").groupby(entity_column, dropna=False):
        latest = group[group["trade_date"] == latest_date].tail(1)
        if latest.empty:
            continue
        latest_row = latest.iloc[0]
        window_return = _window_return_pct(group)
        avg_activity = float(group[activity_column].mean()) if group[activity_column].notna().any() else 0.0
        latest_activity = float(latest_row[activity_column]) if pd.notna(latest_row[activity_column]) else 0.0
        activity_excess = (latest_activity / avg_activity - 1.0) if avg_activity else 0.0
        rows.append(
            {
                "as_of": as_of,
                "window": window,
                "source_dataset": source_dataset,
                entity_column: str(entity_id),
                "latest_trade_date": latest_date,
                "latest_close": float(latest_row["close"]) if pd.notna(latest_row["close"]) else None,
                "latest_pct_chg": float(latest_row["pct_chg"]) if pd.notna(latest_row["pct_chg"]) else None,
                f"latest_{activity_column}": latest_activity,
                f"avg_{activity_column}": avg_activity,
                "activity_excess": activity_excess,
                "window_return_pct": window_return,
                "finality": "final",
            }
        )
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    output["return_rank"] = _rank_pct(output["window_return_pct"])
    output["activity_rank"] = _rank_pct(output["activity_excess"])
    output["strength_score"] = output["return_rank"] * 75.0 + output["activity_rank"] * 25.0
    return output.sort_values(["strength_score", "window_return_pct"], ascending=[False, False]).reset_index(drop=True)


def _window_return_pct(group: pd.DataFrame) -> float:
    pct = pd.to_numeric(group.get("pct_chg"), errors="coerce")
    if pct.notna().any():
        return float(((1 + pct.fillna(0.0) / 100.0).prod() - 1) * 100.0)
    close = pd.to_numeric(group.get("close"), errors="coerce").dropna()
    if len(close) >= 2 and float(close.iloc[0]) != 0:
        return float((float(close.iloc[-1]) / float(close.iloc[0]) - 1.0) * 100.0)
    return 0.0


def _attach_latest_columns(
    frame: pd.DataFrame,
    latest: pd.DataFrame,
    *,
    key: str,
    columns: tuple[str, ...],
    prefix: str,
) -> pd.DataFrame:
    if frame.empty or latest.empty or key not in latest.columns:
        return frame
    available = [column for column in columns if column in latest.columns]
    if not available:
        return frame
    latest_frame = latest.copy()
    latest_frame["trade_date"] = latest_frame["trade_date"].astype(str) if "trade_date" in latest_frame.columns else ""
    if "trade_date" in latest_frame.columns:
        latest_frame = latest_frame.sort_values("trade_date").groupby(key, as_index=False).tail(1)
    latest_frame = latest_frame[[key, *available]].rename(columns={column: f"{prefix}{column}" for column in available})
    return frame.merge(latest_frame, on=key, how="left")


def _concept_strength(frame: pd.DataFrame, *, as_of: str, window: int) -> pd.DataFrame:
    concepts = frame.copy()
    concepts["trade_date"] = concepts["trade_date"].astype(str)
    concepts["pct_chg"] = pd.to_numeric(concepts["pct_chg"], errors="coerce").fillna(0.0)
    rows: list[dict[str, Any]] = []
    latest_date = str(concepts["trade_date"].max())
    for concept_id, group in concepts.sort_values("trade_date").groupby("concept_id", dropna=False):
        latest = group[group["trade_date"] == latest_date].tail(1)
        if latest.empty:
            continue
        latest_row = latest.iloc[0]
        rows.append(
            {
                "as_of": as_of,
                "window": window,
                "concept_id": str(concept_id),
                "name": str(latest_row.get("name", "")),
                "latest_trade_date": latest_date,
                "latest_pct_chg": float(latest_row["pct_chg"]),
                "window_return_pct": float(((1 + group["pct_chg"] / 100.0).prod() - 1) * 100.0),
                "source_dataset": "ashare.dc_index",
                "finality": "final",
            }
        )
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    output["return_rank"] = _rank_pct(output["window_return_pct"])
    output["latest_rank"] = _rank_pct(output["latest_pct_chg"])
    output["strength_score"] = output["return_rank"] * 80.0 + output["latest_rank"] * 20.0
    return output.sort_values(["strength_score", "window_return_pct"], ascending=[False, False]).reset_index(drop=True)


def _limit_sentiment(limit_d: pd.DataFrame, limit_ths: pd.DataFrame, *, as_of: str, window: int) -> pd.DataFrame:
    d_dates = set(limit_d["trade_date"].astype(str)) if "trade_date" in limit_d.columns else set()
    ths_dates = set(limit_ths["trade_date"].astype(str)) if "trade_date" in limit_ths.columns else set()
    dates = sorted(d_dates | ths_dates)
    rows: list[dict[str, Any]] = []
    for trade_date in dates:
        d_day = limit_d[limit_d["trade_date"].astype(str) == trade_date] if "trade_date" in limit_d.columns else pd.DataFrame()
        ths_day = limit_ths[limit_ths["trade_date"].astype(str) == trade_date] if "trade_date" in limit_ths.columns else pd.DataFrame()
        limit_values = d_day.get("limit", pd.Series(dtype=str)).astype(str)
        up_count = int((limit_values == "U").sum() + limit_values.str.contains("涨停", na=False).sum())
        down_count = int((limit_values == "D").sum() + limit_values.str.contains("跌停", na=False).sum())
        ths_count = int(len(ths_day))
        avg_open_num = _safe_mean(ths_day, "open_num")
        limit_order_sum = _safe_sum(ths_day, "limit_order")
        limit_amount_sum = _safe_sum(ths_day, "limit_amount")
        max_board_height = _max_board_height(ths_day)
        sentiment_score = (
            up_count * 2.0
            - down_count * 3.0
            + ths_count * 2.0
            + max_board_height * 10.0
            + min(limit_amount_sum / 100_000_000.0, 50.0)
            - (avg_open_num or 0.0)
        )
        rows.append(
            {
                "as_of": as_of,
                "window": window,
                "trade_date": trade_date,
                "limit_up_count": up_count,
                "limit_down_count": down_count,
                "ths_limit_up_count": ths_count,
                "avg_open_num": avg_open_num,
                "limit_order_sum": limit_order_sum,
                "limit_amount_sum": limit_amount_sum,
                "max_board_height": max_board_height,
                "sentiment_score": float(sentiment_score),
                "source_dataset": "ashare.limit_list_d+ashare.limit_list_ths",
                "finality": "final",
            }
        )
    return pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True) if rows else pd.DataFrame(columns=["as_of", "window", "trade_date", "sentiment_score", "limit_up_count", "ths_limit_up_count"])


def _industry_report_attention(frame: pd.DataFrame, *, as_of: str, window: int) -> pd.DataFrame:
    reports = frame.copy()
    reports["industry_name"] = reports["industry_name"].fillna("").astype(str).str.strip()
    reports = reports[reports["industry_name"] != ""]
    if reports.empty:
        return pd.DataFrame(columns=["as_of", "window", "industry_name", "report_count", "attention_score"])
    grouped = reports.groupby("industry_name", dropna=False)
    output = grouped.agg(
        report_count=("report_id", "nunique"),
        latest_report_at=("published_at", "max"),
        source_count=("source_name", "nunique"),
    ).reset_index()
    output["as_of"] = as_of
    output["window"] = window
    output["attention_score"] = _rank_pct(output["report_count"]) * 100.0
    columns = ["as_of", "window", "industry_name", "report_count", "source_count", "latest_report_at", "attention_score"]
    return output[columns].sort_values(["attention_score", "report_count"], ascending=[False, False]).reset_index(drop=True)


def _input_summary(dataset_id: str, frame: pd.DataFrame, *, status: str, message: str = "") -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "status": status,
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "message": message,
    }


def _coverage_payload(
    *,
    status: str,
    reason: str,
    required_window: int,
    available_partitions: int = 0,
    selected_range: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "coverage_status": status,
        "reason": reason,
        "required_window": required_window,
        "available_partitions": available_partitions,
        "selected_range": selected_range or {"start": None, "end": None},
    }


def _rank_pct(series: pd.Series) -> pd.Series:
    if len(series) <= 1:
        return pd.Series([1.0] * len(series), index=series.index)
    return series.rank(method="average", pct=True).fillna(0.0)


def _safe_sum(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.sum()) if values.notna().any() else 0.0


def _safe_mean(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.mean()) if values.notna().any() else 0.0


def _max_board_height(frame: pd.DataFrame) -> int:
    if frame.empty or "board_tag" not in frame.columns:
        return 0
    heights = [_board_height(value) for value in frame["board_tag"]]
    return max(heights) if heights else 0


def _board_height(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if "首板" in text:
        return 1
    match = re.search(r"(\d+)天(\d+)板", text)
    if match:
        return int(match.group(2))
    match = re.search(r"(\d+)板", text)
    if match:
        return int(match.group(1))
    return 0
