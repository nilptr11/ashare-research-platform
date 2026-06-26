from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..core.paths import default_data_dir
from .schemas import FeatureBuildResult, FeatureError, FeaturePartitionMeta, FeatureSpec


class FeatureStore:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.root = self.data_dir / "features"

    def partition_path(self, spec_or_feature: FeatureSpec | str, *, domain: str | None = None, as_of: str, window: int) -> Path:
        if isinstance(spec_or_feature, FeatureSpec):
            feature_id = spec_or_feature.id
            feature_domain = spec_or_feature.domain
        else:
            feature_id = spec_or_feature
            feature_domain = domain or "_unknown"
        return self.root / feature_domain / feature_id / f"as_of={as_of}" / f"window={window}"

    def write_partition(
        self,
        spec: FeatureSpec,
        frame: pd.DataFrame,
        *,
        as_of: str,
        window: int,
        inputs: list[dict[str, Any]],
        refresh: bool = False,
    ) -> FeatureBuildResult:
        path = self.partition_path(spec, as_of=as_of, window=window)
        if path.exists() and not refresh:
            raise FeatureError(f"feature partition already exists: {path}; pass refresh=True to overwrite")
        path.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path / "part.parquet", index=False)
        quality = quality_payload(spec, frame, inputs=inputs)
        meta = FeaturePartitionMeta(
            feature_id=spec.id,
            version=spec.version,
            domain=spec.domain,
            partition={"as_of": as_of, "window": str(window)},
            rows=len(frame),
            columns=tuple(str(column) for column in frame.columns),
            inputs=tuple(inputs),
            quality=quality,
            generated_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        )
        (path / "_meta.json").write_text(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return FeatureBuildResult(
            feature_id=spec.id,
            version=spec.version,
            domain=spec.domain,
            as_of=as_of,
            window=window,
            rows=len(frame),
            path=str(path),
            inputs=tuple(inputs),
            quality=quality,
        )

    def read_partition(
        self,
        feature_id: str,
        *,
        domain: str,
        as_of: str,
        window: int,
        limit: int | None = None,
    ) -> pd.DataFrame:
        path = self.partition_path(feature_id, domain=domain, as_of=as_of, window=window) / "part.parquet"
        if not path.exists():
            raise FeatureError(f"missing feature partition: {path}")
        frame = pd.read_parquet(path)
        return frame.head(limit) if limit and limit > 0 else frame

    def load_meta(self, feature_id: str, *, domain: str, as_of: str, window: int) -> FeaturePartitionMeta:
        path = self.partition_path(feature_id, domain=domain, as_of=as_of, window=window) / "_meta.json"
        if not path.exists():
            raise FeatureError(f"missing feature metadata: {path}")
        return FeaturePartitionMeta.from_file(path)

    def discover(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for domain_dir in sorted(path for path in self.root.iterdir() if path.is_dir()):
            for feature_dir in sorted(path for path in domain_dir.iterdir() if path.is_dir()):
                for as_of_dir in sorted(path for path in feature_dir.iterdir() if path.is_dir() and path.name.startswith("as_of=")):
                    as_of = as_of_dir.name.split("=", 1)[1]
                    for window_dir in sorted(path for path in as_of_dir.iterdir() if path.is_dir() and path.name.startswith("window=")):
                        window = window_dir.name.split("=", 1)[1]
                        rows.append(
                            {
                                "domain": domain_dir.name,
                                "feature_id": feature_dir.name,
                                "as_of": as_of,
                                "window": int(window),
                                "has_meta": (window_dir / "_meta.json").exists(),
                                "path": str(window_dir),
                            }
                        )
        return rows


def quality_payload(spec: FeatureSpec, frame: pd.DataFrame, *, inputs: list[dict[str, Any]]) -> dict[str, Any]:
    missing_columns = [column for column in spec.analysis_columns if column not in frame.columns]
    ratios: dict[str, float] = {}
    status = "ok"
    reason = ""
    if frame.empty and spec.analysis_columns:
        status = "degraded"
        reason = "empty feature partition"
    elif missing_columns:
        status = "degraded"
        reason = "missing analysis columns"
    elif spec.analysis_columns:
        ratios = {column: float(frame[column].notna().sum() / len(frame)) for column in spec.analysis_columns}
        low_columns = [column for column, ratio in ratios.items() if ratio < spec.analysis_min_non_null]
        if low_columns:
            status = "degraded"
            reason = "analysis columns below non-null threshold"
    component_quality = component_quality_payload(spec, inputs)
    if status == "ok" and component_quality["status"] != "ok":
        status = component_quality["status"]
        reason = component_quality["reason"]
    return {
        "status": status,
        "reason": reason,
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "analysis_columns": list(spec.analysis_columns),
        "missing_analysis_columns": missing_columns,
        "non_null_ratios": ratios,
        "component_quality": component_quality["components"],
        "usage": spec.usage.to_dict(),
    }


def component_quality_payload(spec: FeatureSpec, inputs: list[dict[str, Any]]) -> dict[str, Any]:
    by_dataset = {str(item.get("dataset_id")): item for item in inputs if item.get("dataset_id")}
    components: dict[str, dict[str, Any]] = {}
    degraded = False
    missing_required = False
    for input_spec in spec.inputs:
        raw = by_dataset.get(input_spec.dataset_id)
        status = str(raw.get("status", "missing")) if raw else "missing"
        rows = int(raw.get("rows", 0)) if raw else 0
        ok = status == "ok"
        if input_spec.role == "required" and not ok:
            missing_required = True
        if input_spec.role in {"required", "degrade_if_missing"} and not ok:
            degraded = True
        components[input_spec.dataset_id] = {
            "role": input_spec.role,
            "status": "ok" if ok else status,
            "rows": rows,
            "columns": list(raw.get("columns", [])) if raw else [],
            "supports": list(input_spec.supports),
            "message": str(raw.get("message", "")) if raw else "",
        }
    reason = "required feature inputs are not usable" if missing_required else "degraded feature inputs" if degraded else ""
    return {"status": "degraded" if degraded else "ok", "reason": reason, "components": components}
