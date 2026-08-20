# AM7-R08 — Candidate-level Decision Boundary

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R08
- Document Type: Technical Implementation Design
- Version: 0.1
- Status: Frozen
- Source RPD: AM7-R08 v0.1 Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r08-candidate-decision-boundary`
- Working HEAD / Baseline: `843e73fd71f71219e4cd323c9eea79a78847f75f`
- Prepared On: 2026-08-19 (Asia/Shanghai)

## 1. Technical Objective

Determine and freeze the smallest technically correct treatment of the AM7-R08 authority boundary in the current repository.

The Frozen product invariant is:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

AM7-R08 is an authority/architectural-boundary requirement. It does not require source code merely to create an implementation artifact. Targeted inspection found no current Ocria Am7 Candidate Decision / Action production chain and no current violation of the Frozen boundary. The chosen technical outcome is therefore **Option A — No Runtime Product-Code Change**.

This TID does not redesign later Candidate evaluation, Decision, action, persistence, or replay requirements. It records the current boundary and the binding obligations that AM7-R09 through AM7-R14 must honor.

## 2. Authoritative Technical Contract

### 2.1 Ocria Am7 authority

In a future Ocria Am7 production path:

- `ScanObservation` is evidence only;
- `formal_screen.raw_text` is evidence only;
- `OcrScreenRecord` is evidence only;
- fingerprint, normalized text, comparison text, and screen-level projections are evidence only;
- Legacy Screen-level match and non-match are non-authoritative;
- no Screen-level value can independently become final Match, Reject, or equivalent production Decision;
- no Legacy Screen-level value can directly trigger an Am7 production action;
- formal Candidate production evaluation is not eligible before the relevant `CandidateOcrDocument` is finalized.

### 2.2 Legacy BossOCR authority

The existing Legacy chain remains valid and production-authoritative in the preserved Legacy runtime:

```text
Screen
  -> Legacy Rule Match
  -> independent confirmation
  -> Legacy judgment
  -> existing Legacy action
