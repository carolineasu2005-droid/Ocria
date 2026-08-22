# Ocria Am7 — AM7-R12 Candidate Decision & Action Integration

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R12
- Requirement Name: Candidate Decision & Action Integration
- Document Type: Acceptance Report
- Requirement Branch: `am7-r12-candidate-decision-action-integration`
- Upstream Baseline: `ca3cf7b3a4ceda091f67d2e8fc65e535623b7caf`
- RPD: v0.1 Frozen
- TID: v0.1 Frozen

## 2. Acceptance Status

- Implementation: Completed
- Automated Acceptance: Passed
- Human Final Review: Pending

## 3. Frozen Source Documents

- `docs/RPD-AM7-R12-candidate-decision-action-integration.md`: Version 0.1, Status Frozen.
- `docs/TID-AM7-R12-candidate-decision-action-integration.md`: Version 0.1, Status Frozen.

Both documents identify AM7-R12, the requirement branch, upstream baseline, AC-01 through AC-24, and R01 through R43. They were inspected as the acceptance authority and were not modified during this acceptance task.

## 4. Requirement / Implementation Summary

AM7-R12 adds the minimum Candidate-level Decision boundary between R11 and the accepted R06 Rule Engine. A finalized normal `CandidateOcrDocument` reaches R11; R11 `completed` is evaluated by the one Run-bound R06 `ScreeningRuleSet`; the resulting immutable `CandidateDecision` is `qualified`, `rejected`, or `ai_failed`. Only `qualified` reaches the existing favorite/forward call sites. The existing Candidate/batch continuation owns all subsequent control flow.

The implementation supplies explicit repeatable Rule input, one immutable RuleSet binding per live Run, one valid Provider configuration load per Run, rule-neutral Complete Scan, and narrow R11/R12/action orchestration. It does not redesign upstream R05–R11 contracts or protected action, OCR, calibration, switch, browser, or mouse mechanics.

## 5. Branch and Baseline

- Current branch: `am7-r12-candidate-decision-action-integration`
- Current `HEAD`: `ca3cf7b3a4ceda091f67d2e8fc65e535623b7caf`
- Expected upstream baseline: `ca3cf7b3a4ceda091f67d2e8fc65e535623b7caf`

`HEAD` equals the upstream baseline. The R12 implementation is intentionally uncommitted; no implementation commit SHA is claimed.

## 6. Final Changed-File Scope

Implementation and focused-test scope reviewed:

- New: `candidate_decision.py`
- Modified: `simple_brush.py`
- New: `tests/test_candidate_decision.py`
- New: `tests/test_candidate_decision_integration.py`
- Modified: `tests/test_simple_brush_ocr.py`

Documentation scope reviewed:

- `docs/RPD-AM7-R12-candidate-decision-action-integration.md` (Frozen)
- `docs/TID-AM7-R12-candidate-decision-action-integration.md` (Frozen)
- `docs/AM7-R12-acceptance-report.md` (this report)

`git status --short` and `git diff --name-status` showed the two tracked modified files and the authorized untracked R12 files. The untracked implementation/test/Frozen-document files were confirmed to exist directly. No unexpected runtime or test file change was found.

## 7. Final Functionality

- `CandidateDecision` is a frozen, two-field value with exactly `qualified`, `rejected`, and `ai_failed` normal statuses.
- `decide_candidate()` copies the R11 Candidate identity exactly, short-circuits failed AI results before R06, and otherwise calls public `evaluate_rule_set()` with the same RuleSet and mapping objects.
- `--screening-rule` is repeatable, preserves raw expressions, and is independent of Legacy keyword input. Interactive mode collects one expression per entry.
- `main()` builds one RuleSet before `run()`; `run()` accepts that required keyword-only object and retains it for the live invocation.
- `run()` validates the saved Profile first, then loads one valid Provider configuration before OCR storage and Candidate execution. No provider/model fallback or per-Candidate reload is added.
- `initialize_ocr()` and `ensure_ocr_region_calibrated()` are no longer gated by Legacy keyword state. `view_candidate()` uses accepted `scan_candidate()` and has no Legacy keyword action branch.
- Only retained normal finalized documents with `COMPLETED` or `COMPLETED_WITH_LIMIT` reach R11/R12. Stop, abort, interrupt, empty, recovery, and cleanup paths do not.
- The normal order is finalization, retained document, R11, R12, qualified-only existing action, then existing continuation. For non-last Candidates, switch context remains prepared before finalization.
- `rejected` and `ai_failed` call no action and reset the existing `forward_consecutive` counter. `no_forward_mode` preserves `qualified` while suppressing real forwarding and does not fall back to favorite.

