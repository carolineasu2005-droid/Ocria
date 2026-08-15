# AM7-R03 Acceptance Report

## 1. Metadata

| Field | Value |
| --- | --- |
| Product | Ocria |
| Generation | Am7 |
| Requirement | AM7-R03 — LLM Provider Runtime 与 Qwen / DeepSeek 接入 |
| Document | Acceptance Report |
| RPD | v0.2 — Approved / Frozen |
| TID | v0.2 — Approved / Frozen for Implementation |
| Branch | `am7-r03-llm-provider-runtime` |
| Implementation Changes | Change 1–4 |
| Status | Automated Acceptance Passed / Pending Human Final Review |

## 2. Scope Summary

- **Change 1:** Added the Provider-neutral Runtime contracts, OpenAI-compatible client configuration, Qwen/DeepSeek dispatch, `list_models()`, `complete()`, normalized results, and normalized errors.
- **Change 2:** Added non-inference `test_connection()` with R02 VERIFIED/FAILED write-back, stale protection, capability-unavailable handling, and local write-back I/O composition.
- **Change 3:** Added the staged AI Provider Configuration CLI for local editing, discovery, persistence, and explicit connection checks.
- **Change 4:** Added the startup-menu entry and return dispatch, targeted offline startup assertions, PyInstaller verification, and packaged offline smoke.

## 3. Files Changed

### Create

- `llm_provider_runtime.py`
- `ai_provider_cli.py`
- `tests/test_llm_provider_runtime.py`
- `tests/test_ai_provider_cli.py`
- `docs/AM7-R03-acceptance-report.md`

### Modify

- `requirements.txt` — added `openai>=2.53,<3.0` only.
- `simple_brush.py` — startup-menu import, option, and same-level dispatch only.
- `tests/test_simple_brush_ocr.py` — `StartupMenuTests` only.

### Conditional Modify

- `BossOCR.spec` — **not modified**. The first targeted PyInstaller build succeeded without an OpenAI SDK module or metadata collection failure.

## 4. Change 1 Evidence

- Implemented immutable public message/request/result contracts, operation and error enums, and one `LLMRuntimeError` surface.
- Qwen and DeepSeek use direct canonical-id dispatch and one configured `OpenAI` client per network operation (`timeout=120.0`, `max_retries=0`).
- `list_models()` calls `client.models.list()` exactly once, normalizes provider order and identifiers, and gives Qwen 404/405 `capability_unavailable` semantics.
- `complete()` validates locally before client construction, issues exactly one `stream=False` chat completion with no unsupported inference parameters, retries, or fallbacks.
- SDK/status/structured provider errors are normalized without API Key, headers, request bodies, or message bodies in the public error.
- Targeted Runtime suite: **37 passed, 0 failed, 0 errors, 0 skipped**.

## 5. Change 2 Evidence

- Implemented immutable `LLMConnectionTestResult` and one non-inference `test_connection()` models check.
- Successful checks write `VERIFIED`; executed remote failures write `FAILED`; both use timezone-aware UTC completion times.
- Qwen 404/405 produces `capability_unavailable` with zero write-back and no inference fallback.
- R02 stale write-back `False` is reported without overwriting current persisted configuration.
- Remote failure plus local write-back I/O failure preserves normalized remote code/status/request ID in one Runtime error; remote success plus local write-back I/O failure is reported separately as local failure.
- R02 `AIProviderConfigVerificationWriteBackTests`: **5 passed, 0 failed, 0 errors, 0 skipped**.

## 6. Change 3 Evidence

- Added `run_ai_provider_configuration(store=None)` using the existing R02 Store and `AIProviderConfig` staged snapshot.
- Save reloads current Store state and uses R02 `update()` or `save()`; incomplete Provider/API Key/Base URL configurations with no model remain supported.
- API Key input uses `getpass.getpass()` and display uses only `api_key_display()`.
- Explicit List Models stores a current-session result; empty/failure paths retain manual model entry and do not invoke inference.
- Test Connection requires confirmation, saves the connection tuple first, uses the saved snapshot, reloads after all remote/local outcomes, and distinguishes capability/stale/write-back semantics.
- Targeted CLI suite: **24 passed, 0 failed, 0 errors, 0 skipped**.

## 7. Change 4 Evidence

- The interactive startup menu now includes `3. AI Provider Configuration`; `choose_startup_action()` returns `ai_provider_config` for that selection.
- `main()` dispatches the CLI and continues to the startup menu after normal CLI return. Existing run, calibration, exit, and non-interactive semantics remain unchanged.
- Startup tests patch the CLI dispatcher and Runtime `OpenAI` constructor. Run, calibration, exit, `--auto`, `--keywords`, and `--calibration-profile` all assert zero AI CLI/client calls.
- `StartupMenuTests`: **9 passed, 0 failed, 0 errors, 0 skipped**.
- Packaged smoke A (`0`) and smoke B (`3`, `0`, `0`) both exited with code 0 without credentials or Provider operations.

## 8. Dependency Verification

