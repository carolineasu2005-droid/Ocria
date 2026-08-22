# Ocria Am7 — AM7-R12 Candidate Decision & Action Integration

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R12
- Document Type: Requirement / Product Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Requirement Branch: `am7-r12-candidate-decision-action-integration`
- Working HEAD / Upstream Baseline: `ca3cf7b3a4ceda091f67d2e8fc65e535623b7caf`

## 1. Document Status

This document defines the Frozen AM7-R12 product contract. Human Review approved explicit in-memory Run input as the RuleSet source and binding, no product decision remains open, and this RPD is the authoritative product source for subsequent AM7-R12 TID work.

## 2. Requirement Summary

AM7-R12 connects the accepted R11 Candidate-level AI screening result to the accepted R06 Screening Rule Engine, produces one formal Candidate Decision, and uses that Decision only to authorize the existing favorite or forward action path.

The formal production chain is:

```text
OcrScreenRecord
    -> finalized CandidateOcrDocument
    -> R09 AICandidateInput
    -> R11 AI Screening Runtime
    -> complete Criterion Boolean mapping
    -> R06 Screening Rule Engine
    -> R12 CandidateDecision
    -> optional existing action
    -> existing Candidate continuation
```

R12 changes only the condition under which an existing action path is authorized. It does not redesign Candidate scanning, AI evaluation, Rule evaluation, action mechanics, or Candidate continuation.

## 3. Goals

AM7-R12 must:

- preserve `Screen = Evidence Scope` and `Candidate = Ocria Am7 Production Decision Scope`;
- map the accepted R11 result and R06 Boolean result to exactly one normal Candidate Decision status;
- distinguish an AI technical failure from a successful business rejection;
- prevent a RuleSet/configuration failure from becoming a business Decision;
- authorize the existing favorite or forward path only for a qualified Candidate;
- keep the existing action result separate from the Candidate Decision;
- return every normal Candidate outcome to the existing batch and Candidate-continuation flow;
- establish one explicit, stable RuleSet binding for all Candidates in a Run.

## 4. Non-Goals

AM7-R12 does not introduce or redesign:

- OCR capture, Complete Scan, Dynamic End, Candidate construction, or Candidate finalization;
- Criteria, `ScreeningProfileVersion`, or R06 expression semantics;
- AI Prompt construction, Provider invocation, or Boolean response validation;
- favorite, forward, next-Candidate, focus-restore, calibration, mouse-motion, or browser-automation mechanics;
- a third action mode;
- AI retry, fallback, degradation, recovery, or consecutive-failure stop policy;
- AI result, failure, Decision, action, or Rule persistence;
- replay, cache, hashes, digests, migration, packaging, or release behavior;
- a generic Decision Engine, Action Engine, Gate, Guard, Scanner, Wrapper, Sanitizer, Dispatcher, Pipeline, or orchestration framework.

## 5. Accepted Upstream Contracts

AM7-R12 composes, and does not redesign, these accepted contracts:

- AM7-R05: immutable saved `ScreeningProfileVersion`, non-empty Criteria, and the Run-level Profile binding of `screening_profile_id`, `profile_version`, and `criteria_digest`;
- AM7-R06: immutable `ScreeningRule`, immutable one-or-more `ScreeningRuleSet`, fixed multi-Rule ANY semantics, deterministic Boolean evaluation, and explicit validation/input failures;
- AM7-R07: rule-independent Candidate Complete Scan and finalized Candidate evidence;
- AM7-R08: Screen evidence authority, Candidate production-Decision authority, Candidate-finalization prerequisite, and Legacy shadow/compatibility boundary;
- AM7-R09: exact finalized-Candidate to `AICandidateInput` projection;
- AM7-R10: complete strict-Boolean Criterion mapping contract;
- AM7-R11: `AIScreeningResult` with exact Candidate identity and exact `completed` or `failed` AI status.

## 6. Product Context / Targeted Repository Findings

The targeted inspection was limited to the governing document, the named accepted R05/R06/R08/R09/R10/R11 design and acceptance artifacts, and the directly relevant runtime, Rule, Profile, Candidate, and current main-loop code.

