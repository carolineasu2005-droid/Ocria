# Ocria Am7 — AM7-R13 AI Persistence & Runtime Failure Degradation

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R13
- Document Type: Formal Acceptance Report — Final Re-run
- Requirement Branch: am7-r13-ai-persistence-failure-degradation
- Baseline HEAD: 4ba8fe402ce5c27831d6813373bc637dd594cf36
- RPD: v0.1 Frozen
- TID: v0.1 Frozen

## 2. Acceptance Status

- Implementation: Completed
- Automated Acceptance: Passed
- Human Final Review: Pending

This final re-run records the current acceptance result after Windows sandbox ACL/setup recovery.

## 3. Frozen Source Documents

- CODEX-CONSTITUTION.md
- docs/RPD-AM7-R13-ai-persistence-failure-degradation.md — v0.1 Frozen
- docs/TID-AM7-R13-ai-persistence-failure-degradation.md — v0.1 Frozen

## 4. Requirement Summary

AM7-R13 adds bounded Candidate-level AI attempts and Run-scoped write-only trace records. Failed attempts persist before retry; one final AI outcome persists before R12 Decision production; each produced Decision persists before qualified-only action. Technical AI failure remains Candidate-recoverable when persistence succeeds, while required persistence failure is Run-fatal through existing cleanup.

## 5. Branch / Baseline

- Branch: am7-r13-ai-persistence-failure-degradation
- HEAD: 4ba8fe402ce5c27831d6813373bc637dd594cf36

Branch and HEAD match the Frozen documents. R13 implementation remains uncommitted for Human review.

## 6. Final Changed-File Scope

- New: ai_screening_persistence.py
- New: tests/test_ai_screening_persistence.py
- Modified: ai_screening_runtime.py
- Modified: simple_brush.py
- Modified: tests/test_ai_screening_runtime.py
- Modified: tests/test_candidate_decision_integration.py
- Modified: tests/test_simple_brush_ocr.py

This Acceptance task modifies only this report. Frozen documents, runtime code, and tests were not modified during acceptance.

## 7. Final Functionality

Change 1 provides the private R11 diagnostic seam with unchanged public API. Change 2 provides frozen records, exact JSONL streams, synchronous writer, and integrity exception. Change 3 creates one Store per Run and enforces error-before-retry, final-outcome-before-Decision, and Decision-before-action.

## 8. R11 Compatibility

run_ai_screening(candidate, profile, config) remains the exact three-argument public API. AIScreeningResult remains exactly candidate_record_id, ai_status, and criteria_results. No public diagnostic, callback, or Store was added. Completed all-false mappings remain completed; accepted technical failure remains failed with null criteria_results.

## 9. Diagnostic Seam

_AIScreeningAttemptFailure, _AIScreeningAttemptOutcome, _run_ai_screening_attempt, and the exact 512-character diagnostic bound are present. The seam maps only R09 ValueError, LLMRuntimeError, and AIScreeningContractError. Unexpected defects propagate.

## 10. Retry

R13_MAX_AI_SCREENING_ATTEMPTS is exactly 3. The loop reuses exact Candidate/Profile/Config objects, stops immediately on completion, has no Attempt 4 and no active retry delay, and observes only existing stop/pause state. R03 remains max_retries=0. No Provider/model fallback exists.

## 11. Persistence Schemas

The exact independent streams are ai_errors.jsonl, ai_results.jsonl, and decisions.jsonl in the existing OCR Run directory. Frozen AIAttemptErrorRecord, AIFinalOutcomeRecord, and CandidateDecisionRecord validate exact domains. The writer uses compact UTF-8 JSON lines, newline, flush, and context close; it has no fsync, retry, best-effort Boolean result, or read API.

## 12. Ordering

failed attempt → append_ai_error → permitted retry

final selected result → append_ai_result → decide_candidate / R06

produced Decision → append_decision → qualified-only existing action

Ordered mock-sequence tests passed.

## 13. Persistence Failure

Attempt-error, final-outcome, and Decision-write failures block downstream work. Store setup failure logs only its safe operation, closes the OCR Run as RunStatus.ERROR, and returns 2 before execution startup. Runtime required-write failure escapes to the existing outer error boundary, produces RunStatus.ERROR, and stops later Candidate processing.

