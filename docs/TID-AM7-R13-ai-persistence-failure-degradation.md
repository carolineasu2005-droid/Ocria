# Ocria Am7 — AM7-R13 AI Persistence & Runtime Failure Degradation

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R13
- Requirement Name: AI Persistence & Runtime Failure Degradation
- Document Type: Technical Implementation Design
- Version: 0.1
- Status: Frozen
- Governing Document: CODEX-CONSTITUTION.md
- Source RPD: docs/RPD-AM7-R13-ai-persistence-failure-degradation.md — v0.1 Frozen
- Requirement Branch: am7-r13-ai-persistence-failure-degradation
- Upstream Baseline: 4ba8fe402ce5c27831d6813373bc637dd594cf36

## 2. Document Status

This document defines the Frozen technical implementation contract for AM7-R13. TID v0.1 is the authoritative implementation baseline for AM7-R13.

The design changes no R13 product requirement, no accepted R03/R05/R06/R09/R10/R11/R12 contract, and no Acceptance Criterion.

## 3. Source Authority

Implementation authority, in order, is:

1. CODEX-CONSTITUTION.md;
2. docs/RPD-AM7-R13-ai-persistence-failure-degradation.md — v0.1 Frozen;
3. accepted R03, R05, R09, R10, R11, and R12 contracts and implementations at the stated baseline.

The observed Requirement branch is am7-r13-ai-persistence-failure-degradation and the observed HEAD is exactly 4ba8fe402ce5c27831d6813373bc637dd594cf36. The Frozen R13 RPD is the only pre-existing working-tree document and is not modified by this TID.

## 4. Targeted Inspection Scope

The inspection was limited to the following directly relevant authority and implementation surfaces:

- R03 RPD/TID, llm_provider_runtime.py, and AIProviderConfig public contract;
- R05 RPD/TID and screening_profile.py Profile Version/digest persistence;
- R09 RPD/TID and ai_candidate_input.py;
- R10 RPD/TID, ai_screening_prompt.py, and ai_screening_contract.py;
- R11 Frozen RPD/TID, Acceptance Report, ai_screening_runtime.py, and tests/test_ai_screening_runtime.py;
- R12 Frozen RPD/TID, Acceptance Report, candidate_decision.py, simple_brush.py, tests/test_candidate_decision.py, tests/test_candidate_decision_integration.py, and directly affected simple_brush test fixtures;
- ocr_store.py, ocr_records.py, ocr_candidate.py, and the relevant tests/test_ocr_store.py conventions.

No repository-wide audit, full regression, live Provider call, browser/action execution, packaging inspection, or dependency audit was performed.

## 5. Targeted Repository Findings

1. ai_screening_runtime.run_ai_screening(candidate, profile, config) has the exact accepted three-argument public signature and returns the exact frozen three-field AIScreeningResult.
2. The R11 implementation catches only the R09 source-content ValueError, LLMRuntimeError, and AIScreeningContractError boundaries. It returns failed/None for those failures and deliberately propagates wrong input types, source identity errors, Prompt defects, validator TypeError, plain RuntimeError, and other unexpected defects.
3. The caught exception is currently discarded at each accepted failed boundary. A shared private attempt result is therefore the smallest seam that preserves diagnostics without duplicating R11 logic or altering the public API.
4. LLMRuntimeError exposes normalized code, provider, operation, status_code, request_id, and its safe message. Provider-specific structured error code is not exposed by the accepted object and cannot be reconstructed by R13.
5. llm_provider_runtime._new_client() fixes timeout at 120.0 seconds and max_retries at 0. R13 must remain three separate Candidate-level R11 attempts rather than changing SDK retry behavior.
6. simple_brush.run() loads exactly one valid ScreeningProfileVersion and one complete AIProviderConfig before execution and retains both exact objects for all Candidate processing.
7. simple_brush._process_finalized_candidate() currently calls R11 once, calls decide_candidate(), logs the Decision, and authorizes the existing qualified-only favorite/forward branch. This is the narrow R13 integration point.
8. Both normal Candidate-finalization call sites pass the exact returned CandidateOcrDocument to _process_finalized_candidate(). Aborted/interrupted/recovery finalization does not enter that helper.
9. finalize_current_candidate_recording() clears current_candidate_builder before returning the finalized document. A later R13 exception therefore reaches cleanup with no active builder and cannot cause duplicate Candidate finalization.
10. JsonlOcrRecordStore exposes the current run_id and run_dir. CandidateOcrBuilder and CandidateOcrDocument retain that exact run_id chain.
11. The OCR run directory is unique per live Run and already contains run.json, screens.jsonl, candidates.jsonl, and errors.jsonl. Reusing run_dir avoids a second Run identity or unrelated AI directory.
12. ocr_records.json_dumps() provides the repository compact UTF-8 JSON convention and timezone_iso() provides timezone-aware ISO 8601 timestamps.
13. JsonlOcrRecordStore writes are intentionally best-effort Boolean operations with delayed disable. Those methods cannot implement R13 required-write semantics and will not be reused for R13 records.
14. The outer simple_brush.run() Candidate loop catches an escaping runtime exception, records its type, executes existing final cleanup, and closes the OCR Store with RunStatus.ERROR. An escaping R13 persistence exception therefore stops later Candidate processing without a new Run state.
15. No existing dependency or parser/storage framework is needed.

## 6. Chosen Technical Outcome

R13 uses three narrowly scoped implementation changes:

1. ai_screening_runtime.py gains a shared private single-attempt function and private immutable diagnostic value types. Existing run_ai_screening() delegates to it and still returns only AIScreeningResult.
2. A new ai_screening_persistence.py owns the three exact R13 record types, three run-scoped JSONL streams, and the synchronous raise-on-failure writer.
3. simple_brush.py owns one private R13 attempt loop and the exact final-outcome → Decision → action ordering. One AIScreeningRecordStore is constructed per live Run and passed explicitly; no global store lookup or generic pipeline is added.

Retry has zero additional delay when the Run is active. Existing stop_event and paused state are observed only at formal attempt boundaries.

## 7. Exact File Plan

### 7.1 New implementation files

