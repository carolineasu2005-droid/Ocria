# AM7-R09 — Final Automated Acceptance Report

## 1. Metadata

| Item | Value |
|---|---|
| Product | Ocria Am7 |
| Requirement | AM7-R09 — AI Candidate Input Builder |
| Acceptance type | Final automated acceptance |
| Requirement branch / declared baseline | `am7-r09-ai-candidate-input-builder` / `4ff1b6a988be83cbfcd7728e2c6fff8f358653a1` |
| Governing document | `CODEX-CONSTITUTION.md` |
| Acceptance date | 2026-08-21 (Asia/Shanghai) |

## 2. Acceptance Status

**Automated Acceptance Passed / Pending Human Final Review**

## 3. Requirement Scope

AM7-R09 is limited to the deterministic local projection:

```text
CandidateOcrDocument -> AICandidateInput(candidate_record_id, resume_text)
```

It does not perform Evaluation, Rule execution, LLM Runtime work, Candidate Decision/action work, persistence, replay, or OCR lifecycle work.

## 4. Authoritative Documents

- `docs/RPD-AM7-R09-ai-candidate-input-builder.md` v0.1 Frozen
- `docs/TID-AM7-R09-ai-candidate-input-builder.md` v0.1 Frozen
- `CODEX-CONSTITUTION.md`

## 5. Final Implementation Scope

The final product implementation is one focused runtime module and one focused unit-test module. The runtime module exposes one immutable value and one pure source projection function.

## 6. Exact Changed/New File Scope

| Scope | File | Result |
|---|---|---|
| New runtime product code | `ai_candidate_input.py` | Present; reviewed |
| New focused runtime tests | `tests/test_ai_candidate_input.py` | Present; reviewed |
| Frozen design input | `docs/RPD-AM7-R09-ai-candidate-input-builder.md` | Reviewed; not altered by acceptance |
| Frozen design input | `docs/TID-AM7-R09-ai-candidate-input-builder.md` | Reviewed; not altered by acceptance |
| Acceptance output | `docs/AM7-R09-acceptance-report.md` | Created by this acceptance |

Existing runtime files modified: **None**.

Existing test files modified: **None**.

## 7. Runtime API

```python
@dataclass(frozen=True)
class AICandidateInput:
    candidate_record_id: str
    resume_text: str

def build_ai_candidate_input(
    candidate: CandidateOcrDocument,
) -> AICandidateInput:
```

There are no `build_from_screen`, `build_from_raw_text`, or `build_from_screens` public APIs.

## 8. AICandidateInput Representation

`AICandidateInput` is a frozen dataclass with exactly these fields, in order:

1. `candidate_record_id: str`
2. `resume_text: str`

There is no third product field and no OCR, lifecycle, Profile, Rule, Provider, prompt, Decision, or action field.

## 9. Source Type Contract

`build_ai_candidate_input(...)` first requires `isinstance(candidate, CandidateOcrDocument)`. A dict, raw string, list, Screen, or attribute-compatible arbitrary object fails with:

```text
TypeError: candidate must be a CandidateOcrDocument
```

The implementation has no coercion, duck typing, alternate source entry point, or status/finalization gate.

## 10. Candidate Identity Behavior

The builder directly assigns `candidate.candidate_record_id` to the result. `AICandidateInput.__post_init__` requires only that this value is a string and otherwise raises:

```text
ValueError: candidate_record_id must be a string
```

No normalization, grammar, regeneration, prefix, suffix, hash, or Run-ID composition is present.

## 11. Blank Text Behavior

The constructor uses the Frozen predicate `not isinstance(resume_text, str) or not resume_text.strip()`.

| Source `document_text` | Result |
|---|---|
| `None` | `ValueError: resume_text must contain non-whitespace text` |
| `""` | Same `ValueError` |
| whitespace-only string | Same `ValueError` |
| any non-blank string | Success with the original string |

No partial result or alternate failure/product status is created.

## 12. Text Fidelity

On success the implementation directly assigns `candidate.document_text` to `resume_text`. Leading/trailing whitespace, internal newlines, and multi-Screen Candidate text remain value-equal to the source. The `strip()` call is only a Boolean predicate; its result is not stored or returned.

## 13. No-Fallback Review

