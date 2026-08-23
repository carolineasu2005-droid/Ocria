# Ocria Am7 — AM7-R14 Am7 Final Integration, Regression & Production Readiness Acceptance

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R14
- Requirement Name: Am7 Final Integration, Regression & Production Readiness Acceptance
- Document Type: Technical Implementation Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Source RPD: `docs/RPD-AM7-R14-final-integration-acceptance.md` — v0.1 Frozen
- Requirement Branch: `am7-r14-final-integration-acceptance`
- Requirement Branch Observed: `am7-r14-final-integration-acceptance`
- Official Baseline: `855f7125ebc7b1e62d5a35232892a7d29e28a258`
- Working HEAD Observed: `855f7125ebc7b1e62d5a35232892a7d29e28a258`
- Prepared On: 2026-08-23（Asia/Shanghai）

This document defines the Frozen technical implementation contract for AM7-R14. It answers only how to obtain the Frozen RPD's final integration, regression, documentation-consistency, and acceptance evidence. It does not authorize a production runtime change, README authoring, Acceptance Report creation, live production smoke, Git operation, packaging, or release.

## 2. Frozen RPD Authority

The following preconditions were confirmed before this TID was designed:

- the source RPD is Version `0.1` and Status `Frozen`;
- the Frozen Product Acceptance Criteria are exactly `AC-01` through `AC-24`;
- Open Product Decisions are `0`;
- Contract Conflicts are `0`;
- Deviations are `None`;
- the merged R13 baseline is the Am7 Feature Complete boundary;
- R14 adds no product capability;
- AI Replay, Replay Cache, and Historical Candidate Rescreening are excluded;
- expected production runtime changes are `0`;
- the detailed root README owner is Sol Ultra in a separate task;
- Human Production Smoke is Human-only.

The Frozen RPD is the sole AM7-R14 product authority. This TID does not reopen R02–R13 contracts or any OCR-stage contract.

The requirement identity also matches the repository state observed during targeted inspection:

- branch: `am7-r14-final-integration-acceptance`;
- HEAD: `855f7125ebc7b1e62d5a35232892a7d29e28a258`.

## 3. Technical Objective

AM7-R14 will close automated integration acceptance by adding one dedicated test module, running it before the complete tracked test suite, verifying the separately authored README against final source, checking the final file scope, and recording the results in the later Acceptance Report.

The dedicated test starts at a real finalized `CandidateOcrDocument` and exercises the existing post-Candidate production chain:

```text
CandidateOcrDocument
→ _process_finalized_candidate(...)
→ _run_r13_ai_screening(...)
→ _run_ai_screening_attempt(...)
→ build_ai_candidate_input(...)
→ build_ai_screening_prompt(...)
→ Provider completion boundary
→ validate_ai_screening_response(...)
→ AIScreeningRecordStore final-outcome persistence
→ decide_candidate(...)
→ evaluate_rule_set(...) when AI completed
→ CandidateDecisionRecord persistence
→ qualified-only existing action authorization
→ normal return to existing Candidate continuation
```

Production runtime source changes required: **0**.

Codex implementation Changes: **1**.

## 4. Current Implementation Seams

### 4.1 Candidate evidence boundary

`ocr_records.CandidateOcrDocument` is the accepted finalized Candidate evidence type. A test-local fixture may use the existing `ocr_candidate.CandidateOcrBuilder` to construct and finalize a valid object, but the R14 journey begins only after that real `CandidateOcrDocument` exists. The dedicated test does not simulate live BOSS, a browser, OCR capture, mouse input, or Candidate switching.

### 4.2 R09 and R10

The current real local chain is:

- `ai_candidate_input.build_ai_candidate_input(candidate) -> AICandidateInput`;
- `ai_screening_prompt.build_ai_screening_prompt(candidate_input, profile) -> AIScreeningPrompt`;
- `ai_screening_contract.validate_ai_screening_response(raw_response, criteria) -> dict[str, bool]`.

R09 copies the authoritative non-blank `CandidateOcrDocument.document_text`. R10 constructs Prompt v1 and validates the exact complete Boolean response contract. None of these callables is mocked in R14.

### 4.3 R11 accepted attempt seam

`ai_screening_runtime._run_ai_screening_attempt(candidate, profile, config)` is the accepted private R13 attempt seam. It executes real R09 projection, real R10 prompt construction, the Provider completion boundary, and real R10 response validation. It returns `_AIScreeningAttemptOutcome`, containing one `AIScreeningResult` and either no failure or one structured `_AIScreeningAttemptFailure`.

The dedicated test patches only `ai_screening_runtime.complete`, the imported Provider network completion boundary used by the real attempt function. Successful controlled responses are real `llm_provider_runtime.LLMCompletionResult` values. Accepted technical failures are real `llm_provider_runtime.LLMRuntimeError` values. The private attempt seam itself is not patched.

### 4.4 R13 orchestration and persistence

