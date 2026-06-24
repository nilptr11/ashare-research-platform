import json
from pathlib import Path

from ashare_research.cli import main
from ashare_research.context_packs import ContextPackBuilder
from ashare_research.evidence import EvidenceStore
from ashare_research.knowledge import KnowledgeStore


def _evidence_record():
    return {
        "claim": "AI infrastructure capex remains elevated.",
        "topic": "capex",
        "industry": "ai_infrastructure",
        "product": "data_center",
        "company": "Microsoft",
        "region": "United States",
        "metric": "capital_expenditures",
        "value": 34.9,
        "unit": "USD billion",
        "period": "FY2026 Q1",
        "frequency": "quarterly",
        "source_type": "company_ir",
        "source_name": "Microsoft Investor Relations",
        "source_url": "https://example.com/msft-ir",
        "published_at": "2025-10-29",
        "query_time": "2026-06-24T15:26:50+08:00",
        "confidence": "high",
        "verification": "official_single_source",
    }


def _knowledge_record():
    return {
        "id": "theme_chain:ai_infrastructure:optical_interconnect",
        "subject": {
            "type": "industry",
            "id": "ai_infrastructure",
            "name": "ai_infrastructure",
            "aliases": ["AI 算力"],
        },
        "predicate": "has_component",
        "object": {
            "type": "industry_chain_node",
            "id": "optical_interconnect",
            "name": "optical_interconnect",
            "aliases": ["光互连"],
        },
        "confidence": "medium",
        "source": {
            "source_type": "industry_association",
            "source_url": "https://example.com/industry-map",
            "published_at": "2026-05-01",
        },
        "valid_from": "2026-05-01",
    }


def test_market_context_pack_writes_with_gaps(tmp_path):
    payload = ContextPackBuilder(tmp_path).build_market_structure(as_of="20260623")

    assert payload["schema"] == "ashare.context_pack.market_structure.v1"
    assert payload["coverage"]["datasets_total"] > 0
    assert payload["data_gaps"]
    assert any(flag.startswith("missing_or_unready_mart:") for flag in payload["quality_flags"])
    assert Path(payload["path"]).exists()


def test_industry_context_pack_includes_evidence_and_knowledge(tmp_path):
    EvidenceStore(tmp_path).ingest_evidence(_evidence_record())
    knowledge_store = KnowledgeStore(tmp_path)
    proposal = knowledge_store.propose(_knowledge_record())
    knowledge_store.accept(proposal.proposal_id)

    payload = ContextPackBuilder(tmp_path).build_industry(industry="ai_infrastructure", as_of="20260623")

    assert payload["schema"] == "ashare.context_pack.industry.v1"
    assert payload["coverage"]["evidence_records"] == 1
    assert payload["coverage"]["knowledge_records"] == 1
    assert any(item["kind"] == "evidence" and item["content_hash"] for item in payload["inputs"])
    assert any(item["kind"] == "knowledge" and item["content_hash"] for item in payload["inputs"])


def test_cli_context_build_stock(capsys, tmp_path):
    output_path = tmp_path / "context" / "stock.json"

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "context",
            "build",
            "stock",
            "603938.SH",
            "--as-of",
            "20260623",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "ashare.context_pack.stock.v1"
    assert payload["path"] == str(output_path)
    assert output_path.exists()
