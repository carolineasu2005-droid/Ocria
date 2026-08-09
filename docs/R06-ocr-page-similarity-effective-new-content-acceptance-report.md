# R06 OCR Page Similarity / Effective-New — Change 7 Independent Final Acceptance

Date: 2026-08-02
Scope: independent synthetic automation acceptance only. No production code, configuration, schema, threshold, fixture, dependency, workflow, log, or run-data content was changed.

## 1. Decision

**R06 automated final acceptance: PASS.**

**R05 formal final Acceptance: BLOCKED.** The historical required run recorded
`8x64_unique_pure p95 = 22.0040 ms`, above the frozen 20 ms gate. That status
is not changed by this acceptance's passing current R05 benchmark.

**R05 prerequisite: Satisfied through maintainer waiver.** This is not an R05
formal final Acceptance PASS.

**Production activation: NOT APPROVED.** R05 and R06 production defaults remain
disabled. R06 is eligible to proceed to R07 only under disabled-by-default and
synthetic-validation constraints; real-page production record activation is not
approved.

## 2. Git baseline and scope gate

| Item | Result |
|---|---|
| Branch / HEAD | `main...origin/main [ahead 12]` / `3a3b921235dbfc996406aa0c530ff9bdb75aaea4` |
| Summary fail-open Corrective | `a9674d847ff3bc58cd18d59a7bee15c1a63e44e3` |
| Screen-digest lifecycle Corrective | `4325b1f4c128c66db60b736362ec3aff7868d4fb` |
| Consolidated ownership Corrective and AUDIT-002 binding | `3751e6c2441f62cfc8eb84a43587011395a566cb` |
| Prior blocker record / acceptance baseline | `3a3b921235dbfc996406aa0c530ff9bdb75aaea4` |
| Pre-report tracked production/test changes | none |
| Pre-report staged changes | none |
| Untracked user files | `README.md`, `docs/project-review.zip`, `venv-packages-before-reinstall.txt`; untouched |
| Acceptance report | this allowed, tracked report-only modification; not ignored |
| `git diff --check`, cached, and `HEAD` checks | all pass, with no whitespace errors |

The corrective code was committed before this acceptance. No prohibited Git
operation was run; in particular, no add, commit, push, tag, reset, clean,
restore, or checkout was used.

## 3. Contract and static audit

The RPD, TID, Change 1--6 reports, three Corrective reports, prior acceptance,
R05 acceptance/waiver, required production modules, and R03--R06, Store,
Replay, Sidecar, Builder, page-flow, and benchmark tests were audited.

| Area | Result |
|---|---|
| Defaults | `R05_AGGREGATION_MODE = disabled`; `R06_SIMILARITY_MODE = disabled` |
| Disabled projection | screen result and candidate summary null; manifest mode disabled and other R06 identity null; no zero/completed projection |
| Disabled execution | no R05 aggregator, R06 evaluator/context, resolver, n-gram, SimHash, R05 accounting, effective-new, or R06 sidecar construction |
| Design authority | R03 exact hash remains sole exact authority; R04 normalizer and R05 diff/split-merge authority are reused, not duplicated |
| R06 model | nested screen result is authoritative; top-level fields are compatibility projections; summary is recomputed from screen results |
| Reference | identity/index-based; not JSONL, list, Store-return, or container-order based |
| Boundaries | no R07 dynamic-bottom logic, AI/LLM/embedding/NER, SQLite, UI text blacklist, or R06 split-merge artifact |
| Page control flow | static field-use search found no R06 signal in scroll, end/stop, switch, keyword, favorite, forward, next, refresh, or ESC control |

`git grep -n "save_candidate("` found one production caller: `simple_brush.py`.
It passes `owner_candidate_record_id=builder.candidate_record_id`; the Builder's
identity is the finalized document identity. The compatibility fallback is
limited to valid document/run identities whose embedded screens all agree.

## 4. Synthetic matrix results

All listed matrix results are PASS unless stated NOT RUN.