`simple_brush._run_r13_ai_screening(candidate, profile, config, store)` is the current bounded-attempt orchestration seam. It:

1. enforces Candidate/Run identity;
2. performs at most three formal attempts;
3. persists every failed-attempt record with `AIScreeningRecordStore.append_ai_error(...)` before another attempt;
4. persists exactly one final outcome with `append_ai_result(...)`;
5. returns the selected final `AIScreeningResult` only after that final write succeeds.

`ai_screening_persistence.AIScreeningRecordStore(run_dir, run_id)` is the real persistence implementation. It owns exactly:

- `ai_errors.jsonl`;
- `ai_results.jsonl`;
- `decisions.jsonl`.

The R14 test uses this real store in a `TemporaryDirectory`. It reads the resulting JSONL files back with the standard `json` module to verify record content, order within each stream, and cardinality. It does not replace R13 record construction or successful persistence with a mock.

### 4.5 R06, R12, and action authorization

`candidate_decision.decide_candidate(ai_result, rule_set)` is the real R12 Decision function. For a completed result it calls the real `screening_rule_engine.evaluate_rule_set(rule_set, criterion_results)`; for a failed result it returns `ai_failed` without executing R06.

`simple_brush._process_finalized_candidate(candidate, profile, config, rule_set, store)` is the narrow existing cross-module integration seam. It:

1. calls `_run_r13_ai_screening(...)`;
2. calls the real `decide_candidate(...)` only after final AI outcome persistence;
3. persists one real `CandidateDecisionRecord` before action;
4. authorizes `perform_favorite_action()` or `forward_one_candidate()` only for `qualified` according to the existing `action_mode` and `no_forward_mode` controls;
5. returns the Decision normally for the existing Candidate loop to continue.

The dedicated R14 test invokes this callable directly. Only the favorite and forward physical GUI functions are patched.

### 4.6 Run binding and continuation

`simple_brush.main()` creates one `ScreeningRuleSet` from explicit Run input and passes that object to `run(..., run_bound_rule_set=...)`. `run(...)` retains the same object and passes it to every eligible `_process_finalized_candidate(...)` call. It also loads one saved `ScreeningProfileVersion`, one valid `AIProviderConfig`, and creates one `AIScreeningRecordStore` bound to the OCR Run directory and `run_id`.

The Candidate loop already resumes after a normal `_process_finalized_candidate(...)` return. Existing focused `simple_brush` tests cover Candidate switching, next-Candidate progression, batch refresh, last-Candidate handling, stop/pause, and the Run-level projection of `AIPersistenceIntegrityError`. R14 does not copy that loop into a second simulator.

### 4.7 Regression surfaces inspected

The targeted source and test review confirmed existing coverage and production boundaries for:

- Provider configuration/runtime;
- ScreeningProfile and Rule Engine;
- Complete Scan, OCR Candidate building, records, store, normalization, and similarity;
- Candidate Decision and R13 persistence;
- Candidate switching and existing action authorization;
- calibration profiles, template, steps, and OCR calibration;
- mouse/WindMouse behavior;
- BossOCR Legacy/Core and the accepted OCR replay regression tooling.

The OCR replay tests remain offline OCR regression tooling. They are not AI Replay, Replay Cache, or Historical Candidate Rescreening.

The current implementation supports the Frozen RPD with zero production runtime code changes.

## 5. Technical Scope

### 5.1 In scope

- one dedicated cross-module integration test module;
- J01–J10 using real post-Candidate production modules;
- focused integration, compile, and full tracked regression gates;
- source-to-document verification of the separately authored root README;
- protected-runtime and final-diff review;
- later R14 Acceptance Report evidence and status discipline;
- Human Production Smoke handoff without executing it.

### 5.2 Out of scope

- any production runtime edit;
- any new runtime seam or wrapper for testing;
- README authoring by Codex;
- Acceptance Report creation in the implementation turn;
- live BOSS, browser, OCR, Provider, favorite, forward, or Candidate-switch smoke;
- correction of a runtime defect without a separate Human-authorized scope;
- any product capability, architecture cleanup, packaging, or release work.

## 6. Change 1 — Dedicated Final Integration Evidence

### 6.1 File

Create:

```text
tests/test_am7_final_integration.py
```

No second test-only module is required. The current seam and existing test conventions are sufficient for all J01–J10 journeys with small test-local helpers.

### 6.2 Test class and local fixtures

The file will use `unittest`, `unittest.mock`, `TemporaryDirectory`, and the standard `json` module. It will define one focused test class and only test-local fixture helpers needed to:

