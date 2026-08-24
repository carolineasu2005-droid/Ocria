# AM7-R15 — Run Configuration & Quick Start UX

## 1. Metadata

- Product: Ocria
- Generation: Am7
- Requirement: AM7-R15
- Requirement Name: Run Configuration & Quick Start UX
- Document Type: Acceptance Report / Automated Acceptance
- RPD: v0.2 Frozen (Human-declared authority)
- TID: v0.2 Frozen (Human-declared authority)
- Implementation Change: Change 1
- Implementation Changes: 1
- Branch: `am7-r14-final-integration-acceptance`
- HEAD: `0260f28 chore(am7-r14): prepare Am7 pre-release smoke candidate`
- Acceptance date: 2026-08-24 (Asia/Shanghai)

The physical RPD/TID metadata still says Draft. Per the Human instruction for this
acceptance, both v0.2 documents are treated as Frozen authorities; this report does
not alter their metadata or reopen their design.

## 2. Acceptance Status

**Automated Acceptance Passed / Pending Human Final Review**

Focused tests, targeted regressions, and compile passed. The historical one
permitted full-regression command result remains **FAIL — 1066 tests, 1
failure, 1 error**. A subsequent read-only baseline investigation reproduced
both Stage0 outcomes identically on pre-R15 HEAD `0260f...`; they are an
inherited Stage0 test-seam defect, not an R15 regression. The Frozen TID
requires recording one full-suite result but does not require a literal green
command regardless of a proven inherited baseline failure. Every automated R15
contract is therefore established as passed.

## 3. Governing Contracts

- `CODEX-CONSTITUTION.md`
- `docs/RPD-AM7-R15-run-configuration-quick-start.md` v0.2 Frozen
- `docs/TID-AM7-R15-run-configuration-quick-start.md` v0.2 Frozen

## 4. Repository and Diff Evidence

Pre-flight observations:

- Branch and HEAD match the R15 TID's observed baseline.
- `git diff --check` passed. Git reported only LF/CRLF warnings.
- `git diff --name-status` showed only the five tracked R15-authorized files:
  `README.md`, `screening_profile_cli.py`, `simple_brush.py`,
  `tests/test_screening_profile_cli.py`, and `tests/test_simple_brush_ocr.py`.
- The R15 production and focused-test modules are untracked working-tree files.
- The untracked RPD/TID files were already present before this acceptance turn as
  Human-supplied Frozen authorities; this turn did not modify them.

The pre-acceptance tracked diff was 439 insertions and 219 deletions across the
five authorized tracked files.

A later read-only Stage0 baseline comparison ran both affected selectors on an
archived pre-R15 HEAD with the same virtual environment and reproduced the same
outcomes. This reclassifies their attribution only; it does not alter the
historical full-regression result above.

## 5. Implementation Scope Review

Expected implementation files and inspected actual files match:

| Category | Files | Result |
|---|---|---|
| New production | `screening_preset.py`, `run_configuration.py`, `screening_preset_cli.py` | PASS |
| Modified production/docs | `simple_brush.py`, `screening_profile_cli.py`, `README.md` | PASS |
| New tests | `tests/test_screening_preset.py`, `tests/test_run_configuration.py`, `tests/test_am7_r15_startup.py` | PASS |
| Modified tests | `tests/test_simple_brush_ocr.py`, `tests/test_screening_profile_cli.py` | PASS |
| Requirements/build/packaging/release | No implementation diff | PASS |
| Frozen RPD/TID semantic changes | None | PASS |

No unexpected production or test file was found. No new capability beyond the R15
Preset, resolution, Summary, and startup layer was identified.

## 6. Implemented Functionality Summary

The implementation adds a dedicated one-file Preset/last-used store, pure exact
Profile/Rule/Provider resolution, a UUID-free Summary, normal Quick Start and
Preset management menus, and a resolved-value handoff into `run()`. Advanced and
non-interactive paths retain their existing Profile/Rule setup route.

