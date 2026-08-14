# Ocria Am7 Provenance

## Source baseline

Ocria Am7 is a history-preserving derived repository of BossOCR at the confirmed
source baseline below:

| Field | Value |
| --- | --- |
| Source product | BossOCR |
| Source repository | `https://github.com/carolineasu2005-droid/Boss-OCR.git` |
| Source branch | `main` |
| Baseline commit | `a7c941989a038d7a998ccee707e14b4fd9125cda` |
| Baseline tree | `b3ddfa62cf1673ffc59887b06517baacf9c79cd7` |
| Source tag | `V1.3.1` |

The machine-readable source record is
[`baselines/AM7-R01-source-baseline.json`](baselines/AM7-R01-source-baseline.json).

## Product-line boundary

Ocria is the Am7 development mainline. BossOCR remains an independently
maintained Legacy Stable product and a manual product-line fallback. Ocria does
not promise an automatic runtime fallback to BossOCR.

Subsequent Ocria commits belong only to the Ocria product line. AM7-R01 does
not rewrite BossOCR history, create a subtree/submodule/squash import, or set up
bidirectional synchronization.

## Remote boundary

| Remote | Purpose | Fetch URL | Push rule |
| --- | --- | --- | --- |
| `origin` | Human-approved independent Ocria repository | `https://github.com/carolineasu2005-droid/Ocria.git` | Ocria changes only; this C02 performed no push |
| `bossocr-upstream` | BossOCR source verification and future human-reviewed comparison | `https://github.com/carolineasu2005-droid/Boss-OCR.git` | Disabled locally with `no_push://bossocr-upstream` |

To verify the current local boundary without contacting either remote:

```powershell
git remote -v
git remote get-url origin
git remote get-url bossocr-upstream
git remote get-url --push bossocr-upstream
git merge-base --is-ancestor a7c941989a038d7a998ccee707e14b4fd9125cda HEAD
```

`bossocr-upstream` is fetch-only for AM7 automation and implementation work.
Do not push to it. The `no_push://bossocr-upstream` push URL is a local safety
boundary; this document and the baseline metadata provide the cloneable record
of that boundary.

## C02 evidence

Repository-relative C02 command evidence is stored in
[`acceptance/evidence/AM7-R01-C02/`](acceptance/evidence/AM7-R01-C02/).
It records the approved URL, before/after remote state, URL-rewrite audit,
baseline ancestry, and the zero-push command manifest. It contains no
credentials or local absolute paths.
