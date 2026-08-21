"""Atomic Woven-Line evidence composition for Web Experience attempts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


REQUIRED_ENGINES=frozenset({"euclid","demiurge_or_sae","renderer","browser_oracle","loom"})


class EventLedger(Protocol):
    def record_event(self, session: str, kind: str, value: dict) -> dict: ...


@dataclass(frozen=True, slots=True)
class EngineEvidence:
    engine: str
    verdict: str
    receipt_sha256: str


def compose_experience_attempt(*, session:str, manifest_sha256:str, catalog_sha256:str, evidence:Sequence[EngineEvidence], ledger:EventLedger)->dict[str,Any]:
    """Promote only a complete, unique, all-PASS evidence bundle."""
    names=[item.engine for item in evidence]
    missing=REQUIRED_ENGINES-set(names)
    if missing or len(names)!=len(set(names)):
        raise ValueError(f"incomplete or duplicate engine evidence; missing={sorted(missing)}")
    if any(item.verdict!="PASS" for item in evidence):
        raise ValueError("every engine verdict must be PASS")
    payload={"schema_version":"1.0","manifest_sha256":manifest_sha256,"catalog_sha256":catalog_sha256,"evidence":[item.__dict__ if hasattr(item,"__dict__") else {"engine":item.engine,"verdict":item.verdict,"receipt_sha256":item.receipt_sha256} for item in sorted(evidence,key=lambda x:x.engine)]}
    payload["attempt_sha256"]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=ledger.record_event(session,"experience_certificate",payload)
    if not isinstance(receipt,dict) or ("id" not in receipt and not receipt.get("recorded")):
        raise RuntimeError("TOAM did not acknowledge durable certificate journaling")
    return {**payload,"toam_receipt":receipt}
