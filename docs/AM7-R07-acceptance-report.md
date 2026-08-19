# AM7-R07 Acceptance Report

## 1. Metadata

| Field | Value |
|---|---|
| Product | Ocria |
| Generation | Am7 |
| Requirement | AM7-R07 — Candidate Complete Scan |
| Document Type | Acceptance Report |
| Source RPD | `RPD-AM7-R07-candidate-complete-scan.md` v0.1 Frozen |
| Source TID | `TID-AM7-R07-candidate-complete-scan.md` v0.1 Frozen |
| Requirement Branch | `am7-r07-candidate-complete-scan` |
| Frozen baseline | `46fbaae7356fbf17266fd07e53ab11af683cb936` |
| Prepared date | 2026-08-19 |
| Acceptance Status | Automated Acceptance Passed / Pending Human Final Review |

## 2. Acceptance Review Scope

This acceptance review covers only the Frozen AM7-R07 implementation, its two directly related test modules, and the targeted execution evidence produced in this same Terra conversation.

- No repository-wide audit was performed.
- No unrelated regression suite was run.
- Previously successful targeted commands were not rerun merely to duplicate evidence.
- No new acceptance framework or acceptance harness was added.

## 3. Final Implemented Functionality

- Preserved Legacy `OCRKeywordDetector.detect(rules, first_observation=None)`.
- Preserved empty-rule zero-scan behavior, Legacy matching, independent confirmation, and confirmed-match early-stop.
- Added `OCRKeywordDetector.scan_candidate(first_observation=None) -> DetectionResult`; it accepts no rules parameter.
- Added the local private `_run_scan_lifecycle(...)` factorization selected by Frozen TID Option A.
- `scan_candidate(...)` shallowly neutralizes a supplied first observation's `matched_keyword`, `matched_rule`, and `rule_comparison` while reusing its evidence without OCR recapture.
- Complete Scan enters the shared lifecycle with `legacy_rules=None`; formal matching and rule confirmation are gated on a non-null private Legacy tuple.
- Position-confirmation recovery receives the same private tuple and skips matching and rule confirmation for Complete Scan.
- The existing Dynamic End lifecycle, safety budget, counters, `DetectionResult`, failure fields, and reason fields are reused.
- Existing Candidate evidence callback, builder, and document construction paths are reused.

## 4. Legacy Compatibility Review

- The exact Legacy public `detect(rules, first_observation=None)` entry remains available.
- It materializes the supplied iterable once and retains the immediate empty-rule return with no capture, matcher, scroll, wait, callback, or state-reset effects.
- Legacy matcher and R04 comparison semantics remain in `_match_observation(...)` unchanged.
- Legacy independent confirmation, confirmation wait, and confirmation result semantics remain unchanged.
- A confirmed Legacy rule still may early-stop the Legacy lifecycle, with existing safe/full priority retained before confirmation.
- Existing Legacy runtime and action orchestration were untouched; no caller was redirected to Complete Scan.

## 5. Complete-Scan Rule-Independence Review

Complete Scan:

- accepts no Legacy rules;
- does not invoke `_match_observation(...)`, `matching_keyword_rule(...)`, `_observe(...)` confirmation work, `_consume_rule_confirmation(...)`, or `_rule_confirmation_result(...)`;
- does not spend a rule-confirmation observation or confirmation wait;
- does not emit `capture_type="rule_confirmation"`;
- cannot end because a Legacy keyword/rule would match;
- keeps `confirmed_match=False` and `matched_keyword=None`; and
- has deterministic lifecycle behavior even when Legacy matcher and confirmation outcomes are patched to differ.

The same rule-neutral gate applies to the position-confirmation recovery capture.

## 6. Legacy OCR R07 Dynamic End Ownership Review

Legacy OCR R07 Dynamic End remains the sole normal-completion authority. The shared lifecycle retains the existing Dynamic End state updates, callback consumption, safe/full control, recovery eligibility, and result projection.

No alternate bottom detector, completion detector, Dynamic End algorithm, threshold, reason value, or state meaning was added or changed.

## 7. Safety / Technical Termination Review

The existing `DetectionResult` reason fields retain their meanings:

| Outcome category | Existing representation |
|---|---|
| Normal Dynamic End completion | `dynamic_end_reason="scroll_bottom"` or `"no_new_text"` |
| Safety termination | `dynamic_end_reason="max_screen_limit"` |
| Non-normal interruption | existing `interrupt_reason` |
| Controlled technical termination | existing `abort_reason` |
| Detector error | `success=False` with existing `error` |

`max_screen_limit` remains distinct from normal Dynamic End completion. No enum, status model, Candidate schema field, or persistence contract was introduced.

## 8. Retry / Focus / Candidate Switch Review

AM7-R07 preserves, rather than rewrites:

- the existing detail-load retry contract;
- detector recovery eligibility and bounded recovery behavior;
- focus restoration and its failure outcome;
- bounded scroll retry and settle wait;
- existing interrupt checks; and
- Candidate Switch Verification, including `candidate_switch_failed` behavior.

Candidate Switch Verification remains in protected `simple_brush.py`; it was neither bypassed nor reimplemented.

## 9. Candidate Evidence Boundary Review

Complete Scan reuses the existing evidence path:

```text
OcrScreenRecord → CandidateOcrBuilder → CandidateOcrDocument
```

- Candidate schema changes: None.
- Persistence changes: None.
- Profile, Rule, Boolean, Decision, or Action fields added: None.
- Complete Scan returns `DetectionResult`; it does not itself finalize a Candidate document or take an action.

## 10. Final File Scope

Implementation changes are limited to:

- `ocr_detector.py`
- `tests/test_ocr_detector.py`
- `tests/test_ocr_stage0_integration.py`

