# AM7-R15 — Run Configuration & Quick Start UX

## Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R15
- Document Type: Requirement / Product Design
- Version: 0.2
- Status: Draft — Pending Human Review
- Governing Document: `CODEX-CONSTITUTION.md`
- Observed Working Branch: `am7-r14-final-integration-acceptance`
- Observed Working HEAD / Baseline: `0260f2824aa1b7d932d0fa88ea94a324fa1fe81a`
- Product Source: *Ocria Am7 R15 — Run Configuration & Quick Start UX 优化需求（Draft v0.1）*
- Product Source URL: `https://docs.google.com/document/d/1yJnGUJv13xzmyXK2qMO7RzYvfKB6xod3C4G9HvDOP1c/edit?tab=t.0`

## 1. Requirement Identity

AM7-R15 introduces a Human-facing Run configuration and Quick Start experience for Ocria Am7.

The product principle is:

> R15 does not change Ocria's decision brain. It redesigns the startup cockpit.

The new product boundary converts the normal daily flow from repeated technical input:

```text
Prepare Profile
→ enter Profile UUID
→ enter ScreeningRule expression(s)
→ choose Action Mode
→ enter Legacy keyword configuration
→ continue startup
```

into a reusable Human-facing flow:

```text
choose saved ScreeningPreset
→ inspect resolved Run Summary
→ Human confirms
→ existing Calibration / Run lifecycle
```

and, after at least one confirmed Run configuration exists:

```text
Quick Start
→ inspect resolved Run Summary
→ Human confirms
→ existing Calibration / Run lifecycle
```

## 2. Status

This document is a Draft product contract pending Human Review. It is not Frozen, Approved, Accepted, or Ready for Implementation. No TID or implementation is authorized by this document's current status.

## 3. Source / Baseline

The following sources were read through targeted inspection:

- `CODEX-CONSTITUTION.md`;
- the Human-owned R15 product source identified in Metadata;
- `README.md`;
- `simple_brush.py`;
- `screening_profile.py`;
- `screening_profile_cli.py`;
- `screening_rule_engine.py`;
- the existing AI Provider configuration store and configuration CLI entry;
- focused existing tests for ScreeningProfile CLI, Run-bound RuleSet integration, action/no-forward behavior, and current startup behavior;
- Frozen R05, R06, R12, and R13 RPD/TID contracts.

The branch and HEAD in Metadata are read-only observations of the supplied workspace. They are not an assertion that an R15 Requirement branch was created; this task performs no branch operation.

## 4. Problem Statement

The accepted Am7 runtime already has formal Profile, Rule Engine, AI screening, Candidate Decision, action authorization, persistence, and failure-degradation boundaries. The normal startup experience does not expose those boundaries as one reusable business configuration.

Today, the interactive path requires the operator to traverse separate technical concepts and repeatedly supply values that should be reusable:

- ScreeningProfile preparation returns only an internal Profile ID and the prepared selection is process-local;
- normal Run startup requires a technical Profile identifier rather than a Human-readable business name;
- ScreeningRule expressions are entered again for each Run and exist only in memory;
- the Run currently loads the latest Profile Version from an ID instead of preserving an exact Preset-bound Version;
- Action Mode, duration, `no_forward`, and batch-filter choices are collected separately;
- the Legacy keyword prompt is still part of normal interactive startup even though it has no Ocria Am7 Candidate Decision authority;
- no single resolved Run Summary shows the complete configuration and side effects before execution begins.

The result is repetitive, error-prone startup work that exposes implementation identities and makes the operator reconstruct the same Run intent every day.

## 5. Product Goal

R15 must provide:

1. a persisted, Human-readable `ScreeningPreset` that binds an exact saved ScreeningProfile Version and formal ScreeningRule expression(s);
2. normal first-use, daily Quick Start, preset-switching, and preset-management journeys;
3. persistence of the last Human-confirmed Run choices needed to reproduce a safe Quick Start;
4. one resolved Run Configuration and a complete pre-Run Summary;
5. explicit Human confirmation before any existing Runtime or action-capable flow begins;
6. removal of the Legacy keyword prompt from normal Am7 interactive startup while preserving the Legacy/advanced CLI surface;
7. no change to accepted Calibration, OCR, AI, Rule evaluation, Candidate Decision, persistence, action, Candidate-switch, or batch-continuation semantics.

## 6. Current-State Findings from Code

### 6.1 ScreeningProfile lifecycle

- Formal `ScreeningProfileVersion` values are persisted under stable Profile IDs and immutable monotonic Version numbers.
- Exact versions can be loaded by Profile ID plus Version; `load_latest()` is also available.
- Draft creation/editing and Human Save are provided by the existing Profile subsystem.
- `run_screening_profile_configuration()` returns a prepared Profile ID only. That prepared selection is held only in the current startup process and is not a cross-process Run preset.
- Existing Profile management displays internal Profile IDs and does not provide a separate Human-readable Preset name.

