# R06 Store Screen-Digest Lifecycle Corrective

Date: 2026-08-02  
Scope: narrow corrective only; this is not a Change 7 Acceptance and does not
enable production recording.

## Finding and reproduction

The blocked independent acceptance found that a successful
`JsonlOcrRecordStore.save_screen()` cached a JSON digest, while a later
`save_candidate()` validation failure returned `False` before removing that
candidate's cached digest. Repeated failures therefore grew the in-memory
mapping by the number of saved screens.

The independent synthetic reproduction was added before the fix:

1. Create a temporary record-mode Store and a valid record-mode R06 screen.
2. Save the screen successfully.
3. Change only the candidate-embedded screen's `captured_at`; it remains a
   schema-valid screen but no longer has the saved JSON digest.
4. Save the candidate.

Before the production change, the new test failed with
`digests_after_validation_failure == 1`; candidate persistence remained empty
and `save_candidate()` returned `False`. This is the reported defect, with no
real candidate data involved.

## Corrective design

`_saved_screen_digests` is now an internal mapping from
`(run_id, candidate_record_id, screen_id)` to the SHA-256 digest of the exact
serialized screen record. It stores only identifiers and a digest, never OCR
body text or screen objects.

`_candidate_screen_digest_keys()` establishes ownership only when the document
and embedded screen agree on this Store's run and candidate identity. It does
not delete by an untrusted screen ID and it cannot release another candidate's
entry. `_release_candidate_screen_digests()` uses idempotent `pop(key, None)`
for just those keys.

`save_candidate()` obtains those keys before validation, retains the existing
validation and append result paths, and releases the owned keys in `finally`.
Consequently the terminal boundary covers all three outcomes:

| Outcome | Existing result | Digest lifecycle |
| --- | --- | --- |
| Validation and append succeed | `True`, one candidate JSONL line | Current candidate keys released |
| Screen/digest validation fails | `False`, no candidate JSONL line | Current candidate keys released |
| Candidate append raises | Existing best-effort `False` | Current candidate keys released |

`close()` also clears the in-memory mapping in its terminal `finally` block.
This covers a Store closed after saved screens but before a candidate document;
it changes neither JSONL nor manifest schema or contents. A second `close()`
and a second release remain safe.

## Invariants preserved

The corrective changes only `ocr_store.py` and `tests/test_ocr_store.py`.
They do not alter Schema, JSONL serialization, manifest fields, screen or
candidate data, R03/R04/R05/R06 results, summary/warning ordering, default
modes, or page behavior. The digest verification remains strict: a changed
`captured_at` returns `False`, writes no candidate line, and leaves the already
written screen line untouched. `save_candidate()` still returns the prior
best-effort result for validation and append failures.

## Regression evidence

New synthetic `TemporaryDirectory` tests cover:

- successful A then B candidates: A releases only A, B stays cached until B
  succeeds, and the two persisted candidate lines remain parseable;
- validation failure: no candidate line and no retained current-candidate key;
- injected candidate append `PermissionError`: no candidate partial line,
  saved screen remains, keys release, and a later candidate succeeds;
- 100 consecutive validation failures: mapping is empty after every call and
  at the end (with a failure limit chosen to keep the Store enabled);
- A validation failure alongside B's eight screens: only A releases; B may be
  saved with its embedded screen order reversed and then releases;
- duplicate or missing digest validation, repeated explicit release, and
  `close()` after an unfinalized screen: no exception and an empty mapping.

The mapping-entry assertions are the appropriate lifetime check: it has no
references to candidate documents, screens, OCR bodies, or other large
objects, and remains at zero after every failing candidate. It therefore
rules out the reported unbounded retained-entry growth.

Existing higher-level spy/mock coverage was rerun. The R06 summary fail-open
case still saves the candidate without page actions, and Store failure remains
best effort; OCR, screenshots, scroll/wait behavior, candidate switching,
rules, favorite/forward, next-candidate, ESC, and timing paths were not
changed.

## Verification

All commands used only synthetic fixtures and temporary directories:

- `python -m unittest tests.test_ocr_store -q`: 21 passed.
- `python -m unittest tests.test_ocr_store tests.test_ocr_candidate
  tests.test_ocr_similarity tests.test_simple_brush_ocr -v`: 313 passed.
- `python -m unittest discover -s tests -q`: 688 passed.
- `python -m tests.benchmark_r04_normalization`: passed; deterministic rows.
- `python -m tests.benchmark_r05_aggregation`: passed; frozen R05 gates pass
  in this run (`8x64_unique_pure` p95 16.0865 ms, retained 0.05 KiB).
- `python -m tests.benchmark_r06_similarity`: required gates pass; worst 20k
  p95 11.6709 ms, eight adjacent pairs p95 14.1757 ms, peak 246.47 KiB
  (below 16 MiB).
- `python -m compileall -q ocr_store.py ocr_candidate.py ocr_records.py tests`:
  passed.
- `python -m pip check`: `No broken requirements found.`
- `git diff --check`: passed.

No benchmark fixture, threshold, or performance gate was modified. The R05
formal final status remains `BLOCKED`; this corrective does not change the
maintainer-waiver or Acceptance status.

## Privacy, Git, and disposition

Only synthetic `TemporaryDirectory` runs were used. No real BOSS page was run
and no candidate data was read. The metadata-only before/after check found
`logs/simple_brush.log` unchanged at 7,372,745 bytes, mtime
`2026-08-01T15:15:54.4076423+08:00`, SHA-256
`1BE253B07B246AA1B9F3F207F5C22876FA8116A13DA13959221ECCC2AC62AF96`;
`data/ocr_runs` remained an empty inventory.

Baseline HEAD was `95b1ffd6de7c808de891547ba2928425a1c2eb17` on `main`
(`main...origin/main [ahead 8]`). The committed baselines include Change 6
`ce33f34`, summary-finalize corrective `a9674d8`, and the latest blocked
acceptance baseline `95b1ffd`. Prior to adding this report, the only tracked
changes were this corrective's `ocr_store.py` and `tests/test_ocr_store.py`;
pre-existing untracked files were preserved: `README.md`,
`docs/project-review.zip`, and `venv-packages-before-reinstall.txt`.

Recommendation: this narrow corrective is ready to be committed by the
maintainer and then followed by a new, complete independent R06 Change 7
Acceptance. The existing R06 Change 7 Acceptance remains `BLOCKED`; this
report does not convert it to PASS, approve production record, or authorize
production activation.