Acceptance artifact:

- `docs/AM7-R07-acceptance-report.md`

The current implementation diff contains only the three authorized implementation/test files. This acceptance artifact is the only new acceptance-step file. Protected files remained untouched, including `simple_brush.py`, `ocr_candidate.py`, `ocr_records.py`, `ocr_store.py`, `ocr_text.py`, OCR normalization/aggregation/similarity modules, R05, R06, LLM Runtime, action/mouse/browser code, dependencies, and packaging.

## 11. Verification Evidence

The following commands were executed successfully during the same implementation conversation. They were not redundantly rerun for this acceptance review.

| Verification | Result |
|---|---|
| `tests.test_ocr_detector` | 120 passed |
| `tests.test_ocr_stage0_integration` | 33 passed |
| `tests.test_ocr_candidate` | 21 passed |
| `tests.test_ocr_text` | 37 passed |
| Selected Simple Brush retry/focus/switch methods | 4 passed |
| Targeted `compileall` | passed |

## 12. AC-01–AC-24 Acceptance Mapping

| AC | Implemented behavior/component | Verification evidence | Result |
|---|---|---|---|
| AC-01 | Preserved exact `detect(rules, first_observation=None)` entry. | Empty-rule test and 120-pass detector suite. | Pass |
| AC-02 | Non-empty Legacy rules retain independent confirmation and early return. | Existing Legacy confirmation, later-match, priority, and detector regression tests. | Pass |
| AC-03 | Added separate `scan_candidate(first_observation=None)` rather than redirecting `detect([])`. | Separate public-entry and empty-rule tests. | Pass |
| AC-04 | Complete Scan supplies no rules and gates private rule branches on `legacy_rules is not None`. | Matcher/confirmation fail-if-called test. | Pass |
| AC-05 | Early matching-looking text remains evidence and later screens are collected. | Complete-Scan detector and Stage-0 Candidate-document tests. | Pass |
| AC-06 | Reused existing `_safe_full_control_result(...)` and Dynamic End lifecycle. | Complete-Scan Dynamic End tests and detector/Stage-0 suites. | Pass |
| AC-07 | Added no alternate completion algorithm or threshold. | Targeted code/diff and protected-boundary inspection. | Pass |
| AC-08 | Retained existing `max_scans`, formal-slot counting, and `max_screen_limit`. | Complete-Scan safety-limit and existing formal-slot tests. | Pass |
| AC-09 | Preserved interruption, controlled abort, error, and budget exits. | Complete-Scan failure-projection and existing safe/full tests. | Pass |
| AC-10 | Preserved explicit normal, safety, interruption, abort, and error reason distinctions. | Detector and Stage-0 reason-projection tests. | Pass |
| AC-11 | Preserved detail-load and detector retry behavior. | Selected Simple Brush retry test and Stage-0 recovery coverage. | Pass |
| AC-12 | Preserved focus-recovery trigger, one-recovery bound, order, and failure behavior. | Complete-Scan recovery test and existing focus tests. | Pass |
| AC-13 | Left Candidate Switch Verification and `candidate_switch_failed` behavior untouched. | Selected switch tests and protected-file scope inspection. | Pass |
| AC-14 | Did not change Legacy OCR R02–R07 algorithms or thresholds. | Detector, Stage-0, Candidate, keyword suites and file-scope inspection. | Pass |
| AC-15 | Reused callback, `OcrScreenRecord`, `CandidateOcrBuilder`, and `CandidateOcrDocument`. | Complete-Scan Stage-0 document test and Candidate suite. | Pass |
| AC-16 | Added no Candidate/Profile/Rule/Decision/Action schema fields. | Candidate suite and protected-schema scope inspection. | Pass |
| AC-17 | Left Legacy keyword grammar, matcher, R04 relationship, and confirmation meaning unchanged. | 37-pass keyword suite and Legacy detector suite. | Pass |
| AC-18 | Did not modify AM7-R05 contracts or implementation. | Final protected-file scope inspection. | Pass |
| AC-19 | Did not modify or invoke AM7-R06 Rule Engine V2. | Final protected-file/import scope inspection. | Pass |
| AC-20 | Complete Scan exposes evidence via `DetectionResult`, not a Candidate Decision. | Public API tests and detector source inspection. | Pass |
| AC-21 | Added no LLM, prompt, AI Runtime, Criterion Evaluation, or Boolean mapping. | Changed-file and protected-boundary inspection. | Pass |
| AC-22 | Added no Decision or favorite/forward/reject/skip action integration. | Detector source inspection and untouched `simple_brush.py`. | Pass |
| AC-23 | Added no persistence redesign, status taxonomy, Run binding, or generic framework. | Final file scope and Candidate suite. | Pass |
| AC-24 | Complete Scan is deterministic and independent of changed Legacy rule/match/confirmation outcomes. | Dedicated rule-independence test. | Pass |

## 13. Boundary / Non-Implementation Review

The acceptance review confirms no implementation of:

- a new OCR algorithm;
- a new Dynamic End algorithm or completion detector;
- a new status taxonomy or Stop Condition;
- persistence or Candidate schema redesign;
- ScreeningProfile or R06 Rule Engine changes;
- LLM, Criterion Evaluation, AI Boolean contract, or Candidate Decision;
- favorite/forward/reject/skip integration;
- RuleSet-to-Run binding;
- GUI work;
- R08–R14 functionality; or
- a generic scanner, orchestration, policy, Gate, Guard, Wrapper, or Validator framework.

## 14. Deviations

None

## 15. Open Issues

None

## 16. Contract Conflicts

None

## 17. Acceptance Status

Automated Acceptance Passed / Pending Human Final Review
