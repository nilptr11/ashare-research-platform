from __future__ import annotations

from typing import Any

from ...connectors import ConnectorRegistry
from ...schemas import ConnectorError
from ..store import EvidenceIngestResult, EvidenceStore
from .registry import EvidenceAdapterRegistry
from .schemas import EvidenceAdapterError, EvidenceAdapterSpec, validate_adapter_spec


class EvidenceAdapterRunner:
    def __init__(
        self,
        *,
        evidence_store: EvidenceStore,
        adapter_registry: EvidenceAdapterRegistry,
        connector_registry: ConnectorRegistry | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.adapter_registry = adapter_registry
        self.connector_registry = connector_registry or ConnectorRegistry.builtin()

    def run(self, adapter_id: str, *, params: dict[str, Any] | None = None) -> EvidenceIngestResult:
        spec = validate_adapter_spec(self.adapter_registry.require(adapter_id))
        if spec.status != "accepted":
            raise EvidenceAdapterError(f"{adapter_id}: only accepted adapters can run")
        request_params = dict(spec.params_template)
        request_params.update(params or {})
        connector = self.connector_registry.create(spec.connector)
        try:
            response = connector.fetch(spec.api_name, params=request_params)
        except ConnectorError:
            raise
        records = [_record_from_row(spec, row) for row in response.frame.to_dict(orient="records")]
        return self.evidence_store.ingest_evidence(records)


def _record_from_row(spec: EvidenceAdapterSpec, row: dict[str, Any]) -> dict[str, Any]:
    mapping = spec.field_mapping
    payload = {
        "claim": _claim(spec, row),
        "topic": spec.topic,
        "industry": spec.industry,
        "source_type": spec.source_type,
        "source_name": spec.source_name,
        "source_url": _mapped(mapping, row, "source_url"),
        "published_at": _mapped(mapping, row, "published_at"),
        "query_time": _mapped(mapping, row, "query_time"),
        "confidence": _mapped(mapping, row, "confidence", default="medium"),
        "verification": _mapped(mapping, row, "verification", default="adapter_mapped"),
        "metric": spec.metric,
        "value": _mapped(mapping, row, "value"),
        "unit": _mapped(mapping, row, "unit"),
        "period": _mapped(mapping, row, "period"),
        "frequency": spec.frequency,
        "maturity": "adapter",
        "adapter_id": spec.adapter_id,
    }
    for optional in ("product", "company", "region", "raw_excerpt"):
        if optional in mapping:
            payload[optional] = _mapped(mapping, row, optional)
    return payload


def _claim(spec: EvidenceAdapterSpec, row: dict[str, Any]) -> str:
    if spec.claim_template:
        return spec.claim_template.format_map(_SafeRow(row))
    return str(_mapped(spec.field_mapping, row, "claim"))


def _mapped(mapping: dict[str, str], row: dict[str, Any], field: str, default: Any = None) -> Any:
    column = mapping.get(field)
    if column is None:
        return default
    return row.get(column, default)


class _SafeRow(dict[str, Any]):
    def __init__(self, row: dict[str, Any]) -> None:
        super().__init__(row)

    def __missing__(self, key: str) -> str:
        return ""
