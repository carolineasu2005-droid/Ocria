# AM7-R01 Manual Real BOSS Page Smoke Checklist

Smoke ID: AM7-R01-MS

Status: Passed

Human executor: Human Project Owner

Human approver: Human Project Owner

Execution time: Not recorded

Ocria commit/tree: Not recorded

Build SHA-256: 2B10840E8B7B58B05262A2851C6BEDC04BBD23261E68E2C88638C0DE82F513B0

Windows/browser: Not recorded

Resolution/DPI: Not recorded

Calibration profile identifier: Not recorded

BOSS account authorization: Not recorded

Test object classification: Not recorded

Sensitive evidence confirmation: Pass — Human Project Owner confirmation;
details not recorded. Do not store candidate body, name, phone, email, account
detail, screenshot, credential, or real OCR text in the repository.

This is a human-only checklist. AM7-R01 automated work has not performed any
step, logged in, selected a candidate, opened a real page, favorited, or
forwarded. Record each result as `Pass`, `Fail`, `Blocked`, or `Not Run`.
Evidence references must be sanitized summaries kept outside repository when
they could identify a person or account.

| ID | Preconditions | Human action | Expected | Result | Evidence ref | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| MS-01 | Reviewed unpacked Ocria build; approved isolated session | Start `Ocria.exe`. | Console/start menu displays `Ocria Am7`, not BossOCR Stable. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-02 | Approved controlled BOSS page and browser session | Select a valid calibration profile and enter the controlled page. | Chrome is preferred; Edge is fallback; focus action targets the intended window only. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-03 | Controlled candidate detail is available | Open the controlled detail. | Load gate completes before OCR; incomplete load performs no favorite/forward action. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-04 | Non-matching controlled rule; no business action authorized | Run one candidate. | Multi-screen OCR/scroll is observable; no business action; normal next behavior. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-05 | Controlled session | Verify Space pause/resume and ESC stop. | Pause issues no new navigation/action; ESC follows existing finalization and safe stop. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-06 | `--no-forward`; controlled matching rule | Run the controlled rule. | A match never calls real forward or favorite. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-07 | Human selects `controlled-real` or pre-approved equivalent | Verify the favorite path. | Favorite only, no forward; shared focus restore and next-candidate behavior verified. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-08 | Human selects `controlled-real` or pre-approved equivalent; controlled recipient | Verify the forward path. | Legacy confirmation and forward path; shared focus restore and next-candidate behavior verified. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-09 | Approved safe-failure condition | Observe a missing target window or cancel calibration. | Fail-closed; no unintended business action; no OCR body in error evidence. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-10 | Controlled batch-filter scope | Verify batch filter and first-candidate opening; optionally one approved refresh recovery. | V1.3.1 ordering is retained; no requirement to browse unrelated candidates. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-11 | Local Stage-0 output is available to the human only | Review the four local run files without committing them. | Contract is readable; candidate finalizes once; no unexplained schema drift. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |
| MS-12 | Baseline and Ocria observations available to reviewer | Perform human observable-difference review. | No unapproved observable difference beyond Ocria Am7 display/artifact identity. | Pass | Human Project Owner confirmation; sanitized details not recorded | Not recorded |

Human Project Owner confirms MS-01 through MS-12 passed. This checklist records
only the authorized final result; unspecified execution metadata remains Not
recorded, and sensitive evidence remains outside the repository.
