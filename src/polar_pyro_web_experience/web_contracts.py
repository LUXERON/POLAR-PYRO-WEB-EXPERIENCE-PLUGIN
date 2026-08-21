"""Canonical Web Experience Engine contracts and independent contract oracle.

The oracle proves only structural conformance, cross-document referential closure,
and hash binding for the supplied contract bundle.  It does not prove that the
brief captures human intent, that a UI is usable or beautiful, or that rendered
browser behavior matches the plan; later independent gates own those claims.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "1.0"
SCHEMA_FILES = {
    "application_capability": "application-capability.schema.json",
    "design_brief": "design-brief.schema.json",
    "ux_binding": "ux-binding.schema.json",
    "ux_contract": "ux-contract.schema.json",
    "design_language": "design-language.schema.json",
    "component_manifest": "component-manifest.schema.json",
    "ui_plan": "ui-plan.schema.json",
    "residual": "residual.schema.json",
    "experience_certificate": "experience-certificate.schema.json",
}


class ContractVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NO_RESULT = "NO_RESULT"


@dataclass(frozen=True, slots=True)
class ContractBundle:
    application_capability: Mapping[str, Any]
    design_brief: Mapping[str, Any]
    ux_binding: Mapping[str, Any]
    ux_contract: Mapping[str, Any]
    design_language: Mapping[str, Any]
    component_manifests: tuple[Mapping[str, Any], ...]
    ui_plan: Mapping[str, Any]
    residual: Mapping[str, Any]
    experience_certificate: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ContractOracleReport:
    verdict: ContractVerdict
    violations: tuple[str, ...]
    computed_hashes: Mapping[str, str]
    engine: str = "web-contract-oracle-v1"
    trust_boundary: str = (
        "Proves schema conformance, referential closure, and hash binding for the "
        "supplied bundle only; it does not prove user intent, beauty, usability, or "
        "rendered browser behavior."
    )

    @property
    def passed(self) -> bool:
        return self.verdict is ContractVerdict.PASS


def canonical_bytes(value: Any) -> bytes:
    """Return the project-wide deterministic JSON representation."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def component_catalog_sha256(manifests: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted(manifests, key=lambda item: str(item.get("component_id", "")))
    return content_sha256(ordered)