## 8. CandidateDecision Contract Verification

`candidate_decision.py` contains only the required imports, the frozen `CandidateDecision` value, and `decide_candidate()`. Dataclass inspection and focused tests confirm exactly two fields, immutable assignment, the three permitted statuses, exact ID copy, and required type/value errors.

For failed R11 results, the function returns `ai_failed` without calling R06. For completed R11 results, it invokes the public R06 evaluator once with the exact supplied RuleSet and mapping, yielding `qualified` or `rejected`. R06 validation/input errors propagate unchanged; no fourth status, action result, persistence field, reason, or framework is introduced.

## 9. RuleSet Input / Binding Verification

`parse_args()` accepts repeatable `--screening-rule` entries unchanged. `prompt_screening_rule_expressions()` retains nonblank raw input and requires at least one expression. `_build_screening_rule_set()` uses only `ScreeningRule(expression)` and `ScreeningRuleSet(...)`.

The existing startup-mode predicate is not redefined by formal Profile/Rule flags. The established noninteractive path requires both Profile ID and at least one Rule before `run()`; the interactive path obtains Rules after a Profile is prepared. `main()` constructs one immutable RuleSet and passes the exact object to required keyword-only `run_bound_rule_set`. Candidate processing has no RuleSet reconstruction, store, ID, version, digest, derivation from Criteria, Legacy conversion, or automatic all-Criteria AND.

## 10. AIProviderConfig Binding Verification

After saved Profile loading and Criteria digest validation, `run()` invokes `AIProviderConfigStore().load()` once. Only `VALID` with a non-`None` configuration proceeds; I/O and unusable-configuration paths return before storage, OCR, listener, browser, or Candidate execution.

The loaded `run_ai_provider_config` is retained and supplied unchanged to R11 processing. There is no per-Candidate reload, Provider/model fallback, or new verification gate.

## 11. Complete Scan / OCR Readiness Verification

`view_candidate()` unconditionally calls `ocr_detector.scan_candidate(first_observation=...)`, retains dwell/stop behavior, and does not call Legacy keyword detection for Am7 production action authority. `run()` calls `initialize_ocr()` for every Am7 Run.

After first-detail setup and existing runtime calibration work, `ensure_ocr_region_calibrated()` is unconditional with respect to Legacy configuration and action mode, and is before `start_run_timer()`. A false readiness result returns before formal Candidate scan. `ocr_detector.py` remains outside the implementation diff.

## 12. Candidate Finalization / R11 / R12 Integration Verification

Both normal main-loop finalization call sites retain `candidate_document`. The narrow eligibility check accepts only `CaptureStatus.COMPLETED` and `CaptureStatus.COMPLETED_WITH_LIMIT`; only then does `_process_finalized_candidate()` receive the exact finalized object plus the loaded Profile, Config, and Run-bound RuleSet.

The helper performs R11, R12, minimum identity/status logging, qualified-only dispatch, and returns the produced Decision. Non-last processing preserves `prepare_candidate_switch_context()` before finalization; last-Candidate processing occurs before existing batch convergence. Cleanup finalization and stopped/ineligible paths do not invoke R11/R12.

## 13. Legacy Authority Removal Verification

The prior Legacy `keyword_hit` action branch was removed from `view_candidate()`. `forward_enabled`, `forward_keywords`, `keyword_hit`, and Legacy detection no longer gate Complete Scan, finalization, R11, R06, Decision, or qualified action authorization.