## 7. ScreeningPreset and Last-used Acceptance

Inspection confirms that `ScreeningPreset` is frozen and has exactly
`preset_name`, `screening_profile_id`, `profile_version`, and
`screening_rule_expressions`. Its name is trimmed once; blank names, invalid
versions, and invalid expression tuple shapes are rejected without parsing or
rewriting raw expressions.

`LastUsedRunSettings` is frozen and has exactly the five Frozen-TID fields. It
allows `0` as Unlimited, accepts only `favorite`/`forward`, and requires exact
Boolean flags. It contains no Provider, Calibration, email, Legacy, Profile-copy,
or RuleSet fields. Focused store tests cover canonical persistence, duplicate and
blank rejection, rename/delete consistency, dangling references, malformed
last-used isolation, and atomic-replace failure preservation.

## 8. Persistence Acceptance

`ScreeningPresetStore` uses only `data/screening_presets.json`, with exactly
`presets` and `last_used_run_settings` root keys. Inspection confirms UTF-8,
`ensure_ascii=False`, deterministic name order, two-space JSON, one trailing
newline, same-directory temporary files, and `os.replace()`.

Preset collection validation and last-used validation are independent. A malformed
collection exposes no partial Preset list; malformed last-used data remains opaque
to Preset mutations and does not hide a healthy library. A structurally valid
dangling last-used name is returned as data and rejected only by resolution. There
is no database, migration, lock, cache, or generic settings framework.

## 9. Rule and Exact ProfileVersion Acceptance

ALL and ANY derive exact `AND`/`OR` expressions in Profile criterion order.
Custom expressions are retained raw. `build_screening_rule_set()` creates the
existing R06 `ScreeningRule` and `ScreeningRuleSet` types only.

`validate_preset_definition()` uses `ScreeningProfileStore.load_version()` with
the saved ID/version and validates through `evaluate_rule_set()` with a complete
false Boolean mapping. It has no `load_latest()` call. Focused test evidence proves
a Preset bound to v1 remains v1 after v2 exists and asserts that `load_latest()` is
not used for Preset resolution.

## 10. Provider and ResolvedRunConfiguration Acceptance

Resolution calls the existing Provider store once, accepts only `VALID` plus a
non-`None` configuration, and carries that same configuration object forward. It
does not recreate Provider completeness validation.

`ResolvedRunConfiguration` is a frozen, non-persistent, eight-field run-local
carrier. Its summary renderer accepts only that value, performs no store/disk
read, shows no Profile UUID/API key/Calibration/email/Legacy data, and derives its
ALL/ANY/CUSTOM display from the carried rule expressions.

## 11. Quick Start, Summary, and Handoff Acceptance

The inspected normal menu exactly contains Quick Start, Choose ScreeningPreset and
Run, ScreeningPreset Management, Provider, Calibration, Advanced, and Exit. The
Advanced submenu preserves Existing manual Am7 Run and Advanced
ScreeningProfile Management.

Quick Start resolves last-used settings, applies existing `--no-forward` and
`--no-batch-filter` forcing, displays the pure Summary, and requires Confirm,
Edit, or Cancel. Confirm writes last-used immediately before the handoff; expected
last-used I/O failure warns and still invokes the confirmed handoff. Edit resolves
again and Cancel writes nothing.

The resolved `run()` path rejects mixed/direct incomplete modes before state reset,
uses the exact carried Profile/RuleSet/Provider/settings objects, clears Legacy
runtime state, and does not call Profile or Provider stores. The advanced branch
retains one `load_latest()` and Provider load. Focused identity tests verify the
same configuration values reach the handoff with no resolved-path stores.

## 12. Legacy, Calibration, Advanced CLI, and README Review

Normal Preset paths do not call the Legacy input path; the resolved run setup sets
Legacy forwarding state empty. Advanced/manual and non-interactive paths retain
`--keywords` and the existing parser. There is no `--screening-preset` option.

