from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import FoundationRegistry
from ..domains import default_registry
from ..evidence import EvidenceStore
from ..features import FeatureRegistry, FeatureStore
from ..relations import RelationStore
from ..storage import MartStore

STRONG_EXPOSURE_SOURCE_KINDS = {"mart", "evidence", "relations"}
EXTERNAL_SOURCE_TYPES = {
    "evidence",
    "company_filing",
    "company_ir",
    "exchange",
    "regulator",
    "gov_policy",
    "official",
    "official_platform",
    "association",
    "industry_association",
    "tender_platform",
    "price_index",
    "vendor",
    "media",
    "research_report",
    "web",
    "other",
}
AUDIT_FIELD_ALIASES = {
    "source_name": ("source_name", "source_title", "title"),
    "source_url": ("source_url", "url", "source_api", "interface"),
    "published_at": ("published_at", "publish_date", "published_date", "date"),
    "query_time": ("query_time", "fetched_at", "accessed_at"),
}
HIGH_PRIORITY_VALUES = {"core", "high", "primary", "重点", "优先"}
WEAK_VERIFICATIONS = {"unverified", "stale"}


def evaluate_quality_gates(
    *,
    data_dir: Path | str | None,
    as_of: str,
    mart_refs: tuple[str, ...],
    feature_refs: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    relation_ids: tuple[str, ...],
    validated_output: dict[str, Any],
    registry: FoundationRegistry | None = None,
    feature_registry: FeatureRegistry | None = None,
) -> dict[str, Any]:
    registry = registry or default_registry()
    feature_registry = feature_registry or FeatureRegistry.builtin()
    data_refs = validate_data_refs(
        data_dir=data_dir,
        mart_refs=mart_refs,
        feature_refs=feature_refs,
        registry=registry,
        feature_registry=feature_registry,
    )
    source_refs = validate_source_refs(data_dir=data_dir, evidence_ids=evidence_ids, relation_ids=relation_ids)
    output = validated_output or {}
    gates = {
        "output_gate": _output_gate(as_of, output),
        "freshness_gate": _freshness_gate(data_refs, as_of),
        "data_refs_gate": _data_refs_gate(data_refs),
        "source_refs_gate": _source_refs_gate(source_refs),
        "gap_gate": _gap_gate(data_refs, output),
        "source_gate": _source_gate(
            output,
            data_refs=data_refs,
            source_refs=source_refs,
            registry=registry,
        ),
        "source_audit_gate": _source_audit_gate(output, source_refs=source_refs),
        "confidence_gate": _confidence_gate(output),
    }
    status = "ok"
    reason = ""
    if any(gate["status"] == "blocked" for gate in gates.values()):
        status = "blocked"
        reason = "one or more run quality gates blocked the record"
    elif any(gate["status"] in {"warning", "degraded", "not_evaluated"} for gate in gates.values()):
        status = "degraded"
        reason = "one or more run quality gates require review"
    return {
        "schema": "rdf.run_quality.v1",
        "status": status,
        "reason": reason,
        "checks": {
            "has_data_refs": bool(mart_refs or feature_refs or evidence_ids or relation_ids),
            "validated_output_provided": bool(validated_output),
        },
        "data_refs": data_refs,
        "source_refs": source_refs,
        "gates": gates,
    }


def validate_data_refs(
    *,
    data_dir: Path | str | None,
    mart_refs: tuple[str, ...],
    feature_refs: tuple[str, ...],
    registry: FoundationRegistry,
    feature_registry: FeatureRegistry,
) -> dict[str, Any]:
    mart_store = MartStore(data_dir, registry)
    feature_store = FeatureStore(data_dir)
    marts = [_mart_ref_status(mart_store, registry, raw) for raw in mart_refs]
    features = [_feature_ref_status(feature_store, feature_registry, raw) for raw in feature_refs]
    blocked = [ref for ref in (*marts, *features) if ref["status"] in {"missing", "invalid", "unregistered", "read_error"}]
    degraded = [ref for ref in (*marts, *features) if ref["status"] == "degraded"]
    status = "blocked" if blocked else "degraded" if degraded else "ok"
    return {
        "schema": "rdf.run_data_refs.v1",
        "status": status,
        "marts": marts,
        "features": features,
    }


