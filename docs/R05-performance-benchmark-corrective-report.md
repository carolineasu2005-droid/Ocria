# BossOCR R05 Performance Benchmark Corrective Report

## 1. Overall result

| Item | Result |
| --- | --- |
| Corrective classification | **benchmark defect + production performance defect** |
| Corrective scope result | **partial** |
| R05 performance gates | PASS in all three corrected benchmark rounds |
| Synthetic semantic equivalence | PASS, 14 scenarios × 14 field groups, 196/196 equal |
| Targeted regression | PASS, 62/62 |
| Related regression | PASS, 431/431 |
| Full regression | FAIL, 644/645 passed; one pre-existing stale Schema assertion |
| Independent contract blocker | `257_segment_limit_contract` fails in all three rounds |
| Recommend immediately restarting Change 7 | **No. Correct the separately scoped contract/test blockers first, then rerun Change 7 from the beginning in an independent session.** |
| Commit/push status | Uncommitted; no push/tag/Release |

This report is a performance corrective report. It is not a Change 7 acceptance
report and does not declare Change 7 passed.

## 2. Git baseline and worktree gate

- Branch: `main...origin/main`
- HEAD: `cd5d96c731caed07f7b841c437b2ee9f5086ffd0`
- HEAD subject: `docs(ocr): define R05 multiscreen aggregation`
- Initial `git diff --check`: passed.
- No unassignable tracked modification was found.

Initial tracked changes were the approved Change 6 implementation surface:

```text
ocr_candidate.py
ocr_records.py
ocr_replay.py
ocr_store.py
simple_brush.py
tests/test_ocr_candidate.py
tests/test_ocr_records.py
tests/test_ocr_replay.py
tests/test_ocr_store.py
```

Initial untracked R05 files were attributable to Changes 2–7:

```text
ocr_aggregation.py
tests/test_ocr_aggregation.py
tests/benchmark_r05_aggregation.py
```

The pre-existing user files `docs/project-review.zip` and
`venv-packages-before-reinstall.txt` were not read, modified, staged, or
deleted. `docs/*.md` is ignored by the repository, so this report and the
earlier R05 reports do not appear in ordinary `git status` output.

## 3. Authoritative contract review

The following documents were read in full before production changes:

```text
docs/RPD-R05-ocr-multiscreen-incremental-aggregation.md
docs/TID-R05-ocr-multiscreen-incremental-aggregation.md
docs/R05-ocr-multiscreen-incremental-aggregation-acceptance-report.md
```

The last file is presently a **Change 7 Blocking Audit**, despite its filename.
It explicitly stops Change 7 after the first performance failure and does not
contain complete acceptance evidence.

The relevant frozen contracts retained by this corrective change are:

- formal-screen dual gate and candidate/run identity;
- longest continuous document-tail/current-head exact matching;
- exact evidence thresholds and single-long-line exception;
- fuzzy window 4, shapes 1→1/1→2/2→1, score 0.94, gray floor 0.88,
  unmatched-per-side 2, `autojunk=False`;
- exact-only historical length 2–4 with unique source and two external anchors;
- uncertain content is appended, never silently discarded by this optimization;
- all source occurrences and match evidence are retained;
- `document_segments` remains authoritative and `document_text` remains its LF
  projection;
- candidate-local state only, with no cross-candidate/global cache;
- production default remains `disabled`.

## 4. Blocking Audit reproduction

Environment:

```text
Python: CPython 3.13.14, MSC v.1944, 64-bit AMD64
Platform: Windows-11-10.0.26200-SP0
CPU: 12th Gen Intel(R) Core(TM) i5-12400F
GC before benchmark: enabled
GC thresholds: (2000, 10, 10)
Original warmup: 3 calls plus one untimed reference call
Original timed iterations: 25
Original timer: perf_counter
```

The original command was run three times without modifying the original
benchmark:

```powershell
.\venv\Scripts\python.exe -m tests.benchmark_r05_aggregation
```

