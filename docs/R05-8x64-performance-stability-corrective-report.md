# R05 8x64 Performance Stability Corrective

## 1. Result and scope

Result: **PASS for this narrowly scoped corrective.**  This is not an R05
Change 7 final acceptance and does not change the existing final acceptance
report from BLOCKED to PASS.

The historical trigger was the independent final-acceptance run:

```text
8x64_unique_pure p95 = 20.2872 ms
gate = 20 ms
```

Only the R05 adapter hot path and its focused regression test changed.  No
threshold, fixture scale/content, business classification, exact/fuzzy/
historical rule, config, digest, Schema, record field, Replay, Store, page
flow, dependency, R06 code, or default mode changed.

## 2. Git baseline and isolation gate

- Branch/HEAD: `main` / `aaa5e69a039cc64c2e4ed4c29d74742f284f5a4f`.
- R05 implementation baseline: `f02209c`; R06 is separately committed at
  `0e0deca`.
- The pre-existing tracked change to
  `docs/R05-ocr-multiscreen-incremental-aggregation-acceptance-report.md`
  is the prior independent BLOCKED report and was preserved unchanged here.
- This corrective changed only `ocr_aggregation.py`,
  `tests/test_ocr_aggregation.py`, and this report.  Pre-existing untracked
  `README.md`, `docs/project-review.zip`, and
  `venv-packages-before-reinstall.txt` were untouched; the latter two were not
  read.
- No reset, clean, restore, checkout, staging, commit, push, tag, or release
  was performed.  `git diff --check` passes.

## 3. Pre-change five-run reproduction

The official command was executed five times continuously before any source
change.  Full JSON from every run was retained in the system temporary
directory (`bossocr-r05-pre-stability/pre-1.json` through `pre-5.json`), not
in the repository or governed run-data location.

```powershell
.\venv\Scripts\python.exe -m tests.benchmark_r05_aggregation
```

| Run | 8x64 p50 ms | 8x64 p95 ms | 8x256 p95 ms | Record p95 ms | Required gates |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 15.8189 | 16.8981 | 61.1351 | 23.9500 | true |
| 2 | 15.3424 | 16.3242 | 56.7535 | 22.8263 | true |
| 3 | 15.2733 | 16.4369 | 55.4275 | 21.7767 | true |
| 4 | 15.6485 | 16.4339 | 58.7788 | 21.2389 | true |
| 5 | 16.1000 | 17.1028 | 58.0468 | 24.3974 | true |

Every pre-change result also had `contract_blockers=[]`,
`determinism_100=true`, `reference_release_100_full_candidates=true`,
`disabled_does_not_construct_aggregator=true`, and
`fair_record_semantics_equal=true`.  This does not discard or negate the
historical 20.2872 ms failure; it demonstrates why a stability corrective must
retain every formal result rather than selecting only failures or passes.

## 4. Pre-change profile and root cause

`cProfile` of 25 pre-change 8x64 pure candidate runs recorded 9,954,006 calls
in 2.128 seconds under profiler instrumentation.  The dominant relevant path
was adapter validation: `adapt_r04_screen_segments` cumulative 0.632 s,
`_validate_r04_segment` 0.626 s, `build_comparison_text` 0.600 s, and the
redundant whitespace `any(...isspace())` work 0.667 s across the profiled
call tree.

The adapter first requires exact equality with
`build_comparison_text(normalized_text)`.  That deterministic builder removes
all Unicode whitespace.  The following second per-character whitespace scan
therefore proved no additional property and was avoidable work on every
accepted segment.  The profile identifies this redundant scan as a concrete
tail-latency contributor; it does not claim that a single scheduler-sensitive
20.2872 ms sample has a uniquely provable process-level cause.

## 5. Change

`ocr_aggregation._validate_r04_segment` now relies on the existing exact
derived-value comparison for the whitespace invariant and retains the explicit
non-empty check.  It still validates record type/status, screen ID/index,
segment ID/order, normalized/comparison text equality, box membership, and
source order.  No validation domain was removed.