- create a real finalized `CandidateOcrDocument` with a non-blank authoritative `document_text` and controlled `run_id` / `candidate_record_id`;
- create a real `ScreeningProfileVersion` with real `Criterion` values and `criteria_digest(...)`;
- create a complete synthetic `AIProviderConfig` using non-secret example values and no config-store write;
- create immutable real `ScreeningRule` / `ScreeningRuleSet` values;
- create controlled real `LLMCompletionResult` values containing strict R10 JSON;
- create real normalized `LLMRuntimeError` values for accepted technical-failure journeys;
- create one real `AIScreeningRecordStore` inside a fresh `TemporaryDirectory`;
- read non-empty JSONL lines back into mappings;
- save and restore only the `simple_brush` globals touched by the test: `action_mode`, `no_forward_mode`, `stop_event`, `paused`, and `forward_consecutive`.

Test data must use synthetic identifiers, endpoint text, model text, and API-key text. It must not read or write user AI configuration, calibration profiles, `logs/`, an OCR Run directory, or a real API key.

### 6.3 Test method plan

Use ten explicit test methods, one for each J01–J10 journey. Shared fixture helpers may remove setup repetition, but must not become a generic pipeline, E2E, browser, orchestration, Gate, Guard, Scanner, Wrapper, or Validator framework.

### 6.4 Ordering evidence

Successful writes use the real `AIScreeningRecordStore`. Ordering is verified without replacing R09, R10, R06, R12, R13 records, or successful R13 persistence:

- qualified action fakes inspect the real JSONL files at action invocation and require both the final outcome and Decision records already to exist;
- J07 injects failure at the exact `append_ai_result(...)` boundary and uses a RuleSet that would fail if R06/Decision were reached, proving the final write is a prerequisite;
- J08 injects failure at the exact `append_decision(...)` boundary, captures the real Decision record supplied to that write, and verifies the already persisted final AI outcome remains;
- J09 injects failure at the exact `append_ai_error(...)` boundary and verifies that no retry or downstream record/action occurs;
- per-stream JSONL content and cardinality prove the required persisted order of the three failed attempts and the single final records.

No internal Decision, R06, R09, R10, or R13 success-path callable is patched merely to collect events.

### 6.5 Implementation Change count

Implementation Changes: **1**.

This Change creates one test file only. Production runtime changes: **0**.

## 7. Real Production Module Boundaries

The dedicated test must use these actual modules and callables:

| Requirement boundary | Real implementation used |
|---|---|
| Candidate evidence | real `CandidateOcrDocument` produced by a test fixture |
| AM7-R09 | `build_ai_candidate_input(...)` through `_run_ai_screening_attempt(...)` |
| AM7-R10 prompt | `build_ai_screening_prompt(...)` through `_run_ai_screening_attempt(...)` |
| Provider request shape | real `LLMCompletionRequest` and `LLMMessage` construction |
| AM7-R10 response contract | `validate_ai_screening_response(...)` through `_run_ai_screening_attempt(...)` |
| AM7-R11 attempt | `_run_ai_screening_attempt(...)` |
| AM7-R13 retry/orchestration | `_run_r13_ai_screening(...)` |
| AM7-R13 records/store | real record dataclasses and `AIScreeningRecordStore` |
| AM7-R06 | `evaluate_rule_set(...)` through real `decide_candidate(...)` |
| AM7-R12 | `decide_candidate(...)` and real `CandidateDecision` |
| action authorization | `_process_finalized_candidate(...)` |
| existing continuation | Decision return plus existing loop/regression evidence |

The test must not call `run_ai_screening(...)` as a replacement for R13 orchestration, because R13 correctly consumes the accepted private attempt seam. It must not add a production API to expose intermediate state.

## 8. Allowed Test Doubles

### 8.1 Allowed

- patch `ai_screening_runtime.complete` to avoid Provider/network inference while preserving the real R11 attempt path;
- patch `simple_brush.perform_favorite_action` to observe favorite authorization without GUI effects;
- patch `simple_brush.forward_one_candidate` to observe forward authorization without GUI/email effects;
- control the existing `simple_brush.stop_event`, `paused`, `action_mode`, and `no_forward_mode` values and restore them after every test;
- patch physical `time.sleep` only if a deterministic stop/pause assertion needs it;
- inject `AIPersistenceIntegrityError` at exactly one required `append_ai_error`, `append_ai_result`, or `append_decision` boundary for J07–J09.

### 8.2 Forbidden

Do not mock or replace:

- `build_ai_candidate_input(...)`;
- `build_ai_screening_prompt(...)`;
- `validate_ai_screening_response(...)`;
- `_run_ai_screening_attempt(...)`;
- `_run_r13_ai_screening(...)`;
- `evaluate_rule_set(...)`;
- `decide_candidate(...)`;
- R13 record construction;
- successful `AIScreeningRecordStore` writes;
- the whole chain with a Browser or E2E simulator.

Exact persistence-failure injection is a Frozen failure-boundary test, not authorization to replace the persistence implementation generally.

## 9. Integration Journeys J01–J10

### J01 — Completed AI → Qualified → Favorite

