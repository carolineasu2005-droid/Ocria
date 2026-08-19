# AM7-R07 — Candidate Complete Scan / Legacy Rule Early-Stop Decoupling

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R07
- Document Type: Technical Implementation Design
- Version: 0.1
- Status: Frozen
- Source RPD: AM7-R07 v0.1 Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r07-candidate-complete-scan`
- Working HEAD / Merged-Main Baseline: `46fbaae7356fbf17266fd07e53ab11af683cb936`
- Prepared On: 2026-08-19 (Asia/Shanghai)

## 1. Technical Objective

Implement the smallest local separation between:

1. the existing Legacy rule-driven OCR scan, where confirmed Legacy rule success may end scanning early; and
2. the AM7-R07 Complete Scan, where Legacy rule definitions, keyword-match outcomes, and rule-confirmation outcomes have no control authority.

Both paths shall reuse the same accepted OCR capture, callback, Dynamic End, safety-budget, recovery, and failure-propagation lifecycle. The implementation changes orchestration only. It does not change any Legacy OCR R02–R07 algorithm, threshold, schema, persistence format, runtime action, or downstream business behavior.

## 2. Authoritative Terminology and Contract

- **Legacy OCR R02–R07 pipeline** means the existing detail-load, fingerprint, normalization, aggregation, similarity/effective-new-content, and Dynamic End stages.
- **Legacy OCR R07 Dynamic End** is the sole authority for normal Candidate scan completion.
- **AM7-R07 Complete Scan** is the new explicit detector entry whose control flow is independent of Legacy screening rules.
- **Legacy rule confirmation** is the existing independent second OCR observation for an already matched Legacy rule. It remains part of the Legacy path only.

For identical OCR and scan-lifecycle observations, changing Legacy rule definitions, keyword-match outcomes, or Legacy rule-confirmation outcomes shall not change the AM7-R07 Complete Scan's later-screen collection, normal-completion timing, safety / technical termination reason, or Candidate evidence collection.

## 3. Targeted Repository Findings

The inspection was limited to the Frozen RPD and the current detector, Candidate evidence, persistence callback, runtime boundary, and directly relevant tests.

### 3.1 `ocr_detector.py`

- `OCRKeywordDetector.detect(rules, first_observation=None)` is the current public Legacy entry.
- `detect(...)` materializes `rules` and returns `DetectionResult(success=True, confirmed_match=False)` immediately when the list is empty. Therefore `detect([])` cannot implement Complete Scan without breaking Legacy behavior.
- The formal screen lifecycle, Legacy matching, rule confirmation, Dynamic End control, safety budget, recovery, and exception projection currently live in one `detect(...)` method.
- Each formal observation is captured or reused, assigned its formal screen index, passed through `_match_observation(...)`, appended, and delivered to `observation_callback` as `formal_screen`.
- When a Legacy rule matches, safe/full interrupt and callback/store failure checks run first; otherwise `_rule_confirmation_result(...)` performs the existing wait and independent second observation, then returns immediately.
- `_attempt_position_confirmation(...)` currently also receives rules, applies `_match_observation(...)` to its recovery capture, and may enter `_rule_confirmation_result(...)`. This is the second location that must be made rule-neutral for Complete Scan.
- `ScanObservation` already defaults `matched_keyword`, `matched_rule`, and `rule_comparison` to `None`; raw `capture_observation(...)` does not perform rule matching.
- `DetectionResult` already carries collected observations plus `dynamic_end_reason`, `abort_reason`, `interrupt_reason`, `error`, and all current Dynamic End counters. No new return type is required.
- `DynamicEndState` owns the bounded scan counters. `_safe_full_control_result(...)` applies the accepted priority and returns existing reasons.
- The detector's formal loop respects `max_scans`; safe/full control additionally uses the existing eight-slot bound. The production caller supplies `OCR_MAX_SCANS = 8`.

### 3.2 Existing Dynamic End and failure representation

- `dynamic_end_reason="scroll_bottom"` and `dynamic_end_reason="no_new_text"` are current normal Legacy OCR R07 Dynamic End outcomes in safe/full operation.
- `dynamic_end_reason="max_screen_limit"` identifies exhaustion of the existing formal screen budget. AM7-R07 interprets this as a safety termination, not natural completion.
- `interrupt_reason` is currently limited to `user_interrupted` and `runtime_expired` by the injected provider.
- Safe/full callback/store and health failures return an existing `abort_reason`, including `load_failed`, `switch_failed`, `scroll_failed`, `ocr_failed`, `focus_restore_failed`, `position_unresolved`, `store_failed`, and `unexpected_error` as applicable.
- An unhandled detector exception outside those controlled branches returns `success=False` with `error` and no normal Dynamic End reason.
- `scroll_bottom_candidate`, `recovery_reason`, and shadow prediction fields are supporting facts; by themselves they do not declare normal completion.

### 3.3 `simple_brush.py`

- `detect_keywords(...)` is the Legacy caller of `ocr_detector.detect(forward_keywords, first_observation=...)`.
- `view_candidate(...)` consumes only that Legacy result and may invoke the existing favorite/forward action flow after a confirmed rule.
- The current Candidate loop owns detail-load retries, Candidate Switch Verification, action orchestration, Candidate finalization, and transition to the next Candidate.
- The accepted production detector is constructed with `OCR_MAX_SCANS = 8`, `DynamicEndConfig(mode="full")`, the existing observation callback, the existing focus-restoration callback, and the existing interrupt provider.
- `candidate_capture_status(...)` maps the combination of `CaptureStatus` and reason without adding another schema: `scroll_bottom`, `no_new_text`, and `max_screen_limit` use `COMPLETED_WITH_LIMIT` while the reason remains distinct; interrupt and abort results use their existing abnormal statuses.
- No current Am7 AI/Evaluation consumer needs runtime wiring in AM7-R07. A separate public detector capability satisfies the Frozen RPD's distinct-path requirement and can be tested independently. Modifying `simple_brush.py` would unnecessarily touch Legacy actions and future integration, so it is protected in this TID.

### 3.4 Candidate evidence and persistence

- The actual current builder class is `CandidateOcrBuilder` in `ocr_candidate.py`.
- `record_detection_observation(...)` forwards the already captured observation to the current builder and Store path. It accepts `rule_comparison=None`.
- The builder records existing `OcrScreenRecord` instances, applies the existing R05/R06 projections, and finalizes the existing `CandidateOcrDocument`.
- A raw Complete-Scan observation naturally produces no Legacy match/comparison values. Existing optional screen fields remain schema-compatible and do not require a schema change.
- `CandidateOcrDocument` already carries the existing Dynamic End and abort projection fields. `CaptureSummary` enforces the existing mutually exclusive end/abort reason contract.
- `JsonlOcrRecordStore` persists the existing screen and Candidate types and validates their current identities. No storage change is needed.
- Candidate schema changes = None.

### 3.5 Existing targeted tests

- `tests/test_ocr_detector.py` locks Legacy confirmation, early-return, prefetched observation reuse, formal-slot counting, Dynamic End modes/reasons, callback failure priority, interrupt/error handling, and bounded recovery.
- `tests/test_ocr_stage0_integration.py` locks the observation callback, Store flow, Candidate builder/finalization, Dynamic End document projection, focus recovery, retry evidence, and existing completion/termination reason projection.
- `tests/test_ocr_candidate.py` locks Candidate evidence construction and the current `CaptureStatus` / reason combinations.
- `tests/test_ocr_text.py` locks the Legacy keyword grammar and matcher independently.
- Focused methods in `tests/test_simple_brush_ocr.py` lock detail-load retry, focus callback wiring, and Candidate Switch Verification without requiring the entire repository regression.

## 4. Minimal Factorization Options

### Option A — One private shared lifecycle with optional private Legacy rule control

- Preserve public `detect(rules, first_observation=None)`.
- Add public `scan_candidate(first_observation=None)`.
- Move the existing `detect(...)` scan body into one private `_run_scan_lifecycle(...)` method.
- Pass a non-empty private `legacy_rules` tuple only from `detect(...)`.
- Pass `legacy_rules=None` only from `scan_candidate(...)`.
- Gate all matching and confirmation calls on `legacy_rules is not None`.

This moves the least lifecycle code, retains one Dynamic End/safety implementation, and gives the Complete-Scan public API no rule input.

### Option B — Extract a pure screen collector and wrap it with Legacy confirmation

The current rule branch is interleaved with safe/full callback priority and position-confirmation recovery. Extracting a separately driven collector would require yielding control events, callbacks, or duplicated priority handling. That is more code movement and creates an unnecessary policy/orchestration abstraction.

### Option C — Duplicate the loop for Complete Scan

Copying the loop and deleting rule branches would initially avoid a shared private discriminator, but it would duplicate Dynamic End, budget, recovery, callback, and exception behavior. That creates algorithm drift risk and conflicts with the requirement to reuse the accepted lifecycle.

### Decision

Choose **Option A**.

It is one local class-level refactor, not a strategy or scanner framework. The private optional `legacy_rules` value is not public configuration or a public mode selector. It represents whether the existing Legacy-only rule behavior is present in a private shared invocation.

## 5. Public API Design

### 5.1 Preserved Legacy API

Keep the exact public signature:

```python
def detect(
    self,
    rules: Iterable[KeywordRule],
    first_observation: Optional[ScanObservation] = None,
) -> DetectionResult:
    ...
