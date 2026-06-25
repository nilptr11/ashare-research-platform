import json
from pathlib import Path

import pandas as pd

from ashare_research.cli import main
from ashare_research.context_packs import ContextPackBuilder
from ashare_research.daily import build_status
from ashare_research.evidence import EvidenceStore
from ashare_research.features import FeatureBuilder, FeatureRegistry, FeatureStore
from ashare_research.knowledge import KnowledgeStore
from ashare_research.marts import MartReader


def _evidence_record():
    return {
        "claim": "AI infrastructure capex remains elevated.",
        "topic": "capex",
        "industry": "ai_infrastructure",
        "product": "data_center",
        "company": "Microsoft",
        "region": "United States",
        "metric": "capital_expenditures",
        "value": 34.9,
        "unit": "USD billion",
        "period": "FY2026 Q1",
        "frequency": "quarterly",
        "source_type": "company_ir",
        "source_name": "Microsoft Investor Relations",
        "source_url": "https://example.com/msft-ir",
        "published_at": "2025-10-29",
        "query_time": "2026-06-24T15:26:50+08:00",
        "confidence": "high",
        "verification": "official_single_source",
    }


def _knowledge_record():
    return {
        "id": "theme_chain:ai_infrastructure:optical_interconnect",
        "subject": {
            "type": "industry",
            "id": "ai_infrastructure",
            "name": "ai_infrastructure",
            "aliases": ["AI 算力"],
        },
        "predicate": "has_component",
        "object": {
            "type": "industry_chain_node",
            "id": "optical_interconnect",
            "name": "optical_interconnect",
            "aliases": ["光互连"],
        },
        "confidence": "medium",
        "source": {
            "source_type": "industry_association",
            "source_url": "https://example.com/industry-map",
            "published_at": "2026-05-01",
        },
        "valid_from": "2026-05-01",
    }


def test_market_context_pack_writes_with_gaps(tmp_path):
    payload = ContextPackBuilder(tmp_path).build_market_structure(as_of="20260623")

    assert payload["schema"] == "ashare.context_pack.market_structure.v1"
    assert payload["coverage"]["datasets_total"] > 0
    assert payload["data_gaps"]
    assert any(flag.startswith("missing_or_unready_mart:") for flag in payload["quality_flags"])
    assert payload["agent_guidance"]["unsupported_claims"]
    assert Path(payload["path"]).exists()


def test_daily_status_degrades_stale_context_window(monkeypatch, tmp_path):
    from ashare_research import daily

    class EmptyFeatureRegistry:
        def list(self):
            return []

    ContextPackBuilder(tmp_path).build_market_structure(as_of="20260623", trade_days=60)
    monkeypatch.setattr(daily, "daily_plan", lambda: [])
    monkeypatch.setattr(daily.FeatureRegistry, "builtin", lambda: EmptyFeatureRegistry())

    payload = build_status(MartReader(tmp_path), as_of="20260623", context_trade_days=120)

    assert payload["status"] == "degraded"
    assert payload["context"]["status"] == "degraded"
    assert "stale_context_trade_days" in payload["context"]["dependency_check"]["flags"]


def test_industry_context_pack_includes_evidence_and_knowledge(tmp_path):
    EvidenceStore(tmp_path).ingest_evidence(_evidence_record())
    knowledge_store = KnowledgeStore(tmp_path)
    proposal = knowledge_store.propose(_knowledge_record())
    knowledge_store.accept(proposal.proposal_id)

    payload = ContextPackBuilder(tmp_path).build_industry(industry="ai_infrastructure", as_of="20260623")

    assert payload["schema"] == "ashare.context_pack.industry.v1"
    assert payload["coverage"]["evidence_records"] == 1
    assert payload["coverage"]["knowledge_records"] == 1
    assert any(item["kind"] == "evidence" and item["content_hash"] for item in payload["inputs"])
    assert any(item["kind"] == "knowledge" and item["content_hash"] for item in payload["inputs"])


