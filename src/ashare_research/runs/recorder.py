from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..capabilities import CapabilityRegistry
from ..evidence import EvidenceStore
from ..knowledge import KnowledgeStore
from ..paths import default_data_dir, default_runs_dir
from ..protocols import ProtocolRegistry, ProtocolSpec
from ..reports import render_trace_report
from ..schemas import AShareResearchError
from .manifest import RunArtifact, RunManifest
from .quality_gates import evaluate_quality_gates


class RunError(AShareResearchError):
    """Raised when a run cannot be recorded or replayed."""


class RunRecorder:
    def __init__(self, data_dir: Path | str | None = None, runs_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.runs_dir = Path(runs_dir) if runs_dir is not None else default_runs_dir()

    def record(
        self,
        *,
        question: str,
        as_of: str,
        protocol_id: str | None = None,
        ad_hoc_protocol: dict[str, Any] | None = None,
        capability_ids: list[str] | None = None,
        context_pack_paths: list[Path | str] | None = None,
        evidence_path: Path | str | None = None,
        knowledge_path: Path | str | None = None,
        model_output: str | None = None,
        validated_output: dict[str, Any] | None = None,
        agent_reasoning: dict[str, Any] | None = None,
        report: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        created_at = _now_iso()
        protocol = self._load_protocol(protocol_id, ad_hoc_protocol, question=question)
        run_name = run_id or f"{_timestamp_for_id(created_at)}_{_slug(protocol.protocol_id)}"
        run_dir = self.runs_dir / run_name
        run_dir.mkdir(parents=True, exist_ok=False)

        question_artifact = self._write_text(run_dir / "question.md", question, kind="question")
        protocol_artifact = self._write_json(run_dir / "protocol.json", protocol.to_dict(), kind="protocol")
        capability_artifacts = self._write_capabilities(run_dir, capability_ids or [])
        context_artifacts, context_payloads = self._copy_context_packs(run_dir, context_pack_paths or [])
        evidence_artifact = self._copy_or_create_evidence(run_dir, evidence_path)
        knowledge_artifact = self._copy_or_create_knowledge(run_dir, knowledge_path)
        raw_output_artifact = self._write_text(run_dir / "model_output.raw.md", model_output or "", kind="model_output_raw")
        validated_payload = validated_output or {"schema": "ashare.model_output.validated.v1", "status": "not_provided"}
        validated_artifact = self._write_json(run_dir / "model_output.validated.json", validated_payload, kind="model_output_validated")
        reasoning_payload = agent_reasoning or _empty_agent_reasoning()
        reasoning_artifact = self._write_json(run_dir / "agent_reasoning.json", reasoning_payload, kind="agent_reasoning")
        quality_payload = evaluate_quality_gates(
            protocol=protocol,
            context_packs=context_payloads,
            as_of=as_of,
            has_validated_output=validated_output is not None,
        )
        quality_artifact = self._write_json(run_dir / "quality_gates.json", quality_payload, kind="quality_gates")
        report_text = report or render_trace_report(
            run_id=run_name,
            question=question,
            as_of=as_of,
            protocol=protocol,
            capability_artifacts=capability_artifacts,
            context_artifacts=context_artifacts,
            evidence_artifact=evidence_artifact,
            knowledge_artifact=knowledge_artifact,
            quality_gates=quality_payload,
        )
        report_artifact = self._write_text(run_dir / "report.md", report_text, kind="report")

        manifest = RunManifest(
            run_id=run_name,
            created_at=created_at,
            as_of=as_of,
            protocol_id=protocol.protocol_id,
            protocol_version=protocol.version,
            question=question_artifact,
            protocol=protocol_artifact,
            capabilities=tuple(capability_artifacts),
            context_packs=tuple(context_artifacts),
            evidence=evidence_artifact,
            knowledge=knowledge_artifact,
            model={"provider": "codex", "name": "codex", "temperature": None},
            agent_reasoning=reasoning_payload,
            quality_gates=quality_payload,
            outputs={
                "raw_model_output": raw_output_artifact.to_dict(),
                "validated_json": validated_artifact.to_dict(),
                "agent_reasoning": reasoning_artifact.to_dict(),
                "quality_gates": quality_artifact.to_dict(),
                "report": report_artifact.to_dict(),
            },
        )
        manifest_artifact = self._write_json(run_dir / "run.json", manifest.to_dict(), kind="run_manifest")
        return manifest.to_dict() | {"path": str(run_dir), "manifest_sha256": manifest_artifact.sha256}

    def list_runs(self) -> list[dict[str, Any]]:
        if not self.runs_dir.exists():
            return []
        rows: list[dict[str, Any]] = []
        for run_dir in sorted(path for path in self.runs_dir.iterdir() if path.is_dir()):
            manifest_path = run_dir / "run.json"
            if not manifest_path.exists():
                continue
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "run_id": payload.get("run_id", run_dir.name),
                    "as_of": payload.get("as_of"),
                    "protocol_id": payload.get("protocol_id"),
                    "capabilities": len(payload.get("capabilities") or []),
                    "quality_status": payload.get("quality_gates", {}).get("status"),
                    "path": str(run_dir),
                }
            )
        return rows

    def _load_protocol(self, protocol_id: str | None, ad_hoc_protocol: dict[str, Any] | None, *, question: str) -> ProtocolSpec:
        if ad_hoc_protocol is not None:
            return ProtocolSpec.from_dict(ad_hoc_protocol)
        if not protocol_id:
            return _user_directed_protocol(question)
        return ProtocolRegistry.builtin().require(protocol_id)

    def _write_capabilities(self, run_dir: Path, capability_ids: list[str]) -> list[RunArtifact]:
        artifacts: list[RunArtifact] = []
        registry = CapabilityRegistry.builtin()
        for index, capability_id in enumerate(capability_ids, start=1):
            spec = registry.require(capability_id)
            target = run_dir / ("capability.json" if len(capability_ids) == 1 else f"capability_{index}.json")
            artifacts.append(self._write_json(target, spec.to_dict(), kind="capability"))
        return artifacts

    def _copy_context_packs(self, run_dir: Path, paths: list[Path | str]) -> tuple[list[RunArtifact], list[dict[str, Any]]]:
        artifacts: list[RunArtifact] = []
        payloads: list[dict[str, Any]] = []
        for index, raw_path in enumerate(paths, start=1):
            source = Path(raw_path)
            if not source.exists():
                raise RunError(f"context pack not found: {source}")
            target = run_dir / ("context_pack.json" if len(paths) == 1 else f"context_pack_{index}.json")
            shutil.copyfile(source, target)
            artifacts.append(_artifact(target, "context_pack"))
            payloads.append(json.loads(target.read_text(encoding="utf-8")))
        return artifacts, payloads

    def _copy_or_create_evidence(self, run_dir: Path, evidence_path: Path | str | None) -> RunArtifact:
        target = run_dir / "evidence.jsonl"
        source = Path(evidence_path) if evidence_path else EvidenceStore(self.data_dir).records_path
        if source.exists():
            shutil.copyfile(source, target)
        else:
            target.write_text("", encoding="utf-8")
        return _artifact(target, "evidence")

    def _copy_or_create_knowledge(self, run_dir: Path, knowledge_path: Path | str | None) -> RunArtifact:
        target = run_dir / "knowledge_snapshot.json"
        if knowledge_path:
            source = Path(knowledge_path)
            if not source.exists():
                raise RunError(f"knowledge snapshot not found: {source}")
            shutil.copyfile(source, target)
        else:
            snapshot = KnowledgeStore(self.data_dir).snapshot(output_path=target)
            snapshot.pop("path", None)
            target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return _artifact(target, "knowledge")

    def _write_text(self, path: Path, text: str, *, kind: str) -> RunArtifact:
        path.write_text(text, encoding="utf-8")
        return _artifact(path, kind)

    def _write_json(self, path: Path, payload: dict[str, Any], *, kind: str) -> RunArtifact:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return _artifact(path, kind)


