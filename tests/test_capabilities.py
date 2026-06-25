import json

import pytest

from ashare_research.capabilities import CapabilityError, CapabilityRegistry
from ashare_research.cli import main


def test_builtin_capability_registry_loads_core_specs():
    registry = CapabilityRegistry.builtin()
    capability_ids = {spec.capability_id for spec in registry.list()}

    assert {
        "market_environment.v1",
        "theme_strength_detection.v1",
        "concept_membership_discovery.v1",
        "company_exposure_validation.v1",
        "financial_validation.v1",
        "evidence_collection.v1",
    }.issubset(capability_ids)


def test_capability_registry_show_and_validate():
    registry = CapabilityRegistry.builtin()

    spec = registry.require("company_exposure_validation.v1")
    assert spec.category == "company"
    assert "fina_mainbz" in spec.inputs["marts"]
    assert "industry_chain_selection.v1" in spec.suggested_protocols

    payload = registry.validate()
    assert payload["schema"] == "ashare.capability_validation.v1"
    assert payload["status"] == "ready"
    assert all(item["status"] == "ready" for item in payload["capabilities"])


def test_capability_registry_rejects_unknown_id():
    registry = CapabilityRegistry.builtin()

    with pytest.raises(CapabilityError):
        registry.require("unknown.v1")


def test_cli_capabilities_list_show_validate(capsys):
    exit_code = main(["capabilities", "list", "--format", "json"])

    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    capability_ids = {item["capability_id"] for item in list_payload}
    assert "theme_strength_detection.v1" in capability_ids
    assert "company_exposure_validation.v1" in capability_ids

    exit_code = main(["capabilities", "show", "theme_strength_detection.v1"])

    assert exit_code == 0
    show_payload = json.loads(capsys.readouterr().out)
    assert show_payload["schema"] == "ashare.capability_spec.v1"
    assert show_payload["capability_id"] == "theme_strength_detection.v1"
    assert "concept_strength" in show_payload["inputs"]["features"]

    exit_code = main(["capabilities", "validate", "theme_strength_detection.v1"])

    assert exit_code == 0
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload["status"] == "ready"
    assert validate_payload["capabilities"][0]["capability_id"] == "theme_strength_detection.v1"
