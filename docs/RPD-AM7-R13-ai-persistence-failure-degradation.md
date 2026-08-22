# Ocria Am7 — AM7-R13 AI Persistence & Runtime Failure Degradation

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R13
- Requirement Name: AI Persistence & Runtime Failure Degradation
- Document Type: Requirement / Product Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r13-ai-persistence-failure-degradation`
- Upstream Baseline: `4ba8fe402ce5c27831d6813373bc637dd594cf36`

## 2. Document Status

This document defines the Frozen product contract for AM7-R13. RPD v0.1 is the authoritative product-design baseline for subsequent TID and implementation work.

This RPD does not define the implementation-level schema, module layout, file paths, exception types, retry delay, or writer mechanics that belong to the TID.

## 3. Product Goal

AM7-R13 makes the accepted Candidate-level AI production chain operationally traceable and safely degradable when AI screening fails technically.

For every eligible finalized Candidate that enters formal AI screening, R13 must:

- execute a bounded maximum of three formal AI attempts;
- durably record each failed attempt before retry or final failure processing;
- durably record exactly one final AI outcome;
- durably record every normally produced `CandidateDecision` exactly once;
- preserve the strict distinction between AI technical failure and business false;
- continue normal Candidate processing after a final AI failure when all required persistence succeeds;
- safely terminate the Run when required R13 persistence integrity cannot be maintained.

The highest-level product rule is:

```text
AI failure is Candidate-level recoverable.
Persistence integrity failure is Run-level fatal.
```

## 4. Upstream Accepted Authority

R13 composes and does not redesign these accepted contracts:

- AM7-R03: the current Provider-neutral runtime, normalized `LLMRuntimeError`, selected `AIProviderConfig`, `timeout=120.0`, `max_retries=0`, and no Provider/model fallback;
- AM7-R05: immutable saved `ScreeningProfileVersion` and its Profile ID, version, and Criteria digest authority;
- AM7-R06: exact Boolean Rule evaluation and explicit validation/input failures;
- AM7-R07/R08: finalized Candidate evidence and Candidate-level production authority;
- AM7-R09: authoritative Candidate input projection and blank-text failure;
- AM7-R10: strict complete Boolean response contract;
- AM7-R11: unchanged public `run_ai_screening(candidate, profile, config) -> AIScreeningResult` API and exact three-field `AIScreeningResult`, with only `completed` or `failed`;
- AM7-R12: exact two-field `CandidateDecision`, qualified-only action authorization, zero R06/action for `ai_failed`, and common Candidate continuation.

The accepted upstream reports in the baseline confirm R11 automated AC-01–AC-42 and R12 automated AC-01–AC-24. R13 does not rerun or reopen those accepted requirements.

## 5. Current Production Chain and Targeted Repository Findings

The accepted production chain is:

```text
OcrScreenRecord
→ finalized CandidateOcrDocument
→ R09 AICandidateInput
→ R11 AI Screening Runtime
→ AIScreeningResult
→ R12 CandidateDecision
→ qualified-only existing action
→ existing Candidate continuation
```

Targeted inspection at the stated baseline found:

1. The observed branch is `am7-r13-ai-persistence-failure-degradation`, the observed HEAD is `4ba8fe402ce5c27831d6813373bc637dd594cf36`, and the working tree was clean before this RPD was created.
2. R11 returns immutable `AIScreeningResult(candidate_record_id, ai_status, criteria_results)`. `completed` carries the complete R10 mapping; `failed` carries `None`.
3. R11 converts three accepted failure seams to `failed/None`: R09 source-content `ValueError`, R03 `LLMRuntimeError`, and R10 `AIScreeningContractError`.
4. Each current R11 catch discards the exception object when constructing `AIScreeningResult`. Consequently failure stage, exception type, runtime classification, status code, request ID, and diagnostic message do not cross the public R11 result boundary.
5. The accepted `LLMRuntimeError` already exposes safe normalized facts where available: `code`, `provider`, `operation`, `status_code`, `request_id`, and a bounded normalized message. The original Provider-specific structured error code is not currently retained by that public error object.
6. R09 and R10 failures have distinct existing exception types and bounded local messages, but R11 currently does not expose them after normalization to the final failed result.
7. These facts support a small additive attempt-failure observation boundary while preserving the exact accepted public `run_ai_screening(candidate, profile, config) -> AIScreeningResult` API and the Frozen public `AIScreeningResult` shape. R13 requires neither an additional argument on that API nor error fields on that result.
8. R12 currently invokes R11 once inside `_process_finalized_candidate(...)`, immediately creates a Decision, logs it, and then enters qualified-only action dispatch. R13 must insert bounded attempts and required persistence before the existing Decision/action authorization points.
9. The current `JsonlOcrRecordStore` creates the existing Run identity as `ocr_record_store.run_id`, using the supplied ID or a generated UUID. `CandidateOcrBuilder` receives that exact Run ID, and finalized `CandidateOcrDocument.run_id` preserves it.
10. The current store creates one run-scoped directory under `data/ocr_runs`, writes an atomic `run.json` manifest, and appends compact UTF-8 JSON objects to `screens.jsonl`, `candidates.jsonl`, and `errors.jsonl`.
11. Existing OCR save operations are intentionally best-effort, return Boolean success, and can disable the OCR store only after a configured consecutive-failure limit. That behavior is not strong enough to satisfy R13's immediate Run-fatal persistence-integrity contract and must not silently define R13 semantics.
12. Existing `errors.jsonl` records OCR/storage failures under a restricted OCR-specific context. It is not an AI attempt-error product stream.
13. The existing Run manifest already holds `ScreeningProfileBinding(screening_profile_id, profile_version, criteria_digest)`. `simple_brush.run()` also retains the exact loaded `ScreeningProfileVersion` and one current complete `AIProviderConfig` in memory for the live Run.
14. The existing outer `simple_brush.run()` error boundary stops Candidate processing, performs existing cleanup, and projects `RunStatus.ERROR` for an exception. R13 can require persistence integrity failure to enter this boundary without inventing a new Run state machine.

These findings establish a feasible additive product boundary. Exact classes, minimum internal/private observation mechanics or separate R13-specific attempt helper/API mechanics, record types, file paths, and exception routing remain TID decisions.

## 6. R13 Product Scope

R13 owns only:

- repeated formal R11 invocation policy for one eligible Candidate;
- the exact three-attempt maximum and immediate stop-on-success rule;
- attempt-level technical-failure evidence persistence;
- one final AI outcome record per formally screened Candidate;
- one Decision record per normally produced R12 Decision;
- ordering of required persistence before retry, Decision, and action;
- Candidate-level continuation after fully persisted final AI failure;
- Run-level fatal handling when required R13 persistence fails;
- minimum trace linkage to the existing Run, Candidate, Profile, and configured Provider/model.

## 7. Explicit Non-Scope

R13 does not introduce or redesign:

- R09 Candidate input semantics;
- R10 Prompt or Boolean response semantics;
- R11 public inputs, public result fields, or completed/failed meanings;
- R12 Decision fields, statuses, Rule mapping, or action meanings;
- R06 Rule grammar, RuleSet ANY semantics, or error contract;
- ScreeningProfile persistence, authority, selection, or mutation;
- OCR evidence schema, Candidate schema, OCR Store factual authority, Complete Scan, Dynamic End, or Candidate finalization;
- Provider/model fallback or per-Provider retry policies;
- adaptive retry, retry-budget expansion, circuit breaker, cooldown, or consecutive-failure Run stop;
- action-result persistence or action audit;
- replay, cache, request/response/Decision hashes, migration, packaging, or release integration;
- database, remote sync, GUI, generic persistence, retry, degradation, event, or orchestration framework.

## 8. Core Product Invariants

1. Business false and technical failed are different product facts.
2. A complete all-false Criterion mapping remains `ai_status = completed`.
3. Technical failure is always `ai_status = failed` with `criteria_results = None`; it is never synthesized as Boolean data.
4. Each eligible Candidate receives at most three formal AI attempts total.
5. Every retry uses the same exact live-Run `AIProviderConfig`, Provider, model, Candidate, and Profile Version.
6. Every failed attempt must have one durable error record before another attempt or final failed outcome processing.
7. Every formally screened Candidate must have exactly one durable final AI outcome after its attempt sequence ends.
8. Every normally produced `CandidateDecision` must have exactly one durable Decision record before action authorization.
9. R13 uses the existing Run ID and exact Candidate ID; it creates no replacement identity.
10. AI final failure with successful persistence is recoverable and returns to existing Candidate continuation.
11. Any required R13 persistence failure is Run-fatal and authorizes no subsequent action or Candidate processing.
12. Existing action results remain outside Decision and persistence scope.

### 8.1 Meaning of “Durably Persisted”

Throughout R13, a required record is **durably persisted** when the R13 persistence boundary has synchronously completed and acknowledged that record write before control proceeds to the next permitted step.

This product contract does not require power-loss durability, `fsync`, transactional filesystem guarantees, or a new crash-consistency framework. Exact writer, flush, and close mechanics remain TID decisions. A required write that does not synchronously complete and acknowledge success is a persistence write failure and retains the frozen Run-level integrity semantics: zero subsequent action or Candidate processing and safe Run termination.

## 9. Technical Failure Domain

An R13 retryable technical-failed attempt is a formal R11 invocation that reaches one of the accepted R11 Candidate-associated failed-result boundaries:

- R09 Candidate input/projection failure already normalized by R11, including missing, empty, or whitespace-only authoritative Candidate document text;
- R03 `LLMRuntimeError`, including normalized authentication/authorization, network, timeout, rate-limit, quota/billing, invalid request, model unavailable, Provider server, malformed response, unsupported Provider, or unknown Provider-runtime failure;
- R10 `AIScreeningContractError`, including invalid JSON, duplicate JSON members, invalid structure/schema, missing/duplicate/unknown Criterion, invalid Boolean type, or another accepted response-contract violation.

All failures in this accepted domain use the same three-attempt policy. R13 does not add a business-failure category or an HTTP/provider-specific retry table.

Wrong public input types, invalid source identity, unexpected programming defects, violated invariants, unexpected Prompt exceptions, validator integration `TypeError`, plain unexpected runtime exceptions, and other failures intentionally excluded from R11 `failed` semantics are not converted into R13 retryable technical attempts. They retain their existing error propagation and Run failure behavior.

## 10. Bounded Retry Contract

The maximum formal AI screening attempts per eligible Candidate is exactly:

```text
3 attempts total
= 1 initial attempt + at most 2 retries
```

Frozen behavior:

- Attempt numbers are `1`, `2`, and `3` only.
- A completed, R10-valid R11 result immediately ends the attempt sequence.
- No confirmation, duplicate, or verifier call occurs after success.
- A failed Attempt 1 may proceed to Attempt 2 only after its error record is durably persisted.
- A failed Attempt 2 may proceed to Attempt 3 only after its error record is durably persisted.
- A failed Attempt 3 ends the attempt sequence after its error record is durably persisted.
- After three failed attempts, Attempt 3's failed result is selected as the one final failed AI outcome.
- Retry budget never grows dynamically and never becomes unlimited.

The precise retry wait or no-wait mechanism belongs to TID. R13 adds no exponential-backoff framework, adaptive budget, or code-specific schedule at product level.

## 11. Retry Success and Failure Semantics

Each attempt is one separate formal invocation of the unchanged accepted public `run_ai_screening(candidate, profile, config) -> AIScreeningResult` API. Each invocation returns its own `AIScreeningResult`, and R11 retains its own at-most-one Provider completion call per invocation.

- If any attempt returns `completed`, that exact result becomes the final AI outcome and no later attempt exists.
- If an attempt returns `failed`, its failure evidence must be persisted before retry or finalization.
- If all three attempts return `failed`, the third attempt's failed result is the final selected semantic AI result, with exact Candidate identity, `ai_status = failed`, and `criteria_results = None`.
- Exactly one final AI outcome record is persisted for the Candidate; the three per-attempt results do not create three final outcome records.
- R13 does not create provisional Decisions or actions between attempts.
- Failed earlier attempts remain durable when a later attempt succeeds.

## 12. Provider / Model Stability During Retry

All attempts for a Candidate use the same exact `AIProviderConfig` already bound to the current live Run by R12.

R13 must not:

- reload or edit configuration per attempt;
- switch between Qwen and DeepSeek;
- replace the configured model;
- infer a fallback model;
- change API key or base URL;
- create a Provider/model fallback chain.

Authentication, model-unavailable, quota, and other accepted technical failures are retried under the same bounded policy; they do not authorize configuration substitution.

## 13. Attempt-Level Failure Evidence

Each failed formal AI attempt must produce exactly one durable logical AI error record before any next attempt or final failed-outcome step.

Each logical record must be able to express at least:

- the existing Run identity;
- the exact `candidate_record_id`;
- the attempt number, from 1 through 3;
- the failure stage/category;
- the failure type;
- the occurrence time.

When the observed upstream boundary safely provides them, the record may also carry limited diagnostic facts such as:

- accepted Provider/runtime error classification;
- HTTP/status code;
- request ID or Provider error code;
- bounded diagnostic message.

R13 does not require Provider-specific body parsing or a general error taxonomy. It must never persist API keys, secret credentials, full Prompt/resume payloads, or raw Provider response merely to satisfy this error record.

The existing R11 public API `run_ai_screening(candidate, profile, config) -> AIScreeningResult` and the public `AIScreeningResult` shape remain valid, backward-compatible, and unchanged. R13 must not require an additional argument on that existing API and must not add error fields to `AIScreeningResult`. TID may select the minimum additive internal/private observation seam or a separate R13-specific attempt helper/API capable of preserving this evidence, without redesigning the overall R11 runtime.

## 14. Final AI Outcome Persistence

Every eligible Candidate that formally enters R13 AI screening must produce exactly one durable final AI outcome record after its attempt sequence ends, whether the final result is completed or failed.

The logical record must express at least:

- existing Run identity;
- exact `candidate_record_id`;
- final `ai_status`;
- `criteria_results`:
  - completed: the exact complete strict-Boolean mapping;
  - failed: `None`;
- total attempts used;
- trace references sufficient to identify the bound ScreeningProfile ID/version/digest and configured Provider/model.

The final record does not copy the entire ScreeningProfile, make Profile Criteria a second authority, change the R11 result, or persist an outcome per attempt.

## 15. CandidateDecision Persistence

Every normal R12 `CandidateDecision` that is successfully produced must be durably persisted exactly once before any action authorization.

The logical Decision record must express at least:

- existing Run identity;
- exact `candidate_record_id`;
- exact `decision_status`.

The status domain remains exactly:

- `qualified`;
- `rejected`;
- `ai_failed`.

Persistence adds no `persisted`, `persistence_failed`, `retrying`, `degraded`, `action_failed`, `unknown`, or other Candidate business status. If R06 fails and no Decision is produced under the accepted R12 contract, no Decision record is fabricated.

## 16. Identity / Traceability

R13 uses the current existing identity chain:

```text
JsonlOcrRecordStore.run_id
→ CandidateOcrBuilder.run_id
→ CandidateOcrDocument.run_id
```

For all three logical streams:

```text
R13 run identity = existing current Run identity
R13 candidate identity = exact existing candidate_record_id
```

R13 must not strip, normalize, hash into a replacement, regenerate, prefix, suffix, or otherwise substitute either identity. An implementation-level record ID may be discussed by TID if minimally necessary, but it cannot replace the primary Run/Candidate association or create an unrelated AI Run identity.

## 17. ScreeningProfile Authority Boundary

The existing R05 `ScreeningProfileVersion` and R12 Run-bound Profile remain the sole formal Profile authority.

R13 records may retain stable trace references already accepted by the Run binding:

- `screening_profile_id`;
- `profile_version`;
- `criteria_digest`.

R13 must not create a second editable `screening_profile.json`, second Profile store, independent Criteria snapshot authority, Profile mutation path, or replacement Profile lifecycle.

## 18. OCR Store Authority Boundary

The existing OCR Store remains the factual authority for OCR Screens and finalized Candidate evidence. R13 does not modify the meaning or schema of `OcrScreenRecord`, `CandidateOcrDocument`, `screens.jsonl`, or `candidates.jsonl`.

R13 freezes three independent logical streams:

1. Final AI Outcome Records;
2. AI Attempt Error Records;
3. Candidate Decision Records.

TID may reuse the current run-scoped directory and compact JSONL convention, or choose the smallest equivalent independent boundary, but it must preserve the exact existing Run identity and must not insert AI/Decision fields into OCR evidence records.

The current OCR Store's best-effort delayed-disable policy does not govern R13. A required R13 write failure has the immediate fatal semantics in Sections 22–23. This distinction does not redesign OCR Store behavior.

## 19. Required Persistence Ordering

Every required persistence step below must synchronously complete and acknowledge the record write under Section 8.1 before control proceeds.

### 19.1 Failed attempt

```text
formal AI attempt
→ accepted technical failure observed
→ persist exactly one attempt-level AI error record
→ if persistence succeeds:
     if attempt budget remains:
         optional retry wait
         next attempt
     else:
         finalize failed AI outcome
