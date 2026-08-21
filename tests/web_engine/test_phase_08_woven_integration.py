from __future__ import annotations

import urllib.request

import pytest

from polar_pyro_web_experience.memory import ToamMemory
from polar_pyro_web_experience.web_integration import EngineEvidence, compose_experience_attempt


def evidence():
    return [EngineEvidence(name,"PASS",(str(index)*64)[:64]) for index,name in enumerate(["euclid","demiurge_or_sae","renderer","browser_oracle","loom"],1)]


class RecordingLedger:
    def __init__(self): self.events=[]
    def record_event(self,session,kind,value): self.events.append((session,kind,value)); return {"recorded":True}


def test_candidate_never_promotes_without_complete_all_pass_evidence()->None:
    ledger=RecordingLedger()
    with pytest.raises(ValueError,match="missing"):
        compose_experience_attempt(session="x",manifest_sha256="a"*64,catalog_sha256="b"*64,evidence=evidence()[:-1],ledger=ledger)
    poisoned=evidence(); poisoned[0]=EngineEvidence("euclid","NO_RESULT","1"*64)
    with pytest.raises(ValueError,match="every engine"):
        compose_experience_attempt(session="x",manifest_sha256="a"*64,catalog_sha256="b"*64,evidence=poisoned,ledger=ledger)
    assert ledger.events==[]


def test_live_toam_journals_and_recalls_promoted_certificate()->None:
    try: urllib.request.urlopen("http://127.0.0.1:8810/health",timeout=3).close()
    except OSError: pytest.fail("live TOAM unavailable; P08 is NO_RESULT")
    result=compose_experience_attempt(session="web-p08-live",manifest_sha256="a"*64,catalog_sha256="b"*64,evidence=evidence(),ledger=ToamMemory(timeout=5))
    assert result["toam_receipt"]["id"]>0
    recalled=ToamMemory(timeout=5).retrieve("web-p08-live",result["attempt_sha256"],1500)
    assert recalled and result["attempt_sha256"] in recalled[0].content