Legacy input remains only existing configuration/reference state. Backup email prompting and forward calibration use forward action mode rather than Legacy-rule presence. Therefore changing Legacy match data cannot alter a Decision for the same finalized Candidate, R11 result, and RuleSet.

## 14. Action Authorization Verification

Only `decision.decision_status == "qualified"` enters the existing action-mode dispatch. A qualified favorite calls the existing `perform_favorite_action()`; a qualified forward calls existing `forward_one_candidate()` unless `no_forward_mode` suppresses the real call.

The Decision is constructed before dispatch. Existing action return values, suppression, and exceptions have no branch that mutates or replaces the immutable Decision. `rejected` and `ai_failed` enter neither action call and reset `forward_consecutive` to zero.

## 15. Candidate Continuation Verification

The processing helper returns to the existing surrounding loop for all normal Decision statuses. There is no status-specific `next_candidate()` path. Existing `confirm_candidate_switch()` remains the non-last switch owner, while existing batch refresh, pause, stop, and last-Candidate behavior remain in their established locations.

## 16. Protected Function Review

Targeted diff hunk review found R12 changes only in imports, Rule input, Legacy-independent scan invocation, narrow integration helpers/call positions, Run setup, and startup Run binding. No body hunk changed any protected/reuse-only symbol:

- `perform_favorite_action()`
- `forward_one_candidate()`
- `next_candidate()`
- focus restore, WindMouse, mouse-motion, and calibration helpers
- `prepare_candidate_switch_context()` and `confirm_candidate_switch()`
- Candidate-switch evaluator/helpers
- `finalize_current_candidate_recording()` and `finalize_active_candidate_for_stop()`
- `ensure_ocr_region_calibrated()`
- `OCRKeywordDetector.scan_candidate()` or the OCR scan lifecycle

The authorized call conditions/positions changed; protected mechanics did not. No AST scanner, checksum system, or source-guard framework was created.

## 17. Consolidated Targeted Verification

| Verification | Actual result |
|---|---|
| `./venv/Scripts/python.exe -m unittest tests.test_candidate_decision tests.test_candidate_decision_integration tests.test_simple_brush_ocr -v` | Passed: 290 tests run, 290 passed, 0 failures, 0 errors. Final output: `Ran 290 tests in 3.808s` and `OK`. |
| `./venv/Scripts/python.exe -m compileall candidate_decision.py simple_brush.py tests/test_candidate_decision.py tests/test_candidate_decision_integration.py tests/test_simple_brush_ocr.py` | Passed: exit code 0; no compile error. |
| `git diff --check` | Passed: exit code 0; no whitespace/diff error. LF/CRLF informational warnings were emitted for the two tracked modified files. |
| `git status --short`, `git diff --name-status`, direct new-file existence check | Passed: the expected R12 implementation/test/Frozen-document files were present; no unexpected implementation/test scope was found. |

The focused suite uses mocks for R12 Candidate/Provider/Rule/action integration. It did not perform a live BOSS browser session, AI API request, favorite, forwarding, or mouse operation.

## 18. R01–R43 Technical Responsibility Matrix

