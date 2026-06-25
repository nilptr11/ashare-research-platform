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
        scoring: dict[str, Any] | None = None,
    ) -> FeatureBuildResult:
        path = self.partition_path(spec.name, as_of=as_of, window=window)
        path.mkdir(parents=True, exist_ok=True)
        parquet_path = path / "part.parquet"
        meta_path = path / "_meta.json"
        frame.to_parquet(parquet_path, index=False)
        scoring_payload = dict(scoring or {})
        quality = _quality_payload(spec, frame, inputs=inputs, scoring=scoring_payload)
        meta = FeaturePartitionMeta(
            feature=spec.name,
            version=spec.version,
            partition={"as_of": as_of, "window": str(window)},
            rows=len(frame),
            columns=tuple(str(column) for column in frame.columns),
            inputs=tuple(inputs),
            scoring=scoring_payload,
            generated_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            quality_status=quality["status"],
            quality=quality,
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
            scoring=scoring_payload,
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

    def quality_for_partition(self, spec: FeatureSpec, *, as_of: str, window: int) -> dict[str, Any]:
        meta = self.load_meta(spec.name, as_of=as_of, window=window)
        frame = self.read_partition(spec.name, as_of=as_of, window=window)
        return _quality_payload(spec, frame, inputs=list(meta.inputs), scoring=meta.scoring)

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


def _quality_payload(
    spec: FeatureSpec,
    frame: pd.DataFrame,
    *,
    inputs: list[dict[str, Any]] | None = None,
    scoring: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing = [column for column in spec.analysis_columns if column not in frame.columns]
    ratios: dict[str, float] = {}
    reason = ""
    status = "ok"
    if frame.empty and spec.analysis_columns:
        status = "degraded"
        reason = "empty feature partition"
    elif missing:
        status = "degraded"
        reason = "missing analysis columns"
    elif spec.analysis_columns:
        ratios = {column: float(frame[column].notna().sum() / len(frame)) for column in spec.analysis_columns}
        low_columns = [column for column, ratio in ratios.items() if ratio < spec.analysis_min_non_null]
        if low_columns:
            status = "degraded"
            reason = "analysis columns below non-null threshold"
    component_quality = _component_quality(spec, inputs or [])
    if status == "ok" and component_quality["status"] != "ok":
        status = component_quality["status"]
        reason = component_quality["reason"]
    return {
        "status": status,
        "rows": len(frame),
        "columns": len(frame.columns),
        "analysis_columns": list(spec.analysis_columns),
        "analysis_min_non_null": spec.analysis_min_non_null,
        "missing_analysis_columns": missing,
        "non_null_ratios": ratios,
        "component_quality": component_quality["components"],
        "supported_claims": component_quality["supported_claims"],
        "unsupported_claims": component_quality["unsupported_claims"],
        "scoring": dict(scoring or {}),
        "reason": reason,
    }


def _component_quality(spec: FeatureSpec, inputs: list[dict[str, Any]]) -> dict[str, Any]:
    by_dataset = {str(item.get("dataset")): item for item in inputs if item.get("dataset")}
    components: dict[str, dict[str, Any]] = {}
    supported_claims: list[str] = list(spec.supports)
    unsupported_claims: list[str] = []
    degraded = False
    missing_required = False

    for input_spec in spec.input_specs:
        raw = by_dataset.get(input_spec.dataset)
        input_status = _input_status(raw)
        ok = input_status == "ok"
        component_status = "ok" if ok else "degraded"
        if input_spec.role == "optional" and not ok:
            component_status = "missing_optional"
        if input_spec.role == "required" and not ok:
            missing_required = True
        if input_spec.role in {"required", "degrade_if_missing"} and not ok:
            degraded = True
            for claim in input_spec.supports:
                if claim not in unsupported_claims:
                    unsupported_claims.append(claim)
                if claim in supported_claims:
                    supported_claims.remove(claim)
        elif ok:
            for claim in input_spec.supports:
                if claim not in supported_claims:
                    supported_claims.append(claim)
        components[input_spec.component] = {
            "dataset": input_spec.dataset,
            "role": input_spec.role,
            "status": component_status,
            "input_status": input_status,
            "rows": int(raw.get("rows", 0)) if raw else 0,
            "supports": list(input_spec.supports),
            "message": "" if raw is None else str(raw.get("message", "")),
            "missing_columns": list(raw.get("missing_columns", [])) if raw else [],
            "partition": dict(raw.get("partition", {})) if raw else {},
            "requested_partition": dict(raw.get("requested_partition", {})) if raw else {},
            "partition_mode": str(raw.get("partition_mode", raw.get("snapshot_mode", "exact"))) if raw else "missing",
            "historical_precision": str(raw.get("historical_precision", "exact")) if raw else "missing",
        }

    if missing_required:
        reason = "required feature inputs are not usable"
    elif degraded:
        reason = "degraded feature inputs"
    else:
        reason = ""
    return {
        "status": "degraded" if degraded else "ok",
        "reason": reason,
        "components": components,
        "supported_claims": supported_claims,
        "unsupported_claims": unsupported_claims,
    }


def _input_status(raw: dict[str, Any] | None) -> str:
    if raw is None:
        return "missing"
    explicit = str(raw.get("status", "")).strip()
    if explicit in {"missing", "read_error", "partial_columns", "degraded"}:
        return explicit
    rows = int(raw.get("rows", 0) or 0)
    if rows <= 0:
        return explicit or "empty"
    if explicit in {"", "ready", "ok", "fallback_snapshot"}:
        return "ok"
    return explicit