| Original row | Round 1 p95 ms | Round 2 p95 ms | Round 3 p95 ms |
| --- | ---: | ---: | ---: |
| `8x64_unique` | 126.4369 | 115.9209 | 122.6492 |
| `8x64_exact_50_percent` | 21.9164 | 16.8757 | 17.6155 |
| `8x64_exact_90_percent` | 14.4554 | 14.8621 | 14.3370 |
| `complete_screen_duplicate` | 14.0237 | 13.9361 | 14.4626 |
| `one_new_line_per_screen` | 13.9284 | 14.7436 | 14.1194 |
| `fuzzy_1_to_1` | 1.2800 | 1.6864 | 1.2571 |
| `fuzzy_1_to_2` | 2.2366 | 2.1803 | 2.1209 |
| `fuzzy_2_to_1` | 2.1711 | 3.0715 | 2.1516 |
| `historical_n_minus_2` | 1.8428 | 1.8892 | 1.7316 |
| `historical_ambiguous` | 6.2824 | 8.5739 | 8.3087 |
| `8x256_maximum` | 69.8514 | 67.5819 | 70.6653 |
| `record_build_and_aggregation_8x64` | 27.1751 | 21.2797 | 21.4505 |

The primary failure reproduced reliably. It was not a one-off machine spike.
The original record row also reported `deterministic=false` in all three runs.

## 5. Benchmark credibility audit

### 5.1 Twenty timing/input checks

1. **p95:** `statistics.quantiles(..., n=20, method="inclusive")[18]` is a
   valid inclusive linear p95. The implementation lacked a unit test; the
   corrected benchmark freezes the method and tests `1..25 -> 23.8`.
2. **Timer:** the original used `perf_counter`; the corrected benchmark uses
   `perf_counter_ns`.
3. **Warmup:** the three declared warmups were outside samples, but the
   reference result was an undeclared fourth untimed invocation. The corrected
   output declares 3 warmups and 1 reference invocation separately.
4. **Fixture boundary:** primary fixtures were prebuilt, but fuzzy and
   historical lambdas rebuilt normalization and records inside timing. All
   corrected fixtures are built before timing.
5. **tracemalloc:** original timing and memory passes were separate. The
   corrected timing also rejects an already-active `tracemalloc` session.
6. **GC:** original automatic GC state and previous-result destruction could
   differ by scenario order. Every corrected sample collects outside timing,
   disables GC during only the timed operation, and restores the prior state.
7. **Fresh aggregator:** the original pure and record operations did construct
   a new aggregator/builder per iteration. This remains true.
8. **Finalized result reuse:** no finalized aggregator result was used as the
   next iteration's operation. The reference result is comparison-only.
9. **Mutable fixture reuse:** inputs are frozen records/tuples and were not
   mutated. A corrected unit test deep-compares the fixture before and after.
10. **Partial cache warming:** no production global cache was found, but fixed
    ordering, allocator state and GC generations were uncontrolled. The
    corrected benchmark supports declared, unique-last, randomized and
    single-scenario process execution.
11. **Order effect:** pre-fix fair unique p95 was 63.6951 ms first, 57.5820 ms
    last, 59.2301 ms randomized and 58.0601 ms standalone. All failed 20 ms;
    order did not change the conclusion.
12. **Swallowed exceptions:** the production stages intentionally catch broad
    exceptions for fail-open behavior. The original benchmark did not expose
    status/warnings/counts, so a deterministic fast fallback could be mistaken
    for success. Corrected rows expose status, warnings and `contract_ok`.
13. **Record mode:** it was explicitly `record`, not disabled. However its
    `completed_at` used the live clock, making the row nondeterministic. The
    corrected record operation fixes both timestamps.
14. **Config:** most rows used default config, while the candidate-limit row
    silently used a custom config. Corrected rows report their own config
    version and digest.
15. **Screen count:** scenarios used 1, 2 or 8 screens, but the original output
    omitted this. Corrected rows report formal-screen count.
16. **Segment count:** original output omitted actual input/accepted/document
    counts. Corrected rows report all three plus matched/new/uncertain.
17. **8×256 fail-open:** the original 8×256 row had exactly 256 segments per
    screen and did not exceed the limit. It was a normal 50% exact-overlap
    path. It is now named `8x256_exact_50_percent`; a true 8×256 unique row is
    separate.
18. **Pure/record input:** original pure used the alleged unique fixture while
    record used exact 50%. Corrected pure and record rows use the exact same
    immutable 8×64 unique record tuple and config.
19. **Timed scope:** original pure and record scopes differed but labels hid
    the distinction. Corrected rows name `aggregate_add_screen_plus_finalize`
    and `builder_add_screen_projection_validation_plus_candidate_finalize`.
20. **Path:** pure directly exercises `CandidateDocumentAggregator`; record
    intentionally exercises `CandidateOcrBuilder` projection/model validation.
    Both remain useful, now with identical input and explicit scopes.

