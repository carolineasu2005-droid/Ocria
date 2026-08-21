# AM7-R10 — AI Screening Boolean Contract

## Metadata

| Field | Value |
|---|---|
| Product | Ocria |
| Generation | Am7 |
| Requirement | AM7-R10 — AI Screening Boolean Contract |
| Document Type | Requirement / Product Design |
| Version | 0.1 |
| Status | Frozen |
| Governing Document | `CODEX-CONSTITUTION.md` |
| Requirement Branch | `am7-r10-ai-screening-boolean-contract` |
| Working HEAD / Upstream Baseline | `bd4c18573fc4c43b3c67f9a71b59cc4f55d63f21` |
| Prepared On | 2026-08-21 (Asia/Shanghai) |

## 1. Summary

AM7-R10 freezes the Candidate-level AI screening Boolean contract:

```text
AICandidateInput.resume_text
+ ScreeningProfileVersion.criteria
-> Prompt v1
-> raw AI response
-> strict R10 validation
-> validated Criterion Boolean results
```

R10 defines the meaning of each Criterion Boolean, the exact v1 AI response
shape, strict response validation, the technical-failure boundary, the
normative Prompt v1 behavior, and `prompt_version` governance.

R10 does not call an AI Provider and does not evaluate a RuleSet, produce a
Candidate Decision, trigger an action, or persist/replay an Evaluation.

## 2. Background and Problem

AM7-R05 established immutable, natural-language screening Criteria. AM7-R06
established a pure Boolean Rule Engine that consumes Criterion-ID-to-Boolean
values but does not produce them. AM7-R08 established Candidate, rather than
Screen, as the Ocria Am7 production Decision scope. AM7-R09 established the
narrow Candidate-level AI input projection:

```text
AICandidateInput {
    candidate_record_id,
    resume_text
}
```

The next contract boundary must define how a future AI completion evaluates
all frozen Criteria against that Candidate text and how an untrusted raw
completion becomes a complete, exact Boolean mapping. Without this boundary,
providers or callers could introduce inconsistent truth semantics, partial
results, coercion, Screen-level evaluation, permissive JSON extraction, or
silent all-false degradation.

## 3. Goals

R10 shall:

- define Candidate-level Criterion evaluation input;
- define exact `true` and `false` business semantics;
- require independent evaluation of every supplied Criterion;
- define the exact v1 JSON response contract;
- define strict JSON, schema, identity, uniqueness, and completeness checks;
- distinguish a valid `false` result from a technical contract failure;
- define the validated Criterion Boolean result boundary consumed by later
  logic;
- freeze the normative behavioral content and model-visible data boundary of
  Prompt v1;
- define `prompt_version = "v1"` and its increment rule; and
- preserve the authority and scope boundaries frozen by R05, R06, R08, and
  R09.

## 4. Non-Goals

R10 does not own:

- Provider selection, model selection, inference request execution, timeout,
  retry, or provider-error normalization;
- an actual LLM/API call;
- Rule expression or RuleSet evaluation;
- Candidate Decision, exclusion, recommendation, ranking, scoring, or action;
- persistence, replay, audit storage, degradation policy, stop policy, or
  runtime status naming;
- confidence, probability, reason, evidence quotation, explanation, or partial
  result output;
- Criteria authoring, mutation, classification, prioritization, or semantic
  rewriting;
- Screen reconstruction, OCR normalization, text deduplication, or access to
  OCR evidence internals;
- Prompt experimentation infrastructure, a generic structured-output
  framework, or a generic Evaluation framework; or
- any AM7-R11 through AM7-R14 implementation.

## 5. Targeted Repository and Contract Findings

The inspection for this RPD was limited to the current branch/HEAD and the
R05, R06, R08, and R09 contracts and their directly relevant implementation
surfaces.

- The actual branch is `am7-r10-ai-screening-boolean-contract` and the actual
  HEAD is `bd4c18573fc4c43b3c67f9a71b59cc4f55d63f21`.
- R05 provides immutable `ScreeningProfileVersion.criteria`. Each `Criterion`
  has `criterion_id`, `criterion_text`, and the fixed rule `must_match`; formal
  Versions contain one or more Criteria with unique IDs.
- R05 Criterion IDs are exact uppercase `C` followed by at least three decimal
  digits with a positive numeric value. Criterion text is non-blank and is
  preserved as authored.