def _artifact(path: Path, kind: str) -> RunArtifact:
    return RunArtifact(path=path.name, sha256=_file_sha256(path), kind=kind)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    return slug.strip("_") or "run"


def _timestamp_for_id(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace("+", "_")


def _user_directed_protocol(question: str) -> ProtocolSpec:
    return ProtocolSpec(
        protocol_id="user_directed.v1",
        title="用户当次指令",
        version="v1",
        status="ad_hoc_protocol",
        description="未指定注册协议时，分析约束以用户当次问题和对话中给出的框架为准。",
        required_contexts=("user_selected_context",),
        optional_inputs=("market_context", "industry_context", "stock_context", "evidence_records", "knowledge_snapshot"),
        required_sections=("user_requested_output",),
        forbidden=(
            "Do not use reports/runs as factual source",
            "Do not state unsupported certainty when evidence or mart data is missing",
        ),
        output_schema=None,
        gap_policy={"missing_market_data": "warn", "missing_external_evidence": "warn", "missing_knowledge": "warn"},
        quality_gates=("freshness_gate", "gap_gate", "source_gate", "confidence_gate"),
    )


def _empty_agent_reasoning() -> dict[str, Any]:
    return {
        "schema": "ashare.agent_reasoning.v1",
        "status": "not_provided",
        "facts_used": [],
        "inferences": [],
        "hypotheses": [],
        "unverified_claims": [],
        "validation_steps": [],
        "open_questions": [],
    }


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