def validate_source_refs(
    *,
    data_dir: Path | str | None,
    evidence_ids: tuple[str, ...],
    relation_ids: tuple[str, ...],
) -> dict[str, Any]:
    evidence_by_id = {record.evidence_id: record for record in EvidenceStore(data_dir).read_records() if record.evidence_id}
    relation_by_id = {record.relation_id: record for record in RelationStore(data_dir).read_records() if record.relation_id}
    evidence = [
        {
            "id": evidence_id,
            "status": "ok" if evidence_id in evidence_by_id else "missing",
            "source": evidence_by_id[evidence_id].source.to_dict() if evidence_id in evidence_by_id else {},
        }
        for evidence_id in evidence_ids
    ]
    relations = [
        {
            "id": relation_id,
            "status": "ok" if relation_id in relation_by_id else "missing",
            "source": relation_by_id[relation_id].source.to_dict() if relation_id in relation_by_id else {},
        }
        for relation_id in relation_ids
    ]
    status = "blocked" if any(item["status"] != "ok" for item in (*evidence, *relations)) else "ok"
    return {
        "schema": "rdf.run_source_refs.v1",
        "status": status,
        "evidence": evidence,
        "relations": relations,
        "evidence_ids": list(evidence_ids),
        "relation_ids": list(relation_ids),
    }


def _mart_ref_status(store: MartStore, registry: FoundationRegistry, raw: str) -> dict[str, Any]:
    parsed = parse_ref(raw)
    dataset_id = parsed["id"]
    if not dataset_id:
        return {"raw": raw, "status": "invalid", "reason": "missing dataset id", "partition": {}}
    try:
        contract = registry.require_dataset(dataset_id)
    except Exception as error:
        return {"raw": raw, "name": dataset_id, "status": "unregistered", "reason": str(error), "partition": parsed["partition"]}
    try:
        meta = store.read_meta(dataset_id, parsed["partition"])
    except Exception as error:
        return {
            "raw": raw,
            "name": dataset_id,
            "domain": contract.domain,
            "status": "missing",
            "reason": str(error),
            "partition": parsed["partition"],
        }
    quality_status = str((meta.get("quality") or {}).get("status") or "")
    status = "ok" if quality_status == "ok" else "degraded" if quality_status else "ok"
    return {
        "raw": raw,
        "name": dataset_id,
        "domain": contract.domain,
        "status": status,
        "partition": dict(meta.get("partition") or parsed["partition"]),
        "rows": int(meta.get("rows", 0)),
        "path": str(store.partition_path(dataset_id, parsed["partition"])),
        "quality_status": quality_status,
        "usage": contract.usage.to_dict(),
        "temporal": {
            "temporal_mode": contract.temporal.temporal_mode,
            "finality": contract.temporal.finality,
            "available_after": contract.temporal.available_after,
            "as_of_policy": contract.temporal.as_of_policy,
        },
    }


def _feature_ref_status(store: FeatureStore, feature_registry: FeatureRegistry, raw: str) -> dict[str, Any]:
    parsed = parse_ref(raw)
    feature_id = parsed["id"]
    if not feature_id:
        return {"raw": raw, "status": "invalid", "reason": "missing feature id", "partition": {}}
    try:
        spec = feature_registry.require(feature_id)
    except Exception as error:
        return {"raw": raw, "name": feature_id, "status": "unregistered", "reason": str(error), "partition": parsed["partition"]}
    try:
        as_of = str(parsed["partition"]["as_of"])
        window = int(parsed["partition"]["window"])
        meta = store.load_meta(feature_id, domain=spec.domain, as_of=as_of, window=window)
    except Exception as error:
        return {
            "raw": raw,
            "name": feature_id,
            "domain": spec.domain,
            "status": "missing",
            "reason": str(error),
            "partition": parsed["partition"],
        }
    quality_status = str((meta.quality or {}).get("status") or "")
    status = "ok" if quality_status == "ok" else "degraded" if quality_status else "ok"
    return {
        "raw": raw,
        "name": feature_id,
        "domain": spec.domain,
        "status": status,
        "partition": dict(meta.partition),
        "rows": int(meta.rows),
        "path": str(store.partition_path(spec, as_of=as_of, window=window)),
        "quality_status": quality_status,
        "usage": spec.usage.to_dict(),
    }