- R06 consumes a Criterion-ID-to-strict-Boolean mapping. It does not read
  Criterion text, generate Criterion results, call an AI Provider, or own a
  Candidate Decision.
- R08 freezes `Screen = Evidence Scope` and
  `Candidate = Ocria Am7 Production Decision Scope`.
- R09 provides immutable `AICandidateInput(candidate_record_id, resume_text)`.
  Its `resume_text` is the authoritative Candidate-level model content, while
  `candidate_record_id` is identity/trace association.
- The current Provider-neutral runtime exposes generic completion
  request/result types. It does not contain the R10 Prompt, response schema, or
  validated Criterion Boolean result contract.
- No production integration currently composes R09 Candidate input, R05
  Criteria, an AI completion, and R06 RuleSet evaluation.
- Existing benchmark-only prompt metadata is not a production R10 contract and
  is not reused as authority for this requirement.

These findings reveal no blocker or contract conflict for R10.

## 6. Input Boundary

R10 consumes exactly these semantic inputs:

1. `AICandidateInput.resume_text` from an existing successful R09 projection;
2. the complete ordered Criteria collection from one valid, saved, immutable
   `ScreeningProfileVersion` established by R05.

R10 must use `AICandidateInput.resume_text` exactly as the Candidate resume
content. It must not bypass R09 to read `CandidateOcrDocument`, Screen records,
OCR boxes, segments, fingerprints, comparison text, lifecycle metadata, or
Legacy fields, and it must not rebuild or renormalize Candidate text.

The input Criteria supply their exact `criterion_id` and `criterion_text`.
Their fixed R05 `rule = "must_match"` supplies the shared rule semantics but is
not a model-visible dynamic field in Prompt v1.

`AICandidateInput.candidate_record_id` may be retained outside the model call
by later trace/runtime work. It is not semantic screening content, is not
required in the model-visible Prompt v1, and is not part of the R10 raw AI
response or validated Boolean mapping.

## 7. Candidate-Level Evaluation Scope

One R10 Evaluation concerns one finalized Candidate input and the complete
Criteria collection bound for that Candidate's Evaluation context.

All Criteria are evaluated against the same Candidate-level `resume_text`.
R10 must not evaluate individual Screens, stop after a matching Screen, expose
Screen boundaries to the model, or permit Screen-level outcomes to substitute
for Candidate-level Criterion results.

## 8. Criterion Semantic Contract

Each R05 `criterion_text` is an authoritative natural-language proposition.
R10 evaluates whether the supplied Candidate resume contains sufficient
evidence that the proposition, exactly as written, is satisfied.

R10 does not reclassify a Criterion as positive, negative, exclusionary,
inclusive, hard, soft, preferred, optional, or scored. It does not rewrite the
statement or infer a different business intent.

A negative business condition must be expressed directly in the Criterion's
natural-language proposition and evaluated as written. R10 adds no
`must_not_match`, `NOT`, polarity field, or inversion convention. The R05 rule
remains exactly `must_match`.

## 9. `true` Semantics

For one Criterion, `passed: true` means:

> The supplied Candidate `resume_text` contains sufficient evidence that the
> authoritative `criterion_text`, as written, is satisfied.

`true` must be supported by the supplied resume content. It must not be based
on outside facts, unstated assumptions, invented details, unsupported
probability, or unreliable inference.

## 10. `false` Semantics

For one Criterion, `passed: false` is required when any of the following
applies:

- the resume explicitly shows that the proposition is not satisfied;
- relevant supporting evidence is absent or insufficient;
- the available text is ambiguous, vague, uncertain, or undeterminable;
- reaching `true` would require an unstated assumption, invented detail,
  external fact, or unreliable inference; or
- the model otherwise cannot reliably establish the proposition as satisfied
  from the supplied resume text.

`false` is a successful business Boolean result. It is not an error, unknown,
maybe, null, confidence level, or technical failure.

R10 has exactly two valid per-Criterion values: JSON `true` and JSON `false`.
There is no third Criterion state.

## 11. Independent and Complete Criterion Evaluation

Every input Criterion must be evaluated independently against the Candidate
resume. A result for one Criterion must not determine, skip, imply, invert, or
short-circuit the result of another Criterion.

Every input Criterion must receive exactly one Boolean result even if an
earlier Criterion is already `false` or `true`. Criteria order is not priority
and does not create AND/OR semantics.