Observed facts at the stated baseline:

- `ai_screening_runtime.py` exposes immutable `AIScreeningResult(candidate_record_id, ai_status, criteria_results)` and `run_ai_screening(candidate, profile, config)`. `completed` carries the complete validated Boolean mapping; `failed` carries `None`.
- `screening_rule_engine.py` exposes immutable `ScreeningRule`, immutable `ScreeningRuleSet`, `evaluate_rule_set(rule_set, criterion_results) -> bool`, `ScreeningRuleValidationError`, and `ScreeningRuleInputError`. It contains no Rule persistence or Run binding.
- `screening_profile.py` defines `ScreeningProfileVersion` with `screening_profile_id`, `profile_version`, `criteria`, `criteria_digest`, and `created_at`. It has no `rule_set` field.
- `ScreeningProfileBinding` in `ocr_records.py` contains only `screening_profile_id`, `profile_version`, and `criteria_digest`. No current Run manifest field identifies a RuleSet.
- `simple_brush.run()` loads the selected saved Profile Version, verifies its Criteria digest, constructs the accepted Profile binding, and keeps the loaded `profile_version` locally. It does not currently obtain, bind, or execute a `ScreeningRuleSet`.
- The startup menu can prepare the existing AI Provider configuration and a Screening Profile, but it has no RuleSet-authoring, RuleSet-selection, or RuleSet-binding source.
- The current Legacy action-authorization point is inside `view_candidate()`: a confirmed `keyword_hit` enters the existing `action_mode` branch and may call `perform_favorite_action()` or `forward_one_candidate()`. That occurs before `finalize_current_candidate_recording()` returns the Candidate document.
- `finalize_current_candidate_recording()` already returns the finalized `CandidateOcrDocument` after best-effort storage. Current main-loop call sites do not retain that return value.
- Candidate switching, switch verification, finalization, batch refresh, and continuation remain controlled by the existing main loop. `next_candidate()` performs only the existing right-key switch and wait.
- `perform_favorite_action()` and `forward_one_candidate()` already own their page interactions and focus restoration. `forward_one_candidate()` also retains its existing action-specific limits and failure behavior.
- No production source outside R06 tests currently constructs a `ScreeningRuleSet`, and no current Profile, CLI, Run binding, or main-flow value can be reused as an authoritative RuleSet source.

These findings establish a small Candidate-finalization-to-continuation integration seam and confirm that no pre-existing repository source can supply the formal RuleSet. Human Review has resolved that absence through the explicit Run-setup input contract in Section 11.

## 7. Candidate Decision Boundary

The R12 Decision operation consumes:

- one actual `AIScreeningResult` produced for the finalized Candidate by R11; and
- the one formal `ScreeningRuleSet` already bound to the active Run.

The finalized `CandidateOcrDocument`, saved Profile Version, and current complete AI Provider configuration remain the upstream production inputs used to obtain the R11 result. R12 does not duplicate those values inside its Decision object.

The formal Decision sequence is:

```text
if ai_result.ai_status == "failed":
    CandidateDecision = ai_failed
    do not call R06

if ai_result.ai_status == "completed":
    rule_result = R06.evaluate_rule_set(
        run_bound_rule_set,
        ai_result.criteria_results,
    )
    true  -> CandidateDecision = qualified
    false -> CandidateDecision = rejected
```

The R06 operation receives the exact completed R11 mapping and the exact RuleSet bound to the Run. R12 does not coerce, fill, filter, reorder, or reinterpret Criterion values.

## 8. CandidateDecision Contract

The minimum formal product value is:

```python
@dataclass(frozen=True)
class CandidateDecision:
    candidate_record_id: str
    decision_status: Literal[
        "qualified",
        "rejected",
        "ai_failed",
    ]
```

This two-field immutable value is required because a bare Boolean cannot distinguish rejection from AI failure, and an unassociated status would weaken the accepted Candidate trace boundary. The exact Python module and constructor mechanics belong to TID after this RPD is approved.

