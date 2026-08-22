# AM7-R12 — Candidate Decision & Action Integration

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R12
- Document Type: Technical Implementation Design
- Version: 0.1
- Status: Frozen
- Governing Document: `CODEX-CONSTITUTION.md`
- Source RPD: `docs/RPD-AM7-R12-candidate-decision-action-integration.md` — v0.1 Frozen
- Requirement Branch: `am7-r12-candidate-decision-action-integration`
- Working HEAD / Upstream Baseline: `ca3cf7b3a4ceda091f67d2e8fc65e535623b7caf`

## 1. Document Status

This document is the Frozen technical implementation design for AM7-R12. It translates the Frozen RPD v0.1 product contract into the authoritative implementation-ready, minimum local change plan approved by Human TID Review.

## 2. Source Authority and Design Objective

The sole R12 product authority is `docs/RPD-AM7-R12-candidate-decision-action-integration.md` v0.1 Frozen. Accepted R05, R06, R07, R08, R09, R10, and R11 contracts are upstream constraints and are not redesigned here.

R12 implements this production chain:

```text
finalized CandidateOcrDocument
→ run_ai_screening(candidate, profile, config)
→ AIScreeningResult
→ decide_candidate(ai_result, run_bound_rule_set)
→ CandidateDecision
→ qualified only: existing action_mode dispatch
→ existing Candidate/batch continuation
```

R12 changes only the authorization condition for the existing favorite/forward action paths. It does not redesign Candidate scanning, Candidate finalization, AI evaluation, Boolean Rule evaluation, action mechanics, Candidate switching, or batch control.

## 3. Targeted Inspection Scope

The technical design is based on targeted read-only inspection of:

- governance and product authority:
  - `CODEX-CONSTITUTION.md`
  - the Frozen R12 RPD
  - Frozen R06, R08, and R11 RPD/TID documents
  - the accepted R11 Acceptance Report
- accepted upstream implementation:
  - `ai_screening_runtime.py`
  - `screening_rule_engine.py`
  - `screening_profile.py`
  - `ai_provider_config.py`
  - `ai_provider_cli.py`
  - `ocr_records.py`
  - `ocr_candidate.py`
  - `ocr_detector.py`
- current production integration:
  - `simple_brush.py`
- directly relevant test conventions:
  - `tests/test_screening_rule_engine.py`
  - `tests/test_ai_screening_runtime.py`
  - focused portions of `tests/test_simple_brush_ocr.py`

This was not a repository-wide audit. No tests were run during TID design.

## 4. Targeted Repository Findings

1. `ai_screening_runtime.py` exposes the accepted immutable `AIScreeningResult` and `run_ai_screening(candidate, profile, config)`. Expected R09 projection, provider-runtime, and R10 response-contract failures are already normalized to `ai_status == "failed"`; unexpected exceptions propagate.
2. `screening_rule_engine.py` exposes immutable `ScreeningRule`, immutable one-or-more `ScreeningRuleSet`, `evaluate_rule_set(rule_set, criterion_results)`, `ScreeningRuleValidationError`, and `ScreeningRuleInputError`. Constructors validate public value shape only; full lexical, grammar, reference, and Boolean input validation occurs in `evaluate_rule_set()`.
3. `ScreeningProfileVersion` has no RuleSet field. `ScreeningProfileBinding` and `RunManifest` likewise do not carry a RuleSet. Therefore the Frozen RPD Option A must be implemented as an explicit in-memory Run input, without schema changes.
4. `AIProviderConfigStore.load()` returns an `AIProviderConfigLoadResult`; only `AIProviderConfigLoadStatus.VALID` supplies the current usable `AIProviderConfig`. Configuration can be loaded once before Candidate execution and retained by the live `run()` call.
5. `OCRKeywordDetector.scan_candidate(first_observation=...)` is the accepted R07 rule-neutral Complete Scan API. It clears Legacy match annotations before using the shared scan lifecycle.
6. `simple_brush.py` does not currently call `scan_candidate()`. `view_candidate()` calls Legacy `detect(...)` only when `forward_enabled and forward_keywords`, and its `keyword_hit` block currently authorizes favorite/forward before Candidate finalization.
7. The current no-Legacy-keyword branch bypasses the formal OCR Complete Scan and directly finalizes with `existing_flow_completed`. That branch cannot remain the Am7 production path because Legacy input would continue to gate Candidate evidence and R11 eligibility.
8. `finalize_current_candidate_recording(...)` returns the finalized `CandidateOcrDocument` or `None`, but current successful main-loop call sites discard the return value. It already owns save/finalize/release behavior and must remain unchanged.
9. For non-last Candidates, `prepare_candidate_switch_context(...)` must run while the current Candidate evidence is still available and before builder finalization. The resulting context is then consumed at the start of the next iteration by `confirm_candidate_switch(...)`, which owns the actual `next_candidate()` call and verification.
10. Load-recovery restart finalizes an aborted builder with `abort_reason == "load_recovery_restart"`. Stop and exception cleanup use `finalize_active_candidate_for_stop(...)` to produce aborted/interrupted evidence. These cleanup documents are not formal R11 inputs.
11. The accepted action bodies are `perform_favorite_action()` and `forward_one_candidate()`. Existing forward suppression is a call-site check of `no_forward_mode`; `next_candidate()` and switch verification remain separate continuation mechanics.
12. The current startup menu can prepare a Profile and configure a Provider, but it does not retain a Run-bound RuleSet or `AIProviderConfig` object. Those bindings require narrow Run setup changes.

## 5. Chosen Technical Outcome

Use the smallest local design:

- add one pure module, `candidate_decision.py`, for the exact two-field Decision and the R11-to-R06 mapping;
- add a repeatable `--screening-rule` input plus one-expression-per-entry interactive input;
- construct exactly one immutable `ScreeningRuleSet` in `main()` and pass it explicitly to `run()`;
- load exactly one current valid `AIProviderConfig` in `run()` before Candidate execution;
- wire the accepted `scan_candidate()` API into the Am7 production path regardless of Legacy keywords;
- retain the finalized normal Candidate document and invoke R11 then R12 once;
- allow only `qualified` to enter the existing favorite/forward call sites;
- leave all action, switch, OCR, and upstream module implementations untouched.

