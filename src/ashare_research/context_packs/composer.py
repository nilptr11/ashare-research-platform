from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..capabilities import CapabilityRegistry, CapabilitySpec
from ..datasets.catalog import DatasetCatalog
from ..evidence import EvidenceStore
from ..features import FeatureStore
from ..knowledge import KnowledgeStore
from ..marts.reader import MartReader
from ..paths import default_data_dir
from ..source_policy import source_policy_summary
from .builders import ContextPackBuilder
from .schemas import ContextInput, ContextPack


MAX_SUGGESTED_COMMANDS = 30
MAX_DRILLDOWNS = 20
MAX_PRECISION_NOTES = 12


class ContextComposer:
    version = "v1"

    def __init__(
        self,
        data_dir: Path | str | None = None,
        *,
        reader: MartReader | None = None,
        feature_store: FeatureStore | None = None,
        evidence_store: EvidenceStore | None = None,
        knowledge_store: KnowledgeStore | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.reader = reader or MartReader(self.data_dir, catalog=DatasetCatalog.builtin())
        self.builder = ContextPackBuilder(
            self.data_dir,
            reader=self.reader,
            feature_store=feature_store,
            evidence_store=evidence_store,
            knowledge_store=knowledge_store,
        )
        self.capability_registry = capability_registry or CapabilityRegistry.builtin()
        self.context_root = self.data_dir / "context_packs"

    def compose(
        self,
        *,
        capability_ids: list[str],
        as_of: str,
        industries: list[str] | None = None,
        stocks: list[str] | None = None,
        trade_days: int = 120,
        windows: list[int] | None = None,
        question: str | None = None,
        output_path: Path | str | None = None,
    ) -> dict[str, Any]:
        windows = windows or [5, 20, 60]
        industries = industries or []
        stocks = stocks or []
        specs = [self.capability_registry.require(capability_id) for capability_id in capability_ids]

        inputs = [_capability_input(spec) for spec in specs]
        data_gaps: list[dict[str, Any]] = []
        quality_flags: list[str] = []
        context_payloads: list[dict[str, Any]] = []

        required_contexts = _required_contexts(specs)
        if "market_structure" in required_contexts:
            context_payloads.append(self.builder.build_market_structure(as_of=as_of, trade_days=trade_days, windows=windows))
        if "industry" in required_contexts:
            if industries:
                for industry in industries:
                    context_payloads.append(self.builder.build_industry(industry=industry, as_of=as_of, windows=windows))
            else:
                _missing_anchor("industry", data_gaps, quality_flags)
        if "stock" in required_contexts:
            if stocks:
                for stock in stocks:
                    context_payloads.append(self.builder.build_stock(ts_code=stock, as_of=as_of))
            else:
                _missing_anchor("stock", data_gaps, quality_flags)

        for payload in context_payloads:
            data_gaps.extend(dict(item) for item in payload.get("data_gaps") or [])
            quality_flags.extend(str(item) for item in payload.get("quality_flags") or [])
            inputs.append(_context_pack_input(payload))

        pack_id = _pack_id(capability_ids=capability_ids, as_of=as_of, industries=industries, stocks=stocks)
        pack = ContextPack(
            schema="ashare.context_pack.composed.v1",
            pack_id=pack_id,
            pack_type="composed",
            generated_at=_now_iso(),
            as_of=as_of,
            window={
                "end_trade_date": as_of,
                "trade_days": trade_days,
                "feature_windows": list(windows),
                "capabilities": list(capability_ids),
                "industries": list(industries),
                "stocks": list(stocks),
            },
            inputs=tuple(inputs),
            sections={
                "question": question,
                "capabilities": [_capability_summary(spec) for spec in specs],
                "context_packs": [_context_pack_summary(payload) for payload in context_payloads],
                "suggested_commands": _suggested_commands(specs),
                "data_gap_summary": _gap_summary(data_gaps),
            },
            coverage={
                "capabilities": len(specs),
                "context_packs": len(context_payloads),
                "data_gaps": len(data_gaps),
                "required_contexts": list(required_contexts),
            },
            data_gaps=tuple(data_gaps),
            quality_flags=tuple(_dedupe(quality_flags)),
            agent_guidance=_composed_agent_guidance(specs, context_payloads, data_gaps),
            constraints={
                "latest_complete_trade_date": as_of,
                "intraday_available": False,
                "feature_scores_are_screening_only": True,
                "no_trade_execution": True,
            },
            source_policy_summary=source_policy_summary(),
            provenance={"builder": "ContextComposer", "version": self.version, "generated_by": "ashare_research"},
        )
        return self._write_pack(pack, output_path or self._default_path(pack_id))

    def _write_pack(self, pack: ContextPack, output_path: Path | str) -> dict[str, Any]:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = pack.to_dict()
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return payload | {"path": str(output)}

    def _default_path(self, pack_id: str) -> Path:
        return self.context_root / "composed" / f"key={_slug(pack_id)}" / "context.json"


def _required_contexts(specs: list[CapabilitySpec]) -> tuple[str, ...]:
    values: list[str] = []
    for spec in specs:
        for context_name in spec.inputs.get("context", ()):
            if context_name not in values:
                values.append(context_name)
    return tuple(values)


def _capability_input(spec: CapabilitySpec) -> ContextInput:
    payload = spec.to_dict()
    return ContextInput(
        kind="capability",
        name=spec.capability_id,
        status="ready",
        content_hash=_content_sha256(payload),
        details={"category": spec.category, "version": spec.version},
    )


def _capability_summary(spec: CapabilitySpec) -> dict[str, Any]:
    return {
        "capability_id": spec.capability_id,
        "name": spec.name,
        "category": spec.category,
        "description": spec.description,
        "questions": list(spec.questions),
        "inputs": {key: list(value) for key, value in spec.inputs.items()},
        "can_support": list(spec.can_support),
        "cannot_support": list(spec.cannot_support),
        "quality_requirements": list(spec.quality_requirements),
        "suggested_protocols": list(spec.suggested_protocols),
    }


def _context_pack_input(payload: dict[str, Any]) -> ContextInput:
    path = payload.get("path")
    return ContextInput(
        kind="context_pack",
        name=str(payload.get("pack_type")),
        status="ready" if not payload.get("quality_flags") and not payload.get("data_gaps") else "degraded",
        content_hash=_file_sha256(Path(str(path))) if path else _content_sha256(payload),
        path=str(path) if path else None,
        details={
            "pack_id": payload.get("pack_id"),
            "schema": payload.get("schema"),
            "as_of": payload.get("as_of"),
            "quality_flags": payload.get("quality_flags") or [],
            "data_gaps": len(payload.get("data_gaps") or []),
        },
    )


def _context_pack_summary(payload: dict[str, Any]) -> dict[str, Any]:
    guidance = dict(payload.get("agent_guidance") or {})
    return {
        "schema": payload.get("schema"),
        "pack_id": payload.get("pack_id"),
        "pack_type": payload.get("pack_type"),
        "as_of": payload.get("as_of"),
        "path": payload.get("path"),
        "coverage": payload.get("coverage", {}),
        "quality_flags": payload.get("quality_flags") or [],
        "data_gap_summary": _gap_summary(payload.get("data_gaps") or []),
        "drilldown_paths": _dedupe(guidance.get("suggested_drilldowns") or [])[:MAX_DRILLDOWNS],
        "precision_note_count": len(guidance.get("precision_notes") or []),
        "external_evidence_needed": _dedupe(guidance.get("external_evidence_needed") or []),
    }


def _suggested_commands(specs: list[CapabilitySpec]) -> list[str]:
    commands: list[str] = []
    for spec in specs:
        commands.extend(spec.commands)
    return _dedupe(commands)[:MAX_SUGGESTED_COMMANDS]


def _composed_agent_guidance(
    specs: list[CapabilitySpec],
    context_payloads: list[dict[str, Any]],
    data_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    supported = _dedupe(item for spec in specs for item in spec.can_support)
    unsupported = _dedupe(item for spec in specs for item in spec.cannot_support)
    suggested_drilldowns: list[dict[str, Any]] = []
    precision_notes: list[dict[str, Any]] = []
    external_needed: list[dict[str, Any]] = []

    for payload in context_payloads:
        guidance = dict(payload.get("agent_guidance") or {})
        suggested_drilldowns.extend(guidance.get("suggested_drilldowns") or [])
        precision_notes.extend(guidance.get("precision_notes") or [])
        external_needed.extend(guidance.get("external_evidence_needed") or [])

    for gap in data_gaps:
        if gap.get("kind") in {"evidence", "context_anchor"}:
            external_needed.append({"name": gap.get("name"), "reason": gap.get("message", "")})

    return {
        "schema": "ashare.agent_guidance.v1",
        "supported_claims": supported,
        "unsupported_claims": unsupported,
        "suggested_drilldowns": _dedupe(suggested_drilldowns)[:MAX_DRILLDOWNS],
        "external_evidence_needed": _dedupe(external_needed),
        "precision_notes": _dedupe(precision_notes)[:MAX_PRECISION_NOTES],
        "omitted_detail": {
            "suggested_drilldowns": max(0, len(_dedupe(suggested_drilldowns)) - MAX_DRILLDOWNS),
            "precision_notes": max(0, len(_dedupe(precision_notes)) - MAX_PRECISION_NOTES),
            "message": "Read nested context pack paths for full mart, feature, evidence, and knowledge details.",
        },
        "reasoning_constraints": [
            "Choose the minimum necessary data path from the listed capabilities.",
            "Use nested context packs as convenience snapshots, not a fixed workflow.",
            "Treat feature scores as screening signals, not conclusions.",
            "Degrade claims when anchors, evidence, knowledge, or mart partitions are missing.",
            "Do not output trade execution instructions.",
        ],
    }


def _missing_anchor(anchor: str, data_gaps: list[dict[str, Any]], quality_flags: list[str]) -> None:
    data_gaps.append(
        {
            "kind": "context_anchor",
            "name": anchor,
            "status": "missing",
            "message": f"{anchor} context requested by capability specs but no {anchor} argument was provided",
        }
    )
    quality_flags.append(f"missing_context_anchor:{anchor}")


def _gap_summary(gaps: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    examples: list[dict[str, Any]] = []
    for gap in gaps:
        kind = str(gap.get("kind", "unknown"))
        status = str(gap.get("status", "unknown"))
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        if len(examples) < 8:
            examples.append(
                {
                    "kind": gap.get("kind"),
                    "name": gap.get("name"),
                    "status": gap.get("status"),
                    "message": gap.get("message"),
                }
            )
    return {
        "count": len(gaps),
        "by_kind": by_kind,
        "by_status": by_status,
        "examples": examples,
    }


def _pack_id(*, capability_ids: list[str], as_of: str, industries: list[str], stocks: list[str]) -> str:
    key_parts = list(capability_ids) + [f"industry={item}" for item in industries] + [f"stock={item}" for item in stocks]
    key = ",".join(key_parts) if key_parts else "empty"
    return f"composed:{_slug(key)}:{as_of}:v1"


def _content_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dedupe(values) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    return slug.strip("_") or "unknown"


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