`CandidateDecision` contains no Criterion results, Rule result, Rules, AI result, Provider, model, Prompt version, failure reason, explanation, evidence, action mode, action result, timestamps, hashes, or persistence metadata.

The three statuses are mutually exclusive and exhaustive for a normal Candidate Decision:

- `qualified`: R11 completed and R06 returned exact Boolean `true`;
- `rejected`: R11 completed and R06 returned exact Boolean `false`;
- `ai_failed`: R11 returned its accepted technical-failure result.

No `unknown`, `manual_review`, `skipped`, `action_failed`, `rule_failed`, `invalid`, `pending`, `retrying`, `degraded`, `blocked`, `error`, or other Candidate Decision status exists in R12.

## 9. Candidate Identity and Traceability

R11 already associates its result with the exact source `CandidateOcrDocument.candidate_record_id`. R12 copies `ai_result.candidate_record_id` exactly into `CandidateDecision.candidate_record_id`.

R12 must not generate, normalize, replace, hash, prefix, suffix, or otherwise transform the Candidate identity. This exact identity links the Decision back to the finalized Candidate document and its evidence without copying the document or evidence into the Decision value.

## 10. AI Result to Decision Semantics

### 10.1 Completed AI result

A completed R11 result is not itself a qualified Decision. R12 must submit its complete strict-Boolean Criterion mapping to R06 with the Run-bound RuleSet.

- R06 `true` produces `qualified`.
- R06 `false` produces `rejected`.

A valid all-false R11 result remains an AI-completed result. Its business Decision is whatever the formal RuleSet produces; R12 must not hard-code all-false as an AI failure or bypass R06.

### 10.2 Failed AI result

An R11 `failed` result maps exactly to `ai_failed`. R12 must not call R06, fabricate a mapping, treat the failure as all-false, or produce `rejected`.

`ai_failed` means only that R11 already classified the Candidate-level AI evaluation as a technical failure. It does not include an R06 failure, action failure, integration defect, programming defect, or invalid R12 entry value.

## 11. RuleSet Source / Run Binding

### 11.1 Selected source

Human Review has selected **Option A — Explicit in-memory Run input**.

Before Candidate execution begins, the Run-setup boundary explicitly receives the R06 Rule definition or definitions required for that Run and constructs or resolves exactly one formal immutable `ScreeningRuleSet` through the accepted R06 API.

The product source is this explicit Run-setup input. It is not Configuration Mode state, Profile data, Legacy rule data, or a per-Candidate lookup. TID may determine the smallest exact interactive and non-interactive call site and the constructor mechanics using existing R06 APIs; R12 does not freeze CLI prompt text or line-level placement.

### 11.2 Ownership and Candidate access

Run setup owns resolution and binding of the one formal RuleSet. The current live Run execution holds that exact immutable value in memory and supplies it unchanged to every Candidate-level R12 Decision.

Candidate processing must never:

- reload or rediscover the RuleSet;
- derive it from Criteria;
- derive it from Legacy keyword rules;
- edit or replace it;
- switch it per Candidate;
- construct a different RuleSet for an individual Candidate.

R06 OR, grouping, precedence, and multi-Rule ANY semantics remain authoritative. R12 must not auto-AND Criteria, create one implicit Rule per Criterion, convert Legacy keywords into R06 Rules, or bypass R06.

### 11.3 Current live execution lifetime

The binding is stable for the current live execution session of the Run:

- Active execution uses the bound immutable RuleSet;
- Paused execution retains that same binding;
- resume within the same live process/session continues with that same binding;
- Candidate processing cannot edit, replace, or switch the binding;
- the in-memory binding ends when that live execution is terminally stopped.

R12 does not provide durable RuleSet restoration after a process crash or restart. Crash/restart persistence, replay, and durable reproducibility remain outside R12 and under later persistence/replay ownership.

### 11.4 Repository conclusion and explicit exclusions

