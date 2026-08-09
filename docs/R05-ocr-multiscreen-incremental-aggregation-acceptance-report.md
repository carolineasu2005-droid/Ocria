# R05 OCR Multi-screen Incremental Aggregation — Change 7 Final Re-acceptance

## Disposition

**R05 automated final acceptance: BLOCKED.**

This independent, from-scratch acceptance ran the prescribed functional,
schema, replay, Store, isolation, regression, compilation, dependency, and
performance checks without changing production code, configuration, fixture,
threshold, Schema, Store, Replay, page flow, dependencies, or defaults.  The
fourth of five required continuous R05 performance runs reported
`8x64_unique_pure.p95_ms = 22.0040`, over the fixed `<= 20 ms` gate.  Per the
acceptance contract, that single failed run blocks the result; the passing
fifth run does not override it.

## Git baseline and scope

- Branch / HEAD: `main` / `ac3d7d406c034a6a290713e806e044f75ff6f6d4`
  (`perf(ocr): stabilize R05 aggregation latency`).
- R05 implementation: `f02209c`; R05 design: `cd5d96c`.
- Corrective history: `aaa5e69` records corrective validation history;
  `ac3d7d4` is the submitted stability corrective.  The performance,
  fail-open-contract, and 8x64-stability corrective reports are present.
- R06 Change 2--5 implementation is `0e0deca`; its design baseline is
  `afc41d8`.  No R06 code was changed.
- Pre-existing tracked modification: this acceptance report.  Pre-existing
  untracked files `README.md`, `docs/project-review.zip`, and
  `venv-packages-before-reinstall.txt` were not changed.  The latter two were
  not read.  There were no other tracked modifications or untracked files.
- `git diff --check` passed before and after validation.  Nothing was staged,
  committed, pushed, tagged, or released.

## Identity and Schema

| Item | Verified value/result |
| --- | --- |
| R05 aggregation version | `r05-v1` |
| R05 config version | `r05-config-v1` |
| Frozen config digest | `047ec8c40aab9b28ed3a7a6a63695f416677e1a73c25f3c398d77eca3b31ff7a` |
| Original R05 writer Schema | `1.2.0` |
| Current repository writer Schema | `1.3.0` |
| 1.2 reader compatibility | PASS |
| 1.3 R05 fields, document, and evidence semantics | PASS |
| R06-disabled fields affect R05 result | No; PASS |

The current writer was not reverted.  Synthetic record tests verify 1.2
restoration and the 1.3 R05 projection, including unchanged document/evidence
semantics while R06 is disabled.

## Historical Blocking Audit and Correctives

The historical acceptance was BLOCKED by `8x64_unique_pure p95 = 20.2872 ms`
against the same 20 ms limit.  It is historical evidence, not this result.
The performance corrective, the 257+/stage-exception/tolerant-replay fail-open
corrective, and the 8x64 stability corrective were independently documented;
the last is the current HEAD.  This report does not accept those reports as a
substitute for re-execution.

## Five continuous R05 benchmark runs

All runs used the unchanged repository command
`./venv/Scripts/python.exe -m tests.benchmark_r05_aggregation`, synthetic
fixed fixtures, and 25 timed iterations after warm-up.  `[]` means an empty
`contract_blockers` list.  Peak is the largest scenario peak; all are below
the 32 MiB limit.

| Run | 8x64 p50/p95 ms | 8x256 p50/p95 ms | Record p95 | Fuzzy 1→1/1→2/2→1 p95 ms | Peak KiB | Gates / blockers / deterministic / release / disabled / fair |
| --- | --- | --- | ---: | --- | ---: | --- |
| 1 | 15.2962 / 17.1612 | 52.0832 / 54.2490 | 20.9126 | 0.7367 / 0.4771 / 0.4517 | 2717.53 | true / [] / true / true / true / true |
| 2 | 15.4802 / 16.1481 | 52.2213 / 58.2631 | 22.3032 | 0.4143 / 0.5481 / 0.5808 | 2717.53 | true / [] / true / true / true / true |
| 3 | 16.5443 / 17.7857 | 53.6054 / 55.7274 | 22.5444 | 0.5101 / 0.6052 / 0.6743 | 2717.53 | true / [] / true / true / true / true |
| 4 | 16.7219 / **22.0040** | 52.6674 / 58.3830 | 22.7394 | 0.5470 / 0.6179 / 0.7430 | 2717.53 | **false** / [] / true / true / true / true |
| 5 | 15.4700 / 17.0501 | 53.3303 / 55.5072 | 22.0132 | 0.5003 / 0.6793 / 0.5183 | 2717.53 | true / [] / true / true / true / true |