### 5.2 The alleged unique fixture was not unique

The original `_text()` changed only a short decimal prefix and filled the rest
of each 64-character segment with `x`. With `SequenceMatcher(autojunk=False)`,
adjacent values were highly similar enough for fuzzy acceptance.

Untimed diagnostics, without synthetic text output:

| Scenario | Input | Document | Exact k checks | Fuzzy calls/candidates/scores | Historical lookups/index entries | Matched/new/uncertain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original alleged 8×64 unique | 512 | 484 | 448 | 8 / 182 / 189 | 1218 / 1446 | 28 / 484 / 0 |
| original exact 50% / record input | 512 | 288 | 231 | 1 / 0 / 0 | 630 / 858 | 224 / 288 / 0 |
| original 8×256 maximum | 2048 | 1152 | 903 | 1 / 0 / 0 | 2646 / 3450 | 896 / 1152 / 0 |

Thus the alleged unique case performed a bounded near-duplicate fuzzy search
on every screen, while the maximum and record fixtures accepted exact overlap
and skipped non-empty fuzzy search. This explains both contradictions without
assuming that 8×256 performed less exact/historical work.

### 5.3 Fair controls

The corrected unique generator uses a deterministic SHA-512-derived synthetic
string only as fixture material. It is not used by production matching.

| Fair scenario | Screens/input/accepted | Document | Exact k checks | Fuzzy calls/candidates/scores | Historical lookups/index entries | Matched/new/uncertain |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 8×64 pure | 8 / 512 / 512 | 512 | 448 | 8 / 182 / 189 | 1302 / 1530 | 0 / 512 / 0 |
| 8×64 record, same tuple | 8 / 512 / 512 | 512 | 448 | 8 / 182 / 189 | 1302 / 1530 | 0 / 512 / 0 |
| 8×128 pure | 8 / 1024 / 1024 | 1024 | 896 | 8 / 182 / 189 | 2646 / 3066 | 0 / 1024 / 0 |
| 8×256 pure | 8 / 2048 / 2048 | 2048 | 1792 | 8 / 182 / 189 | 5334 / 6138 | 0 / 2048 / 0 |

Before production modification, this fair fixture measured:

| Scenario | p50 ms | p95 ms |
| --- | ---: | ---: |
| 8×64 unique pure | 54.9137 | 56.7404 |
| 8×128 unique pure | 73.2514 | 76.1355 |
| 8×256 unique pure | 110.5134 | 115.8308 |
| 8×64 unique record, identical input | 61.3079 | 67.4467 |

Therefore the final stage-A classification is **benchmark defect + production
performance defect**, not benchmark-only.

## 6. Production profile

### 6.1 Method

- Fixture: corrected true-unique 8 screens × 64 segments, 64 comparison
  characters per segment.
- Timed/profiled scope: fresh `CandidateDocumentAggregator`, eight
  `add_screen()` calls, and `finalize()`.
- Tools: standard-library `cProfile`, `pstats`, and separate
  `perf_counter_ns` wrapper instrumentation.
- No third-party dependency, OCR, Store, page, network or real data.
- Profile output contained function names/counts/times only, never body text.

Baseline cProfile recorded 1,073,484 calls in 0.231 seconds under profiler
instrumentation. Actual wrapper timing averaged 57.4339 ms per candidate,
7.1632 ms per screen and 112.1756 microseconds per input segment.

### 6.2 Baseline layer attribution

The following top-level percentages are non-overlapping except where the
indented model/index detail is explicitly described as part of append:

| Layer | ms/candidate | Share |
| --- | ---: | ---: |
| R04 adapter/input validation | 3.2921 | 5.73% |
| exact boundary | 1.6938 | 2.95% |
| fuzzy boundary | 39.2741 | 68.38% |
| historical classification | 3.5630 | 6.20% |
| document/source append | 9.1655 | 15.96% |
| finalize | 0.1218 | 0.21% |
| remaining orchestration | 0.3236 | 0.56% |

Within append, historical index update was 1.1749 ms, document-segment model
validation was 3.6119 ms, and source-occurrence validation was 1.5029 ms.

### 6.3 Hottest baseline functions