The baseline repository did not already contain an authoritative RuleSet source or binding: R05 binds only Profile identity/version/digest, R06 intentionally introduced no persistence or Run binding, and the current CLI/main flow had no formal RuleSet input. Human Review resolved this repository gap through the selected explicit Run-setup input; it did not add a store or alter an upstream schema.

R12 adds no:

- RuleSet persistence or RuleSet store;
- RuleSet ID, version, or digest;
- RunManifest RuleSet schema;
- ORM, database, or migration;
- `ScreeningProfileVersion.rule_set`;
- Profile schema or immutable-history change.

The former Option B separate configuration artifact is rejected for R12 because it would introduce new persistence and association contracts. It is not an open alternative.

## 12. Rule Engine Integration Contract

R06 is called exactly when R11 returns `completed`. It is not called for `failed`.

R12 uses the accepted `evaluate_rule_set()` Boolean result directly. It must not replace the R06 tokenizer, parser, validator, precedence, mapping validation, referenced-ID validation, or fixed multi-Rule ANY behavior.

If R06 cannot produce a Boolean because of a malformed RuleSet, missing referenced Criterion result, invalid key/value, wrong input object, or another R06 validation/input failure:

- no `CandidateDecision` is produced for that evaluation;
- the condition is a configuration/integration failure, not a normal Candidate status;
- it is not converted to `qualified`, `rejected`, or `ai_failed`;
- it does not fail open or fail closed as business `false`;
- no favorite or forward action is authorized.

The exact accepted R06 exception propagation and the minimum main-loop handling mechanics belong to TID. R12 must not invent a fourth Decision status to contain this boundary.

## 13. Production Integration Point

The minimum semantic integration point is after the existing Candidate lifecycle has successfully produced the finalized `CandidateOcrDocument` and before the main loop hands control to the existing Candidate/batch continuation.

Conceptually:

```text
Complete Scan finishes
    -> finalize_current_candidate_recording(...) returns CandidateOcrDocument
    -> R11 run_ai_screening(...)
    -> R12 Decision using the Run-bound RuleSet
    -> optional existing action when qualified
    -> existing switch / next-Candidate / batch continuation
```

The current return value from `finalize_current_candidate_recording()` is the smallest existing Candidate handoff. R12 should use that value rather than reconstructing a Candidate from Screens or adding another finalization layer.

The exact line-level placement must preserve the current switch-context preparation, Candidate-switch verification, focus restoration, batch refresh, stop behavior, and last-Candidate handling. That placement belongs to TID; this RPD does not authorize redesign of those mechanisms.

For the Ocria Am7 production path, the current Legacy `keyword_hit` action call must not run before Candidate finalization or independently authorize an action. Legacy code may remain for its compatibility/shadow role without becoming Am7 authority.

## 14. Action Authorization Contract

Only `CandidateDecision.decision_status == "qualified"` authorizes entry into the existing `action_mode` branch.

```text
qualified
    -> authorize existing action_mode path
    -> favorite or forward path may run under all existing action controls

rejected or ai_failed
    -> no favorite
    -> no forward
```

Authorization is not an instruction to bypass current action prerequisites, calibration, safety controls, suppression controls, or failure behavior. Legacy keyword definitions or match outcomes are not action-authorization inputs in the Am7 production path.

## 15. favorite / forward Reuse Contract

R12 preserves exactly the two current action modes:

- `qualified + favorite` enters the existing favorite path and may call the existing `perform_favorite_action()`;
- `qualified + forward` enters the existing forward path and may call the existing `forward_one_candidate()` after its existing controls allow execution.

R12 adds no third action mode and does not change either function's click mechanics, region calibration, waits, focus restoration, action-specific limits, return behavior, or error behavior.

The Candidate Decision and action outcome are independent:

```text
qualified -> action authorized -> action succeeds or fails
```

An action failure, skip, or suppression does not retroactively change `qualified` to `rejected` or `ai_failed`. R12 adds no `action_failed` Candidate Decision.

## 16. no_forward_mode Contract

`no_forward_mode` remains authoritative inside the existing forward-action path.

