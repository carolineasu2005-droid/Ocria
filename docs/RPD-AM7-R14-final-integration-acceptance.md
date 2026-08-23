# Ocria Am7 — AM7-R14 Am7 Final Integration, Regression & Production Readiness Acceptance

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R14
- Requirement Name: Am7 Final Integration, Regression & Production Readiness Acceptance
- Document Type: Requirement / Product Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r14-final-integration-acceptance`
- Requirement Branch Observed: `am7-r14-final-integration-acceptance`
- Official Baseline: `855f7125ebc7b1e62d5a35232892a7d29e28a258`
- Working HEAD Observed: `855f7125ebc7b1e62d5a35232892a7d29e28a258`
- Prepared On: 2026-08-23（Asia/Shanghai）

This document defines the Frozen product contract for AM7-R14 and is the authoritative product-design baseline for subsequent TID work. It does not itself authorize implementation, tests, README authoring, Acceptance Report creation, Git operations, packaging, release, or live BOSS activity.

## 2. Background

AM7-R02 through AM7-R13 have established the production capabilities required by Ocria Am7:

- one current AI Provider configuration and Provider-neutral runtime;
- saved immutable ScreeningProfile Versions and explicit Run-bound ScreeningRuleSet input;
- rule-independent Complete OCR and finalized Candidate evidence;
- Candidate-level AI input, Prompt v1, strict Boolean response validation, and AI Runtime;
- Candidate-level Rule evaluation and CandidateDecision;
- qualified-only authorization of the existing favorite or forward action path;
- bounded AI failure handling and required AI/Decision persistence.

The merged R13 baseline is therefore the Am7 functional-completion boundary. R14 does not add another business capability. It establishes whether the completed capabilities work together, whether existing behavior remains intact, whether production documentation accurately describes the resulting product, and whether Human production smoke has been completed.

The current root `README.md` is an R01-era overview rather than the required detailed Am7 operating guide. R14 therefore includes a new detailed root README as a production-documentation requirement, but that README will be authored by Sol Ultra in a separate task.

## 3. Current Product State / Feature Complete Boundary

At the observed baseline and branch:

- branch and HEAD exactly match the R14 requirement identity;
- the working tree was clean before this RPD was created;
- `simple_brush.py` obtains an explicit one-or-more RuleSet input, loads one saved ScreeningProfile Version and one complete AIProviderConfig for the live Run, initializes OCR persistence and the R13 record store, and retains those exact Run-bound values;
- the Am7 Candidate path calls rule-independent `scan_candidate()`, finalizes one `CandidateOcrDocument`, and admits only normal completed or completed-with-limit documents into AI processing;
- R09 copies authoritative non-blank Candidate document text into the exact two-field AI Candidate input;
- R10 constructs the exact Prompt v1 model-visible content and strictly validates the complete Criterion Boolean mapping;
- R11 preserves Candidate identity and produces only `completed` with a complete Boolean mapping or `failed` with `None`;
- R13 performs at most three formal AI attempts, persists every failed-attempt record before another attempt, persists exactly one final AI outcome before Decision, and persists the Decision before any qualified action;
- R06 and R12 produce exactly `qualified`, `rejected`, or `ai_failed`;
- only `qualified` may enter the existing favorite or forward action path; `no_forward` retains its existing forwarding-suppression authority;
- `rejected` and fully persisted `ai_failed` perform zero action and return to the existing Candidate continuation;
- a required R13 persistence failure reaches the existing Run error/cleanup boundary and prevents subsequent action or Candidate processing.

The current tracked automated test tree contains focused coverage for Provider configuration/runtime, ScreeningProfile, Rule Engine, Complete OCR and Candidate evidence, AI input/prompt/contract/runtime, Candidate Decision, R13 persistence, Candidate switching, actions, calibration, mouse behavior, and the Legacy/OCR regression surface. These existing tests are evidence inputs for R14; their presence is not itself an R14 pass. R14 acceptance requires their actual authoritative execution at the R14 acceptance baseline.

“Am7 Feature Complete” means the intended R02–R13 production functionality exists. It does not mean:

- R14 automated integration acceptance has passed;
- the full tracked regression suite has passed at the R14 acceptance baseline;
- the detailed Am7 README has been accepted;
- Human Production Smoke has passed;
- Human Final Review or Am7 Production Readiness has been accepted.

## 4. Problem Statement

Component-level completion does not alone prove production readiness. Ocria still needs one final acceptance boundary that answers:

1. Do the accepted R02–R13 modules compose into one continuous Candidate production chain with the required ordering and failure semantics?
2. Has AI integration preserved BossOCR Legacy/Core, OCR/Candidate behavior, Candidate switching, calibration, actions, mouse behavior, pause/stop, batching, and continuation?
3. Can a Human operate and troubleshoot the actual Am7 product from accurate source-grounded documentation, and has a Human personally completed the live production smoke that automated acceptance must not perform?

R14 answers those questions through acceptance and documentation requirements. It does not answer them by adding runtime functionality.

## 5. Goals

R14 has exactly three product goals:

1. **Final Automated Integration Acceptance** — prove that the existing R02–R13 Candidate evidence, AI, Rule, Decision, persistence, action-authorization, and continuation boundaries compose correctly.
2. **Full Regression Acceptance** — prove that Am7 AI integration has not regressed the accepted BossOCR Legacy/Core or existing OCR, browser, action, calibration, mouse, stop, batch, and Candidate-continuation behavior.
3. **Production Documentation Requirement** — require one detailed, source-accurate Am7 root README that enables installation, configuration, safe operation, troubleshooting, and developer verification.

Human Production Smoke is the required Human-owned readiness confirmation after automated acceptance. It is not delegated to Codex and is not replaced by the three automated/documentation goals.

## 6. Final Production E2E

The final Am7 production chain is:

```text
start Ocria
→ AI Provider Configuration / load
→ saved ScreeningProfileVersion
→ explicit Run-bound ScreeningRuleSet
→ existing Action Mode
→ Calibration / Calibration Profile
→ “最近没看过” batch filter and first Candidate
→ Candidate Switch Verification
→ R02–R07 Complete OCR
→ finalized CandidateOcrDocument
→ OCR Store
→ R09 AI Candidate Input Builder
→ R10 Prompt v1 + strict Boolean Contract
→ R11 AI Runtime
→ R13 bounded AI attempts + required persistence
→ R06 Screening Rule Engine
→ R12 CandidateDecision
→ R13 Decision persistence
→ qualified-only existing action authorization
→ existing Candidate continuation
→ next Candidate
```

This is the semantic dependency and authority chain. It does not require R14 to reorder already accepted startup prompts or internal call sites where the same frozen dependencies and ordering are preserved.

The final Decision branches are:

| Decision | Action authority | Continuation |
|---|---|---|
| `qualified` | Existing `favorite`, `forward`, or `no_forward` behavior according to the existing Action Mode and controls | Existing Candidate continuation |
| `rejected` | Zero favorite and zero forward | Existing Candidate continuation |
| `ai_failed` with all required persistence successful | Zero favorite and zero forward | Existing Candidate continuation |

CandidateDecision does not own action mechanics or Candidate switching. The existing action and continuation layers remain authoritative after the R12/R13 authorization and persistence prerequisites are satisfied.

## 7. Failure Semantics

R14 preserves the exact R13 distinction:

| Condition | Product meaning | Required outcome |
|---|---|---|
| Complete valid Boolean mapping and R06 returns `false` | Business false | `rejected`; zero action; normal continuation |
| Accepted R09/R03/R10 technical failure reaches the three-attempt limit | Candidate-level AI technical failure | final failed AI outcome; `ai_failed`; zero R06/action; normal continuation after required persistence |
| Any required R13 persistence write fails | Run-level persistence integrity failure | zero subsequent action/Candidate processing; existing safe cleanup; `RunStatus.ERROR` projection |
| R06 validation/input failure or another unexpected integration defect | Configuration/integration or product defect, not business data | no fabricated CandidateDecision or action; existing error boundary |

R14 must not:

- convert technical AI failure to Boolean false or `rejected`;
- convert persistence failure to `ai_failed`;
- create a fourth CandidateDecision status;
- add a new retry, fallback, circuit-breaker, stop, or recovery policy;
- weaken final-outcome-before-Decision or Decision-before-action ordering.

## 8. Final Automated Integration Strategy

R14 automated evidence is the combination of two layers:

### 8.1 Dedicated cross-module integration evidence

Dedicated integration coverage must prove that the real local module boundaries after Candidate evidence finalization compose as one chain:

```text
CandidateOcrDocument
→ AI Candidate input
→ Prompt / Provider completion boundary
→ strict Boolean mapping
→ bounded attempt and persistence ordering
→ Rule evaluation
→ CandidateDecision
→ qualified-only action authorization
→ Candidate continuation
```

At minimum, dedicated integration evidence must cover:

- AI completed plus passing RuleSet produces `qualified`, persists the final AI outcome before Decision, persists Decision before action, and authorizes only the selected existing action path;
- AI completed plus failing RuleSet produces `rejected`, persists the final outcome and Decision in order, performs zero action, and rejoins continuation;
- three accepted technical failures produce three ordered attempt-error records, one final failed outcome, one `ai_failed` Decision, zero R06/action, and normal continuation;
- required attempt-error, final-outcome, or Decision persistence failure prevents all prohibited downstream work and enters the existing Run-fatal boundary;
- `favorite`, `forward`, and `no_forward` retain their existing authority and suppression semantics;
- the existing Run, Candidate, Profile, Provider/model, and Decision trace relationships remain intact, and the exact same immutable Run-bound `ScreeningRuleSet` object remains the Rule authority for every Candidate evaluation in the live Run;
- exactly one immutable `ScreeningRuleSet` remains bound for the live Run, with no per-Candidate RuleSet lookup, Profile-owned RuleSet, Configuration Mode second authority, or Legacy rule conversion authority;
- R14 introduces no RuleSet ID, version, digest, persistence record, RunManifest field, or second RuleSet authority;
- Legacy keyword/match outcomes have no Am7 Complete-Scan, CandidateDecision, or production-action authority.

Real GUI, BOSS, network, Provider, favorite, forward, and Candidate-switch side effects may be replaced by focused test doubles. The tests must compose actual local production modules where their contract is under acceptance; they must not replace the whole chain with one synthetic Browser simulator.

R14 does not require a generic E2E framework, repository scanner, action wrapper, runtime gate, or reusable browser simulation architecture. Exact test files, fixtures, helper APIs, and commands belong to TID.

### 8.2 Existing complete regression suite

The authoritative full tracked automated test suite at the R14 acceptance commit must pass. Focused integration success does not excuse a tracked regression failure, and a full-suite pass does not replace dedicated cross-module integration evidence.

Automated tests must not perform live BOSS login, live browser actions, live favorite/forward, live Candidate switching, live production OCR, or live paid/provider AI smoke.

## 9. Regression Scope

The final automated regression scope must include all existing tracked coverage applicable to:

- BossOCR Legacy/Core behavior and the AM7-R01 accepted baseline;
- Candidate Switch Verification;
- OCR R02 Detail Load;
- OCR R03 Fingerprint;
- OCR R04 Normalization;
- OCR R05 Candidate Aggregation;
- OCR R06 Similarity and AM7-R06 Screening Rule Engine V2;
- OCR R07 Dynamic End and AM7-R07 rule-independent Complete Scan;
- `CandidateOcrDocument` construction and authority;
- OCR Store, Run manifest, Screen/Candidate evidence, and existing OCR replay regression;
- AI Provider configuration and Provider runtime;
- ScreeningProfile, Criterion, immutable saved Version, and Run binding;
- R09 Candidate Input Builder;
- R10 Prompt v1 and Boolean Contract;
- R11 AI Runtime;
- R12 Candidate Decision and action authorization;
- R13 bounded attempts, error/final-outcome/Decision persistence, and persistence-fatal ordering;
- favorite, forward, and `no_forward`;
- focus restoration;
- calibration and Calibration Profiles;
- “最近没看过” batch filtering and first-Candidate placement;
- mouse, WindMouse, and simple-mouse fallback;
- pause/resume, ESC stop, duration stop, and safe cleanup;
- batch refresh, Candidate continuation, and last-Candidate behavior.

Existing OCR replay fixtures/tests remain regression tooling for accepted OCR evidence behavior. They do not authorize or imply AI Replay, historical Candidate rescreening, or a production replay feature.

R14 must report a real tracked regression failure as an automated acceptance failure. Infrastructure failures must remain distinguishable from product/test failures under the governing Constitution and must not be mislabeled as product success or failure.

## 10. README Product Requirement

R14 requires a new detailed root `README.md`. The README author is **Sol Ultra in a separate task**. This RPD defines its product content and acceptance boundary only; this turn does not author or revise README.

The README must be derived from the actual accepted source, CLI, setup, dependency, and runtime behavior at the final R14 baseline. It must accurately explain at least:

- what Ocria is;
- Ocria's provenance and compatibility relationship with BossOCR Legacy;
- the complete current Am7 feature set;
- Windows and supported Python environment requirements;
- installation and source execution;
- AI Provider Configuration;
- Provider, Base URL, API Key, and Model configuration;
- ScreeningProfile, saved Profile Version, Criterion, and Criterion truth semantics;
- ScreeningRuleSet, one-or-more Rule behavior, `AND`, `OR`, parentheses, precedence, and multi-Rule ANY;
- Action Mode, favorite, forward, and `no_forward`;
- Calibration and Calibration Profiles;
- “最近没看过” filtering and first-Candidate placement;
- Candidate Switch Verification;
- Complete OCR and finalized Candidate evidence;
- `qualified`, `rejected`, and `ai_failed`;
- the maximum-three-attempt AI policy and zero-delay retry behavior;
- AI attempt-error, final-outcome, and CandidateDecision persistence;
- `ai_errors.jsonl`, `ai_results.jsonl`, and `decisions.jsonl`;
- pause/resume, ESC stop, duration stop, and safe termination;
- all current CLI arguments and startup paths;
- safe testing practices that avoid unintended live actions;
- common configuration, OCR, calibration, Provider, response-contract, and persistence errors;
- current product limitations;
- key production modules and their responsibility boundaries;
- authoritative developer test commands.

The README must not claim that the product currently includes:

- a GUI;
- AI Replay, Replay Cache, or historical Candidate rescreening;
- a database, SQLite, PostgreSQL, or Talent Library;
- automatic Provider or model fallback;
- DOM access, Selenium, or Playwright;
- an automatic Prompt-version framework;
- any Provider, model, action mode, Decision status, or runtime feature not present in the accepted source.

README examples must not expose a real API key or imply that connection verification guarantees model inference success. AC-22 remains failed until the new README is source-accurate and contains no invented capability.

## 11. Human Production Smoke

Human Production Smoke is owned and executed only by Human against the real BOSS environment. Codex and automated acceptance must not perform it.

The minimum Human smoke coverage is:

1. Ocria starts normally.
2. AI Provider configuration loads normally.
3. ScreeningProfile loads normally.
4. ScreeningRuleSet binds normally.
5. Calibration / Calibration Profile works normally.
6. “最近没看过” filtering works normally.
7. The first Candidate is positioned/opened normally.
8. Candidate Switch Verification works normally.
9. Complete OCR works normally.
10. AI completed produces the required complete Boolean Criteria mapping.
11. `qualified` in favorite mode performs the existing favorite behavior normally.
12. `qualified` in forward mode performs the existing forward behavior normally.
13. `rejected` performs zero action.
14. `ai_failed` performs zero action.
15. With persistence healthy, an `ai_failed` Candidate continues to the next Candidate.
16. The next Candidate proceeds normally.
17. Pause and resume work normally.
18. ESC performs a safe stop.

Human smoke does not require deliberate disk failure, permission failure, corrupted JSONL, or another manufactured persistence-integrity failure. Those semantics belong to automated evidence.

## 12. Human / Automated Acceptance Boundary

Automated acceptance and Human Production Smoke are separate authorities.

After all R14 automated integration and regression requirements pass, but before Human smoke and Human final review, the strongest permitted status is:

```text
Implementation / Integration Verification: Completed
Automated Acceptance: Passed
Human Production Smoke: Pending
Human Final Review: Pending
Am7 Production Readiness: Pending
```

Codex automated acceptance must not:

- log into the real BOSS account;
- operate the live production browser page;
- perform live favorite or forward;
- perform live Candidate switching or Complete OCR production runs;
- perform live production AI smoke;
- declare Human Production Smoke passed;
- declare Human Final Review accepted;
- declare Am7 Production Readiness accepted.

Only Human, after personally completing the required smoke and reviewing the automated/documentation evidence, may set:

```text
Human Production Smoke: Passed
Human Final Review: Accepted
Am7 Production Readiness: Accepted
```

A failed or incomplete Human smoke cannot be replaced by automated mocks. A pending Human smoke is not an automated acceptance failure, but production readiness remains pending.

## 13. Runtime Change Policy

Expected production runtime source changes for AM7-R14: **0**.

R14 may require acceptance-focused tests and the separately authored detailed README. It is not a cleanup, refactor, architecture, or feature Requirement.

If integration or regression reveals a genuine runtime defect:

```text
Automated Acceptance: Failed
→ record the minimum defect evidence
→ Human decides whether to authorize a corrective Change
```

The discovery of a defect does not automatically authorize runtime edits, test-expectation changes, broader investigation, cleanup, or a new feature. Until Human authorizes the exact corrective scope, R14 remains failed/pending rather than silently expanding.

## 14. Explicit Non-Goals

AM7-R14 does not introduce, require, or reserve a runtime placeholder for:

- AI Replay;
- Replay Cache;
- Historical Candidate Rescreening;
- database, SQLite, or PostgreSQL;
- Talent Library;
- GUI;
- model comparison or Prompt A/B;
- a new Provider or other AI feature;
- a new retry policy, Provider fallback, or model fallback;
- a new CandidateDecision status;
- a new action mode;
- a new OCR feature;
- a new Candidate Switch behavior;
- a new calibration behavior;
- a new persistence schema;
- DOM access, Selenium, Playwright, or browser redesign;
- packaging redesign or release automation;
- architecture cleanup or broad refactoring;
- a generic E2E, Replay, pipeline, Gate, Guard, Scanner, Wrapper, Validator, or orchestration framework.

R14 also does not modify the accepted Prompt v1, Rule grammar, Candidate schema, OCR evidence schema, persistence filenames, action mechanics, stop reasons, or Run state model.

## 15. Product Acceptance Criteria

### AC-01 — Complete production chain

R02–R13 compose into one continuous finalized-Candidate production Decision chain from current Run configuration and Complete OCR through AI, Rule, Decision, required persistence, qualified-only action authorization, and existing Candidate continuation.

### AC-02 — Qualified mapping

An AI-completed, complete valid Boolean mapping whose bound ScreeningRuleSet passes produces exactly `qualified`.

### AC-03 — Favorite authorization

`qualified` in favorite mode authorizes only the existing favorite action path, without changing its mechanics or making another path authoritative.

### AC-04 — Forward authorization

`qualified` in forward mode authorizes only the existing forward action path, without changing its mechanics or making another path authoritative.

### AC-05 — no_forward authority

`no_forward` retains its existing real-forward suppression authority and does not alter the `qualified` Decision or authorize favorite as fallback.

### AC-06 — Rejected zero action

An AI-completed mapping whose bound ScreeningRuleSet fails produces `rejected`, performs zero favorite/forward action, and rejoins existing Candidate continuation.

### AC-07 — AI-failed zero action

Exhausting the bounded accepted AI technical-failure attempts produces `ai_failed`, performs zero R06 and zero favorite/forward action.

### AC-08 — AI-failed continuation

When all required R13 persistence succeeds, `ai_failed` remains Candidate-level recoverable and returns to the existing Candidate flow so a later Candidate may be processed.

### AC-09 — Persistence integrity remains Run-fatal

Any required R13 persistence integrity failure prevents subsequent action and Candidate processing and reaches the existing safe Run-level error termination.

### AC-10 — Final AI outcome ordering

Exactly one final AI outcome is durably persisted before CandidateDecision production; failure to persist it produces no Decision or action.

### AC-11 — Decision ordering

Every normally produced CandidateDecision is durably persisted before any qualified action; failure to persist it authorizes zero action.

### AC-12 — Candidate Switch regression

Candidate Switch Verification, including its existing bounds, focus recovery, failure behavior, and scan-admission authority, has no regression.

### AC-13 — OCR R02–R07 regression

Detail Load, Fingerprint, Normalization, Candidate Aggregation, Similarity, Dynamic End, Complete Scan, and their accepted evidence/failure behavior have no regression.

### AC-14 — Candidate evidence and OCR Store regression

`CandidateOcrDocument`, OCR Store, Run/Screen/Candidate identity, and factual evidence authority have no regression or AI/Decision schema contamination.

### AC-15 — Existing action regression

Favorite, forward, `no_forward`, and focus restoration retain their accepted behavior and are changed only in qualified authorization, not mechanics.

### AC-16 — Calibration regression

Calibration and Calibration Profile loading, validation, selection, and current action/OCR region behavior have no regression.

### AC-17 — Mouse regression

Mouse movement, WindMouse behavior, and simple-mouse fallback retain their accepted behavior.

### AC-18 — Batch entry regression

“最近没看过” batch filtering and first-Candidate placement/opening retain their accepted behavior.

### AC-19 — Run and continuation regression

Pause/resume, ESC stop, duration stop, batch refresh, last-Candidate handling, Candidate continuation, and safe cleanup retain their accepted behavior.

### AC-20 — BossOCR Legacy/Core regression

The existing BossOCR Legacy/Core automated regression remains passing; Legacy compatibility is preserved while Legacy rule/match data retains no Am7 Decision or action authority.

### AC-21 — Full tracked automated suite

The complete tracked automated test suite at the R14 acceptance baseline passes, in addition to the dedicated R14 cross-module integration evidence.

### AC-22 — Source-accurate README

The new detailed root README satisfies Section 10, matches the actual accepted Am7 implementation and operating boundaries, and describes no invented capability.

### AC-23 — No live automated smoke

Codex automated acceptance performs no live BOSS login, live production browser action, live favorite/forward, live Candidate switch/OCR run, or live production AI smoke; those remain Human-only.

### AC-24 — No new product capability

R14 adds no Replay, Cache, Historical Rescreening, database, GUI, Provider/model fallback, new AI/OCR/Decision/Action capability, generic framework, or runtime placeholder for such a capability.

Product Acceptance Criteria count: **24 (AC-01–AC-24)**.

## 16. Scope Boundary

### In Scope

- the product-level final integration acceptance contract;
- dedicated Candidate-evidence-to-action-authorization automated integration evidence;
- full tracked automated regression acceptance;
- the detailed root README product and truthfulness contract;
- the Human Production Smoke minimum coverage and ownership boundary;
- final readiness status discipline;
- reporting real defects without automatically changing runtime scope.

### Out of Scope

- production runtime feature implementation;
- implementation-level test file, fixture, helper, API, or command design;
- README authoring in this task;
- live Human smoke execution in this task;
- correction of a defect not separately authorized by Human;
- packaging, release, Git history, branch, or distribution operations;
- all capabilities listed in Section 14.

## 17. Dependencies on AM7-R02–AM7-R13

R14 consumes the accepted current implementations and does not reopen their designs:

| Upstream | R14 dependency |
|---|---|
| AM7-R02 | One current AIProviderConfig and its load/configuration boundary |
| AM7-R03 | Provider-neutral LLM runtime, fixed configured Provider/model use, and no automatic retry/fallback |
| AM7-R04 | Accepted offline model-benchmark closeout remains historical upstream evidence; R14 does not convert it into runtime or replay capability |
| AM7-R05 | Immutable ScreeningProfileVersion and Criterion authority |
| AM7-R06 | Deterministic Screening Rule Engine V2 and fixed multi-Rule ANY |
| AM7-R07 | Rule-independent Candidate Complete Scan and finalized Candidate evidence |
| AM7-R08 | Screen = Evidence Scope; Candidate = Ocria Am7 Production Decision Scope |
| AM7-R09 | Exact non-blank Candidate document-text projection |
| AM7-R10 | Exact Prompt v1 and complete strict-Boolean response contract |
| AM7-R11 | Candidate-associated `completed` / `failed` AI Runtime boundary |
| AM7-R12 | Exact `qualified` / `rejected` / `ai_failed` Decision and qualified-only action authority |
| AM7-R13 | Three-attempt maximum, failure/final-outcome/Decision persistence, continuation, and persistence-fatal ordering |

### Existing OCR-Stage Regression Dependencies

Existing OCR-stage regression dependencies remain independently authoritative:

- OCR R02 — Detail Load;
- OCR R03 — Fingerprint;
- OCR R04 — Normalization;
- OCR R05 — Candidate Aggregation;
- OCR R06 — Similarity;
- OCR R07 — Dynamic End / Complete Scan.

These OCR stage identifiers are not AM7 Requirement identifiers. The `AM7-Rxx` and `OCR Rxx` namespaces remain separate. R14 does not merge, renumber, alias, or reinterpret either namespace; create a unified numbering scheme; modify either namespace's existing ownership; or reinterpret historical RPD/TID contracts.

## 18. Risks

### 18.1 Live environment variance

BOSS page state, login, layout, network, current Provider availability, and actual Candidate data cannot be fully represented by automated mocks. This is why Human Production Smoke remains mandatory and separate.

### 18.2 Real action side effects

Favorite and forward smoke can produce real business effects. Human owns the account, test timing, Candidate selection, Action Mode, and confirmation that the smoke is safe to perform.

### 18.3 Provider and model variability

Automated tests must use controlled doubles rather than depend on live credentials or paid inference. Human live AI smoke may reveal an environment/configuration issue without changing the frozen distinction between product, Provider, and infrastructure failures.

### 18.4 Regression breadth

The full tracked suite is intentionally broad. A genuine failure blocks automated acceptance; a sandbox, file-lock, cache, or other infrastructure failure must be reported separately and must not be converted into a product pass or fail.

### 18.5 Documentation drift

README content can become stale if written from historical designs instead of the final source. AC-22 requires source-grounded review at the final R14 baseline.

### 18.6 Replay terminology

The repository contains accepted offline OCR replay regression tooling. R14's No Replay decision prohibits AI Replay, Replay Cache, and historical Candidate rescreening as product/runtime capabilities; it does not delete accepted OCR regression fixtures.

### 18.7 Defect discovery

A real integration defect can require runtime correction, but R14 itself does not pre-authorize that correction. Automated acceptance remains failed until Human approves and the authorized correction is verified.

## 19. Open Product Decisions

Open Product Decisions: **None**.

Human has already fixed:

- R14 is acceptance/documentation work, not a new feature Requirement;
- AI Replay, Replay Cache, and Historical Candidate Rescreening are removed and out of scope;
- expected production runtime changes are zero;
- automated integration evidence combines dedicated cross-module coverage with the full tracked suite;
- live BOSS/AI/action smoke is Human-only;
- the detailed root README is authored by Sol Ultra in a separate task.

## 20. Contract Conflicts

Contract Conflicts: **None**.

The current implementation supports the required final chain and preserves the R12/R13 ordering and failure boundaries. The No Replay decision does not conflict with existing OCR replay regression tooling because that tooling is not an AI or historical Candidate rescreening production capability.

## 21. Human Review Required

Human Review Required: **None — Human Final RPD Review completed**.

- Human Final RPD Review: **Accepted**
- RPD Freeze: **Approved**
- Open Product Decisions: **0**
- Contract Conflicts: **0**

The next step is to write the AM7-R14 TID. This Frozen RPD does not itself authorize product-feature implementation or Human Production Smoke.

## 22. Draft Summary

AM7-R14 treats the R13 merged baseline as **Am7 Feature Complete** and adds no business capability. It requires final cross-module automated integration evidence, one full tracked regression acceptance, one source-accurate detailed README authored separately by Sol Ultra, and one Human-only production smoke before Human may accept Am7 Production Readiness.

The final product chain preserves Candidate-level authority, exact `qualified/rejected/ai_failed` semantics, final-outcome-before-Decision and Decision-before-action persistence ordering, qualified-only existing action authorization, and common Candidate continuation. AI technical failure remains Candidate-recoverable when persistence succeeds; required persistence integrity failure remains Run-fatal.

AI Replay, Replay Cache, Historical Candidate Rescreening, new runtime features, generic frameworks, cleanup, packaging redesign, and release automation are out of scope. Expected production runtime source changes are zero.

Current state: **AM7-R14 RPD v0.1 — Frozen**.
