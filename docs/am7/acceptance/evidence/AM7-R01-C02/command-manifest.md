# AM7-R01 C02 Command Manifest

Change: C02 — Provenance 与独立 Repository / Remote Boundary

Approved Ocria origin: `https://github.com/carolineasu2005-droid/Ocria.git`

This manifest permits only local read-only Git inspection, the C02-local
configuration of `origin` and `bossocr-upstream.pushurl`, metadata/provenance
documentation, and C02 verification. It contains no `git push`, `gh repo
create`, GitHub release, upload, commit, tag, merge, rebase, or reset command.

Expected command categories:

- repository status, diff, remote, URL-rewrite, and ancestor inspection;
- `git remote set-url --push bossocr-upstream no_push://bossocr-upstream`;
- `git remote add origin https://github.com/carolineasu2005-droid/Ocria.git`
  only when the before-audit establishes that `origin` is absent;
- post-configuration remote and metadata verification;
- whitespace and allowed-file scope inspection.

Forbidden command count in this C02 manifest:

| Command category | Count |
| --- | ---: |
| `git push` | 0 |
| `gh repo create` | 0 |
| release or upload | 0 |
| commit, tag, merge, rebase, reset | 0 |
