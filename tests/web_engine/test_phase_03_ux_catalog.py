from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from polar_pyro_web_experience.web_contracts import ContractVerdict, canonical_bytes
from polar_pyro_web_experience.web_ux_catalog import (
    EXPECTED_ARCHETYPES,
    REQUIRED_CONTENT_STATES,
    compile_web_cheatsheet,
    load_ux_catalog,
    select_design_language,
)


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog" / "web_experience"


def test_ten_archetypes_languages_and_precedents_form_closed_catalog() -> None:
    payload, audit = load_ux_catalog(CATALOG)

    assert audit.passed, audit.violations
    assert len(payload["archetypes"]) == EXPECTED_ARCHETYPES == 10
    assert len(payload["design_languages"]) == 3
    assert len(payload["precedents"]) == 10
    assert len(audit.catalog_sha256) == 64
    for archetype in payload["archetypes"]:
        assert REQUIRED_CONTENT_STATES <= set(archetype["required_content_states"])
        assert archetype["view_recipes"]
        assert archetype["priorities"]


def test_master_librarian_cheatsheet_is_bounded_and_closed() -> None:
    payload, audit = load_ux_catalog(CATALOG)
    assert audit.passed

    sheet = compile_web_cheatsheet(payload, archetype_id="incident_response_workspace")

    assert sheet["archetype"] == "incident_response_workspace"
    assert sheet["allowed_view_recipes"] == [
        "incident_queue_detail", "evidence_timeline", "approval_and_retention"
    ]
    assert sheet["estimated_tokens"] <= 800
    assert len(canonical_bytes(sheet)) < 3200
    assert "no_raw_code_or_css" in sheet["invariants"]


def test_fuzzy_to_discrete_bridge_selects_only_unique_supported_profile() -> None:
    precise = select_design_language(["precise", "trustworthy", "enterprise"])
    warm = select_design_language(["warm", "friendly", "welcoming"])

    assert precise.verdict is ContractVerdict.PASS
    assert precise.design_language_id == "ops.precise.light.v1"
    assert warm.verdict is ContractVerdict.PASS
    assert warm.design_language_id == "warm.approachable.light.v1"


def test_fuzzy_to_discrete_bridge_abstains_on_ambiguity_or_no_evidence() -> None:
    ambiguous = select_design_language(["precise", "dark", "light"])
    unsupported = select_design_language(["baroque", "otherworldly"])

    assert ambiguous.verdict is ContractVerdict.NO_RESULT
    assert ambiguous.design_language_id is None
    assert unsupported.verdict is ContractVerdict.NO_RESULT
    assert unsupported.design_language_id is None


def test_cheatsheet_refuses_unknown_archetype_and_too_small_budget() -> None:
    payload, audit = load_ux_catalog(CATALOG)
    assert audit.passed

    with pytest.raises(ValueError, match="unknown archetype"):
        compile_web_cheatsheet(payload, archetype_id="invented")
    with pytest.raises(ValueError, match="exceeds token budget"):
        compile_web_cheatsheet(
            payload, archetype_id="operations_console", max_estimated_tokens=20
        )


def test_live_poison_precedent_cannot_self_ratify(tmp_path: Path) -> None:
    source = json.loads((CATALOG / "ux-catalog.source.json").read_text(encoding="utf-8"))
    languages = json.loads((CATALOG / "design-languages.json").read_text(encoding="utf-8"))
    precedents = json.loads(
        (CATALOG / "precedents" / "precedent-index.json").read_text(encoding="utf-8")
    )
    poisoned = deepcopy(precedents)
    poisoned["precedents"][0]["human_ratification_required"] = False
    (tmp_path / "precedents").mkdir(parents=True)
    (tmp_path / "ux-catalog.source.json").write_text(json.dumps(source), encoding="utf-8")
    (tmp_path / "design-languages.json").write_text(json.dumps(languages), encoding="utf-8")
    (tmp_path / "precedents" / "precedent-index.json").write_text(
        json.dumps(poisoned), encoding="utf-8"
    )

    _, audit = load_ux_catalog(tmp_path)

    assert not audit.passed
    assert any("human ratification boundary" in item for item in audit.violations)
