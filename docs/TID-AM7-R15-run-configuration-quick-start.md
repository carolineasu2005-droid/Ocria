# Ocria Am7 — AM7-R15 Run Configuration & Quick Start UX

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R15
- Requirement Name: Run Configuration & Quick Start UX
- Document Type: Technical Implementation Design
- Version: 0.2
- Status: Draft — Pending Human Review
- Governing Document: `CODEX-CONSTITUTION.md`
- Source RPD: `docs/RPD-AM7-R15-run-configuration-quick-start.md` — v0.2, Human Final Review Passed / Frozen authority for this TID
- Source Product AC: AC-01 through AC-24
- Observed Working Branch: `am7-r14-final-integration-acceptance`
- Observed Working HEAD / Baseline: `0260f2824aa1b7d932d0fa88ea94a324fa1fe81a`
- Prepared On: 2026-08-24 (Asia/Shanghai)

## 2. Status

This TID is a Draft pending Human Review. It translates the Human-approved AM7-R15 RPD v0.2 product contract into one minimal implementation design. It does not authorize implementation, tests, an Acceptance Report, Git operations, packaging, or release.

Human has approved RPD v0.2 as the Frozen product authority for this TID. The physical RPD file still displays `Draft — Pending Human Review`; aligning that metadata is a documentation-governance follow-up, not a Technical Design blocker. This TID does not modify or reopen the approved product design.

## 3. Governing RPD

The implementation must preserve these product boundaries:

```text
Human
→ ScreeningPreset / last-used Run settings
→ resolve
→ ResolvedRunConfiguration
→ Run Summary
→ Human Confirm
→ existing Calibration flow unchanged
→ existing Runtime
```

R15 owns only:

- `ScreeningPreset` persistence and management;
- last-used Run-setting persistence;
- exact Profile/Rule/Provider/Run-setting resolution;
- Quick Start, Preset selection, Summary, Edit/Confirm/Cancel;
- a narrow handoff seam into the existing Run.

R15 does not own Calibration state, OCR, AI evaluation, retry/persistence, Candidate Decision, action authorization/mechanics, Candidate switching, batch continuation, or Legacy behavior outside normal-startup routing.

Product Open Questions: **None**.

Product Contract Conflicts: **None**.

## 4. Current Code Findings

### 4.1 Startup and argument dispatch

`simple_brush.parse_args()` currently recognizes exactly eleven options:

```text
--keywords
--email
--duration-seconds
--no-forward
--no-batch-filter
--simple-mouse
--auto
--calibration-profile
--screening-profile-id
--screening-rule
--action-mode
```

`is_noninteractive_startup()` returns true only for `--auto`, non-empty `--keywords`, or non-empty `--calibration-profile`. Formal Profile/Rule flags alone do not bypass the menu. This predicate and all eleven parse meanings are compatibility contracts and remain unchanged.

`main()` currently:

- uses the existing non-interactive path when that predicate is true;
- keeps one prepared Profile ID only in the current process;
- prompts for formal Rule expressions for every interactive Run;
- constructs one `ScreeningRuleSet` through `_build_screening_rule_set(...)`;
- calls `run(screening_profile_id=..., run_bound_rule_set=...)`.

### 4.2 Current `run()` coupling

The current signature is:

```python
def run(
    screening_profile_id: Optional[str] = None,
    *,
    run_bound_rule_set: ScreeningRuleSet,
):
    ...
```

The function currently combines four setup responsibilities before the accepted Candidate loop:

1. reparse CLI values and call `get_user_input(...)`;
2. call `ScreeningProfileStore.load_latest(profile_id)` and retain the returned exact object;
3. call `AIProviderConfigStore.load()` once and retain the valid config;
4. initialize OCR/R13 stores and enter existing Calibration/Runtime.

The Candidate loop already passes the retained `profile_version`, `run_ai_provider_config`, and `run_bound_rule_set` unchanged into `_process_finalized_candidate(...)`. No Candidate-loop rewrite is needed.

### 4.3 Current interaction and Calibration boundary

`get_user_input(...)` currently owns:

- Action Mode prompting;
- Legacy keyword prompting/parsing;
- backup-email prompting;
- Calibration Profile selection/application;
- focus/forward/batch calibration-request choices;
- duration prompting.

Physical batch/focus/forward/favorite/OCR calibration occurs later at the existing Run boundary. R15 must separate normal Run settings from this function without moving or changing physical Calibration behavior.

### 4.4 ScreeningProfile

`screening_profile.py` already provides the required authority:

- immutable `ScreeningProfileVersion`;
- exact `load_version(profile_id, version)`;
- current `load_latest(profile_id)`;
- latest-only Draft creation and immutable Human Save;
- same-directory temporary file plus `os.replace()` atomic Version write;
- digest validation and exact Criterion IDs.

`screening_profile_cli.py` exposes the existing advanced Profile CLI but returns only a prepared Profile ID. It has no additive helper that returns the exact newly saved `ScreeningProfileVersion` to another configuration flow.

### 4.5 Rule Engine

`screening_rule_engine.py` provides frozen immutable `ScreeningRule`, immutable one-or-more `ScreeningRuleSet`, and `evaluate_rule_set(...)`. Constructors validate public shape only; complete lexical, grammar, reference, and Boolean-input validation occurs in `evaluate_rule_set(...)`.

The current `_build_screening_rule_set(...)` only constructs public R06 values and preserves raw expressions. No second parser is necessary.

### 4.6 Provider configuration

`AIProviderConfigStore.load()` returns a classified `AIProviderConfigLoadResult`; only `VALID` plus a non-`None` complete `AIProviderConfig` is usable. Its store already demonstrates the repository's minimal UTF-8 JSON, same-directory temporary file, and `os.replace()` pattern.

R15 can load one current complete config during resolution and pass that same immutable object into `run()`. No R02/R03 or R11 change is needed.

### 4.7 Existing tests and README

- `tests/test_candidate_decision_integration.py` protects formal Rule input, the non-interactive predicate, and one Run-bound RuleSet.
- `tests/test_simple_brush_ocr.py` protects the current menu, `get_user_input`, all eleven options, Calibration behavior, Run setup order, action/no-forward behavior, and Candidate-loop boundaries.
- `tests/test_screening_profile.py` and `tests/test_screening_profile_cli.py` protect immutable Profile persistence and current advanced CLI behavior.
- R06/R12/R13 tests protect Rule, Decision, action, retry, and persistence boundaries.
- `README.md` currently describes the pre-R15 five-item startup menu, Prepare-by-ID flow, per-Run Rule input, Legacy prompt, Calibration, and all eleven CLI arguments. It must be updated with implementation, not during this TID turn.

## 5. Technical Goal

Implement one local configuration layer that:

1. persists named Presets and last-used settings;
2. resolves an exact immutable Profile Version, one immutable RuleSet, one complete Provider config, and Run settings before Summary;
3. renders Summary only from that resolved value;
4. requires Human Confirm;
5. hands the same resolved objects/values into the existing Run;
6. invokes existing post-confirm action-input and Calibration preparation without making Calibration part of R15 resolution;
7. preserves the current advanced/non-interactive path.