| Calls | Function | Cumulative seconds | Self seconds |
| ---: | --- | ---: | ---: |
| 8 | `CandidateDocumentAggregator.add_screen` | 0.232 | 0.001 |
| 8 | `find_fuzzy_boundary_overlap` | 0.124 | ~0.000 |
| 182 | `_candidate_from_tiling` | 0.111 | 0.002 |
| 189 | `score_fuzzy_group` | 0.107 | 0.002 |
| 189 | `_unmatched_ranges` | 0.074 | 0.001 |
| 189 | `SequenceMatcher.get_opcodes` | 0.073 | 0.001 |
| 378 | `SequenceMatcher.get_matching_blocks` | 0.071 | 0.004 |
| 2978 | `SequenceMatcher.find_longest_match` | 0.064 | 0.044 |
| 16 | `_append` | 0.049 | 0.002 |
| 24 | `_screen_identity` | 0.033 | 0.002 |
| 512 | `OcrDocumentSegment.__post_init__` | 0.026 | 0.002 |
| 8 | `adapt_r04_screen_segments` | 0.025 | ~0.000 |
| 1024 | `build_comparison_text` | 0.023 | 0.001 |
| 8 | `classify_historical_duplicates` | 0.020 | 0.003 |
| 8 | `find_exact_boundary_overlap` | 0.013 | 0.001 |

### 6.4 Exact, historical and model conclusions

Exact does execute `document_keys[-k:] == current_keys[:k]` for descending
`k`, allocating tuple slices. The fair 8×64 no-match route performed 448 k
checks. Its worst segment-key work remains O(S²), but it represented only
2.95% of measured time. The 8×256 50%-exact fixture performed 903 k checks and
was still faster than the original alleged unique row because it skipped
fuzzy. KMP was therefore not justified for this corrective change.

The historical sequence index is incrementally maintained; it is not rebuilt
per screen. Fair 8×64 performed 1302 lookups and held 1530 entries. Historical
classification plus index update was secondary, not the principal blocker.

Frozen model validation and document/source construction were material but not
the contradiction's root cause. Record mode additionally revalidates replaced
screen records and the candidate document; the fair input proved this overhead
instead of comparing it with a different exact-heavy fixture.

### 6.5 Phase-B conclusion

- Primary bottleneck: bounded fuzzy scoring on every no-exact-overlap screen.
- Secondary bottlenecks: document/source construction and model validation,
  then adapter and historical classification.
- Benchmark overhead: timer call itself negligible; the original selective
  fixture construction and uncontrolled GC were validity defects rather than
  the main 8×64 duration.
- Safe optimization area: call-local group projection/count cache, exact-safe
  fuzzy upper bound, call-local `SequenceMatcher` right-side index reuse, and
  reuse of validation already completed by the R04 adapter.
- Prohibited semantics retained: thresholds, windows, shapes, evidence,
  occurrences, uncertain retention, historical rules and final validation.

## 7. Corrective changes

### 7.1 Benchmark correction

`tests/benchmark_r05_aggregation.py` now:

- uses a real contract-unique generator for 8×64/128/256;
- uses the exact same immutable 8×64 fixture/config for pure and record;
- fixes `created_at` and `completed_at` for deterministic record results;
- constructs every fixture outside timing;
- uses `perf_counter_ns`, inclusive p95 with a unit test, explicit warmup and
  reference counts, and one GC policy for every scenario;
- keeps timing and `tracemalloc` separate;
- outputs actual screen/input/accepted/document/matched/new/uncertain counts;
- outputs exact/fuzzy/historical calls and candidate/index/lookup counts;
- outputs status, warnings, risk, mode, scope, config identity and contract
  result without synthetic text;
- renames the old maximum row to `8x256_exact_50_percent` and adds a true
  8×256 unique row;
- supports declared, unique-last, randomized and one-scenario process runs;
- checks 100-run determinism, 100 full-candidate reference release, disabled
  constructor behavior and pure/record semantic parity.

### 7.2 Production correction

`ocr_aggregation.py` now:

1. computes and caches group join text, content length and exact character
   multiset inside one fuzzy call;
2. uses the multiset similarity as the same safe upper bound represented by
   `SequenceMatcher.quick_ratio`; only when that upper bound is below the
   frozen 0.88 gray floor does it skip exact matching blocks;
3. still runs the full exact `SequenceMatcher` path for every group capable of
   acceptance or uncertainty;
4. reuses the `SequenceMatcher` index for the same right group within one fuzzy
   call by changing only `seq1`;
5. keeps all caches local to one fuzzy call; they are neither serialized nor
   shared across candidates;