Resolver, persistence, models, and Summary do not import or invoke Calibration.
The post-confirm helper routes existing email/Calibration preparation without
modifying physical Calibration function bodies or ordering. `batch_filter_enabled`
is carried only as a Boolean intent.

README changes accurately describe the seven-item menu, Preset persistence path,
exact-version binding, ALL/ANY/Custom, confirmation timing, UUID-free Summary,
post-confirm Calibration, Advanced/Legacy boundary, all eleven existing CLI
arguments, and the absence of `--screening-preset`. It makes no acceptance,
release, or production-ready claim.

## 13. simple_brush Protected Runtime Review

**PASS — R15 protected runtime preserved**

The actual diff inspection found changes only in R15 imports, compatibility
wrappers, normal menu dispatch, reusable post-confirm input extraction, and the
resolved-vs-advanced `run()` setup branch. It did not alter OCR initialization,
Complete Scan, candidate recording/finalization, R13 persistence/retry,
CandidateDecision/action bodies, favorite/forward mechanics, candidate switching,
batch loop, refresh, pause/resume, ESC, timer, or physical Calibration function
bodies.

Targeted protected regression passed. The historical full suite observed two
Stage0 integration outcomes; a subsequent read-only pre-R15 baseline comparison
reproduced both identically. The test-side `view_candidate` callback accepts only
a positional argument while unchanged production calls
`view_candidate(i, first_observation=...)`; the mock raises `TypeError` before
the test body, the Run failure path finalizes `ABORTED`, and the first test's
expected fact lookup then raises `KeyError`. These outcomes do not establish an
R15 runtime change. They do establish that the repository full suite is not
globally healthy because of a separate inherited Stage0 test-seam defect.

## 14. Formal Verification Results

| Gate | Command | Result |
|---|---|---|
| Focused | `python -m unittest tests.test_screening_preset tests.test_run_configuration tests.test_am7_r15_startup -v` | PASS — 22 run, 0 failures, 0 errors, 0 skips |
| Targeted regression | `python -m unittest tests.test_screening_profile tests.test_screening_profile_cli tests.test_screening_rule_engine tests.test_ai_provider_config tests.test_ai_provider_cli tests.test_candidate_decision_integration tests.test_simple_brush_ocr -v` | PASS — 390 run, 0 failures, 0 errors, 0 skips |
| Compile | `python -m compileall screening_preset.py run_configuration.py screening_preset_cli.py screening_profile_cli.py simple_brush.py tests/test_screening_preset.py tests/test_run_configuration.py tests/test_am7_r15_startup.py` | PASS — exit 0 |
| Full regression (run once) | `python -m unittest discover -s tests -v` | FAIL — 1066 tests, 1 failure, 1 error |

Full-regression evidence:

1. Error: `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_normal_run_keeps_one_builder_and_sequence_for_one_candidate` — `KeyError: 'saved_before_view_completed'` at line 1657.
2. Failure: `test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_disabled_initial_store_stops_before_listener_browser_or_view` — expected `CaptureStatus.COMPLETED`, observed `CaptureStatus.ABORTED` at line 1687.

These results are recorded as observed. They were not repaired, suppressed, or
re-run. Subsequent read-only baseline investigation reproduced both affected
tests individually and in their Stage0 module, with identical outcomes on
pre-R15 HEAD using the same virtual environment. The cause is an inherited
test-seam incompatibility: its mocked callback does not accept the keyword
argument used by unchanged production code. This is not an R15-caused failure.

## 15. J01–J22 Journey Matrix

