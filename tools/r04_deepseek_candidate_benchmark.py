import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median

from ai_provider_config import (
    AIProviderConfig,
    PROVIDER_DEEPSEEK,
)
from llm_provider_runtime import (
    LLMCompletionRequest,
    LLMMessage,
    LLMMessageRole,
    LLMRuntimeError,
    complete,
)

# ---------------------------------------------------------------------------
# AM7-R04 local benchmark configuration
# ---------------------------------------------------------------------------

DEFAULT_RUN_DIR = Path(
    r"F:\Ocria\data\ocr_runs\20260816T023649+0800_22bbd36b-e923-46fb-9d94-3069c25f15f6"
)

RUN_DIR = Path(os.environ.get("R04_RUN_DIR", str(DEFAULT_RUN_DIR)))
CANDIDATES_PATH = RUN_DIR / "candidates.jsonl"

BENCHMARK_VERSION = "am7-r04-candidate-benchmark-v1"
PROMPT_VERSION = "r04-scene-art-v1"
CRITERIA_VERSION = "r04-scene-art-v1"
BENCHMARK_AS_OF_MONTH = "2026-08"

MODEL = os.environ.get(
    "R04_DEEPSEEK_MODEL",
    "deepseek-v4-flash",
)

# Stable default name allows an interrupted run to resume without retrying
# candidates that were already recorded. Set R04_BENCHMARK_SESSION to a new
# value only when intentionally starting a separate benchmark run.
BENCHMARK_SESSION = os.environ.get(
    "R04_BENCHMARK_SESSION",
    "deepseek_v4_flash__r04_scene_art_v1",
)

OUTPUT_ROOT = Path(
    os.environ.get(
        "R04_BENCHMARK_OUTPUT_DIR",
        str(RUN_DIR.parent.parent / "r04_benchmarks" / RUN_DIR.name),
    )
)
RESULTS_PATH = OUTPUT_ROOT / f"{BENCHMARK_SESSION}.jsonl"
SUMMARY_PATH = OUTPUT_ROOT / f"{BENCHMARK_SESSION}__summary.json"

# User-verified DeepSeek-V4-Flash pricing snapshot.
# This is an estimate for benchmark comparison, not a claim about final billed
# cost after free quota, discounts, promotions, or later pricing changes.
PRICING_SNAPSHOT_DATE = "2026-08-16"
PRICE_MAX_INPUT_TOKENS = 1_000_000
INPUT_PRICE_CNY_PER_1M = Decimal("1.5")
OUTPUT_PRICE_CNY_PER_1M = Decimal("4.5")


SYSTEM_PROMPT = """
Ocria AM7-R04 离线 Benchmark。

仅依据 Candidate Text。禁止外部知识。
证据不足=false。

判断：
C01：有明确团队管理经验。
必须有明确带人、人员管理、团队分工、成员管理等证据。
仅团队协作、跨团队对接、参与评审、独立负责个人模块不算团队管理。

C02：明确在至少一个3D项目中负责过具体工作。
必须有“负责 / 主要负责 / 承担”等明确责任证据。
在3D项目中明确负责场景原画、概念设计或其它具体美术工作可以符合。
仅参与3D项目、仅使用3D软件、仅与3D团队协作不算符合。

C03：最大完整工作空窗<=6个月。

C04：累计正式工作经验>=48个月。

时间规则：
- C03/C04只根据明确的正式工作经历起止月份计算。
- 不使用简历顶部“X年经验”等汇总数字代替计算。
- 不把教育经历、项目日期、作品日期重复计入正式工作经验。
- 两份正式工作之间完整未工作的月份 = gap。
- 工作经历首尾月份均计入工作时间。
- 重叠工作月份只计算一次。
- “至今”统一视为2026-08。
- 日期不足以可靠计算时，对应条件=false，无法可靠得到的数值返回null。

只做一次必要的判断和月份计算。
不要展开分析，不要验证或重复检查结果。

仅输出一个合法JSON对象，不要Markdown，不要解释，不要其它文字：
{"criteria":{"C01":true,"C02":true,"C03":true,"C04":true},"max_gap_months":0,"total_work_months":0}
""".strip()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value


def load_candidates(path: Path) -> list[dict]:
    candidates: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid JSON in candidates.jsonl at line {line_number}"
                ) from exc
            if not isinstance(value, dict):
                raise RuntimeError(
                    f"Candidate record at line {line_number} is not a JSON object"
                )
            candidates.append(value)

    candidates.sort(key=lambda item: item.get("sequence_number", 10**9))
    return candidates


