# Ocria Am7 AM7-R02 RPD：AI Provider 配置管理

## 1. Document Status

| 项目 | 内容 |
| --- | --- |
| 产品 | Ocria |
| Generation / Codename | Am7 |
| Requirement | AM7-R02 |
| 文档类型 | RPD（Requirement / Product Design） |
| 文档版本 | 0.2 |
| 编写日期 | 2026-08-15（Asia/Shanghai） |
| 当前阶段 | Approved / Frozen for TID |
| Requirement Branch | `am7-r02-ai-provider-config` |
| 上游基线 | AM7-R01 Accepted baseline / `a75fd28` |
| 设计主题 | AI Provider Configuration Infrastructure |

本文定义 AM7-R02 的产品语义、范围、配置概念、生命周期、持久化行为、连接验证状态及与 AM7-R03 的边界。RPD v0.2 已经 Human Review 批准并冻结，是 AM7-R02 后续 TID 的正式产品输入；本文不是 TID，不授权代码实施、主菜单修改、Provider 网络接入、模型调用或 Legacy Core 修改。

本版本以已冻结的 AM7-R02 产品决策、`CODEX-CONSTITUTION.md`、Accepted AM7-R01 基线及当前 Requirement Branch 的定向仓库观察为依据。当前仓库事实与本设计一致：尚无正式统一的 AI Provider 配置来源；现有 `.gitignore` 已覆盖部分本地运行数据，但尚未定义 AI Provider 配置文件边界；仓库存在本地 JSON 读写和“完整写入后整体替换”的既有先例；当前启动菜单没有 AI Provider 配置入口。

本轮没有发现 AM7-R02 与 Accepted AM7-R01 Freeze Contract 之间的 `CONTRACT CONFLICT`。R02 应作为 Am7 Greenfield 能力建立，不修改 Legacy OCR、Candidate、Screening 或页面动作语义。

## 2. Background

Ocria 后续需要接入 Alibaba Bailian / Qwen、DeepSeek 等 AI Provider。Provider Runtime 要执行连接检查、模型发现或推理时，必须获得一份明确且一致的当前配置，包括 Provider identity、credential、Base URL 和 Model。

如果在没有统一配置层的情况下直接实现 Provider Runtime，每个 Provider 很容易自行决定 API Key 从哪里取得、Base URL 如何保存、Model 如何选择以及验证状态如何记录。这会造成重复输入、临时硬编码、Provider 间不一致、配置变化后沿用旧验证结果，以及 API Key 被复制到不应出现的日志或业务数据中。

因此，R02 必须先于 R03 建立唯一的本地 Configuration Layer。R02 只管理配置事实和状态，不解释厂商 API，不进行网络访问，也不执行任何可能收费的模型调用。R03 以后通过这层配置获得统一输入，并把真实 Provider connection check 的结果写回这层状态。

## 3. Problem Statement

AM7-R02 要解决的真实问题不是“让 Ocria 使用 AI”，而是消除正式 Provider Runtime 之前的配置来源不确定性。

当前缺少一套能够同时满足以下条件的正式机制：

- 用户配置一次后，可在 Ocria 重启后继续使用，不必每次重新输入 API Key；
- Qwen、DeepSeek 及后续 Provider 使用同一配置概念，而不是各自建立独立配置逻辑；
- Provider、API Key、Base URL、Model 和连接验证状态拥有唯一、明确的当前来源；
- 配置缺失、不完整、损坏或版本不受支持时，系统能明确识别其不可用原因，而不是崩溃或猜测；
- 影响 Provider connection 语义的字段变化后，旧 `verified` / `failed` 状态不会继续被当作当前配置的结果；
- 配置保存中断时，不会轻易把上一份完整可读配置覆盖成半份 JSON；
- API Key 可以按已批准决定在本地明文保存，同时不会被普通展示、日志或业务数据主动泄露；
- 单纯读取配置或日常启动 Ocria 不会自动联网、调用模型或产生推理费用。

