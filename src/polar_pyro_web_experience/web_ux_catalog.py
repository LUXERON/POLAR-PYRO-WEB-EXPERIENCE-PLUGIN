"""Audited UX vocabulary, design-language selection, and bounded cheat sheets."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .web_contracts import ContractVerdict, canonical_bytes, content_sha256, validate_document


REQUIRED_CONTENT_STATES = frozenset({"loading", "empty", "ready", "error", "recovering", "forbidden"})
EXPECTED_ARCHETYPES = 10


@dataclass(frozen=True, slots=True)
class UXCatalogAudit:
    passed: bool
    violations: tuple[str, ...]
    catalog_sha256: str


@dataclass(frozen=True, slots=True)
class DesignSelection:
    verdict: ContractVerdict
    design_language_id: str | None
    evidence: tuple[str, ...]
    residual: tuple[str, ...]


def load_ux_catalog(root: Path) -> tuple[dict[str, Any], UXCatalogAudit]:
    archetypes_doc = json.loads((root / "ux-catalog.source.json").read_text(encoding="utf-8"))
    languages_doc = json.loads((root / "design-languages.json").read_text(encoding="utf-8"))
    precedents_doc = json.loads(
        (root / "precedents" / "precedent-index.json").read_text(encoding="utf-8")
    )
    violations: list[str] = []
    if any(doc.get("schema_version") != "1.0" for doc in (archetypes_doc, languages_doc, precedents_doc)):
        violations.append("all UX catalog documents must use schema_version 1.0")
    archetypes = archetypes_doc.get("archetypes", [])
    languages = languages_doc.get("design_languages", [])
    precedents = precedents_doc.get("precedents", [])
    if len(archetypes) != EXPECTED_ARCHETYPES:
        violations.append(f"expected {EXPECTED_ARCHETYPES} archetypes, found {len(archetypes)}")
    archetype_ids = {item.get("id") for item in archetypes}
    language_ids = {item.get("design_language_id") for item in languages}
    if len(archetype_ids) != len(archetypes):
        violations.append("archetype IDs must be unique")
    if len(language_ids) != len(languages):
        violations.append("design language IDs must be unique")
    for archetype in archetypes:
        missing = REQUIRED_CONTENT_STATES - set(archetype.get("required_content_states", []))
        if missing:
            violations.append(f"archetype {archetype.get('id')} missing content states {sorted(missing)}")
        if not archetype.get("view_recipes"):
            violations.append(f"archetype {archetype.get('id')} has no view recipes")
        if not archetype.get("priorities"):
            violations.append(f"archetype {archetype.get('id')} has no priorities")
    for language in languages:
        for issue in validate_document("design_language", language):
            violations.append(f"design language {language.get('design_language_id')}: {issue}")
    seen_precedents: set[str] = set()
    for precedent in precedents:
        precedent_id = precedent.get("id")
        if precedent_id in seen_precedents:
            violations.append(f"duplicate precedent {precedent_id}")
        seen_precedents.add(precedent_id)
        if precedent.get("archetype") not in archetype_ids:
            violations.append(f"precedent {precedent_id} has unknown archetype")
        if precedent.get("design_language_id") not in language_ids:
            violations.append(f"precedent {precedent_id} has unknown design language")
        if not precedent.get("applicability") or not precedent.get("exclusions"):
            violations.append(f"precedent {precedent_id} lacks applicability boundary")
        if precedent.get("human_ratification_required") is not True:
            violations.append(f"precedent {precedent_id} must preserve human ratification boundary")
        if precedent.get("status") != "structurally_qualified":
            violations.append(f"precedent {precedent_id} has invalid pre-browser status")
    payload = {
        "schema_version": "1.0",
        "archetypes": sorted(archetypes, key=lambda item: item["id"]),
        "design_languages": sorted(languages, key=lambda item: item["design_language_id"]),
        "precedents": sorted(precedents, key=lambda item: item["id"]),
    }
    digest = content_sha256(payload)
    return payload, UXCatalogAudit(not violations, tuple(violations), digest)


KEYWORDS = {
    "ops.precise.light.v1": frozenset({"precise", "trustworthy", "clean", "enterprise", "light"}),
    "ops.precise.dark.v1": frozenset({"precise", "technical", "focused", "dark", "operations"}),
    "warm.approachable.light.v1": frozenset({"warm", "friendly", "approachable", "cozy", "welcoming"}),
}


def select_design_language(attributes: Sequence[str]) -> DesignSelection:
    """Map fuzzy words to a discrete profile or abstain on no/ambiguous evidence."""
    normalized = {item.strip().lower() for item in attributes if item.strip()}
    scores = {key: len(normalized & words) for key, words in KEYWORDS.items()}
    best = max(scores.values(), default=0)
    winners = sorted(key for key, score in scores.items() if score == best and score > 0)
    if len(winners) != 1:
        reason = "no supported aesthetic evidence" if not winners else f"ambiguous profiles: {winners}"
        return DesignSelection(ContractVerdict.NO_RESULT, None, (), (reason,))
    winner = winners[0]
    evidence = tuple(sorted(normalized & KEYWORDS[winner]))
    return DesignSelection(ContractVerdict.PASS, winner, evidence, ())


def compile_web_cheatsheet(
    catalog: Mapping[str, Any], *, archetype_id: str, max_estimated_tokens: int = 800
) -> dict[str, Any]:
    archetype = next(
        (item for item in catalog["archetypes"] if item["id"] == archetype_id), None
    )
    if archetype is None:
        raise ValueError(f"unknown archetype {archetype_id!r}")
    precedents = [
        {
            "id": item["id"],
            "design_language_id": item["design_language_id"],
            "applicability": item["applicability"],
            "exclusions": item["exclusions"],
        }
        for item in catalog["precedents"]
        if item["archetype"] == archetype_id
    ]
    sheet = {
        "schema_version": "1.0",
        "archetype": archetype["id"],
        "navigation": archetype["navigation"],
        "allowed_view_recipes": archetype["view_recipes"],
        "allowed_priorities": archetype["priorities"],
        "required_content_states": sorted(REQUIRED_CONTENT_STATES),
        "allowed_precedents": precedents,
        "invariants": [
            "no_raw_code_or_css",
            "every_route_has_recipe",
            "every_action_binds_declared_capability",
            "unknown_or_ambiguous_returns_no_result",
        ],
        "catalog_sha256": content_sha256(catalog),
    }
    estimated_tokens = (len(canonical_bytes(sheet)) + 3) // 4
    if estimated_tokens > max_estimated_tokens:
        raise ValueError(
            f"cheat sheet exceeds token budget: {estimated_tokens}>{max_estimated_tokens}"
        )
    sheet["estimated_tokens"] = estimated_tokens
    return sheet
