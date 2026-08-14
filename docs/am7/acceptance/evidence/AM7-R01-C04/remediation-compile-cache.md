# AM7-R01 C04 compile-cache remediation

## Contract and prior failure

TID 0.7 authorizes diagnosis and minimal repair of the ignored Python cache
that caused the prior C05 19-target compileall attempt to fail while creating
a temporary cache file for `tests/test_am7_r01_golden_replay.py`. The original
failure remains preserved in the C05 evidence; it is not rewritten as a pass.

## Read-only diagnosis

At `2026-08-14T07:56:46+08:00`, the actual filesystem inspection found:

- `tests` existed, was not read-only, and had an administrative-group owner;
  the current authenticated operator had `Modify` access.
- `tests/__pycache__` existed, was not read-only, had a current-operator
  owner, and inherited `Modify` access for authenticated users.
- The three AM7-R01 test files existed, were not read-only, and had a
  current-operator owner with inherited `Modify` access.
- The prior temporary failure path
  `tests/__pycache__/test_am7_r01_golden_replay.cpython-311.pyc.1770425696864`
  no longer existed.
- The cache directory contained only ignored Python `.pyc` files; Git
  confirmed the cache pattern is ignored by `.gitignore`.

This shows no Python source, test source, target, or read-only-attribute
failure. The retained evidence supports a restricted execution-context
cache-write restriction rather than a compile-target problem.

## Minimal remediation

The first attempt to remove the verified ignored cache directory from the
restricted execution context received `Access denied`. The same narrow action
was then performed with the required filesystem authority:

```text
Remove-Item -LiteralPath 'tests\\__pycache__' -Recurse -Force
```

It exited `0`. No tracked file was deleted, no repository-wide permission
change was made, and no ACL was changed. The next TID-fixed compileall command
is the verification that recreates cache only as Python requires.

## Verification

At `2026-08-14T08:00:01+08:00`, the exact TID 0.7 19-target existence and
compileall contract completed with all 19 targets present, exit code `0`, no
missing-target output, and no `PermissionError`. The sanitized command,
timestamp, target list, and prior restricted-context failure are retained in
the repository-relative C03 remediation compile log.
