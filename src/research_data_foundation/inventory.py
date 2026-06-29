from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .core.paths import default_data_dir
from .core.registry import FoundationRegistry
from .core.schemas import DatasetContract, IngestionRecipe
from .domains import default_registry
from .evidence import EvidenceSourceRegistry, EvidenceStore
from .features import FeatureRegistry, FeatureStore
from .features.schemas import FeatureSpec
from .features.windowing import feature_window_coverage
from .maintenance.financials import financial_period_for_as_of
from .relations import RelationStore
from .storage import MartStore, StorageError

DEFAULT_RECOVERY_STATUSES = ("missing", "degraded")
DEFAULT_RECOVERY_COVERAGE_STATUSES = ("none", "partial")


class DataInventory:
    def __init__(
        self,
        data_dir: Path | str | None = None,
        *,
        registry: FoundationRegistry | None = None,
        feature_registry: FeatureRegistry | None = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.registry = registry or default_registry()
        self.feature_registry = feature_registry or FeatureRegistry.builtin()
        self.mart = MartStore(self.data_dir, self.registry)
        self.features = FeatureStore(self.data_dir)

    def summary(self, *, as_of: str | None = None) -> dict[str, Any]:
        datasets = self.datasets(as_of=as_of)
        features = self.feature_partitions(as_of=as_of)
        evidence = self.evidence()
        relations = self.relations()
        return {
            "schema": "rdf.data_inventory_summary.v1",
            "generated_at": _now_iso(),
            "data_dir": str(self.data_dir),
            "as_of": as_of,
            "datasets": _status_counts(datasets),
            "dataset_coverage": _coverage_counts(datasets),
            "features": _status_counts(features),
            "evidence": evidence,
            "relations": relations,
        }

    def plan(
        self,
        *,
        as_of: str | None = None,
        domain: str | None = None,
        use: str | None = None,
        statuses: tuple[str, ...] = DEFAULT_RECOVERY_STATUSES,
        coverage_statuses: tuple[str, ...] = DEFAULT_RECOVERY_COVERAGE_STATUSES,
        include_features: bool = True,
        limit: int | None = None,
    ) -> dict[str, Any]:
        datasets = [
            entry
            for entry in self.datasets(as_of=as_of, domain=domain, use=use)
            if _matches_recovery_scope(entry, statuses=statuses, coverage_statuses=coverage_statuses)
        ]
        features = [
            entry
            for entry in self.feature_partitions(as_of=as_of)
            if include_features and (not domain or entry["domain"] == domain) and (not statuses or entry["status"] in statuses)
        ]
        items = [
            self._dataset_plan_item(entry, as_of=as_of)
            for entry in datasets
        ] + [
            self._feature_plan_item(entry, as_of=as_of)
            for entry in features
        ]
        items.sort(key=lambda item: (item["priority"], item["kind"], item["id"]))
        if limit and limit > 0:
            items = items[:limit]
        return {
            "schema": "rdf.inventory_recovery_plan.v1",
            "generated_at": _now_iso(),
            "data_dir": str(self.data_dir),
            "as_of": as_of,
            "filters": {
                "domain": domain,
                "use": use,
                "statuses": list(statuses),
                "coverage_statuses": list(coverage_statuses),
                "include_features": include_features,
                "limit": limit,
            },
            "items": items,
            "items_total": len(items),
            "note": "Plan only: commands are recommendations for status gaps or target coverage gaps and do not run automatically.",
        }

    def datasets(
        self,
        *,
        as_of: str | None = None,
        domain: str | None = None,
        use: str | None = None,
    ) -> list[dict[str, Any]]:
        contracts = sorted(self.registry.datasets.values(), key=lambda item: item.id)
        rows: list[dict[str, Any]] = []
        for contract in contracts:
            if domain and contract.domain != domain:
                continue
            if use and not contract.permits(use):
                continue
            rows.append(self._dataset_entry(contract, as_of=as_of))
        return rows

    def feature_partitions(self, *, as_of: str | None = None) -> list[dict[str, Any]]:
        discovered = self.features.discover()
        rows: list[dict[str, Any]] = []
        for spec in self.feature_registry.list():
            partitions = [item for item in discovered if item["feature_id"] == spec.id and item["domain"] == spec.domain]
            if as_of:
                partitions = [item for item in partitions if str(item.get("as_of")) == as_of]
            rows.append(self._feature_entry(spec, partitions, as_of=as_of))
        return rows

    def evidence(self) -> dict[str, Any]:
        store = EvidenceStore(self.data_dir)
        records = store.read_records()
        sources = EvidenceSourceRegistry(self.data_dir).list()
        return {
            "schema": "rdf.evidence_inventory.v1",
            "records": len(records),
            "sources": len(sources),
            "records_path": str(store.records_path),
            "updated_at": _meta_value(store.meta_path, "updated_at"),
        }

    def relations(self) -> dict[str, Any]:
        store = RelationStore(self.data_dir)
        records = store.read_records()
        return {
            "schema": "rdf.relation_inventory.v1",
            "records": len(records),
            "records_path": str(store.records_path),
            "updated_at": _meta_value(store.meta_path, "updated_at"),
        }

    def _dataset_entry(self, contract: DatasetContract, *, as_of: str | None) -> dict[str, Any]:
        partitions = self.mart.list_partitions(contract.id)
        latest_partition = _latest_partition(partitions, contract.partition_keys)
        latest_meta = _read_meta(self.mart, contract.id, latest_partition) if latest_partition else None
        requested_partition = _requested_partition(contract, as_of)
        requested_partition_count = _matching_partition_count(partitions, requested_partition)
        active_partition = _active_partition(contract, partitions, requested_partition=requested_partition)
        active_meta = _read_meta(self.mart, contract.id, active_partition) if active_partition else None
        status = _table_status(active_meta, requested_partition=requested_partition, partition_count=len(partitions))
        coverage = _partition_coverage(
            contract,
            requested_partition=requested_partition,
            requested_partition_count=requested_partition_count,
            active_partition=active_partition,
            partition_count=len(partitions),
        )
        path = ""
        if active_partition:
            try:
                path = str(self.mart.partition_path(contract.id, active_partition))
            except StorageError:
                path = ""
        latest_path = ""
        if latest_partition:
            try:
                latest_path = str(self.mart.partition_path(contract.id, latest_partition))
            except StorageError:
                latest_path = ""
        recipes = self.registry.recipes_for_dataset(contract.id)
        return {
            "schema": "rdf.dataset_inventory_entry.v1",
            "dataset_id": contract.id,
            "title": contract.title,
            "domain": contract.domain,
            "market_scope": contract.market_scope,
            "role": contract.role,
            "partition_keys": list(contract.partition_keys),
            "primary_key": list(contract.primary_key),
            "temporal": {
                "temporal_mode": contract.temporal.temporal_mode,
                "finality": contract.temporal.finality,
                "available_after": contract.temporal.available_after,
                "as_of_policy": contract.temporal.as_of_policy,
            },
            "usage": contract.usage.to_dict(),
            "status": status,
            "coverage": coverage,
            "requested_partition": requested_partition,
            "active_partition": active_partition,
            "active_rows": int(active_meta.get("rows", 0)) if active_meta else 0,
            "active_quality": dict(active_meta.get("quality", {})) if active_meta else {},
            "active_published_at": str(active_meta.get("published_at", "")) if active_meta else "",
            "active_path": path,
            "partition_count": len(partitions),
            "requested_partition_count": requested_partition_count,
            "latest_partition": latest_partition,
            "latest_rows": int(latest_meta.get("rows", 0)) if latest_meta else 0,
            "latest_quality_status": _quality_status(latest_meta),
            "latest_published_at": str(latest_meta.get("published_at", "")) if latest_meta else "",
            "latest_path": latest_path,
            "recipes": [recipe.id for recipe in recipes],
            "source_ids": sorted({recipe.source_id for recipe in recipes}),
        }

    def _feature_entry(self, spec: FeatureSpec, partitions: list[dict[str, Any]], *, as_of: str | None) -> dict[str, Any]:
        latest = sorted(partitions, key=lambda item: (str(item.get("as_of")), int(item.get("window", 0))))[-1] if partitions else None
        meta = None
        if latest:
            try:
                meta = self.features.load_meta(spec.id, domain=spec.domain, as_of=str(latest["as_of"]), window=int(latest["window"])).to_dict()
            except Exception:
                meta = None
        quality = dict(meta.get("quality", {})) if meta else {}
        quality_status = str(quality.get("status", "")) if quality else ""
        window_status = self._feature_window_status(spec, as_of=as_of)
        status = "missing" if latest is None else "ready" if quality_status == "ok" else "degraded"
        if status == "ready" and any(item.get("input_status") in {"missing", "degraded"} for item in window_status):
            status = "degraded"
        return {
            "schema": "rdf.feature_inventory_entry.v1",
            "feature_id": spec.id,
            "title": spec.title,
            "domain": spec.domain,
            "version": spec.version,
            "role": spec.role,
            "status": status,
            "partition_count": len(partitions),
            "latest_partition": {"as_of": latest["as_of"], "window": str(latest["window"])} if latest else None,
            "latest_rows": int(meta.get("rows", 0)) if meta else 0,
            "latest_quality": quality,
            "latest_generated_at": str(meta.get("generated_at", "")) if meta else "",
            "latest_path": str(latest.get("path", "")) if latest else "",
            "inputs": [item.to_dict() for item in spec.inputs],
            "recommended_windows": list(spec.recommended_windows),
            "window_status": window_status,
            "usage": spec.usage.to_dict(),
        }

    def _dataset_plan_item(self, entry: dict[str, Any], *, as_of: str | None) -> dict[str, Any]:
        contract = self.registry.require_dataset(entry["dataset_id"])
        recipes = self.registry.recipes_for_dataset(contract.id)
        recipe = recipes[0] if recipes else None
        action = _dataset_recovery_action(contract, entry, recipe, as_of=as_of)
        return {
            "kind": "dataset",
            "id": contract.id,
            "title": contract.title,
            "status": entry["status"],
            "priority": _dataset_priority(contract, entry),
            "reason": _plan_reason(entry),
            "domain": contract.domain,
            "role": contract.role,
            "temporal": entry["temporal"],
            "usage": entry["usage"],
            "partition_keys": list(contract.partition_keys),
            "requested_partition": entry.get("requested_partition"),
            "coverage": entry.get("coverage"),
            "latest_partition": entry.get("latest_partition"),
            "recipes": entry.get("recipes", []),
            "source_ids": entry.get("source_ids", []),
            "action": action,
            "boundary": _dataset_boundary(contract),
        }

    def _feature_plan_item(self, entry: dict[str, Any], *, as_of: str | None) -> dict[str, Any]:
        spec = self.feature_registry.require(entry["feature_id"])
        action = _feature_recovery_action(spec, entry=entry, as_of=as_of)
        return {
            "kind": "feature",
            "id": spec.id,
            "title": spec.title,
            "status": entry["status"],
            "priority": _feature_priority(spec),
            "reason": _plan_reason(entry),
            "domain": spec.domain,
            "role": spec.role,
            "usage": entry["usage"],
            "latest_partition": entry.get("latest_partition"),
            "inputs": entry.get("inputs", []),
            "recommended_windows": entry.get("recommended_windows", []),
            "window_status": entry.get("window_status", []),
            "action": action,
            "boundary": "Feature is a reproducible signal. It can rank or triage research, but cannot prove company business exposure.",
        }

    def _feature_window_status(self, spec: FeatureSpec, *, as_of: str | None) -> list[dict[str, Any]]:
        if not as_of:
            return []
        output = []
        for window in spec.recommended_windows:
            feature_partition = {"as_of": as_of, "window": str(window)}
            feature_meta = None
            feature_path = ""
            try:
                feature_meta = self.features.load_meta(spec.id, domain=spec.domain, as_of=as_of, window=window).to_dict()
                feature_path = str(self.features.partition_path(spec, as_of=as_of, window=window))
            except Exception:
                feature_meta = None
            feature_quality = dict(feature_meta.get("quality", {})) if feature_meta else {}
            feature_quality_status = str(feature_quality.get("status", "")) if feature_quality else ""
            if feature_meta is None:
                feature_status = "missing"
            elif feature_quality_status == "ok":
                feature_status = "ready"
            else:
                feature_status = "degraded"
            input_checks = [self._feature_input_status(input_spec, as_of=as_of, window=window) for input_spec in spec.inputs]
            input_status = _aggregate_input_status(input_checks)
            output.append(
                {
                    "window": window,
                    "partition": feature_partition,
                    "feature_status": feature_status,
                    "feature_rows": int(feature_meta.get("rows", 0)) if feature_meta else 0,
                    "feature_quality_status": feature_quality_status,
                    "feature_path": feature_path,
                    "input_status": input_status,
                    "inputs": input_checks,
                    "buildable": input_status == "ready",
                    "build_command": _command_payload(
                        ["uv", "run", "rdf", "features", "build", spec.id, "--as-of", as_of, "--window", str(window), "--refresh"]
                    ),
                }
            )
        return output

    def _feature_input_status(self, input_spec: Any, *, as_of: str, window: int) -> dict[str, Any]:
        dataset_id = str(input_spec.dataset_id)
        coverage = feature_window_coverage(
            mart_store=self.mart,
            registry=self.registry,
            dataset_id=dataset_id,
            as_of=as_of,
            window=window,
        )
        selected = [dict(item) for item in coverage.pop("_read_partitions", [])]
        rows_total = 0
        for partition in selected:
            meta = _read_meta(self.mart, dataset_id, partition)
            rows_total += int(meta.get("rows", 0)) if meta else 0
        coverage_status = str(coverage.get("coverage_status", "missing"))
        if coverage_status == "ok":
            status = "ready"
        elif coverage_status == "missing":
            status = "missing"
        else:
            status = "degraded"
        return {
            "dataset_id": dataset_id,
            "role": input_spec.role,
            "status": status,
            "reason": str(coverage.get("reason", "")),
            "partition_key": coverage.get("partition_key"),
            "required_window": int(coverage.get("required_window", window)),
            "available_partitions": int(coverage.get("available_partitions", 0)),
            "rows_total": rows_total,
            "selected_range": coverage.get("selected_range", {"start": None, "end": None}),
            "expected_partitions": list(coverage.get("expected_partitions", [])),
            "missing_partitions": list(coverage.get("missing_partitions", [])),
            "calendar_status": coverage.get("calendar_status", "not_applicable"),
            "columns": list(input_spec.columns),
            "supports": list(input_spec.supports),
        }


def _requested_partition(contract: DatasetContract, as_of: str | None) -> dict[str, str] | None:
    if not as_of:
        return None
    if contract.temporal.temporal_mode == "filing" and "period" in contract.partition_keys:
        return {"period": financial_period_for_as_of(as_of)}
    date_keys = ("trade_date", "snapshot_date", "publish_date", "query_date", "ann_date", "end_date")
    for key in contract.partition_keys:
        if key in date_keys:
            return {key: as_of}
    return None


def _matches_recovery_scope(
    entry: dict[str, Any],
    *,
    statuses: tuple[str, ...],
    coverage_statuses: tuple[str, ...],
) -> bool:
    status_matches = bool(statuses) and str(entry.get("status")) in statuses
    coverage_status = str((entry.get("coverage") or {}).get("status") or "")
    coverage_matches = bool(coverage_statuses) and coverage_status in coverage_statuses
    if not statuses and not coverage_statuses:
        return True
    return status_matches or coverage_matches


def _latest_partition(partitions: list[dict[str, str]], partition_keys: tuple[str, ...]) -> dict[str, str] | None:
    if not partitions:
        return None
    return sorted(partitions, key=lambda partition: tuple(str(partition.get(key, "")) for key in partition_keys))[-1]


def _active_partition(
    contract: DatasetContract,
    partitions: list[dict[str, str]],
    *,
    requested_partition: dict[str, str] | None,
) -> dict[str, str] | None:
    if not requested_partition:
        return _latest_partition(partitions, contract.partition_keys)
    partial_matches = _matching_partitions(partitions, requested_partition)
    if partial_matches:
        return _latest_partition(partial_matches, contract.partition_keys)
    if set(requested_partition) != set(contract.partition_keys):
        return None
    if requested_partition in partitions:
        return requested_partition
    if contract.temporal.as_of_policy != "latest_before" or len(requested_partition) != 1:
        return None
    key, value = next(iter(requested_partition.items()))
    candidates = [partition for partition in partitions if key in partition and str(partition[key]) <= str(value)]
    return _latest_partition(candidates, contract.partition_keys)


def _matching_partitions(partitions: list[dict[str, str]], requested_partition: dict[str, str] | None) -> list[dict[str, str]]:
    if not requested_partition:
        return partitions
    return [
        partition
        for partition in partitions
        if all(str(partition.get(key, "")) == str(value) for key, value in requested_partition.items())
    ]


def _matching_partition_count(partitions: list[dict[str, str]], requested_partition: dict[str, str] | None) -> int:
    return len(_matching_partitions(partitions, requested_partition)) if requested_partition else 0


def _partition_coverage(
    contract: DatasetContract,
    *,
    requested_partition: dict[str, str] | None,
    requested_partition_count: int,
    active_partition: dict[str, str] | None,
    partition_count: int,
) -> dict[str, Any]:
    partition_keys = list(contract.partition_keys)
    if requested_partition:
        missing_keys = [key for key in partition_keys if key not in requested_partition]
        if requested_partition_count > 0 and missing_keys:
            status = "partial"
            reason = (
                "Requested partition filter omits one or more partition keys; local data covers only the matched "
                "subpartitions and must not be treated as full-universe coverage."
            )
        elif requested_partition_count > 0:
            status = "full"
            reason = "Requested partition fully matches the dataset partition keys."
        elif active_partition:
            status = "latest_before"
            reason = (
                "No exact requested partition exists locally; active_partition is selected by the dataset "
                "latest_before as-of policy."
            )
        else:
            status = "none"
            reason = "No local partition matches the requested as-of partition filter."
        return {
            "schema": "rdf.partition_coverage.v1",
            "status": status,
            "reason": reason,
            "partition_filter": requested_partition,
            "matched_partitions": requested_partition_count,
            "available_partitions": partition_count,
            "missing_partition_keys": missing_keys,
            "target_complete": status == "full",
        }

    if active_partition:
        return {
            "schema": "rdf.partition_coverage.v1",
            "status": "latest",
            "reason": "No as-of partition filter was requested; active_partition is the latest local partition.",
            "partition_filter": None,
            "matched_partitions": partition_count,
            "available_partitions": partition_count,
            "missing_partition_keys": [],
            "target_complete": False,
        }
    return {
        "schema": "rdf.partition_coverage.v1",
        "status": "none",
        "reason": "No local partitions are available.",
        "partition_filter": None,
        "matched_partitions": 0,
        "available_partitions": partition_count,
        "missing_partition_keys": [],
        "target_complete": False,
    }


def _read_meta(mart: MartStore, dataset_id: str, partition: dict[str, str] | None) -> dict[str, Any] | None:
    if not partition:
        return None
    try:
        return mart.read_meta(dataset_id, partition)
    except StorageError:
        return None


def _table_status(meta: dict[str, Any] | None, *, requested_partition: dict[str, str] | None, partition_count: int) -> str:
    if meta is None:
        return "missing"
    quality_status = _quality_status(meta)
    if quality_status == "ok":
        return "ready"
    if quality_status:
        return "degraded"
    return "ready" if partition_count > 0 and not requested_partition else "missing"


def _quality_status(meta: dict[str, Any] | None) -> str:
    if not meta:
        return ""
    quality = meta.get("quality")
    return str(quality.get("status", "")) if isinstance(quality, dict) else ""


def _status_counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for entry in entries:
        status = str(entry.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return {"total": len(entries), **counts}


def _coverage_counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for entry in entries:
        status = str((entry.get("coverage") or {}).get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {"total": len(entries), **counts}


def _meta_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    value = payload.get(key, "")
    return str(value) if value is not None else ""


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _dataset_recovery_action(
    contract: DatasetContract,
    entry: dict[str, Any],
    recipe: IngestionRecipe | None,
    *,
    as_of: str | None,
) -> dict[str, Any]:
    if contract.id == "ashare.index_weights":
        snapshot_date = str((entry.get("requested_partition") or {}).get("snapshot_date") or as_of or "YYYYMMDD")
        command = ["uv", "run", "rdf", "maintain", "ashare-index-weights", "--snapshot-date", snapshot_date]
        return _action(
            "maintain",
            dry_run_command=None,
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN"],
            message="Refresh core index constituent weights as latest-before snapshot facts; weights do not prove company business exposure.",
        )
    if recipe is None:
        return {
            "action_type": "manual",
            "message": "No ingestion recipe is registered for this dataset.",
            "dry_run_command": None,
            "execute_command": None,
            "requires": [],
        }
    partition = _action_partition(contract, entry, as_of=as_of)
    params = _placeholder_params(recipe)
    if recipe.schedule == "ashare_core_eod_daily":
        execute = ["uv", "run", "rdf", "maintain", "ashare-core", "--as-of", partition.get("trade_date") or as_of or "YYYYMMDD", "--lookback-trading-days", "60", "--refresh"]
        dry_run = _recipe_command(recipe.id, partition=partition, params=params, dry_run=True)
        return _action(
            "maintain",
            dry_run_command=dry_run,
            execute_command=execute,
            requires=["TUSHARE_TOKEN", "Run after market close; Tushare EOD does not provide realtime daily bars."],
            message="Use the coordinated A-share EOD maintainer for canonical post-close data.",
        )
    if recipe.schedule == "ashare_market_attention_daily":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_market_attention_daily", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Run after market close; hot ranks are vendor attention signals."],
            message="Refresh hot-rank market attention facts; do not treat rank text, popularity, or topic labels as company evidence.",
        )
    if recipe.schedule == "ashare_short_term_sentiment_daily":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_short_term_sentiment_daily", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Run after market close; KPL and limit-up topic descriptions are vendor market context."],
            message="Refresh short-term limit-up sentiment facts; do not treat board status, theme labels, or vendor descriptions as company evidence.",
        )
    if recipe.schedule == "ashare_chips_on_demand":
        command_partition = partition | _missing_partition_values(contract, partition)
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_chips_on_demand", *_partition_args(command_partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Run after market close; pass one concrete security_id to avoid full-market fanout."],
            message="Fetch per-security chip distribution facts on demand; use as market-structure context, not company evidence.",
        )
    if recipe.schedule == "ashare_ownership_periodic":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_ownership_periodic", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Use a reporting period such as 20260331."],
            message="Refresh periodic shareholder count and holder-list facts; use as ownership-structure context, not company business exposure evidence.",
        )
    if recipe.schedule == "ashare_share_pledge_weekly":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_share_pledge_weekly", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Use an available pledge statistic end_date; inventory latest-before will select the newest local partition for research as-of dates."],
            message="Refresh share pledge statistics as periodic ownership-risk context; not company business exposure evidence.",
        )
    if recipe.schedule == "ashare_corporate_action_events_daily":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_corporate_action_events_daily", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Run after market close; verify official announcements for high-confidence claims."],
            message="Refresh structured corporate action events; use as evidence triage, not company business exposure proof.",
        )
    if recipe.schedule == "ashare_financial_event_daily":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_financial_event_daily", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Run after market close; verify official announcements for high-confidence financial claims."],
            message="Refresh structured earnings forecast announcement events; use as financial event triage, not company business exposure proof.",
        )
    if recipe.schedule == "ashare_block_trades_daily":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_block_trades_daily", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Run after market close."],
            message="Refresh block trade market-structure facts; do not treat buyer/seller seats as company business evidence.",
        )
    if recipe.schedule == "ashare_moneyflow_daily":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_moneyflow_daily", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN", "Run after market close; moneyflow is vendor market context."],
            message="Refresh multi-source moneyflow facts; do not treat capital flow as company business exposure evidence.",
        )
    if recipe.schedule == "ashare_membership_weekly":
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_membership_weekly", *_partition_args(partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN"],
            message="Refresh industry membership as a mart classification fact; do not bulk-ingest it into curated relations.",
        )
    if recipe.schedule == "ashare_identity_weekly":
        command_partition = partition | _missing_partition_values(contract, partition)
        command = ["uv", "run", "rdf", "ingest", "pipeline", "ashare_identity_weekly", *_partition_args(command_partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["TUSHARE_TOKEN"],
            message="Refresh company profile and identity alias seeds; profile text and aliases do not prove business exposure.",
        )
    if recipe.schedule == "ashare_concept_members_weekly":
        command_partition = partition | _missing_partition_values(contract, partition)
        dry_run = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=True)
        execute = [
            "uv",
            "run",
            "rdf",
            "maintain",
            "ashare-concept-members",
            "--snapshot-date",
            command_partition["snapshot_date"],
        ]
        if command_partition["concept_id"] != _placeholder_value("concept_id"):
            execute.extend(["--concept-id", command_partition["concept_id"]])
        execute.append("--refresh")
        return _action(
            "maintain",
            dry_run_command=dry_run,
            execute_command=execute,
            requires=["TUSHARE_TOKEN", "ashare.dc_index partition if concept_id is not specified."],
            message="Refresh Eastmoney concept/sector membership as a mart classification fact; do not treat membership as business exposure proof.",
        )
    if recipe.schedule in {"ashare_ths_index_weekly", "ashare_ths_concept_members_weekly"}:
        command_partition = partition | _missing_partition_values(contract, partition)
        dry_run = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=True)
        snapshot_date = command_partition.get("snapshot_date") or as_of or "YYYYMMDD"
        execute = [
            "uv",
            "run",
            "rdf",
            "maintain",
            "ashare-ths-concepts",
            "--snapshot-date",
            snapshot_date,
        ]
        concept_id = command_partition.get("concept_id")
        if concept_id and concept_id != _placeholder_value("concept_id"):
            execute.extend(["--concept-id", concept_id])
        execute.append("--refresh")
        return _action(
            "maintain",
            dry_run_command=dry_run,
            execute_command=execute,
            requires=["TUSHARE_TOKEN", "ashare.ths_index partition if concept_id is not specified."],
            message="Refresh Tonghuashun concept/sector classification facts; labels and membership do not prove company business exposure.",
        )
    if recipe.schedule == "ashare_main_business_on_demand":
        command_partition = partition | _missing_partition_values(contract, partition)
        dry_run = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=True)
        security_id = command_partition["security_id"]
        segment_types = command_partition.get("segment_type", "P")
        execute = [
            "uv",
            "run",
            "rdf",
            "maintain",
            "ashare-main-business",
            "--period",
            command_partition["period"],
        ]
        if security_id == _placeholder_value("security_id") and as_of:
            execute.extend(["--stock-snapshot-date", as_of, "--limit", "20", "--segment-types", "P,D"])
        else:
            execute.extend(["--security-id", security_id, "--segment-types", segment_types])
        execute.append("--refresh")
        return _action(
            "maintain",
            dry_run_command=dry_run,
            execute_command=execute,
            requires=["TUSHARE_TOKEN", "Choose financial period; use stock_snapshot_date for batch maintenance or security_id for a focused company."],
            message="Use as business exposure seed; prefer stock-pool batch maintenance for a reporting period, then cross-check high-confidence claims against official filing text.",
        )
    if recipe.schedule == "ashare_financials_on_demand":
        command_partition = partition | _missing_partition_values(contract, partition)
        if command_partition.get("period") == _placeholder_value("period") and as_of:
            command_partition["period"] = financial_period_for_as_of(as_of)
        dry_run = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=True)
        security_id = command_partition["security_id"]
        execute = [
            "uv",
            "run",
            "rdf",
            "maintain",
            "ashare-financials",
            "--period",
            command_partition["period"],
        ]
        if security_id == _placeholder_value("security_id") and as_of:
            execute.extend(["--stock-snapshot-date", as_of, "--limit", "20"])
        else:
            execute.extend(["--security-id", security_id])
        execute.extend(["--dataset-id", contract.id, "--refresh"])
        return _action(
            "maintain",
            dry_run_command=dry_run,
            execute_command=execute,
            requires=["TUSHARE_TOKEN", "Use --period for a specific report period or --as-of to infer the latest fully due quarterly period."],
            message="Use as financial fact/evidence seed; default recovery infers the latest fully due quarterly period from as_of and keeps source/date/quality visible.",
        )
    if recipe.schedule == "ashare_disclosure_daily":
        command = _recipe_command(recipe.id, partition=partition, params=params, dry_run=False)
        return _action(
            "ingest_recipe",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["CNINFO reachable"],
            message="Optional full-market CNINFO announcement index snapshot; default research should use announcements discover for focused remote candidates.",
        )
    if recipe.schedule == "ashare_disclosure_text_on_demand":
        command_partition = partition | _missing_partition_values(contract, partition)
        announcement_id = command_partition["announcement_id"]
        if announcement_id == _placeholder_value("announcement_id"):
            discover = [
                "uv",
                "run",
                "rdf",
                "announcements",
                "discover",
                "--start-date",
                command_partition["publish_date"],
                "--end-date",
                command_partition["publish_date"],
                "--keyword",
                "KEYWORD",
                "--limit",
                "20",
            ]
            return _action(
                "discover",
                dry_run_command=[*discover, "--dry-run"],
                execute_command=discover,
                requires=["Research keyword, company/security filter, or announcement category to narrow CNINFO discovery."],
                message="Discover focused CNINFO announcement candidates without writing local mart; fetch only selected PDFs.",
            )
        fetch_text = [
            "uv",
            "run",
            "rdf",
            "announcements",
            "fetch-text",
            "--publish-date",
            command_partition["publish_date"],
            "--announcement-id",
            announcement_id,
            "--source-url",
            params.get("source_url", _placeholder_value("source_url")),
        ]
        if params.get("security_id"):
            fetch_text.extend(["--security-id", params["security_id"]])
        if params.get("security_name"):
            fetch_text.extend(["--security-name", params["security_name"]])
        if params.get("title"):
            fetch_text.extend(["--title", params["title"]])
        return _action(
            "fetch_on_demand",
            dry_run_command=[*fetch_text, "--dry-run"],
            execute_command=fetch_text,
            requires=["Selected CNINFO announcement_id and source_url from discover/search result."],
            message="Fetch and parse only the selected official PDF before using announcement content as company evidence.",
        )
    if recipe.schedule == "ashare_intraday_snapshot":
        command_partition = partition | _missing_partition_values(contract, partition)
        dry_run = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=True)
        execute = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=False)
        return _action(
            "ingest_recipe",
            dry_run_command=dry_run,
            execute_command=execute,
            requires=["secids parameter such as 0.000001", "snapshot_at ISO timestamp"],
            message="Intraday data is provisional and must not overwrite canonical ashare.daily.",
        )
    if recipe.schedule == "global_reference_weekly":
        command_partition = partition | _missing_partition_values(contract, partition)
        command = ["uv", "run", "rdf", "ingest", "pipeline", "global_reference_weekly", *_partition_args(command_partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["SEC_USER_AGENT", "CIK value"],
            message="Cross-market reference data supports evidence and context; it cannot generate A-share primary candidates.",
        )
    if recipe.schedule == "global_reference_universe_weekly":
        command_partition = partition | _missing_partition_values(contract, partition)
        command = ["uv", "run", "rdf", "ingest", "pipeline", "global_reference_universe_weekly", *_partition_args(command_partition)]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["SEC_USER_AGENT", "snapshot_date"],
            message="SEC ticker-CIK mapping is a cross-market identity reference fact; it cannot generate A-share primary candidates.",
        )
    if recipe.schedule == "global_reference_companyfacts_on_demand":
        command_partition = partition | _missing_partition_values(contract, partition)
        command = [
            "uv",
            "run",
            "rdf",
            "ingest",
            "pipeline",
            "global_reference_companyfacts_on_demand",
            *_partition_args(command_partition),
        ]
        return _action(
            "ingest_pipeline",
            dry_run_command=[*command, "--dry-run"],
            execute_command=[*command, "--refresh"],
            requires=["SEC_USER_AGENT", "CIK value"],
            message="SEC companyfacts are cross-market financial facts and evidence seeds; they cannot generate A-share primary candidates.",
        )
    if recipe.schedule == "research_on_demand":
        command_partition = partition | _missing_partition_values(contract, partition)
        if contract.id == "industry.eastmoney_report_index":
            query_date = str(command_partition.get("query_date") or "YYYYMMDD")
            resolved_params = _industry_report_params(query_date)
            dry_run = _recipe_command(recipe.id, partition=command_partition, params=resolved_params, dry_run=True)
            execute = [
                "uv",
                "run",
                "rdf",
                "maintain",
                "industry-report-index",
                "--query-date",
                query_date,
                "--lookback-days",
                "30",
                "--max-pages",
                "1",
                "--refresh",
            ]
            return _action(
                "maintain",
                dry_run_command=dry_run,
                execute_command=execute,
                requires=["Eastmoney direct HTTP access"],
                message="Refresh Eastmoney industry report index as an evidence seed; the end date is capped at query_date to avoid as-of leakage.",
            )
        dry_run = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=True)
        execute = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=False)
        return _action(
            "ingest_recipe",
            dry_run_command=dry_run,
            execute_command=[*execute, "--refresh"],
            requires=["Research query parameters such as begin and max_pages."],
            message="Research reports are evidence seeds and triage inputs, not company business exposure proof.",
        )
    command_partition = partition | _missing_partition_values(contract, partition)
    command = _recipe_command(recipe.id, partition=command_partition, params=params, dry_run=False)
    return _action(
        "ingest_recipe",
        dry_run_command=[*command, "--dry-run"],
        execute_command=[*command, "--refresh"],
        requires=[],
        message="Generic recipe recovery action.",
    )


