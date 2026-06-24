from __future__ import annotations

from .schemas import KnowledgeProposal


def proposal_rows(proposals: list[KnowledgeProposal]) -> list[dict[str, str]]:
    return [
        {
            "proposal_id": proposal.proposal_id,
            "status": proposal.status,
            "record_id": proposal.record.id,
            "predicate": proposal.record.predicate,
            "subject": proposal.record.subject.name,
            "object": proposal.record.object_ref.name,
            "proposed_by": proposal.proposed_by,
            "proposed_at": proposal.proposed_at,
            "decided_by": proposal.decided_by or "",
            "decided_at": proposal.decided_at or "",
        }
        for proposal in proposals
    ]
