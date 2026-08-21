from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from polar_pyro_web_experience.web_contracts import (
    SCHEMA_FILES,
    ContractBundle,
    ContractVerdict,
    canonical_bytes,
    component_catalog_sha256,
    content_sha256,
    default_schema_root,
    verify_contract_bundle,
)


HASH = "a" * 64


def qualified_bundle() -> ContractBundle:
    capability = {
        "schema_version": "1.0",
        "application_id": "casebook",
        "source_engine": "sae",
        "routes": [{"id": "dashboard", "path": "/"}],
        "roles": [{"id": "administrator"}],
        "queries": [
            {"id": "list_cases", "result_type": "CaseList", "roles": ["administrator"]}
        ],
        "commands": [
            {
                "id": "create_case",
                "input_type": "CreateCase",
                "roles": ["administrator"],
                "destructive": False,
                "confirmation_required": False,
            }
        ],
        "state_machines": [
            {
                "id": "case_lifecycle",
                "states": ["open", "resolved"],
                "initial": "open",
                "transitions": [{"event": "resolve", "source": "open", "target": "resolved"}],
            }
        ],
        "errors": [{"code": "VALIDATION_ERROR", "recoverable": True}],
        "provenance": {"source_ref": "sae:casebook@fixture", "source_sha256": HASH},
    }
    design_brief = {
        "schema_version": "1.0",
        "application_id": "casebook",
        "audiences": ["incident administrator"],
        "product_category": "case_management",
        "attributes": ["precise", "trustworthy"],
        "exclusions": ["decorative motion"],
        "density": "compact",
        "device_priorities": ["desktop", "mobile"],
        "accessibility_target": "wcag_2_2_aa",
    }
    ux_binding = {
        "schema_version": "1.0",
        "application_id": "casebook",
        "archetype": "case_review_workspace",
        "navigation": "sidebar_workspace",
        "density": "compact",
        "tone": "authoritative",
        "priorities": ["time_to_triage", "evidence_integrity"],
        "view_recipes": {"dashboard": "data_table_workspace"},
        "design_precedent": "ops.precise.light.v1",
        "evidence_refs": [HASH],
    }
    ux_contract = {
        "schema_version": "1.0",
        "application_id": "casebook",
        "routes": [
            {
                "route_id": "dashboard",
                "visible_to": ["administrator"],
                "primary_task_ids": ["manage_cases"],
            }
        ],
        "tasks": [
            {
                "id": "manage_cases",
                "role_ids": ["administrator"],
                "entry_route": "dashboard",
                "success_state": "case_created",
                "command_ids": ["create_case"],
                "query_ids": ["list_cases"],
            }
        ],
        "journeys": [
            {
                "id": "create_case_journey",
                "task_id": "manage_cases",
                "steps": [
                    {
                        "id": "submit",
                        "route_id": "dashboard",
                        "state": "ready",
                        "command_id": "create_case",
                    }
                ],
                "terminal_state": "case_created",
                "recovery_route": "dashboard",
            }
        ],
        "content_states": {"dashboard": ["loading", "empty", "ready", "error"]},
    }
    design_language = {
        "schema_version": "1.0",
        "design_language_id": "ops.precise.light.v1",
        "color_roles": {"surface": "neutral.0", "action": "blue.600"},
        "typography_roles": {"page_title": "type.title.lg", "body": "type.body.md"},
        "spacing_roles": {"section_gap": "space.6"},
        "radius_roles": {"control": "radius.sm"},
        "motion_policy": "restrained",
        "icon_family": "lucide",
        "breakpoints": ["mobile", "laptop", "desktop"],
    }
    components = (
        {
            "schema_version": "1.0",
            "component_id": "app_shell",
            "provider": "luxeron_registry",
            "version": "1.0.0",
            "commit": "abcdef1",
            "license": "MIT",
            "framework": "react-vite",
            "role": "application_shell",
            "props": {"label": "string"},
            "slots": ["content"],
            "events": [],
            "states": ["ready"],
            "allowed_parents": [],
            "allowed_children": ["data_table"],
            "required_descendants": ["data_table"],
            "dependencies": ["react@19"],
            "evidence_refs": [HASH],
        },
        {
            "schema_version": "1.0",
            "component_id": "data_table",
            "provider": "luxeron_registry",
            "version": "1.0.0",
            "commit": "abcdef1",
            "license": "MIT",
            "framework": "react-vite",
            "role": "data_collection",
            "props": {"rows": "CaseList"},
            "slots": [],
            "events": ["select"],
            "states": ["loading", "empty", "ready", "error"],
            "allowed_parents": ["app_shell"],
            "allowed_children": [],
            "required_descendants": [],
            "dependencies": ["react@19"],
            "evidence_refs": [HASH],
        },
    )
    ui_plan = {
        "schema_version": "1.0",
        "application_id": "casebook",
        "design_language_id": "ops.precise.light.v1",
        "ux_contract_sha256": content_sha256(ux_contract),
        "component_catalog_sha256": component_catalog_sha256(components),
        "routes": [
            {
                "route_id": "dashboard",
                "recipe_id": "data_table_workspace",
                "regions": [
                    {
                        "id": "shell",
                        "component_id": "app_shell",
                        "query_ids": [],
                        "command_ids": [],
                        "children": [],
                    },
                    {
                        "id": "cases",
                        "component_id": "data_table",
                        "query_ids": ["list_cases"],
                        "command_ids": ["create_case"],
                        "children": [],
                    },
                ],
            }
        ],
    }
    residual = {
        "schema_version": "1.0",
        "gate": "contract_oracle",
        "code": "NO_RESIDUAL",
        "path": "/",
        "expected": None,
        "observed": None,
        "allowed_patches": [],
        "actionable": False,
    }
    documents = {
        "application_capability_sha256": content_sha256(capability),
        "design_brief_sha256": content_sha256(design_brief),
        "ux_binding_sha256": content_sha256(ux_binding),
        "ux_contract_sha256": content_sha256(ux_contract),
        "design_language_sha256": content_sha256(design_language),
        "component_catalog_sha256": component_catalog_sha256(components),
        "ui_plan_sha256": content_sha256(ui_plan),
        "residual_sha256": content_sha256(residual),
    }
    certificate = {
        "schema_version": "1.0",
        "application_id": "casebook",
        "contract_hashes": documents,
        "source_sha256": HASH,
        "oracle_results": [
            {"gate": "contract_oracle", "verdict": "PASS", "evidence_sha256": HASH}
        ],
        "assumptions": ["Provider evidence is pinned by hash."],
        "bounds": ["This certificate does not prove beauty or rendered behavior."],
        "created_at": "2026-08-20T00:00:00Z",
    }
    return ContractBundle(
        capability,
        design_brief,
        ux_binding,
        ux_contract,
        design_language,
        components,
        ui_plan,
        residual,
        certificate,
    )