Use a real Candidate, Profile, Config, passing RuleSet, R11 attempt path, R10 validation, R13 store, R06, and R12. Return one strict complete Provider response. Set favorite mode.

Verify:

- `CandidateDecision.decision_status == "qualified"`;
- one completed final record with `attempts_used == 1` and correct Candidate/Profile/Provider/model trace fields;
- one qualified Decision record;
- the favorite fake is called exactly once and the forward fake zero times;
- both persisted records exist before the favorite fake runs;
- `ai_errors.jsonl` is empty.

J07 and J08 provide the complementary cut-point proof for final-outcome-before-Decision and Decision-write-before-action ordering.

### J02 — Completed AI → Qualified → Forward

Use the same real chain with forward mode and `no_forward_mode == False`.

Verify one completed final outcome, one qualified Decision, forward authorization exactly once, favorite zero, and persisted outcome/Decision presence before the forward fake runs. Do not enter or test forward GUI mechanics here.

### J03 — Qualified + `no_forward`

Use a completed passing mapping with forward mode and `no_forward_mode == True`.

Verify the real Decision remains `qualified`, the completed outcome and qualified Decision are persisted, forward is never called, and favorite is not used as a fallback.

### J04 — Completed AI → Rejected

Return a complete valid mapping that makes the real Run-bound RuleSet false.

Verify `rejected`, one completed final outcome, one rejected Decision record, zero favorite/forward, and a normal Decision return showing that the existing caller may continue.

### J05 — Three Accepted AI Technical Failures

Make the Provider network boundary raise a real accepted `LLMRuntimeError` three times. Supply a syntactically valid RuleSet whose Criterion reference is absent from any completed mapping; successful `ai_failed` return therefore also proves R06 was not executed.

Verify:

- Provider completion attempts: exactly three;
- `ai_errors.jsonl`: exactly three records with attempt numbers `1`, `2`, `3` in order;
- `ai_results.jsonl`: exactly one final record with `ai_status == "failed"`, `criteria_results is None`, and `attempts_used == 3`;
- `decisions.jsonl`: exactly one `ai_failed` record;
- zero favorite and zero forward;
- normal `ai_failed` return, with no new failure counter or stop state, permits existing Candidate-level continuation.

### J06 — Retry Recovery

Make attempt 1 raise an accepted technical `LLMRuntimeError`, then return a strict completed response for attempt 2.

Verify:

- exactly two Provider calls and no attempt 3;
- one attempt-error record with attempt number 1;
- exactly one final completed record with `attempts_used == 2`;
- real Rule evaluation and the corresponding real Decision;
- the selected action behavior for that Decision, with no extra action path.

Use a passing RuleSet and forward mode for a single qualified forward authorization; J04 already covers the recovered chain's rejected/zero-action counterpart semantically.

### J07 — Final AI Outcome Persistence Failure

Return one valid completed Provider response, then inject `AIPersistenceIntegrityError("write_ai_result", store.ai_results_path)` at the exact final-outcome append boundary. Use a RuleSet that would fail on evaluation if the Decision path were reached.

Verify:

- the persistence error propagates;
- no Decision record exists;
- favorite and forward are both zero;
- no fallback result or action is manufactured;
- the R06/Decision path was not reached before the required final write.

The existing `simple_brush` Run integration test remains the evidence that a propagated R13 persistence failure projects to safe `RunStatus.ERROR` cleanup and prevents a later Candidate. The R14 test does not reproduce the entire Run loop.

### J08 — Decision Persistence Failure

Complete AI and Rule evaluation normally, allow the real final-outcome write, then inject `AIPersistenceIntegrityError("write_decision", store.decisions_path)` at the exact Decision append boundary.

Verify:

- the real final completed outcome remains in `ai_results.jsonl`;
- the Decision record offered to the failed boundary has the expected status and identity;
- `decisions.jsonl` contains no successful write;
- favorite and forward are both zero;
- the persistence error propagates without rollback or fallback.

### J09 — Failed-Attempt Persistence Failure

Make attempt 1 fail technically, then inject `AIPersistenceIntegrityError("write_ai_error", store.ai_errors_path)` at the exact failed-attempt append boundary.

Verify:

- the persistence error propagates;
- Provider call count remains one, so attempt 2 never starts;
- no final AI outcome and no Decision record exists;
- favorite and forward are both zero;
- no fallback is created.

### J10 — Same Run-bound `ScreeningRuleSet` Authority

Create exactly one real immutable `ScreeningRuleSet` object and use it for two real Candidate processing calls within the same synthetic Run/store. Do not load or rebuild rules between Candidates.

Verify:

- both Decisions follow that same RuleSet's semantics;
- the test passes the identical object for both calls;
- the current `_process_finalized_candidate(...)` / `run(...)` source path has no per-Candidate RuleSet lookup, Profile-owned RuleSet, or Legacy conversion;
- the RuleSet type remains only a one-or-more tuple of immutable `ScreeningRule` values;
- none of the three real R13 JSONL streams gains RuleSet ID, version, digest, or payload fields;
- no RunManifest or persistence schema change is introduced.

