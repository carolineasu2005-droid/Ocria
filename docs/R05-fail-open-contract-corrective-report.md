# R05 Fail-open Contract Corrective Change Report

## 1. Overall result

Result: **passed for this corrective change**.  The four specified fail-open
contract defects are corrected and the requested automated, benchmark, schema,
and isolation checks passed.  This is not an R05 Change 7 acceptance report and
does not claim that Change 7 has passed.

The work was performed on `main` at `cd5d96c731caed07f7b841c437b2ee9f5086ffd0`.
The pre-existing dirty worktree from prior R05 changes and the prior performance
corrective was retained; no reset, checkout, staging, commit, push, tag, or
release action was performed.

Frozen R05 identity remains unchanged:

- aggregation version: `r05-v1`
- config version: `r05-config-v1`
- config digest: `047ec8c40aab9b28ed3a7a6a63695f416677e1a73c25f3c398d77eca3b31ff7a`
- storage schema writer: `1.2.0`

## 2. Reproduced defects and corrective result

### 2.1 Stale R04 schema assertion

The obsolete normalization test asserted the pre-R05 writer schema `1.1.0`.
It now asserts `1.2.0`, preserves the existing R03/R04 raw and normalization
assertions, and explicitly restores the same payload through both the `1.0.0`
and `1.1.0` readers.  The test also verifies that restoring those payloads does
not infer R05 aggregation or R06/R07 fields.

### 2.2 Valid 257+ segment screen

`CandidateDocumentAggregator` now validates an over-limit screen's existing
R04 segment shape and provenance without re-applying the matching limit.  When
the valid segment count is greater than `max_screen_segments`, it:

- does not invoke exact, fuzzy, or historical matching;
- appends every segment as an `uncertain_origin` document occurrence;
- returns screen aggregation `partial` with
  `screen_segment_limit_exceeded`;
- retains the document text and document segment count;
- yields candidate document status `partial` and duplicate risk `elevated`.

The R04 adapter's normal public limit enforcement is unchanged for its normal
callers.  The explicit internal validation path is used only for this
fail-open aggregation path, so structural invalidity still remains controlled
failure rather than being misclassified as a valid limit excess.

Tests cover 255, 256, 257, and 300 valid segments.  The 257 benchmark contract
scenario reported `exact_calls = fuzzy_calls = historical_calls = 0`, 257
uncertain segments, preserved 257 document segments, `partial`, and
`elevated`.

### 2.3 Tolerant candidate aggregation replay

`replay_candidate_aggregation(strict=False)` now reconstructs malformed formal
candidate membership from the immutable candidate member list.  Formal members
are processed by the stable key `(screen_index, original_position)`; duplicate
screen IDs, duplicate formal indexes, and input out-of-order membership each
receive their fixed sanitized issue code and are retained conservatively as
uncertain content.  The rebuilt candidate is `partial` with `elevated` risk.

`strict=True` remains strict and raises the existing sanitized replay error for
these malformed formal-member cases.  Tolerant replay neither writes JSONL nor
mutates the source candidate or source screen records.  Coverage includes
duplicate index, conflicting same ID, out-of-order input, and identical
duplicate membership while the run-level screen source is empty.

The minimal R05 model validation adjustment in `ocr_records.py` was necessary:
source occurrence validation now resolves source records by
`(screen_id, screen_index)`, rather than allowing a duplicate screen ID to
overwrite a different source position in a dictionary.  This preserves source
identity for conflict-retained document occurrences without changing schema,
writer version, or R03/R04 normalization behavior.

### 2.4 Matching-stage exceptions

After valid R04 adaptation, stage exceptions are fail-open and terminal for
the affected remainder:

- exact exception: all current segments are appended uncertain with
  `exact_stage_failed`; fuzzy and historical are not called;
- fuzzy exception: the unmatched remainder is appended uncertain with
  `fuzzy_stage_failed`; historical is not called;
- historical exception: already accepted earlier match evidence remains, and
  the remaining current segments are appended uncertain with
  `historical_stage_failed`.

The regression tests inject exceptions in the aggregator's validated internal
stage cores (the performance-corrected execution path) and assert both the
warning and that later stages were not entered.