## 14. Continuation

Fully persisted qualified, rejected, and ai_failed Candidates retain existing continuation. Three technical failures create one ai_failed Decision with zero R06/action. No counter, threshold, circuit breaker, cooldown, or Run stop was added.

## 15. Protected Behavior

Direct zero-context simple_brush diff review found changes only to imports, the R13 helper, pre-action ordering, Run-local Store setup, and two finalized-Candidate call sites. perform_favorite_action, forward_one_candidate, next_candidate, Candidate switching/finalization, OCR lifecycle, focus, calibration, mouse/WindMouse, and ocr_store.py are unchanged.

## 16. R14

The Store is write-only. No readback, historical lookup, replay, cache, hash, deduplication, migration, packaging, or release behavior was added.

## 17. Consolidated Verification

| Command | Actual result |
|---|---|
| ./venv/Scripts/python.exe -m unittest tests.test_ai_screening_runtime tests.test_ai_screening_persistence tests.test_candidate_decision tests.test_candidate_decision_integration tests.test_simple_brush_ocr -v | Passed: 322 tests; 322 passed; 0 failures; 0 errors. |
| ./venv/Scripts/python.exe -m compileall ai_screening_runtime.py ai_screening_persistence.py simple_brush.py tests/test_ai_screening_runtime.py tests/test_ai_screening_persistence.py tests/test_candidate_decision_integration.py tests/test_simple_brush_ocr.py | Passed: zero compile errors. |
| git diff --check | Passed: no whitespace errors; CRLF messages were warnings only. |
| git status --short and git diff --name-status | Expected R13 scope; no unexpected implementation/test file. |

## 18. R01–R38 Technical Responsibility Matrix

| ID | Expected behavior | Implementation / verification evidence | Result |
|---|---|---|---|
| R01 | Public R11 compatibility | Public signature and result-shape test | Pass |
| R02 | Public result semantics | Runtime projection tests | Pass |
| R03 | R09 diagnostic mapping | R09 seam test | Pass |
| R04 | LLM diagnostic mapping | LLM seam test | Pass |
| R05 | R10 diagnostic mapping | Contract seam test | Pass |
| R06 | Unexpected propagation | Unexpected seam test | Pass |
| R07 | Maximum 3 attempts | Three-failure call count | Pass |
| R08 | Immediate success stop | First-completed ordering | Pass |
| R09 | Failed then completed | Failed-then-completed ordering | Pass |
| R10 | Two failures then completed | Two-failures ordering | Pass |
| R11 | Third failure selection | Three-failure final record | Pass |
| R12 | Object identity reuse | assertIs retry arguments | Pass |
| R13 | Stop/pause gates | Stop/pause test | Pass |
| R14 | Attempt-error schema | Persistence schema test | Pass |
| R15 | Completed final outcome | Final outcome tests | Pass |
| R16 | Failed final outcome | Three-failure test | Pass |
| R17 | Decision schema | Decision schema test | Pass |
| R18 | Three write-only streams | Store initialization test | Pass |
| R19 | Synchronous append | Append acknowledgement test | Pass |
| R20 | Integrity error | Writer OSError test | Pass |
| R21 | Error before retry | Ordered retry test | Pass |
| R22 | Error-write fatality | Error-write-failure test | Pass |
| R23 | Outcome before R06 | Outcome/Decision ordering tests | Pass |
| R24 | Final-write fatality | Final-write table test | Pass |
| R25 | Decision before action | Qualified ordering test | Pass |
| R26 | Decision-write fatality | Decision-write-failure test | Pass |
| R27 | R06 failure ordering | R06-failure test | Pass |
| R28 | Three-failure flow | Three-failure integration | Pass |
| R29 | R12 actions preserved | Retry-success/action tests | Pass |
| R30 | Record cardinality | A-D scenario counts | Pass |
| R31 | Identity/trace | Identity/trace assertions | Pass |
| R32 | Setup failure | Setup-failure Run test | Pass |
| R33 | Runtime failure | Runtime-error Run test | Pass |
| R34 | No failure counter | Repeated-ai-failed test | Pass |
| R35 | No action persistence | Action-result test | Pass |
| R36 | Protected bodies | Direct diff review | Pass |
| R37 | No R14 behavior | Write-only Store/source review | Pass |
| R38 | No generic framework | Changed-file review | Pass |

