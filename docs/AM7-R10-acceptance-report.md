# AM7-R10 — Final Automated Acceptance Report

## 1. Metadata

| Item | Value |
|---|---|
| Product | Ocria Am7 |
| Requirement | AM7-R10 — AI Screening Boolean Contract |
| Acceptance type | Final automated acceptance |
| Requirement branch / declared baseline | `am7-r10-ai-screening-boolean-contract` / `bd4c18573fc4c43b3c67f9a71b59cc4f55d63f21` |
| Governing document | `CODEX-CONSTITUTION.md` |
| Acceptance date | 2026-08-21 (Asia/Shanghai) |

## 2. Acceptance Status

**Automated Acceptance Passed / Pending Human Final Review**

## 3. Requirement Scope

R10 owns deterministic Prompt v1 construction from one R09 `AICandidateInput` and one R05 `ScreeningProfileVersion`, plus strict validation of an already-obtained raw AI response into `dict[str, bool]`. It does not execute an LLM, RuleSet, Decision, action, persistence, replay, or OCR behavior.

## 4. Authoritative Documents

- `CODEX-CONSTITUTION.md`
- `docs/RPD-AM7-R10-ai-screening-boolean-contract.md` v0.1 Frozen
- `docs/TID-AM7-R10-ai-screening-boolean-contract.md` v0.1 Frozen

## 5. Final Implementation Scope

The completed R10 implementation contains two focused runtime modules and two focused unit-test modules. The final Human-approved Prompt v1 asset is present in the Prompt module; strict duplicate-aware response validation is present in the contract module.

## 6. Exact Changed/New File Scope

| Scope | File | Result |
|---|---|---|
| Frozen requirement document | `docs/RPD-AM7-R10-ai-screening-boolean-contract.md` | Reviewed; not altered |
| Frozen requirement document | `docs/TID-AM7-R10-ai-screening-boolean-contract.md` | Reviewed; not altered |
| New runtime | `ai_screening_prompt.py` | Present; reviewed |
| New runtime | `ai_screening_contract.py` | Present; reviewed |
| New focused test | `tests/test_ai_screening_prompt.py` | Present; reviewed |
| New focused test | `tests/test_ai_screening_contract.py` | Present; reviewed |
| Acceptance output | `docs/AM7-R10-acceptance-report.md` | Created by this acceptance |

Existing runtime files modified: **None**.

Existing test files modified: **None**.

This scope conclusion is based on the final target-file inspection and the same-conversation Change 1, Human Injection, and Change 2 implementation evidence; no Git command was used during acceptance.

## 7. Prompt Construction Runtime API

```python
def build_ai_screening_prompt(
    candidate_input: AICandidateInput,
    profile: ScreeningProfileVersion,
) -> AIScreeningPrompt:
```

The builder requires actual R09/R05 values and raises built-in `TypeError` for an incorrect public argument object type.

## 8. AIScreeningPrompt Representation

`AIScreeningPrompt` is a frozen dataclass with exactly these fields, in order:

1. `system_message`
2. `user_message`
3. `prompt_version`

The first two fields are the conceptual model-visible system and user messages. `prompt_version` is local metadata, not a third model-visible message.

## 9. Prompt v1 Exact Fidelity

The final `system_message` directly equals the Human-approved Prompt v1 test-owned exact literal. Focused Prompt evidence confirms byte-for-value string equality without normalization, stripping, hashing, digesting, or semantic-only comparison. It begins with `你是 Ocria 的候选人筛选判定器。` and ends with `}`.

## 10. Placeholder Absence

The production Prompt source and final runtime value do not contain `__OCRIA_AM7_R10_PROMPT_V1_PLACEHOLDER__`. The static Human-approved asset is present instead.

## 11. PROMPT_VERSION

`PROMPT_VERSION == "v1"`, and the builder assigns that exact value to `AIScreeningPrompt.prompt_version`. It is absent from model-visible dynamic payload data and from the raw response contract.

## 12. Exact Message Role Packaging