| Responsibility ID | Expected behavior | Evidence | Result |
|---|---|---|---|
| R01 | Completed R11 plus R06 true returns `qualified`. | `CandidateDecisionTests.test_completed_true_returns_qualified_with_exact_rule_inputs`; targeted suite passed. | Pass |
| R02 | Completed R11 plus R06 false returns `rejected`. | `test_completed_false_returns_rejected_for_all_false_results`; targeted suite passed. | Pass |
| R03 | Failed R11 returns `ai_failed`. | `test_failed_returns_ai_failed_without_evaluating_rules`; targeted suite passed. | Pass |
| R04 | Failed R11 makes zero R06 calls. | `test_failed_returns_ai_failed_without_evaluating_rules`; evaluator mock not called. | Pass |
| R05 | Exact Criteria mapping reaches R06 unchanged. | `test_completed_true_returns_qualified_with_exact_rule_inputs` uses `assertIs`. | Pass |
| R06 | Exact Run-bound RuleSet reaches R06 unchanged. | Same focused test uses `assertIs` for RuleSet. | Pass |
| R07 | Candidate identity is copied exactly. | Pure Decision equality assertions and direct `decide_candidate()` source review. | Pass |
| R08 | Decision has exactly two dataclass fields. | `test_candidate_decision_has_exact_frozen_shape_and_validation`. | Pass |
| R09 | Decision is frozen. | Same test asserts `FrozenInstanceError` on assignment. | Pass |
| R10 | Only the exact three statuses construct. | Same test covers all three and rejects another status. | Pass |
| R11 | `ScreeningRuleValidationError` propagates without Decision. | `test_rule_engine_errors_propagate`. | Pass |
| R12 | `ScreeningRuleInputError` propagates without Decision. | `test_rule_engine_errors_propagate`. | Pass |
| R13 | Completed all-false mapping still reaches R06. | `test_completed_false_returns_rejected_for_all_false_results`. | Pass |
| R14 | R06 false is rejected, never AI failure. | Same all-false Decision test. | Pass |
| R15 | Top-level/type/value boundaries follow Section 10. | `test_decide_candidate_validates_input_types_before_failed_short_circuit` and Decision validation test. | Pass |
| R16 | One retained normal finalized Candidate reaches R11 once. | Retained-document call sites/source review; `test_completed_candidate_reaches_r11_once_and_r06_once`. | Pass |
| R17 | Completed R11 reaches R06 at most once. | Same integration test asserts one evaluator call. | Pass |
| R18 | AI failure gives ai_failed and zero R06. | `test_ai_failure_skips_r06_and_all_actions_and_resets_global`. | Pass |
| R19 | Qualified favorite calls existing favorite once. | `test_completed_candidate_reaches_r11_once_and_r06_once`; favorite mock called once. | Pass |
| R20 | Qualified forward calls existing forward under existing controls. | `test_qualified_forward_and_suppression_do_not_reclassify_decision`. | Pass |
| R21 | Qualified no-forward suppresses real forward and remains qualified. | Same forward/suppression test. | Pass |
| R22 | Rejected calls neither action and resets counter. | `test_rejected_has_zero_actions_and_resets_global`. | Pass |
| R23 | AI-failed calls neither action and resets counter. | `test_ai_failure_skips_r06_and_all_actions_and_resets_global`. | Pass |
| R24 | Action outcomes do not reclassify a Decision. | Forward false-return/suppression test plus source review: Decision precedes dispatch and no mutation/catch branch exists. | Pass |
| R25 | Legacy hit alone cannot invoke Am7 action. | `view_candidate()` source review removes Legacy action branch; focused suite passed. | Pass |
| R26 | Legacy match output cannot change R12 Decision. | Decision helper accepts only R11 result and RuleSet; no Legacy input path. | Pass |
| R27 | No Legacy rules still gets readiness then formal scan; readiness false scans zero. | Unconditional OCR setup/readiness source review and directly affected `tests.test_simple_brush_ocr` pass. | Pass |
| R28 | R11 receives exact retained normal finalization object after finalization. | Normal call-site source review and integration R11 identity assertion. | Pass |
| R29 | Aborted Candidate has zero formal R11/R12 processing. | Eligibility predicate/source review; targeted cleanup/stop regression passed. | Pass |
| R30 | Interrupted Candidate has zero formal R11/R12 processing. | Eligibility predicate/source review; targeted cleanup/stop regression passed. | Pass |
| R31 | Load-recovery cleanup has zero formal processing and no duplicate later call. | Eligibility predicate/call-site source review; existing focused switch/recovery tests passed. | Pass |
| R32 | Existing noninteractive path requires Profile and Rule without new triggers; valid setup builds once. | `test_formal_flags_do_not_change_startup_mode_and_noninteractive_requires_both_inputs` and `test_valid_noninteractive_startup_builds_one_bound_rule_set`. | Pass |
| R33 | Multiple Candidates reuse identical RuleSet object. | `test_multiple_candidates_reuse_the_exact_bound_rule_set` uses `assertIs`. | Pass |
| R34 | Candidate processing does not reconstruct RuleSet. | Required `run_bound_rule_set` source review and R33 identity test. | Pass |
| R35 | One CLI or prompted Rule is representable without changing startup mode. | Prompt, CLI raw-expression, and startup-mode focused tests. | Pass |
| R36 | Multiple Rules retain order and duplicates. | `test_repeatable_cli_rules_preserve_order_duplicates_and_raw_expression`. | Pass |
| R37 | AND/OR/parentheses reach `ScreeningRule` unchanged; R06 evaluates. | Same raw-expression test and public evaluator source review. | Pass |
| R38 | All normal statuses converge to common continuation. | Helper-return/main-loop source review; no status-specific continuation branch. | Pass |
| R39 | Existing switch confirmation/next-Candidate owns switching. | Protected-body/diff review; `confirm_candidate_switch()` remains at the existing loop seam. | Pass |
| R40 | Unexpected R11 exception reaches outer failure boundary, not ai_failed. | `test_rule_and_runtime_errors_propagate_without_actions`. | Pass |
| R41 | R06 exception produces zero action. | Same integration test; Decision exception precedes action dispatch. | Pass |
| R42 | No R13 retry/fallback/degradation behavior is invoked. | Targeted source/diff scope review; no such code added. | Pass |
| R43 | No R14 persistence/replay/cache behavior is invoked. | Targeted source/diff scope review; no such code added. | Pass |

