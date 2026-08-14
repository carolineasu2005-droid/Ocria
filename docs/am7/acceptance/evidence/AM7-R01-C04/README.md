# AM7-R01 C04 Evidence

Repository-relative, sanitized C04 evidence. It contains commands, timestamps,
exit codes, counts, digests, results, and approved synthetic fixture inventory;
it does not retain real OCR data, screenshots, credentials, or local absolute
paths.

| Evidence | Purpose | Result |
| --- | --- | --- |
| `initial-audit.log` | C03/C02/baseline starting-state review | Carry-forward recorded |
| `critical-52.log` | Exact TID §14.2 Critical 52 | PASS — 52, 0 failures/errors/skips |
| `full-legacy-regression.log` | Full suite sanitized command/count/failure summary | FAIL — 783, 1 failure, 0 errors/skips |
| `r04-benchmark.json`, `r04-result.log` | R04 raw JSON and contract | PASS — 8 scenarios |
| `r05-result.log` | R05 contract result | PASS — 18 scenarios; raw JSON was not durably captured |
| `r06-benchmark.json`, `r06-result.log` | R06 raw JSON and contract | PASS — 15 scenarios |
| `compileall.log` | 19-target existence/compile contract | PASS |
| `environment.log` | Isolated dependency check | PASS |
| `synthetic-fixture-inventory.md` | Semantic synthetic review | PASS |
| `protected-workspace-diff.log` | Protected/diff/whitespace classification | Partial; see carry-forward |

The Full failure is an existing test's `BossOCR` menu-text assertion after the
C03 active identity changed that text to `Ocria Am7`. C04 did not alter that
existing test or any production behavior. The R05 raw JSON evidence gap is an
execution-capture omission; it is not fabricated and the benchmark is not
rerun merely to obtain a prettier log.