def validate_contract(parsed: object) -> tuple[bool, str | None]:
    if type(parsed) is not dict:
        return False, "root_not_object"

    expected_root_keys = {
        "criteria",
        "max_gap_months",
        "total_work_months",
    }
    if set(parsed) != expected_root_keys:
        return False, "unexpected_root_fields"

    criteria = parsed.get("criteria")
    if type(criteria) is not dict:
        return False, "criteria_not_object"

    expected_criteria = {"C01", "C02", "C03", "C04"}
    if set(criteria) != expected_criteria:
        return False, "unexpected_criteria_fields"

    for criterion in ("C01", "C02", "C03", "C04"):
        if type(criteria[criterion]) is not bool:
            return False, f"{criterion}_not_boolean"

    for field_name in ("max_gap_months", "total_work_months"):
        value = parsed[field_name]
        if value is None:
            continue
        if type(value) is not int or value < 0:
            return False, f"{field_name}_not_nonnegative_integer_or_null"

    return True, None


def estimate_cost_cny(
    input_tokens: int | None,
    output_tokens: int | None,
) -> tuple[float | None, bool]:
    if (
        type(input_tokens) is not int
        or type(output_tokens) is not int
        or input_tokens < 0
        or output_tokens < 0
    ):
        return None, False

    if input_tokens > PRICE_MAX_INPUT_TOKENS:
        # The frozen local price snapshot only covers the <=32K input tier.
        return None, False

    cost = (
        Decimal(input_tokens) * INPUT_PRICE_CNY_PER_1M
        + Decimal(output_tokens) * OUTPUT_PRICE_CNY_PER_1M
    ) / Decimal(1_000_000)

    return float(cost), True


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")
        handle.flush()


def load_existing_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []

    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid existing benchmark JSONL at line {line_number}: {path}"
                ) from exc
            if not isinstance(row, dict):
                raise RuntimeError(
                    f"Existing benchmark row at line {line_number} is not an object"
                )
            rows.append(row)
    return rows


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * fraction
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = position - lower_index
    return ordered[lower_index] * (1 - weight) + ordered[upper_index] * weight


def build_summary(source_candidates: list[dict], rows: list[dict]) -> dict:
    calls = [row for row in rows if row.get("call_attempted") is True]
    provider_successes = [
        row for row in calls if row.get("provider_call_succeeded") is True
    ]
    provider_errors = [
        row for row in calls if row.get("status") == "provider_error"
    ]
    contract_valid_rows = [
        row for row in provider_successes if row.get("contract_valid") is True
    ]
    contract_invalid_rows = [
        row for row in provider_successes if row.get("contract_valid") is False
    ]
    no_text_rows = [
        row for row in rows if row.get("status") == "no_document_text"
    ]

    latencies = [
        float(row["latency_ms"])
        for row in calls
        if isinstance(row.get("latency_ms"), (int, float))
        and not isinstance(row.get("latency_ms"), bool)
    ]

    usage_rows = [
        row
        for row in provider_successes
        if type(row.get("input_tokens")) is int
        and type(row.get("output_tokens")) is int
        and type(row.get("total_tokens")) is int
    ]

    total_input_tokens = sum(row["input_tokens"] for row in usage_rows)
    total_output_tokens = sum(row["output_tokens"] for row in usage_rows)
    total_tokens = sum(row["total_tokens"] for row in usage_rows)

    priced_rows = [
        row
        for row in provider_successes
        if row.get("pricing_applicable") is True
        and isinstance(row.get("estimated_cost_cny"), (int, float))
        and not isinstance(row.get("estimated_cost_cny"), bool)
    ]
    estimated_total_cost = sum(
        Decimal(str(row["estimated_cost_cny"])) for row in priced_rows
    )

    mean_cost = (
        estimated_total_cost / Decimal(len(priced_rows))
        if priced_rows
        else None
    )
    estimated_per_1000 = (
        mean_cost * Decimal(1000)
        if mean_cost is not None
        else None
    )

    build_status_counts: dict[str, int] = {}
    for candidate in source_candidates:
        status = str(candidate.get("document_build_status") or "unknown")
        build_status_counts[status] = build_status_counts.get(status, 0) + 1

    return {
        "benchmark_version": BENCHMARK_VERSION,
        "prompt_version": PROMPT_VERSION,
        "criteria_version": CRITERIA_VERSION,
        "benchmark_session": BENCHMARK_SESSION,
        "source_run_dir": str(RUN_DIR),
        "source_run_id": (
            source_candidates[0].get("run_id") if source_candidates else None
        ),
        "provider": PROVIDER_DEEPSEEK,
        "requested_model": MODEL,
        "benchmark_as_of_month": BENCHMARK_AS_OF_MONTH,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_records": len(source_candidates),
        "rows_recorded": len(rows),
        "document_build_status_counts": build_status_counts,
        "calls_attempted": len(calls),
        "provider_successes": len(provider_successes),
        "provider_errors": len(provider_errors),
        "contract_valid": len(contract_valid_rows),
        "contract_invalid": len(contract_invalid_rows),
        "no_document_text": len(no_text_rows),
        "latency_ms": {
            "median": round(median(latencies), 1) if latencies else None,
            "p90": round(percentile(latencies, 0.90), 1) if latencies else None,
            "min": round(min(latencies), 1) if latencies else None,
            "max": round(max(latencies), 1) if latencies else None,
        },
        "usage": {
            "rows_with_usage": len(usage_rows),
            "input_tokens_total": total_input_tokens,
            "output_tokens_total": total_output_tokens,
            "total_tokens_total": total_tokens,
        },
        "pricing_snapshot": {
            "date": PRICING_SNAPSHOT_DATE,
            "currency": "CNY",
            "input_tier_max_tokens": PRICE_MAX_INPUT_TOKENS,
            "input_price_per_1m_tokens": float(INPUT_PRICE_CNY_PER_1M),
            "output_price_per_1m_tokens": float(OUTPUT_PRICE_CNY_PER_1M),
            "priced_rows": len(priced_rows),
            "estimated_total_cost_cny": (
                float(estimated_total_cost) if priced_rows else None
            ),
            "mean_estimated_cost_cny_per_called_candidate": (
                float(mean_cost) if mean_cost is not None else None
            ),
            "estimated_cost_cny_per_1000_called_candidates": (
                float(estimated_per_1000)
                if estimated_per_1000 is not None
                else None
            ),
            "note": (
                    "Local conservative estimate using the 2026-08-16 "
                    "DeepSeek-V4-Flash cache-miss input price and output price; "
                    "actual billed input cost may be lower when context cache hits occur."
            ),
        },
        "retry_policy": "none",
        "candidate_text_persisted_in_benchmark_output": False,
    }