| File | Exact purpose |
|---|---|
| ai_screening_persistence.py | R13-only record values, exact JSONL writer, filenames, and persistence integrity exception |
| tests/test_ai_screening_persistence.py | Exact record-schema and writer tests |

### 7.2 Modified implementation/test files

| File | Exact authorized change |
|---|---|
| ai_screening_runtime.py | Add the private shared attempt seam and diagnostic values; preserve the public API/result |
| simple_brush.py | Initialize one R13 store, perform the three-attempt loop, enforce persistence ordering, and pass the store explicitly |
| tests/test_ai_screening_runtime.py | Add private-seam diagnostics and exact public-compatibility tests; retain accepted public behavior tests |
| tests/test_candidate_decision_integration.py | Replace the single-call fixture with R13 retry, ordering, cardinality, stop, continuation, and failure cases |
| tests/test_simple_brush_ocr.py | Minimally align Run setup fixtures and verify R13 initialization/runtime persistence failure reaches existing Run cleanup |

### 7.3 Protected / untouched files and regions

- docs/RPD-AM7-R13-ai-persistence-failure-degradation.md;
- candidate_decision.py and tests/test_candidate_decision.py;
- llm_provider_runtime.py, ai_provider_config.py, ai_candidate_input.py, ai_screening_prompt.py, and ai_screening_contract.py;
- screening_profile.py and screening_rule_engine.py;
- ocr_store.py, ocr_records.py, ocr_candidate.py, OCR detector/browser modules, and their schemas;
- bodies of perform_favorite_action(), forward_one_candidate(), next_candidate(), Candidate switching/finalization, focus restore, calibration, mouse/WindMouse, and scan lifecycle functions;
- requirements and packaging files.

The only file created in this design turn is this TID.

## 8. Dependency Direction

The exact dependency direction is:

~~~text
simple_brush.py
  -> ai_screening_runtime._run_ai_screening_attempt
  -> ai_screening_persistence
  -> candidate_decision.decide_candidate

ai_screening_runtime.py
  -> existing R09 / R10 / R03 modules

ai_screening_persistence.py
  -> standard library
  -> ocr_records.json_dumps / timezone validation helpers
~~~

ai_screening_runtime.py does not import persistence or simple_brush. ai_screening_persistence.py does not import simple_brush, Provider clients, Rule evaluation, OCR Store, or action modules. No circular dependency or new external dependency is introduced.

## 9. R11 Public Compatibility Boundary

The following accepted API remains byte-for-byte equivalent in name, parameter order, requiredness, annotations, and return type:

~~~python
def run_ai_screening(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> AIScreeningResult:
    ...
~~~

It receives no fourth required or optional parameter, no callback, and no persistence object. AIScreeningResult remains a frozen dataclass with exactly:

~~~python
candidate_record_id: str
ai_status: Literal["completed", "failed"]
criteria_results: dict[str, bool] | None
~~~

run_ai_screening() delegates to the private attempt seam and returns only outcome.result. Existing callers and tests therefore remain backward-compatible.

## 10. Failure Observation Seam

ai_screening_runtime.py adds:

~~~python
def _run_ai_screening_attempt(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> _AIScreeningAttemptOutcome:
    ...
~~~

This private function contains the current R11 validation, R09 projection, Prompt construction, request construction, one complete() call, R10 validation, and result construction. No R11 logic is duplicated.

run_ai_screening() becomes exactly the compatibility projection:

~~~python
return _run_ai_screening_attempt(candidate, profile, config).result
~~~

Only simple_brush.py's R13 private orchestration imports this private seam. There is no callback registry, event bus, observer, ContextVar, thread-local diagnostic channel, global last-error state, or changed public result.

## 11. Failure Observation Type and Exact Mapping

ai_screening_runtime.py adds two private frozen dataclasses:

~~~python
@dataclass(frozen=True)
class _AIScreeningAttemptFailure:
    failure_stage: Literal[
        "candidate_input",
        "provider_runtime",
        "response_contract",
    ]
    failure_type: str
    error_code: str | None
    provider: str | None
    operation: str | None
    status_code: int | None
    request_id: str | None
    message: str | None

@dataclass(frozen=True)
class _AIScreeningAttemptOutcome:
    result: AIScreeningResult
    failure: _AIScreeningAttemptFailure | None
~~~

R13_DIAGNOSTIC_MESSAGE_MAX_CHARS is exactly 512. _bounded_failure_message(exception) returns None for an empty string and otherwise the first 512 Python characters of str(exception). It does not include repr(exception), traceback, chained exception data, request payload, Prompt, resume text, API key, or raw Provider response.

The exact mapping is:

| Accepted boundary | failure_stage | failure_type | Diagnostics |
|---|---|---|---|
| R09 source-content ValueError | candidate_input | ValueError | message only; all other optional fields None |
| LLMRuntimeError | provider_runtime | LLMRuntimeError | error_code = exception.code.value; provider = exception.provider; operation = exception.operation.value; status_code and request_id copied exactly; bounded message |
| AIScreeningContractError | response_contract | AIScreeningContractError | message only; all other optional fields None |
| completed R11 path | not applicable | not applicable | failure is None |

The accepted LLMRuntimeError does not expose the Provider-specific structured body code. R13 records no invented provider error code and performs no Provider-body parsing.

_AIScreeningAttemptOutcome validates only the relationship needed by the private seam: completed requires failure is None; failed requires one _AIScreeningAttemptFailure. It does not alter AIScreeningResult construction.

## 12. Unexpected Exception Boundary

The private attempt seam preserves the current catch placement:

- only build_ai_candidate_input(candidate) is covered by except ValueError;
- only complete(config, request) is covered by except LLMRuntimeError;
- only validate_ai_screening_response(...) is covered by except AIScreeningContractError.

The following continue to propagate unchanged and do not produce a retryable attempt outcome:

- wrong Candidate, Profile, or Config type;
- non-string source Candidate identity;
- R09 top-level TypeError;
- Prompt construction exception;
- request construction/programming defect;
- plain RuntimeError from the Provider integration;
- validator TypeError;
- any arbitrary unexpected exception.

Neither _run_ai_screening_attempt() nor R13 orchestration catches Exception or BaseException. Unexpected defects reach the existing outer Run error boundary and are never normalized to failed, false, rejected, or ai_failed.

## 13. R13 Attempt Orchestration API

simple_brush.py adds:

~~~python
R13_MAX_AI_SCREENING_ATTEMPTS = 3

def _run_r13_ai_screening(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
    store: AIScreeningRecordStore,
) -> AIScreeningResult | None:
    ...
~~~

The return is:

- the final selected AIScreeningResult only after its one final AI outcome record has been synchronously acknowledged;
- None only when the existing stop_event prevents the first or a later retry attempt before the three-attempt sequence completes.

None is an interruption projection, not a failed AI result and not a CandidateDecision.

_process_finalized_candidate() changes only its private integration signature:

~~~python
def _process_finalized_candidate(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
    rule_set: ScreeningRuleSet,
    store: AIScreeningRecordStore,
) -> CandidateDecision | None:
    ...
~~~

Both successful Candidate-finalization call sites pass the one exact Run-local store explicitly. No per-Candidate construction and no hidden global store lookup is permitted.

## 14. Retry Contract

R13_MAX_AI_SCREENING_ATTEMPTS is a non-configurable constant equal to 3. The loop uses attempt numbers 1, 2, and 3 only.

For every call, the loop passes the same object identities candidate, profile, and config to _run_ai_screening_attempt(). It does not reload configuration, rebuild Candidate evidence, copy or reload the Profile, change Provider/model, or create a fallback.

The first completed outcome ends the loop immediately. A failed outcome is followed by exactly one acknowledged attempt-error write. A next attempt is possible only after that write succeeds. Attempt 3's failed AIScreeningResult is selected as the final semantic result after its error record succeeds.

R03 remains unchanged:

~~~text
OpenAI SDK max_retries = 0
R13 formal Candidate-level R11 attempts = at most 3 separate calls
~~~

No fourth attempt, dynamic budget, Provider-specific count, confirmation call, verifier call, or persistence-write retry exists.

## 15. Retry Wait, Stop, and Pause Behavior

There is zero additional retry delay while the Run is active and unpaused. R13 calls neither safe_wait() nor sleep merely to delay a retry, and it adds no backoff, jitter, status-code table, or cooldown.

Before Attempt 1 and before each permitted retry, _run_r13_ai_screening() consumes only the existing simple_brush module state:

~~~python
if stop_event:
    return None
while paused and not stop_event:
    time.sleep(0.2)
if stop_event:
    return None
~~~

The 0.2-second sleep is only the existing pause polling convention; it is not retry delay. R13 creates no new stop controller or state.

If stop_event becomes true during a failed Attempt 1 or 2, that genuine failed attempt's error record is written first, then the next-attempt gate returns None. No final AI outcome, Decision, action, or synthetic ai_failed value is created for the interrupted sequence.

If a completed result or Attempt 3 result has already completed the formal sequence, its final outcome is persisted. _process_finalized_candidate() then checks stop_event before decide_candidate(); a stop therefore authorizes no new Decision or action. A stop during or after Decision persistence is still checked before the action branch.

## 16. Run-Bound Identity and Store Binding

After initialize_run_ocr_storage(screening_profile_binding) returns one enabled JsonlOcrRecordStore and before initialize_ocr(), listener startup, browser focus, or Candidate processing, run() constructs:

~~~python
r13_store = AIScreeningRecordStore(
    run_dir=initial_store.run_dir,
    run_id=initial_store.run_id,
)
~~~

This is exactly one R13 store per live Run. It remains a local run() object and is passed through both Candidate call sites.

Before Attempt 1, _run_r13_ai_screening() requires:

~~~text
candidate.run_id == store.run_id
candidate.candidate_record_id is used exactly
~~~

A mismatch raises ValueError as an invariant/programming failure and reaches the existing Run error boundary. R13 generates no ai_run_id, screening_run_id, replacement Candidate ID, record ID, prefix, suffix, or hash identity.

## 17. Persistence Home and Physical Streams

R13 uses initial_store.run_dir as its only physical home. It does not modify run.json or the OCR data_files mapping and does not insert AI fields into OCR records.

The exact three filenames are:

~~~text
ai_results.jsonl
ai_errors.jsonl
decisions.jsonl
~~~

There is no actions.jsonl, retry_state.json, cache, replay stream, second manifest, or separate AI directory.

## 18. Persistence Writer Contract

ai_screening_persistence.py defines:

~~~python
class AIScreeningRecordStore:
    def __init__(self, run_dir: Path, run_id: str) -> None: ...
    def append_ai_error(self, record: AIAttemptErrorRecord) -> None: ...
    def append_ai_result(self, record: AIFinalOutcomeRecord) -> None: ...
    def append_decision(self, record: CandidateDecisionRecord) -> None: ...
~~~

Constructor behavior:

1. require run_id to be a non-empty string;
2. require run_dir to be an existing directory;
3. establish exact Path objects for the three filenames;
4. create each file with mode x, encoding utf-8, and newline="";
5. close each successful creation before returning.

If initialization partially creates files and a later creation fails, it does not roll them back. No AI attempt or action has started; setup fails safely and the existing OCR Run closes as ERROR.

Each append method:

1. requires the exact corresponding frozen record type;
2. requires record.run_id == store.run_id;
3. serializes with ocr_records.json_dumps(), preserving dataclass field order;
4. opens the one stream with mode a, encoding utf-8, and newline="";
5. writes serialized + "\n";
6. calls flush();
7. exits the context manager so close completes;
8. returns None only after those synchronous steps succeed.

The implementation uses no fsync, power-loss guarantee, transaction, file lock, background queue, delayed disable, Boolean result, write retry, readback, or generic storage abstraction. JSON member order is deterministic by the frozen dataclass field order, but JSON object order is not a product identity.

## 19. Persistence Integrity Exception

ai_screening_persistence.py defines:

~~~python
class AIPersistenceIntegrityError(RuntimeError):
    operation: Literal[
        "initialize",
        "write_ai_error",
        "write_ai_result",
        "write_decision",
    ]
    path: Path

    def __init__(self, operation: str, path: Path) -> None:
        ...
~~~

Its safe message is exactly:

~~~text
R13 persistence integrity failure during <operation>
~~~

Initialization and append OSError values, including open, write, flush, and close failures, are wrapped with this exception and chained as the cause. The exception does not include record data, API key, Prompt, resume text, or raw Provider response.

Wrong record type raises TypeError and record/store identity mismatch raises ValueError before I/O. Those are programming/invariant failures, remain non-retryable, and still reach the existing Run error boundary. There is no local catch-and-continue for any required write.

Setup handles AIPersistenceIntegrityError only to log its safe operation, close the already-created OCR Store with RunStatus.ERROR, and return 2 before OCR/listener/browser/AI/action startup. Runtime append errors are not caught by either private R13 helper; they escape to the existing outer Candidate-loop exception boundary.

## 20. AI Attempt Error Record Schema

ai_screening_persistence.py defines the exact frozen dataclass and JSON member order:

~~~python
@dataclass(frozen=True)
class AIAttemptErrorRecord:
    run_id: str
    candidate_record_id: str
    attempt_number: int
    failure_stage: Literal[
        "candidate_input",
        "provider_runtime",
        "response_contract",
    ]
    failure_type: str
    occurred_at: str
    error_code: str | None
    provider: str | None
    operation: str | None
    status_code: int | None
    request_id: str | None
    message: str | None
~~~

Validation is exact:

- run_id, candidate_record_id, and failure_type are non-empty strings;
- attempt_number is a non-bool integer from 1 through 3;
- failure_stage is one of the three exact values;
- occurred_at passes ocr_records.validate_timezone_iso();
- status_code is None or a positive non-bool integer;
- every other optional value is None or a non-empty string;
- message is at most 512 characters.

All twelve members are always serialized. Unavailable diagnostics are JSON null. No unknown member can enter because the store accepts only the exact dataclass type.

occurred_at is generated with timezone_iso() immediately after the failed attempt and before append_ai_error(). The record contains no Provider body code unavailable from LLMRuntimeError, secret, Prompt, resume text, raw response, traceback, or action fact.

## 21. Final AI Outcome Record Schema

ai_screening_persistence.py defines the exact frozen dataclass and JSON member order:

~~~python
@dataclass(frozen=True)
class AIFinalOutcomeRecord:
    run_id: str
    candidate_record_id: str
    ai_status: Literal["completed", "failed"]
    criteria_results: dict[str, bool] | None
    attempts_used: int
    screening_profile_id: str
    profile_version: int
    criteria_digest: str
    provider: str
    model: str
~~~

Validation is exact:

- all identity/trace string fields are non-empty strings;
- attempts_used is a non-bool integer from 1 through 3;
- profile_version is a positive non-bool integer;
- completed requires a non-empty dict whose keys have exact str type and values have exact bool type;
- failed requires criteria_results is None;
- no other status or field exists.

The completed mapping is the exact final AIScreeningResult mapping serialized without omission, defaulting, coercion, all-false substitution, or Profile reconstruction. The failed record contains JSON null. The record has no occurrence timestamp because the Frozen minimum does not require one.

The record excludes the full Profile, Criteria, RuleSet, Prompt, resume text, raw response, API key, base_url, usage, action result, hash, retry history, and replay state.

## 22. CandidateDecision Record Schema

ai_screening_persistence.py defines the exact frozen dataclass and JSON member order:

~~~python
@dataclass(frozen=True)
class CandidateDecisionRecord:
    run_id: str
    candidate_record_id: str
    decision_status: Literal["qualified", "rejected", "ai_failed"]
~~~

Both identities must be non-empty strings and decision_status must be one of the exact accepted R12 values. There is no reason, evidence, confidence, time, action mode, no-forward state, action result, retry state, persistence state, or fourth Decision status.

## 23. Traceability Sources

The exact record sources are:

| Record member | Authoritative source |
|---|---|
| run_id | AIScreeningRecordStore.run_id, initialized from initial_store.run_id |
| candidate_record_id | candidate.candidate_record_id and the selected AIScreeningResult/CandidateDecision identity |
| attempt_number | the local range(1, 4) loop value |
| occurred_at | timezone_iso() at accepted failure observation |
| ai_status / criteria_results | the final selected AIScreeningResult |
| attempts_used | the selected loop attempt number |
| decision_status | the exact CandidateDecision returned by decide_candidate() |

Before record construction:

- candidate.run_id must equal store.run_id;
- every selected AIScreeningResult.candidate_record_id must equal candidate.candidate_record_id;
- CandidateDecision.candidate_record_id must equal the same Candidate identity.

Any mismatch is an invariant ValueError, not normalized AI failure. No new identity is generated.

## 24. Profile and Provider Trace

The final outcome uses only:

~~~text
screening_profile_id = profile.screening_profile_id
profile_version      = profile.profile_version
criteria_digest      = profile.criteria_digest
provider             = config.provider
model                = config.model
~~~

The exact profile and config objects are the already loaded Run-bound objects passed to every attempt. R13 does not recompute criteria_digest, serialize Criteria/Profile, reload configuration, persist base_url, or include api_key.

## 25. Exact Attempt Flow

The implementation follows this exact pseudocode:

~~~python
def _run_r13_ai_screening(candidate, profile, config, store):
    require candidate.run_id == store.run_id

    for attempt_number in range(1, R13_MAX_AI_SCREENING_ATTEMPTS + 1):
        if stop_event:
            return None
        while paused and not stop_event:
            time.sleep(0.2)
        if stop_event:
            return None

        outcome = _run_ai_screening_attempt(candidate, profile, config)

        if outcome.result.ai_status == "completed":
            final_result = outcome.result
            attempts_used = attempt_number
            break

        store.append_ai_error(
            AIAttemptErrorRecord(
                run_id=store.run_id,
                candidate_record_id=candidate.candidate_record_id,
                attempt_number=attempt_number,
                failure_stage=outcome.failure.failure_stage,
                failure_type=outcome.failure.failure_type,
                occurred_at=timezone_iso(),
                error_code=outcome.failure.error_code,
                provider=outcome.failure.provider,
                operation=outcome.failure.operation,
                status_code=outcome.failure.status_code,
                request_id=outcome.failure.request_id,
                message=outcome.failure.message,
            )
        )

        if attempt_number == R13_MAX_AI_SCREENING_ATTEMPTS:
            final_result = outcome.result
            attempts_used = attempt_number
            break

    store.append_ai_result(
        AIFinalOutcomeRecord(
            run_id=store.run_id,
            candidate_record_id=candidate.candidate_record_id,
            ai_status=final_result.ai_status,
            criteria_results=final_result.criteria_results,
            attempts_used=attempts_used,
            screening_profile_id=profile.screening_profile_id,
            profile_version=profile.profile_version,
            criteria_digest=profile.criteria_digest,
            provider=config.provider,
            model=config.model,
        )
    )
    return final_result
~~~

No separate attempt ledger, retry state file, mutable outcome accumulator, or read path exists.

## 26. Final Outcome Before Decision

_process_finalized_candidate() performs:

~~~python
ai_result = _run_r13_ai_screening(
    candidate,
    profile,
    config,
    store,
)
if ai_result is None or stop_event:
    return None

decision = decide_candidate(ai_result, rule_set)
~~~

Because _run_r13_ai_screening() returns only after append_ai_result() succeeds, the final AI outcome is acknowledged before decide_candidate() and before any R06 call.

If final completed or failed outcome persistence raises AIPersistenceIntegrityError, decide_candidate(), R06, Decision persistence, logging as a produced Decision, and action are all skipped.

## 27. Decision Before Action

After decide_candidate() succeeds:

~~~python
store.append_decision(
    CandidateDecisionRecord(
        run_id=store.run_id,
        candidate_record_id=decision.candidate_record_id,
        decision_status=decision.decision_status,
    )
)
logger.info(existing minimum Candidate Decision event)

if stop_event:
    return decision

if decision.decision_status == "qualified":
    existing favorite/forward/no-forward branch
else:
    existing forward_consecutive reset
return decision
~~~

The one Decision write is acknowledged before any favorite/forward authorization. A false action return, no-forward suppression, or action exception cannot rewrite or duplicate the Decision record. No action outcome is persisted.

## 28. Persistence Failure Propagation

### 28.1 Setup failure

AIScreeningRecordStore initialization occurs immediately after the enabled OCR Store establishes run_dir/run_id. AIPersistenceIntegrityError is caught at that setup call only:

~~~text
log fixed safe operation
→ close_run_ocr_storage(RunStatus.ERROR)
→ return 2
~~~

initialize_ocr(), listener.start(), browser focus, Candidate AI, Decision, and action are not called.

### 28.2 Runtime write failure

The exact call path is:

~~~text
AIScreeningRecordStore append
→ AIPersistenceIntegrityError
→ _run_r13_ai_screening or _process_finalized_candidate
→ existing outer simple_brush.run() Candidate-loop except Exception
→ run_exception_type set
→ existing finally cleanup
→ RunStatus.ERROR
→ OCR Store close
→ no later Candidate
~~~

No R13 helper catches, converts, retries, suppresses, or logs-and-continues a runtime required-write failure.

The Candidate has already been finalized and finalize_current_candidate_recording() already cleared current_candidate_builder. Existing finalize_active_candidate_for_stop() therefore performs no duplicate Candidate finalization. R13 performs no rollback or duplicate persistence.

## 29. R06 Failure After Final Outcome Persistence

For a completed AI result:

~~~text
final AI outcome acknowledged
→ decide_candidate()
→ evaluate_rule_set() raises accepted R06 validation/input error
→ no CandidateDecision exists
→ no Decision record
→ no action
→ existing outer Run error boundary
~~~

The already acknowledged final AI outcome remains in ai_results.jsonl. It is not deleted, rewritten, or rolled back. R13 adds no transaction framework and fabricates no Decision.

## 30. Final AI-Failed Flow

The exact all-failed flow is:

~~~text
Attempt 1 failed
→ ai_errors line 1 acknowledged
→ Attempt 2 failed
→ ai_errors line 2 acknowledged
→ Attempt 3 failed
→ ai_errors line 3 acknowledged
→ select Attempt 3 AIScreeningResult
→ one ai_results line:
     ai_status = failed
     criteria_results = null
     attempts_used = 3
→ decide_candidate()
→ ai_failed
→ one decisions line acknowledged
→ zero R06
→ zero favorite/forward
→ existing Candidate continuation
~~~

There is no fourth attempt, all-false substitute, rejected substitute, Provider/model fallback, or consecutive-failure stop.

## 31. Candidate Continuation and Retry-Success Flows

When all required persistence succeeds:

| Flow | Attempts | Error lines | Final outcome | Decision | Continuation |
|---|---:|---:|---|---|---|
| A | completed | 0 | one completed, attempts_used 1 | one qualified/rejected | existing continuation |
| B | failed, completed | 1 | one completed, attempts_used 2 | one qualified/rejected | existing continuation |
| C | failed, failed, completed | 2 | one completed, attempts_used 3 | one qualified/rejected | existing continuation |
| D | failed, failed, failed | 3 | one failed/null, attempts_used 3 | one ai_failed | existing continuation |

Earlier error lines remain. No unused attempt runs. Exactly one final outcome and one normally produced Decision are written.

Repeated fully persisted ai_failed Candidates use the same existing continuation. R13 adds no consecutive_ai_failures variable, threshold, health flag, circuit breaker, cooldown, or Run stop.

## 32. Protected Existing Behavior

The implementation may change only imports, Run-local R13 setup/passing, _process_finalized_candidate() ordering, and its two successful-finalization call sites in simple_brush.py.

It must not change:

- perform_favorite_action(), forward_one_candidate(), next_candidate(), or their prerequisites;
- no_forward_mode behavior or action_mode meanings;
- Complete Scan, OCR capture, Candidate finalization, switch preparation/confirmation, batch continuation, refresh, stop reason, focus, calibration, mouse, or WindMouse behavior;
- candidate_decision.py or R06 evaluation;
- ScreeningProfile/AIProvider configuration load semantics;
- OCR Store schemas, best-effort behavior, manifest, or existing streams.

Changed-file and focused diff review, rather than a new scanner or source guard, proves this boundary.

## 33. R14 Boundary

AIScreeningRecordStore exposes write methods only. It has no open/read/list/load/query/replay/cache/deduplicate/hash/migrate API.

R13 never reads ai_results.jsonl, ai_errors.jsonl, or decisions.jsonl at runtime and never uses historical state to skip an AI call or replay a Decision. It creates no request/result/Decision/Candidate hash, migration, cross-Run lookup, packaging, or release behavior.

## 34. Implementation Change Plan

### Change 1 — Shared R11 private attempt seam

Files:

- Modified: ai_screening_runtime.py
- Modified: tests/test_ai_screening_runtime.py

Responsibilities:

- add the two private frozen attempt types and the exact 512-character message bound;
- move the current one-invocation body into _run_ai_screening_attempt();
- map only the three accepted exceptions;
- make existing run_ai_screening() return the private outcome's AIScreeningResult;
- prove exact public signature, result fields, completed/failed behavior, and unexpected propagation.

Verification: targeted R11 runtime unit module and compileall for the changed source/test.

### Change 2 — R13 record and writer boundary

Files:

- New: ai_screening_persistence.py
- New: tests/test_ai_screening_persistence.py

Responsibilities:

- define the exact three frozen record types and validations;
- define AIPersistenceIntegrityError;
- create the exact three run-scoped files;
- implement synchronous compact UTF-8 append/flush/close behavior;
- prove exact schemas, null behavior, cardinality primitives, failure behavior, and no read API.

Verification: the new persistence unit module and compileall.

### Change 3 — R13 orchestration and production ordering

Files:

- Modified: simple_brush.py
- Modified: tests/test_candidate_decision_integration.py
- Modified: tests/test_simple_brush_ocr.py

Responsibilities:

- construct one Run-local AIScreeningRecordStore after OCR Run identity exists;
- implement _run_r13_ai_screening() with exactly three attempts and zero active retry delay;
- pass the same Candidate/Profile/Config objects and explicit store;
- persist failed attempt before retry, final outcome before Decision, and Decision before action;
- preserve R06 error semantics, ai_failed continuation, action bodies, and outer Run error cleanup;
- align only directly affected Run fixtures/tests.

Verification: focused Candidate Decision integration, pure protected Candidate Decision regression, simple_brush focused module, compileall, and targeted diff review.

Implementation Changes count: **3**.

## 35. Focused Test Plan

All tests use unittest and unittest.mock. They perform no real Provider call, network request, browser interaction, mouse action, favorite, forwarding, or email operation.

### 35.1 Technical Responsibility Matrix

| ID | Exact technical responsibility | Product AC / invariant |
|---|---|---|
| R01 | Existing run_ai_screening signature and exact three AIScreeningResult fields remain unchanged; no callback/extra argument | AC-02 |
| R02 | Public completed, all-false, and accepted failed/None projections remain unchanged | AC-01, AC-02 |
| R03 | Private seam maps only R09 ValueError to candidate_input diagnostics | AC-02, AC-08 |
| R04 | Private seam copies exact available LLMRuntimeError diagnostics and no secret/raw body | AC-02, AC-08 |
| R05 | Private seam maps only AIScreeningContractError to response_contract diagnostics | AC-02, AC-08 |
| R06 | Wrong inputs, Prompt/runtime defects, and validator TypeError propagate without retry normalization | AC-02 |
| R07 | One Candidate receives at most Attempts 1–3 and never Attempt 4 | AC-03 |
| R08 | Attempt 1 completed ends calls immediately | AC-04 |
| R09 | failed/completed uses two calls, one error record, and no Attempt 3 | AC-07, AC-14 |
| R10 | failed/failed/completed uses three calls and two retained error records | AC-07, AC-14 |
| R11 | three failures select Attempt 3 result and create one failed/null final outcome | AC-05, AC-12 |
| R12 | Every attempt reuses exact Candidate/Profile/Config identity and configured Provider/model | AC-06, AC-25 |
| R13 | Existing stop/pause state gates attempts without synthetic failed result, Decision, or action | AC-20, AC-24, AC-30 |
| R14 | AIAttemptErrorRecord exact twelve-field schema, timestamp, nullable diagnostics, and validation | AC-07, AC-08 |
| R15 | Completed AIFinalOutcomeRecord preserves the complete strict mapping and exact trace | AC-10, AC-11, AC-13 |
| R16 | Failed AIFinalOutcomeRecord stores null and actual attempts_used | AC-10, AC-12, AC-13 |
| R17 | CandidateDecisionRecord has exactly three fields and exact R12 status domain | AC-17 |
| R18 | Store initializes exactly three files in the existing run_dir and exposes no read/action stream | AC-27, AC-31 |
| R19 | Append writes one compact UTF-8 line and returns only after flush/close | AC-07, AC-15, AC-18 |
| R20 | Initialization/write OSError raises exact AIPersistenceIntegrityError with no write retry | AC-09, AC-22, AC-23, AC-24 |
| R21 | A failed-attempt record is acknowledged before the next attempt | AC-07 |
| R22 | Attempt-error write failure blocks retry, final outcome, Decision, action, and continuation | AC-09 |
| R23 | One final outcome is acknowledged before decide_candidate()/R06 | AC-15 |
| R24 | Completed or failed final-outcome write failure blocks Decision and action | AC-22 |
| R25 | One Decision record is acknowledged before qualified action | AC-18 |
| R26 | Decision write failure leaves the in-memory Decision unauthorized and blocks action/continuation | AC-23 |
| R27 | R06 failure after final-outcome persistence leaves that outcome, creates no Decision record, and performs no action | AC-15, AC-16 |
| R28 | Three failures create persisted ai_failed, zero R06/action, and normal continuation | AC-16, AC-19, AC-20 |
| R29 | Qualified/rejected mappings retain exact R12 action and common continuation behavior | AC-16, AC-18, AC-20 |
| R30 | Scenario matrix proves one error per failed attempt, one final outcome, and one produced Decision | AC-10, AC-17, AC-28 |
| R31 | Records reuse exact Run/Candidate identity and existing Profile/config trace without second authority | AC-13, AC-25, AC-26 |
| R32 | R13 store setup failure closes OCR Run as ERROR before OCR/listener/browser/AI/action | AC-24 |
| R33 | Runtime persistence failure reaches existing outer cleanup, RunStatus.ERROR, and no later Candidate | AC-22, AC-23, AC-24 |
| R34 | Repeated persisted ai_failed Candidates add no counter/threshold/stop | AC-21 |
| R35 | Action return/suppression/failure writes no action record and no duplicate Decision | AC-29 |
| R36 | OCR evidence, Candidate finalization/switching, and action function bodies remain unchanged | AC-27, AC-30 |
| R37 | No R14 read, replay, cache, hash, deduplication, migration, packaging, or release path exists | AC-31 |
| R38 | No generic persistence/retry/event/gate/guard/scanner/wrapper/orchestration framework or dependency is added | AC-32 |

Technical Responsibility count: **38 (R01–R38)**.

### 35.2 tests/test_ai_screening_runtime.py

Retain all accepted public behavior tests and add these exact focused methods:

- test_public_signature_and_result_shape_remain_exact_after_attempt_seam
- test_private_attempt_seam_completed_has_no_failure
- test_private_attempt_seam_maps_r09_value_error
- test_private_attempt_seam_maps_llm_runtime_error
- test_private_attempt_seam_maps_contract_error
- test_private_attempt_seam_propagates_unexpected_exceptions

The LLM error fixture includes code, provider, operation, status_code, request_id, and a message longer than 512 characters to prove exact copying/truncation. Source/contract fixtures prove unavailable optional fields are None.

### 35.3 tests/test_ai_screening_persistence.py

Create these exact methods:

- test_attempt_error_record_exact_schema_and_validation
- test_final_outcome_record_completed_failed_schemas
- test_decision_record_exact_schema_and_no_action_fields
- test_store_initializes_exact_three_streams_in_existing_run_dir
- test_appends_compact_utf8_single_lines_and_acknowledges_after_close
- test_writer_oserror_raises_integrity_error_without_retry_or_read_api

Use TemporaryDirectory. Parse lines with json and also verify one deterministic raw line/member order fixture. Patch Path.open only for targeted failure points; do not build a filesystem fault framework.

### 35.4 tests/test_candidate_decision_integration.py

Update the directly affected R12 helper fixture to supply one mock/spec AIScreeningRecordStore and add/retain these exact R13 cases:

- test_first_attempt_completed_orders_outcome_decision_persistence_and_qualified_action
- test_failed_then_completed_persists_error_before_retry_and_reuses_exact_objects
- test_two_failures_then_completed_stops_after_third_call
- test_three_failures_select_third_persist_ai_failed_and_continue
- test_attempt_error_write_failure_blocks_retry_outcome_decision_and_action
- test_final_outcome_write_failure_blocks_decision_and_action
- test_decision_write_failure_blocks_action_and_continuation
- test_r06_failure_after_final_outcome_writes_no_decision
- test_stop_and_pause_use_existing_state_without_synthetic_decision
- test_repeated_ai_failed_candidates_add_no_counter_or_stop
- test_action_result_does_not_write_an_additional_record

Use mock call sequences to assert:

~~~text
attempt failure → append_ai_error → next attempt
final result → append_ai_result → decide_candidate
decision → append_decision → qualified-only action
~~~

The final-outcome failure test is table-driven for completed and failed final results. Exact object reuse uses assertIs for Candidate, Profile, Config, RuleSet, and Store.

### 35.5 tests/test_simple_brush_ocr.py

Only directly affected setup/error tests change:

- extend test_binding_store_creation_precedes_ocr_listener_and_browser so the order is profile, config, OCR store, R13 store, OCR, listener, browser and the R13 constructor receives exact run_dir/run_id;
- add test_r13_store_initialization_failure_closes_ocr_run_as_error_before_execution;
- add test_runtime_r13_persistence_failure_projects_run_error_without_later_candidate.

The runtime failure case uses the existing mocked Run fixture, makes _process_finalized_candidate raise AIPersistenceIntegrityError, and proves existing finally cleanup closes RunStatus.ERROR, does not process a later Candidate, and does not duplicate finalization. No real browser/action is used.

tests/test_ocr_store.py is not modified because ocr_store.py is not modified. tests/test_candidate_decision.py is not modified and remains a targeted protected R12 regression.

## 36. Verification Commands

Implementation must run exactly these targeted commands:

~~~powershell
.\venv\Scripts\python.exe -m unittest tests.test_ai_screening_runtime tests.test_ai_screening_persistence tests.test_candidate_decision tests.test_candidate_decision_integration tests.test_simple_brush_ocr -v

.\venv\Scripts\python.exe -m compileall ai_screening_runtime.py ai_screening_persistence.py simple_brush.py tests\test_ai_screening_runtime.py tests\test_ai_screening_persistence.py tests\test_candidate_decision_integration.py tests\test_simple_brush_ocr.py

git diff --check

git diff --name-status

git diff -- ai_screening_runtime.py ai_screening_persistence.py simple_brush.py tests/test_ai_screening_runtime.py tests/test_ai_screening_persistence.py tests/test_candidate_decision_integration.py tests/test_simple_brush_ocr.py
~~~

Do not run the full suite, live AI, network, browser, real action, benchmark, packaging, dependency audit, repository scanner, full R03 regression, or unrelated accepted suites.

## 37. AC-01–AC-32 Implementation Mapping

| AC | Implementation symbol / file | Responsibilities | Planned verification evidence | Status |
|---|---|---|---|---|
| AC-01 | ai_screening_runtime private/public result paths; candidate_decision.py unchanged | R02, R28, R29 | public all-false/completed tests and final-flow integration matrix | Planned |
| AC-02 | _run_ai_screening_attempt(); run_ai_screening() compatibility projection | R01–R06 | exact signature/fields; three accepted mappings; unexpected propagation tests | Planned |
| AC-03 | simple_brush.R13_MAX_AI_SCREENING_ATTEMPTS; _run_r13_ai_screening() | R07 | three-failure call count and no fourth call | Planned |
| AC-04 | completed branch before error persistence/retry | R08 | first-attempt completed call sequence | Planned |
| AC-05 | Attempt 3 selection; AIFinalOutcomeRecord | R11, R30 | three distinct failed outcomes; third selected; one final line | Planned |
| AC-06 | exact candidate/profile/config loop arguments; final provider/model source | R12, R31 | assertIs identity across all calls and exact config trace | Planned |
| AC-07 | AIAttemptErrorRecord; append_ai_error() before loop continuation | R09, R10, R14, R19, R21 | one/two/three error-line matrices and ordered mocks | Planned |
| AC-08 | _AIScreeningAttemptFailure; AIAttemptErrorRecord | R03–R05, R14 | exact schemas, nulls, timestamp, bounded safe diagnostics | Planned |
| AC-09 | append_ai_error() AIPersistenceIntegrityError propagation | R20, R22, R33 | write-failure sequence proves no retry/downstream call and Run ERROR | Planned |
| AC-10 | AIFinalOutcomeRecord and one append_ai_result() per completed sequence | R15, R16, R30 | A–D scenario cardinality matrix | Planned |
| AC-11 | completed final record construction from selected result | R15 | exact complete mapping equality including all-false | Planned |
| AC-12 | failed final record construction from Attempt 3 | R11, R16 | failed/null/attempts_used=3 fixture | Planned |
| AC-13 | final trace fields from store/candidate/profile/config | R15, R16, R31 | exact field/source assertions; no full Profile/base_url/key | Planned |
| AC-14 | retained append_ai_error calls before later completed result | R09, R10 | retry-success cases B/C | Planned |
| AC-15 | _run_r13_ai_screening() append_ai_result before return/Decision | R23, R24, R27 | ordered calls and final-write failure/R06 failure cases | Planned |
| AC-16 | decide_candidate() unchanged after persisted final outcome | R27–R29 | qualified/rejected/ai_failed and R06-call matrix | Planned |
| AC-17 | CandidateDecisionRecord; one append_decision() | R17, R30 | exact schema and A–D Decision cardinality | Planned |
| AC-18 | append_decision() before existing qualified branch | R19, R25 | ordered mock sequence and Decision-write failure | Planned |
| AC-19 | final failed outcome → ai_failed Decision path | R11, R28 | three failures, zero R06/action, one persisted Decision | Planned |
| AC-20 | unchanged caller continuation after fully persisted status | R28, R29, R34 | ai_failed/qualified/rejected common continuation cases | Planned |
| AC-21 | no new failure counter/state | R34 | repeated ai_failed integration plus targeted diff review | Planned |
| AC-22 | append_ai_result() failure route | R20, R24, R33 | completed/failed final-write failure and outer Run ERROR | Planned |
| AC-23 | append_decision() failure route | R20, R26, R33 | in-memory Decision, zero action/later Candidate, Run ERROR | Planned |
| AC-24 | setup/runtime persistence propagation through existing Run cleanup | R13, R20, R32, R33 | setup and runtime RunStatus.ERROR tests | Planned |
| AC-25 | store.run_id/candidate IDs and equality checks | R12, R31 | exact identity tests; no generated replacement ID | Planned |
| AC-26 | final record copies only Profile ID/version/digest | R31 | exact key set and Profile source assertions | Planned |
| AC-27 | separate R13 module/files in existing directory; OCR Store untouched | R18, R36 | file/diff scope and existing OCR focused regression | Planned |
| AC-28 | one error per failure, one final, one produced Decision | R30 | scenario matrix and write-call counts | Planned |
| AC-29 | no action record/API; Decision write occurs once | R35 | action suppression/false/error tests and exact store surface | Planned |
| AC-30 | narrow pre-action ordering only; protected function bodies | R13, R29, R36 | focused integration and changed-file/diff review | Planned |
| AC-31 | write-only store and exact three files | R18, R37 | API/file list tests and targeted source review | Planned |
| AC-32 | requirement-specific private loop/store only | R38 | dependency and changed-file review | Planned |

AC mapping completeness: **32 / 32**.

## 38. Final Scope Review

The design introduces only:

- one shared private R11 attempt outcome;
- one R13-specific record/store module;
- one private simple_brush attempt loop;
- the exact persistence-before-retry/Decision/action ordering;
- focused tests for those seams.

It introduces no:

- R11 public argument/result change;
- R03 SDK retry change;
- Provider/model/config fallback;
- generic RetryManager, PersistenceManager, EventBus, callback registry, observer, pipeline, gate, guard, scanner, wrapper, validator, or database layer;
- persistence retry, delayed disable, fsync, transaction, crash-consistency framework, or background writer;
- Candidate/Run/OCR/Profile/Rule/Decision schema change;
- action-result persistence or action function change;
- consecutive failure stop/circuit breaker;
- R14 read/replay/cache/hash/deduplication/migration;
- dependency, packaging, release, CLI/UI, or repository-wide audit work.

After implementation and targeted verification, a separate docs/AM7-R13-acceptance-report.md may be created by a later Acceptance task. Implementation must not self-declare Human acceptance, merge, or release.

## 39. Open Technical Issues

None.

All implementation-level choices requested by the Frozen RPD are resolved: exact private failure seam, types, mappings, retries, delay, pause/stop behavior, store lifecycle, directory, filenames, schemas, writer mechanics, exception, integration order, file plan, tests, and verification commands.

## 40. Contract Conflicts

None.

The private shared attempt seam preserves the exact R11 public API and result shape. The independent raise-on-failure writer can reuse the existing OCR Run directory and identity without adopting OCR Store best-effort semantics or changing OCR authority. Existing R12 and outer Run boundaries can enforce the Frozen ordering and fatal persistence behavior without a new state machine.

## 41. Human Review Required Items and Readiness

Human Review Required Items: None.

This TID is Frozen and ready for implementation.

Final frozen-candidate technical outcome:

~~~text
one finalized Candidate
→ up to three shared-private R11 attempts
→ every failed attempt synchronously persisted before retry
→ exactly one final AI outcome synchronously persisted
→ R12 Decision
→ exactly one Decision synchronously persisted
→ qualified-only existing action
→ existing Candidate continuation

any required R13 write failure
→ AIPersistenceIntegrityError
→ zero downstream action/Candidate processing
→ existing RunStatus.ERROR cleanup
~~~

Current state: **AM7-R13 TID v0.1 — Frozen / Ready for Implementation**.