For a qualified Candidate in `forward` mode:

- when existing forward controls permit and `no_forward_mode` is false, the existing forward path may call `forward_one_candidate()`;
- when `no_forward_mode` is true, real forwarding remains suppressed exactly as today;
- suppression does not change the Candidate Decision from `qualified`;
- suppression does not authorize favorite as a fallback.

R12 does not redefine `no_forward_mode` or introduce a parallel dry-run setting.

## 17. Candidate Continuation / next_candidate Boundary

`qualified`, `rejected`, and `ai_failed` all complete normal Candidate Decision processing and then return control to the same existing Candidate/batch continuation.

R12 does not branch directly to a newly designed switch behavior for rejection or AI failure. It does not make `next_candidate()` a responsibility of `CandidateDecision`, and it does not modify the function. Existing loop position, batch-filter behavior, verified Candidate switching, last-Candidate handling, refresh, pause, stop, and safe continuation remain authoritative.

The normal product sequence is:

```text
Decision -> optional existing action -> Candidate processing ends
         -> existing continuation -> existing next-Candidate behavior
```

## 18. Legacy Compatibility Boundary

Legacy BossOCR screen-level keyword/match behavior remains within its accepted compatibility, shadow, and reference boundary. It may continue to exist and to provide incidental comparison/log information where already supported.

In the Ocria Am7 production path:

- no single Screen can produce final `qualified`, `rejected`, or `ai_failed`;
- `keyword_hit`, Legacy rule definitions, keyword outcomes, and Legacy confirmation outcomes cannot authorize or deny the production action;
- Legacy data cannot replace the finalized Candidate, R11 result, R06 evaluation, or R12 Decision;
- changing Legacy rule/match outcomes must not change the R12 Candidate Decision for the same finalized Candidate, R11 result, and Run-bound RuleSet.

R12 does not require a repository-wide Legacy refactor. It only removes Legacy match authority from the Am7 production action-authorization condition.

## 19. Failure Semantics

### 19.1 AI technical failure

An accepted R11 `failed` result produces `CandidateDecision(..., "ai_failed")`, invokes no R06 evaluation, authorizes no action, uses the existing runtime/log visibility, and returns to normal Candidate continuation.

In R12, “record AI failure” means this formal Candidate Decision plus the minimum existing logging visibility needed by the current flow. It does not mean a database row, file ledger, retry queue, failure history, counter policy, or degradation state.

### 19.2 Business rejection

An R11 completed result followed by R06 `false` produces `rejected`, authorizes no action, and returns to normal Candidate continuation. It must remain distinguishable from `ai_failed`.

### 19.3 Rule/configuration failure

An R06 failure produces no normal Candidate Decision and no action. It remains an explicit configuration/integration failure. TID must use the accepted R06 error boundary without normalizing it to business data or inventing a status framework.

### 19.4 Action failure

An action failure occurs after a `qualified` Decision. It does not alter that Decision. R12 adds no new retry, recovery, fallback, stop condition, or action-failure persistence; existing action/main-loop behavior remains authoritative.

## 20. R13 / R14 Boundary

AM7-R13 retains ownership of:

- AI result and failure persistence;
- retry, repeated-invocation, degradation, fallback, and recovery policy;
- consecutive-failure counters or stop policy;
- persistent Candidate Decision or action-outcome records.

AM7-R14 retains ownership of:

- AI and Decision replay;
- cache and replay lookup;
- additional hashes/digests and reproducibility data;
- overall Am7 integration history, migration, packaging, and release behavior.

R12 introduces none of these capabilities.

## 21. Product Invariants