No generic Decision, Action, Gate, Guard, Validator, Scanner, Wrapper, Dispatcher, Pipeline, or orchestration framework is introduced.

## 6. Exact File Plan

### New implementation file

- `candidate_decision.py`

### Modified implementation file

- `simple_brush.py`

### New focused test files

- `tests/test_candidate_decision.py`
- `tests/test_candidate_decision_integration.py`

### Modified directly affected test file

- `tests/test_simple_brush_ocr.py`
  - update only existing assertions/fixtures directly invalidated by the explicit Run RuleSet argument, Run-level Provider config load, rule-independent Complete Scan wiring, and removal of Legacy keyword action authority;
  - do not broaden this module into a new R12 framework or rewrite unrelated accepted tests.

### Documentation created by this design turn

- `docs/TID-AM7-R12-candidate-decision-action-integration.md`

### Protected / untouched upstream implementation

- `ai_screening_runtime.py`
- `screening_rule_engine.py`
- `screening_profile.py`
- `ocr_records.py`
- `ocr_candidate.py`
- `ai_candidate_input.py`
- `ai_screening_prompt.py`
- `ai_screening_contract.py`
- `llm_provider_runtime.py`
- `ai_provider_config.py`
- `ai_provider_cli.py`
- `ocr_detector.py`

No dependency or packaging file changes are planned.

## 7. Required Imports and Dependency Direction

`candidate_decision.py` imports only:

```python
from dataclasses import dataclass
from typing import Literal

from ai_screening_runtime import AIScreeningResult
from screening_rule_engine import ScreeningRuleSet, evaluate_rule_set
```

`simple_brush.py` adds only the public integration imports it consumes:

```python
from ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigIOError,
    AIProviderConfigLoadStatus,
    AIProviderConfigStore,
)
from ai_screening_runtime import run_ai_screening
from candidate_decision import CandidateDecision, decide_candidate
from ocr_records import CandidateOcrDocument
from screening_profile import ScreeningProfileVersion
from screening_rule_engine import (
    ScreeningRule,
    ScreeningRuleSet,
    ScreeningRuleValidationError,
)
```

Existing grouped imports may be extended rather than duplicated. `simple_brush.py` does not import or call R06 private tokenizer/parser symbols.

## 8. CandidateDecision Representation

`candidate_decision.py` defines exactly:

```python
@dataclass(frozen=True)
class CandidateDecision:
    candidate_record_id: str
    decision_status: Literal["qualified", "rejected", "ai_failed"]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_record_id, str):
            raise ValueError("candidate_record_id must be a string")
        if self.decision_status not in (
            "qualified",
            "rejected",
            "ai_failed",
        ):
            raise ValueError(
                "decision_status must be qualified, rejected, or ai_failed"
            )
```

The class is immutable and has exactly two dataclass fields. String identity is not required to be UUID-shaped or nonblank because R12 must not strengthen the accepted R11 identity contract. No reason, action result, AI payload, Rule result, Profile, Provider, timestamp, hash, or persistence field is added.

## 9. Public Decision API

The exact public function is:

```python
def decide_candidate(
    ai_result: AIScreeningResult,
    rule_set: ScreeningRuleSet,
) -> CandidateDecision:
```

Its exact implementation logic is:

```python
def decide_candidate(
    ai_result: AIScreeningResult,
    rule_set: ScreeningRuleSet,
) -> CandidateDecision:
    if not isinstance(ai_result, AIScreeningResult):
        raise TypeError("ai_result must be an AIScreeningResult")
    if not isinstance(rule_set, ScreeningRuleSet):
        raise TypeError("rule_set must be a ScreeningRuleSet")

    if ai_result.ai_status == "failed":
        return CandidateDecision(
            candidate_record_id=ai_result.candidate_record_id,
            decision_status="ai_failed",
        )

    rule_passed = evaluate_rule_set(
        rule_set,
        ai_result.criteria_results,
    )
    return CandidateDecision(
        candidate_record_id=ai_result.candidate_record_id,
        decision_status="qualified" if rule_passed else "rejected",
    )
```

The exact `criteria_results` object and exact Run-bound `ScreeningRuleSet` object are passed unchanged to R06. The exact `AIScreeningResult.candidate_record_id` string is copied without stripping, normalization, hashing, rebuilding, prefixing, or regeneration.

## 10. Decision Entry and Invariant Boundary

- Wrong `ai_result` top-level type raises `TypeError` before any Decision or R06 call.
- Wrong `rule_set` top-level type raises `TypeError` before any Decision or R06 call, including when the supplied AI result is failed.
- Non-string `CandidateDecision.candidate_record_id` raises `ValueError`, matching the accepted upstream value-object convention.
- Any Decision status outside the exact three-value domain raises `ValueError`.
- R12 does not revalidate the internal completed/failed combinations already enforced by `AIScreeningResult`.
- R12 does not revalidate Rule expressions or Criterion mappings already owned by R06.
- There is no broad `except Exception` in `candidate_decision.py`.

## 11. R06 Evaluation and Exception Boundary

For `ai_status == "completed"`, `decide_candidate()` calls the public `evaluate_rule_set()` exactly once. It does not preflight the expression and does not access `_tokenize`, `_parse_rule`, or other R06 private implementation.

`ScreeningRuleValidationError` and `ScreeningRuleInputError` propagate unchanged from R06. On either exception:

- no `CandidateDecision` is returned;
- no false/rejected/ai_failed substitute is produced;
- no favorite or forward call is authorized;
- no synthetic Criterion mapping, fallback, retry, or fail-closed business status is created.

The production call site does not catch these errors locally. They reach the existing outer `run()` error boundary, which records the exception type, performs existing cleanup, and terminates that Run path. This preserves the accepted exception meaning and guarantees zero action because action dispatch follows successful Decision construction.

For `ai_status == "failed"`, R06 is not called at all.