```

Contract:

- materialize the supplied iterable exactly once;
- preserve the current empty-rule immediate result with zero capture, matching, scroll, wait, callback, or state-reset effects;
- for non-empty rules, call the private shared lifecycle with that non-empty tuple;
- preserve all current Legacy matching, confirmation, priority, result, and early-return behavior;
- preserve `first_observation` identity/reuse semantics for Legacy callers.

### 5.2 New Complete-Scan API

Add the exact public method:

```python
def scan_candidate(
    self,
    first_observation: Optional[ScanObservation] = None,
) -> DetectionResult:
    ...
```

Contract:

- accepts no `rules`, rule callback, mode, stop policy, or completion callback;
- returns the existing `DetectionResult`;
- reuses the same capture, formal loop, observation callback, Dynamic End, budget, recovery, counters, and failure projection as the Legacy lifecycle;
- supports the current pre-captured first-observation optimization without another OCR capture;
- never calls `_match_observation(...)`, `matching_keyword_rule(...)`, `_observe(...)` for confirmation, `_consume_rule_confirmation(...)`, or `_rule_confirmation_result(...)`;
- always returns `confirmed_match=False` and `matched_keyword=None`;
- emits no `rule_confirmation` observation merely because captured OCR text would satisfy a Legacy rule;
- exposes no AI-specific result type and performs no Candidate finalization or action itself.

### 5.3 First-observation rule neutrality

`scan_candidate(...)` shall make the supplied observation rule-neutral before entering the shared lifecycle by using a shallow dataclass replacement with:

```python
matched_keyword=None
matched_rule=None
rule_comparison=None
```

All OCR items, text, normalization, timestamp, screen identity, and fingerprint evidence are reused; no OCR is repeated. This prevents incidental Legacy annotations on a shared prefetched observation from changing Complete-Scan control or persisted Candidate evidence. The caller's object is not mutated. Freshly captured later observations already have these fields unset because Complete Scan never invokes matching.

This is a narrow value normalization inside the new API, not a new sanitizer or framework.

## 6. Private Shared Scan-Lifecycle Design

Add one private method with this exact role and signature shape:

```python
def _run_scan_lifecycle(
    self,
    *,
    legacy_rules: Optional[Tuple[KeywordRule, ...]],
    first_observation: Optional[ScanObservation],
) -> DetectionResult:
    ...
