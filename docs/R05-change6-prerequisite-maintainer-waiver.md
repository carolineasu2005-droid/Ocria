# R05 Record Mode — R06 Change 6 Technical Prerequisite Maintainer Waiver

## Decision

R05 automated final acceptance remains formally **BLOCKED** because one of five required continuous benchmark runs reported:

```text
8x64_unique_pure p95 = 22.0040 ms
formal gate = 20 ms
```

This document does not modify the R05 performance threshold and does not change the final Acceptance Report to PASS.

After reviewing the complete acceptance evidence, the maintainer approves a limited technical waiver allowing R05 record mode to serve as the automated integration prerequisite for R06 Change 6.

## Evidence considered

The final R05 re-acceptance demonstrated:

* Four of five continuous 8×64 benchmark runs passed, with p95 values between approximately 16.1 and 17.8 ms.
* One run reported a 22.0040 ms p95 result.
* All 8×256, record projection, fuzzy matching and memory gates passed.
* All contract blockers were empty.
* Determinism, reference release, disabled constructor isolation and pure/record semantic parity passed.
* 673 repository tests passed.
* Schema compatibility, fail-open behavior, Replay, Store, Builder and page-flow isolation passed.
* R05 production default remained disabled.
* No real candidate data or real BOSS page was used.

The maintainer considers the approximately 2 ms absolute overrun operationally insignificant relative to the complete BossOCR page-processing workflow. The observed failure is treated as a formal benchmark-tail exception, not evidence of a functional or practical production-latency defect.

## Approved scope

R05 record mode is approved as a technical prerequisite for R06 Change 6 only for:

* synthetic automated record-mode tests;
* Builder integration tests;
* Store and JSONL persistence tests;
* Replay equivalence tests;
* R05 and R06 combined integration tests;
* disabled-by-default production code wiring;
* fail-open and behavior-isolation verification.

## Unapproved scope

This waiver does not approve:

* changing `R05_AGGREGATION_MODE` default from `disabled`;
* changing the R06 default from `disabled`;
* real BOSS page record-mode execution;
* use of real candidate data;
* production record-mode activation;
* changing or relaxing the frozen 20 ms R05 benchmark threshold;
* declaring R05 final automated Acceptance PASS;
* ignoring new functional, memory, determinism or integration failures.

## Change 6 requirements

R06 Change 6 must:

1. Keep both R05 and R06 production defaults disabled.
2. Use synthetic fixtures for record-mode integration.
3. Preserve all existing page, OCR, scrolling, rule and action behavior.
4. Measure and report the combined R05 and R06 integration overhead.
5. Stop if integration introduces a material regression beyond the already documented isolated R05 tail-latency exception.
6. Clearly state that the R05 prerequisite was satisfied by a maintainer waiver rather than a formal R05 Acceptance PASS.
7. Avoid claiming real-page or production record-mode validation.

## Final authorization

The maintainer approves R05 record mode as the limited automated technical prerequisite for R06 Change 6 under the scope and restrictions above.

R05 final automated Acceptance remains formally BLOCKED.

R05 and R06 production defaults remain disabled.
