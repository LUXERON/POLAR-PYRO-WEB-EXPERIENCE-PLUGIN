"""Deterministic component-foundry normalization and audit.

Provider metadata and compact component definitions are untrusted inputs until
this module expands them into P01 ComponentManifest objects and verifies exact
commit/license closure.  Passing this audit does not certify rendered behavior;
Storybook and browser oracles remain mandatory later gates.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .web_contracts import canonical_bytes, component_catalog_sha256, content_sha256, validate_document


CATALOG_VERSION = "1.0"
EXPECTED_COMPONENTS = 30
LICENSE_ALLOWLIST = frozenset({"MIT", "ISC"})
SHA40 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class CatalogAudit:
    passed: bool
    violations: tuple[str, ...]
    catalog_sha256: str
    component_count: int


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_catalog(
    providers_path: Path, components_path: Path
) -> tuple[dict[str, Any], CatalogAudit]:
    providers_doc = _load_json(providers_path)
    source = _load_json(components_path)
    violations: list[str] = []
    if providers_doc.get("schema_version") != CATALOG_VERSION:
        violations.append("provider lock schema_version mismatch")
    if source.get("schema_version") != CATALOG_VERSION:
        violations.append("component source schema_version mismatch")

    provider_rows = providers_doc.get("providers", [])
    providers: dict[str, Mapping[str, Any]] = {}
    for row in provider_rows if isinstance(provider_rows, list) else []:
        provider_id = row.get("id")
        if not isinstance(provider_id, str) or not provider_id:
            violations.append("provider has invalid id")
            continue
        if provider_id in providers:
            violations.append(f"duplicate provider {provider_id}")
        providers[provider_id] = row
        if SHA40.fullmatch(str(row.get("commit", ""))) is None:
            violations.append(f"provider {provider_id} is not pinned to a 40-character commit")
        if row.get("license") not in LICENSE_ALLOWLIST:
            violations.append(f"provider {provider_id} license is not allowlisted")
        if SHA256.fullmatch(str(row.get("license_sha256", ""))) is None:
            violations.append(f"provider {provider_id} license hash is invalid")
        for field in ("repository", "license_url"):
            if not str(row.get(field, "")).startswith("https://"):
                violations.append(f"provider {provider_id} {field} must be HTTPS")

    source_provider = source.get("provider")
    if source_provider not in providers:
        violations.append(f"unknown source provider {source_provider!r}")
        provider: Mapping[str, Any] = {}
    else:
        provider = providers[source_provider]
    dependency_pins = [
        f"{row['id']}@commit:{row['commit']}" for row in sorted(providers.values(), key=lambda item: item["id"])
    ]

    compact_rows = source.get("components", [])
    if not isinstance(compact_rows, list):
        violations.append("components must be an array")
        compact_rows = []
    if len(compact_rows) != EXPECTED_COMPONENTS:
        violations.append(
            f"catalog must contain exactly {EXPECTED_COMPONENTS} MVP components, found {len(compact_rows)}"
        )
    ids = [row.get("id") for row in compact_rows if isinstance(row, dict)]
    if len(ids) != len(set(ids)):
        violations.append("component ids must be unique")
    known_ids = {str(item) for item in ids}

    manifests: list[dict[str, Any]] = []
    for row in compact_rows:
        if not isinstance(row, dict):
            violations.append("component row must be an object")
            continue
        manifest = {
            "schema_version": "1.0",
            "component_id": row.get("id"),
            "provider": source_provider,
            "version": source.get("version"),
            "commit": provider.get("commit"),
            "license": provider.get("license"),
            "framework": "react-vite",
            "role": row.get("role"),
            "props": row.get("props", {}),
            "slots": row.get("slots", []),
            "events": row.get("events", []),
            "states": row.get("states", []),
            "allowed_parents": row.get("parents", []),
            "allowed_children": row.get("children", []),
            "required_descendants": row.get("required", []),
            "dependencies": dependency_pins,
            "evidence_refs": [provider.get("license_sha256")],
        }
        for issue in validate_document("component_manifest", manifest):
            violations.append(f"component {row.get('id')}: {issue}")
        for relation in ("allowed_parents", "allowed_children", "required_descendants"):
            unknown = set(manifest[relation]) - known_ids
            if unknown:
                violations.append(f"component {row.get('id')} {relation} has unknown IDs {sorted(unknown)}")
        if not manifest["states"]:
            violations.append(f"component {row.get('id')} has no modeled states")
        if not set(manifest["required_descendants"]).issubset(manifest["allowed_children"]):
            violations.append(f"component {row.get('id')} requires a descendant it does not allow")
        manifests.append(manifest)

    by_id = {row["component_id"]: row for row in manifests}
    required_profiles = {
        "dialog": ({"closed", "open"}, {"dialog_title", "dialog_description"}),
        "data_table": ({"loading", "empty", "ready", "error"}, set()),
        "form": ({"idle", "submitting", "success", "error"}, {"form_field"}),
        "button": ({"idle", "focus", "disabled"}, set()),
    }
    for component_id, (states, descendants) in required_profiles.items():
        row = by_id.get(component_id)
        if row is None:
            violations.append(f"required profile component missing: {component_id}")
            continue
        missing_states = states - set(row["states"])
        missing_descendants = descendants - set(row["required_descendants"])
        if missing_states:
            violations.append(f"component {component_id} missing states {sorted(missing_states)}")
        if missing_descendants:
            violations.append(f"component {component_id} missing descendants {sorted(missing_descendants)}")

    manifests.sort(key=lambda item: item["component_id"])
    providers_sorted = sorted(provider_rows, key=lambda item: item["id"])
    catalog_hash = component_catalog_sha256(manifests)
    payload = {
        "schema_version": CATALOG_VERSION,
        "catalog_id": "luxeron.web-experience.mvp.v1",
        "providers": providers_sorted,
        "components": manifests,
        "component_catalog_sha256": catalog_hash,
        "provider_lock_sha256": content_sha256(providers_sorted),
    }
    audit = CatalogAudit(not violations, tuple(violations), catalog_hash, len(manifests))
    return payload, audit


def write_catalog_lock(output: Path, payload: Mapping[str, Any], audit: CatalogAudit) -> None:
    if not audit.passed:
        raise ValueError("catalog audit failed: " + "; ".join(audit.violations))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_bytes(payload) + b"\n")