```

AM7-R08 does not convert, disable, reroute, or reinterpret this chain.

### 2.3 Candidate finalization

Finalization establishes a Candidate evidence boundary. It is a prerequisite only and is not technically equivalent to:

- Match;
- Reject;
- successful evaluation;
- an evidence-completeness guarantee;
- action authorization.

### 2.4 No placeholder enforcement

AM7-R08 requires no `CandidateDecision` placeholder, Decision enum, Decision engine, Decision manager, `DecisionGate`, `ActionGate`, guard, interceptor, authority enum, runtime mode router, shadow-decision schema, evidence-link schema, status object, persistence artifact, enforcement wrapper, or generic Decision/Authority framework.

## 3. Targeted Inspection Scope

The technical inspection was limited to:

- `CODEX-CONSTITUTION.md`;
- `docs/RPD-AM7-R08-candidate-decision-boundary.md`;
- Frozen AM7-R07 RPD and TID;
- `ocr_detector.py`;
- `ocr_candidate.py`;
- `ocr_records.py`;
- `ocr_store.py`;
- `simple_brush.py`;
- `screening_rule_engine.py`;
- directly relevant R07 detector, Candidate evidence, integration, and Legacy action-handoff tests.

No repository-wide audit was performed. No implementation test was run.

`docs/AM7-R07-acceptance-report.md` exists in the current baseline and may be referenced as accepted historical evidence where useful. AM7-R08 does not reopen or re-review R07, rerun its tests, or reconstruct its acceptance evidence. The Option A conclusion remains supported by the current source structure, the Frozen R08/R07 contracts, and the accepted R07 historical evidence.

## 4. Targeted Repository Findings

### 4.1 Legacy Screen-level matching and confirmation

Owner: `OCRKeywordDetector` in `ocr_detector.py`.

- `detect(rules, first_observation=None) -> DetectionResult` is the public Legacy detector entry.
- `_match_observation(...)` runs the existing Legacy matcher and annotates `ScanObservation.matched_keyword`, `matched_rule`, and `rule_comparison`.
- `_run_scan_lifecycle(...)` enters the rule branch only when a non-null private `legacy_rules` tuple exists.
- `_rule_confirmation_result(...)` performs the existing independent second OCR observation and returns `DetectionResult.confirmed_match`.
- The position-confirmation recovery path can enter Legacy rule confirmation only when `legacy_rules is not None`.

No R08 modification is required or authorized in these functions.

### 4.2 Legacy confirmed-match to action handoff

Owner: `simple_brush.py`.

- `detect_keywords(...)` calls `ocr_detector.detect(forward_keywords, first_observation=...)`.
- It converts `DetectionResult.confirmed_match` into the existing `keyword_hit` Boolean.
- `view_candidate(...)` consumes only that Legacy Boolean.
- A positive Legacy Boolean invokes `perform_favorite_action()` in favorite mode or `forward_one_candidate()` in forward mode, subject to the existing `no_forward_mode` behavior.
- The current `run(...)` production loop calls `view_candidate(...)`; it does not call `scan_candidate(...)` and does not contain an Am7 Candidate Decision consumer.

This call graph is the preserved Legacy Screen-to-action runtime. The program's Ocria Am7 branding and its use of accepted Candidate evidence storage do not turn this Legacy compatibility path into a future Candidate Decision/Action chain. No new mode enum or router is needed merely to label the current path.

### 4.3 AM7-R07 Complete Scan

Owner: `OCRKeywordDetector.scan_candidate(...)` in `ocr_detector.py`.

- Exact public API: `scan_candidate(first_observation=None) -> DetectionResult`.
- The API accepts no rule input.
- It removes incidental Legacy rule annotations from a reused first observation without mutating the caller's value.
- It calls `_run_scan_lifecycle(legacy_rules=None, ...)`.
- Formal and recovery observations do not call Legacy matching or confirmation.
- It returns the existing evidence/lifecycle `DetectionResult`; it does not create a Candidate Decision or invoke an action.
- No targeted runtime source calls `scan_candidate(...)`; directly relevant tests exercise it as the accepted evidence-only capability.

Current direct tests structurally cover rule independence, later-Screen collection, Dynamic End, safety limits, failure projection, and reuse of the Candidate evidence/finalization path. They are not rerun under R08.

### 4.4 Candidate evidence construction and finalization

The existing technical boundary is:

```text
ScanObservation
  -> record_detection_observation(...)
  -> OcrScreenRecord
  -> CandidateOcrBuilder
  -> CandidateOcrBuilder.finalize(...)
  -> CandidateOcrDocument
  -> optional existing Store persistence
  -> future evaluator boundary
