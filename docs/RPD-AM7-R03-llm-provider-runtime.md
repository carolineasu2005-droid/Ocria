# Ocria Am7 AM7-R03 RPD：LLM Provider Runtime 与 Qwen / DeepSeek 接入

## 1. Metadata

| 项目 | 内容 |
| --- | --- |
| 产品 | Ocria |
| Generation / Codename | Am7 |
| Requirement | AM7-R03 |
| 文档类型 | RPD（Requirement / Product Design） |
| 文档版本 | 0.2 |
| 编写日期 | 2026-08-15（Asia/Shanghai） |
| 当前阶段 | Approved / Frozen for TID |
| Requirement Branch | `am7-r03-llm-provider-runtime` |
| 当前基线 | AM7-R02 merged baseline / `18502f1` |
| 上游配置合同 | AM7-R02 RPD v0.2、TID v0.1、Acceptance Report |
| 设计主题 | Unified LLM Provider Runtime、Alibaba Bailian / Qwen、DeepSeek、AI Provider Configuration CLI |

本文定义 AM7-R03 的 Requirement 与产品设计边界。它不授权编写 TID、实施代码、修改产品代码、执行 Provider 付费推理、提交 Git 变更或发布版本。

本设计遵守 `CODEX-CONSTITUTION.md` 的最小充分架构原则：只建立支持两个已冻结 Provider 所需的统一 Runtime、少量 Provider-specific adaptation 和现有 CLI 挂载，不建立插件框架、动态 Registry、自动路由、重试、failover、额外安全门禁或新的 verification 状态体系。

## 2. Requirement Summary

AM7-R03 解决一个明确问题：

> 在 AM7-R02 已经回答“当前配置是什么”的基础上，回答“如何真实连接并调用当前 Provider”。

R03 首版必须同时支持两个 canonical provider id：

- `aliyun-bailian`
- `deepseek`

统一 Runtime 能力冻结为：

- `list_models()`
- `test_connection()`
- `complete()`

核心链路为：

```text
AIProviderConfig
    -> provider selection
    -> minimal OpenAI-compatible runtime
    -> Alibaba Bailian / Qwen or DeepSeek
    -> list_models / test_connection / complete
    -> normalized result or normalized runtime error
```

R03 同时把 AM7-R02 尚未接入主流程的 AI Provider Configuration 作为完整 CLI 入口挂入现有启动菜单。普通启动仍然保持本地、离线且无推理费用；只有用户在配置入口中明确选择“获取模型”或“测试连接”，或者后续业务明确调用 `complete()`，才允许联网。

## 3. Background

AM7-R02 已建立一份且仅一份 Active AI Provider Configuration，并冻结 Provider、API Key、Base URL、Model 和连接验证状态的持久化语义。R02 没有网络能力，也没有 UI 入口。

R03 需要在不复制 R02 配置、不侵入 Legacy OCR / Candidate / Action Core 的前提下完成三项工作：

1. 把两个 Provider 映射到真实 API；
2. 把厂商差异压缩成最小的统一调用与错误合同；
3. 给用户一条可完成配置、模型选择、连接检查和保存的 CLI 路径。

Qwen 与 DeepSeek 都提供 OpenAI-compatible Chat Completions，但“OpenAI-compatible”不代表它们的所有 endpoint、错误码、thinking 参数、模型发现和元数据完全相同。R03 因此共享客户端与 Chat Completion 主链路，同时保留必要的 Provider-specific capability 和错误映射。

## 4. Current Repository Findings

本轮只检查了与 R03 直接相关的文件和启动路径，没有进行 repository-wide audit。

| 观察项 | 当前事实 | R03 设计影响 |
| --- | --- | --- |
| 当前分支 / 基线 | `am7-r03-llm-provider-runtime`，HEAD `18502f1`，AM7-R02 已合入 | R03 直接消费当前 R02 public contract |
| Python 布局 | 生产模块位于仓库根目录，不存在 package/service hierarchy | R03 使用少量根模块，不新建多层 framework |
| 交互入口 | `simple_brush.py` 的 `main()` 调用 `choose_startup_action()`；现有菜单是运行、校准、退出 | 在同一顶层菜单增加“AI Provider Configuration”，不改 `run()` 业务流程 |
| 非交互启动 | `--auto`、`--keywords` 或 `--calibration-profile` 会绕过启动菜单 | 非交互路径不进入配置 CLI，不自动联网 |
| 启动脚本 | `start.bat` 切换到项目目录后运行 `simple_brush.py` | R02 的相对路径 `config/ai_provider.json` 在现有启动方式下稳定 |
| Python 版本 | 当前 venv 为 Python 3.11.9；CI 固定 Python 3.11 x64；OCR 依赖说明 Python 3.10+ | R03 依赖必须兼容 Python 3.10+ / 3.11 |
| 声明依赖 | `requirements.txt`、`requirements-ocr.txt`、`requirements-build.txt` 未声明 `openai` 或 `httpx` | R03 需要正式加入 OpenAI Python SDK；不需要同时加入 DashScope SDK |
| 本地环境 | 当前 venv 未安装 `openai` / `httpx`；存在 `requests`，但不是当前正式 Provider runtime 底座 | 不依赖偶然存在的 transitive package |
| 打包入口 | PyInstaller 从 `simple_brush.py` 分析 imports；spec 仅对现有动态/数据依赖做显式收集 | Runtime 经 CLI import 后进入依赖图；是否需要额外 hook 由后续 TID 做 targeted packaging 验证决定 |
| 测试风格 | 当前使用标准库 `unittest` 和 targeted test modules | 后续 TID 应保持小型、可注入的 Runtime / CLI 测试，不建立网络 harness framework |

适合的挂载点是现有顶层启动菜单，而不是 `run()`、OCR 扫描循环、Candidate 处理或页面 Action 路径。菜单集成只负责 dispatch 到独立配置流程；AI 配置逻辑不应继续堆入 `simple_brush.py`。

## 5. R02 Dependency / Existing Contract

### 5.1 Frozen public data contract

R03 必须直接消费 `ai_provider_config.py` 当前提供的合同：

