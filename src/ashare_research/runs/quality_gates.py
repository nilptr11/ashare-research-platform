from __future__ import annotations

from typing import Any

from ..protocols import ProtocolSpec


def evaluate_quality_gates(
    *,
    protocol: ProtocolSpec,
    context_packs: list[dict[str, Any]],
    as_of: str,
    has_validated_output: bool,
) -> dict[str, Any]:
    gates = {
        "schema_gate": _gate("passed" if has_validated_output else "not_evaluated", "validated output not provided"),
        "freshness_gate": _freshness_gate(context_packs, as_of),
        "gap_gate": _gap_gate(protocol, context_packs),
        "source_gate": _source_gate(context_packs),
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


def _freshness_gate(context_packs: list[dict[str, Any]], as_of: str) -> dict[str, Any]:
    stale = [pack.get("pack_id") for pack in context_packs if str(pack.get("as_of")) != as_of]
    if stale:
        return _gate("blocked", f"context as_of mismatch: {stale}")
    return _gate("passed", "")


def _gap_gate(protocol: ProtocolSpec, context_packs: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = [gap for pack in context_packs for gap in pack.get("data_gaps", [])]
    mart_gaps = [gap for gap in gaps if gap.get("kind") == "mart"]
    evidence_gaps = [gap for gap in gaps if gap.get("kind") == "evidence"]
    if mart_gaps and protocol.gap_policy.get("missing_market_data") == "block":
        return _gate("blocked", "critical mart data gap", {"gaps": mart_gaps})
    if evidence_gaps and protocol.gap_policy.get("missing_external_evidence") == "degrade_with_gap":
        return _gate("degraded", "external evidence missing; conclusions must be conditional", {"gaps": evidence_gaps})
    if gaps:
        return _gate("warning", "non-critical data gaps present", {"gaps": gaps})
    return _gate("passed", "")


def _source_gate(context_packs: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [pack.get("pack_id") for pack in context_packs if not pack.get("source_policy_summary")]
    if missing:
        return _gate("warning", f"source policy summary missing: {missing}")
    return _gate("passed", "")


def _gate(status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "details": details or {},
    }
