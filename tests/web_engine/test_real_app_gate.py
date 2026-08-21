from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qwen_harness.real_app_gate import Verdict, verify_real_application


BACKEND = {
    "verdict": "PASS",
    "authorization_passed": True,
    "mutual_match_messaging_passed": True,
    "blocked_contact_denial_passed": True,
    "restart_persistence_passed": True,
    "moderator_decision_audit_passed": True,
}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def write_case(root: Path, manifest: dict, concept: dict, browser: dict) -> None:
    for directory in ("evidence", "design", "app"):
        (root / directory).mkdir()
    (root / "product-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "design/concept-provenance.json").write_text(json.dumps(concept), encoding="utf-8")
    (root / "evidence/backend-oracle.json").write_text(json.dumps(BACKEND), encoding="utf-8")
    (root / "evidence/real-app-browser.json").write_text(json.dumps(browser), encoding="utf-8")
    artifact = b"frozen renderer source"
    (root / "app/artifact.txt").write_bytes(artifact)
    files = {"artifact.txt": hashlib.sha256(artifact).hexdigest()}
    render = {
        "renderer": "test.renderer.v1",
        "files": files,
        "output_sha256": hashlib.sha256(canonical(files)).hexdigest(),
        "design_ir_sha256": concept.get("design_ir_sha256"),
        "manifest_sha256": hashlib.sha256(canonical(manifest)).hexdigest(),
    }
    (root / "app/RENDER_RECEIPT.json").write_text(json.dumps(render), encoding="utf-8")


def deep_manifest() -> tuple[dict, list[dict]]:
    journeys = [{"id": f"journey_{i}", "steps": ["open", "act", "confirm"]} for i in range(5)]
    manifest = {
        "routes": [{"id": f"route_{i}"} for i in range(10)],
        "critical_journeys": journeys,
        "persistent_entities": ["user", "conversation", "message"],
        "roles": ["member", "moderator"],
        "content_states": ["loading", "empty", "ready", "error", "offline", "forbidden"],
        "backend_contracts": ["api.v1"],
        "distinctive_product_thesis": "Private, proof-carrying community conversations.",
    }
    return manifest, journeys


def admitted_concept(**extra: object) -> dict:
    value = {
        "certifying": True,
        "source_kind": "user_supplied_text",
        "producer": "qwen06_harness_design_pipeline",
        "autonomy_run_id": "run-1",
        "design_input_sha256": "a",
        "design_ir_sha256": "b",
        "admission_receipt_sha256": "c",
        "toam_record_ref": "d",
    }
    value.update(extra)
    return value


def passing_browser(journeys: list[dict]) -> dict:
    return {
        "verdict": "PASS",
        "journeys": [item["id"] for item in journeys],
        "reload_persistence_passed": True,
        "negative_authorization_passed": True,
        "api_failure_recovery_passed": True,
    }


def test_generic_single_page_shell_is_rejected(tmp_path: Path) -> None:
    manifest = {"routes": [{"id": "workspace"}], "critical_journeys": [], "persistent_entities": [], "roles": ["operator"], "content_states": ["ready"], "backend_contracts": [], "distinctive_product_thesis": ""}
    write_case(tmp_path, manifest, admitted_concept(certifying=False), {"verdict": "PASS", "journeys": []})
    report = verify_real_application(tmp_path)
    assert report.verdict is Verdict.FAIL
    assert any("10 product routes" in item for item in report.violations)
    assert any("persistent" in item for item in report.violations)


def test_market_depth_requires_live_matching_journey_evidence(tmp_path: Path) -> None:
    manifest, journeys = deep_manifest()
    write_case(tmp_path, manifest, admitted_concept(), passing_browser(journeys))
    assert verify_real_application(tmp_path).passed


def test_external_concept_cannot_certify_autonomy(tmp_path: Path) -> None:
    manifest, journeys = deep_manifest()
    concept = admitted_concept(certifying=False, source_kind="configured_generator")
    write_case(tmp_path, manifest, concept, passing_browser(journeys))
    report = verify_real_application(tmp_path)
    assert report.verdict is Verdict.FAIL
    assert any("admitted autonomous evidence" in item for item in report.violations)


def test_configured_generator_is_provider_neutral(tmp_path: Path) -> None:
    manifest, journeys = deep_manifest()
    concept = admitted_concept(
        source_kind="configured_generator",
        generation={"provider": "any-user-configured-provider", "capability_digest": "e", "receipt_sha256": "f"},
    )
    write_case(tmp_path, manifest, concept, passing_browser(journeys))
    assert verify_real_application(tmp_path).passed


def test_rendered_source_tampering_fails_closed(tmp_path: Path) -> None:
    manifest, journeys = deep_manifest()
    write_case(tmp_path, manifest, admitted_concept(), passing_browser(journeys))
    (tmp_path / "app/artifact.txt").write_text("tampered", encoding="utf-8")
    report = verify_real_application(tmp_path)
    assert report.verdict is Verdict.FAIL
    assert "rendered source hash mismatch: artifact.txt" in report.violations
