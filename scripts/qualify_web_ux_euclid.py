from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    harness_root = Path(__file__).resolve().parents[1]
    workspace = harness_root.parent
    sys.path.insert(0, str(harness_root / "src"))
    from polar_pyro_web_experience.euclid_bridge import EuclidOmegaBridge
    from polar_pyro_web_experience.web_ux_compiler import (
        compile_euclid_ux_requests,
        compile_ux_contract,
        qualify_ux_reasoning,
    )

    parser = argparse.ArgumentParser(description="Live Euclid qualification for compiled UX journeys")
    parser.add_argument("--bridge", default=str(workspace / "external" / "EUCLID-OMEGA" / "target" / "debug" / "eo-harness.exe"))
    parser.add_argument("--verifier", default=str(workspace / "external" / "EUCLID-OMEGA" / "target" / "debug" / "eo.exe"))
    parser.add_argument("--evidence", default=str(harness_root / "runtime" / "web-ux-euclid"))
    args = parser.parse_args()
    capability = {
        "application_id": "ux_euclid_qualification",
        "routes": [{"id": "workspace"}],
        "roles": [{"id": "operator"}],
        "queries": [{"id": "inspect_cases"}],
        "commands": [{"id": "resolve_case"}],
    }
    binding = {
        "application_id": "ux_euclid_qualification",
        "view_recipes": {"workspace": "case_queue_detail"},
    }
    journeys = [
        {
            "id": "resolve_case_journey",
            "task_id": "resolve_case_task",
            "role_ids": ["operator"],
            "entry_route": "workspace",
            "recovery_route": "workspace",
            "success_state": "case_resolved",
            "query_ids": ["inspect_cases"],
            "command_ids": ["resolve_case"],
            "steps": [
                {"id": "inspect", "route_id": "workspace", "state": "ready"},
                {"id": "resolve", "route_id": "workspace", "state": "submitting", "command_id": "resolve_case"},
            ],
        }
    ]
    contract = compile_ux_contract(capability, binding, journeys)
    requests = compile_euclid_ux_requests(contract)
    bridge = EuclidOmegaBridge(args.bridge, args.verifier, args.evidence)
    report = qualify_ux_reasoning(bridge, requests)
    payload = {
        "schema_version": "web-ux-euclid-qualification/v1",
        "passed": report.passed,
        "request_modes": [item["mode"] for item in requests],
        "receipts": list(report.receipts),
        "violations": list(report.violations),
        "bounds": list(report.bounds),
        "qualified_at": datetime.now(timezone.utc).isoformat(),
    }
    evidence_root = Path(args.evidence)
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "QUALIFICATION.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    document = [
        "# Web UX Euclid-Ω Qualification",
        "",
        f"- Live status: **{'PASS' if report.passed else 'FAIL'}**",
        f"- Qualified at: `{payload['qualified_at']}`",
        f"- Request modes: `{', '.join(payload['request_modes'])}`",
        f"- Replayable receipts: `{len(report.receipts)}`",
        "",
        "## Trust boundary",
        "",
        *[f"- {item}" for item in report.bounds],
        "",
        "## Evidence",
        "",
        *[f"- `{item}`" for item in report.receipts],
        "",
    ]
    (harness_root / "docs" / "WEB_UX_EUCLID_QUALIFICATION.md").write_text(
        "\n".join(document), encoding="utf-8", newline="\n"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
