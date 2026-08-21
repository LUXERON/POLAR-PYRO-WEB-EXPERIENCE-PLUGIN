"""Fail-closed production gauntlet for the Web Experience Engine.

The runner executes only reviewed argv arrays with ``shell=False``.  It records
phase and application commits atomically, rejects manifest drift on resume, and
cannot declare success until every machine gate and every human UI review passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


SCHEMA_VERSION = "1.0"
PENDING = "PENDING"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
MACHINE_FAILED = "MACHINE_FAILED"
MACHINE_PASSED = "MACHINE_PASSED"
AWAITING_HUMAN_UI_APPROVAL = "AWAITING_HUMAN_UI_APPROVAL"
HUMAN_REJECTED = "HUMAN_REJECTED"
SUCCESS = "SUCCESS"


class GauntletError(RuntimeError):
    """Raised when a manifest, gate, or state transition is invalid."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical(value) + b"\n")
    temporary.replace(path)


def _inside(root: Path, relative: str, *, label: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise GauntletError(f"{label} escapes workspace_root: {relative!r}") from exc
    return candidate


def _require_identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        raise GauntletError(f"{label} must be a non-empty identifier without whitespace")
    return value


def _validate_command(command: Mapping[str, Any], *, label: str) -> None:
    _require_identifier(command.get("id"), label=f"{label}.id")
    argv = command.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise GauntletError(f"{label}.argv must be a non-empty string array")
    cwd = command.get("cwd", ".")
    if not isinstance(cwd, str) or not cwd:
        raise GauntletError(f"{label}.cwd must be a non-empty relative path")
    timeout = command.get("timeout_seconds", 600)
    if not isinstance(timeout, int) or timeout < 1 or timeout > 86_400:
        raise GauntletError(f"{label}.timeout_seconds must be in [1, 86400]")


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the immutable execution contract without running its commands."""
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise GauntletError(f"schema_version must be {SCHEMA_VERSION!r}")
    phases = manifest.get("phases")
    applications = manifest.get("applications")
    requirements = manifest.get("requirements")
    if not isinstance(phases, list) or not phases:
        raise GauntletError("manifest must declare at least one phase")
    if not isinstance(applications, list) or not applications:
        raise GauntletError("manifest must declare test applications")
    if not isinstance(requirements, dict):
        raise GauntletError("manifest.requirements is required")

    phase_ids: set[str] = set()
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise GauntletError(f"phases[{index}] must be an object")
        phase_id = _require_identifier(phase.get("id"), label=f"phases[{index}].id")
        if phase_id in phase_ids:
            raise GauntletError(f"duplicate phase id: {phase_id}")
        phase_ids.add(phase_id)
        commands = phase.get("commands")
        if not isinstance(commands, list) or not commands:
            raise GauntletError(f"phase {phase_id} must have at least one live command gate")
        for command_index, command in enumerate(commands):
            if not isinstance(command, dict):
                raise GauntletError(f"phase {phase_id} command {command_index} must be an object")
            _validate_command(command, label=f"phase {phase_id} command {command_index}")
        artifacts = phase.get("required_artifacts", [])
        if not isinstance(artifacts, list) or any(not isinstance(item, str) or not item for item in artifacts):
            raise GauntletError(f"phase {phase_id}.required_artifacts must be a string array")

    seen: set[str] = set()
    for phase in phases:
        for dependency in phase.get("depends_on", []):
            if dependency not in phase_ids:
                raise GauntletError(f"phase {phase['id']} has unknown dependency {dependency!r}")
            if dependency not in seen:
                raise GauntletError(
                    f"phase {phase['id']} dependency {dependency!r} must appear earlier"
                )
        seen.add(phase["id"])

    app_ids: set[str] = set()
    counts = {"stateless": 0, "stateful": 0}
    for index, application in enumerate(applications):
        if not isinstance(application, dict):
            raise GauntletError(f"applications[{index}] must be an object")
        app_id = _require_identifier(application.get("id"), label=f"applications[{index}].id")
        if app_id in app_ids:
            raise GauntletError(f"duplicate application id: {app_id}")
        app_ids.add(app_id)
        kind = application.get("kind")
        if kind not in counts:
            raise GauntletError(f"application {app_id}.kind must be stateless or stateful")
        counts[kind] += 1
        gates = application.get("machine_gates")
        if not isinstance(gates, list) or not gates:
            raise GauntletError(f"application {app_id} must have at least one machine gate")
        for gate_index, gate in enumerate(gates):
            if not isinstance(gate, dict):
                raise GauntletError(f"application {app_id} gate {gate_index} must be an object")
            _validate_command(gate, label=f"application {app_id} gate {gate_index}")
        review_url = application.get("review_url")
        parsed = urlparse(review_url) if isinstance(review_url, str) else None
        if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise GauntletError(f"application {app_id}.review_url must be an HTTP(S) URL")

    for kind in counts:
        required = requirements.get(f"{kind}_applications")
        if not isinstance(required, int) or required < 0:
            raise GauntletError(f"requirements.{kind}_applications must be non-negative")
        if counts[kind] != required:
            raise GauntletError(
                f"manifest has {counts[kind]} {kind} apps; exact requirement is {required}"
            )


class WebExperienceGauntlet:
    """Checkpointed phase/app runner with an explicit human judgment boundary."""

    def __init__(self, manifest_path: Path, state_path: Path | None = None) -> None:
        self.manifest_path = manifest_path.resolve()
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        validate_manifest(self.manifest)
        root_value = self.manifest.get("workspace_root", ".")
        if not isinstance(root_value, str) or not root_value:
            raise GauntletError("workspace_root must be a non-empty path")
        self.workspace_root = (self.manifest_path.parent / root_value).resolve()
        if not self.workspace_root.is_dir():
            raise GauntletError(f"workspace_root does not exist: {self.workspace_root}")
        self.manifest_sha256 = _sha256(_canonical(self.manifest))
        self.state_path = (
            state_path.resolve()
            if state_path is not None
            else self.manifest_path.parent / ".gauntlet" / f"{self.manifest_path.stem}.state.json"
        )
        self.logs_root = self.state_path.parent / f"{self.manifest_path.stem}.logs"
        self.state = self._load_or_initialize_state()

    def _initial_state(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "manifest_sha256": self.manifest_sha256,
            "terminal_state": PENDING,
            "created_at": _now(),
            "updated_at": _now(),
            "phases": {phase["id"]: {"status": PENDING, "commands": []} for phase in self.manifest["phases"]},
            "applications": {
                app["id"]: {"status": PENDING, "machine_gates": [], "human_review": None}
                for app in self.manifest["applications"]
            },
        }

    def _load_or_initialize_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            state = self._initial_state()
            _write_json_atomic(self.state_path, state)
            return state
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("manifest_sha256") != self.manifest_sha256:
            raise GauntletError(
                "manifest drift detected; preserve the old state as evidence and start a new run"
            )
        return state

    def _save(self) -> None:
        self.state["updated_at"] = _now()
        _write_json_atomic(self.state_path, self.state)

    def _run_command(self, command: Mapping[str, Any], *, scope: str) -> dict[str, Any]:
        cwd = _inside(self.workspace_root, command.get("cwd", "."), label=f"{scope}.cwd")
        if not cwd.is_dir():
            raise GauntletError(f"{scope}.cwd does not exist: {cwd}")
        argv = list(command["argv"])
        started = _now()
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=command.get("timeout_seconds", 600),
                shell=False,
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            returncode = -1
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            timed_out = True
        result = {
            "id": command["id"],
            "argv": argv,
            "cwd": str(cwd),
            "started_at": started,
            "finished_at": _now(),
            "returncode": returncode,
            "timed_out": timed_out,
        }
        log_path = self.logs_root / scope / f"{command['id']}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"STDOUT\n{stdout}\n\nSTDERR\n{stderr}\n",
            encoding="utf-8",
            newline="\n",
        )
        result["log"] = str(log_path)
        return result

    def _require_artifacts(self, phase: Mapping[str, Any]) -> None:
        missing: list[str] = []
        for relative in phase.get("required_artifacts", []):
            artifact = _inside(
                self.workspace_root,
                relative,
                label=f"phase {phase['id']} required_artifact",
            )
            if not artifact.exists():
                missing.append(relative)
        if missing:
            raise GauntletError(f"phase {phase['id']} missing required artifacts: {missing}")

    def run_machine(self) -> str:
        """Run all incomplete phase and application gates in manifest order."""
        for phase in self.manifest["phases"]:
            phase_state = self.state["phases"][phase["id"]]
            if phase_state["status"] == COMPLETED:
                continue
            for dependency in phase.get("depends_on", []):
                if self.state["phases"][dependency]["status"] != COMPLETED:
                    raise GauntletError(f"phase {phase['id']} dependency {dependency} is not complete")
            # Attempt-scoped transaction: interrupted or failed work reruns the
            # entire phase.  Individual command success is never cached as a release.
            phase_state.update({"status": RUNNING, "commands": [], "started_at": _now()})
            self.state["terminal_state"] = RUNNING
            self._save()
            try:
                for command in phase["commands"]:
                    result = self._run_command(command, scope=f"phase-{phase['id']}")
                    phase_state["commands"].append(result)
                    self._save()
                    if result["returncode"] != 0:
                        raise GauntletError(
                            f"phase {phase['id']} gate {command['id']} failed; see {result['log']}"
                        )
                self._require_artifacts(phase)
            except GauntletError as exc:
                phase_state.update({"status": MACHINE_FAILED, "failure": str(exc), "finished_at": _now()})
                self.state["terminal_state"] = MACHINE_FAILED
                self._save()
                raise
            phase_state.update({"status": COMPLETED, "finished_at": _now()})
            phase_state.pop("failure", None)
            self._save()

        for application in self.manifest["applications"]:
            app_state = self.state["applications"][application["id"]]
            if app_state["status"] in {MACHINE_PASSED, AWAITING_HUMAN_UI_APPROVAL, SUCCESS}:
                continue
            app_state.update({"status": RUNNING, "machine_gates": [], "started_at": _now()})
            self.state["terminal_state"] = RUNNING
            self._save()
            for gate in application["machine_gates"]:
                result = self._run_command(gate, scope=f"app-{application['id']}")
                app_state["machine_gates"].append(result)
                self._save()
                if result["returncode"] != 0:
                    app_state.update(
                        {
                            "status": MACHINE_FAILED,
                            "failure": f"gate {gate['id']} failed; see {result['log']}",
                            "finished_at": _now(),
                        }
                    )
                    self.state["terminal_state"] = MACHINE_FAILED
                    self._save()
                    raise GauntletError(app_state["failure"])
            app_state.update({"status": MACHINE_PASSED, "finished_at": _now()})
            app_state.pop("failure", None)
            self._save()

        if self.manifest.get("require_live_review_services"):
            unavailable: list[str] = []
            for application in self.manifest["applications"]:
                try:
                    with urllib.request.urlopen(application["review_url"], timeout=3) as response:
                        if response.status != 200:
                            unavailable.append(application["id"])
                except OSError:
                    unavailable.append(application["id"])
            if unavailable:
                self.state["terminal_state"] = MACHINE_FAILED
                self._save()
                raise GauntletError(f"review services failed health check: {unavailable}")

        for app_state in self.state["applications"].values():
            if app_state["status"] == MACHINE_PASSED:
                app_state["status"] = AWAITING_HUMAN_UI_APPROVAL
        self.state["terminal_state"] = AWAITING_HUMAN_UI_APPROVAL
        self._save()
        return self.state["terminal_state"]

    def review_urls(self) -> list[dict[str, str]]:
        return [
            {
                "id": application["id"],
                "name": application["name"],
                "url": application["review_url"],
                "status": self.state["applications"][application["id"]]["status"],
            }
            for application in self.manifest["applications"]
            if self.state["applications"][application["id"]]["status"]
            in {AWAITING_HUMAN_UI_APPROVAL, HUMAN_REJECTED}
        ]

    def record_human_review(
        self, application_id: str, *, verdict: str, reviewer: str, notes: str
    ) -> str:
        verdict = verdict.upper()
        if verdict not in {"PASS", "FAIL"}:
            raise GauntletError("human verdict must be PASS or FAIL")
        if not reviewer.strip():
            raise GauntletError("reviewer is required")
        if application_id not in self.state["applications"]:
            raise GauntletError(f"unknown application: {application_id}")
        app_state = self.state["applications"][application_id]
        if app_state["status"] not in {AWAITING_HUMAN_UI_APPROVAL, HUMAN_REJECTED}:
            raise GauntletError(
                f"application {application_id} is not ready for human review: {app_state['status']}"
            )
        app_state["human_review"] = {
            "verdict": verdict,
            "reviewer": reviewer,
            "notes": notes,
            "recorded_at": _now(),
        }
        app_state["status"] = SUCCESS if verdict == "PASS" else HUMAN_REJECTED
        statuses = {item["status"] for item in self.state["applications"].values()}
        if statuses == {SUCCESS}:
            self.state["terminal_state"] = SUCCESS
        elif HUMAN_REJECTED in statuses:
            self.state["terminal_state"] = HUMAN_REJECTED
        else:
            self.state["terminal_state"] = AWAITING_HUMAN_UI_APPROVAL
        self._save()
        return self.state["terminal_state"]

    def reset_application_after_repair(self, application_id: str) -> None:
        if application_id not in self.state["applications"]:
            raise GauntletError(f"unknown application: {application_id}")
        app_state = self.state["applications"][application_id]
        if app_state["status"] != HUMAN_REJECTED:
            raise GauntletError("only a human-rejected application may be reset after repair")
        self.state["applications"][application_id] = {
            "status": PENDING,
            "machine_gates": [],
            "human_review": None,
        }
        self.state["terminal_state"] = PENDING
        self._save()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Web Experience Engine production gauntlet")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--state", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("run")
    subparsers.add_parser("status")
    subparsers.add_parser("review-urls")
    review = subparsers.add_parser("review")
    review.add_argument("--app", required=True)
    review.add_argument("--verdict", choices=("PASS", "FAIL"), required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--notes", default="")
    reset = subparsers.add_parser("reset-app")
    reset.add_argument("--app", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        gauntlet = WebExperienceGauntlet(args.manifest, args.state)
        if args.command == "validate":
            payload: Any = {"valid": True, "manifest_sha256": gauntlet.manifest_sha256}
        elif args.command == "run":
            payload = {"terminal_state": gauntlet.run_machine()}
        elif args.command == "status":
            payload = gauntlet.state
        elif args.command == "review-urls":
            payload = gauntlet.review_urls()
        elif args.command == "review":
            payload = {
                "terminal_state": gauntlet.record_human_review(
                    args.app,
                    verdict=args.verdict,
                    reviewer=args.reviewer,
                    notes=args.notes,
                )
            }
        elif args.command == "reset-app":
            gauntlet.reset_application_after_repair(args.app)
            payload = {"terminal_state": gauntlet.state["terminal_state"]}
        else:  # pragma: no cover - argparse enforces the command set
            raise AssertionError(args.command)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if isinstance(payload, dict) and payload.get("terminal_state") == AWAITING_HUMAN_UI_APPROVAL:
            return 3
        return 0
    except (GauntletError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
