from __future__ import annotations

import re
from typing import Any

import pandas as pd

from ..marts.reader import MartReader
from ..schemas import AShareResearchError, FeatureBuildResult, FeatureError, FeatureSpec
from .registry import FeatureRegistry
from .scoring import FeatureScoreConfig, ScoringProfile
from .store import FeatureStore


class FeatureBuilder:
    def __init__(
        self,
        mart_reader: MartReader,
        feature_store: FeatureStore | None = None,
        registry: FeatureRegistry | None = None,
        scoring_profile: ScoringProfile | None = None,
    ) -> None:
        self.mart_reader = mart_reader
        self.feature_store = feature_store or FeatureStore(mart_reader.data_dir)
        self.registry = registry or FeatureRegistry.builtin()
        self.scoring_profile = scoring_profile or ScoringProfile.builtin()

    def build(self, feature: str, *, as_of: str, windows: list[int]) -> list[FeatureBuildResult]:
        spec = self.registry.require(feature)
        score_config = self.scoring_profile.require(feature)
        scoring = self.scoring_profile.metadata(feature)
        results: list[FeatureBuildResult] = []
        for window in windows:
            if feature == "market_strength":
                frame, inputs = self._build_market_strength(as_of=as_of, window=window, score_config=score_config)
            elif feature == "industry_strength":
                frame, inputs = self._build_industry_strength(as_of=as_of, window=window, score_config=score_config)
            elif feature == "concept_strength":
                frame, inputs = self._build_concept_strength(as_of=as_of, window=window, score_config=score_config)
            elif feature == "limit_sentiment":
                frame, inputs = self._build_limit_sentiment(as_of=as_of, window=window, score_config=score_config)
            elif feature == "leader_validation":
                frame, inputs = self._build_leader_validation(as_of=as_of, window=window, score_config=score_config)
            elif feature == "elasticity_candidates":
                frame, inputs = self._build_elasticity_candidates(as_of=as_of, window=window, score_config=score_config)
            else:
                raise FeatureError(f"No builder registered for feature {feature!r}")
            results.append(self.feature_store.write_partition(spec, frame, as_of=as_of, window=window, inputs=inputs, scoring=scoring))
        return results

    def _build_market_strength(
        self,
        *,
        as_of: str,
        window: int,
        score_config: FeatureScoreConfig,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        daily = self.mart_reader.read_window(
            "index_daily",
            as_of=as_of,
            trade_days=window,
            columns=["ts_code", "trade_date", "close", "pct_chg", "amount"],
        )
        basic = self.mart_reader.read_partition(
            "index_dailybasic",
            {"trade_date": as_of},
            columns=["ts_code", "trade_date", "turnover_rate", "pe_ttm", "pb", "total_mv", "float_mv"],
        )
        frame = _window_strength(daily, as_of=as_of, window=window, source_dataset="index_daily", score_config=score_config)
        frame = _attach_latest_columns(
            frame,
            basic,
            key="ts_code",
            columns=["turnover_rate", "pe_ttm", "pb", "total_mv", "float_mv"],
            prefix="latest_",
        )
        return frame, [
            _input_summary("index_daily", daily, "trade_date"),
            _input_summary("index_dailybasic", basic, "trade_date"),
        ]

    def _build_industry_strength(
        self,
        *,
        as_of: str,
        window: int,
        score_config: FeatureScoreConfig,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        frames: list[pd.DataFrame] = []
        inputs: list[dict[str, Any]] = []
        sw_members, sw_members_input = self._read_snapshot_partition(
            "index_member_all",
            {"snapshot_date": as_of},
            columns=["l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name", "ts_code"],
        )
        ci_members, ci_members_input = self._read_snapshot_partition(
            "ci_index_member",
            {"snapshot_date": as_of},
            columns=["l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name", "ts_code"],
        )
        hierarchy_by_dataset = {
            "sw_daily": _industry_hierarchy(sw_members),
            "ci_daily": _industry_hierarchy(ci_members),
        }
        for dataset in ("sw_daily", "ci_daily"):
            daily = self.mart_reader.read_window(
                dataset,
                as_of=as_of,
                trade_days=window,
                columns=None,
            )
            strength = _window_strength(daily, as_of=as_of, window=window, source_dataset=dataset, score_config=score_config)
            frames.append(_attach_industry_hierarchy(strength, hierarchy_by_dataset[dataset]))
            inputs.append(_input_summary(dataset, daily, "trade_date"))
        inputs.extend([sw_members_input, ci_members_input])
        return pd.concat(frames, ignore_index=True), inputs

    def _build_concept_strength(
        self,
        *,
        as_of: str,
        window: int,
        score_config: FeatureScoreConfig,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        concepts = self.mart_reader.read_window("dc_index", as_of=as_of, trade_days=window, columns=None)
        frame = _concept_strength(concepts, as_of=as_of, window=window, source_dataset="dc_index", score_config=score_config)
        return frame, [_input_summary("dc_index", concepts, "trade_date")]

    def _build_limit_sentiment(
        self,
        *,
        as_of: str,
        window: int,
        score_config: FeatureScoreConfig,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        limit_d = self.mart_reader.read_window("limit_list_d", as_of=as_of, trade_days=window)
        limit_ths = self.mart_reader.read_window("limit_list_ths", as_of=as_of, trade_days=window)
        trade_dates = sorted(set(limit_d["trade_date"].astype(str)) | set(limit_ths["trade_date"].astype(str)))
        rows: list[dict[str, Any]] = []
        for trade_date in trade_dates:
            d_day = limit_d[limit_d["trade_date"].astype(str) == trade_date]
            ths_day = limit_ths[limit_ths["trade_date"].astype(str) == trade_date]
            up_count = int((d_day.get("limit", pd.Series(dtype=str)).astype(str) == "U").sum())
            down_count = int((d_day.get("limit", pd.Series(dtype=str)).astype(str) == "D").sum())
            limit_up_score = float(up_count * score_config.weight("up_count"))
            limit_down_score = float(down_count * score_config.weight("down_count"))
            ths_pool_score = float(len(ths_day) * score_config.weight("ths_count"))
            rows.append(
                {
                    "as_of": as_of,
                    "window": window,
                    "trade_date": trade_date,
                    "limit_up_count": up_count,
                    "limit_down_count": down_count,
                    "ths_limit_up_count": int(len(ths_day)),
                    "avg_open_num": _safe_mean(ths_day, "open_num"),
                    "limit_amount_sum": _safe_sum(ths_day, "limit_amount"),
                    "limit_order_sum": _safe_sum(ths_day, "limit_order"),
                    "max_board_height": _max_board_height(ths_day),
                    "limit_up_score": limit_up_score,
                    "limit_down_score": limit_down_score,
                    "ths_pool_score": ths_pool_score,
                    "sentiment_score": _limit_sentiment_score(up_count, down_count, int(len(ths_day)), score_config),
                }
            )
        return pd.DataFrame(rows), [
            _input_summary("limit_list_d", limit_d, "trade_date"),
            _input_summary("limit_list_ths", limit_ths, "trade_date"),
        ]

    def _build_leader_validation(
        self,
        *,
        as_of: str,
        window: int,
        score_config: FeatureScoreConfig,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        base, inputs = self._stock_validation_base(as_of=as_of, window=window, score_config=score_config)
        if base.empty:
            return base, inputs
        frame = base.copy()
        frame = _attach_leader_scores(frame, score_config)
        frame["is_large_cap"] = pd.to_numeric(frame.get("latest_circ_mv"), errors="coerce").fillna(0) >= 1_000_000
        frame = frame.sort_values(["leader_score", "window_return_pct"], ascending=[False, False])
        return frame, inputs

    def _build_elasticity_candidates(
        self,
        *,
        as_of: str,
        window: int,
        score_config: FeatureScoreConfig,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        base, inputs = self._stock_validation_base(as_of=as_of, window=window, score_config=score_config)
        if base.empty:
            return base, inputs
        frame = base.copy()
        frame = _attach_elasticity_scores(frame, score_config)
        frame = frame.sort_values(["elasticity_score", "window_return_pct"], ascending=[False, False]).reset_index(drop=True)
        frame["elasticity_rank"] = frame.index + 1
        return frame, inputs

    def _stock_validation_base(
        self,
        *,
        as_of: str,
        window: int,
        score_config: FeatureScoreConfig,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        daily = self.mart_reader.read_window(
            "daily",
            as_of=as_of,
            trade_days=window,
            columns=["ts_code", "trade_date", "close", "pct_chg", "amount"],
        )
        basic = self.mart_reader.read_partition(
            "daily_basic",
            {"trade_date": as_of},
            columns=[
                "ts_code",
                "trade_date",
                "turnover_rate",
                "volume_ratio",
                "pe_ttm",
                "pb",
                "total_mv",
                "circ_mv",
            ],
        )
        stock_basic, stock_basic_input = self._read_snapshot_partition(
            "stock_basic",
            {"snapshot_date": as_of},
            columns=["ts_code", "name", "industry", "market", "list_status"],
        )
        moneyflow, moneyflow_input = self._read_optional_window("moneyflow_dc", as_of=as_of, window=window)
        top_list, top_input = self._read_optional_window("top_list", as_of=as_of, window=window)
        limit_ths, limit_input = self._read_optional_window("limit_list_ths", as_of=as_of, window=window)
        sw_members, sw_members_input = self._read_snapshot_partition(
            "index_member_all",
            {"snapshot_date": as_of},
            columns=["ts_code", "l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name"],
        )

        frame = _window_strength(daily, as_of=as_of, window=window, source_dataset="daily", score_config=score_config)
        frame = _attach_stock_basic(frame, stock_basic)
        frame = _attach_stock_sw_industry(frame, sw_members)
        frame = _attach_latest_columns(
            frame,
            basic,
            key="ts_code",
            columns=["turnover_rate", "volume_ratio", "pe_ttm", "pb", "total_mv", "circ_mv"],
            prefix="latest_",
        )
        frame = _attach_moneyflow(frame, moneyflow)
        frame = _attach_top_list(frame, top_list)
        frame = _attach_limit_pool(frame, limit_ths)
        inputs = [
            _input_summary("daily", daily, "trade_date"),
            _input_summary("daily_basic", basic, "trade_date"),
            stock_basic_input,
            moneyflow_input,
            top_input,
            limit_input,
            sw_members_input,
        ]
        return frame, inputs

    def _read_optional_window(self, dataset: str, *, as_of: str, window: int) -> tuple[pd.DataFrame, dict[str, Any]]:
        try:
            frame = self.mart_reader.read_window(dataset, as_of=as_of, trade_days=window)
            return frame, _input_summary(dataset, frame, "trade_date")
        except AShareResearchError as error:
            return pd.DataFrame(), {"dataset": dataset, "rows": 0, "status": "missing", "message": str(error)}

    def _read_optional_partition(
        self,
        dataset: str,
        partition: dict[str, str],
        *,
        columns: list[str] | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        try:
            frame = self.mart_reader.read_partition(dataset, partition, columns=columns)
            return frame, _input_summary(dataset, frame, next(iter(partition)))
        except AShareResearchError as error:
            return pd.DataFrame(), {"dataset": dataset, "rows": 0, "status": "missing", "message": str(error)}
        except Exception as error:
            if not columns:
                return pd.DataFrame(), {"dataset": dataset, "rows": 0, "status": "read_error", "message": str(error)}
            try:
                frame = self.mart_reader.read_partition(dataset, partition)
            except Exception as fallback_error:
                return pd.DataFrame(), {"dataset": dataset, "rows": 0, "status": "read_error", "message": str(fallback_error)}
            missing_columns = [column for column in columns if column not in frame.columns]
            for column in missing_columns:
                frame[column] = pd.NA
            frame = frame[columns]
            return frame, _input_summary(dataset, frame, next(iter(partition))) | {
                "status": "partial_columns" if missing_columns else "ok",
                "missing_columns": missing_columns,
                "message": str(error) if missing_columns else "",
            }

    def _read_snapshot_partition(
        self,
        dataset: str,
        partition: dict[str, str],
        *,
        columns: list[str] | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        frame, info = self._read_optional_partition(dataset, partition, columns=columns)
        if _is_usable_input(info, frame):
            return frame, _snapshot_input_info(info, requested_partition=partition, actual_partition=partition, mode="exact")
        latest = self.mart_reader.latest_partition(dataset, "snapshot_date")
        if latest is None:
            return frame, _snapshot_input_info(info, requested_partition=partition, actual_partition={}, mode="missing")
        fallback_frame, fallback_info = self._read_optional_partition(dataset, latest.values, columns=columns)
        if not _is_usable_input(fallback_info, fallback_frame):
            return fallback_frame, _snapshot_input_info(
                fallback_info,
                requested_partition=partition,
                actual_partition=latest.values,
                mode="missing",
            )
        return fallback_frame, _snapshot_input_info(
            fallback_info,
            requested_partition=partition,
            actual_partition=latest.values,
            mode="latest_available",
        )


def _concept_strength(
    frame: pd.DataFrame,
    *,
    as_of: str,
    window: int,
    source_dataset: str,
    score_config: FeatureScoreConfig,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    working["trade_date"] = working["trade_date"].astype(str)
    if "pct_change" in working.columns:
        working["pct_change"] = pd.to_numeric(working["pct_change"], errors="coerce")
    if "leading_pct" in working.columns:
        working["leading_pct"] = pd.to_numeric(working["leading_pct"], errors="coerce")
    for column in ("turnover_rate", "total_mv", "up_num", "down_num"):
        if column in working.columns:
            working[column] = pd.to_numeric(working[column], errors="coerce")

    rows: list[dict[str, Any]] = []
    for ts_code, group in working.sort_values("trade_date").groupby("ts_code", sort=True):
        latest = group.iloc[-1]
        pct = pd.to_numeric(group.get("pct_change"), errors="coerce") if "pct_change" in group.columns else pd.Series(dtype=float)
        latest_up = _nullable_float(latest["up_num"]) if "up_num" in group.columns else None
        latest_down = _nullable_float(latest["down_num"]) if "down_num" in group.columns else None
        breadth_score = _breadth_score(latest_up, latest_down)
        latest_pct = _nullable_float(latest["pct_change"]) if "pct_change" in group.columns else None
        leading_pct = _nullable_float(latest["leading_pct"]) if "leading_pct" in group.columns else None
        window_return = float(pct.sum()) if not pct.empty else None
        momentum_score = (window_return or 0.0) * score_config.weight("window_return")
        latest_pct_score = (latest_pct or 0.0) * score_config.weight("latest_pct")
        leading_pct_score = (leading_pct or 0.0) * score_config.weight("leading_pct")
        breadth_component_score = (breadth_score or 0.0) * score_config.weight("breadth")
        rows.append(
            {
                "as_of": as_of,
                "window": window,
                "source_dataset": source_dataset,
                "ts_code": ts_code,
                "name": str(latest["name"]) if "name" in group.columns and pd.notna(latest["name"]) else None,
                "start_trade_date": str(group.iloc[0]["trade_date"]),
                "end_trade_date": str(latest["trade_date"]),
                "observations": int(len(group)),
                "latest_pct_chg": latest_pct,
                "window_return_pct": window_return,
                "avg_pct_chg": _nullable_float(pct.mean()) if not pct.empty else None,
                "latest_leading": str(latest["leading"]) if "leading" in group.columns and pd.notna(latest["leading"]) else None,
                "latest_leading_code": str(latest["leading_code"]) if "leading_code" in group.columns and pd.notna(latest["leading_code"]) else None,
                "latest_leading_pct": leading_pct,
                "latest_total_mv": _nullable_float(latest["total_mv"]) if "total_mv" in group.columns else None,
                "latest_turnover_rate": _nullable_float(latest["turnover_rate"]) if "turnover_rate" in group.columns else None,
                "latest_up_num": latest_up,
                "latest_down_num": latest_down,
                "breadth_score": breadth_score,
                "momentum_score": momentum_score,
                "latest_pct_score": latest_pct_score,
                "leading_pct_score": leading_pct_score,
                "breadth_component_score": breadth_component_score,
                "strength_score": _concept_score(window_return, latest_pct, leading_pct, breadth_score, score_config),
            }
        )
    return pd.DataFrame(rows).sort_values(["strength_score", "window_return_pct"], ascending=[False, False])


def _window_strength(
    frame: pd.DataFrame,
    *,
    as_of: str,
    window: int,
    source_dataset: str,
    score_config: FeatureScoreConfig,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    working["trade_date"] = working["trade_date"].astype(str)
    working["close"] = pd.to_numeric(working["close"], errors="coerce")
    if "amount" in working.columns:
        working["amount"] = pd.to_numeric(working["amount"], errors="coerce")
    pct_column = "pct_chg" if "pct_chg" in working.columns else "pct_change" if "pct_change" in working.columns else None
    name_column = "name" if "name" in working.columns else None

    rows: list[dict[str, Any]] = []
    for ts_code, group in working.sort_values("trade_date").groupby("ts_code", sort=True):
        group = group.dropna(subset=["close"])
        if group.empty:
            continue
        first = group.iloc[0]
        latest = group.iloc[-1]
        first_close = float(first["close"])
        latest_close = float(latest["close"])
        window_return = ((latest_close / first_close) - 1.0) * 100.0 if first_close else None
        avg_amount = float(group["amount"].mean()) if "amount" in group.columns else None
        latest_amount = float(latest["amount"]) if "amount" in group.columns and pd.notna(latest["amount"]) else None
        amount_vs_avg = (latest_amount / avg_amount) if latest_amount is not None and avg_amount else None
        amount_excess = _amount_excess(amount_vs_avg, score_config)
        momentum_score = (window_return or 0.0) * score_config.weight("window_return")
        volume_score = amount_excess * score_config.weight("amount_excess")
        rows.append(
            {
                "as_of": as_of,
                "window": window,
                "source_dataset": source_dataset,
                "ts_code": ts_code,
                "name": str(latest[name_column]) if name_column else None,
                "start_trade_date": str(first["trade_date"]),
                "end_trade_date": str(latest["trade_date"]),
                "observations": int(len(group)),
                "latest_close": latest_close,
                "latest_pct_chg": _nullable_float(latest[pct_column]) if pct_column else None,
                "window_return_pct": window_return,
                "avg_amount": avg_amount,
                "latest_amount": latest_amount,
                "amount_vs_avg": amount_vs_avg,
                "above_window_midpoint": latest_close > float(group["close"].mean()),
                "momentum_score": momentum_score,
                "volume_score": volume_score,
                "strength_score": _strength_score(window_return, amount_vs_avg, score_config),
            }
        )
    return pd.DataFrame(rows).sort_values(["strength_score", "window_return_pct"], ascending=[False, False])


def _industry_hierarchy(members: pd.DataFrame) -> pd.DataFrame:
    columns = ["ts_code", "industry_name", "industry_level", "l1", "l2", "l3"]
    required = {"l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name"}
    if members.empty or not required.issubset(set(members.columns)):
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    levels = (("l1", "l1_code", "l1_name"), ("l2", "l2_code", "l2_name"), ("l3", "l3_code", "l3_name"))
    for level, code_column, name_column in levels:
        subset = members.dropna(subset=[code_column]).drop_duplicates(code_column, keep="last")
        for _, row in subset.iterrows():
            rows.append(
                {
                    "ts_code": str(row[code_column]),
                    "industry_name": str(row[name_column]) if pd.notna(row[name_column]) else None,
                    "industry_level": level.upper(),
                    "l1": str(row["l1_name"]) if pd.notna(row["l1_name"]) else None,
                    "l2": str(row["l2_name"]) if level in {"l2", "l3"} and pd.notna(row["l2_name"]) else None,
                    "l3": str(row["l3_name"]) if level == "l3" and pd.notna(row["l3_name"]) else None,
                }
            )
    return pd.DataFrame(rows, columns=columns).drop_duplicates("ts_code", keep="last")


def _attach_industry_hierarchy(frame: pd.DataFrame, hierarchy: pd.DataFrame) -> pd.DataFrame:
    defaults = {"industry_name": None, "industry_level": None, "l1": None, "l2": None, "l3": None}
    if frame.empty:
        return frame
    if hierarchy.empty or "ts_code" not in hierarchy.columns:
        return _fill_missing_columns(frame, defaults)
    addon = hierarchy[["ts_code", "industry_name", "industry_level", "l1", "l2", "l3"]].drop_duplicates("ts_code", keep="last")
    merged = frame.merge(addon, on="ts_code", how="left")
    if "name" in merged.columns:
        merged["name"] = merged["name"].where(merged["name"].notna(), merged["industry_name"])
    ordered = ["as_of", "window", "source_dataset", "ts_code", "name", "industry_name", "industry_level", "l1", "l2", "l3"]
    return _frontload_columns(_fill_missing_columns(merged, defaults), ordered)


def _strength_score(window_return: float | None, amount_vs_avg: float | None, score_config: FeatureScoreConfig) -> float | None:
    if window_return is None:
        return None
    return float(
        window_return * score_config.weight("window_return")
        + _amount_excess(amount_vs_avg, score_config) * score_config.weight("amount_excess")
    )


def _concept_score(
    window_return: float | None,
    latest_pct: float | None,
    leading_pct: float | None,
    breadth_score: float | None,
    score_config: FeatureScoreConfig,
) -> float | None:
    if window_return is None:
        return None
    return float(
        window_return * score_config.weight("window_return")
        + (latest_pct or 0.0) * score_config.weight("latest_pct")
        + (leading_pct or 0.0) * score_config.weight("leading_pct")
        + (breadth_score or 0.0) * score_config.weight("breadth")
    )


def _breadth_score(up_num: float | None, down_num: float | None) -> float | None:
    if up_num is None or down_num is None:
        return None
    total = up_num + down_num
    if not total:
        return None
    return float((up_num - down_num) / total)


def _attach_moneyflow(frame: pd.DataFrame, moneyflow: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    if moneyflow.empty or "ts_code" not in moneyflow.columns:
        return _fill_missing_columns(
            frame,
            {
                "moneyflow_net_amount": 0.0,
                "moneyflow_net_amount_rate": 0.0,
                "moneyflow_buy_elg_amount_rate": 0.0,
                "moneyflow_buy_lg_amount_rate": 0.0,
            },
        )
    latest = _latest_by_ts_code(moneyflow)
    keep = [
        column
        for column in ("ts_code", "net_amount", "net_amount_rate", "buy_elg_amount_rate", "buy_lg_amount_rate")
        if column in latest.columns
    ]
    addon = latest[keep].rename(
        columns={
            "net_amount": "moneyflow_net_amount",
            "net_amount_rate": "moneyflow_net_amount_rate",
            "buy_elg_amount_rate": "moneyflow_buy_elg_amount_rate",
            "buy_lg_amount_rate": "moneyflow_buy_lg_amount_rate",
        }
    )
    merged = frame.merge(addon, on="ts_code", how="left")
    return _fill_missing_columns(
        merged,
        {
            "moneyflow_net_amount": 0.0,
            "moneyflow_net_amount_rate": 0.0,
            "moneyflow_buy_elg_amount_rate": 0.0,
            "moneyflow_buy_lg_amount_rate": 0.0,
        },
    )


def _attach_stock_basic(frame: pd.DataFrame, stock_basic: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or stock_basic.empty or "ts_code" not in stock_basic.columns:
        return frame
    keep = [column for column in ("ts_code", "name", "industry", "market", "list_status") if column in stock_basic.columns]
    addon = stock_basic[keep].drop_duplicates("ts_code", keep="last")
    merged = frame.drop(columns=["name"], errors="ignore").merge(addon, on="ts_code", how="left")
    ordered = [
        "as_of",
        "window",
        "source_dataset",
        "ts_code",
        "name",
        "industry",
        "market",
        "list_status",
    ]
    return _frontload_columns(merged, ordered)


def _attach_stock_sw_industry(frame: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "sw_l1_code": None,
        "sw_l1_name": None,
        "sw_l2_code": None,
        "sw_l2_name": None,
        "sw_l3_code": None,
        "sw_l3_name": None,
    }
    if frame.empty:
        return frame
    required = {"ts_code", "l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name"}
    if members.empty or not required.issubset(set(members.columns)):
        return _fill_missing_columns(frame, defaults)
    addon = members[["ts_code", "l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name"]].drop_duplicates(
        "ts_code",
        keep="last",
    )
    addon = addon.rename(
        columns={
            "l1_code": "sw_l1_code",
            "l1_name": "sw_l1_name",
            "l2_code": "sw_l2_code",
            "l2_name": "sw_l2_name",
            "l3_code": "sw_l3_code",
            "l3_name": "sw_l3_name",
        }
    )
    merged = frame.merge(addon, on="ts_code", how="left")
    ordered = [
        "as_of",
        "window",
        "source_dataset",
        "ts_code",
        "name",
        "industry",
        "sw_l1_name",
        "sw_l2_name",
        "sw_l3_name",
        "market",
        "list_status",
    ]
    return _frontload_columns(_fill_missing_columns(merged, defaults), ordered)


def _attach_top_list(frame: pd.DataFrame, top_list: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    if top_list.empty or "ts_code" not in top_list.columns:
        return _fill_missing_columns(
            frame,
            {
                "top_list_count": 0,
                "top_list_net_amount_sum": 0.0,
                "latest_top_list_reason": None,
            },
        )
    working = top_list.copy()
    if "net_amount" in working.columns:
        working["net_amount"] = pd.to_numeric(working["net_amount"], errors="coerce")
    grouped = working.groupby("ts_code", sort=True)
    metrics = grouped.size().rename("top_list_count").to_frame()
    if "net_amount" in working.columns:
        metrics["top_list_net_amount_sum"] = grouped["net_amount"].sum()
    metrics = metrics.reset_index()
    latest = _latest_by_ts_code(working)
    if "reason" in latest.columns:
        metrics = metrics.merge(latest[["ts_code", "reason"]].rename(columns={"reason": "latest_top_list_reason"}), on="ts_code", how="left")
    else:
        metrics["latest_top_list_reason"] = None
    merged = frame.merge(metrics, on="ts_code", how="left")
    return _fill_missing_columns(
        merged,
        {
            "top_list_count": 0,
            "top_list_net_amount_sum": 0.0,
            "latest_top_list_reason": None,
        },
    )


def _attach_limit_pool(frame: pd.DataFrame, limit_ths: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    if limit_ths.empty or "ts_code" not in limit_ths.columns:
        return _fill_missing_columns(
            frame,
            {
                "limit_pool_count": 0,
                "latest_limit_pool": False,
                "max_board_height": 0,
                "limit_amount_sum": 0.0,
            },
        )
    working = limit_ths.copy()
    if "limit_amount" in working.columns:
        working["limit_amount"] = pd.to_numeric(working["limit_amount"], errors="coerce")
    latest_date = str(working["trade_date"].astype(str).max()) if "trade_date" in working.columns else None
    grouped = working.groupby("ts_code", sort=True)
    metrics = grouped.size().rename("limit_pool_count").to_frame()
    metrics["max_board_height"] = grouped.apply(_max_board_height, include_groups=False)
    if "limit_amount" in working.columns:
        metrics["limit_amount_sum"] = grouped["limit_amount"].sum()
    metrics = metrics.reset_index()
    if latest_date:
        latest_codes = set(working[working["trade_date"].astype(str) == latest_date]["ts_code"].astype(str))
        metrics["latest_limit_pool"] = metrics["ts_code"].astype(str).isin(latest_codes)
    else:
        metrics["latest_limit_pool"] = False
    merged = frame.merge(metrics, on="ts_code", how="left")
    return _fill_missing_columns(
        merged,
        {
            "limit_pool_count": 0,
            "latest_limit_pool": False,
            "max_board_height": 0,
            "limit_amount_sum": 0.0,
        },
    )


def _attach_leader_scores(frame: pd.DataFrame, score_config: FeatureScoreConfig) -> pd.DataFrame:
    output = frame.copy()
    scores = output.apply(lambda row: _leader_score_parts(row, score_config), axis=1, result_type="expand")
    for column in scores.columns:
        output[column] = scores[column]
    output["leader_score"] = scores[
        ["momentum_score", "volume_score", "size_score", "moneyflow_score", "top_list_score", "limit_pool_score"]
    ].sum(axis=1)
    return output


def _leader_score_parts(row: pd.Series, score_config: FeatureScoreConfig) -> dict[str, float]:
    window_return = _series_float(row, "window_return_pct")
    amount_boost = _series_float(row, "amount_vs_avg")
    circ_mv = _series_float(row, "latest_circ_mv")
    moneyflow_rate = _series_float(row, "moneyflow_net_amount_rate")
    top_count = _series_float(row, "top_list_count")
    limit_count = _series_float(row, "limit_pool_count")
    large_cap_bonus = min((circ_mv or 0.0) / score_config.param("large_cap_divisor", 200000.0), score_config.param("large_cap_cap", 8.0))
    return {
        "momentum_score": window_return * score_config.weight("window_return"),
        "volume_score": max((amount_boost or 0.0) - 1.0, 0.0) * score_config.weight("amount_excess"),
        "size_score": large_cap_bonus * score_config.weight("large_cap"),
        "moneyflow_score": (moneyflow_rate or 0.0) * score_config.weight("moneyflow_rate"),
        "top_list_score": (top_count or 0.0) * score_config.weight("top_list_count"),
        "limit_pool_score": (limit_count or 0.0) * score_config.weight("limit_pool_count"),
    }


def _attach_elasticity_scores(frame: pd.DataFrame, score_config: FeatureScoreConfig) -> pd.DataFrame:
    output = frame.copy()
    scores = output.apply(lambda row: _elasticity_score_parts(row, score_config), axis=1, result_type="expand")
    for column in scores.columns:
        output[column] = scores[column]
    output["elasticity_score"] = scores[
        ["momentum_score", "volume_score", "turnover_score", "moneyflow_score", "top_list_score", "limit_pool_score", "size_penalty_score"]
    ].sum(axis=1)
    return output


def _elasticity_score_parts(row: pd.Series, score_config: FeatureScoreConfig) -> dict[str, float]:
    window_return = _series_float(row, "window_return_pct")
    amount_boost = _series_float(row, "amount_vs_avg")
    turnover = _series_float(row, "latest_turnover_rate")
    circ_mv = _series_float(row, "latest_circ_mv")
    moneyflow_rate = _series_float(row, "moneyflow_net_amount_rate")
    top_count = _series_float(row, "top_list_count")
    limit_count = _series_float(row, "limit_pool_count")
    size_penalty = min((circ_mv or 0.0) / score_config.param("size_penalty_divisor", 500000.0), score_config.param("size_penalty_cap", 8.0))
    return {
        "momentum_score": window_return * score_config.weight("window_return"),
        "volume_score": max((amount_boost or 0.0) - 1.0, 0.0) * score_config.weight("amount_excess"),
        "turnover_score": (turnover or 0.0) * score_config.weight("turnover"),
        "moneyflow_score": (moneyflow_rate or 0.0) * score_config.weight("moneyflow_rate"),
        "top_list_score": (top_count or 0.0) * score_config.weight("top_list_count"),
        "limit_pool_score": (limit_count or 0.0) * score_config.weight("limit_pool_count"),
        "size_penalty_score": size_penalty * score_config.weight("size_penalty"),
    }


def _latest_by_ts_code(frame: pd.DataFrame) -> pd.DataFrame:
    if "trade_date" not in frame.columns:
        return frame.drop_duplicates("ts_code", keep="last")
    working = frame.copy()
    working["trade_date"] = working["trade_date"].astype(str)
    return working.sort_values("trade_date").drop_duplicates("ts_code", keep="last")


def _fill_missing_columns(frame: pd.DataFrame, defaults: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    for column, default in defaults.items():
        if column not in output.columns:
            output[column] = default
        else:
            if default is None:
                output[column] = output[column].where(output[column].notna(), None)
            else:
                output[column] = output[column].fillna(default)
    return output


def _series_float(row: pd.Series, column: str) -> float:
    if column not in row or pd.isna(row[column]):
        return 0.0
    return float(row[column])


def _frontload_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    existing = [column for column in columns if column in frame.columns]
    rest = [column for column in frame.columns if column not in existing]
    return frame[existing + rest]


def _limit_sentiment_score(up_count: int, down_count: int, ths_count: int, score_config: FeatureScoreConfig) -> float:
    return float(
        up_count * score_config.weight("up_count")
        + down_count * score_config.weight("down_count")
        + ths_count * score_config.weight("ths_count")
    )


def _amount_excess(amount_vs_avg: float | None, score_config: FeatureScoreConfig) -> float:
    if amount_vs_avg is None:
        return 0.0
    raw = amount_vs_avg - 1.0
    return min(
        max(raw, score_config.param("amount_excess_floor", -1.0)),
        score_config.param("amount_excess_cap", 3.0),
    )


def _max_board_height(frame: pd.DataFrame) -> int:
    values: list[int] = []
    for raw in frame.get("tag", pd.Series(dtype=str)).dropna().astype(str):
        if "首板" in raw:
            values.append(1)
            continue
        board_match = re.search(r"(\d+)板", raw)
        if board_match:
            values.append(int(board_match.group(1)))
    return max(values) if values else 0


def _attach_latest_columns(
    frame: pd.DataFrame,
    latest: pd.DataFrame,
    *,
    key: str,
    columns: list[str],
    prefix: str,
) -> pd.DataFrame:
    if frame.empty or latest.empty:
        return frame
    keep = [key, *[column for column in columns if column in latest.columns]]
    addon = latest[keep].copy()
    addon = addon.rename(columns={column: f"{prefix}{column}" for column in keep if column != key})
    return frame.merge(addon, on=key, how="left")


def _safe_mean(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns or frame.empty:
        return None
    value = pd.to_numeric(frame[column], errors="coerce").mean()
    return None if pd.isna(value) else float(value)


def _safe_sum(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns or frame.empty:
        return None
    value = pd.to_numeric(frame[column], errors="coerce").sum()
    return None if pd.isna(value) else float(value)


def _nullable_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _input_summary(dataset: str, frame: pd.DataFrame, date_column: str) -> dict[str, Any]:
    if frame.empty or date_column not in frame.columns:
        return {"dataset": dataset, "rows": int(len(frame))}
    dates = frame[date_column].astype(str)
    return {
        "dataset": dataset,
        "rows": int(len(frame)),
        "start": str(dates.min()),
        "end": str(dates.max()),
    }


def _is_usable_input(info: dict[str, Any], frame: pd.DataFrame) -> bool:
    if frame.empty:
        return False
    return str(info.get("status", "ok")) not in {"missing", "read_error"}


def _snapshot_input_info(
    info: dict[str, Any],
    *,
    requested_partition: dict[str, str],
    actual_partition: dict[str, str],
    mode: str,
) -> dict[str, Any]:
    output = dict(info)
    output["requested_partition"] = dict(requested_partition)
    output["partition"] = dict(actual_partition)
    output["snapshot_mode"] = mode
    output["partition_mode"] = mode
    output["historical_precision"] = "exact" if mode == "exact" else "approximate" if mode == "latest_available" else "missing"
    if mode == "latest_available":
        output["status"] = "fallback_snapshot"
        output["message"] = f"using latest_available snapshot {actual_partition} for requested {requested_partition}"
    return output