### 6.2 Rule input and Run binding

- Current interactive startup asks for one-or-more raw ScreeningRule expressions on every Run.
- `_build_screening_rule_set(...)` constructs one `ScreeningRuleSet` from those expressions.
- `run(..., run_bound_rule_set=...)` requires that RuleSet, and the same Run-bound RuleSet is used for Candidate processing.
- The accepted R06 grammar and fixed multi-Rule ANY behavior already provide the only Rule evaluation authority.
- ScreeningRule and ScreeningRuleSet do not have persistent IDs, versions, or digests.

### 6.3 Current Profile resolution gap

- Current `run()` accepts a Profile ID and calls `ScreeningProfileStore.load_latest(...)`.
- That behavior is insufficient for a Preset because a Preset must continue to mean the exact saved Profile Version selected at Human Save time.
- R15 therefore owns a startup-resolution correction: Preset execution resolves by exact Profile ID plus exact Version and carries that resolved Version into the confirmed Run. It must never reinterpret a Preset as `latest`.

### 6.4 Current Run-setting inputs

- Action Mode is collected interactively or through `--action-mode`.
- Duration is collected interactively or through `--duration-seconds`; zero/blank retains the accepted unlimited-duration behavior.
- `no_forward` originates from `--no-forward` and suppresses forwarding without converting the action to favorite.
- batch-filter behavior is controlled by the current calibration/profile path and `--no-batch-filter`.
- AI Provider configuration is persisted independently and the current Run loads one complete current configuration for repeated AI calls.

### 6.5 Legacy keyword and Calibration boundaries

- Normal interactive `get_user_input(...)` currently asks for Legacy keyword rules even though the accepted Am7 Candidate Decision path does not use them as decision or action authority.
- Startup currently exposes explicit Calibration configuration, and the Run performs accepted batch/focus/action/OCR-region calibration steps at their existing runtime boundary.
- R15 may reorganize menu access and configuration collection, but it does not alter Calibration data, geometry, ordering, persistence, or execution behavior.

### 6.6 Current public CLI surface

