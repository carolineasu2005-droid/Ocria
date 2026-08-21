# Ocria Am7 — AM7-R11 AI Screening Runtime

## 1. Metadata

- Product: Ocria Am7
- Requirement: AM7-R11 — AI Screening Runtime
- Document Type: Technical Implementation Design
- Version: 0.1
- Status: Draft
- Source RPD: `docs/RPD-AM7-R11-ai-screening-runtime.md` — v0.1 Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r11-ai-screening-runtime`
- Baseline: `3b5c61066c8df2e2d4573394c0df5167193f4bf3`

## 2. Status

This document defines the Draft technical implementation design for AM7-R11. It is ready for Human TID Review and must not be treated as Frozen until that review explicitly approves it.


Status: Frozen

## 3. Implementation Objective

Implement the smallest local Candidate-level AI screening runtime that composes the already-accepted R09, R10, and R03 public APIs:

```text
CandidateOcrDocument
    + ScreeningProfileVersion
    + AIProviderConfig
    -> build_ai_candidate_input(...)
    -> build_ai_screening_prompt(...)
    -> exact SYSTEM / USER LLMCompletionRequest
    -> complete(config, request) at most once
    -> completion.content
    -> validate_ai_screening_response(...)
    -> AIScreeningResult
```

R11 ends at the Candidate-associated complete Boolean mapping or the exact failed result. It does not execute R06, make a Candidate Decision, trigger an Action, or implement R13/R14 behavior.

## 4. Authoritative Contracts

Implementation authority, in order, is:

1. `CODEX-CONSTITUTION.md`;
2. `docs/RPD-AM7-R11-ai-screening-runtime.md` v0.1 Frozen;
3. the accepted public APIs of R03, R05, R09, and R10 identified below;
4. this TID after Human Freeze.

The implementation must not reopen or alter any accepted upstream product contract. If implementation evidence exposes an actual contradiction, implementation stops at that contradiction and reports it rather than adding a workaround.

## 5. Targeted Repository Findings

Inspection was limited to the Frozen R11 RPD, the exact upstream runtime types and functions R11 calls, the Candidate document definition, and narrowly relevant R03/R09/R10 tests.

### 5.1 Baseline

- Observed branch: `am7-r11-ai-screening-runtime`.
- Observed HEAD: `3b5c61066c8df2e2d4573394c0df5167193f4bf3`.
- The Frozen R11 RPD is v0.1 with AC-01 through AC-42.

### 5.2 Candidate and Profile types

- `ocr_records.CandidateOcrDocument` is the actual Candidate input type.
- Its Candidate identity field is `candidate_record_id: str`.
- Its authoritative R09 source text is `document_text: Optional[str]`.
- `screening_profile.ScreeningProfileVersion` is the actual Profile input type.
- Its Criteria are held in `criteria: tuple[Criterion, ...]`; construction enforces a non-empty tuple of actual valid Criteria.

### 5.3 R09 API and failure behavior

`ai_candidate_input.py` exposes:

```python
@dataclass(frozen=True)
class AICandidateInput:
    candidate_record_id: str
    resume_text: str


def build_ai_candidate_input(
    candidate: CandidateOcrDocument,
) -> AICandidateInput:
    ...
```

Observed behavior:

- wrong source object type raises built-in `TypeError`;
- `AICandidateInput` requires a string Candidate ID;
- missing, empty, whitespace-only, or otherwise invalid resume-text content raises built-in `ValueError`;
- successful projection copies the source Candidate ID and document text exactly;
- R09 adds no Candidate-ID grammar, non-blank ID rule, or normalization.

### 5.4 R10 Prompt API

`ai_screening_prompt.py` exposes:

```python
@dataclass(frozen=True)
class AIScreeningPrompt:
    system_message: str
    user_message: str
    prompt_version: str


def build_ai_screening_prompt(
    candidate_input: AICandidateInput,
    profile: ScreeningProfileVersion,
) -> AIScreeningPrompt:
    ...
```

The builder raises built-in `TypeError` for wrong public argument object types. For valid accepted R09/R05 inputs it defines no expected runtime-failure state. It owns exact Prompt v1 content and serialization.

### 5.5 R03 configuration and completion APIs

`ai_provider_config.AIProviderConfig` is the actual Provider configuration type. It contains the selected Provider, API key, base URL, and model and exposes `is_complete`. R11 receives an instance directly and does not load or alter configuration.

`llm_provider_runtime.py` exposes:

```python
class LLMMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class LLMMessage:
    role: LLMMessageRole
    content: str


