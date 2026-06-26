from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import FoundationRegistry
from ..core.schemas import DatasetContract, IngestionRecipe
from ..domains import default_registry
from ..sources import SourceAdapter, default_source_adapters
from ..storage import MartStore, RawStore, SourceFetchResult, StagingStore


class IngestionError(RuntimeError):
    """Raised when a recipe cannot be executed."""


@dataclass(frozen=True)
class IngestionResult:
    recipe_id: str
    dataset_id: str
    partition: dict[str, str]
    rows: int
    raw_path: str | None
    staging_path: str | None
    mart_path: str
    source_id: str
    source_api: str
    params: dict[str, Any]
    fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.ingestion_result.v1",
            "recipe_id": self.recipe_id,
            "dataset_id": self.dataset_id,
            "partition": dict(self.partition),
            "rows": self.rows,
            "raw_path": self.raw_path,
            "staging_path": self.staging_path,
            "mart_path": self.mart_path,
            "source_id": self.source_id,
            "source_api": self.source_api,
            "params": dict(self.params),
            "fields": list(self.fields),
        }


@dataclass(frozen=True)
class IngestionPlan:
    recipe_id: str
    dataset_id: str
    partition: dict[str, str]
    params: dict[str, Any]
    source: dict[str, Any]
    dataset: dict[str, Any]
    recipe: dict[str, Any]
    refresh: bool = False

    @property
    def would_write_layers(self) -> tuple[str, ...]:
        layers = []
        if self.recipe.get("raw_required"):
            layers.append("raw")
        if self.recipe.get("staging_required"):
            layers.append("staging")
        layers.append("mart")
        return tuple(layers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.ingestion_plan.v1",
            "execution_mode": "plan",
            "will_fetch": False,
            "will_write": False,
            "would_write_layers": list(self.would_write_layers),
            "recipe_id": self.recipe_id,
            "dataset_id": self.dataset_id,
            "partition": dict(self.partition),
            "params": dict(self.params),
            "source": dict(self.source),
            "dataset": dict(self.dataset),
            "recipe": dict(self.recipe),
            "refresh": self.refresh,
            "note": "Dry-run plan only: no source request, raw artifact, staging partition, or mart partition is created.",
        }


@dataclass(frozen=True)
class PipelineRunResult:
    pipeline_id: str
    results: tuple[IngestionResult, ...]
    failures: tuple[str, ...] = ()

    @property
    def rows(self) -> int:
        return sum(result.rows for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.pipeline_run_result.v1",
            "pipeline_id": self.pipeline_id,
            "steps": [result.to_dict() for result in self.results],
            "failures": list(self.failures),
            "rows": self.rows,
        }


@dataclass(frozen=True)
class PipelinePlan:
    pipeline_id: str
    partition: dict[str, str]
    params: dict[str, Any]
    steps: tuple[dict[str, Any], ...]
    refresh: bool = False
    continue_on_error: bool = False

    @property
    def would_write_layers(self) -> tuple[str, ...]:
        layers: list[str] = []
        for step in self.steps:
            for layer in step["plan"].would_write_layers:
                if layer not in layers:
                    layers.append(layer)
        return tuple(layers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.pipeline_ingestion_plan.v1",
            "execution_mode": "plan",
            "will_fetch": False,
            "will_write": False,
            "would_write_layers": list(self.would_write_layers),
            "pipeline_id": self.pipeline_id,
            "partition": dict(self.partition),
            "params": dict(self.params),
            "refresh": self.refresh,
            "continue_on_error": self.continue_on_error,
            "steps": [
                {
                    "recipe_id": step["recipe_id"],
                    "required": step["required"],
                    "depends_on": list(step["depends_on"]),
                    "plan": step["plan"].to_dict(),
                }
                for step in self.steps
            ],
            "note": "Dry-run plan only: no source request, raw artifact, staging partition, or mart partition is created.",
        }


