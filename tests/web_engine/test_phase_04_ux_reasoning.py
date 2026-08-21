from __future__ import annotations

from dataclasses import dataclass

import pytest

from polar_pyro_web_experience.web_contracts import validate_document
from polar_pyro_web_experience.web_ux_compiler import (
    UXCompileError,
    compile_euclid_ux_requests,
    compile_ux_contract,
    qualify_ux_reasoning,
)


CAPABILITY = {
    "application_id": "casebook",
    "routes": [{"id": "dashboard"}],
    "roles": [{"id": "administrator"}],
    "queries": [{"id": "list_cases"}],
    "commands": [{"id": "create_case"}],
}
BINDING = {"application_id": "casebook", "view_recipes": {"dashboard": "case_queue_detail"}}
JOURNEYS = [
    {
        "id": "create_case_journey",
        "task_id": "manage_cases",
        "role_ids": ["administrator"],
        "entry_route": "dashboard",
        "recovery_route": "dashboard",
        "success_state": "case_created",
        "query_ids": ["list_cases"],
        "command_ids": ["create_case"],
        "steps": [
            {"id": "inspect", "route_id": "dashboard", "state": "ready"},
            {"id": "submit", "route_id": "dashboard", "state": "submitting", "command_id": "create_case"},
        ],
    }
]


@dataclass
class Outcome:
    status: str = "PROVED"
    certificates: tuple[str, ...] = ("proof.cert",)
    receipt: str = "proof.reasoning.json"


class FakeReasoner:
    def __init__(self, outcome: Outcome | None = None) -> None:
        self.outcome = outcome or Outcome()
        self.requests = []

    def reason(self, request):
        self.requests.append(request)
        return self.outcome


def test_compiler_covers_routes_tasks_states_and_schema() -> None:
    contract = compile_ux_contract(CAPABILITY, BINDING, JOURNEYS)

    assert not validate_document("ux_contract", contract)
    assert contract["routes"][0]["visible_to"] == ["administrator"]
    assert contract["routes"][0]["primary_task_ids"] == ["manage_cases"]
    assert set(contract["content_states"]["dashboard"]) == {
        "loading", "empty", "ready", "error", "recovering", "forbidden"
    }


def test_unknown_command_poison_is_rejected_before_reasoning() -> None:
    poisoned = [dict(JOURNEYS[0], command_ids=["delete_everything"])]

    with pytest.raises(UXCompileError, match="unknown command"):
        compile_ux_contract(CAPABILITY, BINDING, poisoned)


def test_euclid_adapter_emits_plan_and_recovery_liveness_obligations() -> None:
    contract = compile_ux_contract(CAPABILITY, BINDING, JOURNEYS)
    requests = compile_euclid_ux_requests(contract)

    assert [item["mode"] for item in requests] == ["plan", "fsm"]
    assert requests[0]["goals"] == ["create_case_journey_success()"]
    assert requests[1]["operation"] == "liveness"
    assert {"success", "recovered"} == set(requests[1]["halting"])
    assert any(item["event"] == "recover" for item in requests[1]["transitions"])


def test_reasoning_qualification_requires_proof_and_replayable_certificate() -> None:
    requests = compile_euclid_ux_requests(compile_ux_contract(CAPABILITY, BINDING, JOURNEYS))
    passing = qualify_ux_reasoning(FakeReasoner(), requests)
    failed = qualify_ux_reasoning(
        FakeReasoner(Outcome(status="NO_RESULT", certificates=())), requests
    )

    assert passing.passed
    assert len(passing.receipts) == 2
    assert not failed.passed
    assert any("NO_RESULT" in item for item in failed.violations)
    assert any("no replayable certificate" in item for item in failed.violations)


def test_empty_or_route_incomplete_journeys_fail_closed() -> None:
    with pytest.raises(UXCompileError, match="non-vacuous journey"):
        compile_ux_contract(CAPABILITY, BINDING, [])
    incomplete_capability = dict(CAPABILITY, routes=[{"id": "dashboard"}, {"id": "settings"}])
    incomplete_binding = dict(BINDING, view_recipes={"dashboard": "case_queue_detail", "settings": "settings"})
    with pytest.raises(UXCompileError, match="routes have no primary task"):
        compile_ux_contract(incomplete_capability, incomplete_binding, JOURNEYS)
