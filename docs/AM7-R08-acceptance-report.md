# AM7-R08 Acceptance Report

## 1. Metadata

| Field | Value |
|---|---|
| Product | Ocria |
| Generation | Am7 |
| Requirement | AM7-R08 — Candidate-level Decision Boundary |
| Document Type | Acceptance Report |
| Report Version | 0.1 |
| Source RPD | `RPD-AM7-R08-candidate-decision-boundary.md` v0.1 Frozen |
| Source TID | `TID-AM7-R08-candidate-decision-boundary.md` v0.1 Frozen |
| Requirement Branch | `am7-r08-candidate-decision-boundary` |
| Frozen merged-main baseline / current HEAD | `843e73fd71f71219e4cd323c9eea79a78847f75f` |
| Prepared date | 2026-08-20 (Asia/Shanghai) |
| Acceptance Status | Automated Acceptance Passed / Pending Human Final Review |

## 2. Acceptance Status

`Automated Acceptance Passed / Pending Human Final Review`

All Frozen AM7-R08 requirements and AC-01–AC-28 pass targeted structural acceptance. This report does not declare Human Accepted, Human Approved, Merged, or Released.

## 3. Requirement Scope

AM7-R08 freezes an architectural authority boundary:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

This acceptance determines whether the current repository is structurally compatible with that boundary and whether the completed no-op TID execution was correct. It does not require or assess new runtime functionality.

The acceptance scope is limited to the Frozen R08 documents, the accepted R07 historical report, and the exact detector, Candidate evidence, Store, Legacy action-handoff, and R06 modules named by the Frozen TID. No repository-wide audit was performed.

## 4. Authoritative Documents

- `CODEX-CONSTITUTION.md` — governing execution discipline.
- `docs/RPD-AM7-R08-candidate-decision-boundary.md` — v0.1 Frozen.
- `docs/TID-AM7-R08-candidate-decision-boundary.md` — v0.1 Frozen.
- `docs/AM7-R07-acceptance-report.md` — accepted historical evidence for the R07 Complete-Scan boundary.

The R07 acceptance was referenced as historical evidence only. R07 was not reopened, its suites were not rerun, and its evidence was not reconstructed.

## 5. Frozen Technical Outcome

Chosen Technical Outcome: **Option A — No Runtime Product-Code Change**.

Targeted inspection confirms the Option A conditions:

- current Complete Scan is evidence-only;
- no current Am7 Candidate Decision object, schema, engine, or manager exists;
- no current Am7 Candidate Decision-to-action integration exists;
- no Screen currently has Am7 production Decision authority;
- Candidate finalization provides the clean future evaluator boundary;
- the existing Screen-to-action chain remains the preserved Legacy BossOCR path;
- no current implementation violates the Frozen R08 invariant.

No Option B correction is required.

## 6. TID Execution Result

- TID Execution: Completed
- Chosen Technical Outcome: Option A — No Runtime Product-Code Change
- Runtime Product-Code Changes: None
- Runtime Test Changes: None
- Product Files Modified: None
- Test Files Modified: None
- Implementation Changes count: 0 runtime Changes
- Deviations: None
- Open Issues: None
- Contract Conflicts: None
- Ready for Acceptance: Yes

The zero-runtime-change execution is the expected successful execution of the Frozen TID, not an omitted implementation.

## 7. Verification Method

Verification used targeted structural inspection only:

1. confirmed current branch and HEAD directly from repository metadata;
2. confirmed the R08 RPD and TID are v0.1 Frozen;
3. confirmed the R07 Acceptance Report exists and used its accepted findings as historical context;
4. inspected the exact Legacy match, confirmation, judgment, and action handoff;
5. inspected `scan_candidate(...)` and its private lifecycle selection;
6. inspected Screen evidence, Candidate builder/finalizer, Candidate document, and Store persistence boundaries;
7. inspected current Decision-like identifiers before classifying their semantics;
8. inspected R06's public Boolean-combiner boundary and current targeted runtime invocation scope;
9. confirmed the acceptance-step write scope is this report only.

No runtime test, R07 rerun, full regression, benchmark, package smoke, network test, dependency validation, scanner, compliance harness, or dummy test was run or created.

## 8. Runtime Product-Code Changes

`Runtime Product-Code Changes: None`

## 9. Runtime Test Changes

`Runtime Test Changes: None`

## 10. Implementation Changes Count

`Implementation Changes count: 0 runtime Changes`

Documentation creation is not counted as a runtime implementation Change.

