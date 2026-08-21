from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Verdict(StrEnum):
    PROVE_RELATIVE_TO_SPEC = "PROVE_RELATIVE_TO_SPEC"
    BOUND = "BOUND"
    ABSTAIN = "ABSTAIN"


class BuildStatus(StrEnum):
    CERTIFIED = "CERTIFIED"
    FAILED = "FAILED"
    ABSTAINED = "ABSTAINED"


@dataclass(frozen=True)
class EvidenceSpan:
    source: str
    content: str
    sha256: str
    trust: str = "untrusted"


@dataclass(frozen=True)
class OntologyPacket:
    domain: str
    intent: str
    schema: dict[str, Any]
    allowed_values: dict[str, tuple[str, ...]]
    seed_spec: dict[str, Any]
    evidence: tuple[EvidenceSpan, ...]
    route_score: float


@dataclass(frozen=True)
class Candidate:
    spec: dict[str, Any]
    binding: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str
    allowed: tuple[str, ...] = ()
    actionable: bool = True


@dataclass(frozen=True)
class OracleResult:
    verdict: Verdict
    code: str = ""
    proof: str = ""
    issues: tuple[Issue, ...] = ()
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReasoningProblem:
    """A frozen mathematical question compiled from a guarded domain spec."""

    domain: str
    facts: tuple[str, ...]
    goals: tuple[str, ...]
    policy: tuple[str, ...]
    depth: int = 10_000
    fuel: int = 1_000_000


@dataclass(frozen=True)
class ReasoningResult:
    verdict: Verdict
    certificates: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    residual: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttemptRecord:
    number: int
    stage: str
    candidate: dict[str, Any]
    issues: tuple[Issue, ...]
    verdict: str
    elapsed_ms: float


@dataclass(frozen=True)
class BuildResult:
    status: BuildStatus
    domain: str | None
    spec: dict[str, Any] | None
    code: str
    proof: str
    attempts: tuple[AttemptRecord, ...]
    assumptions: tuple[str, ...]
    bounds: tuple[str, ...]
    evidence: tuple[EvidenceSpan, ...]
    reasoning: ReasoningResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
