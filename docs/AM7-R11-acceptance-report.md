# AM7-R11 — Final Automated Acceptance Report

## 1. Metadata

| Item | Value |
|---|---|
| Product | Ocria Am7 |
| Requirement | AM7-R11 — AI Screening Runtime |
| Acceptance type | Final automated acceptance |
| Requirement branch / declared baseline | `am7-r11-ai-screening-runtime` / `3b5c61066c8df2e2d4573394c0df5167193f4bf3` |
| Governing document | `CODEX-CONSTITUTION.md` |
| Acceptance date | 2026-08-22 (Asia/Shanghai) |

## 2. Acceptance Status

**Automated Acceptance Passed / Pending Human Final Review**

## 3. Requirement Scope

R11 composes one finalized Candidate, one saved Profile Version, and one supplied Provider configuration through R09 Candidate input, R10 Prompt construction, one SYSTEM/USER Provider request, and R10 response validation. It returns only the Candidate association, a completed/failed state, and a validated mapping or `None`.

## 4. Authoritative Documents

- `CODEX-CONSTITUTION.md`
- `docs/RPD-AM7-R11-ai-screening-runtime.md` v0.1 Frozen
- `docs/TID-AM7-R11-ai-screening-runtime.md` v0.1 Frozen

## 5. Final Implementation Scope

The final R11 implementation is one direct runtime module and one focused test module. It delegates Candidate input to R09, Prompt construction and Boolean validation to R10, and performs exactly the accepted R03 request projection without adding a framework or downstream Decision behavior.

## 6. Exact Changed/New File Scope

| Scope | File | Result |
|---|---|---|
| Frozen requirement document | `docs/RPD-AM7-R11-ai-screening-runtime.md` | Reviewed; not altered |
| Frozen requirement document | `docs/TID-AM7-R11-ai-screening-runtime.md` | Reviewed; not altered |
| New runtime | `ai_screening_runtime.py` | Present; reviewed |
| New focused test | `tests/test_ai_screening_runtime.py` | Present; reviewed |
| Acceptance output | `docs/AM7-R11-acceptance-report.md` | Created by this acceptance |

Existing runtime files modified: **None**.

Existing test files modified: **None**.

This scope conclusion is based on final target-file inspection and same-conversation Change 1/Change 2 evidence; no Git command was used during acceptance.

## 7. Public Runtime API

```python
@dataclass(frozen=True)
class AIScreeningResult:
    candidate_record_id: str
    ai_status: Literal["completed", "failed"]
    criteria_results: dict[str, bool] | None

def run_ai_screening(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> AIScreeningResult:
```

No alternate R11 source API, raw-text shortcut, Screen input, Criterion-only input, override, retry, or persistence parameter exists.

## 8. AIScreeningResult Representation

`AIScreeningResult` is frozen and has exactly three fields in this order: `candidate_record_id`, `ai_status`, and `criteria_results`. It has no Provider/model/Prompt/raw-response/time/token/request/Profile/failure/confidence/evidence/Rule/Decision/Action field.

## 9. Result Constructor Invariants

The local `__post_init__` rejects non-string IDs, third statuses, completed with `None`, completed with an empty dict, non-string mapping keys, non-Boolean mapping values, and failed with any mapping. It does not perform Profile-specific R10 completeness validation and it passes a completed mapping by reference without copying.

## 10. Entry Type Boundary

`run_ai_screening(...)` performs the three Frozen `isinstance` checks first. Wrong Candidate, Profile, or Config object types raise built-in `TypeError`; they do not create failed results or invoke the Provider.

## 11. Candidate Identity Establishment

R11 reads `candidate.candidate_record_id` before R09 projection and requires only a string. It introduces no non-blank rule, UUID grammar, normalization, generated fallback, or transformation. The established source value is the exact association used for all R11 results.

## 12. R09 Projection

The runtime invokes exactly `build_ai_candidate_input(candidate)` and otherwise does not construct `AICandidateInput`, read Screens, reconstruct text, aggregate OCR, normalize text, or deduplicate content.