统一 Configuration Layer 是 R03 的必要前置条件，因为 Runtime 只有在配置的来源、完整性和状态语义稳定后，才能可靠地消费配置，而不把配置管理与厂商网络逻辑混在一起。

## 4. Goals

AM7-R02 完成后，Ocria 应获得以下能力：

1. 维护一份且仅一份当前 Active AI Provider Configuration。
2. 以 Provider-agnostic 的统一概念保存 `config_version`、Provider、API Key、Base URL、Model、连接验证状态和最后验证时间。
3. 将配置可靠地保存在本地，使进程重启后能够读取相同配置和状态。
4. 支持创建、读取和修改当前配置，并能判断配置是未配置、不完整、无效、版本不受支持还是有效。
5. 持久化简单的 Provider connection verification 状态：`unverified`、`verified`、`failed`。
6. 当 Provider、API Key 或 Base URL 的有效值发生变化时，使旧连接验证状态失效；仅修改 Model 时保留 Provider connectivity 状态。
7. 保证配置保存失败不会把上一份完整配置破坏成不可读的部分文件。
8. 允许 API Key 按已批准决定在本地配置文件中明文保存，同时只向普通用户展示是否已配置，不展示其完整值。
9. 为 R03 提供稳定的配置输入和连接验证结果回写边界，但不实现任何 Provider Runtime。
10. 保持日常配置读取完全本地化，不因配置系统本身触发网络请求、模型调用或付费推理。

## 5. Non-Goals

AM7-R02 明确不包含：

- Provider Runtime abstraction 或 Provider adapter；
- Alibaba Bailian / Qwen API 接入；
- DeepSeek API 接入；
- 任何其它厂商 API 接入；
- `list_models()` 的网络实现或模型发现；
- connection check 的网络执行；
- `complete()`、chat completion 或其它 inference；
- 生产用户可见的 Test Inference；
- Model Smoke、Candidate Benchmark、FP / FN、JSON 稳定性、token、latency 或成本比较；
- Provider 网络错误归一化；
- Provider 默认 Base URL 的厂商定义或 endpoint registry；
- 模型价格、context window、capability、family、tier、thinking、multimodal 等模型元数据；
- 多账户、多 Provider Profile、多 API Key Pool、配置历史、一键账号切换或多环境配置；
- Credential Vault、Windows Credential Manager、DPAPI、AES、master password、OS keyring 或其它加密凭据系统；
- Secret Scanner、Privacy Gate、关键词门禁或自定义安全框架；
- 自动配置迁移框架、备份轮转、journal、checksum gate 或事务框架；
- Candidate、CandidateOcrDocument 或 Candidate processing；
- ScreeningProfile、Screening Rule Engine 或 Criterion；
- AI Prompt、AI Boolean Contract、AI Result、Candidate Decision；
- favorite、forward、next candidate 或其它页面 Action；
- OCR、R02—R07 Legacy OCR algorithms、校准、WindMouse 或页面自动化修改；
- Ocria 主启动菜单集成或半成品配置 UI；
- 自动恢复或猜测损坏 JSON 原本应有的内容；
- 复杂 Provider Registry 或预先设计未来 Provider 能力。

## 6. Scope

### 6.1 In Scope

R02 的产品范围由两个概念组成：

- `AIProviderConfig`：当前唯一 Active Provider Configuration 的数据与状态概念；
- `AIProviderConfigStore`：负责本地保存、读取、修改、分类和连接验证状态持久化的配置存储概念。

上述名称用于表达产品边界，不在本 RPD 中规定 Python class、函数签名或具体模块结构。

R02 负责：

- v1 配置 Schema 的最小字段和业务语义；
- 单一 Active Configuration；
- 本地持久化和重启后读取；
- 配置创建和修改；
- 配置完整性与可用性分类；
- connection verification 状态和时间；
- 关键配置变化后的 verification invalidation；
- API Key 的安全展示边界；
- 保存失败不破坏上一份完整配置的可靠性语义；
- 向 R03 提供读取配置和回写连接验证结果的概念边界。