Identity beyond the current function argument is verified by the existing source seam and the test's reuse of the exact object. R14 must not create a runtime hook solely to observe object identity.

## 10. Continuation Evidence Strategy

R14 uses three complementary evidence sources rather than duplicating the browser loop:

1. J04 and J05 require `_process_finalized_candidate(...)` to return real `rejected` and `ai_failed` Decisions normally with no stop flag or action.
2. Existing `tests/test_candidate_decision_integration.py` verifies Candidate-level recovery, repeated `ai_failed` behavior, stop/pause handling, action ordering, and Run-bound RuleSet handoff.
3. Existing `tests/test_simple_brush_ocr.py` verifies the real Candidate loop, Candidate switch, next-Candidate progression, batch refresh, last-Candidate behavior, safe cleanup, and Run-fatal persistence projection.

The full tracked regression command is the authority for this existing evidence at the final acceptance baseline. No second main-loop or browser simulator is added.

## 11. Full Regression Strategy

### 11.1 Execution order

1. compile the new test module;
2. run the focused R14 integration module;
3. only after focused success, run the complete tracked automated suite;
4. verify README consistency and file scope;
5. create the Acceptance Report in its separately authorized closeout turn.

### 11.2 Authoritative complete suite

The primary complete-suite command is:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Pass requires zero failures and zero errors. The TID does not freeze an expected total test count. The Acceptance Report must record actual tests run, failures, errors, and skips, if any.

### 11.3 Regression authority

The complete suite is responsible for the accepted regression surfaces listed in Frozen AC-12 through AC-21, including BossOCR Legacy/Core, OCR R02–R07, Candidate evidence/store, Candidate switching, calibration, actions, focus restoration, mouse behavior, pause/stop, batching, and continuation.

AM7 Requirement identifiers (`AM7-R02` through `AM7-R13`) and OCR stage identifiers (`OCR R02` through `OCR R07`) remain separate namespaces. R14 does not merge, alias, renumber, or reinterpret them.

### 11.4 Failure classification

- a reproducible product/test failure in the focused or full suite makes `Automated Acceptance: Failed`;
- a sandbox, file-lock, interpreter, missing-environment, or comparable execution failure is reported as infrastructure failure, not product pass or product fail;
- warnings do not automatically fail acceptance unless a Frozen contract makes the warning a failure;
- no failed assertion may be hidden by weakening a test or changing a Frozen expectation.

## 12. README Delivery / Verification Boundary

### 12.1 Ownership workflow

The fixed workflow is:

1. Frozen RPD;
2. Frozen TID;
3. Sol Ultra separately reads the final source;
4. Sol Ultra authors the detailed root `README.md`;
5. Human reviews the README;
6. Codex R14 Acceptance performs source-to-document consistency verification.

Codex Acceptance may read, compare, and report a mismatch. It must not opportunistically rewrite README, change its style, add features, or expand documentation scope.

### 12.2 Required consistency matrix

| Area | Source-to-document verification |
|---|---|
| A. Startup / CLI | Compare README with actual `parse_args()`, startup menu, Configuration entrypoints, and Run entry requirements. |
| B. AI Provider | Compare Provider, Base URL, API Key, Model, load status, and current configuration semantics with `ai_provider_config.py`, `llm_provider_runtime.py`, and startup loading. |
| C. Screening | Compare `ScreeningProfileVersion`, Criterion truth semantics, `ScreeningRuleSet`, `AND`, `OR`, parentheses, precedence, one-or-more Rules, and multi-Rule ANY with source. |
| D. Actions | Compare favorite, forward, Action Mode, and `no_forward` authority with `simple_brush.py`. |
| E. OCR / Candidate | Compare Complete Scan, `CandidateOcrDocument`, Candidate Switch, batch filtering, and calibration with current source. |
| F. AI failure | Require maximum three formal attempts, zero retry delay, `ai_failed`, Candidate continuation after successful persistence, and persistence-fatal distinction. |
| G. Persistence | Require the exact files `ai_errors.jsonl`, `ai_results.jsonl`, and `decisions.jsonl` and their current responsibilities. |
| H. No imaginary features | Reject claims of GUI, AI Replay, Replay Cache, historical Candidate rescreening, database, Talent Library, automatic Provider/model fallback, DOM, Selenium, Playwright, or an automatic Prompt-version framework. |

The review also checks installation, Windows/Python requirements, safe non-live verification commands, common failures, limitations, and module responsibilities required by Frozen RPD Section 10. Examples must contain no real API key and must not imply that connection verification guarantees inference success.

AC-22 cannot pass before this source-grounded comparison passes.

## 13. Protected Runtime Source

The following files are explicitly protected from R14 Codex implementation changes:

```text
simple_brush.py
ai_candidate_input.py
ai_screening_prompt.py
ai_screening_contract.py
ai_screening_runtime.py
ai_screening_persistence.py
ai_provider_config.py
llm_provider_runtime.py
screening_profile.py
screening_rule_engine.py
candidate_decision.py
ocr_detector.py
ocr_candidate.py
ocr_records.py
ocr_store.py
ocr_normalization.py
ocr_similarity.py
mouse_motion.py
calibration_profiles.py
calibration_template.py
calibration_steps.py
ocr_calibration.py
```

All other tracked production `.py` source is also protected. R14 tests must adapt to the accepted source; production code must not be changed to make a test easier.

## 14. Failure / Defect Handling

If dedicated integration, full regression, README verification, or diff review identifies a genuine runtime defect:

```text
Automated Acceptance: Failed
→ preserve the minimum reproducible defect evidence
→ identify the exact failing Frozen contract and source boundary
→ stop without changing production runtime
→ Human decides whether to authorize a corrective Change
```

R14 does not pre-authorize the corrective Change. It also does not authorize test-expectation weakening, broader audit, cleanup, new abstraction, or unrelated fixes.

If a required persistence write fails during J07–J09, the expected test outcome is propagation of `AIPersistenceIntegrityError` and zero prohibited downstream work. The test must not reinterpret this accepted behavior as a defect.

## 15. Verification Commands

Run the gates in this order after the single implementation Change and the separately authored README are present:

```powershell
.\venv\Scripts\python.exe -m compileall tests\test_am7_final_integration.py
.\venv\Scripts\python.exe -m unittest tests.test_am7_final_integration -v
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
git diff --check
git status --short
git diff --name-status
```

No live AI API, browser, BOSS, favorite, forward, Candidate switch, OCR production, packaging, benchmark, load, or performance command is added.

The implementation turn should use the focused test repeatedly while developing the new test file and run the full suite only after the focused test is stable. The Acceptance Report must retain the final command outputs and actual counts rather than inferring success from existing test files.

## 16. Expected File Scope

### 16.1 New in Codex implementation

```text
tests/test_am7_final_integration.py
```

### 16.2 Separate deliverables

```text
README.md                                      # authored by Sol Ultra; modified
docs/AM7-R14-acceptance-report.md              # created during later acceptance
```

The RPD and this TID are Requirement documents already present in the working tree by their respective design turns.

### 16.3 Ideal final R14 PR scope

```text
M  README.md
A  tests/test_am7_final_integration.py
A  docs/RPD-AM7-R14-final-integration-acceptance.md
A  docs/TID-AM7-R14-final-integration-acceptance.md
A  docs/AM7-R14-acceptance-report.md
```

Expected production runtime diff: **0 files**.

If the Acceptance Report is ignored by existing Git rules, Human decides any later staging treatment. R14 must not modify `.gitignore`.

### 16.4 Diff checks

The final review must confirm:

- no unexpected production runtime diff;
- no unrelated file;
- no Replay/Cache implementation;
- no generic framework;
- no packaging or release change;
- no hidden modification to Prompt, RuleSet, Candidate, persistence, action, OCR, or stop contracts.

## 17. Acceptance Report Requirements

The later R14 automated closeout must create:

```text
docs/AM7-R14-acceptance-report.md
```

It must include exactly the required evidence categories:

1. Metadata.
2. Requirement / baseline / branch.
3. Frozen RPD.
4. Frozen TID.
5. R13 Feature Complete boundary.
6. Actual changed-file scope.
7. Dedicated R14 integration results.
8. Full tracked regression result.
9. Actual test counts.
10. AM7-R02–AM7-R13 integration evidence.
11. OCR R02–R07 regression evidence.
12. BossOCR Legacy/Core regression evidence.
13. Candidate Switch regression.
14. Calibration regression.
15. favorite / forward / `no_forward` regression.
16. mouse / WindMouse / simple-mouse regression.
17. R13 failure/persistence ordering.
18. README source-consistency review.
19. protected runtime source review.
20. Technical Responsibilities matrix.
21. AC-01–AC-24 matrix.
22. Deviations.
23. Open Issues.
24. Contract Conflicts.
25. Human Production Smoke checklist.
26. Automated Acceptance status.
27. Human Production Smoke status.
28. Human Final Review status.
29. Am7 Production Readiness status.

The report records evidence actually obtained at the final acceptance baseline. It does not declare a Human-owned status.

## 18. Human Production Smoke Handoff

Codex does not perform Human Production Smoke. The Acceptance Report must preserve this exact Human-owned minimum checklist:

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

Human smoke does not require deliberate disk, permission, or persistence failure. Automated J07–J09 own those failure boundaries.

After successful automated closeout, Codex may declare only:

```text
Implementation / Integration Verification: Completed
Dedicated Integration Verification: Passed
Full Automated Regression: Passed
Documentation Verification: Passed
Automated Acceptance: Passed

Human Production Smoke: Pending
Human Final Review: Pending
Am7 Production Readiness: Pending
```

