import json
from pathlib import Path

from ashare_research.cli import main
from ashare_research.context_packs import ContextPackBuilder
from ashare_research.runs import RunRecorder, replay_run


def test_run_recorder_records_and_replays(tmp_path):
    context_path = tmp_path / "context.json"
    ContextPackBuilder(tmp_path).build_market_structure(as_of="20260623", output_path=context_path)
    recorder = RunRecorder(tmp_path, runs_dir=tmp_path / "runs")

    manifest = recorder.record(
        question="按市场结构框架分析 AI 算力硬件链",
        as_of="20260623",
        context_pack_paths=[context_path],
        run_id="test_run",
    )

    run_dir = Path(manifest["path"])
    assert (run_dir / "run.json").exists()
    assert (run_dir / "context_pack.json").exists()
    assert "not a factual source" in (run_dir / "report.md").read_text(encoding="utf-8")
    assert manifest["protocol_id"] == "user_directed.v1"
    assert manifest["quality_gates"]["status"] == "warning"

    replay = replay_run(run_dir)
    assert replay["status"] == "replayable"
    assert replay["quality_status"] == "warning"


def test_run_recorder_uses_registered_protocol_when_requested(tmp_path):
    context_path = tmp_path / "context.json"
    ContextPackBuilder(tmp_path).build_market_structure(as_of="20260623", output_path=context_path)
    recorder = RunRecorder(tmp_path, runs_dir=tmp_path / "runs")

    manifest = recorder.record(
        question="按市场结构框架分析 AI 算力硬件链",
        as_of="20260623",
        protocol_id="market_structure.v1",
        context_pack_paths=[context_path],
        run_id="registered_protocol_run",
    )

    assert manifest["protocol_id"] == "market_structure.v1"
    assert manifest["quality_gates"]["status"] == "blocked"


def test_cli_runs_record_list_replay(capsys, tmp_path):
    context_path = tmp_path / "context.json"
    ContextPackBuilder(tmp_path).build_market_structure(as_of="20260623", output_path=context_path)
    runs_dir = tmp_path / "runs"

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
            "--context-pack",
            str(context_path),
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

    exit_code = main(["--data-dir", str(tmp_path), "runs", "list", "--runs-dir", str(runs_dir), "--format", "json"])
    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload[0]["run_id"] == "cli_run"

    exit_code = main(["--data-dir", str(tmp_path), "runs", "replay", run_dir])
    assert exit_code == 0
    replay_payload = json.loads(capsys.readouterr().out)
    assert replay_payload["status"] == "replayable"
