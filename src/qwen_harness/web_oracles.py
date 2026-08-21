"""Independent source, bundle, security, accessibility, and mutation gates.

These checks establish conformance of the owned renderer and its build artifact.
They do not replace real browser journeys or human aesthetic judgment.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping


class OracleVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NO_RESULT = "NO_RESULT"


@dataclass(frozen=True, slots=True)
class WebOracleReport:
    verdict: OracleVerdict
    violations: tuple[str, ...]
    evidence: Mapping[str, str | int]
    trust_boundary: str = (
        "Proves admitted source/bundle security and structural accessibility invariants; "
        "it does not prove journey behavior, assistive-technology equivalence, or beauty."
    )

    @property
    def passed(self) -> bool:
        return self.verdict is OracleVerdict.PASS


FORBIDDEN_SOURCE = (
    "dangerouslySetInnerHTML", "eval(", "new Function(", "document.write(",
    "javascript:", "http://", "https://", "child_process", "process.env",
)
REQUIRED_SOURCE = (
    "aria-label", "aria-labelledby", "aria-current", "data-testid",
    "type=\"button\"", "luxeron:command",
)
REQUIRED_STATES = ("loading", "empty", "ready", "error", "recovering", "forbidden")


def verify_rendered_project(project: Path, *, max_js_bytes: int = 300_000) -> WebOracleReport:
    source_path = project / "src" / "main.tsx"
    css_path = project / "src" / "styles.css"
    package_lock = project / "package-lock.json"
    dist = project / "dist"
    missing = [str(path.relative_to(project)) for path in (source_path, css_path, package_lock, dist / "index.html") if not path.exists()]
    if missing:
        return WebOracleReport(OracleVerdict.NO_RESULT, (f"missing required artifacts: {missing}",), {})
    source = source_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    violations: list[str] = []
    for poison in FORBIDDEN_SOURCE:
        if poison.lower() in source.lower():
            violations.append(f"forbidden source capability: {poison}")
    for required in REQUIRED_SOURCE:
        if required not in source:
            violations.append(f"missing accessibility/action invariant: {required}")
    for state in REQUIRED_STATES:
        if f"'{state}'" not in source:
            violations.append(f"missing content state: {state}")
    if "prefers-reduced-motion:reduce" not in css.replace(" ", ""):
        violations.append("missing reduced-motion policy")
    js_files = sorted((dist / "assets").glob("*.js")) if (dist / "assets").is_dir() else []
    if not js_files:
        violations.append("production JavaScript bundle missing")
    js_bytes = sum(path.stat().st_size for path in js_files)
    if js_bytes > max_js_bytes:
        violations.append(f"JavaScript bundle exceeds {max_js_bytes} bytes: {js_bytes}")
    evidence = {
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "css_sha256": hashlib.sha256(css.encode()).hexdigest(),
        "javascript_bytes": js_bytes,
        "bundle_count": len(js_files),
    }
    return WebOracleReport(OracleVerdict.FAIL if violations else OracleVerdict.PASS, tuple(violations), evidence)


def mutation_adequacy(project: Path) -> WebOracleReport:
    """Run critical live poisons against the same gate invocation."""
    source_path = project / "src" / "main.tsx"
    css_path = project / "src" / "styles.css"
    if not source_path.is_file() or not css_path.is_file():
        return WebOracleReport(OracleVerdict.NO_RESULT, ("source unavailable",), {})
    original_source = source_path.read_text(encoding="utf-8")
    original_css = css_path.read_text(encoding="utf-8")
    mutations = {
        "xss_sink": (original_source + "\nconst poison=eval('1');", original_css),
        "lost_accessible_name": (original_source.replace("aria-labelledby", "data-lost-label"), original_css),
        "lost_recovery_state": (original_source.replace("'recovering',", ""), original_css),
        "lost_reduced_motion": (original_source, original_css.replace("prefers-reduced-motion:reduce", "prefers-motion:always")),
    }
    killed: list[str] = []
    try:
        for name, (source, css) in mutations.items():
            source_path.write_text(source, encoding="utf-8", newline="\n")
            css_path.write_text(css, encoding="utf-8", newline="\n")
            if verify_rendered_project(project).verdict is OracleVerdict.FAIL:
                killed.append(name)
    finally:
        source_path.write_text(original_source, encoding="utf-8", newline="\n")
        css_path.write_text(original_css, encoding="utf-8", newline="\n")
    survivors = sorted(set(mutations) - set(killed))
    violations = tuple(f"critical mutation survived: {name}" for name in survivors)
    return WebOracleReport(
        OracleVerdict.FAIL if violations else OracleVerdict.PASS,
        violations,
        {"killed": len(killed), "total": len(mutations), "kill_rate_percent": int(100*len(killed)/len(mutations))},
        "Proves only that the declared critical source mutations are detected by the structural oracle.",
    )
