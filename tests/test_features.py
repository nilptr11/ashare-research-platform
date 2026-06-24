import json

import pandas as pd
import pytest

from ashare_research.features import FeatureBuilder, FeatureStore
from ashare_research.marts.reader import MartReader


def test_build_market_strength_writes_feature_partition(tmp_path):
    _write_partition(
        tmp_path,
        "index_daily",
        "trade_date",
        "20260622",
        [
            {"ts_code": "000001.SH", "trade_date": "20260622", "close": 100.0, "pct_chg": 0.0, "amount": 1000.0},
            {"ts_code": "000300.SH", "trade_date": "20260622", "close": 200.0, "pct_chg": 0.0, "amount": 1000.0},
        ],
    )
    _write_partition(
        tmp_path,
        "index_daily",
        "trade_date",
        "20260623",
        [
            {"ts_code": "000001.SH", "trade_date": "20260623", "close": 110.0, "pct_chg": 10.0, "amount": 2000.0},
            {"ts_code": "000300.SH", "trade_date": "20260623", "close": 190.0, "pct_chg": -5.0, "amount": 1000.0},
        ],
    )
    _write_partition(
        tmp_path,
        "index_dailybasic",
        "trade_date",
        "20260623",
        [
            {
                "ts_code": "000001.SH",
                "trade_date": "20260623",
                "turnover_rate": 1.5,
                "pe_ttm": 12.0,
                "pb": 1.1,
                "total_mv": 10000.0,
                "float_mv": 8000.0,
            },
            {
                "ts_code": "000300.SH",
                "trade_date": "20260623",
                "turnover_rate": 1.0,
                "pe_ttm": 11.0,
                "pb": 1.0,
                "total_mv": 9000.0,
                "float_mv": 7000.0,
            },
        ],
    )

    reader = MartReader(data_dir=tmp_path)
    result = FeatureBuilder(reader).build("market_strength", as_of="20260623", windows=[2])[0]
    store = FeatureStore(tmp_path)
    frame = store.read_partition("market_strength", as_of="20260623", window=2)
    meta = store.load_meta("market_strength", as_of="20260623", window=2)

    assert result.rows == 2
    assert frame.iloc[0]["ts_code"] == "000001.SH"
    assert frame.iloc[0]["window_return_pct"] == pytest.approx(10.0)
    assert frame.iloc[0]["latest_pe_ttm"] == 12.0
    assert meta.feature == "market_strength"
    assert {item["dataset"] for item in meta.inputs} == {"index_daily", "index_dailybasic"}


def test_build_limit_sentiment_extracts_board_height(tmp_path):
    _write_partition(
        tmp_path,
        "limit_list_d",
        "trade_date",
        "20260623",
        [
            {"trade_date": "20260623", "ts_code": "000001.SZ", "limit": "U"},
            {"trade_date": "20260623", "ts_code": "000002.SZ", "limit": "D"},
            {"trade_date": "20260623", "ts_code": "000003.SZ", "limit": "U"},
        ],
    )
    _write_partition(
        tmp_path,
        "limit_list_ths",
        "trade_date",
        "20260623",
        [
            {
                "trade_date": "20260623",
                "ts_code": "600707.SH",
                "tag": "4天2板",
                "open_num": 4,
                "limit_amount": 100.0,
                "limit_order": 10.0,
            }
        ],
    )

    reader = MartReader(data_dir=tmp_path)
    FeatureBuilder(reader).build("limit_sentiment", as_of="20260623", windows=[1])
    frame = FeatureStore(tmp_path).read_partition("limit_sentiment", as_of="20260623", window=1)

    assert frame.iloc[0]["limit_up_count"] == 2
    assert frame.iloc[0]["limit_down_count"] == 1
    assert frame.iloc[0]["max_board_height"] == 2
    assert frame.iloc[0]["sentiment_score"] == 1.5


def test_build_concept_strength_from_dc_index(tmp_path):
    _write_partition(
        tmp_path,
        "dc_index",
        "trade_date",
        "20260622",
        [
            {"ts_code": "BK001", "trade_date": "20260622", "name": "AI 算力", "pct_change": 1.0, "leading": "A", "leading_code": "000001.SZ", "leading_pct": 3.0, "turnover_rate": 1.0, "total_mv": 1000.0, "up_num": 20, "down_num": 10},
            {"ts_code": "BK002", "trade_date": "20260622", "name": "消费", "pct_change": -1.0, "leading": "B", "leading_code": "000002.SZ", "leading_pct": 1.0, "turnover_rate": 0.5, "total_mv": 800.0, "up_num": 8, "down_num": 18},
        ],
    )
    _write_partition(
        tmp_path,
        "dc_index",
        "trade_date",
        "20260623",
        [
            {"ts_code": "BK001", "trade_date": "20260623", "name": "AI 算力", "pct_change": 4.0, "leading": "A", "leading_code": "000001.SZ", "leading_pct": 8.0, "turnover_rate": 2.0, "total_mv": 1200.0, "up_num": 25, "down_num": 5},
            {"ts_code": "BK002", "trade_date": "20260623", "name": "消费", "pct_change": -2.0, "leading": "B", "leading_code": "000002.SZ", "leading_pct": 2.0, "turnover_rate": 0.8, "total_mv": 700.0, "up_num": 6, "down_num": 24},
        ],
    )

    FeatureBuilder(MartReader(data_dir=tmp_path)).build("concept_strength", as_of="20260623", windows=[2])
    frame = FeatureStore(tmp_path).read_partition("concept_strength", as_of="20260623", window=2)

    assert frame.iloc[0]["ts_code"] == "BK001"
    assert frame.iloc[0]["window_return_pct"] == pytest.approx(5.0)
    assert frame.iloc[0]["breadth_score"] == pytest.approx(20 / 30)