6. keeps public exact/fuzzy/historical functions fully validating their input,
   while the aggregator reuses the adapter-validated current screen and its
   own frozen, already-validated document objects in private cores;
7. uses `len(comparison_text)` during append after adapter validation, while
   `OcrDocumentSegment.__post_init__` still performs complete final validation.

No fuzzy stage or candidate was removed. The optimization only avoids exact
matching-block construction when a mathematical upper bound proves the score
cannot reach even the uncertainty floor.

### 7.3 Complexity

| Area | Before | After |
| --- | --- | --- |
| exact boundary | O(S²) descending tuple-slice comparisons | unchanged; profile did not justify KMP |
| low-similarity fuzzy group | exact bounded `SequenceMatcher`, worst near O(C²) | O(C) character multiset upper bound when provably below 0.88 |
| potentially gray/accepted fuzzy group | bounded exact `SequenceMatcher` | same exact result; right-side index reused per call |
| group projection | repeated join/content scan per score pair | once per exact group-key tuple per call |
| public validation | full validation | unchanged |
| aggregator validation | repeated public document/current scans | one adapter validation plus private validated cores; frozen model validation retained |
| append character count | extra whitespace-validating scan plus model validation | `len` plus unchanged full frozen-model validation |

Worst-case fuzzy scope remains bounded by the same windows, candidate limit and
512-character group limit. No threshold or acceptance scope changed.

### 7.4 Post-change profile

On the same fair 8×64 input, cProfile fell to 398,184 calls and 0.085 seconds
under profiler instrumentation. Fuzzy cumulative time fell from 0.124 to 0.011
seconds. The new top cumulative costs are append/model validation, adapter
validation, fuzzy, and historical; all remain inside the performance gate.

## 8. Semantic equivalence

Before modifying production code, a completely synthetic golden was retained
in memory as canonical per-field SHA-256 values. After modification, the same
fields were regenerated and compared. No synthetic body was written to disk or
printed.

Covered scenarios:

```text
unique
exact 50%
exact 90%
complete duplicate
one new line
fuzzy 1→1
fuzzy 1→2
fuzzy 2→1
fuzzy uncertain
historical N-2
historical ambiguous
duplicate index
out-of-order
interrupted
```

Field groups compared for every scenario:

```text
screen aggregation status
matched IDs
new IDs
uncertain IDs
match evidence
source occurrences
warning codes
risk
counts
document segments
document text
summary
document status
version/config/digest/Schema identity
```

Result: **14 scenarios × 14 field groups = 196 comparisons; 196 equal, 0
differences**. The comparison was repeated after the validated-core refactor
and again produced 0 differences.

## 9. Corrected performance: all three rounds

Command, executed three times from the repository root:

```powershell
.\venv\Scripts\python.exe -m tests.benchmark_r05_aggregation
```

