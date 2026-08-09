# R06 Summary Finalize Fail-open Corrective

## Result

This narrow Corrective fixes the blocked R06 candidate-summary finalization
path. It does not re-run Change 7, alter the blocked acceptance report, enable
production record mode, or change R03/R04/R05/R06 algorithms, thresholds,
defaults, page behavior, Store, Replay, or Sidecar.

## Original defect and minimal reproduction

Before this change, `CandidateOcrBuilder.finalize()` evaluated
`recompute_similarity_summary()` before its only release-protected block. A
synthetic injection of `RuntimeError("injected-summary")` produced:

```text
RuntimeError injected-summary finalized=False retained=1 evaluator=True
```

The exception escaped, the builder retained its screen list, and the R06
evaluator remained reachable.

## Root cause and implementation

`finalize()` now has one outer `try` / `finally` covering capture summary,
R05 finalization, R06 summary, document construction, and validation. The
finally block always calls the idempotent `_release_candidate_context()`, which
clears retained screens and attempts, detaches the R05 aggregator, clears and
detaches the R06 evaluator, and marks the builder finalized.

`recompute_similarity_summary()` remains the primary summary function. Its
existing result-only accounting was factored into
`ocr_records.summarize_similarity_results()`. If only the primary summary call
raises, Builder emits the fixed content-free warning:

```text
event=r06_candidate_summary_failed warning_code=evaluation_failed
```

and invokes that count-only primitive over the already completed ordered screen
results. It does not retry the primary function, run OCR/R03/R04/R05/R06 again,
or alter any screen. The fallback is therefore schema-valid and exactly matches
the candidate validation contract. It preserves all completed screens and their
screen-level R06 results. Exception text is never logged.

If a non-summary finalize operation itself fails (including candidate record
construction or validation), its exception still propagates according to the
existing contract, but context release is unconditional.

## Schema and immutability

No Schema version, field, field meaning, TID, algorithm, or threshold changed.
The minimal `ocr_records.py` change is required by the existing 1.3 validation
contract: non-empty record-mode candidates require a summary that equals the
count of their screen results. The shared pure counting primitive avoids a
second summary implementation.

The injection regression asserts that returned `screens` are field-for-field
the already saved record, including the R03/R04/R05 projection, and that the
screen `similarity_result` is unchanged. It also asserts the fallback summary
equals the standard recomputation over those screens.

## Lifecycle and page-flow evidence

The injected summary test asserts: one primary summary call; no raised
exception; a returned candidate; `finalized=True`; retained screens `0`; both
builder context references `None`; a fixed warning; and schema-valid fallback.
Weak references confirm that the screen, R05 aggregator, and R06 evaluator are
collectable once returned test references are released. A separate injected
candidate-record-construction failure verifies the same cleanup boundary.

The `simple_brush` integration regression injects the same summary failure at
the candidate finalization entry point. It saves the candidate and verifies
that OCR scrolling, human scrolling, next-candidate navigation, and refresh
spies are not invoked. Existing page-flow tests remain unchanged and pass;
there are no new OCR, screenshot, wait, click, rule, favorite, forward, ESC,
timing, or navigation calls.

Existing R06 integration coverage continues to cover normal summary output,
disabled mode, record mode, first no-reference screen, and eight-screen paths.
The full suite also covers the R05-record/R06-record and disabled combinations.

## Files changed

- `ocr_candidate.py` — whole-finalize lifecycle boundary and summary fail-open.
- `ocr_records.py` — shared pure candidate-summary count primitive only.
- `tests/test_ocr_candidate.py` — document-construction cleanup regression.
- `tests/test_ocr_similarity.py` — summary injection, immutable screen,
  fixed-warning, fallback, and weak-reference regression.
- `tests/test_simple_brush_ocr.py` — candidate save and page-action isolation.

## Verification

All commands used only synthetic fixtures and temporary test storage.

- Targeted required suites: 314 tests passed.
- `python -m unittest discover -s tests -q`: 681 tests passed.
- R04 normalization benchmark: passed.
- R05 aggregation benchmark: passed without changing its performance gate.
- R06 similarity benchmark: `required_performance_gates_pass=true`; the
  measured mandatory cases remained below 15 ms (20k cases) and 100 ms (eight
  adjacent pairs).
- `compileall`, `pip check`, and `git diff --check`: passed.

## Privacy, Git, and disposition

No real BOSS page was run. No log or run-data body was read. Before and after
testing, only inventory, size, mtime, and SHA-256 were inspected. The existing
`logs/simple_brush.log` remained 7,372,745 bytes with SHA-256
`1BE253B07B246AA1B9F3F207F5C22876FA8116A13DA13959221ECCC2AC62AF96`; the
four existing `data/ocr_runs` files remained empty with their original mtimes
and SHA-256 values.

Initial HEAD was `406f315` on `main...origin/main [ahead 6]`. Change 6 and the
blocked acceptance report are committed. This Corrective leaves the existing
untracked `README.md`, `docs/project-review.zip`, and
`venv-packages-before-reinstall.txt` untouched. No add, commit, push, tag, or
release operation was performed.

The R06 independent Change 7 acceptance remains **BLOCKED** until it is rerun
in full as a separate acceptance. This Corrective is a prerequisite repair,
not an acceptance PASS or production-record approval.