def write_summary(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    api_key = require_env("R04_DEEPSEEK_API_KEY")
    base_url = require_env("R04_DEEPSEEK_BASE_URL")

    if not CANDIDATES_PATH.is_file():
        raise RuntimeError(f"candidates.jsonl not found: {CANDIDATES_PATH}")

    config = AIProviderConfig(
        provider=PROVIDER_DEEPSEEK,
        api_key=api_key,
        base_url=base_url,
        model=MODEL,
    )

    candidates = load_candidates(CANDIDATES_PATH)
    if not candidates:
        raise RuntimeError("No candidate records found.")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    existing_rows = load_existing_rows(RESULTS_PATH)
    recorded_candidate_ids = {
        row.get("candidate_record_id")
        for row in existing_rows
        if row.get("candidate_record_id")
    }

    print(f"Source: {CANDIDATES_PATH}")
    print(f"Records: {len(candidates)}")
    print(f"Model: {MODEL}")
    print(f"Prompt: {PROMPT_VERSION}")
    print(f"Results: {RESULTS_PATH}")
    print(f"Already recorded: {len(recorded_candidate_ids)}")
    print("Retry policy: none")
    print()

    total = len(candidates)

    for position, candidate in enumerate(candidates, start=1):
        candidate_record_id = candidate.get("candidate_record_id")
        sequence_number = candidate.get("sequence_number")
        document_text = candidate.get("document_text")
        document_build_status = candidate.get("document_build_status")
        capture_status = candidate.get("capture_status")

        if not isinstance(candidate_record_id, str) or not candidate_record_id:
            raise RuntimeError(
                f"Candidate sequence {sequence_number} has no valid candidate_record_id"
            )

        if candidate_record_id in recorded_candidate_ids:
            print(
                f"[{position:02d}/{total:02d}] "
                f"seq={sequence_number} already recorded -> SKIP"
            )
            continue

        base_record = {
            "benchmark_version": BENCHMARK_VERSION,
            "prompt_version": PROMPT_VERSION,
            "criteria_version": CRITERIA_VERSION,
            "benchmark_session": BENCHMARK_SESSION,
            "benchmark_as_of_month": BENCHMARK_AS_OF_MONTH,
            "source_run_id": candidate.get("run_id"),
            "candidate_record_id": candidate_record_id,
            "sequence_number": sequence_number,
            "capture_status": capture_status,
            "document_build_status": document_build_status,
            "document_char_count": (
                len(document_text) if isinstance(document_text, str) else 0
            ),
            "provider": PROVIDER_DEEPSEEK,
            "requested_model": MODEL,
            "retry_policy": "none",
        }

        if not isinstance(document_text, str) or not document_text.strip():
            row = {
                **base_record,
                "status": "no_document_text",
                "call_attempted": False,
                "provider_call_succeeded": False,
                "contract_valid": None,
                "contract_error": None,
                "response_model": None,
                "latency_ms": None,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "finish_reason": None,
                "request_id": None,
                "pricing_applicable": False,
                "estimated_cost_cny": None,
                "result": None,
                "tested_at": datetime.now(timezone.utc).isoformat(),
            }
            append_jsonl(RESULTS_PATH, row)
            recorded_candidate_ids.add(candidate_record_id)

            print(
                f"[{position:02d}/{total:02d}] "
                f"seq={sequence_number} build={document_build_status} "
                f"chars=0 -> NO_DOCUMENT_TEXT"
            )
            continue

        print(
            f"[{position:02d}/{total:02d}] "
            f"seq={sequence_number} build={document_build_status} "
            f"chars={len(document_text)} -> calling {MODEL}..."
        )

        request = LLMCompletionRequest(
            messages=(
                LLMMessage(
                    role=LLMMessageRole.SYSTEM,
                    content=SYSTEM_PROMPT,
                ),
                LLMMessage(
                    role=LLMMessageRole.USER,
                    content=f"Candidate Text:\n{document_text}",
                ),
            )
        )

        started = time.perf_counter()
        tested_at = datetime.now(timezone.utc).isoformat()

        try:
            result = complete(config, request)
            latency_ms = round((time.perf_counter() - started) * 1000, 1)

            estimated_cost_cny, pricing_applicable = estimate_cost_cny(
                result.input_tokens,
                result.output_tokens,
            )

            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError:
                contract_valid = False
                contract_error = "invalid_json"
                parsed = None
            else:
                contract_valid, contract_error = validate_contract(parsed)

            row = {
                **base_record,
                "status": "success" if contract_valid else "contract_error",
                "call_attempted": True,
                "provider_call_succeeded": True,
                "contract_valid": contract_valid,
                "contract_error": contract_error,
                "response_model": result.model,
                "latency_ms": latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "finish_reason": result.finish_reason,
                "request_id": result.request_id,
                "pricing_applicable": pricing_applicable,
                "estimated_cost_cny": estimated_cost_cny,
                # Persist only validated structured output.
                # Never persist Candidate Text or raw malformed model content.
                "result": parsed if contract_valid else None,
                "tested_at": tested_at,
            }
            append_jsonl(RESULTS_PATH, row)
            recorded_candidate_ids.add(candidate_record_id)

            if contract_valid:
                criteria = parsed["criteria"]
                print(
                    "  PASS "
                    f"{latency_ms / 1000:.1f}s "
                    f"in={result.input_tokens} "
                    f"out={result.output_tokens} "
                    f"cost≈¥{estimated_cost_cny:.6f} "
                    f"C01={criteria['C01']} "
                    f"C02={criteria['C02']} "
                    f"C03={criteria['C03']} "
                    f"C04={criteria['C04']} "
                    f"gap={parsed['max_gap_months']} "
                    f"work={parsed['total_work_months']}"
                )
            else:
                print(
                    "  CONTRACT_ERROR "
                    f"{contract_error} "
                    f"{latency_ms / 1000:.1f}s "
                    f"in={result.input_tokens} "
                    f"out={result.output_tokens}"
                )

        except LLMRuntimeError as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)

            row = {
                **base_record,
                "status": "provider_error",
                "call_attempted": True,
                "provider_call_succeeded": False,
                "contract_valid": None,
                "contract_error": None,
                "response_model": None,
                "latency_ms": latency_ms,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "finish_reason": None,
                "request_id": exc.request_id,
                "error_code": exc.code.value,
                "status_code": exc.status_code,
                "pricing_applicable": False,
                "estimated_cost_cny": None,
                "result": None,
                "tested_at": tested_at,
            }
            append_jsonl(RESULTS_PATH, row)
            recorded_candidate_ids.add(candidate_record_id)

            print(
                "  PROVIDER_ERROR "
                f"code={exc.code.value} "
                f"http={exc.status_code} "
                f"latency={latency_ms / 1000:.1f}s"
            )

        # No retry, no fallback, no Candidate/BOSS action.

    final_rows = load_existing_rows(RESULTS_PATH)
    summary = build_summary(candidates, final_rows)
    write_summary(SUMMARY_PATH, summary)

    print()
    print("Benchmark pass finished.")
    print(f"Results: {RESULTS_PATH}")
    print(f"Summary: {SUMMARY_PATH}")
    print(
        "Recorded "
        f"{summary['rows_recorded']}/{summary['source_records']} source records; "
        f"calls={summary['calls_attempted']}, "
        f"provider_errors={summary['provider_errors']}, "
        f"contract_invalid={summary['contract_invalid']}, "
        f"no_document_text={summary['no_document_text']}."
    )
    print(
        "Latency: "
        f"median={summary['latency_ms']['median']} ms, "
        f"p90={summary['latency_ms']['p90']} ms."
    )
    print(
        "Estimated cost: "
        f"total=¥{summary['pricing_snapshot']['estimated_total_cost_cny']}, "
        "per 1000 called candidates≈¥"
        f"{summary['pricing_snapshot']['estimated_cost_cny_per_1000_called_candidates']}"
    )


if __name__ == "__main__":
    main()