### 6.2 Scope Invariants

- 配置架构不得永久绑定 DeepSeek、Qwen 或任一具体 Provider。
- 第一版只存在一份当前配置，不引入 Profile 或账户选择层。
- 配置文件是独立本地配置，不属于 OCR Store、Run Manifest、Candidate data 或 AI Result。
- 配置读取是本地操作；联网和收费行为只能由后续 Runtime 在明确调用时发起。
- R02 不修改 Legacy Core，也不接入当前主启动菜单。

## 7. Configuration Concept

### 7.1 v1 最小持久化字段

| 字段 | v1 业务语义 | 约束 |
| --- | --- | --- |
| `config_version` | 当前持久化配置 Schema 的版本 | v1 固定为整数 `1`；缺失或类型错误属于 invalid；其它明确版本属于 unsupported version |
| `provider` | 当前 Provider 的稳定内部 identity | 字符串；完整配置中必须非空；R02 不通过复杂 Registry 解释它 |
| `api_key` | 当前 Provider credential | 字符串；完整配置中必须非空；允许在专用本地配置文件中明文保存 |
| `base_url` | 用户当前最终使用的 Provider API Base URL | 字符串；完整配置中必须非空且具有基本可解释的 URL 形式；R02 不提供 Provider 默认值或 endpoint registry |
| `model` | 当前选定模型的真实 API identifier | 字符串；完整配置中必须非空；不保存价格、能力或展示元数据 |
| `connection_verification_status` | 最近一次适用于当前连接语义的 Provider connectivity 状态 | 只允许 `unverified`、`verified`、`failed` |
| `last_verification_time` | 最近一次适用于当前连接语义的真实 connection check 完成时间 | `unverified` 时为无值；`verified` 或 `failed` 时为带明确时区的时间值 |

v1 不增加 `updated_at`、profile name、account id、credential id、verification error、model metadata、pricing 或 capability 等字段。它们不解决已确认的 R02 必要问题。

### 7.2 Provider Identity

Provider 使用稳定的内部 identifier，而不是用户可见品牌文案。v0.2 建议使用 lower-case kebab-case，例如：

- `aliyun-bailian`
- `deepseek`

具体首批 identifier 在 TID 阶段冻结。R02 Store 不为这些 identifier 建立复杂 Provider Registry，也不通过联网判断 Provider 是否真实存在或当前受 Runtime 支持。某个 identifier 是否有对应 Runtime 是 R03 的责任。

### 7.3 Base URL

R02 保存用户最终当前使用的 Base URL。R02 可以判断它是否为空或是否具有基本 URL 结构，但不解释 Provider 专属路径、版本、region、可用性或默认值。

如果 R03 以后为特定 Provider 提供默认 Base URL，R03 负责得到该默认值；一旦它成为用户当前实际配置，R02 只按普通 `base_url` 保存。

### 7.4 Model

`model` 只表示发送给 Provider API 的真实模型 identifier，例如 `qwen3.7-flash`。R02 不验证该模型是否存在、账号是否有权限、是否支持特定能力或能否完成 inference。这些事实必须由 R03 或后续 Model Smoke / Candidate Benchmark 处理。

### 7.5 Derived Configuration Classification

配置的“未配置 / 不完整 / 无效 / 不支持 / 有效”是读取和解释结果，不需要作为额外持久化字段写回文件。

五类结果互斥：

| 分类 | 定义 | 系统可做什么 |
| --- | --- | --- |
| `not configured` | 专用配置文件不存在 | 明确报告尚未配置；允许用户以后创建 |
| `incomplete configuration` | JSON 可读、版本受支持、已提供值本身可解释，但 `provider`、`api_key`、`base_url`、`model` 中至少一项缺失或为空 | 可读取和继续编辑；不得视为完整 inference 配置 |
| `invalid configuration` | 文件存在但不能按 v1 安全解释，例如 JSON 损坏、根结构错误、必要 Schema / verification 元数据缺失或类型/取值错误、已提供的非空值明显不符合基本结构 | 明确报告配置无效；不得猜测、联网或静默修复 |
| `unsupported config version` | JSON 中存在可识别的 `config_version`，但不是当前支持的版本 | 明确报告版本不受支持；不得按 v1 猜读或自动迁移 |
| `valid configuration` | v1 结构和状态一致，四项运行配置值均已提供且可解释 | 可作为 R03 后续操作的完整配置输入 |

