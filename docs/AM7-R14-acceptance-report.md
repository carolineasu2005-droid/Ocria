# Ocria Am7 — AM7-R14 Acceptance Report

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R14
- Requirement Name: Am7 Final Integration, Regression & Production Readiness Acceptance
- Report Type: Final Automated Acceptance
- Date: 2026-08-23 (Asia/Shanghai)
- Branch: `am7-r14-final-integration-acceptance`
- Observed HEAD: `855f7125ebc7b1e62d5a35232892a7d29e28a258`
- Official Baseline: `855f7125ebc7b1e62d5a35232892a7d29e28a258`
- Frozen RPD: `docs/RPD-AM7-R14-final-integration-acceptance.md` v0.1 Frozen
- Frozen TID: `docs/TID-AM7-R14-final-integration-acceptance.md` v0.1 Frozen

## 2. Acceptance Scope

R13 is the Am7 Feature Complete boundary. R14 adds no product feature and
expects zero production-runtime source changes. This turn performs automated
acceptance only; it does not perform Human Production Smoke, modify runtime,
README, tests, Frozen documents, packaging, or Git history.

## 3. Changed File Scope

Observed working-tree scope before this report:

| File | Status / owner |
|---|---|
| `README.md` | Modified separate Sol Ultra R14 deliverable |
| `docs/RPD-AM7-R14-final-integration-acceptance.md` | Untracked Frozen requirement document |
| `docs/TID-AM7-R14-final-integration-acceptance.md` | Untracked Frozen requirement document |
| `tests/test_am7_final_integration.py` | Untracked Change 1 dedicated integration test |
| `docs/AM7-R14-acceptance-report.md` | This acceptance report |

Observed production runtime source changes: **0**. `git diff --name-status`
contained only `README.md`; `git status --short` contained no production `.py`
change. `git diff --check` passed; CRLF and global-ignore access messages were
warnings, not whitespace defects.

## 4. Dedicated Integration Verification

