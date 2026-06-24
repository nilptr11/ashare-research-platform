from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from ..schemas import ConnectorError, SourceResponse


ConnectorFactory = Callable[..., Any]


@dataclass(frozen=True)
class ConnectorSpec:
    name: str
    title: str
    factory: ConnectorFactory
    kind: str
    requires_url: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "kind": self.kind,
            "requires_url": self.requires_url,
            "description": self.description,
        }


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def frame_from_payload(payload: Any) -> pd.DataFrame:
    if payload is None:
        return pd.DataFrame()
    if isinstance(payload, pd.DataFrame):
        return payload
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return pd.DataFrame(data)
        if isinstance(data, dict):
            return pd.DataFrame([data])
        return pd.DataFrame([payload])
    return pd.DataFrame([{"value": payload}])


def response_from_frame(
    *,
    source: str,
    api_name: str,
    params: dict[str, Any],
    fields: list[str] | tuple[str, ...] | None,
    requested_at: str,
    frame: pd.DataFrame,
) -> SourceResponse:
    requested_fields = tuple(str(field) for field in (fields or ()))
    if requested_fields:
        existing = [field for field in requested_fields if field in frame.columns]
        if existing:
            frame = frame[existing]
    return SourceResponse(
        source=source,
        api_name=api_name,
        params=params,
        fields=requested_fields,
        rows=len(frame),
        columns=tuple(str(column) for column in frame.columns),
        requested_at=requested_at,
        frame=frame,
    )


def require_callable(module: Any, name: str) -> Any:
    func = getattr(module, name, None)
    if func is None or not callable(func):
        raise ConnectorError(f"API function not found: {name}")
    return func