`incomplete configuration` 与 `invalid configuration` 必须保持区别。未填写 Model 是不完整；半份 JSON、错误的 verification 枚举或无法识别的 Schema 不是“不完整”，而是无效。

R03 的某些连接操作可能只需要 Provider、API Key 和 Base URL，不需要 Model。R02 因此必须允许 R03 读取明确分类的不完整配置；但是否具备某项 Runtime 操作所需输入由 R03 判断，R02 不新增另一套持久化 readiness 状态，也不得把不完整配置表示为完整 inference 配置。

## 8. Configuration Lifecycle

### 8.1 Normal Lifecycle

1. **不存在**：首次使用时没有配置文件，读取结果为 `not configured`，不报致命错误。
2. **创建**：建立 v1 当前配置；初始连接验证状态为 `unverified`，最后验证时间无值。
3. **保存**：将当前配置作为独立本地配置可靠保存。
4. **读取**：从本地文件恢复字段、verification 状态和时间，并返回明确分类；读取本身不联网。
5. **修改**：用户或未来上层配置流程修改一个或多个字段。
6. **Verification invalidation**：若 Provider、API Key 或 Base URL 的有效值发生变化，则状态变为 `unverified`，最后验证时间清空；Model-only 变化不触发该失效。
7. **再次保存**：更新后的配置和状态按同一可靠性语义持久化。
8. **程序重启**：再次读取时，应得到最后一次成功保存的配置和 verification 状态，不要求重新输入 API Key。
9. **R03 连接检查**：后续 R03 在明确发起真实 check 后，将 `verified` 或 `failed` 及相应时间写回 R02；R02 自身不执行该检查。

### 8.2 Effective Change

Verification invalidation 只由配置的有效值变化触发。重复保存相同 Provider、API Key、Base URL 和 Model 不应改变 verification 状态或时间。

若一次修改同时包含多个字段，只要 Provider、API Key 或 Base URL 中任一有效值发生变化，就执行 invalidation。Model 的同时变化不能抵消该结果。

### 8.3 Incomplete and Invalid Lifecycle

- 不完整配置可以被持久化、读取和继续修改，但不能被误报为完整有效配置。
- 无效配置在读取时保持无效；单纯读取不得覆盖、删除或自动重写它。
- unsupported version 在读取时保持不受支持；R02 v1 不自动迁移。
- 用户以后明确保存一份新的受支持配置时，可以用该新配置替代旧的无效或不受支持配置；恢复必须来自明确的新输入，而不是系统猜测。

## 9. Verification Semantics

### 9.1 State Definitions

| 状态 | 精确定义 |
| --- | --- |
| `unverified` | 当前 Provider、API Key、Base URL 组合从未成功完成适用于当前值的连接检查，或者这些连接语义字段自最近一次检查后发生了变化 |
| `verified` | 后续 R03 最近一次针对当前 Provider、API Key、Base URL 组合执行的 Provider connection check 成功 |
| `failed` | 后续 R03 最近一次针对当前 Provider、API Key、Base URL 组合执行的 Provider connection check 失败 |

这三个状态只描述 Provider connectivity。它们不证明或否定：

- 当前 Model 存在；
- 当前账号对 Model 有 inference 权限；
- Model 能稳定返回约定 JSON；
- Candidate 判断准确；
- inference 延迟或成本可接受。

R02 不定义 `inference_status`、model verification 或其它状态机。

### 9.2 Invalidation Matrix

