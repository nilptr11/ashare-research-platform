from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import FoundationRegistry
from ..domains import default_registry
from ..ingestion import IngestionRunner
from ..sources import SourceAdapter
from ..storage import MartStore, StorageError
from .ashare_core import MaintenanceError, compact_date


class AShareConceptMembersMaintainer:
    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        registry: FoundationRegistry | None = None,
        adapters: dict[str, SourceAdapter] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.registry = registry or default_registry()
        self.runner = IngestionRunner(data_dir=data_dir, registry=self.registry, adapters=adapters)
        self.mart_store = MartStore(data_dir, self.registry)

    def maintain(
        self,
        *,
        snapshot_date: str,
        concept_ids: tuple[str, ...] = (),
        dc_index_date: str | None = None,
        limit: int = 0,
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        normalized_snapshot_date = compact_date(snapshot_date)
        normalized_dc_index_date = compact_date(dc_index_date or snapshot_date)
        concepts = normalize_concept_ids(concept_ids)
        if not concepts:
            concepts = self._concept_pool(normalized_dc_index_date)
        if limit and limit > 0:
            concepts = concepts[:limit]
        if not concepts:
            return {
                "schema": "rdf.ashare_concept_members_maintenance_run.v1",
                "snapshot_date": normalized_snapshot_date,
                "dc_index_date": normalized_dc_index_date,
                "concept_ids": [],
                "status": "blocked",
                "message": "no concept ids to maintain",
                "tasks": [],
            }

        tasks: list[dict[str, Any]] = []
        for concept_id in concepts:
            partition = {"snapshot_date": normalized_snapshot_date, "concept_id": concept_id}
            if self._partition_exists("ashare.concept_members", partition) and not refresh:
                tasks.append(task_payload(partition, status="skipped"))
                continue
            try:
                result = self.runner.run_recipe(
                    "tushare.dc_member.to_ashare_concept_members",
                    partition=partition,
                    refresh=refresh,
                )
                tasks.append(task_payload(partition, status="ready", rows=result.rows, result=result.to_dict()))
            except Exception as error:
                tasks.append(task_payload(partition, status="failed", message=str(error)))
                if not continue_on_error:
                    raise

        failures = [task for task in tasks if task["status"] == "failed"]
        ready = [task for task in tasks if task["status"] in {"ready", "skipped"}]
        status = "blocked" if failures and not ready else "warning" if failures else "ready"
        return {
            "schema": "rdf.ashare_concept_members_maintenance_run.v1",
            "snapshot_date": normalized_snapshot_date,
            "dc_index_date": normalized_dc_index_date,
            "concept_ids": list(concepts),
            "status": status,
            "tasks": tasks,
        }

    def _concept_pool(self, dc_index_date: str) -> tuple[str, ...]:
        try:
            frame = self.mart_store.read("ashare.dc_index", {"trade_date": dc_index_date}, columns=["concept_id"])
        except StorageError as error:
            raise MaintenanceError(f"missing dc_index partition: {dc_index_date}") from error
        if frame.empty or "concept_id" not in frame.columns:
            return ()
        return normalize_concept_ids(tuple(str(value) for value in frame["concept_id"].dropna()))

    def _partition_exists(self, dataset_id: str, partition: dict[str, str]) -> bool:
        try:
            path = self.mart_store.partition_path(dataset_id, partition)
        except Exception:
            return False
        return (path / "part.parquet").exists() and (path / "_meta.json").exists()


def normalize_concept_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    output: list[str] = []
    for value in values:
        text = str(value).strip().upper()
        if not text:
            continue
        if text not in output:
            output.append(text)
    return tuple(output)


def task_payload(
    partition: dict[str, str],
    *,
    status: str,
    rows: int | None = None,
    result: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": "ashare.concept_members",
        "recipe_id": "tushare.dc_member.to_ashare_concept_members",
        "partition": dict(partition),
        "status": status,
    }
    if rows is not None:
        payload["rows"] = rows
    if result is not None:
        payload["result"] = result
    if message:
        payload["message"] = message
    return payload
