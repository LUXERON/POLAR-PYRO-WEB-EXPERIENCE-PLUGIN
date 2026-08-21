"""Deterministic UX contract compiler and Euclid-Ω request adapter."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


SAFE = re.compile(r"[a-z][a-z0-9_]*")
CONTENT_STATES = ["loading", "empty", "ready", "error", "recovering", "forbidden"]


class UXCompileError(ValueError):
    pass


class ReasoningOutcome(Protocol):
    status: str
    certificates: tuple[str, ...]
    receipt: str


class UXReasoner(Protocol):
    def reason(self, request: Mapping[str, Any]) -> ReasoningOutcome:
        ...


@dataclass(frozen=True, slots=True)
class UXReasoningReport:
    passed: bool
    receipts: tuple[str, ...]
    violations: tuple[str, ...]
    bounds: tuple[str, ...] = (
        "Proofs establish reachability and abstract recovery in the compiled UX model, not rendered browser behavior.",
        "Permission closure is recomputed deterministically; it is not inferred from visual appearance.",
    )


def _ids(rows: Any, key: str = "id") -> set[str]:
    return {str(item[key]) for item in rows if isinstance(item, dict) and key in item}


def _safe(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]", "_", value.lower())
    if SAFE.fullmatch(normalized) is None:
        raise UXCompileError(f"identifier cannot be compiled safely: {value!r}")
    return normalized


def compile_ux_contract(
    capability: Mapping[str, Any],
    binding: Mapping[str, Any],
    journey_specs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compile trusted journey templates against a frozen capability alphabet."""
    if capability.get("application_id") != binding.get("application_id"):
        raise UXCompileError("binding application_id does not match capability manifest")
    route_ids = _ids(capability.get("routes", []))
    role_ids = _ids(capability.get("roles", []))
    query_ids = _ids(capability.get("queries", []))
    command_ids = _ids(capability.get("commands", []))
    if set(binding.get("view_recipes", {})) != route_ids:
        raise UXCompileError("binding recipes must cover exactly the capability routes")
    if not journey_specs:
        raise UXCompileError("at least one non-vacuous journey is required")

    tasks: list[dict[str, Any]] = []
    journeys: list[dict[str, Any]] = []
    route_tasks: dict[str, list[str]] = {route: [] for route in route_ids}
    route_roles: dict[str, set[str]] = {route: set() for route in route_ids}
    seen_tasks: set[str] = set()
    seen_journeys: set[str] = set()
    for spec in journey_specs:
        task_id = str(spec.get("task_id", ""))
        journey_id = str(spec.get("id", ""))
        if not SAFE.fullmatch(task_id) or not SAFE.fullmatch(journey_id):
            raise UXCompileError("task and journey IDs must use the closed identifier alphabet")
        if task_id in seen_tasks or journey_id in seen_journeys:
            raise UXCompileError("task and journey IDs must be unique")
        seen_tasks.add(task_id)
        seen_journeys.add(journey_id)
        entry_route = spec.get("entry_route")
        recovery_route = spec.get("recovery_route")
        roles = list(spec.get("role_ids", []))
        queries = list(spec.get("query_ids", []))
        commands = list(spec.get("command_ids", []))
        if entry_route not in route_ids or recovery_route not in route_ids:
            raise UXCompileError(f"journey {journey_id} references an unknown route")
        if set(roles) - role_ids:
            raise UXCompileError(f"journey {journey_id} references an unknown role")
        if set(queries) - query_ids:
            raise UXCompileError(f"journey {journey_id} references an unknown query")
        if set(commands) - command_ids:
            raise UXCompileError(f"journey {journey_id} references an unknown command")
        steps = list(spec.get("steps", []))
        if not steps:
            raise UXCompileError(f"journey {journey_id} has no live steps")
        for step in steps:
            if step.get("route_id") not in route_ids:
                raise UXCompileError(f"journey {journey_id} step references an unknown route")
            command_id = step.get("command_id")
            if command_id is not None and command_id not in commands:
                raise UXCompileError(f"journey {journey_id} step command is not admitted by its task")
        success_state = str(spec.get("success_state", ""))
        if SAFE.fullmatch(success_state) is None:
            raise UXCompileError(f"journey {journey_id} has invalid success state")
        tasks.append(
            {
                "id": task_id,
                "role_ids": roles,
                "entry_route": entry_route,
                "success_state": success_state,
                "command_ids": commands,
                "query_ids": queries,
            }
        )
        journeys.append(
            {
                "id": journey_id,
                "task_id": task_id,
                "steps": steps,
                "terminal_state": success_state,
                "recovery_route": recovery_route,
            }
        )
        route_tasks[entry_route].append(task_id)
        route_roles[entry_route].update(roles)

    uncovered = sorted(route for route, task_list in route_tasks.items() if not task_list)
    if uncovered:
        raise UXCompileError(f"routes have no primary task: {uncovered}")
    routes = [
        {
            "route_id": route,
            "visible_to": sorted(route_roles[route]),
            "primary_task_ids": sorted(route_tasks[route]),
        }
        for route in sorted(route_ids)
    ]
    return {
        "schema_version": "1.0",
        "application_id": capability["application_id"],
        "routes": routes,
        "tasks": sorted(tasks, key=lambda item: item["id"]),
        "journeys": sorted(journeys, key=lambda item: item["id"]),
        "content_states": {route: CONTENT_STATES for route in sorted(route_ids)},
    }


