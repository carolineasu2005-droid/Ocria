# AM7-R09 — AI Candidate Input Builder

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R09
- Document Type: Technical Implementation Design
- Version: 0.1
- Status: Frozen
- Source RPD: AM7-R09 v0.1 Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r09-ai-candidate-input-builder`
- Working HEAD / Baseline: `4ff1b6a988be83cbfcd7728e2c6fff8f358653a1`
- Prepared On: 2026-08-21 (Asia/Shanghai)

## 1. Technical Objective

Implement the smallest local runtime capability for the Frozen transformation:

```text
CandidateOcrDocument
  -> AICandidateInput
```

The successful output is exactly:

```text
AICandidateInput
{
    candidate_record_id: str,
    resume_text: str
}
```

The implementation shall consist of one immutable value and one pure projection function. It shall read the two authoritative source values, validate only the source/output shape and the Frozen blank-text rule, and return the new value.

R09 does not implement AI Runtime, prompts, structured resume extraction, Criteria, Rule evaluation, Candidate Decision, action wiring, persistence, replay, or a reusable preprocessing framework.

## 2. Authoritative Technical Contract

For one actual `CandidateOcrDocument` instance:

```text
source.document_text is a non-blank str
  -> output.candidate_record_id = source.candidate_record_id
  -> output.resume_text         = source.document_text
```

The successful `AICandidateInput` has no third field.

The following each fail with no output:

```text
source is not a CandidateOcrDocument
source.document_text is None
source.document_text == ""
source.document_text contains only whitespace
source fields cannot satisfy the exact output value shape
```

Blank detection may call `strip()` only as a predicate. The stripped value is never stored or returned.

The implementation provides no fallback to Screens, `document_segments`, normalized Screen text, Legacy data, placeholders, or inference.

## 3. Targeted Repository Inspection

### 3.1 Inspection scope

The targeted inspection covered only:

- `CODEX-CONSTITUTION.md`;
- `docs/RPD-AM7-R09-ai-candidate-input-builder.md` v0.1 Frozen;
- the Frozen R08 RPD and TID plus the R08 Acceptance Report;
- `ocr_records.py`;
- `ocr_candidate.py`;
- the Candidate document portion of `ocr_aggregation.py`;
- directly relevant sections of `tests/test_ocr_candidate.py` and `tests/test_ocr_aggregation.py`;
- `screening_rule_engine.py`, `screening_profile.py`, and their nearby tests only for immutable-value, exception, import, and test-layout conventions;
- the root Python-module layout and focused exact-symbol search for an existing R09 role.

No repository-wide audit, Provider/model Runtime inspection, or test execution was performed.

### 3.2 Current branch and baseline

The actual repository metadata is:

```text
Requirement Branch: am7-r09-ai-candidate-input-builder
Working HEAD / Baseline: 4ff1b6a988be83cbfcd7728e2c6fff8f358653a1
```

This matches the requested Requirement branch and merged-main baseline.

### 3.3 CandidateOcrDocument location and type contract

`CandidateOcrDocument` is the existing frozen dataclass in `ocr_records.py`:

```python
@dataclass(frozen=True)
class CandidateOcrDocument(JsonRecordMixin):
    run_id: str
    candidate_record_id: str
    ...
    document_text: Optional[str] = None
    document_segments: tuple[OcrDocumentSegment, ...] = ()
    ...