Required gates are 8x64 <=20 ms, 8x256 <=150 ms, record <=30 ms, each fuzzy
shape <=50 ms, peak <=32 MiB, empty blockers, deterministic 100, full
candidate reference release, disabled constructor isolation, and fair record
semantics.  All pass in all rows except the Run 4 8x64 tail latency and its
derived required-gate flag.  The final full-regression confirmation benchmark
also passed all of its required flags, but cannot erase Run 4.

Minimal reproduction: run the command above on this baseline and retain every
result; no averaging, median, or later rerun may replace a failed required run.

## Contracts, fail-open, replay, builder, and Store

The targeted and discovery suites passed automated coverage for:

- 255/256 normal aggregation and 257/300 partial fail-open: no exact, fuzzy,
  or historical call; all content uncertain and document-visible; source
  evidence retained; `screen_segment_limit_exceeded`; elevated risk.
- Exact, fuzzy, and historical injected exceptions: terminal later-stage stop,
  prior accepted evidence retained, remainder uncertain, fixed redacted
  warning, and source screen immutability.
- Mutually exclusive/complete matched-new-uncertain groups; authoritative
  `document_segments`; deterministic LF `document_text`; source, exact,
  historical, and fuzzy 1→1/1→2/2→1 traceability; formal double gate and
  run/candidate isolation.
- Strict replay rejection of duplicate ID, duplicate formal index, and
  out-of-order data; tolerant stable ordering, uncertain conflict retention,
  partial/elevated result, no source candidate/screen/JSONL mutation, and no
  text loss.
- Synthetic `R05_AGGREGATION_MODE=record`: one aggregator per candidate, one
  add per screen, one finalize, final screen projection and candidate document,
  Store persistence without recomputation, online/replay equality, and Store
  failure without page-flow change.  Production default remains `disabled`.
- Existing spies/mocks cover unchanged OCR/screenshot counts, load gate,
  scrolling/distance/eight-screen limit, waits, clicks, candidate/focus/refresh,
  keywords, favorite/forward/next, ESC, timing, and controlled stops.  No real
  BOSS page was run.

## Full validation and isolation

| Check | Result |
| --- | --- |
| Requested nine-module unittest command | 552 tests, OK |
| `unittest discover -s tests -q` | 673 tests, OK |
| `tests.benchmark_r04_normalization` | PASS |
| Final R05 benchmark after full regression | PASS for its invocation; does not supersede Run 4 |
| Requested `compileall -q` | PASS |
| `pip check` | No broken requirements found |
| `git diff --check` | PASS |

No log or governed data body was read.  Before and after, `logs/simple_brush.log`
was 7,372,745 bytes with mtime `2026-08-01 15:15:54` and SHA-256
`1BE253B07B246AA1B9F3F207F5C22876FA8116A13DA13959221ECCC2AC62AF96`.
`data/ocr_runs` remained the same four zero-byte files with unchanged inventory
and SHA-256 values.  Tests used synthetic fixtures and temporary locations.

Windows real BOSS page: **NOT RUN**.  Real candidate data: **NOT USED**.
macOS GUI/browser/package: **NOT RUN**.  These do not change the automated
technical verdict, but this report neither validates nor approves real-page
production record activation.

## Remaining risk and recommendation

The strict 8x64 p95 performance threshold remains unstable under this fresh
five-run acceptance: one required result is 22.0040 ms.  A separate corrective
would need to address that instability without changing fixture, thresholds,
algorithmic semantics, config identity, or default mode, followed by a new
independent full acceptance.

R05 record mode is not approved as the automated integration prerequisite for
R06 Change 6 while this acceptance is BLOCKED.  Production default remains
disabled.  Real-page production record activation is not approved by this
report.