Implementation Changes count: **1 coherent AM7-R15 Change**.

## 6. Technical Non-goals

Do not add or change:

- a generic settings/configuration framework;
- database, migration framework, file-lock service, or multi-process transaction system;
- Preset ID/version/digest/timestamps/status/tags/owner/metadata;
- RuleSet persistence/identity/version/digest or a second parser/evaluator;
- Profile branching, historical Draft editing, active/latest/default publication state;
- `--screening-preset`;
- Calibration model/storage/profile/regions/geometry/preview/DPI/prompts/ordering;
- OCR, Candidate, AI Prompt/Runtime, retry/degradation, Decision, action, switch, pause/resume, or stop semantics;
- real network, BOSS, browser, mouse, email, favorite, or forward activity in automated tests.

## 7. Exact File Plan

### 7.1 New production files

| File | Responsibility | Why separate |
|---|---|---|
| `screening_preset.py` | Frozen Preset/last-used models and one dedicated atomic state store | Keeps local R15 persistence out of `simple_brush.py` without creating a generic framework |
| `run_configuration.py` | Rule authoring helpers, exact resolver, immutable `ResolvedRunConfiguration`, Summary renderer | Pure setup logic can be tested without importing browser/mouse runtime |
| `screening_preset_cli.py` | R15 top-level menu helpers, Preset CRUD UX, Run-setting prompts, Summary Confirm/Edit/Cancel | Prevents the new normal CLI workflow from expanding the sensitive runtime file |

### 7.2 Modified production/documentation files

| File | Authorized change |
|---|---|
| `simple_brush.py` | Minimal startup dispatch, compatibility wrappers, resolved-config `run()` seam, and post-confirm normal-input routing only |
| `screening_profile_cli.py` | One additive Draft-editor helper returning an exact newly saved Version; existing advanced CLI remains intact |
| `README.md` | Update startup/Preset/Quick Start/Summary/normal-vs-Advanced documentation and keep Calibration/CLI facts accurate |

### 7.3 New test files

| File | Coverage |
|---|---|
| `tests/test_screening_preset.py` | Models, strict JSON, atomic store, CRUD, rename/delete/last-used consistency |
| `tests/test_run_configuration.py` | ALL/ANY/Custom, exact Profile and Provider resolution, Summary, fail-closed behavior |
| `tests/test_am7_r15_startup.py` | Menu journeys, Confirm timing, same-value handoff, normal Legacy removal, Calibration boundary, CLI routing |

### 7.4 Modified existing test files

| File | Authorized change |
|---|---|
| `tests/test_simple_brush_ocr.py` | Replace only obsolete startup-menu expectations and add assertions for the narrow resolved `run()` setup branch; retain existing Calibration/Candidate/action tests |
| `tests/test_screening_profile_cli.py` | Add focused coverage for the additive exact-Version-returning Draft helper |

No other existing test file requires modification. Existing R06/R12/R13 and non-interactive assertions must remain valid.

## 8. `ScreeningPreset` Model

Implement in `screening_preset.py`:

```python
@dataclass(frozen=True)
class ScreeningPreset:
    preset_name: str
    screening_profile_id: str
    profile_version: int
    screening_rule_expressions: tuple[str, ...]
```

Constructor responsibilities are public value-shape validation only:

- `preset_name` must be `str`; `preset_name.strip()` must be non-empty;
- canonical `preset_name` is the stripped value, assigned once in `__post_init__` with `object.__setattr__`;
- `screening_profile_id` must be a non-empty `str`; exact Profile semantic validation belongs to `ScreeningProfileStore.load_version(...)`;
- `profile_version` must be a positive non-`bool` `int`;
- expressions must be a non-empty `tuple` of non-blank strings;
- expression strings are preserved exactly and are not stripped, repaired, normalized, or parsed by the constructor.

The model has no additional field. Name uniqueness is a collection/store responsibility because one isolated value cannot determine duplication.

## 9. Preset and Last-used Persistence

### 9.1 Dedicated path

Use one dedicated state file:

```python
DEFAULT_SCREENING_PRESET_STATE_PATH = Path("data") / "screening_presets.json"
```

Preset collection and last-used settings share this one R15-specific file. This is not a generic settings framework. One file is the smallest design that makes Preset rename/delete and the last-used name reference one same-file atomic replacement.

Human names are JSON data and never filenames. Windows-invalid filename characters therefore require no encoding, UUID, slug, hash, or mapping scheme.

### 9.2 Exact JSON schema

```json
{
  "presets": [
    {
      "preset_name": "UI组长-SLG",
      "screening_profile_id": "sp_0123456789abcdef0123456789abcdef",
      "profile_version": 1,
      "screening_rule_expressions": [
        "C001 AND C002 AND C003"
      ]
    }
  ],
  "last_used_run_settings": {
    "last_used_preset_name": "UI组长-SLG",
    "last_action_mode": "favorite",
    "last_duration_seconds": 0,
    "last_no_forward": false,
    "last_batch_filter_enabled": true
  }
}
```

`last_used_run_settings` is JSON `null` when no confirmed launch exists. A missing file means empty Presets plus no last-used state. An existing file must contain exactly the two root keys.

Validation is partitioned deliberately:

- file/root validation requires valid UTF-8 JSON, an object root, and exactly `presets` plus `last_used_run_settings`;
- Preset collection validation requires a list, exact four-key Preset objects, valid field types/shapes, and canonical exact-name uniqueness;
- last-used structural validation requires either JSON `null` or an exact five-key object with valid field types/shapes;
- cross-reference resolution is not JSON parsing: a structurally valid `last_used_preset_name` may currently refer to no Preset.

Malformed file/root or Preset collection data raises `ScreeningPresetValidationError` and exposes no partial Preset collection. A malformed last-used portion makes only last-used/Quick Start unavailable; it does not hide an otherwise healthy Preset collection from list, get, selection, or management. A structurally valid but dangling last-used reference is returned as a value and makes only Quick Start unavailable during resolution. Neither case triggers guessing, fallback, automatic rewrite, orphan cleanup, or migration.

Writer format is UTF-8, `ensure_ascii=False`, two-space indentation, and one trailing newline. Presets are written in deterministic exact-name order; array order has no product identity.

### 9.3 Store errors and atomic writer

Use only:

```python
class ScreeningPresetValidationError(ValueError): ...
class ScreeningPresetIOError(RuntimeError): ...
```

- malformed persisted content, blank/duplicate/missing names, and invalid model shapes use `ScreeningPresetValidationError`;
- read/write/replace filesystem failures use `ScreeningPresetIOError`;
- do not add separate not-found, conflict, transaction, recovery, or migration exception hierarchies.

Every mutation requires a valid file/root and Preset collection, builds one complete replacement mapping in memory, writes a temporary file in `data/`, and calls `os.replace()` on the target. The internal loader retains the raw last-used JSON portion separately so Preset list/get/selection remain independent from its validity. A Preset mutation preserves a malformed last-used portion unchanged rather than treating it as accepted settings or silently repairing it; a later explicit Human-confirmed `save_last_used()` may replace it with a valid object. On write failure, best-effort remove only the temporary file and leave the prior target authoritative. Reuse the pattern already present in `AIProviderConfigStore` and `ScreeningProfileStore`; do not create a shared persistence framework.