```

Relevant facts:

- `candidate_record_id` is annotated as `str`.
- `document_text` is annotated as `Optional[str]`.
- The document is immutable at the dataclass attribute level.
- Its R05 validation enforces that a built document has a string `document_text` equal to the newline join of its ordered document segments.
- `NOT_ATTEMPTED` and `FAILED` document states require `document_text is None`.
- The document class does not independently validate the runtime type or format of `candidate_record_id` in `__post_init__`.

### 3.4 Candidate identity construction

The accepted finalization path is `CandidateOcrBuilder.finalize(...)` in `ocr_candidate.py`.

- `CandidateOcrBuilder` assigns `candidate_record_id = str(candidate_record_id or uuid4())`, so normal builder output carries a string ID.
- Record-mode `CandidateDocumentAggregator` also rejects a missing or non-string Candidate identity before aggregation.
- R09 does not normalize, regenerate, hash, prefix, suffix, or otherwise alter this ID.
- Because the document dataclass itself does not enforce the type annotation, the R09 output value performs one minimal `isinstance(candidate_record_id, str)` shape check before a successful value can exist.
- R09 deliberately adds no ID grammar, non-blank rule, UUID rule, Run prefix, or other new identity semantic. A valid source string is copied exactly.

### 3.5 Candidate document text states

Current construction can produce:

- `None`: aggregation disabled, not attempted, or failed;
- `""`: the current pure `build_document_text(())` projection returns an empty string for zero document segments;
- non-blank string text: one or more accepted document segments joined in deterministic order.

The normal accepted aggregation path does not produce a valid whitespace-only document segment: normalization removes leading/trailing and repeated whitespace for readable segments, comparison text removes Unicode whitespace, and `OcrDocumentSegment` requires non-empty normalized and comparison text. Nevertheless, the Frozen R09 boundary explicitly requires whitespace-only `document_text` to fail if such a value is supplied in an actual `CandidateOcrDocument` instance.

R09 therefore validates all three Frozen failure forms independently:

```text
None
empty string
whitespace-only string
```

It does not infer Evaluation eligibility from `document_build_status`, `capture_status`, Dynamic End, or any other lifecycle field.

### 3.6 Existing value and failure conventions

The current repository uses:

- root-level focused Python modules;
- `@dataclass(frozen=True)` for immutable public values;
- `__post_init__` for small public value-shape validation;
- `TypeError` for a wrong argument object type in small builders/functions;
- `ValueError` or a domain-specific `ValueError` subclass for invalid value content;
- `unittest` modules named `tests/test_<module>.py`;
- direct root-module imports rather than a package-relative hierarchy.

R09 does not need a domain error taxonomy. Built-in `TypeError` and `ValueError` are the smallest consistent choice.

### 3.7 Existing role overlap

The targeted exact-symbol search found no existing:

- `AICandidateInput`;
- `StructuredCandidate`;
- `build_ai_candidate_input(...)`;
- Screen/raw-text Candidate-input builder;
- current `CandidateOcrDocument`-to-AI-input production consumer.

No existing module cleanly owns this new two-field boundary. A new focused root module avoids placing R09 inside `ocr_records.py`, `ocr_candidate.py`, the Provider Runtime, or another unrelated subsystem.

### 3.8 Chosen module and imports

Freeze the new runtime module as:

```text
ai_candidate_input.py
```

Its only required imports are:

```python
from dataclasses import dataclass
from ocr_records import CandidateOcrDocument
```

No dependency change is required.

## 4. Exact Runtime API

The public R09 runtime API is exactly:

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

The function has one input parameter and one return value. It has no overload and no optional configuration.

No public API is added for:

- `OcrScreenRecord`;
- a raw string;
- a Screen sequence;
- document segments;
- dict/JSON input;
- Profile, Criteria, Rule, Provider, model, prompt, Decision, or action data.

## 5. Exact AICandidateInput Representation

Freeze `AICandidateInput` as one root-module frozen dataclass with exactly two fields in this order:

```python
@dataclass(frozen=True)
class AICandidateInput:
    candidate_record_id: str
    resume_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_record_id, str):
            raise ValueError("candidate_record_id must be a string")
        if (
            not isinstance(self.resume_text, str)
            or not self.resume_text.strip()
        ):
            raise ValueError(
                "resume_text must contain non-whitespace text"
            )
