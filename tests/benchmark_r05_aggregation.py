"""Repeatable, contract-audited synthetic R05 aggregation benchmark.

This module performs no OCR invocation, screenshot, page action, Store write,
network access, or fixture persistence.  It never prints synthetic body text.
Fixture construction, diagnostics, timing, and tracemalloc are deliberately
separate so every reported timing has one explicit scope.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import gc
import hashlib
import json
import platform
import random
import statistics
import sys
import time
import tracemalloc
from typing import Any, Callable, Optional, Sequence, Tuple
import weakref
from unittest.mock import patch

import ocr_aggregation as aggregation_module
from ocr_aggregation import (
    AGGREGATION_CONFIG_VERSION,
    AGGREGATION_VERSION,
    DEFAULT_OCR_AGGREGATION_CONFIG,
    CandidateDocumentAggregator,
    OcrAggregationConfig,
    aggregation_config_digest,
    aggregation_screen_record_fields,
)
from ocr_candidate import CandidateOcrBuilder
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_records import (
    AggregationStatus,
    CaptureStatus,
    CaptureType,
    OcrScreenRecord,
)
from ocr_text import OCRItem


SEED = 20260801
WARMUP_RUNS = 3
REFERENCE_RUNS = 1
RUNS = 25
P95_METHOD = "statistics.quantiles(n=20, method=inclusive)[18]"
GC_POLICY = "collect_before_each_sample_then_disable_during_timed_operation"
FIXTURE_GENERATOR_VERSION = "r05-benchmark-contract-unique-v2"
_TIMESTAMP = "2026-08-01T12:00:00+08:00"


def percentile_95(values: Sequence[float]) -> float:
    """Return the inclusive linear 95th percentile used by this benchmark."""

    samples = tuple(values)
    if len(samples) < 2:
        raise ValueError("p95 requires at least two samples")
    return statistics.quantiles(samples, n=20, method="inclusive")[18]


def _unique_text(number: int, width: int = 64) -> str:
    """Return deterministic text that is exact- and fuzzy-distinct by design."""

    seed = "r05-segment-{0:08d}".format(number).encode("ascii")
    value = hashlib.sha512(seed).hexdigest()
    if not 1 <= width <= len(value):
        raise ValueError("synthetic text width is out of range")
    return value[:width]


def _unique_series(segment_count: int, width: int = 64) -> Tuple[Tuple[str, ...], ...]:
    return tuple(
        tuple(
            _unique_text(screen * segment_count + offset, width)
            for offset in range(segment_count)
        )
        for screen in range(8)
    )


def _overlap_series(
    segment_count: int,
    overlap: int,
    width: int = 64,
) -> Tuple[Tuple[str, ...], ...]:
    if not 0 <= overlap <= segment_count:
        raise ValueError("synthetic overlap is out of range")
    increment = segment_count - overlap
    return tuple(
        tuple(
            _unique_text(screen * increment + offset, width)
            for offset in range(segment_count)
        )
        for screen in range(8)
    )


def _make_records(
    screens: Sequence[Sequence[str]],
    *,
    candidate_id: str = "benchmark-candidate",
) -> Tuple[OcrScreenRecord, ...]:
    """Build immutable R04 records outside every timed aggregation section."""

    source = CandidateOcrBuilder(
        "benchmark-run",
        1,
        candidate_record_id=candidate_id,
        created_at=_TIMESTAMP,
        aggregation_mode="disabled",
        similarity_mode="disabled",
    )
    records = []
    for screen_index, texts in enumerate(screens, 1):
        screen_id = "benchmark-screen-{0:02d}".format(screen_index)
        items = tuple(
            OCRItem(
                text,
                0.99,
                (
                    (0, order * 20),
                    (480, order * 20),
                    (480, order * 20 + 12),
                    (0, order * 20 + 12),
                ),
            )
            for order, text in enumerate(texts)
        )
        normalization = normalize_ocr_text(
            tuple(
                NormalizationBox(
                    "{0}:box:{1}".format(screen_id, order),
                    item.text,
                    item.box,
                    order,
                    item.confidence,
                )
                for order, item in enumerate(items)
            )
        )
        records.append(
            source.build_screen_record(
                items,
                capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True,
                screen_index=screen_index,
                screen_id=screen_id,
                captured_at=_TIMESTAMP,
                normalization=normalization,
                ocr_min_confidence=0.85,
            )
        )
    return tuple(records)


def _pure_run(
    records: Sequence[OcrScreenRecord],
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
):
    aggregator = CandidateDocumentAggregator(
        "benchmark-run",
        "benchmark-candidate",
        config=config,
    )
    for record in records:
        aggregator.add_screen(record)
    return aggregator.finalize(CaptureStatus.COMPLETED)


def _record_run(
    records: Sequence[OcrScreenRecord],
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
):
    builder = CandidateOcrBuilder(
        "benchmark-run",
        1,
        candidate_record_id="benchmark-candidate",
        created_at=_TIMESTAMP,
        aggregation_mode="record",
        aggregation_config=config,
        similarity_mode="disabled",
    )
    for record in records:
        builder.add_screen(record)
    return builder.finalize(
        CaptureStatus.COMPLETED,
        end_reason="benchmark",
        completed_at=_TIMESTAMP,
    )


def _run_gc_isolated(operation: Callable[[], Any]) -> Tuple[Any, float]:
    gc.collect()
    was_enabled = gc.isenabled()
    if was_enabled:
        gc.disable()
    started = time.perf_counter_ns()
    try:
        value = operation()
    finally:
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        if was_enabled:
            gc.enable()
    return value, elapsed_ms


def _measure(operation: Callable[[], Any], runs: int = RUNS) -> dict[str, Any]:
    if runs < 2:
        raise ValueError("benchmark requires at least two timed samples")
    if tracemalloc.is_tracing():
        raise RuntimeError("tracemalloc must be disabled during timing")

    for _ in range(WARMUP_RUNS):
        value, _ = _run_gc_isolated(operation)
        del value
    expected, _ = _run_gc_isolated(operation)

    durations = []
    deterministic = True
    for _ in range(runs):
        value, elapsed_ms = _run_gc_isolated(operation)
        durations.append(elapsed_ms)
        deterministic = deterministic and value == expected
        del value

    gc.collect()
    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    memory_value = operation()
    _, peak = tracemalloc.get_traced_memory()
    del memory_value
    gc.collect()
    retained, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del expected
    return {
        "timed_iterations": runs,
        "p50_ms": round(statistics.median(durations), 4),
        "p95_ms": round(percentile_95(durations), 4),
        "min_ms": round(min(durations), 4),
        "max_ms": round(max(durations), 4),
        "peak_kib": round(max(0, peak - baseline) / 1024.0, 2),
        "retained_kib": round(max(0, retained - baseline) / 1024.0, 2),
        "deterministic": deterministic,
    }


def _fuzzy_records(shape: str) -> Tuple[OcrScreenRecord, ...]:
    source = "".join(chr(0x4E00 + index) for index in range(96))
    if shape == "1_to_1":
        screens = ((source,), (source[:-1] + "z",))
    elif shape == "1_to_2":
        screens = ((source,), (source[:48], source[48:]))
    elif shape == "2_to_1":
        screens = ((source[:48], source[48:]), (source,))
    elif shape == "uncertain":
        screens = ((source[:-6] + "UVWXYZ",), (source[:-3] + "XYZ",))
    else:
        raise ValueError("unsupported fuzzy benchmark shape")
    return _make_records(screens)


def _near_duplicate_fuzzy_records() -> Tuple[OcrScreenRecord, ...]:
    def near_text(number: int) -> str:
        prefix = "r05{0:06d}".format(number)
        return (prefix + ("x" * 64))[:64]

    return _make_records(
        tuple(
            tuple(near_text(screen * 64 + offset) for offset in range(64))
            for screen in range(8)
        )
    )


def _historical_records(ambiguous: bool = False) -> Tuple[OcrScreenRecord, ...]:
    values = tuple(_unique_text(10000 + index, 36) for index in range(6))
    first = values + (values[1:3] if ambiguous else ())
    second = (values[4], values[5], values[0], values[1], values[2], values[3])
    return _make_records((first, second))


@dataclass(frozen=True)
class Scenario:
    name: str
    records: Tuple[OcrScreenRecord, ...]
    mode: str = "pure"
    timing_scope: str = "aggregate_add_screen_plus_finalize"
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG
    p95_limit_ms: Optional[float] = None
    memory_limit_mib: Optional[float] = 32.0
    contract: str = "no_stage_failure"

    def operation(self) -> Callable[[], Any]:
        if self.mode == "record":
            return lambda: _record_run(self.records, self.config)
        return lambda: _pure_run(self.records, self.config)


def _diagnose(scenario: Scenario) -> dict[str, Any]:
    counters = {
        "exact_calls": 0,
        "exact_candidate_k_comparisons": 0,
        "exact_matched_segments": 0,
        "fuzzy_calls": 0,
        "fuzzy_candidates": 0,
        "fuzzy_group_scores": 0,
        "historical_calls": 0,
        "historical_lookups": 0,
        "historical_matched_segments": 0,
    }
    original_exact = aggregation_module._find_exact_boundary_overlap_validated
    original_fuzzy = aggregation_module._find_fuzzy_boundary_overlap_validated
    original_tilings = aggregation_module.enumerate_fuzzy_tilings
    original_score = aggregation_module._score_fuzzy_group_for_search
    original_historical = aggregation_module._classify_historical_duplicates_validated
    original_positions = aggregation_module.HistoricalSequenceIndex.positions

    def exact(document, current, config, identity):
        counters["exact_calls"] += 1
        result = original_exact(document, current, config, identity)
        maximum = min(len(document), len(current), config.max_screen_segments)
        counters["exact_candidate_k_comparisons"] += (
            maximum - len(result.matched_current_segment_ids) + 1
            if result.accepted
            else maximum
        )
        counters["exact_matched_segments"] += len(result.matched_current_segment_ids)
        return result

    def fuzzy(document, current, config, identity):
        counters["fuzzy_calls"] += 1
        return original_fuzzy(document, current, config, identity)

    def tilings(document_count, current_count):
        result = original_tilings(document_count, current_count)
        counters["fuzzy_candidates"] += len(result)
        return result

    def score(*args, **kwargs):
        counters["fuzzy_group_scores"] += 1
        return original_score(*args, **kwargs)

    def historical(document, current, index, config, match_order_offset, identity):
        counters["historical_calls"] += 1
        result = original_historical(
            document,
            current,
            index,
            config,
            match_order_offset,
            identity,
        )
        counters["historical_matched_segments"] += len(
            result.matched_current_segment_ids
        )
        return result

    def positions(index, key):
        counters["historical_lookups"] += 1
        return original_positions(index, key)

    with (
        patch.object(
            aggregation_module,
            "_find_exact_boundary_overlap_validated",
            exact,
        ),
        patch.object(
            aggregation_module,
            "_find_fuzzy_boundary_overlap_validated",
            fuzzy,
        ),
        patch.object(aggregation_module, "enumerate_fuzzy_tilings", tilings),
        patch.object(
            aggregation_module,
            "_score_fuzzy_group_for_search",
            score,
        ),
        patch.object(
            aggregation_module,
            "_classify_historical_duplicates_validated",
            historical,
        ),
        patch.object(
            aggregation_module.HistoricalSequenceIndex,
            "positions",
            positions,
        ),
    ):
        if scenario.mode == "record":
            builder = CandidateOcrBuilder(
                "benchmark-run",
                1,
                candidate_record_id="benchmark-candidate",
                created_at=_TIMESTAMP,
                aggregation_mode="record",
                aggregation_config=scenario.config,
                similarity_mode="disabled",
            )
            for record in scenario.records:
                builder.add_screen(record)
            aggregator = builder._aggregator
            if aggregator is None:
                raise AssertionError("record diagnostic aggregator is missing")
            screen_results = tuple(
                aggregator._screen_results[record.screen_id]
                for record in scenario.records
                if record.screen_id in aggregator._screen_results
            )
            index_entries = sum(len(value) for value in aggregator._index._keys.values())
            final = builder.finalize(
                CaptureStatus.COMPLETED,
                end_reason="benchmark",
                completed_at=_TIMESTAMP,
            )
            document_segments = final.document_segments
            document_status = final.document_build_status.value
            final_warnings = final.aggregation_warning_codes
            final_risk = (
                None
                if final.aggregation_duplicate_risk is None
                else final.aggregation_duplicate_risk.value
            )
        else:
            aggregator = CandidateDocumentAggregator(
                "benchmark-run",
                "benchmark-candidate",
                config=scenario.config,
            )
            screen_results = tuple(
                aggregator.add_screen(record) for record in scenario.records
            )
            index_entries = sum(len(value) for value in aggregator._index._keys.values())
            final = aggregator.finalize(CaptureStatus.COMPLETED)
            document_segments = final.document_segments
            document_status = final.document_build_status.value
            final_warnings = final.aggregation_warning_codes
            final_risk = final.aggregation_duplicate_risk.value

    stage_warnings = tuple(
        dict.fromkeys(
            warning
            for result in screen_results
            for warning in result.warning_codes
        )
    )
    matched = sum(len(result.matched_segment_ids) for result in screen_results)
    new = sum(len(result.new_segment_ids) for result in screen_results)
    uncertain = sum(len(result.uncertain_segment_ids) for result in screen_results)
    input_segments = sum(len(record.segments) for record in scenario.records)
    accepted_segments = sum(
        len(record.segments)
        for record, result in zip(scenario.records, screen_results)
        if result.status != AggregationStatus.FAILED
    )
    diagnostic = {
        "formal_screen_count": sum(
            record.capture_type == CaptureType.FORMAL_SCREEN
            and record.is_formal_screen
            for record in scenario.records
        ),
        "input_screen_segment_count": input_segments,
        "accepted_screen_segment_count": accepted_segments,
        "document_segment_count": len(document_segments),
        "matched_segment_count": matched,
        "new_segment_count": new,
        "uncertain_segment_count": uncertain,
        "stage_warning_codes": stage_warnings,
        "screen_statuses": tuple(result.status.value for result in screen_results),
        "final_document_status": document_status,
        "aggregation_duplicate_risk": final_risk,
        "historical_index_entry_count": index_entries,
        **counters,
    }
    diagnostic["contract_ok"] = _contract_ok(
        scenario,
        diagnostic,
        tuple(final_warnings),
    )
    return diagnostic


def _contract_ok(
    scenario: Scenario,
    diagnostic: dict[str, Any],
    final_warnings: Tuple[str, ...],
) -> bool:
    stage_failed = any(
        warning.endswith("_stage_failed")
        for warning in diagnostic["stage_warning_codes"]
    )
    if stage_failed:
        return False
    if scenario.contract == "all_unique":
        return (
            diagnostic["matched_segment_count"] == 0
            and diagnostic["uncertain_segment_count"] == 0
            and diagnostic["new_segment_count"]
            == diagnostic["input_screen_segment_count"]
            and diagnostic["document_segment_count"]
            == diagnostic["input_screen_segment_count"]
            and diagnostic["final_document_status"] == "completed"
            and not final_warnings
        )
    if scenario.contract == "fuzzy_uncertain":
        return (
            diagnostic["uncertain_segment_count"] > 0
            and diagnostic["final_document_status"] == "partial"
        )
    if scenario.contract == "segment_limit_fail_open":
        return (
            diagnostic["accepted_screen_segment_count"]
            == diagnostic["input_screen_segment_count"]
            and diagnostic["uncertain_segment_count"]
            == diagnostic["input_screen_segment_count"]
            and diagnostic["document_segment_count"]
            == diagnostic["input_screen_segment_count"]
            and diagnostic["final_document_status"] == "partial"
            and "screen_segment_limit_exceeded"
            in diagnostic["stage_warning_codes"]
        )
    return diagnostic["final_document_status"] in ("completed", "partial")


def _measure_scenario(scenario: Scenario) -> dict[str, Any]:
    diagnostic = _diagnose(scenario)
    measured = _measure(scenario.operation())
    p95_pass = (
        None
        if scenario.p95_limit_ms is None
        else measured["p95_ms"] <= scenario.p95_limit_ms
    )
    memory_pass = (
        None
        if scenario.memory_limit_mib is None
        else measured["peak_kib"] <= scenario.memory_limit_mib * 1024.0
    )
    return {
        "scenario": scenario.name,
        "timing_scope": scenario.timing_scope,
        "mode": scenario.mode,
        "aggregation_config_version": scenario.config.aggregation_config_version,
        "aggregation_config_digest": aggregation_config_digest(scenario.config),
        "p95_limit_ms": scenario.p95_limit_ms,
        "p95_pass": p95_pass,
        "memory_limit_mib": scenario.memory_limit_mib,
        "memory_pass": memory_pass,
        **diagnostic,
        **measured,
    }


def _reference_release_check(records: Sequence[OcrScreenRecord]) -> bool:
    references = []
    for index in range(100):
        candidate_id = "release-{0}".format(index)
        aggregator = CandidateDocumentAggregator("benchmark-run", candidate_id)
        for record in records:
            rebound = record.__class__.from_dict(
                {**record.to_dict(), "candidate_record_id": candidate_id}
            )
            aggregator.add_screen(rebound)
        aggregator.finalize(CaptureStatus.COMPLETED)
        references.append(weakref.ref(aggregator))
        del aggregator
    gc.collect()
    return all(reference() is None for reference in references)


def _disabled_does_not_construct_aggregator(
    records: Sequence[OcrScreenRecord],
) -> bool:
    with patch("ocr_candidate.CandidateDocumentAggregator") as constructor:
        builder = CandidateOcrBuilder(
            "benchmark-run",
            1,
            candidate_record_id="benchmark-candidate",
            created_at=_TIMESTAMP,
            aggregation_mode="disabled",
            similarity_mode="disabled",
        )
        for record in records:
            builder.add_screen(record)
        builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="benchmark",
            completed_at=_TIMESTAMP,
        )
    return not constructor.called


def _record_semantics_equal(records: Sequence[OcrScreenRecord]) -> bool:
    aggregator = CandidateDocumentAggregator("benchmark-run", "benchmark-candidate")
    projected = []
    for record in records:
        result = aggregator.add_screen(record)
        projected.append(aggregation_screen_record_fields(record, result))
    pure = aggregator.finalize(CaptureStatus.COMPLETED)
    integrated = _record_run(records)
    screen_equal = all(
        all(getattr(screen, name) == value for name, value in fields.items())
        for screen, fields in zip(integrated.screens, projected)
    )
    return screen_equal and (
        integrated.document_segments == pure.document_segments
        and integrated.document_text == pure.document_text
        and integrated.document_build_status == pure.document_build_status
        and integrated.aggregation_warning_codes == pure.aggregation_warning_codes
        and integrated.aggregation_duplicate_risk == pure.aggregation_duplicate_risk
    )


def _cpu_model() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def _scenario_catalog() -> Tuple[Scenario, ...]:
    unique_64 = _make_records(_unique_series(64))
    unique_128 = _make_records(_unique_series(128))
    unique_256 = _make_records(_unique_series(256))
    exact_50 = _make_records(_overlap_series(64, 32))
    exact_90 = _make_records(_overlap_series(64, 58))
    duplicate = _make_records(_overlap_series(64, 64))
    one_new = _make_records(_overlap_series(64, 63))
    maximum_exact_50 = _make_records(_overlap_series(256, 128))
    over_limit = _make_records(
        (tuple(_unique_text(index, 40) for index in range(257)),)
    )
    candidate_limit_config = OcrAggregationConfig(fuzzy_candidate_limit=1)
    candidate_limit = _make_records(
        (
            (_unique_text(1, 48), _unique_text(2, 48)),
            (_unique_text(3, 48), _unique_text(4, 48)),
        )
    )
    return (
        Scenario(
            "8x64_unique_pure",
            unique_64,
            p95_limit_ms=20.0,
            memory_limit_mib=16.0,
            contract="all_unique",
        ),
        Scenario("8x128_unique_pure", unique_128, contract="all_unique"),
        Scenario(
            "8x256_unique_pure",
            unique_256,
            p95_limit_ms=150.0,
            contract="all_unique",
        ),
        Scenario(
            "8x64_unique_record_projection_candidate_finalize",
            unique_64,
            mode="record",
            timing_scope=(
                "builder_add_screen_projection_validation_plus_candidate_finalize"
            ),
            p95_limit_ms=30.0,
            contract="all_unique",
        ),
        Scenario("8x64_exact_50_percent", exact_50),
        Scenario("8x64_exact_90_percent", exact_90),
        Scenario("complete_screen_duplicate", duplicate),
        Scenario("one_new_line_per_screen", one_new),
        Scenario(
            "single_screen_fuzzy_1_to_1",
            _fuzzy_records("1_to_1"),
            p95_limit_ms=50.0,
        ),
        Scenario(
            "single_screen_fuzzy_1_to_2",
            _fuzzy_records("1_to_2"),
            p95_limit_ms=50.0,
        ),
        Scenario(
            "single_screen_fuzzy_2_to_1",
            _fuzzy_records("2_to_1"),
            p95_limit_ms=50.0,
        ),
        Scenario(
            "single_screen_fuzzy_uncertain",
            _fuzzy_records("uncertain"),
            p95_limit_ms=50.0,
            contract="fuzzy_uncertain",
        ),
        Scenario(
            "8x64_near_duplicate_fuzzy_stress",
            _near_duplicate_fuzzy_records(),
        ),
        Scenario("historical_n_minus_2", _historical_records()),
        Scenario("historical_ambiguous", _historical_records(True)),
        Scenario("8x256_exact_50_percent", maximum_exact_50),
        Scenario(
            "fuzzy_candidate_limit_1_contract",
            candidate_limit,
            config=candidate_limit_config,
        ),
        Scenario(
            "257_segment_limit_contract",
            over_limit,
            p95_limit_ms=None,
            memory_limit_mib=None,
            contract="segment_limit_fail_open",
        ),
    )


def _ordered_scenarios(
    scenarios: Sequence[Scenario],
    order: str,
) -> Tuple[Scenario, ...]:
    values = list(scenarios)
    if order == "declared":
        return tuple(values)
    if order == "unique_last":
        target = next(item for item in values if item.name == "8x64_unique_pure")
        values.remove(target)
        values.append(target)
        return tuple(values)
    if order == "randomized":
        random.Random(SEED).shuffle(values)
        return tuple(values)
    raise ValueError("unsupported benchmark order")


def main(argv: Optional[Sequence[str]] = None) -> None:
    catalog = _scenario_catalog()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=tuple(item.name for item in catalog),
        help="run one scenario in this otherwise isolated process",
    )
    parser.add_argument(
        "--order",
        choices=("declared", "unique_last", "randomized"),
        default="declared",
    )
    args = parser.parse_args(argv)
    selected = (
        tuple(item for item in catalog if item.name == args.scenario)
        if args.scenario
        else _ordered_scenarios(catalog, args.order)
    )
    rows = tuple(_measure_scenario(item) for item in selected)

    unique_64 = next(
        item.records for item in catalog if item.name == "8x64_unique_pure"
    )
    deterministic_result = _pure_run(unique_64)
    hundred_deterministic = all(
        _pure_run(unique_64) == deterministic_result for _ in range(100)
    )
    clock = time.get_clock_info("perf_counter")
    summary = {
        "aggregation_version": AGGREGATION_VERSION,
        "aggregation_config_version": AGGREGATION_CONFIG_VERSION,
        "aggregation_config_digest": aggregation_config_digest(
            DEFAULT_OCR_AGGREGATION_CONFIG
        ),
        "fixture_generator_version": FIXTURE_GENERATOR_VERSION,
        "seed": SEED,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "cpu_model": _cpu_model(),
        "timer": "perf_counter_ns",
        "timer_resolution_seconds": clock.resolution,
        "p95_method": P95_METHOD,
        "gc_enabled_before_benchmark": gc.isenabled(),
        "gc_threshold": gc.get_threshold(),
        "gc_policy": GC_POLICY,
        "warmup_iterations": WARMUP_RUNS,
        "reference_iterations": REFERENCE_RUNS,
        "timed_iterations_per_scenario": RUNS,
        "scenario_order_mode": args.order,
        "scenario_order": tuple(item.name for item in selected),
        "process_scenario_filter": args.scenario,
        "fair_record_semantics_equal": _record_semantics_equal(unique_64),
        "determinism_100": hundred_deterministic,
        "reference_release_100_full_candidates": _reference_release_check(
            unique_64
        ),
        "disabled_does_not_construct_aggregator": (
            _disabled_does_not_construct_aggregator(unique_64)
        ),
        "required_performance_gates_pass": all(
            row["p95_pass"] is not False and row["memory_pass"] is not False
            for row in rows
        ),
        "contract_blockers": tuple(
            row["scenario"] for row in rows if not row["contract_ok"]
        ),
        "rows": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
