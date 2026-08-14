# AM7-R01 C01 Evidence Index

All evidence in this directory is sanitized. It contains commands, exit codes,
counts, immutable Git identifiers, digests, and repository-relative paths only.
No release asset, local absolute path, credential, OCR body, screenshot, or
unredacted runtime log is stored here.

| Evidence | Purpose |
| --- | --- |
| `gate-summary.md` | Source identity, Release asset, regression, benchmark, compile, dependency, and workspace guard outcomes |
| `environment.log` | Python 3.11 x64, isolated environment, and `pip check` command output |
| `full-legacy-regression.log` | Full Legacy Regression command, timing, exit code, and test outcome |
| `full-legacy-regression.raw.log.gz.base64` | Gzip/base64 UTF-8 capture of the Full Legacy Regression stdout/stderr |
| `r04-benchmark.json`, `r04-result.log` | R04 raw JSON and TID 0.6 output-contract result |
| `r05-benchmark.json`, `r05-result.log` | R05 raw JSON and TID 0.6 output-contract result |
| `r06-benchmark.json`, `r06-result.log` | R06 raw JSON and TID 0.6 output-contract result |
| `compileall.log` | Fixed-target existence checks and `compileall` output contract |
| `workspace-guards.log` | TID 0.6 §14.4 protected diff, whitespace, and workspace classification output |
| `evidence-recovery-manifest.md` | Recovery scope and an index of the persisted execution evidence |

Asset transport method: `human_downloaded_from_official_v1.3.1_release_due_to_sandbox_timeout`.