@dataclass(frozen=True)
class LLMCompletionRequest:
    messages: tuple[LLMMessage, ...]


@dataclass(frozen=True)
class LLMCompletionResult:
    content: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    finish_reason: str | None
    request_id: str | None


def complete(
    config: AIProviderConfig,
    request: LLMCompletionRequest,
) -> LLMCompletionResult:
    ...
```

The accepted completion failure boundary is `llm_provider_runtime.LLMRuntimeError`. The current runtime performs one non-streaming SDK call, uses `timeout=120.0`, uses `max_retries=0`, and implements no application retry or Provider/model fallback.

### 5.6 R10 response contract API

`ai_screening_contract.py` exposes:

```python
class AIScreeningContractError(ValueError):
    ...


def validate_ai_screening_response(
    raw_response: str,
    criteria: tuple[Criterion, ...],
) -> dict[str, bool]:
    ...
```

Invalid model response content raises `AIScreeningContractError`. Wrong validator argument object types raise built-in `TypeError`. On success it returns a complete strict-Boolean mapping reconstructed in authoritative Profile Criterion order.

### 5.7 Test conventions

- Tests use standard-library `unittest` and `unittest.mock.patch`.
- Root-level implementation modules are imported directly.
- Existing R09 tests construct actual finalized Candidates through `CandidateOcrBuilder`; that pattern can represent one or multiple Screens without adding an R11 fixture framework.
- Existing R10 tests construct actual Criteria/Profile values locally.
- Existing R03 tests construct normalized `LLMCompletionResult` values and patch only the network-facing seam.
- No new dependency is required.

No technical conflict was found.

## 6. Final File Scope

### 6.1 New implementation files

| File | Purpose |
|---|---|
| `ai_screening_runtime.py` | Exact R11 result value and one formal runtime function |
| `tests/test_ai_screening_runtime.py` | Focused offline R11 unittest coverage |

### 6.2 Later acceptance file

`docs/AM7-R11-acceptance-report.md` is created only in the later Acceptance step. It is not an implementation Change.

### 6.3 Modified existing runtime files

None.

No additional production or test module is technically necessary.

## 7. Imports and Dependencies

`ai_screening_runtime.py` must use only standard-library `dataclasses`/`typing` and these accepted local public symbols:

```python
from dataclasses import dataclass
from typing import Literal

from ai_candidate_input import build_ai_candidate_input
from ai_provider_config import AIProviderConfig
from ai_screening_contract import (
    AIScreeningContractError,
    validate_ai_screening_response,
)
from ai_screening_prompt import build_ai_screening_prompt
from llm_provider_runtime import (
    LLMCompletionRequest,
    LLMMessage,
    LLMMessageRole,
    LLMRuntimeError,
    complete,
)
from ocr_records import CandidateOcrDocument
from screening_profile import ScreeningProfileVersion
```

No dependency, requirements, packaging, environment, or Provider SDK change is authorized.

The runtime must not import R06, Candidate Decision, browser/action, persistence, store, replay, cache, hash, or orchestration modules.

## 8. Public Runtime Module

Create one root-level module, `ai_screening_runtime.py`. Its only R11 product surface is:

- `AIScreeningResult`;
- `run_ai_screening(...)`.

Do not create a class-based runtime, manager, pipeline, adapter, router, registry, wrapper, guard, scanner, or framework.

## 9. AIScreeningResult

Freeze the result as:

```python
@dataclass(frozen=True)
class AIScreeningResult:
    candidate_record_id: str
    ai_status: Literal["completed", "failed"]
    criteria_results: dict[str, bool] | None
```

The field order is exact. There is no fourth field and no inheritance hierarchy.

### 9.1 Minimal constructor invariants

Use one small `__post_init__` to enforce only the result's local value shape:

```python
def __post_init__(self) -> None:
    if not isinstance(self.candidate_record_id, str):
        raise ValueError("candidate_record_id must be a string")

    if self.ai_status == "completed":
        if (
            not isinstance(self.criteria_results, dict)
            or not self.criteria_results
            or any(
                type(criterion_id) is not str or type(value) is not bool
                for criterion_id, value in self.criteria_results.items()
            )
        ):
            raise ValueError(
                "completed result requires a non-empty Boolean mapping"
            )
    elif self.ai_status == "failed":
        if self.criteria_results is not None:
            raise ValueError("failed result requires criteria_results=None")
    else:
        raise ValueError("ai_status must be completed or failed")