```

Constructor validation covers only the public value shape frozen by R09:

- Candidate ID must be a string;
- resume text must be a string containing at least one non-whitespace character.

It does not validate resume meaning, quality, completeness, relevance, detail, or Evaluation eligibility. It does not normalize either field.

The dataclass has no methods for serialization, hashing, persistence, prompt construction, Evaluation, Decision, or action.

## 6. Source Type Contract

Freeze the builder implementation shape as:

```python
def build_ai_candidate_input(
    candidate: CandidateOcrDocument,
) -> AICandidateInput:
    if not isinstance(candidate, CandidateOcrDocument):
        raise TypeError("candidate must be a CandidateOcrDocument")
    return AICandidateInput(
        candidate_record_id=candidate.candidate_record_id,
        resume_text=candidate.document_text,
    )
```

Technical consequences:

- The source must be an actual `CandidateOcrDocument` instance; an `isinstance`-compatible subclass remains an instance rather than duck typing.
- Dicts, raw strings, Screens, Screen lists, and arbitrary attribute-compatible objects fail with `TypeError`.
- A constructed `CandidateOcrDocument` is the technical evidence-boundary value. R09 adds no finalization marker, capture-status gate, or document-status gate.
- The function reads only `candidate_record_id` and `document_text`.
- No `str(...)`, `strip()` assignment, copy builder, coercion, or adapter is used.

Direct construction of the immutable result value is not a Screen/raw-text projection API. `build_ai_candidate_input(...)` is the sole R09 source transformation entry point.

## 7. Blank Text Validation

The exact predicate is:

```python
not isinstance(resume_text, str) or not resume_text.strip()
```

This freezes the following outcomes:

| Source `document_text` | Outcome |
|---|---|
| `None` | `ValueError`; no output |
| `""` | `ValueError`; no output |
| `"   \t\r\n"` | `ValueError`; no output |
| `"x"` | Success |
| `" \n x \n "` | Success with the original string unchanged |

The `strip()` result is used only for truth testing. It is never assigned to `resume_text` and never returned.

No minimum length, language, character category, completeness, quality, relevance, or Evaluation-eligibility test is added.

## 8. Exact Text Fidelity

On success:

```text
result.resume_text is value-equal to candidate.document_text
```

R09 performs no:

- trimming;
- whitespace or newline normalization;
- line reordering;
- Screen concatenation;
- document-segment reconstruction;
- deduplication or overlap removal;
- truncation or token clipping;
- summarization, translation, redaction, filtering, keyword extraction, repair, or enrichment.

Example:

```text
source.document_text = "\n  Candidate resume text  \n"
result.resume_text    = "\n  Candidate resume text  \n"
```

The implementation trusts the accepted upstream Candidate document projection.

## 9. Failure Representation

Use only built-in exceptions:

| Condition | Exception | Frozen message | Result |
|---|---|---|---|
| Source is not `CandidateOcrDocument` | `TypeError` | `candidate must be a CandidateOcrDocument` | No output |
| Candidate ID is not a string | `ValueError` | `candidate_record_id must be a string` | No output |
| Candidate text is `None`, non-string, empty, or whitespace-only | `ValueError` | `resume_text must contain non-whitespace text` | No output |

No custom exception class is introduced.

Failure is synchronous and direct. It produces no partial `AICandidateInput`, Boolean result, status object, warning value, retry, recovery, or fallback.

These failures do not mean Match, Reject, skip, `ai_failed`, action, or production degradation. Those semantics remain outside R09.

## 10. Determinism

The result is a pure function of exactly:

```text
candidate.candidate_record_id
candidate.document_text
```

For identical values:

- non-blank text produces value-equal `AICandidateInput` values;
- missing/blank text produces the same exception type and message;
- excluded metadata cannot alter the result.

The implementation uses no time, randomness, environment, filesystem, Store, database, network, Provider, model, Profile, RuleSet, Legacy outcome, current Screen, or browser state.

Determinism is verified through repeat construction and value equality. No hash is computed.

## 11. Immutability and Side-Effect Contract

- `AICandidateInput` is `@dataclass(frozen=True)`.
- Both fields are immutable strings after successful construction.
- The function does not mutate the source Candidate document, its Screens, its document segments, metadata, Store state, or global state.
- The function does not deep-copy the Candidate document or any OCR evidence.
- It creates only the two-field result value.
- It performs no external I/O or persistence.

No mutable Builder class, service, manager, factory, dependency injection, serializer, mapper, pipeline, protocol, or interface is introduced.

## 12. No-Fallback Contract

When `document_text` is missing or blank, the function raises `ValueError` even if the source document contains:

- Screens with non-blank `raw_text`;
- normalized Screen text;
- non-empty `document_segments`;
- OCR boxes;
- Legacy match text or comparison/debug data;
- other evidence or metadata that appears capable of reconstruction.

The implementation must not inspect these fields to build `resume_text`.

There is no placeholder text, Screen selection, Screen concatenation, segment join, re-normalization, aggregation call, LLM synthesis, or recovery path.

## 13. No-Hash Contract

R09 adds no:

- `input_text_hash`;
- SHA-256 or other content digest;
- request digest;
- Candidate input digest;
- replay hash;
- cache key;
- hash helper;
- hashing dependency;
- hashing test.

`AICandidateInput` contains only `candidate_record_id` and `resume_text`. Determinism is verified by direct value equality and repeated construction.

## 14. No Production Wiring

R09 implementation creates the projection capability and its unit tests only.

It does not wire `build_ai_candidate_input(...)` into:

- `simple_brush.py`;
- `ocr_detector.py` or `scan_candidate(...)`;
- Candidate loops or Candidate switching;
- browser/mouse/action code;
- ScreeningProfile or R06;
- Provider Runtime or any LLM path;
- Store or persistence code.

No production caller is required under R09. The direct runtime consumer belongs to AM7-R11.

## 15. R05 / R06 / R07 / R08 Protection

### 15.1 AM7-R05

ScreeningProfile schema, persistence, versions, digest, Criteria, Run binding, and Configuration/Execution lifecycle remain untouched and uninvoked.

### 15.2 AM7-R06

`screening_rule_engine.py`, `ScreeningRule`, `ScreeningRuleSet`, Criterion Boolean mappings, parsing, and evaluation remain untouched and uninvoked.

### 15.3 AM7-R07

Complete Scan, `scan_candidate(...)`, Candidate aggregation, Candidate finalization, Dynamic End, retry/focus/switch behavior, and evidence semantics remain untouched. R09 consumes the existing finalized evidence value only.

### 15.4 AM7-R08

The binding authority remains:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

R09 begins after the finalized Candidate evidence boundary. It provides no Screen/raw-text overload, no per-Screen AI input, and no Evaluation, Decision, or action authority.

## 16. R10–R14 Deferrals

R09 does not implement:

- **AM7-R10**: Criterion Boolean schema, semantics, generation, or validation;
- **AM7-R11**: prompt construction, model-visible messages, token budgeting, Provider/model selection, LLM calls, response parsing, retries, timeouts, or Runtime normalization;
- **AM7-R12**: Candidate Decision, R06 integration, production authority, or favorite/forward/reject/skip/no-action wiring;
- **AM7-R13**: AI persistence, failure degradation, or durable Candidate-input storage;
- **AM7-R14**: replay, input hashing, cache identity, comparison, or end-to-end orchestration.

R09 determinism may support later work but does not pre-implement it.

## 17. Exact File Plan

### 17.1 New files

| Phase | File | Purpose |
|---|---|---|
| Current design | `docs/TID-AM7-R09-ai-candidate-input-builder.md` | This TID |
| Implementation | `ai_candidate_input.py` | Frozen value and pure projection function |
| Implementation | `tests/test_ai_candidate_input.py` | Focused R09 unit tests |
| Later acceptance | `docs/AM7-R09-acceptance-report.md` | Required acceptance evidence; not created during design or implementation |

### 17.2 Modified existing runtime files

None.

### 17.3 Modified existing test files

None.

### 17.4 Protected / untouched files

At minimum:

- `docs/RPD-AM7-R09-ai-candidate-input-builder.md`;
- all R05/R06/R07/R08 RPDs, TIDs, and accepted reports;
- `ocr_records.py`;
- `ocr_candidate.py`;
- `ocr_aggregation.py`;
- `ocr_detector.py`;
- `simple_brush.py`;
- `ocr_store.py` and Store formats;
- `screening_profile.py` and `screening_profile_cli.py`;
- `screening_rule_engine.py`;
- `llm_provider_runtime.py`, `ai_provider_config.py`, and `ai_provider_cli.py`;
- OCR normalization, similarity, replay, browser, mouse, and action modules;
- existing Candidate, aggregation, Profile, Rule Engine, Provider, and integration tests;
- dependency files;
- packaging, build, release, and Git configuration.

## 18. Implementation Changes

Implementation Changes count: **2**.

### Change 1 — R09 Runtime Projection Capability

Create `ai_candidate_input.py` with:

1. the exact frozen `AICandidateInput` two-field representation;
2. minimal constructor shape validation;
3. `build_ai_candidate_input(candidate: CandidateOcrDocument) -> AICandidateInput`;
4. actual source-type enforcement;
5. missing/blank text failure using `strip()` only as a predicate;
6. exact ID/text copying;
7. no fallback, hash, I/O, persistence, or production wiring.

Preconditions:

- Frozen R09 RPD remains v0.1 Frozen;
- `CandidateOcrDocument` remains in `ocr_records.py` with the inspected fields;
- no existing `ai_candidate_input.py` or equivalent R09 implementation appears before implementation begins.

If a changed implementation baseline contradicts one of these preconditions, report the concrete drift rather than modifying upstream evidence contracts.

### Change 2 — R09 Targeted Unit Tests

Create `tests/test_ai_candidate_input.py` with the exact focused matrix in Section 19.

The tests shall:

- use `unittest`;
- construct actual `CandidateOcrDocument` instances through existing Candidate helpers where practical;
- use the existing controlled frozen-object edge-fixture technique only where the explicit whitespace/no-fallback boundary cannot be produced through normal upstream aggregation;
- avoid a fake Candidate schema or relaxed source type;
- avoid mocks except where a concrete side effect could not otherwise be proven;
- contain no Prompt, Provider, LLM, R06, Decision, Action, persistence, replay, benchmark, or integration behavior.

## 19. Targeted Test Matrix

### 19.1 Fixture discipline

Use one small test-local helper based on the accepted pattern in `tests/test_ocr_candidate.py`:

- `CandidateOcrBuilder`;
- `OCRItem`;
- `NormalizationBox` / `normalize_ocr_text`;
- `CaptureType.FORMAL_SCREEN` and `CaptureStatus`;
- record-mode aggregation when a real built `document_text` is needed.

For `None`, use a genuine finalized Candidate document whose aggregation was not attempted. For an empty built string, use the existing zero-segment document projection path. For whitespace-only and the explicit “segments exist but authoritative text is unavailable” boundary, start from a genuine finalized `CandidateOcrDocument`, copy it, and use the same controlled `object.__setattr__` edge-fixture technique already present in the accepted OCR aggregation tests. The value remains an actual `CandidateOcrDocument`; no dict, duck type, or parallel schema is introduced.

Use the existing `RuleComparisonResult` construction pattern only for the one Legacy-independence test. Do not invoke Legacy matching.

### 19.2 Planned tests

Planned targeted test methods: **20**.

| ID | Planned test | Frozen verification |
|---|---|---|
| T01 | `test_non_blank_candidate_document_builds_input` | Normal non-blank success returns `AICandidateInput` |
| T02 | `test_candidate_record_id_is_copied_exactly` | Exact ID equality; no normalization, regeneration, hash, prefix, or suffix |
| T03 | `test_resume_text_is_copied_exactly` | Exact source/output text equality |
| T04 | `test_leading_and_trailing_whitespace_is_preserved` | `strip()` is predicate-only; example text remains byte-for-byte/value-equal |
| T05 | `test_internal_newlines_and_multiscreen_text_are_preserved` | Ordered Candidate-level multi-Screen text and newlines remain unchanged |
| T06 | `test_none_document_text_raises_value_error` | `None` fails with no output |
| T07 | `test_empty_document_text_raises_value_error` | `""` fails with no output |
| T08 | `test_whitespace_only_document_text_raises_value_error` | spaces/tabs/newlines fail with no output |
| T09 | `test_any_non_whitespace_character_allows_success` | Minimal non-blank text succeeds and remains unchanged |
| T10 | `test_missing_text_never_falls_back_to_screen_raw_text` | A Screen may contain text; authoritative `None` still fails |
| T11 | `test_missing_text_never_falls_back_to_document_segments` | Segments may exist; authoritative `None` still fails |
| T12 | `test_repeated_build_is_deterministic` | Repeated success values and repeated failure type/message are stable |
| T13 | `test_output_value_shape_and_constructor_contract_are_frozen` | Exact field order, `FrozenInstanceError`, type/blank constructor validation |
| T14 | `test_source_candidate_document_is_not_mutated` | Source, Screens, segments, and metadata remain unchanged |
| T15 | `test_excluded_metadata_and_lifecycle_fields_do_not_affect_output` | Same ID/text with different excluded data yields equal output |
| T16 | `test_legacy_comparison_fields_do_not_affect_output` | Legacy shadow/debug differences have no result authority |
| T17 | `test_wrong_source_and_malformed_identity_fail_clearly` | dict/string/list/Screen -> `TypeError`; non-string ID in actual Candidate -> `ValueError` |
| T18 | `test_output_has_exactly_two_fields_and_no_hash` | No hash, version, timestamp, Run ID, status, warnings, or extra payload |
| T19 | `test_projection_is_local_and_side_effect_free` | Direct pure call, unchanged source, no Store/external effect; paired with module import review |
| T20 | `test_public_api_has_no_screen_or_raw_text_builder` | Exact single-parameter function signature and no `build_from_screen/raw_text/screens` API |

No test may treat projection failure as Match, Reject, skip, `ai_failed`, or action.

## 20. Verification Commands

Run only after implementation, with evidence captured from command start:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ai_candidate_input -v
```