def _feature_recovery_action(spec: FeatureSpec, *, entry: dict[str, Any], as_of: str | None) -> dict[str, Any]:
    resolved_as_of = as_of or "YYYYMMDD"
    window_status = entry.get("window_status", [])
    windows = [int(item.get("window")) for item in window_status if item.get("buildable")]
    if not windows and not window_status:
        windows = list(spec.recommended_windows)
    preferred = 20 if 20 in windows else windows[0] if windows else None
    command = (
        ["uv", "run", "rdf", "features", "build", spec.id, "--as-of", resolved_as_of, "--window", str(preferred)]
        if preferred is not None
        else None
    )
    input_checks = [
        ["uv", "run", "rdf", "inventory", "datasets", "--as-of", resolved_as_of, "--use", use]
        for item in spec.inputs
        for use in item.supports[:1]
    ]
    build_commands = [
        item["build_command"]
        for item in entry.get("window_status", [])
        if item.get("buildable") and item.get("feature_status") != "ready" and item.get("build_command")
    ]
    return _action(
        "build_feature",
        dry_run_command=None,
        execute_command=[*command, "--refresh"] if command else None,
        requires=[f"Required input dataset: {item.dataset_id}" for item in spec.inputs],
        message="Build only after required mart inputs are ready; feature output is a signal, not company fact proof.",
        extra={
            "recommended_windows": list(spec.recommended_windows),
            "buildable_windows": windows,
            "build_commands": build_commands,
            "precheck_commands": [_command_payload(command) for command in input_checks],
        },
    )


