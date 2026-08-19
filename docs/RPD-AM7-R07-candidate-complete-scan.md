# AM7-R07 — Candidate Complete Scan / Legacy Rule Early-Stop Decoupling

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R07
- Document Type: Requirement / Product Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r07-candidate-complete-scan`
- Working HEAD at Design Time: `46fbaae7356fbf17266fd07e53ab11af683cb936`
- Upstream Baseline / Current Merged-Main Baseline: `HEAD`, `main`, and `origin/main` at `46fbaae7356fbf17266fd07e53ab11af683cb936`
- Prepared On: 2026-08-19 (Asia/Shanghai)

The Requirement Branch records the actual checked-out branch at design time. No branch change, merge, rebase, commit, or other Git mutation is part of this RPD task. Local `main`, `origin/main`, and the merge base between the working HEAD and `origin/main` all resolved to the recorded merged-main baseline.

## Terminology

This document distinguishes requirement identifiers from the existing BossOCR / Legacy OCR pipeline stage names:

- **Legacy OCR R02**: detail-page loading detection.
- **Legacy OCR R03**: page fingerprint.
- **Legacy OCR R04**: OCR text normalization.
- **Legacy OCR R05**: multi-screen incremental aggregation.
- **Legacy OCR R06**: page similarity / effective-new-content logic.
- **Legacy OCR R07 Dynamic End**: existing dynamic scan-ending logic.
- **Legacy OCR R02–R07 pipeline**: the existing OCR evidence and scan-lifecycle pipeline comprising those stages.
- **AM7-R07 Complete Scan**: the new Am7 orchestration path specified by this requirement.

Any statement about completion authority in this document refers explicitly to **Legacy OCR R07 Dynamic End**, not to the AM7-R07 requirement number.

## 1. Requirement Summary

BossOCR's current Legacy scanning path accepts screening keyword/rule input and may stop scanning after an early rule match is independently confirmed. That behavior remains valid for the Legacy workflow.

AM7 Candidate-level processing needs a different orchestration path. Candidate OCR evidence must not be truncated merely because an early screen satisfies a Legacy business screening rule. AM7-R07 therefore separates business-rule early-stop from the Am7 scan lifecycle while reusing the existing Legacy OCR R02–R07 pipeline, its normal Dynamic End authority, its bounded safety behavior, and the existing `CandidateOcrDocument` evidence boundary.

The smallest required product change is two explicit orchestration behaviors:

1. The backward-compatible Legacy path retains rule-confirmed early-stop.
2. The AM7-R07 Complete Scan path ignores business-rule success as a scan-ending signal and continues until existing normal completion or an existing safety / technical termination boundary.

## 2. Goals

AM7-R07 shall:

1. Preserve the existing Legacy rule-driven scanning behavior and entry point compatibility.
2. Establish a distinct AM7 Candidate complete-scan path.
3. Remove keyword, rule, screening success, and “enough evidence to pass” from scan-ending authority in that path.
4. Retain Legacy OCR R07 Dynamic End as the sole normal scan-completion authority.
5. Preserve existing safety budget, retry, focus recovery, interrupt, technical-failure, and Candidate Switch Verification behavior.
6. Reuse the existing Legacy OCR R02–R07 pipeline and `CandidateOcrDocument` evidence model.
7. Give later Candidate-level processing an evidence boundary that is not shortened by a Legacy business match.
8. Keep normal completion semantically distinct from safety / technical termination.

## 3. Non-Goals

AM7-R07 does not include:

- changing Legacy keyword grammar or matching semantics;
- replacing the Legacy `detect(rules)` behavior;
- rewriting any Legacy OCR R02–R07 algorithm;
- a new OCR loader;
- a new page-fingerprint algorithm;
- new text normalization;
- a new aggregation algorithm;
- a new similarity or effective-new-content algorithm;
- a new Dynamic End algorithm, bottom detector, stability detector, completion detector, or completion heuristic;
- unlimited scanning or retry;
- safety-budget redesign, enlargement, bypass, reset, or reinterpretation;
- a generic retry or resume framework;
- a new focus manager;
- a new Candidate switch algorithm;
- Candidate schema redesign or a second Candidate document model;
- ScreeningProfile or Screening Rule Engine changes;
- LLM calls, prompts, AI Runtime, Criterion Evaluation, or an AI Boolean result contract;
- Candidate Decision or Candidate/page Action integration;
- persistence or database changes unless a later technical review proves one unavoidable to meet this frozen product contract;
- GUI or CLI work;
- a new Gate, Guard, Scanner, Wrapper, Sanitizer, integrity framework, completion framework, orchestration framework, event bus, plugin system, audit framework, status taxonomy, generic failure hierarchy, or Stop Condition;
- AM7-R08–AM7-R14 pre-implementation.

## 4. Targeted Repository Findings

The inspection was limited to the current Legacy detector/orchestration, Candidate evidence construction, and directly related tests.

### 4.1 Current entry and early-stop location

- `OCRKeywordDetector.detect(rules, first_observation=None)` in `ocr_detector.py` is the current Legacy rule-driven entry point.
- Passing no rules to the current `detect(rules)` does not mean “scan without rule termination”; it returns successfully without entering the multi-screen scan. The AM7-R07 Complete Scan therefore requires a distinct orchestration path rather than treating `detect([])` as complete scanning.
- The current detector combines scan lifecycle and Legacy keyword/rule matching. A matched rule is subjected to the existing independent rule-confirmation observation, and confirmed success returns a `DetectionResult` immediately instead of collecting remaining screens.
- Directly relevant detector tests confirm the current behavior: an early confirmed match uses one formal scan slot plus its confirmation observation and terminates the remaining Legacy scan, while a miss can continue through the configured formal scan slots.
- Legacy matching uses the existing keyword-rule parsing and matching path. AM7-R07 has no reason to change that grammar or its matching semantics.

### 4.2 Current scan lifecycle and Legacy OCR R07 Dynamic End

- The current production orchestration constructs the detector with `DynamicEndConfig(mode="full")` and `OCR_MAX_SCANS = 8`.
- The formal scan loop is bounded by the configured maximum screen count.
- Existing Legacy OCR R07 Dynamic End uses the existing fingerprints, normalization, aggregation, similarity/effective-new-content state, and bounded position-confirmation flow. It can report natural ending evidence such as confirmed scroll bottom or consecutive no-new-text completion.
- The existing maximum-screen result is separately identifiable through `dynamic_end_reason="max_screen_limit"`. For AM7-R07 product semantics, reaching that fixed safety budget is a safety termination, not proof of natural Candidate scan completion.
- Existing interrupt, callback/store failure, OCR/technical failure, and abort information is already carried by the detector result through fields such as `interrupt_reason`, `abort_reason`, `error`, and `dynamic_end_reason`. Exact representation reuse or minimal adjustment is a TID decision; this RPD does not create a new status taxonomy.
- In the current safe/full control flow, existing interrupt and technical checks retain priority over business rule confirmation.

### 4.3 Existing bounded recovery and switching controls

- Detail-page load detection is bounded by the initial attempt plus `MAX_LOAD_RETRIES = 3`; exhaustion follows the existing recovery or stop behavior.
- Existing Dynamic End position confirmation has bounded focus restoration and one bounded scroll retry. It feeds the existing Legacy OCR R07 Dynamic End decision and is not a separate completion algorithm.
- Candidate Switch Verification is already bounded by two switch actions and six observations per action, with the existing stable-observation rule and narrowly eligible single focus-recovery retry.
- A Candidate switch must be confirmed before OCR scanning of the next Candidate proceeds. A `candidate_switch_failed` result stops the current flow under existing behavior.
- AM7-R07 does not alter any of these budgets, thresholds, retry conditions, or failure outcomes.

### 4.4 Existing Candidate evidence boundary

- `CandidateOcrDocumentBuilder` aggregates committed `OcrScreenRecord` evidence and finalizes the existing `CandidateOcrDocument` with capture summary, document text/segments, normalization, aggregation, similarity, and Dynamic End evidence.
- Existing capture records already retain ending and abort information. Current capture-status mapping groups some bounded endings under `COMPLETED_WITH_LIMIT`, while the associated reason distinguishes `scroll_bottom`, `no_new_text`, and `max_screen_limit`.
- The product-level distinction frozen here can therefore be carried through the existing result/evidence boundary. Whether the TID needs a minimal mapping clarification is a technical design question; a second Candidate schema or a new general status framework is not justified.
- The current Legacy UI orchestration lets a confirmed rule match directly enter its existing favorite/forward action path. The AM7-R07 Complete Scan must not use that Legacy match-to-action control path.

## 5. Legacy Scanning Path

The Legacy path remains:

```text
Candidate
  -> existing Legacy OCR scanning
  -> existing Legacy keyword/rule matching and confirmation
  -> confirmed rule success may terminate the Legacy scan early
  -> existing Legacy result/action flow
