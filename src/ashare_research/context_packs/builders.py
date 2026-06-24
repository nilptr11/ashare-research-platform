from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..datasets.catalog import DatasetCatalog
from ..evidence import EvidenceStore
from ..features import FeatureStore
from ..knowledge import KnowledgeStore
from ..marts.reader import MartReader
from ..paths import default_data_dir
from ..schemas import AShareResearchError
from ..source_policy import source_policy_summary
from .schemas import ContextInput, ContextPack


MARKET_DATASETS = ("trade_cal", "stock_basic", "daily", "daily_basic", "index_daily", "index_dailybasic")
MARKET_FEATURES = (
    "market_strength",
    "industry_strength",
    "concept_strength",
    "limit_sentiment",
    "leader_validation",
    "elasticity_candidates",
)


class ContextPackBuilder:
    version = "v1"

    def __init__(
        self,
        data_dir: Path | str | None = None,
        *,
        reader: MartReader | None = None,
        feature_store: FeatureStore | None = None,
        evidence_store: EvidenceStore | None = None,
        knowledge_store: KnowledgeStore | None = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.reader = reader or MartReader(self.data_dir, catalog=DatasetCatalog.builtin())
        self.feature_store = feature_store or FeatureStore(self.data_dir)
        self.evidence_store = evidence_store or EvidenceStore(self.data_dir)
        self.knowledge_store = knowledge_store or KnowledgeStore(self.data_dir)
        self.context_root = self.data_dir / "context_packs"

    def build_market_structure(
        self,
        *,
        as_of: str,
        trade_days: int = 120,
        windows: list[int] | None = None,
        output_path: Path | str | None = None,
    ) -> dict[str, Any]:
        windows = windows or [5, 20, 60]
        pack_id = f"market_structure:{as_of}:{trade_days}d:{self.version}"
        inputs: list[ContextInput] = []
        data_gaps: list[dict[str, Any]] = []
        quality_flags: list[str] = []

        dataset_checks = self._dataset_checks(MARKET_DATASETS, as_of=as_of, inputs=inputs, data_gaps=data_gaps, quality_flags=quality_flags)
        feature_rows = self._feature_summaries(
            MARKET_FEATURES,
            as_of=as_of,
            windows=windows,
            inputs=inputs,
            data_gaps=data_gaps,
            quality_flags=quality_flags,
        )
        evidence_records = self._evidence_records(limit=30, inputs=inputs, data_gaps=data_gaps)
        knowledge_records = self._knowledge_records(limit=50, inputs=inputs, data_gaps=data_gaps)

        coverage = {
            "datasets_ready": sum(1 for item in dataset_checks if item["status"] == "ready"),
            "datasets_total": len(dataset_checks),
            "features_ready": sum(1 for item in feature_rows if item["status"] == "ready"),
            "features_total": len(feature_rows),
            "evidence_records": len(evidence_records),
            "knowledge_records": len(knowledge_records),
        }
        pack = ContextPack(
            schema="ashare.context_pack.market_structure.v1",
            pack_id=pack_id,
            pack_type="market_structure",
            generated_at=_now_iso(),
            as_of=as_of,
            window={"trade_days": trade_days, "end_trade_date": as_of},
            inputs=tuple(inputs),
            sections={
                "market": {"dataset_checks": dataset_checks},
                "features": feature_rows,
                "evidence": evidence_records,
                "knowledge": knowledge_records,
                "data_gaps": data_gaps,
            },
            coverage=coverage,
            data_gaps=tuple(data_gaps),
            quality_flags=tuple(quality_flags),
            constraints={"latest_complete_trade_date": as_of, "intraday_available": False},
            source_policy_summary=source_policy_summary(),
            provenance=self._provenance(),
        )
        return self._write_pack(pack, output_path or self._default_path("market_structure", as_of=as_of))

    def build_industry(
        self,
        *,
        industry: str,
        as_of: str,
        windows: list[int] | None = None,
        output_path: Path | str | None = None,
    ) -> dict[str, Any]:
        windows = windows or [5, 20, 60]
        pack_id = f"industry:{_slug(industry)}:{as_of}:{self.version}"
        inputs: list[ContextInput] = []
        data_gaps: list[dict[str, Any]] = []
        quality_flags: list[str] = []
        feature_rows = self._feature_summaries(
            ("industry_strength",),
            as_of=as_of,
            windows=windows,
            inputs=inputs,
            data_gaps=data_gaps,
            quality_flags=quality_flags,
        )
        evidence_records = self._evidence_records(industry=industry, limit=50, inputs=inputs, data_gaps=data_gaps)
        knowledge_records = self._knowledge_records(entity=industry, limit=80, inputs=inputs, data_gaps=data_gaps)
        coverage = {
            "features_ready": sum(1 for item in feature_rows if item["status"] == "ready"),
            "features_total": len(feature_rows),
            "evidence_records": len(evidence_records),
            "knowledge_records": len(knowledge_records),
        }
        pack = ContextPack(
            schema="ashare.context_pack.industry.v1",
            pack_id=pack_id,
            pack_type="industry",
            generated_at=_now_iso(),
            as_of=as_of,
            window={"end_trade_date": as_of},
            inputs=tuple(inputs),
            sections={
                "industry": {"name": industry},
                "features": feature_rows,
                "evidence": evidence_records,
                "knowledge": knowledge_records,
                "data_gaps": data_gaps,
            },
            coverage=coverage,
            data_gaps=tuple(data_gaps),
            quality_flags=tuple(quality_flags),
            constraints={"latest_complete_trade_date": as_of, "intraday_available": False},
            source_policy_summary=source_policy_summary(),
            provenance=self._provenance(),
        )
        return self._write_pack(pack, output_path or self._default_path("industry", as_of=as_of, key=industry))

    def build_stock(
        self,
        *,
        ts_code: str,
        as_of: str,
        output_path: Path | str | None = None,
    ) -> dict[str, Any]:
        pack_id = f"stock:{ts_code}:{as_of}:{self.version}"
        inputs: list[ContextInput] = []
        data_gaps: list[dict[str, Any]] = []
        quality_flags: list[str] = []
        mart_rows = self._stock_mart_rows(ts_code, as_of=as_of, inputs=inputs, data_gaps=data_gaps, quality_flags=quality_flags)
        evidence_records = self._evidence_records(company=ts_code, limit=50, inputs=inputs, data_gaps=data_gaps)
        knowledge_records = self._knowledge_records(entity=ts_code, limit=80, inputs=inputs, data_gaps=data_gaps)
        coverage = {
            "mart_rows": sum(len(rows) for rows in mart_rows.values()),
            "mart_datasets": len(mart_rows),
            "evidence_records": len(evidence_records),
            "knowledge_records": len(knowledge_records),
        }
        pack = ContextPack(
            schema="ashare.context_pack.stock.v1",
            pack_id=pack_id,
            pack_type="stock",
            generated_at=_now_iso(),
            as_of=as_of,
            window={"end_trade_date": as_of},
            inputs=tuple(inputs),
            sections={
                "stock": {"ts_code": ts_code, "mart_rows": mart_rows},
                "evidence": evidence_records,
                "knowledge": knowledge_records,
                "data_gaps": data_gaps,
            },
            coverage=coverage,
            data_gaps=tuple(data_gaps),
            quality_flags=tuple(quality_flags),
            constraints={"latest_complete_trade_date": as_of, "intraday_available": False},
            source_policy_summary=source_policy_summary(),
            provenance=self._provenance(),
        )
        return self._write_pack(pack, output_path or self._default_path("stock", as_of=as_of, key=ts_code))

    def _dataset_checks(
        self,
        datasets: tuple[str, ...],
        *,
        as_of: str,
        inputs: list[ContextInput],
        data_gaps: list[dict[str, Any]],
        quality_flags: list[str],
    ) -> list[dict[str, Any]]:
        checks = self.reader.check(list(datasets), as_of=as_of)["datasets"]
        for check in checks:
            path = Path(str(check["path"])) if check.get("path") else None
            meta_path = path / "_meta.json" if path else None
            content_hash = _file_sha256(meta_path) if meta_path and meta_path.exists() else None
            inputs.append(
                ContextInput(
                    kind="mart",
                    name=str(check["dataset"]),
                    status=str(check["status"]),
                    content_hash=content_hash,
                    path=str(path) if path else None,
                    details={"partition": check.get("partition", {}), "rows": check.get("rows")},
                )
            )
            if check["status"] != "ready":
                gap = {"kind": "mart", "name": check["dataset"], "status": check["status"], "message": check.get("message", "")}
                data_gaps.append(gap)
                quality_flags.append(f"missing_or_unready_mart:{check['dataset']}")
        return checks

    def _feature_summaries(
        self,
        features: tuple[str, ...],
        *,
        as_of: str,
        windows: list[int],
        inputs: list[ContextInput],
        data_gaps: list[dict[str, Any]],
        quality_flags: list[str],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for feature in features:
            for window in windows:
                name = f"{feature}:{window}"
                try:
                    meta = self.feature_store.load_meta(feature, as_of=as_of, window=window)
                    path = self.feature_store.partition_path(feature, as_of=as_of, window=window)
                    row = meta.to_dict() | {"status": "ready", "path": str(path)}
                    rows.append(row)
                    inputs.append(
                        ContextInput(
                            kind="feature",
                            name=name,
                            status="ready",
                            content_hash=_file_sha256(path / "_meta.json"),
                            path=str(path),
                            details={"rows": meta.rows, "version": meta.version},
                        )
                    )
                except AShareResearchError as error:
                    rows.append({"feature": feature, "window": window, "status": "missing", "message": str(error)})
                    data_gaps.append({"kind": "feature", "name": name, "status": "missing", "message": str(error)})
                    quality_flags.append(f"missing_feature:{name}")
                    inputs.append(ContextInput(kind="feature", name=name, status="missing"))
        return rows

    def _evidence_records(
        self,
        *,
        topic: str | None = None,
        industry: str | None = None,
        company: str | None = None,
        limit: int,
        inputs: list[ContextInput],
        data_gaps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        records = self.evidence_store.find_evidence(topic=topic, industry=industry, company=company, limit=limit)
        inputs.append(
            ContextInput(
                kind="evidence",
                name="records",
                status="ready" if self.evidence_store.records_path.exists() else "missing",
                content_hash=_file_sha256(self.evidence_store.records_path),
                path=str(self.evidence_store.records_path),
                details={"records": len(records), "topic": topic, "industry": industry, "company": company},
            )
        )
        if not records:
            data_gaps.append({"kind": "evidence", "name": "records", "status": "empty", "message": "no matching evidence records"})
        return [record.to_dict() for record in records]

    def _knowledge_records(
        self,
        *,
        entity: str | None = None,
        limit: int,
        inputs: list[ContextInput],
        data_gaps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        records = self.knowledge_store.search(entity=entity, limit=limit) if entity else self.knowledge_store.read_current_records()
        if limit and limit > 0:
            records = records[:limit]
        inputs.append(
            ContextInput(
                kind="knowledge",
                name="current",
                status="ready" if self.knowledge_store.current_path.exists() else "missing",
                content_hash=_file_sha256(self.knowledge_store.current_path),
                path=str(self.knowledge_store.current_path),
                details={"records": len(records), "entity": entity},
            )
        )
        if not records:
            data_gaps.append({"kind": "knowledge", "name": "current", "status": "empty", "message": "no matching current knowledge"})
        return [record.to_dict() for record in records]

    def _stock_mart_rows(
        self,
        ts_code: str,
        *,
        as_of: str,
        inputs: list[ContextInput],
        data_gaps: list[dict[str, Any]],
        quality_flags: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        rows: dict[str, list[dict[str, Any]]] = {}
        for dataset, partition in {
            "daily": {"trade_date": as_of},
            "daily_basic": {"trade_date": as_of},
            "stock_basic": {"snapshot_date": as_of},
        }.items():
            try:
                frame = self.reader.read_partition(dataset, partition)
                filtered = _filter_ts_code(frame, ts_code)
                path = self.reader.partition_path(dataset, partition)
                rows[dataset] = filtered.to_dict(orient="records")
                inputs.append(
                    ContextInput(
                        kind="mart",
                        name=dataset,
                        status="ready",
                        content_hash=_file_sha256(path / "_meta.json"),
                        path=str(path),
                        details={"partition": partition, "rows": len(filtered)},
                    )
                )
                if filtered.empty:
                    data_gaps.append({"kind": "mart", "name": dataset, "status": "empty", "message": f"{ts_code} not found"})
                    quality_flags.append(f"missing_stock_row:{dataset}")
            except AShareResearchError as error:
                rows[dataset] = []
                data_gaps.append({"kind": "mart", "name": dataset, "status": "missing", "message": str(error)})
                quality_flags.append(f"missing_or_unready_mart:{dataset}")
                inputs.append(ContextInput(kind="mart", name=dataset, status="missing", details={"partition": partition}))
        return rows

    def _write_pack(self, pack: ContextPack, output_path: Path | str) -> dict[str, Any]:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = pack.to_dict()
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return payload | {"path": str(output)}

    def _default_path(self, pack_type: str, *, as_of: str, key: str | None = None) -> Path:
        if key:
            return self.context_root / pack_type / f"as_of={as_of}" / f"key={_slug(key)}" / "context.json"
        return self.context_root / pack_type / f"as_of={as_of}" / "context.json"

    def _provenance(self) -> dict[str, Any]:
        return {
            "builder": "ContextPackBuilder",
            "version": self.version,
            "generated_by": "ashare_research",
        }


def _filter_ts_code(frame: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if "ts_code" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["ts_code"] == ts_code].head(5)


def _file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    return slug.strip("_") or "unknown"


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