```powershell
.\venv\Scripts\python.exe -m compileall ai_candidate_input.py tests\test_ai_candidate_input.py
```

No existing runtime file is modified, and the focused R09 tests construct the accepted source type directly. Therefore no existing Candidate suite rerun is required by this TID.

Do not run:

- full repository regression;
- the full R07 or R08 acceptance suites;
- LLM or network tests;
- benchmarks;
- packaging smoke;
- dependency audit.

If implementation unexpectedly requires an existing-source modification, that exceeds this Frozen file plan and must be reported before broadening verification.

## 21. AC-01–AC-24 Mapping

| AC | Implementation owner | Verification owner / evidence |
|---|---|---|
| AC-01 | `build_ai_candidate_input(...)` actual Candidate source | T01, T17, T20 |
| AC-02 | Source `isinstance` check; no overloads | T17, T20; runtime-module API review |
| AC-03 | `AICandidateInput` two fields | T13, T18 |
| AC-04 | Direct Candidate ID assignment | T02 |
| AC-05 | Direct document-text assignment | T03, T04, T05 |
| AC-06 | Function reads `document_text` only | T10, T11; runtime-module review |
| AC-07 | No second processing code | T03–T05; exact two-import/runtime review |
| AC-08 | Existing Candidate document text remains intact | T05 |
| AC-09 | No per-Screen builder/API | T17, T20 |
| AC-10 | Exact two-field representation | T13, T18 |
| AC-11 | Excluded lifecycle/metadata absent | T15, T18 |
| AC-12 | Legacy data ignored | T16; runtime-module import review |
| AC-13 | Pure deterministic construction | T12 |
| AC-14 | Frozen value and no side effects | T13, T14, T19 |
| AC-15 | `None` failure and no evidence fallback | T06, T10, T11 |
| AC-16 | Empty/whitespace failure; successful whitespace fidelity | T04, T07–T09 |
| AC-17 | Output has content only, no eligibility/status | T13, T15, T18; structural review |
| AC-18 | No Decision/result fields or behavior | T18; exact file/import review |
| AC-19 | No capture/document-status gate | T15; runtime-function review |
| AC-20 | No Profile/Criteria/R06 imports or calls | Protected-file and runtime-import review |
| AC-21 | No Prompt/Provider/model/LLM code | Protected-file and runtime-import review |
| AC-22 | No production caller or action wiring | Exact file-scope review; protected runtime files |
| AC-23 | No existing schema/persistence change; no ID/version/digest/cache | T13, T18, T19; exact file plan |
| AC-24 | R10–R14 absent | Exact file/import review and protected-scope review |