Only Human may later declare the three pending Human statuses passed or accepted.

## 19. Technical Responsibilities R01–R24

| ID | Frozen technical responsibility | Planned evidence |
|---|---|---|
| R01 | Dedicated final cross-module integration test exists. | `tests/test_am7_final_integration.py`; focused command. |
| R02 | Integration begins from real CandidateOcrDocument evidence boundary. | Real finalized Candidate fixture used by J01–J10. |
| R03 | Real R09 Candidate Input Builder is used. | Unpatched R11 attempt path in J01–J10. |
| R04 | Real R10 Prompt / Boolean Contract behavior is used. | Controlled Provider output passes through real Prompt and validator. |
| R05 | Real accepted R11 AI runtime/attempt boundary is used. | Unpatched `_run_ai_screening_attempt(...)`; only `complete` is patched. |
| R06 | Real R13 bounded-attempt semantics are exercised. | J05, J06, and J09. |
| R07 | Real R13 AI error persistence is exercised. | J05/J06 real JSONL; J09 precise failed-write boundary. |
| R08 | Real R13 final AI outcome persistence is exercised. | J01–J06/J08/J10 real JSONL; J07 precise failed-write boundary. |
| R09 | Real R06 Screening Rule Engine is used. | J01–J04, J06, and J10. |
| R10 | Real R12 CandidateDecision is used. | J01–J06, J08, and J10. |
| R11 | Qualified → favorite authorization is verified. | J01. |
| R12 | Qualified → forward authorization is verified. | J02 and J06. |
| R13 | qualified + no_forward suppression is verified. | J03. |
| R14 | Rejected → zero action is verified. | J04. |
| R15 | ai_failed → zero R06/action and Candidate-level continuation semantics are verified. | J05 plus existing continuation regression. |
| R16 | Retry-recovery semantics are verified. | J06. |
| R17 | Required persistence failure blocks prohibited downstream work. | J07–J09 plus existing Run-fatal test. |
| R18 | R13 three JSONL streams and ordering/cardinality are verified. | J01, J04–J09 real file assertions. |
| R19 | Exact immutable Run-bound ScreeningRuleSet authority is preserved with no new RuleSet identity/persistence. | J10, source review, and diff review. |
| R20 | Full tracked automated suite passes. | Complete discovery command; actual counts recorded. |
| R21 | BossOCR Legacy/Core and OCR R02–R07 regression remain passing. | Full tracked suite and namespace-specific report evidence. |
| R22 | Candidate Switch / Calibration / action / mouse / continuation regression remains passing. | Full tracked suite and focused existing-module evidence. |
| R23 | README source-to-document consistency passes and no imaginary capability is documented. | Section 12 A–H review matrix. |
| R24 | Production runtime diff remains zero; no Replay/Cache/new product capability is introduced; live production smoke remains Human-only. | Diff review, protected-source review, and status audit. |

Technical Responsibilities count: **24 (R01–R24)**.

## 20. AC-01–AC-24 Mapping

| Frozen Product AC | Technical responsibility mapping | Verification evidence |
|---|---|---|
| AC-01 — Complete production chain | R01–R10, R18, R19 | J01–J06 and J10 exercise the real post-Candidate chain; full suite covers upstream/continuation. |
| AC-02 — Qualified mapping | R04, R09, R10 | J01, J02, J03, and J06. |
| AC-03 — Favorite authorization | R11 | J01. |
| AC-04 — Forward authorization | R12 | J02 and J06. |
| AC-05 — no_forward authority | R13 | J03. |
| AC-06 — Rejected zero action | R14 | J04 plus normal-return continuation evidence. |
| AC-07 — AI-failed zero action | R06, R07, R08, R15 | J05 uses a RuleSet sentinel to prove no R06 and verifies zero action. |
| AC-08 — AI-failed continuation | R15, R22 | J05 normal return plus existing Candidate loop/full regression. |
| AC-09 — Persistence integrity remains Run-fatal | R17 | J07–J09 propagation plus existing `simple_brush` Run-fatal/cleanup regression. |
| AC-10 — Final AI outcome ordering | R08, R17, R18 | J01 persisted state, J07 cut point, and J08 retained final outcome. |
| AC-11 — Decision ordering | R10, R17, R18 | J01/J02 action-time persisted state and J08 action-blocking cut point. |
| AC-12 — Candidate Switch regression | R20, R22 | Full tracked suite's Candidate Switch tests. |
| AC-13 — OCR R02–R07 regression | R20, R21 | Full tracked OCR detector/candidate/records/normalization/similarity/stage tests. |
| AC-14 — Candidate evidence and OCR Store regression | R02, R20, R21 | Real Candidate boundary plus full Candidate/OCR Store regression. |
| AC-15 — Existing action regression | R11–R13, R20, R22 | J01–J03 plus existing action/focus/full regression. |
| AC-16 — Calibration regression | R20, R22 | Full calibration profile/template/steps/OCR calibration regression. |
| AC-17 — Mouse regression | R20, R22 | Full mouse/WindMouse/simple-mouse regression. |
| AC-18 — Batch entry regression | R20, R22 | Full batch-filter and first-Candidate tests. |
| AC-19 — Run and continuation regression | R15, R17, R20, R22 | J04/J05 returns plus full pause/stop/refresh/continuation/cleanup regression. |
| AC-20 — BossOCR Legacy/Core regression | R21, R24 | Full R01/Legacy/Core suite, rule-independence tests, and scope review. |
| AC-21 — Full tracked automated suite | R20–R22 | Authoritative unittest discovery command with actual counts. |
| AC-22 — Source-accurate README | R23 | Section 12 source-to-document verification after Sol Ultra authors README. |
| AC-23 — No live automated smoke | R24 | Command review, test-double boundary, and Human handoff status. |
| AC-24 — No new product capability | R19, R24 | File/diff review; zero runtime change; no Replay/Cache/framework/placeholder. |