```

This is not a second R10 validator. It enforces status/payload shape only. Completeness against a particular Profile remains guaranteed by the mandatory R10 validator call before normal completed construction. The normal R11 path never constructs a completed value from an unvalidated or partial mapping.

The outer value is immutable. R11 passes the validator-returned mapping directly and does not copy or normalize it.

## 10. Status Representation

Use the two literal strings directly with the type annotation:

```python
Literal["completed", "failed"]
```

Do not add an Enum, status registry, status class, pending/retry/degraded state, or error subtype. Runtime constructor enforcement in §9 rejects every third status.

## 11. Public run_ai_screening API

Freeze the exact public signature:

```python
def run_ai_screening(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> AIScreeningResult:
    ...
```

There is no overload, dict input, raw-text input, Screen input, Criterion-only input, optional Provider/model parameter, retry parameter, or persistence parameter.

## 12. Entry Type Validation

The function begins with these checks in this order and outside all failure-normalization `try` blocks:

```python
if not isinstance(candidate, CandidateOcrDocument):
    raise TypeError("candidate must be a CandidateOcrDocument")
if not isinstance(profile, ScreeningProfileVersion):
    raise TypeError("profile must be a ScreeningProfileVersion")
if not isinstance(config, AIProviderConfig):
    raise TypeError("config must be an AIProviderConfig")
```

These are public entry-contract violations. They produce no `AIScreeningResult` and are never caught by R11.

R11 does not add a separate `config.is_complete` gate. The actual supplied configuration is passed unchanged to R03; accepted R03 request/configuration failures already use `LLMRuntimeError`.

## 13. Candidate Identity Establishment

After public object-type checks and before R09 projection:

```python
candidate_record_id = candidate.candidate_record_id
if not isinstance(candidate_record_id, str):
    raise ValueError("candidate.candidate_record_id must be a string")
```

This is the smallest enforcement of the Frozen source identity shape. It deliberately adds no non-blank rule, UUID grammar, prefix, suffix, normalization, transformation, or regenerated ID.

A non-string source ID is an entry-contract value violation. It produces no result and is outside every expected-failure catch block. An unexpected missing attribute or corrupt object invariant also propagates; R11 does not fabricate identity.

The local `candidate_record_id` variable is the sole result-association source for both completed and failed construction.

## 14. R09 Projection

Invoke exactly:

```python
candidate_input = build_ai_candidate_input(candidate)
```

Do not read Candidate Screens or document segments, reconstruct text, normalize text, or create `AICandidateInput` directly.

The accepted R09 contract guarantees on success:

```python
candidate_input.candidate_record_id == candidate_record_id
```

R11 relies on this accepted upstream invariant and uses the source ID for result construction. It does not add a duplicate identity guard or comparison framework. Focused integration coverage uses the real R09 builder to verify exact equality.

## 15. R09 ValueError Boundary

The `ValueError` catch is scoped to the single accepted R09 builder call:

```python
try:
    candidate_input = build_ai_candidate_input(candidate)
except ValueError:
    return AIScreeningResult(
        candidate_record_id=candidate_record_id,
        ai_status="failed",
        criteria_results=None,
    )
```

Because top-level Candidate type and source Candidate ID are validated before this block, the expected current `ValueError` at this seam is the R09 source-content/output-value failure, including missing, empty, or whitespace-only authoritative document text.

The block must not include Prompt building, message/request construction, Provider execution, or validation. R11 must not catch R09's top-level `TypeError`, a `ValueError` outside this exact call, or an unrelated exception.

On this failure path, Provider call count is zero and the failed result retains the exact source Candidate ID without requiring an `AICandidateInput`.

## 16. R10 Prompt Construction

After successful R09 projection, invoke exactly:

```python
prompt = build_ai_screening_prompt(candidate_input, profile)
```

This call is outside all three expected-failure catch blocks. R11 does not catch Prompt-builder `TypeError` or another unexpected Prompt exception.

R11 does not copy Prompt v1, inspect or change `prompt.prompt_version`, change serialization, append instructions, or alter `system_message` or `user_message`.

## 17. Provider Message Projection

Construct exactly two accepted R03 messages in this order:

```python
messages = (
    LLMMessage(
        role=LLMMessageRole.SYSTEM,
        content=prompt.system_message,
    ),
    LLMMessage(
        role=LLMMessageRole.USER,
        content=prompt.user_message,
    ),
)
```

No third or assistant message, prefill, metadata message, Candidate ID, Profile metadata, Rule data, or Prompt-version value is added. Message contents are passed byte-for-byte as Python strings returned by R10.

## 18. LLMCompletionRequest Construction

The actual R03 constructor has one field. Construct it exactly as:

```python
request = LLMCompletionRequest(messages=messages)
```

Do not add temperature, maximum-token policy, response-format option, structured-output mode, retry option, timeout override, streaming option, or any guessed field.

## 19. Provider Config Handling

Pass the exact supplied object to R03:

```python
complete(config, request)
```

R11 does not load `AIProviderConfigStore`, clone or rebuild config, select another Provider/model, override API key/base URL/model, or create a registry/fallback list.

Tests must use identity assertion (`is`) or equivalent mock call inspection to confirm that the same config object reaches `complete()`.

## 20. Single complete() Invocation

Within one call to `run_ai_screening(...)`:

- entry violation: zero calls;
- expected R09 projection failure: zero calls;
- accepted pre-Provider success: exactly one `complete(config, request)` call;
- Provider failure or response-contract failure: no second call.

No loop encloses `complete()`. Screen count and Criterion count do not affect invocation count. No verification, repair, retry, fallback, voting, comparison, alternate model, or alternate Provider call is permitted.

This is a per-R11-call invariant, not a cross-call deduplication mechanism.

## 21. LLMRuntimeError Boundary

Only the one Provider call is enclosed by this catch:

```python
try:
    completion = complete(config, request)
except LLMRuntimeError:
    return AIScreeningResult(
        candidate_record_id=candidate_record_id,
        ai_status="failed",
        criteria_results=None,
    )
```

Do not inspect the `LLMRuntimeError` code or add a failure reason/status subtype. Do not retry or switch Provider/model. Do not catch arbitrary `RuntimeError` or broad `Exception`.

## 22. Raw Response Handoff

The raw model response supplied to R10 is exactly:

```python
completion.content
```

R11 must not call `.strip()`, remove Markdown fences, extract a JSON substring, parse JSON itself, repair content, normalize whitespace, coerce values, or use fallback parsing.

No other `LLMCompletionResult` field is read into the R11 result.

## 23. R10 Contract Validation

Invoke exactly:

```python
criteria_results = validate_ai_screening_response(
    raw_response=completion.content,
    criteria=profile.criteria,
)
```

The exact same Profile Version supplies Prompt Criteria and validation Criteria. R11 does not copy, filter, reorder, default, or otherwise rebuild the returned mapping.

Validator argument `TypeError` signals an integration/programming defect and must propagate.

## 24. AIScreeningContractError Boundary

Only the validator call is enclosed by this catch:

```python
try:
    criteria_results = validate_ai_screening_response(
        raw_response=completion.content,
        criteria=profile.criteria,
    )
except AIScreeningContractError:
    return AIScreeningResult(
        candidate_record_id=candidate_record_id,
        ai_status="failed",
        criteria_results=None,
    )
```

No partial mapping escapes. Contract failure causes no repair or second Provider call.

## 25. Unexpected Exception Propagation

The implementation must contain no `except Exception` or `except BaseException`.

It must not normalize these into a failed result:

- wrong public entry object `TypeError`;
- source identity `ValueError` raised before R09;
- Prompt-builder `TypeError` or unexpected Prompt exception;
- validator argument/integration `TypeError`;
- unexpected `AttributeError`, `AssertionError`, `KeyError`, arbitrary `RuntimeError`, or other programming defect;
- any `ValueError` outside the single R09 builder call.

R11 is not an exception-suppression boundary.

## 26. Exact Control Flow

The implementation shape is frozen as the following direct sequence:

```python
def run_ai_screening(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> AIScreeningResult:
    if not isinstance(candidate, CandidateOcrDocument):
        raise TypeError("candidate must be a CandidateOcrDocument")
    if not isinstance(profile, ScreeningProfileVersion):
        raise TypeError("profile must be a ScreeningProfileVersion")
    if not isinstance(config, AIProviderConfig):
        raise TypeError("config must be an AIProviderConfig")

    candidate_record_id = candidate.candidate_record_id
    if not isinstance(candidate_record_id, str):
        raise ValueError("candidate.candidate_record_id must be a string")

    try:
        candidate_input = build_ai_candidate_input(candidate)
    except ValueError:
        return AIScreeningResult(candidate_record_id, "failed", None)

    prompt = build_ai_screening_prompt(candidate_input, profile)
    request = LLMCompletionRequest(messages=(
        LLMMessage(LLMMessageRole.SYSTEM, prompt.system_message),
        LLMMessage(LLMMessageRole.USER, prompt.user_message),
    ))

    try:
        completion = complete(config, request)
    except LLMRuntimeError:
        return AIScreeningResult(candidate_record_id, "failed", None)

    try:
        criteria_results = validate_ai_screening_response(
            raw_response=completion.content,
            criteria=profile.criteria,
        )
    except AIScreeningContractError:
        return AIScreeningResult(candidate_record_id, "failed", None)

    return AIScreeningResult(
        candidate_record_id,
        "completed",
        criteria_results,
    )
```

Keyword versus positional use in the small result/message constructors may follow this shown form, but field order, values, catch placement, and called public APIs are exact.

## 27. Completed Construction

Completed construction occurs only after the validator returns:

```python
AIScreeningResult(
    candidate_record_id=source_candidate_record_id,
    ai_status="completed",
    criteria_results=criteria_results,
)
```

The exact source ID and exact validator-returned dict are used. `criteria_results` is never `None` on this path.

## 28. Failed Construction

Each of the three accepted expected failure catches constructs exactly:

```python
AIScreeningResult(
    candidate_record_id=source_candidate_record_id,
    ai_status="failed",
    criteria_results=None,
)
```

There is no failure reason, subtype, mapping, empty dict, or default Boolean value.

## 29. All-False Semantics

If R10 returns a complete mapping whose every value is `False`, R11 passes that same mapping into a `completed` result. R11 does not reinterpret it as failure, rejection, or no result.

## 30. No Partial Success

R11 constructs completed output only from the return value of the complete R10 validator. An `AIScreeningContractError` yields failed plus `None`; no valid subset, partial dict, empty dict, or default-false mapping is retained.

## 31. No Cross-Invocation State

`ai_screening_runtime.py` contains no mutable registry, ledger, cache, already-evaluated set, request key, persistence record, or duplicate-call guard.

Two separate explicit calls with the same Candidate/Profile/config may each call `complete()` once. R11 does not remember or suppress the second call. Normal orchestration expectations and repeated-execution decisions remain outside R11.

## 32. R06 / R12 Boundary

The runtime does not import or call `evaluate_rule_set`, `ScreeningRuleSet`, or Decision logic. Its successful output ends at the R10-compatible Boolean mapping. AM7-R12 owns Rule evaluation, Candidate Decision, and production-action authority.

## 33. R13 Boundary

R11 implements no retry, retry scheduling, repeated-call policy, cross-invocation deduplication, degradation, failure persistence, stop condition, Provider switching, or model switching. These remain R13 or later accepted orchestration responsibilities.

## 34. R14 Boundary

R11 implements no replay, cache, hash, digest, history, evaluation metadata, raw-response persistence, Prompt persistence, token/latency logging, comparison, or reproducibility record.

## 35. Protected Scope

Implementation must not modify:

- `docs/RPD-AM7-R11-ai-screening-runtime.md`;
- `ai_candidate_input.py` and R09 tests/docs/reports;
- `ai_screening_prompt.py`, `ai_screening_contract.py`, and R10 tests/docs/reports;
- `screening_profile.py` and R05 files;
- `screening_rule_engine.py` and R06 files;
- `ai_provider_config.py`, `ai_provider_cli.py`, `llm_provider_runtime.py`, and R03 files;
- `ocr_records.py`, `ocr_candidate.py`, `ocr_detector.py`, or other Candidate/OCR files;
- persistence/store files;
- `simple_brush.py`, browser/UI/action files;
- existing tests;
- dependencies, requirements, packaging, build, Git, or release files;
- prior Frozen documents and acceptance reports.

Implementation is additive: one runtime file and one focused test file.

## 36. Focused Test Strategy

Create `tests/test_ai_screening_runtime.py` using `unittest` and `unittest.mock.patch`.

### 36.1 Fixtures

Use small local helpers only:

- `make_candidate(...)`: follow the existing accepted R09 test pattern using `CandidateOcrBuilder` to produce an actual finalized `CandidateOcrDocument`; allow one or two simple Screen texts and an aggregation-disabled missing-text case;
- `make_profile(...)`: construct actual `Criterion` values and one actual `ScreeningProfileVersion` with `criteria_digest(...)`;
- `make_config()`: construct one complete `AIProviderConfig` using a test-only Provider URL and model;
- `make_completion(content)`: construct `LLMCompletionResult` with the exact required fields and no live Provider call;
- a small raw-response helper using standard-library `json.dumps` for complete R10 payloads.

Do not create fake Provider classes, a fixture framework, or reusable test infrastructure outside this one test module.

### 36.2 Mocking boundary

- Happy-path composition tests use real R09 builder, real R10 Prompt builder, and real R10 validator; patch only `ai_screening_runtime.complete`.
- Patch `ai_screening_runtime.build_ai_candidate_input` only to isolate the accepted R09 `ValueError` catch placement when needed in addition to the real missing-text case.
- Patch `ai_screening_runtime.build_ai_screening_prompt` only for the unexpected-exception propagation test.
- Patch `ai_screening_runtime.validate_ai_screening_response` only to observe exact raw-response/Criteria handoff or force the targeted exception path.
- Never patch or call the OpenAI SDK and never make a live Provider request.

### 36.3 Planned test method groups

Closely related responsibilities may be consolidated into approximately these focused methods:

1. completed mixed/all-true/all-false subcases;
2. exact source identity and exact Provider request projection;
3. one call with multiple Criteria and multiple Screens;
4. real R09 missing-text failure and zero Provider calls;
5. isolated accepted R09 `ValueError` catch placement;
6. `LLMRuntimeError` failed-result path;
7. malformed transport-success response and R10 contract failure;
8. incomplete/partial response failure and no synthesized mapping;
9. three wrong top-level argument-type subcases;
10. invalid source Candidate ID entry violation;
11. result field/status/payload constructor invariants;
12. unexpected Provider exception propagation;
13. unexpected Prompt exception propagation;
14. validator `TypeError` propagation;
15. exact raw-content/Profile-Criteria handoff;
16. equal local result and two independent explicit calls.

Direct import/source review covers the absence of R06 and browser/action dependencies without introducing a repository scanner test.

## 37. Test Responsibility Mapping R01–R37

| ID | Focused responsibility | Planned verification |
|---|---|---|
| R01 | Completed mixed Boolean mapping | Real R10 validator + mocked completion; exact completed result |
| R02 | Completed all-true mapping | Valid response subcase; exact mapping |
| R03 | Completed all-false mapping | Valid response subcase; completed, not failed |
| R04 | Exact source Candidate ID on success | Compare source, R09 output, and R11 result |
| R05 | Exact SYSTEM then USER roles/order | Inspect the one `LLMCompletionRequest` passed to `complete` |
| R06 | Exact Prompt message contents | Compare request contents with real R10 Prompt output |
| R07 | Exactly two Provider messages | Assert tuple length and exact values |
| R08 | Supplied config passed unchanged | `complete` mock receives the identical config object |
| R09 | Successful evaluation calls `complete` once | `assert_called_once` |
| R10 | Multiple Criteria still one call | Multi-Criterion Profile subcase |
| R11 | Multiple Screens still one call | Actual two-Screen finalized Candidate fixture |
| R12 | R09 content `ValueError` -> source ID/failed/None | Real missing-text Candidate and isolated seam case |
| R13 | R09 failure -> zero Provider calls | `complete.assert_not_called()` |
| R14 | `LLMRuntimeError` -> failed/None | Exact accepted exception fixture |
| R15 | `AIScreeningContractError` -> failed/None | Invalid raw response or patched validator |
| R16 | Transport success + malformed response -> failed | Completion result with malformed content; real validator |
| R17 | Technical failure never synthesizes all-false | Assert `criteria_results is None` on all failure paths |
| R18 | No partial mapping on contract failure | Missing-ID response -> failed/None |
| R19 | Wrong Candidate type -> `TypeError` | Public entry test; no result |
| R20 | Wrong Profile type -> `TypeError` | Public entry test; no result |
| R21 | Wrong config type -> `TypeError` | Public entry test; no result |
| R22 | Invalid source Candidate ID -> entry violation | Mutate test Candidate ID to non-string; assert `ValueError`, no result/call |
| R23 | Successful R09 ID equals source ID | Real R09 integration assertion |
| R24 | Candidate ID absent model-visible messages | Search only the two captured message strings for the known test ID |
| R25 | Completed carries mapping, never `None` | Happy-path assertions and constructor invariant test |
| R26 | Failed carries `None`, never mapping | Three expected-failure path assertions and constructor invariant test |
| R27 | Only completed/failed constructed | Dataclass fields/status invariant test; third status rejected |
| R28 | Unexpected Provider exception propagates | `complete` raises plain `RuntimeError`; assert propagation |
| R29 | Unexpected Prompt exception propagates | Prompt seam raises plain `RuntimeError`; assert propagation |
| R30 | Validator argument/integration `TypeError` propagates | Validator seam raises `TypeError`; assert propagation |
| R31 | Raw `completion.content` reaches validator unchanged | Capture exact object/string and `profile.criteria` call arguments |
| R32 | No JSON repair or strip | Whitespace/fence-bearing sentinel reaches patched validator unchanged |
| R33 | Same local inputs/content -> equal local result | Two explicit calls with identical mocked completion content |
| R34 | No R06 evaluation | Runtime import/call surface review; no R06 symbol in implementation |
| R35 | No browser/action behavior | Runtime import/call surface review; protected files untouched |
| R36 | No second call after contract failure | Malformed response path still has exactly one `complete` call |
| R37 | No cross-invocation deduplication | Two separate calls each reach `complete`; total call count two |

There are 37 technical coverage responsibilities. The unittest method count may be lower through the listed consolidations; each responsibility must remain individually traceable in implementation/acceptance evidence.

## 38. Implementation Change Plan

### Change 1 — Runtime

- Create `ai_screening_runtime.py` only.
- Implement `AIScreeningResult` and `run_ai_screening(...)` exactly as frozen here.
- Do not create tests or modify docs during this Change.
- Review imports and control-flow catch placement against §§7–26.

### Change 2 — Focused tests and verification

- Create `tests/test_ai_screening_runtime.py` only.
- Implement R01–R37 focused responsibilities.
- Run the Frozen targeted verification commands once with direct output evidence.
- If a focused test exposes a genuine R11 implementation mismatch, make only the minimum correction in `ai_screening_runtime.py` and rerun the affected targeted command under the accepted execution protocol.
- Make no unrelated source, test, or documentation change.

Implementation Change count: **2**.

The later Acceptance Report is not a numbered implementation Change.

## 39. Targeted Verification Commands

After Change 2, run exactly:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ai_screening_runtime -v
.\venv\Scripts\python.exe -m compileall ai_screening_runtime.py tests\test_ai_screening_runtime.py
```

Capture the direct command, output, and exit result from the first formal execution.

Do not run full repository tests, live Provider/API calls, model benchmarks, packaging smoke, dependency audit, or full R03/R09/R10 acceptance suites for R11 implementation.

## 40. AC-01–AC-42 Verification Mapping

| Frozen AC | Implementation symbol / behavior | Focused responsibility / evidence |
|---|---|---|
| AC-01 | `run_ai_screening` exact typed entry; three type checks; source ID check | R19–R22; signature review |
| AC-02 | Accept actual finalized Candidate; no lifecycle gate/finalizer | Actual builder fixture; runtime import/source review |
| AC-03 | Direct `build_ai_candidate_input(candidate)` | R12, R23; call/source review |
| AC-04 | Source ID local variable; real R09 equality; same result ID | R04, R12, R23 |
| AC-05 | Same `profile` passed to Prompt builder; `profile.criteria` passed to validator | R01, R06, R31 |
| AC-06 | Direct `build_ai_screening_prompt(candidate_input, profile)` | R05–R07, R29 |
| AC-07 | Candidate ID used only for local result association | R24; request inspection |
| AC-08 | First `LLMMessage` uses SYSTEM and exact system content | R05, R06 |
| AC-09 | Second `LLMMessage` uses USER and exact user content | R05, R06 |
| AC-10 | Exact two-element message tuple | R05, R07 |
| AC-11 | Supplied config directly used; no store/registry | R08; import/source review |
| AC-12 | No Provider/model/config override | R08; object identity and request call inspection |
| AC-13 | Actual `LLMMessage`, `LLMCompletionRequest`, `complete` APIs | R05–R09; signature/source review |
| AC-14 | Zero calls on R09 failure; exactly one after pre-Provider success | R09, R13 |
| AC-15 | No Screen iteration; multi-Screen Candidate still one call | R11 |
| AC-16 | No Criterion loop around Provider call; multi-Criterion still one call | R10 |
| AC-17 | No second/alternate/repair/fallback invocation | R36; control-flow review |
| AC-18 | Direct `completion.content` handoff | R31, R32 |
| AC-19 | Exact same `profile.criteria` validator argument | R31 |
| AC-20 | Completed construction follows all successful stages only | R01–R09, R25 |
| AC-21 | Malformed transport-success content becomes failed through R10 | R15, R16 |
| AC-22 | Only three expected catches construct failed/None; defects propagate | R12, R14, R15, R28–R30 |
| AC-23 | Established source ID retained across R09 content failure | R12, R13, R19, R22 |
| AC-24 | Catch exact `LLMRuntimeError` only | R14, R28 |
| AC-25 | Catch exact `AIScreeningContractError`; no partial; TypeError propagates | R15, R16, R18, R30 |
| AC-26 | Literal statuses and constructor rejection of third status | R27 |
| AC-27 | Exact three dataclass fields | R25–R27; `dataclasses.fields` review |
| AC-28 | Completed mapping comes only from real complete R10 validation | R01–R03, R25 |
| AC-29 | `__post_init__` status/payload invariants; normal path validation | R25–R27 |
| AC-30 | All-false response remains completed | R03 |
| AC-31 | Every expected technical failure carries `None` | R17 |
| AC-32 | R10 contract error discards all partial data | R18 |
| AC-33 | No Decision value/import/API | R27, R34; import/source review |
| AC-34 | No R06 import or call | R34 |
| AC-35 | No action/browser import or call | R35 |
| AC-36 | No persistence/store import or write | File/import/source review |
| AC-37 | No retry; per-call one invocation; no cross-call memory | R09, R13, R36, R37 |
| AC-38 | No replay/cache/hash/digest/history implementation | File/import/source review |
| AC-39 | Exact result fields; no deferred metadata | R27; dataclass field review |
| AC-40 | Equal local result for same inputs and completion content | R33 |
| AC-41 | Only two additive files; upstream files protected | Final file-scope/diff review |
| AC-42 | No R12/R13/R14 implementation | R34, R35, R37; import/source review |

Every Frozen AC has an implementation owner and focused verification responsibility. No additional product AC is introduced.

## 41. Acceptance Report Contract

The later Acceptance step creates:

`docs/AM7-R11-acceptance-report.md`

If all Frozen automated checks pass, its status must be exactly:

`Automated Acceptance Passed / Pending Human Final Review`

The report must include:

- final implemented functionality and file scope;
- focused command evidence;
- exact R09/R03/R10 exception-boundary evidence;
- exact one-invocation and zero-call-on-R09-failure evidence;
- Candidate identity behavior;
- completed/failed and all-false/no-partial invariants;
- Provider message and raw-response handoff evidence;
- protected upstream scope and R12/R13/R14 non-implementation;
- individual AC-01 through AC-42 mapping;
- Deviations, Open Issues, and Contract Conflicts.

It must not self-declare Human Accepted, Merged, or Released.

## 42. Deviations Policy

Implementation must follow this TID after Human Freeze. Any discovered mismatch between the exact accepted upstream API and this design must be reported with the smallest concrete evidence.

Do not silently:

- add a catch-all;
- change result shape/status;
- add a retry/fallback/deduplication path;
- alter Prompt or Provider request content;
- modify a protected upstream file;
- add a third implementation Change or production module.

A documented Human-approved revision is required before any such contract change.

## 43. Open Issues

None.

## 44. Contract Conflicts

None.

## 45. Final Implementation Contract Summary

AM7-R11 is implemented additively in one runtime module and one focused test module. The runtime exposes one frozen result dataclass and one function. It validates three top-level object types, establishes the exact source Candidate ID, delegates Candidate projection to R09, delegates Prompt construction to R10, creates exactly two R03 messages and the one-field completion request, calls `complete(config, request)` at most once per R11 call, hands exact `completion.content` to the R10 validator, and constructs either the exact completed mapping result or exact failed/None result.

Only the narrowly scoped R09 source-content `ValueError`, R03 `LLMRuntimeError`, and R10 `AIScreeningContractError` become failed results. Entry violations and unexpected defects propagate. R11 adds no cross-invocation state, R06 execution, Decision, Action, retry, fallback, persistence, replay, cache, hash, or R12–R14 implementation.