R10 packages exactly two conceptual messages in order: `system_message`, then `user_message`. It creates no assistant prefill, third/few-shot message, Candidate-identity message, hidden business-context message, Provider message type, or completion request.

## 13. Exact User Payload

The User Message payload is exactly:

```json
{
  "criteria": [
    {
      "criterion_id": "<exact Criterion ID>",
      "criterion_text": "<exact Criterion text>"
    }
  ],
  "resume_text": "<exact R09 resume_text>"
}
```

Top-level construction order is `criteria`, then `resume_text`. Each Criterion object order is `criterion_id`, then `criterion_text`. The array preserves `profile.criteria` order and source values are assigned directly.

## 14. Exact User Serialization

The implementation uses:

```python
json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
```

There is no key sorting, pretty printing, manual JSON concatenation, wrapper, text normalization, or custom delimiter. Focused evidence confirms compact deterministic output, readable Unicode, and exact JSON round-trip fidelity for quotes, newlines, and backslashes.

## 15. Model-Visible Dynamic Data Boundary

Only exact Criterion IDs/text and R09 `resume_text` appear in the User payload. It excludes `candidate_record_id`, Profile ID/version/digest, `rule`, RuleSet data, `prompt_version`, Provider/model, trace, persistence, replay, and other metadata. The system prompt remains static and contains no Candidate/Profile dynamic value.

## 16. R09 Candidate Input Boundary

The Prompt builder imports actual `AICandidateInput` and reads only `candidate_input.resume_text`. It does not import `CandidateOcrDocument`, Screens, OCR boxes/segments, Legacy data, or reconstruction logic. Candidate identity remains outside Prompt v1 model-visible dynamic content.

## 17. R05 Criteria Boundary

The Prompt builder imports actual `ScreeningProfileVersion`, iterates the authoritative `profile.criteria` tuple in order, and copies exact `criterion_id`/`criterion_text` values. It does not change Criterion grammar, text, fixed `must_match` rule, Profile version semantics, or `criteria_digest`.

## 18. Validator Runtime API

```python
def validate_ai_screening_response(
    raw_response: str,
    criteria: tuple[Criterion, ...],
) -> dict[str, bool]:
```

It accepts a non-empty tuple of actual `Criterion` values and returns an input-ordered plain dictionary only after complete validation.

## 19. Failure Representation

`AIScreeningContractError(ValueError)` is the one local raw-response contract failure type. Invalid public input object types use built-in `TypeError`. There is no error hierarchy, status enum, `ai_failed` state, partial-result value, warning wrapper, retry classification, or action consequence.

## 20. Strict JSON Parsing

The validator calls standard-library `json.loads()` on the complete raw response. It allows JSON grammar whitespace around one value and rejects prose prefix/suffix, Markdown fences, malformed JSON, multiple values, `NaN`, `Infinity`, and `-Infinity`. It performs no extraction, repair, retry, or best-effort parsing.

## 21. Duplicate JSON Member Detection

A private `object_pairs_hook` builds dictionaries while rejecting repeated member names at every object depth. It raises `AIScreeningContractError` rather than allowing normal `json.loads()` duplicate-key collapse. Focused evidence covers duplicate top-level and result-item members.

## 22. Exact Schema Validation

Successful input must be an exact top-level `dict` with only `criteria_results`; that value must be an exact `list`; every item must be an exact `dict` with only `criterion_id` and `passed`; and `criterion_id` must be an exact `str`. Extra or missing members and all alternative top-level/item shapes fail.

## 23. Strict Boolean Validation

The exact check is `type(passed) is bool`. Strings, integers, floats, `null`, objects, arrays, and other truthy/falsy substitutes fail without coercion. Mixed, explicit all-true, and explicit all-false strict-Boolean responses succeed when otherwise complete and valid.

## 24. Criterion Identity Validation

Expected IDs are read exactly from the supplied Criteria tuple. Returned IDs undergo no strip, case conversion, zero-padding, aliasing, fuzzy matching, repair, or normalization. Unknown, differently cased, whitespace-padded, and rewritten IDs fail.

