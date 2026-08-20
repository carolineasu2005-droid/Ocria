# AM7-R08 — Candidate-level Decision Boundary

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R08
- Document Type: Requirement / Product Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r08-candidate-decision-boundary`
- Working HEAD / Upstream Baseline: `843e73fd71f71219e4cd323c9eea79a78847f75f`
- Prepared On: 2026-08-19 (Asia/Shanghai)

## Terminology

- **Screen**: one OCR evidence unit, represented today by an observation and, when recorded, an `OcrScreenRecord`.
- **Candidate evidence boundary**: the finalized `CandidateOcrDocument` for one Candidate capture lifecycle, containing or referencing the corresponding Candidate OCR evidence.
- **Legacy BossOCR mode**: the existing compatibility/fallback context in which a confirmed Legacy Screen-level rule match may remain production-authoritative and enter the existing Legacy action flow.
- **Ocria Am7 mode**: the product context in which production recruiting authority is Candidate-scoped. This term freezes an authority boundary; AM7-R08 does not require a new mode enum, selector, CLI, or runtime router.
- **Production Decision**: the final recruiting Match / Reject, qualified / rejected, or equivalent authoritative outcome that may later control a production Candidate/page action.
- **Legacy Screen-level result**: the existing Legacy keyword/rule match and confirmation outcome. It is authoritative only in Legacy BossOCR mode and non-authoritative in Ocria Am7 mode.

## 1. Requirement Summary

AM7-R08 freezes one product boundary:

> **Production Decision Scope = Candidate**

In Ocria Am7 mode, a Screen is evidence, not the final recruiting decision scope. Formal production Candidate-level evaluation becomes eligible only after the relevant Candidate evidence has crossed the accepted Candidate evidence boundary and the `CandidateOcrDocument` has been finalized for that Candidate lifecycle.

AM7-R08 does not implement the evaluator, Criterion Boolean contract, Rule execution, Candidate Decision engine, action integration, persistence, or any later AI requirement. It defines which scope may eventually hold production authority and which existing signals cannot hold that authority in Am7.

## 2. Problem Statement

The Legacy BossOCR decision chain evaluates a rule against one current Screen. Recruiting conditions, however, apply to the complete Candidate. This scope mismatch causes two opposite defects.

### 2.1 False positive when exclusion evidence scrolls away

Example:

```text
Screen 1: contains an exclusion fact such as “高中”
          but not every positive condition
          -> Rule(Screen 1) = False

Screen 2: the exclusion fact is outside the viewport
          and C#, Unity, game, SLG, or other positive facts appear
          -> Rule(Screen 2) may become True
