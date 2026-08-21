# AM7-R09 — AI Candidate Input Builder

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R09
- Document Type: Requirement / Product Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r09-ai-candidate-input-builder`
- Working HEAD / Upstream Baseline: `4ff1b6a988be83cbfcd7728e2c6fff8f358653a1`
- Prepared On: 2026-08-21 (Asia/Shanghai)

## Terminology

- **Finalized Candidate evidence**: an existing `CandidateOcrDocument` produced when one Candidate capture lifecycle is finalized. Finalized means that the Candidate evidence object has been constructed; it does not imply that capture was normal, evidence was complete, Evaluation succeeded, or a Candidate Decision exists.
- **Candidate document text**: the existing `CandidateOcrDocument.document_text` projection produced by the accepted Candidate aggregation path from ordered Candidate document segments.
- **AICandidateInput**: the minimal Candidate-level content value produced by AM7-R09 for later AI screening work.
- **Projection success**: successful construction of an `AICandidateInput`. Projection success does not authorize Evaluation, imply Match or Reject, or authorize an action.
- **Candidate-level Evaluation**: future interpretation of the Candidate content against screening Criteria. It is outside AM7-R09.

## 1. Requirement Summary

AM7-R09 introduces one narrow product boundary:

```text
finalized CandidateOcrDocument
  -> deterministic local projection
  -> AICandidateInput
```

The v1 product shape is exactly:

```text
AICandidateInput
{
    candidate_record_id: string,
    resume_text: string
}
```

AM7-R09 converts existing Candidate-level OCR evidence into the minimum Candidate content needed by future AI screening. It does not evaluate the Candidate, generate Criterion Booleans, execute a RuleSet, call an LLM, create a Candidate Decision, or trigger a production action.

## 2. Background and Problem Statement

AM7-R07 established rule-independent Complete Scan and the `CandidateOcrDocument` evidence boundary. AM7-R08 then froze:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

The accepted future production chain is conceptually:

```text
OcrScreenRecord
  -> CandidateOcrDocument
  -> Candidate-level AI input
  -> Candidate-level Evaluation
  -> Candidate Decision
  -> production action