## 11. Legacy BossOCR Authority Review

The preserved Legacy production chain is:

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

Owner review:

- `OCRKeywordDetector.detect(...)` is the public Legacy detector entry.
- `_match_observation(...)` applies the existing Legacy rule matcher and records match/comparison annotations.
- `_rule_confirmation_result(...)` performs the independent second OCR confirmation and returns `DetectionResult.confirmed_match`.
- `simple_brush.detect_keywords(...)` converts confirmed Legacy match into `keyword_hit`.
- `simple_brush.view_candidate(...)` hands a positive Legacy Boolean to the existing favorite or forward action according to the existing Legacy runtime configuration.

This chain remains production-authoritative in the preserved Legacy context. R08 did not modify, disable, convert, or reroute it. Its existence is not an Am7 Candidate Decision path because it neither consumes a Candidate Decision nor claims Candidate-scoped Am7 authority.

Result: Pass.

## 12. R07 Complete-Scan Review

`OCRKeywordDetector.scan_candidate(first_observation=None) -> DetectionResult` remains:

- rule-independent: it accepts no rule input and calls `_run_scan_lifecycle(legacy_rules=None, ...)`;
- evidence-only: it returns the existing `DetectionResult` and collected observations;
- Decision-free: it creates no Candidate Decision or Match/Reject result;
- Action-free: it invokes no favorite, forward, reject, skip, browser, mouse, or other Candidate/page action.

A reused first observation is copied with incidental Legacy rule annotations cleared. Formal and recovery observations enter no Legacy match/confirmation branch when `legacy_rules is None`.

No targeted runtime source calls `scan_candidate(...)`; it remains the accepted evidence capability for a future authorized Am7 caller. The accepted R07 report records its prior targeted verification. No R07 test was rerun for R08.

Result: Pass.

## 13. Candidate Finalization Boundary Review

The existing evidence boundary is:

```text
OcrScreenRecord
  -> CandidateOcrBuilder
  -> CandidateOcrBuilder.finalize(...)
  -> CandidateOcrDocument
```

Current owners and behavior:

- `CandidateOcrBuilder.add_screen(...)` collects validated Screen evidence and existing R05/R06 evidence projections.
- `CandidateOcrBuilder.finalize(...)` constructs one `CandidateOcrDocument` from committed Screens, capture summary, document text/segments, and existing summaries.
- `simple_brush.finalize_current_candidate_recording(...)` calls the builder finalizer, attaches existing Dynamic End summary fields, and may call `ocr_record_store.save_candidate(...)`.
- `JsonlOcrRecordStore.save_candidate(...)` validates and persists the existing Candidate evidence document.

Finalization does not call Candidate Evaluation, produce Match or Reject, imply evaluation success, guarantee complete evidence, or authorize a production action.

Candidate finalization is a necessary future evaluation boundary, not a Candidate Decision.

Result: Pass.

## 14. Ocria Am7 Current Decision/Action State

Targeted inspection found no current:

- Candidate Decision object or schema;
- Candidate Decision status, engine, or manager;
- Candidate Decision-to-production-Action chain;
- `CandidateOcrDocument`-to-final-Match/Reject consumer;
- R06-to-production-Action wiring;
- Screen-to-Am7-Candidate-Decision wiring;
- `CandidateDecision` placeholder, `DecisionGate`, `ActionGate`, runtime mode router, guard, interceptor, or generic authority framework.

Two existing names were checked and are not future Candidate production Decisions:

- `EffectiveDecision` classifies whether an OCR similarity segment represents effective new content inside `OcrSimilarityResult`.
- `PositionDecision` classifies page position/change evidence for Legacy OCR R07 Dynamic End.

Neither value produces recruiting Match/Reject or invokes an action.

Result: Pass.

## 15. Screen Authority Review

The following current values remain evidence or Legacy data rather than Am7 final production authority:

- `ScanObservation`;
- one formal Screen's raw text;
- one `OcrScreenRecord`;
- OCR boxes and raw OCR text;
- normalized/comparison text;
- Screen fingerprint;
- aggregation and similarity projections;
- Legacy Screen match and non-match;
- existing comparison/debug fields.

No current Ocria Am7 production consumer converts any one of these values directly into final Candidate Match, Reject, favorite, forward, reject, skip, or another Candidate/page production action. The only Screen-to-action conversion is the separately preserved Legacy chain documented in Section 11.

No Screen authority flag or enforcement layer is required.

Result: Pass.