Command:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_am7_final_integration -v
```

Result: **Passed** — 10 tests run, 0 failures, 0 errors, 0 skips.

| Journey | Required evidence | Status |
|---|---|---|
| J01 | completed → qualified → favorite; outcome and Decision precede action | Passed |
| J02 | completed → qualified → forward; outcome and Decision precede action | Passed |
| J03 | qualified + `no_forward`; no forward and no favorite fallback | Passed |
| J04 | completed → rejected; zero action and normal return | Passed |
| J05 | three accepted technical failures → `ai_failed`; three errors, zero R06/action | Passed |
| J06 | retry recovery; one error then completed qualified forward | Passed |
| J07 | final AI outcome write failure blocks Decision/action | Passed |
| J08 | Decision write failure retains outcome and blocks action | Passed |
| J09 | failed-attempt write failure blocks retry/downstream work | Passed |
| J10 | same immutable Run-bound RuleSet for two Candidates; no RuleSet identity persistence | Passed |

Compile command:

```powershell
.\venv\Scripts\python.exe -m compileall tests\test_am7_final_integration.py
```

Compile result: **Passed**.

## 5. Full Automated Regression

Command:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Final result: **Failed** — 1042 tests run, 0 assertion failures, 8 errors,
0 skips, exit code 1.

The initial verbose terminal output was truncated by the execution channel. A
non-mutating in-memory recapture of the same command established the final
count and failure report; it did not modify the repository.

All eight errors are `TypeError` at the same protected source boundary:
`simple_brush.run()` requires keyword-only `run_bound_rule_set`, while existing
regression tests call it without that required argument.

| Existing regression test | Exact failure |
|---|---|
| `test_mouse_motion.HumanMouseMotionTests.test_run_resets_simple_mouse_state_before_input_failure` | `simple_brush.run()` missing `run_bound_rule_set` |
| `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_disabled_initial_store_stops_before_hard_recovery_business_calls` | same `TypeError` |
| `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_disabled_initial_store_stops_before_listener_browser_or_view` | same `TypeError` |
| `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_failed_hard_recovery_keeps_existing_stop_finalization` | same `TypeError` |
| `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_hard_recovery_ignores_candidate_and_error_store_failures` | same `TypeError` |
| `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_hard_recovery_starts_a_fresh_candidate_recording_lifecycle` | same `TypeError` |
| `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_normal_run_keeps_one_builder_and_sequence_for_one_candidate` | same `TypeError` |
| `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_run_exception_saves_aborted_candidate_and_closes_error` | same `TypeError` |

Minimum source evidence:

- `simple_brush.py:3832` defines `run(..., *, run_bound_rule_set: ScreeningRuleSet)`.
- The failing legacy test calls are at `tests/test_mouse_motion.py:521` and
  `tests/test_ocr_stage0_integration.py:1167,1310`.

Classification: **Product/Test regression failure** for R14 automated
acceptance. It is not an interpreter, network, ACL, or transient infrastructure
failure. R14 authorizes neither a protected runtime compatibility change nor an
existing-test change; no correction was made.

## 6. BossOCR Legacy/Core Regression

Not established as passing. The complete tracked suite did not meet its zero-
error gate. Legacy/Core test execution began, but R14 may not claim complete
regression success while the suite fails.

## 7. OCR R02–R07 Regression

Not established as passing. The failures are in existing OCR-stage main-flow
regression tests whose no-RuleSet `run()` calls no longer satisfy the protected
R13 Run boundary. `OCR R02`–`OCR R07` remain a distinct namespace from
`AM7-R02`–`AM7-R07`.

## 8. AM7-R02–AM7-R13 Integration Evidence

The dedicated J01–J10 test passed real post-Candidate R09, R10, R11, R13, R06,
and R12 boundaries. Existing focused modules for Provider configuration/runtime,
ScreeningProfile, Rule Engine, Candidate input, Prompt/Boolean Contract, R11,
R12, and R13 executed as part of discovery, but the R14 full regression gate
failed. Consequently, this section is evidence of the completed dedicated
chain, not a claim that every upstream regression is accepted.

## 9. Candidate / Run Regression

Candidate Switch, batch entry/first Candidate, continuation, refresh, last-
Candidate, pause, ESC stop, and duration behavior are covered by existing
tracked tests, but their aggregate R14 regression acceptance is **not
established** because the complete suite has eight errors at the Run invocation
boundary.

## 10. Action Regression

Dedicated J01–J04 and J06 prove qualified-only favorite/forward authorization,
`no_forward` suppression, and rejected zero-action behavior. Full action/focus
regression is not accepted while the complete suite fails.

## 11. Calibration / Mouse Regression

Not established as passing for final R14 acceptance. One of the eight errors
is the existing simple-mouse regression test calling `simple_brush.run()`
without the required Run-bound RuleSet.

## 12. R13 Persistence / Failure Ordering

Dedicated J01–J10 passed real `ai_errors.jsonl`, `ai_results.jsonl`, and
`decisions.jsonl` persistence evidence. They prove failed-attempt persistence
before retry, final outcome before Decision, Decision before qualified action,
`ai_failed` continuation, and propagation of each required persistence failure.

## 13. README Source Consistency Review

The root README and relevant current source were directly reviewed before the
blocking full-regression conclusion. It accurately presents Ocria/BossOCR
identity, the 11 CLI arguments, Chrome-first/Edge fallback, two supported
runtime Providers, Profile/Criteria, `AND`/`OR`/parentheses/ANY RuleSet
semantics, action and `no_forward` authority, Candidate/OCR boundaries, the
three-attempt policy, the three R13 JSONL streams, no automatic fallback, and
the absence of GUI/AI Replay/Cache/database/DOM automation.

It also records rather than conceals the current release-automation limitation,
and uses `YOUR_API_KEY` rather than a credential value. The source-to-document
comparison found no substantive root-README contradiction.

Documentation Verification: **Passed**. AC-22 documentation content is
source-consistent; this does not cure the failed full-regression gate.

Non-blocking out-of-scope findings recorded by README: historical old-doc
references, Legacy keyword descriptions, Edge-only historical documentation,
old automatic claims, incompatible build/workflow smoke commands, and a
missing historical release-note file. None was modified in R14.

## 14. Protected Runtime Source Review

**Passed.** Production runtime modified-file count: **0**. No protected runtime
file has a working-tree diff. The current failed full-regression boundary is
reported without modifying `simple_brush.py` or another production source.

## 15. No-New-Capability Review

**Passed.** The R14 Change is one test module and this report. No AI Replay,
Replay Cache, historical Candidate rescreening, database, Talent Library, GUI,
Provider/model fallback, retry redesign, Decision/action status, persistence
schema, RuleSet identity/persistence, or generic framework was added.

## 16. Technical Responsibilities R01–R24

| ID | Requirement | Evidence | Status |
|---|---|---|---|
| R01 | Dedicated final integration test | `tests/test_am7_final_integration.py`; focused run | Passed |
| R02 | Real Candidate boundary | J01–J10 real finalized Candidate fixture | Passed |
| R03 | Real R09 input | Unpatched R11 attempt path in J01–J10 | Passed |
| R04 | Real R10 prompt/contract | Strict controlled Provider responses through real path | Passed |
| R05 | Real R11 attempt | Only Provider completion boundary patched | Passed |
| R06 | Real R13 bounded attempts | J05, J06, J09 | Passed |
| R07 | Real AI-error persistence | J05/J06 real JSONL; J09 exact failure boundary | Passed |
| R08 | Real final-outcome persistence | J01–J06/J08 real JSONL; J07 exact failure boundary | Passed |
| R09 | Real Rule Engine | J01–J04, J06, J10 | Passed |
| R10 | Real CandidateDecision | J01–J06, J08, J10 | Passed |
| R11 | Qualified favorite | J01 | Passed |
| R12 | Qualified forward | J02, J06 | Passed |
| R13 | `no_forward` authority | J03 | Passed |
| R14 | Rejected zero action | J04 | Passed |
| R15 | `ai_failed` zero action/continuation | J05 | Passed |
| R16 | Retry recovery | J06 | Passed |
| R17 | Persistence failure blocks downstream work | J07–J09 | Passed |
| R18 | Three streams / ordering / cardinality | J01, J04–J10 | Passed |
| R19 | One immutable Run-bound RuleSet | J10 and scope review | Passed |
| R20 | Complete tracked suite passes | 1042 tests; 8 errors | Failed |
| R21 | Legacy/Core and OCR R02–R07 regression pass | Full gate failed at Run invocation boundary | Not established |
| R22 | Switch/calibration/action/mouse/continuation regression pass | Full gate failed at Run invocation boundary | Not established |
| R23 | README source consistency | Direct root README/source comparison | Passed |
| R24 | Zero runtime diff/no new capability/Human-only smoke | Scope review and command review | Passed |

Technical Responsibilities: **21 / 24 Passed; 1 Failed; 2 Not established.**

## 17. Product Acceptance Criteria AC-01–AC-24

| AC | Requirement summary | Evidence | Status |
|---|---|---|---|
| AC-01 | Complete production chain | J01–J10 prove post-Candidate chain; full upstream regression failed | Not established |
| AC-02 | Qualified mapping | J01/J02/J03/J06 | Passed |
| AC-03 | Favorite authorization | J01 | Passed |
| AC-04 | Forward authorization | J02/J06 | Passed |
| AC-05 | `no_forward` authority | J03 | Passed |
| AC-06 | Rejected zero action | J04 | Passed |
| AC-07 | AI-failed zero action | J05 | Passed |
| AC-08 | AI-failed continuation | J05 normal return; full continuation gate failed | Not established |
| AC-09 | Persistence integrity Run-fatal | J07–J09 propagation; full Run regression failed | Not established |
| AC-10 | Final outcome ordering | J01/J07/J08 | Passed |
| AC-11 | Decision ordering | J01/J02/J08 | Passed |
| AC-12 | Candidate Switch regression | Full gate failed | Not established |
| AC-13 | OCR R02–R07 regression | Full gate failed | Not established |
| AC-14 | Candidate evidence/OCR Store regression | Full gate failed | Not established |
| AC-15 | Existing action regression | Full gate failed | Not established |
| AC-16 | Calibration regression | Full gate failed | Not established |
| AC-17 | Mouse regression | Full gate failed; one direct error | Not established |
| AC-18 | Batch entry regression | Full gate failed | Not established |
| AC-19 | Run and continuation regression | Full gate failed; seven stage0 errors | Not established |
| AC-20 | BossOCR Legacy/Core regression | Full gate failed | Not established |
| AC-21 | Full tracked automated suite | 1042 tests; 8 errors | Failed |
| AC-22 | Source-accurate README | Direct source-to-document comparison | Passed |
| AC-23 | No live automated smoke | Only local controlled tests run | Passed |
| AC-24 | No new product capability | Scope/diff review | Passed |

Product AC: **11 / 24 Passed; 1 Failed; 12 Not established.**

## 18. Deviations

None from the Frozen R14 scope. The terminal's verbose-output truncation
required a non-mutating evidence recapture; it did not alter product or test
scope and established the final full-suite result.

## 19. Open Issues

**Blocking automated-acceptance issue:** the complete tracked regression suite
does not satisfy zero errors because eight existing tests call
`simple_brush.run()` without the required R13 `run_bound_rule_set` argument.
No R14 corrective scope authorizes changing the protected runtime signature or
those existing tests.

### Non-blocking Out-of-Scope Findings

- Historical documents and release/build automation issues described in the
  root README remain outside this Change.
- The root README documents these limitations and does not claim a verified
  current production release.

## 20. Contract Conflicts

**1 observed blocking baseline conflict.** The Frozen requirement demands a
zero-error complete suite while R14 acceptance permits only the report write
and forbids runtime/test changes. The current protected `run_bound_rule_set`
Run signature conflicts with eight existing regression calls that omit it.
Human must decide a separately authorized corrective scope.

## 21. Human Production Smoke Checklist

All items remain **Pending** and were not performed by Codex:

1. Ocria starts normally.
2. AI Provider configuration loads normally.
3. ScreeningProfile loads normally.
4. ScreeningRuleSet binds normally.
5. Calibration / Calibration Profile works normally.
6. “最近没看过” filtering works normally.
7. First Candidate is positioned/opened normally.
8. Candidate Switch Verification works normally.
9. Complete OCR works normally.
10. AI completed produces complete Boolean Criteria mapping.
11. `qualified` + favorite works normally.
12. `qualified` + forward works normally.
13. `rejected` performs zero action.
14. `ai_failed` performs zero action.
15. `ai_failed` with healthy persistence continues.
16. Next Candidate proceeds normally.
17. Pause/resume works normally.
18. ESC safe stop works normally.

## 22. Final Automated Status

```text
Implementation / Integration Verification: Completed
Dedicated Integration Verification: Passed
Full Automated Regression: Failed (1042 tests; 8 errors)
Documentation Verification: Passed
Automated Acceptance: Failed

Human Production Smoke: Pending
Human Final Review: Pending
Am7 Production Readiness: Pending
```

This report does not declare Human Production Smoke passed, Human Final Review
accepted, or Am7 Production Readiness accepted.