class IngestionRunner:
    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        registry: FoundationRegistry | None = None,
        adapters: dict[str, SourceAdapter] | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.adapters = adapters or default_source_adapters()
        self.raw_store = RawStore(data_dir)
        self.staging_store = StagingStore(data_dir, self.registry)
        self.mart_store = MartStore(data_dir, self.registry)

    def plan_recipe(
        self,
        recipe_id: str,
        *,
        partition: dict[str, str],
        params: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> IngestionPlan:
        recipe = self.registry.require_recipe(recipe_id)
        source = self.registry.require_source(recipe.source_id)
        contract = self.registry.require_dataset(recipe.target_dataset_id)
        request_params = resolve_params(recipe.params_template, partition=partition, params=params or {})
        return IngestionPlan(
            recipe_id=recipe.id,
            dataset_id=contract.id,
            partition=dict(partition),
            params=request_params,
            source={
                "id": source.id,
                "title": source.title,
                "source_role": source.source_role,
                "authority_tier": source.authority_tier,
                "transport": source.transport,
                "rate_limit": dict(source.rate_limit),
                "auth": dict(source.auth),
            },
            dataset={
                "id": contract.id,
                "title": contract.title,
                "domain": contract.domain,
                "market_scope": contract.market_scope,
                "role": contract.role,
                "temporal": {
                    "temporal_mode": contract.temporal.temporal_mode,
                    "finality": contract.temporal.finality,
                    "available_after": contract.temporal.available_after,
                    "as_of_policy": contract.temporal.as_of_policy,
                },
                "usage": contract.usage.to_dict(),
                "partition_keys": list(contract.partition_keys),
                "primary_key": list(contract.primary_key),
                "required_columns": list(contract.required_columns),
                "analysis_columns": list(contract.analysis_columns),
                "empty_policy": contract.empty_policy,
            },
            recipe={
                "source_api": recipe.source_api,
                "schedule": recipe.schedule,
                "fields": list(recipe.fields),
                "params_template": dict(recipe.params_template),
                "fanout_params": {key: list(value) for key, value in recipe.fanout_params.items()},
                "pagination": dict(recipe.pagination),
                "field_map": dict(recipe.field_map),
                "numeric_columns": list(recipe.numeric_columns),
                "raw_required": recipe.lineage.raw_required,
                "staging_required": recipe.lineage.staging_required,
                "selection_priority": recipe.selection_priority,
                "notes": recipe.notes,
            },
            refresh=refresh,
        )

    def plan_pipeline(
        self,
        pipeline_id: str,
        *,
        partition: dict[str, str],
        params: dict[str, Any] | None = None,
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> PipelinePlan:
        pipeline = self.registry.require_pipeline(pipeline_id)
        plan_params = params or {}
        steps = tuple(
            {
                "recipe_id": step.recipe_id,
                "required": step.required,
                "depends_on": tuple(step.depends_on),
                "plan": self.plan_recipe(
                    step.recipe_id,
                    partition=partition,
                    params=plan_params,
                    refresh=refresh,
                ),
            }
            for step in pipeline.steps
        )
        return PipelinePlan(
            pipeline_id=pipeline.id,
            partition=dict(partition),
            params=dict(plan_params),
            steps=steps,
            refresh=refresh,
            continue_on_error=continue_on_error,
        )

    def run_recipe(
        self,
        recipe_id: str,
        *,
        partition: dict[str, str],
        params: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> IngestionResult:
        recipe = self.registry.require_recipe(recipe_id)
        contract = self.registry.require_dataset(recipe.target_dataset_id)
        request_params = resolve_params(recipe.params_template, partition=partition, params=params or {})
        adapter = self._adapter(recipe.source_id)
        fetch_result = self._fetch_recipe(recipe, adapter=adapter, request_params=request_params)
        normalized = transform_frame(fetch_result.frame, recipe, partition=partition)
        normalized = filter_frame_to_partition(normalized, partition)
        normalized = normalize_primary_key_frame(normalized, contract)

        raw_path = None
        if recipe.lineage.raw_required:
            raw_path = self.raw_store.write(fetch_result)

        lineage = {
            "source_id": recipe.source_id,
            "source_api": recipe.source_api,
            "recipe_id": recipe.id,
            "requested_params": request_params,
            "requested_fields": list(recipe.fields),
        }
        if recipe.fanout_params:
            lineage["fanout_params"] = {key: list(value) for key, value in recipe.fanout_params.items()}
        if recipe.pagination:
            lineage["pagination"] = dict(recipe.pagination)
        if raw_path is not None:
            lineage["raw_path"] = str(raw_path)

        staging_path = None
        if recipe.lineage.staging_required:
            staging_path = self.staging_store.publish(
                contract.id,
                normalized,
                partition=partition,
                lineage=lineage,
                refresh=refresh,
            )

        mart_lineage = dict(lineage)
        if staging_path is not None:
            mart_lineage["staging_path"] = str(staging_path)
        mart_path = self.mart_store.publish(
            contract.id,
            normalized,
            partition=partition,
            lineage=mart_lineage,
            refresh=refresh,
        )
        return IngestionResult(
            recipe_id=recipe.id,
            dataset_id=contract.id,
            partition=dict(partition),
            rows=int(len(normalized)),
            raw_path=str(raw_path) if raw_path is not None else None,
            staging_path=str(staging_path) if staging_path is not None else None,
            mart_path=str(mart_path),
            source_id=recipe.source_id,
            source_api=recipe.source_api,
            params=request_params,
            fields=tuple(recipe.fields),
        )

    def run_pipeline(
        self,
        pipeline_id: str,
        *,
        partition: dict[str, str],
        params: dict[str, Any] | None = None,
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> PipelineRunResult:
        pipeline = self.registry.require_pipeline(pipeline_id)
        results: list[IngestionResult] = []
        failures: list[str] = []
        for step in pipeline.steps:
            try:
                results.append(
                    self.run_recipe(
                        step.recipe_id,
                        partition=partition,
                        params=params,
                        refresh=refresh,
                    )
                )
            except Exception as error:
                if step.required or not continue_on_error:
                    raise
                failures.append(f"{step.recipe_id}: {error}")
        if failures:
            failures = list(failures)
        return PipelineRunResult(pipeline_id=pipeline.id, results=tuple(results), failures=tuple(failures))

    def _adapter(self, source_id: str) -> SourceAdapter:
        try:
            return self.adapters[source_id]
        except KeyError as error:
            raise IngestionError(f"source adapter not configured: {source_id}") from error

    def _validate_fetch_result(self, recipe: IngestionRecipe, result: SourceFetchResult) -> None:
        if result.source_id != recipe.source_id:
            raise IngestionError(f"{recipe.id}: adapter returned source {result.source_id!r}, expected {recipe.source_id!r}")
        if result.api_name != recipe.source_api:
            raise IngestionError(f"{recipe.id}: adapter returned api {result.api_name!r}, expected {recipe.source_api!r}")

    def _fetch_recipe(self, recipe: IngestionRecipe, *, adapter: SourceAdapter, request_params: dict[str, Any]) -> SourceFetchResult:
        if recipe.pagination and recipe.fanout_params:
            raise IngestionError(f"{recipe.id}: pagination and fanout cannot be combined")
        if recipe.pagination:
            return self._fetch_paginated_recipe(recipe, adapter=adapter, request_params=request_params)
        if not recipe.fanout_params:
            result = adapter.fetch(recipe.source_api, request_params, fields=recipe.fields)
            self._validate_fetch_result(recipe, result)
            return result
        if len(recipe.fanout_params) != 1:
            raise IngestionError(f"{recipe.id}: only one fanout param is currently supported")
        fanout_key, fanout_values = next(iter(recipe.fanout_params.items()))
        if not fanout_values:
            raise IngestionError(f"{recipe.id}: fanout param {fanout_key!r} has no values")
        frames: list[pd.DataFrame] = []
        child_counts: dict[str, int] = {}
        requested_at = ""
        for value in fanout_values:
            child_params = dict(request_params)
            child_params[fanout_key] = value
            result = adapter.fetch(recipe.source_api, child_params, fields=recipe.fields)
            self._validate_fetch_result(recipe, result)
            if not requested_at:
                requested_at = result.requested_at
            child_counts[str(value)] = result.rows
            child_frame = result.frame.copy()
            if fanout_key not in child_frame.columns:
                child_frame[fanout_key] = value
            frames.append(child_frame)
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return SourceFetchResult(
            source_id=recipe.source_id,
            api_name=recipe.source_api,
            params=dict(request_params) | {"fanout": {fanout_key: list(fanout_values)}},
            requested_at=requested_at,
            frame=frame,
            metadata={
                "adapter": "fanout",
                "fields": list(recipe.fields),
                "fanout_key": fanout_key,
                "fanout_values": list(fanout_values),
                "child_counts": child_counts,
            },
        )

    def _fetch_paginated_recipe(
        self,
        recipe: IngestionRecipe,
        *,
        adapter: SourceAdapter,
        request_params: dict[str, Any],
    ) -> SourceFetchResult:
        limit_param = str(recipe.pagination.get("limit_param", "limit"))
        offset_param = str(recipe.pagination.get("offset_param", "offset"))
        limit = _positive_int(recipe.pagination.get("limit", 3000), f"{recipe.id}.pagination.limit")
        max_pages = _positive_int(recipe.pagination.get("max_pages", 20), f"{recipe.id}.pagination.max_pages")

        frames: list[pd.DataFrame] = []
        page_rows: list[int] = []
        requested_at = ""
        for page in range(max_pages):
            child_params = dict(request_params)
            child_params[limit_param] = limit
            child_params[offset_param] = page * limit
            result = adapter.fetch(recipe.source_api, child_params, fields=recipe.fields)
            self._validate_fetch_result(recipe, result)
            if not requested_at:
                requested_at = result.requested_at
            frames.append(result.frame)
            page_rows.append(result.rows)
            if result.rows < limit:
                break
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return SourceFetchResult(
            source_id=recipe.source_id,
            api_name=recipe.source_api,
            params=dict(request_params)
            | {
                "pagination": {
                    "limit_param": limit_param,
                    "offset_param": offset_param,
                    "limit": limit,
                    "max_pages": max_pages,
                    "page_rows": page_rows,
                }
            },
            requested_at=requested_at,
            frame=frame,
            metadata={
                "adapter": "pagination",
                "fields": list(recipe.fields),
                "pagination": {
                    "limit_param": limit_param,
                    "offset_param": offset_param,
                    "limit": limit,
                    "max_pages": max_pages,
                    "page_rows": page_rows,
                },
            },
        )


def transform_frame(frame: pd.DataFrame, recipe: IngestionRecipe, *, partition: dict[str, str]) -> pd.DataFrame:
    output = frame.copy()
    if recipe.field_map:
        rename_map = {source: target for source, target in recipe.field_map.items() if source in output.columns}
        output = output.rename(columns=rename_map)
    for key, value in partition.items():
        if key not in output.columns:
            output[key] = value
    for column in recipe.numeric_columns:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.reset_index(drop=True)


def normalize_primary_key_frame(frame: pd.DataFrame, contract: DatasetContract) -> pd.DataFrame:
    output = frame.copy()
    primary_key = [column for column in contract.primary_key if column in output.columns]
    if output.empty or len(primary_key) != len(contract.primary_key):
        return output.reset_index(drop=True)
    if not output.duplicated(primary_key, keep=False).any():
        return output.reset_index(drop=True)

    helper_columns: list[str] = []
    sort_columns: list[str] = []
    ascending: list[bool] = []
    if "update_flag" in output.columns:
        helper = "_rdf_update_flag_rank"
        output[helper] = output["update_flag"].map(_update_flag_rank)
        helper_columns.append(helper)
        sort_columns.append(helper)
        ascending.append(True)
    for column in ("f_ann_date", "ann_date", "publish_time", "publish_date", "report_date"):
        if column in output.columns:
            helper = f"_rdf_sort_{column}"
            output[helper] = output[column].fillna("").astype(str)
            helper_columns.append(helper)
            sort_columns.append(helper)
            ascending.append(True)
    order_helper = "_rdf_source_order"
    output[order_helper] = range(len(output))
    helper_columns.append(order_helper)
    sort_columns.append(order_helper)
    ascending.append(True)

    deduped = output.sort_values(sort_columns, ascending=ascending).drop_duplicates(primary_key, keep="last")
    return deduped.drop(columns=helper_columns).reset_index(drop=True)


def filter_frame_to_partition(frame: pd.DataFrame, partition: dict[str, str]) -> pd.DataFrame:
    output = frame.copy()
    for key, value in partition.items():
        if key not in output.columns or output.empty:
            continue
        mask = output[key].fillna("").astype(str) == str(value)
        output = output.loc[mask].copy()
    return output.reset_index(drop=True)


def _update_flag_rank(value: Any) -> int:
    if pd.isna(value):
        return -1
    text = str(value).strip().lower()
    if text in {"1", "y", "yes", "true", "updated", "revision", "revised"}:
        return 1
    if text in {"0", "n", "no", "false", ""}:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def resolve_params(template: dict[str, Any], *, partition: dict[str, str], params: dict[str, Any]) -> dict[str, Any]:
    return {key: _resolve_value(value, partition=partition, params=params) for key, value in template.items()}


def _resolve_value(value: Any, *, partition: dict[str, str], params: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_value(item, partition=partition, params=params) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, partition=partition, params=params) for item in value]
    if not isinstance(value, str):
        return value

    matches = list(re.finditer(r"\$\{(partition|params)\.([A-Za-z0-9_]+)\}", value))
    if not matches:
        return value
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return _lookup_placeholder(matches[0].group(1), matches[0].group(2), partition=partition, params=params)
    output = value
    for match in matches:
        replacement = str(_lookup_placeholder(match.group(1), match.group(2), partition=partition, params=params))
        output = output.replace(match.group(0), replacement)
    return output


def _lookup_placeholder(scope: str, key: str, *, partition: dict[str, str], params: dict[str, Any]) -> Any:
    source: dict[str, Any] = partition if scope == "partition" else params
    if key not in source:
        raise IngestionError(f"missing template value: {scope}.{key}")
    return source[key]


def _positive_int(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise IngestionError(f"{field_name} must be a positive integer") from error
    if normalized <= 0:
        raise IngestionError(f"{field_name} must be a positive integer")
    return normalized