## 25. Completeness / Uniqueness Validation

The validator rejects duplicate returned IDs and requires `set(returned_results) == set(expected_ids)`. Missing and unknown IDs fail; no unknown ID is discarded and no missing ID is filled. A successful mapping contains every authoritative ID exactly once.

## 26. Reordered Result Semantics

Raw array position is non-authoritative. A complete unique reordered response succeeds, and the returned dictionary is reconstructed in authoritative input-Criteria order. No positional Criterion meaning is introduced.

## 27. Valid All-False Business Result

An explicitly complete response whose `passed` values are all JSON `false` is accepted as a valid business result. It remains distinct from a technical response-contract failure.

## 28. No-All-False Degradation

JSON, duplicate-member, schema, Boolean, identity, uniqueness, and completeness failures raise `AIScreeningContractError`; none becomes a synthesized all-false mapping.

## 29. No-Partial-Success

Success construction occurs only after the entire response validates. An invalid item, unknown/duplicate ID, or missing required ID raises and no valid subset, warning-bearing value, or partial mapping escapes.

## 30. Validated Result Representation

Each successful value is a plain `dict[str, bool]` containing only all authoritative Criterion IDs in input order and strict Boolean values. It contains no Candidate, Profile, Prompt, Provider, reason/evidence/confidence, hash, timestamp, persistence, or cache identity.

## 31. R06 Compatibility / Non-Execution

The plain validated mapping is directly accepted by R06's `Mapping[str, bool]` boundary in one narrow compatibility test. R10 production modules do not import `screening_rule_engine`, execute `evaluate_rule_set`, parse Rules, or produce a Rule outcome.

## 32. Determinism

The same Candidate/Profile values produce value-equal prompts. The same Criteria/raw response produces an equal input-ordered mapping or the same failure type/behavior. No time, randomness, environment, current Screen, or Legacy state is read.

## 33. Side-Effect Review

The modules perform only local JSON/data construction and validation. They have no network, Provider, filesystem runtime read, database/Store, persistence, browser, mouse, action, retry, or sleep behavior. Focused tests confirm Candidate/Profile/Criterion inputs are unchanged.

## 34. R08 Candidate-Level Boundary

R10 operates after R09 on Candidate-level resume content. It has no Screen input, per-Screen AI evaluation, Screen-level Match/Reject behavior, or production Decision authority. The binding constraint remains: `Screen = Evidence Scope`; `Candidate = Ocria Am7 Production Decision Scope`.

## 35. R11 Non-Implementation

No Provider/model selection, completion request, actual LLM call, timeout, retry, streaming, or structured-output execution exists in R10.

## 36. R12 Non-Implementation

No production RuleSet integration, Candidate Decision, Match/Reject, favorite, forward, skip, or action behavior exists in R10.

## 37. R13 Non-Implementation

No AI/Evaluation persistence, failure degradation, durable retry, runtime status, or stop policy exists in R10.

## 38. R14 Non-Implementation

No replay, cache identity, orchestration, comparison infrastructure, or hash-based reproducibility capability exists in R10.

## 39. No-Hash Review

R10 creates no prompt, response, Candidate, Criteria, or result hash/digest/cache key. Existing R05 `criteria_digest` is not recalculated or model-visible. Prompt identity is the literal `prompt_version = "v1"`.

## 40. No-Extra-Framework Review

The implementation adds only the Frozen focused Prompt value/builder, response error/validator, and focused tests. No Prompt manager/registry/strategy, generic schema/validator/Evaluation framework, Guard, Gate, Scanner, or Wrapper is present.

## 41. Prompt Test Results