def test_industry_chain_context_pack_includes_feature_previews_evidence_and_knowledge(tmp_path):
    _write_industry_chain_features(tmp_path)
    EvidenceStore(tmp_path).ingest_evidence(_evidence_record() | {"industry": "AI"})
    knowledge_store = KnowledgeStore(tmp_path)
    proposal = knowledge_store.propose(_knowledge_record())
    knowledge_store.accept(proposal.proposal_id)

    payload = ContextPackBuilder(tmp_path).build_industry_chain(theme="AI", as_of="20260623", windows=[5], preview_limit=5)

    assert payload["schema"] == "ashare.context_pack.industry_chain.v1"
    assert payload["pack_type"] == "industry_chain"
    assert payload["sections"]["theme"]["protocol"] == "industry_chain_selection.v1"
    assert payload["coverage"]["feature_preview_rows"] >= 4
    assert payload["coverage"]["evidence_records"] == 1
    assert payload["coverage"]["knowledge_records"] == 1
    assert payload["constraints"]["no_trade_execution"] is True
    assert "自动化交易执行" in payload["agent_guidance"]["unsupported_claims"]
    previews = {
        (item["feature"], item["window"]): item
        for item in payload["sections"]["feature_previews"]
    }
    assert previews[("concept_strength", 5)]["match_mode"] == "theme_filtered"
    assert previews[("leader_validation", 5)]["rows"][0]["name"] == "AI龙头"


def test_market_context_exposes_feature_snapshot_precision_notes(tmp_path):
    _write_partition(
        tmp_path,
        "sw_daily",
        "trade_date",
        "20260326",
        [{"ts_code": "801080.SI", "trade_date": "20260326", "close": 100.0, "pct_change": 1.0}],
    )
    _write_partition(
        tmp_path,
        "ci_daily",
        "trade_date",
        "20260326",
        [{"ts_code": "CI005016.CI", "trade_date": "20260326", "close": 200.0, "pct_change": 2.0}],
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
        "ci_index_member",
        "snapshot_date",
        "20260624",
        [{"ts_code": "000002.SZ", "l1_code": "CI005016.CI", "l1_name": "家电", "l2_code": "CI005145.CI", "l2_name": "白色家电", "l3_code": "CI005306.CI", "l3_name": "白电"}],
    )

    reader = MartReader(tmp_path)
    FeatureBuilder(reader).build("industry_strength", as_of="20260326", windows=[1])
    payload = ContextPackBuilder(tmp_path, reader=reader).build_market_structure(as_of="20260326", windows=[1])

    notes = payload["agent_guidance"]["precision_notes"]
    assert any(item["kind"] == "feature_component" and item["name"] == "industry_strength:sw_industry_hierarchy" for item in notes)
    assert any(item["partition"] == {"snapshot_date": "20260624"} for item in notes)


def test_stock_context_uses_latest_snapshot_for_identity(tmp_path):
    _write_partition(
        tmp_path,
        "daily",
        "trade_date",
        "20260326",
        [{"ts_code": "000001.SZ", "trade_date": "20260326", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "pct_chg": 1.0, "vol": 100.0, "amount": 1000.0}],
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
        [{"ts_code": "000001.SZ", "symbol": "000001", "name": "龙头股份", "market": "主板", "list_status": "L"}],
    )

    payload = ContextPackBuilder(tmp_path).build_stock(ts_code="000001.SZ", as_of="20260326")
    stock_basic_input = next(item for item in payload["inputs"] if item["kind"] == "mart" and item["name"] == "stock_basic")

    assert payload["sections"]["stock"]["mart_rows"]["stock_basic"][0]["name"] == "龙头股份"
    assert stock_basic_input["details"]["requested_partition"] == {"snapshot_date": "20260326"}
    assert stock_basic_input["details"]["partition"] == {"snapshot_date": "20260624"}
    assert stock_basic_input["details"]["partition_mode"] == "latest_available"
    assert stock_basic_input["details"]["historical_precision"] == "approximate"