Result: **43 / 43 Pass**.

## 19. AC-01–AC-24 Product Acceptance Matrix

| AC ID | Frozen requirement summary | Implementation symbol/file | Verification evidence | Result |
|---|---|---|---|---|
| AC-01 | Finalized Candidate document precedes R11/R12; no Screen produces a production Decision. | `simple_brush.run()` finalization call sites | R16, R28–R31 evidence; retained-document eligibility review. | Pass |
| AC-02 | Completed plus R06 true produces exact qualified Decision. | `candidate_decision.decide_candidate()` | R01, R05–R07 focused tests. | Pass |
| AC-03 | Completed plus R06 false produces exact rejected Decision. | `candidate_decision.decide_candidate()` | R02, R14 focused tests. | Pass |
| AC-04 | Failed R11 produces exact ai_failed Decision. | `candidate_decision.decide_candidate()` | R03 and R07 focused tests. | Pass |
| AC-05 | Failed R11 makes no Rule evaluation or synthetic mapping. | Failed branch before evaluator | R04 and R18 evaluator mocks. | Pass |
| AC-06 | Normal status domain is exactly qualified/rejected/ai_failed. | `CandidateDecision.__post_init__()` | R10 and R15 validation tests. | Pass |
| AC-07 | Decision is frozen and has exactly two required fields. | `CandidateDecision` | R08/R09 dataclass and immutability inspection. | Pass |
| AC-08 | Decision copies exact R11 Candidate identity without transformation. | `decide_candidate()` | R07 equality/source review. | Pass |
| AC-09 | Completed result passes exact mapping and exact Run RuleSet to R06. | Public evaluator call in `decide_candidate()` | R05, R06, R13, R33, R37 identity/expression evidence. | Pass |
| AC-10 | R06 validation/input failure makes no normal Decision or action. | No R06 catch; helper action follows Decision | R11, R12, R41 exception tests. | Pass |
| AC-11 | Only qualified authorizes existing action path. | `_process_finalized_candidate()` | R19–R23 action-call matrix and source review. | Pass |
| AC-12 | Qualified favorite reuses unchanged favorite path. | Existing `perform_favorite_action()` call site | R19 mock call and protected-body review. | Pass |
| AC-13 | Qualified forward reuses unchanged forward path; no-forward suppresses real forwarding without changing Decision. | Existing `forward_one_candidate()` call site | R20/R21 forward/suppression matrix and body review. | Pass |
| AC-14 | Rejected performs zero action and continues normally. | Nonqualified helper branch | R22 and R38 evidence. | Pass |
| AC-15 | AI-failed performs zero action and continues normally. | Failed Decision/helper branch | R18, R23, R38 evidence. | Pass |
| AC-16 | Action result, suppression, or failure cannot rewrite qualified or add action_failed. | Decision before dispatch | R21/R24 evidence and immutable Decision/source review. | Pass |
| AC-17 | All normal statuses return to common Candidate/batch continuation. | Surrounding `run()` loop | R38 source/control-flow review. | Pass |
| AC-18 | `next_candidate()` and existing switch ownership remain unchanged. | `confirm_candidate_switch()` / `next_candidate()` | R39 protected-body/diff review. | Pass |
| AC-19 | Legacy results have no Am7 Decision/action authority. | `view_candidate()` / Run setup | R25–R27 Legacy-independent source and regression evidence. | Pass |
| AC-20 | Action/mouse/focus/calibration mechanics remain protected. | Reused protected functions | R19–R21/R27 plus protected-body diff review. | Pass |
| AC-21 | One explicit immutable RuleSet is bound and reused for each live Run. | `main()`, `run(..., run_bound_rule_set=...)` | R32–R36 binding/construction/identity evidence. | Pass |
| AC-22 | No inferred or weakened Rule contract. | `_build_screening_rule_set()` | R35–R37 raw expressions, no Profile/Legacy inference source review. | Pass |
| AC-23 | AI failure has minimum visibility only; no R13 persistence/retry/fallback/degradation. | Decision logging and outer error boundary | R18, R40, R42; targeted scope review. | Pass |
| AC-24 | No R14 replay/cache/hash/migration/framework work. | Exact local implementation scope | R43 and changed-file/source review. | Pass |

