from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..paths import default_data_dir
from ..schemas import FeatureBuildResult, FeatureError, FeaturePartitionMeta, FeatureSpec


class FeatureStore:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.feature_root = self.data_dir / "features"

    def partition_path(self, feature: str, *, as_of: str, window: int) -> Path:
        return self.feature_root / feature / f"as_of={as_of}" / f"window={window}"

    def write_partition(
        self,
        spec: FeatureSpec,
        frame: pd.DataFrame,
        *,
        as_of: str,
        window: int,
        inputs: list[dict[str, Any]],
    ) -> FeatureBuildResult:
        path = self.partition_path(spec.name, as_of=as_of, window=window)
        path.mkdir(parents=True, exist_ok=True)
        parquet_path = path / "part.parquet"
        meta_path = path / "_meta.json"
        frame.to_parquet(parquet_path, index=False)
        meta = FeaturePartitionMeta(
            feature=spec.name,
            version=spec.version,
            partition={"as_of": as_of, "window": str(window)},
            rows=len(frame),
            columns=tuple(str(column) for column in frame.columns),
            inputs=tuple(inputs),
            generated_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        )
        meta_path.write_text(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return FeatureBuildResult(
            feature=spec.name,
            version=spec.version,
            as_of=as_of,
            window=window,
            rows=len(frame),
            path=str(path),
            inputs=tuple(inputs),
        )

    def read_partition(self, feature: str, *, as_of: str, window: int, limit: int | None = None) -> pd.DataFrame:
        path = self.partition_path(feature, as_of=as_of, window=window) / "part.parquet"
        if not path.exists():
            raise FeatureError(f"Missing feature parquet: {path}")
        frame = pd.read_parquet(path)
        if limit is not None and limit > 0:
            return frame.head(limit)
        return frame

    def load_meta(self, feature: str, *, as_of: str, window: int) -> FeaturePartitionMeta:
        path = self.partition_path(feature, as_of=as_of, window=window) / "_meta.json"
        if not path.exists():
            raise FeatureError(f"Missing feature metadata: {path}")
        return FeaturePartitionMeta.from_file(path)

    def discover(self) -> list[dict[str, Any]]:
        if not self.feature_root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for feature_dir in sorted(path for path in self.feature_root.iterdir() if path.is_dir()):
            for as_of_dir in sorted(path for path in feature_dir.iterdir() if path.is_dir() and path.name.startswith("as_of=")):
                as_of = as_of_dir.name.split("=", 1)[1]
                for window_dir in sorted(path for path in as_of_dir.iterdir() if path.is_dir() and path.name.startswith("window=")):
                    window = window_dir.name.split("=", 1)[1]
                    meta_path = window_dir / "_meta.json"
                    rows.append(
                        {
                            "feature": feature_dir.name,
                            "as_of": as_of,
                            "window": int(window),
                            "has_meta": meta_path.exists(),
                            "path": str(window_dir),
                        }
                    )
        return rows