def default_schema_root() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas" / "web_experience"


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _schema_violations(value: Any, schema: Mapping[str, Any], path: str = "") -> list[str]:
    """Validate the deliberately small JSON-Schema subset used by P01.

    Unsupported schema keywords fail closed so a future schema cannot silently
    become weaker than the oracle understands.
    """
    supported = {
        "$schema", "$id", "title", "description", "type", "const", "enum",
        "required", "properties", "additionalProperties", "items", "minItems",
        "maxItems", "uniqueItems", "minProperties", "maxProperties", "minLength", "maxLength", "pattern",
        "minimum", "maximum",
    }
    unknown_keywords = sorted(set(schema) - supported)
    if unknown_keywords:
        return [f"{path or '/'}: unsupported schema keywords {unknown_keywords}"]

    violations: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else expected
        if not isinstance(expected_types, list) or not all(isinstance(item, str) for item in expected_types):
            return [f"{path or '/'}: schema type declaration is invalid"]
        if not any(_json_type_matches(value, item) for item in expected_types):
            return [f"{path or '/'}: expected {'|'.join(expected_types)}"]

    if "const" in schema and value != schema["const"]:
        violations.append(f"{path or '/'}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        violations.append(f"{path or '/'}: value {value!r} is not in the closed enum")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            violations.append(f"{path or '/'}: string is shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            violations.append(f"{path or '/'}: string is longer than maxLength")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            violations.append(f"{path or '/'}: string does not match required pattern")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            violations.append(f"{path or '/'}: number is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            violations.append(f"{path or '/'}: number is above maximum")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            violations.append(f"{path or '/'}: array has fewer than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            violations.append(f"{path or '/'}: array has more than maxItems")
        if schema.get("uniqueItems"):
            encoded = [canonical_bytes(item) for item in value]
            if len(encoded) != len(set(encoded)):
                violations.append(f"{path or '/'}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                violations.extend(_schema_violations(item, item_schema, f"{path}/{index}"))

    if isinstance(value, dict):
        if len(value) < schema.get("minProperties", 0):
            violations.append(f"{path or '/'}: object has fewer than minProperties")
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            violations.append(f"{path or '/'}: object has more than maxProperties")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                violations.append(f"{path or '/'}: missing required property {key!r}")
        for key, item in value.items():
            child_path = f"{path}/{key}"
            if key in properties:
                violations.extend(_schema_violations(item, properties[key], child_path))
                continue
            additional = schema.get("additionalProperties", True)
            if additional is False:
                violations.append(f"{child_path}: additional property is forbidden")
            elif isinstance(additional, dict):
                violations.extend(_schema_violations(item, additional, child_path))
    return violations


def validate_document(
    kind: str, value: Mapping[str, Any], *, schema_root: Path | None = None
) -> tuple[str, ...]:
    if kind not in SCHEMA_FILES:
        return (f"unknown contract kind {kind!r}",)
    root = schema_root or default_schema_root()
    schema_path = (root / SCHEMA_FILES[kind]).resolve()
    try:
        schema_path.relative_to(root.resolve())
    except ValueError:
        return (f"schema path escaped schema root: {schema_path}",)
    if not schema_path.is_file():
        return (f"schema missing: {schema_path}",)
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (f"schema unreadable: {schema_path}: {exc}",)
    return tuple(_schema_violations(value, schema))


def _ids(rows: Any, key: str) -> set[str]:
    if not isinstance(rows, list):
        return set()
    return {str(row[key]) for row in rows if isinstance(row, dict) and key in row}


def _region_walk(regions: Any) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    if not isinstance(regions, list):
        return found
    for region in regions:
        if not isinstance(region, dict):
            continue
        found.append(region)
        found.extend(_region_walk(region.get("children", [])))
    return found


def _cross_reference_violations(bundle: ContractBundle) -> list[str]:
    violations: list[str] = []
    manifest = bundle.application_capability
    application_id = manifest.get("application_id")
    for name, document in (
        ("design_brief", bundle.design_brief),
        ("ux_binding", bundle.ux_binding),
        ("ux_contract", bundle.ux_contract),
        ("ui_plan", bundle.ui_plan),
        ("experience_certificate", bundle.experience_certificate),
    ):
        if document.get("application_id") != application_id:
            violations.append(f"/{name}/application_id: does not match capability manifest")

    route_ids = _ids(manifest.get("routes"), "id")
    role_ids = _ids(manifest.get("roles"), "id")
    query_ids = _ids(manifest.get("queries"), "id")
    command_ids = _ids(manifest.get("commands"), "id")
    component_ids = {str(item.get("component_id")) for item in bundle.component_manifests}

    for collection_name, rows in (
        ("routes", manifest.get("routes", [])),
        ("roles", manifest.get("roles", [])),
        ("queries", manifest.get("queries", [])),
        ("commands", manifest.get("commands", [])),
    ):
        identifiers = [row.get("id") for row in rows]
        if len(identifiers) != len(set(identifiers)):
            violations.append(f"/application_capability/{collection_name}: duplicate IDs")
    for row in (*manifest.get("queries", []), *manifest.get("commands", [])):
        unknown_roles = set(row.get("roles", [])) - role_ids
        if unknown_roles:
            violations.append(
                f"/application_capability/{row.get('id')}/roles: unknown roles {sorted(unknown_roles)}"
            )
    for command in manifest.get("commands", []):
        if command.get("destructive") and not command.get("confirmation_required"):
            violations.append(
                f"/application_capability/commands/{command.get('id')}: destructive command requires confirmation"
            )
    for machine in manifest.get("state_machines", []):
        states = set(machine.get("states", []))
        if machine.get("initial") not in states:
            violations.append(f"/application_capability/state_machines/{machine.get('id')}: unknown initial state")
        for transition in machine.get("transitions", []):
            if transition.get("source") not in states or transition.get("target") not in states:
                violations.append(
                    f"/application_capability/state_machines/{machine.get('id')}: transition escapes state set"
                )

    binding_routes = set(bundle.ux_binding.get("view_recipes", {}))
    if binding_routes != route_ids:
        violations.append(
            f"/ux_binding/view_recipes: route closure mismatch missing={sorted(route_ids-binding_routes)} "
            f"unknown={sorted(binding_routes-route_ids)}"
        )

    ux_routes = _ids(bundle.ux_contract.get("routes"), "route_id")
    if ux_routes != route_ids:
        violations.append("/ux_contract/routes: must cover exactly the capability routes")
    tasks = bundle.ux_contract.get("tasks", [])
    task_ids = _ids(tasks, "id")
    for route in bundle.ux_contract.get("routes", []):
        unknown_roles = set(route.get("visible_to", [])) - role_ids
        unknown_tasks = set(route.get("primary_task_ids", [])) - task_ids
        if unknown_roles:
            violations.append(f"/ux_contract/routes/{route.get('route_id')}: unknown roles {sorted(unknown_roles)}")
        if unknown_tasks:
            violations.append(f"/ux_contract/routes/{route.get('route_id')}: unknown tasks {sorted(unknown_tasks)}")
    content_state_routes = set(bundle.ux_contract.get("content_states", {}))
    if content_state_routes != route_ids:
        violations.append("/ux_contract/content_states: must cover exactly the capability routes")
    for task in tasks if isinstance(tasks, list) else []:
        if not isinstance(task, dict):
            continue
        unknown_roles = set(task.get("role_ids", [])) - role_ids
        unknown_queries = set(task.get("query_ids", [])) - query_ids
        unknown_commands = set(task.get("command_ids", [])) - command_ids
        if task.get("entry_route") not in route_ids:
            violations.append(f"/ux_contract/tasks/{task.get('id')}: unknown entry_route")
        if unknown_roles:
            violations.append(f"/ux_contract/tasks/{task.get('id')}: unknown roles {sorted(unknown_roles)}")
        if unknown_queries:
            violations.append(f"/ux_contract/tasks/{task.get('id')}: unknown queries {sorted(unknown_queries)}")
        if unknown_commands:
            violations.append(f"/ux_contract/tasks/{task.get('id')}: unknown commands {sorted(unknown_commands)}")

    for journey in bundle.ux_contract.get("journeys", []):
        if journey.get("task_id") not in task_ids:
            violations.append(f"/ux_contract/journeys/{journey.get('id')}: unknown task")
            task = None
        else:
            task = next((item for item in tasks if item.get("id") == journey.get("task_id")), None)
        if task is not None and journey.get("terminal_state") != task.get("success_state"):
            violations.append(f"/ux_contract/journeys/{journey.get('id')}: terminal state does not satisfy task")
        if journey.get("recovery_route") not in route_ids:
            violations.append(f"/ux_contract/journeys/{journey.get('id')}: unknown recovery_route")
        for step in journey.get("steps", []):
            if step.get("route_id") not in route_ids:
                violations.append(f"/ux_contract/journeys/{journey.get('id')}: unknown step route")
            action = step.get("command_id")
            if action is not None and action not in command_ids:
                violations.append(f"/ux_contract/journeys/{journey.get('id')}: unknown command {action}")

    plan_routes = _ids(bundle.ui_plan.get("routes"), "route_id")
    if plan_routes != ux_routes:
        violations.append("/ui_plan/routes: must cover exactly the UX routes")
    for route in bundle.ui_plan.get("routes", []):
        for region in _region_walk(route.get("regions", [])):
            component_id = region.get("component_id")
            if component_id not in component_ids:
                violations.append(f"/ui_plan/regions/{region.get('id')}: unknown component {component_id}")
            for query_id in region.get("query_ids", []):
                if query_id not in query_ids:
                    violations.append(f"/ui_plan/regions/{region.get('id')}: unknown query {query_id}")
            for command_id in region.get("command_ids", []):
                if command_id not in command_ids:
                    violations.append(f"/ui_plan/regions/{region.get('id')}: unknown command {command_id}")

    if bundle.ui_plan.get("design_language_id") != bundle.design_language.get("design_language_id"):
        violations.append("/ui_plan/design_language_id: does not match design language")
    expected_ux_hash = content_sha256(bundle.ux_contract)
    if bundle.ui_plan.get("ux_contract_sha256") != expected_ux_hash:
        violations.append("/ui_plan/ux_contract_sha256: hash mismatch")
    expected_catalog_hash = component_catalog_sha256(bundle.component_manifests)
    if bundle.ui_plan.get("component_catalog_sha256") != expected_catalog_hash:
        violations.append("/ui_plan/component_catalog_sha256: hash mismatch")
    for component in bundle.component_manifests:
        for relation in ("allowed_parents", "allowed_children", "required_descendants"):
            unknown = set(component.get(relation, [])) - component_ids
            if unknown:
                violations.append(
                    f"/component_manifest/{component.get('component_id')}/{relation}: unknown components {sorted(unknown)}"
                )
    return violations


def _computed_hashes(bundle: ContractBundle) -> dict[str, str]:
    return {
        "application_capability_sha256": content_sha256(bundle.application_capability),
        "design_brief_sha256": content_sha256(bundle.design_brief),
        "ux_binding_sha256": content_sha256(bundle.ux_binding),
        "ux_contract_sha256": content_sha256(bundle.ux_contract),
        "design_language_sha256": content_sha256(bundle.design_language),
        "component_catalog_sha256": component_catalog_sha256(bundle.component_manifests),
        "ui_plan_sha256": content_sha256(bundle.ui_plan),
        "residual_sha256": content_sha256(bundle.residual),
    }


def verify_contract_bundle(
    bundle: ContractBundle, *, schema_root: Path | None = None
) -> ContractOracleReport:
    """Independently recompute contract validity and certificate hash bindings."""
    documents: list[tuple[str, Mapping[str, Any]]] = [
        ("application_capability", bundle.application_capability),
        ("design_brief", bundle.design_brief),
        ("ux_binding", bundle.ux_binding),
        ("ux_contract", bundle.ux_contract),
        ("design_language", bundle.design_language),
        ("ui_plan", bundle.ui_plan),
        ("residual", bundle.residual),
        ("experience_certificate", bundle.experience_certificate),
    ]
    documents.extend(("component_manifest", item) for item in bundle.component_manifests)
    violations: list[str] = []
    missing_schema = False
    for kind, document in documents:
        found = validate_document(kind, document, schema_root=schema_root)
        violations.extend(f"/{kind}{item}" for item in found)
        missing_schema = missing_schema or any("schema missing" in item or "schema unreadable" in item for item in found)

    hashes = _computed_hashes(bundle)
    if not violations:
        violations.extend(_cross_reference_violations(bundle))
    if not violations:
        certificate_hashes = bundle.experience_certificate.get("contract_hashes", {})
        for key, computed in hashes.items():
            if certificate_hashes.get(key) != computed:
                violations.append(
                    f"/experience_certificate/contract_hashes/{key}: hash mismatch"
                )
        oracle_results = bundle.experience_certificate.get("oracle_results", [])
        if not oracle_results:
            violations.append("/experience_certificate/oracle_results: non-empty live evidence required")
        for result in oracle_results:
            if result.get("verdict") != "PASS":
                violations.append(
                    f"/experience_certificate/oracle_results/{result.get('gate')}: verdict is not PASS"
                )

    if missing_schema:
        verdict = ContractVerdict.NO_RESULT
    else:
        verdict = ContractVerdict.FAIL if violations else ContractVerdict.PASS
    return ContractOracleReport(verdict, tuple(violations), hashes)