| Scenario | Round 1 p50/p95 ms | Round 2 p50/p95 ms | Round 3 p50/p95 ms | Peak KiB, rounds 1/2/3 |
| --- | ---: | ---: | ---: | ---: |
| `8x64_unique_pure` | 15.1306 / 16.5343 | 15.8014 / 17.6488 | 15.2541 / 16.0888 | 709.47 / 709.47 / 709.47 |
| `8x128_unique_pure` | 27.6830 / 29.7076 | 27.8369 / 29.9150 | 27.7290 / 29.5889 | 1376.52 / 1376.52 / 1376.52 |
| `8x256_unique_pure` | 52.8404 / 58.6096 | 52.9763 / 57.1297 | 53.1443 / 57.1214 | 2717.53 / 2717.53 / 2717.53 |
| `8x64_unique_record_projection_candidate_finalize` | 20.1479 / 20.9713 | 20.3144 / 21.2868 | 20.4401 / 22.2202 | 759.75 / 759.75 / 759.75 |
| `8x64_exact_50_percent` | 12.0823 / 14.4209 | 12.0828 / 13.2518 | 12.0086 / 17.8967 | 429.78 / 429.78 / 429.78 |
| `8x64_exact_90_percent` | 11.5428 / 14.6818 | 10.8374 / 12.2406 | 10.7734 / 12.3500 | 247.89 / 247.89 / 247.89 |
| `complete_screen_duplicate` | 11.1667 / 14.1965 | 11.0637 / 12.3948 | 10.5285 / 11.9253 | 221.60 / 221.60 / 221.60 |
| `one_new_line_per_screen` | 10.8310 / 11.6306 | 10.7691 / 12.3884 | 10.6879 / 11.6459 | 225.97 / 225.97 / 225.97 |
| `single_screen_fuzzy_1_to_1` | 0.3277 / 0.4838 | 0.3428 / 0.4469 | 0.3296 / 0.3783 | 44.80 / 44.80 / 44.80 |
| `single_screen_fuzzy_1_to_2` | 0.5382 / 0.7363 | 0.3870 / 0.4513 | 0.3786 / 0.6385 | 51.00 / 51.00 / 51.00 |
| `single_screen_fuzzy_2_to_1` | 0.4357 / 0.7201 | 0.3969 / 0.5235 | 0.3976 / 0.6641 | 51.87 / 51.87 / 51.87 |
| `single_screen_fuzzy_uncertain` | 0.3376 / 0.5065 | 0.3205 / 0.5103 | 0.3244 / 0.5002 | 42.95 / 42.95 / 42.95 |
| `8x64_near_duplicate_fuzzy_stress` | 36.5263 / 38.8340 | 38.8156 / 44.4160 | 37.5214 / 43.0156 | 702.46 / 702.46 / 702.46 |
| `historical_n_minus_2` | 0.3818 / 0.4207 | 0.3785 / 0.4959 | 0.3923 / 0.5235 | 16.67 / 16.67 / 16.67 |
| `historical_ambiguous` | 0.8075 / 1.1695 | 0.8320 / 1.1059 | 0.8211 / 1.3427 | 58.62 / 58.62 / 58.62 |
| `8x256_exact_50_percent` | 54.9574 / 57.8071 | 55.2609 / 59.6311 | 54.7263 / 56.6698 | 1792.90 / 1792.90 / 1792.90 |
| `fuzzy_candidate_limit_1_contract` | 0.2599 / 0.3138 | 0.2475 / 0.3158 | 0.2563 / 0.3860 | 10.37 / 10.37 / 10.37 |
| `257_segment_limit_contract` | 0.0457 / 0.0522 | 0.0434 / 0.0511 | 0.0453 / 0.0496 | 2.73 / 2.73 / 2.73 |

Gate results in every round:

```text
8×64 pure aggregate+finalize p95 <= 20 ms: PASS
8×256 pure aggregate+finalize p95 <= 150 ms: PASS
single-screen fuzzy p95 <= 50 ms: PASS
8×64 record projection+aggregation+candidate finalize p95 <= 30 ms: PASS
peak additional memory <= 32 MiB: PASS
```

All three rounds also reported:

```text
determinism_100 = true
reference_release_100_full_candidates = true
disabled_does_not_construct_aggregator = true
fair_record_semantics_equal = true
required_performance_gates_pass = true
```

No round was omitted. The highest gated p95 values, not the best values, still
pass: 17.6488 ms for 8×64 pure, 58.6096 ms for 8×256 pure, 22.2202 ms for
record, and 0.7363 ms for the listed single-screen fuzzy shapes.

## 10. Tests and static checks

### Targeted

```powershell
.\venv\Scripts\python.exe -m unittest `
  tests.test_ocr_aggregation `
  tests.test_ocr_candidate `
  -v
```

Result: **62 tests, OK**.

### Related regression

```powershell
.\venv\Scripts\python.exe -m unittest `
  tests.test_ocr_records `
  tests.test_ocr_store `
  tests.test_ocr_replay `
  tests.test_ocr_stage0_integration `
  tests.test_simple_brush_ocr `
  tests.test_ocr_detector `
  tests.test_ocr_text `
  -v
```

Result: **431 tests, OK**.

### Full regression

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result: **645 tests run; 644 passed, 1 failed**.

Failure:

```text
tests.test_ocr_normalization.OcrComparisonTextTests.
test_r04_schema_bump_leaves_r05_to_r07_fields_unimplemented
expected STORAGE_SCHEMA_VERSION == "1.1.0"
actual STORAGE_SCHEMA_VERSION == "1.2.0"
```

This assertion predates/already conflicts with the Change 6 Schema 1.2 writer.
`tests/test_ocr_normalization.py` is outside this performance corrective's
allowed test files and was not modified.

### Other checks

```powershell
.\venv\Scripts\python.exe -m compileall -q `
  ocr_aggregation.py `
  ocr_candidate.py `
  tests
```