def test_build_leader_validation_uses_moneyflow_top_list_and_limit_pool(tmp_path):
    _write_stock_feature_inputs(tmp_path)

    FeatureBuilder(MartReader(data_dir=tmp_path)).build("leader_validation", as_of="20260623", windows=[2])
    frame = FeatureStore(tmp_path).read_partition("leader_validation", as_of="20260623", window=2)

    assert frame.iloc[0]["ts_code"] == "000001.SZ"
    assert frame.iloc[0]["name"] == "龙头股份"
    assert frame.iloc[0]["top_list_count"] == 1
    assert frame.iloc[0]["latest_limit_pool"] == True
    assert frame.iloc[0]["leader_score"] > frame.iloc[1]["leader_score"]


def test_build_elasticity_candidates_prefers_smaller_momentum_stock(tmp_path):
    _write_stock_feature_inputs(tmp_path)

    FeatureBuilder(MartReader(data_dir=tmp_path)).build("elasticity_candidates", as_of="20260623", windows=[2])
    frame = FeatureStore(tmp_path).read_partition("elasticity_candidates", as_of="20260623", window=2)

    assert frame.iloc[0]["ts_code"] == "000002.SZ"
    assert frame.iloc[0]["elasticity_rank"] == 1
    assert frame.iloc[0]["elasticity_score"] > frame.iloc[1]["elasticity_score"]


def _write_stock_feature_inputs(tmp_path):
    _write_partition(
        tmp_path,
        "daily",
        "trade_date",
        "20260622",
        [
            {"ts_code": "000001.SZ", "trade_date": "20260622", "close": 10.0, "pct_chg": 0.0, "amount": 1000.0},
            {"ts_code": "000002.SZ", "trade_date": "20260622", "close": 10.0, "pct_chg": 0.0, "amount": 500.0},
        ],
    )
    _write_partition(
        tmp_path,
        "daily",
        "trade_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "trade_date": "20260623", "close": 11.0, "pct_chg": 10.0, "amount": 2500.0},
            {"ts_code": "000002.SZ", "trade_date": "20260623", "close": 12.0, "pct_chg": 20.0, "amount": 2000.0},
        ],
    )
    _write_partition(
        tmp_path,
        "daily_basic",
        "trade_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "trade_date": "20260623", "turnover_rate": 5.0, "volume_ratio": 2.0, "pe_ttm": 20.0, "pb": 2.0, "total_mv": 2000000.0, "circ_mv": 1500000.0},
            {"ts_code": "000002.SZ", "trade_date": "20260623", "turnover_rate": 18.0, "volume_ratio": 4.0, "pe_ttm": 30.0, "pb": 4.0, "total_mv": 120000.0, "circ_mv": 90000.0},
        ],
    )
    _write_partition(
        tmp_path,
        "stock_basic",
        "snapshot_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "name": "龙头股份", "industry": "硬件", "market": "主板", "list_status": "L"},
            {"ts_code": "000002.SZ", "name": "弹性股份", "industry": "硬件", "market": "创业板", "list_status": "L"},
        ],
    )
    _write_partition(
        tmp_path,
        "moneyflow_dc",
        "trade_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "trade_date": "20260623", "net_amount": 1000.0, "net_amount_rate": 6.0, "buy_elg_amount_rate": 4.0, "buy_lg_amount_rate": 2.0},
            {"ts_code": "000002.SZ", "trade_date": "20260623", "net_amount": 500.0, "net_amount_rate": 12.0, "buy_elg_amount_rate": 6.0, "buy_lg_amount_rate": 4.0},
        ],
    )
    _write_partition(
        tmp_path,
        "top_list",
        "trade_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "trade_date": "20260623", "net_amount": 800.0, "reason": "日涨幅偏离值达7%"},
        ],
    )
    _write_partition(
        tmp_path,
        "limit_list_ths",
        "trade_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "trade_date": "20260623", "tag": "2连板", "limit_amount": 300.0},
            {"ts_code": "000002.SZ", "trade_date": "20260623", "tag": "首板", "limit_amount": 200.0},
        ],
    )


def _write_partition(data_dir, dataset, key, value, rows):
    partition_dir = data_dir / "mart" / dataset / f"{key}={value}"
    partition_dir.mkdir(parents=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(partition_dir / "part.parquet", index=False)
    (partition_dir / "_meta.json").write_text(
        json.dumps(
            {
                "schema": "ashare.mart_partition.v1",
                "dataset": dataset,
                "partition": {key: value},
                "rows": len(frame),
                "columns": list(frame.columns),
            }
        ),
        encoding="utf-8",
    )