| 变化 | Verification 结果 | 原因 |
| --- | --- | --- |
| Provider 有效值变化 | 设为 `unverified`，清空最后验证时间 | 已验证的 Provider identity 不再相同 |
| API Key 有效值变化 | 设为 `unverified`，清空最后验证时间 | 认证语义已变化 |
| Base URL 有效值变化 | 设为 `unverified`，清空最后验证时间 | 目标 endpoint 已变化 |
| 仅 Model 有效值变化 | 保留当前状态和最后验证时间 | connectivity 与特定模型 inference 不是同一语义 |
| 重复保存相同有效值 | 保留当前状态和最后验证时间 | 没有发生语义变化 |

将 Model 清空或从空值改为具体 identifier 仍属于 Model-only 变化；它会改变完整性分类，但不会错误地否定已经针对同一 Provider、API Key 和 Base URL 得到的 connectivity 结果。

### 9.3 Verification Time

- `unverified` 不保留一个会让人误认为当前连接已检查的旧时间，因此 `last_verification_time` 为无值。
- `verified` 和 `failed` 都记录最近一次真实 connection check 完成时间。
- Model-only 变化保留该时间，因为对应的连接语义没有变化。
- 时间本身不使状态自动过期；R02 v1 不引入 verification TTL。

### 9.4 Write-back Integrity

R02 不能自行把状态提升为 `verified`。只有 R03 完成真实 connection check 后才能写入 `verified` 或 `failed`。

写回结果必须对应当前 Provider、API Key 和 Base URL 组合。如果 R03 检查期间这些值已经变化，旧检查结果不得覆盖当前配置的 `unverified` 状态。

v1 应优先通过最小充分方式判断 connection check 的输入是否仍对应当前配置，例如比较该次检查实际使用的 Provider、API Key、Base URL 与写回时的当前有效值。除非后续 TID 能证明存在无法通过这种简单语义解决的真实需求，不得为 AM7-R02 增加持久化 config revision、verification fingerprint、generation counter、history 或复杂 concurrency framework。具体关联方式由 TID 在此边界内确定，本 RPD 不规定函数、锁、线程或 async 实现。

## 10. Persistence Semantics

### 10.1 Storage Boundary

R02 使用一份专用的本地 JSON 配置文件保存当前 Active Configuration。该文件必须：

- 与 OCR Store、Run Manifest、Candidate data、AI Result 和日志分离；
- 被 Git ignore 规则覆盖；
- 不作为 fixture、evidence、release asset 或业务记录提交；
- 在 Ocria 重启后继续存在，除非用户或外部环境明确删除它。

具体目录、文件名和 Python API 属于 TID，不在本 RPD 冻结。

### 10.2 Expected Behavior by Scenario

| 场景 | 预期行为 |
| --- | --- |
| 配置文件不存在 | 返回 `not configured`；不创建隐式默认 Provider，不联网，不导致 Ocria 崩溃 |
| 配置完整且有效 | 恢复所有字段、verification 状态和时间，返回 `valid configuration` |
| 配置不完整 | 恢复可解释字段并返回 `incomplete configuration`；不得伪装成完整配置 |
| JSON 格式损坏 | 返回 `invalid configuration`；不猜测、不联网、不自动覆盖 |
| 结构或字段语义无效 | 返回 `invalid configuration`，提供不含完整 API Key 的明确原因 |
| `config_version` 不受支持 | 返回 `unsupported config version`；不按 v1 猜读、不自动迁移 |
| 首次保存成功 | 一份完整可读取的新文件成为当前配置 |
| 更新保存成功 | 新配置作为一个完整整体替代旧配置 |
| 保存中断或失败 | 不把上一份完整配置替换为半份 JSON；正式配置应保持旧完整版本或完整生效的新版本 |
| 无旧配置时保存失败 | 仍表现为未配置，或者不存在可被误认为成功配置的部分正式文件 |
| 程序重启 | 读取最后一次成功保存的配置和状态，不要求重新输入 API Key |
| 单纯加载配置 | 不修改配置、不改变 verification、不联网、不调用模型、不产生推理费用 |

### 10.3 Reliable Save Requirement

保存语义是“先完整形成新内容，再整体替换正式配置”。本 RPD 只要求可观察结果：