## 12. Rule-Definition Input Surface

### 12.1 Noninteractive / CLI input

Add the repeatable exact flag:

```text
--screening-rule <R06 expression>
```

`parse_args()` adds:

```python
'screening_rules': [],
```

Each occurrence appends its following argument unchanged:

```python
elif sys.argv[i] == '--screening-rule':
    if i + 1 >= len(sys.argv):
        raise ValueError('--screening-rule 缺少 Rule 表达式')
    args['screening_rules'].append(sys.argv[i + 1])
    i += 2
```

One flag represents one independent R06 Rule. Multiple flags preserve ordered, duplicate-allowed, multi-Rule ANY input without a delimiter:

```text
--screening-rule "C001 AND C002"
--screening-rule "C003 OR (C004 AND C005)"
```

The shell supplies each full expression as one argument; AND, OR, whitespace, and parentheses are not rewritten. `--keywords` is not a Rule source and is never converted.

R12 does not change `is_noninteractive_startup()` or its existing accepted triggers. When those existing triggers already select the noninteractive path, R12 additionally requires both a nonempty `--screening-profile-id` and at least one `--screening-rule`. If either formal R12 input is missing, `main()` prints one startup error, returns exit code `2`, and does not call `run()`. A `--screening-profile-id` or `--screening-rule` by itself does not become a new noninteractive trigger.

### 12.2 Interactive input

Add private startup helper:

```python
def prompt_screening_rule_expressions() -> Tuple[str, ...]:
```

Interactive startup remains selected by the existing menu-driven mode. When the startup menu action is `run` and a Profile has been prepared through that menu, this helper prompts for one R06 expression per entry. A blank entry terminates collection only after at least one expression exists. A blank first entry prints that one or more formal Rules are required and prompts again. Blank checking may use `raw.strip()` only to detect absence; every accepted nonblank expression is stored exactly as entered. Formal R12 flags do not silently switch this path to noninteractive mode.

The prompt states that each entry is one independent Rule and that R06 supports Criterion IDs, `AND`, `OR`, and parentheses. It does not describe or reuse Legacy keyword grammar.

## 13. Exact RuleSet Construction

Add one private construction helper in `simple_brush.py`:

```python
def _build_screening_rule_set(
    expressions: Tuple[str, ...],
) -> ScreeningRuleSet:
    return ScreeningRuleSet(tuple(
        ScreeningRule(expression) for expression in expressions
    ))
```

`main()` calls this helper exactly once for the selected startup path, after obtaining the explicit one-or-more expressions and before calling `run()`.

- Interactive: prompt → one tuple → one helper call → one `ScreeningRuleSet`.
- Noninteractive: `tuple(cli_args['screening_rules'])` → one helper call → one `ScreeningRuleSet`.

`main()` catches only `ScreeningRuleValidationError` from this construction point, reports `[错误] Screening Rule 无法用于运行：<message>`, and returns `2` before `run()`. Constructor-level empty/type errors therefore retain the accepted R06 error and message. Lexical, grammar, unsupported syntax, missing reference, invalid key, and non-Boolean value errors remain deferred to the public `evaluate_rule_set()` validation phase. R12 neither normalizes expression text nor performs dummy/preflight evaluation.

## 14. RuleSet / Profile Relationship

The RuleSet is an independent explicit Run input. R12 does not modify or assume fields on:

- `ScreeningProfileVersion`;
- `ScreeningProfileBinding`;
- `RunManifest`;
- Profile JSON or digest computation.

R12 does not derive automatic AND Rules, create one Rule per Criterion, convert Legacy keywords, or create a second Profile-aware Rule validator. For completed AI results, R06 remains solely responsible for confirming that every referenced Criterion ID exists in the supplied complete mapping.

## 15. RuleSet Live-Run Binding

The exact Run signature becomes:

```python
def run(
    screening_profile_id: Optional[str] = None,
    *,
    run_bound_rule_set: ScreeningRuleSet,
):
```

The keyword-only required argument makes the formal RuleSet explicit and prevents an implicit/default Rule. The first operation in `run()` validates `isinstance(run_bound_rule_set, ScreeningRuleSet)` and raises `TypeError` before Run state reset or other side effects if the direct caller violates the contract.

`main()` passes the exact single object:

```python
return run(
    screening_profile_id=selected_profile_id,
    run_bound_rule_set=run_bound_rule_set,
)
```

The local `run_bound_rule_set` reference remains unchanged for the whole live `run()` invocation, including existing in-process pause/resume behavior. Every Candidate receives that exact object. There is no per-Candidate construction, reload, discovery, edit, replacement, or switch. Its lifetime ends at terminal Run return. Crash/restart restoration, persistence, replay, ID, version, digest, and RunManifest extension are out of scope.

## 16. AIProviderConfig Live-Run Binding

After loading and digest-validating the selected `ScreeningProfileVersion`, and before OCR storage initialization, listener/browser startup, calibration, or Candidate execution, `run()` performs exactly one config load:

```python
try:
    config_result = AIProviderConfigStore().load()
except AIProviderConfigIOError as exc:
    print(f'[错误] AI Provider 配置无法读取：{exc}')
    return 2

if (
    config_result.status is not AIProviderConfigLoadStatus.VALID
    or config_result.config is None
):
    detail = config_result.error or config_result.status.value
    print(f'[错误] AI Provider 配置无法用于运行：{detail}')
    return 2

run_ai_provider_config = config_result.config
```

`AIProviderConfigLoadStatus.NOT_CONFIGURED`, `INCOMPLETE`, `INVALID`, and `UNSUPPORTED_VERSION` are startup/configuration failures and prevent Candidate execution. R12 does not add a new verification-status gate or redesign R02/R03 configuration semantics. The exact `run_ai_provider_config` object is retained by the live `run()` invocation and passed unchanged to every R11 call; there is no per-Candidate reload or model/provider selection.

## 17. Formal Candidate Eligibility

Only the retained return value from a normal main-loop call to `finalize_current_candidate_recording(...)` is considered. The narrow eligibility predicate is:

```python
candidate_document is not None and candidate_document.capture_status in (
    CaptureStatus.COMPLETED,
    CaptureStatus.COMPLETED_WITH_LIMIT,
)
```

Eligible normal completion reasons include current Dynamic End projections such as `scroll_bottom`, `no_new_text`, and the safety result `max_screen_limit`, plus the existing normal completion projection. R11 remains responsible for converting a missing/blank authoritative document text into its accepted `failed` result.

The following do not enter R11/R12:

- `CaptureStatus.ABORTED` from detector abort or load-recovery restart;
- `CaptureStatus.INTERRUPTED` from user/runtime interruption;
- `CaptureStatus.EMPTY` if produced;
- `None` returned after finalize/store failure;
- `finalize_active_candidate_for_stop(...)` cleanup for user stop, runtime expiry, Candidate-switch stop, or exception;
- a new Candidate whose `confirm_candidate_switch(...)` or load gate fails before Complete Scan;
- any other recovery/cleanup finalization call site.

For each eligible normal Candidate, exactly one retained document is supplied to exactly one R11 call. A completed R11 result causes at most one R06 evaluation and, absent R06 failure, exactly one Decision. No cleanup call site invokes the new processing helper.

## 18. Complete Scan Integration

`view_candidate(...)` must call the accepted R07 public API unconditionally for the Am7 Candidate path:

```python
detection_result = ocr_detector.scan_candidate(
    first_observation=first_observation,
)
```

It does not call `detect_keywords()` and contains no Legacy `keyword_hit` action branch. It retains the existing dwell-time accounting, stop check, safe wait, human scrolling, and return shape. The display/log status is no longer derived from `keyword_hit`.

`run()` initializes OCR for every Am7 Run and uses the existing formal load/switch/scan branch for every Candidate, regardless of `forward_enabled` or `forward_keywords`. The current no-keyword branch that bypasses formal scanning is removed from the Am7 main loop. `ocr_detector.py` is untouched; R12 only integrates its accepted `scan_candidate()` public method.

Because `view_candidate()` no longer enters Legacy `detect_keywords()`, `run()` must retain the existing OCR-region readiness operation at the Run setup call site. After the first Candidate detail page has opened and after the existing required runtime calibration preparation on that page, but before the Run timer and before any formal Candidate Complete Scan, execute exactly:

```python
if not ensure_ocr_region_calibrated():
    return 0
```

This call is unconditional with respect to `forward_enabled`, `forward_keywords`, `keyword_hit`, and `action_mode`. The body of `ensure_ocr_region_calibrated()` is protected and unchanged; no new calibration helper or subsystem is introduced.

## 19. Candidate Finalization Integration

The implementation retains the document returned by each of the two normal main-loop finalization call sites:

```python
candidate_document = finalize_current_candidate_recording(...)
```

It does not change `finalize_current_candidate_recording()` itself. Immediately after normal finalization, the call site applies the eligibility check from Section 17. An eligible exact document is passed to one narrow processing helper with the already loaded `profile_version`, `run_ai_provider_config`, and exact `run_bound_rule_set`.

For a non-last Candidate, `prepare_candidate_switch_context(...)` remains before finalization so its evidence dependency is preserved. R11/R12/action processing occurs after finalization and before the existing check of whether that prepared context permits continuation. For the last Candidate, processing occurs after finalization and before existing batch-loop completion/refresh behavior.

## 20. Exact Main-Loop Ordering

Before the Candidate loop, exact Run readiness ordering is:

```text
initialize_ocr()
→ open first Candidate detail page
→ existing required runtime calibrations on that page
→ ensure_ocr_region_calibrated()
→ if readiness fails: return 0 with zero formal Candidate scan
→ start_run_timer(run_duration_seconds)
→ formal Candidate execution / scan_candidate()
```

Neither Legacy keyword presence nor action mode changes this ordering.

### 20.1 First Candidate / later Candidate entry

Existing ordering remains:

```text
first Candidate: run_detail_load_gate(...)
later Candidate: confirm_candidate_switch(previous_candidate_context, ...)
→ accepted first_observation
→ total_viewed increment
```

`confirm_candidate_switch(...)` continues to own the actual `next_candidate()` action and switch verification before the later Candidate is scanned.

### 20.2 Every Candidate

```text
view_candidate(...)
  → ocr_detector.scan_candidate(first_observation=...)
  → existing dwell/stop behavior
→ candidate_capture_status(detection_result)
```

If `view_candidate()` does not complete, existing stop finalization runs and no R11/R12 call is made.

### 20.3 Non-last Candidate

The exact call order is:

```text
prepare_candidate_switch_context(detection_result, ...)
→ finalize_current_candidate_recording(...), retain candidate_document
→ if candidate_document is formally eligible:
     _process_finalized_candidate(
         candidate_document,
         profile_version,
         run_ai_provider_config,
         run_bound_rule_set,
     )
→ existing previous_candidate_context/context_reason check
→ loop continues
→ next iteration confirm_candidate_switch(...)
```

The current Candidate page has not been switched when AI/Decision/action processing occurs. Existing favorite/forward focus restoration therefore still returns to the current detail page before the later existing switch operation.

If `prepare_candidate_switch_context(...)` cannot produce context, the already completed current Candidate is still finalized and processed once, then the existing Candidate-switch stop request occurs. No new Candidate evaluation follows.

### 20.4 Last Candidate

The exact call order is:

```text
finalize_current_candidate_recording(...), retain candidate_document
→ if formally eligible: _process_finalized_candidate(...)
→ existing end-of-batch convergence
→ existing refresh_page()/next batch behavior
```

### 20.5 Pause, stop, and exception

Existing `stop_event`, pause, listener, timer, and outer `try/except/finally` remain authoritative. A stop detected before action prevents entry to the action call. Existing cleanup can finalize evidence but never invokes R11/R12. Unexpected R11/R06/action exceptions reach the existing outer error boundary; cleanup and Run status projection remain unchanged.

## 21. Legacy Keyword Action-Authority Removal