## 12. Exact Raw AI Response Contract

The v1 raw AI response must be one JSON object of exactly this form:

```json
{
  "criteria_results": [
    {
      "criterion_id": "C001",
      "passed": true
    },
    {
      "criterion_id": "C002",
      "passed": false
    }
  ]
}
```

The top-level object contains exactly one member: `criteria_results`.
`criteria_results` is a JSON array. Each array item is a JSON object containing
exactly two members:

- `criterion_id`: the exact input Criterion ID string;
- `passed`: a JSON Boolean.

The response must not contain reason, evidence, explanation, confidence,
score, probability, status, Criterion text copies, `prompt_version`, Candidate
identity, profile identity, model/provider information, timestamps, warnings,
metadata, or any other field.

## 13. Strict JSON-Only Contract

The entire non-whitespace response must be exactly one JSON value satisfying
the R10 schema. JSON grammar whitespace before or after that value is allowed;
any other prefix or suffix is not.

R10 rejects:

- prose before or after the JSON value;
- Markdown or fenced code blocks;
- malformed JSON;
- multiple top-level JSON values;
- extracted JSON embedded inside a larger response; and
- any permissive repair, guessing, or best-effort object extraction.

Duplicate JSON member names do not satisfy an exact object shape and must be
rejected rather than collapsed silently.

## 14. Strict Schema and Type Validation

Validation must require the exact top-level and item member sets defined in
Section 12. Missing or additional members are invalid at either level.

`criteria_results` must be an array. Every item must be an object.
`criterion_id` must be a string. `passed` must be a real JSON Boolean.

R10 rejects string, number, null, object, or array substitutes for a Boolean,
including `"true"`, `"false"`, `1`, `0`, `"yes"`, and `"no"`. It performs no
Boolean coercion.

## 15. Criterion Identity, Uniqueness, and Completeness

Let the input Criterion-ID set be the exact IDs supplied by the bound R05
Criteria collection. A valid response must satisfy all of the following:

- the returned Criterion-ID set equals the input Criterion-ID set;
- every input ID appears exactly once;
- no ID is missing;
- no ID is duplicated;
- no unknown ID is present; and
- every returned ID exactly matches an input string.

R10 performs no trimming, case folding, alias resolution, zero-padding,
rewriting, or normalization of returned IDs. A malformed, differently cased,
space-padded, or otherwise altered ID is invalid even if a Human might infer
the intended Criterion.

## 16. Response Order

Prompt v1 instructs the model to return results in input Criterion order for
predictability and review convenience.

Order is not part of result identity or validity. The validator matches by
exact `criterion_id`; a complete, unique, otherwise valid response remains
valid when its array order differs from input order. The validated conceptual
result is an ID-to-Boolean mapping, not an order-based positional result.

## 17. Technical Contract Failure

Any response that fails JSON parsing, exact schema validation, strict type
validation, ID validation, uniqueness, or exact completeness is an invalid or
unusable AI response. R10 must return no successful validated Criterion
Boolean result for that Evaluation attempt.

This is a technical contract failure, not a Criterion business outcome. R10
does not freeze the later runtime's concrete exception class, final status
name, retry/degradation decision, stop reason, or action consequence. Those
belong to later requirements.

## 18. No All-False or Partial-Success Fallback

R10 must never transform a malformed, incomplete, unparseable, or otherwise
invalid AI response into all-false Criterion results. Doing so would erase the
distinction between a valid business `false` and a technical failure.

R10 also has no partial success. If any result item or any required ID fails
the contract, the entire raw response is unusable and no subset is returned as
a successful validated result.

## 19. Validated Criterion Boolean Result Semantics

The conceptual validated result is a complete mapping:

```text
Criterion ID -> Boolean
```

It contains exactly the input Criterion IDs and one strict Boolean value per
ID. It exists only after the entire raw response has passed JSON, exact schema,
strict type, exact identity, uniqueness, and completeness validation.

For the same input Criterion set and the same raw response, validation must
produce the same mapping or the same failure. The concrete Python type and
public API belong to the TID; this RPD freezes the product semantics only.

## 20. Prompt v1 Normative Behavior

Prompt v1 must communicate all of the following to the model:

1. Evaluate every supplied Criterion independently against only the supplied
   Candidate resume text.