## 10. `LastUsedRunSettings` and Store API

### 10.1 Model

Implement in `screening_preset.py`:

```python
@dataclass(frozen=True)
class LastUsedRunSettings:
    last_used_preset_name: str
    last_action_mode: str
    last_duration_seconds: int
    last_no_forward: bool
    last_batch_filter_enabled: bool
```

Validation:

- name uses the same trim/canonicalization rule as `ScreeningPreset`;
- action is exactly `"favorite"` or `"forward"`;
- duration is a non-negative non-`bool` `int`; `0` is the existing Unlimited representation;
- the two flags require exact `bool` values.

Missing state is represented by `None`, not an empty/sentinel model. The model contains no Provider, Calibration, email, Legacy keyword, Profile copy, or RuleSet.

### 10.2 Minimal store API

```python
class ScreeningPresetStore:
    def __init__(self, path: Path = DEFAULT_SCREENING_PRESET_STATE_PATH) -> None: ...
    def list_presets(self) -> tuple[ScreeningPreset, ...]: ...
    def get_preset(self, preset_name: str) -> ScreeningPreset: ...
    def create_preset(self, preset: ScreeningPreset) -> None: ...
    def replace_preset(
        self,
        current_name: str,
        replacement: ScreeningPreset,
    ) -> None: ...
    def delete_preset(self, preset_name: str) -> None: ...
    def load_last_used(self) -> LastUsedRunSettings | None: ...
    def save_last_used(self, settings: LastUsedRunSettings) -> None: ...
```

Semantics:

- `list_presets()` returns deterministic exact-name order;
- `get_preset()` trims lookup input and fails if absent;
- `create_preset()` rejects an existing canonical exact name;
- `replace_preset()` requires `current_name` to exist and rejects a replacement name used by another Preset;
- if `current_name` is last-used, `replace_preset()` changes that last-used name in the same in-memory state and one atomic write;
- `delete_preset()` removes only the Preset and clears last-used in the same write when it references the deleted name;
- any failed replace/delete leaves the old Preset and old last-used state authoritative;
- `load_last_used()` validates only the last-used portion and returns `None` or a structurally valid `LastUsedRunSettings`; it may return a value whose name is not currently in the Preset collection;
- a malformed last-used portion causes `load_last_used()` to raise `ScreeningPresetValidationError` but does not affect `list_presets()` or `get_preset()`;
- Quick Start / `resolve_run_configuration()` owns the name-to-Preset lookup and rejects a dangling returned reference;
- `save_last_used()` replaces only the last-used object in the complete state and requires the referenced Preset to exist.

Normal write paths still prevent new dangling references. A structurally valid last-used reference matching a renamed Preset is updated with the rename in one atomic write; deleting that Preset writes JSON `null` in the same atomic operation. If the existing last-used portion is malformed, Preset mutations preserve it as invalid opaque JSON and never infer a reference from partial fields.

No `exists()`, repository base class, transaction object, lock, cache, watcher, or migration API is added.

## 11. Rule Authoring and Resolution

Implement in `run_configuration.py`:

```python
def build_all_rule_expression(profile: ScreeningProfileVersion) -> str: ...
def build_any_rule_expression(profile: ScreeningProfileVersion) -> str: ...
def build_screening_rule_set(
    expressions: tuple[str, ...],
) -> ScreeningRuleSet: ...
def validate_preset_definition(
    preset: ScreeningPreset,
    profile_store: ScreeningProfileStore,
) -> tuple[ScreeningProfileVersion, ScreeningRuleSet]: ...
```

Rules:

- ALL joins every `criterion.criterion_id` in Profile tuple order with exact separator `" AND "`;
- ANY joins every ID with exact separator `" OR "`;
- one Criterion produces its one ID for either shortcut;
- Custom expressions are passed and persisted byte-for-byte as entered;
- `build_screening_rule_set()` uses only `ScreeningRule(...)` and `ScreeningRuleSet(tuple(...))`;
- `simple_brush._build_screening_rule_set()` remains as a compatibility wrapper delegating to this function.

Complete semantic validation must use the existing public R06 authority:

```python
criterion_results = {
    criterion.criterion_id: False
    for criterion in profile.criteria
}
evaluate_rule_set(rule_set, criterion_results)
```

The Boolean result is discarded. This call validates tokenization, grammar, unsupported syntax, every referenced ID, key shape, and Boolean values without a second parser. Extra unreferenced Profile Criteria remain allowed exactly as R06 permits. Multiple rules retain R06 fixed ANY; duplicates and raw expression text remain preserved.

## 12. Exact ProfileVersion Resolution

`validate_preset_definition(...)` performs:

```text
preset.screening_profile_id + preset.profile_version
→ ScreeningProfileStore.load_version(...)
→ validate persisted Profile/digest through existing model/store
→ build one ScreeningRuleSet
→ evaluate_rule_set with a complete synthetic Boolean mapping
→ return the exact Profile object and exact RuleSet object
```

It never calls `load_latest()`.

### 12.1 Preset path

The exact returned Profile object is placed directly in `ResolvedRunConfiguration`, shown by Version in Summary, and passed unchanged into `run()`. No Summary or handoff code performs a second Profile read.

### 12.2 Advanced/non-interactive path

The existing `--screening-profile-id` path keeps its current meaning:

```text
Profile ID
→ one `load_latest(profile_id)` inside existing advanced Run setup
→ retain that returned exact ProfileVersion for the whole Run
```

It does not require a Version argument and does not become a Preset path. `load_latest()` is therefore protected for advanced compatibility but forbidden in Preset resolution.

## 13. Provider Resolution

Implement in the R15 resolver, without changing `ai_provider_config.py`:

```text
AIProviderConfigStore.load() exactly once
→ require status VALID and config is not None
→ retain exact immutable AIProviderConfig object
→ place it in ResolvedRunConfiguration
```

`NOT_CONFIGURED`, `INCOMPLETE`, `INVALID`, `UNSUPPORTED_VERSION`, and `AIProviderConfigIOError` are classifications/outcomes supplied by the existing Store boundary and become `RunConfigurationError` with a concise non-secret startup message. R15 does not re-derive completeness from `provider`, `api_key`, `base_url`, or `model`, and adds no second Provider validator. No connectivity retest, Provider/model fallback, config write, API-key display, or R02/R03 redesign occurs.

The Summary reads only `config.provider` and `config.model`. Confirmed Run handoff passes the same config object into the existing R11/R13 call chain; `run()` performs no Provider store lookup on this path.

## 14. `ResolvedRunConfiguration`

Implement in `run_configuration.py`:

```python
@dataclass(frozen=True)
class ResolvedRunConfiguration:
    selected_preset_name: str
    exact_screening_profile_version: ScreeningProfileVersion
    run_bound_screening_rule_set: ScreeningRuleSet
    current_complete_ai_provider_config: AIProviderConfig
    action_mode: str
    duration_seconds: int
    no_forward: bool
    batch_filter_enabled: bool
```