Result: PASS.

```powershell
.\venv\Scripts\python.exe -m pip check
```

Result: `No broken requirements found.`

```powershell
git diff --check
```

Result: PASS.

## 11. Independent blockers and deviations

### 11.1 257-segment path is not fail-open

The corrected benchmark deliberately records the actual result rather than
calling its fast duration a pass:

```text
formal screens = 1
input segments = 257
accepted segments = 0
document segments = 0
matched/new/uncertain = 0/0/0
screen status = failed
warning = segment_mapping_invalid
contract_ok = false
```

The aggregator detects `> max_screen_segments` and calls `_all_uncertain`, but
that helper calls the adapter again; the adapter rejects the same 257-segment
record, producing `failed` instead of preserving all content as uncertain.
Changing this would alter warning/status/document semantics, so it is excluded
from this performance-equivalent corrective.

### 11.2 Other static contract gaps observed but not modified

- Tolerant replay currently rejects duplicate/out-of-order formal screens
  before rebuilding, rather than returning a tolerant uncertain document.
- Stage exception handling can continue later matching stages or classify a
  historical-stage failure's remaining content as new, rather than uniformly
  retaining the affected content as uncertain.

These are pre-existing semantic issues. They were not needed to achieve the
performance result and cannot be disguised as performance changes.

## 12. Privacy and data isolation

Real ordinary log before and after all diagnostics/tests/benchmarks:

| Property | Before | After |
| --- | --- | --- |
| size | 7,372,745 bytes | 7,372,745 bytes |
| mtime UTC | `2026-08-01T07:15:54.4076423Z` | `2026-08-01T07:15:54.4076423Z` |
| SHA-256 | `1BE253B07B246AA1B9F3F207F5C22876FA8116A13DA13959221ECCC2AC62AF96` | same |

`data/ocr_runs` before and after:

```text
file count = 4
total bytes = 0
recursive relative path/size/mtime/SHA-256 inventory exact match = true
```

No synthetic body was printed by the corrected benchmark, written to Store, or
persisted in a diagnostic file. No real OCR JSONL content was created.

## 13. Version/config/Schema decision

| Identity | Before | After | Decision |
| --- | --- | --- | --- |
| aggregation version | `r05-v1` | `r05-v1` | unchanged |
| config version | `r05-config-v1` | `r05-config-v1` | unchanged |
| config digest | `047ec8c40aab9b28ed3a7a6a63695f416677e1a73c25f3c398d77eca3b31ff7a` | same | unchanged |
| storage Schema | `1.2.0` | `1.2.0` | unchanged |

The golden comparison proves there was no output, threshold, field or matching
semantic change. A version/config/digest/Schema bump would therefore be
incorrect.

## 14. Corrective file scope

Files changed by this corrective work:

```text
ocr_aggregation.py
tests/benchmark_r05_aggregation.py
tests/test_ocr_aggregation.py
docs/R05-performance-benchmark-corrective-report.md
```

No white-list-external production file was changed. Existing Changes 2–6
remain uncommitted in the same worktree, so ordinary Git output also lists
their earlier files.

## 15. Final Git state

Expected `git status --short` after this report (ignored Markdown omitted):

```text
 M ocr_candidate.py
 M ocr_records.py
 M ocr_replay.py
 M ocr_store.py
 M simple_brush.py
 M tests/test_ocr_candidate.py
 M tests/test_ocr_records.py
 M tests/test_ocr_replay.py
 M tests/test_ocr_store.py
?? docs/project-review.zip
?? ocr_aggregation.py
?? tests/benchmark_r05_aggregation.py
?? tests/test_ocr_aggregation.py
?? venv-packages-before-reinstall.txt
```

`git diff --stat` covers only tracked pre-existing Changes 2–6 and therefore
does not list the untracked corrective files. `git diff --check` passes.

## 16. Explicit declarations

```text
未运行真实BOSS页面
未使用真实候选人数据
未修改默认disabled
未实现AI
未实现R06/R07
未调整验收门槛
未调整R05阈值
未修改Schema
未删除source occurrence或match evidence
未增加跨candidate缓存
未增加第三方依赖
未commit
未push
未创建tag或Release
未宣布Change 7通过
```

This corrective change stops here for maintainer review. Resolve the separately
scoped 257-segment contract defect and stale full-suite Schema assertion (and
review the other static fail-open gaps) before an independent session restarts
Change 7 from the beginning.