## 13. R09 ValueError Boundary

Only the R09 builder call is enclosed in `except ValueError`. An accepted source-content failure returns exact source ID + `failed` + `None`, and makes zero Provider calls. R09 top-level `TypeError` and unexpected defects are outside this boundary.

## 14. Prompt Construction

After successful R09 projection, R11 invokes exactly `build_ai_screening_prompt(candidate_input, profile)` outside all expected-failure catches. It neither copies nor modifies Human Prompt v1, serialization, message content, Candidate identity, Profile metadata, Rule data, or prompt version.

## 15. Exact Provider Message Projection

The request contains exactly two `LLMMessage` values: first `LLMMessageRole.SYSTEM` with exact `prompt.system_message`, then `LLMMessageRole.USER` with exact `prompt.user_message`. No assistant, prefill, third message, or metadata message exists.

## 16. LLMCompletionRequest Construction

R11 constructs only `LLMCompletionRequest(messages=messages)`. It adds no temperature, token policy, response format, structured output setting, timeout, retry, streaming, or metadata field.

## 17. Provider Config Handling

The exact supplied `AIProviderConfig` object is passed to `complete(config, request)` by identity. R11 does not load a config Store, clone/rebuild config, override Provider/model/key/base URL, or create a selector, registry, router, or fallback chain.

## 18. Single Formal Invocation

R09 failure makes zero `complete()` calls. A successful pre-Provider path makes exactly one. Provider and R10 contract failures make no retry, repair, fallback, verification, voting, or second request. No loop surrounds `complete()`.

## 19. Multiple-Criteria Behavior

The three-Criterion Profile fixture produces one complete request and exactly one Provider call. R11 does not split or issue per-Criterion calls.

## 20. Multiple-Screen Behavior

A real finalized Candidate built from two Screens produces one Candidate-level R11 invocation and exactly one Provider call. R11 has no Screen-aware input or request logic.

## 21. No Cross-Invocation Deduplication

The runtime has no mutable registry, ledger, cache, request key, or duplicate-call guard. Two explicit same-input calls each invoke the patched Provider once, for a total of two calls.

## 22. LLMRuntimeError Boundary

Only the single Provider call is enclosed in `except LLMRuntimeError`. That expected R03 failure returns source ID + `failed` + `None`, with no error-code interpretation, retry, Provider/model switch, or failure subtype. Plain `RuntimeError` propagates.

## 23. Raw Response Handoff

The exact unaltered `completion.content` string is passed to R10. Focused capture evidence uses whitespace and fence-like content and confirms no `.strip()`, extraction, fence removal, parsing, repair, normalization, coercion, or fallback occurs in R11.

## 24. R10 Validator Handoff

R11 calls `validate_ai_screening_response(raw_response=completion.content, criteria=profile.criteria)` using the same Profile Version as Prompt construction. The validator-returned mapping is sent unchanged to completed construction.

## 25. AIScreeningContractError Boundary

Only the validator call is enclosed in `except AIScreeningContractError`. A contract failure returns source ID + `failed` + `None`; it retains no partial/empty/all-false mapping and makes no repair or second Provider call. Validator `TypeError` propagates.

## 26. Unexpected Exception Propagation

There is no `except Exception` or `except BaseException`. Entry `TypeError`, source identity `ValueError`, unexpected Prompt exception, Provider plain `RuntimeError`, validator `TypeError`, and programming defects are not silently converted into failed values.

## 27. Completed Result Construction

Only a complete R10 validation return constructs `AIScreeningResult(source_id, "completed", criteria_results)`. Valid mixed, all-true, and all-false mappings are completed and retain exact strict Boolean mappings.

## 28. Failed Result Construction

Only the accepted R09 source-content `ValueError`, R03 `LLMRuntimeError`, and R10 `AIScreeningContractError` boundaries construct `AIScreeningResult(source_id, "failed", None)`. Failed values contain no mapping, reason, subtype, exception, Provider/model, or metadata.

