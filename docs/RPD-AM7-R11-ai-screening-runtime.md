# Ocria Am7 — AM7-R11 AI Screening Runtime

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R11
- Document Type: Requirement / Product Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r11-ai-screening-runtime`
- Working HEAD / Upstream Baseline: `3b5c61066c8df2e2d4573394c0df5167193f4bf3`

## 1. Status

This document defines the Frozen product contract for AM7-R11. RPD v0.1 is the authoritative product-design baseline for subsequent TID and implementation work.

## 2. Requirement Summary

AM7-R11 owns the Candidate-level runtime composition that takes one existing finalized `CandidateOcrDocument`, one saved formal `ScreeningProfileVersion`, and the currently selected complete `AIProviderConfig`; builds the already-defined R09 Candidate input and R10 Prompt; performs one formal Provider completion invocation; validates the raw model response through the R10 Boolean contract; and returns one Candidate-associated `AIScreeningResult`.

AM7-R11 does not decide whether the Candidate qualifies, execute R06 Rules, perform any production action, or own retry, persistence, replay, or orchestration policy.

## 3. Product Goal

Provide the smallest authoritative runtime boundary for one formal Candidate-level AI screening evaluation while preserving the accepted separation between OCR evidence, Candidate input projection, Prompt construction, Provider transport, Boolean response validation, Rule evaluation, Candidate Decision, and production action.

## 4. Accepted Upstream Contracts

AM7-R11 composes, and does not redesign, these accepted contracts:

- AM7-R03: current Provider configuration and Provider-neutral LLM Runtime;
- AM7-R05: immutable saved `ScreeningProfileVersion` and its Criteria;
- AM7-R06: deterministic Boolean Rule Engine, deferred from R11 execution;
- AM7-R08: `Screen = Evidence Scope` and `Candidate = Ocria Am7 Production Decision Scope`;
- AM7-R09: exact `CandidateOcrDocument` to `AICandidateInput` projection;
- AM7-R10: exact Prompt v1 construction and strict Boolean response validation.

No accepted upstream contract is reopened by R11.

## 5. Targeted Repository Findings

The targeted inspection was limited to the governing document, R10 Frozen design and acceptance artifacts, R09/R10 runtime modules, R05 profile representation, R03 Provider configuration/runtime, narrowly relevant tests, and the Candidate document/finalization path.

Observed facts at the stated baseline:

- The current branch is `am7-r11-ai-screening-runtime`; HEAD is the stated baseline and descends from that baseline trivially because they are identical. The working tree was clean before this RPD was created.
- `ai_candidate_input.py` exposes immutable `AICandidateInput` and `build_ai_candidate_input(candidate)`. It copies `candidate_record_id` and exact non-blank `document_text`; missing or blank document text fails projection.
- The accepted R09 builder raises built-in `TypeError` for a non-`CandidateOcrDocument` argument. Its `AICandidateInput` value raises built-in `ValueError` when the copied Candidate ID is not a string or the copied resume text is not a non-blank string. R09 adds no Candidate-ID grammar or normalization.
- `ai_screening_prompt.py` exposes immutable `AIScreeningPrompt` and `build_ai_screening_prompt(candidate_input, profile)`. Prompt v1 contains exactly one system message and one user message.
- The accepted R10 Prompt builder raises built-in `TypeError` only for wrong public argument object types; it defines no expected runtime failure state for otherwise valid R09/R05 values.
- `ai_screening_contract.py` exposes `validate_ai_screening_response(raw_response, criteria)`. Invalid raw model responses raise `AIScreeningContractError`; wrong local public argument types raise built-in `TypeError`. Successful validation returns the mapping in Criterion input order.
- `screening_profile.py` represents immutable saved `ScreeningProfileVersion` values and their non-empty, uniquely identified Criteria.
- The accepted Provider selection mechanism is the single current `AIProviderConfig` persisted and loaded by `AIProviderConfigStore`; a complete configuration supplies Provider, API key, base URL, and model.
- `llm_provider_runtime.py` exposes `LLMMessage`, `LLMCompletionRequest`, `LLMCompletionResult`, and `complete(config, request)`.
- `complete()` makes one non-streaming SDK completion call using the selected model. The existing client has `timeout=120.0` and `max_retries=0`; R03 adds no application retry or fallback.
- The accepted R03 completion failure boundary is `LLMRuntimeError`, including validated request/configuration failures, normalized Provider failures, and unusable completion responses.
- The raw response text available to R11 is `LLMCompletionResult.content`. An absent or unusable first completion response is normalized by R03 as a malformed-response runtime failure.
- `CandidateOcrDocument` is produced by the existing Candidate builder finalization lifecycle. Normal AM7 flow finalizes Candidate evidence upstream before any formal Candidate-level evaluation.
- R08 requires formal Candidate Evaluation to occur only after Candidate finalization, while R09 deliberately trusts the accepted lifecycle rather than adding another finalization gate.

These findings support a small local composition contract; they do not justify a second Provider registry, runtime router, Candidate readiness framework, retry layer, or Decision/Action mechanism.

## 6. In Scope

AM7-R11 includes only:

- the formal Candidate-level evaluation entry boundary;
- composition of accepted R09, R10, and R03 operations;
- exact Provider message projection;
- one formal Provider completion invocation;
- strict R10 response validation;
- exact `AIScreeningResult` construction;
- collapse of only the expected accepted formal-chain technical failures into the frozen failed result state;
- preservation of R06, R12, R13, and R14 ownership boundaries.

## 7. Non-Goals

AM7-R11 does not introduce or implement:

- OCR, Screen collection, Candidate construction, or Candidate finalization;
- Profile or Criterion authoring, mutation, selection UI, or persistence;
- Prompt authoring outside the accepted R10 builder;
- per-Screen, per-page, per-segment, or per-Criterion AI evaluation;
- request splitting, aggregation, voting, comparison, or multi-model evaluation;
- Rule evaluation or Candidate Decision;
- browser, UI, forwarding, rejection, or other production action;
- Provider registries, routing, model fallback, or Provider fallback;
- retry policy, degradation policy, stop conditions, or orchestration recovery;
- result persistence, replay, cache, hashes, digests, histories, or reproducibility metadata;
- confidence, explanations, evidence extraction, reasons, traces, or diagnostics frameworks.

## 8. Core Terms

- **Formal AI evaluation invocation**: one call to the R11 operation for one finalized Candidate and one saved formal Profile Version. Its invocation count is local to that call; R11 retains no memory of earlier or later calls for the same Candidate/Profile pair.
- **Formal Provider completion invocation**: the single call by R11 to the accepted Provider-neutral `complete()` operation. It is distinct from any transport-internal behavior, although the current accepted runtime performs one outbound SDK call and has retries disabled.
- **Usable Provider response**: a completion result whose content can be supplied as raw text to the R10 validator. Provider transport success alone does not make an R11 evaluation successful.
- **Expected technical failure**: a failure explicitly defined by an accepted stage of the formal chain and selected by this RPD for failed-result normalization: an accepted R09 source-content projection `ValueError` after valid Candidate identity is established, an R03 `LLMRuntimeError`, or an R10 `AIScreeningContractError`. It is not a negative screening decision. Programming defects and unexpected implementation exceptions are not expected technical failures.
- **Complete Boolean mapping**: the exact R10 mapping containing every expected Criterion ID once, no additional ID, and values whose actual type is Boolean.

## 9. Standard Runtime Chain

The only standard R11 product chain is:

```text
finalized CandidateOcrDocument
    + saved ScreeningProfileVersion
    + current complete AIProviderConfig
    -> R09 build_ai_candidate_input(...)
    -> AICandidateInput
    -> R10 build_ai_screening_prompt(...)
    -> AIScreeningPrompt
    -> exact SYSTEM / USER LLMCompletionRequest
    -> selected Provider and model through R03 complete(...)
    -> LLMCompletionResult.content
    -> R10 validate_ai_screening_response(...)
    -> complete Boolean mapping
    -> Candidate-associated AIScreeningResult
