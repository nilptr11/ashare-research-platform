from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib import parse, request

from ..schemas import ConnectorError, SourceResponse
from .base import frame_from_payload, now_iso, response_from_frame


@dataclass(frozen=True)
class HttpPayload:
    status: int
    body: str
    headers: dict[str, str]
    url: str


HttpTransport = Callable[[str, str, dict[str, Any], dict[str, str], Any], HttpPayload]


class HttpJsonConnector:
    source = "http_json"

    def __init__(self, *, transport: HttpTransport | None = None) -> None:
        self._transport = transport or _urllib_transport

    def fetch(
        self,
        api_name: str,
        params: dict[str, Any],
        fields: list[str] | tuple[str, ...] | None = None,
    ) -> SourceResponse:
        request_params = dict(params)
        url = str(request_params.pop("url", "") or "")
        if not url:
            raise ConnectorError(f"{self.source}: url is required")
        method = str(request_params.pop("method", "GET")).upper()
        headers = _headers(request_params.pop("headers", None))
        body = request_params.pop("body", None)
        requested_at = now_iso()
        try:
            response = self._transport(method, url, request_params, headers, body)
            payload = json.loads(response.body) if response.body else None
        except json.JSONDecodeError as error:
            raise ConnectorError(f"{self.source}: response is not valid JSON") from error
        except Exception as error:  # pragma: no cover - wraps network errors.
            raise ConnectorError(f"{self.source}: request failed for {api_name}: {error}") from error
        frame = frame_from_payload(payload)
        return response_from_frame(
            source=self.source,
            api_name=api_name,
            params={
                "url": response.url,
                "method": method,
                "query": request_params,
                "status": response.status,
            },
            fields=fields,
            requested_at=requested_at,
            frame=frame,
        )


def _headers(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    raise ConnectorError("headers must be a JSON object")


def _urllib_transport(method: str, url: str, params: dict[str, Any], headers: dict[str, str], body: Any) -> HttpPayload:
    target_url = url
    payload_bytes: bytes | None = None
    request_headers = dict(headers)
    if method == "GET":
        query = parse.urlencode(params, doseq=True)
        if query:
            separator = "&" if parse.urlparse(url).query else "?"
            target_url = f"{url}{separator}{query}"
    else:
        payload = body if body is not None else params
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = request.Request(target_url, data=payload_bytes, headers=request_headers, method=method)
    with request.urlopen(req, timeout=30) as response:  # noqa: S310 - source URLs are user-provided connector inputs.
        text = response.read().decode("utf-8")
        return HttpPayload(
            status=response.status,
            body=text,
            headers={str(key): str(value) for key, value in response.headers.items()},
            url=target_url,
        )