def test_all_nine_schemas_exist_and_qualified_bundle_passes() -> None:
    root = default_schema_root()
    assert len(SCHEMA_FILES) == 9
    assert all((root / filename).is_file() for filename in SCHEMA_FILES.values())

    report = verify_contract_bundle(qualified_bundle())

    assert report.verdict is ContractVerdict.PASS
    assert report.passed
    assert not report.violations
    assert "does not prove" in report.trust_boundary


def test_canonical_hash_is_key_order_invariant_and_unicode_stable() -> None:
    left = {"z": "Δ", "a": [2, 1]}
    right = {"a": [2, 1], "z": "Δ"}

    assert canonical_bytes(left) == canonical_bytes(right)
    assert content_sha256(left) == content_sha256(right)
    assert len(content_sha256(left)) == 64


def test_live_poison_undeclared_ui_command_is_rejected() -> None:
    bundle = qualified_bundle()
    poisoned_plan = deepcopy(bundle.ui_plan)
    poisoned_plan["routes"][0]["regions"][1]["command_ids"] = ["delete_everything"]
    poisoned = replace(bundle, ui_plan=poisoned_plan)

    report = verify_contract_bundle(poisoned)

    assert report.verdict is ContractVerdict.FAIL
    assert any("unknown command delete_everything" in item for item in report.violations)


def test_live_poison_tampered_certificate_hash_is_rejected() -> None:
    bundle = qualified_bundle()
    certificate = deepcopy(bundle.experience_certificate)
    certificate["contract_hashes"]["ux_contract_sha256"] = "0" * 64

    report = verify_contract_bundle(replace(bundle, experience_certificate=certificate))

    assert report.verdict is ContractVerdict.FAIL
    assert any("ux_contract_sha256: hash mismatch" in item for item in report.violations)


def test_schema_drift_and_unknown_fields_fail_closed() -> None:
    bundle = qualified_bundle()
    binding = deepcopy(bundle.ux_binding)
    binding["raw_css"] = "body { display: none }"

    report = verify_contract_bundle(replace(bundle, ux_binding=binding))

    assert report.verdict is ContractVerdict.FAIL
    assert any("raw_css" in item and "forbidden" in item for item in report.violations)


def test_missing_oracle_schema_returns_no_result_not_pass(tmp_path: Path) -> None:
    report = verify_contract_bundle(qualified_bundle(), schema_root=tmp_path)

    assert report.verdict is ContractVerdict.NO_RESULT
    assert not report.passed
    assert any("schema missing" in item for item in report.violations)


def test_destructive_action_without_confirmation_is_rejected() -> None:
    bundle = qualified_bundle()
    capability = deepcopy(bundle.application_capability)
    capability["commands"][0]["destructive"] = True
    certificate = deepcopy(bundle.experience_certificate)
    certificate["contract_hashes"]["application_capability_sha256"] = content_sha256(capability)

    report = verify_contract_bundle(
        replace(bundle, application_capability=capability, experience_certificate=certificate)
    )

    assert report.verdict is ContractVerdict.FAIL
    assert any("destructive command requires confirmation" in item for item in report.violations)