2. Evaluate the Criterion proposition exactly as written, without
   reclassification, inversion, or rewriting.
3. Return `true` only when the resume contains sufficient evidence that the
   proposition is satisfied.
4. Return `false` for explicit non-satisfaction, absent or insufficient
   evidence, ambiguity, vagueness, uncertainty, undeterminability, or whenever
   reliable `true` would require invention, external facts, or unstated
   assumptions.
5. Do not treat probability or unreliable inference as evidence.
6. Evaluate all Criteria; do not skip or short-circuit any item.
7. Return every exact input Criterion ID exactly once and return no unknown ID.
8. Return only the exact JSON object/array/item shape from Section 12, with a
   real JSON Boolean for every `passed` value.
9. Include no prose, Markdown, code fence, reason, evidence, explanation,
   confidence, score, metadata, or additional field.
10. Prefer the input Criterion order in `criteria_results`.

This RPD freezes the Prompt v1 product semantics above and the authorized
model-visible dynamic product data in Section 21. It intentionally does not
contain the final full Prompt text.

The AM7-R10 TID must freeze one exact Prompt v1 model-visible template,
including:

- the exact static instruction text;
- the exact message-role packaging;
- the exact placement and serialization of dynamic `resume_text`;
- the exact placement and serialization of Criterion IDs and Criterion
  statements; and
- the exact output-format instructions.

Once the AM7-R10 TID is Frozen, that exact model-visible template is the sole
template identified by `prompt_version = "v1"`. Its wording, role packaging,
structure, dynamic-content placement/serialization, and output-format
instructions are no longer left open-ended within v1.

## 21. Model-Visible Content Boundary

Prompt v1 model-visible dynamic product data is limited to:

- the exact `AICandidateInput.resume_text`; and
- each input Criterion's exact `criterion_id` and exact `criterion_text`.

The model-visible prompt must not include the following as additional dynamic
product data:

- `candidate_record_id`;
- Candidate, Run, Screen, OCR box, segment, fingerprint, comparison, Dynamic
  End, lifecycle, or Legacy metadata;
- `screening_profile_id`, `profile_version`, or `criteria_digest`;
- R06 Rule or RuleSet expressions;
- provider/model selection, request IDs, trace data, persistence data, or
  replay data; or
- any other dynamic product data beyond the authorized resume and Criterion
  inputs.

This dynamic-data restriction does not prohibit the static model-visible
instructions required by the exact Prompt v1 template frozen in the TID.

This restriction does not prohibit later runtime/trace layers from retaining
authorized association metadata outside the model-visible prompt and outside
the R10 AI response.

## 22. `prompt_version`

The initial contract version is:

```text
prompt_version = "v1"
```

`prompt_version` is Runtime/trace metadata identifying the behavioral Prompt
contract. RPD v0.1 supplies its Frozen product semantics and authorized dynamic
data boundary; the Frozen AM7-R10 TID supplies its exact model-visible
template. Once that TID is Frozen, `prompt_version = "v1"` identifies that one
exact template.

`prompt_version` is not model output, must not be requested from the model, and
must not appear in the R10 raw response or validated Criterion Boolean result.

## 23. Prompt Version Increment Rule

After the exact Prompt v1 template is Frozen by the TID, an intentional change
to any of the following that can affect model behavior requires a monotonic
prompt-version increment: `v2`, then `v3`, and so on:

- model-visible static instruction wording;
- message-role structure;
- template structure;
- dynamic-content placement or serialization;
- model-visible content selection; or
- output-format instructions.

Purely non-model-visible implementation refactoring that preserves the same
Prompt v1 behavior and content contract does not require an increment.

R10 does not use semantic versioning, dates, hashes, digests, or content
fingerprints as `prompt_version`.

## 24. R05 Contract Relationship

R10 consumes, but does not alter, one valid saved R05
`ScreeningProfileVersion.criteria` collection.

- `criterion_id` and `criterion_text` remain authoritative and exact.
- `rule` remains fixed at `must_match`.
- Negative business conditions remain natural-language propositions evaluated
  as written.
- R10 does not mutate Criteria, create Profile Versions, change digests, or
  introduce new Criterion fields or rule types.

## 25. R06 Contract Relationship

The complete validated R10 mapping is naturally compatible with the R06
Criterion Boolean mapping input: exact valid Criterion ID keys and strict
Boolean values.

