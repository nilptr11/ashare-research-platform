from __future__ import annotations

from typing import Any

from ..protocols import ProtocolSpec
from ..runs.manifest import RunArtifact


def render_trace_report(
    *,
    run_id: str,
    question: str,
    as_of: str,
    protocol: ProtocolSpec,
    capability_artifacts: list[RunArtifact],
    context_artifacts: list[RunArtifact],
    evidence_artifact: RunArtifact,
    knowledge_artifact: RunArtifact,
    quality_gates: dict[str, Any],
) -> str:
    lines = [
        f"# Run Trace Report: {run_id}",
        "",
        "This report is an output artifact, not a factual source.",
        "",
        "## Question",
        "",
        question.strip(),
        "",
        "## Protocol",
        "",
        f"- protocol_id: `{protocol.protocol_id}`",
        f"- version: `{protocol.version}`",
        f"- output_schema: `{protocol.output_schema}`",
        "",
        "## Inputs",
        "",
    ]
    lines.extend(_artifact_lines("capability", capability_artifacts))
    lines.extend(_artifact_lines("context_pack", context_artifacts))
    lines.extend(
        [
            f"- evidence: `{evidence_artifact.path}` sha256=`{evidence_artifact.sha256}`",
            f"- knowledge: `{knowledge_artifact.path}` sha256=`{knowledge_artifact.sha256}`",
            f"- as_of: `{as_of}`",
            "",
            "## Quality Gates",
            "",
            f"- status: `{quality_gates.get('status')}`",
        ]
    )
    for name, gate in quality_gates.get("gates", {}).items():
        message = gate.get("message") or ""
        lines.append(f"- {name}: `{gate.get('status')}` {message}".rstrip())
    lines.extend(["", "## Traceability", "", "- Market facts: mart/context pack inputs.", "- External industry claims: evidence artifact.", "- Slow variable mappings: knowledge artifact.", "- Model inference: model output artifacts."])
    return "\n".join(lines) + "\n"


def _artifact_lines(label: str, artifacts: list[RunArtifact]) -> list[str]:
    if not artifacts:
        return [f"- {label}: none"]
    return [f"- {label}: `{artifact.path}` sha256=`{artifact.sha256}`" for artifact in artifacts]