Validation is exact and local:

- selected name is canonical/nonblank;
- exact model instances are required;
- Provider value must be an `AIProviderConfig` object already carried from resolution; the dataclass does not repeat field-level completeness validation;
- action is `favorite` or `forward`;
- duration is non-negative non-`bool` integer, with `0 == Unlimited`;
- flags require exact `bool`.

The object is Run-local and never serialized. It contains no Calibration, email, Legacy keyword, Candidate, mutable Runtime state, replay data, store, persistent identity, version, or digest.

Define one expected setup exception:

```python
class RunConfigurationError(ValueError): ...
```

It normalizes expected Preset/Profile/Rule/Provider/Run-setting failures only for startup display. It does not catch unexpected defects or Runtime failures.

The resolver API is:

```python
def resolve_run_configuration(
    settings: LastUsedRunSettings,
    *,
    preset_store: ScreeningPresetStore,
    profile_store: ScreeningProfileStore,
    provider_store: AIProviderConfigStore,
) -> ResolvedRunConfiguration:
    ...
```

It loads by `settings.last_used_preset_name`, rejects that reference if `get_preset()` cannot resolve it, validates the exact Preset definition, consumes the existing Provider Store's `VALID` classification once, and copies the five validated Run-setting values into the immutable result. `ResolvedRunConfiguration` carries the resulting Provider and RuleSet values; their semantic validation remains owned by the existing Provider Store and R06 respectively.

## 15. Interactive Startup Architecture

### 15.1 Top-level menu

Freeze this v1 order in `screening_preset_cli.choose_startup_action()`:

```text
1. Quick Start
2. Choose ScreeningPreset and Run
3. ScreeningPreset Management
4. AI Provider Configuration
5. Calibration
6. Advanced
0. Exit
```

`simple_brush.choose_startup_action()` remains a compatibility wrapper so existing imports need not change; the menu text/validation lives in `screening_preset_cli.py`.

### 15.2 Advanced submenu

Freeze:

```text
1. Existing manual Am7 Run
2. Advanced ScreeningProfile Management
0. Return
```

The existing manual path retains the process-local prepared Profile ID and formal Rule prompt. It enters the existing `run(screening_profile_id=..., run_bound_rule_set=...)` branch, where Legacy/action/email/duration/Calibration behavior remains compatible.

### 15.3 Normal setting input

`screening_preset_cli.prompt_run_settings(...)` returns a validated `LastUsedRunSettings` value without persisting it. For Choose-Preset it explicitly collects/reviews Action, duration, `no_forward`, and batch-filter enabled state, using last-used values only as visible defaults when available.

Current invocation safety switches remain authoritative:

- parsed `--no-forward` forces resolved `last_no_forward=True`;
- parsed `--no-batch-filter` forces resolved `last_batch_filter_enabled=False`;
- `--simple-mouse` remains an advanced runtime flag applied by `run()` and is not added to the R15 model;
- other flags retain their current interactive/non-interactive meaning.

Use one shared `run_configuration.parse_duration_seconds(...)`; keep `simple_brush.parse_duration_seconds(...)` as a compatibility wrapper.

## 16. Quick Start and Preset Selection

### 16.1 Quick Start

```text
store.load_last_used()
→ if None: explain unavailable, return to menu
→ apply current no-forward/no-batch CLI forcing
→ resolve_run_configuration(...)
→ render Summary from the returned object
→ Confirm / Edit / Cancel
```

A malformed last-used portion or a structurally valid but dangling Preset reference makes Quick Start unavailable with a concise reason and returns to Configuration Mode. Healthy Presets remain listable/selectable/manageable, so the user may explicitly use Choose ScreeningPreset and Run. Missing exact Profile, invalid Rule, existing Provider Store non-`VALID` result, or invalid Run settings follows the same fail-closed path. It never selects another Preset, `latest`, repaired Rule, another Provider, or Legacy keywords.

### 16.2 Choose Preset and Run

`choose_preset(...)` lists deterministic sequence numbers and names and accepts either. The number is transient UI state. After selection, Run settings are collected, then the same resolver/Summary/confirmation loop is used.

### 16.3 Edit and Cancel

- Edit discards the old `ResolvedRunConfiguration`; prompts produce a new settings value and invoke the resolver again.
- Switching Preset through Edit performs a new lookup and resolution.
- Cancel starts no Run and writes no last-used state.
- No field on a resolved frozen object is mutated.

## 17. Preset Management

### 17.1 Profile selection and additive editor seam

`screening_preset_cli.py` lists saved exact Profile Versions by transient sequence number with Criteria preview; the normal user never types a UUID. Details may display the internal ID.

Add to `screening_profile_cli.py`:

```python
def run_screening_profile_draft_editor(
    store: ScreeningProfileStore | None = None,
    *,
    screening_profile_id: str | None = None,
) -> ScreeningProfileVersion | None:
    ...
```

- `None` creates a new Draft;
- an ID calls existing `create_draft_from_latest(id)`;
- the helper reuses existing Store add/edit/delete/show/save operations;
- Human Save returns the exact newly written `ScreeningProfileVersion`;
- cancel/no-op returns `None`;
- existing `run_screening_profile_configuration()` behavior and return type remain unchanged.

This is an additive CLI seam, not a second Profile store/editor subsystem.

### 17.2 Create

```text
canonical unique Preset name
→ choose existing exact ProfileVersion by sequence
   OR create/save one through the additive Draft helper
→ show Criteria
→ ALL / ANY / Custom
→ build and validate with R06
→ full Preset preview
→ Human Save
→ store.create_preset(...)
```

No accepted Preset write occurs before the final Save.

### 17.3 Edit and Criterion transaction boundary

Edit supports rename, Rule change, exact rebind, and Criterion editing.

For Criteria:

1. inspect the Preset's exact binding and current Profile latest;
2. when bound Version is not latest, require an explicit Preset rebind/save to latest before editing; never branch the historical Version;
3. call the additive latest-only Draft helper;
4. if Profile Human Save creates a new Version, retain that exact object in the edit flow but leave the stored Preset unchanged;
5. regenerate or collect Rule, validate, and show a complete Preset preview;
6. only explicit Preset Save calls `replace_preset(old_name, replacement)`.

If step 3 succeeds and step 6 fails, formal Profile history keeps the new Version and the atomic Preset file keeps the old binding.

Rename and Rule-only edits use the same `replace_preset(...)`. When the old name is last-used, the one-file atomic replacement updates the last-used name in the same operation.

### 17.4 Delete and details

Delete requires Human confirmation, then calls `delete_preset(name)`. It never calls any ScreeningProfile delete API. If the name is last-used, the same atomic state replacement sets last-used to `null`; Quick Start becomes unavailable.

Details may show name, internal Profile ID, Version, Criteria IDs/text, and exact expressions. Normal Run Summary remains UUID-free.

## 18. Run Summary

Implement a pure renderer in `run_configuration.py`:

```python
def render_run_summary(
    configuration: ResolvedRunConfiguration,
) -> str:
    ...
```

It receives no store and performs no read. It renders only:

- Preset name;
- `Profile Version: vN`, never `screening_profile_id` or `sp_...`;
- each exact Criterion ID and text from the resolved Profile object;
- Rule business display and every exact expression from the resolved RuleSet;
- Provider and Model from the resolved Provider object;
- Action as uppercase `FAVORITE` or `FORWARD`;
- `no_forward` enabled/disabled and real-forward suppression meaning;
- batch-filter enabled/disabled;
- duration (`Unlimited` for zero, otherwise exact seconds);
- optional static text: confirmation continues into the existing Calibration flow.

Business display is derived without persisted Rule mode:

- exact one-expression equality with generated ALL → `ALL`;
- otherwise exact one-expression equality with generated ANY → `ANY`;
- one-Criterion expression matching both → `SINGLE (ALL / ANY equivalent)`;
- all other valid one-or-more collections → `CUSTOM` and, for multiple rules, state fixed ANY.

The renderer never displays API keys, Profile UUID, Calibration profile/readiness/geometry, email, Legacy keywords, Candidate data, or persistence paths.

`screening_preset_cli.prompt_run_summary(...)` prints this string and returns exactly `confirm`, `edit`, or `cancel`.

## 19. Runtime Handoff

### 19.1 Backward-compatible signature

Change only the setup signature to:

```python
def run(
    screening_profile_id: Optional[str] = None,
    *,
    run_bound_rule_set: ScreeningRuleSet | None = None,
    resolved_run_configuration: ResolvedRunConfiguration | None = None,
):
    ...
```

Modes are mutually exclusive:

- resolved path: `resolved_run_configuration` is present and both legacy setup arguments must be absent;
- advanced path: resolved config is absent, `screening_profile_id` must resolve as today, and `run_bound_rule_set` must be a `ScreeningRuleSet`;
- mixed or incomplete direct calls raise `TypeError` before Run state mutation.

Existing callers remain valid without positional/signature migration.

### 19.2 Resolved path

After the existing per-Run state reset:

```text
profile_version = configuration.exact_screening_profile_version
run_bound_rule_set = configuration.run_bound_screening_rule_set
run_ai_provider_config = configuration.current_complete_ai_provider_config
action_mode = configuration.action_mode
run_duration_seconds = configuration.duration_seconds
no_forward_mode = configuration.no_forward
```

The Profile digest/binding is computed from that exact object. No Profile, Preset, Rule, or Provider store is called. The same Profile/RuleSet/Provider objects then enter the unchanged OCR/R13 initialization and Candidate loop.

`--simple-mouse` may still be read from the already parsed invocation because it is an existing advanced physical-movement switch outside the R15 configuration model. No other CLI value may override the confirmed resolved fields after Summary.

### 19.3 Last-used write timing

Immediately after Summary returns `confirm` and immediately before calling `run(resolved_run_configuration=...)`:

```text
construct LastUsedRunSettings from the resolved object
→ ScreeningPresetStore.save_last_used(...)
→ call run(...) regardless of an expected last-used I/O failure
```

On write failure, print a concise warning that future Quick Start was not updated. Do not alter the resolved object, reload any store, or prevent the already confirmed Run.

Browse, selection, Preset save, Summary render, Edit, and Cancel never call `save_last_used()`.

## 20. Existing Action Input and Calibration Preparation

Extract the current interactive code after Action/Legacy collection into one private `simple_brush.py` helper rather than duplicating it:

```python
def _prepare_interactive_runtime_inputs(
    *,
    action_mode_value: str,
    no_forward: bool,
    duration_seconds_value: int | None,
    batch_filter_enabled_choice: bool | None,
) -> None:
    ...
```

- `duration_seconds_value=None` and `batch_filter_enabled_choice=None` preserve the existing advanced interactive prompts;
- resolved R15 path supplies the confirmed duration and batch Boolean, so those choices are not prompted again;
- backup-email behavior remains exactly conditional on `forward and not no_forward` and remains outside the R15 persistent models;
- Calibration Profile selection and current focus/forward/favorite/OCR preparation stay after Human Confirm;
- for a resolved disabled batch switch, use the current no-batch branch;
- for a resolved enabled batch switch, request the existing physical batch calibration when no selected template supplies regions; physical calibration success/cancel/failure retains existing behavior;
- the helper does not return or mutate `ResolvedRunConfiguration`.

The existing `get_user_input(...)` continues to own the advanced/non-interactive entry and delegates its current interactive post-Legacy work to this helper. The R15 resolved path sets Legacy state empty and calls the helper only after confirmation.

This extraction is routing only. Do not modify the physical Calibration functions or action mechanics.

## 21. Advanced CLI Compatibility

The non-interactive branch in `main()` remains first and semantically unchanged:

```text
is_noninteractive_startup(cli_args)
→ require --screening-profile-id and one-or-more --screening-rule
→ build one RuleSet
→ run(screening_profile_id=..., run_bound_rule_set=...)
```

The existing advanced `run()` branch continues:

- current `get_user_input(...)` behavior;
- one `load_latest(profile_id)`;
- one `AIProviderConfigStore.load()`;
- the exact returned objects held for the whole Run.

Do not change the trigger predicate, parse behavior, repeatable Rule preservation, `--calibration-profile`, `--keywords`, `--email`, Action, duration, no-forward, no-batch, simple-mouse, or auto semantics.

R15 adds no `--screening-preset` option.

## 22. Legacy Compatibility

The exact branch split is `simple_brush.main()`:

- non-interactive or explicit Advanced manual Run calls the existing advanced `run()` setup and retains Legacy keyword input/parsing;
- Quick Start and Choose-Preset call `run(resolved_run_configuration=...)` and never call the Legacy keyword prompt or `parse_keyword_rules()`;
- resolved path explicitly sets `forward_keywords=[]` and `forward_enabled=False` before post-confirm Runtime preparation;
- no invalid R15 state routes into the advanced/Legacy branch.

Do not delete `--keywords`, `parse_keyword_rules`, `detect_keywords`, Legacy globals/logging, or existing tests. Legacy remains compatibility/shadow behavior with no Am7 Decision/action authority.

## 23. Calibration Protected Boundary

R15 resolver, data models, persistence, and Summary must not import or call:

- Calibration Profile scanning/loading;
- coordinate/region readers;
- system geometry/DPI comparison;
- preview generation;
- physical region selection;
- calibration validation or readiness checks.

Only after Summary confirmation does `simple_brush.run()` invoke the existing post-confirm input/Calibration path. `batch_filter_enabled` remains only an intent switch. It never carries coordinates, regions, a Calibration Profile, or readiness.

Protected unchanged functions include:

- `launch_calibration_template()` behavior;
- `prompt_calibration_profile_selection()` behavior;
- `load_calibration_profile_into_runtime()` behavior;
- `ensure_batch_filter_regions_calibrated()`;
- `ensure_focus_restore_region_calibrated()`;
- `ensure_forward_click_regions_calibrated()`;
- `ensure_favorite_button_region_calibrated()`;
- `ensure_ocr_region_calibrated()`;
- all calibration models, paths, eleven regions, preview, DPI, cancellation, fallback, and physical ordering.

