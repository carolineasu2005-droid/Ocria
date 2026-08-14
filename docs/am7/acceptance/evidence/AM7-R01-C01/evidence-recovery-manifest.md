# AM7-R01 C01 Evidence Recovery Manifest

Scope: persist the missing raw C01 execution evidence only. This recovery did
not change product code, tests, benchmarks, requirements, the approved RPD/TID,
or Git/remote configuration.

Baseline identity: `a7c941989a038d7a998ccee707e14b4fd9125cda`
with tree `b3ddfa62cf1673ffc59887b06517baacf9c79cd7`.

| Gate | Evidence | Command / scope | Result |
| --- | --- | --- | --- |
| Environment and dependency | `environment.log` | Python 3.11 x64, isolated `venv`, `pip --version`, `pip freeze`, `pip check` | PASS; `pip check` exit 0 |
| Full Legacy Regression | `full-legacy-regression.log`; `full-legacy-regression.raw.log.gz.base64` | `python -m unittest discover -s tests -p 'test_*.py' -v` | PASS; exit 0; 776 tests; 0 failures; 0 errors; 0 skips |
| R04 | `r04-benchmark.json`; `r04-result.log` | `python -m tests.benchmark_r04_normalization`; TID 0.6 §14.1.1 output contract | PASS; exit 0; 8 scenarios |
| R05 | `r05-benchmark.json`; `r05-result.log` | `python -m tests.benchmark_r05_aggregation`; TID 0.6 §14.1.2 output contract | PASS; exit 0; 18 scenarios; 0 blockers |
| R06 | `r06-benchmark.json`; `r06-result.log` | `python -m tests.benchmark_r06_similarity`; TID 0.6 §14.1.3 output contract | PASS; exit 0; 15 scenarios |
| Compile targets | `compileall.log` | 19 fixed target-existence checks; `python -m compileall -q <19 fixed targets>` | PASS; exit 0; 0 missing targets; 0 missing-output matches |
| Protected/workspace guard | `workspace-guards.log` | TID 0.6 §14.4 protected diff, existing-test byte identity, whitespace, tracked/untracked/deleted/ignored classification | PASS; all command exits 0; protected diff 0; existing-test diff 0; deleted tracked 0; unknown ignored 0 |

## Release evidence retained from C01 verification

The large release ZIP was not downloaded again during evidence recovery. The
existing `gate-summary.md` records the completed C01 Release identity and
four-way digest verification:

- asset: `BossOCR-Windows-x64.zip`
- size: `123421312` bytes
- SHA-256: `1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9`
- transport: `human_downloaded_from_official_v1.3.1_release_due_to_sandbox_timeout`

All paths in this manifest are repository-relative. No release asset, local
absolute path, credential, OCR body, screenshot, or runtime data is retained.