`tests/test_ocr_aggregation.py` adds a forged comparison value with a trailing
space to the existing invalid-adapter matrix.  It remains rejected, proving
the derived-value equality continues to enforce the whitespace contract.

The optimization is candidate-local computation only: no cache, mutable
global state, cross-candidate reuse, changed ordering, or changed object field
is introduced.

## 6. Semantic equivalence

Before/after complete `ScreenAggregationResult` and
`CandidateAggregationResult` representations were SHA-256 compared per
scenario, including screen status, matched/new/uncertain IDs, match evidence,
document segments/text, source occurrences, warnings, duplicate risk, final
status, and config identity.  The 18 benchmark scenarios were all identical
(`18/18`, no differing scenario):

```text
8x64 unique; 8x256 unique; exact; historical exact; fuzzy 1->1;
fuzzy 1->2; fuzzy 2->1; uncertain; 257 fail-open; and all other catalog cases.
```

The target regression suite additionally passes injected exact, fuzzy, and
historical stage-exception fail-open tests, plus 257/300 segment-limit tests.
Those assertions verify the affected remainder, warnings, preserved evidence,
and skipped later stages.  No synthetic body text was printed or persisted.

## 7. Post-change five-run stability evidence

The same full command was executed five times continuously after the change.
Full JSON is retained as `post-1.json` through `post-5.json` in the same
system temporary directory; no run was omitted.

| Run | 8x64 p50 ms | 8x64 p95 ms | 8x256 p95 ms | Record p95 ms | Fuzzy max p95 ms | Required gates |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 15.5908 | 17.2497 | 56.2359 | 23.7404 | 0.8204 | true |
| 2 | 16.2788 | 18.0208 | 56.0067 | 22.4242 | 0.6230 | true |
| 3 | 15.6938 | 17.5636 | 56.6739 | 21.8857 | 0.7863 | true |
| 4 | 15.8842 | 17.6605 | 57.2971 | 23.1870 | 0.6745 | true |
| 5 | 15.4270 | 16.9534 | 56.9383 | 22.6410 | 0.8062 | true |

All five runs satisfy the required limits: 8x64 <= 20 ms, 8x256 <= 150 ms,
record projection/finalize <= 30 ms, and each listed fuzzy shape <= 50 ms.
Each has `contract_blockers=[]`, `determinism_100=true`,
`reference_release_100_full_candidates=true`,
`disabled_does_not_construct_aggregator=true`, and
`fair_record_semantics_equal=true`.  The largest measured peak is 2717.53 KiB,
well below 32 MiB.  Candidate reference-release and retained-memory checks
remain successful.

## 8. Regression and isolation

| Check | Result |
| --- | --- |
| `unittest test_ocr_aggregation test_ocr_candidate test_ocr_records test_ocr_replay -v` | 108 tests, OK |
| `unittest discover -s tests -q` | 673 tests, OK |
| `tests.benchmark_r04_normalization` | PASS; all rows deterministic |
| Final independent R05 benchmark | PASS; all required flags true |
| `compileall -q ocr_aggregation.py ocr_candidate.py tests` | PASS |
| `pip check` | `No broken requirements found.` |
| `git diff --check` | PASS |

No real log or candidate/data body was read.  Before/after metadata and
SHA-256 values are identical: `logs/simple_brush.log` is 7,372,745 bytes,
mtime `2026-08-01T07:15:54.4076423Z`, SHA-256
`1BE253B07B246AA1B9F3F207F5C22876FA8116A13DA13959221ECCC2AC62AF96`.
`data/ocr_runs` remains four zero-byte files with inventory SHA-256
`A59878C97FBC990B25C79DCB3EF8ABE900CFDA4AE9B61DF8A3B0B9C3585C8659`.

## 9. Disposition

This narrow stability corrective is ready for maintainer review.  It is
appropriate to **recommend a fresh, independent R05 final Acceptance rerun**.
It does not itself approve R05 final acceptance, record-mode production
activation, real-page validation, or any change to the production default,
which remains disabled.