R10 does not parse Rule expressions, execute `evaluate_rule_set()`, apply
RuleSet ANY semantics, or convert the R06 Boolean outcome into a Candidate
Decision. R06 remains a separate pure consumer.

## 26. R08 and R09 Binding Constraints

R08 binds R10 to Candidate-level evaluation. A Screen, Screen-level Legacy
match, or partial OCR observation cannot become an R10 production Criterion
result.

R09 binds R10 model content to `AICandidateInput.resume_text`. R10 must not
bypass the projection boundary or reconstruct content from Candidate/OCR
internals. `candidate_record_id` remains an association field outside Prompt
v1's model-visible product content.

R10 produces no Candidate Decision or action and therefore does not cross the
R08 authority boundary.

## 27. AM7-R11 Through AM7-R14 Deferrals

- AM7-R11 owns Provider/model selection, completion request execution, runtime
  integration, provider responses, and applicable request-level failures.
- AM7-R12 owns Candidate Decision and production action integration.
- AM7-R13 owns Evaluation persistence, degradation/runtime policy, and any
  later operational status or stop behavior assigned to it.
- AM7-R14 owns replay, audit/integration behavior, and any later authorized
  reproducibility metadata.

These later requirements must obey the Frozen R10 Boolean, Prompt, response,
and technical-failure contracts. R10 does not pre-implement them.

## 28. No-Hash Decision

R10 introduces no hash or digest of the prompt, prompt template, response,
Candidate input, resume text, Criteria, validated results, or Evaluation.

`prompt_version` is the literal monotonic label defined above, not a hash.
Existing R05 `criteria_digest` remains an R05 artifact and is neither
recomputed by R10 nor sent to the model.

## 29. Persistence and Replay Boundary

R10 requires no persistence and defines no storage schema, Evaluation record,
cache, replay bundle, audit log, retention rule, or migration.

R10 also defines no Evaluation ID, result version, response version, schema
version, request identity, timestamp, or persistence key. Later authorized
requirements may retain R10 inputs, outputs, and `prompt_version` subject to
their own contracts without changing R10 semantics.

## 30. Product Invariants

1. Evaluation scope is one Candidate, never one Screen.
2. Candidate model content comes only from exact R09 `resume_text`.
3. The model evaluates exact R05 Criterion IDs and statements.
4. `true` requires sufficient resume evidence that the statement as written is
   satisfied.
5. Absence, insufficiency, ambiguity, uncertainty, or required invention yields
   valid business `false`.
6. `false` is not a technical failure, and technical failure is not `false`.
7. Every Criterion is evaluated independently and receives exactly one result.
8. The only valid Criterion values are strict JSON Booleans.
9. The raw response is JSON only and has the exact v1 shape.
10. Returned IDs are exact, unique, complete, and neither missing nor unknown.
11. Result order is non-authoritative; identity matching is by exact ID.
12. Any contract violation invalidates the complete response and returns no
    successful mapping.
13. Invalid responses are never degraded to all-false or partial success.
14. Prompt v1 exposes only resume text and exact Criterion IDs/statements as
    dynamic model data.
15. `prompt_version = "v1"` is external metadata, never model output.
16. RPD v0.1 freezes Prompt v1 semantics and authorized dynamic data; the R10
    TID must freeze its exact model-visible template, which
    `prompt_version = "v1"` then identifies, and behavior-affecting changes to
    that template require monotonic version increments.
17. R10 does not execute R06, call a Provider, decide, act, persist, replay, or
    hash.
18. R05, R06, R08, and R09 contracts and implementation surfaces remain
    unmodified by R10 product design.

## 31. Acceptance Criteria

### Input and scope

- **AC-01:** Given one successful R09 `AICandidateInput` and one valid saved
  R05 `ScreeningProfileVersion`, R10 uses `resume_text` and the Version's
  complete Criteria collection as its semantic inputs.
- **AC-02:** R10 uses `AICandidateInput.resume_text` exactly and does not read or
  reconstruct content from `CandidateOcrDocument`, Screens, OCR boxes,
  segments, fingerprints, comparison text, lifecycle metadata, or Legacy
  fields.
- **AC-03:** `candidate_record_id` is not required in model-visible Prompt v1,
  the raw AI response, or the validated Boolean mapping; retaining it outside
  R10 model content remains a later trace/runtime concern.
