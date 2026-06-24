from __future__ import annotations

from typing import Any

import pandas as pd

from ..schemas import ConnectorError, SourceResponse
from .base import frame_from_payload, now_iso, require_callable, response_from_frame


class AkshareConnector:
    source = "akshare"

    def __init__(self, *, module: Any = None) -> None:
        self._module = module

    def fetch(self, api_name: str, params: dict[str, Any], fields: list[str] | tuple[str, ...] | None = None) -> SourceResponse:
        module = self._module or self._load_module()
        requested_at = now_iso()
        func = require_callable(module, api_name)
        try:
            payload = func(**params)
        except Exception as error:  # pragma: no cover - wraps external SDK errors.
            raise ConnectorError(f"Akshare call failed for {api_name}: {error}") from error
        frame = frame_from_payload(payload)
        if not isinstance(frame, pd.DataFrame):
            frame = pd.DataFrame(frame)
        return response_from_frame(
            source=self.source,
            api_name=api_name,
            params=dict(params),
            fields=fields,
            requested_at=requested_at,
            frame=frame,
        )

    def _load_module(self) -> Any:
        try:
            import akshare as ak
        except ImportError as error:  # pragma: no cover - optional dependency.
            raise ConnectorError("akshare is not installed") from error
        return ak