1. Screen evidence never has Ocria Am7 production Decision or action authority.
2. One normal R12 Decision is Candidate-level and has exactly one of three statuses: `qualified`, `rejected`, or `ai_failed`.
3. `qualified` requires both R11 `completed` and R06 `true`.
4. `rejected` requires both R11 `completed` and R06 `false`.
5. `ai_failed` requires R11 `failed` and never invokes R06.
6. R06 failure is not a normal Candidate Decision and authorizes no action.
7. Only `qualified` authorizes an existing action path.
8. Action success, failure, skip, or suppression cannot modify the Candidate Decision.
9. Candidate identity is copied exactly from the R11 result.
10. The same immutable formal RuleSet is used for every Candidate in the current live Run execution, including pause and resume within the same live process/session.
11. The RuleSet is never inferred from Criteria or Legacy keyword rules.
12. Existing action mechanics and Candidate continuation remain outside the Decision value and outside R12 redesign.

## 22. Acceptance Criteria

### AC-01 — Candidate-finalization authority

The Am7 production chain obtains a finalized `CandidateOcrDocument` before invoking R11 or producing an R12 Decision; no Screen produces a production Candidate Decision.

### AC-02 — Qualified mapping

For an R11 `completed` result whose exact complete mapping causes the Run-bound R06 RuleSet to return `true`, R12 produces exactly `CandidateDecision(ai_result.candidate_record_id, "qualified")`.

### AC-03 — Rejected mapping

For an R11 `completed` result whose exact complete mapping causes the Run-bound R06 RuleSet to return `false`, R12 produces exactly `CandidateDecision(ai_result.candidate_record_id, "rejected")`.

### AC-04 — AI-failed mapping

For an R11 `failed` result, R12 produces exactly `CandidateDecision(ai_result.candidate_record_id, "ai_failed")`.

### AC-05 — No Rule evaluation after AI failure

An R11 `failed` result causes no call to `evaluate_rule_set()` and no synthetic Criterion mapping.

### AC-06 — Exact Decision status domain

Normal Candidate Decisions accept exactly `qualified`, `rejected`, or `ai_failed`; no fourth status or combined state is introduced.

### AC-07 — Minimum Decision shape

`CandidateDecision` is immutable and contains exactly `candidate_record_id` and `decision_status`, with none of the explicitly excluded upstream, reason, action, timing, hash, or persistence fields.

### AC-08 — Exact Candidate trace identity

Every produced Decision copies the exact R11 `candidate_record_id` without generation, normalization, replacement, or hashing.

### AC-09 — Exact R06 inputs and semantics

For an R11 completed result, R12 supplies the exact complete `criteria_results` mapping and exact Run-bound `ScreeningRuleSet` to accepted R06 evaluation, preserving expression, grouping, precedence, and multi-Rule ANY semantics.

### AC-10 — R06 failure boundary

Any accepted R06 validation/input failure produces no `qualified`, `rejected`, or `ai_failed` Decision, is not coerced to Boolean false, and authorizes no action.

### AC-11 — Qualified-only authorization

Only a produced `qualified` Decision authorizes entry into the existing `action_mode` path.

### AC-12 — Existing favorite path

A qualified Candidate in `favorite` mode may enter the existing favorite path; `perform_favorite_action()` and its mechanics are reused unchanged.

### AC-13 — Existing forward path and suppression

A qualified Candidate in `forward` mode may enter the existing forward path; `forward_one_candidate()` is reused unchanged, and `no_forward_mode` continues to suppress real forwarding without changing the Decision.

### AC-14 — Rejected zero action

A rejected Candidate calls neither the favorite path nor the forward path and returns to normal continuation.

### AC-15 — AI-failed zero action

An AI-failed Candidate calls neither the favorite path nor the forward path and returns to normal continuation.

### AC-16 — Decision/action-result separation

Existing action success, false return, skip, suppression, or failure does not change a produced `qualified` Decision and creates no `action_failed` Decision status.

### AC-17 — Common Candidate continuation

After normal Decision processing and any authorized existing action attempt, all three Decision statuses rejoin the existing Candidate/batch continuation without a status-specific continuation subsystem.

### AC-18 — next-Candidate boundary

R12 does not modify `next_candidate()` or make it a `CandidateDecision` responsibility; existing switch verification, batch position, refresh, pause, and stop behavior remain authoritative.

### AC-19 — Legacy rule independence

