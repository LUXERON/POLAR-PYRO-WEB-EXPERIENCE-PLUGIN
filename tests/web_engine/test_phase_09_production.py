from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from qwen_harness.web_production import rollback_drill, verify_production_project

ROOT=Path(__file__).resolve().parents[2]


def _build_renderer() -> None:
    project = ROOT / "renderers/react-vite"
    npm = shutil.which("npm")
    assert npm is not None, "npm is required for the renderer production gate"
    subprocess.run([npm, "ci", "--offline", "--ignore-scripts"], cwd=project, check=True, shell=False, timeout=300)
    subprocess.run([npm, "run", "build"], cwd=project, check=True, shell=False, timeout=300)

def test_pinned_supply_chain_and_clean_production_build()->None:
    _build_renderer()
    report=verify_production_project(ROOT/"renderers/react-vite")
    assert report.passed,report.violations
    assert report.evidence["dependency_count"]>=5

def test_failed_candidate_cannot_mutate_promoted_workspace(tmp_path:Path)->None:
    report=rollback_drill(ROOT/"renderers/react-vite",tmp_path)
    assert report.passed and report.evidence["before"]==report.evidence["after"]

def test_unpinned_dependency_poison_is_rejected(tmp_path:Path)->None:
    project=tmp_path/"project"; shutil.copytree(ROOT/"renderers/react-vite",project,ignore=shutil.ignore_patterns("node_modules"))
    package=(project/"package.json").read_text(encoding="utf-8").replace('"react": "19.0.0"','"react": "^19.0.0"')
    (project/"package.json").write_text(package,encoding="utf-8")
    report=verify_production_project(project)
    assert not report.passed and any("not exactly pinned" in item for item in report.violations)