def _industry_report_params(query_date: str) -> dict[str, str]:
    if len(query_date) == 8 and query_date.isdigit():
        date_value = datetime.strptime(query_date, "%Y%m%d").date()
        begin = (date_value - timedelta(days=30)).isoformat()
        end = date_value.isoformat()
    else:
        begin = "YYYY-MM-DD"
        end = "YYYY-MM-DD"
    return {"begin": begin, "end": end, "max_pages": "1"}


def _action(
    action_type: str,
    *,
    dry_run_command: list[str] | None,
    execute_command: list[str] | None,
    requires: list[str],
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "action_type": action_type,
        "message": message,
        "requires": requires,
        "dry_run_command": _command_payload(dry_run_command),
        "execute_command": _command_payload(execute_command),
    }
    if extra:
        payload.update(extra)
    return payload


def _command_payload(command: list[str] | None) -> dict[str, Any] | None:
    if command is None:
        return None
    return {"argv": command, "text": " ".join(command)}


def _recipe_command(
    recipe_id: str,
    *,
    partition: dict[str, str],
    params: dict[str, str],
    dry_run: bool,
) -> list[str]:
    command = ["uv", "run", "rdf", "ingest", "recipe", recipe_id, *_partition_args(partition), *_param_args(params)]
    if dry_run:
        command.append("--dry-run")
    return command


