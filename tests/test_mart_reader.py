import json

import pandas as pd

from ashare_research.marts.reader import MartReader


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
                "source": {"kind": "fixture"},
                "published_at": "2026-06-24T00:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return partition_dir


def test_reader_checks_registered_partition(tmp_path):
    _write_partition(
        tmp_path,
        "daily",
        "trade_date",
        "20260623",
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260623",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "pct_chg": 0.0,
                "vol": 10.0,
                "amount": 100.0,
            }
        ],
    )

    reader = MartReader(data_dir=tmp_path)
    check = reader.check_dataset("daily", as_of="20260623")

    assert check.status == "ready"
    assert check.rows == 1
    assert check.partition == {"trade_date": "20260623"}


def test_reader_blocks_schema_mismatch(tmp_path):
    _write_partition(tmp_path, "daily", "trade_date", "20260623", [{"ts_code": "000001.SZ"}])

    reader = MartReader(data_dir=tmp_path)
    check = reader.check_dataset("daily", as_of="20260623")

    assert check.status == "schema_mismatch"
    assert "trade_date" in check.missing_columns


def test_reader_degrades_when_analysis_columns_are_missing(tmp_path):
    _write_partition(tmp_path, "dc_index", "trade_date", "20260623", [{"ts_code": "BK001", "trade_date": "20260623"}])

    reader = MartReader(data_dir=tmp_path)
    check = reader.check_dataset("dc_index", as_of="20260623")
    payload = reader.check(["dc_index"], as_of="20260623")

    assert check.status == "degraded"
    assert "pct_change" in check.missing_analysis_columns
    assert check.message == "missing analysis columns"
    assert payload["status"] == "degraded"


def test_reader_reads_partition_with_limit(tmp_path):
    _write_partition(
        tmp_path,
        "stock_basic",
        "snapshot_date",
        "20260623",
        [
            {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "market": "主板", "list_status": "L"},
            {"ts_code": "000002.SZ", "symbol": "000002", "name": "万科A", "market": "主板", "list_status": "L"},
        ],
    )

    reader = MartReader(data_dir=tmp_path)
    frame = reader.read_partition("stock_basic", {"snapshot_date": "20260623"}, limit=1)

    assert list(frame["ts_code"]) == ["000001.SZ"]


def test_reader_dumps_meta_json(tmp_path):
    _write_partition(
        tmp_path,
        "stock_basic",
        "snapshot_date",
        "20260623",
        [{"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "market": "主板", "list_status": "L"}],
    )

    payload = json.loads(MartReader(data_dir=tmp_path).dump_meta_json("stock_basic", {"snapshot_date": "20260623"}))

    assert payload["dataset"] == "stock_basic"
    assert payload["partition"] == {"snapshot_date": "20260623"}