> 一次保存失败不得把上一份完整、可读取的正式配置破坏为部分 JSON。

R02 不要求 backup rotation、历史版本、journal、checksum、database transaction 或自动恢复框架。具体临时文件和替换机制由 TID 选择最小充分实现。

## 11. API Key Handling

### 11.1 Approved Local Storage

v1 明确允许 API Key 在专用本地配置文件中明文保存。这是已批准的产品权衡：减少用户每次启动重复输入，并避免在 R02 中引入 Credential Vault 或加密系统。

这意味着能读取该本地文件的用户或进程也能读取 Key。R02 不声称提供静态加密保护。

### 11.2 Required Boundaries

- 专用配置文件必须被 Git ignore。
- 普通配置查看不得显示完整 API Key，也不显示其任意可识别片段；推荐只显示 `API Key: configured` 或 `API Key: not configured`。
- 普通运行日志和错误信息不得主动输出完整 API Key value。
- OCR Store、Run Manifest、Candidate data、AI Result 及其它非配置业务记录不得复制完整 API Key。
- R03 可以在内存中消费原始 Key 以完成认证，但不得把它通过普通显示、日志或业务持久化回传出去。
- 配置读取、验证错误或保存错误的说明不得包含完整 Key。

这些要求针对真实 API Key value，不针对 `key`、`token`、`secret` 等普通技术单词。R02 不设计关键词 scanner、Privacy Gate、Secret Gate 或额外 compliance framework。

上述 API Key 安全要求约束 AM7-R02 新增配置代码及其明确的数据流边界。它不授权为本 Requirement 新增 repository-wide secret scanner、keyword scanner、Privacy Gate、Secret Gate、全仓库日志扫描、release-wide credential audit 或独立 compliance framework。后续验收应通过 targeted verification 证明 R02 不主动向明确输出路径传播完整 API Key，而不是建立新的全局安全门禁体系。验收目标是证明“R02 不主动泄露 Key”，不是证明“整个仓库任何位置绝对不存在任何可能的 secret 字符串”。

## 12. R02 / R03 Boundary

| 责任 | AM7-R02 | AM7-R03 |
| --- | --- | --- |
| 当前 Active Configuration | 定义、保存、读取、修改 | 消费 |
| Provider identity | 作为稳定字符串保存 | 解释并映射到具体 Runtime |
| API Key | 本地保存并按安全展示边界提供 | 用于真实 Provider 认证 |
| Base URL | 保存用户最终当前值 | 定义 Provider 默认值和实际 endpoint 行为 |
| Model | 保存真实 API identifier | 发现、选择并用于 Runtime 请求 |
| 完整性 / 无效配置 | 分类并报告 | 根据具体操作决定所需字段，拒绝不满足该操作的输入 |
| `list_models()` | 不实现 | 实现真实网络调用 |
| Connection check | 不联网、不执行 | 明确触发后执行真实检查 |
| Verification state | 持久化、按配置变化失效 | 将真实结果作为 `verified` / `failed` 写回 |
| `complete()` / inference | 不实现 | 实现并处理 Provider Runtime 行为 |
| Provider network errors | 不定义厂商网络语义 | 归一化并向上层报告 |

### 12.1 R03 Consumption

R03 后续读取 R02 返回的配置字段及其分类。R02 必须让 R03 能区分“没有配置”“可编辑但不完整”“无效”“版本不受支持”和“完整有效”，而不是只返回空值或抛出导致整个应用终止的未分类错误。

R03 不得绕开 R02 再建立 Qwen 或 DeepSeek 私有的持久化配置来源。Provider-specific defaults、认证请求、模型列表和网络错误属于 Runtime；一旦确定用户当前采用的 Provider、Base URL 和 Model，当前事实仍回到 R02 的统一配置中。

### 12.2 Verification Write-back

后续 R03 在明确执行 connection check 后：