Change 2 final-Human-injected focused evidence was reviewed and reused because the final runtime/test files were unchanged afterward. Command previously run exactly:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ai_screening_prompt -v
```

Result: **6 / 6 tests passed**.

| Frozen cases | Evidence |
|---|---|
| P01–P03 | Version, placeholder absence, direct exact Human Prompt equality, first/final character, no leading/trailing newline |
| P04–P05 | Two-message packaging; static system message without Candidate/Profile values |
| P06–P10 | Exact User shape/key orders and authoritative Criterion order |
| P11–P14 | Resume/Criteria fidelity, Unicode, compact deterministic serialization |
| P15–P18 | Candidate/Profile/Rule/prompt-version dynamic-data exclusions |
| P19–P20 | Determinism and input immutability |

Result: **P01–P20 Pass**.

## 42. Validator Test Results

Change 2 final-Human-injected focused evidence was reviewed and reused. Command previously run exactly:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ai_screening_contract -v
```

Result: **14 / 14 tests passed**.

| Frozen cases | Evidence |
|---|---|
| V01–V05 | Mixed/all-true/all-false success, reordering, JSON whitespace |
| V06–V12 | Full-input JSON failures and duplicate JSON member rejection |
| V13–V20 | Exact top-level/item schema failures |
| V21–V26, V41 | Strict Boolean rejection and exact successful `bool` values |
| V27–V34 | Exact ID, unknown/missing/duplicate/case/space/rewritten failure, complete mapping |
| V35–V38 | No all-false degradation and no partial success |
| V39–V40 | Deterministic success/failure behavior |
| V42–V44 | R06 Mapping compatibility, no R06 runtime dependency, no Provider/network dependency |

Result: **V01–V44 Pass**.

## 43. Public Argument Type Tests

Focused evidence confirms built-in `TypeError` for wrong Prompt builder Candidate/Profile inputs, non-string `raw_response`, list criteria, empty criteria tuple, and tuples containing non-`Criterion` values.

## 44. Non-JSON Constant Rejection

Focused evidence confirms `NaN`, `Infinity`, and `-Infinity` each raise `AIScreeningContractError` through the private `parse_constant` rejection path.

## 45. Compile Result

Change 2 final evidence was reviewed and reused. The Frozen compile command passed:

```powershell
.\venv\Scripts\python.exe -m compileall ai_screening_prompt.py ai_screening_contract.py tests\test_ai_screening_prompt.py tests\test_ai_screening_contract.py
```

Result: **Passed**.

## 46. Protected Scope Review

Final R10 review found only the focused R10 runtime/test artifacts plus this required acceptance report. R10 runtime imports only the required R09/R05 types and standard-library JSON/dataclass support; no protected upstream runtime, Provider, OCR, Store, browser/action, dependency, packaging, or prior requirement document was modified by R10 implementation or this acceptance.

## 47. AC-01–AC-45 Individual Mapping