```

The implementation is the current non-empty `detect(...)` body, moved with only the following rule-control separations.

### 6.1 Entry ownership

- `detect(...)` performs its existing rule materialization and empty fast return, then passes a non-empty tuple.
- `scan_candidate(...)` clears incidental rule fields on its optional first observation and passes `legacy_rules=None`.
- No other caller calls `_run_scan_lifecycle(...)`.

### 6.2 Formal observation processing

For every formal screen:

1. retain the existing scroll/wait behavior;
2. reuse or capture the observation exactly as today;
3. bind the existing formal fingerprint index;
4. call `_match_observation(...)` only when `legacy_rules is not None`;
5. append and notify the observation exactly once;
6. update and consume the existing Dynamic End callback facts exactly as today;
7. apply existing Dynamic End, safety, recovery, and failure control.

The main branch shall not inspect incidental `ScanObservation.matched_rule` when `legacy_rules is None`. Complete Scan always follows the non-rule lifecycle branch.

### 6.3 Position-confirmation recovery

Narrowly change `_attempt_position_confirmation(...)` to accept the same private optional Legacy rule tuple.

- With a tuple, preserve current `_match_observation(...)`, possible rule confirmation, and returned `rule_result` behavior exactly.
- With `None`, do not match the recovery observation and do not enter rule confirmation, even if its text contains a Legacy keyword or an incidental field is populated.
- Preserve focus restore, scroll retry, waits, interrupt checks, capture, callback, canonical position classification, formal-slot promotion, bottom-candidate decision, and all existing recovery reasons.

No other recovery helper or ownership changes.

### 6.4 Legacy rule confirmation

`_rule_confirmation_result(...)`, `_observe(...)`, `_match_observation(...)`, and `_consume_rule_confirmation(...)` retain their existing implementations and meaning. They are reachable only when the public Legacy entry supplied non-empty rules.

### 6.5 Lifecycle state and exception handling

The private method retains the current reset of:

- `dynamic_end_state`;
- `last_observation_result`;
- `last_position_confirmation`;
- `saw_scroll_bottom_candidate`;
- `_shadow_prediction`.

It also retains the current loop bounds, promoted-slot handling, logger behavior, returned result fields, outer exception handling, and interrupt projection. There is no second loop and no new policy object.

## 7. Legacy Compatibility Design

The implementation must preserve byte-for-byte public signature compatibility for `detect(...)` and behavioral compatibility for:

- empty rules returning before scanning;
- Legacy rule order and matching authority;
- R04 comparison remaining observational only;
- first-pass matched-rule selection;
- the existing confirmation wait;
- the second independent OCR observation against the same complete rule;
- confirmation success/failure result fields;
- confirmed-rule early return;
- safe/full priority of interrupt and callback/store failure before confirmation;
- off/shadow Legacy effects;
- formal versus non-formal fingerprint indexing;
- existing `DetectionResult` shape;
- existing `simple_brush.detect_keywords(...)`, `view_candidate(...)`, and favorite/forward behavior.

No Legacy caller is redirected to `scan_candidate(...)`. No current action orchestration is modified.

## 8. Complete-Scan Rule-Independence Design

The following conditions make rule independence structural rather than advisory:

1. `scan_candidate(...)` has no rules parameter.
2. It passes no Legacy rule object into the private lifecycle.
3. It removes incidental rule annotations from a reused first observation without recapturing OCR.
4. Fresh formal observations are captured directly and never passed to `_match_observation(...)`.
5. Position-confirmation recovery skips matching and confirmation.
6. All rule branches require `legacy_rules is not None`, not merely `observation.matched_rule is not None`.
7. No `rule_confirmation` capture, wait, callback, counter increment, or result is produced by Complete Scan.
8. Rule-specific result outputs remain non-authoritative; `confirmed_match` is always false and `matched_keyword` is always null.

Consequently, a patched or changed Legacy matcher and a patched or changed confirmation outcome are unreachable from Complete Scan. Text that would match a Legacy rule remains ordinary OCR evidence and cannot change screen count, scroll count, Dynamic End timing, termination reason, or stored Candidate evidence.

## 9. Legacy OCR R07 Dynamic End Ownership

The shared private lifecycle retains the current calls to:

- `_update_dynamic_end_state(...)`;
- `_consume_shadow_formal_callback(...)`;
- `_safe_full_control_result(...)`;
- `_recovery_is_allowed(...)`;
- `_attempt_position_confirmation(...)`.

The Complete-Scan path therefore uses the exact accepted Legacy OCR R07 Dynamic End flow. This Change shall not modify:

- `DynamicEndConfig` or `DynamicEndState` contracts;
- mode semantics;
- no-new threshold;
- position classification;
- fingerprint generation/comparison;
- R05/R06 evidence interpretation;
- scroll-bottom confirmation;
- reason values;
- safe/full priority;
- any counter bound or state-machine meaning.

No other component may declare normal completion.

## 10. Normal Completion and Safety / Technical Termination Representation

Reuse `DetectionResult` and the existing Candidate capture contracts. Interpret the existing combinations as follows:

| Outcome | Required `DetectionResult` combination | Existing Candidate projection when finalization is invoked | AM7-R07 meaning |
|---|---|---|---|
| Normal Dynamic End: bottom | `success=True`, `dynamic_end_reason="scroll_bottom"`, no `abort_reason`, `interrupt_reason`, or `error` | `CaptureStatus.COMPLETED_WITH_LIMIT` + `end_reason="scroll_bottom"` | Normal completion established by Legacy OCR R07 Dynamic End |
| Normal Dynamic End: no new text | `success=True`, `dynamic_end_reason="no_new_text"`, no `abort_reason`, `interrupt_reason`, or `error` | `CaptureStatus.COMPLETED_WITH_LIMIT` + `end_reason="no_new_text"` | Normal completion established by Legacy OCR R07 Dynamic End |
| Safety-budget exhaustion | `success=True`, `dynamic_end_reason="max_screen_limit"`, no `abort_reason`, `interrupt_reason`, or `error` | `CaptureStatus.COMPLETED_WITH_LIMIT` + `end_reason="max_screen_limit"` | Non-normal safety termination; the reason, not the shared enum label, is authoritative |
| Explicit interruption | `success=True`, `interrupt_reason` is `user_interrupted` or `runtime_expired`, no Dynamic End reason | `CaptureStatus.INTERRUPTED`, with the existing reason carried as Candidate `abort_reason` when finalized | Non-normal interruption |
| Controlled technical abort | `success=True`, non-empty existing `abort_reason`, no Dynamic End reason | `CaptureStatus.ABORTED`, with that existing abort reason | Non-normal technical termination |
| Detector exception | `success=False`, non-empty `error`, no normal Dynamic End reason | No new R07 mapping is introduced; direct result remains a technical failure until an authorized runtime consumer finalizes it | Non-normal technical termination |

Additional rules:

- `scroll_bottom_candidate=True` without `dynamic_end_reason="scroll_bottom"` is not normal completion.
- `recovery_reason` and shadow prediction fields never override the explicit reason fields.
- `max_screen_limit` is never described as natural completion, despite sharing the legacy `COMPLETED_WITH_LIMIT` enum with normal Dynamic End reasons.
- Existing fields and reason values are sufficient; no new enum, schema field, persistence revision, or general status taxonomy is added.
- AM7-R07 does not define downstream business treatment of any non-normal result.

## 11. Safety Budget Ownership

- `OCRKeywordDetector.max_scans` and the existing `DynamicEndState` slot bound continue to own formal scan counting.
- The production source remains `simple_brush.OCR_MAX_SCANS`, currently `8`.
- `scan_candidate(...)` receives no budget parameter beyond the detector's existing construction contract.
- Complete Scan does not add, reset, or separately count slots after text that would match a rule.
- Rule confirmation is absent, so Complete Scan also spends no non-formal rule-confirmation OCR attempt.
- Position-confirmation promotion continues to consume the same existing formal slot and skip the same subsequent loop slot.

No separate AI budget is introduced.

## 12. Retry, Focus Recovery, Interrupt, and Candidate Switch Preservation

### 12.1 Detail-page load retry

Owner: `simple_brush.run_detail_load_gate(...)`.

It remains outside the detector lifecycle and outside this Change. The current initial attempt plus `MAX_LOAD_RETRIES = 3`, wait behavior, hard-recovery boundary, interruption behavior, and exhaustion result remain unchanged.

### 12.2 Dynamic End position/focus recovery

Owner: `OCRKeywordDetector._recovery_is_allowed(...)` and `_attempt_position_confirmation(...)`, using the injected `restore_focus`, `scroll`, `wait`, and interrupt provider.

Only Legacy-rule handling inside the recovery observation becomes conditional. All recovery eligibility, one focus restoration, one scroll retry, settle wait, promotion, bottom confirmation, reasons, and counters remain unchanged.

### 12.3 Interrupt checks

Owner: the existing detector lifecycle and injected `interrupt_reason_provider`.

The extracted private lifecycle retains every current check and projection without adding another interrupt or Stop Condition.

### 12.4 Candidate Switch Verification

Owner: `simple_brush.prepare_candidate_switch_context(...)` and `confirm_candidate_switch(...)` before the next Candidate scan.

The existing two-action, six-observation-per-action, stable-observation, narrowly eligible focus-recovery, and `candidate_switch_failed` behavior remain untouched. Candidate Switch Verification is not moved into `scan_candidate(...)` and is not duplicated.

## 13. Candidate Evidence and Callback Design

- Complete Scan invokes the existing `observation_callback` for every formal and existing position-confirmation/promoted observation using the same capture types, formality flags, and indexes.
- It does not invoke the callback with `capture_type="rule_confirmation"`.
- Callback return values continue to drive only the existing Store/health/position/Dynamic End behavior.
- Saved observations continue through `CandidateOcrBuilder` to existing `OcrScreenRecord` instances and the existing `CandidateOcrDocument`.
- Rule-neutral observations leave existing optional Legacy comparison fields unset; no field is added or repurposed.
- Candidate schema changes = None.
- Persistence changes = None.
- Candidate finalization code changes = None.
- `scan_candidate(...)` returns the `DetectionResult`; it does not itself create or save a Candidate document. A caller with the current callback/builder can finalize through the existing path, as verified by the targeted integration test.

## 14. Runtime Orchestration Decision

No AM7-R07 runtime wiring is added to `simple_brush.py`.

Rationale:

- The Frozen RPD requires a distinct Complete-Scan path, not Future AI execution.
- A public, independently testable detector entry is an actual capability and satisfies that boundary.
- There is no accepted downstream AI/Evaluation/Decision consumer to select or consume this path yet.
- Wiring it into the current Legacy loop would risk invoking or suppressing existing favorite/forward behavior and would pre-implement later requirements.
- Existing load retry and Candidate Switch Verification remain available to a future authorized caller without relocation.

This deferral does not weaken the Complete-Scan API. It protects the current Legacy runtime and the Future AI boundary.

## 15. Failure Propagation

The shared private lifecycle preserves the current direct result contract:

- callback/store/health failures in safe/full return the existing `abort_reason`;
- explicit stops return the existing `interrupt_reason`;
- Dynamic End returns the existing explicit reason;
- outer exceptions remain fail-closed as `success=False` with `error`;
- no Boolean rule success is returned by Complete Scan;
- no partial-success, recovery result, diagnostic hierarchy, retry policy, or fallback is added.

The Complete-Scan caller must inspect the same explicit reason fields. This TID does not authorize a downstream business decision or action based on them.

## 16. File Plan

### 16.1 New Files

No new product or test module.

After implementation and verification, create the required acceptance artifact:

- `docs/AM7-R07-acceptance-report.md`

### 16.2 Modified Files

- `ocr_detector.py`
  - preserve `detect(...)`;
  - add `scan_candidate(...)`;
  - extract `_run_scan_lifecycle(...)`;
  - make only the rule portion of `_attempt_position_confirmation(...)` conditional on the private Legacy rule tuple.
- `tests/test_ocr_detector.py`
  - add focused public API, Legacy compatibility, rule-independence, Dynamic End, safety, recovery, interrupt, and technical-failure tests.
- `tests/test_ocr_stage0_integration.py`
  - add focused proof that Complete Scan uses the existing callback/builder/document path, collects later screens without rule confirmation, and preserves the existing completion/termination reason distinction.

### 16.3 Protected / Untouched Files

- `docs/RPD-AM7-R07-candidate-complete-scan.md`
- `simple_brush.py`
- `ocr_candidate.py`
- `ocr_records.py`
- `ocr_store.py`
- `ocr_text.py`
- `ocr_normalization.py`
- `ocr_aggregation.py`
- `ocr_similarity.py`
- `ocr_similarity_sidecar.py`
- `ocr_calibration.py`
- `screening_profile.py`
- `screening_profile_cli.py`
- `screening_rule_engine.py`
- `llm_provider_runtime.py`
- `mouse_motion.py`
- all other browser, mouse, favorite, forward, reject, skip, and action code
- `requirements.txt`
- `requirements-ocr.txt`
- `requirements-build.txt`
- packaging and startup scripts
- all unrelated tests and documentation

## 17. Implementation Change Plan

Implementation Changes count: **1**.

### Change 1 — Add rule-independent Complete Scan to the existing detector lifecycle

Files:

- `ocr_detector.py`
- `tests/test_ocr_detector.py`
- `tests/test_ocr_stage0_integration.py`

Implementation:

1. Keep the exact public `detect(...)` signature and empty-rule fast return.
2. Extract the current non-empty scan body to `_run_scan_lifecycle(...)` without altering Dynamic End, callback, counters, recovery, or exception handling.
3. Add `scan_candidate(first_observation=None) -> DetectionResult`.
4. Clear incidental Legacy rule fields on a supplied Complete-Scan first observation through a shallow replacement without recapturing OCR.
5. Gate all matching and confirmation work on a non-null private Legacy rule tuple.
6. Keep recovery mechanics identical while skipping Legacy match/confirmation for Complete Scan.
7. Add only the focused tests described below.

Verification:

- new Complete-Scan tests;
- full detector targeted suite;
- focused Stage-0 Candidate evidence suite;
- Candidate builder and Legacy grammar regression suites;
- selected unchanged simple-brush retry/focus/switch tests;
- targeted compile check.

AC mapping: AC-01–AC-24.

## 18. Targeted Test Design

Test method names may be grouped where setup reuse makes one method clearer; the behaviors below are mandatory.

### 18.1 `tests/test_ocr_detector.py` additions

1. `test_detect_empty_rules_preserves_legacy_zero_scan_fast_return`
   - call `detect([])`;
   - assert the existing result shape and zero capture, backend, matcher, callback, scroll, and wait effects.
2. `test_scan_candidate_is_separate_rule_free_public_entry`
   - call `scan_candidate()` successfully;
   - assert it does not accept `rules` as a keyword or positional scan-control input;
   - assert `DetectionResult` return type, `confirmed_match=False`, and null matched keyword.
3. `test_scan_candidate_reuses_rule_neutral_first_observation_without_recapture`
   - supply a first observation already carrying Legacy match/comparison annotations;
   - assert no OCR recapture for that screen;
   - assert the caller object is not mutated;
   - assert the Complete-Scan observation has null rule annotations and later screens remain collectible.
4. `test_scan_candidate_never_calls_matcher_or_rule_confirmation`
   - use OCR text that would satisfy a Legacy rule;
   - patch matcher and confirmation helpers to fail if invoked;
   - assert no `rule_confirmation` observation or confirmation wait and assert later screens are collected.
5. `test_scan_candidate_rule_independence_for_identical_lifecycle_observations`
   - run identical captured pages and callback position decisions with different patched Legacy matcher/confirmation outcomes;
   - assert identical formal observations, callback capture types, scroll/capture counts, Dynamic End timing, explicit termination reason, and rule-neutral result fields.
6. `test_scan_candidate_uses_existing_dynamic_end_and_safety_limit`
   - cover existing `scroll_bottom` or `no_new_text` normal Dynamic End;
   - separately cover `max_screen_limit`;
   - assert reason distinction and unchanged slot counting.
7. `test_scan_candidate_recovery_skips_rule_confirmation_and_preserves_focus_scroll_bounds`
   - force the existing position-confirmation path with matching-looking text;
   - assert one existing focus restoration, one scroll retry, unchanged callback types/reason, and no rule confirmation.
8. `test_scan_candidate_preserves_interrupt_abort_and_error_projection`
   - exercise the current interrupt, controlled callback failure, and outer exception paths without inventing new errors;
   - assert no normal Dynamic End reason on those results.

### 18.2 `tests/test_ocr_stage0_integration.py` additions

1. `test_complete_scan_collects_later_screens_into_existing_candidate_document`
   - start the existing builder and FakeStore;
   - use `record_detection_observation` as callback;
   - run `scan_candidate(...)` through existing Dynamic End with early matching-looking text;
   - assert later formal screen records are saved, no rule-confirmation record exists, and finalization yields the existing `CandidateOcrDocument` with unchanged aggregation/similarity evidence.
2. `test_complete_scan_preserves_existing_completion_reason_projection`
   - assert normal Legacy OCR R07 Dynamic End reasons such as `scroll_bottom` / `no_new_text` remain distinguishable through the existing result and Candidate evidence fields;
   - assert safety termination remains explicitly identified by `max_screen_limit` through those same existing fields.

No new test framework, repository scanner, or test-only product hook is permitted.

## 19. Targeted Regression Commands

Run each formal command once after implementation, capturing its real output from command start.

### 19.1 Changed detector and Complete-Scan behavior

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_detector -v
```

