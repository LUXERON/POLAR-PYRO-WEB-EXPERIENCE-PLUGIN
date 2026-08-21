"""Closed-alphabet Qwen3-0.6B UX-binding transducer."""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class WebBindingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BindingEvidence:
    binding: Mapping[str, Any]
    model: str
    repaired: bool = False


def binding_schema(
    application_id: str,
    route_ids: Sequence[str],
    archetypes: Sequence[str],
    design_languages: Sequence[str],
    recipes: Sequence[str],
) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["schema_version", "application_id", "archetype_id", "design_language_id", "view_recipes", "confidence", "evidence_refs", "abstain"],
        "properties": {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "application_id": {"type": "string", "enum": [application_id]},
            "archetype_id": {"type": "string", "enum": list(archetypes)},
            "design_language_id": {"type": "string", "enum": list(design_languages)},
            "view_recipes": {
                "type": "object", "additionalProperties": False, "required": list(route_ids),
                "properties": {route: {"type": "string", "enum": list(recipes)} for route in route_ids},
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "abstain": {"type": "boolean"},
        },
    }


def generate_binding(
    *, base_url: str, model: str, intent: str, application_id: str,
    route_ids: Sequence[str], archetype_recipes: Mapping[str, Sequence[str]],
    design_languages: Sequence[str], timeout: float = 90,
) -> BindingEvidence:
    archetypes = sorted(archetype_recipes)
    recipes = sorted({recipe for values in archetype_recipes.values() for recipe in values})
    schema = binding_schema(application_id, sorted(route_ids), archetypes, sorted(design_languages), recipes)
    catalog = {key: list(archetype_recipes[key]) for key in archetypes}
    body = {
        "model": model, "temperature": 0, "max_tokens": 500,
        "messages": [
            {"role": "system", "content": "You are an untrusted UX slot filler. Select only exact catalog values. Set abstain=false when the intent explicitly names an available archetype or recipe. Set abstain=true only when no unique compatible selection exists. evidence_refs must be empty because no evidence catalog is supplied. Emit one JSON object and no prose."},
            {"role": "user", "content": f"APPLICATION={application_id}\nROUTES={json.dumps(sorted(route_ids))}\nARCHETYPE_RECIPES={json.dumps(catalog,sort_keys=True)}\nDESIGN_LANGUAGES={json.dumps(sorted(design_languages))}\nINTENT={intent}"},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "ux_binding", "strict": True, "schema": schema}},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = urllib.request.Request(base_url.rstrip("/")+"/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type":"application/json","Authorization":"Bearer local"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw=json.load(response)["choices"][0]["message"]["content"]
        value=json.loads(raw)
    except Exception as exc:
        raise WebBindingError(f"live inference failed: {type(exc).__name__}") from exc
    if value.get("application_id") != application_id or set(value.get("view_recipes",{})) != set(route_ids):
        raise WebBindingError("model binding escaped frozen application/route closure")
    chosen_archetype=value.get("archetype_id")
    if chosen_archetype not in archetype_recipes:
        raise WebBindingError("model selected unknown archetype")
    if any(recipe not in archetype_recipes[chosen_archetype] for recipe in value["view_recipes"].values()):
        raise WebBindingError("model selected recipe outside chosen archetype")
    return BindingEvidence(value, model)