- **AC-04:** All Criteria are evaluated against one Candidate-level resume; no
  Screen result, Screen stopping condition, or Legacy match substitutes for a
  Candidate result.
- **AC-05:** Exact input `criterion_id` and `criterion_text` values are
  authoritative; R10 does not rewrite them or alter the fixed `must_match`
  rule.
- **AC-06:** A negative business condition is evaluated as its natural-language
  proposition is written, with no polarity classification, inversion, or
  `must_not_match` behavior.

### Boolean semantics

- **AC-07:** R10 defines `passed: true` only when `resume_text` contains
  sufficient evidence that the exact Criterion proposition is satisfied.
- **AC-08:** Explicit evidence that the proposition is not satisfied produces
  the valid business result `passed: false`.
- **AC-09:** Missing or insufficient supporting evidence produces the valid
  business result `passed: false`.
- **AC-10:** Ambiguous, vague, uncertain, or undeterminable resume evidence
  produces the valid business result `passed: false`.
- **AC-11:** When `true` would require external facts, unstated assumptions,
  invention, probability-as-evidence, or unreliable inference, the result is
  `passed: false`.
- **AC-12:** A valid `false` remains a successful Criterion business result and
  is not represented as unknown, null, confidence, error, or technical
  failure.
- **AC-13:** Each Criterion is evaluated independently; one Criterion result
  cannot imply, invert, skip, or short-circuit another.
- **AC-14:** Every input Criterion receives exactly one attempted Boolean result
  regardless of earlier Criterion outcomes.

### Raw response and validation

- **AC-15:** A successful raw response is one JSON object whose exact top-level
  member set is `{ "criteria_results" }`.
- **AC-16:** `criteria_results` is an array whose every item is an object with
  the exact member set `{ "criterion_id", "passed" }`.
- **AC-17:** Any additional top-level or item field, including reason, evidence,
  explanation, confidence, score, probability, status, metadata, Criterion
  text, `prompt_version`, Candidate identity, or provider/model data, causes
  validation failure.
- **AC-18:** Prose, Markdown, code fences, malformed JSON, duplicate JSON member
  names, multiple top-level values, or JSON embedded in surrounding content is
  rejected without extraction, repair, or guessing.
- **AC-19:** `passed` accepts only a real JSON Boolean; strings, numbers, null,
  yes/no values, objects, and arrays are rejected without coercion.
- **AC-20:** Every returned `criterion_id` must exactly equal an input ID; R10
  performs no trimming, case folding, aliasing, zero-padding, rewriting, or
  normalization.
- **AC-21:** A response validates only when its returned Criterion-ID set equals
  the complete input Criterion-ID set.
- **AC-22:** A response missing any input Criterion ID fails validation and
  yields no successful result.
- **AC-23:** A response containing a duplicate Criterion ID fails validation and
  yields no successful result.
- **AC-24:** A response containing an unknown, malformed, differently cased,
  space-padded, or rewritten Criterion ID fails validation and yields no
  successful result.
- **AC-25:** Prompt v1 prefers input order, but a complete and otherwise valid
  response in a different array order validates to the same ID-based mapping.
- **AC-26:** Any JSON, shape, type, identity, uniqueness, or completeness
  violation is a technical contract failure with no valid R10 result.
- **AC-27:** A technical contract failure is never converted to an all-false
  mapping.
- **AC-28:** R10 exposes no partial success; one invalid item or missing required
  item invalidates the entire response.
- **AC-29:** Only after complete validation does R10 yield a mapping containing
  exactly every input Criterion ID and one strict Boolean value per ID; the
  same input set and raw response yield the same mapping or failure.

### Prompt and version contract

- **AC-30:** The validated R10 mapping is compatible with R06's exact
  Criterion-ID-to-Boolean input, while R10 does not execute R06.
- **AC-31:** Prompt v1 instructs the model to evaluate every Criterion
  independently and not to skip or short-circuit any supplied Criterion.
- **AC-32:** Prompt v1 communicates the exact R10 `true` and `false` semantics,
  including false for missing, insufficient, ambiguous, vague, uncertain, or
  undeterminable evidence.
- **AC-33:** Prompt v1 forbids reliance on invented details, external facts,
  unstated assumptions, probability-as-evidence, or unreliable inference.