| Check | Result |
| --- | --- |
| Declared direct dependency | `openai>=2.53,<3.0` |
| Resolved / imported `openai` | `2.54.0` |
| Python environment | Python 3.11.9, `F:\Ocria\venv` |
| `python -m pip check` | PASS — no broken requirements |
| Source import | PASS — `openai`, `llm_provider_runtime`, and `ai_provider_cli` imported |

## 9. Packaging Verification

| Check | Result |
| --- | --- |
| Command | `python -m PyInstaller --clean --noconfirm BossOCR.spec` |
| Result | PASS (exit 0) |
| `BossOCR.spec` change | None |
| Packaged smoke A | PASS — `"0" | .\dist\Ocria\Ocria.exe`, exit 0 |
| Packaged smoke B | PASS — `"3\n0\n0" | .\dist\Ocria\Ocria.exe`, exit 0 |

The successful build emitted non-blocking optional-dependency warnings for RapidOCR TensorRT, ONNX Runtime quantization, Tkinter, and `tzdata`. They were not OpenAI collection failures and did not prevent build or packaged smoke.

## 10. Acceptance Criteria Mapping

| AC | Status | Evidence |
| --- | --- | --- |
| AC-01 | PASS | Runtime provider-dispatch tests |
| AC-02 | PASS | Runtime/CLI consume R02 public types and Store |
| AC-03 | PASS | Direct canonical-id dispatch and unsupported-provider tests |
| AC-04 | PASS | Shared OpenAI-compatible Runtime path |
| AC-05 | PASS | DeepSeek `models.list()` Runtime tests |
| AC-06 | PASS | Qwen best-effort list and 404/405 tests |
| AC-07 | PASS | CLI empty/failure/manual model tests |
| AC-08 | PASS | Non-inference `test_connection()` tests |
| AC-09 | PASS | VERIFIED/FAILED write-back tests |
| AC-10 | PASS | R02 and Runtime stale tests |
| AC-11 | PASS | Exact `stream=False` single-call tests |
| AC-12 | PASS | Config-only Runtime input tests |
| AC-13 | PASS | Completion result extraction tests |
| AC-14 | PASS | Malformed response tests |
| AC-15 | PASS | SDK/status/provider error-mapping tests |
| AC-16 | PASS | `max_retries=0` and single-call tests |
| AC-17 | PASS | 120-second client timeout tests |
| AC-18 | PASS | Exact SDK-kwargs test excludes thinking controls |
| AC-19 | PASS | CLI suite and packaged CLI return smoke |
| AC-20 | PASS | Captured-output and `getpass` tests |
| AC-21 | PASS | Base-URL recommendation preservation tests |
| AC-22 | PASS | Startup mock assertions and packaged offline smoke |
| AC-23 | PASS | CLI never invokes `complete()` test |
| AC-24 | PASS | StartupMenuTests and minimal startup diff |
| AC-25 | PASS | Source import, PyInstaller build, packaged smoke |

Summary: **25 PASS, 0 FAIL, 0 NOT EVIDENCED**.

## 11. Test Summary

| Command | Tests run | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| `test_llm_provider_runtime.py` | 37 | 37 | 0 | 0 | 0 |
| `test_ai_provider_cli.py` | 24 | 24 | 0 | 0 | 0 |
| `AIProviderConfigVerificationWriteBackTests` | 5 | 5 | 0 | 0 | 0 |
| `StartupMenuTests` | 9 | 9 | 0 | 0 | 0 |

No full legacy suite, real Provider smoke, paid completion, archive, tag, or release flow was run.

## 12. Source Verification

| Check | Result |
| --- | --- |
| `python -m py_compile llm_provider_runtime.py ai_provider_cli.py simple_brush.py` | PASS |
| `python -c "import openai, llm_provider_runtime, ai_provider_cli; print(openai.__version__)"` | PASS — `2.54.0` |
| `python -m pip check` | PASS |
| `git diff --check` | PASS |

## 13. Scope Compliance

- Forbidden R02 implementation files and schema: not modified.
- Legacy OCR/Candidate/Screening/Action Core and `run()` business behavior: not modified.
- No automatic retry, streaming, Test Inference, Provider framework, fallback, extra Gate, Guard, or Scanner was added.
- `BossOCR.spec` was not modified because packaging evidence did not justify it.

## 14. Scope Deviations

None. The two frozen R03 RPD/TID files were already untracked in the workspace when Queue 1 began and were not modified by implementation.

## 15. Contract Conflicts

None. The existing R02 `record_connection_verification()` API expressed all required VERIFIED, FAILED, and stale semantics without schema or state changes.

## 16. Escalations

None.

## 17. Optional Real Provider Smoke

Not performed. No Provider credentials were supplied, and optional real-provider smoke is not required for automated acceptance.

## 18. Known Limitations

- Qwen discovery and non-inference connection check remain the frozen R03 v1 best-effort `models.list()` mechanism; explicit 404/405 is `capability_unavailable`.
- Streaming, retries, Provider/model fallback, thinking controls, and Test Inference are intentionally not implemented.
- Real Provider smoke was not performed.

## 19. Final Automated Acceptance Verdict

Automated Acceptance Passed.

AM7-R03 is ready for Human Final Review.

Optional real-provider smoke was not performed and is not required for automated acceptance.