```

R11 may not replace any named accepted stage with a local duplicate.

## 10. Public Product Entry Boundary

The R11 product operation is conceptually:

```text
run_ai_screening(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> AIScreeningResult
```

The exact Python module placement and exception mechanics belong to TID, but the three explicit input responsibilities and the single returned result are frozen product semantics.

The caller supplies:

- one actual, already-finalized `CandidateOcrDocument` from the accepted Candidate lifecycle;
- one actual, valid, saved formal `ScreeningProfileVersion`;
- the current selected complete `AIProviderConfig` obtained through the accepted R03 configuration flow.

Candidate association originates from the source `CandidateOcrDocument`, not from a successful R09 output. Before projection, R11 establishes the exact existing `candidate.candidate_record_id` under the accepted R09 identity shape: it must be a string, and R11 adds no non-blank rule, UUID grammar, normalization, regeneration, prefix, suffix, or other identity semantic.

Wrong top-level public argument object types are API/entry-contract violations and use built-in `TypeError`; they are not normal Candidate-associated AI failures. If no actual Candidate object is supplied, its Candidate ID does not satisfy the accepted source identity shape, or Candidate identity otherwise cannot be established, R11 must not fabricate an ID, placeholder, empty substitute, or failed `AIScreeningResult`. Once valid source Candidate identity and the formal call boundary are established, only the expected accepted technical failures named by this RPD use the failed result semantics.

## 11. Candidate Finalization Boundary

R11 consumes a finalized Candidate; it does not finalize one. The accepted upstream lifecycle remains responsible for creating the immutable `CandidateOcrDocument` before R11 is invoked.

R11 must not add a `CandidateReadyGate`, finalization status enum, readiness scanner, guard, interceptor, or duplicate lifecycle check merely to restate this precondition. R09 projection remains the authoritative check for its own narrow source requirements, including non-blank authoritative Candidate document text.

## 12. Candidate-Level Evaluation Scope

One invocation of the formal R11 operation has exactly one Candidate and one Profile Version as its evaluation scope. R11 does not evaluate `OcrScreenRecord` values independently and does not use Screen boundaries to schedule, split, terminate, or combine model requests.

Under normal production orchestration, one Candidate should receive one formal R11 evaluation for the applicable Profile Version. R11 does not enforce that operational expectation with memory across separate API invocations. Repeated-invocation policy belongs to R13 or a later accepted orchestration contract.

This preserves the R08 contract:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

## 13. Profile Version Boundary

Each formal R11 evaluation uses exactly one already-saved immutable `ScreeningProfileVersion`. All Criteria sent to R10 Prompt construction and R10 response validation come from that same Profile Version.

R11 does not mutate the Profile, select or switch another Profile during evaluation, combine Profile Versions, or infer Criteria from Candidate evidence.

## 14. R09 Candidate Input Ownership

R11 must first retain the exact valid source `CandidateOcrDocument.candidate_record_id`, then invoke the accepted `build_ai_candidate_input(candidate)` operation. It must not read Screens to reconstruct Candidate text, normalize or deduplicate text again, trim successful text, synthesize a Candidate input, or introduce a parallel Candidate projection.

On successful projection, `AICandidateInput.candidate_record_id` must equal the already-established source Candidate ID exactly. That equality is an upstream compatibility invariant. Only `AICandidateInput.resume_text` enters the R10 model-visible Prompt.

If valid source Candidate identity is already established but R09 then raises its accepted `ValueError` because the source content cannot satisfy the output value contract—for example, `document_text` is `None`, empty, or whitespace-only—R11 retains the established source identity and may construct the Candidate-associated failed result without a successful `AICandidateInput`.

## 15. R10 Prompt Ownership

R11 must invoke the accepted `build_ai_screening_prompt(candidate_input, profile)` operation and consume the returned `AIScreeningPrompt` without changing its content.

R11 must not:

- recreate Prompt v1;
- prepend, append, translate, normalize, or otherwise modify either message;
- add model-visible Candidate, Profile, Provider, Rule, trace, or runtime data;
- override `prompt_version` or choose a different Prompt template.

Prompt construction and version identity remain owned by R10.

## 16. Provider and Model Selection

R11 reuses the existing current Provider configuration mechanism. The supplied complete `AIProviderConfig` is the sole source of Provider, API key, base URL, and model for the formal completion invocation.

R11 does not maintain a second current configuration, Provider registry, model registry, alias table, capability router, automatic selector, or fallback chain. An incomplete current configuration cannot produce a successful formal evaluation.

## 17. Exact Message Projection

R11 constructs one `LLMCompletionRequest` using the accepted R03 message types and exactly these two messages, in this order:

```text
1. LLMMessage(
       role = LLMMessageRole.SYSTEM,
       content = prompt.system_message,
   )
2. LLMMessage(
       role = LLMMessageRole.USER,
       content = prompt.user_message,
   )
```

There is no third message. R11 must not reverse the order, merge the messages, change their roles, or alter either content value.

## 18. Single Formal Provider Invocation

Within one invocation of the formal R11 operation for one Candidate and one Profile Version, R11 performs at most one formal Provider completion invocation. If pre-Provider projection cannot produce a valid Candidate input, the Provider is not invoked. If accepted pre-Provider stages succeed, R11 calls `complete(config, request)` exactly once.

R11 must not perform:

- one call per Screen, page, text segment, or Criterion;
- request splitting or continuation calls;
- repair, correction, or schema-retry calls;
- voting, consensus, self-review, or verifier calls;
- model comparison or Provider comparison;
- fallback calls to another model or Provider.

This is a per-evaluation-invocation constraint, not a cross-invocation identity or deduplication contract. R11 stores no `already_evaluated` state, request registry, evaluation ledger, persistent request key, deduplication cache, or duplicate-call guard. If a caller separately invokes `run_ai_screening(candidate, profile, config)` twice, R11 itself does not remember or suppress the second call.

## 19. Lower Runtime Retry Distinction

The R11 single-invocation rule counts calls from R11 to the accepted `complete()` operation within one formal R11 evaluation invocation. It neither redefines transport internals owned by the lower runtime nor adds cross-invocation deduplication.

At the inspected baseline, the lower R03 runtime has `max_retries=0`, makes one SDK completion call per `complete()` invocation, and defines no application-level retry or fallback. Therefore one current R11 formal invocation produces at most one outbound Provider completion call.

If lower-runtime retry behavior changes under an explicitly accepted later contract, it remains distinguishable from the count of R11 calls to `complete()`. R11 itself still may not add a retry, repair call, or repeated-execution policy.

## 20. Raw Response Boundary

The sole model business output consumed by R11 is the exact `LLMCompletionResult.content` returned by the accepted Provider runtime.

R11 supplies that value directly as `raw_response` to the R10 validator. It must not extract JSON through repair logic, strip code fences, rewrite keys or values, coerce types, fill omissions, discard additions, or otherwise transform the response before validation.

An absent or unusable response is a technical failure. The current R03 runtime normally exposes this as normalized malformed-response failure before a successful completion result is returned.

## 21. R10 Validation Ownership

R11 must validate the raw response using the accepted operation:

```text
validate_ai_screening_response(
    raw_response = completion.content,
    criteria = profile.criteria,
)
```

Only a successful R10 validation result is accepted as `criteria_results`. R11 must not implement a permissive parser, duplicate response validator, compatibility mode, response repair, partial validator, or all-false fallback.

## 22. AIScreeningResult Contract

The R11 result has exactly these product fields:

```text
AIScreeningResult
{
    candidate_record_id,
    ai_status,
    criteria_results
}
```

Field semantics:

- `candidate_record_id`: the exact Candidate identifier established locally from the valid source `CandidateOcrDocument` before R09 projection;
- `ai_status`: exactly `completed` or `failed`;
- `criteria_results`: the complete strict-Boolean R10 mapping when completed, otherwise `None`.

The result must not add Provider, model, Prompt version, raw response, timestamps, latency, token counts, finish reason, request ID, Profile identity/version, failure reason, confidence, explanation, evidence, Rule results, Decision, or Action fields.

## 23. Candidate Identifier Restoration

`candidate_record_id` is not model-visible under R10. R11 establishes and retains the exact valid identifier from the source `CandidateOcrDocument`, then places it in the final `AIScreeningResult` whether the owned chain completes or encounters an expected technical failure.

When R09 projection succeeds, its `AICandidateInput.candidate_record_id` must equal the established source identifier exactly. When R09 source-content projection fails after identity establishment, no `AICandidateInput` is required merely to preserve the association.

The identifier must not be transformed, replaced, inserted into Prompt messages, inferred from model output, or accepted from model output. If it cannot be established from the valid source Candidate at entry, no `AIScreeningResult` is fabricated.

## 24. Completed Semantics

`ai_status = completed` is valid only when all of the following are true:

1. valid source Candidate identity was established and R09 Candidate input projection succeeded with the same exact identifier;
2. R10 Prompt construction succeeded for valid accepted inputs;
3. the selected Provider returned a usable completion response through R03;
4. R10 validation of the exact raw response succeeded completely;
5. `criteria_results` is the complete validated mapping for the Profile Version's Criteria.

Provider transport success alone is insufficient. A syntactically or semantically invalid R10 response makes the formal evaluation failed, not completed.

## 25. Failed Semantics

`ai_status = failed` means the formal AI evaluation did not produce a complete validated R10 Boolean mapping.

For a failed result:

```text
criteria_results = None
```

Only the following expected accepted failures produce this result once valid source Candidate identity and the formal call boundary exist:

- the built-in `ValueError` emitted by the accepted R09 projection value contract for invalid source content after the Candidate ID has already been established, including `None`, empty, or whitespace-only authoritative Candidate document text;
- `LLMRuntimeError` emitted by the accepted R03 completion runtime, including unusable response failure;
- `AIScreeningContractError` emitted by the accepted R10 response validator for JSON, schema, Criterion-ID, completeness, uniqueness, or strict-Boolean failure.

The accepted R10 Prompt builder defines only built-in `TypeError` for wrong public argument object types and no normal runtime failure state for otherwise valid R09/R05 values. R11 therefore has no generic `prompt_failed` product category.

Programming defects, violated internal invariants, coding errors, unexpected missing attributes, and other exceptions not defined above as expected accepted technical failures must not be silently converted to `ai_status = failed`. R11 is not a generic exception-suppression boundary. The result does not expose or classify accepted failure causes; unexpected defects propagate through normal error behavior rather than being disguised as a product result.

## 26. Result State Invariants

The only valid state combinations are:

```text
ai_status = completed
criteria_results = complete validated dict[str, bool]

ai_status = failed
criteria_results = None
```

These combinations are invalid:

- `completed` with `None`;
- `completed` with an incomplete, extra-key, duplicate-key, non-Boolean, or otherwise invalid mapping;
- `failed` with any mapping, including an empty or all-false mapping;
- any status other than `completed` or `failed`.

## 27. Valid All-False Result

A complete R10-valid mapping in which every Criterion value is `false` is a successful AI evaluation:

```text
ai_status = completed
criteria_results = complete all-false mapping
```

This is model business data, not a technical failure and not yet a Candidate Decision.

## 28. No Technical-Failure-to-All-False Conversion

R11 must never convert an accepted R09 source-content projection failure, `LLMRuntimeError`, or `AIScreeningContractError` into an all-false mapping.

Each expected accepted technical failure is represented only as `failed` with `criteria_results = None`. Unexpected programming defects are not converted to either an all-false mapping or a failed product result.

## 29. No Partial Success

R11 has no partial result state. If even one expected Criterion result is missing or invalid, or any unexpected Criterion ID is present, the entire formal evaluation fails.

R11 must not return a subset, combine valid members with defaults, retain a partially parsed result, or mark the operation completed with partial data.

## 30. Determinism and Side Effects

R11 does not claim that a remote model will return identical output for repeated calls. The deterministic local contract is narrower:

- for the same accepted Candidate input, Profile Version, Provider completion content, and accepted upstream implementations, message projection and response validation yield the same local `AIScreeningResult`;
- R11 performs no persistence, Candidate mutation, Profile mutation, Rule evaluation, Decision, or Action as a side effect;
- result identity is derived from the valid source Candidate, while the mapping is derived only from the formal call's accepted local inputs and validated raw response;
- R11 retains no cross-invocation memory or deduplication state.

## 31. R06 Rule Engine Boundary

R11 does not execute `ScreeningRule`, `ScreeningRuleSet`, or `evaluate_rule_set()`. It does not interpret the Boolean mapping as qualification, rejection, exclusion, or any other Candidate outcome.

The complete mapping is intentionally compatible with the future R12 input boundary, where R06 evaluation may be composed under a separate Frozen contract.

## 32. R08 Authority Boundary

R11 operates at Candidate scope but does not itself hold Candidate Decision or production Action authority. Its output is a Candidate-associated AI evaluation result only.

Legacy Screen-level rule or confirmation outcomes cannot replace, short-circuit, or alter the formal R11 Candidate-level chain. R11 also does not modify Legacy BossOCR behavior.

## 33. No Candidate Decision

Neither `ai_status` nor any Boolean Criterion value is a Candidate Decision:

- `completed` means technical AI evaluation completion, not qualification;
- `failed` means technical evaluation failure, not rejection;
- `true` and `false` retain R10 Criterion semantics but are not final Candidate outcomes;
- an all-false mapping remains completed model business data.

R11 must not produce `qualified`, `rejected`, `excluded`, `accepted`, `forward`, `skip`, or equivalent Decision values.

## 34. No Production Action

R11 does not invoke browser, favorite, forward, next, refresh, email, UI, or any other production Action path. It does not add hooks, callbacks, event dispatch, gates, or action-ready wrappers.

## 35. R12 Boundary

AM7-R12 owns the next composition from the complete R11 Boolean mapping through the accepted R06 Rule Engine into Candidate Decision and subsequent production-action authority.

R11 must not pre-implement:

- mapping-to-RuleSet evaluation;
- Rule outcome interpretation;
- Candidate Decision construction;
- action selection or execution.

## 36. R13 Boundary

AM7-R13 owns retry and repeated-execution decisions, persistent technical-failure handling, degradation policy, operational stop conditions, and related orchestration behavior across formal R11 invocations.

R11 reports only `completed` or `failed` for an invocation that reaches the Candidate-associated result boundary. It does not retry, schedule or suppress a later invocation, remember earlier evaluations, count failures, persist failures, change Provider/model, degrade to another path, stop a Run, or decide whether execution may continue.

## 37. R14 Boundary

AM7-R14 owns replay, cache, hash/digest strategy, orchestration history, comparison, reproducibility records, and related metadata.

R11 does not persist Prompt or response content, compute a hash or digest, cache a result, create a replay envelope, record token/latency/provider metadata, or build a comparison/history schema.

## 38. No Fallback or Alternate Success Path

R11 has one success path: the standard accepted chain ending in full R10 validation. It has no alternate parser, local heuristic, Legacy-rule substitute, default Boolean result, second Provider, second model, or human/manual completion path.

If the standard chain encounters one of the expected accepted technical failures defined in §25, the formal result is failed. Unexpected implementation defects are not an alternate product path and are not hidden as failed results.

## 39. No Persistence, Replay, Hash, or Cache

R11's `AIScreeningResult` is an in-memory product result. This requirement introduces no store, table, file, schema revision, migration, retention policy, replay record, cache key, content hash, Prompt hash, Candidate hash, result digest, duplicate-evaluation registry, evaluation ledger, or cross-invocation guard.

## 40. Failure Handling Boundary

R11 normalizes only the expected accepted exception boundaries named in §25 into the exact failed result state: the accepted R09 source-content projection `ValueError` after source identity is established, R03 `LLMRuntimeError`, and R10 `AIScreeningContractError`. It does not replace those upstream contracts.

Wrong top-level public argument types remain built-in `TypeError` entry-contract violations. Prompt-builder `TypeError`, validator argument `TypeError`, programming defects, violated internal invariants, and unexpected implementation exceptions are not normal Candidate-associated AI failures.

TID may specify the smallest local `try/except` structure necessary to implement these exact semantic boundaries. It must catch only the specific expected accepted exceptions needed for the failed result and must not use a broad `except Exception` for convenience. It also must not introduce a general error taxonomy, recovery framework, failure event system, trace framework, wrapper hierarchy, or diagnostic schema.

## 41. Upstream Compatibility and Protected Semantics

R11 must preserve without modification:

- R03 configuration storage, Provider contracts, completion API, timeout, and retry behavior;
- R05 Criterion, Profile Version, immutability, and persistence contracts;
- R06 Rule and RuleSet types, parser, validation, and ANY evaluation;
- R07 Complete Scan and Candidate evidence behavior;
- R08 Candidate Decision authority boundary;
- R09 exact two-field Candidate input and document-text fidelity;
- R10 exact Prompt v1 and strict response validator;
- Legacy keyword, OCR, browser, and production-action behavior.

## 42. Product Invariants

1. One invocation of the formal R11 operation binds exactly one finalized Candidate and one saved formal Profile Version.
2. R11 uses exactly one accepted R09 Candidate input projection.
3. R11 uses exactly one accepted R10 Prompt construction.
4. R11 projects exactly two Provider messages: SYSTEM then USER, with exact R10 content.
5. Within one formal R11 invocation, R11 performs at most one formal Provider completion invocation and exactly one when accepted pre-Provider stages succeed.
6. The current accepted lower runtime performs no retry and no fallback.
7. R11 validates the exact Provider content through R10 without repair or coercion.
8. `AIScreeningResult` has exactly three fields and exactly two statuses.
9. `completed` always carries a complete valid mapping; `failed` always carries `None`.
10. A valid all-false mapping is completed; technical failure is never represented as all-false.
11. No partial success exists.
12. `candidate_record_id` originates from the valid source Candidate; successful R09 projection preserves it exactly, and it remains available for an R09 source-content failed result without becoming model-visible.
13. R11 does not execute R06, make a Candidate Decision, or trigger an Action.
14. Only the accepted R09 source-content `ValueError`, R03 `LLMRuntimeError`, and R10 `AIScreeningContractError` become failed product results; entry violations and unexpected defects do not.
15. R11 introduces no retry, fallback, persistence, replay, hash, cache, cross-invocation deduplication, or orchestration policy.
16. Normal orchestration expects one formal evaluation per applicable Candidate/Profile pair, while R13 owns whether a separate invocation occurs again.
17. Accepted upstream contracts remain authoritative and unmodified.

## 43. Acceptance Criteria

### AC-01 — Exact formal entry

The formal R11 product operation accepts one actual finalized `CandidateOcrDocument` with a source Candidate ID satisfying the accepted string shape, one actual saved `ScreeningProfileVersion`, and one current complete `AIProviderConfig`. Wrong top-level public argument object types raise built-in `TypeError`; unavailable source identity is an entry-contract violation, and neither case fabricates an `AIScreeningResult`.

### AC-02 — Finalization precondition

R11 consumes the Candidate only after accepted upstream finalization and does not introduce a Candidate readiness gate, lifecycle framework, or duplicate finalization operation.

### AC-03 — R09 projection reuse

R11 obtains `AICandidateInput` through the accepted R09 builder and does not reconstruct or independently normalize Candidate text.

### AC-04 — Candidate association

Candidate identity originates from the valid source `CandidateOcrDocument`. A successful R09 input preserves that exact source ID, and every Candidate-associated result uses that same unmodified source ID.

### AC-05 — One Profile Version

One formal evaluation uses Criteria from exactly one saved immutable `ScreeningProfileVersion` for both Prompt construction and response validation.

### AC-06 — R10 Prompt reuse

R11 obtains `AIScreeningPrompt` through the accepted R10 builder and does not recreate or modify Prompt v1.

### AC-07 — Candidate ID remains local

`candidate_record_id` remains local whether R09 succeeds or fails: it is not added to either Provider message or the model output schema and is not obtained from model output.

### AC-08 — Exact system-message mapping

The first Provider message uses `LLMMessageRole.SYSTEM` and exact `prompt.system_message` content.

### AC-09 — Exact user-message mapping

The second Provider message uses `LLMMessageRole.USER` and exact `prompt.user_message` content.

### AC-10 — Exact message sequence

The completion request contains exactly those two messages in SYSTEM-then-USER order and contains no third message.

### AC-11 — Existing configuration mechanism

R11 uses the current selected complete `AIProviderConfig` from the accepted R03 configuration flow and introduces no second configuration or registry.

### AC-12 — Exact Provider configuration use

Provider, API key, base URL, and model come from the supplied current configuration without R11 override, automatic selection, or substitution.

### AC-13 — Existing Provider API reuse

R11 uses the accepted `LLMMessage`, `LLMCompletionRequest`, and `complete(config, request)` Provider-neutral runtime contract.

### AC-14 — One formal completion invocation

Within one invocation of the formal R11 operation, accepted pre-Provider success causes exactly one `complete()` call; pre-Provider projection failure causes none. This AC does not require memory or suppression across separate R11 invocations.

### AC-15 — No per-Screen or per-page calls

Within one formal evaluation invocation, the number or content of underlying Screens or pages does not cause an additional Provider completion call.

### AC-16 — No per-Criterion or split calls

Within one formal evaluation invocation, the number of Criteria does not cause per-Criterion calls, request splitting, continuation calls, or response aggregation.

### AC-17 — No comparison or fallback calls

Within one formal evaluation invocation, R11 performs no voting, verifier, model comparison, Provider comparison, repair call, model fallback, Provider fallback, or retry call.

### AC-18 — Exact raw-response handoff

R11 passes exact `LLMCompletionResult.content` to the R10 validator without repair, fence stripping, coercion, filling, or rewriting.

### AC-19 — Exact validation Criteria

R11 validates the raw response against `profile.criteria` from the same Profile Version used to build the Prompt.

### AC-20 — Completed requires full chain success

R11 returns `completed` only after valid source identity establishment, successful R09 projection with the same ID, Prompt construction for valid inputs, usable Provider response, and complete R10 validation.

### AC-21 — Transport success is insufficient

A Provider call that returns content rejected with `AIScreeningContractError` produces `failed` with `criteria_results = None`, never `completed`; Provider transport success alone is insufficient.

### AC-22 — Exact failed payload

Each expected Candidate-associated failure named by the accepted R09/R03/R10 exception boundaries returns exact status `failed` and exact `criteria_results = None`. Entry-contract violations and unexpected programming defects are not silently normalized to this result.

### AC-23 — Candidate-input failure

After valid source Candidate identity is established, missing, empty, or whitespace-only authoritative document text raises the accepted R09 `ValueError` and yields `failed`, `None`, and the exact source Candidate ID even though no `AICandidateInput` was created. Invalid top-level Candidate input or unavailable valid source identity fabricates no result.

### AC-24 — Provider/runtime failure

An accepted R03 `LLMRuntimeError`, including normalized authentication, network, timeout, rate-limit, quota, invalid-request, unavailable-model, Provider-server, or malformed-response failure, yields the R11 failed result and no Boolean mapping.

### AC-25 — R10 contract failure

Malformed JSON, duplicate members, wrong top-level shape, wrong Criterion IDs, missing or extra IDs, or non-Boolean values raise `AIScreeningContractError` and yield the R11 failed result with no partial mapping. Validator argument `TypeError` or another unexpected defect is not normalized as a product failure.

### AC-26 — Two statuses only

`ai_status` accepts exactly `completed` or `failed`; R11 introduces no pending, retrying, degraded, rejected, or other status.

### AC-27 — Three result fields only

`AIScreeningResult` contains exactly `candidate_record_id`, `ai_status`, and `criteria_results`, with none of the explicitly deferred metadata fields.

### AC-28 — Completed mapping completeness

A completed result contains every expected Criterion ID exactly once, no unexpected ID, and values whose actual type is Boolean.

### AC-29 — Invalid combinations rejected

`completed` with `None` or invalid mapping, and `failed` with any mapping, are invalid result states.

### AC-30 — Valid all-false completion

A complete R10-valid all-false mapping produces `ai_status = completed` and preserves the complete all-false mapping.

### AC-31 — No synthetic all-false failure result

No technical failure is converted into an empty, defaulted, or all-false Boolean mapping.

### AC-32 — No partial success

R11 never returns a subset or partially valid Criteria mapping as a successful or failed result.

### AC-33 — No Decision status

R11 does not produce or imply qualified, rejected, excluded, accepted, forward, skip, or equivalent Candidate Decision semantics.

### AC-34 — R06 not executed

R11 does not invoke the R06 Rule Engine or interpret the Boolean mapping through a RuleSet.

### AC-35 — No production action

R11 does not invoke or modify browser, favorite, forward, next, refresh, email, UI, or any production Action behavior.

### AC-36 — No persistence

R11 introduces no result/configuration/Profile/Candidate persistence, database, file store, migration, or history record.

### AC-37 — Retry ownership preserved

R11 adds no retry and retains no cross-invocation deduplication state. Within one formal evaluation invocation, its at-most-one `complete()` call maps to at most one outbound SDK completion request at the accepted baseline because lower-runtime retries are disabled. Normal orchestration expects one applicable Candidate/Profile evaluation, while R13 owns retry and repeated-invocation decisions.

### AC-38 — No R14 capability

R11 introduces no replay, cache, hash, digest, orchestration history, comparison record, or reproducibility metadata.

### AC-39 — No deferred result metadata

The result contains no Provider/model/Prompt/raw-response/time/latency/token/request/Profile/failure/confidence/explanation/evidence/Rule/Decision/Action fields.

### AC-40 — Deterministic local projection

Given the same accepted formal inputs and the same Provider completion content, R11 produces the same local message projection, validation outcome, and `AIScreeningResult`, without claiming remote-model determinism.

### AC-41 — Accepted contracts protected

R03, R05, R06, R07, R08, R09, R10, Legacy keyword, OCR, browser, and action semantics remain unchanged by R11.

### AC-42 — Later ownership preserved

R12 retains Rule-to-Decision/action composition, R13 retains retry/repeated-execution/degradation/stop orchestration across invocations, and R14 retains replay/cache/history/reproducibility ownership; R11 pre-implements none of them.

## 44. Open Issues

None.

## 45. Contract Conflicts

None.

## 46. Final Product Contract Summary

AM7-R11 defines one narrow Candidate-level AI screening runtime composition. One invocation binds one finalized Candidate and one saved Profile Version, establishes exact Candidate identity from the valid source document, projects through accepted R09 and R10 contracts, submits exactly one SYSTEM message followed by one USER message through the current R03 Provider configuration, and performs at most one formal Provider completion invocation. Exact response content is accepted only through complete R10 validation. R11 retains no cross-invocation memory or deduplication state; R13 owns retry and repeated-execution orchestration.

Success returns the exact source Candidate identity, `completed`, and the complete strict-Boolean mapping. After identity is established, accepted R09 source-content `ValueError`, R03 `LLMRuntimeError`, or R10 `AIScreeningContractError` returns that identity, `failed`, and `None`; successful R09 projection is not required merely to retain the association. Invalid entry identity fabricates no result, and unexpected programming defects are not silently collapsed into `failed`. A valid all-false mapping is completed; expected technical failure is never represented as Boolean business data; partial success does not exist.

R11 does not execute R06, make a Candidate Decision, trigger an Action, retry, fall back, persist, replay, cache, hash, or pre-implement R12 through R14.
