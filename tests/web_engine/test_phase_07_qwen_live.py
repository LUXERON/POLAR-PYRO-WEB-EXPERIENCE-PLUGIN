from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from qwen_harness.web_binding import binding_schema, generate_binding


ROOT=Path(__file__).resolve().parents[2]
UX=json.loads((ROOT/"catalog/web_experience/ux-catalog.source.json").read_text(encoding="utf-8"))
DESIGNS=json.loads((ROOT/"catalog/web_experience/design-languages.json").read_text(encoding="utf-8"))["design_languages"]
ARCH={item["id"]:item["view_recipes"] for item in UX["archetypes"]}


def test_binding_grammar_closes_routes_and_catalog_values()->None:
    schema=binding_schema("fixture",["dashboard"],list(ARCH),[item["design_language_id"] for item in DESIGNS],sorted({r for v in ARCH.values() for r in v}))
    assert schema["properties"]["application_id"]["enum"]==["fixture"]
    assert schema["properties"]["view_recipes"]["required"]==["dashboard"]
    assert schema["properties"]["view_recipes"]["additionalProperties"] is False


def test_live_qwen06_selects_closed_incident_binding()->None:
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/v1/models",timeout=3).close()
    except OSError:
        pytest.fail("live vLLM Qwen3-0.6B endpoint unavailable; P07 is NO_RESULT")
    result=generate_binding(base_url="http://127.0.0.1:8000",model="Qwen/Qwen3-0.6B",intent="Use the incident_response_workspace archetype and incident_queue_detail recipe for incident triage, attributed evidence timelines, independent approvals, retention holds and safe closure.",application_id="incident.casebook",route_ids=["incidents"],archetype_recipes=ARCH,design_languages=[item["design_language_id"] for item in DESIGNS])
    assert result.binding["abstain"] is False
    assert result.binding["archetype_id"]=="incident_response_workspace"
    assert result.binding["view_recipes"]["incidents"] in ARCH["incident_response_workspace"]