For the same finalized Candidate, R11 result, and Run-bound RuleSet, changes to Legacy keywords, screen-level match results, or Legacy confirmation results cannot change the R12 Decision or independently authorize an Am7 production action.

### AC-20 — Protected action mechanics

R12 does not modify favorite/forward click mechanics, focus restoration, forward/favorite calibration, WindMouse/mouse motion, waits/delays, browser automation, or action-specific safety controls.

### AC-21 — Explicit stable RuleSet binding

Before Candidate execution begins, Run setup resolves exactly one explicit formal R06 `ScreeningRuleSet`; that same immutable value is held in memory and supplied unchanged to every Candidate in the current live Run execution, with no per-Candidate reload, rediscovery, derivation, edit, replacement, or switch.

### AC-22 — No inferred or weakened Rule contract

R12 introduces no `ScreeningProfileVersion.rule_set` assumption, automatic all-Criteria AND, one-Rule-per-Criterion substitute, Legacy-rule conversion, or bypass of R06 OR/grouping/multi-Rule semantics.

### AC-23 — Minimal failure visibility and R13 protection

AI failure is represented by `ai_failed` plus minimum existing log visibility only; R12 adds no result/failure/Decision/action/Rule persistence, retry queue, fallback, degradation, recovery, counter, or failure-stop policy.

### AC-24 — R14 and framework protection

R12 adds no replay, cache, new hash/digest, migration/release integration, or generic Decision/Action/Gate/Guard/Scanner/Wrapper/Sanitizer/Dispatcher/Pipeline/orchestration framework.

## 23. Open Decisions / Human Review

### OD-01 — Formal RuleSet source and Run binding

- Status: Resolved.
- Selected: Option A — Explicit in-memory Run input.
- Human Review decision: Approved.
- Binding: Run setup resolves one formal immutable R06 `ScreeningRuleSet` before Candidate execution, and the current live Run execution supplies that same value to every Candidate.
- Durability boundary: no crash/restart restoration, persistence, or replay is provided by R12.

Open Decisions: None.

## 24. Explicit Non-Changes

AM7-R12 does not change:

- R05 Profile fields, Criteria, versioning, digest, persistence, or Configuration/Execution rules;
- R06 types, grammar, tokenizer/parser, validation, Boolean evaluation, or ANY semantics;
- R07 Complete Scan, Dynamic End, Candidate-switch, or Candidate-finalization semantics;
- R08 authority, finalization, traceability, or Legacy compatibility boundaries;
- R09 Candidate input projection;
- R10 Prompt or Boolean contract;
- R11 inputs, result type, statuses, Provider invocation, or failure boundary;
- Candidate, Run, Screen, or action persistence schemas;
- existing favorite, forward, `next_candidate()`, focus restore, calibration, WindMouse, mouse, browser, delay, or batch mechanics.

## 25. Contract Conflicts

None.

The selected explicit in-memory Run input fills an ownership point deliberately left outside R05 and R06 without changing their Frozen schemas, persistence, or evaluation contracts. This RPD is Frozen.

## 26. Final Product Contract Summary

AM7-R12 introduces one minimal immutable Candidate Decision with exact Candidate identity and one of three normal statuses. R11 failed maps to `ai_failed` without R06 or action. R11 completed is evaluated through the exact Run-bound R06 RuleSet: `true` maps to `qualified`, and `false` maps to `rejected`. R06 failure produces no normal Decision and no action.

Only `qualified` authorizes the existing favorite or forward path. Existing `action_mode`, `no_forward_mode`, action mechanics, action outcome behavior, and Candidate continuation remain authoritative. Action outcome never rewrites the Decision. Legacy screen-level matches remain compatibility/shadow information and have no Am7 production Decision or action authority.

Before Candidate execution, Run setup explicitly receives the required R06 Rule definition or definitions and resolves exactly one immutable `ScreeningRuleSet`. The current live Run holds that value in memory and supplies it unchanged to every Candidate, including pause and resume within the same live process/session. R12 adds no RuleSet persistence or crash/restart restoration. Human Review has approved this source and binding decision; this RPD is Frozen.