## 29. Valid All-False Semantics

A complete all-false R10 mapping remains `completed` with its exact mapping. R11 does not equate false business outcomes with a technical failure or Candidate Decision.

## 30. No Synthetic All-False

Every expected technical failure returns `failed` plus `None`, never `{}`, a defaulted mapping, or an all-false mapping.

## 31. No Partial Success

An incomplete R10 response, malformed result, unknown/duplicate/missing Criterion, or other contract violation yields `failed` plus `None`. No valid subset or partially successful mapping escapes.

## 32. Local Determinism

Given identical accepted local inputs and identical mocked completion content, two explicit R11 calls yield value-equal local results. This verifies local deterministic projection, not remote-model determinism.

## 33. R06 / R12 Boundary

R11 stops at its validated Boolean mapping. It does not import or execute `evaluate_rule_set`, `ScreeningRuleSet`, or Candidate Decision logic. R12 retains Boolean-to-Rule-to-Decision-to-Action composition.

## 34. R13 Boundary

R11 implements no retry, retry schedule, repeated-call policy, cross-call deduplication, degradation, failure persistence, stop condition, Provider switch, or model switch. Repeated-invocation decisions remain later orchestration ownership.

## 35. R14 Boundary

R11 implements no replay, cache, hash, digest, history, raw-response/Prompt persistence, token/latency logging, comparison, or reproducibility record.

## 36. No Production Action

R11 imports or calls no favorite, forward, skip, next, refresh, browser, `pyautogui`, `simple_brush`, UI callback, or other production action behavior.

## 37. R01–R37 Individual Mapping

| Responsibility | Implementation evidence | Verification evidence | Result |
|---|---|---|---|
| R01 | Complete validator mapping goes to completed result | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R02 | Exact validator all-true mapping is unchanged | `test_all_true_and_all_false_are_completed_results` | Pass |
| R03 | Exact validator all-false mapping is completed | `test_all_true_and_all_false_are_completed_results` | Pass |
| R04 | Source ID establishes R09/R11 association | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R05 | SYSTEM then USER message construction | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R06 | Prompt strings are assigned directly to messages | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R07 | Request tuple has exactly two messages | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R08 | `complete()` receives identical Config object | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R09 | Successful evaluation makes one call | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R10 | Multiple Criteria do not split calls | `test_multiple_criteria_and_multiple_screens_still_make_one_call` | Pass |
| R11 | Multiple Screens do not split calls | `test_multiple_criteria_and_multiple_screens_still_make_one_call` | Pass |
| R12 | Real missing R09 text returns failed/None/source ID | `test_r09_value_error_returns_failed_without_provider_call` | Pass |
| R13 | R09 failure invokes no Provider | `test_r09_value_error_returns_failed_without_provider_call` | Pass |
| R14 | Exact `LLMRuntimeError` returns failed/None | `test_llm_runtime_error_returns_failed_after_one_provider_call` | Pass |
| R15 | Exact `AIScreeningContractError` returns failed/None | `test_explicit_contract_error_boundary_returns_failed` | Pass |
| R16 | Transport success plus real invalid R10 content fails | `test_contract_failures_return_failed_without_synthetic_or_partial_mapping` | Pass |
| R17 | Technical failure never creates all-false mapping | R09/R03/R10 failure tests | Pass |
| R18 | Incomplete result has no retained subset | `test_contract_failures_return_failed_without_synthetic_or_partial_mapping` | Pass |
| R19 | Wrong Candidate type raises TypeError | `test_entry_type_and_invalid_source_identity_errors_propagate` | Pass |
| R20 | Wrong Profile type raises TypeError | `test_entry_type_and_invalid_source_identity_errors_propagate` | Pass |
| R21 | Wrong Config type raises TypeError | `test_entry_type_and_invalid_source_identity_errors_propagate` | Pass |
| R22 | Non-string source ID raises ValueError/no result | `test_entry_type_and_invalid_source_identity_errors_propagate` | Pass |
| R23 | Real R09 projection preserves source ID | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R24 | Candidate ID absent from two message contents | `test_completed_mixed_result_preserves_identity_and_provider_request` | Pass |
| R25 | Completed mapping invariant | `test_result_constructor_has_only_frozen_state_invariants` | Pass |
| R26 | Failed has None and rejects mapping | `test_result_constructor_has_only_frozen_state_invariants` | Pass |
| R27 | Exact fields/statuses only | `test_result_constructor_has_only_frozen_state_invariants` | Pass |
| R28 | Unexpected Provider RuntimeError propagates | `test_unexpected_provider_and_prompt_exceptions_propagate` | Pass |
| R29 | Unexpected Prompt RuntimeError propagates | `test_unexpected_provider_and_prompt_exceptions_propagate` | Pass |
| R30 | Validator TypeError propagates | `test_validator_type_error_propagates_and_raw_content_is_unchanged` | Pass |
| R31 | Exact content and Profile criteria handoff | `test_validator_type_error_propagates_and_raw_content_is_unchanged` | Pass |
| R32 | No strip/repair of raw content | `test_validator_type_error_propagates_and_raw_content_is_unchanged` | Pass |
| R33 | Repeated local calls give equal values | `test_local_results_are_deterministic_without_cross_invocation_deduplication` | Pass |
| R34 | No R06 runtime dependency | `test_runtime_has_no_r06_or_browser_action_dependencies` | Pass |
| R35 | No browser/action dependency | `test_runtime_has_no_r06_or_browser_action_dependencies` | Pass |
| R36 | Contract failure does not make second call | `test_contract_failures_return_failed_without_synthetic_or_partial_mapping` | Pass |
| R37 | No cross-call deduplication | `test_local_results_are_deterministic_without_cross_invocation_deduplication` | Pass |