| Journey | Evidence | Result |
|---|---|---|
| J01 Preset create + persistence | `test_create_persists_canonical_preset_in_strict_json` | PASS |
| J02 blank/duplicate | `test_blank_duplicate_and_invalid_model_shapes_are_rejected` | PASS |
| J03 ALL | `test_all_and_any_preserve_profile_criterion_order` | PASS |
| J04 ANY | Same deterministic helper test and renderer inspection | PASS |
| J05 Custom | `test_custom_rule_is_preserved_and_invalid_rule_fails_closed` | PASS |
| J06 exact ProfileVersion | `test_preset_resolution_uses_exact_version_without_load_latest` | PASS |
| J07 Criterion edit/rebind | Draft-helper tests plus explicit-rebind flow inspection | PASS |
| J08 Profile save / Preset-write failure | Draft-helper save test and atomic-replace preservation test | PASS |
| J09 Rename + last-used | `test_rename_updates_last_used_in_the_same_state_write` | PASS |
| J10 Delete last-used | `test_delete_last_used_preset_clears_only_last_used_reference` | PASS |
| J11 last-used timing | Confirm/cancel/edit/I-O-failure startup tests | PASS |
| J12 Quick Start success | `test_quick_start_confirm_writes_once_before_same_value_handoff` | PASS |
| J13 dangling/malformed state | Store and Quick-Start healthy-library tests | PASS |
| J14 invalid exact Profile | Exact `load_version()` fail-closed resolver inspection | PASS |
| J15 invalid Rule | Custom-invalid-rule focused test | PASS |
| J16 Provider invalid | Provider classification/IO focused test | PASS |
| J17 no_forward | Safety forcing and suppressed-forward Summary test | PASS |
| J18 UUID-free Summary | Pure Summary focused test | PASS |
| J19 Calibration untouched | Resolver/Summary inspection plus targeted Calibration regressions | PASS |
| J20 normal Legacy removal | Resolved-path inspection plus Advanced/Legacy targeted regression | PASS |
| J21 Advanced CLI compatibility | Targeted `test_simple_brush_ocr` startup/CLI regressions | PASS |
| J22 one Run-bound RuleSet | Resolved-handoff identity focused test and targeted Candidate integration | PASS |

**Journey result: 22 / 22 PASS.**

## 16. R01–R36 Technical Responsibility Matrix

| ID | Evidence | Result |
|---|---|---|
| R01–R04 | Frozen value types and exact fields inspected; model tests | PASS |
| R05–R07 | Strict two-key JSON, partitioned loader, atomic writer tests | PASS |
| R08–R11 | Management/Human Save, rename/delete, Confirm timing tests | PASS |
| R12–R14 | ALL/ANY helpers and R06 construction/evaluation inspection/tests | PASS |
| R15–R17 | Exact Profile resolver, Provider-once validation, fail-closed tests | PASS |
| R18–R20 | Pure UUID-free Summary and Confirm/Edit/Cancel tests | PASS |
| R21–R24 | Frozen menus, selection, CRUD/details inspections/tests | PASS |
| R25–R26 | Additive latest-only Draft helper and explicit rebind inspection/tests | PASS |
| R27–R30 | Exclusive run modes, same-value handoff, advanced/Legacy regressions | PASS |
| R31–R33 | Post-confirm Calibration boundary and Action/no-forward settings review | PASS |
| R34 | Protected-body diff inspection; targeted regression | PASS |
| R35 | README review against implemented behavior | PASS |
| R36 | Focused tests use local temporary state/mocks; no real external action | PASS |

**Responsibility result: 36 / 36 PASS.**

## 17. AC-01–AC-24 Product Acceptance Matrix