```

If the attempt-error record cannot be durably written:

```text
→ Persistence Integrity Failure
→ no retry
→ no final Candidate action
→ safe Run termination
```

### 19.2 Final outcome and Decision

```text
finalized eligible Candidate
→ bounded AI attempts
→ final AIScreeningResult
→ persist exactly one final AI outcome
→ R12 decide_candidate(...)
→ persist exactly one CandidateDecision
→ qualified only: existing action path
→ existing Candidate continuation
```

No successfully persisted final AI outcome means no R12 Decision or action. No successfully persisted Decision means no favorite or forward action.

## 20. Successful First-Attempt Flow

```text
Attempt 1 completed
→ no attempt-error record
→ persist one completed final AI outcome, attempts_used = 1
→ R12 Decision
→ persist one Decision
→ qualified only: existing action
→ existing continuation
```

There is no Attempt 2 or Attempt 3.

## 21. Successful Retry Flow

Example:

```text
Attempt 1 failed
→ persist Attempt 1 error
→ Attempt 2 completed
→ persist one completed final AI outcome, attempts_used = 2
→ R12 Decision
→ persist one Decision
→ qualified only: existing action
→ existing continuation
```

The earlier failed-attempt record remains durable. Attempt 3 does not occur.

## 22. Final AI-Failed Flow

```text
Attempt 1 failed → persist error 1
Attempt 2 failed → persist error 2
Attempt 3 failed → persist error 3
→ final AIScreeningResult(
     candidate_record_id = exact Candidate ID,
     ai_status = "failed",
     criteria_results = None,
  )