| AC | Requirement | Implementation evidence | Verification evidence | Result |
|---|---|---|---|---|
| AC-01 | Actual R09/R05 semantic inputs | Actual typed builder signature and direct fields | P06, P10–P12; signature review | Pass |
| AC-02 | Only R09 resume content | Prompt builder reads only `resume_text` | P11, P15–P17; import review | Pass |
| AC-03 | Candidate identity excluded from model content | Exact User payload exclusions | P15, P18; payload review | Pass |
| AC-04 | Candidate-level, not Screen-level, scope | No Screen source/API; static prompt scope | P03, P15–P17; import review | Pass |
| AC-05 | Exact Criterion ID/text | Direct ordered assignments | P08–P12 | Pass |
| AC-06 | Criterion evaluated as written | Exact Human Prompt equality | P03 | Pass |
| AC-07 | Exact `true` instruction | Exact Human Prompt equality | P03 | Pass |
| AC-08 | Explicit non-satisfaction means false | Exact Prompt and valid false schema | P03; V03 | Pass |
| AC-09 | Missing/insufficient evidence means false | Exact Human Prompt equality | P03; V03 | Pass |
| AC-10 | Ambiguity/uncertainty means false | Exact Human Prompt equality | P03; V03 | Pass |
| AC-11 | No invention/external inference | Exact Human Prompt equality | P03 | Pass |
| AC-12 | Strict Boolean result validation | `type(passed) is bool` | V03, V21–V26, V41 | Pass |
| AC-13 | Independent Criterion evaluation instruction | Exact Human Prompt equality | P03 | Pass |
| AC-14 | All Criteria required | Full ordered payload and completeness validator | P03, P10; V28, V33 | Pass |
| AC-15 | Exact top-level object schema | Exact key-set checks | V01, V13–V15 | Pass |
| AC-16 | Exact array/item schema | Exact list/item checks | V01, V16–V20 | Pass |
| AC-17 | Extra fields rejected | Exact key-set comparisons | V15, V20; P18 | Pass |
| AC-18 | Full-input JSON and duplicate rejection | `json.loads`, hook, constant rejection | V06–V12 | Pass |
| AC-19 | Boolean only, no coercion | Exact bool type check | V21–V26, V41 | Pass |
| AC-20 | Exact ID membership/no normalization | Direct exact membership | V30–V32, V34 | Pass |
| AC-21 | Complete exact ID set | Set equality after all items | V27–V29, V33 | Pass |
| AC-22 | Missing ID failure | Completeness failure path | V28, V36 | Pass |
| AC-23 | Duplicate ID failure | Returned-ID map duplicate check | V29 | Pass |
| AC-24 | Unknown/rewritten ID failure | Exact set membership | V27, V30–V32, V34 | Pass |
| AC-25 | Reordering valid, output input-ordered | Input-order reconstruction | V04 | Pass |
| AC-26 | One technical response-contract failure | `AIScreeningContractError` | V06–V32, V35 | Pass |
| AC-27 | No all-false degradation | Raise on every invalid response | V03, V35–V37 | Pass |
| AC-28 | No partial success | Return occurs only after complete validation | V35, V38 | Pass |
| AC-29 | Complete input-ordered strict mapping | Final dict comprehension | V01, V33, V39, V41 | Pass |
| AC-30 | R06-compatible mapping without execution | Plain dict result; no R06 runtime import | V42, V43 | Pass |
| AC-31 | Independent/all-Criteria prompt instructions | Exact Human Prompt equality | P03 | Pass |
| AC-32 | Exact Prompt true/false semantics | Exact Human Prompt equality | P03 | Pass |
| AC-33 | Exact no-invention instruction | Exact Human Prompt equality | P03 | Pass |
| AC-34 | Exact Prompt output contract instructions | Exact Human Prompt plus validator | P03; V01, V15, V20–V29 | Pass |
| AC-35 | Exact User dynamic payload selection | Payload construction | P06, P08, P11, P12 | Pass |
| AC-36 | Dynamic-data exclusions | Exact payload/system static boundary | P05, P15–P18; source review | Pass |
| AC-37 | Prompt asset, roles, serialization, version | Static asset, fields, JSON serialization | P01–P04, P06–P14, P18; Injection evidence | Pass |
| AC-38 | Frozen template/version governance | Literal `v1`, no router/hash | Sections 9–14; P03, P04, P19 | Pass |
| AC-39 | No diagnostic output fields | Exact Prompt/output schema | P03; V20 | Pass |
| AC-40 | No Provider execution/import | No Provider code/import | P04; V44; source review | Pass |
| AC-41 | No R06 execution, Decision, or action | No production Rule/action import | V43; protected-scope review | Pass |
| AC-42 | No persistence/degradation/status/stop code | Focused local modules only | Source/scope review | Pass |
| AC-43 | No replay/hash/integration | No hash/cache/replay imports/API | Sections 38–39; source review | Pass |
| AC-44 | Pure deterministic construction/validation | Local direct construction/validation | P19, P20; V39, V40, V44 | Pass |
| AC-45 | Upstream contracts unchanged | R10 new-file-only scope | Final scope/protected review | Pass |

Result: **45 / 45 Pass**.

## 48. Deviations

None.

## 49. Open Issues

None.

## 50. Contract Conflicts

None.

## 51. Final Automated Conclusion

All final R10 runtime/test artifacts, the Human-approved Prompt v1 asset, and the reused focused verification evidence conform to Frozen RPD/TID v0.1. All AC-01 through AC-45 individually pass. **Automated Acceptance Passed / Pending Human Final Review**.
