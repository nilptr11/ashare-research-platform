from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourcePolicyRule:
    rule_id: str
    statement: str
    severity: str = "required"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "statement": self.statement,
            "severity": self.severity,
        }


SOURCE_POLICY_RULES = (
    SourcePolicyRule(
        rule_id="mart_over_external",
        statement="mart facts override external evidence for market, finance, and filing facts",
    ),
    SourcePolicyRule(
        rule_id="evidence_for_external_industry_claims",
        statement="evidence is required for external industry claims",
    ),
    SourcePolicyRule(
        rule_id="knowledge_traceability",
        statement="knowledge records must trace to evidence_id or source_url",
    ),
    SourcePolicyRule(
        rule_id="runs_not_factual_sources",
        statement="reports and runs are not factual sources",
    ),
)


def source_policy_summary() -> dict[str, Any]:
    return {
        "schema": "ashare.source_policy_summary.v1",
        "rules": [rule.to_dict() for rule in SOURCE_POLICY_RULES],
    }