- **AC-34:** Prompt v1 requires JSON only, the exact response shape, strict
  Boolean values, every exact ID exactly once, no unknown ID, no extra field,
  and preferred input order.
- **AC-35:** Prompt v1 dynamic model-visible product data consists only of exact
  `resume_text` and each Criterion's exact `criterion_id` and
  `criterion_text`.
- **AC-36:** Prompt v1 excludes Candidate identity, Screens/OCR internals,
  Profile/version/digest metadata, R06 rules, provider/model data, trace data,
  persistence data, replay data, and all other unauthorized dynamic product
  data from model-visible content; this does not exclude the static Prompt
  instructions themselves.
- **AC-37:** RPD v0.1 freezes Prompt v1 product semantics and authorized dynamic
  data, and the AM7-R10 TID freezes its exact static text, message roles,
  dynamic-content placement/serialization, and output-format instructions;
  once the TID is Frozen, that exact template is identified by the external
  metadata `prompt_version = "v1"`, which is neither requested nor accepted as
  model output and is absent from validated Criterion results.
- **AC-38:** After the exact Prompt v1 template is Frozen, any intentional
  behavior-affecting change to its model-visible static wording, message-role
  structure, template structure, dynamic-content placement/serialization,
  model-visible content selection, or output-format instructions requires the
  next monotonic `vN` label; purely non-model-visible refactoring does not, and
  no semantic version, date, hash, digest, or fingerprint substitutes for that
  label.
- **AC-39:** Prompt v1 and the v1 response contract require no reason, evidence,
  explanation, confidence, score, or probability output.

### Requirement boundaries

- **AC-40:** R10 makes no Provider/model selection and performs no completion
  request; those responsibilities remain deferred to R11.
- **AC-41:** R10 performs no RuleSet outcome, Candidate Decision, exclusion,
  ranking, recommendation, or production action; R06 remains separate and R12
  remains deferred.
- **AC-42:** R10 defines no persistence, retry/degradation policy, final runtime
  status name, stop reason, or operational consequence; applicable later work
  remains deferred to R13.
- **AC-43:** R10 defines no replay/integration mechanism, Evaluation hash,
  prompt hash, response hash, Candidate hash, Criteria hash, or result hash;
  applicable later work remains deferred to R14.
- **AC-44:** For identical R10 semantic inputs, Prompt v1 construction is
  deterministic; for identical input IDs and raw response, strict validation
  deterministically returns the same mapping or the same failure, without
  product side effects.
- **AC-45:** R10 introduces no mutation to R05 Criteria/Profile semantics, R06
  Rule Engine semantics, R08 Candidate authority, or R09 Candidate input
  projection.

## 32. Known Limitations

- Boolean-only results intentionally provide no explanation, evidence quote,
  confidence, score, or uncertainty state.
- Ambiguous or insufficient evidence intentionally collapses to valid business
  `false`; v1 does not expose why.
- R10 validation can prove structural compliance, not factual correctness of a
  model's Boolean judgment.
- Prompt v1 does not select a model or guarantee a Provider will follow the
  contract; R11 owns the actual request and Provider behavior.
- R10 does not decide retry, degradation, persistence, Candidate Decision, or
  action consequences after a technical failure.

These are deliberate scope boundaries, not Open Issues.

## 33. Open Issues

None.

## 34. Contract Conflicts

None.

## 35. Final RPD Conclusion

AM7-R10 defines a strict Candidate-level boundary between future AI completion
text and validated Criterion Boolean results. It uses only authoritative R09
resume text plus exact R05 Criteria, gives every Criterion one independent
strict Boolean, treats insufficient or uncertain evidence as valid business
`false`, and treats every response-contract violation as a technical failure
with no all-false or partial-result fallback.

RPD v0.1 freezes Prompt v1 product semantics and authorizes only resume text
and exact Criterion IDs/statements as dynamic model-visible product data. The
AM7-R10 TID must freeze the one exact model-visible template—including static
wording, message roles, dynamic-content placement/serialization, and
output-format instructions—that `prompt_version = "v1"` identifies after the
TID is Frozen. The complete validated mapping is compatible with R06 without
executing it. Provider calls, Decision/action, persistence/degradation, and
replay/integration remain deferred to R11 through R14 respectively.

The targeted repository and Frozen-contract inspection found no Open Issue or
Contract Conflict. This RPD is Frozen and ready to govern AM7-R10 TID design.
