from __future__ import annotations

import json
from collections import ChainMap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..core.paths import default_data_dir
from ..sources.base import SourceAdapterError
from ..sources.http import HttpTransport, urllib_get_json, urllib_post_json
from .schemas import CONFIDENCE_VALUES, MATURITY_VALUES, SOURCE_TYPES, EvidenceRecord, EvidenceSourceRef
from .store import EvidenceIngestResult, EvidenceStore


class EvidenceSourceError(ValueError):
    """Raised when a reusable evidence source spec is invalid."""


@dataclass(frozen=True)
class EvidenceSourceSpec:
    source_id: str
    title: str
    source_type: str
    source_name: str
    source_url: str
    topic: str
    claim_template: str = ""
    method: str = "GET"
    params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    records_path: str = ""
    field_map: dict[str, str] = field(default_factory=dict)
    published_at: str = ""
    published_at_path: str = ""
    market_scope: str = ""
    industry: str = ""
    company: str = ""
    product: str = ""
    metric: str = ""
    period: str = ""
    unit: str = ""
    confidence: str = "medium"
    verification: str = "registered_evidence_source"
    supports: tuple[str, ...] = ("evidence",)
    maturity: str = "fetched"
    quality_flags: tuple[str, ...] = ()
    notes: str = ""
    timeout_seconds: int = 20

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceSourceSpec":
        normalized = dict(payload)
        normalized.pop("schema", None)
        normalized.pop("status", None)
        return cls(
            source_id=str(normalized["source_id"]),
            title=str(normalized.get("title") or normalized["source_id"]),
            source_type=str(normalized["source_type"]),
            source_name=str(normalized["source_name"]),
            source_url=str(normalized["source_url"]),
            topic=str(normalized["topic"]),
            claim_template=str(normalized.get("claim_template", "")),
            method=str(normalized.get("method", "GET")).upper(),
            params=dict(normalized.get("params") or {}),
            headers={str(key): str(value) for key, value in (normalized.get("headers") or {}).items()},
            records_path=str(normalized.get("records_path", "")),
            field_map={str(key): str(value) for key, value in (normalized.get("field_map") or {}).items()},
            published_at=str(normalized.get("published_at", "")),
            published_at_path=str(normalized.get("published_at_path", "")),
            market_scope=str(normalized.get("market_scope", "")),
            industry=str(normalized.get("industry", "")),
            company=str(normalized.get("company", "")),
            product=str(normalized.get("product", "")),
            metric=str(normalized.get("metric", "")),
            period=str(normalized.get("period", "")),
            unit=str(normalized.get("unit", "")),
            confidence=str(normalized.get("confidence", "medium")),
            verification=str(normalized.get("verification", "registered_evidence_source")),
            supports=tuple(str(item) for item in normalized.get("supports") or ("evidence",)),
            maturity=str(normalized.get("maturity", "fetched")),
            quality_flags=tuple(str(item) for item in normalized.get("quality_flags") or ()),
            notes=str(normalized.get("notes", "")),
            timeout_seconds=int(normalized.get("timeout_seconds", 20)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rdf.evidence_source_spec.v1",
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "topic": self.topic,
            "claim_template": self.claim_template,
            "method": self.method,
            "params": dict(self.params),
            "headers": dict(self.headers),
            "records_path": self.records_path,
            "field_map": dict(self.field_map),
            "published_at": self.published_at,
            "published_at_path": self.published_at_path,
            "market_scope": self.market_scope,
            "industry": self.industry,
            "company": self.company,
            "product": self.product,
            "metric": self.metric,
            "period": self.period,
            "unit": self.unit,
            "confidence": self.confidence,
            "verification": self.verification,
            "supports": list(self.supports),
            "maturity": self.maturity,
            "quality_flags": list(self.quality_flags),
            "notes": self.notes,
            "timeout_seconds": self.timeout_seconds,
        }


def validate_evidence_source(source: EvidenceSourceSpec) -> EvidenceSourceSpec:
    if not source.source_id:
        raise EvidenceSourceError("source_id is required")
    for field_name in ("title", "source_type", "source_name", "source_url", "topic"):
        if not getattr(source, field_name):
            raise EvidenceSourceError(f"{source.source_id}: {field_name} is required")
    if source.source_type not in SOURCE_TYPES:
        raise EvidenceSourceError(f"{source.source_id}: invalid source_type {source.source_type!r}")
    if source.confidence not in CONFIDENCE_VALUES:
        raise EvidenceSourceError(f"{source.source_id}: invalid confidence {source.confidence!r}")
    if source.maturity not in MATURITY_VALUES:
        raise EvidenceSourceError(f"{source.source_id}: invalid maturity {source.maturity!r}")
    if source.method.upper() not in {"GET", "POST"}:
        raise EvidenceSourceError(f"{source.source_id}: method must be GET or POST")
    if not source.claim_template and "claim" not in source.field_map:
        raise EvidenceSourceError(f"{source.source_id}: claim_template or field_map.claim is required")
    if not (source.published_at or source.published_at_path or "published_at" in source.field_map):
        raise EvidenceSourceError(f"{source.source_id}: published_at, published_at_path or field_map.published_at is required")
    if source.timeout_seconds <= 0:
        raise EvidenceSourceError(f"{source.source_id}: timeout_seconds must be positive")
    return source


class EvidenceSourceRegistry:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.sources_dir = self.data_dir / "evidence" / "sources"

    def list(self) -> list[EvidenceSourceSpec]:
        if not self.sources_dir.exists():
            return []
        sources: list[EvidenceSourceSpec] = []
        for path in sorted(self.sources_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            sources.append(validate_evidence_source(EvidenceSourceSpec.from_dict(payload)))
        return sources

    def require(self, source_id: str) -> EvidenceSourceSpec:
        for source in self.list():
            if source.source_id == source_id:
                return source
        raise EvidenceSourceError(f"evidence source not found: {source_id}")

    def add(self, source: EvidenceSourceSpec, *, overwrite: bool = False) -> Path:
        source = validate_evidence_source(source)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        path = self.sources_dir / f"{_safe_filename(source.source_id)}.json"
        if path.exists() and not overwrite:
            raise EvidenceSourceError(f"evidence source already exists: {path}")
        path.write_text(json.dumps(source.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path


class EvidenceSourceFetcher:
    def __init__(
        self,
        *,
        evidence_store: EvidenceStore,
        source_registry: EvidenceSourceRegistry,
        get_transport: HttpTransport = urllib_get_json,
        post_transport: HttpTransport = urllib_post_json,
        now: datetime | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.source_registry = source_registry
        self.get_transport = get_transport
        self.post_transport = post_transport
        self.now = now

    def fetch(self, source_id: str, *, params: dict[str, Any] | None = None, limit: int = 0) -> EvidenceIngestResult:
        records = self.build_records(source_id, params=params, limit=limit)
        return self.evidence_store.ingest(records)

    def build_records(self, source_id: str, *, params: dict[str, Any] | None = None, limit: int = 0) -> list[EvidenceRecord]:
        source = validate_evidence_source(self.source_registry.require(source_id))
        request_params = dict(source.params)
        request_params.update(params or {})
        transport = self.post_transport if source.method.upper() == "POST" else self.get_transport
        try:
            response = transport(source.source_url, request_params, source.headers, source.timeout_seconds)
        except SourceAdapterError:
            raise
        payload = response.json()
        rows = _extract_rows(payload, source.records_path)
        if limit and limit > 0:
            rows = rows[:limit]
        query_time = self._query_time()
        records = [
            _record_from_row(
                source,
                row=row,
                root=payload,
                response_url=response.url,
                row_number=index,
                query_time=query_time,
            )
            for index, row in enumerate(rows, start=1)
        ]
        return records

    def _query_time(self) -> str:
        current = self.now or datetime.now(ZoneInfo("Asia/Shanghai"))
        return current.isoformat(timespec="seconds")


def _record_from_row(
    source: EvidenceSourceSpec,
    *,
    row: Any,
    root: Any,
    response_url: str,
    row_number: int,
    query_time: str,
) -> EvidenceRecord:
    row_payload = row if isinstance(row, dict) else {"value": row}
    mapped = {field: _select(row_payload, path, root=root) for field, path in source.field_map.items()}
    template_values = _template_values(source, row_payload, mapped)
    claim = str(mapped.get("claim") or source.claim_template.format_map(_SafeMapping(template_values))).strip()
    source_url = str(mapped.get("source_url") or response_url or source.source_url)
    published_at = str(
        mapped.get("published_at")
        or (source.published_at_path and _select(row_payload, source.published_at_path, root=root))
        or source.published_at
    )
    return EvidenceRecord(
        claim=claim,
        topic=str(mapped.get("topic") or source.topic),
        source=EvidenceSourceRef(
            source_type=str(mapped.get("source_type") or source.source_type),
            source_name=str(mapped.get("source_name") or source.source_name),
            source_url=source_url,
            published_at=published_at,
            query_time=str(mapped.get("query_time") or query_time),
        ),
        confidence=str(mapped.get("confidence") or source.confidence),
        verification=str(mapped.get("verification") or source.verification),
        row_ref=f"evidence_source:{source.source_id}:row:{row_number}",
        market_scope=_optional_str(mapped.get("market_scope") or source.market_scope),
        industry=_optional_str(mapped.get("industry") or source.industry),
        company=_optional_str(mapped.get("company") or source.company),
        product=_optional_str(mapped.get("product") or source.product),
        metric=_optional_str(mapped.get("metric") or source.metric),
        value=mapped.get("value"),
        unit=_optional_str(mapped.get("unit") or source.unit),
        period=_optional_str(mapped.get("period") or source.period),
        supports=source.supports,
        maturity=str(mapped.get("maturity") or source.maturity),
        quality_flags=source.quality_flags,
    )


def _template_values(source: EvidenceSourceSpec, row: dict[str, Any], mapped: dict[str, Any]) -> dict[str, Any]:
    static_values = {
        "source_id": source.source_id,
        "source_name": source.source_name,
        "topic": source.topic,
        "market_scope": source.market_scope,
        "industry": source.industry,
        "company": source.company,
        "product": source.product,
        "metric": source.metric,
        "period": source.period,
        "unit": source.unit,
    }
    return dict(ChainMap(mapped, row, static_values))


def _extract_rows(payload: Any, records_path: str) -> list[Any]:
    selected = _select(payload, records_path, root=payload) if records_path else payload
    if selected is None:
        raise EvidenceSourceError(f"records_path not found: {records_path}")
    if isinstance(selected, list):
        return selected
    if isinstance(selected, dict):
        return [selected]
    return [{"value": selected}]


def _select(payload: Any, path: str, *, root: Any) -> Any:
    if not path:
        return None
    current = root if path == "$" else payload
    parts = path[2:].split(".") if path.startswith("$.") else path.split(".")
    for part in parts:
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _safe_filename(value: str) -> str:
    return value.replace(":", "_").replace("/", "_")


class _SafeMapping(dict[str, Any]):
    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(values)

    def __missing__(self, key: str) -> str:
        return ""
