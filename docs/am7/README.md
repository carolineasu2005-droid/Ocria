# Ocria Am7 Governance

This directory contains governed AM7-R01 baseline, acceptance, provenance, and
freeze records. C01 confirms the immutable BossOCR source baseline. C02 records
the independent Ocria repository and BossOCR upstream boundary.

Current repository-boundary state:

- `origin_status`: `configured`
- `origin_url`: `https://github.com/carolineasu2005-droid/Ocria.git`
- `upstream_remote_name`: `bossocr-upstream`
- `upstream_fetch_url`: `https://github.com/carolineasu2005-droid/Boss-OCR.git`
- `upstream_push_disabled`: `true`

The machine-readable baseline record is in
`baselines/AM7-R01-source-baseline.json`. Evidence is stored under
`acceptance/evidence/` and is limited to commands, outcomes, counts, digests,
and repository-relative paths. Human-readable source and remote provenance is
in `PROVENANCE.md`.