```

Exact owners:

- `simple_brush.record_detection_observation(...)` forwards an observed Screen into the existing record/builder path.
- `CandidateOcrBuilder.add_screen(...)` commits validated `OcrScreenRecord` evidence and existing aggregation/similarity projections.
- `CandidateOcrBuilder.finalize(...)` constructs one immutable `CandidateOcrDocument` and releases the builder's Candidate context.
- `simple_brush.finalize_current_candidate_recording(...)` is the current orchestration owner that calls the builder finalizer, projects existing Dynamic End facts, and optionally calls `ocr_record_store.save_candidate(...)`.
- `JsonlOcrRecordStore.save_candidate(...)` validates and persists the existing Candidate document. It produces no Decision and invokes no action.

Candidate finalization currently triggers neither Candidate Evaluation nor Candidate Decision nor Candidate/page Action.

### 4.5 Candidate document and cross-Screen evidence

`CandidateOcrDocument` already provides a viable future Candidate evidence anchor:

- `run_id`;
- `candidate_record_id`;
- Candidate sequence and timestamps;
- the ordered tuple of committed `OcrScreenRecord` values;
- capture summary and explicit lifecycle reasons;
- document text and document segments when aggregation completes;
- normalization, aggregation, similarity, and Dynamic End projections.

Each embedded Screen retains `screen_id`, raw OCR boxes/text, normalized/comparison evidence, fingerprints, and existing derived projections. Therefore evidence can remain distributed across multiple Screens, and earlier exclusion evidence remains available after it leaves the viewport. R08 requires no input-building, concatenation, deduplication, Criterion, Rule, or prompt design.

### 4.6 Existing Legacy shadow/debug fields

`OcrScreenRecord` already has optional fields such as:

- `rule_evaluation_mode`;
- `legacy_match`;
- `r04_match`;
- `comparison_outcome`;
- `legacy_rule_index`;
- `r04_rule_index`.

These may remain existing evidence/debug/reference projections. They are not a Candidate Decision, action authority, fallback Decision, or reason to add a shadow-decision object or logging infrastructure.

### 4.7 Current Candidate Decision / Action availability

Within the targeted runtime files:

- no `CandidateDecision` schema or value exists;
- no Decision status, Decision engine, or Decision manager exists;
- no `DecisionGate`, `ActionGate`, authority enum, runtime mode router, interceptor, or authority framework exists;
- no code consumes `CandidateOcrDocument` to produce an Ocria Am7 Candidate Decision;
- no Am7 action path consumes a Candidate Decision;
- no current code gives one Screen, `formal_screen.raw_text`, one `OcrScreenRecord`, or a Legacy Screen match final Am7 authority;
- no current Am7 action can occur before Candidate finalization because no current Am7 Candidate Decision/Action chain exists.

The only current Screen-to-action authority found is the explicitly preserved Legacy `detect_keywords(...) -> view_candidate(...)` chain.

### 4.8 AM7-R06 boundary

`screening_rule_engine.py` remains a pure local Boolean combiner:

- `ScreeningRule` and `ScreeningRuleSet` are immutable public values;
- `evaluate_rule_set(rule_set, criterion_results) -> bool` consumes an already supplied Criterion ID-to-Boolean mapping;
- it has no Screen, Candidate document, Legacy action, or browser dependency.

R08 neither modifies nor invokes R06 and does not import Legacy `NOT`, `ANY(...)`, Parser, or AST semantics into it.

## 5. Technical Decision Matrix

| Decision condition | Option A — No Runtime Product-Code Change | Option B — Minimal Existing-Violation Correction | Current evidence |
|---|---|---|---|
| Complete Scan is evidence-only | Required | A violation would require correction | Confirmed: `scan_candidate(...)` returns `DetectionResult` and has no Decision/Action dependency |
| Current Am7 Candidate Decision engine exists | Must be absent | Concrete violating owner must exist | Absent in targeted runtime files |
| Current Am7 action integration exists | Must be absent | Concrete premature action must exist | Absent; only Legacy action handoff exists |
| Screen has Am7 production authority | Must be absent | Concrete Screen-authority call path must exist | Absent |
| Candidate finalization is a clean future boundary | Required | Boundary would need minimal correction | Confirmed: builder finalization produces evidence and nothing downstream |
| Legacy Screen-to-action is preserved separately | Required | A mixed Am7 path would need separation | Confirmed through `detect_keywords(...) -> view_candidate(...)` |
| Current R08 invariant violation | None | At least one concrete violation | None found |

### Decision

Choose **Option A — No Runtime Product-Code Change**.

Option B is rejected because targeted inspection found no current Ocria Am7 Candidate Decision/Action production path and no concrete R08 violation to correct. Choosing Option B would create implementation solely for the sake of implementation and would contradict the Frozen RPD and `CODEX-CONSTITUTION.md`.

## 6. Chosen Technical Outcome — Option A

Freeze the following exact result:

- Runtime Product-Code Changes: None
- Runtime Test Changes: None
- New Product Schema: None
- Persistence Changes: None
- Enforcement Layer: None
- Runtime Mode Router: None
- Candidate Decision Placeholder: None
- Comparison Infrastructure: None

R08 is satisfied technically by its Frozen authority contract, the current compatible architecture, and targeted structural acceptance. The contract is binding on later requirements even though R08 adds no runtime artifact.

## 7. Legacy BossOCR Technical Boundary

The exact preserved Legacy authority chain is:

```text
simple_brush.view_candidate(...)
  -> simple_brush.detect_keywords(...)
  -> OCRKeywordDetector.detect(...)
  -> OCRKeywordDetector._match_observation(...)
  -> OCRKeywordDetector._rule_confirmation_result(...)
  -> DetectionResult.confirmed_match
  -> keyword_hit
  -> perform_favorite_action() or forward_one_candidate()
