import json

import pandas as pd
import pytest

from ashare_research.features import FeatureBuilder, FeatureStore, ScoringProfile
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


def test_feature_build_uses_configurable_scoring_profile(tmp_path):
    _write_partition(
        tmp_path,
        "index_daily",
        "trade_date",
        "20260622",
        [{"ts_code": "000001.SH", "trade_date": "20260622", "close": 100.0, "pct_chg": 0.0, "amount": 1000.0}],
    )
    _write_partition(
        tmp_path,
        "index_daily",
        "trade_date",
        "20260623",
        [{"ts_code": "000001.SH", "trade_date": "20260623", "close": 110.0, "pct_chg": 10.0, "amount": 2000.0}],
    )
    _write_partition(
        tmp_path,
        "index_dailybasic",
        "trade_date",
        "20260623",
        [{"ts_code": "000001.SH", "trade_date": "20260623", "turnover_rate": 1.5, "pe_ttm": 12.0, "pb": 1.1, "total_mv": 10000.0, "float_mv": 8000.0}],
    )
    profile_path = tmp_path / "scoring.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema": "ashare.feature_scoring_profile.v1",
                "profile_id": "volume_only.v1",
                "version": "v1",
                "features": {
                    "market_strength": {
                        "weights": {"window_return": 0.0, "amount_excess": 10.0},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    reader = MartReader(data_dir=tmp_path)
    profile = ScoringProfile.from_file(profile_path)
    FeatureBuilder(reader, scoring_profile=profile).build("market_strength", as_of="20260623", windows=[2])
    frame = FeatureStore(tmp_path).read_partition("market_strength", as_of="20260623", window=2)
    meta = FeatureStore(tmp_path).load_meta("market_strength", as_of="20260623", window=2)

    assert frame.iloc[0]["momentum_score"] == pytest.approx(0.0)
    assert frame.iloc[0]["volume_score"] == pytest.approx((2000.0 / 1500.0 - 1.0) * 10.0)
    assert frame.iloc[0]["strength_score"] == pytest.approx((2000.0 / 1500.0 - 1.0) * 10.0)
    assert meta.scoring["profile_id"] == "volume_only.v1"
    assert meta.scoring["source_path"] == str(profile_path)
    assert meta.quality["scoring"]["profile_hash"] == meta.scoring["profile_hash"]


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


def test_concept_strength_quality_degrades_when_scores_are_empty(tmp_path):
    _write_partition(
        tmp_path,
        "dc_index",
        "trade_date",
        "20260623",
        [{"ts_code": "BK001", "trade_date": "20260623"}],
    )

    FeatureBuilder(MartReader(data_dir=tmp_path)).build("concept_strength", as_of="20260623", windows=[1])
    meta = FeatureStore(tmp_path).load_meta("concept_strength", as_of="20260623", window=1)

    assert meta.quality_status == "degraded"
    assert meta.quality["reason"] == "analysis columns below non-null threshold"
    assert meta.quality["non_null_ratios"]["strength_score"] == 0.0


def test_industry_strength_enriches_industry_names_and_levels(tmp_path):
    _write_partition(
        tmp_path,
        "sw_daily",
        "trade_date",
        "20260623",
        [{"ts_code": "801010.SI", "trade_date": "20260623", "close": 100.0, "pct_change": 1.0}],
    )
    _write_partition(
        tmp_path,
        "ci_daily",
        "trade_date",
        "20260623",
        [{"ts_code": "CI005016.CI", "trade_date": "20260623", "close": 200.0}],
    )
    _write_partition(
        tmp_path,
        "index_member_all",
        "snapshot_date",
        "20260623",
        [
            {
                "l1_code": "801010.SI",
                "l1_name": "农林牧渔",
                "l2_code": "801011.SI",
                "l2_name": "种植业",
                "l3_code": "801012.SI",
                "l3_name": "粮食种植",
                "ts_code": "000001.SZ",
            }
        ],
    )
    _write_partition(
        tmp_path,
        "ci_index_member",
        "snapshot_date",
        "20260623",
        [
            {
                "l1_code": "CI005016.CI",
                "l1_name": "家电",
                "l2_code": "CI005145.CI",
                "l2_name": "白色家电Ⅱ",
                "l3_code": "CI005306.CI",
                "l3_name": "白色家电Ⅲ",
                "ts_code": "000002.SZ",
            }
        ],
    )

    FeatureBuilder(MartReader(data_dir=tmp_path)).build("industry_strength", as_of="20260623", windows=[1])
    frame = FeatureStore(tmp_path).read_partition("industry_strength", as_of="20260623", window=1)
    meta = FeatureStore(tmp_path).load_meta("industry_strength", as_of="20260623", window=1)

    sw_row = frame[frame["ts_code"] == "801010.SI"].iloc[0]
    ci_row = frame[frame["ts_code"] == "CI005016.CI"].iloc[0]
    assert sw_row["industry_name"] == "农林牧渔"
    assert sw_row["industry_level"] == "L1"
    assert sw_row["l1"] == "农林牧渔"
    assert ci_row["industry_name"] == "家电"
    assert meta.quality_status == "ok"


def test_build_leader_validation_uses_moneyflow_top_list_and_limit_pool(tmp_path):
    _write_stock_feature_inputs(tmp_path)

    FeatureBuilder(MartReader(data_dir=tmp_path)).build("leader_validation", as_of="20260623", windows=[2])
    frame = FeatureStore(tmp_path).read_partition("leader_validation", as_of="20260623", window=2)

    assert frame.iloc[0]["ts_code"] == "000001.SZ"
    assert frame.iloc[0]["name"] == "龙头股份"
    assert frame.iloc[0]["sw_l1_name"] == "电子"
    assert frame.iloc[0]["top_list_count"] == 1
    assert frame.iloc[0]["latest_limit_pool"] == True
    assert frame.iloc[0]["leader_score"] > frame.iloc[1]["leader_score"]


def test_feature_quality_degrades_when_optional_components_are_missing(tmp_path):
    _write_partition(
        tmp_path,
        "daily",
        "trade_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "trade_date": "20260623", "close": 10.0, "pct_chg": 1.0, "amount": 1000.0},
            {"ts_code": "000002.SZ", "trade_date": "20260623", "close": 8.0, "pct_chg": 0.5, "amount": 500.0},
        ],
    )
    _write_partition(
        tmp_path,
        "daily_basic",
        "trade_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "trade_date": "20260623", "turnover_rate": 3.0, "volume_ratio": 1.5, "pe_ttm": 20.0, "pb": 2.0, "total_mv": 100000.0, "circ_mv": 80000.0},
            {"ts_code": "000002.SZ", "trade_date": "20260623", "turnover_rate": 2.0, "volume_ratio": 1.2, "pe_ttm": 30.0, "pb": 3.0, "total_mv": 80000.0, "circ_mv": 60000.0},
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

    FeatureBuilder(MartReader(data_dir=tmp_path)).build("leader_validation", as_of="20260623", windows=[1])
    meta = FeatureStore(tmp_path).load_meta("leader_validation", as_of="20260623", window=1)

    assert meta.quality_status == "degraded"
    assert meta.quality["component_quality"]["moneyflow"]["status"] == "degraded"
    assert meta.quality["component_quality"]["top_list"]["status"] == "degraded"
    assert "资金确认" in meta.quality["unsupported_claims"]


def test_feature_uses_latest_snapshot_without_degrading_historical_as_of(tmp_path):
    _write_partition(
        tmp_path,
        "daily",
        "trade_date",
        "20260326",
        [{"ts_code": "000001.SZ", "trade_date": "20260326", "close": 10.0, "pct_chg": 1.0, "amount": 1000.0}],
    )
    _write_partition(
        tmp_path,
        "daily_basic",
        "trade_date",
        "20260326",
        [{"ts_code": "000001.SZ", "trade_date": "20260326", "turnover_rate": 3.0, "volume_ratio": 1.5, "pe_ttm": 20.0, "pb": 2.0, "total_mv": 100000.0, "circ_mv": 80000.0}],
    )
    _write_partition(
        tmp_path,
        "stock_basic",
        "snapshot_date",
        "20260624",
        [{"ts_code": "000001.SZ", "name": "龙头股份", "industry": "硬件", "market": "主板", "list_status": "L"}],
    )
    _write_partition(
        tmp_path,
        "index_member_all",
        "snapshot_date",
        "20260624",
        [{"ts_code": "000001.SZ", "l1_code": "801080.SI", "l1_name": "电子", "l2_code": "801081.SI", "l2_name": "半导体", "l3_code": "801082.SI", "l3_name": "数字芯片设计"}],
    )
    _write_partition(
        tmp_path,
        "moneyflow_dc",
        "trade_date",
        "20260326",
        [{"ts_code": "000001.SZ", "trade_date": "20260326", "net_amount": 10.0, "net_amount_rate": 2.0, "buy_elg_amount_rate": 1.0, "buy_lg_amount_rate": 1.0}],
    )
    _write_partition(
        tmp_path,
        "top_list",
        "trade_date",
        "20260326",
        [{"ts_code": "000001.SZ", "trade_date": "20260326", "name": "龙头股份", "reason": "日涨幅偏离", "net_amount": 5.0}],
    )
    _write_partition(
        tmp_path,
        "limit_list_ths",
        "trade_date",
        "20260326",
        [{"ts_code": "000001.SZ", "trade_date": "20260326", "name": "龙头股份", "tag": "首板", "limit_amount": 100.0, "limit_order": 10.0}],
    )

    FeatureBuilder(MartReader(data_dir=tmp_path)).build("leader_validation", as_of="20260326", windows=[1])
    meta = FeatureStore(tmp_path).load_meta("leader_validation", as_of="20260326", window=1)

    assert meta.quality_status == "ok"
    assert meta.quality["component_quality"]["stock_identity"]["partition_mode"] == "latest_available"
    assert meta.quality["component_quality"]["stock_identity"]["historical_precision"] == "approximate"
    assert meta.quality["component_quality"]["sw_industry"]["partition"] == {"snapshot_date": "20260624"}
    assert meta.quality["unsupported_claims"] == []


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
        "index_member_all",
        "snapshot_date",
        "20260623",
        [
            {
                "ts_code": "000001.SZ",
                "l1_code": "801080.SI",
                "l1_name": "电子",
                "l2_code": "801081.SI",
                "l2_name": "半导体",
                "l3_code": "801082.SI",
                "l3_name": "数字芯片设计",
            },
            {
                "ts_code": "000002.SZ",
                "l1_code": "801080.SI",
                "l1_name": "电子",
                "l2_code": "801081.SI",
                "l2_name": "半导体",
                "l3_code": "801083.SI",
                "l3_name": "模拟芯片设计",
            },
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