def _partition_args(partition: dict[str, str]) -> list[str]:
    args: list[str] = []
    for key, value in partition.items():
        args.extend(["--partition", f"{key}={value}"])
    return args


def _param_args(params: dict[str, str]) -> list[str]:
    args: list[str] = []
    for key, value in params.items():
        args.extend(["--param", f"{key}={value}"])
    return args


def _placeholder_params(recipe: IngestionRecipe) -> dict[str, str]:
    params: dict[str, str] = {}
    _collect_param_placeholders(recipe.params_template, params)
    return params


def _collect_param_placeholders(value: Any, params: dict[str, str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _collect_param_placeholders(item, params)
    elif isinstance(value, list):
        for item in value:
            _collect_param_placeholders(item, params)
    elif isinstance(value, str):
        for part in value.split("${params.")[1:]:
            key = part.split("}", 1)[0]
            if key:
                params.setdefault(key, _placeholder_value(key))


def _action_partition(contract: DatasetContract, entry: dict[str, Any], *, as_of: str | None) -> dict[str, str]:
    requested = entry.get("requested_partition")
    if isinstance(requested, dict) and requested:
        return {str(key): str(value) for key, value in requested.items()}
    date_keys = {"trade_date", "snapshot_date", "publish_date", "query_date", "ann_date", "end_date"}
    if as_of and any(key in date_keys for key in contract.partition_keys):
        partition = {key: as_of for key in contract.partition_keys if key in date_keys}
        return partition | _missing_partition_values(contract, partition)
    if len(contract.partition_keys) == 1:
        key = contract.partition_keys[0]
        if key == "exchange":
            return {"exchange": "SSE"}
    return _missing_partition_values(contract, {})


def _missing_partition_values(contract: DatasetContract, partition: dict[str, str]) -> dict[str, str]:
    return {key: _placeholder_value(key) for key in contract.partition_keys if key not in partition}


def _placeholder_value(key: str) -> str:
    values = {
        "trade_date": "YYYYMMDD",
        "snapshot_date": "YYYYMMDD",
        "publish_date": "YYYYMMDD",
        "query_date": "YYYYMMDD",
        "ann_date": "YYYYMMDD",
        "end_date": "YYYYMMDD",
        "period": "PERIOD",
        "security_id": "SECURITY_ID",
        "segment_type": "P",
        "announcement_id": "ANNOUNCEMENT_ID",
        "concept_id": "CONCEPT_ID",
        "snapshot_at": "ISO_TIME",
        "cik": "CIK",
        "secids": "SECIDS",
        "security_name": "SECURITY_NAME",
        "title": "TITLE",
        "source_url": "SOURCE_URL",
        "begin": "YYYY-MM-DD",
        "max_pages": "MAX_PAGES",
    }
    return values.get(key, key.upper())


def _aggregate_input_status(inputs: list[dict[str, Any]]) -> str:
    required = [item for item in inputs if item.get("role") == "required"]
    relevant = required or inputs
    if not relevant:
        return "ready"
    if any(item.get("status") == "missing" for item in relevant):
        return "missing"
    if any(item.get("status") == "degraded" for item in relevant):
        return "degraded"
    return "ready"


def _dataset_priority(contract: DatasetContract, entry: dict[str, Any]) -> int:
    if contract.domain == "ashare_core" and contract.role == "core_fact":
        return 10
    if contract.permits("company_business_exposure"):
        return 20
    if contract.role == "evidence_seed":
        return 30
    if entry["status"] == "degraded":
        return 40
    return 50


def _feature_priority(spec: FeatureSpec) -> int:
    if spec.usage.permits("candidate_generation"):
        return 35
    return 60


def _plan_reason(entry: dict[str, Any]) -> str:
    status = entry.get("status")
    coverage = entry.get("coverage") or {}
    coverage_status = str(coverage.get("status") or "")
    if status == "ready" and coverage_status == "partial":
        matched = coverage.get("matched_partitions")
        missing_keys = coverage.get("missing_partition_keys") or []
        suffix = f"; missing partition keys: {', '.join(missing_keys)}" if missing_keys else ""
        return f"Local data is readable but only covers {matched} matched subpartitions for the requested target{suffix}."
    if status == "ready" and coverage_status == "none":
        return "Local data is readable only outside the requested target coverage."
    if status == "ready" and coverage_status == "latest_before":
        return "Local data is readable through a latest-before snapshot, not an exact target partition."
    if status == "missing":
        return "No usable local partition is available for the requested scope."
    if status == "degraded":
        for window in entry.get("window_status", []):
            if window.get("input_status") not in {"missing", "degraded"}:
                continue
            for input_item in window.get("inputs", []):
                if input_item.get("status") in {"missing", "degraded"}:
                    reason = str(input_item.get("reason", ""))
                    dataset_id = str(input_item.get("dataset_id", "input"))
                    window_value = window.get("window")
                    return (
                        f"Feature inputs are not ready for window {window_value}: {dataset_id}"
                        f"{': ' + reason if reason else ''}."
                    )
        quality = entry.get("active_quality") or entry.get("latest_quality") or {}
        reason = quality.get("reason") if isinstance(quality, dict) else ""
        return f"Local partition exists but quality is degraded{': ' + reason if reason else ''}."
    return "Local data is available."


def _dataset_boundary(contract: DatasetContract) -> str:
    if contract.domain == "ashare_intraday":
        return "Provisional intraday observation; never overwrite canonical EOD mart and never use for primary candidate generation."
    if contract.domain == "global_reference":
        return "Cross-market reference; use for context or evidence, not A-share primary candidate generation."
    if contract.id == "ashare.hsgt_top10":
        return "Northbound trading context; useful for market validation, not company fundamentals or business exposure proof."
    if contract.id == "ashare.northbound_eligible":
        return "Northbound eligibility reference; useful for stock-connect candidate grouping, not company fundamentals or business exposure proof."
    if contract.id == "ashare.margin_detail":
        return "Margin trading and leverage context; useful for market validation, not company fundamentals or business exposure proof."
    if contract.id in {"ashare.chip_distribution_perf", "ashare.chip_distribution_detail"}:
        return "Chip distribution market-structure context; useful for technical validation, not company fundamentals or business exposure proof."
    if contract.id in {"ashare.shareholder_count", "ashare.top10_holders", "ashare.top10_float_holders"}:
        return "Shareholder ownership-structure context; useful for concentration and holder-change screening, not company business exposure proof."
    if contract.id == "ashare.share_pledge_stats":
        return "Share pledge ownership-risk context; useful for risk and market validation, not company fundamentals or business exposure proof."
    if contract.id == "ashare.shareholder_trades":
        return "Shareholder increase/decrease event context; verify official announcements for high-confidence claims."
    if contract.id == "ashare.repurchase_events":
        return "Repurchase event context from structured source; verify official announcements for high-confidence claims."
    if contract.id == "ashare.earnings_forecast_events":
        return "Earnings forecast announcement event context; verify official announcements before using forecast details as high-confidence financial claims."
    if contract.id == "ashare.block_trades":
        return "Block trade market-structure context; useful for market validation, not company fundamentals or business exposure proof."
    if contract.id == "ashare.price_limits":
        return "Daily market price limit bounds; useful for market validation, not company fundamentals or business exposure proof."
    if contract.id == "ashare.limit_list_ths":
        return "Tonghuashun limit-up pool and board-height context; useful for short-term sentiment and market validation, not company fundamentals or business exposure proof."
    if contract.id == "ashare.index_weights":
        return "Core index constituent weights; useful for benchmark context and candidate grouping, not company fundamentals or business exposure proof."
    if contract.id in {"ashare.sw_industry_classification", "ashare.industry_members", "ashare.ci_industry_members"}:
        return "Industry classification fact; not company product, customer, revenue, or business exposure proof."
    if contract.role == "evidence_seed":
        return "Evidence seed; inspect source text or official filing before promoting to high-confidence company conclusion."
    if "company_business_exposure" in contract.usage.forbidden_uses:
        return "Cannot prove company business exposure by itself."
    return "Use according to allowed_uses and keep source/date/quality visible in research output."