Menu movement is routing only. Calibration failure remains outside R15 and retains current behavior.

## 24. Failure Semantics

| Failure | Exact handling |
|---|---|
| Preset state file missing | Empty Preset list and no last-used state |
| File/root or Preset collection malformed, including invalid JSON/UTF-8, Preset fields, or duplicate name | `ScreeningPresetValidationError`; no accepted partial Preset collection |
| Last-used portion malformed | Preset collection remains listable/gettable/selectable/manageable; `load_last_used()` fails and Quick Start is unavailable; no automatic rewrite |
| Last-used object structurally valid but referenced Preset missing | Preset collection remains usable; resolver makes Quick Start unavailable; no substitute, Legacy prompt, or Runtime |
| Preset state read/write/replace error | `ScreeningPresetIOError`; prior file remains authoritative |
| Create duplicate or blank name | Reject before write |
| Replace/rename failure | Old Preset and old last-used reference remain authoritative |
| Delete failure | Old Preset and last-used reference remain authoritative; do not report deletion |
| Profile Save succeeds, Preset rebind fails | New formal Version remains; old Preset binding remains |
| Quick Start has no state | Explain unavailable; return to menu |
| Exact Profile missing/invalid | Fail closed; no `load_latest()` substitution |
| Rule invalid/unknown Criterion | Existing R06 exception becomes setup error; no repair or Runtime |
| Provider missing/incomplete/invalid/unreadable | Setup error; route to configuration/menu; no Runtime |
| Run setting invalid | Setup error; no guessed default and no Runtime |
| Summary Edit/Cancel | Discard resolved object; no last-used write and no Runtime |
| Last-used write fails after Confirm | Warn; confirmed resolved Run may proceed unchanged |
| Calibration fails after Confirm | Existing Calibration behavior; not an R15 setup result |
| Unexpected defect | Propagate to existing outer boundary; do not normalize as config invalid |

No path guesses, repairs, retries, falls back to latest/another Preset/Provider/Legacy, or starts a partial Run.

## 25. Implementation Sequence

One coherent AM7-R15 Change is implemented in this order:

1. add `screening_preset.py` models/store and its focused tests;
2. add `run_configuration.py` pure helpers/resolver/renderer and focused tests;
3. add the exact-Version-returning helper to `screening_profile_cli.py` and its tests;
4. add `screening_preset_cli.py` management/startup UX and focused startup tests;
5. modify only `simple_brush.py` startup/setup seams and obsolete startup assertions;
6. update `README.md` to the implemented truth;
7. run focused new tests, targeted protected regressions, compile, then the full suite once;
8. create the Acceptance Report only in its separately authorized acceptance turn.

No intermediate micro-Change, migration, or release operation is required.

Implementation should occur only after Human TID approval on one dedicated AM7-R15 Requirement branch (recommended name: `am7-r15-run-configuration-quick-start`) and remain one coherent implementation Change. This TID turn does not create, switch, or modify any branch.

## 26. Technical Responsibilities

| ID | Responsibility | Primary file/function | Product AC |
|---|---|---|---|
| R01 | Define exact immutable four-field Preset with canonical trimmed name and shape-only validation | `screening_preset.ScreeningPreset` | AC-01–AC-03, AC-11 |
| R02 | Enforce blank/trimmed exact-name uniqueness without ID/alias/case-fold framework | Preset model/store | AC-01, AC-10, AC-11 |
| R03 | Define exact immutable five-field last-used value and `None` missing state | `LastUsedRunSettings` | AC-14–AC-17 |
| R04 | Define exact immutable non-persistent eight-field carrier for already resolved Profile/RuleSet/Provider/Run settings | `ResolvedRunConfiguration` | AC-17–AC-19, AC-21 |
| R05 | Parse/write the strict one-file two-key JSON while validating Preset collection and last-used portions independently | `ScreeningPresetStore` | AC-03, AC-09, AC-14–AC-16 |
| R06 | Reject malformed file/root or Preset collection without partial Presets; isolate malformed/dangling last-used from healthy Presets | Store loader | AC-09–AC-11, AC-17 |
| R07 | Use same-directory temporary write and `os.replace()` | Store writer | AC-09, AC-13–AC-16 |
| R08 | Create Preset only after valid preview/Human Save | `create_preset`; Preset CLI | AC-01–AC-03, AC-09 |
| R09 | Replace/rename Preset and matching last-used name in one atomic state write | `replace_preset` | AC-11, AC-14 |
| R10 | Delete only Preset and atomically clear matching last-used | `delete_preset` | AC-13, AC-14 |
| R11 | Write last-used only after Confirm; allow confirmed Run after preference-write failure | `main()` handoff | AC-14–AC-17 |
| R12 | Generate exact Profile-order ALL/ANY expressions | Rule helper functions | AC-05–AC-07 |
| R13 | Preserve Custom raw C00x expressions and fixed multi-Rule ANY | Rule construction | AC-03, AC-05, AC-08 |
| R14 | Reuse R06 construction/evaluation for complete semantic validation | `validate_preset_definition` | AC-03, AC-06–AC-08, AC-21 |
| R15 | Load Preset Profile by exact ID+Version only | `validate_preset_definition` | AC-02, AC-12, AC-18 |
| R16 | Consume one existing Provider Store `VALID` result before Summary and retain its exact config without duplicate completeness checks | `resolve_run_configuration` | AC-17, AC-18 |
| R17 | Resolve Preset references and all R15 settings fail-closed without invalidating a healthy library for dangling last-used | `resolve_run_configuration` | AC-02, AC-10, AC-17 |
| R18 | Render UUID-free, Calibration-free Summary solely from resolved value | `render_run_summary` | AC-04, AC-18, AC-19, AC-23 |
| R19 | Derive ALL/ANY/Custom display without persisted Rule mode | Summary renderer | AC-06–AC-08, AC-18 |
| R20 | Implement Confirm/Edit/Cancel; Edit always re-resolves | Summary CLI | AC-17–AC-19 |
| R21 | Implement exact normal top-level and Advanced routing | startup CLI / `main()` | AC-04, AC-10, AC-20, AC-24 |
| R22 | Implement Quick Start from structurally valid last-used, with explicit dangling/malformed unavailability and current safety overrides | startup CLI / resolver | AC-10, AC-14–AC-17 |
| R23 | Select Preset by deterministic number/name without persisted number identity | Preset CLI | AC-04, AC-10 |
| R24 | Implement list/create/edit/delete/details/Advanced Profile Management | Preset CLI | AC-01, AC-10–AC-13 |
| R25 | Add exact newly saved ProfileVersion-returning Draft helper without changing existing CLI | `screening_profile_cli.py` | AC-02, AC-04, AC-12 |
| R26 | Enforce latest-only Criterion edit and explicit Preset rebind boundary | Preset edit flow | AC-02, AC-12, AC-13 |
| R27 | Extend `run()` with mutually exclusive resolved/advanced setup modes | `simple_brush.run` setup | AC-02, AC-18, AC-21, AC-24 |
| R28 | Pass same resolved Profile/RuleSet/Provider objects and settings into unchanged downstream Run | `simple_brush.run` handoff | AC-18, AC-21, AC-22 |
| R29 | Preserve advanced `load_latest()` once and all eleven argument semantics | advanced `main`/`run` branch | AC-02, AC-24 |
| R30 | Skip Legacy collection only on normal resolved path; preserve advanced Legacy | branch in `main`/`run` | AC-20, AC-22, AC-24 |
| R31 | Invoke unchanged Calibration only after Confirm and exclude it from resolver/Summary | private preparation helper | AC-23 |
| R32 | Persist/pass only batch enabled Boolean, never Calibration data | models/resolver/handoff | AC-16, AC-23 |
| R33 | Preserve Action, duration, no-forward, email, and no-favorite-fallback behavior | settings CLI/setup seam | AC-15, AC-16, AC-19, AC-22 |
| R34 | Keep Candidate/OCR/AI/R12/R13/action/calibration bodies untouched | protected diff review | AC-21–AC-23 |
| R35 | Update README to implemented startup truth and unchanged compatibility boundaries | `README.md` | AC-04, AC-18, AC-20, AC-23, AC-24 |
| R36 | Keep automated verification local and side-effect-free | three focused test modules | AC-01–AC-24 |

