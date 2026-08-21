"""Fail-closed market-grade application depth gate.

This oracle proves declared product depth, executable journey evidence, persistent
state evidence, and product-specific surface diversity. It cannot prove that a
human would pay a particular price; owner judgment remains blocking.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class Verdict(StrEnum):
    PASS="PASS"; FAIL="FAIL"; NO_RESULT="NO_RESULT"


@dataclass(frozen=True,slots=True)
class RealAppReport:
    verdict:Verdict
    violations:tuple[str,...]
    evidence:Mapping[str,Any]

    @property
    def passed(self)->bool:return self.verdict is Verdict.PASS


def verify_real_application(root:Path)->RealAppReport:
    manifest_path=root/"product-manifest.json"; receipt_path=root/"evidence/real-app-browser.json"; backend_path=root/"evidence/backend-oracle.json"
    concept_path=root/"design/concept-provenance.json"; render_path=root/"app/RENDER_RECEIPT.json"
    if not manifest_path.is_file() or not receipt_path.is_file() or not concept_path.is_file() or not backend_path.is_file() or not render_path.is_file():
        return RealAppReport(Verdict.NO_RESULT,("product manifest, certified design provenance, immutable render receipt, live backend evidence, and live browser receipt are required",),{})
    try:
        m=json.loads(manifest_path.read_text(encoding="utf-8")); r=json.loads(receipt_path.read_text(encoding="utf-8")); c=json.loads(concept_path.read_text(encoding="utf-8")); b=json.loads(backend_path.read_text(encoding="utf-8")); rr=json.loads(render_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:return RealAppReport(Verdict.FAIL,(f"invalid JSON: {exc}",),{})
    v=[]; routes=m.get("routes",[]); journeys=m.get("critical_journeys",[]); entities=m.get("persistent_entities",[]); roles=m.get("roles",[])
    if len(routes)<10:v.append(f"at least 10 product routes required; found {len(routes)}")
    route_ids=[x.get("id") for x in routes if isinstance(x,dict)]
    if len(route_ids)!=len(set(route_ids)):v.append("route IDs must be unique")
    if len(journeys)<5:v.append("at least five application-specific critical journeys required")
    if any(len(j.get("steps",[]))<3 for j in journeys):v.append("every critical journey requires at least three executable steps")
    if len(entities)<3:v.append("at least three persistent domain entities required")
    if len(roles)<2:v.append("at least two authorization roles required")
    required_states={"loading","empty","ready","error","offline","forbidden"}
    if not required_states<=set(m.get("content_states",[])):v.append("complete content and recovery states required")
    if not m.get("backend_contracts"):v.append("working backend contracts required")
    if not m.get("distinctive_product_thesis"):v.append("distinctive product thesis required")
    if c.get("certifying") is not True:v.append("design provenance must be admitted autonomous evidence")
    source_kinds={"user_supplied_image","user_supplied_text","configured_generator","bundled_generator","deterministic_catalog"}
    if c.get("source_kind") not in source_kinds:v.append("design source must use an admitted provider-neutral source kind")
    if c.get("producer")!="qwen06_harness_design_pipeline":v.append("design IR must be produced through the deterministic harness design pipeline")
    required_design_receipt={"autonomy_run_id","design_input_sha256","design_ir_sha256","admission_receipt_sha256","toam_record_ref"}
    if not required_design_receipt<=set(c) or any(c.get(k) in (None,"",{},[]) for k in required_design_receipt):v.append("complete provider-neutral design and TOAM receipt required")
    if c.get("source_kind") in {"configured_generator","bundled_generator"}:
        generation=c.get("generation")
        if not isinstance(generation,dict) or any(generation.get(k) in (None,"",{},[]) for k in ("provider","capability_digest","receipt_sha256")):v.append("generated concepts require a configured provider capability receipt")
    canonical=lambda value:json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    rendered_files=rr.get("files")
    if not isinstance(rendered_files,dict) or not rendered_files:v.append("render receipt requires a nonempty frozen file map")
    else:
        app_root=(root/"app").resolve()
        for rel_path,expected in rendered_files.items():
            target=(app_root/str(rel_path)).resolve()
            try:target.relative_to(app_root)
            except ValueError:v.append(f"render receipt path escapes application root: {rel_path}");continue
            if not target.is_file():v.append(f"rendered source is missing: {rel_path}");continue
            if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:v.append(f"rendered source hash mismatch: {rel_path}")
        if hashlib.sha256(canonical(rendered_files)).hexdigest()!=rr.get("output_sha256"):v.append("render output hash does not bind the frozen file map")
    if rr.get("design_ir_sha256")!=c.get("design_ir_sha256"):v.append("design provenance does not bind the rendered design IR")
    if rr.get("manifest_sha256")!=hashlib.sha256(canonical(m)).hexdigest():v.append("render receipt does not bind the product manifest")
    if b.get("verdict")!="PASS":v.append("live backend oracle verdict must be PASS")
    for field in ("authorization_passed","mutual_match_messaging_passed","blocked_contact_denial_passed","restart_persistence_passed","moderator_decision_audit_passed"):
        if b.get(field) is not True:v.append(f"backend evidence missing: {field}")
    if r.get("verdict")!="PASS":v.append("live browser journey verdict must be PASS")
    covered=set(r.get("journeys",[])); declared={j.get("id") for j in journeys}
    if covered!=declared:v.append("browser receipt must cover every declared critical journey")
    if not r.get("reload_persistence_passed"):v.append("reload persistence proof required")
    if not r.get("negative_authorization_passed"):v.append("negative authorization proof required")
    if not r.get("api_failure_recovery_passed"):v.append("API failure/recovery proof required")
    evidence={"routes":len(routes),"journeys":len(journeys),"persistent_entities":len(entities),"roles":len(roles),"manifest_sha256":hashlib.sha256(manifest_path.read_bytes()).hexdigest(),"concept_receipt_sha256":hashlib.sha256(concept_path.read_bytes()).hexdigest(),"render_receipt_sha256":hashlib.sha256(render_path.read_bytes()).hexdigest(),"backend_receipt_sha256":hashlib.sha256(backend_path.read_bytes()).hexdigest(),"browser_receipt_sha256":hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
    return RealAppReport(Verdict.FAIL if v else Verdict.PASS,tuple(v),evidence)
