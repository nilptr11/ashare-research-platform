import json

from ashare_research.daily import DailyTask, build_status, daily_plan, event_days_for_daily, task_build_params
from ashare_research.schemas import DatasetCheck


def test_daily_plan_keeps_stock_pool_and_financial_tasks_out_of_default_flow():
    datasets = [task.dataset for task in daily_plan()]

    assert "daily" in datasets
    assert "dc_index" in datasets
    assert "dc_member" in datasets
    assert "income" not in datasets
    assert "cyq_chips" not in datasets
    assert datasets.index("dc_index") < datasets.index("dc_member")
    assert datasets.index("tdx_index") < datasets.index("tdx_member")
    assert datasets.index("ths_index") < datasets.index("ths_member")


def test_daily_event_lookback_defaults_and_task_params():
    assert event_days_for_daily() == 7

    notice_task = next(task for task in daily_plan() if task.dataset == "a_stock_notice")
    params = task_build_params(notice_task, as_of="20260624", event_days=7)

    assert params == {"start_date": "20260618", "end_date": "20260624"}


def test_daily_status_reports_degraded_required_data_without_blocking(monkeypatch, tmp_path):
    from ashare_research import daily

    class FakeReader:
        data_dir = tmp_path

        def check_dataset(self, dataset, as_of=None):
            return DatasetCheck(dataset=dataset, status="degraded", registered=True, partition={"trade_date": as_of}, rows=1)

    class EmptyFeatureRegistry:
        def list(self):
            return []

    context_dir = tmp_path / "context_packs" / "market_structure" / "as_of=20260624"
    context_dir.mkdir(parents=True)
    (context_dir / "context.json").write_text(json.dumps({"coverage": {}, "quality_flags": []}), encoding="utf-8")

    monkeypatch.setattr(daily, "daily_plan", lambda: [DailyTask("dc_index", "membership", "trade_date", required=True)])
    monkeypatch.setattr(daily.FeatureRegistry, "builtin", lambda: EmptyFeatureRegistry())

    payload = build_status(FakeReader(), as_of="20260624", windows=[5])

    assert payload["status"] == "degraded"
    assert payload["blocking"] == []
    assert payload["degraded"][0]["dataset"] == "dc_index"


def test_cli_daily_run_writes_report(monkeypatch, capsys, tmp_path):
    from ashare_research import cli

    calls = []

    def fake_build_dataset(args, reader):
        calls.append(args)
        return {"schema": "ashare.data_build_result.v1", "dataset": args.dataset, "rows": 1}

    def fake_build_status(reader, *, as_of, windows, context_trade_days):
        return {
            "schema": "ashare.daily_status.v1",
            "as_of": as_of,
            "status": "ready",
            "coverage": {},
            "datasets": [],
            "features": [],
            "context": {},
            "blocking": [],
            "warnings": [],
            "skipped": [],
        }

    monkeypatch.setattr(cli, "_build_dataset", fake_build_dataset)
    monkeypatch.setattr(cli, "build_status", fake_build_status)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "daily",
            "run",
            "--as-of",
            "20260624",
            "--skip-features",
            "--skip-context",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "ashare.daily_run_report.v1"
    assert payload["status"] == "ready"
    assert payload["refresh"] is True
    assert [call.dataset for call in calls][:3] == ["trade_cal", "stock_basic", "daily"]
    assert calls[0].exchange == "SSE"
    assert calls[0].start_date == "20260101"
    assert calls[0].end_date == "20260624"
    forecast_call = next(call for call in calls if call.dataset == "earnings_forecast")
    assert forecast_call.start_date == "20260618"
    assert forecast_call.end_date == "20260624"
    assert (tmp_path / "reports" / "daily" / "as_of=20260624" / "report.json").exists()
    assert (tmp_path / "reports" / "daily" / "latest.json").exists()


def test_cli_daily_run_propagates_degraded_status(monkeypatch, capsys, tmp_path):
    from ashare_research import cli

    def fake_build_dataset(args, reader):
        return {"schema": "ashare.data_build_result.v1", "dataset": args.dataset, "rows": 1}

    def fake_build_status(reader, *, as_of, windows, context_trade_days):
        return {
            "schema": "ashare.daily_status.v1",
            "as_of": as_of,
            "status": "degraded",
            "coverage": {"degraded": 1},
            "datasets": [{"dataset": "dc_index", "status": "degraded"}],
            "features": [],
            "context": {},
            "blocking": [],
            "degraded": [{"dataset": "dc_index", "status": "degraded"}],
            "warnings": [],
            "skipped": [],
        }

    monkeypatch.setattr(cli, "_build_dataset", fake_build_dataset)
    monkeypatch.setattr(cli, "build_status", fake_build_status)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "daily",
            "run",
            "--as-of",
            "20260624",
            "--skip-features",
            "--skip-context",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "degraded"
    assert payload["status_check"]["status"] == "degraded"


def test_cli_daily_repair_only_runs_unready_datasets(monkeypatch, capsys, tmp_path):
    from ashare_research import cli

    calls = []
    statuses = iter(
        [
            {
                "schema": "ashare.daily_status.v1",
                "as_of": "20260624",
                "status": "blocked",
                "coverage": {},
                "datasets": [
                    {"dataset": "trade_cal", "status": "ready"},
                    {"dataset": "daily", "status": "missing"},
                ],
                "features": [],
                "context": {},
                "blocking": [{"dataset": "daily", "status": "missing"}],
                "warnings": [],
                "skipped": [],
            },
            {
                "schema": "ashare.daily_status.v1",
                "as_of": "20260624",
                "status": "ready",
                "coverage": {},
                "datasets": [],
                "features": [],
                "context": {},
                "blocking": [],
                "warnings": [],
                "skipped": [],
            },
        ]
    )

    monkeypatch.setattr(
        cli,
        "_build_dataset",
        lambda args, reader: calls.append(args.dataset) or {"dataset": args.dataset, "rows": 1},
    )
    monkeypatch.setattr(cli, "build_status", lambda *args, **kwargs: next(statuses))

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "daily",
            "repair",
            "--as-of",
            "20260624",
            "--skip-features",
            "--skip-context",
        ]
    )

    assert exit_code == 0
    assert calls == ["daily"]
    assert json.loads(capsys.readouterr().out)["mode"] == "repair"
