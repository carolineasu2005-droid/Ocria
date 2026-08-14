# AM7-R01 Source Baseline Confirmation

## Confirmed source

| Field | Value |
| --- | --- |
| Source product | BossOCR |
| Source repository | `https://github.com/carolineasu2005-droid/Boss-OCR.git` |
| Branch observation | `main` = `a7c941989a038d7a998ccee707e14b4fd9125cda` |
| Baseline commit | `a7c941989a038d7a998ccee707e14b4fd9125cda` |
| Parent | `79bc98e9fac5de3ee50d081125b66f1c73aa6c61` |
| Tree | `b3ddfa62cf1673ffc59887b06517baacf9c79cd7` |
| Commit subject | `fix(focus): use safe region for candidate focus recovery` |
| Author time | `2026-08-11T21:45:20+08:00` |
| Tag / Release | `V1.3.1` / `BossOCR v1.3.1 — Final Stable Hotfix` |
| Release published | `2026-08-11T13:52:42Z` |
| ZIP | `BossOCR-Windows-x64.zip`, 123421312 bytes |
| SHA-256 | `1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9` |

## Verification conclusion

The local ZIP SHA-256, checksum-asset SHA-256, GitHub Release API ZIP digest,
and the TID 0.6 frozen SHA-256 are identical. The asset was human-downloaded
from the official V1.3.1 Release solely because the execution sandbox timed
out during large-asset transport; this did not replace any identity, size,
checksum, API, or digest verification.

All C01 automated gates passed on the immutable baseline: Full Legacy
Regression, R04/R05/R06 output contracts, compile target/compileall contract,
dependency check, and protected/workspace guards.

## Repository boundary at C01

This confirmation intentionally records the current boundary, not C02's future
target: `origin_status=absent_pending_human`, `origin_url=null`, and
`upstream_push_disabled=false`.

## Human approval

Approved by: Human Project Owner
Confirmation time: `2026-08-13T22:25:40+08:00`

This is a source-baseline confirmation. C01 itself remains subject to separate
Sol/Human Change acceptance before C02 may begin.

See `docs/am7/acceptance/evidence/AM7-R01-C01/gate-summary.md` for the
sanitized command and gate record.
