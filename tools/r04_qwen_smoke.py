import json
import os
import time

from ai_provider_config import (
    PROVIDER_DEEPSEEK,
    AIProviderConfig,
    PROVIDER_ALIYUN_BAILIAN,
)
from llm_provider_runtime import (
    LLMCompletionRequest,
    LLMMessage,
    LLMMessageRole,
    LLMRuntimeError,
    complete,
)

MODEL = os.environ.get(
    "R04_DEEPSEEK_MODEL",
    "deepseek-v4-flash-2026-08-16",
)

config = AIProviderConfig(
    provider=PROVIDER_DEEPSEEK,
    api_key=os.environ["R04_DEEPSEEK_API_KEY"],
    base_url=os.environ["R04_DEEPSEEK_BASE_URL"],
    model=MODEL,
)

SYSTEM_PROMPT = """
Ocria AM7-R04 离线 Benchmark。

仅依据 Candidate Text。禁止外部知识。
证据不足=false。

判断：
C01：有明确团队管理经验。
C02：候选人是否明确在至少一个3D项目中负责过具体工作。
必须有“负责/主要负责/承担”等明确责任证据。
仅参与项目、仅使用3D软件、仅与3D团队协作，不算符合。
C03：最大完整工作空窗<=6个月。
C04：累计正式工作经验>=48个月。

时间规则：
- 两份工作之间完整未工作月份 = gap。
- 工作首尾月份均计入。
- 重叠月份只计算一次。
- “至今”=2026-08。
- 日期不足以计算时，对应条件=false。

只做一次必要的判断和月份计算。
不要展开分析，不要验证或重复检查结果。

仅输出：
{"criteria":{"C01":true,"C02":true,"C03":true,"C04":true},"max_gap_months":0,"total_work_months":0}
""".strip()

CANDIDATE_TEXT = """
2021.01–2022.12
A游戏公司，场景原画。
负责游戏场景概念设计、氛围图和建筑设定，与场景原画、3D美术及关卡团队协作。
参与项目评审，并使用 Blender 辅助构图和空间验证。

2023.08–2025.06
B游戏公司，高级场景原画。
参与一款3D游戏项目，主要负责场景概念设计，并根据3D团队提供的白盒和模型进行设计调整。
负责个人场景模块的美术质量，与其他美术成员协作完成项目内容。
""".strip()

request = LLMCompletionRequest(
    messages=(
        LLMMessage(
            role=LLMMessageRole.SYSTEM,
            content=SYSTEM_PROMPT,
        ),
        LLMMessage(
            role=LLMMessageRole.USER,
            content=f"Candidate Text:\n{CANDIDATE_TEXT}",
        ),
    )
)

started = time.perf_counter()

try:
    result = complete(config, request)
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    parsed = json.loads(result.content)

    print(json.dumps({
        "provider": result.provider,
        "requested_model": MODEL,
        "response_model": result.model,
        "latency_ms": latency_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
        "finish_reason": result.finish_reason,
        "request_id": result.request_id,
        "contract_valid": True,
        "result": parsed,
    }, ensure_ascii=False, indent=2))

except json.JSONDecodeError:
    print("SMOKE FAILED: output is not valid JSON")

except LLMRuntimeError as exc:
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    print(json.dumps({
        "smoke": "failed",
        "error_code": exc.code.value,
        "status_code": exc.status_code,
        "request_id": exc.request_id,
        "latency_ms": latency_ms,
    }, ensure_ascii=False, indent=2))