```

AM7-R08 modifies none of these owners. It does not:

- convert Legacy BossOCR to Candidate-level evaluation;
- disable or weaken Legacy action;
- rewrite the matcher/parser;
- remove independent confirmation;
- redirect Legacy runtime through a future Am7 Candidate Decision.

Legacy Screen-level judgment remains production-authoritative in this Legacy runtime only.

## 8. AM7-R07 Technical Boundary

R07 answers:

> Have we gathered Candidate evidence according to the accepted OCR lifecycle?

R08 answers:

> Which scope may later own Ocria Am7 production Decision authority?

The current R07 capability remains:

- rule-independent;
- evidence-only;
- Decision-free;
- Action-free.

AM7-R08 does not modify:

- `scan_candidate(...)`;
- `detect(...)`;
- `_run_scan_lifecycle(...)`;
- Legacy OCR R07 Dynamic End;
- safety budgets or reason meanings;
- retry or focus recovery;
- Candidate Switch Verification;
- Candidate evidence construction;
- Candidate finalization.

## 9. Candidate Finalization Technical Boundary

The clean future evaluator boundary begins only after `CandidateOcrBuilder.finalize(...)` has returned a valid `CandidateOcrDocument` for the relevant Candidate lifecycle.

Technical obligations:

1. A later formal Am7 evaluator must consume Candidate-scoped input associated with a finalized Candidate document.
2. A Screen or intermediate builder state cannot independently authorize Evaluation, Decision, or Action.
3. Finalization alone does not imply Match, Reject, evaluation success, complete evidence, or action authorization.
4. R08 does not decide whether interrupted, aborted, limited, or otherwise technically terminated Candidate documents are eligible for later evaluation.
5. No finalization status enum, eligibility field, Decision field, or `evaluation_ready` flag is added.

## 10. Screen Authority Technical Boundary

The following values may become input evidence for later Candidate-scoped work, but none may independently own final production authority:

- `ScanObservation`;
- `formal_screen.raw_text` or any equivalent one-Screen text value;
- `OcrScreenRecord`;
- Screen raw boxes/text;
- Screen fingerprint;
- Screen normalized/comparison text;
- Screen aggregation/similarity projections;
- Legacy Screen match or non-match;
- screen-level shadow/debug/comparison fields.

This is a later-caller constraint. R08 adds no Screen authority flag, schema discriminator, guard, or runtime wrapper.

## 11. Cross-Screen Evidence Boundary

The existing Candidate document boundary preserves the technical possibility of later Candidate-scoped composition:

```text
Screen 1: C#
Screen 2: Unity
Screen 3: SLG
  -> one finalized CandidateOcrDocument
  -> future Candidate-scoped evaluator
```

It also preserves exclusion persistence:

```text
Screen 1: exclusion evidence
later Screens: positive evidence
  -> all remain Candidate evidence after finalization