Result: **R01–R37 Pass**.

## 38. Focused Test Results

Change 2 final-state evidence was reviewed and reused because the runtime/test files have not changed afterward. Command previously run exactly:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ai_screening_runtime -v
```

Result: **13 / 13 tests passed**.

## 39. Compile Result

Change 2 final-state evidence was reviewed and reused. The Frozen compile command passed:

```powershell
.\venv\Scripts\python.exe -m compileall ai_screening_runtime.py tests\test_ai_screening_runtime.py
```

Result: **Passed**.

## 40. Protected Scope Review

Final R11 review found only focused R11 runtime/test artifacts plus this required report. R11 uses accepted R03, R05, R09, and R10 public values without modifying their files or semantics. No Provider configuration, OCR/Candidate, Rule Engine, browser/action, Store/persistence, dependency, packaging, or prior Requirement document/report was modified by R11 implementation or this acceptance.

## 41. AC-01–AC-42 Individual Mapping

| AC | Requirement | Implementation evidence | Verification evidence | Result |
|---|---|---|---|---|
| AC-01 | Exact formal entry and error boundary | Ordered `isinstance` checks; source-ID shape check | R19–R22 tests | Pass |
| AC-02 | Consume finalized Candidate only | Actual finalized Candidate fixture; no lifecycle logic | R01/R11 fixture and source review | Pass |
| AC-03 | Reuse R09 projection | Direct `build_ai_candidate_input(candidate)` call | R04, R12–R13, R23 | Pass |
| AC-04 | Exact Candidate association | Source ID retained across all result paths | R04, R12, R14–R16, R23 | Pass |
| AC-05 | One Profile Version | Same `profile` supplies Prompt and validator criteria | R31 capture; source review | Pass |
| AC-06 | Reuse R10 Prompt | Direct builder call, no Prompt text/serialization code | R05–R07; R29 | Pass |
| AC-07 | Candidate ID remains local | Only source/result field; absent message contents | R12, R24 | Pass |
| AC-08 | Exact system mapping | First `LLMMessage` uses SYSTEM/source string | R05–R06 | Pass |
| AC-09 | Exact user mapping | Second `LLMMessage` uses USER/source string | R05–R06 | Pass |
| AC-10 | Exact message sequence | Two-message tuple only | R05–R07 | Pass |
| AC-11 | Existing configuration mechanism | Direct supplied Config, no Store/registry | R08; source review | Pass |
| AC-12 | Exact config use | `complete(config, request)` unchanged | R08 | Pass |
| AC-13 | Existing Provider API reuse | R03 value types and `complete` imported | R05–R09; source review | Pass |
| AC-14 | One formal completion invocation | One direct call and narrow failure branches | R09–R13, R36–R37 | Pass |
| AC-15 | No per-Screen calls | No Screen logic/loop | R11 | Pass |
| AC-16 | No per-Criterion calls | One request for multiple Criteria | R10 | Pass |
| AC-17 | No comparison/fallback/retry calls | No loop/fallback code | R14–R18, R36; source review | Pass |
| AC-18 | Exact raw-response handoff | Direct `completion.content` validator argument | R31–R32 | Pass |
| AC-19 | Exact validation Criteria | Direct `profile.criteria` argument | R31 | Pass |
| AC-20 | Completed requires full chain success | Completed return follows validator only | R01–R03, R20 | Pass |
| AC-21 | Transport success insufficient | Real R10-invalid completion returns failed | R16, R18, R36 | Pass |
| AC-22 | Exact failed payload | Three narrow catches return failed/None | R12–R18 | Pass |
| AC-23 | Candidate-input failure | Real missing authoritative text path | R12–R13 | Pass |
| AC-24 | Provider/runtime failure | Narrow `LLMRuntimeError` catch | R14 | Pass |
| AC-25 | R10 contract failure | Narrow contract catch; TypeError propagation | R15–R18, R30 | Pass |
| AC-26 | Two statuses only | Literal values and constructor rejection | R27 | Pass |
| AC-27 | Three result fields only | Exact frozen dataclass fields | R27 | Pass |
| AC-28 | Completed mapping completeness | Successful return only from R10 validator | R01–R03, R25 | Pass |
| AC-29 | Invalid combinations rejected | Local constructor invariants | R25–R27 | Pass |
| AC-30 | Valid all-false completion | Direct complete all-false path | R03, R17 | Pass |
| AC-31 | No synthetic all-false result | Expected failure result always `None` | R12–R18 | Pass |
| AC-32 | No partial success | R10 contract error returns `None` | R16–R18, R36 | Pass |
| AC-33 | No Decision status | Only two statuses/no Decision import | R27; source review | Pass |
| AC-34 | R06 not executed | No Rule Engine import/call | R34 | Pass |
| AC-35 | No production action | No action/browser import/call | R35 | Pass |
| AC-36 | No persistence | Focused local module only | Source/scope review | Pass |
| AC-37 | Retry ownership preserved | One call per invocation, no cross-state | R09–R11, R36–R37 | Pass |
| AC-38 | No R14 capability | No replay/cache/hash/history code | Source/scope review | Pass |
| AC-39 | No deferred result metadata | Exact three-field dataclass | R27; representation review | Pass |
| AC-40 | Deterministic local projection | Direct deterministic sequence | R33 | Pass |
| AC-41 | Accepted contracts protected | New focused file scope only | Protected-scope review | Pass |
| AC-42 | Later ownership preserved | No R12–R14 runtime capability | Sections 33–36; source review | Pass |

Result: **42 / 42 Pass**.

## 42. Deviations

None.

## 43. Open Issues

None.

## 44. Contract Conflicts

None.

## 45. Final Automated Conclusion

All final R11 runtime/test artifacts conform to Frozen RPD/TID v0.1. The Human-independent runtime composition, exact narrow failure boundaries, single invocation behavior, protected upstream interfaces, and deferred R12–R14 ownership are verified. All R01–R37 responsibilities and AC-01–AC-42 individually pass. **Automated Acceptance Passed / Pending Human Final Review**.