### 19.2 Existing callback, Dynamic End, recovery, and Candidate evidence integration

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_stage0_integration -v
```

### 19.3 Existing Candidate builder/status/reason contract

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_candidate -v
```

### 19.4 Legacy keyword grammar and matcher contract

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_text -v
```

### 19.5 Unchanged detail-load retry, focus wiring, and Candidate Switch Verification

Run only the directly relevant existing methods because `simple_brush.py` is protected:

```powershell
.\venv\Scripts\python.exe -m unittest -v tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_retry_three_success_uses_four_ocr_calls_and_three_waits tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_confirm_switch_first_unchanged_recovers_then_confirms tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_confirm_switch_focus_recovery_failure_stops_before_retry tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_r07_detector_receives_shared_safe_focus_restore_callback
```

### 19.6 Targeted compile check

```powershell
.\venv\Scripts\python.exe -m compileall ocr_detector.py tests\test_ocr_detector.py tests\test_ocr_stage0_integration.py
```

No full repository regression, benchmark, packaging, dependency resolver, or unrelated accepted suite is required.

## 20. AC-01–AC-24 Verification Mapping

| AC | Planned implementation / behavior | Targeted verification |
|---|---|---|
| AC-01 | Preserve exact `detect(rules, first_observation=None)` public entry | Empty-rule and full Legacy detector suite |
| AC-02 | Non-empty Legacy rules retain independent confirmation and early return | Existing confirmation, later-screen match, safe/full priority, and new regression assertions in `tests.test_ocr_detector` |
| AC-03 | Add separate `scan_candidate(first_observation=None)`; it is not `detect([])` | New public-entry and Legacy empty-rule tests |
| AC-04 | Complete Scan has no rule input and gates all private rule branches off | Matcher/confirmation fail-if-called test |
| AC-05 | Matching-looking early OCR text remains evidence and later screens are collected | Complete-Scan later-screen detector and Stage-0 integration tests |
| AC-06 | Reuse `_safe_full_control_result(...)` and existing Dynamic End lifecycle | New normal Dynamic End test plus full detector/Stage-0 suites |
| AC-07 | No new completion algorithm or threshold; only loop factorization | Protected-file scope review and detector diff review in acceptance report |
| AC-08 | Preserve `max_scans`, slot counting, and existing eight-slot production source | Complete-Scan max-limit test plus existing formal-slot tests |
| AC-09 | Preserve interrupt, controlled abort, error, and budget exits | New failure-projection test plus existing safe/full tests |
| AC-10 | Interpret explicit reason combinations; `max_screen_limit` remains non-normal | Reason-matrix assertions in detector/Stage-0 tests |
| AC-11 | Keep detail-load and detector retry behavior unchanged | Existing selected load-retry method and Stage-0 retry suite |
| AC-12 | Keep focus-recovery triggers and one-recovery bounds unchanged | New Complete-Scan recovery test plus existing detector/Stage-0 focus tests |
| AC-13 | Keep Candidate Switch Verification in `simple_brush.py`, untouched | Selected existing switch-confirmation and failure methods; protected diff review |
| AC-14 | Do not modify Legacy OCR R02–R07 algorithms or thresholds | Full detector and Stage-0 targeted suites; protected OCR module review |
| AC-15 | Reuse callback, `OcrScreenRecord`, `CandidateOcrBuilder`, and `CandidateOcrDocument` | New Complete-Scan Stage-0 document test plus `tests.test_ocr_candidate` |
| AC-16 | Add no Candidate/Profile/Rule/Decision/Action fields | Candidate schema protected-file review and existing Candidate tests |
| AC-17 | Leave Legacy grammar, matcher, R04 comparison, and confirmation meaning unchanged | `tests.test_ocr_text` plus Legacy detector suite |
| AC-18 | Do not touch AM7-R05 implementation or contracts | Protected-file/final-scope review |
| AC-19 | Do not touch or invoke AM7-R06 Rule Engine V2 | Protected-file/final-scope review and import/diff confirmation limited to changed files |
| AC-20 | Complete Scan emits evidence only and no Candidate decision | `DetectionResult`-only API assertions and changed-file/import review of `ocr_detector.py` |
| AC-21 | No LLM, prompt, AI Runtime, Criterion Evaluation, or Boolean mapping | Planned file scope and acceptance protected-scope review |
| AC-22 | No Decision or favorite/forward/reject/skip action integration | Changed-file/import review of `ocr_detector.py`; protected/untouched confirmation for `simple_brush.py`; absence of Decision/Action runtime wiring |
| AC-23 | No persistence, schema, status, framework, or Run-binding expansion | File-scope review and existing Candidate tests |
| AC-24 | Same OCR/lifecycle observations yield identical Complete-Scan behavior despite changed Legacy rule/match/confirmation outcomes | Dedicated deterministic rule-independence test |

All 24 Frozen ACs are mapped. The mapping does not require 24 separate test methods.

## 21. Acceptance Report Contract

After implementation and successful required verification, create:

`docs/AM7-R07-acceptance-report.md`

It must record:

- final implemented functionality;
- final file scope;
- exact targeted command results;
- AC-01–AC-24 mapping;
- Legacy compatibility review;
- Complete-Scan rule-independence review;
- Legacy OCR R07 Dynamic End ownership review;
- safety / technical termination review;
- Candidate evidence boundary review;
- protected-scope review;
- deviations;
- open issues;
- contract conflicts.

If all Frozen criteria and scope checks pass, use exactly:

`Automated Acceptance Passed / Pending Human Final Review`

Do not declare Human Accepted, Merged, or Released.

## 22. Explicit Non-Implementation

Implementation under this TID shall not add or change:

- an OCR algorithm;
- Legacy OCR R07 Dynamic End algorithm;
- bottom, repeated-screen, stability, fingerprint, similarity, normalization, aggregation, or completion algorithms;
- Dynamic End modes, thresholds, states, reasons, or priority;
- a completion status framework or status taxonomy;
- a Stop Condition;
- a generic scanner, orchestration, policy, strategy, callback, Gate, Guard, Wrapper, or Validator framework;
- detail-load retry, Candidate retry, AI retry, or resume policy;
- focus management or Candidate switch logic;
- persistence or database contracts;
- Candidate schema or a new Candidate document type;
- ScreeningProfile;
- AM7-R06 Rule Engine V2;
- LLM calls, prompts, Criterion Evaluation, AI Boolean output, or AI Runtime;
- Candidate Decision;
- favorite, forward, reject, skip, browser, mouse, or action integration;
- RuleSet-to-Run binding;
- CLI or GUI;
- dependencies, packaging, startup scripts, or release configuration;
- AM7-R08–AM7-R14 functionality.

## 23. Implementation Preconditions and Escalation Boundaries

Before implementation:

- confirm the authoritative RPD remains AM7-R07 v0.1 Frozen;
- confirm the implementation branch remains the authorized AM7-R07 branch;
- inspect the current diff and preserve Human-owned work.

Stop and report to Human rather than expanding scope if implementation evidence shows that:

- exact Legacy `detect(...)` behavior cannot be preserved without a product change;
- rule independence would require changing a Legacy OCR R02–R07 algorithm;
- the existing result/reason fields cannot express the frozen distinction without a schema/status change;
- a protected runtime, Candidate schema, persistence, Profile, Rule Engine, AI, or action file must change.

These are escalation boundaries, not additional gates or anticipated issues.

## 24. Open Issues

None.

The targeted inspection resolves the public API, private factorization, result reuse, first-observation behavior, Candidate evidence reuse, runtime deferral, file scope, and verification plan without changing the Frozen product contract.

## 25. Contract Conflicts

None.

The existing empty-rule fast return requires a separate public Complete-Scan method; it does not conflict with the Frozen RPD. Existing `DetectionResult`, `CaptureStatus` plus explicit reason, callback, builder, and Candidate document contracts are sufficient without a new status or schema.

## 26. Final Technical Conclusion

AM7-R07 will be implemented as one local `OCRKeywordDetector` lifecycle refactor with two explicit public entries:

- `detect(rules, first_observation=None)` retains exact Legacy semantics and rule-confirmed early-stop;
- `scan_candidate(first_observation=None)` accepts no rule input, performs no Legacy match or confirmation work, and reuses the same Dynamic End, safety, recovery, callback, and `DetectionResult` lifecycle.

The implementation modifies only `ocr_detector.py` and two directly related test modules. Runtime AI wiring, Candidate schemas, persistence, Legacy OCR algorithms, Profile, Rule Engine, actions, dependencies, and all later requirements remain outside scope.
