"""Production and recovery gates for web-experience artifacts."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ProductionReport:
    passed: bool
    violations: tuple[str, ...]
    evidence: Mapping[str, str | int]


def tree_hash(root: Path) -> str:
    rows=[]
    for path in sorted(item for item in root.rglob("*") if item.is_file() and "node_modules" not in item.parts):
        rows.append((path.relative_to(root).as_posix(),hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(rows,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def verify_production_project(project: Path)->ProductionReport:
    required=("package.json","package-lock.json","src/main.tsx","src/styles.css","dist/index.html")
    missing=[name for name in required if not (project/name).is_file()]
    violations=[f"missing {name}" for name in missing]
    package=json.loads((project/"package.json").read_text(encoding="utf-8")) if not missing or (project/"package.json").is_file() else {}
    deps=package.get("dependencies",{})
    for name,value in deps.items():
        if not isinstance(value,str) or value.startswith(("^","~","*","latest","http","git")):
            violations.append(f"dependency is not exactly pinned: {name}={value}")
    if package.get("scripts",{}).get("dev") != "vite --host 127.0.0.1":
        violations.append("development service must bind loopback only")
    return ProductionReport(not violations,tuple(violations),{"tree_sha256":tree_hash(project),"dependency_count":len(deps)})


def rollback_drill(project: Path, scratch: Path)->ProductionReport:
    before=tree_hash(project)
    candidate=scratch/"candidate"
    if candidate.exists(): shutil.rmtree(candidate)
    shutil.copytree(project,candidate,ignore=shutil.ignore_patterns("node_modules"))
    (candidate/"src/main.tsx").write_text("BROKEN",encoding="utf-8")
    shutil.rmtree(candidate)
    after=tree_hash(project)
    violations=() if before==after else ("failed candidate altered promoted workspace",)
    return ProductionReport(not violations,violations,{"before":before,"after":after})