## 16. Cross-Screen Evidence Review

`CandidateOcrDocument` is a viable Candidate-level evidence container because it retains:

- an ordered tuple of committed `OcrScreenRecord` values;
- each Screen's raw OCR boxes/text and `screen_id`;
- normalized/comparison evidence and fingerprints;
- aggregation/similarity projections;
- Candidate document text and segments when built;
- Candidate/run identity and capture summary.

Therefore distributed positive evidence such as C#, Unity, and SLG on different Screens remains representable at Candidate scope. Earlier exclusion evidence also remains embedded in the finalized Candidate document after the viewport changes and later positive Screens are captured.

No Candidate evaluation, input builder, concatenation, deduplication, `StructuredCandidate`, Criterion Boolean generation, Rule execution, or prompt construction was performed or added.

Result: Pass.

## 17. Traceability Review

Current Candidate evidence provides viable future traceability anchors:

- `run_id`;
- `candidate_record_id`;
- `screen_id`;
- Candidate sequence and timestamps;
- ordered embedded Screen evidence;
- the finalized Candidate document and its evidence projections.

These anchors make the Frozen future relationship technically feasible:

```text
Future Candidate Decision
  -> finalized CandidateOcrDocument
  -> corresponding OCR evidence
```

Exact linkage remains deferred. R08 created no Decision evidence link, foreign key, digest, Decision schema, audit/event record, or persistence contract.

Result: Pass.

## 18. Legacy Shadow / Debug Review

`OcrScreenRecord` already contains optional Legacy/comparison projections including `rule_evaluation_mode`, `legacy_match`, `r04_match`, `comparison_outcome`, `legacy_rule_index`, and `r04_rule_index`.

They may remain future Am7 shadow, debug, diagnostic, comparison/reference, or regression evidence. They currently do not constitute an Am7 Candidate Decision and may not later override a Candidate Decision, suppress Candidate evaluation, directly trigger an Am7 action, or become fallback production authority.

No shadow schema, Decision object, logger, telemetry, table, or persistence expansion was added.

Result: Pass.

## 19. Legacy-vs-Candidate Regression Principle

The Frozen future regression examples remain:

### False-positive scope error

An earlier Screen contains exclusion evidence while a later Screen contains the current positive evidence. A Legacy current-Screen judgment may be positive, while the future Candidate judgment must retain the earlier exclusion evidence.

### False-negative scope error

Positive requirements are distributed across multiple Screens. Individual Legacy Screen judgments may all be false while the Candidate-level evidence supports all required conditions.

These are future integration/regression examples only. R08 added no comparison infrastructure, persistence, logger, telemetry, dataset, table, replay record, or regression harness.

Result: Pass.

## 20. R05 Protection Review

AM7-R05 ScreeningProfile remains outside R08. Criterion/Profile schema, versioning, digest, persistence, Run binding, and Configuration/Execution lifecycle were not modified or invoked by the R08 no-op execution.

Result: Pass.

## 21. R06 Protection Review

`screening_rule_engine.py` remains an unchanged pure Boolean combiner over a supplied Criterion ID-to-Boolean mapping:

- immutable `ScreeningRule` and `ScreeningRuleSet` public values;
- `evaluate_rule_set(rule_set, criterion_results) -> bool`;
- no Screen, Candidate document, browser, or action dependency.

No targeted R08 runtime module invokes `evaluate_rule_set(...)`. No Legacy `NOT`, `ANY(...)`, Parser, or AST semantics were imported into R06.

The `EffectiveDecision` enum found in `ocr_records.py` belongs to pre-existing OCR similarity evidence and is unrelated to the R06 Rule result or future Candidate Decision.

Result: Pass.

## 22. R07 Protection Review

AM7-R07 remains unchanged:

- Complete Scan is rule-independent, evidence-only, Decision-free, and Action-free;
- `detect(...)`, `scan_candidate(...)`, and `_run_scan_lifecycle(...)` were not changed by R08;
- Legacy OCR R07 Dynamic End algorithms, thresholds, states, reasons, safety budgets, retry, and focus recovery remain unchanged;
- Candidate Switch Verification remains unchanged;
- Candidate evidence construction and finalization remain unchanged.

The R07 Acceptance Report supplies accepted historical evidence; no R07 suite was rerun.

Result: Pass.

## 23. R09–R14 Binding Constraints

The Frozen R08 contract binds later Requirements without implementing them.

### R09 — AI Candidate Input Builder

