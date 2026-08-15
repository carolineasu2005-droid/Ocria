# AM7-R03 — LLM Provider Runtime 与 Qwen / DeepSeek 接入

## 1. Metadata

| Field | Value |
|---|---|
| Document Type | Technical Implementation Design |
| Requirement | AM7-R03 — LLM Provider Runtime 与 Qwen / DeepSeek 接入 |
| Version | 0.2 |
| Status | Approved / Frozen for Implementation |
| Target Branch | am7-r03-llm-provider-runtime |
| Prepared On | 2026-08-15 |
| Implementation Authorization | Contract frozen for subsequent implementation; no implementation performed in this review |

本 TID 只把已冻结的 R03 产品合同转换为最小、可直接实施的技术合同。它不重新设计 R03，不授权产品代码、测试、提交、发布或真实付费 inference 的实施。

## 2. Frozen Inputs

本 TID 已读取并服从以下输入，优先级为：

1. docs/RPD-AM7-R03-llm-provider-runtime.md，Version 0.2，Approved / Frozen for TID。
2. docs/RPD-AM7-R02-ai-provider-configuration-management.md。
3. docs/TID-AM7-R02-ai-provider-configuration-management.md。
4. docs/AM7-R02-acceptance-report.md。
5. CODEX-CONSTITUTION.md。
6. 当前 repository 中与 R03 直接相关的实现、依赖、启动与打包事实。

R03 不建立第二套配置合同。AIProviderConfig、AIProviderConfigStore、R02 的三个 verification 状态和 stale comparison 均原样复用。

本轮 targeted recheck 未发现 Frozen R03 RPD 与 Frozen R02 合同之间的不可实现冲突。

## 3. Requirement Summary

R03 以当前 flat repository 风格增加：

- 一个最小 Provider Runtime，支持 aliyun-bailian 与 deepseek；
- 一个独立的 AI Provider Configuration CLI；
- OpenAI-compatible 的模型发现、非推理连接检查和单次非流式 completion；
- 与 R02 Store 的 verification write-back 集成；
- 启动菜单中的显式配置入口；
- 不依赖真实凭据的 targeted unit tests 和最小 packaging verification。

R03 v1 明确不包含 streaming、自动 retry、inference fallback、Provider/model fallback、thinking control、模型缓存、动态 Provider registry、Test Inference、R04 screening 或 Candidate 业务接入。

## 4. Targeted Repository Findings

### 4.1 Startup entry

simple_brush.py 当前具备以下稳定入口：

- parse_args() 解析现有 flags；
- is_noninteractive_startup() 在 --auto、--keywords 或 --calibration-profile 任一存在时返回 true；
- 非交互路径在 main() 中直接调用既有 run()，不进入启动菜单；
- choose_startup_action() 当前返回 run、calibrate 或 exit；
- main() 在 run 时返回既有 run() 结果，在 exit 时返回 0，calibration 完成后回到菜单。

最小挂载点因此是 choose_startup_action() 的交互菜单和 main() 的同级 dispatch。不得改 parse_args()、is_noninteractive_startup() 或 run() 主链。

### 4.2 R02 public implementation

ai_provider_config.py 当前冻结并由 R03 直接消费：

- AI_PROVIDER_CONFIG_VERSION = 1；
- DEFAULT_AI_PROVIDER_CONFIG_PATH = Path("config") / "ai_provider.json"；
- PROVIDER_ALIYUN_BAILIAN = "aliyun-bailian"；
- PROVIDER_DEEPSEEK = "deepseek"；
- ConnectionVerificationStatus：UNVERIFIED、VERIFIED、FAILED；
- AIProviderConfigLoadStatus：NOT_CONFIGURED、INCOMPLETE、INVALID、UNSUPPORTED_VERSION、VALID；
- frozen AIProviderConfig；
- AIProviderConfig.is_complete；
- AIProviderConfig.api_key_display()；
- AIProviderConfigLoadResult；
- AIProviderConfigIOError；
- AIProviderConfigStore.load()、save()、update()、record_connection_verification()。

R02 的真实行为满足 R03：

- INCOMPLETE load result 仍带有可访问的 AIProviderConfig；
- provider、api_key、base_url 或 model 可以不完整地持久化；
- connection tuple 为 provider、api_key、base_url；
- connection tuple 变化会失效为 unverified；仅 model 变化保留 verification；
- record_connection_verification() 只接受 VERIFIED 或 FAILED；
- write-back 使用 checked provider/api_key/base_url 与当前值做 stale comparison；
- stale 时返回 False 且不覆盖当前配置；
- 成功写回要求 timezone-aware completed_at；
- capability_unavailable 不需要也不得调用该写回 API。

### 4.3 Dependency and packaging

- repository 支持 Python 3.10+；当前开发环境为 Python 3.11；
- requirements.txt 承载应用运行时依赖；
- requirements-ocr.txt 承载 OCR 相关依赖；
- requirements-build.txt 承载 PyInstaller；
- 当前 requirements 中没有 openai，当前虚拟环境也尚未安装 openai；
- 2026-08-15 对官方 PyPI 执行的 read-only resolver check 已确认：openai>=2.53,<3.0 在 Python 3.10 target 与当前 Python 3.11.9 环境均可解析，二者当前都选择 openai 2.54.0；
- resolver check 只下载 wheel metadata/artifact 到 pip cache，不安装 package；
- BossOCR.spec 的 Analysis 入口为 simple_brush.py，常规静态 import 会由 PyInstaller 自动分析；
- spec 已有针对既有动态依赖的 collect_all/copy_metadata 处理，但没有 R03 SDK 特例；
- setup/build 脚本会安装 requirements.txt，因此 openai 应只直接加入该文件；
- R03 不默认修改 BossOCR.spec，只有真实 packaged import evidence 证明自动收集不足时才做最小修正。

## 5. Provider Capability Recheck

本节是 2026-08-15 针对实施所需能力的有限复核，不把当前实现机制提升为超出 Frozen RPD 的永久产品合同。

### 5.1 Alibaba Bailian / Qwen

复核来源：