```

If Screen 2 independently owns the production decision, the earlier exclusion evidence disappears from decision scope even though it remains true of the Candidate. That can create a false positive.

### 2.2 False negative when positive evidence is distributed

Example:

```text
Screen 1: C#
Screen 2: Unity + game
Screen 3: SLG
```

No individual Screen contains the entire conjunction, yet the complete Candidate evidence may support all required conditions. Requiring every fact to coexist in one viewport can create a false negative.

### 2.3 Root cause

The root defect is not merely a Legacy `NOT` expression defect. It is the difference between:

```text
Rule(Screen_n)
```

and the required Ocria Am7 business scope:

```text
Decision(Candidate)
```

Changing rule syntax alone cannot correct a decision made at the wrong evidence scope.

## 3. Goals

AM7-R08 shall:

1. Freeze Candidate as the sole Ocria Am7 production Decision scope.
2. Freeze Screen as an evidence scope in Ocria Am7.
3. Preserve the existing Legacy BossOCR Screen-level production chain inside Legacy mode.
4. Make every Legacy Screen-level result non-authoritative inside Ocria Am7 mode.
5. Require Candidate finalization/evidence boundary establishment before formal Am7 production evaluation may begin.
6. Preserve cross-Screen composition of positive and exclusion evidence at Candidate scope.
7. Require future production Candidate Decisions to be traceable to their `CandidateOcrDocument` and corresponding evidence.
8. Preserve Legacy-vs-Candidate disagreement as a future validation principle without creating comparison infrastructure.
9. Protect AM7-R05, AM7-R06, AM7-R07, Legacy OCR behavior, and AM7-R09–AM7-R14 boundaries.

## 4. Non-Goals

AM7-R08 does not include:

- deleting or disabling BossOCR Legacy judgment;
- converting Legacy BossOCR itself to Candidate-level evaluation;
- modifying Legacy confirmation or action behavior;
- rewriting the Legacy parser, AST, keyword grammar, or deterministic rules;
- changing AM7-R06 syntax, tokenizer, parser, evaluator, fixed ANY semantics, or failure behavior;
- adding Legacy `NOT` or Legacy `ANY(...)` syntax to AM7-R06;
- Candidate Input Builder or `StructuredCandidate` implementation;
- AI prompts or LLM Runtime execution;
- Criterion Boolean generation or its contract;
- actual Candidate-level Rule or AI Evaluation;
- a `CandidateDecision` schema, Decision status enum, Decision engine, Decision manager, or authority framework;
- favorite, forward, reject, skip, stop-run, browser, mouse, or other production action wiring for the Am7 path;
- Legacy-vs-Candidate comparison persistence, tables, logs, telemetry, audit database, or regression dataset framework;
- Candidate schema redesign or a new Decision/evidence-link schema;
- persistence or database expansion;
- a new status taxonomy;
- a new Gate, Guard, Scanner, Wrapper, Sanitizer, `DecisionGate`, `ActionGate`, interceptor, authority enum, runtime mode router, or generic Decision/Authority framework;
- a `CandidateDecision` placeholder or shadow-decision schema created only to represent R08 in source code;
- OCR capture, normalization, fingerprint, aggregation, similarity, Candidate finalization, or Dynamic End changes;
- AM7-R09–AM7-R14 implementation.

## 5. Targeted Repository Findings

The inspection was limited to the Frozen AM7-R07 design, current detector, Candidate evidence/finalization types, the existing Legacy match-to-action boundary, the AM7-R06 public module, and directly relevant tests. No implementation tests were run.

### 5.1 Current Legacy Screen-level result and action boundary

- `OCRKeywordDetector.detect(rules, first_observation=None)` remains the explicit Legacy entry.
- Legacy matching annotates `ScanObservation.matched_keyword`, `matched_rule`, and `rule_comparison`; independent confirmation produces `DetectionResult.confirmed_match`.
- In `simple_brush.py`, `detect_keywords(...)` calls the Legacy `detect(...)` entry and converts `confirmed_match` into a `keyword_hit` Boolean.
- `view_candidate(...)` consumes that Legacy Boolean and may invoke the existing favorite or forward behavior. This is the current Screen-level Legacy production chain.
- Directly relevant tests lock confirmed Legacy match, Legacy early return, and the current favorite/forward behavior.

### 5.2 Current AM7-R07 evidence path

- AM7-R07 RPD and TID are both v0.1 Frozen.
- `OCRKeywordDetector.scan_candidate(first_observation=None)` is implemented as a rule-independent detector entry. It clears incidental Legacy rule annotations from a reused first observation and invokes the shared scan lifecycle without Legacy rules.
- The Complete-Scan path does not call Legacy matching or confirmation and does not have Decision/Action dependencies.
- Current targeted tests confirm later-screen collection, rule independence, existing Dynamic End ownership, safety/technical reason preservation, and reuse of the Candidate evidence path.
- AM7-R07 provides the evidence collection boundary required by R08; R08 does not alter that lifecycle.

### 5.3 Current Candidate evidence and finalization

- `OcrScreenRecord` is the current persisted Screen evidence unit. It contains raw and normalized OCR evidence, fingerprints, aggregation/similarity projections, Dynamic End evidence, and optional Legacy comparison fields.
- `CandidateOcrBuilder` collects the Candidate's recorded screens and finalizes one existing `CandidateOcrDocument`.
- `CandidateOcrDocument` contains the corresponding screens, capture summary, Candidate document text/segments, normalization/aggregation/similarity summaries, Dynamic End facts, and Candidate/run identity.
- `simple_brush.finalize_current_candidate_recording(...)` invokes the builder's finalization and can persist the resulting Candidate document through the existing Store.
- The clean future boundary lies after successful `CandidateOcrDocument` finalization and before any future Candidate-level evaluator.

### 5.4 Current Decision availability

- No `CandidateDecision`, Decision status, Decision engine, or equivalent Am7 Candidate-level production Decision object exists in the inspected current modules.
- No current code consumes `CandidateOcrDocument` to produce an Am7 Candidate Decision or Am7 production action.
- No current code was found that gives an individual `formal_screen.raw_text` final Am7 Decision authority.
- The only existing Screen-to-production-action authority found is the explicitly preserved Legacy `detect_keywords(...) -> view_candidate(...)` chain.
- Therefore R08 can freeze the future authority boundary without adding a schema or modifying current runtime code.

### 5.5 Current AM7-R06 public boundary

- `screening_rule_engine.py` exposes immutable `ScreeningRule` and `ScreeningRuleSet` values plus `evaluate_rule_set(rule_set, criterion_results) -> bool`.
- R06 consumes an already supplied Criterion ID-to-Boolean mapping. It does not consume OCR Screens, `CandidateOcrDocument`, Legacy keyword syntax, or actions.
- R06 does not itself establish Candidate evidence scope and is not invoked by AM7-R08.

## 6. Decision Scope Invariant

The central frozen invariant is:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

In Ocria Am7 mode:

- no individual Screen;
- no individual `formal_screen.raw_text`;
- no individual `OcrScreenRecord`;
- no Legacy Screen-level match or non-match;
- no assertion that one Screen contains “enough” evidence;

may independently produce, imply, authorize, or control the final production Match / Reject or equivalent Candidate outcome.

Candidate scope is necessary for production authority. AM7-R08 does not specify the future algorithm that computes a Candidate-level result.

## 7. Legacy BossOCR Compatibility

The Legacy BossOCR chain remains valid and available in Legacy mode:

```text
Screen
  -> Legacy Rule Match
  -> existing independent confirmation
  -> existing Legacy judgment
  -> existing Legacy action
