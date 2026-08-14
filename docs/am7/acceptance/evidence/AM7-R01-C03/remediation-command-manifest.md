# AM7-R01 C03 remediation command manifest

Repository-relative, sanitized evidence for the TID 0.7 remediation queue.
No credentials, real BOSS-page content, candidate data, screenshots, local
absolute paths, host names, or user names are retained.

| Timestamp (Asia/Shanghai) | Scope | Command / action | Exit | Result |
| --- | --- | --- | --- | --- |
| 2026-08-14T07:56:46+08:00 | TID 0.7 C03/C04 remediation preflight | Read-only owner, ACL, attribute, and cache-state inspection of `tests`, `tests/__pycache__`, and the three AM7 test files | 0 | Completed; see C04 remediation record |
| 2026-08-14T07:56:46+08:00..2026-08-14T07:59:34+08:00 | C03 exact existing-test migration | `rg -n -F` located exactly one `开始运行 BossOCR` expectation in the authorized StartupMenu test method | 0 | Precondition passed |
| 2026-08-14T07:56:46+08:00..2026-08-14T07:59:34+08:00 | C03 exact existing-test migration | Replaced only `开始运行 BossOCR` with `开始运行 Ocria Am7` in `tests/test_simple_brush_ocr.py` | 0 | Completed; exact post-change diff is retained in `remediation-startup-assertion.diff` |
| 2026-08-14T07:56:46+08:00..2026-08-14T07:59:34+08:00 | C04 ignored cache recovery | Restricted removal returned `Access denied`; the same verified ignored `tests/__pycache__` directory was then removed with narrow filesystem authority | 0 | Completed; no tracked file or ACL changed |
| 2026-08-14T08:00:01+08:00 | TID 0.7 19-target compile contract | Exact fixed target list, existence check, then `python -m compileall -q` | 0 | PASS; 19 present, no PermissionError |
| 2026-08-14T08:00:54+08:00 | Targeted StartupMenu regression | Fixed qualified test name from the remediation authorization | 0 | PASS; 1 test, 0 failures/errors/skips |
| 2026-08-14T08:01:36+08:00 | TID 0.7 Critical 52 | Exact fixed qualified-name list | 0 | PASS; 52 tests, 0 failures/errors/skips |
| 2026-08-14T08:01:58+08:00 | TID 0.7 Full Legacy Regression | `python -m unittest discover -s tests -p 'test_*.py' -v` | 0 | PASS; 783 tests, 0 failures/errors/skips |
| 2026-08-14T08:03:51+08:00 | TID 0.7 protected/existing-test/whitespace guard | Fixed protected paths, frozen existing tests, exact startup hunk checks, and whitespace checks | 0 | PASS |

The remediation begins from baseline commit
`a7c941989a038d7a998ccee707e14b4fd9125cda` and tree
`b3ddfa62cf1673ffc59887b06517baacf9c79cd7`. It is governed by RPD 0.3 /
Approved and TID 0.7 / Approved. It does not run C05, benchmarks, build,
smoke, packaging, or real-page actions.

The first shell attempt to write a remediation log was denied by the restricted
execution context before the test was executed, and its `Tee-Object` invocation
was also incompatible with this PowerShell version. That infrastructure attempt
is retained here rather than presented as a test result. The subsequent test,
Critical, Full, and compile records are based only on their observed results;
local absolute dependency paths emitted by test diagnostics are omitted.
