import json
from pathlib import Path

import pandas as pd

from ashare_research.cli import main
from ashare_research.features import FeatureRegistry, FeatureStore
from ashare_research.marts.publisher import MartPublisher
from ashare_research.runs import RunRecorder, replay_run


def test_run_recorder_records_and_replays(tmp_path):
    _write_run_data_refs(tmp_path)
    recorder = RunRecorder(tmp_path, runs_dir=tmp_path / "runs")

    manifest = recorder.record(
        question="按市场结构框架分析 AI 算力硬件链",
        as_of="20260623",
        mart_refs=["daily:trade_date=20260623"],
        feature_refs=["market_strength:as_of=20260623,window=20"],
        run_id="test_run",
    )

    run_dir = Path(manifest["path"])
    assert (run_dir / "run.json").exists()
    assert (run_dir / "data_refs.json").exists()
    assert (run_dir / "agent_reasoning.json").exists()
    assert "data_refs: `data_refs.json`" in (run_dir / "report.md").read_text(encoding="utf-8")
    assert "not a factual source" in (run_dir / "report.md").read_text(encoding="utf-8")
    data_refs = json.loads((run_dir / "data_refs.json").read_text(encoding="utf-8"))
    assert data_refs["marts"][0]["partition"] == {"trade_date": "20260623"}
    assert data_refs["features"][0]["partition"] == {"as_of": "20260623", "window": "20"}
    assert data_refs["validation"]["status"] == "ready"
    assert data_refs["marts"][0]["status"] == "ready"
    assert data_refs["features"][0]["status"] == "ready"
    assert manifest["protocol_id"] == "user_directed.v1"
    assert manifest["agent_reasoning"]["status"] == "not_provided"
    assert manifest["quality_gates"]["status"] == "warning"
    assert manifest["quality_gates"]["gates"]["data_refs_gate"]["status"] == "passed"

    replay = replay_run(run_dir)
    assert replay["status"] == "replayable"
    assert replay["quality_status"] == "warning"
    assert any(item["kind"] == "data_refs" for item in replay["artifacts"])


def test_run_recorder_uses_registered_protocol_when_requested(tmp_path):
    _write_run_data_refs(tmp_path)
    recorder = RunRecorder(tmp_path, runs_dir=tmp_path / "runs")

    manifest = recorder.record(
        question="按市场结构框架分析 AI 算力硬件链",
        as_of="20260623",
        protocol_id="market_structure.v1",
        mart_refs=["daily:trade_date=20260623"],
        feature_refs=["market_strength:as_of=20260623,window=20"],
        run_id="registered_protocol_run",
    )

    assert manifest["protocol_id"] == "market_structure.v1"
    assert manifest["quality_gates"]["status"] == "warning"


def test_run_recorder_blocks_missing_data_refs(tmp_path):
    recorder = RunRecorder(tmp_path, runs_dir=tmp_path / "runs")

    manifest = recorder.record(
        question="按市场结构框架分析 AI 算力硬件链",
        as_of="20260623",
        mart_refs=["daily:trade_date=20260623"],
        feature_refs=["market_strength:as_of=20260623,window=20"],
        run_id="missing_refs_run",
    )

    run_dir = Path(manifest["path"])
    data_refs = json.loads((run_dir / "data_refs.json").read_text(encoding="utf-8"))

    assert data_refs["validation"]["status"] == "blocked"
    assert data_refs["marts"][0]["status"] == "missing"
    assert data_refs["features"][0]["status"] == "missing"
    assert manifest["quality_gates"]["status"] == "blocked"
    assert manifest["quality_gates"]["gates"]["data_refs_gate"]["status"] == "blocked"


def test_cli_runs_record_list_replay(capsys, tmp_path):
    _write_run_data_refs(tmp_path)
    runs_dir = tmp_path / "runs"
    reasoning_path = tmp_path / "agent_reasoning.json"
    reasoning_path.write_text(
        json.dumps(
            {
                "schema": "ashare.agent_reasoning.v1",
                "status": "provided",
                "facts_used": [],
                "inferences": ["市场结构偏强"],
                "hypotheses": ["算力链可能有事件催化"],
                "unverified_claims": [],
                "validation_steps": [],
                "open_questions": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "runs",
            "record",
            "--question",
            "按市场结构框架分析 AI 算力硬件链",
            "--as-of",
            "20260623",
            "--mart-ref",
            "daily:trade_date=20260623",
            "--feature-ref",
            "market_strength:as_of=20260623,window=20",
            "--agent-reasoning",
            str(reasoning_path),
            "--runs-dir",
            str(runs_dir),
            "--run-id",
            "cli_run",
        ]
    )
    assert exit_code == 0
    record_payload = json.loads(capsys.readouterr().out)
    run_dir = record_payload["path"]
    assert record_payload["protocol_id"] == "user_directed.v1"
    assert record_payload["agent_reasoning"]["status"] == "provided"

    exit_code = main(["--data-dir", str(tmp_path), "runs", "list", "--runs-dir", str(runs_dir), "--format", "json"])
    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload[0]["run_id"] == "cli_run"

    exit_code = main(["--data-dir", str(tmp_path), "runs", "replay", run_dir])
    assert exit_code == 0
    replay_payload = json.loads(capsys.readouterr().out)
    assert replay_payload["status"] == "replayable"


def _write_run_data_refs(data_dir):
    MartPublisher(data_dir).publish(
        "daily",
        pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260623",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.5,
                    "pct_chg": 5.0,
                    "vol": 100.0,
                    "amount": 1000.0,
                }
            ]
        ),
        partition={"trade_date": "20260623"},
        source={"kind": "fixture"},
    )
    spec = FeatureRegistry.builtin().require("market_strength")
    FeatureStore(data_dir).write_partition(
        spec,
        pd.DataFrame(
            [
                {
                    "as_of": "20260623",
                    "window": 20,
                    "ts_code": "000001.SH",
                    "strength_score": 1.0,
                }
            ]
        ),
        as_of="20260623",
        window=20,
        inputs=[
            {"dataset": "index_daily", "status": "ready", "rows": 1},
            {"dataset": "index_dailybasic", "status": "ready", "rows": 1},
        ],
    )