| AC | Evidence | Result |
|---|---|---|
| AC-01 | Preset create/Human Save focused test | PASS |
| AC-02 | Exact-v1-after-v2 test; no `load_latest()` resolution | PASS |
| AC-03 | Strict raw-expression persistence and R06 validation | PASS |
| AC-04 | UUID-free normal Summary/menu inspection and test | PASS |
| AC-05 | C00x-only R06 helper construction | PASS |
| AC-06 | ALL exact-order test | PASS |
| AC-07 | ANY exact-order test | PASS |
| AC-08 | Custom preservation and invalid-rule failure test | PASS |
| AC-09 | Reloadable strict JSON test | PASS |
| AC-10 | Name/sequence selector and normal menu inspection/tests | PASS |
| AC-11 | Trimmed blank/duplicate test | PASS |
| AC-12 | Immutable Draft helper/latest-only/rebind review | PASS |
| AC-13 | Delete clears only Preset last-used reference test | PASS |
| AC-14 | Confirm-only last-used timing tests | PASS |
| AC-15 | Forward suppression restoration/Summary test | PASS |
| AC-16 | Duration/batch carrier and Summary tests | PASS |
| AC-17 | Quick Start malformed/dangling/provider fail-closed tests | PASS |
| AC-18 | Pure Summary and same-value handoff identity test | PASS |
| AC-19 | Explicit action/suppression Summary and Confirm gate | PASS |
| AC-20 | Normal resolved path bypasses Legacy; advanced regression retained | PASS |
| AC-21 | One carried RuleSet identity test | PASS |
| AC-22 | Protected runtime diffs and focused/targeted regressions pass; read-only pre-R15 baseline reproduces both Stage0 outcomes identically | PASS |
| AC-23 | Calibration-free R15 models/resolver/Summary and targeted regressions | PASS |
| AC-24 | Eleven-argument advanced/non-interactive targeted regressions; no new flag | PASS |

**AC result: 24 / 24 PASS.**

## 18. Protected Runtime Review

Protected files with no R15 implementation diff: `screening_profile.py`,
`screening_rule_engine.py`, `ai_provider_config.py`, `ai_provider_cli.py`,
`llm_provider_runtime.py`, `ai_candidate_input.py`, `ai_screening_prompt.py`,
`ai_screening_contract.py`, `ai_screening_runtime.py`,
`ai_screening_persistence.py`, `candidate_decision.py`, `ocr_detector.py`, OCR /
Candidate / store modules, Calibration modules, browser/mouse modules, and
requirements/build/release files.

Diff inspection establishes no protected-file modification. Targeted regressions
cover R05, R06, Provider, CandidateDecision/action, action/no-forward, Calibration,
and startup boundaries. The historical full-suite outcomes are preserved as
observed. Read-only baseline investigation establishes that both occurred
identically on pre-R15 HEAD because of a Stage0 test-seam defect. R15 protected
runtime behavior is therefore preserved. The inherited defect remains outside
R15 and prevents any claim that the repository full suite is globally healthy.

## 19. Deviations, Open Issues, and Contract Conflicts

### Deviations from Frozen TID

None.

### Open Issues

None for AM7-R15.

### Inherited Baseline Defect (outside AM7-R15)

The two Stage0 outcomes are caused by a test mock whose `view_candidate`
callback accepts only a positional argument, while unchanged production invokes
it with `first_observation=...`. This predates R15 and requires a separately
authorized baseline corrective test change. No R15 production correction is
indicated, and none was made in this acceptance update.

### Contract Conflicts

None.

## 20. Human Review Pending Items

- Human final review may review Quick Start UX, Preset selection, Summary, and
  normal Legacy-prompt removal.
- Address the inherited Stage0 test-seam defect separately before claiming that
  the repository full suite is globally healthy.

## 21. Final Automated Acceptance Conclusion

Implementation scope, focused verification, targeted regression, compile, the
Journey matrix, the Responsibility matrix, and README consistency passed. The
historical one permitted full-suite result is recorded as FAIL — 1066 tests, 1
failure, 1 error. Read-only pre-R15 baseline evidence establishes both affected
Stage0 outcomes as inherited test-seam defects rather than R15 regressions. The
Frozen contracts require recording that result, not a literal global green suite
overriding proven inherited attribution.

**Formal status: Automated Acceptance Passed / Pending Human Final Review.**

Human Final Review has not been performed. This report does not claim Human
Acceptance, merge, release, or production readiness.
