"""Synthetic, pure Change 3 benchmark for R06 n-gram and SimHash primitives."""

import gc
import json
import math
import statistics
import time
import tracemalloc
import tempfile
from pathlib import Path

from ocr_similarity import (
    DEFAULT_OCR_SIMILARITY_CONFIG,
    compute_char_ngram_similarity,
    compute_simhash_similarity,
)
from tests.test_ocr_similarity import make_r04_screen, with_r05_fields
from ocr_aggregation import CandidateDocumentAggregator
from ocr_similarity import compute_r05_accounting
from ocr_candidate import CandidateOcrBuilder
from ocr_records import CaptureStatus
from ocr_replay import _evaluate_r06_screens, replay_candidate_similarity
from ocr_similarity_sidecar import write_similarity_sidecar
from ocr_store import JsonlOcrRecordStore


WARMUP_ITERATIONS = 3
TIMED_ITERATIONS = 25


def _pair(left: str, right: str) -> None:
    compute_char_ngram_similarity(left, right)
    compute_simhash_similarity(left, right)


def _p95(values):
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def _measure(name: str, operation, *, p95_limit_ms=None):
    for _ in range(WARMUP_ITERATIONS):
        operation()
    timings = []
    for _ in range(TIMED_ITERATIONS):
        started = time.perf_counter_ns()
        operation()
        timings.append((time.perf_counter_ns() - started) / 1_000_000)
    gc.collect()
    tracemalloc.start()
    operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    p95 = _p95(timings)
    return {
        "scenario": name,
        "warmup_iterations": WARMUP_ITERATIONS,
        "timed_iterations": TIMED_ITERATIONS,
        "p50_ms": round(statistics.median(timings), 4),
        "p95_ms": round(p95, 4),
        "peak_kib": round(peak / 1024, 2),
        "p95_limit_ms": p95_limit_ms,
        "p95_pass": None if p95_limit_ms is None else p95 <= p95_limit_ms,
    }


def _build_candidate(screens, *, aggregation_mode, similarity_mode):
    builder = CandidateOcrBuilder(
        "run", 1, candidate_record_id="candidate",
        created_at="2026-08-01T12:00:00+08:00",
        aggregation_mode=aggregation_mode,
        similarity_mode=similarity_mode,
    )
    for screen in screens:
        builder.add_screen(screen)
    return builder.finalize(
        CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
        completed_at="2026-08-01T12:01:00+08:00",
    )


def run_benchmark():
    base_20k = ("abcdefghijklmnopqrstuvwxyz0123456789" * 556)[:20_000]
    half_changed = base_20k[:10_000] + ("Z" * 10_000)
    unicode_pair = ("中文C++C#.NETSLG+X0-12D/3D😀" * 1_000)[:20_000]
    boundary = ("边界文本C++" * 20_000)[:100_000]
    too_long = "a" * 100_001
    adjacent = tuple(
        (base_20k[:2_500] + chr(65 + index), base_20k[:2_500] + chr(66 + index))
        for index in range(8)
    )
    accounting_aggregator = CandidateDocumentAggregator("run", "candidate")
    accounting_screen = make_r04_screen(
        "accounting", 1, tuple("segment-{0:03d}-C++-中文".format(index) for index in range(64)),
    )
    accounting_screen = with_r05_fields(accounting_screen, accounting_aggregator.add_screen(accounting_screen))
    builder_screens = tuple(
        make_r04_screen(
            "builder-{0}".format(index), index,
            ("稳定基线 C++ 内容 " * 5,),
        )
        for index in range(1, 9)
    )
    r05_candidate = _build_candidate(
        builder_screens, aggregation_mode="record", similarity_mode="disabled",
    )
    r06_candidate = _build_candidate(
        builder_screens, aggregation_mode="record", similarity_mode="record",
    )
    replay_store_root = tempfile.TemporaryDirectory()
    replay_store = JsonlOcrRecordStore(
        Path(replay_store_root.name), run_id="run",
        aggregation_mode="record", similarity_mode="record",
    )

    def replay_operation():
        return replay_candidate_similarity(r06_candidate, replay_store.manifest)

    def sidecar_operation():
        with tempfile.TemporaryDirectory() as sidecar_root:
            store = JsonlOcrRecordStore(
                Path(sidecar_root), run_id="run",
                aggregation_mode="record", similarity_mode="record",
            )
            try:
                return write_similarity_sidecar(
                    store.run_dir, store.manifest, (r06_candidate,), strict=True,
                )
            finally:
                store.close()
    scenarios = (
        _measure("20k_exact_same", lambda: _pair(base_20k, base_20k), p95_limit_ms=15.0),
        _measure("20k_50_percent_changed", lambda: _pair(base_20k, half_changed), p95_limit_ms=15.0),
        _measure("20k_repeated_ngram_stress", lambda: _pair("a" * 20_000, "a" * 20_000), p95_limit_ms=15.0),
        _measure("short_pair", lambda: _pair("C++", "C#")),
        _measure("unicode_pair", lambda: _pair(unicode_pair, unicode_pair)),
        _measure("100k_boundary", lambda: _pair(boundary, boundary)),
        _measure("100001_reject", lambda: _pair(too_long, "b")),
        _measure("r05_accounting_64_segments", lambda: compute_r05_accounting(accounting_screen)),
        _measure("8_adjacent_pairs", lambda: tuple(_pair(left, right) for left, right in adjacent), p95_limit_ms=100.0),
        _measure("r05_record_only_8_screens", lambda: _build_candidate(
            builder_screens, aggregation_mode="record", similarity_mode="disabled",
        )),
        _measure("r06_calculation_only_8_screens", lambda: _evaluate_r06_screens(
            r05_candidate.screens, DEFAULT_OCR_SIMILARITY_CONFIG,
        )),
        _measure("r05_r06_record_builder_8_screens", lambda: _build_candidate(
            builder_screens, aggregation_mode="record", similarity_mode="record",
        )),
        _measure("r05_r06_disabled_builder_8_screens", lambda: _build_candidate(
            builder_screens, aggregation_mode="disabled", similarity_mode="disabled",
        )),
        _measure("r05_r06_replay_8_screens", replay_operation),
        _measure("r06_sidecar_synthetic_8_screens", sidecar_operation),
    )
    single_pair = scenarios[:3]
    eight_screen_gate = next(
        item for item in scenarios if item["scenario"] == "8_adjacent_pairs"
    )
    required_pass = (
        all(item["p95_pass"] for item in single_pair)
        and eight_screen_gate["p95_pass"]
        and max(item["peak_kib"] for item in scenarios) <= 16 * 1024
    )
    replay_store.close()
    replay_store_root.cleanup()
    return {
        "benchmark": "r06_change3_pure_similarity",
        "timer": "perf_counter_ns",
        "warmup_iterations": WARMUP_ITERATIONS,
        "timed_iterations": TIMED_ITERATIONS,
        "memory_limit_kib": 16 * 1024,
        "required_performance_gates_pass": required_pass,
        "scenarios": scenarios,
        "integration_fixture_screen_count": len(r06_candidate.screens),
    }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), ensure_ascii=False, indent=2, sort_keys=True))