```

AM7-R08 does not delete, rewrite, disable, or reinterpret this path. Existing Legacy rule parsing, matching, confirmation, result semantics, favorite/forward behavior, and fallback use remain outside the R08 change.

Legacy Screen-level judgment remains production-authoritative only inside Legacy BossOCR mode.

## 8. Ocria Am7 Authority Boundary

The Ocria Am7 production authority chain is conceptually:

```text
Screens
  -> CandidateOcrDocument
  -> future Candidate-level Evaluation
  -> future Candidate Decision
  -> future production action
```

Inside this chain, a Legacy Screen-level result may be retained as shadow, debug, diagnostic, comparison, or regression-reference evidence, but it has no production authority.

Specifically:

```text
legacy_screen_match = True
```

does not imply:

```text
candidate_decision = MATCH
```

Likewise, one or all Legacy Screen-level matches being false does not imply Candidate Reject. Candidate facts may be distributed across Screens or represented by evidence no longer visible in the current viewport.

A Legacy Screen-level result cannot directly invoke favorite, forward, reject, skip, stop-run, or another production Candidate/page action in the Ocria Am7 path.

AM7-R08 freezes this authority rule but does not implement the future Am7 runtime path or mode selection.

### 8.1 Authority contract without forced runtime implementation

AM7-R08 is an authority/boundary requirement. It does not require a source-code implementation merely for the sake of having implementation.

Targeted technical inspection confirms that the current repository does not yet contain an Ocria Am7 Candidate Decision / Action production chain. Therefore AM7-R08 legitimately requires no runtime product-code change at this stage. The absence of an R08-specific runtime artifact does not weaken this Frozen authority contract.

AM7-R08 does not authorize a placeholder enforcement layer. In particular, it requires no `DecisionGate`, `ActionGate`, `CandidateDecision` placeholder, authority enum, runtime mode router, interceptor, guard, shadow-decision schema, or generic Decision/Authority framework.

The Frozen authority contract remains binding on later requirements, especially AM7-R09 through AM7-R12, when the Candidate input, evaluation, runtime, Decision, and action production chain is designed and implemented.

## 9. Candidate Finalization Prerequisite

Formal Ocria Am7 production evaluation is not eligible to begin until the Candidate evidence boundary has been established for that Candidate lifecycle:

```text
multiple OcrScreenRecord
  -> CandidateOcrDocument finalized
  -> Candidate-level production evaluation becomes eligible