def parse_ref(raw: str) -> dict[str, Any]:
    name, _, tail = raw.partition(":")
    partition: dict[str, str] = {}
    if tail:
        for item in tail.split(","):
            if not item:
                continue
            if "=" not in item:
                return {"id": name, "partition": partition, "invalid": item}
            key, value = item.split("=", 1)
            partition[key] = value
    return {"id": name, "partition": partition}


def _output_gate(as_of: str, output: dict[str, Any]) -> dict[str, Any]:
    if not output:
        return _gate("not_evaluated", "validated output not provided")
    output_as_of = output.get("as_of")
    if output_as_of is not None and str(output_as_of) != as_of:
        return _gate("blocked", f"as_of mismatch: expected {as_of}, got {output_as_of}")
    return _gate("passed", "")


def _freshness_gate(data_refs: dict[str, Any], as_of: str) -> dict[str, Any]:
    stale = []
    for ref in [*data_refs.get("marts", []), *data_refs.get("features", [])]:
        partition = dict(ref.get("partition") or {})
        ref_date = partition.get("trade_date") or partition.get("as_of")
        if ref_date and str(ref_date) != str(as_of):
            stale.append(ref.get("raw") or ref.get("name"))
    if stale:
        return _gate("blocked", f"data ref date mismatch: {stale}", {"refs": stale})
    return _gate("passed", "")


def _data_refs_gate(data_refs: dict[str, Any]) -> dict[str, Any]:
    refs = [*data_refs.get("marts", []), *data_refs.get("features", [])]
    blocked = [ref for ref in refs if ref.get("status") in {"missing", "invalid", "unregistered", "read_error"}]
    if blocked:
        return _gate("blocked", "data refs not usable", {"items": blocked})
    degraded = [ref for ref in refs if ref.get("status") == "degraded"]
    if degraded:
        return _gate("warning", "data refs degraded", {"items": degraded})
    return _gate("passed", "")


def _source_refs_gate(source_refs: dict[str, Any]) -> dict[str, Any]:
    missing = [item for item in [*source_refs.get("evidence", []), *source_refs.get("relations", [])] if item["status"] != "ok"]
    if missing:
        return _gate("blocked", "evidence or relation refs not found in local stores", {"items": missing})
    return _gate("passed", "")