def test_cli_context_build_stock(capsys, tmp_path):
    output_path = tmp_path / "context" / "stock.json"

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "context",
            "build",
            "stock",
            "603938.SH",
            "--as-of",
            "20260623",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "ashare.context_pack.stock.v1"
    assert payload["path"] == str(output_path)
    assert output_path.exists()


def test_cli_context_build_industry_chain(capsys, tmp_path):
    output_path = tmp_path / "context" / "industry_chain.json"

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "context",
            "build",
            "industry-chain",
            "AI",
            "--as-of",
            "20260623",
            "--windows",
            "5",
            "--preview-limit",
            "3",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "ashare.context_pack.industry_chain.v1"
    assert payload["path"] == str(output_path)
    assert output_path.exists()


def _write_industry_chain_features(data_dir):
    registry = FeatureRegistry.builtin()
    store = FeatureStore(data_dir)
    common_inputs = {
        "daily": {"dataset": "daily", "rows": 2},
        "daily_basic": {"dataset": "daily_basic", "rows": 2},
        "stock_basic": {"dataset": "stock_basic", "rows": 2},
        "moneyflow_dc": {"dataset": "moneyflow_dc", "rows": 2},
        "top_list": {"dataset": "top_list", "rows": 1},
        "limit_list_ths": {"dataset": "limit_list_ths", "rows": 1},
        "index_member_all": {"dataset": "index_member_all", "rows": 2},
    }
    store.write_partition(
        registry.require("industry_strength"),
        pd.DataFrame(
            [
                {
                    "as_of": "20260623",
                    "window": 5,
                    "source_dataset": "sw_daily",
                    "ts_code": "801080.SI",
                    "name": "AI设备",
                    "industry_name": "AI设备",
                    "strength_score": 10.0,
                    "window_return_pct": 8.0,
                }
            ]
        ),
        as_of="20260623",
        window=5,
        inputs=[
            {"dataset": "sw_daily", "rows": 1},
            {"dataset": "ci_daily", "rows": 1},
            {"dataset": "index_member_all", "rows": 1},
            {"dataset": "ci_index_member", "rows": 1},
        ],
    )
    store.write_partition(
        registry.require("concept_strength"),
        pd.DataFrame(
            [
                {
                    "as_of": "20260623",
                    "window": 5,
                    "source_dataset": "dc_index",
                    "ts_code": "BKAI",
                    "name": "AI算力",
                    "latest_pct_chg": 3.0,
                    "strength_score": 12.0,
                    "window_return_pct": 9.0,
                    "latest_leading": "AI龙头",
                }
            ]
        ),
        as_of="20260623",
        window=5,
        inputs=[{"dataset": "dc_index", "rows": 1}],
    )
    store.write_partition(
        registry.require("leader_validation"),
        pd.DataFrame(
            [
                {
                    "as_of": "20260623",
                    "window": 5,
                    "ts_code": "000001.SZ",
                    "name": "AI龙头",
                    "sw_l1_name": "AI设备",
                    "sw_l2_name": "AI服务器",
                    "sw_l3_name": "AI加速卡",
                    "leader_score": 20.0,
                    "window_return_pct": 15.0,
                }
            ]
        ),
        as_of="20260623",
        window=5,
        inputs=list(common_inputs.values()),
    )
    store.write_partition(
        registry.require("elasticity_candidates"),
        pd.DataFrame(
            [
                {
                    "as_of": "20260623",
                    "window": 5,
                    "ts_code": "000002.SZ",
                    "name": "AI弹性",
                    "sw_l1_name": "AI设备",
                    "sw_l2_name": "AI服务器",
                    "sw_l3_name": "AI连接器",
                    "elasticity_score": 18.0,
                    "window_return_pct": 12.0,
                }
            ]
        ),
        as_of="20260623",
        window=5,
        inputs=list(common_inputs.values()),
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
