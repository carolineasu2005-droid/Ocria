# AM7-R01 Legacy Freeze Matrix

## Purpose

AM7-R01 keeps the confirmed BossOCR source baseline frozen while adding only
the approved Ocria Am7 identity, provenance, acceptance, and synthetic replay
barriers. This matrix is the review contract for C04 and later work.

| Zone | Frozen material | Permitted AM7-R01 exception | Verification |
| --- | --- | --- | --- |
| Source identity | Baseline commit `a7c941989a038d7a998ccee707e14b4fd9125cda`, parent, tree, tag, release identity, ZIP size and SHA-256 | C01/C02 repository metadata only | Baseline JSON, provenance, evidence digest records |
| Production Legacy | All production Python behavior, OCR/R02–R07 algorithms, parameters, thresholds, schemas, CLI semantics, control flow | C03's minimal active display/build identity strings only | Protected diff, active-brand audit, full regression |
| Existing regression suite | Existing tests, benchmark sources, expected values, fixtures | None | Byte/diff guard and regression result |
| Build and release history | Existing Release Notes source and historical documentation | C03 active archive/executable identity only; notes source remains fixed | Workflow text audit and protected diff |
| C04 barrier | No prior Golden contract | New deterministic synthetic fixture, new AM7 tests, this matrix, and pending manual checklist | Strict reader, exact expected replay equality, synthetic inventory |

## C03 exception boundary

The C03 identity exception is limited to the approved active surfaces. It does
not authorize a production refactor, test rewrite, algorithm change, schema
change, threshold change, automation behavior change, or Release Notes source
change. Historical BossOCR provenance and BOSS site identifiers remain Legacy
identifiers where they describe the upstream product or external site.

## C04 Golden barrier

The C04 Golden uses only the explicitly human-approved synthetic text inventory
recorded in `tests/fixtures/am7_r01/golden_replay_v1/README.md`. The fixture is
read strictly and replayed offline through R04, R05, R06, and R07. Expected
summary equality and canonical digests detect drift; expected values are not
regenerated during normal test execution.

## Override rule

Any required edit outside a current Change allowlist, any Legacy behavior
drift, or any attempt to alter historical expectations requires a separately
authorized Change. It is not an in-place C04 correction.