The current `view_candidate()` block:

```text
keyword_hit
→ action_mode
→ perform_favorite_action()/forward_one_candidate()
```

is removed from the Am7 Candidate production path. `view_candidate()` no longer derives action authority from `detect_keywords()` or `keyword_hit`. Therefore a Legacy hit alone cannot invoke favorite/forward and the same Candidate cannot receive both a Legacy-authorized and CandidateDecision-authorized action.

The Legacy keyword parser, `detect_keywords()`, match logging, and underlying detection subsystem remain available for Legacy compatibility or future explicit shadow/debug use, but R12 does not call them as part of Am7 production evaluation. If later used for shadow/debug, their output has no scan-ending or action authority.

## 22. Legacy Keyword / forward_enabled Decoupling

R12 separates Legacy configuration state from Am7 processing:

- `forward_enabled` and `forward_keywords` describe only Legacy keyword configuration/reference state.
- They do not gate OCR initialization, `ensure_ocr_region_calibrated()`, Complete Scan, Candidate finalization, R11, R06, Decision, or a qualified action.
- The main-loop `if forward_enabled and forward_keywords` split is replaced by one rule-neutral Complete Scan path.
- Interactive text for blank Legacy rules no longer says that Am7 forwarding/action is disabled; it says only that Legacy keyword rules are not configured.
- Startup logging labels the value as Legacy rule configuration, not production action readiness.
- Backup-email prompting remains an actual forward-mode concern: it is conditioned on `action_mode == ACTION_MODE_FORWARD and not no_forward`, not on Legacy rule presence.
- Existing forward/focus calibration selection is conditioned on `action_mode == ACTION_MODE_FORWARD`, not on Legacy rule presence. Favorite calibration behavior remains unchanged.
- `no_forward_mode`, `action_mode`, email availability, calibration state, action safety checks, and forward consecutive limits remain existing action-mechanics inputs rather than Decision inputs.

No Legacy parser or detector implementation is deleted or rewritten.

## 23. Qualified Action Authorization

Add one narrow private orchestration helper in `simple_brush.py`:

```python
def _process_finalized_candidate(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
    rule_set: ScreeningRuleSet,
) -> CandidateDecision:
    global forward_consecutive
```

The `global forward_consecutive` declaration is mandatory inside this helper because its rejected and ai_failed branches assign to the existing module-level counter. The counter is not moved into `CandidateDecision` and no runtime-state wrapper is introduced.

The helper performs only:

1. `run_ai_screening(candidate, profile, config)`;
2. `decide_candidate(ai_result, rule_set)`;
3. one minimum log containing `candidate_record_id` and `decision_status`;
4. qualified-only dispatch to the existing `action_mode` call sites;
5. return of the exact Decision for focused verification.

It is local glue, not a generic pipeline. The action authorization condition is exactly:

```python
if decision.decision_status == "qualified":
```

No other value and no Legacy match can enter the action branch.

## 24. Favorite Reuse

For a qualified Decision and `action_mode == ACTION_MODE_FAVORITE`, the helper calls:

```python
perform_favorite_action()
```

exactly once, unless the existing stop state prevents action entry. The body of `perform_favorite_action()` and its focus restoration, clicking, waits, and safety behavior are untouched. Its return value or failure does not rewrite the already produced Decision.

## 25. Forward / no_forward_mode Reuse

For a qualified Decision and `action_mode == ACTION_MODE_FORWARD`:

- when `no_forward_mode` is false, call existing `forward_one_candidate()` exactly once and let all existing controls remain authoritative;
- when `no_forward_mode` is true, retain the existing suppression log, make no real `forward_one_candidate()` call, make no favorite fallback, and return the unchanged qualified Decision.

No `suppressed`, `dry_run`, `skipped`, or `action_failed` Decision status is introduced. The `forward_one_candidate()` body remains untouched.

## 26. Action Outcome Separation

Decision construction completes before action dispatch. Existing action success, false return, skip, suppression, or exception cannot reclassify `qualified` as `rejected` or `ai_failed` and cannot create a fourth status. R12 does not persist an action result.

The private helper ignores normal action return values. If an action raises unexpectedly, the already selected Decision value is not mutated; the exception follows the existing outer Run error boundary.

## 27. Rejected / AI-Failed Zero Action

- `rejected`: call neither action function, assign the existing module-level `forward_consecutive = 0`, then return to common continuation.
- `ai_failed`: R06 was not called; call neither action function, emit only the minimum Decision-status log, assign the same module-level `forward_consecutive = 0`, then return to common continuation.

Neither status has a dedicated switching branch, retry, fallback, degradation, stop policy, or persistence path.

## 28. Candidate Continuation / next_candidate Boundary

After `_process_finalized_candidate(...)` returns normally—or after an ineligible finalization simply skips it—all statuses converge into the current surrounding main-loop control flow.

- Non-last Candidate switching remains owned by the next iteration's `confirm_candidate_switch(...)` and its existing `next_candidate()` call.
- Last-Candidate handling, batch refresh, batch position, pause, and stop behavior remain where they are.
- `next_candidate()` accepts no Decision and its body is unchanged.
- R12 adds no `if rejected: next_candidate()` / `if ai_failed: next_candidate()` subsystem.

## 29. Unexpected Failure Propagation and Minimum Logging

The new integration does not broad-catch R11, R06, Decision-constructor, or action defects.

- Only an actual accepted `AIScreeningResult(ai_status="failed")` becomes `ai_failed`.
- Unexpected R11 exceptions are not normalized by R12.
- R06 validation/input errors are not converted to a Decision.
- An invalid `action_mode` on a qualified path retains the existing `ValueError` behavior.
- All such unexpected/configuration errors reach the existing outer `run()` error boundary and authorize zero subsequent action.

Minimum new runtime logging is one existing-style line after successful Decision construction:

```python
logger.info(
    'event=candidate_decision candidate_record_id=%s decision_status=%s',
    decision.candidate_record_id,
    decision.decision_status,
)
```

No resume text, Criterion mapping, raw AI response, Provider secret, failure ledger, Decision history, analytics, retry queue, or persistence record is logged or created.