- Candidate-level evidence boundary is the input source.
- No individual Screen becomes final production scope.
- Multi-Screen evidence remains representable.

### R10 — AI Screening Boolean Contract

- Criterion Boolean semantics are Candidate-scoped.
- A Legacy Screen Boolean cannot substitute for a Candidate Criterion result.

### R11 — AI Screening Runtime

- Runtime evaluates Candidate-scoped input.
- One Screen cannot become final Candidate authority.
- Successful AI output does not itself become production Action authority.

### R12 — Candidate Decision & Action Integration

- Candidate Decision becomes the sole Ocria Am7 production authority.
- Action consumes Candidate Decision, not Legacy Screen Match.
- Candidate Decision traces to the finalized Candidate document and corresponding evidence.

### R13 — AI Persistence / Failure Degradation

- Persistence and failure handling preserve Candidate Decision/evidence traceability.
- No Screen or Legacy result becomes fallback production Decision.

### R14 — AI Replay / Overall Integration

- Integration/replay tests meaningful Legacy-vs-Candidate disagreement cases.
- The original false-positive and false-negative scope-error patterns remain covered.

No AM7-R09–AM7-R14 functionality was implemented.

Result: Pass.

## 24. Exact File Scope

### Final R08 Requirement artifacts

- `docs/RPD-AM7-R08-candidate-decision-boundary.md` — existing, v0.1 Frozen, unmodified by acceptance.
- `docs/TID-AM7-R08-candidate-decision-boundary.md` — existing, v0.1 Frozen, unmodified by acceptance.
- `docs/AM7-R08-acceptance-report.md` — new acceptance artifact.

### Runtime and delivery scope

- Runtime Product-Code Changes: None
- Runtime Test Changes: None
- Schema Changes: None
- Persistence Changes: None
- Dependency Changes: None
- Packaging/Release Changes: None
- Implementation Changes count: 0 runtime Changes

The acceptance-step file write is limited to this report. Untracked Requirement documentation is an expected documentation artifact and is not an implementation deviation.

## 25. AC-01–AC-28 Individual Acceptance Mapping