The runtime module reads only `candidate_record_id` and `document_text`. It does not access `screens`, `raw_text`, normalized text, `document_segments`, OCR boxes, Legacy comparison/debug data, metadata, or any reconstruction helper. T10 and T11 independently verify that `None` authoritative text fails even when Screen raw text or document segments are present.

## 14. Determinism

The function constructs a value solely from the two source fields. It has no time, randomness, environment, filesystem, Store, database, Provider, model, Profile, Rule, Legacy, browser, or current-Screen dependency. T12 verifies repeated success equality and stable repeated blank-text failure type/message.

## 15. Immutability / Side Effects

The result is a frozen dataclass. The reviewed module imports only `dataclass` and `CandidateOcrDocument`, constructs only `AICandidateInput`, and performs no I/O or external call. T13 verifies frozen-value behavior; T14 and T19 verify the Candidate document, Screens, segments, and metadata are unchanged.

## 16. No-Hash Review

The module contains no product hash, digest, request/replay hash, cache key, or hashing helper/dependency. The result contains only the two frozen fields. Ordinary Python frozen-dataclass behavior is not an R09 product hash. T18 verifies the absence of product hash/digest/cache fields.

## 17. Model-visible Content Boundary

`AICandidateInput` contains exactly:

- `candidate_record_id`
- `resume_text`

`resume_text` is the Candidate resume content produced by R09 for future AI screening. `candidate_record_id` is the Candidate identity / traceability association; it is not itself resume content.

R09 does not require `candidate_record_id` to appear in model-visible prompt/messages. Whether AM7-R11 transmits it, retains it internally, or otherwise uses it is deferred to AM7-R11.

All OCR technical metadata, Screens, document segments, fingerprints, similarity/aggregation internals, Dynamic End data, lifecycle metadata, Legacy fields, Profile/Criteria/Rules, Provider/model/prompt data, Decision, and action state remain excluded from `AICandidateInput`.

## 18. No Production Wiring

The final runtime module has no production caller or action import. A targeted exact-symbol search found no use of `ai_candidate_input`, `AICandidateInput`, or `build_ai_candidate_input` outside the R09 module and its focused test module. There is no wiring into `simple_brush.py`, OCR scanning, Candidate loops, Profile/Rule code, Provider/LLM paths, Store/persistence, or browser/action flow.

## 19. R05 Protection

R09 imports no ScreeningProfile module and invokes no Profile, Criterion, version, digest, Run-binding, Configuration, or Execution behavior. The R05 boundary remains separate and uninvoked.

## 20. R06 Protection

R09 imports no Rule Engine module and invokes no `ScreeningRule`, `ScreeningRuleSet`, tokenizer, parser, Criterion Boolean mapping, or Boolean evaluation. The R06 boundary remains separate and uninvoked.

## 21. R07 Protection

R09 does not modify or call Complete Scan, Candidate aggregation/finalization, Dynamic End, retry/focus/switch behavior, or Candidate evidence semantics. It consumes only the existing `CandidateOcrDocument` boundary.

## 22. R08 Binding Constraint

R09 provides one Candidate-level content projection after Candidate evidence exists. It provides no Screen/raw-text overload, per-Screen AI input, Evaluation, Decision, or production authority. The binding constraint remains:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

## 23. R10–R14 Non-Implementation

The reviewed files add none of the following:

- R10 Criterion Boolean schema, generation, or validation;
- R11 prompts, messages, token budgeting, Provider/model selection, LLM calls, parsing, retries, or timeouts;
- R12 Candidate Decision, R06 integration, or production action authority;
- R13 persistence, durable input storage, or failure degradation;
- R14 replay, input hashing, cache identity, comparison, or end-to-end orchestration.

## 24. Targeted Test Results

