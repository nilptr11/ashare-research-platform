import json

import pytest

from ashare_research.cli import main
from ashare_research.knowledge import KnowledgeStore
from ashare_research.knowledge.schemas import KnowledgeError, KnowledgeRecord


def _knowledge_record(**overrides):
    payload = {
        "id": "company_product:603938.SH:high_purity_silicon_tetrachloride",
        "subject": {
            "type": "company",
            "id": "603938.SH",
            "name": "三孚股份",
            "aliases": ["Sanfu"],
        },
        "predicate": "has_product_exposure",
        "object": {
            "type": "product",
            "id": "high_purity_silicon_tetrachloride",
            "name": "高纯四氯化硅",
            "aliases": ["HP SiCl4"],
        },
        "confidence": "medium",
        "source": {
            "source_type": "company_filing",
            "source_name": "annual report",
            "source_url": "https://example.com/sanfu-annual-report",
            "published_at": "2026-04-15",
        },
        "valid_from": "2026-04-15",
        "updated_at": "2026-06-24T00:00:00+08:00",
        "tags": ["ai_infrastructure", "materials"],
    }
    payload.update(overrides)
    return payload


def test_knowledge_propose_accept_search_and_snapshot(tmp_path):
    store = KnowledgeStore(tmp_path)

    propose_result = store.propose_records(_knowledge_record(), reason="filing mapping")

    assert propose_result.inserted == 1
    assert store.read_current_records() == []

    proposal_id = propose_result.proposal_ids[0]
    accept_result = store.accept(proposal_id, accepted_by="human")

    assert accept_result.status == "accepted"
    records = store.search(entity="三孚", predicate="has_product_exposure")
    assert len(records) == 1
    assert records[0].object_ref.name == "高纯四氯化硅"

    snapshot = store.snapshot()
    assert snapshot["record_count"] == 1
    assert snapshot["records_sha256"]


def test_knowledge_requires_traceable_source(tmp_path):
    store = KnowledgeStore(tmp_path)
    payload = _knowledge_record(source={"source_type": "company_filing"})

    with pytest.raises(KnowledgeError, match="source requires source_url or evidence_id"):
        store.propose_records(payload)


def test_knowledge_accept_is_idempotent(tmp_path):
    store = KnowledgeStore(tmp_path)
    proposal = store.propose(_knowledge_record())

    first = store.accept(proposal.proposal_id)
    second = store.accept(proposal.proposal_id)

    assert first.status == "accepted"
    assert second.status == "already_accepted"
    assert len(store.read_current_records()) == 1


def test_cli_knowledge_flow(capsys, tmp_path):
    knowledge_file = tmp_path / "knowledge.json"
    knowledge_file.write_text(json.dumps(_knowledge_record(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "knowledge",
            "propose",
            str(knowledge_file),
            "--reason",
            "source checked",
        ]
    )
    assert exit_code == 0
    propose_payload = json.loads(capsys.readouterr().out)
    proposal_id = propose_payload["proposal_ids"][0]

    exit_code = main(["--data-dir", str(tmp_path), "knowledge", "list", "--format", "json"])
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == []

    exit_code = main(["--data-dir", str(tmp_path), "knowledge", "accept", proposal_id])
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "accepted"

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "knowledge",
            "search",
            "--entity",
            "HP SiCl4",
            "--format",
            "json",
        ]
    )
    assert exit_code == 0
    search_payload = json.loads(capsys.readouterr().out)
    assert search_payload[0]["subject"]["id"] == "603938.SH"

    snapshot_path = tmp_path / "knowledge-snapshot.json"
    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "knowledge",
            "snapshot",
            "--output",
            str(snapshot_path),
        ]
    )
    assert exit_code == 0
    snapshot_payload = json.loads(capsys.readouterr().out)
    assert snapshot_payload["path"] == str(snapshot_path)
    assert snapshot_path.exists()


def test_knowledge_record_round_trip():
    record = KnowledgeRecord.from_dict(_knowledge_record())

    assert KnowledgeRecord.from_dict(record.to_dict()).to_dict() == record.to_dict()