- `AIProviderConfig`
- `AIProviderConfigStore`
- `AIProviderConfigLoadResult`
- `AIProviderConfigLoadStatus`
- `ConnectionVerificationStatus`
- `PROVIDER_ALIYUN_BAILIAN = "aliyun-bailian"`
- `PROVIDER_DEEPSEEK = "deepseek"`
- `DEFAULT_AI_PROVIDER_CONFIG_PATH = config/ai_provider.json`

R03 不建立 Qwen / DeepSeek 私有配置文件，也不修改 R02 v1 的七字段 Schema。

### 5.2 Operation readiness

不同 Runtime 操作需要不同的最小字段：

| Operation | 必需配置字段 | Model 是否必需 |
| --- | --- | --- |
| `list_models()` | `provider`、`api_key`、`base_url` | 否 |
| `test_connection()` | `provider`、`api_key`、`base_url` | 否 |
| `complete()` | `provider`、`api_key`、`base_url`、`model` | 是 |

因此，R02 返回 `INCOMPLETE` 不必然禁止所有 Runtime 操作。缺少 Model 的可解释配置仍可以获取模型或测试 Provider connectivity；缺少 Provider、API Key 或 Base URL 时则不得发起这两类请求。

`INVALID`、`UNSUPPORTED_VERSION` 和 `NOT_CONFIGURED` 没有可消费 config，必须先由 CLI 引导用户建立一份受支持配置。

### 5.3 Frozen verification semantics

R03 必须复用：

```text
AIProviderConfigStore.record_connection_verification(
    checked_provider,
    checked_api_key,
    checked_base_url,
    status,
    completed_at,
)
```

规则保持不变：

- 只有真正执行了有效的非推理 connectivity / authentication check，且 Provider 明确成功响应时，`test_connection()` 才写 `verified`；
- 只有当前 Provider 存在可用的非推理 connection-check capability、实际检查已经执行，并因 authentication、network、timeout、rate limit、provider server error 或其它明确 HTTP / API failure 失败时，才写 `failed`；
- 当前 Provider / region / Workspace / plan 没有可用的非推理 connection-check capability 时，Runtime 返回 `capability_unavailable`，不写 `verified` 或 `failed`；检查前为 `unverified` 时保持 `unverified`；
- 未执行真实检查时不写结果，也不使用 inference fallback；
- 检查期间 Provider / API Key / Base URL 已变化时，Store 返回 stale `False`，旧结果不得覆盖当前状态；
- Model 不参与 stale comparison；
- 不新增 revision、generation、fingerprint、TTL 或第二套 verification state。

`verified` 只表示当前 Provider / API Key / Base URL 的非推理连接检查成功，不表示 Model 可推理、输出质量合格或 Candidate 判断正确。`failed` 只表示存在可用 capability 且实际执行的本次检查未能建立 connectivity，不必然等同于“API Key 肯定错误”。

## 6. Product Goals

1. 同时支持 `aliyun-bailian` 和 `deepseek` 的真实 OpenAI-compatible API 调用。
2. 提供稳定的 Provider-neutral `list_models()`、`test_connection()` 和非流式 `complete()`。
3. 使用 R02 保存的 API Key、Base URL 和 Model，不建立旁路配置。
4. 在共享 OpenAI-compatible 主链路上保留两家真实能力差异。
5. 返回最小、诚实的 completion metadata，不伪造 usage 或 request information。
6. 将网络、认证、限流、请求、模型和响应错误归一为小型可诊断合同。
7. 明确配置 finite timeout，并关闭 SDK 自动重试，使一次公开调用只代表一次应用级尝试。
8. 完成 AI Provider Configuration CLI：查看、编辑、发现或手填 Model、测试连接、保存和查看 verification。
9. 保证普通启动不自动联网、不自动检查、不自动调用模型、不产生 AI 推理费用。
10. 保持 Legacy OCR、Candidate、Screening、Decision 与页面 Action 完全解耦。

## 7. Non-Goals

R03 不负责：

- Provider plugin framework、marketplace、动态插件或复杂 Registry；
- 多 Provider 自动路由、自动切换、failover 或 load balancing；
- 自动 retry、exponential backoff、retry queue 或 circuit breaker；
- streaming、SSE、chunk aggregation、partial JSON 或中断恢复；
- 独立的 `test_inference()` 或 CLI “Test Inference”；
- thinking / reasoning 统一抽象或 R02 thinking 配置字段；
- `extra_body`、`enable_thinking`、`reasoning_effort`、`thinking.type` 的上层公开入口；
- 模型目录缓存、模型价格数据库、人民币价格、成本判断或 Benchmark；
- 模型质量、FP / FN、JSON 稳定性或 Candidate 效果排名；
- Prompt、ScreeningProfile、Criterion、Boolean Contract、Rule Engine 或 Candidate Decision；
- OCR、Candidate scanning、Legacy Rule Engine、favorite、forward、页面动作或 WindMouse；
- Credential Vault、加密 Key、secret scanner、Privacy Gate 或 compliance framework；
- repository-wide audit、机会主义重构或 Warning-to-Failure policy。

## 8. Provider Scope

### 8.1 Canonical provider ids

Runtime selection 只识别 R02 已冻结的两个 canonical id：

| Provider id | 用户显示名 | R03 v1 状态 |
| --- | --- | --- |
| `aliyun-bailian` | Alibaba Bailian / Qwen | Supported |
| `deepseek` | DeepSeek | Supported |

R02 Store 仍允许其它符合语法的 provider string；如果 R03 收到没有实现的 id，Runtime 抛出 normalized `unsupported_provider`，不猜测、不自动路由。

### 8.2 Base URL ownership

`config.base_url` 始终是最终请求使用的 authoritative value。Provider adapter 可以给 CLI 提供推荐值或示例，但不得在运行时覆盖已持久化值。

- DeepSeek 当前有单一推荐 OpenAI base URL：`https://api.deepseek.com`。
- Alibaba Model Studio 的 URL 与区域、Workspace 和计费方案相关，当前不能安全地冻结一个全球通用默认值。CLI 应提示用户使用控制台给出的 API Host，并展示少量官方区域示例；不得静默用北京、国际站或某个套餐 URL 覆盖用户值。

Model 始终来自 `config.model`。Runtime 不写死 Benchmark 候选模型，也不维护一份长期硬编码“完整模型列表”。

