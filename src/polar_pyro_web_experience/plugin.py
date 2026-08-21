"""Polar Pyro native capability adapter for the Web Experience Engine."""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from .web_contracts import content_sha256
from .web_renderer import RendererError, solve_ui_plan
from .web_ux_compiler import UXCompileError, compile_euclid_ux_requests, compile_ux_contract


_FIELDS = {"capability", "binding", "journeys", "components", "design_language"}


def compile_experience(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compile a closed semantic contract into a UI plan and proof obligations."""

    unknown = sorted(set(payload) - _FIELDS)
    missing = sorted(_FIELDS - set(payload))
    if unknown or missing:
        return {
            "schema_version": "polar.web-experience-receipt/v1",
            "status": "FAIL",
            "error": {"code": "CLOSED_INPUT", "unknown": unknown, "missing": missing},
            "evidence": [],
        }
    try:
        capability = payload["capability"]
        binding = payload["binding"]
        journeys = payload["journeys"]
        components = payload["components"]
        design_language = payload["design_language"]
        if not isinstance(capability, Mapping) or not isinstance(binding, Mapping):
            raise UXCompileError("capability and binding must be objects")
        if not isinstance(journeys, list) or not isinstance(components, list):
            raise UXCompileError("journeys and components must be arrays")
        if not isinstance(design_language, Mapping):
            raise UXCompileError("design_language must be an object")
        contract = compile_ux_contract(capability, binding, journeys)
        obligations = list(compile_euclid_ux_requests(contract))
        plan = solve_ui_plan(capability, contract, binding, components, design_language)
    except (KeyError, TypeError, UXCompileError, RendererError) as exc:
        return {
            "schema_version": "polar.web-experience-receipt/v1",
            "status": "FAIL",
            "error": {"code": "COMPILATION_REJECTED", "message": str(exc)},
            "evidence": [],
        }
    output = {"ux_contract": contract, "euclid_obligations": obligations, "ui_plan": plan}
    return {
        "schema_version": "polar.web-experience-receipt/v1",
        "status": "PASS",
        "output": output,
        "evidence": [
            {"class": "web.closed_compilation", "sha256": content_sha256(output)},
            {"class": "web.euclid_obligations", "count": len(obligations), "sha256": content_sha256(obligations)},
        ],
        "limits": [
            "PASS proves deterministic closed compilation only.",
            "Euclid, browser, accessibility, mutation and release gates remain mandatory.",
        ],
    }


def main() -> int:
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise TypeError("request root must be an object")
        receipt = compile_experience(value)
    except (json.JSONDecodeError, TypeError) as exc:
        receipt = {
            "schema_version": "polar.web-experience-receipt/v1",
            "status": "FAIL",
            "error": {"code": "INVALID_REQUEST", "message": str(exc)},
            "evidence": [],
        }
    sys.stdout.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
