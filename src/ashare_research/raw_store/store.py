from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..paths import default_data_dir
from ..schemas import RawStoreError, SourceResponse


class RawStore:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.raw_root = self.data_dir / "raw"

    def write_response(self, response: SourceResponse) -> Path:
        request_hash = hashlib.sha256(response.request_fingerprint().encode("utf-8")).hexdigest()[:16]
        safe_time = response.requested_at.replace(":", "").replace("+", "_")
        path = self.raw_root / response.source / response.api_name / f"{safe_time}_{request_hash}"
        if path.exists():
            raise RawStoreError(f"Raw response already exists: {path}")
        path.mkdir(parents=True)
        request_payload = {
            "schema": "ashare.raw_request.v1",
            "source": response.source,
            "api_name": response.api_name,
            "params": response.params,
            "fields": list(response.fields),
            "requested_at": response.requested_at,
            "rows": response.rows,
            "columns": list(response.columns),
        }
        (path / "request.json").write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        response.frame.to_json(path / "response.jsonl", orient="records", lines=True, force_ascii=False)
        return path