## 9. Official Provider Capability Findings

以下结论基于 2026-08-15 可访问的厂商官方资料和一次不带凭据、无推理的 endpoint probe。Provider 文档和线上能力可能变化，后续 TID 开始实施时只需对这些直接依赖点做一次 targeted recheck。

### 9.1 Alibaba Bailian / Qwen

官方资料：

- [OpenAI-compatible Chat API](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions)
- [Model Studio model overview](https://www.alibabacloud.com/help/en/model-studio/models)
- [Obtain and scope an API key](https://www.alibabacloud.com/help/en/model-studio/get-api-key)
- [Install the OpenAI or DashScope SDK](https://www.alibabacloud.com/help/en/model-studio/install-sdk)
- [Model Studio error codes](https://www.alibabacloud.com/help/en/model-studio/error-code)

确认结论：

| 能力 | 结论 |
| --- | --- |
| OpenAI-compatible Base URL | 支持；URL 随 region / Workspace / plan 变化。当前 workspace-specific domain 是主要推荐形式，路径通常以 `/compatible-mode/v1` 结尾 |
| Authentication | `Authorization: Bearer <Model Studio API Key>`；Key 与 region / Workspace / plan 必须匹配 |
| Chat Completion | 支持 `POST <base_url>/chat/completions`，官方 Python 示例使用 `OpenAI(...).chat.completions.create(...)` |
| Non-streaming | 支持；不传 `stream` 或显式 `stream=False` 返回完整 Chat Completion object |
| Completion metadata | 正式 response 提供 `choices[0].message.content`、`choices[0].finish_reason`、`model`、顶层 `id` 和 `usage.prompt_tokens/completion_tokens/total_tokens`；细分 usage 随模型变化 |
| Errors | 官方错误目录覆盖 400 请求问题、401 Key / Workspace / endpoint 问题、429 throttling 及服务端错误；具体 body code 因产品方案和 endpoint 而异 |
| Official model discovery contract | 官方模型列表主要通过文档 / Model Studio console 提供；当前 Chat / SDK 文档没有把 `GET /models` 或 `client.models.list()` 列为稳定公开合同 |
| Actual `/models` route | 2026-08-15 对北京和国际 legacy compatible base URL 的无凭据请求均返回 HTTP 401 和 request-id header，而不是 404/405，证明当前网关存在鉴权路由；该探测不证明每个 region / Workspace / plan 都保证同一能力 |
| Non-inference connection check | 当前 OpenAI-compatible `/models` route 是优先实现候选，但官方未提供稳定、统一的文档保证；RPD 只冻结“尝试当前可用的非推理 connection-check capability”，且不得 fallback 到 Chat Completion |

产品决定：Qwen adapter 的 `list_models()` 尝试当前 Provider / region / Workspace / plan 可用的非推理 model discovery capability。OpenAI-compatible `/models` 或 SDK `client.models.list()` 是 current best-effort implementation direction，不是 RPD 冻结的永久 endpoint 合同；TID 实施前必须对 Alibaba 官方能力做一次 targeted recheck。成功时返回真实 API identifiers；没有可用 discovery capability 时返回 `capability_unavailable`，其它失败返回准确的 normalized Runtime error。CLI 始终保留手工填写 Model 的完整路径，不使用硬编码列表，也不通过 inference 模拟 discovery。

Qwen 的 `test_connection()` 同样只尝试 TID targeted recheck 后确认当前可用的非推理 connection-check capability；当前优先候选是 OpenAI-compatible `/models`。只有有效检查被真正执行且 Provider 明确成功响应时才写 `verified`。如果 capability 存在且实际检查因 401/403、timeout、network、rate limit、5xx 或其它明确 HTTP / API failure 失败，才写 `failed`。如果 endpoint 不支持、404/405 明确表示 capability 不存在，或当前没有可用的非推理验证机制，则返回 `capability_unavailable`，不写 `failed` 或 `verified`；检查前为 `unverified` 时保持 `unverified`。绝不调用 `complete()` 兜底。

### 9.2 DeepSeek

官方资料：

- [Your First API Call](https://api-docs.deepseek.com/)
- [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
- [Lists Models](https://api-docs.deepseek.com/api/list-models/)
- [Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/)
- [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/)
- [Get User Balance](https://api-docs.deepseek.com/api/get-user-balance)

确认结论：

| 能力 | 结论 |
| --- | --- |
| OpenAI-compatible Base URL | 官方 OpenAI base URL 为 `https://api.deepseek.com` |
| Authentication | Bearer API Key；官方 curl 使用 `Authorization: Bearer` |
| Chat Completion | 支持 `POST /chat/completions` 和 OpenAI Python SDK |
| Non-streaming | 支持 `stream=false`，返回完整 Chat Completion object；官方还记录 non-stream 请求可能收到 HTTP keep-alive 空行 |
| Model discovery | 官方明确提供 `GET /models`，返回当前可用 model objects 及 `id`；因此 `client.models.list()` 是正式适配路径 |
| Non-inference connection check | `GET /models` 已足以验证 endpoint、认证和基础访问，不需要也不应调用 inference。官方另有 `GET /user/balance`，但 R03 不需要读取余额 |
| Completion metadata | 正式 response 提供 content、finish reason、model、顶层 id，以及 prompt / completion / total token usage；部分模型还提供 cache / reasoning token detail，R03 v1 不向上层扩展这些细项 |
| Errors | 官方列出 400 invalid format、401 authentication、402 insufficient balance、422 invalid parameters、429 rate limit、500 server error、503 overload |

产品决定：DeepSeek 的 `list_models()` 和 `test_connection()` 都使用官方 `GET /models`，由共享 OpenAI-compatible client 发起。`test_connection()` 不使用 `/user/balance`，因为余额不是 connectivity 的必要条件，也不属于 R03 产品输出。

### 9.3 Capability difference summary

| Topic | Alibaba Bailian / Qwen | DeepSeek |
| --- | --- | --- |
| Chat Completion | 官方支持 | 官方支持 |
| Non-streaming complete | 官方支持，部分具体模型仍受自身能力限制 | 官方支持 |
| `GET /models` 文档状态 | 当前网关 route 可观察，但未形成明确官方稳定合同 | 官方明确文档化 |
| `client.models.list()` | current best-effort implementation candidate；TID 前 targeted recheck | 正式 adaptation |
| `test_connection()` | 尝试当前可用的非推理检查能力；能力不存在时 `capability_unavailable` 且不写 verification | 官方 `/models` |
| Manual Model fallback | 必须 | 必须 |

## 10. Runtime Architecture

### 10.1 Minimal structure

R03 采用三层职责，但不建立 framework：

```text
AI Provider Configuration CLI
    -> R02 AIProviderConfigStore
    -> Provider Runtime facade
         -> shared OpenAI-compatible helper
         -> tiny Qwen capability adapter
         -> tiny DeepSeek capability adapter
```

职责如下：

1. **CLI orchestration**：本地显示与编辑配置，明确触发模型发现 / 连接检查，保存并刷新状态。
2. **Runtime facade**：检查 operation readiness，按 canonical id 做简单映射，暴露三个统一 operation，返回 normalized result / error。
3. **OpenAI-compatible helper + provider adaptations**：构造客户端、关闭 retry、设置 timeout、发送非推理 discovery / connection-check 与 chat 请求、提取 response、归一化 SDK / HTTP error；Provider-specific 部分只定义 base URL 建议、非推理 capability 状态和少量 error/request-id 提取差异。

Provider selection 使用两个显式分支或等价的小型静态 mapping。R03 不需要动态 import、entry point、plugin loader、registration lifecycle 或多层 Registry。

### 10.2 Shared OpenAI-compatible helper

推荐使用 OpenAI Python SDK 作为共同 HTTP / serialization 底座。Alibaba 官方明确支持该 SDK，DeepSeek 官方示例也使用该 SDK；当前 Ocria Python 3.10+ / 3.11 约束与其兼容。[OpenAI 官方 SDK 页面](https://developers.openai.com/api/docs/libraries)也提供 Python SDK 安装与直接 API 调用入口。

共享 helper 必须：

- 从 `config.api_key` 和 `config.base_url` 构造 client；
- 配置明确、有限的 timeout；
- 显式设置 `max_retries=0`，覆盖 SDK 的自动 retry 行为；
- `complete()` 显式发送 `stream=False`；
- 不发送 provider-specific thinking / reasoning 参数；
- 不把 API Key、完整 request body 或 Candidate data写入普通日志；
- 将 SDK / HTTP exception 转换为 R03 error contract；
- 不做 retry、fallback、provider switch 或 hidden second attempt。

RPD 不冻结 SDK patch version 和具体 timeout 秒数；这些属于 TID 的依赖与实施常量。但 TID 必须保证 timeout 有限、retry 为零，并让 targeted tests 能验证一次 operation 只进行一次 outbound attempt。

## 11. Provider Contract

以下是产品级 public contract；TID 可以选择 module-level functions、facade class 或小型 Protocol，只要可观察语义一致。

### 11.1 `list_models(config)`

```text
input:  AIProviderConfig with provider + api_key + base_url
output: ordered collection of unique, non-empty model identifier strings
error:  LLMRuntimeError
side effect: network request only; no configuration or verification mutation
```

### 11.2 `test_connection(config, store)`

```text
input:  AIProviderConfig snapshot + its AIProviderConfigStore
action: one non-inference provider check
output on remote success:
        provider, completion time, whether R02 write-back was applied
error on remote failure:
        LLMRuntimeError after attempting R02 failed write-back
error when no non-inference check capability exists:
        capability_unavailable without verification write-back
side effect:
        record_connection_verification(verified|failed) only after an effective check
```

如果 remote check 成功但 R02 write-back 因 stale tuple 返回 `False`，结果必须明确说明“检查成功，但配置已变化，结果未应用”；当前配置状态保持不变。

### 11.3 `complete(config, request)`

```text
input:  complete AIProviderConfig + minimal completion request
output: LLMCompletionResult
error:  LLMRuntimeError
side effect: exactly one non-streaming inference request; no config mutation
```

`complete()` 是唯一正式推理入口。R03 不提供 `test_inference()`。

## 12. `list_models()` Design

Provider-neutral 语义：

> 尝试通过当前 Provider 可用的非推理 model discovery capability 返回真实 Model identifiers，而不是返回 R03 自带的推荐清单。

DeepSeek 的实现机制冻结为官方 `GET /models`。Alibaba Bailian / Qwen 只冻结上述产品语义：当前实现候选可以优先尝试 OpenAI-compatible `/models` 或 SDK `client.models.list()`，但 TID 实施前必须 targeted recheck Alibaba 官方能力，不得把该 endpoint 固化为永久产品合同。如果当前 Provider / region / Workspace / plan 没有可用的非推理 discovery capability，则返回 `capability_unavailable`。

归一化规则：

- 使用 provider response 的真实 `id`；
- 去除空 id 和重复 id，保留 provider 返回顺序；
- 不重命名、不创建 display alias、不附加价格或 capability；
- provider 合法返回空 `data` 时返回空 collection；
- response 结构无法解释时为 `malformed_response`；
- API 失败时抛出 normalized error；
- 不写回 verification 状态，因为模型发现和显式连接检查是两个不同的用户动作；
- 不缓存长期模型目录，不用 hardcoded list 代替 discovery。
- 不通过 inference 模拟 `list_models()`。

CLI 中，空 collection、capability unavailable 或任意失败都必须继续提供“手工填写 Model identifier”。失败不得清空用户已保存或当前 staged Model。

## 13. `test_connection()` Design

### 13.1 Exact product semantics

`test_connection()` 只检查本次使用的：

- Provider id 有对应 Runtime；
- Base URL 可以到达所选 Provider 的非推理 endpoint；
- API Key 对该 endpoint 的认证 / 基础访问成功。

它不检查：

- 当前 Model 是否存在或有推理权限；
- 当前账户余额是否足够完成一次 inference；
- Chat Completion 是否能成功；
- thinking 模式、Prompt、JSON 或 Candidate 输出；
- latency、质量或成本。

### 13.2 Provider mechanisms

- DeepSeek：正式 `GET <base_url>/models`。
- Alibaba Bailian / Qwen：尝试 TID targeted recheck 后确认当前可用的非推理 connection-check capability；OpenAI-compatible `/models` 是 current best-effort implementation candidate，而不是永久产品合同。如果当前 region / Workspace / plan 没有可用能力，明确返回 `capability_unavailable`。

严格禁止以下 fallback：

- `complete()`；
- `chat.completions.create()`；
- 极短 Prompt；
- 零 token / one token inference；
- 任何可能产生模型推理费用的请求。

### 13.3 Verification write-back

调用开始前保存 checked tuple：`provider/api_key/base_url`。远程 operation 结束时记录 timezone-aware completion time：

- remote success -> `VERIFIED`；
- capability 存在、实际检查已执行，但因 authentication、network、timeout、rate limit、provider server error 或其它明确 HTTP / API failure 失败 -> `FAILED`；
- capability 不存在或当前没有可用的非推理检查机制 -> 返回 `capability_unavailable`，不调用 `record_connection_verification()`，不写 `FAILED` 或 `VERIFIED`；检查前为 `UNVERIFIED` 时保持 `UNVERIFIED`；
- local readiness failure、unsupported config load 或用户没有真正发起检查 -> 不写；
- Store stale comparison 返回 `False` -> 不覆盖新配置。

Provider error detail 不进入 R02 JSON。CLI 可以展示 normalized safe error；R02 仍只保存三态和时间。

## 14. `complete()` Design

### 14.1 Minimal input contract

R03 v1 completion request 只包含一个按顺序排列、非空的 text message collection：

```text
messages = [
    {role: "system" | "user" | "assistant", content: non-empty string},
    ...
]
```

约束：

- 至少一条 message；
- 只支持 text content；
- 不包含 Provider、API Key、Base URL 或 Model override；
- 不暴露 stream、tools、temperature、top_p、response_format、thinking 或 `extra_body`；
- `config.model` 是唯一模型来源；
- runtime 采用自身有限 timeout policy，R02 不新增 timeout 字段。

后续 Screening Requirement 可以在不改变 Provider 配置合同的情况下构造 messages；后续若确有 token limit、structured output 或 reasoning control 需求，应由新的 Requirement 扩展。

### 14.2 Request behavior

Runtime 调用：

```text
client.chat.completions.create(
    model=config.model,
    messages=request.messages,
    stream=False,
)
```

概念代码只表达冻结行为，不规定 TID 的具体 Python syntax。

一次 `complete()`：

- 成功：等待完整 response，提取 result；
- timeout / network / provider error：立即返回或抛出 normalized error；
- 不自动 retry；
- 不切换 Provider 或 Model；
- 不修改 R02 verification；
- 不对 content 做招聘业务判断。

### 14.3 Thinking / reasoning

R03 不发送 `extra_body`、`enable_thinking`、`reasoning_effort` 或 `thinking.type`，使用所选 Model / Provider 的当前默认行为。

这意味着某些具体模型如果无法同时满足自身默认 thinking 行为与非流式调用，Provider 可能拒绝请求。R03 应把它作为 normalized runtime error 返回，不应偷偷关闭 thinking、改成 streaming 或维护模型 capability 表。该限制与 R03 已冻结边界一致。

## 15. Completion Result Contract

```text
LLMCompletionResult
    content: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    finish_reason: str | None
    request_id: str | None
```

字段语义：

| 字段 | 来源与规则 |
| --- | --- |
| `content` | 第一项正式 choice 的 `message.content`；缺失、非字符串或没有正式 choice 时为 `malformed_response` |
| `provider` | 本次选中的 canonical provider id |
| `model` | 优先使用 provider response 的非空 `model`；若未提供，使用实际请求的 `config.model` |
| `input_tokens` | `usage.prompt_tokens`，不存在或不可解释时为 `None` |
| `output_tokens` | `usage.completion_tokens`，不存在或不可解释时为 `None` |
| `total_tokens` | `usage.total_tokens`，不存在或不可解释时为 `None`；不从其它字段制造一个 provider 未返回的值 |
| `finish_reason` | 第一项正式 choice 的 finish reason；未提供时为 `None` |
| `request_id` | 优先使用 completion 顶层 `id`；可用时允许 provider-specific header fallback；均不可用时为 `None` |

R03 不把 reasoning content、cache token detail、system fingerprint、价格或人民币成本加入 v1 public result。Provider 提供但合同未消费的 metadata 不需要伪造统一字段。

## 16. Error Contract

### 16.1 Shape

R03 使用一个小型 error-code enum 和一个 normalized exception，不建立 Result/Exception 双体系或巨大 hierarchy：

```text
LLMRuntimeError
    code: LLMRuntimeErrorCode
    provider: str | None
    operation: list_models | test_connection | complete
    message: safe diagnostic string
    status_code: int | None
    request_id: str | None
```

所有 public operation 成功时返回正常 result，失败时抛出 `LLMRuntimeError`。底层异常可通过 exception chaining 保留给调试，但普通 CLI 不打印 traceback、request headers、API Key 或完整 request body。

### 16.2 Error codes

| Code | 典型来源 |
| --- | --- |
| `authentication` | HTTP 401/403 或 provider 明确的 invalid key / workspace permission |
| `timeout` | SDK timeout 或 HTTP 408 |
| `network` | DNS、TLS、connection reset、无法建立连接 |
| `rate_limit` | HTTP 429 |
| `quota_or_billing` | DeepSeek 402、Qwen arrearage / allocation quota 等明确结构化错误 |
| `invalid_request` | 400/422，且没有更准确分类 |
| `model_unavailable` | `complete()` 中 provider 结构化报告模型不存在、未开通或不可用 |
| `capability_unavailable` | `list_models()` / `test_connection()` 没有当前可用的非推理 capability，例如 endpoint 不支持、404/405 明确表示能力不存在，或官方当前没有可用机制 |
| `provider_server_error` | HTTP 5xx，包括 overload |
| `malformed_response` | 2xx 但 response 缺少 operation 所需结构或正式 content |
| `unsupported_provider` | R02 provider id 没有 R03 adapter |
| `unknown` | 不能可靠归入上述类别的其余失败 |

映射优先使用 SDK exception type、HTTP status 和 provider 的结构化 error code；不依赖自由文本关键词猜测。无法可靠识别 model-specific failure 时使用 `invalid_request` 或 `unknown`，同时保留安全 message、status code 和 request id。

Provider Runtime error 只是技术调用结果。它不得自动变成 Candidate `qualified` / `rejected`，也不得触发页面 Action。

## 17. CLI AI Provider Configuration UX

### 17.1 Startup menu integration

交互启动菜单增加一个独立选项，例如：

```text
1. 开始运行 Ocria Am7
2. 创建或更新校准模板
3. AI Provider Configuration
0. 退出
```

现有 `run()` 和 calibration dispatch 保持原语义。非交互 CLI 参数路径保持绕过菜单，不自动进入 AI 配置。

### 17.2 Configuration screen

进入配置入口时只做 R02 local load，并显示：

```text
Provider: <id or not configured>
API Key: configured | not configured
Base URL: <value or not configured>
Model: <identifier or not configured>
Connection verification: unverified | verified | failed
Last verification time: <time or unavailable>
Configuration state: not configured | incomplete | invalid | unsupported | valid
```

完整 API Key、Key prefix / suffix、长度和 masked fragment 都不得显示。

### 17.3 Actions and normal flow

配置入口至少提供：

1. 选择 Provider：只列 `aliyun-bailian` 和 `deepseek`；
2. 输入 / 修改 API Key：使用不回显输入；空输入默认保留当前值，不能意外清空；
3. 输入 / 修改 Base URL：显示 provider recommendation，但保留用户当前值优先；
4. 获取可用 Model：明确提示将联网，调用 `list_models()`；
5. 从最近获取的列表选择 Model；
6. 手工填写 Model identifier：始终可用；
7. 保存配置；
8. 测试连接：明确提示将联网但不会执行 inference；
9. 重新查看当前状态；
10. 返回启动菜单。

编辑可以在内存中 staged，但任何 `test_connection()` 前必须先把本次要检查的 Provider / API Key / Base URL 明确保存为当前 R02 配置。这样检查才能使用 R02 的 stale-safe write-back。若用户不愿保存 pending connection fields，则不执行测试。

R02 允许保存 incomplete 配置，因此用户可以先保存 Provider / API Key / Base URL、完成连接检查，再设置 Model。`complete()` 仍然必须等待四字段完整。

### 17.4 Model discovery failure UX

如果模型列表为空或失败：

- 显示 normalized safe reason；
- 明确说明“模型列表不可用不代表配置不能继续”；
- 不清空当前 Model；
- 立即提供手工填写 identifier；
- 允许保存；
- 不把文档中的模型清单复制为硬编码 fallback；
- 不自动调用 inference 验证手填模型。

### 17.5 Test connection UX

测试完成后 reload R02 配置并显示最新状态：

- success + applied -> `verified` 和时间；
- failure + applied -> `failed`、时间和 safe Runtime error；
- stale result -> 明确说明配置已变化，结果未应用；
- local persistence error -> 与 Provider connectivity failure 分开报告；
- capability unavailable -> 明确说明当前 Provider endpoint 没有可用的非推理检查，且系统没有执行 inference fallback。

`capability_unavailable` 不代表配置已验证失败：CLI 不显示新的 verification 状态，不触发 `failed` 写回；检查前为 `unverified` 时继续显示 `unverified`。

CLI 中没有“Test Inference”。

## 18. Configuration / Verification Interaction

| 用户动作 | R02 状态行为 | 网络行为 |
| --- | --- | --- |
| 查看配置 | 不修改 | 无 |
| 修改 Provider / API Key / Base URL 并保存 | R02 自动设 `unverified`、清空时间 | 无 |
| 只修改 Model 并保存 | 保留 connectivity 状态和时间 | 无 |
| 获取模型成功 / 失败 | 不修改 verification | 一次 non-inference discovery request |
| 测试连接成功 | 用 R02 接口写 `verified` + time，subject to stale check | 一次 non-inference request |
| 测试连接失败（capability 存在且实际检查失败） | 用 R02 接口写 `failed` + time，subject to stale check | 一次 non-inference request |
| 测试连接 capability unavailable | 不写 verification；检查前为 `unverified` 时保持 `unverified` | 零次或一次非推理 capability probe；不 inference |
| `complete()` 成功 / 失败 | 不修改 connectivity verification | 一次 inference request |
| 普通启动 / `run()` | 最多本地读取与完整性判断；不强制读取 | 无 Provider network |

R03 不增加“model verified”“inference verified”“expired”或其它状态。

## 19. Qwen-specific Notes

1. Base URL 与 region、Workspace、站点和 plan 强相关；API Key 必须匹配。
2. CLI 不假定一个全球默认 endpoint。当前配置始终优先。
3. RPD 冻结的是“尝试当前可用的非推理 model discovery / connection-check capability”，不是永久冻结 `/models`；OpenAI-compatible `/models` / `client.models.list()` 只是当前优先实现候选，TID 前必须 targeted recheck。
4. Qwen adapter 不维护硬编码 model catalog；官方文档 / console 只作为用户参考。
5. non-streaming Chat Completion 返回 OpenAI-shaped content、finish reason、id 和 usage，可进入统一 result。
6. 具体 Qwen 模型对 thinking 与 non-streaming 的组合限制可能不同；R03 不覆盖默认 thinking 行为。
7. Qwen-specific error code / request header extraction可以存在于小型 adapter 内，不应污染 public result。

## 20. DeepSeek-specific Notes

1. 推荐 base URL 是 `https://api.deepseek.com`；Runtime 仍使用用户持久化值。
2. `/models` 是官方 endpoint，可同时服务 model discovery 和非推理 connection check。
3. `/user/balance` 虽可非推理访问，但 R03 不读取余额、不向 completion result 加余额信息。
4. DeepSeek 官方明确列出 402 insufficient balance，应归一为 `quota_or_billing`，而不是 authentication 或 Candidate failure。
5. 非流式连接可能持续收到 keep-alive 空行；使用 SDK 处理 response framing，Runtime 仍需要 finite timeout。
6. DeepSeek 当前 thinking defaults 属于 Provider / Model 行为；R03 不发送控制参数。

## 21. Security / API Key Handling

- API Key 只从 R02 config 在内存中交给 SDK；
- 普通 UI 只显示 `configured / not configured`；
- 输入 Key 时不回显；
- Runtime result、Runtime error、日志、Candidate data、OCR Store 和 Run Manifest 不包含 Key；
- 不打印 client、config、Authorization header、完整 exception request 或完整 request body；
- provider error message 只保留安全、必要诊断；
- R03 继续接受 R02 已批准的本地明文保存权衡，不引入 credential vault；
- 不建立 repository-wide scanner、keyword gate 或额外 privacy framework。

## 22. Failure Semantics

1. Local config missing / incomplete / invalid 与 Provider network error 是不同事实。
2. `list_models()` 失败不阻止手工 Model 配置，也不修改 verification。
3. `test_connection()` 只有在非推理检查能力存在、实际检查已执行且明确失败时写 `failed`；能力不存在时返回 `capability_unavailable`，不写 verification，也不自动调用 inference。
4. `complete()` 失败返回 normalized Runtime error，不产生 Candidate 业务结论。
5. timeout、network、rate limit 和 5xx 不自动重试。
6. provider 返回 usage 缺失时保持 `None`，不伪造数值。
7. response 没有正式 content 时为 `malformed_response`，不把空响应当成功。
8. unsupported provider 不 fallback 到另一个 Provider。
9. 配置写回失败与远程检查结果分开报告；不得把本地 I/O failure 伪装为 Provider `failed`。
10. Warning 或 optional metadata 缺失不自动升级为 unrelated application failure。

## 23. Compatibility / Legacy Core Boundary

### 23.1 Expected R03 module responsibilities

后续 TID 应保持最小模块职责，建议：

- 一个独立 Runtime 根模块：contracts、simple provider mapping、OpenAI-compatible calls、normalization；
- 一个独立 AI Provider Configuration CLI 根模块：R02 load/edit/save、模型选择、连接检查交互；
- 对 `simple_brush.py` 只做顶层菜单 import / dispatch 的精确修改；
- 对 `requirements.txt` 增加正式 SDK dependency；
- 只有 targeted packaging evidence 证明需要时才修改 PyInstaller spec。

是否把两个 tiny adapter 放在 Runtime 同一文件或拆成两个根模块属于 TID 选择；不得因此创建 `providers/services/registries/plugins` 多层目录。

### 23.2 Files / areas expected to remain unchanged

下列 Legacy Core 职责应保持完全不变：

- OCR detection、normalization、aggregation、similarity；
- Candidate capture / record / store；
- calibration profiles / steps / template semantics；
- mouse motion / WindMouse；
- screening rules 和现有 keyword behavior；
- favorite / forward / next candidate / refresh / browser actions；
- BOSS page scanning and run loop；
- existing Candidate / OCR data schemas。

`simple_brush.py` 的允许变更仅是启动菜单和配置流程 dispatch；不得借 R03 修改 `run()` 内部行为。

### 23.3 Packaging compatibility

R03 加入外部 SDK 且接入 PyInstaller 入口，后续 TID 必须设计 targeted dependency、import 和 packaged CLI verification。RPD 不预设一定需要 spec hook，也不授权提前做完整 release。构建问题应先区分 product dependency 与 packaging environment，不应通过修改 Legacy behavior 解决。

## 24. Downstream R04 / Screening Boundary

后续 Model Smoke / Candidate Benchmark 可以：

- 读取一份完整 R02 config；
- 构造 R03 minimal messages；
- 调用同一个 `complete()`；
- 使用 normalized content、usage、finish reason 和 request id 做自身分析。

后续 Screening Runtime 可以在 R03 之外定义 Prompt、Boolean Contract、schema validation、Decision 和 failure policy。

R03 不知道 Candidate、岗位、Criterion、qualified / rejected，也不调用页面 Action。固定边界仍然是：

```text
OCR sees data
Downstream AI understands data
Downstream Rule decides
Existing orchestration performs any action
```

## 25. Open Questions / Decisions

### 25.1 Decisions made in this RPD

- 使用 OpenAI Python SDK 作为共同底座，不同时引入 DashScope SDK。
- 使用两个显式 provider adapters / branches，不建立插件或动态 Registry。
- DeepSeek `/models` 是正式 discovery / connection-check mechanism。
- Qwen 冻结为尝试当前可用的非推理 discovery / connection-check capability；`/models` / `client.models.list()` 仅是 TID targeted recheck 前的 current best-effort implementation direction，不是永久产品合同。
- completion input v1 只包含 text messages；Model 和连接字段全部来自 R02 config。
- normalized error 使用一个 enum + 一个 exception。
- 增加 `capability_unavailable` 与 `quota_or_billing`，避免把真实 Provider 限制误报为 authentication / unknown；`capability_unavailable` 不写 `failed` 或 `verified`，也不新增 R02 verification 状态。
- SDK retry 必须关闭；timeout 必须有限；具体 dependency version 和秒数交给 TID。
- Qwen 没有全球统一 default Base URL；CLI 展示官方示例但不覆盖 persisted value。

### 25.2 Open questions requiring Human decision

None.

当前没有需要 Human 在产品语义上先行裁决的问题。本文 v0.2 已获批准并冻结供 TID 使用；TID 前对 Alibaba 官方 capability 的 targeted recheck 是实施事实核对，不是新的 Human architecture decision。

## 26. Acceptance Intents

后续 AM7-R03 实现完成后必须满足以下产品行为；这些意图不规定测试脚本、命令或 Change 拆分：

- **AC-01 — Two-provider support**：同一 Runtime 正式支持 `aliyun-bailian` 和 `deepseek`，不是 DeepSeek-only。
- **AC-02 — R02 consumption**：所有 Provider 请求使用 R02 的 provider、api_key、base_url 和 model；没有第二份 Provider 配置。
- **AC-03 — Minimal selection**：两个 canonical id 映射到各自 adapter；未知 id 返回 `unsupported_provider`，不 fallback。
- **AC-04 — Shared runtime**：两家复用 OpenAI-compatible client / Chat Completion / result extraction，差异只在必要 adapter boundary。
- **AC-05 — DeepSeek model discovery**：DeepSeek `list_models()` 通过官方 `/models` 返回真实 identifiers。
- **AC-06 — Qwen best-effort discovery**：Qwen `list_models()` 尝试 TID targeted recheck 后确认当前可用的非推理 model discovery capability；能力不存在时返回 `capability_unavailable`，不硬编码模型列表，也不使用 inference 模拟 discovery。
- **AC-07 — Manual model entry**：任何 Provider 的模型列表不可用、为空或失败时，用户仍能手填并保存 Model identifier。
- **AC-08 — Non-inference connection test**：DeepSeek `test_connection()` 使用官方 `/models`；Qwen 尝试当前可用的非推理 connection-check capability，不把具体 endpoint 冻结为永久合同；两家均不会调用 Chat Completion 或其它 inference fallback。
- **AC-09 — Verification write-back**：有效非推理检查成功时使用 R02 原接口写 `verified`；capability 存在且实际检查明确失败时写 `failed`；capability unavailable 时不写 verification，检查前为 `unverified` 时保持 `unverified`。所有实际写回均带 timezone-aware time 并服从 R02 stale protection。
- **AC-10 — Stale protection**：检查期间 connection tuple 变化时，旧结果不覆盖新配置；不新增 revision framework。
- **AC-11 — Non-streaming completion**：`complete()` 只进行 `stream=False` 的单次完整请求，不实现 streaming。
- **AC-12 — Runtime inputs**：Model、Base URL 和 API Key 都取自 config；request 不允许绕过配置覆盖这些字段。
- **AC-13 — Normalized result**：成功返回 content、provider、model 和可获得的 usage / finish reason / request id；unavailable metadata 保持 `None`。
- **AC-14 — Malformed response**：缺少正式 content 或必要 response shape 不被误报为成功。
- **AC-15 — Normalized errors**：认证、timeout、network、rate limit、quota/billing、invalid request、model unavailable、capability unavailable、5xx、malformed response、unsupported provider 和 unknown 可被稳定区分。
- **AC-16 — No automatic retry**：每次 public operation 不做 application retry，SDK retry 明确关闭。
- **AC-17 — Finite timeout**：discovery / connection-check 与 completion requests 均有明确有限 timeout，并归一为 `timeout`。
- **AC-18 — Default thinking behavior**：R03 不发送 thinking / reasoning control 参数，不新增 R02 字段。
- **AC-19 — Full CLI flow**：用户能查看、选择 Provider、修改 Key / Base URL、获取或手填 Model、保存、测试连接并查看状态。
- **AC-20 — API Key display**：CLI 只显示 configured / not configured，输入不回显，errors/logs 不泄露完整 Key。
- **AC-21 — Base URL preservation**：Provider recommendation 不覆盖当前 persisted base_url。
- **AC-22 — Offline daily startup**：普通交互启动、非交互启动和进入 run flow 都不自动 list models、test connection 或 complete。
- **AC-23 — No Test Inference**：CLI 不出现 Test Inference；`complete()` 是唯一推理入口。
- **AC-24 — Legacy isolation**：OCR、Candidate、Screening、Decision 和页面 Action 行为不因 R03 改变。
- **AC-25 — Packaging readiness**：新增 Runtime dependency 在 Python 3.11 Windows source / packaged CLI path 可用，但本 Requirement 不执行 release。

## 27. Out of Scope

本 Requirement 明确排除：

- ScreeningProfile、招聘标准、Criterion；
- CandidateOcrDocument 业务分析、AI Candidate Input Builder；
- Prompt v1、AI Screening Boolean Contract、Screening Rule Engine；
- Candidate Decision、qualified / rejected、favorite、forward；
- 页面动作、OCR、Candidate scanning、Legacy Rule Engine 修改；
- Model Smoke、Candidate Benchmark、FP / FN、模型质量排名；
- Token 成本比较、人民币价格计算、价格数据库；
- 生产级 Test Inference；
- 自动 retry / backoff；
- streaming；
- 多 Provider 自动切换；
- AI 直接控制页面动作。

## 28. TID Handoff Notes

后续 TID 只需要在本 RPD 内决定最小实现细节：

1. 冻结 Runtime / CLI 文件名和 public Python signatures；
2. 选择并固定兼容 Python 3.10+ / 3.11 的 `openai` dependency range；
3. 实施前对 Alibaba 官方非推理 model discovery / connection-check capability 做一次 targeted recheck，再冻结当时可用的 best-effort 实现机制；不得把 `/models` 当作 RPD 已永久保证的 Qwen endpoint；
4. 冻结 discovery / completion 的有限 timeout 常量，并显式设置 `max_retries=0`；
5. 定义 provider error status / structured code 到 R03 enum 的小型映射，并保证 `capability_unavailable` 不触发 verification 写回；
6. 设计可注入 client 或 mock transport 的 targeted tests，避免真实付费 inference 成为自动验收前提；
7. 精确限制 `simple_brush.py` 为菜单 dispatch 修改；
8. 验证 PyInstaller 自动收集是否足够，只有 evidence 表明需要时才改 spec；
9. 把可选、带真实凭据的 Provider smoke 与正式自动测试区分，不把无凭据环境视为 product failure；
10. 不增加 Test Inference、retry、streaming、provider registry、verification framework 或后续 Screening scope。

## 29. Final RPD Conclusion

AM7-R03 应以一个最小 Runtime facade、一个共享 OpenAI-compatible helper、两个 tiny Provider adaptations 和一个独立配置 CLI 完成。DeepSeek 使用正式 `/models`；Qwen 尝试 TID targeted recheck 后确认当前可用的非推理 discovery / connection-check capability，当前 `/models` / `client.models.list()` 只作为 best-effort implementation direction，不构成永久 endpoint 合同。能力不存在时返回 `capability_unavailable`，不写 verification；任何 discovery 失败都保留手填 Model，并禁止 inference fallback。`complete()` 只做单次非流式调用，返回最小 normalized result，失败通过一个小型 normalized exception 合同上报。

本设计没有改变 R02 Schema、verification state 或 stale-result contract，也没有发现与 R02 冻结合同的冲突。

**R03 RPD v0.2：Approved / Frozen for TID。**