Technical Responsibilities count: **36 (R01–R36)**.

## 27. Focused Test Journeys

All tests use `TemporaryDirectory` for Profile/Preset state and mocks only at external Provider/browser/mouse/action/Runtime-entry boundaries. They do not use real API keys or live BOSS.

| Journey | Level / file | Required proof |
|---|---|---|
| J01 Preset create + persistence | Unit / `test_screening_preset` | Save named exact v1 ALL expression; reload identical fields |
| J02 Duplicate / blank name | Unit / `test_screening_preset` | Blank rejected; same trimmed exact name rejected; no write corruption |
| J03 ALL generation | Unit / `test_run_configuration` | C001/C002/C003 → exact `C001 AND C002 AND C003`; R06 validation executes |
| J04 ANY generation | Unit / `test_run_configuration` | Exact OR expression; one-Criterion behavior |
| J05 Custom Rule | Unit / `test_run_configuration` | Raw `C001 AND (C002 OR C003)` preserved; invalid grammar/reference fails with no repair |
| J06 Exact ProfileVersion binding | Unit / `test_run_configuration` | Preset v1 remains v1 after v2 exists; Preset resolver never calls `load_latest()` |
| J07 Criterion edit / explicit rebind | Focused / Profile/Preset CLI tests | Profile save produces v2; stored Preset stays v1 until explicit preview/save, then v2 |
| J08 Profile save success / Preset rebind failure | Unit / `test_screening_preset` | v2 remains; failed atomic Preset replace leaves v1 binding |
| J09 Rename + last-used | Unit / `test_screening_preset` | Successful one-write rename updates last-used; injected write failure preserves both old values |
| J10 Delete last-used Preset | Unit / `test_screening_preset` | Preset removed, Profile history untouched, last-used null, Quick Start unavailable |
| J11 Last-used write timing | Startup / `test_am7_r15_startup` | Browse/edit/save/cancel make zero writes; Confirm writes once immediately before handoff; write failure warns and proceeds |
| J12 Quick Start success | Startup / `test_am7_r15_startup` | Restores five settings, resolves exact Profile/RuleSet/Provider, Summary, Confirm, same objects/values reach `run()` |
| J13 Quick Start invalid Preset state | Resolver/startup | A: structurally valid dangling last-used fails Quick Start with no Runtime/Legacy/substitution while healthy Presets remain listable/selectable and Choose Preset remains usable; B: malformed Preset collection fails validation with no partial list; C: malformed last-used alone disables Quick Start without hiding healthy Presets |
| J14 Invalid ProfileVersion | Resolver | Missing exact Version gives no latest call/substitution and no Runtime |
| J15 Invalid Rule | Resolver | Malformed/unsupported/unknown Criterion fails through R06 and starts no Run |
| J16 Provider invalid | Resolver/startup | Existing Store `NOT_CONFIGURED`/`INCOMPLETE`/`INVALID`/`UNSUPPORTED_VERSION` classifications and IO error return to config/menu with no Runtime; R15 performs no duplicate field-level completeness validation |
| J17 no_forward restoration | Resolver/startup | FORWARD + true is shown as suppressed and passed true; no favorite fallback |
| J18 Run Summary UUID-free | Unit / `test_run_configuration` | Includes name, v1, Criteria, Rule, Provider/model/settings; excludes `sp_...`, Calibration, API key |
| J19 Calibration untouched | Startup / `test_am7_r15_startup` + existing regression | Resolver/Summary make zero Calibration calls; existing preparation begins only after Confirm; no new persistence |
| J20 Legacy normal UX removal | Startup / existing compatibility | Quick/Preset makes zero Legacy prompt/parse calls; `--keywords` advanced path remains unchanged |
| J21 Advanced CLI compatibility | Existing + focused startup | All eleven parse; trigger predicate unchanged; advanced ID resolves latest exactly once and retains object |
| J22 One Run-bound RuleSet identity | Setup integration | Resolver builds one RuleSet; same object reaches `run()` and each Candidate; no Preset lookup/rebuild per Candidate |

Focused Test Journey count: **22 (J01–J22)**.

## 28. Regression and Verification Plan

### 28.1 New focused tests

Run once per implementation verification cycle after code completion:

```powershell
.\venv\Scripts\python.exe -m unittest `
  tests.test_screening_preset `
  tests.test_run_configuration `
  tests.test_am7_r15_startup -v
```

### 28.2 Targeted accepted regressions

```powershell
.\venv\Scripts\python.exe -m unittest `
  tests.test_screening_profile `
  tests.test_screening_profile_cli `
  tests.test_screening_rule_engine `
  tests.test_ai_provider_config `
  tests.test_ai_provider_cli `
  tests.test_candidate_decision_integration `
  tests.test_simple_brush_ocr -v
```

These existing tests supply the needed Profile, Rule, Provider, startup/CLI, action/no-forward, Calibration, Run setup, and Candidate-loop regressions. Do not add a repository scanner or duplicate R12/R13 integration harness.

### 28.3 Compile

```powershell
.\venv\Scripts\python.exe -m compileall `
  screening_preset.py `
  run_configuration.py `
  screening_preset_cli.py `
  screening_profile_cli.py `
  simple_brush.py `
  tests/test_screening_preset.py `
  tests/test_run_configuration.py `
  tests/test_am7_r15_startup.py
```

### 28.4 Full regression

Only after focused and targeted tests pass, run the complete tracked suite once for final Requirement acceptance:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Do not repeatedly run the full suite during iteration. Capture formal evidence from command start in the later implementation/acceptance workflow.

## 29. Product AC → Technical Verification Matrix