```

R08 does not choose document input shape, concatenation, deduplication, structured Candidate representation, Criterion Boolean generation, Rule execution, or LLM prompting.

## 12. Traceability Technical Obligation

Every future production Candidate Decision must be associated with:

1. the relevant finalized `CandidateOcrDocument`; and
2. the corresponding Candidate OCR evidence represented by that document and its embedded Screens.

Current viable anchors include `run_id`, `candidate_record_id`, `screen_id`, Candidate sequence, and the document's embedded ordered Screen evidence. These facts demonstrate technical feasibility; they do not freeze the future Decision linkage representation.

AM7-R08 adds no `DecisionEvidenceLink`, foreign key, evidence digest, Decision schema, audit record, event, or persistence revision. Exact representation remains for AM7-R12/R13.

## 13. Legacy Shadow / Debug Technical Role

Existing optional Legacy annotations may remain as:

- debug/reference evidence;
- comparison data;
- future regression observation.

In a future Am7 path they may not:

- become a Candidate Decision;
- override a Candidate Decision;
- suppress Candidate evaluation;
- trigger an Am7 action;
- become a fallback Decision when Candidate evaluation is unavailable.

No existing schema is expanded, and no shadow Decision object, logger, telemetry stream, table, or audit mechanism is introduced.

## 14. Legacy-vs-Candidate Comparison Deferral

Future acceptance may use these disagreement examples:

- **False-positive case:** earlier exclusion evidence plus a later positive Screen can make a Legacy current-Screen result differ from the Candidate Decision.
- **False-negative case:** positive conditions distributed across Screens can leave all individual Legacy Screen results false while Candidate evidence supports the future Candidate Decision.

These are future integration examples only. R08 adds no comparison persistence, logger, telemetry, dataset, table, replay record, or regression harness. AM7-R14 or later authorized integration work may define the mechanism.

## 15. AM7-R05 / AM7-R06 Protection

- AM7-R05 ScreeningProfile schema, versioning, digest, persistence, Run binding, and Configuration/Execution lifecycle remain untouched.
- AM7-R06 Rule Engine V2 remains untouched and uninvoked.
- R08 does not decide how R06 later participates in Candidate evaluation.
- Legacy `NOT`, `ANY(...)`, Parser, and AST semantics are not imported into R06.

## 16. AM7-R09–AM7-R14 Binding Constraints

These constraints bind later designs but do not implement them.

### AM7-R09 — Candidate Input Builder

- Input must originate from the Candidate-level evidence boundary.
- No individual Screen may become final production scope.
- Input construction must preserve the ability to represent relevant evidence distributed across Candidate Screens.

### AM7-R10 — AI Screening Boolean Contract

- Criterion Boolean semantics must be Candidate-scoped.
- A Legacy Screen match/non-match cannot substitute for a Candidate-scoped Criterion result.

### AM7-R11 — AI Screening Runtime

- AI Runtime must evaluate Candidate-scoped input.
- One `formal_screen.raw_text` value cannot be treated as final Candidate authority.
- Runtime success cannot itself bypass the later Candidate Decision boundary.

### AM7-R12 — Candidate Decision & Action Integration

- Candidate Decision is the sole Ocria Am7 production authority.
- Action orchestration must consume Candidate Decision, not Legacy Screen result.
- Candidate Decision must trace to the finalized Candidate document and corresponding evidence.
- Legacy results may remain non-authoritative shadow/debug/reference information only.

### AM7-R13 — Persistence / Failure Degradation

- Persistence and failure handling must preserve Candidate evidence/Decision traceability.
- R13 must not make a Screen or Legacy result a fallback production Decision.

### AM7-R14 — Replay / Overall Integration

- Integration/replay acceptance must include meaningful Legacy-vs-Candidate disagreement cases.
- R14 decides the authorized comparison/replay mechanism; R08 does not pre-create it.

## 17. Exact File Plan

### 17.1 New Files

- `docs/TID-AM7-R08-candidate-decision-boundary.md` — this design artifact.
- Later, after Frozen TID review and targeted structural acceptance: `docs/AM7-R08-acceptance-report.md`.

### 17.2 Modified Product Files

None.

### 17.3 Modified Test Files

None.

### 17.4 Protected / Untouched Files

- all runtime source files;
- all current test files;
- `docs/RPD-AM7-R08-candidate-decision-boundary.md`;
- Frozen R07 implementation and design;
- `ocr_detector.py`;
- `ocr_candidate.py`;
- `ocr_records.py`;
- `ocr_store.py`;
- `simple_brush.py`;
- `screening_profile.py` and R05 CLI/persistence;
- `screening_rule_engine.py`;
- LLM Runtime and provider configuration;
- Candidate schemas and persistence formats;
- Legacy keyword parser and matcher;
- OCR, normalization, aggregation, similarity, and Dynamic End modules;
- browser, mouse, favorite, forward, reject, skip, stop, and action code;
- dependencies, packaging, startup, and release configuration;
- all unrelated documentation.

## 18. Implementation Change Plan

Implementation Changes count: **0 runtime Changes**.

There is no runtime implementation queue under this TID. Documentation creation is not counted as a runtime Change.

The intended lifecycle is:

```text
Frozen RPD
  -> Frozen TID
  -> no runtime implementation required
  -> targeted structural acceptance
  -> Acceptance Report
  -> Human Final Review