→ persist one final failed AI outcome, attempts_used = 3
→ R12 CandidateDecision(..., "ai_failed")
→ persist one ai_failed Decision
→ zero R06
→ zero favorite
→ zero forward
→ existing Candidate continuation
```

No all-false mapping, rejected Decision, Provider/model fallback, or fourth status is created.

## 23. Persistence Integrity Failure

Any required R13 persistence failure is a Run-level integrity failure, including at least:

- failure to durably write a failed-attempt error record;
- failure to durably write the final AI outcome;
- failure to durably write a produced CandidateDecision.

The required result is:

```text
Persistence Integrity Failure
→ no further action for the current Candidate
→ zero favorite
→ zero forward
→ no further Candidate processing
→ existing safe cleanup
→ terminate current Run as error/integrity failure
```

R13 must not log-only and continue, retry the AI after an error-record write failure, produce/authorize a Decision after final-outcome write failure, or act after Decision-record write failure.

## 24. Safe Run Termination

R13 does not create a new Run state machine. Persistence integrity failure must enter the existing safe Run termination and cleanup boundary.

Frozen product outcome:

- current Candidate receives no action after the failure;
- no later Candidate is processed;
- existing cleanup runs;
- the Run is not reported as successful completion;
- the Run terminates under the existing error/integrity-failure projection.

The exact exception class, stop reason, call site, and use of the existing `RunStatus.ERROR` projection belong to TID.

## 25. Action Authorization Ordering

No action is authorized during attempts or before required persistence.

The only action-authorizing order is:

```text
final attempt sequence ended
+ final AI outcome durably persisted
+ CandidateDecision produced
+ CandidateDecision durably persisted
+ decision_status == "qualified"
→ existing action_mode path may run
```

`no_forward_mode`, action prerequisites, action safety behavior, and existing favorite/forward mechanics remain authoritative after this R13 ordering requirement is satisfied.

Action success, false return, suppression, or failure does not alter the persisted CandidateDecision.

## 26. Candidate Continuation

When all required R13 persistence succeeds:

- completed + R06 true → persisted `qualified` → optional existing action → normal continuation;
- completed + R06 false → persisted `rejected` → zero action → normal continuation;
- three failed attempts → persisted failed outcome + persisted `ai_failed` → zero action → normal continuation.

AI technical failure itself never creates a Run stop threshold. Multiple consecutive `ai_failed` Candidates continue normally as long as required persistence remains intact.

Persistence integrity failure is the only new R13 Run-fatal condition and does not create a Candidate Decision status.

## 27. Cardinality Rules

For each Candidate that enters formal R13 screening and whose required persistence succeeds:

- AI attempt error records: exactly one per failed attempt;
- final AI outcome records: exactly one total;
- CandidateDecision records: exactly one total if a Decision is produced;
- actions: at most the existing qualified-authorized action attempt after persistence.

R13 must not:

- write a final outcome for each attempt;
- create a Decision for each attempt;
- duplicate the final outcome because retries occurred;
- duplicate a Decision because action execution returned false or failed;
- combine attempt errors and final outcomes into an ambiguous single cardinality.

## 28. Example Outcome Matrix

| Case | Attempt results | Error records | Final AI outcome | Decision record | Action / continuation |
|---|---|---:|---|---|---|
| A | completed | 0 | 1 completed, attempts 1 | 1 | qualified-only action; continue |
| B | failed, completed | 1 | 1 completed, attempts 2 | 1 | qualified-only action; continue |
| C | failed, failed, completed | 2 | 1 completed, attempts 3 | 1 | qualified-only action; continue |
| D | failed, failed, failed | 3 | 1 failed, attempts 3 | 1 ai_failed | zero action; continue |
| E | any required record write fails | only records confirmed durable before failure | no further required processing | none after failure point | zero subsequent action; terminate Run |

The completed cases may produce either qualified or rejected according to accepted R06/R12 semantics. The table does not reinterpret Boolean results.

## 29. Protected Existing Behavior

R13 preserves:

- R11's public `AIScreeningResult` shape and completed/failed semantics;
- R12's public `CandidateDecision` shape and exact three statuses;
- R06 evaluation, including no R06 call for final AI failure;
- R12 qualified-only action authorization and common continuation;
- `perform_favorite_action()`;
- `forward_one_candidate()`;
- `next_candidate()`;
- focus restoration, WindMouse, calibration, browser automation, waits, and action safety controls;
- Complete Scan, Candidate switching, Candidate finalization, and OCR evidence persistence semantics;
- Run-bound ScreeningProfile, RuleSet, and Provider configuration ownership.

R13 changes only repeated AI invocation policy, required durable record ordering, AI-failure continuation, and persistence-integrity Run termination.

## 30. R14 Boundary

R13 persistence provides traceable historical facts but does not implement AM7-R14.

Explicitly out of scope:

- AI, Decision, or retry replay;
- cache or historical lookup;
- duplicate suppression across Runs;
- request, response, RuleSet, Decision, or Candidate hashes/digests for replay;
- replay mapping or comparison;
- old-record or schema migration;
- persistence migration, packaging, release, or distribution integration.

R13 records are written for durability and traceability only; no runtime behavior reads them back under this requirement.

## 31. Product Acceptance Criteria

### AC-01 — Business false and technical failure remain distinct

A complete R10-valid mapping, including an all-false mapping, remains `ai_status = completed` and proceeds to R06. No R09/R03/R10 technical failure is converted to Boolean false or `rejected`.

### AC-02 — Exact technical-failure domain

Only accepted R11 Candidate-associated failures—R09 source-content failure, `LLMRuntimeError`, and `AIScreeningContractError`—enter the R13 bounded technical-failed attempt policy. Unexpected defects retain existing propagation rather than being normalized or retried. Exposing structured failure evidence preserves the unchanged public `run_ai_screening(candidate, profile, config) -> AIScreeningResult` API, requires no additional argument on it, and does not change `AIScreeningResult`.

### AC-03 — Exact maximum attempt count

Each eligible Candidate receives at most three formal R11 attempts total: one initial attempt and at most two retries. No fourth attempt or dynamic budget expansion is permitted.

### AC-04 — Immediate stop on completed result

The first completed valid R11 result ends retries immediately. No confirmation, verifier, or additional AI call occurs afterward.

### AC-05 — Three failures produce final failed outcome

Each formal R11 attempt has its own `AIScreeningResult`. After three accepted failed attempts, the third failed result is the final selected semantic AI result, with exact Candidate identity, `ai_status = failed`, and `criteria_results = None`; exactly one final AI outcome record is persisted for the Candidate.

### AC-06 — Stable Provider and model

Every attempt uses the same exact live-Run `AIProviderConfig`, Provider, model, Candidate, and Profile Version. No Provider/model/config fallback, reload, or substitution occurs.

### AC-07 — One durable error record per failed attempt

Every failed attempt produces exactly one attempt-error record whose write synchronously completes and is acknowledged under Section 8.1 before any retry or final failed-outcome processing; successful attempts produce none.

### AC-08 — Minimum attempt-error evidence

Each attempt-error record carries the existing Run identity, exact Candidate identity, attempt number, failure stage/category, failure type, and occurrence time, plus only bounded safe diagnostics already available at the observed boundary; no API key or credential is persisted.

### AC-09 — Attempt-error persistence failure is immediately fatal

If a required attempt-error record cannot be durably written, no retry, Decision, favorite, forward, or later Candidate processing occurs, and the current Run enters safe error termination.

### AC-10 — Exactly one final AI outcome

Every eligible Candidate that enters R13 formal screening and completes required persistence has exactly one final AI outcome record, regardless of whether one, two, or three attempts were used.

### AC-11 — Completed final outcome fidelity

A completed final outcome stores the exact complete strict-Boolean `criteria_results` mapping from the final completed R11 result without defaulting, omission, or reinterpretation.

### AC-12 — Failed final outcome fidelity

A failed final outcome stores exact `ai_status = failed`, `criteria_results = None`, and the actual total attempts used; it stores no empty or all-false substitute mapping.

### AC-13 — Final outcome trace linkage

The final AI outcome is linked through the existing Run ID and exact Candidate ID and contains sufficient references to the bound Profile ID/version/digest and configured Provider/model without storing a second authoritative Profile.

### AC-14 — Earlier failed attempts survive later success

When a later attempt completes, all earlier successfully persisted attempt-error records remain durable, while no unused later attempt is executed.

### AC-15 — Final outcome precedes Decision and action

The final AI outcome must be durably persisted before R12 Decision production. If it cannot be persisted, no Decision or action follows.

### AC-16 — Accepted R12 Decision mapping remains unchanged

After successful final-outcome persistence, completed results proceed through exact R06/R12 semantics to qualified or rejected, while a final failed result produces ai_failed with zero R06.

### AC-17 — Exactly one Decision record

Every normally produced `CandidateDecision` has exactly one durable Decision record containing the existing Run identity, exact Candidate identity, and exact qualified/rejected/ai_failed status. No per-attempt Decision exists.

### AC-18 — Decision persistence precedes action

No favorite or forward action is authorized before the produced CandidateDecision is durably persisted.

### AC-19 — Three failures produce persisted ai_failed and zero action

After three failed attempts and successful required persistence, R12 produces and R13 persists exactly one ai_failed Decision, calls R06 zero times, and authorizes zero favorite/forward actions.

### AC-20 — Final AI failure remains Candidate-recoverable

When the failed-attempt records, final failed outcome, and ai_failed Decision are all durably persisted, the Candidate returns to existing continuation and the next Candidate may be processed.

### AC-21 — No consecutive-AI-failure stop policy

Repeated or consecutive fully persisted ai_failed Candidates do not create an R13 counter, threshold, circuit breaker, cooldown, or Run stop.

### AC-22 — Final-outcome persistence failure is Run-fatal

Failure to durably persist the final AI outcome produces no Decision or action, processes no later Candidate, and enters existing safe Run error termination.

### AC-23 — Decision persistence failure is Run-fatal

Failure to durably persist a produced Decision authorizes zero action, processes no later Candidate, and enters existing safe Run error termination without adding a Candidate business status.

### AC-24 — Safe Run termination semantics

Any required R13 persistence integrity failure stops further Candidate processing, performs existing safe cleanup, and prevents the Run from being reported as normally completed, without introducing a new Run state machine.

### AC-25 — Exact existing identities

All R13 logical records reuse the current existing Run ID and exact `candidate_record_id`; neither is normalized, replaced, hashed into a substitute, regenerated, or associated through an unrelated AI Run ID.

### AC-26 — No second ScreeningProfile authority

R13 uses only stable references to the existing R05/R12 Profile authority and creates no second editable Profile snapshot, Profile store, or Profile lifecycle.

### AC-27 — OCR evidence authority remains unchanged

R13 logical persistence does not alter OCR/Candidate evidence schemas or factual authority and does not rely on the OCR Store's best-effort failure policy to weaken R13 integrity semantics.

### AC-28 — Exact record cardinality

For successful required persistence, a Candidate has one error record per failed attempt, exactly one final AI outcome, and exactly one Decision record when a Decision is produced; retries create no duplicate final outcome or Decision.

### AC-29 — No action-result persistence

R13 persists no favorite/forward success, failure, suppression, click history, or other action outcome, and action results cannot rewrite the persisted Decision.

### AC-30 — Existing action and continuation mechanics protected

R13 changes only pre-action authorization ordering. Existing favorite, forward, no-forward, next-Candidate, focus, calibration, switching, batch, stop, and cleanup mechanics remain authoritative.

### AC-31 — No R14 behavior

R13 adds no replay, cache, historical lookup, replay hash/digest, cross-Run deduplication, migration, packaging, or release behavior.

### AC-32 — No generic framework

R13 introduces no general persistence, retry, degradation, event, gate, guard, scanner, wrapper, or orchestration framework beyond the minimum requirement-specific boundaries.

Acceptance Criteria count: **32**.

## 32. Open Decisions

None.

Human has already fixed:

- maximum attempts: exactly three total;
- persistence integrity failure: safely terminate the current Run.

Physical record names/paths, exact schemas, retry delay, minimum internal/private error-observation or separate R13-specific attempt helper/API mechanics, writer implementation, and exact exception/call-site choices are TID decisions, not product Open Decisions.

## 33. Contract Conflicts

None.

The required attempt diagnostics are feasible through an additive internal/private seam or separate R13-specific attempt helper/API while retaining the exact accepted R11 `run_ai_screening(candidate, profile, config) -> AIScreeningResult` public API and Frozen result shape. The three R13 logical streams can reuse existing Run/Candidate references without modifying OCR evidence authority, ScreeningProfile authority, or the Frozen R12 Decision shape.

## 34. Human Review Required Items and Final Product Summary

Human Review Required Items: None.

AM7-R13 freezes a Candidate-level, three-attempt maximum around separate calls to the unchanged accepted R11 public API, with one `AIScreeningResult` per formal attempt. If all three attempts fail, Attempt 3's failed result is the final selected semantic AI result and exactly one final AI outcome record is persisted for the Candidate. Every failed attempt is durably recorded before retry; one final AI outcome is durably recorded before R12 Decision; and every normally produced Decision is durably recorded before qualified-only action authorization. Here, durable persistence means synchronous completion and acknowledgment by the R13 persistence boundary before control proceeds, without requiring power-loss durability, `fsync`, transactional filesystem guarantees, or a new crash-consistency framework. All retries use the same Run-bound Provider/model/configuration.

Completed Boolean data remains business data and proceeds through unchanged R06/R12 semantics. Three failed attempts produce failed/None, then a persisted ai_failed Decision, zero R06/action, and normal Candidate continuation when persistence succeeds. R13 introduces no consecutive-AI-failure stop policy.

Every R13 record reuses the existing Run ID and exact Candidate identity, with Profile and Provider/model references only. R13 creates no second Profile authority and does not alter OCR evidence schemas. Any required R13 persistence failure authorizes no subsequent action or Candidate processing and enters the existing safe Run error/cleanup boundary. Action outcomes and all R14 replay/cache/hash/migration behavior remain out of scope.

Current state: **AM7-R13 RPD v0.1 — Frozen / Ready for TID**.
