from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..core.paths import default_data_dir
from ..core.schemas import SchemaError


@dataclass(frozen=True)
class SourceArtifact:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        if not self.filename:
            raise SchemaError("SourceArtifact.filename is required")
        if not isinstance(self.content, bytes):
            raise SchemaError("SourceArtifact.content must be bytes")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def bytes(self) -> int:
        return len(self.content)

    def metadata(self, *, path: str | None = None) -> dict[str, Any]:
        payload = {
            "filename": self.filename,
            "content_type": self.content_type,
            "bytes": self.bytes,
            "sha256": self.sha256,
        }
        if path:
            payload["path"] = path
        return payload


@dataclass(frozen=True)
class SourceFetchResult:
    source_id: str
    api_name: str
    params: dict[str, Any]
    requested_at: str
    frame: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[SourceArtifact, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_id:
            raise SchemaError("SourceFetchResult.source_id is required")
        if not self.api_name:
            raise SchemaError("SourceFetchResult.api_name is required")

    @property
    def rows(self) -> int:
        return int(len(self.frame))

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(str(column) for column in self.frame.columns)

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "api_name": self.api_name,
            "params": self.params,
            "requested_at": self.requested_at,
            "rows": self.rows,
            "columns": list(self.columns),
        }


class RawStore:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.raw_root = self.data_dir / "raw"

    def write(self, result: SourceFetchResult) -> Path:
        request_hash = hashlib.sha256(
            json.dumps(result.fingerprint_payload(), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        safe_time = result.requested_at.replace(":", "").replace("+", "_")
        path = self.raw_root / result.source_id / result.api_name / f"{safe_time}_{request_hash}"
        if path.exists():
            raise FileExistsError(f"raw response already exists: {path}")
        path.mkdir(parents=True)
        request_payload = {
            "schema": "rdf.raw_request.v1",
            **result.fingerprint_payload(),
            "metadata": result.metadata,
        }
        if result.artifacts:
            artifact_root = path / "artifacts"
            artifact_root.mkdir(parents=True, exist_ok=True)
            artifact_metadata = []
            for artifact in result.artifacts:
                artifact_path = artifact_root / safe_filename(artifact.filename)
                artifact_path.write_bytes(artifact.content)
                artifact_metadata.append(artifact.metadata(path=str(artifact_path.relative_to(path))))
            request_payload["artifacts"] = artifact_metadata
        (path / "request.json").write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result.frame.to_json(path / "response.jsonl", orient="records", lines=True, force_ascii=False)
        return path


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {".", "-", "_"} else "_" for char in value)
