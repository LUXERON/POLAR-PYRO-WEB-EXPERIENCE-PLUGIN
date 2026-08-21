from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from polar_pyro_web_experience.web_catalog import EXPECTED_COMPONENTS, build_catalog
from polar_pyro_web_experience.web_contracts import canonical_bytes, component_catalog_sha256


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog" / "web_experience"


def test_catalog_rebuild_is_deterministic_and_matches_checked_lock() -> None:
    first, first_audit = build_catalog(
        CATALOG / "providers.lock.json", CATALOG / "components.source.json"
    )
    second, second_audit = build_catalog(
        CATALOG / "providers.lock.json", CATALOG / "components.source.json"
    )
    checked = json.loads((CATALOG / "catalog.lock.json").read_text(encoding="utf-8"))

    assert first_audit.passed, first_audit.violations
    assert second_audit.passed, second_audit.violations
    assert first_audit.component_count == EXPECTED_COMPONENTS == 30
    assert canonical_bytes(first) == canonical_bytes(second) == canonical_bytes(checked)
    assert first["component_catalog_sha256"] == component_catalog_sha256(first["components"])


def test_all_components_have_exact_provider_license_and_state_evidence() -> None:
    payload, audit = build_catalog(
        CATALOG / "providers.lock.json", CATALOG / "components.source.json"
    )
    providers = {item["id"]: item for item in payload["providers"]}

    assert audit.passed, audit.violations
    assert set(providers) == {"shadcn-ui", "radix-primitives", "lucide"}
    for provider in providers.values():
        assert len(provider["commit"]) == 40
        assert len(provider["license_sha256"]) == 64
        assert provider["license"] in {"MIT", "ISC"}
    for component in payload["components"]:
        provider = providers[component["provider"]]
        assert component["commit"] == provider["commit"]
        assert component["license"] == provider["license"]
        assert provider["license_sha256"] in component["evidence_refs"]
        assert component["states"]
        assert all("@commit:" in item for item in component["dependencies"])


def test_dialog_form_table_and_button_profiles_are_non_vacuous() -> None:
    payload, audit = build_catalog(
        CATALOG / "providers.lock.json", CATALOG / "components.source.json"
    )
    by_id = {item["component_id"]: item for item in payload["components"]}

    assert audit.passed, audit.violations
    assert {"dialog_title", "dialog_description"} <= set(by_id["dialog"]["required_descendants"])
    assert {"closed", "open"} <= set(by_id["dialog"]["states"])
    assert "form_field" in by_id["form"]["required_descendants"]
    assert {"loading", "empty", "ready", "error"} <= set(by_id["data_table"]["states"])
    assert {"idle", "focus", "disabled"} <= set(by_id["button"]["states"])


def test_live_poison_unpinned_provider_and_forbidden_license_are_rejected(tmp_path: Path) -> None:
    providers = json.loads((CATALOG / "providers.lock.json").read_text(encoding="utf-8"))
    poisoned = deepcopy(providers)
    poisoned["providers"][0]["commit"] = "main"
    poisoned["providers"][0]["license"] = "UNKNOWN"
    provider_path = tmp_path / "providers.json"
    provider_path.write_text(json.dumps(poisoned), encoding="utf-8")

    _, audit = build_catalog(provider_path, CATALOG / "components.source.json")

    assert not audit.passed
    assert any("40-character commit" in item for item in audit.violations)
    assert any("license is not allowlisted" in item for item in audit.violations)


def test_live_poison_dialog_without_accessible_title_is_rejected(tmp_path: Path) -> None:
    source = json.loads((CATALOG / "components.source.json").read_text(encoding="utf-8"))
    poisoned = deepcopy(source)
    dialog = next(item for item in poisoned["components"] if item["id"] == "dialog")
    dialog["required"] = ["dialog_description"]
    source_path = tmp_path / "components.json"
    source_path.write_text(json.dumps(poisoned), encoding="utf-8")

    _, audit = build_catalog(CATALOG / "providers.lock.json", source_path)

    assert not audit.passed
    assert any("dialog missing descendants ['dialog_title']" in item for item in audit.violations)


def test_third_party_notices_bind_every_provider_revision_and_license_hash() -> None:
    providers = json.loads((CATALOG / "providers.lock.json").read_text(encoding="utf-8"))
    notices = (CATALOG / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    for provider in providers["providers"]:
        assert provider["commit"] in notices
        assert provider["license_sha256"] in notices
        assert provider["license"] in notices