def _gap_gate(data_refs: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    gaps = _items(output, "data_gaps")
    blocking = [gap for gap in gaps if gap.get("impact") == "block"]
    degraded = [gap for gap in gaps if gap.get("impact") == "degrade"]
    if blocking:
        return _gate("blocked", "validated output contains blocking data gaps", {"gaps": blocking})
    if not data_refs.get("marts") and not data_refs.get("features"):
        return _gate("warning", "no mart or feature refs recorded")
    if degraded:
        return _gate("degraded", "validated output contains degrading data gaps", {"gaps": degraded})
    return _gate("passed", "")


def _source_gate(
    output: dict[str, Any],
    *,
    data_refs: dict[str, Any],
    source_refs: dict[str, Any],
    registry: FoundationRegistry,
) -> dict[str, Any]:
    unsupported = _unsupported_company_exposure(output, data_refs=data_refs, source_refs=source_refs, registry=registry)
    if unsupported:
        return _gate(
            "blocked",
            "company exposure claims require mart, evidence, or traceable relations support",
            {"items": unsupported},
        )
    missing = _missing_output_refs(output, source_refs=source_refs)
    if missing:
        return _gate("blocked", "validated output references evidence or relations not recorded in this run", {"items": missing})
    return _gate("passed", "")


def _source_audit_gate(output: dict[str, Any], *, source_refs: dict[str, Any]) -> dict[str, Any]:
    if not output:
        return _gate("not_evaluated", "validated output not provided")
    known_evidence = set(source_refs.get("evidence_ids", []))
    known_relations = set(source_refs.get("relation_ids", []))
    missing = []
    for ref in _walk_dicts(output):
        if _has_recorded_artifact_ref(ref, evidence_ids=known_evidence, relation_ids=known_relations):
            continue
        if _requires_audit(ref):
            fields = _missing_audit_fields(ref)
            if fields:
                missing.append(
                    {
                        "source": _source_ref_label(ref),
                        "source_kind": ref.get("source_kind") or ref.get("source_type"),
                        "missing_fields": fields,
                    }
                )
    if missing:
        return _gate("blocked", "external source refs require source name, URL, publish date, and fetch time", {"items": missing})
    return _gate("passed", "")


def _confidence_gate(output: dict[str, Any]) -> dict[str, Any]:
    if not output:
        return _gate("not_evaluated", "validated output not provided")
    weak_priority = [
        _candidate_label(candidate)
        for candidate in _items(output, "candidate_pool")
        if _is_high_priority(candidate) and candidate.get("evidence_strength") == "weak"
    ]
    if weak_priority:
        return _gate("blocked", "high-priority candidates cannot have weak evidence", {"candidates": weak_priority})
    warnings: dict[str, Any] = {}
    weak_high_evidence = [
        item.get("evidence_id") or item.get("source_id") or item.get("claim") or item.get("topic")
        for item in _items(output, "evidence_matrix")
        if item.get("confidence") == "high" and item.get("verification") in WEAK_VERIFICATIONS
    ]
    if weak_high_evidence:
        warnings["high_confidence_evidence_with_weak_verification"] = weak_high_evidence
    if output.get("confidence") == "high" and not _items(output, "evidence_matrix"):
        warnings["high_confidence_without_evidence_matrix"] = True
    if warnings:
        return _gate("warning", "validated output confidence requires review", warnings)
    return _gate("passed", "")


def _unsupported_company_exposure(
    output: dict[str, Any],
    *,
    data_refs: dict[str, Any],
    source_refs: dict[str, Any],
    registry: FoundationRegistry,
) -> list[dict[str, Any]]:
    if not output:
        return []
    mappings = _items(output, "company_mapping")
    mapping_by_code = {str(item.get("ts_code") or ""): item for item in mappings if item.get("ts_code")}
    unsupported = []
    for mapping in mappings:
        exposure_level = mapping.get("exposure_level")
        if exposure_level in {"core", "direct"} and not _has_strong_exposure(
            mapping,
            data_refs=data_refs,
            source_refs=source_refs,
            registry=registry,
        ):
            unsupported.append(
                {
                    "scope": "company_mapping",
                    "ts_code": mapping.get("ts_code"),
                    "name": mapping.get("name"),
                    "exposure_level": exposure_level,
                    "source_kinds": _source_kinds(mapping.get("exposure_evidence")),
                }
            )
    for candidate in _items(output, "candidate_pool"):
        mapping = mapping_by_code.get(str(candidate.get("ts_code") or ""))
        has_claim = candidate.get("exposure_level") in {"core", "direct"} or _is_high_priority(candidate)
        if has_claim and (
            not mapping
            or not _has_strong_exposure(
                mapping,
                data_refs=data_refs,
                source_refs=source_refs,
                registry=registry,
            )
        ):
            unsupported.append(
                {
                    "scope": "candidate_pool",
                    "ts_code": candidate.get("ts_code"),
                    "name": candidate.get("name"),
                    "priority": candidate.get("priority") or candidate.get("research_priority") or candidate.get("tier"),
                    "source_kinds": _source_kinds((mapping or {}).get("exposure_evidence")),
                }
            )
    return unsupported


def _has_strong_exposure(
    mapping: dict[str, Any],
    *,
    data_refs: dict[str, Any],
    source_refs: dict[str, Any],
    registry: FoundationRegistry,
) -> bool:
    refs = _list_of_dicts(mapping.get("exposure_evidence"))
    return any(_is_strong_exposure_ref(ref, data_refs=data_refs, source_refs=source_refs, registry=registry) for ref in refs)


def _is_strong_exposure_ref(
    ref: dict[str, Any],
    *,
    data_refs: dict[str, Any],
    source_refs: dict[str, Any],
    registry: FoundationRegistry,
) -> bool:
    source_kind = str(ref.get("source_kind") or "").lower()
    if source_kind not in STRONG_EXPOSURE_SOURCE_KINDS:
        return False
    if source_kind == "evidence":
        evidence_id = str(ref.get("evidence_id") or ref.get("source_id") or "").strip()
        return evidence_id in set(source_refs.get("evidence_ids", []))
    if source_kind == "relations":
        relation_id = str(ref.get("relation_id") or ref.get("source_id") or "").strip()
        return relation_id in set(source_refs.get("relation_ids", []))
    if source_kind == "mart":
        source_id = str(ref.get("source_id") or "").strip()
        if source_id and source_id not in {item.get("raw") for item in data_refs.get("marts", [])}:
            return False
        dataset_id = parse_ref(source_id).get("id") if source_id else str(ref.get("dataset_id") or "")
        try:
            return registry.require_dataset(dataset_id).permits("company_business_exposure")
        except Exception:
            return False
    return False


def _missing_output_refs(output: dict[str, Any], *, source_refs: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_ids = set(source_refs.get("evidence_ids", []))
    relation_ids = set(source_refs.get("relation_ids", []))
    missing = []
    seen: set[tuple[str, str, str]] = set()
    for ref in _walk_dicts(output):
        source_kind = str(ref.get("source_kind") or "").lower()
        if source_kind == "evidence":
            evidence_id = str(ref.get("evidence_id") or ref.get("source_id") or "").strip()
            if not evidence_id:
                _append_missing(missing, seen, "evidence", _source_ref_label(ref), "evidence reference requires evidence_id or source_id")
            elif evidence_id not in evidence_ids:
                _append_missing(missing, seen, "evidence", _source_ref_label(ref), f"evidence id not recorded in run: {evidence_id}")
        elif source_kind == "relations":
            relation_id = str(ref.get("relation_id") or ref.get("source_id") or "").strip()
            if not relation_id:
                _append_missing(missing, seen, "relations", _source_ref_label(ref), "relations reference requires relation_id or source_id")
            elif relation_id not in relation_ids:
                _append_missing(missing, seen, "relations", _source_ref_label(ref), f"relation id not recorded in run: {relation_id}")
    return missing


def _append_missing(output: list[dict[str, Any]], seen: set[tuple[str, str, str]], source_kind: str, source: str, reason: str) -> None:
    key = (source_kind, source, reason)
    if key in seen:
        return
    seen.add(key)
    output.append({"source_kind": source_kind, "source": source, "reason": reason})


def _has_recorded_artifact_ref(ref: dict[str, Any], *, evidence_ids: set[str], relation_ids: set[str]) -> bool:
    source_kind = str(ref.get("source_kind") or "").lower()
    if source_kind == "evidence":
        return str(ref.get("evidence_id") or ref.get("source_id") or "") in evidence_ids
    if source_kind == "relations":
        return str(ref.get("relation_id") or ref.get("source_id") or "") in relation_ids
    return False


def _requires_audit(ref: dict[str, Any]) -> bool:
    source_kind = str(ref.get("source_kind") or "").lower()
    source_type = str(ref.get("source_type") or "").lower()
    return source_type in EXTERNAL_SOURCE_TYPES or source_kind in (EXTERNAL_SOURCE_TYPES - {"evidence"})


def _missing_audit_fields(ref: dict[str, Any]) -> list[str]:
    missing = []
    for field_name, aliases in AUDIT_FIELD_ALIASES.items():
        if not any(str(ref.get(alias) or "").strip() for alias in aliases):
            missing.append(field_name)
    return missing


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(_walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_dicts(child))
    return found


def _items(output: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return _list_of_dicts(output.get(key))


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _source_kinds(value: Any) -> list[str]:
    return sorted({str(item.get("source_kind") or "") for item in _list_of_dicts(value) if item.get("source_kind")})


def _source_ref_label(ref: dict[str, Any]) -> str:
    return str(ref.get("source_id") or ref.get("evidence_id") or ref.get("relation_id") or ref.get("claim") or ref.get("title") or "<unknown>")


def _candidate_label(candidate: dict[str, Any]) -> str:
    return str(candidate.get("ts_code") or candidate.get("name") or "<unknown>")


def _is_high_priority(candidate: dict[str, Any]) -> bool:
    values = {
        str(candidate.get("priority") or "").lower(),
        str(candidate.get("research_priority") or "").lower(),
        str(candidate.get("tier") or "").lower(),
    }
    return bool(values & HIGH_PRIORITY_VALUES)


def _gate(status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": status, "message": message, "details": details or {}}