Result: **24 / 24 Pass**.

## 20. R13 / R14 Scope Review

R12 added none of the R13 capabilities: AI result/failure persistence, CandidateDecision/action/Rule persistence, retry, queue, fallback, degradation, recovery, repeated-failure policy, or failure-stop counter.

R12 added none of the R14 capabilities: replay, AI/Decision replay, cache, replay lookup, RuleSet/Decision digest, request hash, migration, packaging integration, or release integration. It also added no generic Decision, Action, Gate, Guard, Scanner, Wrapper, Sanitizer, Dispatcher, Pipeline, or orchestration framework.

## 21. Packaging / Live Smoke

Packaging / Live Smoke: **Not Required by Frozen AM7-R12 TID**.

No PyInstaller/package build, live BOSS browser run, live AI API request, real favorite/forward, real mouse automation, model benchmark, or dependency audit was performed.

## 22. Deviations

None.

## 23. Open Issues

None.

## 24. Contract Conflicts

None.

## 25. Final Scope Review

The implementation/test changes are limited to the TID-authorized R12 files. The only acceptance-task write is this report. Frozen RPD/TID, implementation, and tests were not modified during acceptance. `git diff --check` completed without an actual whitespace error; LF/CRLF and inaccessible global Git-ignore warnings were informational environment output, not product or acceptance failures.

No Git write operation was performed.

## 26. Final Acceptance Summary

- Targeted unittest: 290 / 290 passed; 0 failures; 0 errors.
- Compile verification: Passed.
- `git diff --check`: Passed.
- Technical responsibilities: 43 / 43 Pass.
- Product acceptance criteria: 24 / 24 Pass.
- Authorized file scope: Passed.
- Protected function bodies: Unchanged.
- Deviations: None.
- Open Issues: None.
- Contract Conflicts: None.

AM7-R12 Implementation: **Completed**  
AM7-R12 Automated Acceptance: **Passed**  
AM7-R12 Human Final Review: **Pending**

## 27. Human Final Review Status

Automated Acceptance Passed / Pending Human Final Review.

This report does not declare Human acceptance, merge, release, or any Git state transition.