- [Alibaba Model Studio: first OpenAI-compatible Qwen call](https://www.alibabacloud.com/help/en/model-studio/first-api-call-to-qwen)
- [Alibaba Model Studio: models](https://www.alibabacloud.com/help/en/model-studio/models)
- [Alibaba Model Studio: error codes](https://www.alibabacloud.com/help/en/model-studio/error-code)
- [Alibaba Model Studio: more tools](https://www.alibabacloud.com/help/en/model-studio/more-tools)

截至复核日期：

- 官方继续提供 OpenAI-compatible Chat Completion；
- 调用路径为所选 region、Workspace 或 plan 对应 Base URL 下的 /chat/completions；
- 官方示例支持非流式完整响应，R03 显式发送 stream=False；
- Base URL 不是唯一全球常量，Workspace、region 和 plan 可能使用不同地址；
- 正常响应可提供 choices[0].message.content、choices[0].finish_reason、model、usage.prompt_tokens、usage.completion_tokens、usage.total_tokens 和顶层 id；
- 结构化错误可提供 HTTP status 与 code；request correlation 可从 SDK exception、x-request-id header 或结构化 body 中尽力提取；
- 官方资料仍未将通用 GET /models、client.models.list() 或另一项通用非推理 model discovery/authentication API 明确冻结为稳定合同；
- 一次不带凭据、无 inference 的官方 compatible endpoint targeted probe 对 /models 返回 401 而非 404/405。这只支持把 client.models.list() 作为当前 R03 v1 best-effort 机制，不能替代官方文档合同。

因此本 TID 冻结：

- Qwen R03 v1 的 list_models() 和 test_connection() 当前都调用 client.models.list()；
- 这是 current best-effort implementation mechanism，不是 Qwen 的永久产品 endpoint 合同；
- 当前 Provider/region/Workspace/plan 明确以 404 或 405 表示该非推理 capability 不存在时，返回 capability_unavailable；
- 401/403、timeout、network、429、5xx 和 malformed response 仍按实际失败分类；
- 不使用 inference 模拟 discovery 或 connection check；
- CLI 始终保留手工 Model identifier；
- 不硬编码模型列表。

### 5.2 DeepSeek

复核来源：

- [DeepSeek: List Models](https://api-docs.deepseek.com/api/list-models/)
- [DeepSeek: Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek: Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/)
- [DeepSeek: Models and Pricing](https://api-docs.deepseek.com/quick_start/pricing/)

截至复核日期：

- 官方 OpenAI-compatible Base URL 为 https://api.deepseek.com；
- 官方 GET /models 返回 data 中的真实 model id；
- client.models.list() 是 R03 选择的 SDK 等价调用路径；
- Chat Completion 支持非流式完整响应；
- 正常响应提供顶层 id、model、choices[0].message.content、finish_reason 以及 usage 的 prompt/completion/total token 字段；
- 官方错误状态包括 400、401、402、422、429、500 和 503；
- 402 归一为 quota_or_billing；
- DeepSeek /models 是正式 discovery/connection-check capability，因此 DeepSeek 的 404/405 不归类为 capability_unavailable。

### 5.3 Recheck conclusion

两家 Provider 均可复用官方 OpenAI Python SDK 的 client creation、models.list()、chat.completions.create()、基础异常映射和正常响应提取。Provider-specific 差异只保留：

- 推荐 Base URL 文案；
- Qwen /models 的 best-effort 层级与 404/405 capability_unavailable 语义；
- DeepSeek /models 的正式合同；
- 少量结构化 billing/model error override。

## 6. Implementation Constraints

实施必须遵守：

- 只支持 aliyun-bailian 与 deepseek；
- 只使用 R02 AIProviderConfig；
- 一个 Runtime module 足以承载 public contracts、dispatch、shared SDK logic 和 tiny adaptations；
- 不创建 services/providers/factory/manager 层级；
- 不创建动态 registry、plugin framework、route engine 或 Provider marketplace；
- 所有 public network operation 都只执行一次 application-level SDK operation；
- SDK max_retries=0；
- 固定有限 timeout 为 120.0 秒；
- complete 显式 stream=False；
- 不发送任何 thinking、reasoning、tools 或 sampling control；
- 不记录 API Key、Authorization、完整 request body 或 Candidate text；
- 不创建 secret scanner、privacy gate、network gate、evidence framework 或测试服务器。

如果具体模型的默认 thinking 行为不兼容非流式调用，Runtime 原样归一 Provider error；不得自动关 thinking、开 streaming、换模型、重试或 fallback。

## 7. Final Module / File Layout

| Path | Action | Responsibility |
|---|---|---|
| llm_provider_runtime.py | CREATE | Runtime public types/functions、SDK client、dispatch、list/connection/completion、error normalization |
| ai_provider_cli.py | CREATE | 独立交互式配置 CLI；只消费 R02 Store 与 Runtime |
| tests/test_llm_provider_runtime.py | CREATE | Runtime、SDK contract、Provider、verification integration tests |
| tests/test_ai_provider_cli.py | CREATE | CLI staging/save/display/network-action tests |
| requirements.txt | MODIFY | 增加单一直接依赖 openai>=2.53,<3.0 |
| simple_brush.py | MODIFY | 增加一个启动菜单选项及同级 dispatch |
| tests/test_simple_brush_ocr.py | MODIFY | 只扩展 StartupMenuTests |
| BossOCR.spec | CONDITIONAL MODIFY | 仅 packaged evidence 证明 SDK 自动收集不足时最小修正 |

不增加 package directory，不移动既有文件。

## 8. Runtime Public API

llm_provider_runtime.py 必须提供以下 public contract：

~~~python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ai_provider_config import AIProviderConfig, AIProviderConfigStore


LLM_REQUEST_TIMEOUT_SECONDS = 120.0


class LLMOperation(str, Enum):
    LIST_MODELS = "list_models"
    TEST_CONNECTION = "test_connection"
    COMPLETE = "complete"


class LLMMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMRuntimeErrorCode(str, Enum):
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    QUOTA_OR_BILLING = "quota_or_billing"
    INVALID_REQUEST = "invalid_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    PROVIDER_SERVER_ERROR = "provider_server_error"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUPPORTED_PROVIDER = "unsupported_provider"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LLMMessage:
    role: LLMMessageRole
    content: str


@dataclass(frozen=True)
class LLMCompletionRequest:
    messages: tuple[LLMMessage, ...]


@dataclass(frozen=True)
class LLMCompletionResult:
    content: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    finish_reason: str | None
    request_id: str | None


@dataclass(frozen=True)
class LLMConnectionTestResult:
    provider: str
    completed_at: datetime
    verification_writeback_applied: bool


class LLMRuntimeError(RuntimeError):
    def __init__(
        self,
        *,
        code: LLMRuntimeErrorCode,
        provider: str | None,
        operation: LLMOperation,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
        verification_writeback_applied: bool | None = None,
        verification_writeback_error: str | None = None,
    ) -> None:
        ...


def list_models(config: AIProviderConfig) -> tuple[str, ...]:
    ...


def test_connection(
    config: AIProviderConfig,
    store: AIProviderConfigStore,
) -> LLMConnectionTestResult:
    ...


def complete(
    config: AIProviderConfig,
    request: LLMCompletionRequest,
) -> LLMCompletionResult:
    ...
~~~

这些 dataclass 均 immutable。除 exception 上两个精确的 verification outcome 字段外，不增加 Result/metadata 对象或 exception subclass。

test_connection() 返回 LLMConnectionTestResult 本身即表示 remote check succeeded；remote check 未成功时一律抛 LLMRuntimeError。因此不再增加恒为 true 的 remote_check_succeeded 字段。verification_writeback_applied=False 精确表示远端成功但 R02 stale protection 未应用旧结果。

### 8.1 Operation readiness

所有 public operation 首先：

1. 验证 config 是 AIProviderConfig；
2. 验证 provider 非空并且是两个 canonical id 之一；
3. 未知非空 provider 返回 unsupported_provider；
4. list_models() 与 test_connection() 要求 provider、api_key、base_url 非空，model 可空；
5. complete() 要求 config.is_complete 为 true；
6. 缺失必要字段或类型不符返回 invalid_request；
7. readiness 失败时不创建 OpenAI client、不发网络请求、不写 verification。

错误 message 使用固定、安全、可操作的文本，不包含配置值。

## 9. Completion Request Contract

LLMCompletionRequest 只允许 messages。LLMMessage 只允许 role 和 content。

为了保证所有 Runtime 失败都使用 LLMRuntimeError，两个 request dataclass 不在 __post_init__ 抛出 ValueError；complete() 在任何 SDK 调用前执行本地验证：

- request 必须是 LLMCompletionRequest；
- messages 必须是 tuple；
- messages 必须至少有一项；
- 每项必须是 LLMMessage；
- role 必须是 LLMMessageRole.SYSTEM、USER 或 ASSISTANT；
- content 必须是 str；
- content.strip() 必须非空。

任一失败均抛出：

- code = invalid_request；
- operation = complete；
- 不创建 client，不调用 Provider。

发送给 SDK 的 messages 按输入顺序转换为：

~~~python
[
    {"role": message.role.value, "content": message.content}
    for message in request.messages
]
~~~

保留原 content，不自动 trim、改写或拼接。

Request 不包含也不得通过额外参数接受 api_key、base_url、provider/model override、stream、temperature、top_p、tools、response_format、thinking、reasoning_effort 或 extra_body。model 只能来自 config.model。

## 10. Completion Result Contract

complete() 只读取第一项 choice。成功响应必须满足：

- response.choices 是可索引且至少有一项；
- choices[0].message 存在；
- message.content 是 str 且 content.strip() 非空。

否则抛 malformed_response，不把空或无法解释的 shape 当成功。

提取规则：

| Result field | Rule |
|---|---|
| content | choices[0].message.content，保留原值 |
| provider | config.provider |
| model | response.model 为非空 str 时使用它，否则回退 config.model |
| input_tokens | usage.prompt_tokens 是非 bool 的非负 int 时使用，否则 None |
| output_tokens | usage.completion_tokens 是非 bool 的非负 int 时使用，否则 None |
| total_tokens | usage.total_tokens 是非 bool 的非负 int 时使用，否则 None |
| finish_reason | choices[0].finish_reason 是 str 时使用，否则 None |
| request_id | 顶层 response.id 为非空 str 时优先；否则 response._request_id 为非空 str 时使用；否则 None |

usage 整体缺失时三个 token 字段全部为 None；单个字段不可用时只将该字段设为 None。不得自行计算 total_tokens。

request_id 在 R03 v1 中表示 best available provider response/request correlation id。使用 completion 顶层 id 时如实保存；不另建 metadata object。

## 11. Error Contract

### 11.1 Exception invariants

LLMRuntimeError：

- RuntimeError 的 message/args[0] 等于安全 message；
- code、operation 必须为对应 enum；
- provider 在尚无可用 Provider 时允许 None；
- status_code 只保存可用 HTTP status；
- request_id 只保存可用 correlation id；
- verification_writeback_applied 与 verification_writeback_error 仅由 test_connection() 使用；
- 不保存 raw request、headers、API Key 或完整 Provider body。

### 11.2 Base SDK mapping

先读取结构化 provider code 并应用 11.3 的少量 override，再使用以下基础映射：

| OpenAI SDK exception / HTTP status | Runtime code |
|---|---|
| APITimeoutError 或 408 | timeout |
| APIConnectionError | network |
| AuthenticationError 或 401/403 | authentication |
| RateLimitError 或 429 | rate_limit |
| BadRequestError、UnprocessableEntityError 或 400/422 | invalid_request |
| InternalServerError 或 500–599 | provider_server_error |
| COMPLETE 的 404 | model_unavailable |
|非 Qwen capability case 的 404/405 | invalid_request |
|其它 APIStatusError | unknown |
|其它 OpenAIError | unknown |

Runtime 不捕获 KeyboardInterrupt、SystemExit 或 BaseException。显式的 response parser 错误归一为 malformed_response；未可靠归属的 SDK 错误使用 unknown。

### 11.3 Minimal provider overrides

结构化 code 只从以下位置读取：

1. exception.body 根级 code；
2. exception.body.error.code；
3.均不可用则无 override。

request_id 只按以下顺序读取：

1. exception.request_id；
2. exception.response.headers 的 x-request-id，大小写不敏感；
3. exception.body 根级 request_id；
4.否则 None。

Override：

- DeepSeek HTTP 402 → quota_or_billing；
- Qwen Arrearage、AllocationQuota.FreeTierOnly、CommodityNotPurchased、PrepaidBillOverdue、PostpaidBillOverdue → quota_or_billing；
- COMPLETE 中 Qwen Model.AccessDenied、ModelNotFound、model_not_found、model_not_supported → model_unavailable；
- Qwen LIST_MODELS 或 TEST_CONNECTION 中 HTTP 404/405 → capability_unavailable。

不基于自由文本 message 做关键词猜测。未列出的 code 回到基础 status/SDK type 映射。

### 11.4 Safe messages

Public message 使用 Runtime 自己的固定分类文案，可附 status_code，但不拼接 str(exception)、raw body、request headers 或原 messages。CLI 只显示这些安全字段。

## 12. Provider Dispatch

dispatch 使用直接 if/elif，不创建 registry：

~~~python
if config.provider == PROVIDER_ALIYUN_BAILIAN:
    ...
elif config.provider == PROVIDER_DEEPSEEK:
    ...
else:
    raise LLMRuntimeError(code=UNSUPPORTED_PROVIDER, ...)
~~~

共享代码：

- readiness validation；
- OpenAI client creation；
- chat.completions.create()；
- completion response extraction；
- models.list() response normalization；
- 基础 SDK exception/status mapping；
- safe request-id extraction。

Tiny Provider-specific adaptation：

- Base URL recommendation 只在 CLI；
- Qwen models.list() 是 best-effort，404/405 为 capability_unavailable；
- DeepSeek models.list() 是正式 capability；
- 少量 structured error override。

## 13. OpenAI SDK Client Configuration

只使用官方 openai Python SDK，不引入 DashScope SDK。

依赖冻结为：

~~~text
openai>=2.53,<3.0
~~~

依据：

- [OpenAI official Python library guidance](https://developers.openai.com/api/docs/libraries) 保持 OpenAI() client、client.models.list() 与 client.chat.completions.create() 的官方 SDK 路径；
- 2026-08-15 使用官方 PyPI index 执行 binary/no-deps dry-run，Python 3.10 target 对该 range 成功解析 openai 2.54.0；
- 同一 range 在当前 Python 3.11.9 环境也成功解析 openai 2.54.0；
- 因而该 dependency contract 满足 repository 的 Python 3.10+ / 当前 Python 3.11 compatibility requirement，并明确排除 3.0 及后续 major。
- 实施测试会直接验证本 TID 使用的 OpenAI、exception、models.list() 和 chat.completions.create() surface。

requirements.txt 只增加 openai 这一直接依赖；不直接声明其 transitive dependencies。

每个 public network operation 创建一个 client：

~~~python
OpenAI(
    api_key=config.api_key,
    base_url=config.base_url,
    timeout=LLM_REQUEST_TIMEOUT_SECONDS,
    max_retries=0,
)
~~~

固定 policy：

- timeout = 120.0 秒；
- application retry = 0；
- SDK max_retries = 0；
- 不增加 per-provider、per-operation 或用户可配置 timeout。

120 秒避免 batch candidate 场景无限挂起，同时不过度压缩 Provider 首次响应窗口。

## 14. Qwen Adapter

Qwen adapter 不是独立 class hierarchy；它只是 shared runtime 中的条件分支：

- provider id 必须是 PROVIDER_ALIYUN_BAILIAN；
- client 完全使用 config.api_key 和 config.base_url；
- list_models() 和 test_connection() 当前调用 client.models.list()；
- 该 models path 标记为 R03 v1 best-effort implementation；
- 明确的 404/405 → capability_unavailable；
- 其它异常进入真实 error mapping；
- complete() 复用 shared chat completion；
- 不发送 DashScope-specific extra_body；
- 不 inference fallback；
- 不硬编码 model ids。

CLI guidance 必须说明 Qwen Base URL 取决于官方控制台中的 region、Workspace 和 plan。可以展示少量官方格式示例，例如 Workspace-specific compatible-mode/v1 地址；不得把某一地址自动写成全球默认值。

## 15. DeepSeek Adapter

DeepSeek adapter 同样只是条件分支：

- provider id 必须是 PROVIDER_DEEPSEEK；
- 推荐 Base URL 是 https://api.deepseek.com；
- list_models() 与 test_connection() 调用 client.models.list()，等价于正式 GET /models；
- 404/405 不视为 capability_unavailable；
- HTTP 402 → quota_or_billing；
- complete() 复用 shared chat completion；
- 不发送 thinking controls。

Provider recommendation 只是 CLI 文案，不覆盖用户已保存的 base_url。

## 16. list_models() Implementation

时序：

1. readiness validation；
2. provider dispatch；
3.创建一次 OpenAI client；
4.精确调用一次 client.models.list()；
5. normalize 或抛 LLMRuntimeError；
6.返回 tuple[str, ...]。

Response normalization：

- response.data 必须是 list 或 tuple，否则 malformed_response；
- 每个 item.id 必须是 str，否则 malformed_response；
- id.strip() 为空时跳过；
- 非空 id 保留 Provider 原值与 Provider 顺序；
- 按完整 id 精确去重，保留第一次出现；
- 空结果合法，返回空 tuple；
- 不排序、不 alias、不增加价格或 capability metadata。

list_models() 不：

- 写 config；
- 写 verification；
- 调用 chat/completions；
- 缓存；
- 读取或替换 config.model；
- 硬编码完整模型列表。

## 17. test_connection() Implementation

### 17.1 Success path

1. 校验 config 与 store 类型以及 provider/api_key/base_url readiness；
2.捕获 checked_provider、checked_api_key、checked_base_url；
3.通过与 list_models() 相同的 Provider-specific non-inference models check 精确执行一次远端调用；
4.对 response.data 运行同样的 shape validation；空模型集合仍表示 endpoint/auth check 成功；
5.远端成功后生成 datetime.now(timezone.utc)；
6.调用 store.record_connection_verification()，status=VERIFIED，并传入 checked tuple；
7.返回 LLMConnectionTestResult：
   - provider = checked_provider；
   - completed_at = 上述 UTC 时间；
   - verification_writeback_applied = R02 返回的 bool。

False 仅表示 stale/current config 不可写，不表示 Provider 失败。

### 17.2 Remote failure with available capability

如果 capability 存在且实际 check 因 authentication、network、timeout、rate limit、quota/billing、invalid API response、Provider 5xx 等失败：

1.先把远端异常归一为 remote_error；
2.生成 timezone-aware UTC completed_at；
3.调用 R02 record_connection_verification(..., status=FAILED, completed_at=...)；
4.构造并抛出同 code/status/request_id/message 的 LLMRuntimeError；
5.将 verification_writeback_applied 设为 R02 返回的 True 或 False；
6. verification_writeback_error 保持 None。

False 是 stale write-back，不改变 remote error 分类。

### 17.3 Capability unavailable

Qwen 当前 Provider/region/Workspace/plan 明确 404/405，或未来 targeted implementation evidence 表明没有当前可用的非推理 check capability时：

- 抛 capability_unavailable；
- verification_writeback_applied=None；
- 不调用 record_connection_verification()；
- 不写 failed；
- 不写 verified；
- 不 inference fallback。

### 17.4 Write-back I/O failure

为同时表达远端事实与本地 persistence failure，但不引入 multi-error framework：

- 远端失败后 FAILED write-back 抛 AIProviderConfigIOError：
  -最终仍抛单个 LLMRuntimeError；
  - code/status_code/request_id 保留原 remote error；
  - verification_writeback_applied=None；
  - verification_writeback_error 固定为 "verification write-back failed locally"；
  -安全 message 明确“远端检查失败，且本地 verification 写回失败”，不包含底层 path/secret；
  - exception chaining 保留本地 I/O cause 供开发诊断，但 CLI 不打印 raw cause。
- 远端成功后 VERIFIED write-back 抛 AIProviderConfigIOError：
  -抛 code=unknown、operation=test_connection 的 LLMRuntimeError；
  - message 明确“Provider check succeeded, but verification write-back failed locally”；
  - verification_writeback_applied=None；
  - verification_writeback_error 使用同一固定文本；
  -不得将其显示为 Provider connectivity failure。

这两个字段只解决 test_connection 的远端结果与 R02 write-back 组合，不扩展为通用 Result framework。

## 18. R02 Verification Integration

Runtime 只调用现有：

~~~python
store.record_connection_verification(
    checked_provider=checked_provider,
    checked_api_key=checked_api_key,
    checked_base_url=checked_base_url,
    status=verification_status,
    completed_at=timezone_aware_utc_datetime,
)
~~~

其中 verification_status 只能按第 17 节时序取 ConnectionVerificationStatus.VERIFIED 或 ConnectionVerificationStatus.FAILED。

不得修改 R02 schema、枚举、serialization、atomic save、stale comparison 或 model exclusion rule。

语义矩阵：

| Remote outcome | R02 call | Requested status | Public outcome |
|---|---|---|---|
|有效非推理 check 成功 |是 | VERIFIED | LLMConnectionTestResult，applied 为 True/False |
|可用 capability 实际 check 失败 |是 | FAILED | LLMRuntimeError，携带 write-back True/False |
| capability_unavailable |否 |无 | LLMRuntimeError；现有状态不变 |
| readiness/unsupported 本地失败 |否 |无 | LLMRuntimeError；现有状态不变 |

不增加第四种 verification 状态、revision、generation、fingerprint、TTL 或 verification framework。

## 19. complete() Implementation

时序：

1.校验 complete config；
2.校验 LLMCompletionRequest；
3. provider dispatch；
4.创建一次 configured OpenAI client；
5.精确执行一次：

~~~python
client.chat.completions.create(
    model=config.model,
    messages=normalized_messages,
    stream=False,
)
~~~

6.按第 10 节提取 LLMCompletionResult；
7.异常按第 11 节归一。

不得传入任何未列出的 SDK request field。不得：

- application retry；
- SDK retry；
- streaming；
- Provider/model switch；
- fallback；
- verification write-back；
- 自动修改 config；
- 自动修改 thinking。

无论成功或失败，每次 complete() 最多调用一次 chat.completions.create()。

## 20. CLI AI Provider Configuration

### 20.1 Module contract

ai_provider_cli.py 提供：

~~~python
def run_ai_provider_configuration(
    store: AIProviderConfigStore | None = None,
) -> None:
    ...
~~~

store 为 None 时构造 AIProviderConfigStore()，从而使用 R02 default path。测试通过传入临时 Store 并 patch 本模块导入的 list_models/test_connection；不额外建立 dependency-injection framework。

### 20.2 Entry/load behavior

- INCOMPLETE 或 VALID：使用 result.config 作为 staged snapshot；
- NOT_CONFIGURED：以内存中的 AIProviderConfig() 开始；
- INVALID 或 UNSUPPORTED_VERSION：显示安全错误，以空 AIProviderConfig() 作为尚未持久化的 staged snapshot；
- unusable persisted file 只有在用户明确选择 Save 后才会被新 v1 config 替换；
- 本地 I/O error 被安全显示并返回当前 CLI 菜单，不打印 traceback 或 API Key。

staged snapshot 使用 AIProviderConfig，不定义第二个持久化 schema。内部小 helper 在 connection tuple 改变时把 staged verification 设为 UNVERIFIED/None；model-only staged change 保留 verification。最终保存仍必须通过 R02 save/update，使 R02 规则成为持久化权威。

### 20.3 Menu actions

循环菜单至少有：

1. Show current state
2. Select Provider
3. Change API Key
4. Change Base URL
5. List Models
6. Select Model from latest list
7. Enter Model manually
8. Save
9. Test Connection
10. Refresh Status
0. Return to startup menu

具体中文文案可与现有 CLI 风格一致，但动作与语义不得省略。

Show current state 只显示：

- provider；
- base_url；
- model；
- connection_verification_status；
- last_verification_time；
- config load/staged 状态；
- config.api_key_display() 的 configured/not configured。

不得显示 key fragment 或完整 key。

### 20.4 Provider and Base URL

Select Provider 只接受两个 canonical id；改变 provider 时：

- 不自动改写 base_url；
- 清除 latest discovered models；
- 按 R02 connection invalidation 语义更新 staged status；
- 显示对应 recommendation。

Recommendation：

- DeepSeek：https://api.deepseek.com；
- Qwen：提示用户从 Alibaba Model Studio 当前 region/Workspace/plan 获取 compatible-mode/v1 Base URL，并固定展示以下非默认示例：
  - Beijing Workspace：https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
  - Singapore Workspace：https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
  - US public compatible endpoint：https://dashscope-us.aliyuncs.com/compatible-mode/v1
- recommendation 只显示，不自动覆盖任何 persisted/staged 非空 base_url。

Change Base URL 的空输入保留现有值。

### 20.5 API Key

- 使用标准库 getpass.getpass()；
- 输入不回显；
- 空输入保留现有 key；
- 不提供 reveal、fragment、clipboard 或 vault；
- connection tuple 改变后清除 latest models 并将 staged verification 设为 unverified。

### 20.6 Model flow

List Models：

- 要求 staged provider/api_key/base_url 完整；
- 这是用户明确触发的联网动作；
- 调用 Runtime list_models(staged_config)；
- 成功时保存最新 tuple 供当前 CLI session 选择；
- 空列表或失败时明确提示仍可手工输入；
- 失败不清除已保存 model，不写 verification；
- 不调用 test_connection 或 complete。

Select Model from latest list：

- 只能从最近一次成功 list result 的编号中选择；
- 没有结果时提示先 list 或手填；
- 只改变 staged model。

Manual Model Entry：

- 始终可用；
- 非空输入作为精确 model identifier；
- 空输入保留现有 model；
- 不 alias、不验证价格或 capability。

### 20.7 Save

Save 是唯一一般 staged persistence 动作：

- 重新 load 当前 Store；
- 当前是 INCOMPLETE/VALID 时调用 store.update(current, provider=..., api_key=..., base_url=..., model=...)；
- NOT_CONFIGURED、INVALID 或 UNSUPPORTED_VERSION 时，构造 v1 AIProviderConfig 并调用 store.save()；
- 允许 provider + api_key + base_url 已填而 model 为空的 incomplete config；
- model-only save 由 R02 保留 verification；
- connection field change 由 R02 失效 verification；
- 保存后 reload 并显示安全状态。

### 20.8 Test Connection

Test Connection 的冻结用户流程：

1.要求 staged provider/api_key/base_url 非空，model 可空；
2.提示这是一项非推理网络检查，且将先保存当前 connection fields；
3.用户明确确认继续；拒绝时不保存、不联网；
4.用第 20.7 节相同路径先保存 staged snapshot；
5.将实际保存后返回/重载的 AIProviderConfig snapshot 传给 test_connection(snapshot, store)；
6.成功、remote failure、stale 或 write-back I/O error 后都 reload Store；
7.显示远端检查与 verification write-back 是否 applied 的区别；
8. capability_unavailable 明确显示“当前无可用非推理验证能力，verification 状态未因此改为 failed”，并提示仍可手填 model；
9.绝不调用 complete()。

### 20.9 Refresh and return

- Refresh Status 从 Store 重新 load；存在未保存 staged change 时先确认是否丢弃；
- refresh 后清除 latest models；
- Return 直接从 run_ai_provider_configuration() 返回；
- 所有正常返回都回到 simple_brush.py 启动菜单。

## 21. Startup Menu Integration

simple_brush.py 最小修改：

1.静态导入 run_ai_provider_configuration；
2. choose_startup_action() 增加：
   - 3. AI Provider Configuration；
   -输入 3 返回 "ai_provider_config"；
   -无效提示更新为 1、2、3 或 0；
3. main() 的 while dispatch 增加：

~~~python
if action == "ai_provider_config":
    run_ai_provider_configuration()
    continue
~~~

4. calibration 继续走现有 launch_calibration_template()；
5. run 与 exit 返回语义不变。

不得修改：

- parse_args()；
- is_noninteractive_startup()；
- 任何现有 flag；
- run()；
- calibration semantics；
- OCR/Candidate/Screening/Action 主链。

Runtime/CLI module import 不构造 client、不访问 Store、不发网络。普通交互 run、calibration 和三个非交互入口均为零 Provider operation。

## 22. Dependency Changes

requirements.txt 增加一行：

~~~text
openai>=2.53,<3.0
~~~

不修改 requirements-ocr.txt 或 requirements-build.txt，不直接声明 openai 的 transitive dependency。

实施时先安装/解析当前 requirements，然后用 pip check 和 source import 验证。依赖 resolver warning 若与 R03 无关，不阻塞独立代码 Change；若 openai>=2.53,<3.0 无法在 supported Python 3.10+ 解析，或实际 2.x public surface 与本 TID 不兼容，则停止该合同点并升级给 Human。

## 23. Packaging Plan

默认 BossOCR.spec 不变，因为 Analysis 从 simple_brush.py 的静态 import 可追踪到 ai_provider_cli、llm_provider_runtime 和 openai。

实施后做 targeted packaging verification：

1.用当前 BossOCR.spec 执行一次 clean/noconfirm PyInstaller build；
2.启动 packaged Ocria.exe，观察新增菜单，进入 AI Provider Configuration 后立即 Return，再 Exit；
3.该过程不输入凭据、不选择联网动作；
4.另以输入 0 的 packaged startup smoke 验证可导入并正常退出。

只有出现可复现且明确归因于 openai SDK module/metadata collection 的 packaged import failure，才允许 conditional 修改 BossOCR.spec：

- 先记录缺失 module/metadata 的明确错误；
- 只添加证明必要的 hidden import、data 或 copy_metadata；
- 不使用未经证明的全依赖 blanket collection；
- 修正后只重复 targeted package build/smoke；
- 不生成 release archive，不 tag/release。

普通 PyInstaller warning 或与 R03 无关的环境问题不自动触发 spec 修改。

## 24. Test Strategy

所有自动测试使用 unittest、unittest.mock、临时目录和 SDK-shaped fake。无真实 API Key、无真实网络、无付费 inference、无 VCR/proxy/custom server。

### 24.1 tests/test_llm_provider_runtime.py

覆盖：

- public enum/dataclass/signature 与 immutability；
- 两个 Provider dispatch、未知 Provider；
- 各 operation readiness；
- 空 messages、非法 role、空/非字符串 content；
- OpenAI 构造参数 api_key/base_url/120.0/max_retries=0；
- 每次 operation 的 SDK call count；
- DeepSeek models success；
- model id 去空、稳定去重、空 collection、malformed shape；
- list auth/timeout/network/rate limit/5xx；
- Qwen 404/405 capability_unavailable；
- list 无 verification、无 chat fallback；
- test success → VERIFIED；
- test real failure → FAILED；
- capability_unavailable → zero write-back；
- stale write-back False；
- remote failure + local I/O write-back composite；
- remote success + local I/O write-back；
- test never calls chat completion；
- complete request message 顺序与精确字段；
- model、usage、finish_reason、request_id 提取与 fallback；
- 缺失 usage → None；
- missing/empty content → malformed_response；
- auth/timeout/network/rate/quota/model/5xx/unknown；
- stream=False、一次 chat call、无 retry、无 verification。

SDK exception tests 构造最小 httpx Request/Response 与 OpenAI exception，或 patch 内部单次 SDK call boundary；不得用 message keyword 猜测。

R02 integration 使用临时 AIProviderConfigStore 和真实 record_connection_verification()，只覆盖 R03 boundary，不复制 R02 serialization 全套测试。

### 24.2 tests/test_ai_provider_cli.py

覆盖：

- 本地 display；
- API Key 只显示 configured/not configured；
- getpass 输入且 key 不出现在 output；
- 空 key 保留；
- 两个 Provider 选择；
- Base URL recommendation 不覆盖当前值；
- list success 与 latest selection；
- list failure/empty 后 manual entry 仍可用；
- incomplete config 保存；
- model-only save 保留 verification；
- connection save 通过 R02 失效 verification；
- test 前确认、save、snapshot 与 Store 传参；
- test success/failure/stale/capability unavailable/write-back I/O UX；
- refresh；
- return；
- CLI 不调用 complete。

### 24.3 tests/test_simple_brush_ocr.py

只修改 StartupMenuTests：

- 菜单包含新选项，3 dispatch 到 run_ai_provider_configuration()；
- CLI 返回后再次显示启动菜单；
- 原 run choice 的 Provider/CLI call count 为 0；
- calibration choice 的 Provider/CLI call count 为 0；
- --auto、--keywords、--calibration-profile 的 Provider/CLI call count 为 0；
- 现有 run/calibration/exit/invalid 行为保持。

不得为此运行整个 legacy test file 或整个 legacy suite；最终只运行 StartupMenuTests。

### 24.4 Offline startup assertion

Startup tests patch simple_brush.run_ai_provider_configuration 和 Runtime OpenAI constructor，断言普通 run、calibration 与非交互路径均未调用。Runtime tests另断言 readiness error 不构造 client。

不增加 network monitor/gate。

## 25. Optional Real Provider Smoke

Optional smoke 与 automated acceptance 完全分离。没有真实 API Key 不是验收失败。

由 Human 提供凭据并明确授权时：

- DeepSeek 可执行一次 list_models() 和一次 test_connection()；
- Qwen 可执行一次 current best-effort list_models()/test_connection()，结果允许 capability_unavailable；
- 只有 Human 再次明确授权付费调用时，每家可执行最多一次最小 complete()；
- 记录 code/status/request_id 等安全结果，不记录 key、Authorization 或 prompt body；
- 不自动 retry。

Smoke 只证明 Runtime connectivity/completion path，不证明模型质量、screening 质量或 Candidate 正确性；后者属于 R04。

## 26. Change Plan

### Change 1 — Runtime contracts、SDK base、list_models 与 complete

**Objective**

建立最小 public Runtime、SDK client、Provider dispatch、error normalization、list_models() 与 complete()。

**Allowed files**

- CREATE llm_provider_runtime.py
- CREATE tests/test_llm_provider_runtime.py
- MODIFY requirements.txt

**Forbidden files / areas**

- ai_provider_config.py 与其 tests
- simple_brush.py
- OCR、Candidate、Screening、calibration、mouse/action code
- BossOCR.spec

**Preconditions**

- R03 RPD v0.2 与本 TID 已冻结供实施；
- openai>=2.53,<3.0 可在 Python 3.10 target 与当前 Python 3.11 环境解析。

**Exact implementation work**

- 实现第 8–16、19、22 节合同；
- client timeout=120.0、max_retries=0；
- Qwen/DeepSeek 用直接 dispatch；
- Qwen models.list() 明确保留 best-effort 语义；
- 实现 safe structured error mapping；
- 不实现 test_connection write-back 或 CLI。

**Public contract affected**

- LLMOperation、LLMMessageRole、LLMRuntimeErrorCode；
- LLMMessage、LLMCompletionRequest、LLMCompletionResult；
- LLMRuntimeError；
- list_models()、complete()；
- LLM_REQUEST_TIMEOUT_SECONDS。

**Tests to add / modify**

- Runtime contract/readiness；
- client configuration；
- Provider dispatch；
- list_models success/normalization/errors；
- complete validation/extraction/errors/single call。

**Exact targeted test command**

~~~powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_llm_provider_runtime.py" -v
~~~

**Evidence expected**

- requirements diff；
- Runtime/test diff；
- test exit 0；
- fake client assertions显示正确参数、一次 operation、无 retry/fallback。

**Stop / escalation condition**

- openai>=2.53,<3.0 无法在 Python 3.10+ 解析，或其实际 2.x public SDK surface 无法满足 frozen operations；
- 官方 Provider API 与 Frozen R03 的必要行为发生真实冲突。

### Change 2 — test_connection 与 R02 verification integration

**Objective**

在既有 Runtime 上增加一次非推理 check、VERIFIED/FAILED write-back、stale 与 composite I/O 语义。

**Allowed files**

- MODIFY llm_provider_runtime.py
- MODIFY tests/test_llm_provider_runtime.py

**Forbidden files / areas**

- ai_provider_config.py
- tests/test_ai_provider_config.py
- R02 schema/enums
- CLI、startup、OCR 主链

**Preconditions**

- Change 1 通过；
- R02 Store 当前 public API 未变化。

**Exact implementation work**

- 增加 LLMConnectionTestResult；
- 实现第 17–18 节完整时序；
- 复用 models check；
- capability_unavailable zero write-back；
- 使用 timezone-aware UTC；
- 实现 remote error 与 local write-back failure 的单 exception 组合。

**Public contract affected**

- LLMConnectionTestResult；
- test_connection()；
- LLMRuntimeError 的两个 verification outcome 字段。

**Tests to add / modify**

- success/failed/capability unavailable；
- stale True/False；
- remote failure + I/O failure；
- remote success + I/O failure；
- 真实临时 R02 Store boundary；
- zero chat completion。

**Exact targeted test commands**

~~~powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_llm_provider_runtime.py" -v
.\venv\Scripts\python.exe -m unittest tests.test_ai_provider_config.AIProviderConfigVerificationWriteBackTests -v
~~~

**Evidence expected**

- write-back call args；
- 持久化 status/time；
- stale 不覆盖；
- capability_unavailable call count 0；
- composite exception fields；
- 两个命令 exit 0。

**Stop / escalation condition**

- 当前 R02 record_connection_verification() 无法表达 Frozen R03 的 verified/failed/stale 语义；
- 需要第四种状态、revision 或 R02 schema 变更才能实现。

### Change 3 — AI Provider Configuration CLI

**Objective**

实现独立、可返回的 staged CLI，覆盖配置、model discovery、save、connection test 与安全显示。

**Allowed files**

- CREATE ai_provider_cli.py
- CREATE tests/test_ai_provider_cli.py

**Forbidden files / areas**

- simple_brush.py
- ai_provider_config.py
- Runtime public contract
- OCR/Candidate/Screening/action code

**Preconditions**

- Changes 1–2 通过；
- CLI 只消费其 public contract。

**Exact implementation work**

- 实现第 20 节 function、loop、staging/save/test/refresh；
- 使用 getpass；
- recommendation 不覆盖 persisted value；
- test 前确认并保存；
- capability unavailable UX；
- 不提供 Test Inference。

**Public contract affected**

- run_ai_provider_configuration(store=None)。

**Tests to add / modify**

- 第 24.2 节全部 CLI paths；
- 使用临时 Store 和 patched Runtime functions；
- 断言 output 无 key。

**Exact targeted test command**

~~~powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_ai_provider_cli.py" -v
~~~

**Evidence expected**

- CLI/test diff；
- test exit 0；
- captured prompts/output；
- R02 Store 最终状态；
- Runtime call counts。

**Stop / escalation condition**

- 实现 frozen flow 必须绕过 R02 Store 或建立第二套配置；
- R02 incomplete config 无法保存 connection tuple 后先测试。

### Change 4 — Startup integration 与 targeted packaging verification

**Objective**

以最小菜单 dispatch 挂载 CLI，并证明 source/packaged startup 不会自动联网。

**Allowed files**

- MODIFY simple_brush.py
- MODIFY tests/test_simple_brush_ocr.py，仅 StartupMenuTests
- CONDITIONAL MODIFY BossOCR.spec

**Forbidden files / areas**

- run() 行为
- parse_args()/is_noninteractive_startup() 语义
- calibration implementation
- OCR/Candidate/Screening/action code
- build release/archive/tag scripts

**Preconditions**

- Changes 1–3 通过；
- source imports 通过。

**Exact implementation work**

- 实现第 21 节菜单与 dispatch；
- 扩展 targeted startup tests；
- 执行第 23 节 package build/smoke；
- 只有明确 SDK collection failure 才最小修改 spec。

**Public contract affected**

- choose_startup_action() 新返回值 "ai_provider_config"；
- simple_brush.main() 新同级 dispatch；
- 既有 run/calibrate/exit contract 不变。

**Tests to add / modify**

- 只扩展 StartupMenuTests；
- 运行最终 Runtime/CLI/R02 boundary tests；
- targeted package smoke。

**Exact targeted test commands**

~~~powershell
.\venv\Scripts\python.exe -m unittest tests.test_simple_brush_ocr.StartupMenuTests -v
.\venv\Scripts\python.exe -m PyInstaller --clean --noconfirm BossOCR.spec
"0" | .\dist\Ocria\Ocria.exe
~~~

**Evidence expected**

- 最小 startup diff；
- StartupMenuTests exit 0；
- Provider/client call count 0；
- PyInstaller exit 0；
- packaged menu 可启动并退出；
- 若 spec 改动，保留原始 missing-module/metadata evidence。

**Stop / escalation condition**

- 最小菜单挂载仍必须改变非交互或 run() contract；
- required SDK 与 supported Python/package target 存在真实不兼容。

Packaging warning或 unrelated local environment failure 不阻塞已独立验证的 Runtime/CLI Change；只按证据处理受影响项。

## 27. File Scope Matrix

| Scope | Files / areas |
|---|---|
| CREATE | llm_provider_runtime.py；ai_provider_cli.py；tests/test_llm_provider_runtime.py；tests/test_ai_provider_cli.py |
| MODIFY | requirements.txt；simple_brush.py；tests/test_simple_brush_ocr.py 的 StartupMenuTests |
| CONDITIONAL MODIFY | BossOCR.spec，仅 SDK collection evidence 成立时 |
| MUST NOT MODIFY | CODEX-CONSTITUTION.md；R03/R02 RPD/TID/acceptance docs；ai_provider_config.py；tests/test_ai_provider_config.py；requirements-ocr.txt；requirements-build.txt；OCR core；Candidate schemas；screening/decision rules；mouse_motion；calibration semantics；favorite/forward；run() 业务行为；release/tag/archive scripts |

实现 Agent 不得顺手修复、格式化或重构 scope 外既有问题。

## 28. Acceptance Mapping AC-01–AC-25

| AC | Change | Implementation evidence | Verification type |
|---|---|---|---|
| AC-01 Two-provider support | 1 |两个 canonical provider dispatch 与成功 fake calls | Automated |
| AC-02 R02 consumption | 1,2,3 |函数只接收 AIProviderConfig；CLI 只用 AIProviderConfigStore | Automated + diff |
| AC-03 Minimal selection | 1 | if/elif dispatch；未知 id → unsupported_provider | Automated |
| AC-04 Shared runtime | 1 |共享 OpenAI client/chat/parser；仅 tiny branch | Diff + automated |
| AC-05 DeepSeek discovery | 1 | client.models.list()、真实 id normalization | Automated；Optional smoke |
| AC-06 Qwen best-effort discovery | 1 | models.list()、404/405 capability_unavailable、无硬编码/inference | Automated；Optional smoke |
| AC-07 Manual model entry | 3 | list 失败/空后仍可手填保存 | Automated |
| AC-08 Non-inference connection test | 2 | models.list() only；chat call count 0 | Automated；Optional smoke |
| AC-09 Verification write-back | 2 | success VERIFIED、real failure FAILED、capability unavailable zero write | Automated |
| AC-10 Stale protection | 2 |真实 R02 Store 返回 False 且不覆盖 | Automated |
| AC-11 Non-streaming completion | 1 | stream=False、一次 create | Automated；Optional paid smoke |
| AC-12 Runtime inputs | 1 | client/model 仅来自 config；request 无 override fields | Automated + type contract |
| AC-13 Normalized result | 1 |八字段 extraction 与 None/fallback | Automated |
| AC-14 Malformed response | 1 | missing/empty content 与 bad shape → malformed_response | Automated |
| AC-15 Normalized errors | 1,2 |完整 enum、SDK/status/provider overrides | Automated |
| AC-16 No automatic retry | 1 | max_retries=0；operation call count=1 | Automated |
| AC-17 Finite timeout | 1 | constructor timeout=120.0；timeout mapping | Automated |
| AC-18 Default thinking behavior | 1 | SDK kwargs 精确断言无 thinking/reasoning/extra_body | Automated |
| AC-19 Full CLI flow | 3,4 |全部菜单动作、保存/测试/refresh/return | Automated + packaged manual |
| AC-20 API Key display | 3 | api_key_display/getpass；captured output 无 key | Automated |
| AC-21 Base URL preservation | 3 | recommendation 不改变 persisted/staged 非空值 | Automated |
| AC-22 Offline daily startup | 4 | run/calibration/noninteractive 均零 CLI/Provider client call | Automated + packaged smoke |
| AC-23 No Test Inference | 1,3 | CLI 无 complete action；complete 唯一 chat path | Diff + automated |
| AC-24 Legacy isolation | 4 |仅 startup dispatch diff；原 startup tests；run() 不改 | Targeted regression + diff |
| AC-25 Packaging readiness | 1,4 | Python 3.11 source import、PyInstaller build、packaged menu exit | Automated command + manual packaged check |

Mapping 覆盖 AC-01 至 AC-25，没有创建新的产品 AC。Optional real Provider smoke 不替代任何 automated acceptance。

## 29. Final Verification Commands

以下是 implementation 完成后的最小充分命令；从第一次执行起保留原始 exit/result，不为补证重复运行已成功的昂贵步骤。

~~~powershell
.\venv\Scripts\python.exe -m pip install --dry-run --ignore-installed --only-binary=:all: --python-version 3.10 --no-deps --index-url https://pypi.org/simple "openai>=2.53,<3.0"
.\venv\Scripts\python.exe -m pip install --dry-run --ignore-installed --only-binary=:all: --no-deps --index-url https://pypi.org/simple "openai>=2.53,<3.0"
.\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr.txt
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe -m py_compile llm_provider_runtime.py ai_provider_cli.py simple_brush.py
.\venv\Scripts\python.exe -c "import openai, llm_provider_runtime, ai_provider_cli; print(openai.__version__)"

.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_llm_provider_runtime.py" -v
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_ai_provider_cli.py" -v
.\venv\Scripts\python.exe -m unittest tests.test_ai_provider_config.AIProviderConfigVerificationWriteBackTests -v
.\venv\Scripts\python.exe -m unittest tests.test_simple_brush_ocr.StartupMenuTests -v

.\venv\Scripts\python.exe -m PyInstaller --clean --noconfirm BossOCR.spec
"0" | .\dist\Ocria\Ocria.exe

git diff --check
git status --short --branch
~~~

随后做一次不联网的 packaged manual check：

1.启动 Ocria.exe；
2.确认菜单含 AI Provider Configuration；
3.进入后立即 Return；
4.回到启动菜单并 Exit；
5.不选择 List Models/Test Connection，不输入真实 key。

不默认运行 legacy full suite，不执行 build.bat 的完整 release/archive 流程。风险依据只涉及新 Runtime、CLI、R02 verification boundary 和 simple_brush startup dispatch，因此以上 targeted regression 足够。

## 30. Risks / Escalation Conditions

真正需要停止相关合同点并升级给 Human 的条件只有：

- Frozen R03 RPD 与 R02 public contract 出现无法同时满足的冲突；
- Alibaba 或 DeepSeek 官方 API 事实改变到无法满足 Frozen R03 必要语义；
- openai>=2.53,<3.0 无法支持 Python 3.10+ 或缺失所需 public API；
- 实现 connection verification 必须新增 R02 状态/schema/revision；
- 最小 startup integration 必须改变既有非交互或 run() 行为。

以下不是自动 escalation：

- Qwen 某 region/Workspace/plan 返回 capability_unavailable；
- list result 为空；
- optional metadata 为 None；
- ordinary PyInstaller warning；
- unrelated legacy/environment test issue；
- 没有真实 Provider credentials；
- 未执行付费 smoke。

这些情况按本 TID 的精确语义记录，不扩大 scope。

## 31. Out of Scope

- R04 Candidate screening；
- 模型质量评估；
- Candidate schema、Decision、favorite/forward；
- OCR、mouse motion、calibration；
- streaming；
- retry/backoff；
- thinking/reasoning controls；
- tool calling、response format、sampling controls；
- dynamic Provider plugin/registry；
- model cache、price/capability catalog；
- Provider/model fallback、load balance、circuit breaker；
- Test Inference CLI；
- secret vault/clipboard/key reveal；
- R02 schema、状态或 stale framework 修改；
- 完整 legacy regression；
- 真实付费 inference 自动测试；
- release、commit、push、merge、tag。

## 32. Implementation Handoff

实施顺序固定为 Change 1 → Change 2 → Change 3 → Change 4。

每个 Change：

- 只修改 Allowed files；
- 先运行该 Change targeted tests；
- 保留首次充分 evidence；
- 不重新做 repository-wide investigation；
- 不重写已冻结 RPD/TID；
- 仅在第 30 节真实冲突时停止相关合同点并报告 Human。

Change 4 完成后按第 29 节执行一次最终 targeted verification。Optional real Provider smoke 必须由 Human 提供凭据并明确授权；付费 complete 永不属于自动验收。

本 TID 当前为 Version 0.2、Approved / Frozen for Implementation。本轮 Human Review 只冻结 dependency contract 与既有实施合同，没有实施代码。

截至本 TID v0.2 冻结，没有未决 Human product/architecture decision。