| Product AC | Technical responsibility | Verification journey | Planned result |
|---|---|---|---|
| AC-01 Human-readable Preset | R01, R02, R08, R24 | J01, J02 | Pending implementation |
| AC-02 exact Profile binding | R01, R15, R17, R25–R27 | J06, J07, J14, J21 | Pending implementation |
| AC-03 formal Rule persistence | R01, R05, R08, R13, R14 | J01, J05 | Pending implementation |
| AC-04 UUID-free normal UX | R18, R21, R23, R25 | J12, J18 | Pending implementation |
| AC-05 existing Criterion identity | R12–R14, R18 | J03–J05, J18 | Pending implementation |
| AC-06 ALL shortcut | R12, R14, R19 | J03 | Pending implementation |
| AC-07 ANY shortcut | R12, R14, R19 | J04 | Pending implementation |
| AC-08 Custom compatibility | R13, R14, R19 | J05 | Pending implementation |
| AC-09 cross-process persistence | R05–R08 | J01, J02, J13 | Pending implementation |
| AC-10 Human selection | R02, R06, R17, R21–R24 | J12, J13 | Pending implementation |
| AC-11 unique name | R01, R02, R06, R08, R09 | J02, J09 | Pending implementation |
| AC-12 immutable Criterion editing | R15, R25, R26 | J07, J08 | Pending implementation |
| AC-13 deletion isolation | R07, R10, R26 | J08, J10 | Pending implementation |
| AC-14 last-used Preset timing | R03, R09–R11, R22 | J09–J12 | Pending implementation |
| AC-15 last action/no-forward | R03, R11, R22, R33 | J11, J12, J17 | Pending implementation |
| AC-16 duration/batch state | R03, R11, R22, R32, R33 | J11, J12, J19 | Pending implementation |
| AC-17 Quick Start validation | R05, R06, R16, R17, R20, R22 | J12–J16 | Pending implementation |
| AC-18 complete Summary/identity | R04, R16, R18–R20, R28 | J12, J18, J22 | Pending implementation |
| AC-19 explicit action confirmation | R18, R20, R33 | J11, J17, J18 | Pending implementation |
| AC-20 normal Legacy removal | R21, R30 | J20 | Pending implementation |
| AC-21 one Run-bound RuleSet | R14, R27, R28 | J22 | Pending implementation |
| AC-22 brain contracts unchanged | R28, R30, R33, R34 | J17, J20–J22 + targeted regression | Pending implementation |
| AC-23 Calibration unchanged | R18, R31, R32, R34 | J19 + existing Calibration regression | Pending implementation |
| AC-24 advanced CLI compatibility | R21, R27, R29, R30 | J20, J21 | Pending implementation |

Product AC mapped: **24 / 24**.

## 30. README and Documentation Changes

`README.md` is part of the one authorized implementation Change, not deferred to Acceptance. After code behavior exists, update only the affected sections:

- safety note about normal Legacy prompt;
- first-run and daily startup flows;
- seven-item top-level menu and Advanced submenu;
- ScreeningPreset schema/location and exact Profile Version meaning;
- ALL/ANY/Custom persistence and fixed R06 authority;
- Quick Start last-used fields and Confirm timing;
- UUID-free, Calibration-free Run Summary;
- normal versus advanced/Legacy paths;
- all eleven CLI arguments unchanged and no `--screening-preset`;
- Calibration remains post-confirm and unchanged;
- local data-path table includes `data/screening_presets.json`.

Do not rewrite unrelated README sections or claim implementation/acceptance before evidence exists.

## 31. Acceptance Report Requirements

After implementation and verification, a separately authorized acceptance turn creates:

```text
docs/AM7-R15-acceptance-report.md
```

It records:

- implemented file scope;
- focused, targeted regression, compile, and one full-suite result;
- J01–J22 evidence;
- AC-01–AC-24 mapping;
- exact resolved-value identity/handoff evidence;
- UUID-free Summary and Legacy-normal-UX evidence;
- Calibration protected-boundary evidence;
- AI/OCR/Decision/action protected-diff review;
- deviations, open issues, and conflicts.

If every automated contract passes, status is exactly:

```text
Automated Acceptance Passed / Pending Human Final Review
```

The report must not claim Human Accepted, Merged, or Released.

## 32. Explicit Protected / Untouched Scope

### 32.1 Entire files protected from R15 modification

- `screening_profile.py`;
- `screening_rule_engine.py`;
- `ai_provider_config.py`;
- `ai_provider_cli.py`;
- `llm_provider_runtime.py`;
- `ai_candidate_input.py`;
- `ai_screening_prompt.py`;
- `ai_screening_contract.py`;
- `ai_screening_runtime.py`;
- `ai_screening_persistence.py`;
- `candidate_decision.py`;
- `ocr_detector.py` and all OCR/Candidate/record/store modules;
- `ocr_calibration.py`, `calibration_profiles.py`, `calibration_steps.py`, and `calibration_template.py`;
- browser/mouse modules, packaging, requirements, build, and release files;
- Frozen R05–R15 RPD/TID documents other than this newly created TID.

### 32.2 Protected regions of `simple_brush.py`

No semantic edits are permitted in:

- OCR initialization/capture/detection/Complete Scan;
- Candidate recording/finalization;
- R13 retry and AI persistence;
- Candidate Decision and Decision persistence;
- `perform_favorite_action()` and `forward_one_candidate()`;
- Candidate-switch preparation/confirmation and `next_candidate()`;
- Candidate/batch loop, refresh, pause/resume, stop, and timer behavior;
- physical Calibration bodies and ordering.

Only imports, startup menu/dispatch, reusable input extraction, `run()` setup branching, and the pre-existing Profile/Provider/Rule handoff block may change.

## 33. Open Technical Questions / Conflicts

### Open Technical Questions

None.

### Contract Conflicts

None.

The current in-`run()` Profile/Provider loading is a narrow setup gap, not a conflict: the resolved path bypasses both loads, while the advanced path retains its accepted behavior. Separating last-used reference resolution from Preset collection parsing preserves both fail-closed Quick Start and usable healthy Presets without a recovery framework. The accepted Calibration flow remains post-confirm and outside the resolver; the retained batch Boolean is only the requested Run switch and carries no Calibration data.

### Human Review Required Items

- Review and Freeze this TID before implementation.

No product decision is requested.

## 34. Final Change Scope

```text
One coherent AM7-R15 implementation Change

NEW production (3)
  screening_preset.py
  run_configuration.py
  screening_preset_cli.py

MODIFIED production/documentation (3)
  simple_brush.py                 # startup/setup seam only
  screening_profile_cli.py        # additive exact-Version Draft helper
  README.md                        # implemented startup truth

NEW tests (3)
  tests/test_screening_preset.py
  tests/test_run_configuration.py
  tests/test_am7_r15_startup.py

MODIFIED tests (2)
  tests/test_simple_brush_ocr.py   # obsolete menu/setup assertions only
  tests/test_screening_profile_cli.py

PROTECTED
  OCR / Candidate / AI / R06 / R12 / R13 / action / switch / Calibration
  all other source, tests, dependencies, packaging, and release files
```

Final TID state:

- Version: 0.2
- Status: Draft — Pending Human Review
- Implementation Changes: 1
- Technical Responsibilities: 36 (R01–R36)
- Focused Test Journeys: 22 (J01–J22)
- Product AC Mapping: 24 / 24
- Open Technical Questions: None
- Contract Conflicts: None
- Implementation / tests / Acceptance Report: Not started