```

The following are not authorization to begin final production evaluation:

- one Screen appearing complete enough;
- one Screen satisfying a positive condition;
- one confirmed Legacy Screen-level rule match;
- an intermediate aggregation, similarity, fingerprint, or Dynamic End observation;
- a Screen-level non-match.

Finalization is a necessary prerequisite, not a sufficient production Decision. A finalized document does not itself mean Match, Reject, complete evidence, or successful evaluation.

AM7-R08 does not decide which normal, limited, interrupted, aborted, or technically terminated Candidate documents are eligible for later Evaluation. That downstream treatment remains deferred under the accepted R07 boundary and later requirements.

## 10. Screen Role in Ocria Am7

Screen remains an evidence unit. Screen-level components may continue to provide:

- raw OCR boxes and text;
- normalized/comparison text;
- fingerprints and page-change evidence;
- aggregation and document-segment evidence;
- similarity/effective-new-content evidence;
- Dynamic End and capture evidence;
- optional Legacy shadow/debug match and comparison information.

These values may contribute to a later Candidate-scoped evaluation. None independently owns the final production Candidate Decision.

AM7-R08 adds no new Screen role field, schema discriminator, or authority flag.

## 11. Cross-Screen Evidence Composition

Future Candidate-level evaluation must be able to consider relevant evidence distributed across multiple Screens from the same Candidate evidence boundary.

Example:

```text
Screen 1 -> C#
Screen 2 -> Unity
Screen 3 -> SLG
```

If the finalized Candidate evidence supports all required Candidate-level conditions, the product contract must not require those facts to have appeared together on any single Screen.

This requirement does not prescribe concatenation, deduplication, prompting, Boolean generation, rule evaluation, evidence weighting, or conflict resolution. Those are later Evaluation/Input design decisions.

## 12. Exclusion Persistence Across Screens

Relevant Candidate evidence does not lose decision relevance merely because it has scrolled out of the current OCR viewport.

For example, an exclusion fact captured on Screen 1 remains part of the Candidate evidence considered by future Candidate-level evaluation even when Screen 2 contains only positive technical evidence.

The future production Decision must not depend on which facts happen to coexist on one current Screen. AM7-R08 does not define Legacy `NOT` reuse, exclusion parsing, Criterion semantics, or the future evaluator's algorithm.

## 13. Candidate Decision Traceability

Every future Candidate-level production Decision must be traceable to:

1. the relevant finalized `CandidateOcrDocument`; and
2. the corresponding Candidate OCR evidence from which the Decision was derived.

Traceability is a product invariant: a production Decision cannot be an unassociated Screen Boolean or an outcome detached from its Candidate evidence boundary.

AM7-R08 does not prescribe a Decision schema, field name, foreign key, digest, database table, audit event, log record, evidence link object, or retention framework. Exact representation belongs to later technical design and downstream Decision/persistence requirements.

## 14. Legacy Screen-level Shadow / Debug Role

In Ocria Am7 mode, Legacy Screen-level results may be retained only for non-authoritative purposes such as:

- shadow comparison;
- debugging;
- diagnosing old-versus-new behavior;
- regression analysis;
- reference evidence during coexistence validation.

They may not:

- decide Candidate Match or Reject;
- start final Candidate evaluation early;
- override a Candidate-level result;
- suppress Candidate-level evaluation;
- trigger a production action;
- become a fallback Candidate Decision merely because later evaluation is unavailable.

No particular field such as `legacy_screen_match` is required. Existing optional Legacy comparison information may remain where already accepted, but R08 adds no schema.

## 15. Legacy-vs-Candidate Comparison Principle

Later integration and acceptance should be capable of demonstrating meaningful disagreements between the Legacy Screen-level judgment and the future Candidate-level judgment, especially:

- a Legacy false positive caused by exclusion evidence scrolling away; and
- a Legacy false negative caused by positive facts being distributed across Screens.

Such disagreements are useful future regression evidence. They do not imply that AM7-R08 must record them now.

AM7-R08 does not authorize a comparison database, shadow-decision table, persistence schema, generic comparison logger, telemetry/event framework, or regression dataset framework. Exact observation and recording mechanisms are deferred.

## 16. AM7-R07 Boundary

AM7-R07 remains unchanged.

R07 owns the accepted responsibility:

> Collect Candidate evidence without Legacy business-rule truncation.

R08 owns the distinct responsibility:

> Only Candidate scope may own the Ocria Am7 production Decision.

AM7-R08 does not modify:

- `scan_candidate(...)`;
- Legacy `detect(...)`;
- `_run_scan_lifecycle(...)`;
- Complete-Scan rule independence;
- Legacy OCR R07 Dynamic End;
- safety budget or termination reasons;
- retry, focus recovery, or Candidate Switch Verification;
- `OcrScreenRecord`, Candidate evidence construction, or Candidate finalization.

AM7-R08 adds no completeness detector and does not reinterpret Dynamic End as a business Decision.

## 17. AM7-R05 Boundary

AM7-R05 ScreeningProfile remains unchanged. AM7-R08 does not modify Criterion schema, Profile versioning, `criteria_digest`, persistence, Run binding, or Configuration/Execution lifecycle.

Screening criteria remain configuration, not Screen-level production authority.

## 18. AM7-R06 Boundary and Legacy Rule Terminology

AM7-R06 Screening Rule Engine V2 remains unchanged and is not executed by R08.

AM7-R08 does not modify:

- `ScreeningRule`;
- `ScreeningRuleSet`;
- the Criterion ID-to-Boolean mapping contract;
- tokenizer/parser or token boundaries;
- precedence;
- fixed multi-Rule ANY;
- validation or failure semantics;
- the supported operator set.

Legacy BossOCR terms such as `NOT`, `ANY(...)`, Parser, or AST describe the Legacy rule language only. They are not imported into AM7-R06. Whether any Legacy parser behavior is ever reused at Candidate scope is an unresolved future product/technical choice, not authorization under AM7-R08.

## 19. AM7-R09–AM7-R14 Deferrals

The following remain outside AM7-R08:

- **AM7-R09 — AI Candidate Input Builder**: Candidate transformation and input preparation.
- **AM7-R10 — AI Screening Boolean Contract**: Criterion Boolean generation and semantics.
- **AM7-R11 — AI Screening Runtime**: LLM execution and runtime behavior.
- **AM7-R12 — Candidate Decision & Action Integration**: Candidate Decision execution, authority wiring, and production actions.
- **AM7-R13 — AI persistence / failure degradation**: persistence and degraded/failure behavior.
- **AM7-R14 — AI Replay / overall integration**: replay and end-to-end integration.

AM7-R08 neither pre-implements nor narrows the future approved designs for those requirements, except that they must respect the frozen Candidate production Decision scope.

## 20. Invariants

1. Production Decision Scope in Ocria Am7 is Candidate.
2. Screen is evidence scope in Ocria Am7.
3. An individual Screen, `formal_screen.raw_text`, or `OcrScreenRecord` cannot independently produce final Am7 Match or Reject.
4. Legacy Screen-level judgment remains production-authoritative only inside Legacy BossOCR mode.
5. Legacy BossOCR matching, confirmation, judgment, and action behavior remain available and unchanged.
6. Legacy Screen-level match and non-match are non-authoritative inside Ocria Am7.
7. A Legacy Screen-level result cannot directly trigger an Am7 production action.
8. Formal Am7 production evaluation cannot begin before the relevant `CandidateOcrDocument` is finalized.
9. Candidate finalization is necessary but does not itself produce or guarantee a production Decision.
10. Candidate-level evaluation may use relevant evidence distributed across multiple Screens.
11. Relevant exclusion evidence remains Candidate evidence after it leaves the current viewport.
12. Candidate Decision semantics do not require all relevant facts to coexist on one Screen.
13. Every future production Candidate Decision is traceable to its `CandidateOcrDocument` and corresponding OCR evidence.
14. Legacy Screen-level results may remain shadow/debug/reference information but never production authority in Am7.
15. Legacy-vs-Candidate disagreement is a future validation principle, not an R08 persistence requirement.
16. AM7-R08 creates no Candidate Decision schema, status, engine, or action integration.
17. AM7-R07 OCR lifecycle and evidence boundary remain unchanged.
18. Legacy OCR R07 Dynamic End remains unchanged and does not become Decision authority.
19. AM7-R05 ScreeningProfile remains unchanged.
20. AM7-R06 Screening Rule Engine V2 remains unchanged and uninvoked by R08.
21. Legacy rule syntax is not added to AM7-R06.
22. AM7-R08 adds no LLM, Criterion Boolean, persistence, database, schema, comparison, telemetry, or framework implementation.
23. AM7-R09–AM7-R14 are not pre-implemented.
24. AM7-R08 does not require runtime product-code change when no current Ocria Am7 Candidate Decision / Action production chain exists, and it does not require placeholder enforcement artifacts.
25. The Frozen R08 authority contract remains binding on later requirements, especially AM7-R09 through AM7-R12.

## 21. Acceptance Criteria

### AC-01 — Legacy production chain remains available

Legacy BossOCR mode retains the existing Screen -> Legacy Rule Match -> confirmation -> Legacy judgment -> Legacy action behavior.

### AC-02 — Candidate owns Am7 production scope

The Ocria Am7 product contract recognizes Candidate, not an individual Screen, as the final production Decision scope.

### AC-03 — Formal Screen text is not final authority

No individual `formal_screen.raw_text`, Screen observation, or `OcrScreenRecord` can independently authorize final Am7 Match or Reject.

### AC-04 — Legacy positive cannot trigger Am7 action

A Legacy Screen-level match cannot directly trigger favorite, forward, reject, skip, stop-run, or another production action in the Ocria Am7 path.

### AC-05 — Legacy negative cannot force Am7 rejection

A Legacy Screen-level non-match, including all Screen-level matches being false, cannot independently force an Am7 Candidate rejection.

### AC-06 — Candidate finalization precedes evaluation

Formal Am7 production evaluation is not eligible to begin before the relevant `CandidateOcrDocument` has been finalized for that Candidate lifecycle.

### AC-07 — Finalization is not a Decision

A finalized `CandidateOcrDocument` establishes an evidence boundary but does not itself imply Match, Reject, successful evaluation, or complete evidence.

### AC-08 — Cross-Screen positive composition

Future Candidate-level evaluation can consider relevant positive evidence distributed across different Screens of the same finalized Candidate evidence boundary.

### AC-09 — Exclusion evidence persists

Relevant exclusion evidence captured on an earlier Screen remains part of Candidate-level evidence semantics after it scrolls out of the current viewport.

### AC-10 — Simultaneous viewport coexistence is not required

Candidate Decision semantics do not require every relevant positive and exclusion fact to appear simultaneously on one Screen.

### AC-11 — Decision traces to Candidate document

Every future production Candidate Decision is traceable to the relevant finalized `CandidateOcrDocument`.

### AC-12 — Decision traces to OCR evidence

Every future production Candidate Decision is traceable through that Candidate document to its corresponding Candidate OCR evidence.

### AC-13 — Legacy shadow/debug data may remain

Ocria Am7 may retain Legacy Screen-level match information for shadow, debugging, diagnostic, comparison, reference, or regression purposes.

### AC-14 — Shadow/debug data remains non-authoritative

Retained Legacy Screen-level data cannot decide, override, suppress, or directly action an Am7 Candidate outcome.

### AC-15 — Disagreement is future regression evidence

Future coexistence validation may use Legacy false-positive and false-negative disagreements as meaningful regression evidence.

### AC-16 — No comparison infrastructure

AM7-R08 requires no comparison database, shadow-decision table, comparison logger, telemetry framework, audit database, or regression dataset framework.

### AC-17 — AM7-R07 Complete Scan remains unchanged

`scan_candidate(...)`, Legacy `detect(...)`, rule independence, safety/technical termination, recovery, switching, and Candidate evidence construction receive no R08 change.

### AC-18 — Legacy OCR R07 Dynamic End remains unchanged

Dynamic End algorithms, thresholds, states, reasons, and completion authority receive no R08 change or Decision responsibility.

### AC-19 — AM7-R05 remains unchanged

ScreeningProfile schema, versioning, digest, persistence, Run binding, and lifecycle receive no R08 change.

### AC-20 — AM7-R06 remains unchanged

Screening Rule Engine V2 values, Boolean mapping, parser, evaluator, fixed ANY, and failure semantics receive no R08 change or invocation.

### AC-21 — Legacy syntax is not imported into R06

AM7-R08 does not add Legacy `NOT`, Legacy `ANY(...)`, or other Legacy parser/AST behavior to AM7-R06.

### AC-22 — No LLM execution

AM7-R08 performs no LLM call, prompt execution, or AI Runtime behavior.

### AC-23 — No Criterion Boolean contract

AM7-R08 creates no Criterion ID-to-Boolean generation, semantics, or input-building contract.

### AC-24 — No Candidate Decision engine implementation

AM7-R08 creates no Candidate Decision object, schema, status enum, engine, manager, execution behavior, `CandidateDecision` placeholder, `DecisionGate`, `ActionGate`, interceptor, guard, authority enum, runtime mode router, shadow-decision schema, or generic Decision/Authority framework.

### AC-25 — No Am7 action integration

AM7-R08 wires no favorite, forward, reject, skip, stop-run, browser, mouse, or other production action to the Am7 Candidate path.

### AC-26 — No Candidate schema expansion

No Screen, `OcrScreenRecord`, `CandidateOcrDocument`, Profile, Rule, or Candidate schema is expanded merely to freeze the R08 authority boundary.

### AC-27 — No persistence expansion

AM7-R08 adds no persistence, database, audit, telemetry, comparison, or evidence-link storage contract.

### AC-28 — No later-requirement pre-implementation

AM7-R09–AM7-R14 functionality is not implemented under AM7-R08.

Where targeted inspection confirms that no current Ocria Am7 Candidate Decision / Action production chain exists, AM7-R08 may be satisfied without a runtime product-code change. Its Frozen authority contract remains binding on later requirements, especially AM7-R09 through AM7-R12.

## 22. Known Limitations / Explicit Deferrals

- The future Candidate evaluator, its inputs, and its algorithm are deferred.
- Criterion Boolean semantics and generation are deferred to AM7-R10.
- LLM execution is deferred to AM7-R11.
- Candidate Decision representation, execution, and action authority wiring are deferred to AM7-R12.
- Persistence and failure/degradation behavior are deferred to AM7-R13.
- Replay and end-to-end integration are deferred to AM7-R14.
- The product treatment of normal, limited, interrupted, aborted, or technically terminated Candidate documents remains deferred.
- Exact Decision-to-evidence traceability representation is deferred.
- Exact Legacy-vs-Candidate disagreement observation/recording mechanics are deferred.
- AM7-R08 does not decide whether a future evaluator uses document text, segments, individual screens, structured input, LLM output, R06, or another approved combination.
- The current repository does not yet contain the future Am7 Candidate Decision/Action chain; this is expected, legitimately requires no R08 runtime product-code change, and does not weaken the Frozen authority contract binding later requirements, especially AM7-R09 through AM7-R12.
- No placeholder enforcement layer or generic Decision/Authority framework is required to represent this boundary in current source code.

## 23. Open Issues

None.

The Frozen requirement intent resolves the Decision scope, Legacy coexistence, Candidate finalization prerequisite, cross-Screen evidence semantics, traceability invariant, and downstream deferrals without requiring a schema or implementation choice.

## 24. Contract Conflicts

None.

The current Legacy Screen-level action path is compatible because it remains explicitly confined to Legacy BossOCR mode. The separate AM7-R07 Complete-Scan evidence path has no Decision/Action authority and provides the clean Candidate evidence boundary required by R08. AM7-R06 remains a downstream pure Boolean combiner and is neither modified nor invoked.

## 25. Final Product Conclusion

AM7-R08 freezes the authority boundary that prevents Screen-scoped evidence from becoming an Am7 Candidate-scoped production decision:

```text
Screen = Evidence Scope
Candidate = Ocria Am7 Production Decision Scope
```

Legacy BossOCR may continue its accepted Screen-level production behavior inside Legacy mode. In Ocria Am7 mode, Legacy Screen-level positive and negative results are non-authoritative, final Candidate evaluation cannot begin before the `CandidateOcrDocument` evidence boundary, and future Candidate Decisions must remain traceable to that document and its corresponding evidence.

Because the current repository has no Ocria Am7 Candidate Decision / Action production chain, this Frozen authority/boundary requirement legitimately requires no runtime product-code change. It remains binding on the later Candidate production chain, especially AM7-R09 through AM7-R12, without authorizing placeholder gates, routers, guards, schemas, enums, interceptors, or frameworks.

No Evaluation, Rule execution, LLM, Candidate Decision, action, schema, persistence, comparison infrastructure, OCR change, or AM7-R09–AM7-R14 implementation is authorized by this RPD.