The current public/advanced CLI surface contains these eleven arguments and must remain compatible:

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
--screening-rule   (repeatable)
--action-mode
```

R15 v1 does not require a new `--screening-preset` option. Preset use is the normal interactive UX; the existing non-interactive and advanced CLI contracts remain available.

## 7. User Stories

### US-01 — First-time operator

As an operator, I can create a Human-readable screening scheme without copying a Profile UUID or manually deriving a long Rule expression.

### US-02 — Daily operator

As an operator, I can Quick Start from the last Human-confirmed configuration, inspect its real effects, and confirm it before Runtime begins.

### US-03 — Operator switching jobs

As an operator, I can select another saved Preset by name or displayed sequence number and see its exact Profile Version, Criteria, and Rule before Run confirmation.

### US-04 — Operator maintaining criteria

As an operator, I can edit a Preset's criteria through the existing immutable Profile Version lifecycle, review the resulting Rule, and deliberately rebind the Preset to the newly saved exact Version.

### US-05 — Advanced operator

As an advanced operator, I retain the existing Profile management and CLI capabilities, including Legacy keyword input, without those technical paths becoming normal Am7 Run UX or Am7 decision authority.

## 8. First-Use UX

When no valid Preset and no last-used configuration exist, Quick Start is unavailable with a clear explanation. The normal first-use flow is:

```text
Startup
→ ScreeningPreset Management
→ Create Preset
→ enter unique Human-readable name
→ select an existing saved Profile Version or create/save Profile criteria
→ inspect C00x Criteria
→ choose ALL, ANY, or Custom Rule authoring
→ inspect exact Profile/Criteria/formal Rule preview
→ Human Save Preset
→ choose Run-only settings
→ resolve Provider and all Run inputs
→ inspect Run Summary
→ Human Confirm
→ existing Calibration / Run
```

The normal journey must not require typing a Profile UUID. Internal Profile IDs remain visible only in details/advanced views where traceability requires them.

## 9. Daily Quick Start UX

After one valid confirmed configuration exists, the preferred daily flow is:

```text
Startup
→ Quick Start
→ resolve the saved last-used choices
→ validate the referenced Preset, exact Profile Version, RuleSet, Provider, and Run settings
→ display Run Summary
→ Confirm / Edit / Cancel
```

- `Confirm` hands the exact displayed resolved configuration forward, then enters the existing Calibration flow and existing Runtime boundary.
- `Edit` returns to Configuration Mode; any changed choices must be resolved again and a new Summary shown.
- `Cancel` starts no Runtime and does not alter last-used state.
- Quick Start is never an implicit auto-run. The final Human confirmation remains mandatory.

## 10. Switch-Preset UX

The normal startup menu must provide a saved-Preset selection flow:

1. list Presets with stable display ordering for the current view;
2. allow selection by Human-readable name or displayed sequence number;
3. show Preset details before it can start a Run;
4. collect or reuse Run-only settings;
5. resolve and validate the complete Run Configuration;
6. show Run Summary and require Human confirmation.

Displayed sequence numbers are transient menu selectors, not Criterion IDs, Preset identities, or persisted references.

A suitable top-level information architecture is:

```text
Quick Start
Choose ScreeningPreset and Run
ScreeningPreset Management
AI Provider Configuration
Calibration
Advanced
Exit
```

Exact labels and menu numbering are TID/implementation decisions. The product separations above are mandatory.

## 11. ScreeningPreset Domain Definition

`ScreeningPreset` (Chinese display term: “筛选方案”) is a Human-facing reusable Run-screening configuration.

Its v1 product content is exactly:

```text
ScreeningPreset
{
    preset_name,
    screening_profile_id,
    profile_version,
    screening_rule_expressions
}
```

Contracts:

- `preset_name` is the v1 Human identity and selection label.
- A name must contain at least one non-whitespace character. Leading/trailing whitespace is not identity-bearing and is removed before uniqueness comparison/storage.
- Stored names are unique by exact comparison after that trim. Case-folding, aliases, hidden IDs, and rename history are not required.
- `screening_profile_id` plus `profile_version` identifies one exact saved formal `ScreeningProfileVersion`.
- `screening_rule_expressions` is an ordered one-or-more collection of formal R06 expressions.
- Preset order has no Rule evaluation authority. Multiple expressions retain R06 fixed ANY semantics.
- Action Mode, duration, `no_forward`, batch-filter state, Provider configuration, Calibration selection/data, email, and Legacy keywords are not Preset content.
- ScreeningPreset does not replace `ScreeningProfileVersion`, `ScreeningRule`, `ScreeningRuleSet`, or the R06 Rule Engine.
- R15 adds no Preset ID, Preset version, Preset digest, lifecycle status, publication state, active state, or ownership framework.

## 12. Preset Persistence Semantics

- A Human-saved Preset and its formal Rule expressions persist across process restarts.
- Persistence preserves the exact Profile ID, exact Profile Version, expression order, and expression text approved at Save.
- Runtime does not persist a `ScreeningRuleSet` object. It reconstructs the accepted R06 value types from the stored expressions during pre-Run resolution.
- Preset persistence is configuration persistence only; it creates no RuleSet authority, evaluation engine, Candidate data, Run snapshot, replay record, or result record.
- Storage format, physical path, writer mechanics, and atomicity technique are TID decisions, subject to fail-closed product behavior.
- A Preset read or write error must be reported clearly and must not produce a partially accepted Preset or an implicit fallback.

## 13. ProfileVersion Binding Semantics

- Every Preset binds an exact existing formal `ScreeningProfileVersion` by `screening_profile_id + profile_version`.
- Creating or saving a Preset must verify that the exact formal Version exists and is valid.
- Selecting or starting a Preset must call the semantic equivalent of exact `load_version(...)`; it must not call `load_latest(...)` to reinterpret the Preset.
- A later Profile Version does not change an existing Preset.
- A Preset may deliberately be rebound to another already saved exact Version only through Human edit, preview, and Save.
- A Run binds the exact internal Profile ID plus the Profile Version shown in its Summary. No post-confirmation `latest` lookup is permitted.
- Criterion editing continues through R05 Draft and Human Save semantics. A formal Version is never modified in place.
- Because the accepted R05 edit path is latest-based, a Preset bound to a non-latest Version must not silently edit or fork that historical Version. The user must explicitly rebind to the current latest formal Version before criterion editing, or use Advanced Profile Management to create/select the intended formal state.
- After a new formal Profile Version is saved, the Preset remains bound to its previous exact Version until the Human reviews the criteria and Rule preview and saves the Preset rebind.
- If Profile Save succeeds but Preset rebind persistence fails, the new immutable Profile Version remains valid history and the Preset remains bound to its previous exact Version. R15 must report the failure and must not delete, rewrite, or roll back formal Profile history.

## 14. Rule UX / ALL / ANY / Custom

R15 provides authoring convenience only. R06 remains the sole grammar, validation, and evaluation authority.

### 14.1 Criterion identity

- Criteria continue to use exact R05 IDs such as `C001`, `C002`, and `C003`.
- No numeric `1/2/3` mapping, alias layer, label-to-ID translation, or second identity system is introduced.

### 14.2 ALL shortcut

For the bound Profile Version, ALL generates one formal expression by joining every Criterion ID in Profile order with ` AND `.

```text
C001 AND C002 AND C003
```

A one-Criterion Profile generates that single ID.

### 14.3 ANY shortcut

For the bound Profile Version, ANY generates one formal expression by joining every Criterion ID in Profile order with ` OR `.

```text
C001 OR C002 OR C003
```

A one-Criterion Profile generates that single ID.

### 14.4 Custom

- Custom accepts one-or-more formal expressions in the existing R06 language: Criterion IDs, uppercase `AND`, uppercase `OR`, and parentheses with the accepted token-boundary rules.
- `NOT`, lowercase repair, automatic token guessing, new operators, and new precedence rules are not supported.
- Multiple Custom expressions remain a one-or-more R06 Rule collection with fixed ANY semantics; duplicate expressions remain permitted because R06 does not define RuleSet as a mathematical set.

### 14.5 Preview and storage

- ALL and ANY are UX shortcuts, not stored evaluation modes and not a second Rule language.
- The Preset stores the resulting formal expression(s), not an authoritative `rule_mode`.
- Preview must show Criterion IDs/text and the exact formal expression(s) that will be saved.
- Before Preset Save and before Run Summary, the expressions must pass R06-compatible complete lexical, grammar, Criterion-reference, and input-domain validation against the exact bound Profile Version.
- R15 must reuse the accepted R06 authority; it must not add a second parser, evaluator, repair layer, or generic validation framework.

## 15. Preset Create / Edit / Delete Semantics

### 15.1 List and details

Normal management supports listing Presets and viewing:

- Human-readable Preset name;
- exact Profile ID and Version in details;
- ordered Criterion IDs and exact Criterion text;
- exact formal Rule expression(s).

### 15.2 Create

Create requires:

1. a unique valid name;
2. one exact saved Profile Version;
3. one-or-more valid formal Rule expressions produced by ALL, ANY, or Custom;
4. a complete preview;
5. explicit Human Save.

Browsing or previewing does not persist a Preset.

### 15.3 Edit

Edit supports:

- rename;
- rebind to an exact saved Profile Version;
- add/edit/delete Criterion through the existing R05 Draft/save boundary;
- change Rule authoring choice or formal expressions;
- view details and preview before Save.

Renaming changes the v1 Human identity. If the renamed Preset is the last-used Preset, the last-used reference must be updated as part of the successful rename; a failed rename must not leave a dangling last-used reference.

Criterion changes that produce a new Profile Version never auto-change the Preset. The Human must review and save the new exact binding and Rule. If referenced Criterion IDs become invalid or incomplete, Preset Save fails closed until corrected.

### 15.4 Delete

- Delete requires explicit Human confirmation.
- Delete removes only the Preset configuration.
- Delete never removes or rewrites formal ScreeningProfile history.
- Deleting the last-used Preset invalidates/clears the last-used Preset reference. Quick Start then becomes unavailable until another Run configuration is Human-confirmed.

## 16. Last-Used Semantics

R15 v1 persists the following last-used Run choices:

```text
last_used_preset_name
last_action_mode
last_duration_seconds
last_no_forward
last_batch_filter_enabled
```

Decisions based on current code and simplest sufficient safety:

- `last_no_forward` is included because it controls whether a confirmed FORWARD Run may cause an external side effect. Omitting it could turn a prior dry/suppressed Run into real forwarding during Quick Start.
- `last_batch_filter_enabled` is included because it changes Candidate-entry behavior and is an existing explicit Run switch. It persists only the desired enabled/disabled state; it does not persist Calibration coordinates, regions, profile selection, or new Calibration data.

Last-used state does not include Provider secrets/configuration, Profile data, RuleSet objects, email, Legacy keywords, Calibration data, or Runtime/Candidate state.

Update timing is strict:

- browsing, selecting, previewing, editing, or saving a Preset does not update last-used state;
- editing the Run Summary does not update last-used state;
- last-used state updates only after the complete resolved Summary has been explicitly confirmed and the Run is being handed to the existing Runtime boundary;
- it records the last Human-confirmed launch configuration, not whether the Run later completed successfully.

If a last-used preference write fails after confirmation, the already resolved confirmed Run may proceed because the write affects only future startup convenience. The failure must be clearly reported, and the system must not claim that Quick Start state was updated.

## 17. Quick Start Semantics

Quick Start resolves last-used state as a reference, never as trusted executable state.

Before showing a confirmable Summary, it must validate:

- the referenced Preset still exists under its exact name;
- the Preset is structurally valid;
- the exact bound Profile ID and Version exist and validate;
- all formal Rule expressions satisfy the existing R06 contract and reference the exact Criteria completely;
- the current AI Provider configuration is complete and valid;
- Action Mode, duration, `no_forward`, and batch-filter state are valid current Run inputs;

Quick Start must not:

- pick another Preset;
- upgrade to a latest Profile Version;
- repair or replace a Rule;
- guess a Provider/model;
- fall back to Legacy keywords;
- disable a failing safety choice silently;
- start Runtime before Human confirmation.

An invalid Quick Start returns to Configuration Mode with a concise actionable reason.

## 18. Run Configuration Boundary

R15 introduces a product-level resolved Run Configuration boundary before Runtime. It is not a new decision engine or persistent Run schema.

Conceptually, the resolved configuration contains:

```text
ResolvedRunConfiguration
{
    selected_preset_name,
    exact_screening_profile_version,
    run_bound_screening_rule_set,
    current_complete_ai_provider_config,
    action_mode,
    duration_seconds,
    no_forward,
    batch_filter_enabled
}
```

Contracts:

- All fields required for the Summary and Run entry are resolved and validated before confirmation.
- The Summary is a projection of that resolved configuration, not a preview assembled from stale or separate reads.
- On Confirm, the same resolved exact Profile Version, the same immutable RuleSet, and the same resolved Provider/configuration values enter the current Run.
- There is no second Preset/Profile/Rule/Provider disk lookup between Summary confirmation and Run binding.
- Edit discards the prior resolved configuration and requires a new resolution and Summary.
- The resolved configuration is Run-local. R15 does not require a persistent Run manifest, snapshot framework, replay system, cache, or new identity/digest.
- Calibration configuration, selection, geometry, readiness, and prerequisites are outside `ResolvedRunConfiguration` and are not resolved or validated by R15.
- The boundary sequence is strictly: resolve R15 Run Configuration → Run Summary → Human Confirm → existing Calibration flow unchanged → existing Runtime.

## 19. Run Summary

The pre-Run Summary must show at least:

- ScreeningPreset name;
- exact Profile Version, such as `v1`, without the internal ScreeningProfile UUID;
- every Criterion ID and exact Criterion text;
- Rule business display (ALL, ANY, Custom, or an unambiguous equivalent where derivable);
- every exact formal Rule expression and the fixed multi-Rule ANY meaning where applicable;
- current AI Provider and Model identifier;
- Action Mode as `FAVORITE` or `FORWARD`;
- `no_forward` enabled/disabled state and, for FORWARD, whether a real forward side effect is authorized;
- batch-filter enabled/disabled state;
- duration, including the accepted unlimited representation;

The normal Run Summary must not display the internal `screening_profile_id` or an `sp_...` UUID. The same exact ID remains present in the internal resolved `ScreeningProfileVersion` binding and may be shown in ScreeningPreset Details, Advanced Profile Management, debug output, persistence, and developer evidence.

The Summary contains no Calibration selection, profile, geometry, readiness, or prerequisite status. It may contain only a static notice that confirmation continues into the existing Calibration flow; such a notice is not configuration state or acceptance authority.

The Summary must not hide action side effects behind “Quick Start.” It offers exactly:

- Confirm;
- Edit;
- Cancel/back.

Only Confirm may cross the Runtime boundary.

## 20. Action Mode Handling

- Action Mode remains a Run-level choice and is not stored in ScreeningPreset.
- Last-used state may restore it for Quick Start, but the Summary must always display the exact effective mode.
- `FAVORITE` and `FORWARD` retain all accepted action mechanics and authorization ordering.
- `no_forward` applies only to `FORWARD`, suppresses the real forward action, and never falls back to favorite.
- R15 does not change the qualified-only action authorization contract.
- R15 does not change Candidate Decision statuses, action execution, Candidate switching, or continuation.
- No action-capable flow may begin before the final Summary confirmation.

## 21. Legacy Keyword Removal from Normal UX

- A normal Am7 interactive Run must not ask for Legacy keyword rules.
- Legacy keyword definitions, matches, and confirmation outcomes have no authority over the Am7 ScreeningPreset, RuleSet, Candidate Decision, or action authorization path.
- R15 does not delete or change the Legacy subsystem.
- `--keywords` and the existing Legacy parser remain available through the existing Advanced/Legacy CLI compatibility surface.
- Legacy input must not be automatically translated into R05 Criteria, R06 Rules, or Presets.
- Invalid Am7 configuration must never fall back to Legacy keywords.

## 22. Advanced / CLI Compatibility

- Advanced Profile Management remains available for technical inspection, formal Profile creation/editing, exact history inspection, and existing maintenance workflows.
- All eleven existing CLI arguments listed in §6.6 remain accepted with their current meanings and combinations.
- Existing non-interactive Profile/Rule input remains an advanced compatibility path; it is not the normal Preset UX.
- When an advanced CLI path resolves `--screening-profile-id` through its current latest-selection behavior, that selection must be resolved once before any Summary/Run handoff and then treated as the exact Run-bound Version. This does not change the flag into a Preset contract.
- R15 v1 deliberately does not require `--screening-preset`. Adding such a flag is outside the v1 product contract and is not needed to satisfy normal interactive Quick Start.
- No existing argument is renamed, repurposed, or removed by R15.

## 23. Calibration Explicit Non-Goal

R15 does not optimize or redesign Calibration.

The following remain unchanged:

- existing Calibration behavior and persistence;
- existing calibration template/profile data;
- all accepted screen regions, including the existing eleven-region layout where applicable;
- OCR region semantics;
- preview behavior;
- DPI behavior;
- recalibration rules;
- focus, batch-filter, forward, favorite, and OCR-region calibration mechanics;
- the accepted sequence in which calibration is performed before/within Run entry.

R15 may expose Calibration as a clearer startup menu entry. Calibration is not part of `ResolvedRunConfiguration`, Run Summary resolution, R15 validation, or R15 acceptance authority. R15 must not resolve a Calibration Profile, inspect or validate Calibration geometry, choose Calibration, persist last Calibration, move Calibration earlier, skip Calibration, auto-reuse Calibration, or redesign Calibration prompts.

After Human confirmation of the R15 Run Summary, the existing Calibration flow executes at its accepted boundary. A static notice that Calibration follows confirmation is permitted, but it is not a configuration field or resolved state.

`batch_filter_enabled` remains a Run-level switch in last-used state, `ResolvedRunConfiguration`, and Run Summary. It expresses only enabled/disabled state and never contains or represents batch-filter coordinates, Calibration regions, or a Calibration Profile.

## 24. Runtime Invariants

1. A Preset always means one exact saved `ScreeningProfileVersion`, never `latest`.
2. Formal Profile Versions remain immutable and monotonically versioned under R05.
3. Criterion identity remains exact `C00x`-style R05 identity; no second numeric mapping exists.
4. R06 remains the only Rule grammar, validation, precedence, and evaluation authority.
5. A Run uses exactly one immutable Run-bound `ScreeningRuleSet` for all Candidates.
6. Preset persistence stores formal expressions, not a persistent RuleSet identity/version/digest.
7. Rules are not looked up or rebuilt per Candidate.
8. The Profile Version displayed in the confirmed Summary corresponds to the same internally resolved exact Profile ID plus Version used by that Run; the same RuleSet and Provider configuration shown in the Summary are also used by that Run.
9. Action Mode and `no_forward` remain separate from screening logic.
10. Legacy keyword information has no Am7 decision or action authority.
11. ScreeningProfileVersion, AI Boolean evaluation, AI Runtime, retry/degradation, Candidate Decision, and persistence semantics remain unchanged.
12. Only `qualified` authorizes the accepted existing action path; `rejected` and `ai_failed` do not.
13. Candidate scan, finalization, switching, batch continuation, and stop behavior remain unchanged.
14. Calibration behavior, data, ordering, and runtime boundary remain unchanged and are outside R15 `ResolvedRunConfiguration`, Summary resolution, and validation; existing Calibration begins only after Human confirmation.
15. R15 adds no inference, fallback, repair, cache, replay, database, GUI, or generic configuration framework.

## 25. Failure / Invalid Configuration Behavior

All startup configuration failures fail closed before Runtime:

| Failure | Required behavior |
|---|---|
| No last-used state | Quick Start unavailable; offer normal configuration |
| Last-used Preset missing/deleted | Clear/mark invalid last-used reference; return to Preset selection |
| Preset persistence unreadable/invalid | Report configuration failure; no partial Preset and no Run |
| Exact Profile ID/Version missing or invalid | Report exact binding failure; do not load latest or another Profile |
| Rule lexical/grammar/reference validation fails | Report Rule failure; do not repair, evaluate, or fall back |
| Provider configuration missing/invalid | Route to Provider configuration or configuration menu; no Run |
| Action/duration/no-forward/batch choice invalid | Return to Run configuration; no guessed default |
| Preset Save fails | Preset is not accepted as saved; prior valid state remains authoritative |
| Preset delete fails | Preset remains present/authoritative; report failure |
| Profile Save succeeds but Preset rebind fails | Preserve new Profile history and old Preset binding; report rebind failure |
| Last-used write fails after confirmed handoff | Report that Quick Start state was not updated; the already resolved confirmed Run may proceed |

No failure may invoke Legacy keyword fallback, `latest` substitution, another Preset, Rule guessing, Provider guessing, or partial Runtime entry.

Calibration failures are not R15 configuration-resolution failures. After Summary confirmation, they retain their existing behavior inside the unchanged Calibration flow; R15 adds no pre-resolution, fallback, bypass, or new Calibration failure contract.

## 26. Product Acceptance Criteria

### AC-01 — Human-readable Preset creation

The user can create and Human-save a ScreeningPreset with a valid Human-readable name.

### AC-02 — Exact formal Profile binding

A Preset binds an existing saved Profile by exact `screening_profile_id + profile_version`; a later Version does not alter it and Run resolution never substitutes `latest`.

### AC-03 — Formal Rule persistence

A Preset saves an ordered one-or-more collection of exact formal ScreeningRule expressions without persisting a RuleSet identity/version/digest.

### AC-04 — UUID-free normal UX

Normal first-use, selection, Quick Start, and Run Summary neither require the user to type nor normally display a Profile UUID; technical identity remains available in Preset Details, Advanced Profile Management, debug output, persistence, and developer evidence.

### AC-05 — Existing Criterion identity

All Rule authoring, preview, persistence, and Summary use exact existing Criterion IDs such as `C001`; no numeric alias or conversion layer exists.

### AC-06 — ALL shortcut

ALL deterministically generates one R06-valid expression joining every bound Criterion ID in Profile order with `AND`, or the single ID for a one-Criterion Profile.

### AC-07 — ANY shortcut

ANY deterministically generates one R06-valid expression joining every bound Criterion ID in Profile order with `OR`, or the single ID for a one-Criterion Profile.

### AC-08 — Custom Rule compatibility

Custom supports one-or-more expressions using only the existing R06 Criterion-ID, uppercase `AND`/`OR`, parentheses, boundary, precedence, and fixed multi-Rule ANY contracts; `NOT`, repair, and guessing remain unsupported.

### AC-09 — Cross-process Preset persistence

After process restart, a successfully saved Preset retains its name, exact Profile binding, ordered expression collection, and exact expression text.

### AC-10 — Human selection

The user can select an existing Preset by its Human-readable name or current displayed sequence number without treating the sequence number as persisted identity.

### AC-11 — Unique display name

Two Presets cannot have the same trimmed exact display name; blank names are rejected.

### AC-12 — Immutable Criterion editing

Add/edit/delete Criterion operations use the existing R05 Draft and Human Save mechanism to create a new immutable formal Version; no formal Version is edited in place, and the Preset rebind requires separate Human preview/Save.

### AC-13 — Preset deletion isolation

Deleting a Preset removes no historical ScreeningProfileVersion and leaves no last-used pointer to the deleted Preset.

### AC-14 — Last-used Preset timing

The last-used Preset reference persists across restarts and changes only when a complete Run Summary is Human-confirmed for launch, not during browse/edit/save/cancel.

### AC-15 — Last-used action and side-effect suppression

The last confirmed Action Mode and `no_forward` state persist across restarts; Quick Start restores both and visibly distinguishes FORWARD-with-suppression from an authorized real forward.

### AC-16 — Last-used duration and batch state

The last confirmed duration and batch-filter enabled state persist across restarts without persisting or changing Calibration data; their existing Runtime meanings remain unchanged.

### AC-17 — Quick Start validation and reuse

Quick Start resolves the persisted last-used choices, validates the Preset/exact Profile/Rules/current Provider/current Run settings, and either presents that configuration for confirmation or fails closed to Configuration Mode without substitution or Legacy fallback.

### AC-18 — Complete Run Summary and identity

Before Runtime, the Summary displays the Human-facing Preset name and exact Profile Version without the internal Profile UUID, plus all other §19 fields. After confirmation, the same internally resolved exact Profile ID plus Version, immutable RuleSet, Provider/model, and Run choices continue without a second configuration lookup, then enter the unchanged existing Calibration flow and Runtime.

### AC-19 — Explicit action confirmation

The Summary explicitly shows `FAVORITE` or `FORWARD`, the effective `no_forward` state, and whether a real external action is authorized; only explicit Human confirmation starts Runtime.

### AC-20 — Legacy removed from normal startup

Normal Am7 interactive startup does not prompt for Legacy keywords; the Legacy subsystem and `--keywords` advanced compatibility remain intact and have no Am7 authority.

### AC-21 — One immutable Run-bound RuleSet

Each confirmed Run constructs/binds exactly one immutable R06 ScreeningRuleSet and reuses it for every Candidate without per-Candidate lookup or reconstruction.

### AC-22 — Accepted brain contracts unchanged

R05 Profile, R06 Rule Engine, R09 Candidate input, R10 Boolean contract, R11 runtime, R12 Candidate Decision/action authorization, and R13 retry/persistence/failure-degradation semantics remain unchanged.

### AC-23 — Calibration unchanged

The existing Calibration data, regions, preview, DPI, persistence, recalibration, prompts, mechanics, failures, and runtime sequence remain unchanged. Calibration is not part of R15 `ResolvedRunConfiguration`, Run Summary resolution, validation, or acceptance authority; after Human confirmation, the existing Calibration flow continues unchanged. The retained `batch_filter_enabled` switch persists no Calibration data.

### AC-24 — Advanced CLI compatibility

All eleven existing CLI arguments and their current advanced/non-interactive meanings remain compatible; no `--screening-preset` flag is required for R15 v1.

## 27. Regression Constraints

R15 design and later verification must protect:

- R05 immutable ScreeningProfileVersion semantics and Criterion ID lifecycle;
- R06 exact grammar, token boundaries, precedence, full validation, strict Boolean mapping, fixed ANY, and failure behavior;
- rule-neutral R07 Complete Scan and Candidate evidence behavior;
- R08 Candidate authority boundary;
- R09 exact Candidate input projection;
- R10 exact Boolean response contract and Prompt v1 identity;
- R11 single Candidate-level AI runtime semantics;
- R12 `qualified` / `rejected` / `ai_failed`, action authorization, and continuation;
- R13 retry count, diagnostic, durable persistence, ordering, and safe degradation;
- OCR acquisition, Dynamic End, retries, focus, Candidate finalization, Candidate switch, batch continuation, and stop reasons;
- favorite, forward, and `no_forward` mechanics;
- AI Provider configuration semantics and current config authority;
- all existing advanced CLI behavior;
- all existing Calibration behavior.

R15 verification must remain targeted to the startup/configuration change plus the accepted regression boundaries required to show no contract change. It must not become a platform-wide rewrite or new full-stack framework.

## 28. Explicit Non-Goals

R15 does not deliver:

- a GUI, web UI, database, server, or remote configuration service;
- a generic configuration/state/settings framework;
- Preset IDs, versions, digests, lifecycle states, publication, activation, inheritance, templates, tags, or access control;
- RuleSet IDs, versions, digests, or a RuleSet repository;
- a second Rule parser, evaluator, grammar, validation framework, or `NOT` operator;
- automatic Rule repair, Criterion guessing, Profile migration, or fallback;
- Screen-level evaluation or any change to Candidate decision scope;
- Profile criteria copied into Candidate or Preset-owned Profile truth;
- persistence of resolved Run Configuration, Run replay, cache, or recovery snapshots;
- persistence or redesign of Calibration data through last-used state;
- Provider discovery/config redesign, AI calls, prompt changes, retry changes, or AI result changes;
- Candidate scan, Candidate document, Candidate Decision, action, Candidate switch, or batch-control redesign;
- Legacy subsystem deletion or conversion into Am7 rules;
- a new `--screening-preset` CLI requirement;
- TID, implementation, tests, Acceptance Report, or release work in this RPD task.

## 29. Open Questions / Conflicts

### Open Product Questions

None.

The two Human-delegated v1 choices are resolved in this Draft:

- persist `last_no_forward` because silent re-enablement could change external side effects;
- persist `last_batch_filter_enabled` as an existing Run switch, while explicitly excluding all Calibration data/profile/region persistence;
- do not require `--screening-preset` because Preset is the normal interactive UX and the existing advanced CLI already has a complete compatible Run-input path.

### Contract Conflicts

None found.

The current code's `load_latest(...)` behavior is a targeted implementation gap, not a conflict with Frozen upstream contracts: R05 already supports exact version loading, and R12 already requires immutable Run-bound Profile/Rule authority. R15 freezes the product behavior that Preset resolution uses the exact saved Version.

### Baseline Note

The observed workspace remains on the R14 branch/HEAD listed in Metadata. No R15 branch expectation was supplied and no Git operation is authorized here; this is a repository-state note, not a product-contract blocker.

## 30. Final Scope Summary

AM7-R15 adds one Human-facing startup layer:

```text
persisted ScreeningPreset
    = Human-readable unique name
    + exact saved ScreeningProfileVersion reference
    + ordered formal R06 Rule expression(s)

last Human-confirmed Run choices
    = Preset
    + Action Mode
    + duration
    + no-forward state
    + batch-filter enabled state

pre-Run resolution
    → validate exact Profile / Rules / Provider / Run choices
    → display complete Run Summary
    → Human Confirm
    → existing Calibration flow unchanged
    → existing Runtime uses the same resolved R15 values
```

It removes Profile UUID entry, repeated formal Rule entry, and Legacy keyword prompting from normal Am7 startup. It preserves Advanced Profile Management, the full existing CLI surface, and the Legacy subsystem as advanced compatibility paths.

It does not alter the Ocria “brain”: immutable Profile semantics, R06 evaluation, Candidate-level AI, retries/persistence, Candidate Decision, qualified-only actions, OCR/scan/finalization/switching, duration, `no_forward`, batch filtering, and Calibration remain authoritative and unchanged.

Final document state for this turn:

- Version: 0.2
- Status: Draft — Pending Human Review
- Product Acceptance Criteria: 24
- Open Product Questions: None
- Contract Conflicts: None
- TID / implementation / tests: Not started