| AC | Frozen requirement | Acceptance evidence | Result |
|---|---|---|---|
| AC-01 | Legacy production chain remains available. | Current `view_candidate(...) -> detect_keywords(...) -> detect(...) -> matcher -> confirmation -> confirmed_match -> keyword_hit -> existing action` call graph remains present. | Pass |
| AC-02 | Candidate owns Ocria Am7 production scope. | Frozen RPD/TID plus absence of any current competing Am7 Candidate Decision owner; later R09–R14 obligations are explicit. | Pass |
| AC-03 | One formal Screen is not final authority. | `ScanObservation` and `OcrScreenRecord` feed evidence/finalization only; no Screen-to-Am7-Match/Reject consumer exists. | Pass |
| AC-04 | Legacy positive cannot directly trigger Am7 action. | Legacy positive triggers only the preserved Legacy action handoff; no Am7 Candidate Decision/action path exists. | Pass |
| AC-05 | Legacy negative cannot independently force Candidate rejection. | No Candidate rejection consumer of Legacy non-match or all-false Screen outcomes exists. | Pass |
| AC-06 | Candidate finalization precedes formal future evaluation. | `CandidateOcrBuilder.finalize(...)` creates the clean Candidate evidence boundary; the binding later-evaluator obligation is frozen. | Pass |
| AC-07 | Finalization is not itself a Decision. | Finalizer creates `CandidateOcrDocument`; orchestration optionally stores it and invokes no Evaluation, Match, Reject, or action. | Pass |
| AC-08 | Cross-Screen positive composition remains possible. | Finalized document embeds ordered Screen evidence and document text/segments, preserving distributed facts. | Pass |
| AC-09 | Earlier exclusion evidence persists. | Earlier committed `OcrScreenRecord` values remain in the finalized Candidate document after later Screens are collected. | Pass |
| AC-10 | Relevant facts need not coexist in one viewport. | Candidate document boundary retains multi-Screen evidence independently of the current viewport. | Pass |
| AC-11 | Future Decision traces to Candidate document. | `run_id`, `candidate_record_id`, Candidate sequence, and finalized document provide viable anchors; binding R12/R13 obligation recorded. | Pass |
| AC-12 | Future Decision traces to OCR evidence. | Candidate document embeds ordered Screen records with `screen_id`, raw boxes/text, and derived evidence. | Pass |
| AC-13 | Legacy shadow/debug information may remain. | Existing optional Legacy/comparison fields remain on `OcrScreenRecord`. | Pass |
| AC-14 | Legacy shadow/debug information is non-authoritative. | No current consumer turns those fields into Am7 Candidate Decision or action; later non-authority constraint is explicit. | Pass |
| AC-15 | Legacy-vs-Candidate disagreement remains future regression evidence. | False-positive and false-negative scope-error examples are preserved in Section 19. | Pass |
| AC-16 | No comparison infrastructure. | No runtime, schema, persistence, logger, telemetry, dataset, or test infrastructure was added. | Pass |
| AC-17 | R07 Complete Scan remains unchanged. | Current `scan_candidate(...)` matches accepted R07 evidence-only contract; R08 made no runtime/test change. | Pass |
| AC-18 | Dynamic End remains unchanged. | Current shared lifecycle and accepted R07 report retain existing Dynamic End ownership; R08 changed nothing. | Pass |
| AC-19 | R05 remains unchanged. | Zero runtime Changes and protected R05 boundary; no R08 modification or invocation. | Pass |
| AC-20 | R06 remains unchanged and uninvoked. | Current pure Boolean API remains; no targeted R08 runtime module invokes it. | Pass |
| AC-21 | Legacy syntax is not imported into R06. | Current R06 supports only its Frozen Criterion-ID / `AND` / `OR` grammar; no Legacy `NOT`, `ANY(...)`, Parser, or AST import. | Pass |
| AC-22 | No LLM execution. | Zero runtime Changes; no LLM call, prompt, or AI Runtime integration under R08. | Pass |
| AC-23 | No Criterion Boolean contract. | No Candidate input, Criterion Boolean generation, or R10 artifact was created. | Pass |
| AC-24 | No Candidate Decision engine, object, placeholder, Gate, router, guard, or authority framework. | Targeted runtime inspection found none; `EffectiveDecision` and `PositionDecision` are OCR evidence classifications, not Candidate Decisions. | Pass |
| AC-25 | No Am7 production action integration. | No Candidate Decision-to-action chain exists and no runtime source was changed. | Pass |
| AC-26 | No Candidate/schema expansion. | Existing Screen/Candidate schemas remain evidence-only; no R08 schema change occurred. | Pass |
| AC-27 | No persistence expansion. | Existing Store only persists current evidence contracts; no R08 persistence artifact or change occurred. | Pass |
| AC-28 | No R09–R14 pre-implementation. | R09–R14 appear only as binding architectural constraints; runtime implementation Changes remain zero. | Pass |

All 28 Frozen Acceptance Criteria pass.

## 26. Non-Implementation / Boundary Review

The acceptance confirms no R08 implementation of or change to:

- Candidate Decision object, schema, enum, status, engine, or manager;
- `DecisionGate`, `ActionGate`, guard, interceptor, enforcement wrapper, authority enum, or runtime mode router;
- shadow-decision or Decision evidence-link schema;
- Candidate eligibility or evaluation-ready field;
- new persistence, comparison, telemetry, audit, replay, or regression infrastructure;
- Candidate Input Builder or `StructuredCandidate`;
- Criterion Boolean generation or R06 execution;
- LLM calls, prompts, or AI Runtime;
- Candidate Decision execution or production action integration;
- favorite, forward, reject, skip, stop, browser, or mouse behavior;
- OCR, Dynamic End, Candidate Switch, Candidate evidence, or finalization behavior;
- R05, R06, or R07 behavior;
- AM7-R09–AM7-R14 functionality;
- generic Decision/Authority/enforcement framework;
- runtime source, tests, schemas, dependencies, packaging, or release configuration.

Result: Pass.

## 27. Deviations

None.

## 28. Open Issues

None.

## 29. Contract Conflicts

None.

## 30. Final Acceptance Conclusion

The current repository is structurally compatible with the Frozen AM7-R08 Candidate-level Decision Boundary. The preserved Legacy BossOCR chain remains authoritative only in its Legacy context; R07 Complete Scan and Candidate finalization remain evidence-only; no current Ocria Am7 Candidate Decision/Action production chain exists; and no Screen has current Am7 production authority.

The completed TID execution correctly selected Option A and introduced no runtime or test change. The Frozen authority contract is technically grounded and remains binding on AM7-R09–AM7-R14, especially the Candidate input, Boolean, Runtime, Decision, and Action work in AM7-R09 through AM7-R12.

Final status:

`Automated Acceptance Passed / Pending Human Final Review`