## 30. Protected Functions / Reuse-Only Scope

R12 may change call conditions around these symbols but must not change their bodies:

- `perform_favorite_action()`;
- `forward_one_candidate()`;
- `next_candidate()`;
- `restore_candidate_detail_focus()`;
- `restore_candidate_page_focus_after_favorite()`;
- `human_move_to()` and imported WindMouse/mouse-motion implementation;
- focus-restore, forward-click, and batch-filter calibration helpers;
- calibration region/value types and click-region definitions;
- `prepare_candidate_switch_context()`;
- `confirm_candidate_switch()`;
- Candidate-switch evaluator/helper symbols;
- `finalize_current_candidate_recording()`;
- `finalize_active_candidate_for_stop()`;
- `ensure_ocr_region_calibrated()`;
- R07 `OCRKeywordDetector.scan_candidate()` and the OCR scan lifecycle.

Acceptance review proves this boundary through exact changed-file/diff review and targeted source inspection. No AST guard, checksum, repository scanner, or protection framework is added.

## 31. Detailed Implementation Pseudocode

### 31.1 Rule input to Run-bound RuleSet

```python
# main()
cli_args = parse_args()

if is_noninteractive_startup(cli_args):  # existing accepted triggers only
    require cli_args['screening_profile_id']
    require one-or-more cli_args['screening_rules']
    raw_rule_expressions = tuple(cli_args['screening_rules'])
else:
    use existing menu-driven startup
    require prepared_screening_profile_id from the menu before Run
    raw_rule_expressions = prompt_screening_rule_expressions()

run_bound_rule_set = _build_screening_rule_set(raw_rule_expressions)

return run(
    screening_profile_id=selected_profile_id,
    run_bound_rule_set=run_bound_rule_set,
)
```

`_build_screening_rule_set()` is called once. It uses only `ScreeningRule(...)` and `ScreeningRuleSet(...)` and retains every expression exactly. `is_noninteractive_startup()` is not changed to inspect `screening_profile_id` or `screening_rules`; those formal flags do not select the startup mode.

### 31.2 Run setup

```python
def run(..., *, run_bound_rule_set):
    require isinstance(run_bound_rule_set, ScreeningRuleSet)
    existing argument/action configuration
    profile_version = ScreeningProfileStore().load_latest(...)
    validate existing criteria_digest
    config_result = AIProviderConfigStore().load()  # exactly once
    require status VALID and config present
    run_ai_provider_config = config_result.config
    existing OCR store/listener/browser setup
    initialize_ocr()  # no Legacy-keyword gate
    open first Candidate detail page
    perform existing required runtime calibrations on that page
    if not ensure_ocr_region_calibrated():  # no Legacy-keyword/action gate
        return 0
    run_timer = start_run_timer(run_duration_seconds)
    existing main loop
```

### 31.3 Candidate Decision

```python
ai_result = run_ai_screening(
    candidate_document,
    profile_version,
    run_ai_provider_config,
)

if ai_result.ai_status == "failed":
    decision = CandidateDecision(
        candidate_record_id=ai_result.candidate_record_id,
        decision_status="ai_failed",
    )
else:
    rule_passed = evaluate_rule_set(
        run_bound_rule_set,
        ai_result.criteria_results,
    )
    decision = CandidateDecision(
        candidate_record_id=ai_result.candidate_record_id,
        decision_status=("qualified" if rule_passed else "rejected"),
    )
```

### 31.4 Production Candidate flow

```python
view_completed, detection_result = view_candidate(
    i,
    first_observation=first_observation,
)  # internally calls scan_candidate(), never Legacy detect for authority

if not view_completed:
    finalize_active_candidate_for_stop(...)
    break

capture_status, capture_end_reason = candidate_capture_status(detection_result)

if non_last_candidate:
    previous_candidate_context, context_reason = (
        prepare_candidate_switch_context(...)
    )

candidate_document = finalize_current_candidate_recording(
    capture_status,
    capture_end_reason,
    detection_result=detection_result,
)

if candidate_document is eligible completed evidence:
    decision = _process_finalized_candidate(
        candidate_document,
        profile_version,
        run_ai_provider_config,
        run_bound_rule_set,
    )

# existing context check, loop convergence, switch, and batch behavior
```

### 31.5 Qualified-only action and common continuation

```python
global forward_consecutive

decision = decide_candidate(ai_result, rule_set)
log candidate identity and decision status

if stop_event:
    return decision

if decision.decision_status == "qualified":
    if action_mode == ACTION_MODE_FAVORITE:
        perform_favorite_action()
    elif action_mode == ACTION_MODE_FORWARD:
        if no_forward_mode:
            retain existing suppression log
        else:
            forward_one_candidate()
    else:
        raise ValueError(...)
else:
    forward_consecutive = 0

return decision
# caller resumes existing common continuation
```

### 31.6 R06 failure

```text
evaluate_rule_set(...) raises ScreeningRuleValidationError/InputError
→ decide_candidate does not return
→ _process_finalized_candidate reaches no action branch
→ exception reaches existing run outer error boundary
→ existing cleanup/status handling
```

### 31.7 Legacy authority

```text
Legacy keyword definition / keyword_hit
→ optional Legacy reference or logging only
→ never production action

CandidateDecision.decision_status == "qualified"
→ sole R12 production action authorization
```

## 32. Implementation Change Plan

### Change 1 — Pure Candidate Decision boundary

- create `candidate_decision.py` with the exact immutable two-field class;
- add the exact `decide_candidate()` public API;
- preserve R11 identity and R06 input objects exactly;
- propagate R06 errors unchanged;
- add `tests/test_candidate_decision.py` for responsibilities R01–R15.

### Change 2 — Production integration and focused verification

