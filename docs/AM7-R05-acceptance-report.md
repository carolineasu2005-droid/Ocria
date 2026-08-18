# AM7-R05 Acceptance Report

## 1. Requirement

AM7-R05 — ScreeningProfile Dynamic Screening Criteria.

**Status:** Automated Acceptance Passed / Pending Human Final Review

## 2. Frozen Sources

- `docs/RPD-AM7-R05-screening-profile.md` v0.2 Frozen
- `docs/TID-AM7-R05-screening-profile.md` v0.1 Frozen for Implementation

## 3. Final Functionality Implemented

- Immutable Criterion and ScreeningProfile Version models, deterministic
  criterion IDs, canonical SHA-256 criteria digests, and atomic local version
  persistence.
- Configuration-only ScreeningProfile CLI with latest-only editing, in-memory
  Drafts, Human Save, and explicit Prepare.
- Optional legacy-compatible RunManifest binding containing only Profile ID,
  version, and digest; bound manifests preserve the tuple on close.
- Startup Profile configuration, process-local prepared ID, noninteractive
  `--screening-profile-id`, mandatory latest/digest freeze before execution,
  and initial Store failure refusal before OCR/listener/browser work.

## 4. Final File Scope

### New implementation and tests

- `screening_profile.py`
- `screening_profile_cli.py`
- `tests/test_screening_profile.py`
- `tests/test_screening_profile_cli.py`

### Modified implementation and tests

- `.gitignore`
- `ocr_records.py`
- `ocr_store.py`
- `simple_brush.py`
- `tests/test_ocr_records.py`
- `tests/test_ocr_store.py`
- `tests/test_ocr_replay.py`
- `tests/test_ocr_stage0_integration.py`
- `tests/test_simple_brush_ocr.py`

### Approved documentation

- `docs/RPD-AM7-R05-screening-profile.md`
- `docs/TID-AM7-R05-screening-profile.md`
- `docs/AM7-R05-acceptance-report.md`

Protected production files listed by the Frozen TID were absent from the R05
implementation diff.

## 5. Targeted Verification Commands

```powershell
git check-ignore -v --no-index data/screening_profiles/sp_00000000000000000000000000000000/versions/1.json
.\venv\Scripts\python.exe -m unittest tests.test_screening_profile tests.test_screening_profile_cli -v
.\venv\Scripts\python.exe -m unittest tests.test_ocr_records tests.test_ocr_store tests.test_ocr_replay -v
.\venv\Scripts\python.exe -m unittest tests.test_ocr_stage0_integration tests.test_simple_brush_ocr -v
.\venv\Scripts\python.exe -m compileall screening_profile.py screening_profile_cli.py ocr_records.py ocr_store.py simple_brush.py
```

## 6. Exact Verification Results

| Verification | Result |
|---|---|
| Git local Profile-data ignore | Passed: `.gitignore:14:/data/screening_profiles/` matched the requested formal Version path. |
| Profile model and CLI tests | Passed: 21 tests. |
| Records, Store, and Replay tests | Passed: 96 tests. |
| Stage-0 and startup/OCR tests | Passed: 305 tests. |
| Compile | Passed: all five specified Python modules compiled successfully. |

## 7. AC-01 through AC-20 Mapping

| AC | Result | Supporting evidence |
|---|---|---|
| AC-01 | Passed | Formal model, Save, reload, and serialization lifecycle tests passed. |
| AC-02 | Passed | `Criterion` is frozen and has ID, text, and `must_match` rule only. |
| AC-03 | Passed | Criterion text is stored verbatim; no evaluator exists. |
| AC-04 | Passed | No expression, score, weight, priority, or condition-tree fields or APIs are present. |
| AC-05 | Passed | C001/C1000, edit stability, deleted-formal, and abandoned-Draft ID tests passed. |
| AC-06 | Passed | New v1 and latest-only v1-to-v2 progression tests passed. |
| AC-07 | Passed | Drafts are in-memory and Save/no-op/error lifecycle tests passed. |
| AC-08 | Passed | Formal dataclasses are immutable; edit API is `create_draft_from_latest()` and stale-base save is rejected. |
| AC-09 | Passed | Deterministic canonical digest, rule fixture, Unicode, whitespace, and change-sensitivity tests passed. |
| AC-10 | Passed | Atomic failure/reload tests passed and formal data path is ignored by the repository rule. |
| AC-11 | Passed | Prepare returns ID; Run loads latest Profile and validates digest before execution. |
| AC-12 | Passed | Bound Store constructor writes the binding in initial `run.json` before OCR/listener/browser startup. |
| AC-13 | Passed | One immutable binding is created once per Run and preserved on close. |
| AC-14 | Passed | Binding contains exactly ID, version, and digest; no full Profile Snapshot is written. |
| AC-15 | Passed | Candidate serialization tests confirm no Profile business fields. |
| AC-16 | Passed | Configuration is dispatched only by startup menu; execution tests assert it is not called. |
| AC-17 | Passed | Pause toggle does not enter configuration; terminal Run followed by a new `main()` exposes configuration. No resume subsystem was added. |
| AC-18 | Passed | Missing/invalid/digest-mismatched Profile and None/disabled initial Store tests stop before OCR, listener, browser, or view work. |
| AC-19 | Passed | Legacy manifest reads as unbound (`None`) without source mutation or backfill. |
| AC-20 | Passed | Profile CLI no-call tests cover LLM/Candidate/page-action isolation; no Criterion evaluation or Candidate Decision was added. |

## 8. Compatibility Result

- Legacy unbound `run.json` remains readable with
  `screening_profile_binding=None` and is not backfilled.
- Candidate schema remains isolated from Profile business fields.
- Existing OCR, candidate, favorite, forward, pause, and terminal action
  behavior remained outside the R05 implementation diff; targeted regression
  tests passed.

## 9. Scope Review

The worktree matched the Frozen R05 file-scope matrix. The implementation
diff contained the approved new and modified files only; approved R05 design
documents and this acceptance artifact are documentation additions. No
protected production file appeared in the implementation diff.

## 10. Remaining Warnings or Limitations

- `git check-ignore` emitted an environment warning that the user-global Git
  ignore file could not be accessed. The command exited successfully and
  explicitly matched the repository `.gitignore` rule, so this is not an R05
  product failure.
- This acceptance report exists at the requested path but is matched by the
  existing `.gitignore` `*.md` rule and therefore does not appear in normal
  `git status` output. Per the acceptance instruction, `.gitignore` was not
  changed; any tracking decision requires Human handling.
- R05 deliberately provides no Criterion evaluator, LLM screening, Candidate
  Decision, Profile state machine, or resume subsystem.

## 11. Open Issues

None.

## 12. Contract Conflicts

None.
