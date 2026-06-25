from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..paths import default_data_dir
from .schemas import (
    KnowledgeDecision,
    KnowledgeError,
    KnowledgeProposal,
    KnowledgeRecord,
    compute_proposal_id,
    records_digest,
    validate_knowledge_record,
    validate_proposal,
)


@dataclass(frozen=True)
class KnowledgeProposeResult:
    inserted: int
    path: str
    proposal_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ashare.knowledge_propose_result.v1",
            "inserted": self.inserted,
            "path": self.path,
            "proposal_ids": list(self.proposal_ids),
        }


@dataclass(frozen=True)
class KnowledgeAcceptResult:
    proposal_id: str
    record_id: str
    status: str
    current_path: str
    decision_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ashare.knowledge_accept_result.v1",
            "proposal_id": self.proposal_id,
            "record_id": self.record_id,
            "status": self.status,
            "current_path": self.current_path,
            "decision_path": self.decision_path,
        }


class KnowledgeStore:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.knowledge_root = self.data_dir / "knowledge"
        self.current_path = self.knowledge_root / "current.jsonl"
        self.proposals_path = self.knowledge_root / "proposals.jsonl"
        self.decisions_path = self.knowledge_root / "decisions.jsonl"
        self.snapshots_dir = self.knowledge_root / "snapshots"
        self.meta_path = self.knowledge_root / "_meta.json"

    def propose_records(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        reason: str | None = None,
        proposed_by: str = "llm_agent",
    ) -> KnowledgeProposeResult:
        records = payload if isinstance(payload, list) else [payload]
        proposal_ids: list[str] = []
        self.knowledge_root.mkdir(parents=True, exist_ok=True)
        with self.proposals_path.open("a", encoding="utf-8") as file:
            for raw in records:
                proposal = self.propose(raw, reason=reason, proposed_by=proposed_by, write=False)
                file.write(json.dumps(proposal.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
                proposal_ids.append(proposal.proposal_id)
        self._write_meta()
        return KnowledgeProposeResult(
            inserted=len(proposal_ids),
            path=str(self.proposals_path),
            proposal_ids=tuple(proposal_ids),
        )

    def propose(
        self,
        payload: dict[str, Any] | KnowledgeRecord,
        *,
        reason: str | None = None,
        proposed_by: str = "llm_agent",
        write: bool = True,
    ) -> KnowledgeProposal:
        record = payload if isinstance(payload, KnowledgeRecord) else KnowledgeRecord.from_dict(payload)
        record = validate_knowledge_record(record)
        proposed_at = _now_iso()
        proposal = validate_proposal(
            KnowledgeProposal(
                proposal_id=compute_proposal_id(record, proposed_at, proposed_by),
                record=record,
                proposed_by=proposed_by,
                proposed_at=proposed_at,
                reason=reason,
                status="proposed",
            )
        )
        if write:
            self.knowledge_root.mkdir(parents=True, exist_ok=True)
            with self.proposals_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(proposal.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            self._write_meta()
        return proposal

    def accept(self, proposal_id: str, *, accepted_by: str = "human", reason: str | None = None) -> KnowledgeAcceptResult:
        proposal = self.require_proposal(proposal_id)
        existing_decision = self.decision_for(proposal_id)
        if existing_decision and existing_decision.status == "accepted":
            return KnowledgeAcceptResult(
                proposal_id=proposal_id,
                record_id=proposal.record.id,
                status="already_accepted",
                current_path=str(self.current_path),
                decision_path=str(self.decisions_path),
            )
        if existing_decision:
            raise KnowledgeError(f"{proposal_id}: proposal already decided as {existing_decision.status}")

        record = validate_knowledge_record(proposal.record)
        decision = KnowledgeDecision(
            proposal_id=proposal_id,
            record_id=record.id,
            status="accepted",
            decided_by=accepted_by,
            decided_at=_now_iso(),
            reason=reason,
        )

        self.knowledge_root.mkdir(parents=True, exist_ok=True)
        with self.current_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        with self.decisions_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(decision.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        self._write_meta()
        return KnowledgeAcceptResult(
            proposal_id=proposal_id,
            record_id=record.id,
            status="accepted",
            current_path=str(self.current_path),
            decision_path=str(self.decisions_path),
        )

    def read_current_records(self) -> list[KnowledgeRecord]:
        records_by_id: dict[str, KnowledgeRecord] = {}
        for record in self._read_jsonl(self.current_path, KnowledgeRecord.from_dict):
            records_by_id[record.id] = validate_knowledge_record(record)
        return [records_by_id[key] for key in sorted(records_by_id)]

    def read_proposals(self, *, status: str | None = None) -> list[KnowledgeProposal]:
        decisions = {decision.proposal_id: decision for decision in self.read_decisions()}
        proposals: list[KnowledgeProposal] = []
        for proposal in self._read_jsonl(self.proposals_path, KnowledgeProposal.from_dict):
            effective = proposal.with_decision(decisions[proposal.proposal_id]) if proposal.proposal_id in decisions else proposal
            validate_proposal(effective)
            if status and effective.status != status:
                continue
            proposals.append(effective)
        return proposals

    def read_decisions(self) -> list[KnowledgeDecision]:
        return self._read_jsonl(self.decisions_path, KnowledgeDecision.from_dict)

    def require_proposal(self, proposal_id: str) -> KnowledgeProposal:
        for proposal in self.read_proposals():
            if proposal.proposal_id == proposal_id:
                return proposal
        raise KnowledgeError(f"proposal not found: {proposal_id}")

    def decision_for(self, proposal_id: str) -> KnowledgeDecision | None:
        for decision in reversed(self.read_decisions()):
            if decision.proposal_id == proposal_id:
                return decision
        return None

    def search(
        self,
        *,
        entity: str | None = None,
        predicate: str | None = None,
        source_type: str | None = None,
        evidence_id: str | None = None,
        limit: int | None = None,
    ) -> list[KnowledgeRecord]:
        filters = {
            "entity": entity,
            "predicate": predicate,
            "source_type": source_type,
            "evidence_id": evidence_id,
        }
        records = [record for record in self.read_current_records() if _matches(record, filters)]
        if limit and limit > 0:
            return records[:limit]
        return records

    def snapshot(self, output_path: Path | str | None = None) -> dict[str, Any]:
        records = self.read_current_records()
        generated_at = _now_iso()
        payload = {
            "schema": "ashare.knowledge_snapshot.v1",
            "generated_at": generated_at,
            "records": [record.to_dict() for record in records],
            "record_count": len(records),
            "records_sha256": records_digest(records),
        }
        if output_path is None:
            safe_time = generated_at.replace(":", "").replace("+", "_")
            output = self.snapshots_dir / f"{safe_time}.json"
        else:
            output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return payload | {"path": str(output)}

    def _write_meta(self) -> None:
        self.knowledge_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "ashare.knowledge_store_meta.v1",
            "current_records": len(self.read_current_records()),
            "proposals": len(self.read_proposals()),
            "current_path": str(self.current_path),
            "proposals_path": str(self.proposals_path),
            "decisions_path": str(self.decisions_path),
            "updated_at": _now_iso(),
        }
        self.meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_jsonl(self, path: Path, factory: Any) -> list[Any]:
        if not path.exists():
            return []
        rows: list[Any] = []
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    rows.append(factory(json.loads(line)))
                except (TypeError, ValueError, KeyError) as error:
                    raise KnowledgeError(f"Invalid knowledge JSONL at {path}:{line_number}: {error}") from error
        return rows


def _matches(record: KnowledgeRecord, filters: dict[str, str | None]) -> bool:
    if filters["predicate"] and filters["predicate"] != record.predicate:
        return False
    if filters["source_type"] and filters["source_type"] != record.source.source_type:
        return False
    if filters["evidence_id"] and filters["evidence_id"] != record.source.evidence_id:
        return False
    entity = filters["entity"]
    if entity:
        needle = entity.lower()
        terms = (*record.subject.searchable_terms(), *record.object_ref.searchable_terms())
        if not any(needle in term.lower() for term in terms):
            return False
    return True


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