Product AC mapping completeness: **24 / 24**. No AC is unmapped, and no `AC-25` is introduced.

## 21. Explicitly Forbidden

AM7-R14 implementation and acceptance must not add or perform:

- a production runtime edit or test-only production seam;
- AI Replay, Replay Cache, Historical Candidate Rescreening, or related placeholder;
- database, SQLite, PostgreSQL, Talent Library, or GUI;
- Provider/model fallback, retry redesign, or new Decision/action status;
- Prompt, RuleSet, Candidate, persistence, OCR, action, stop, or Run schema change;
- RuleSet ID, version, digest, persistence, or RunManifest field;
- generic E2E, browser simulator, test orchestration, pipeline, Gate, Guard, Scanner, Wrapper, Validator, or contract framework;
- repository, privacy, secret, AST, dependency, or architecture scanner;
- new CI, benchmark, load, performance, packaging, or release verification;
- live BOSS login, browser action, favorite, forward, Candidate switch, Complete OCR, or paid/production Provider request;
- README authoring or rewriting by Codex during this Change;
- a runtime defect fix without separate Human authorization;
- Git commit, push, merge, rebase, reset, clean, tag, or release.

Legacy code remains present. Legacy keyword and match data must not gain Am7 Complete-Scan, AI Criteria, CandidateDecision, or production-action authority.

## 22. Open Technical Decisions

Open Technical Decisions: **0**.

The source review resolves the integration seam, real-module boundary, allowed doubles, persistence fixture, test file count, journey plan, commands, README ownership, and defect stop condition.

## 23. Contract Conflicts

Contract Conflicts: **0**.

The current source can satisfy all Frozen ACs using one dedicated test file and zero production runtime changes. Existing OCR replay tests remain regression tooling and do not conflict with the No AI Replay / No Historical Candidate Rescreening contract.

## 24. Deviations

Deviations: **None**.

The design uses the expected single Change, primary test file, ten journeys, 24 Responsibilities, 24 Product AC mappings, full regression gate, Sol Ultra README boundary, and Human-only smoke boundary.

## 25. Human Final TID Review / Freeze

Human Final TID Review: **Accepted**.

TID Freeze: **Approved**.

- Open Technical Decisions: `0`
- Contract Conflicts: `0`
- Deviations: `None`

Implementation is authorized only according to this Frozen TID.

Any genuine production runtime defect discovered during AM7-R14 implementation
or acceptance is not pre-authorized for correction. The implementation or
acceptance step must stop, preserve the minimum defect evidence, and return the
scope decision to Human.

## 26. Draft Summary

AM7-R14 requires one Codex implementation Change: add `tests/test_am7_final_integration.py`. The test starts from a real `CandidateOcrDocument`, exercises real R09, R10, the accepted R11 attempt seam, R13 retry and real JSONL persistence, R06, R12, and the existing `simple_brush` qualified action boundary. Only Provider network completion and physical favorite/forward effects are replaced; precise persistence failures are injected only for J07–J09.

J01–J10 cover qualified favorite/forward, `no_forward`, rejected, three technical failures, retry recovery, all three required persistence cut points, and exact Run-bound RuleSet authority. Existing focused tests and the complete tracked suite remain authoritative for Candidate continuation, BossOCR Legacy/Core, OCR R02–R07, Candidate switching, calibration, actions, mouse, batching, pause/stop, and cleanup.

The root README remains a separate Sol Ultra deliverable and is accepted only after Codex performs the Section 12 source-consistency review. Human Production Smoke remains Human-only. Any genuine runtime defect makes automated acceptance fail and requires a separate Human scope decision; R14 authorizes zero production runtime changes.

Current state: AM7-R14 TID v0.1 — Frozen.
