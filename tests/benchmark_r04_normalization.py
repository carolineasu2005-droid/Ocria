"""Repeatable synthetic R04 acceptance benchmark.

This script performs no OCR, page action, persistence, or network access.  It
keeps timing and tracemalloc runs separate so memory instrumentation does not
inflate the frozen p95 thresholds.
"""

import gc
import json
import statistics
import time
import tracemalloc

from ocr_normalization import (
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NORMALIZATION_VERSION,
    NormalizationBox,
    canonical_normalization_config,
    normalization_config_digest,
    normalize_ocr_text,
)


def make_boxes(count, mode):
    boxes = []
    for index in range(count):
        if mode == "dense":
            left, top, text = 0, 0, "same"
        elif mode == "far":
            left, top, text = index * 150, 0, "same"
        else:
            row, column = divmod(index, 25)
            left, top = column * 120, row * 30
            text = "unique-{0:03d}".format(index)
        boxes.append(NormalizationBox(
            "box-{0:03d}".format(index),
            text,
            (left, top, left + 100, top + 20),
            index,
            0.90,
        ))
    return tuple(boxes)


def percentile_95(values):
    return statistics.quantiles(
        values,
        n=20,
        method="inclusive",
    )[18]


def measure(label, count, mode, runs):
    boxes = make_boxes(count, mode)
    for _ in range(3):
        normalize_ocr_text(boxes)

    timings = []
    expected = None
    deterministic = True
    for _ in range(runs):
        started = time.perf_counter()
        result = normalize_ocr_text(boxes)
        timings.append((time.perf_counter() - started) * 1000.0)
        if expected is None:
            expected = result
        else:
            deterministic = deterministic and result == expected

    gc.collect()
    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    memory_result = normalize_ocr_text(boxes)
    _, peak = tracemalloc.get_traced_memory()
    trace = {
        "candidate_count": (
            memory_result.duplicate_candidate_pair_count
        ),
        "survivor_confirmation_count": (
            memory_result.duplicate_confirmation_count
        ),
        "survivor_count": len(memory_result.effective_box_ids),
        "suppressed_count": len(
            memory_result.suppressed_duplicate_box_ids
        ),
        "gray_count": memory_result.duplicate_gray_pair_count,
    }
    del memory_result
    gc.collect()
    retained, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "scenario": label,
        "boxes": count,
        "runs": runs,
        "median_ms": round(statistics.median(timings), 4),
        "p95_ms": round(percentile_95(timings), 4),
        **trace,
        "peak_kib": round(max(0, peak - baseline) / 1024.0, 2),
        "gc_retained_kib": round(
            max(0, retained - baseline) / 1024.0,
            2,
        ),
        "deterministic": deterministic,
    }


def main():
    rows = (
        measure("unique-0", 0, "unique", 25),
        measure("unique-1", 1, "unique", 25),
        measure("unique-8", 8, "unique", 25),
        measure("unique-100", 100, "unique", 25),
        measure("unique-500", 500, "unique", 25),
        measure("far-same-text-500", 500, "far", 25),
        measure(
            "dense-same-position-text-500",
            500,
            "dense",
            25,
        ),
        measure(
            "dense-100-repeated-identical",
            100,
            "dense",
            100,
        ),
    )
    config = DEFAULT_OCR_NORMALIZATION_CONFIG
    print(json.dumps(
        {
            "normalization_version": NORMALIZATION_VERSION,
            "normalization_config_version": (
                config.normalization_config_version
            ),
            "normalization_config_digest": normalization_config_digest(
                canonical_normalization_config(config)
            ),
            "rows": rows,
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