- modify `simple_brush.py` with repeatable/interactive formal Rule input;
- construct one Run-bound RuleSet in `main()` and require it in `run()`;
- load and retain one valid Run-level `AIProviderConfig`;
- initialize OCR, preserve unconditional OCR-region readiness after first-detail runtime calibration, and wire rule-independent `scan_candidate()` into every Am7 Candidate path;
- retain normal finalized documents and invoke R11 then R12 exactly once;
- remove Legacy keyword action authority and Legacy gating of Am7 processing;
- authorize existing favorite/forward call sites only for qualified Decisions;
- preserve `no_forward_mode`, action outcomes, and common continuation;
- add `tests/test_candidate_decision_integration.py` for responsibilities R16–R43;
- minimally align directly affected cases/fixtures in `tests/test_simple_brush_ocr.py`;
- run only the exact targeted commands in Section 34 and perform diff-scope review.

Implementation Changes count: **2**. There is no separate framework or verification Change.

## 33. Focused Test Plan

Tests use `unittest`, `unittest.mock`, and accepted production value types. They do not use a real browser, Boss session, AI API, mouse, keyboard, favorite, forwarding, email, or calibration operation.

### 33.1 Pure Decision tests — `tests/test_candidate_decision.py`

| Responsibility | Focused verification |
|---|---|
| R01 | completed R11 result + mocked R06 true returns `qualified`. |
| R02 | completed R11 result + mocked R06 false returns `rejected`. |
| R03 | failed R11 result returns `ai_failed`. |
| R04 | failed result makes zero `evaluate_rule_set()` calls. |
| R05 | exact `criteria_results` object is passed unchanged to R06. |
| R06 | exact Run-bound `ScreeningRuleSet` object is passed unchanged. |
| R07 | exact `candidate_record_id` is copied. |
| R08 | dataclass fields are exactly `candidate_record_id`, `decision_status`. |
| R09 | frozen assignment raises `FrozenInstanceError`. |
| R10 | exact three statuses construct; all other values fail. |
| R11 | `ScreeningRuleValidationError` propagates with no Decision. |
| R12 | `ScreeningRuleInputError` propagates with no Decision. |
| R13 | completed all-false mapping still reaches R06. |
| R14 | R06 false maps to rejected, never ai_failed. |
| R15 | wrong top-level types, non-string identity, and invalid status follow Section 10. |

These responsibilities may be grouped into approximately seven focused test methods; responsibility IDs, not method count, are authoritative.

### 33.2 Production integration tests — `tests/test_candidate_decision_integration.py`

| Responsibility | Focused mocked verification |
|---|---|
| R16 | one normal completed Candidate retains one finalized document and calls R11 once. |
| R17 | completed R11 result reaches R06 at most once. |
| R18 | R11 failed produces ai_failed and zero R06. |
| R19 | qualified + favorite calls existing favorite once. |
| R20 | qualified + forward calls existing forward once under existing controls. |
| R21 | qualified + forward + `no_forward_mode` makes zero real forward call and remains qualified. |
| R22 | rejected makes zero favorite/forward calls. |
| R23 | ai_failed makes zero favorite/forward calls. |
| R24 | false return, suppression, and raised action do not reclassify a Decision. |
| R25 | Legacy keyword hit alone cannot invoke an Am7 action. |
| R26 | changing Legacy match output cannot change the R12 Decision. |
| R27 | no Legacy keywords still reaches `ensure_ocr_region_calibrated()` and then Complete Scan/finalization/R11/R06; readiness false returns before `scan_candidate()`. |
| R28 | R11 receives the exact object returned by normal finalization, after finalization. |
| R29 | aborted Candidate makes zero formal R11/R12 calls. |
| R30 | interrupted Candidate makes zero formal R11/R12 calls. |
| R31 | load-recovery restart cleanup makes zero formal R11/R12 calls and no duplicate later call. |
| R32 | existing noninteractive startup requires both formal Profile/Rule inputs and returns `2` before `run()` when either is missing; formal flags alone do not alter existing startup-mode selection; a valid startup builds once. |
| R33 | multiple Candidates receive the identical bound RuleSet object. |
| R34 | Candidate processing never reconstructs the RuleSet. |
| R35 | one repeatable CLI Rule in the existing noninteractive path and one prompted interactive Rule are representable without changing startup mode. |
| R36 | multiple independent CLI/prompted Rules retain order and duplicates. |
| R37 | expressions containing AND/OR/parentheses reach `ScreeningRule` unchanged and are evaluated only by R06. |
| R38 | qualified, rejected, and ai_failed all return to the same continuation seam. |
| R39 | existing `confirm_candidate_switch()`/`next_candidate()` remains the switching owner. |
| R40 | unexpected R11 exception reaches the existing outer failure boundary, not ai_failed. |
| R41 | R06 exception makes zero action calls. |
| R42 | no retry, fallback, degradation, or R13 behavior is invoked. |
| R43 | no persistence, replay, cache, or R14 behavior is invoked. |

High-value responsibilities are combined into a small table-driven/mocked set. Identity assertions use `assertIs` for Candidate, Profile, Config, RuleSet, and mapping objects where exact reuse is required.

The R16 setup assertion also proves that `AIProviderConfigStore.load()` is called once before the first Candidate and that the exact loaded Config reaches R11. The multi-Candidate R33 fixture additionally proves that the same Profile, Config, and RuleSet objects reach every R11/R12 call; no separate responsibility ID or configuration framework is added.

R22 and R23 additionally set the real module-level `forward_consecutive` to a nonzero value before calling the helper and assert that rejected and ai_failed each reset that global value to `0`. R27 covers both OCR-region readiness success with no Legacy keywords and readiness failure with zero `scan_candidate()` calls.

### 33.3 Direct existing-test alignment — `tests/test_simple_brush_ocr.py`

Only directly affected tests are updated:

- replace old `view_candidate()` keyword-authorized action assertions with rule-neutral `scan_candidate()` and zero-Legacy-authority expectations;
- supply a valid explicit `run_bound_rule_set` to direct `run()` calls;
- mock `AIProviderConfigStore.load()` with an accepted VALID result in Run fixtures that reach setup;
- update parse/startup assertions for repeatable `screening_rules`, existing noninteractive missing-input failures, and unchanged startup-mode triggers;
- assert unconditional `ensure_ocr_region_calibrated()` ordering and zero scan when readiness fails;
- keep unrelated OCR, switch, action-body, calibration, and store assertions unchanged.