```

The existing `detect(rules)` API, or an equivalent fully backward-compatible Legacy entry point if technical refactoring is necessary, remains available. “Backward-compatible” includes the current ability for independently confirmed Legacy rule success to end the remaining Legacy scan and feed the existing Legacy result/action flow.

AM7-R07 does not make the Legacy path collect all Candidate screens and does not reinterpret Legacy rule success.

## 6. AM7 Candidate Complete-Scan Path

The AM7-R07 Complete Scan path is:

```text
Candidate
  -> Legacy OCR R02 detail-page loading detection
  -> Legacy OCR R03 page fingerprint
  -> Legacy OCR R04 OCR text normalization
  -> Legacy OCR R05 multi-screen incremental aggregation
  -> Legacy OCR R06 page similarity / effective-new-content logic
  -> Legacy OCR R07 Dynamic End
  -> CandidateOcrDocument
  -> future Candidate-level processing
```

This is a distinct orchestration entry, conceptually `scan_candidate()`. Its exact Python name, signature, module placement, and internal factorization remain TID decisions.

The operation exists to gather Candidate evidence. It must be functionally independent of Legacy screening rules and must not require or consume screening `rules` as scan-control or scan-termination input. For the same OCR and scan-lifecycle observations, changing Legacy rule definitions, keyword match outcomes, or Legacy rule-confirmation outcomes must not change later-screen collection, normal-completion timing, the safety / technical termination reason, or Candidate evidence collection in the AM7-R07 Complete Scan. Legacy rule or match information may exist incidentally inside shared private implementation, but it is semantically irrelevant to the complete-scan control flow and has no scan-ending authority. It cannot declare normal completion, produce an Am7 Candidate decision, or trigger an action.

The complete-scan path reuses the existing OCR stages and evidence construction. It is not a second OCR implementation.

## 7. Business-Rule Early-Stop Semantics

Business-rule early-stop means that a keyword or rule outcome ends scanning because the Candidate has already satisfied a screening condition.

- It remains allowed in the Legacy scanning path.
- It is forbidden in the AM7-R07 Complete Scan path.
- A keyword match, Legacy rule match, confirmed screening success, or assertion that there is “already enough evidence to pass” is not scan completion in the AM7-R07 Complete Scan path.
- An early-screen rule match in the AM7-R07 Complete Scan path cannot prevent later screens from being captured when the existing scan lifecycle would otherwise reach them.
- AM7-R07 must not reintroduce equivalent business-rule early-stop under a different name or callback.

This distinction concerns control authority, not a change to Legacy keyword grammar or matching results.

## 8. Normal Scan-Completion Authority

Under normal scanning conditions, only the existing **Legacy OCR R07 Dynamic End** determines that the Candidate OCR scan has reached its natural completion point.

For the AM7-R07 Complete Scan path:

- confirmed scroll-bottom and existing no-new-content completion remain examples of normal completion as determined by the current Legacy OCR R07 Dynamic End contract;
- business screening success is never normal completion;
- safety-budget exhaustion is not natural completion;
- interruption, abort, retry exhaustion, and unrecoverable technical failure are not natural completion.

No AM7-R07 component may compete with, wrap into a replacement for, or reinterpret the existing normal-completion decision.

## 9. Legacy OCR R07 Dynamic End Ownership

Legacy OCR R07 Dynamic End continues to own the normal ending question:

> Has the existing OCR evidence and page-position lifecycle reached the Candidate's natural scan completion point?

AM7-R07 changes only whether business screening success can seize control of the Am7 scan lifecycle before that answer is reached. It does not change the Legacy OCR R07 Dynamic End inputs, algorithms, thresholds, consecutive-evidence rules, position-confirmation behavior, reason meanings, or outputs.

Existing safety controls may still stop execution before Legacy OCR R07 Dynamic End establishes normal completion. That does not transfer normal-completion ownership to the safety control.

## 10. Safety / Technical Termination Boundary

The AM7-R07 Complete Scan has two permitted lifecycle outcomes at this requirement boundary:

1. **Normal completion**: Legacy OCR R07 Dynamic End establishes the existing natural completion condition.
2. **Safety / technical termination**: an already-existing bounded or technical condition stops scanning before normal completion is established.

Existing safety / technical termination examples include:

- the configured formal screen limit (`max_screen_limit`);
- bounded load or recovery exhaustion;
- explicit interruption;
- unrecoverable OCR, capture, callback/store, focus, or scrolling failure;
- Candidate Switch Verification failure before scanning the next Candidate;
- another existing technical stop already owned by the current lifecycle.

These conditions remain authoritative for safety. They must not be bypassed merely to collect more evidence. They also must not be silently reported as normal complete-scan success.

AM7-R07 does not introduce a new Stop Condition or decide the downstream business treatment of a technically terminated Candidate. The TID may select the smallest accurate reuse of existing status/reason fields needed to preserve the distinction.

## 11. Exact Meaning of “Complete Scan”

A **Candidate Complete Scan** is a scanning path whose lifecycle is not terminated by business screening-rule success and which continues until either:

- the existing Legacy OCR R07 Dynamic End determines normal scan completion; or
- an already-existing safety / technical termination boundary stops scanning.

“Complete Scan” describes freedom from business-rule truncation. It does not mean infinite scanning, unlimited retries, bypassed budgets, ignored interrupts or failures, guaranteed natural completion, or permission to manufacture evidence after a technical stop.

A safety- or technically terminated attempt followed the complete-scan orchestration path, but it did not thereby achieve normal complete-scan success.

## 12. Safety Budget Preservation

The existing safety budget remains active and independent of screening-rule outcomes.

- AM7-R07 does not remove, enlarge, reset, bypass, or reinterpret the configured maximum formal scan count.
- Reaching the existing maximum remains a valid stop boundary.
- Reaching the maximum does not prove natural completion.
- The current value and its configuration ownership are implementation facts, not a new AM7-R07 constant contract; TID must preserve the then-current accepted configuration rather than inventing a new budget.

## 13. Retry Preservation

All existing bounded retry semantics remain available and unchanged, including detail-load and scan-position recovery behavior.

AM7-R07 neither adds retry opportunities to force completeness nor removes retries because business matching no longer ends the scan. Existing retry eligibility, counts, waits, ordering, exhaustion behavior, interrupt handling, and associated observations remain owned by their current contracts.

No AI retry, Candidate retry, generic retry framework, or resume framework is introduced.

## 14. Focus Recovery Preservation

Existing focus recovery remains active in the same narrowly defined situations and with the same bounds.

Removing Legacy business-rule early-stop from the AM7 path must not disable, duplicate, broaden, or redesign focus recovery. Focus recovery is a technical recovery mechanism; it is neither normal completion nor a business decision.

## 15. Candidate Switch Verification Preservation

Existing Candidate Switch Verification remains the authority for determining whether the browser has moved to the intended next Candidate before scanning begins.

- It remains required where the current flow requires it.
- Its current action, observation, stable-evidence, retry, and focus-recovery bounds remain unchanged.
- It cannot be bypassed to make the AM7-R07 Complete Scan appear continuous.
- A switch failure remains an existing technical stop and does not mean that the next Candidate completed scanning.
- Candidate Switch Verification is not a new Candidate scan-ending mechanism; it protects the boundary between Candidate lifecycles.

## 16. CandidateOcrDocument Boundary

`OcrScreenRecord -> CandidateOcrDocument` remains the OCR evidence pipeline and Candidate evidence boundary.

Where technically possible, the AM7-R07 Complete Scan shall reuse the current screen recording, incremental aggregation, finalization, and `CandidateOcrDocument` construction. It shall not create a parallel Candidate document type or copy the same evidence into an AI-specific schema.

`CandidateOcrDocument` remains evidence only. It must not absorb:

- ScreeningProfile data;
- Profile version or criteria digest merely for this scan change;
- R06 `Rule` or `RuleSet` data;
- Legacy keyword/rule configuration;
- Criterion ID-to-Boolean results;
- role-specific Candidate fields;
- Candidate Decision or action state.

Normal completion and safety / technical termination must remain accurately distinguishable through the smallest compatible result/evidence representation. AM7-R07 does not prescribe a new persistence or status model.

## 17. Legacy Compatibility

Compatibility is a product requirement, not merely a migration preference.

- Existing Legacy callers retain a rule-driven detector entry path.
- Existing Legacy rule parsing, matching, independent confirmation, early-stop, result interpretation, and result/action flow remain semantically available.
- Introducing AM7-R07 Complete Scan must not silently route Legacy callers through complete scanning.
- Introducing AM7-R07 Complete Scan must not route Am7 Candidate evidence collection through Legacy match-to-action behavior.
- Shared implementation may be factored only if the two public behaviors remain deterministic and explicit.

## 18. Legacy OCR R02–R07 Algorithm Isolation

AM7-R07 is an orchestration/control-authority change. It does not modify the algorithms, thresholds, or output interpretations of:

- Legacy OCR R02 detail-page loading detection;
- Legacy OCR R03 page fingerprint;
- Legacy OCR R04 OCR text normalization;
- Legacy OCR R05 multi-screen incremental aggregation;
- Legacy OCR R06 page similarity / effective-new-content logic;
- Legacy OCR R07 Dynamic End.

The implementation may share or minimally separate existing loop control so the AM7 path cannot terminate on business success. It may not use that refactoring as authority to tune OCR behavior or build a generic scanning/orchestration framework.

## 19. AM7-R05 Boundary

AM7-R05 ScreeningProfile remains unchanged. AM7-R07 neither reads nor mutates its Criterion schema, Profile versioning, `criteria_digest`, persistence, Run binding, or Configuration/Execution lifecycle.

Screening criteria remain separate configuration. They are not copied into `CandidateOcrDocument` and are not used as complete-scan termination inputs.

## 20. AM7-R06 Boundary

AM7-R06 Screening Rule Engine V2 remains unchanged. AM7-R07 does not alter or invoke its `Rule`, `RuleSet`, Boolean mapping, tokenizer/parser, fixed multi-Rule ANY, or failure semantics.

The term “rule” in Legacy rule-confirmed early-stop refers to the existing Legacy keyword/rule behavior, not to authorization to evaluate an AM7-R06 `RuleSet` during OCR scanning.

## 21. Future Evaluation / AI / Decision / Action Boundary

AM7-R07 ends at establishing the appropriate Candidate OCR evidence boundary for later Candidate-level processing.

It does not:

- call an LLM;
- create or select an AI prompt;
- evaluate Criterion text;
- produce a Criterion ID-to-Boolean mapping;
- execute the AM7-R06 Rule Engine;
- produce a Candidate Decision;
- infer pass, fail, skip, manual review, or a third business state;
- choose retry-AI or retry-Candidate behavior;
- trigger favorite, forward, reject, stop-run, or another Candidate/page action.

Future requirements will decide whether and how a normally completed or technically terminated `CandidateOcrDocument` enters Evaluation, Decision, and Action. A screen-level Legacy keyword hit can never itself become the final Am7 Candidate decision.

## 22. Invariants

1. Legacy rule-driven early-stop remains available to the Legacy path.
2. AM7-R07 Complete Scan and Legacy rule-driven scanning are distinct orchestration paths.
3. AM7-R07 Complete Scan is functionally independent of Legacy rule definitions, keyword match outcomes, and Legacy rule-confirmation outcomes; for the same OCR and scan-lifecycle observations, they cannot alter later-screen collection, normal-completion timing, safety / technical termination reason, Candidate evidence collection, or scan termination.
4. Screening success is not scan completion.
5. Legacy OCR R07 Dynamic End remains the normal Candidate scan-completion authority.
6. AM7-R07 does not create a second normal-completion detector.
7. Existing safety / technical termination remains valid.
8. Safety / technical termination does not automatically mean normal complete-scan success.
9. The existing safety budget remains active.
10. Existing retry semantics remain active.
11. Existing focus recovery remains active.
12. Existing Candidate Switch Verification remains active.
13. Legacy OCR R02–R07 algorithms remain unchanged.
14. `CandidateOcrDocument` remains the Candidate evidence boundary.
15. `CandidateOcrDocument` does not absorb Profile or Rule business configuration.
16. A screen-level match never becomes the final Am7 Candidate Decision.
17. AM7-R07 does not call an LLM or perform Criterion Evaluation.
18. AM7-R07 does not execute Candidate Decision or final Candidate/page Action.
19. AM7-R05 ScreeningProfile remains unchanged.
20. AM7-R06 Screening Rule Engine V2 remains unchanged.
21. No persistence, schema, or framework expansion is introduced merely for AM7-R07.
22. No AM7-R08–AM7-R14 functionality is pre-implemented.

## 23. Acceptance Criteria

### AC-01 — Legacy entry remains available

The existing `detect(rules)` API, or an equivalent backward-compatible Legacy entry point, remains callable by existing Legacy orchestration.

### AC-02 — Legacy early-stop remains valid

An independently confirmed Legacy keyword/rule match may continue to terminate the remaining scan in the Legacy path and feed the existing Legacy result/action flow.

### AC-03 — Separate AM7 path exists

A distinct AM7 Candidate complete-scan entry exists. Its behavior cannot be selected accidentally merely by passing an empty Legacy rule list.

### AC-04 — Business match has no AM7 ending authority

Keyword match, Legacy rule match, screening success, and “enough evidence to pass” cannot terminate the AM7-R07 Complete Scan or declare normal completion.

### AC-05 — Later screens remain collectible

When a match occurs on an early screen and neither Legacy OCR R07 Dynamic End nor an existing safety / technical boundary has stopped scanning, the AM7-R07 Complete Scan continues and can collect later Candidate screens.

### AC-06 — Existing normal completion remains authoritative

The AM7-R07 Complete Scan stops normally when the existing Legacy OCR R07 Dynamic End establishes its existing normal completion condition.

### AC-07 — No alternate completion algorithm

No new or alternate bottom, stability, fingerprint, no-new-content, Dynamic End, or complete-scan completion detector is introduced.

### AC-08 — Safety budget remains active

The existing configured screen/safety budget remains enforced without increase, reset, bypass, or rule-dependent reinterpretation.

### AC-09 — Existing safety and technical stops remain effective

Existing interruption, retry exhaustion, budget exhaustion, and unrecoverable technical failure paths can still stop the AM7-R07 Complete Scan.

### AC-10 — Technical stop is not normal completion

A safety- or technically terminated scan exposes its actual non-normal cause through the smallest compatible existing result/evidence contract and is not silently reported as normal complete-scan success.

### AC-11 — Retry behavior is preserved

Existing bounded retry eligibility, count, ordering, waits, interruption behavior, and exhaustion outcomes remain unchanged.

### AC-12 — Focus recovery is preserved

Existing focus-recovery triggers, bounds, ordering, and failure behavior remain unchanged and available to the AM7-R07 Complete Scan where the current pipeline uses them.

### AC-13 — Candidate Switch Verification is preserved

Existing Candidate Switch Verification remains required and bounded as today; it is neither bypassed nor reimplemented, and switch failure still prevents scanning an unverified next Candidate.

### AC-14 — Legacy OCR algorithms remain isolated

Targeted regression evidence confirms unchanged accepted behavior for Legacy OCR R02 loading, R03 fingerprint, R04 normalization, R05 aggregation, R06 similarity/effective-new-content, and Legacy OCR R07 Dynamic End.

### AC-15 — Existing Candidate evidence path is reused

AM7-R07 Complete Scan records existing `OcrScreenRecord` evidence and uses the existing `CandidateOcrDocument` construction/finalization path wherever technically possible; no second Candidate document model is introduced.

### AC-16 — Candidate schema remains evidence-only

No role-specific, ScreeningProfile, Criterion, Legacy rule, AM7-R06 Rule/RuleSet, Boolean result, Decision, or Action field is added to the Candidate evidence schema for AM7-R07.

### AC-17 — Legacy keyword contract remains unchanged

Legacy keyword grammar, matching, normalization relationship, independent confirmation, and confirmed-result semantics remain unchanged.

### AC-18 — AM7-R05 remains unchanged

AM7-R05 Criterion/Profile schema, versioning, digest, persistence, Run binding, and lifecycle contracts receive no AM7-R07 modification.

### AC-19 — AM7-R06 remains unchanged

AM7-R06 Rule/RuleSet types, Boolean mapping, parser, fixed ANY evaluation, and failure contracts receive no AM7-R07 modification or invocation.

### AC-20 — Screen match is not Candidate Decision

No screen-level Legacy keyword/rule match is emitted or consumed as the final Am7 Candidate Decision.

### AC-21 — No AI or Criterion Evaluation

AM7-R07 contains no LLM call, AI prompt, AI Runtime use, Criterion Evaluation, or Criterion ID-to-Boolean generation.

### AC-22 — No Decision or Action integration

AM7-R07 creates no Candidate Decision and triggers no favorite, forward, reject, skip, stop-run, or other Candidate/page action from the complete-scan path.

### AC-23 — No unrelated persistence or framework expansion

AM7-R07 adds no RuleSet-to-Run binding, database contract, new persistence layer, generic orchestration/retry/completion framework, status taxonomy, or AM7-R08–AM7-R14 functionality.

### AC-24 — Deterministic path separation and rule independence

Given the same accepted OCR and scan-lifecycle observations, the Legacy path deterministically retains rule-confirmed early-stop. In the AM7-R07 Complete Scan, changing Legacy rule definitions, keyword match outcomes, or Legacy rule-confirmation outcomes does not change later-screen collection, normal-completion timing, safety / technical termination reason, or Candidate evidence collection; the path proceeds deterministically until the existing normal or safety / technical boundary.

## 24. Known Limitations / Explicit Deferrals

- The exact complete-scan Python function name and signature are deferred to TID.
- The smallest internal factorization that shares OCR logic without sharing business ending authority is deferred to TID.
- The exact reuse or minimal clarification of current `DetectionResult`, `CaptureStatus`, `dynamic_end_reason`, `abort_reason`, and `interrupt_reason` representation is deferred to TID. The frozen product distinction between normal completion and safety / technical termination is not deferred.
- The downstream treatment of a safety- or technically terminated Candidate is deferred to later Evaluation / Decision integration requirements.
- No guarantee is made that every Candidate reaches natural Dynamic End under technical failure or safety-budget exhaustion.
- AM7-R07 does not provide history, resume, partial-result recovery, diagnostics expansion, manual review, or retry policy.

## 25. Open Issues

None.

The current result/evidence contracts retain enough reason information to preserve the required semantic distinction. Selecting the smallest representation in TID is an implementation choice, not an unresolved product decision.

## 26. Contract Conflicts

None.

The current early return on confirmed Legacy rule success is compatible with the preserved Legacy path. The current empty-rule fast return shows why a separate AM7-R07 Complete Scan entry is required, but it does not conflict with the requested product contract. Existing ending, safety, evidence, and Candidate-switch information can be reused without redesigning accepted AM7-R01–AM7-R06 behavior.

## 27. Final Product Conclusion

AM7-R07 freezes one narrow architectural separation: Legacy business screening success may continue to end the Legacy scan early, but it has no scan-ending authority in the AM7-R07 Complete Scan path.

The AM7-R07 Complete Scan reuses the Legacy OCR R02–R07 pipeline, retains Legacy OCR R07 Dynamic End as the sole normal scan-completion authority, preserves every existing safety and recovery boundary, and produces the existing `CandidateOcrDocument` evidence boundary wherever technically possible. A stop caused by safety or technical limits remains a stop, not a declaration of normal completion.

No Profile, Rule Engine, LLM, Evaluation, Decision, Action, persistence, schema, OCR-algorithm, or framework expansion is authorized by this RPD.