def compile_euclid_ux_requests(ux_contract: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Compile each journey into proof-bearing planning and recovery FSM obligations."""
    requests: list[dict[str, Any]] = []
    for journey in ux_contract.get("journeys", []):
        journey_id = _safe(str(journey["id"]))
        steps = journey["steps"]
        start = f"{journey_id}_start()"
        goal = f"{journey_id}_success()"
        fluents = [start]
        actions: list[dict[str, Any]] = []
        previous = start
        fsm_states = ["start"]
        fsm_transitions: list[dict[str, str]] = []
        for index, step in enumerate(steps):
            step_state = f"step_{index}"
            fluent = f"{journey_id}_{step_state}()"
            action_name = _safe(f"{journey_id}_{step['id']}")
            fluents.append(fluent)
            actions.append({"name": action_name, "pre": [previous], "add": [fluent], "delete": [previous]})
            fsm_states.append(step_state)
            fsm_transitions.append(
                {"from": "start" if index == 0 else f"step_{index-1}", "event": action_name, "to": step_state}
            )
            previous = fluent
        fluents.append(goal)
        actions.append(
            {"name": f"complete_{journey_id}", "pre": [previous], "add": [goal], "delete": [previous]}
        )
        fsm_states.extend(["success", "error", "recovered"])
        fsm_transitions.append(
            {"from": f"step_{len(steps)-1}", "event": "complete", "to": "success"}
        )
        for state in ["start", *(f"step_{index}" for index in range(len(steps)) )]:
            fsm_transitions.append({"from": state, "event": "error", "to": "error"})
        fsm_transitions.extend(
            [
                {"from": "error", "event": "recover", "to": "recovered"},
                {"from": "recovered", "event": "retry", "to": "start"},
            ]
        )
        requests.append(
            {
                "mode": "plan",
                "fluents": fluents,
                "initial": [start],
                "actions": actions,
                "goals": [goal],
                "max_depth": len(actions) + 2,
            }
        )
        requests.append(
            {
                "mode": "fsm",
                "operation": "liveness",
                "states": fsm_states,
                "initial": "start",
                "transitions": fsm_transitions,
                "halting": ["success", "recovered"],
            }
        )
    if not requests:
        raise UXCompileError("cannot reason over an empty journey set")
    return tuple(requests)


def qualify_ux_reasoning(reasoner: UXReasoner, requests: Sequence[Mapping[str, Any]]) -> UXReasoningReport:
    receipts: list[str] = []
    violations: list[str] = []
    for index, request in enumerate(requests):
        outcome = reasoner.reason(request)
        if outcome.status != "PROVED":
            violations.append(f"obligation {index} returned {outcome.status}")
        if not outcome.certificates:
            violations.append(f"obligation {index} has no replayable certificate")
        if outcome.receipt:
            receipts.append(outcome.receipt)
    return UXReasoningReport(not violations, tuple(receipts), tuple(violations))