Result: **38 / 38 Pass**.

## 19. AC-01–AC-32 Product Acceptance Matrix

| AC | Frozen requirement | Concrete evidence | Result |
|---|---|---|---|
| AC-01 | Business false remains distinct | All-false completed; failed null | Pass |
| AC-02 | Accepted failure domain only | Three seam mappings; unexpected propagation | Pass |
| AC-03 | At most three attempts | Exact range; no fourth | Pass |
| AC-04 | Completed stops immediately | First-completed sequence | Pass |
| AC-05 | Third failed result selected | Third failed/null/3 final record | Pass |
| AC-06 | Same Config/Provider/model | assertIs arguments and final config trace | Pass |
| AC-07 | Error before retry | Ordered retry-success tests | Pass |
| AC-08 | Bounded safe error evidence | 12 fields; 512-character bound | Pass |
| AC-09 | Error-write failure fatal | Blocks retry/outcome/Decision/action | Pass |
| AC-10 | One final outcome | A-D call counts | Pass |
| AC-11 | Completed mapping fidelity | Strict Boolean mapping copied | Pass |
| AC-12 | Failed null/attempt fidelity | Failed/null/attempts=3 | Pass |
| AC-13 | Trace linkage | Store/Candidate/Profile/config sources | Pass |
| AC-14 | Earlier errors retained | Earlier error appends remain | Pass |
| AC-15 | Outcome before Decision/action | Final append before decide_candidate | Pass |
| AC-16 | R12 mapping unchanged | Completed R12 and failed ai_failed/zero R06 | Pass |
| AC-17 | One Decision record | One append per Decision | Pass |
| AC-18 | Decision before action | Qualified ordering test | Pass |
| AC-19 | Three failures ai_failed/zero action | Three-failure integration | Pass |
| AC-20 | Candidate continuation | Persisted ai_failed returns normally | Pass |
| AC-21 | No failure counter | Repeated test; no counter in source | Pass |
| AC-22 | Final-write failure fatal | Final-write table plus Run error | Pass |
| AC-23 | Decision-write failure fatal | Decision-write failure plus outer error | Pass |
| AC-24 | Safe Run termination | Setup/runtime ERROR; no later Candidate | Pass |
| AC-25 | Exact identities | Candidate/store identity checks | Pass |
| AC-26 | No second Profile authority | Only ID/version/digest retained | Pass |
| AC-27 | OCR authority unchanged | Separate streams; OCR diff clean | Pass |
| AC-28 | Exact cardinality | A-D integration scenarios | Pass |
| AC-29 | No action-result persistence | No action stream/API | Pass |
| AC-30 | Protected mechanics | Pre-action ordering only | Pass |
| AC-31 | No R14 | No readback/replay/cache/hash/migration | Pass |
| AC-32 | No generic framework | Narrow helper/store; no dependency | Pass |

Result: **32 / 32 Pass**.

## 20. Packaging / Live Smoke

Packaging / Live Smoke: Not Required by Frozen AM7-R13 TID.

No live AI, browser, favorite, forward, mouse, PyInstaller, benchmark, packaging, or network smoke was run.

## 21. Deviations

None.

## 22. Open Issues

None.

## 23. Contract Conflicts

None.

## 24. Final Scope Review

The implementation/test changes match the Frozen three-change plan. No protected runtime/test file outside the expected seven-file implementation/test scope is changed. Frozen documents are unmodified. This report is the sole Acceptance-task write.

## 25. Final Acceptance Summary

- Consolidated targeted unittest: 322 / 322 passed; 0 failures; 0 errors.
- Required compileall: passed with zero compile errors.
- git diff --check: passed.
- R01–R38: 38 / 38 Pass.
- AC-01–AC-32: 32 / 32 Pass.
- Protected bodies: unchanged.
- R14 behavior: absent.

AM7-R13 Implementation: **Completed**  
AM7-R13 Automated Acceptance: **Passed**  
AM7-R13 Human Final Review: **Pending**

## 26. Human Final Review Status

Automated Acceptance Passed / Pending Human Final Review.

This report does not declare Human acceptance, merge, or release.