- 成功：向 R02 写回 `verified` 和检查完成时间；
- 失败：向 R02 写回 `failed` 和检查完成时间；
- 未执行真实检查：不得写入 `verified` 或 `failed`；
- 检查所用连接字段已不是当前值：该结果不得替代当前配置的 `unverified`。

R02 只负责保存这一结果，不保存 Provider-specific error history，也不把 connection check 扩展为 inference test。

## 13. Expected System Behavior

### 13.1 R02 完成后的用户可见行为

R02 暂时不接入 Ocria 主启动菜单，因此最终用户可以没有新的菜单项或完整配置流程。当前“开始运行 Ocria Am7 / 创建或更新校准模板 / 退出”的交互不因 R02 改变。

这不是功能缺失，而是明确的阶段边界：等 R03 具备 Provider Runtime、模型发现和 connection check 后，再由后续批准范围一次性提供完整配置体验。

### 13.2 Daily Startup

Ocria 日常启动不得因为 R02：

- 自动发起网络请求；
- 自动执行 connection check；
- 自动调用 `list_models()`；
- 自动调用模型；
- 自动产生付费推理。

如果未来启动流程读取 R02 配置，该行为也只能是本地读取和状态分类。任何真实网络动作必须由 R03 在明确的 Runtime / 用户操作语义下执行。

### 13.3 Missing or Unusable Configuration

- 未配置时，系统可以明确识别“尚未配置”，而不是崩溃或假定默认 Provider。
- 不完整时，系统可以展示或传递缺少配置的状态，但不能把它视为完整 inference 配置。
- 损坏或无效时，系统可以明确识别配置不可用，并保留用户显式修正的机会。
- 版本不受支持时，系统可以明确识别版本问题，不自动猜读。
- 上述任一状态都不会由 R02 自动触发网络或付费行为。

## 14. Failure / Invalid Configuration Semantics

### 14.1 Failure Categories

| 类别 | 示例 | R02 结果 |
| --- | --- | --- |
| Absence | 专用配置文件不存在 | `not configured` |
| Incompleteness | 缺少或清空 Provider / API Key / Base URL / Model 中的一项 | `incomplete configuration` |
| Serialization invalidity | JSON 截断、语法损坏、根不是对象 | `invalid configuration` |
| Schema invalidity | `config_version` 缺失/类型错误、verification 枚举非法、字段类型不符 | `invalid configuration` |
| Basic value invalidity | 非空 Base URL 明显不是可解释 URL、时间值无法解释 | `invalid configuration` |
| Version incompatibility | 可识别版本不是 `1` | `unsupported config version` |
| Persistence failure | 写入或整体替换未完成 | 保存失败；上一份完整正式配置保持可读，或新配置完整生效 |
| Runtime connectivity failure | R03 真实 connection check 失败 | R03 写回 `failed`；不等于配置 JSON 无效 |

### 14.2 Required Error Behavior

- 配置错误不得导致整个 Ocria 进程因未处理配置异常而崩溃。
- 返回结果必须足以区分缺失、不完整、无效和版本不受支持。
- 错误说明可以指出字段或结构问题，但不得包含完整 API Key。
- R02 不自动删除、覆盖或推测损坏配置。
- 配置无效与 Provider 网络失败是两类不同事实：前者属于本地配置解释，后者只能由 R03 的真实网络检查产生。

## 15. Acceptance Intent

后续 TID 应以最小充分方式证明以下 Requirement 级行为，不为这些意图额外发明安全门禁、复杂 harness 或 Evidence framework：