## 3. Scope and unchanged contracts

Changed in this corrective change:

- `ocr_aggregation.py`
- `ocr_replay.py`
- `ocr_records.py` (minimal source identity validation correction)
- `tests/test_ocr_aggregation.py`
- `tests/test_ocr_replay.py`
- `tests/test_ocr_normalization.py`
- this report

No config value, threshold, window, evidence type, occurrence type, default
disabled mode, schema writer version, R03/R04 normalizer, OCR engine, page
action, Store behavior, or benchmark implementation was changed by this
corrective change.  No AI payload/interface, R06 similarity, R07 dynamic end,
new OCR, screenshot, wait, scroll, click, network, or real BOSS page action
was added or executed.

## 4. Validation

Executed successfully:

```text
.\venv\Scripts\python.exe -m unittest tests.test_ocr_aggregation tests.test_ocr_records tests.test_ocr_candidate tests.test_ocr_replay tests.test_ocr_store tests.test_ocr_normalization tests.test_ocr_detector tests.test_ocr_text tests.test_ocr_stage0_integration tests.test_simple_brush_ocr -v
# 583 tests

.\venv\Scripts\python.exe -m unittest discover -s tests -v
# 649 tests

.\venv\Scripts\python.exe -m tests.benchmark_r05_aggregation
.\venv\Scripts\python.exe -m tests.benchmark_r04_normalization
.\venv\Scripts\python.exe -m compileall -q ocr_aggregation.py ocr_records.py ocr_candidate.py ocr_store.py ocr_replay.py ocr_normalization.py ocr_detector.py ocr_text.py simple_brush.py tests
.\venv\Scripts\python.exe -m pip check
git diff --check
```

`pip check` reported no broken requirements and `git diff --check` passed.

## 5. Performance and determinism

The fixed-seed fair R05 benchmark completed with all required performance gates
passing and `determinism_100 = true`:

| scenario | p95 | gate | peak memory |
| --- | ---: | ---: | ---: |
| 8 x 64 pure aggregate + finalize | 16.42 ms | <= 20 ms | 709.47 KiB |
| 8 x 256 pure aggregate + finalize | 56.93 ms | <= 150 ms | 2717.53 KiB |
| 8 x 64 record projection + finalize | 22.14 ms | <= 30 ms | 759.75 KiB |
| single-screen fuzzy 1->1 | 0.58 ms | <= 50 ms | 44.80 KiB |
| single-screen fuzzy 1->2 | 0.61 ms | <= 50 ms | 51.00 KiB |
| single-screen fuzzy 2->1 | 0.55 ms | <= 50 ms | 51.87 KiB |
| 257 limit fail-open | 4.65 ms | contract-only | 261.12 KiB |

The benchmark reports `required_performance_gates_pass = true`, no contract
blockers, and uses separated timing/tracemalloc with warm-up and 25 timed
iterations.  The R04 normalization benchmark also completed with deterministic
results.

## 6. Privacy, source immutability, and isolation

Before and after the test and benchmark runs, `logs/simple_brush.log` had the
same size (7,372,745 bytes), UTC mtime
`2026-08-01T07:15:54.4076423Z`, and SHA-256
`1BE253B07B246AA1B9F3F207F5C22876FA8116A13DA13959221ECCC2AC62AF96`.

`data/ocr_runs` contained five zero-byte directory entries and no tracked
`data/ocr_runs` or `logs` files.  The replay tests use temporary run locations,
assert source JSON serialization before and after replay, and do not persist
their synthetic candidate text.  Static review of the corrective production
scope found no AI payload, SimHash, SQLite, qualification, rejection, or manual
review implementation.

## 7. Remaining boundary and disposition

This change stops here.  It does not supersede the existing R05 performance or
acceptance reports, and it does not mark Change 7 as passed.  No real Windows
shadow, production-record default mode, formal production validation, or real
page run was performed.  Default mode remains disabled.

Suggested next action: have the maintainer review this corrective report and
the updated fail-open tests before deciding whether to resume the separately
scoped acceptance work.