All 24 Frozen RPD Acceptance Criteria are mapped. No product AC is added or redefined.

## 22. Acceptance Report Contract

After implementation and successful targeted verification, create:

```text
docs/AM7-R09-acceptance-report.md
```

The report must include:

- metadata referencing R09 RPD v0.1 Frozen and TID v0.1 Frozen;
- final implementation scope and exact changed/new files;
- exact runtime API and two-field output representation;
- source-type enforcement;
- `None`, empty, whitespace-only, and non-blank results;
- exact successful text fidelity;
- no Screen/segment fallback evidence;
- deterministic behavior;
- immutable/side-effect review;
- no-hash evidence;
- no production wiring confirmation;
- R05/R06/R07/R08 protected-boundary review;
- R10–R14 non-implementation review;
- targeted unit-test and compile results;
- AC-01–AC-24 individual mapping;
- deviations;
- open issues;
- contract conflicts.

After all automated checks pass, use exactly:

```text
Automated Acceptance Passed / Pending Human Final Review
```

Do not declare Human Accepted, Merged, or Released.

## 23. Protected Scope / Explicit Non-Implementation

R09 must not add or modify:

- input/request/replay hashes, digests, or cache keys;
- ID/version/revision/timestamp/status/warning fields;
- Run ID, Screen IDs, metadata, Provider, model, Criteria, or prompt fields in the output;
- `StructuredCandidate` or another Candidate schema;
- generic DTO, mapper, builder, serializer, validator, pipeline, service, manager, factory, protocol, or dependency-injection framework;
- Prompt Builder, Provider/model logic, AI Runtime, LLM call, or response parser;
- ScreeningProfile, Criteria, Criterion Boolean, or R06 execution;
- Candidate Decision or action integration;
- favorite, forward, reject, skip, stop, browser, or mouse behavior;
- persistence, replay, retry, or degradation orchestration;
- Screen or segment reconstruction fallback;
- trimming, normalization, deduplication, overlap removal, or any second text processing;
- OCR, Dynamic End, Complete Scan, Candidate aggregation, or Candidate finalization behavior;
- generic Gate, Guard, Wrapper, Scanner, Sanitizer, or compliance framework.

The only implementation artifacts authorized before acceptance are `ai_candidate_input.py` and `tests/test_ai_candidate_input.py`.

## 24. Open Issues

None.

The exact module, API, dataclass placement, failure types, fixture strategy, test matrix, and verification commands are resolved by current repository conventions and the Frozen RPD.

## 25. Contract Conflicts

None.

The current Candidate document contract permits the exact two-field projection. Its optional/blank text states align with the Frozen R09 failure contract, and the R08 Candidate-level authority boundary is preserved.

## 26. Final Technical Conclusion

AM7-R09 shall add one focused runtime module and one focused unit-test module through exactly two implementation Changes:

```text
CandidateOcrDocument
  -> build_ai_candidate_input(...)
  -> AICandidateInput(candidate_record_id, resume_text)
```

The function requires an actual Candidate document, delegates exact output-shape validation to one frozen two-field value, rejects `None`/empty/whitespace-only text with `ValueError`, preserves non-blank text exactly, and performs no fallback, hash, I/O, persistence, production wiring, or adjacent-requirement work.

No existing runtime or test file is modified. R05/R06/R07/R08 remain protected, and R10–R14 remain deferred.
