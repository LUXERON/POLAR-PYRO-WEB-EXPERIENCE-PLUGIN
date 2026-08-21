"""Deterministic UI-plan solver and React/Vite materializer.

The renderer proves a narrow fact: a closed, validated UI plan can be mapped to
owned React source without executing model-authored markup, styles, URLs, package
names, or scripts. Browser behavior and subjective quality belong to later gates.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .web_contracts import canonical_bytes, component_catalog_sha256, content_sha256


SAFE_ID = re.compile(r"[a-z][a-z0-9._-]*")
RECIPE_COMPONENT = {
    "metric_grid": "metric_card",
    "data_table_detail_drawer": "data_table",
    "timeline_workspace": "card",
    "editor_evidence_split": "form",
    "simulation_results": "data_table",
    "revision_compare": "tabs",
    "input_canvas_results": "form",
    "result_inspector": "card",
    "infeasibility_evidence": "alert",
    "stream_health": "metric_card",
    "search_results_inspector": "data_table",
    "index_diagnostics": "card",
    "constraint_editor_timeline": "form",
    "conflict_inspector": "alert",
    "schedule_compare": "tabs",
    "grammar_editor_tree": "form",
    "proof_inspector": "card",
    "counterexample_panel": "alert",
    "availability_calendar": "card",
    "reservation_form": "form",
    "booking_detail": "card",
    "case_queue_detail": "data_table",
    "evidence_timeline": "card",
    "independent_decision_panel": "form",
    "fleet_health_grid": "metric_card",
    "work_order_workspace": "form",
    "maintenance_schedule": "data_table",
    "incident_queue_detail": "data_table",
    "approval_and_retention": "form",
}


class RendererError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RenderReceipt:
    renderer: str
    input_sha256: str
    output_sha256: str
    file_hashes: Mapping[str, str]
    plan_to_source: Mapping[str, str]
    trust_boundary: str = (
        "Proves deterministic source materialization from the admitted plan only; "
        "browser behavior, backend correctness, and aesthetic quality are not proved."
    )


def _ids(rows: Any) -> set[str]:
    return {str(row["id"]) for row in rows if isinstance(row, dict) and "id" in row}


def solve_ui_plan(
    capability: Mapping[str, Any],
    ux_contract: Mapping[str, Any],
    binding: Mapping[str, Any],
    components: Sequence[Mapping[str, Any]],
    design_language: Mapping[str, Any],
) -> dict[str, Any]:
    """Choose one admitted component per route with stable lexical tie-breaking."""
    app_id = capability.get("application_id")
    if app_id != ux_contract.get("application_id") or app_id != binding.get("application_id"):
        raise RendererError("application_id closure failed")
    routes = sorted(_ids(capability.get("routes", [])))
    if not routes or set(binding.get("view_recipes", {})) != set(routes):
        raise RendererError("view recipes must cover exactly the capability routes")
    component_ids = {str(item.get("component_id")) for item in components}
    query_ids = _ids(capability.get("queries", []))
    command_ids = _ids(capability.get("commands", []))
    plan_routes: list[dict[str, Any]] = []
    for route in routes:
        recipe = str(binding["view_recipes"][route])
        component = RECIPE_COMPONENT.get(recipe)
        if component is None:
            raise RendererError(f"unknown recipe: {recipe}")
        if component not in component_ids:
            raise RendererError(f"recipe component is absent from catalog: {component}")
        route_tasks = [
            task for task in ux_contract.get("tasks", []) if task.get("entry_route") == route
        ]
        admitted_queries = sorted({item for task in route_tasks for item in task.get("query_ids", [])})
        admitted_commands = sorted({item for task in route_tasks for item in task.get("command_ids", [])})
        if set(admitted_queries) - query_ids or set(admitted_commands) - command_ids:
            raise RendererError(f"route {route} bindings escape capability alphabet")
        plan_routes.append(
            {
                "route_id": route,
                "recipe_id": recipe,
                "regions": [{
                    "id": f"{route}.primary",
                    "component_id": component,
                    "query_ids": admitted_queries,
                    "command_ids": admitted_commands,
                    "children": [],
                }],
            }
        )
    return {
        "schema_version": "1.0",
        "application_id": app_id,
        "design_language_id": design_language["design_language_id"],
        "ux_contract_sha256": content_sha256(ux_contract),
        "component_catalog_sha256": component_catalog_sha256(components),
        "routes": plan_routes,
    }


def _validate_materialization_inputs(plan: Mapping[str, Any], capability: Mapping[str, Any]) -> None:
    if plan.get("application_id") != capability.get("application_id"):
        raise RendererError("plan/capability application_id mismatch")
    route_ids = _ids(capability.get("routes", []))
    query_ids = _ids(capability.get("queries", []))
    command_ids = _ids(capability.get("commands", []))
    seen: set[str] = set()
    for route in plan.get("routes", []):
        route_id = route.get("route_id")
        if not isinstance(route_id, str) or SAFE_ID.fullmatch(route_id) is None or route_id not in route_ids:
            raise RendererError(f"unknown or unsafe route: {route_id!r}")
        if route_id in seen:
            raise RendererError(f"duplicate route: {route_id}")
        seen.add(route_id)
        for region in route.get("regions", []):
            if set(region.get("query_ids", [])) - query_ids:
                raise RendererError(f"region {region.get('id')} contains unknown query")
            if set(region.get("command_ids", [])) - command_ids:
                raise RendererError(f"region {region.get('id')} contains unknown command")
    if seen != route_ids:
        raise RendererError("plan does not cover exactly the capability routes")


def _tree_hash(root: Path) -> tuple[str, dict[str, str]]:
    hashes: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return content_sha256(hashes), hashes


def materialize_react_vite(
    plan: Mapping[str, Any],
    capability: Mapping[str, Any],
    design_language: Mapping[str, Any],
    output: Path,
    *,
    template_root: Path | None = None,
) -> RenderReceipt:
    """Materialize only frozen templates plus canonical data files."""
    _validate_materialization_inputs(plan, capability)
    if plan.get("design_language_id") != design_language.get("design_language_id"):
        raise RendererError("design language mismatch")
    root = template_root or Path(__file__).resolve().parents[2] / "renderers" / "react-vite"
    required = {"package.json", "index.html", "tsconfig.json", "vite.config.ts", "src/main.tsx", "src/styles.css"}
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if not required <= actual:
        raise RendererError(f"renderer template incomplete: {sorted(required - actual)}")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(root, output, ignore=shutil.ignore_patterns("node_modules", "dist", "*.tsbuildinfo"))
    generated = output / "src" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "ui-plan.json").write_bytes(canonical_bytes(plan) + b"\n")
    (generated / "capability.json").write_bytes(canonical_bytes(capability) + b"\n")
    (generated / "design-language.json").write_bytes(canonical_bytes(design_language) + b"\n")
    mapping = {
        region["id"]: "src/main.tsx#Region"
        for route in plan["routes"] for region in route["regions"]
    }
    (generated / "plan-to-source.json").write_bytes(canonical_bytes(mapping) + b"\n")
    output_hash, file_hashes = _tree_hash(output)
    return RenderReceipt(
        renderer="luxeron.react-vite.closed-data.v1",
        input_sha256=content_sha256({"plan": plan, "capability": capability, "design_language": design_language}),
        output_sha256=output_hash,
        file_hashes=file_hashes,
        plan_to_source=mapping,
    )
