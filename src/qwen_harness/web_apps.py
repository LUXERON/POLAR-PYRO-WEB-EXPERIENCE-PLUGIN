"""Autonomous qualification and review-service machinery for the ten web apps."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from .web_contracts import canonical_bytes
from .web_oracles import mutation_adequacy, verify_rendered_project
from .web_production import verify_production_project
from .real_app_gate import verify_real_application
from .web_renderer import materialize_react_vite, solve_ui_plan
from .web_ux_compiler import compile_ux_contract


RECIPE={
 "policy_authoring_workbench":"editor_evidence_split","analytical_workbench":"input_canvas_results",
 "search_operations_console":"search_results_inspector","planning_workspace":"constraint_editor_timeline",
 "developer_proof_workbench":"grammar_editor_tree","scheduling_saas":"availability_calendar",
 "operations_control_tower":"data_table_detail_drawer","case_review_workspace":"case_queue_detail",
 "maintenance_operations_center":"fleet_health_grid","incident_response_workspace":"incident_queue_detail",
}


def _run(argv:list[str],cwd:Path,timeout:int)->dict[str,Any]:
    result=subprocess.run(argv,cwd=cwd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,shell=False)
    return {"argv":argv,"returncode":result.returncode,"stdout":result.stdout[-8000:],"stderr":result.stderr[-8000:]}


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def _browser_oracle(project:Path)->dict[str,Any]:
    handler=partial(_QuietHandler,directory=str(project/"dist")); server=ThreadingHTTPServer(("127.0.0.1",0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        screenshot=project.parent/"browser-mobile.png"
        result=_run([shutil.which("node") or "node",str(project/"browser-oracle.mjs"),f"http://127.0.0.1:{server.server_port}/",str(screenshot)],project,120)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
    if result["returncode"]: raise RuntimeError(f"browser oracle failed: {result['stdout']} {result['stderr']}")
    payload=json.loads(result["stdout"].strip().splitlines()[-1])
    if payload.get("verdict")!="PASS": raise RuntimeError(f"browser oracle rejected: {payload}")
    payload["screenshot_sha256"]=hashlib.sha256(screenshot.read_bytes()).hexdigest()
    return payload


def qualify_application(*, workspace:Path, harness:Path, manifest:Mapping[str,Any], app_id:str)->dict[str,Any]:
    app=next((item for item in manifest["applications"] if item["id"]==app_id),None)
    if app is None: raise ValueError(f"unknown application {app_id}")
    project=(workspace/app["project"]).resolve(); project.relative_to(workspace)
    if not project.is_dir(): raise FileNotFoundError(project)
    real_app=verify_real_application(project)
    if not real_app.passed:
        raise RuntimeError(f"real-application depth gate failed: {real_app.verdict}: {real_app.violations}")
    source_receipt=project/"BUILD_RECEIPT.json"
    if not source_receipt.is_file(): raise RuntimeError("domain BUILD_RECEIPT.json missing")
    source=json.loads(source_receipt.read_text(encoding="utf-8"))
    if source.get("status") != "QUALIFIED_LOCAL": raise RuntimeError("domain application is not QUALIFIED_LOCAL")
    domain_test=_run([sys.executable,"-m","pytest","-q"],project,900)
    if domain_test["returncode"]: raise RuntimeError(f"domain tests failed: {domain_test['stdout']} {domain_test['stderr']}")
    catalog=json.loads((harness/"catalog/web_experience/catalog.lock.json").read_text(encoding="utf-8"))
    designs=json.loads((harness/"catalog/web_experience/design-languages.json").read_text(encoding="utf-8"))["design_languages"]
    design=designs[1 if app_id in {"S03","A02","A05"} else 0]
    capability={"application_id":app_id.lower(),"routes":[{"id":"workspace"}],"roles":[{"id":"operator"}],"queries":[{"id":"inspect_evidence"}],"commands":[{"id":"execute_primary"}]}
    binding={"application_id":app_id.lower(),"view_recipes":{"workspace":RECIPE[app["archetype"]]}}
    journeys=[{"id":"primary_journey","task_id":"primary_task","role_ids":["operator"],"entry_route":"workspace","recovery_route":"workspace","success_state":"completed","query_ids":["inspect_evidence"],"command_ids":["execute_primary"],"steps":[{"id":"inspect","route_id":"workspace","state":"ready"},{"id":"execute","route_id":"workspace","state":"submitting","command_id":"execute_primary"}]}]
    ux=compile_ux_contract(capability,binding,journeys)
    plan=solve_ui_plan(capability,ux,binding,catalog["components"],design)
    output=harness/"runtime/web-experience-gauntlet/applications"/app_id/"review-app"
    render=materialize_react_vite(plan,capability,design,output)
    npm=shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None: raise RuntimeError("npm unavailable")
    install=_run([npm,"install","--ignore-scripts","--offline"],output,300)
    if install["returncode"]: raise RuntimeError(f"npm install failed: {install['stderr']}")
    build=_run([npm,"run","build"],output,300)
    if build["returncode"]: raise RuntimeError(f"build failed: {build['stdout']} {build['stderr']}")
    browser=_browser_oracle(output)
    oracle=verify_rendered_project(output); adequacy=mutation_adequacy(output); production=verify_production_project(output)
    if not oracle.passed or not adequacy.passed or not production.passed:
        raise RuntimeError(f"web oracle failed: {oracle.violations+adequacy.violations+production.violations}")
    receipt={"schema_version":"1.0","application_id":app_id,"status":"MACHINE_PASSED","source_receipt_sha256":hashlib.sha256(source_receipt.read_bytes()).hexdigest(),"domain_tests":domain_test,"render_output_sha256":render.output_sha256,"browser_oracle":browser,"web_oracle":dict(oracle.evidence),"mutation":dict(adequacy.evidence),"production":dict(production.evidence)}
    receipt["receipt_sha256"]=hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    receipt_path=output.parent/"machine-certificate.json"; receipt_path.write_bytes(canonical_bytes(receipt)+b"\n")
    return receipt


def start_review_service(*, dist:Path,port:int,pid_file:Path)->int:
    if not dist.is_dir() or not (dist/"index.html").is_file(): raise RuntimeError(f"review dist missing: {dist}")
    if not 1024<=port<=65535: raise ValueError("unsafe port")
    argv=[sys.executable,"-m","http.server",str(port),"--bind","127.0.0.1","--directory",str(dist)]
    flags=0
    if os.name=="nt": flags=getattr(subprocess,"CREATE_NO_WINDOW",0)|getattr(subprocess,"DETACHED_PROCESS",0)
    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,shell=False,creationflags=flags,start_new_session=os.name!="nt")
    pid_file.parent.mkdir(parents=True,exist_ok=True); pid_file.write_text(str(process.pid),encoding="ascii")
    url=f"http://127.0.0.1:{port}/"
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen(url,timeout=1) as response:
                if response.status==200: return process.pid
        except OSError: time.sleep(.1)
    process.terminate(); raise RuntimeError(f"review service failed health check: {url}")