```

`CandidateOcrDocument` is deliberately evidence-oriented. It may contain or reference ordered Screens, OCR boxes and raw text, normalized/comparison text, fingerprints, similarity and aggregation projections, Dynamic End facts, capture/lifecycle facts, optional Legacy comparison data, Candidate/run metadata, and the Candidate document text.

Making the future AI Runtime consume that entire evidence schema would:

- duplicate content from overlapping Screens;
- increase token usage and provider cost;
- expose irrelevant OCR and lifecycle metadata to the model;
- introduce avoidable model noise;
- couple AI Runtime to OCR implementation details;
- risk restoring Screen-level Evaluation behavior prohibited by AM7-R08.

AM7-R09 solves this by establishing a minimal Candidate-level content projection. OCR evidence remains in its existing evidence model; future AI screening receives only the Candidate association and Candidate document text it needs.

## 3. Goals

AM7-R09 shall:

1. Accept an existing finalized `CandidateOcrDocument` as its sole source object.
2. Produce the exact two-field `AICandidateInput` v1 product shape.
3. Preserve `candidate_record_id` exactly for Candidate association.
4. Use the existing Candidate-level `document_text` as `resume_text` without reconstructing text from Screens.
5. Keep Candidate input construction deterministic, local, and side-effect-free.
6. Keep the future AI Runtime independent of the full OCR evidence schema.
7. Preserve cross-Screen Candidate content through the existing Candidate aggregation projection.
8. Exclude OCR technical metadata, lifecycle metadata, and Legacy shadow/debug data from the AI input.
9. Fail clearly when the required Candidate document text is missing or blank, without Screen-level or inference fallback.
10. Preserve all R05, R06, R07, and R08 boundaries while leaving R10–R14 responsibilities deferred.

## 4. Non-Goals

AM7-R09 does not include:

- OCR capture, scrolling, retry, focus, Candidate switching, Dynamic End, or Complete-Scan behavior;
- creation, mutation, or finalization of `CandidateOcrDocument`;
- new Screen aggregation, overlap removal, deduplication, normalization, similarity, or fingerprint logic;
- selection of which Candidate capture statuses are eligible for later Evaluation;
- ScreeningProfile, Criterion, Rule, or RuleSet loading or mutation;
- Criterion ID-to-Boolean generation or validation;
- AM7-R06 RuleSet evaluation;
- prompt templates, system instructions, message construction, structured output schemas, or token budgeting;
- LLM Provider selection, credentials, connectivity, model discovery, model choice, API calls, retries, streaming, or timeout behavior;
- Candidate Evaluation, Candidate Decision, Match, Reject, score, reason, or confidence;
- favorite, forward, reject, skip, stop-run, browser, mouse, or other production action;
- persistence, replay, audit, telemetry, version, revision, digest, cache, or retention behavior for `AICandidateInput`;
- PII redaction, anonymization, translation, summarization, enrichment, classification, or content repair;
- a generic projection, DTO, mapper, serializer, validator, pipeline, Gate, Guard, Scanner, Wrapper, or AI-input framework;
- changes to Legacy BossOCR behavior or its rule/match/action chain;
- AM7-R10–AM7-R14 implementation.

## 5. Targeted Repository Findings

The design inspection was limited to the Frozen AM7-R07 and AM7-R08 boundaries, their accepted evidence, the current `CandidateOcrDocument` representation, and the current Candidate document aggregation/finalization path. No repository-wide audit or test execution was performed.

### 5.1 Current Candidate evidence boundary

- `CandidateOcrBuilder.finalize(...)` constructs the existing immutable `CandidateOcrDocument` after collecting the Candidate's committed Screen evidence.
- The document carries `candidate_record_id`, ordered `screens`, capture/lifecycle facts, Candidate text/segments, and existing normalization, aggregation, similarity, Dynamic End, and metadata projections.
- Candidate finalization does not itself perform Evaluation or produce a Candidate Decision.

### 5.2 Current Candidate text projection

- The existing aggregation path builds `document_text` from the ordered Candidate document segments.
- The current projection joins the segments' normalized text in deterministic order.
- Overlap handling and Candidate document assembly already belong to the accepted upstream aggregation path.
- `document_text` is a Candidate-level projection; it is not one Screen's `raw_text` and does not require all relevant text to coexist in one viewport.
- A valid existing Candidate document may have `document_text` unavailable when document building was not attempted or failed. Completed or partial document building may provide a string value; R09 succeeds only when that value contains at least one non-whitespace character.

### 5.3 Current downstream boundary

- The accepted AM7-R08 evidence confirms that no current Ocria Am7 Candidate Input Builder, Candidate evaluator, Candidate Decision-to-action chain, or equivalent production consumer exists.
- AM7-R08 requires later Candidate input to originate from the Candidate evidence boundary, preserve multi-Screen representability, and never make an individual Screen the final production scope.
- No existing `AICandidateInput` or `StructuredCandidate` implementation was found in the targeted exact-symbol inspection.

## 6. Frozen Product Contract

### 6.1 Source boundary

The sole AM7-R09 source is one existing finalized `CandidateOcrDocument` for one Candidate capture lifecycle.

R09 must not accept an individual `OcrScreenRecord`, one `formal_screen.raw_text`, a list of raw OCR boxes, or a Legacy Screen-level result as an equivalent source.

The caller supplies the finalized Candidate document. AM7-R09 does not create, finalize, persist, select, or search for that document.

### 6.2 Exact output shape

The successful v1 output contains exactly:

1. `candidate_record_id`
2. `resume_text`

No other source field is copied into `AICandidateInput`.

In particular, v1 does not include `run_id`, Screens, document segments, raw boxes, fingerprints, similarity results, aggregation evidence, capture status, Dynamic End reason, timestamps, metadata, Legacy match data, Profile data, Criteria, Rules, Provider configuration, prompt data, Evaluation results, or Decision/action state.

The concrete Python representation and exception class names belong to a future TID. The two product fields and their semantics are frozen by this RPD.

### 6.3 Exact transformation

For a source with non-blank Candidate document text, the successful transformation is:

```text
output.candidate_record_id = source.candidate_record_id
output.resume_text         = source.document_text
```

Both values are copied exactly. R09 does not reinterpret either value.

The successful output is determined entirely by these two source values. Differences confined to raw Screens, boxes, fingerprints, similarity projections, lifecycle metadata, Dynamic End facts, Legacy comparison fields, or other excluded evidence metadata do not change the R09 output when `candidate_record_id` and `document_text` are unchanged.

### 6.4 Candidate document text availability

`CandidateOcrDocument.document_text` is the only authorized source for `resume_text`.

- A successful projection requires `document_text` to be a string containing at least one non-whitespace character.
- `document_text is None`, `document_text == ""`, and whitespace-only `document_text` each produce no successful `AICandidateInput` and report a clear local projection failure.
- For non-blank `document_text`, R09 copies the complete source string exactly, including its existing leading/trailing whitespace, ordering, and line boundaries.
- Blank checking may determine only whether at least one non-whitespace character exists. It must not trim, normalize, rewrite, or otherwise modify a successful source string.

For example, source text `\n  Candidate resume text  \n` is non-blank and the successful `resume_text` remains exactly `\n  Candidate resume text  \n`.

R09 performs no broader semantic validation. It does not decide whether non-blank resume text is sufficiently detailed, complete, relevant, meaningful, high quality, or eligible for Evaluation.

When text is missing or blank, R09 must not:

- concatenate Screen `raw_text` values;
- choose one Screen as a fallback;
- rebuild from `document_segments`;
- invoke normalization or aggregation again;
- use Legacy match text;
- use a hard-coded placeholder;
- call an LLM or another external service to synthesize content.

Exact technical exception representation is deferred to TID. R09 requires only a direct failure with no fabricated or partial success value.

## 7. Text Fidelity and Content-Minimization Contract

`resume_text` is the accepted Candidate document text under a new consumer-facing name. R09 does not alter its content.

R09 performs no:

- trimming or whitespace normalization;
- line reordering;
- concatenation of Screen text;
- overlap removal or second deduplication pass;
- truncation or token-budget clipping;
- summarization, paraphrasing, translation, or rewriting;
- keyword filtering or rule-based extraction;
- PII removal or anonymization;
- prompt decoration, XML/JSON wrapping, labels, or instructions;
- inference, heuristic repair, or enrichment.

This preserves one authoritative Candidate text projection and prevents the AI input layer from becoming a second OCR aggregation system.

Future prompt construction or Runtime token-budget behavior must be designed by its owning Requirement. It must not be silently introduced into R09.

## 8. Candidate-Level and Cross-Screen Semantics

R09 consumes Candidate-level aggregated text only after the `CandidateOcrDocument` boundary exists.

The source text may represent relevant content accumulated across multiple Screens. R09 does not require all relevant facts to appear together on one Screen and does not expose Screen boundaries as AI decision scopes.

The following are prohibited:

- building one `AICandidateInput` per Screen;
- evaluating each Screen independently and merging results;
- selecting a supposedly most relevant Screen;
- stopping input construction because an earlier Screen has a Legacy positive match;
- omitting earlier Candidate text because it has scrolled out of the current viewport.

This preserves the AM7-R08 contract:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

R09 still produces content only. It does not acquire Candidate Decision authority.

## 9. Finalization, Capture Status, and Evaluation Eligibility

An existing finalized `CandidateOcrDocument` is required before R09 projection. Finalization is the evidence boundary, not an assertion of success or completeness.

R09 is not an eligibility gate. It does not classify or decide the future Evaluation treatment of:

- normally completed captures;
- completed-with-limit captures;
- partial Candidate documents;
- aborted or interrupted captures;
- empty captures;
- safety or technical termination outcomes.

Where `document_text` is non-blank, R09 may perform its content projection without declaring that Evaluation should run. Where it is `None`, empty, or whitespace-only, the required two-field projection cannot succeed.

Missing/blank detection is the only R09 content acceptance check. R09 does not judge the detail, completeness, relevance, meaning, quality, or Evaluation eligibility of non-blank text.

Projection success means only that `candidate_record_id` and `resume_text` were constructed. It does not mean:

- Candidate evidence is complete;
- capture ended normally;
- the Candidate is eligible for an LLM call;
- Evaluation succeeded;
- the Candidate matched or was rejected;
- an action is authorized.

Eligibility, degradation, and production handling remain assigned to their later owning requirements.

## 10. Determinism and Side-Effect Boundary

For the same source `candidate_record_id` and `document_text`, R09 produces the same successful `AICandidateInput` value.

R09 must not depend on:

- current time;
- random values;
- process-global mutable state;
- network or Provider state;
- filesystem or database reads;
- ScreeningProfile or Rule configuration;
- Legacy match outcomes;
- model behavior.

R09 does not mutate the source `CandidateOcrDocument`, its Screens, its segments, or any Store. It performs no persistence and no external call.

## 11. Legacy Independence

Legacy BossOCR rules, keyword matches, confirmation outcomes, and action behavior remain outside R09.

Optional Legacy match/comparison data may remain inside the source evidence document, but R09 does not read or project it. Changing Legacy rule definitions or incidental Legacy shadow/debug fields cannot change `AICandidateInput` when the source `candidate_record_id` and `document_text` are unchanged.

Legacy positive or negative outcomes cannot:

- select the source Screen;
- terminate the projection;
- alter `resume_text`;
- substitute for Candidate document text;
- produce a Criterion Boolean;
- authorize or suppress later Candidate Evaluation;
- trigger an Am7 production action.

## 12. Failure Semantics

R09 uses a small all-or-nothing product contract:

- valid source with string `document_text` containing at least one non-whitespace character -> one `AICandidateInput` with the original text unchanged;
- `document_text is None`, empty, or whitespace-only -> clear failure and no success value;
- malformed or wrong source value -> clear failure and no success value.

R09 provides no partial result, fallback text, inferred text, recovery loop, retry, warning framework, error taxonomy framework, or degraded success mode.

R09 performs no content-semantic validation beyond the missing/blank check.

The future TID may choose the smallest local exception types needed to distinguish invalid input from missing/blank Candidate text. It must not reinterpret failure as Match, Reject, or action authority.

## 13. Requirement Boundaries

### 13.1 AM7-R05 — ScreeningProfile

R09 does not read or mutate ScreeningProfile, Profile versions, `criteria_digest`, Criteria, Run binding, or Configuration/Execution lifecycle. Profile and Criterion content is not copied into `AICandidateInput`.

### 13.2 AM7-R06 — Screening Rule Engine V2

R09 does not invoke or modify `ScreeningRule`, `ScreeningRuleSet`, tokenization, parsing, Criterion Boolean mapping, or fixed multi-Rule ANY evaluation.

### 13.3 AM7-R07 — Candidate Complete Scan

R07 continues to own rule-independent evidence collection and the Candidate OCR evidence boundary. R09 does not change Complete Scan, Dynamic End, safety/retry/focus/switch behavior, or Candidate finalization.

### 13.4 AM7-R08 — Candidate Decision Boundary

R09 respects Candidate as the production Decision scope and Screen as evidence scope. It produces one Candidate-level input only after the Candidate evidence boundary. It does not itself perform Evaluation or acquire Decision authority.

### 13.5 AM7-R10 — AI Screening Boolean Contract

Criterion Boolean meaning, generation, completeness, and validation are deferred to R10. R09 supplies no Boolean mapping and does not pair resume text with Criteria.

### 13.6 AM7-R11 — AI Screening Runtime

Prompt construction, model input messages, Provider/model choice, LLM execution, timeout, retry, parsing, and Runtime error normalization are deferred to R11. R09 performs no SDK or network operation.

### 13.7 AM7-R12 — Candidate Decision and Action Integration

Candidate Decision representation, authority, execution, traceability linkage, and production action wiring are deferred to R12. `candidate_record_id` preserves the Candidate association but is not itself a Decision or action authorization.

### 13.8 AM7-R13 and AM7-R14

Persistence, failure degradation, replay, and end-to-end integration remain deferred to R13 and R14. R09 creates no storage or replay contract.

## 14. Persistence and Schema Boundary

R09 does not modify:

- `CandidateOcrDocument`;
- `OcrScreenRecord`;
- Candidate/run schemas;
- ScreeningProfile or Rule schemas;
- OCR Store formats;
- dependency or packaging contracts.

R09 introduces no product requirement for an `AICandidateInput` ID, version, digest, timestamp, lifecycle status, database table, JSONL record, cache entry, or durable history.

The two-field value is a projection boundary. Any later persistence or wire-format requirement must be introduced by its owning Requirement.

## 15. Invariants

1. AM7-R09 owns only `CandidateOcrDocument -> AICandidateInput`.
2. The input source is one existing finalized `CandidateOcrDocument`.
3. An individual Screen is never an equivalent R09 source.
4. The v1 successful output contains exactly `candidate_record_id` and `resume_text`.
5. Output `candidate_record_id` equals source `candidate_record_id` exactly.
6. Output `resume_text` equals source `document_text` exactly.
7. R09 does not reconstruct Candidate text from Screens or segments.
8. R09 does not re-run normalization, aggregation, overlap removal, or deduplication.
9. OCR technical, lifecycle, Dynamic End, similarity, fingerprint, and Legacy fields are excluded from the output.
10. Multi-Screen content remains represented through the upstream Candidate document text.
11. R09 never creates one AI input or one production result per Screen.
12. Legacy rule and match information has no R09 control or output authority.
13. The same source ID and text produce the same output.
14. R09 is local, side-effect-free, and does not mutate evidence.
15. R09 performs no external, Provider, SDK, LLM, filesystem, or database call.
16. `document_text` that is `None`, empty, or whitespace-only produces no successful output and no fallback reconstruction; R09 performs no broader content-semantic validation.
17. Projection success does not mean evidence completeness, Evaluation eligibility, Match, Reject, or action authorization.
18. R09 does not decide the Evaluation treatment of capture or document statuses.
19. ScreeningProfile, Criteria, and AM7-R06 Rules remain separate and uninvoked.
20. R09 creates no Criterion Boolean, Candidate Decision, or action.
21. R09 creates no persistence, identity, version, digest, cache, replay, or audit framework.
22. AM7-R05 through AM7-R08 remain unchanged.
23. AM7-R10 through AM7-R14 are not pre-implemented.

## 16. Acceptance Criteria

### AC-01 — Candidate document is the source boundary

R09 accepts one existing finalized `CandidateOcrDocument` as the source of a successful Candidate input projection.

### AC-02 — No Screen-level source substitution

An individual Screen, `OcrScreenRecord`, Screen raw text, or Legacy Screen result cannot substitute for the finalized Candidate document source.

### AC-03 — Exact v1 output shape

A successful `AICandidateInput` contains exactly `candidate_record_id` and `resume_text`.

### AC-04 — Candidate identity is preserved

The output `candidate_record_id` equals the source `CandidateOcrDocument.candidate_record_id` exactly.

### AC-05 — Candidate text is preserved

For every successful projection, output `resume_text` equals the non-blank source `CandidateOcrDocument.document_text` exactly, including existing leading/trailing whitespace and line boundaries.

### AC-06 — Existing Candidate aggregation is authoritative

R09 uses the existing Candidate-level `document_text`; it does not concatenate Screens or rebuild Candidate text from raw OCR evidence or segments.

### AC-07 — No second content-processing pass

R09 performs no second normalization, overlap removal, deduplication, reordering, trimming, truncation, summarization, translation, filtering, redaction, repair, or enrichment pass.

### AC-08 — Multi-Screen evidence remains representable

Relevant text already accumulated across Candidate Screens remains represented through the Candidate document text without requiring all facts to coexist on one Screen.

### AC-09 — No per-Screen AI input behavior

R09 does not build one AI input per Screen, select a preferred Screen, or create a Screen-level Evaluation path.

### AC-10 — OCR technical fields are excluded

Raw boxes, Screens, document segments, normalization details, fingerprints, similarity projections, aggregation evidence, and OCR versions are absent from `AICandidateInput`.

### AC-11 — Lifecycle and metadata fields are excluded

Run ID, capture status, Dynamic End information, timestamps, Candidate sequence, source metadata, warnings, and other lifecycle/technical fields are absent from `AICandidateInput`.

### AC-12 — Legacy data is excluded and non-authoritative

Legacy rule definitions, keyword matches, confirmations, comparison/debug fields, and outcomes are not read into the output and cannot control R09 projection.

### AC-13 — Deterministic projection

The same source `candidate_record_id` and `document_text` produce the same projection outcome, independent of time, randomness, external state, configuration, or Legacy outcomes: the same non-blank text produces the same `AICandidateInput`, while the same missing/blank text produces the same failure.

### AC-14 — Local and side-effect-free

R09 mutates no source evidence, writes no Store, performs no external call, and creates no production side effect.

### AC-15 — Missing text fails without fallback

When source `document_text` is `None`, R09 returns no successful `AICandidateInput` and does not reconstruct, synthesize, or infer fallback text.

### AC-16 — Blank text fails without altering successful text

When source `document_text` is empty or whitespace-only, R09 returns no successful `AICandidateInput`. Blank checking does not trim or otherwise modify non-blank source text, and R09 performs no broader semantic resume validation.

### AC-17 — Projection is not eligibility

Successful construction of `AICandidateInput` does not assert normal completion, complete evidence, Evaluation eligibility, or Evaluation success.

### AC-18 — Projection is not a Candidate Decision

R09 produces no Match, Reject, score, reason, confidence, Candidate Decision, or action authorization.

### AC-19 — Capture-status policy remains deferred

R09 does not decide how completed, limited, partial, aborted, interrupted, empty, safety-stopped, or technically stopped Candidate evidence is treated by future Evaluation or production orchestration.

### AC-20 — Profile and Rule contracts remain separate

R09 does not read, copy, mutate, or execute ScreeningProfile, Criteria, Criterion IDs, `ScreeningRule`, `ScreeningRuleSet`, or Criterion Boolean mappings.

### AC-21 — No LLM or Runtime behavior

R09 creates no prompt, message, Provider/model selection, token-budget policy, SDK call, LLM request, response parser, retry, timeout, or Runtime error behavior.

### AC-22 — No Decision or Action integration

R09 does not favorite, forward, reject, skip, stop a Run, control browser/mouse behavior, or wire any result to the production action path.

### AC-23 — No persistence or schema expansion

R09 changes no Candidate, Screen, Run, Profile, Rule, OCR Store, dependency, or packaging schema and requires no `AICandidateInput` persistence, ID, version, digest, cache, history, or audit framework.

### AC-24 — No adjacent-requirement pre-implementation

R09 does not pre-implement AM7-R10 Criterion Boolean generation, AM7-R11 AI Runtime, AM7-R12 Candidate Decision/action integration, AM7-R13 persistence/failure degradation, or AM7-R14 replay/end-to-end integration.

## 17. Known Limitations / Explicit Deferrals

- The concrete Python type, module, function name, and exception types are deferred to TID.
- Future Criterion Boolean semantics and generation are deferred to AM7-R10.
- Prompt construction, token budgeting, Provider execution, and response handling are deferred to AM7-R11.
- Candidate Decision representation, traceability linkage, authority, and production action integration are deferred to AM7-R12.
- Persistence and failure/degradation behavior are deferred to AM7-R13.
- Replay and end-to-end orchestration are deferred to AM7-R14.
- The product policy determining which finalized capture/document statuses may proceed to Evaluation remains deferred to its owning later Requirement.

These deferrals do not weaken the R09 projection contract. They prevent the Candidate input layer from acquiring Evaluation, Runtime, Decision, persistence, or orchestration responsibilities.

## 18. Open Issues

None.

## 19. Contract Conflicts

None.

## 20. Final RPD Conclusion

AM7-R09 freezes a deterministic, local, Candidate-level content projection for authoritative non-blank Candidate document text:

```text
CandidateOcrDocument
  -> {
       candidate_record_id = CandidateOcrDocument.candidate_record_id,
       resume_text = CandidateOcrDocument.document_text
     }
```

The projection reuses the existing Candidate document text exactly, carries only the Candidate association and resume content, and exposes none of the underlying Screen/OCR/lifecycle/Legacy evidence schema to future AI Runtime consumers.

If Candidate document text is `None`, empty, or whitespace-only, projection fails with no successful `AICandidateInput` and no fallback reconstruction. Non-blank source text is copied exactly without trimming, normalization, rewriting, or broader semantic validation.

It performs no Screen reconstruction, content transformation, Evaluation, Rule execution, LLM call, Decision, action, persistence, or adjacent-requirement implementation. AM7-R07 evidence collection, AM7-R08 Candidate authority, and all earlier frozen contracts remain unchanged.