- **AC-01 — Single active configuration**：R02 只维护一份当前 Active Provider Configuration，不引入 Profile、账户池或历史系统。
- **AC-02 — Field persistence**：v1 必要字段能够保存并按相同业务值读取，包括 Provider、API Key、Base URL、Model、verification 状态和最后验证时间。
- **AC-03 — Restart persistence**：一次成功保存后，新的 Ocria 进程仍能读取相同配置；用户无需重新输入 API Key。
- **AC-04 — Load classification**：不存在、不完整、无效、unsupported version 和有效配置能被明确区分。
- **AC-05 — Provider invalidation**：Provider 有效值变化使 verification 变为 `unverified` 并清空最后验证时间。
- **AC-06 — Credential invalidation**：API Key 有效值变化使 verification 变为 `unverified` 并清空最后验证时间。
- **AC-07 — Endpoint invalidation**：Base URL 有效值变化使 verification 变为 `unverified` 并清空最后验证时间。
- **AC-08 — Model-only preservation**：仅 Model 有效值变化不错误地使 Provider connectivity verification 失效，且保留对应最后验证时间。
- **AC-09 — No-change preservation**：重复保存相同有效值不改变 verification 状态或时间。
- **AC-10 — Verification persistence**：R03 概念边界写回的 `verified` 或 `failed` 及其时间能持久化，并且旧连接输入的结果不能覆盖已变化配置的 `unverified`。
- **AC-11 — Corruption and version handling**：损坏 JSON 和不受支持版本被识别为不可用，不导致整个 Ocria 崩溃，也不被自动猜测或迁移。
- **AC-12 — Reliable save**：更新保存中断或失败时，上一份完整正式配置不会被破坏成部分 JSON。
- **AC-13 — API Key display safety**：普通配置展示只报告 `configured` / `not configured`，不输出完整 API Key；普通错误、日志和非配置业务数据不主动复制该完整值。
- **AC-14 — Local-only behavior**：创建、保存、读取、分类和修改配置本身不发起网络请求、模型调用或付费推理。
- **AC-15 — R02/R03 separation**：R02 不包含 Qwen / DeepSeek Runtime、`list_models()`、connection check 网络执行、`complete()` 或 Test Inference。
- **AC-16 — Startup and Legacy boundary**：R02 不新增主启动菜单入口，不修改 Legacy OCR、Candidate、Screening、Decision、Action、校准、WindMouse 或页面自动化行为。
- **AC-17 — Local secret boundary**：专用配置文件被 Git ignore，且完整 API Key 不进入 OCR Store、Run Manifest、Candidate data、AI Result、release asset 或其它业务记录。

这些 Acceptance Intent 定义要证明的行为，不规定具体测试文件、测试命令、Change 拆分、Evidence 路径或执行协议；这些内容属于 TID。

## 16. Risks / Constraints

### 16.1 Plaintext Credential Risk

本地明文配置意味着拥有该文件读取权限的用户或进程可以看到 API Key。这是 v1 已接受的限制。R02 通过专用本地文件、Git ignore 和不向普通输出复制真实值来控制暴露面，但不宣称加密保护。

### 16.2 Manual File Damage

用户或外部工具可能手工截断、错误编辑或写入不受支持版本。R02 的责任是明确识别不可用状态并避免整个 Ocria 崩溃，不是自动恢复未知原意。

### 16.3 Connectivity Is Not Model Capability

`verified` 容易被误解为“当前模型一定能推理”。本 RPD 明确将其限制为 Provider connectivity。Model inference 能力只能由后续 Runtime / Model Smoke 证明。

### 16.4 Provider-specific Change

Provider endpoint、模型列表和能力会变化。R02 只保存当前事实，不把这些易变元数据固化进 v1 Schema；R03 负责 Provider-specific 行为。

### 16.5 No R02 Menu Entry

R02 完成后不会立即形成完整用户配置体验。这是为保持 R02/R03 边界而接受的阶段性结果，不授权提前制作无法完成连接检查或模型发现的半成品 UI。

### 16.6 Legacy Freeze

AM7-R01 是 Accepted 稳定基线。R02 必须在 Greenfield 配置区域内实现，不能以配置接入为由修改 Legacy Core、现有业务 Schema 或页面动作。

## 17. Open Questions

Open Questions: None

本 RPD v0.2 已经 Human Review 批准并冻结，是 AM7-R02 后续 TID 的产品输入。本轮到此停止，不继续编写 TID、拆分 Change、实施代码、修改主菜单、接入 Provider Runtime，或执行 commit、push、PR、merge、rebase、tag、release。