```

If later evidence on a changed baseline reveals a concrete current violation, that is not authorization to silently convert this Option A TID to Option B. The exact violating path must be reported to Human for an updated design decision.

## 19. Acceptance / Verification Design

R08 acceptance uses the smallest targeted structural evidence. It does not add or run runtime tests merely to prove that a future feature is absent.

### 19.1 Required targeted checks

1. Confirm the authoritative RPD remains AM7-R08 v0.1 Frozen.
2. Confirm the reviewed branch/baseline matches the TID metadata or explicitly record drift.
3. Inspect the exact Legacy authority call graph documented in Section 7.
4. Confirm `scan_candidate(...)` remains evidence-only, Decision-free, and Action-free.
5. Confirm `CandidateOcrBuilder.finalize(...)` and `finalize_current_candidate_recording(...)` establish/persist evidence without Decision or Action.
6. Confirm no current targeted runtime file contains an Ocria Am7 Candidate Decision/Action production chain.
7. Confirm no R08 runtime source or test change was introduced.
8. Confirm R05, R06, R07, Candidate schema, persistence, OCR, LLM Runtime, and action code remain protected.
9. Record the later R09–R14 obligations and AC-01–AC-28 mapping in the Acceptance Report.

### 19.2 Evidence sources

- current source inspection limited to the files named in this TID;
- current file-scope review;
- Frozen R08 and R07 design documents;
- existing directly relevant R07 test structure where useful;
- the final R08 Acceptance Report.

No R07 suite is rerun solely for R08. No full regression, repository scanner, import scanner, action scanner, negative-scope test framework, dummy Candidate Decision test, or dummy Gate test is required.

## 20. AC-01–AC-28 Verification Mapping

| AC | Frozen behavior | Targeted acceptance evidence |
|---|---|---|
| AC-01 | Legacy production chain remains available | Inspect `detect_keywords(...) -> detect(...) -> confirmed_match -> view_candidate(...) -> existing action`; protected-file confirmation |
| AC-02 | Candidate owns future Am7 production scope | TID/RPD authority review; confirm no current competing Am7 Decision owner |
| AC-03 | Formal Screen text is not final authority | Inspect `ScanObservation`, callback, `OcrScreenRecord`, and absence of any Screen-to-Am7-Decision consumer |
| AC-04 | Legacy positive cannot trigger Am7 action | Confirm current action handoff is Legacy-only and no Am7 Candidate action path exists |
| AC-05 | Legacy negative cannot force Am7 rejection | Confirm no Candidate Decision/rejection consumer of Legacy non-match exists |
| AC-06 | Candidate finalization precedes future evaluation | Inspect builder/finalizer boundary; record binding R09–R12 obligation |
| AC-07 | Finalization is not a Decision | Confirm finalizer returns evidence document and optional Store write only |
| AC-08 | Cross-Screen positive composition remains possible | Inspect ordered embedded Screens and Candidate document evidence fields |
| AC-09 | Exclusion evidence persists | Confirm earlier committed `OcrScreenRecord` remains embedded after later Screens/finalization |
| AC-10 | Simultaneous viewport coexistence is not required | Candidate document/cross-Screen structural review |
| AC-11 | Decision traces to Candidate document | Review future R12/R13 obligation and current Candidate identity anchors |
| AC-12 | Decision traces to OCR evidence | Confirm document embeds corresponding Screen evidence with Candidate/run identities |
| AC-13 | Legacy shadow/debug data may remain | Inspect existing optional Legacy comparison fields on `OcrScreenRecord` |
| AC-14 | Shadow/debug data remains non-authoritative | Confirm no current consumer turns those fields into Candidate Decision/action |
| AC-15 | Disagreement is future regression evidence | Review the two deferred FP/FN acceptance examples |
| AC-16 | No comparison infrastructure | Final file-scope review: no runtime/test/schema/persistence change |
| AC-17 | AM7-R07 Complete Scan remains unchanged | Protected-file review; inspect current `scan_candidate(...)` contract without modification |
| AC-18 | Legacy OCR R07 Dynamic End remains unchanged | Protected detector/Dynamic End source and test scope confirmation |
| AC-19 | AM7-R05 remains unchanged | Protected R05 source/schema/persistence confirmation |
| AC-20 | AM7-R06 remains unchanged | Protected `screening_rule_engine.py`; confirm no R08 invocation |
| AC-21 | Legacy syntax is not imported into R06 | Inspect unchanged R06 public grammar and R08 file scope |
| AC-22 | No LLM execution | Confirm no runtime product-code change and no LLM wiring under R08 |
| AC-23 | No Criterion Boolean contract | Confirm no R10/input/Boolean artifact is added |
| AC-24 | No Candidate Decision engine or placeholder | Targeted symbol/file review and exact Option A file scope |
| AC-25 | No Am7 action integration | Confirm no runtime modification and no Candidate Decision-to-action path |
| AC-26 | No Candidate schema expansion | Protected `ocr_records.py` / Candidate builder review |
| AC-27 | No persistence expansion | Protected Store/schema review; no new persistence artifact |
| AC-28 | No later-requirement pre-implementation | Confirm 0 runtime Changes and review binding-constraint-only R09–R14 section |

All 28 Frozen ACs are mapped. No new Acceptance Criterion or runtime test is added.

## 21. Acceptance Report Contract

After the TID is Frozen, create:

`docs/AM7-R08-acceptance-report.md`

The Acceptance Report must include:

- final R08 technical conclusion;
- chosen Option A or Option B;
- current Legacy authority location;
- current Am7 evidence boundary;
- Candidate finalization boundary;
- confirmation of current Am7 Decision/Action availability;
- Screen authority review;
- cross-Screen evidence boundary review;
- traceability obligation review;
- R05/R06/R07 protected-boundary review;
- R09–R14 binding-constraint review;
- exact file scope;
- AC-01–AC-28 mapping;
- deviations;
- open issues;
- contract conflicts.

For the selected Option A, it must state exactly:

```text
Runtime Product-Code Changes: None
Runtime Test Changes: None
```

If all Frozen criteria and scope checks pass, use exactly:

`Automated Acceptance Passed / Pending Human Final Review`

Do not declare Human Accepted, Merged, or Released.

## 22. Explicit Non-Implementation

AM7-R08 shall not create, modify, or invoke:

- a `CandidateDecision` object or placeholder;
- a Decision enum, status, engine, or manager;
- `DecisionGate` or `ActionGate`;
- a guard, interceptor, enforcement wrapper, or authority enum;
- a runtime mode router;
- a shadow-decision schema;
- a Decision evidence-link schema;
- a Candidate eligibility field or `evaluation_ready` flag;
- a new persistence artifact, database, telemetry, or audit record;
- comparison infrastructure, logger, table, dataset, replay record, or regression framework;
- Candidate Input Builder or `StructuredCandidate`;
- Criterion Boolean generation;
- R06 execution or Legacy syntax migration into R06;
- LLM calls, prompts, or AI Runtime;
- Candidate Decision execution;
- Candidate/page action integration;
- favorite, forward, reject, skip, stop, browser, or mouse behavior;
- OCR capture or processing behavior;
- Dynamic End algorithms, thresholds, states, or reasons;
- R07 APIs, lifecycle, recovery, evidence construction, or finalization;
- R05 or R06 behavior;
- AM7-R09–AM7-R14 implementation;
- a generic Decision/Authority/enforcement framework.

## 23. Acceptance Preconditions and Escalation Boundary

Before targeted acceptance:

- confirm this TID is the Human-approved Frozen version;
- confirm the RPD remains AM7-R08 v0.1 Frozen;
- confirm the reviewed source baseline is identified accurately;
- preserve all Human-owned work.

Report to Human rather than creating implementation if new evidence establishes a concrete contradiction, such as an existing Am7 path that directly treats one Screen as Candidate Decision authority or triggers an Am7 action before Candidate finalization. A future baseline violation requires a revised technical decision; it does not authorize a generic framework or placeholder layer.

These are escalation boundaries, not new runtime gates or anticipated issues.

## 24. Open Issues

None.

The existing R07 Acceptance Report is accepted historical evidence and does not require reconstruction or a test rerun under R08. The current source boundary and Frozen contracts remain sufficient to choose Option A without creating runtime work.

## 25. Contract Conflicts

None.

The current repository is compatible with the Frozen R08 authority contract: Complete Scan is evidence-only, Candidate finalization is a clean future boundary, no Am7 Candidate Decision/Action production chain exists, and the existing Screen-to-action chain is the preserved Legacy runtime.

## 26. Final Technical Conclusion

AM7-R08 selects **Option A — No Runtime Product-Code Change**.

```text
Runtime Product-Code Changes: None
Runtime Test Changes: None
Implementation Changes count: 0 runtime Changes
```

No existing R08 invariant violation requires correction. The Frozen R08 authority boundary therefore remains a binding architectural constraint for later AM7-R09–AM7-R14 work, especially Candidate input, Candidate-scoped Boolean semantics, AI Runtime, and Candidate Decision/Action integration in AM7-R09 through AM7-R12.

No placeholder enforcement, schema, persistence, Decision object, runtime router, guard, action integration, test change, or product source change is authorized by this TID.
