from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from qwen_harness.web_oracles import OracleVerdict, mutation_adequacy, verify_rendered_project


ROOT=Path(__file__).resolve().parents[2]
TEMPLATE=ROOT/"renderers/react-vite"


@pytest.fixture(scope="module")
def built_project(tmp_path_factory: pytest.TempPathFactory)->Path:
    target=tmp_path_factory.mktemp("browser-oracle")/"app"
    shutil.copytree(TEMPLATE,target,ignore=shutil.ignore_patterns("node_modules","dist"))
    npm=shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        pytest.fail("npm executable is unavailable")
    completed=subprocess.run([npm,"install","--ignore-scripts","--offline"],cwd=target,capture_output=True,text=True,shell=False,timeout=180)
    if completed.returncode:
        pytest.fail(completed.stdout+completed.stderr)
    built=subprocess.run([npm,"run","build"],cwd=target,capture_output=True,text=True,shell=False,timeout=180)
    if built.returncode:
        pytest.fail(built.stdout+built.stderr)
    return target


def test_independent_oracle_accepts_real_production_build(built_project: Path)->None:
    report=verify_rendered_project(built_project)
    assert report.verdict is OracleVerdict.PASS, report.violations
    assert report.evidence["javascript_bytes"]<300_000


def test_all_critical_mutations_are_killed_in_same_invocation(built_project: Path)->None:
    report=mutation_adequacy(built_project)
    assert report.verdict is OracleVerdict.PASS, report.violations
    assert report.evidence=={"killed":4,"total":4,"kill_rate_percent":100}


def test_missing_build_is_no_result_not_pass(tmp_path: Path)->None:
    report=verify_rendered_project(tmp_path)
    assert report.verdict is OracleVerdict.NO_RESULT
    assert not report.passed