No new source scanner or protected-body guard test is added.

Test responsibility count: **43 (R01–R43)**.

## 34. Verification Commands

Implementation acceptance must run only:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_candidate_decision tests.test_candidate_decision_integration tests.test_simple_brush_ocr -v
.\venv\Scripts\python.exe -m compileall candidate_decision.py simple_brush.py tests\test_candidate_decision.py tests\test_candidate_decision_integration.py tests\test_simple_brush_ocr.py
git diff --check
git diff --name-status
git diff -- candidate_decision.py simple_brush.py tests/test_candidate_decision.py tests/test_candidate_decision_integration.py tests/test_simple_brush_ocr.py
```

`tests.test_simple_brush_ocr` is included because the only modified existing production file is `simple_brush.py` and this is its directly affected focused regression module. The final diff commands are read-only scope/protected-body review, not repository scanners.

Do not run the full suite, live AI/browser/action flows, model benchmarks, packaging, PyInstaller, dependency audits, full R03 regression, full R06 acceptance, or full R11 acceptance for R12.

## 35. AC-01–AC-24 Implementation Mapping

| AC | Implementation file / symbol | Test responsibilities | Acceptance evidence | Status |
|---|---|---|---|---|
| AC-01 | `simple_brush.run()` normal finalization call sites; `_process_finalized_candidate()` | R16, R28–R31 | exact retained finalized object reaches one R11 call; cleanup paths do not | Planned |
| AC-02 | `candidate_decision.decide_candidate()` | R01, R05–R07 | completed + R06 true yields exact qualified Decision | Planned |
| AC-03 | `candidate_decision.decide_candidate()` | R02, R14 | completed + R06 false yields exact rejected Decision | Planned |
| AC-04 | `candidate_decision.decide_candidate()` | R03, R07 | failed yields exact ai_failed Decision | Planned |
| AC-05 | failed branch before `evaluate_rule_set()` | R04, R18 | mock proves zero R06 and no synthetic mapping | Planned |
| AC-06 | `CandidateDecision.__post_init__()` | R10, R15 | exact three-value construction matrix | Planned |
| AC-07 | frozen two-field `CandidateDecision` | R08, R09 | dataclass field and immutability inspection | Planned |
| AC-08 | exact ID copy in `decide_candidate()` | R07 | equality plus no normalization/rebuild source review | Planned |
| AC-09 | public R06 call in `decide_candidate()` | R05, R06, R13, R33, R37 | identity mocks and accepted R06 public evaluator | Planned |
| AC-10 | no catch around public R06 call/action follows Decision | R11, R12, R41 | both accepted errors propagate; zero action | Planned |
| AC-11 | `_process_finalized_candidate()` qualified-only branch | R19–R23 | action-call matrix | Planned |
| AC-12 | qualified favorite call site; protected `perform_favorite_action()` | R19 | mock call once plus diff/source body review | Planned |
| AC-13 | qualified forward/no-forward call site; protected `forward_one_candidate()` | R20, R21 | forward/suppression matrix plus body review | Planned |
| AC-14 | nonqualified common branch | R22, R38 | zero action and common continuation | Planned |
| AC-15 | failed Decision path | R18, R23, R38 | zero R06/action and common continuation | Planned |
| AC-16 | Decision constructed before action; action return ignored | R21, R24 | false/failure/suppression cannot rewrite Decision | Planned |
| AC-17 | caller resumes current loop after helper | R38 | all statuses reach identical continuation mock | Planned |
| AC-18 | protected `confirm_candidate_switch()` / `next_candidate()` | R39 | switching ownership assertion plus body/diff review | Planned |
| AC-19 | unconditional OCR-region readiness; `view_candidate()` uses `scan_candidate()`; old keyword action block removed | R25–R27 | no-Legacy readiness/scan evidence and Legacy-result variation cannot change Decision/action | Planned |
| AC-20 | protected action/focus/calibration/mouse bodies, including `ensure_ocr_region_calibrated()` | R19–R21, R27 | changed-file/diff review plus readiness call-order evidence | Planned |
| AC-21 | unchanged startup-mode selection; `main()` one construction; required keyword-only `run_bound_rule_set` | R32–R36 | missing-input/startup-mode, construction-count, and same-object assertions | Planned |
| AC-22 | `_build_screening_rule_set()` uses exact public values only | R35–R37 | expression fidelity; no Profile/Legacy inference; source review | Planned |
| AC-23 | one minimum Decision log; existing outer failure boundary | R18, R40, R42 | no retry/fallback/degradation/persistence in diff | Planned |
| AC-24 | exact local files and narrow helper only | R43 | scope review confirms no replay/cache/framework/R14 work | Planned |

Mapping completeness: **24 / 24 Frozen Acceptance Criteria mapped**.

## 36. Final Scope Review

The design introduces no:

- Candidate scan redesign or OCR detector modification;
- Candidate finalization redesign or Candidate/Run schema change;
- R06 parser/evaluator modification or duplicate validation;
- R11 runtime modification, AI retry, fallback, or degradation;
- Rule persistence, RuleSet identity/version/digest, Profile field, or RunManifest field;
- CandidateDecision persistence, history, reason/evidence, action result, hash, or timestamp;
- action-engine abstraction or favorite/forward mechanics change;
- next-Candidate, switch evaluator, batch, pause, stop, browser, mouse, calibration, or safety-control redesign;
- R13 observability/recovery implementation;
- R14 persistence/replay/cache implementation;
- migration, release, dependency, packaging, CLI parser migration, or generic framework.

Planned implementation is limited to one pure Decision module and the minimum `simple_brush.py` integration, with focused tests.

## 37. Open Issues

None.

## 38. Contract Conflicts

None.

The design satisfies the Frozen R12 RPD using public accepted R06/R07/R11/config APIs. No upstream implementation modification or product-contract workaround is required.

## 39. Human Review Outcome

Frozen
