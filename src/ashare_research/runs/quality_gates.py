from __future__ import annotations

from typing import Any

from ..protocols import ProtocolSpec


def evaluate_quality_gates(
    *,
    protocol: ProtocolSpec,
    data_refs: dict[str, Any],
    as_of: str,
    has_validated_output: bool,
    evidence_artifact: dict[str, Any] | None = None,
    knowledge_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gates = {
        "schema_gate": _gate("passed" if has_validated_output else "not_evaluated", "validated output not provided"),
        "freshness_gate": _freshness_gate(data_refs, as_of),
        "data_refs_gate": _data_refs_gate(data_refs),
        "gap_gate": _gap_gate(protocol, data_refs),
        "source_gate": _source_gate(evidence_artifact, knowledge_artifact),
        "confidence_gate": _gate("passed", ""),
    }
    status = "passed"
    if any(gate["status"] == "blocked" for gate in gates.values()):
        status = "blocked"
    elif any(gate["status"] in {"warning", "degraded", "not_evaluated"} for gate in gates.values()):
        status = "warning"
    return {
        "schema": "ashare.run_quality_gates.v1",
        "status": status,
        "gates": gates,
    }


def _freshness_gate(data_refs: dict[str, Any], as_of: str) -> dict[str, Any]:
    stale = []
    for ref in [*data_refs.get("marts", []), *data_refs.get("features", [])]:
        partition = dict(ref.get("partition") or {})
        ref_date = partition.get("trade_date") or partition.get("as_of") or partition.get("snapshot_date")
        if ref_date and str(ref_date) != as_of:
            stale.append(ref.get("raw") or ref.get("name"))
    if stale:
        return _gate("blocked", f"data ref date mismatch: {stale}")
    return _gate("passed", "")


def _gap_gate(protocol: ProtocolSpec, data_refs: dict[str, Any]) -> dict[str, Any]:
    marts = data_refs.get("marts", [])
    features = data_refs.get("features", [])
    if protocol.required_inputs and not marts and not features:
        return _gate("warning", "no mart or feature refs recorded; data coverage must be checked from run notes")
    return _gate("passed", "")


def _data_refs_gate(data_refs: dict[str, Any]) -> dict[str, Any]:
    refs = [*data_refs.get("marts", []), *data_refs.get("features", [])]
    blocked = [
        ref.get("raw") or ref.get("name")
        for ref in refs
        if ref.get("status") in {"missing", "invalid", "unregistered", "schema_mismatch", "empty", "read_error"}
    ]
    if blocked:
        return _gate("blocked", f"data refs not usable: {blocked}")
    degraded = [ref.get("raw") or ref.get("name") for ref in refs if ref.get("status") == "degraded"]
    if degraded:
        return _gate("warning", f"data refs degraded: {degraded}")
    return _gate("passed", "")


def _source_gate(evidence_artifact: dict[str, Any] | None, knowledge_artifact: dict[str, Any] | None) -> dict[str, Any]:
    missing = []
    if not evidence_artifact:
        missing.append("evidence")
    if not knowledge_artifact:
        missing.append("knowledge")
    if missing:
        return _gate("warning", f"source artifacts missing: {missing}")
    return _gate("passed", "")


def _gate(status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "details": details or {},
    }
