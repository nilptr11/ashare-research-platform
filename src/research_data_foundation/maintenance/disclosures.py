from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import FoundationRegistry
from ..domains import default_registry
from ..ingestion import IngestionRunner
from ..sources import SourceAdapter
from ..storage import MartStore, StorageError
from .ashare_core import MaintenanceError, compact_date


class AShareAnnouncementTextMaintainer:
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
        publish_date: str,
        announcement_ids: tuple[str, ...] = (),
        limit: int = 0,
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        normalized_publish_date = compact_date(publish_date)
        rows = self._announcement_rows(normalized_publish_date)
        requested_ids = {str(item).strip() for item in announcement_ids if str(item).strip()}
        if requested_ids:
            rows = [row for row in rows if str(row.get("announcement_id") or "") in requested_ids]
        if limit and limit > 0:
            rows = rows[:limit]
        if not rows:
            return {
                "schema": "rdf.ashare_announcement_text_maintenance_run.v1",
                "publish_date": normalized_publish_date,
                "announcement_ids": sorted(requested_ids),
                "status": "blocked",
                "message": "no announcements to maintain",
                "tasks": [],
            }

        tasks: list[dict[str, Any]] = []
        for row in rows:
            announcement_id = str(row.get("announcement_id") or "").strip()
            partition = {"publish_date": normalized_publish_date, "announcement_id": announcement_id}
            if self._partition_exists("ashare.announcement_text", partition) and not refresh:
                tasks.append(task_payload(partition, status="skipped"))
                continue
            try:
                result = self.runner.run_recipe(
                    "cninfo.announcement_pdf_text.to_ashare_announcement_text",
                    partition=partition,
                    params={
                        "security_id": str(row.get("security_id") or ""),
                        "security_name": str(row.get("security_name") or ""),
                        "title": str(row.get("title") or ""),
                        "source_url": str(row.get("source_url") or ""),
                    },
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
            "schema": "rdf.ashare_announcement_text_maintenance_run.v1",
            "publish_date": normalized_publish_date,
            "announcement_ids": sorted(requested_ids),
            "status": status,
            "tasks": tasks,
        }

    def _announcement_rows(self, publish_date: str) -> list[dict[str, Any]]:
        try:
            frame = self.mart_store.read("ashare.announcements", {"publish_date": publish_date})
        except StorageError as error:
            raise MaintenanceError(f"missing ashare.announcements partition: {publish_date}") from error
        if frame.empty:
            return []
        return [
            row
            for row in frame.to_dict(orient="records")
            if str(row.get("announcement_id") or "").strip() and str(row.get("source_url") or "").strip()
        ]

    def _partition_exists(self, dataset_id: str, partition: dict[str, str]) -> bool:
        try:
            path = self.mart_store.partition_path(dataset_id, partition)
        except Exception:
            return False
        return (path / "part.parquet").exists() and (path / "_meta.json").exists()


def task_payload(
    partition: dict[str, str],
    *,
    status: str,
    rows: int | None = None,
    result: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": "ashare.announcement_text",
        "recipe_id": "cninfo.announcement_pdf_text.to_ashare_announcement_text",
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
