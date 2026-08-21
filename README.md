# Polar Pyro Web Experience Engine

The Web Experience Engine is the deterministic UX compiler and owned React/Vite renderer used by the Polar Pyro neurosymbolic software forge. It converts a bounded product capability contract into user journeys, Euclid-Ω proof obligations, a closed UI plan, and reproducible source materialization. Qwen3-0.6B may select symbols from the frozen vocabulary; it does not author trusted JSX, CSS, package names, shell commands, or release tests.

This repository is an exact extraction of the working web-engine slice from `QWEN3-0.6B-NEUROSYMBOLIC-HARNESS` at parent commit `8a24a2b`. It was separated so the web compiler can evolve, release, and qualify as a Polar Pyro plugin without coupling its lifecycle to the inference harness.

## North star

A user supplies a natural-language product brief. Polar Pyro compiles it into a closed application capability manifest and task-specific vocabulary. This engine then produces a premium, accessible, state-correct web experience whose routes and controls refine declared application semantics. Git contains source truth, TOAM journals attempts and certificates, and no candidate reaches the canonical branch until independent browser, accessibility, security, mutation, and domain gates pass.

```text
brief + evidence
      ↓
SAE AppSpec or DEMIURGE Contract
      ↓
ApplicationCapabilityManifest
      ↓
Qwen bounded UXBinding
      ↓
UX compiler ──► Euclid-Ω obligations
      ↓
component solver + design language
      ↓
UIPlan ──► deterministic React/Vite source
      ↓
browser · a11y · security · mutation · performance
      ↓
ExperienceCertificate ──► LOOM/Git promotion
```

## Prior art

The LUXERON estate was searched across 477 repositories for deterministic web experience compilation, design-token registries, and component solvers. No strong duplicate was found. Adjacent work includes the Woven Line deterministic engines, the Sovereign Harness verification protocol, and QCEOM intent compilers.

| System | Relationship | Reuse |
| --- | --- | --- |
| Qwen3-0.6B Neurosymbolic Harness | Parent implementation | Exact extracted code, schemas, tests, gauntlet, and renderer |
| Polar Pyro Plugin SDK | Governing ABI | Manifest, effects, receipts, lifecycle, Git transaction and evidence rules |
| SAE | Application semantics | Stateful entities, auth, permissions, workflows, persistence and APIs |
| DEMIURGE | Decidable synthesis | Stateless kernels and formally bounded interaction subdomains |
| Euclid-Ω | Mathematical reasoning | Journey reachability, permission closure, recovery and constraint obligations |
| LOOM | Repository composition | Cross-engine seam closure, repair, hardening and release orchestration |

**Position:** this repository is an extraction and productization of proven local work, not a clean-room reinvention.

## Trust boundary

The engine's `PASS` receipt proves only deterministic closed compilation. It does not prove that a UI is beautiful, that browser behavior works, or that backend semantics are correct.

- Qwen emits a bounded `UXBinding` only.
- The capability manifest is the semantic firewall.
- Every route must have a primary task and admitted roles.
- Every command/query referenced by the UI must exist in the capability alphabet.
- Euclid obligations are returned for independent proof; they are not silently assumed.
- The React renderer copies frozen owned templates and canonical JSON only.
- Browser and mutation gates issue the release verdict.
- Workspace writes occur only inside a Polar Pyro Git transaction.
- `NO_RESULT` never promotes.

## Plugin capability

`dev.luxeron.engine.web-experience@0.1.0` currently exposes:

### `web.compile_experience`

Input is a closed object containing:

- `capability`: application ID, roles, routes, queries and commands;
- `binding`: route recipe choices from the allowed vocabulary;
- `journeys`: trusted task/journey templates;
- `components`: audited component manifests;
- `design_language`: one frozen, coherent token system.

Output contains:

- a deterministic `UXContract`;
- replayable Euclid-Ω requests for planning and FSM liveness;
- a deterministic `UIPlan`;
- SHA-256 evidence and explicit limits.

Unknown top-level fields, uncovered routes, unknown symbols, duplicate tasks, empty journeys, missing components, or mismatched application IDs fail closed.

## Repository map

```text
src/qwen_harness/             UX compiler, catalog, renderer, oracles and adapter
schemas/web_experience/       Versioned IR schemas
catalog/web_experience/       Audited components, providers, precedents and languages
renderers/react-vite/         Frozen source template and browser oracle
tests/web_engine/             Phase contract, rendering, oracle and integration gates
gauntlet/                     Production phase/application manifest
scripts/                      Qualification entry points
plugin.manifest.json          Polar Pyro capability declaration
WHITEPAPER.md                 Architectural argument and rollout boundary
```

## Quick start

```powershell
python -m pytest -q
```

Invoke the native closed compiler with one JSON object on standard input:

```powershell
$request | polar-web-experience
```

The executable prints one canonical `polar.web-experience-receipt/v1` object and exits nonzero on `FAIL`.

## Rendering lane

The first production lane is intentionally opinionated:

- React + TypeScript + Vite;
- one accessible primitive substrate per recipe;
- curated source-owned component registry;
- named design-token roles compiled to CSS variables;
- deterministic source mapping from UI regions;
- offline locked dependency installation;
- real-browser, accessibility, responsive, security, visual, performance and mutation qualification.

Svelte and Web Components are future renderer adapters. They become equivalent only after the same semantic contract suite passes; framework similarity is not treated as proof.

## Git and long-horizon development

Every materialization or repair binds to a base commit and runs in an attempt worktree. The attempt produces a candidate commit plus evidence. LOOM may compose the candidate with SAE/DEMIURGE artifacts, but only a certificate bound to the candidate, manifests, oracle versions and evidence permits a fast-forward. A moved canonical `HEAD` invalidates the proof and forces replay.

This is essential for complex, multi-engine systems: chat memory cannot represent branch ancestry, binary-safe diffs, concurrent attempts, rollback or proof-to-source binding. Git can.

## Production gates

The engine is not production-ready merely because unit tests pass. Release requires:

1. schema and cross-reference conformance;
2. audited component/provider catalog and license notices;
3. Euclid proof qualification;
4. renderer reproducibility;
5. browser, accessibility, responsive and security oracles;
6. mutation adequacy;
7. live Qwen3-0.6B bounded-binding qualification;
8. SAE/DEMIURGE/Euclid/LOOM/TOAM integration;
9. crash, rollback and supply-chain drills;
10. five stateless and five stateful autonomy applications with human UI approval.

The current repository carries the extracted implementation and its existing gates. Product-level frontier claims remain prohibited until the full ten-application evidence set passes without product-source hand editing.

## License and provenance

LUXERON code in this repository is MIT licensed. Third-party component/provider obligations are recorded under `catalog/web_experience/THIRD_PARTY_NOTICES.md` and pinned catalog artifacts. Dependency licenses and model weights require their own audit; this MIT license does not cover them.