The same-conversation Change 2 verification evidence was reviewed and reused under the acceptance reuse policy. The final inspected runtime and test files are the files that produced that evidence; no subsequent acceptance action altered either file. The focused command was:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ai_candidate_input -v
```

Result: **20 / 20 passed**.

| Test | Result |
|---|---|
| T01 normal success | Pass |
| T02 exact Candidate ID | Pass |
| T03 exact resume text | Pass |
| T04 leading/trailing whitespace fidelity | Pass |
| T05 newlines / multi-Screen Candidate text | Pass |
| T06 `None` failure | Pass |
| T07 empty failure | Pass |
| T08 whitespace-only failure | Pass |
| T09 minimal non-whitespace success | Pass |
| T10 no Screen fallback | Pass |
| T11 no document-segment fallback | Pass |
| T12 deterministic repeated build | Pass |
| T13 exact output shape / frozen constructor | Pass |
| T14 source immutability | Pass |
| T15 excluded metadata independence | Pass |
| T16 Legacy data independence | Pass |
| T17 wrong source / malformed identity | Pass |
| T18 exact two fields / no hash | Pass |
| T19 local side-effect-free projection | Pass |
| T20 no Screen/raw-text public builder API | Pass |

## 25. Compile Result

The same-conversation Change 2 verification evidence was reviewed and reused. The focused command was:

```powershell
.\venv\Scripts\python.exe -m compileall ai_candidate_input.py tests\test_ai_candidate_input.py
```

Result: **Passed**.

## 26. AC-01–AC-24 Individual Mapping

| AC | Requirement | Implementation evidence | Verification evidence | Result |
|---|---|---|---|---|
| AC-01 | Candidate document source boundary | Actual `CandidateOcrDocument` `isinstance` check | T01, T17, T20 | Pass |
| AC-02 | No Screen-level source substitution | No alternate source API or coercion | T17, T20; module review | Pass |
| AC-03 | Exact v1 output shape | Frozen dataclass has two fields | T13, T18 | Pass |
| AC-04 | Preserve Candidate identity | Direct `candidate_record_id` assignment | T02 | Pass |
| AC-05 | Preserve Candidate text | Direct `document_text` assignment | T03, T04, T05 | Pass |
| AC-06 | Existing aggregation is authoritative | Only `document_text` is read | T10, T11; module review | Pass |
| AC-07 | No second content-processing pass | No transformation/helper code; predicate-only `strip()` | T03–T05; import review | Pass |
| AC-08 | Multi-Screen evidence remains representable | Existing aggregated text is passed unchanged | T05 | Pass |
| AC-09 | No per-Screen input behavior | No Screen entry point or output path | T17, T20; module review | Pass |
| AC-10 | Exclude OCR technical fields | Exact two-field value | T13, T18 | Pass |
| AC-11 | Exclude lifecycle/metadata fields | Builder uses neither class of field | T15, T18 | Pass |
| AC-12 | Legacy data excluded/non-authoritative | No Legacy import/read | T16; import review | Pass |
| AC-13 | Deterministic projection | Pure direct construction from two fields | T12 | Pass |
| AC-14 | Local and side-effect-free | Frozen value; no I/O/store/action code | T13, T14, T19 | Pass |
| AC-15 | Missing text fails without fallback | Constructor rejects `None`; no evidence read | T06, T10, T11 | Pass |
| AC-16 | Blank text fails without altering success text | Frozen predicate and direct source text assignment | T04, T07–T09 | Pass |
| AC-17 | Projection is not eligibility | No status/eligibility field or gate | T13, T15, T18; structural review | Pass |
| AC-18 | Projection is not a Candidate Decision | No Decision/result/action field or code | T18; exact module review | Pass |
| AC-19 | Capture-status policy remains deferred | No capture/document-status read or gate | T15; function review | Pass |
| AC-20 | Profile and Rule contracts remain separate | No Profile/Criteria/R06 import or call | Protected-boundary/import review | Pass |
| AC-21 | No LLM or Runtime behavior | No prompt/Provider/model/LLM import or code | Protected-boundary/import review | Pass |
| AC-22 | No Decision or Action integration | No production caller; no action imports | Exact-symbol and scope review | Pass |
| AC-23 | No persistence or schema expansion | New two-field value only; no persistence/schema files | T13, T18, T19; scope review | Pass |
| AC-24 | No adjacent-requirement pre-implementation | No R10–R14 import, API, or code | Exact module/import/scope review | Pass |

Result: **24 / 24 Pass**.

## 27. Exact Scope Review

The final reviewed implementation is limited to the two Frozen-TID implementation artifacts. This acceptance creates only its required report. No existing runtime or test file is part of the R09 implementation change. The targeted symbol search found no consumer beyond the R09 module and test module.

## 28. Deviations

None.

## 29. Open Issues

None.

## 30. Contract Conflicts

None.

## 31. Final Acceptance Conclusion

All 24 Frozen RPD acceptance criteria are individually supported by final implementation review and the focused 20/20 test and compile evidence. AM7-R09 is **Automated Acceptance Passed / Pending Human Final Review**.