| Matrix | Evidence and result |
|---|---|
| Schema 1.0--1.3 | Reader compatibility, future additive fields, required/type/enum/warning/identity validation, null/false/zero, Unicode, ordering, duplicate IDs, disabled and record projections: PASS |
| Reference and algorithm | no-reference/adjacent/explicit/legacy/strict-tolerant references; n=2/3/4 multiset Dice, frozen weighted normalization, 64-bit SHA-256 big-endian SimHash, Unicode, technical tokens, cross-process determinism, 100000 boundary and pre-Counter 100001 rejection: PASS |
| Accounting and conflict | matched/new/uncertain partitions, count/ratio recomputation, zero denominator, R05 projection, partial/failed/not-attempted, exact/R04/R05/R06 cross-layer conflict: PASS |
| Effective-new / UI / class | all emitted reasons, protected short terms and structured dates/versions/ranges, conservative uncertain handling, 2/3-screen geometry evidence, no text blacklist, all neutral comparison classes: PASS |
| Builder and summary fail-open | single evaluation, R05-before-R06, immutable saved result, fallback from finished results only, sanitized warning, no repeat OCR/R03/R04/R05/R06, context/weakref release and A-to-B continuation: PASS |
| Store normal lifecycle | 1/8 screens, A/B isolation, out-of-order embedded screens, finalize/close/repeated close, disabled/failure limit/manifest/screen failures: PASS |
| AUDIT-001 | document/embedded run, candidate, and screen identity permutations; mixed A/B screens; no candidate write or screen modification; only trusted terminal owner released: PASS |
| AUDIT-002 binding | `document_b` under trusted owner A and reverse A/B strictly reject before serialization/append; only supplied owner releases; B/A peer state remains; correct owner then saves: PASS |
| A/B/C isolation | owner A plus document B releases A only, retains B/C, then B/C finalize correctly: PASS |
| Digest/content and I/O failure | captured-at, result/reference/warning/summary changes, missing/duplicate/extra/fewer screens; serialization/open/append/flush failure best effort and later candidate viability: PASS |
| JSONL / Store | saved screen and embedded candidate screen equality; Store does not recompute; manifest identity matches: PASS |
| Replay | 1.0 through 1.3 record/disabled, online equality, strict sanitized rejection, tolerant structured issue, injected screen/summary failure and source immutability: PASS |
| Sidecar | exclusive create, existing destination, manifest-first, deterministic sort, override digest, source/duplicate checks and I/O failure recovery; no source mutation, OCR body, contact data, or full bbox: PASS |
| Page zero impact | synthetic disabled/record/error spy paths preserve OCR, screenshot, load/retry, scroll, wait, 8-screen limit, clicks, switch, focus, refresh, rule/action, ESC, and stop behavior: PASS |

## 5. Store trusted-ownership stress and release

The independent `TemporaryDirectory` stress invocation ran the five required
1,000-path groups: success, digest mismatch, identity mismatch, owner/document
mismatch, and candidate-append failure. It passed in 52.7491 s; Python
`tracemalloc` peak for this test process was 20,505.22 KiB. Each loop asserts
the digest cache and ownership index are empty after its terminal path (or that
only the explicitly unfinalized peer remains), verifies cross-candidate
isolation, and closes with both mappings empty. The owner/document group writes
1,000 correct documents after each rejected trusted-owner call; candidate-line
and screen-line assertions pass in the relevant success/failure groups.

## 6. Performance, determinism, and resources

| Benchmark | Current result |
|---|---|
| R04 | all eight synthetic rows deterministic; largest peak 999.02 KiB; PASS |
| R05 | required gates, contract blockers, determinism-100, reference release-100, disabled constructor isolation, and pure/record equivalence all PASS; 8x64 p50/p95 15.7490/17.0837 ms (<=20) |
| R06 20k | p50/p95: exact 6.4457/8.2025, 50% changed 10.2574/10.9015, repeated 5.3730/7.0124 ms; all <=15 ms |
| R06 eight adjacent | p50/p95 14.1451/16.2484 ms; <=100 ms |
| R06 memory | maximum measured scenario peak 592.38 KiB; <=16 MiB |
| R05-only / R06-only / combined Builder | p95 2.6195 / 4.0336 / 7.2462 ms |
| Replay / Sidecar | p95 5.0731 / 17.2770 ms |

Current R05 performance is recorded as supporting regression evidence only; it
does not supersede the historical formal BLOCKED verdict.

## 7. Full verification

```text
python -m unittest [requested 10 R03--R06/Store/Replay/Builder/page modules] -v: 591 passed
python -m unittest discover -s tests -q: 694 passed
python -m tests.benchmark_r04_normalization: PASS
python -m tests.benchmark_r05_aggregation: PASS
python -m tests.benchmark_r06_similarity: PASS
python -m compileall -q [required production modules and tests]: PASS
python -m pip check: PASS
git diff --check; git diff --cached --check; git diff HEAD --check: PASS
```

## 8. Privacy, platform, and NOT RUN

Only synthetic fixtures, `TemporaryDirectory` locations, temporary JSONL and
sidecar data, and Python subprocesses were used. The before/after inventories
of `logs/` and `data/ocr_runs/` match exactly by filename, size, mtime, and
SHA-256. Their contents were not read.

Windows real BOSS page: **NOT RUN**. Real candidate data: **NOT USED**. macOS
GUI/browser/package: **NOT RUN**. No production record activation was attempted.

## 9. Disposition

All automated R06 hard gates passed on the committed corrective baseline. There
are no R06 automated blockers from this acceptance. R05 remains formally
BLOCKED, its limited prerequisite is the maintainer waiver, both defaults remain
disabled, and production record / real-page activation remains **NOT APPROVED**.
