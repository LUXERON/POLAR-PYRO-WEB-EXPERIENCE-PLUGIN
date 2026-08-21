"""Provider-neutral, closed-alphabet design planning for real applications."""
from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


DESIGN_LANGUAGES = ("editorial_pearl", "midnight_intimacy", "warm_minimal")
DENSITIES = ("calm", "balanced", "compact")
EMPHASES = ("safety", "compatibility", "conversation")
NAV_MODELS = ("journey", "functional")

ROUTE_RECIPES: Mapping[str, tuple[str, ...]] = {
    "discover": ("editorial_discovery_canvas", "discovery_mosaic"),
    "matches": ("match_gallery", "relationship_pipeline"),
    "messages": ("conversation_inbox", "message_activity"),
    "conversation": ("focused_conversation", "contextual_conversation"),
    "plans": ("plan_board", "plan_timeline"),
    "plan_detail": ("plan_detail", "safety_plan_detail"),
    "safety": ("trust_center", "safety_action_center"),
    "profile": ("editorial_profile", "profile_workbench"),
    "preferences": ("preference_controls", "compatibility_preferences"),
    "verification": ("verification_flow", "trust_evidence"),
    "subscription": ("subscription_cards", "membership_comparison"),
    "moderation": ("moderation_queue", "evidence_review"),
}
FALLBACK_RECIPES = ("record_collection", "record_workbench")


class DesignPlanningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DesignEvidence:
    design_ir: Mapping[str, Any]
    model: str
    request_sha256: str
    response_sha256: str
    attempts: int = 1


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def route_catalog(route_ids: Sequence[str]) -> dict[str, tuple[str, ...]]:
    return {route: ROUTE_RECIPES.get(route, FALLBACK_RECIPES) for route in sorted(route_ids)}


def design_schema(product_id: str, routes: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "product_id", "design_language", "density", "emphasis", "nav_model", "route_recipes", "confidence", "abstain"],
        "properties": {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "product_id": {"type": "string", "enum": [product_id]},
            "design_language": {"type": "string", "enum": list(DESIGN_LANGUAGES)},
            "density": {"type": "string", "enum": list(DENSITIES)},
            "emphasis": {"type": "string", "enum": list(EMPHASES)},
            "nav_model": {"type": "string", "enum": list(NAV_MODELS)},
            "route_recipes": {
                "type": "object",
                "additionalProperties": False,
                "required": list(routes),
                "properties": {route: {"type": "string", "enum": list(options)} for route, options in routes.items()},
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "abstain": {"type": "boolean"},
        },
    }


def generate_design_ir(*, base_url: str, model: str, manifest: Mapping[str, Any], timeout: float = 180, max_attempts: int = 3) -> DesignEvidence:
    product_id = str(manifest["product_id"])
    route_ids = [str(item["id"]) for item in manifest["routes"]]
    catalog = route_catalog(route_ids)
    schema = design_schema(product_id, catalog)
    request_payload = {
        "product_id": product_id,
        "name": manifest["name"],
        "thesis": manifest["distinctive_product_thesis"],
        "routes": route_ids,
        "critical_journeys": manifest["critical_journeys"],
        "design_languages": DESIGN_LANGUAGES,
        "route_recipe_catalog": catalog,
    }
    system = "You are an untrusted product-experience slot filler. Choose only exact values from the supplied closed catalogs. Cover every route exactly once. Prefer a coherent, premium, application-specific experience over a dashboard. Set abstain=true only if the contract cannot be represented. Output one JSON object and no prose."
    residual: list[str] = []
    last_error = "no attempt"
    for attempt in range(1, max(1, max_attempts) + 1):
        user_payload: dict[str, Any] = dict(request_payload)
        if residual:
            user_payload["previous_residual"] = residual
            user_payload["repair_instruction"] = "Return the complete corrected object. The supplied route catalog covers every route, so abstention is invalid."
        body = {
            "model": model,
            "temperature": 0,
            "max_tokens": 900,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user_payload, sort_keys=True, ensure_ascii=False)}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "real_app_design_ir", "strict": True, "schema": schema}},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request_bytes = canonical(body)
        request = urllib.request.Request(base_url.rstrip("/") + "/v1/chat/completions", data=request_bytes, headers={"Authorization": "Bearer local", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = str(json.load(response)["choices"][0]["message"]["content"])
            value = json.loads(raw)
        except Exception as exc:
            residual = [f"transport or JSON failure: {type(exc).__name__}"]
            last_error = f"live design inference failed: {type(exc).__name__}: {exc}"
            continue
        violations: list[str] = []
        if value.get("product_id") != product_id:
            violations.append("product_id escaped the frozen contract")
        if set(value.get("route_recipes", {})) != set(catalog):
            violations.append("route recipe closure failed")
        for route, recipe in value.get("route_recipes", {}).items():
            if route not in catalog or recipe not in catalog[route]:
                violations.append(f"off-catalog route recipe: {route}={recipe}")
        if value.get("abstain") is not False:
            violations.append("model abstained despite complete catalog coverage")
        if not violations:
            return DesignEvidence(value, model, _sha(request_bytes), _sha(raw.encode("utf-8")), attempt)
        residual = violations
        last_error = "; ".join(violations)
    raise DesignPlanningError(f"design binding failed after {max_attempts} attempt(s): {last_error}")
