# AM7-R01 C01 Gate Summary

| Field | Value |
| --- | --- |
| Change | C01 — 文档版本化与 Source Baseline 锁定 |
| RPD / TID | 0.3 / Approved; 0.6 / Approved |
| Repository-relative cwd | `.` |
| Baseline commit / tree | `a7c941989a038d7a998ccee707e14b4fd9125cda` / `b3ddfa62cf1673ffc59887b06517baacf9c79cd7` |
| Verification timestamp | `2026-08-13T22:25:40+08:00` |
| Privacy review | Sanitized; no local absolute paths, OCR bodies, screenshots, credentials, or runtime logs retained |

## Gates

| Gate | Command | Result | Count / contract | Exit code |
| --- | --- | --- | --- | --- |
| Workspace precheck | `git status --short --branch`; `git status --porcelain --untracked-files=all`; `git diff --stat`; `git diff --name-only` | PASS | 0 tracked changes; 0 untracked files | 0 |
| Local source identity | `git rev-parse`; `git rev-list`; `git show`; `git cat-file`; `git diff --exit-code <baseline> -- .` | PASS | HEAD, V1.3.1, upstream main, parent, tree, time, and subject match frozen baseline | 0 |
| Remote tag / API identity | `git ls-remote`; `gh api repos/.../releases/tags/V1.3.1`; `gh api .../git/ref/tags/V1.3.1` | PASS | tag, title, timestamp, asset names and sizes match | 0 |
| Release asset four-way digest | `Get-FileHash -Algorithm SHA256`; checksum format parse; GitHub API digest compare | PASS | ZIP 123421312 bytes; checksum asset 91 bytes; four SHA-256 values identical | 0 |
| Asset transport | human-provided official V1.3.1 local copy | PASS | `human_downloaded_from_official_v1.3.1_release_due_to_sandbox_timeout` | 0 |
| Full Legacy Regression | `./venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -v` | PASS | 776 tests; failures 0; errors 0; skips 0 | 0 |
| R04 | `./venv/Scripts/python.exe -m tests.benchmark_r04_normalization` plus TID 0.6 §14.1.1 assertions | PASS | 8 scenarios; output contract PASS; `unique-100` p95 3.4932 ms; max 500-box p95 21.9885 ms | 0 |
| R05 | `./venv/Scripts/python.exe -m tests.benchmark_r05_aggregation` plus TID 0.6 §14.1.2 assertions | PASS | 18 scenarios; output contract PASS; blockers 0 | 0 |
| R06 | `./venv/Scripts/python.exe -m tests.benchmark_r06_similarity` plus TID 0.6 §14.1.3 assertions | PASS | 15 scenarios; output contract PASS; max peak 593.04 KiB | 0 |
| Compile | `./venv/Scripts/python.exe -m compileall -q <19 fixed targets>` | PASS | 19 target existence checks; 0 missing-output matches | 0 |
| Dependencies | `./venv/Scripts/python.exe -m pip check` | PASS | no broken requirements | 0 |
| Protected/workspace guard | TID 0.6 §14.4 `git diff`, whitespace, tracked/untracked/ignored checks | PASS | protected production/benchmark diff 0; existing test diff 0; deleted tracked 0; unknown ignored 0 | 0 |

## Release asset contract

| Value | SHA-256 |
| --- | --- |
| Local human-provided ZIP | `1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9` |
| Checksum asset content | `1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9` |
| GitHub Release API ZIP digest | `1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9` |
| TID 0.6 frozen digest | `1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9` |

Result: PASS — all four values are identical.
