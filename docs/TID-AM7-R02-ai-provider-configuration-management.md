# Ocria Am7 AM7-R02 TID：AI Provider 配置管理

## 1. Document Status

| 项目 | 内容 |
| --- | --- |
| 产品 | Ocria |
| Generation / Codename | Am7 |
| Requirement | AM7-R02 |
| 文档类型 | TID（Technical Implementation Document） |
| 文档版本 | 0.1 |
| 编写日期 | 2026-08-15（Asia/Shanghai） |
| 当前阶段 | Approved / Frozen for Implementation |
| Requirement Branch | `am7-r02-ai-provider-config` |
| 上游产品合同 | `RPD-AM7-R02-ai-provider-configuration-management.md` v0.2 / Approved / Frozen for TID |
| 上游稳定基线 | AM7-R01 Accepted / `a75fd28` |
| 实施状态 | Not Started；本 TID 不授权自动开始实施 |

本文把冻结 RPD v0.2 下沉为 AM7-R02 的精确技术实施合同。本文只设计实现文件、类型、接口、JSON、持久化、测试和 Change 顺序；本轮不修改产品代码、不运行测试、不创建 implementation commit，也不授权 push、PR、merge、rebase、tag 或 release。

本 TID 没有发现 `CONTRACT CONFLICT`。如后续实施发现必须改变 RPD 字段、状态、失效语义、R02/R03 边界或 Legacy Freeze，必须交回 Human / Sol，不得在 Change 内自行改写合同。

## 2. Inputs / Contract

### 2.1 Authoritative Inputs

本 TID 的优先输入为：

1. 冻结的 AM7-R02 RPD v0.2；
2. `CODEX-CONSTITUTION.md`；
3. Accepted AM7-R01 baseline 与 Legacy Freeze；
4. 当前 `am7-r02-ai-provider-config` 分支的 targeted repository findings。

RPD 决定产品语义，TID 只决定最小技术实现。TID 不重新讨论以下已冻结决定：单一 Active Configuration、Provider-agnostic、七个持久化字段、五类读取状态、三态 Provider connectivity、Model-only 不失效、本地明文 API Key、可靠替换保存、无 R02 菜单、无网络、无 Legacy 修改。

### 2.2 Implementation Boundary

AM7-R02 的最终生产实现只允许新增一个 Greenfield 根模块，并修改一个精确 ignore 文件：

- 新增 `ai_provider_config.py`；
- 新增 `tests/test_ai_provider_config.py`；
- 修改 `.gitignore`。

冻结 RPD 和本 TID 是设计文档，不计入后续产品实施文件。后续实施不得修改 `simple_brush.py`、`BossOCR.spec`、requirements、OCR / Candidate / Screening / Action 模块或任何既有测试。

## 3. Targeted Repository Findings

本轮只检查了与 R02 直接相关的仓库区域，结论如下：

| 观察项 | 当前事实 | TID 决定 |
| --- | --- | --- |
| Python 布局 | 生产模块位于仓库根目录，没有要求新功能建立 package hierarchy | 新增单一根模块 `ai_provider_config.py` |
| Python 版本习惯 | 构建使用 Python 3.11；OCR requirements 注明 Python 3.10+；现有代码使用 `from __future__ import annotations` 和 `typing.Optional` | 新模块保持 Python 3.10+ / 3.11 兼容写法 |
| 本地路径 | `logs/`、`calibration_profiles/`、`data/ocr_runs/` 都使用相对当前工作目录的路径 | 使用独立 `config/ai_provider.json`，不引入 AppData abstraction |
| 启动工作目录 | `start.bat` 先 `cd` 到项目目录再启动 Python | 默认配置路径可稳定落在项目/便携运行目录下的 `config/` |
| JSON 模式 | `calibration_profiles.py` 使用 `pathlib`、`json`、显式字段检查；不依赖 JSON Schema | R02 使用标准库和小型显式解析，不新增 validation framework |
| 原子写入先例 | `ocr_store.py` 在目标目录写临时文件，关闭/flush 后使用 `os.replace`，异常时清理临时文件 | R02 采用同一产品语义，用 `tempfile` + `os.replace` 的独立最小实现 |
| 测试框架 | 现有测试使用标准库 `unittest`、`tempfile.TemporaryDirectory`、`unittest.mock.patch` | 新增一个 targeted unittest module，真实读写临时目录并最小注入替换失败 |
| 启动菜单 | 当前只提供运行、校准、退出；没有 AI 配置入口或 import | 不修改或测试新的启动菜单行为 |
| 打包入口 | PyInstaller 从 `simple_brush.py` 及其 imports 收集模块 | R02 不接 startup，故不修改 spec、不执行 package acceptance；R03 以后 import 时再自然纳入 |
| 依赖 | 当前没有 R02 必需的配置/Schema/Provider 依赖 | R02 standard library only，不修改 requirements |
| `.gitignore` | 已忽略日志、校准 JSON、OCR runs；尚无 AI Provider 配置规则 | 精确忽略正式配置及同目录临时配置文件 |

这些事实足以回答 R02 的实现落点，不需要 repository-wide audit、Legacy 复查、安全扫描或全仓日志检查。

## 4. Technical Goals

1. 用一个独立模块提供 `AIProviderConfig` 和 `AIProviderConfigStore`。
2. 用明确 enum 和 structured load result 表示三态 verification 与五类读取结果。
3. 精确实现 v1 七字段 JSON 合同和简单显式 validation。
4. 允许保存和加载 incomplete 配置，同时不把 invalid / unsupported 配置构造成可消费对象。
5. 用同目录临时文件和 `os.replace` 实现可靠保存。
6. 用一次纯粹的字段更新操作实现 verification invalidation。
7. 为 R03 提供最小 stale-safe connection verification 写回接口。
8. 通过 `repr=False` 和固定 API Key 状态文案提供安全展示边界。
9. 仅使用 Python 标准库，且所有 create/load/save/update/classify 操作保持本地离线。
10. 用一个 targeted test module 覆盖 RPD AC-01—AC-17 的直接 R02 行为。

## 5. Technical Non-Goals

本 TID 不设计或授权：

- Provider adapter、Provider Registry framework 或 plugin system；
- Qwen、DeepSeek 或其它 Provider 网络实现；
- HTTP client、Provider SDK、`list_models()`、connection check 网络执行或 inference；
- Test Inference、Model Smoke、Candidate Benchmark 或 token/cost 统计；
- 多配置、Profile、account、credential pool、history 或 environment system；
- DPAPI、Credential Vault、keyring、encryption 或 master password；
- repository-wide secret scanner、keyword scanner、Privacy Gate、Secret Gate 或 compliance framework；
- persistent revision、verification fingerprint、generation counter、optimistic locking 或 concurrency framework；
- backup、journal、checksum、database transaction 或 migration framework；
- main menu、startup UX、PyInstaller spec、build/release 或 requirements 修改；
- OCR、Candidate、Screening、Prompt、Decision、Action、calibration、WindMouse 或 browser automation 修改；
- 全量 Legacy regression、package build、BOSS live smoke、Provider network smoke 或 inference test。

## 6. Proposed File Layout

```text
Ocria/
├── .gitignore                                      # modify: two exact local-config rules
├── ai_provider_config.py                           # add: all R02 production types and behavior
├── config/
│   └── ai_provider.json                            # runtime-created, local, ignored, not committed
├── docs/
│   ├── RPD-AM7-R02-ai-provider-configuration-management.md
│   └── TID-AM7-R02-ai-provider-configuration-management.md
└── tests/
    └── test_ai_provider_config.py                  # add: one targeted unittest module
```

`config/` 不需要 `.gitkeep`。正式配置只有在用户或后续 R03 明确保存时才由 Store 创建。R02 不创建 `providers/`、`services/`、`repositories/`、`schemas/` 或其它层级。

## 7. v1 Configuration Data Contract

### 7.1 Constants and Canonical Provider IDs

`ai_provider_config.py` 冻结以下模块常量：

```python
AI_PROVIDER_CONFIG_VERSION = 1
DEFAULT_AI_PROVIDER_CONFIG_PATH = Path("config") / "ai_provider.json"
PROVIDER_ALIYUN_BAILIAN = "aliyun-bailian"
PROVIDER_DEEPSEEK = "deepseek"
```

两个 Provider 常量只冻结 R03 后续使用的首批 canonical identifier。它们不是 allowlist，也不形成 Provider capability table。R02 接受任何满足基础 identifier 语法的 Provider 字符串。

### 7.2 Exact JSON Keys

v1 正式 JSON object 只允许以下七个 key：

| JSON key | JSON type | Python type | Required in file | Semantics |
| --- | --- | --- | --- | --- |
| `config_version` | integer | `int` | Yes | 必须严格为 `1`；`bool` 不视为 integer |
| `provider` | string | `str` | No on load; Yes on save output | 缺失在内存中归一为 `""` 并形成 incomplete |
| `api_key` | string | `str` | No on load; Yes on save output | 缺失归一为 `""`；原值可明文持久化，repr 隐藏 |
| `base_url` | string | `str` | No on load; Yes on save output | 缺失归一为 `""`；非空时执行基本 HTTP(S) URL validation |
| `model` | string | `str` | No on load; Yes on save output | 缺失归一为 `""`；不验证 Provider model capability |
| `connection_verification_status` | string enum | `ConnectionVerificationStatus` | Yes | `unverified` / `verified` / `failed` |
| `last_verification_time` | string or null | `Optional[datetime]` | Yes | `unverified` 对应 `null`；其它两态对应 timezone-aware 时间 |

运行字段缺失或值为 `""` 时属于 incomplete；显式 JSON `null` 不等于缺失或空字符串，因类型不符而属于 invalid。Store 每次成功保存都写出全部七个 key，不省略 incomplete 字段。

v1 unknown key 一律返回 `invalid configuration`。这保证 `config_version = 1` 的文件不会悄悄携带未批准的持久化字段；未来新增字段必须配合新的配置版本设计，而不是由 v1 猜读。

### 7.3 Valid Example

```json
{
  "config_version": 1,
  "provider": "aliyun-bailian",
  "api_key": "<local-plaintext-api-key>",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model": "qwen3.7-flash",
  "connection_verification_status": "verified",
  "last_verification_time": "2026-08-15T14:30:00+08:00"
}
```

### 7.4 Canonical Incomplete / Unverified Example

```json
{
  "config_version": 1,
  "provider": "deepseek",
  "api_key": "",
  "base_url": "",
  "model": "",
  "connection_verification_status": "unverified",
  "last_verification_time": null
}
```

### 7.5 Serialization Format

- Encoding: UTF-8 without BOM.
- JSON serialization: `json.dumps(..., ensure_ascii=False, indent=2)` plus one final newline.
- Key insertion order follows the seven-key table for readability；load semantics do not depend on object order.
- No comments、trailing commas、JSON5 or JSON Schema dependency.
- Serialization code must build a dedicated mapping；ordinary display不得使用 `dataclasses.asdict(config)` 后直接打印。

### 7.6 Minimal Value Validation

- `provider`：`""` 表示未提供；非空值必须匹配 lower-case kebab-case `^[a-z0-9]+(?:-[a-z0-9]+)*$`。这不是 Provider allowlist。
- `api_key`：只要求为字符串；`""` 表示未提供；不检查 prefix、长度或厂商格式，也不 strip 或 mask 后再持久化。
- `base_url`：`""` 表示未提供；非空值使用 `urllib.parse.urlsplit`，只接受 `http` 或 `https` scheme，且 `hostname` 必须存在。不得联网，也不做完整 RFC validator。
- `model`：只要求为字符串；`""` 表示未提供；不建立模型格式、能力或存在性检查。
- 四个运行字段全部非空且其它 Schema 合法时，配置为 `valid`；否则为 `incomplete`。

## 8. Core Types

所有公开类型都放在 `ai_provider_config.py`，不建立第二个 DTO / repository / service module。

### 8.1 `ConnectionVerificationStatus`

```python
class ConnectionVerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILED = "failed"
```

该 enum 只表示 Provider connectivity。没有 inference、model、TTL 或 expired 状态。

### 8.2 `AIProviderConfigLoadStatus`

```python
class AIProviderConfigLoadStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    UNSUPPORTED_VERSION = "unsupported_version"
    VALID = "valid"
```

枚举名和值是代码合同；它们分别对应 RPD 的五类产品状态。

### 8.3 `AIProviderConfig`

```python
@dataclass(frozen=True)
class AIProviderConfig:
    config_version: int = AI_PROVIDER_CONFIG_VERSION
    provider: str = ""
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    model: str = ""
    connection_verification_status: ConnectionVerificationStatus = (
        ConnectionVerificationStatus.UNVERIFIED
    )
    last_verification_time: Optional[datetime] = None
```

技术合同：

- dataclass 必须 frozen；字段更新通过构造新值完成。
- `api_key` 保持正常 equality comparison，但从 dataclass `repr()` / `str()` 中排除。
- `__post_init__` 只做第 7 节定义的简单 Schema / value / verification-time consistency 检查，错误使用不含输入值的静态 `ValueError` 文案。
- `is_complete` 只读 property 在四个运行字段都非空时返回 `True`。
- `api_key_display()` 返回且只返回 `"API Key: configured"` 或 `"API Key: not configured"`。
- 不提供 masked fragment、last four characters 或通用 secret formatter。

### 8.4 `AIProviderConfigLoadResult`

```python
@dataclass(frozen=True)
class AIProviderConfigLoadResult:
    status: AIProviderConfigLoadStatus
    config: Optional[AIProviderConfig] = None
    error: Optional[str] = None
```

精确不变量：

- `NOT_CONFIGURED`：`config=None`、`error=None`。
- `INCOMPLETE` / `VALID`：`config` 非空、`error=None`。
- `INVALID` / `UNSUPPORTED_VERSION`：`config=None`、`error` 为简短、不含 API Key 或原始 JSON 的原因。
- Error reason 可以包含字段名、配置版本和文件路径，但不得插入字段原值。

### 8.5 `AIProviderConfigIOError`

只新增一个 persistence exception：

```python
class AIProviderConfigIOError(RuntimeError):
    pass
```

它包装真实 read、directory creation、temp write、close 或 replace 的 `OSError`。配置内容错误不使用该异常，而是由 `load()` 返回 structured status。构造或更新一个不符合 v1 合同的 Python 对象使用内建 `ValueError`；不创建复杂 exception hierarchy。

### 8.6 `AIProviderConfigStore`

```python
class AIProviderConfigStore:
    def __init__(
        self,
        path: Path = DEFAULT_AI_PROVIDER_CONFIG_PATH,
    ) -> None: ...

    def load(self) -> AIProviderConfigLoadResult: ...

    def save(self, config: AIProviderConfig) -> Path: ...

    def update(
        self,
        current: AIProviderConfig,
        *,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AIProviderConfig: ...

    def record_connection_verification(
        self,
        *,
        checked_provider: str,
        checked_api_key: str,
        checked_base_url: str,
        status: ConnectionVerificationStatus,
        completed_at: datetime,
    ) -> bool: ...
```

`update()` 中 `None` 表示该参数没有参与此次更新；`""` 表示明确清空字段并允许配置变为 incomplete。所有成功改变持久化状态的方法都通过同一个 `save()` atomic path，不存在旁路写入。

首次创建不增加单独的 Manager / Service 方法：调用方构造一个 structurally valid 的 `AIProviderConfig`（可以 incomplete），再调用 `save()`。这同样是用明确新输入替代磁盘上 invalid / unsupported 文件的唯一显式路径。

## 9. Load / Classification Contract

### 9.1 Ordered Load Algorithm

`AIProviderConfigStore.load()` 按以下顺序执行：

1. `path` 不存在，或检查后在读取前被删除并产生 `FileNotFoundError`：返回 `NOT_CONFIGURED`。
2. 文件读取发生其它 `OSError`：抛出 `AIProviderConfigIOError`，不得返回 `None` 或误报 invalid JSON。
3. `json.loads` 失败：返回 `INVALID`，reason 为 `configuration is not valid JSON`；不包含 parser 附带的原始文本。
4. JSON root 不是 object：返回 `INVALID`。
5. `config_version` 缺失、为 `bool` 或不是 `int`：返回 `INVALID`。
6. `config_version != 1`：立即返回 `UNSUPPORTED_VERSION`；不再按 v1 猜读其它字段。
7. 存在七个允许 key 之外的 unknown key：返回 `INVALID`。
8. verification status 或 time key 缺失、类型错误或相互不一致：返回 `INVALID`。
9. runtime field 缺失：用 `""` 构造；runtime field 存在但不是 string：返回 `INVALID`。
10. 非空 Provider 或 Base URL 未通过第 7.6 节基础检查：返回 `INVALID`。
11. 解析成 `AIProviderConfig`；`is_complete=True` 返回 `VALID`，否则返回 `INCOMPLETE`。

该过程不修改或重写文件，不发起网络，也不自动从错误内容恢复。

### 9.2 Unsupported Version

`config_version` 必须用 `type(value) is int` 判断，避免 JSON boolean 被 Python 当作 integer。任何整数但不等于 `1` 的版本都返回 `UNSUPPORTED_VERSION`，error 可写为 `unsupported config_version: 2`。R02 不迁移、不覆盖、不构造部分 config。

### 9.3 Invalid Result

`INVALID` 不返回 `AIProviderConfig`，避免调用方误用半解析对象。Reason 必须是字段/结构级文案，例如：

- `configuration root must be an object`
- `config_version must be integer 1`
- `unknown configuration field`
- `connection_verification_status is invalid`
- `base_url must be an absolute HTTP(S) URL`
- `last_verification_time must include a timezone offset`

文案不得包含 JSON field value，尤其不得包含 `api_key` 原值。

## 10. Verification Time Contract

### 10.1 Python and JSON Representation

- Python：`Optional[datetime]`。
- JSON：`null`，或 `datetime.isoformat()` 可生成并由 `datetime.fromisoformat()` 读取的 ISO 8601 字符串。
- 接受的非空形式必须包含日期、`T`、时分秒和显式数字 timezone offset：`YYYY-MM-DDTHH:MM:SS[.ffffff]±HH:MM`。
- v1 serializer 保留传入 datetime 的 offset 和可选 microseconds，不自动转换时区。
- Naive datetime、缺少 offset 的字符串或不能解析的字符串均 invalid。
- 不使用 `Z` 作为 v1 canonical output；UTC 以 `+00:00` 输出。

### 10.2 State Consistency

| Status | `last_verification_time` |
| --- | --- |
| `unverified` | 必须是 `None` / JSON `null` |
| `verified` | 必须是 timezone-aware `datetime` / JSON string |
| `failed` | 必须是 timezone-aware `datetime` / JSON string |

R02 不计算时间年龄，不增加 TTL，也不因时间经过自动修改 status。

## 11. Save / Atomic Persistence Contract

### 11.1 Exact Mechanism

`AIProviderConfigStore.save(config)` 使用以下标准库流程：

`save()` 接受 structurally valid 的 complete 或 incomplete `AIProviderConfig`；完整性不是持久化前置条件。它不接受 invalid Python config，也不负责写入 unsupported version。

1. 在任何目标文件写入前，将 config 显式转换为七-key mapping 并完成 `json.dumps`。
2. 创建 `path.parent`，使用 `mkdir(parents=True, exist_ok=True)`。
3. 使用 `tempfile.NamedTemporaryFile` 在 `path.parent` 创建临时文件，参数至少包含：UTF-8 text mode、`delete=False`、prefix `.ai_provider.`、suffix `.tmp`。
4. 一次写入完整 serialized JSON 和 final newline。
5. 正常退出 `with`，确保 Windows 上临时文件已经 flush 并关闭。
6. 调用 `os.replace(temp_path, path)` 整体替换正式文件。
7. 成功返回正式 `Path`。
8. 任一 I/O 步骤失败时，尽力删除本次临时文件；清理失败不得遮蔽原始错误；随后抛出不含配置值的 `AIProviderConfigIOError`。

临时文件和正式文件位于同一目录，因此正常本地文件系统上的 replace 不跨文件系统。v1 不要求额外 `fsync` framework、backup、journal、checksum 或 transaction manager。

### 11.2 Failure Semantics

- 有旧正式配置且 temp write / close / replace 失败：旧文件内容保持不变且仍可由新 Store instance 读取。
- 无旧正式配置且保存失败：正式 `config/ai_provider.json` 不存在；临时文件不被当作正式配置。
- 成功：正式路径只呈现完整的新 JSON。
- 序列化或 config validation 在创建临时文件前完成；这类 `ValueError` 不被包装成 I/O failure。

测试只对 `os.replace` 做一次 targeted failure injection，不建立 crash simulator、filesystem chaos 或 process-killer framework。

## 12. Update / Verification Invalidation Contract

### 12.1 Update Algorithm

`AIProviderConfigStore.update(current, ...)` 执行：

1. `None` 参数取 `current` 原值；显式字符串（包括 `""`）作为 proposed value。
2. 用 proposed values 构造新的 v1 `AIProviderConfig`，因此共享同一简单 validation。
3. 比较 proposed 与 current 的 `provider`、`api_key`、`base_url` 原始有效值。
4. 三者任一不相等：强制 proposed status 为 `UNVERIFIED` 且 time 为 `None`。
5. 三者全部相等：原 verification status 和 time 原样保留；Model 是否变化不影响 connectivity。
6. 使用 `save()` 持久化 proposed config；成功后返回该 config。

短伪代码：

```text
connection_changed = any(
    proposed[field] != current[field]
    for field in (provider, api_key, base_url)
)

if connection_changed:
    status = unverified
    time = None
else:
    status = current.status
    time = current.time

save(replacement config)
```

### 12.2 Exact Change Semantics

| Effective change | Result |
| --- | --- |
| Provider only | `unverified` + `None` time |
| API Key only | `unverified` + `None` time |
| Base URL only | `unverified` + `None` time |
| Model only | preserve status + time |
| No effective change | preserve status + time |
| Multiple fields including any connection field | `unverified` + `None` time |
| Clear Provider / API Key / Base URL to `""` | incomplete + `unverified` + `None` time |
| Clear Model only | incomplete + preserve status + time |

不新增 event、observer、revision、history 或 state-machine framework。

## 13. Verification Write-back Contract

### 13.1 Interface Preconditions

`record_connection_verification(...)`：

- `status` 只接受 `VERIFIED` 或 `FAILED`；传入 `UNVERIFIED` 是调用合同错误，抛出静态 `ValueError`。
- `completed_at` 必须是 timezone-aware `datetime`；否则抛出静态 `ValueError`。
- checked values 是 R03 该次真实 connection check 实际使用的原始 Provider、API Key 和 Base URL。
- 方法本身不发起网络，也不接受或保存 Provider error detail。

### 13.2 Minimal Stale Comparison Algorithm

1. 在写回时调用 `load()` 重新读取当前正式配置。
2. 只有 `INCOMPLETE` 或 `VALID` 且 config 非空时继续；其它 load status 返回 `False`，不写文件。
3. 当前 Provider、API Key、Base URL 必须都非空，否则返回 `False`。
4. 精确比较当前三值与 `checked_provider`、`checked_api_key`、`checked_base_url`。
5. 任一不相等：视为 stale，返回 `False`；不得修改当前 `unverified` 或其它当前状态。
6. 三值全部相等：创建只替换 status 和 completed time 的 config，通过 atomic `save()` 持久化，返回 `True`。
7. Model 不参与比较，因此检查期间的 Model-only 变化不阻止 connectivity result 写回。

此接口不持久化 checked values、revision、fingerprint 或 generation。v1 采用当前 Ocria 本地单进程、顺序配置操作语义，不承诺多个进程同时写配置；不增加 lock、async 或 concurrency manager。

### 13.3 Save Failure

匹配结果写回时若 atomic save 发生真实 I/O failure，`AIProviderConfigIOError` 向调用方明确传播，旧正式配置保持完整。不得把 persistence failure 返回成 stale `False`，也不得把它转换为 `failed` Provider connectivity。

## 14. Safe API Key Presentation

### 14.1 Required Implementation

- `AIProviderConfig.api_key` 使用 `field(repr=False)`。
- `repr(config)` 和 `str(config)` 不含完整 Key；包含 config 的 `AIProviderConfigLoadResult` repr 也因此不含 Key。
- `config.api_key_display()` 对非空 Key 返回 `API Key: configured`，对空 Key 返回 `API Key: not configured`。
- 不显示 prefix、suffix、长度或 masked fragment。
- `ai_provider_config.py` 不调用 `print`、不配置 logger、也不把 config 传给业务记录。
- load / validation / I/O error message 只描述字段或操作，不插入 API Key 或原始 JSON。

### 14.2 Targeted Verification Boundary

测试使用一个明显的 synthetic sentinel API Key，只检查：

- config repr / str；
- load result repr；
- `api_key_display()`；
- R02 产生的 expected error reason / exception string。

不得扫描整个 repository、logs、release、OCR Store 或 package。普通 `token` / `key` / `secret` 技术词不构成失败；只有 sentinel 的完整真实值出现在上述明确输出路径才表示 R02 行为错误。

## 15. Local Config Path / Git Ignore

### 15.1 Default Path

默认路径冻结为：

```text
config/ai_provider.json
```

它相对于当前工作目录解析，遵循现有 `logs/`、`calibration_profiles/` 和 `data/ocr_runs/` 本地路径惯例。`AIProviderConfigStore(path=...)` 允许测试和未来明确调用方注入其它 `Path`；R02 不实现 OS-wide AppData、home directory 或 credential store abstraction。

该路径独立于：

- `data/ocr_runs/`；
- OCR Store / Run Manifest；
- Candidate data；
- logs；
- AI Result。

### 15.2 Exact `.gitignore` Rules

在 Runtime data 区域增加：

```gitignore
# Local AI Provider configuration (contains plaintext API key)
/config/ai_provider.json
/config/.ai_provider.*.tmp
```

第二条只覆盖 R02 `NamedTemporaryFile` 的精确命名模式，避免一次失败清理后残留的同内容临时配置被 Git 识别；它不是 repository-wide secret rule。不得忽略整个 `config/`，以免未来受版本控制的非敏感配置被无意隐藏。

## 16. Error Handling

| Situation | Technical result |
| --- | --- |
| File missing | structured `NOT_CONFIGURED` |
| JSON / Schema / field invalid | structured `INVALID` + safe reason |
| Unsupported integer version | structured `UNSUPPORTED_VERSION` + safe reason |
| Runtime fields missing / empty, rest valid | structured `INCOMPLETE` + config |
| Complete v1 | structured `VALID` + config |
| Read permission / other read I/O failure | raise `AIProviderConfigIOError` |
| Save directory / temp write / close / replace failure | raise `AIProviderConfigIOError`；old target preserved |
| Invalid Python config/update argument | static `ValueError` |
| Stale verification result | return `False`；not an exception and no write |
| Matching verification write-back | atomic save and return `True` |

不得吞掉所有异常后返回 `None`，也不得把本地 I/O failure 记录成 Provider `failed`。R02 不记录错误日志；调用方以后可以在不包含 API Key 的前提下处理 structured result 或明确 exception。

## 17. Change Plan

AM7-R02 拆为 3 个顺序 Change。三个 Change 足以把一个小型 Greenfield 配置模块从数据合同推进到可靠存储和边界验收；不需要 4—12 个更细层级。

### Change 1 — v1 Core Types, JSON and Load Classification

**Goal**

建立单一配置对象、两个 enum、structured load result、v1 JSON parser 和五类 load contract。

**Files**

- Add `ai_provider_config.py`
- Add `tests/test_ai_provider_config.py`

**Exact implementation contract**

- 增加第 7—10 节冻结的 constants、types、simple validation、JSON mapping 和 `AIProviderConfigStore.load()`。
- `api_key` 从首次创建 dataclass 起即 `repr=False`。
- Runtime missing fields 归一为空字符串；invalid / unsupported 不返回 config。
- 不实现网络、Provider runtime、menu 或其它 package。

**Tests added / modified**

- `AIProviderConfigDataContractTests`
- valid v1 decode / encode shape；canonical Provider constants；basic Provider / Base URL validation；timezone contract。
- `AIProviderConfigLoadTests.test_load_classification_matrix` 使用 `subTest` 覆盖 missing、incomplete、invalid JSON、invalid Schema、unsupported、valid。
- unknown key 和 safe error reason 的少量代表测试。

**Change acceptance**

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_ai_provider_config.py" -v
```

**Explicit non-goals**

Atomic save、update、verification write-back、`.gitignore`、Provider network、UI、Legacy changes。

### Change 2 — Atomic Store, Update and Verification Write-back

**Goal**

完成 Store 的可靠保存、字段更新失效语义和 R03 stale-safe verification 写回。

**Files**

- Modify `ai_provider_config.py`
- Modify `tests/test_ai_provider_config.py`

**Exact implementation contract**

- 实现 `save()` 的 same-directory `NamedTemporaryFile` + close + `os.replace`。
- 实现 `update()` 的 exact-value comparison 和 invalidation matrix。
- 实现 `record_connection_verification()` 的三个 checked value 比较、boolean applied result 和 atomic write-back。
- 只新增一个 I/O exception；无 lock、revision、fingerprint、history 或 event system。

**Tests added / modified**

- `AIProviderConfigPersistenceTests`：valid save/load、新 Store reload、replace failure with/without existing target、temp cleanup。
- `AIProviderConfigUpdateTests`：Provider/API Key/Base URL 参数化 invalidation、Model-only、no-op、multi-field。
- `AIProviderConfigVerificationWriteBackTests`：matching verified、matching failed、stale result、Model-only current change。

**Change acceptance**

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_ai_provider_config.py" -v
```

**Explicit non-goals**

真实 connection check、network mock、concurrency manager、backup、fsync framework、journal、database、full regression。

### Change 3 — Safe Presentation and Local File Boundary

**Goal**

完成固定 API Key 状态展示、明确 R02 输出边界和正式/临时配置的精确 Git ignore。

**Files**

- Modify `ai_provider_config.py`
- Modify `tests/test_ai_provider_config.py`
- Modify `.gitignore`

**Exact implementation contract**

- 增加 `api_key_display()` exact strings；保持 `repr=False`。
- R02 error strings 不插入输入值或原始 JSON。
- 增加第 15.2 节两条 ignore 规则。
- 完成 AC mapping 所需 targeted checks；不触碰任何其它文件。

**Tests added / modified**

- `AIProviderConfigSafetyTests`：safe display、config/load-result repr、expected error strings 不含 synthetic full key。
- default path 与 temp naming contract 的直接断言。
- 不新增 repository/release/log scanner。

**Change acceptance**

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_ai_provider_config.py" -v
git check-ignore -v -- config/ai_provider.json config/.ai_provider.example.tmp
git diff --check
```

**Explicit non-goals**

全仓 secret audit、keyword gate、logging framework、UI、Provider SDK、packaging、release。

## 18. Testing Strategy

### 18.1 One Targeted Test Module

全部 R02 自动化测试位于 `tests/test_ai_provider_config.py`，使用标准库 `unittest`。测试通过 `tempfile.TemporaryDirectory()` 向 Store 注入独立 `Path`，不读写用户默认配置，也不需要网络、Provider credential 或模型。

建议测试分组：

| Test class | Core coverage |
| --- | --- |
| `AIProviderConfigDataContractTests` | fields、enum、JSON、Provider/Base URL、timezone、repr foundation |
| `AIProviderConfigLoadTests` | five load classifications、unknown fields、safe reasons |
| `AIProviderConfigPersistenceTests` | save/load/reload、atomic replacement failure、temp cleanup |
| `AIProviderConfigUpdateTests` | invalidation matrix、Model-only、no-op、multi-field |
| `AIProviderConfigVerificationWriteBackTests` | verified、failed、stale、Model-only write-back |
| `AIProviderConfigSafetyTests` | exact API Key display、repr、error value non-propagation、default path |

多个产品 AC 由同一测试组证明；不得为 17 个 AC 创建 17 个文件、harness 或 runner。

### 18.2 Classification Coverage

`test_load_classification_matrix` 至少包含：

- no file → `NOT_CONFIGURED`；
- missing/empty runtime field → `INCOMPLETE` + config；
- truncated JSON → `INVALID`；
- representative invalid Schema/type/status/time/URL → `INVALID`；
- integer version 2 → `UNSUPPORTED_VERSION`；
- full v1 → `VALID` + config。

使用少量代表 case 和 `subTest`；不做 fuzz、property framework 或几十种畸形 JSON 组合。

### 18.3 Persistence and Restart

测试在 temporary path 保存完整配置，然后创建新的 `AIProviderConfigStore(path)` instance 加载，证明配置和 API Key 继续存在。测试不得通过重新输入 Key 或共享旧 Store object 伪装 restart persistence。

### 18.4 Invalidation

Provider、API Key、Base URL 三组 change 使用 subTest / table-driven case，共同断言 `UNVERIFIED` 和 `None` time。另测 Model-only 与 exact no-op 保留 status/time；一个 multi-field case 证明 connection field 优先失效。

### 18.5 Verification Write-back

- matching checked tuple + `VERIFIED` → `True`，reload 后 status/time 持久化；
- matching checked tuple + `FAILED` → `True`，reload 后 status/time 持久化；
- 当前 connection tuple 已变化 → `False`，reload 后保持当前 `UNVERIFIED` / `None`；
- 当前只变化 Model → tuple 仍匹配，允许 connection result 写回。

不发网络请求，不 mock Provider API。

### 18.6 Reliable Save Failure Injection

仅 patch `ai_provider_config.os.replace` 抛出 synthetic `PermissionError`：

- 先有旧配置：断言 `AIProviderConfigIOError`、旧 bytes 未变、新 Store 仍能 valid load、无 `.ai_provider.*.tmp`。
- 没有旧配置：断言正式 target 不存在、无残缺 target、无临时残留。

这直接证明 atomic product semantics；不建立 crash simulator 或 filesystem chaos framework。

### 18.7 API Key Safety

使用 synthetic sentinel，例如 `synthetic-r02-key-value`，只断言它不出现在：

- `repr(config)` / `str(config)`；
- `repr(load_result)`；
- `api_key_display()`；
- 代表性的 invalid/load/save error string。

同时断言 raw `config.api_key` 仍保持该值，证明 R03 以后可以在内存消费。不得扫描 repository、logs、release 或 business stores。

### 18.8 Local-only and Legacy Boundary

新模块 imports 只允许：`dataclasses`、`datetime`、`enum`、`json`、`os`、`pathlib`、`re`、`tempfile`、`typing`、`urllib.parse` 等标准库。没有 HTTP client / Provider SDK 时，不建立全局 network interception test。

实施 touched files 只允许 `ai_provider_config.py`、`tests/test_ai_provider_config.py`、`.gitignore`。`simple_brush.py` 和所有 Legacy 模块/测试无 diff 即证明 R02 未接 startup / Legacy；不创建 Legacy scanner。

## 19. Acceptance Mapping AC-01—AC-17

| AC | Implementation location | Targeted test / inspection evidence |
| --- | --- | --- |
| AC-01 | One `DEFAULT_AI_PROVIDER_CONFIG_PATH` and one `AIProviderConfigStore`; no profile types | default-path assertion + touched-file inspection |
| AC-02 | `AIProviderConfig` + seven-key serializer/parser | valid round-trip test |
| AC-03 | `save()` and new Store `load()` from same temp path | process-style new-instance reload test |
| AC-04 | `AIProviderConfigLoadStatus` + ordered load algorithm | classification matrix |
| AC-05 | `update()` provider comparison | connectivity-field parameterized test |
| AC-06 | `update()` API Key comparison | connectivity-field parameterized test |
| AC-07 | `update()` Base URL comparison | connectivity-field parameterized test |
| AC-08 | `update()` excludes Model from invalidation tuple | Model-only preservation test |
| AC-09 | exact proposed/current equality | no-op preservation test |
| AC-10 | `record_connection_verification()` + atomic save | verified/failed/stale/Model-only write-back tests |
| AC-11 | structured invalid / unsupported results | invalid JSON/Schema and version-2 cases |
| AC-12 | same-directory temp + closed file + `os.replace` | two targeted replace-failure tests |
| AC-13 | `repr=False` + `api_key_display()` + safe reasons | sentinel targeted presentation/error tests only |
| AC-14 | standard-library-only module with local temp-path tests | import inspection + targeted tests; no network gate |
| AC-15 | no Runtime imports/methods; Store only handles local config | touched module inspection; requirements unchanged |
| AC-16 | implementation allowlist excludes startup/Legacy | `git status` / touched-file review; no full Legacy scanner |
| AC-17 | exact `.gitignore` rules + no business-store integration | `git check-ignore` + sentinel targeted tests + touched-file review |

AC-13 / AC-17 明确采用 R02 data-flow targeted verification。该映射不授权 repository-wide secret audit、release audit 或关键词门禁。

## 20. Final Acceptance Commands

Terra / Codex 在全部 3 个 Change 完成后，从 branch root 依次执行一次：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_ai_provider_config.py" -v
.\venv\Scripts\python.exe -m py_compile ai_provider_config.py tests\test_ai_provider_config.py
.\venv\Scripts\python.exe -c "import ai_provider_config; print(ai_provider_config.AI_PROVIDER_CONFIG_VERSION)"
git check-ignore -v -- config/ai_provider.json config/.ai_provider.example.tmp
git diff --check
git status --short --branch
```

Pass intent：

- targeted unittest 全部通过；
- 新生产/测试模块 compile 且 production module import 成功；
- 两个精确 runtime paths 命中预期 `.gitignore` 规则；
- tracked diff 无 whitespace error；
- status 只出现已知 RPD/TID 文档和三个 implementation-scope 文件，没有 Legacy/startup 修改。

### 20.1 Full Regression Decision

AM7-R02 **不要求 full 783 regression**。原因是批准的实施只新增一个未接入 startup 的 Greenfield module、一个 targeted test module，并修改 `.gitignore`；没有既有 production import、Legacy algorithm、Candidate、action、startup 或 packaging path 被修改。运行完整 OCR/browser suite 不能为 R02 的配置语义提供额外直接证据，只会扩大执行成本。

本 TID 也不要求 packaging、EXE build、BOSS live smoke、browser smoke、Provider API test、network smoke 或 inference test。若实施需要修改本 TID allowlist 外文件，那是 scope deviation，需要先交回 Human / Sol，而不是自动增加 full regression 来扩大授权。

## 21. Execution / Evidence Rules

### 21.1 First-run Capture

每个 Change 和 Final Acceptance 的命令第一次执行时就保留：

- exact command；
- exit code；
- concise unittest / compile / Git result；
- 失败时定位所需的错误输出。

测试自身输出是主要 evidence。无需 JSON evidence pipeline、base64 transcript、hash manifest、PASS parser、wrapper 或额外 evidence framework。

### 21.2 Rerun Discipline

不得为了补一个额外日志文件而重跑已经明确通过的测试。只有实现经过授权修复，或有证据表明首次失败是基础设施问题时，才运行必要的 targeted command，并记录原因。不得重复 benchmark；R02 本身没有 benchmark。

### 21.3 Branch / Git Discipline

- 所有实施只发生在 `am7-r02-ai-provider-config`。
- 不直接修改 `main`，不切回 main 实施。
- TID 不自动授权 commit 或 push；是否执行由后续 Human 指令决定。
- 未经明确授权不得 merge、rebase、reset、tag、release。
- 预期最终流程是 implementation → testing → Sol/Human acceptance → branch push → PR → main。

## 22. Risks / Constraints

### 22.1 Plaintext Local Credential

正式配置和短暂 temp 文件包含本地明文 API Key。精确 `.gitignore` 与 R02 safe output boundary 降低主动传播风险，但不提供静态加密，也不防止拥有本地文件读取权限的主体读取 Key。

### 22.2 Working-directory-relative Path

`config/ai_provider.json` 跟随当前 Ocria 相对路径惯例。`start.bat` 会切到项目目录；直接从其它 working directory 调用 Python / EXE 时，默认配置也相对于该目录。v1 不因此引入跨平台 AppData abstraction；调用方可显式注入 `Path`。

### 22.3 Strict v1 Unknown-field Handling

手工增加未知 key 会使 v1 invalid。这是为了保持七字段冻结合同，不代表 migration framework；未来扩展必须由新的 Requirement / config version 处理。

### 22.4 Filesystem Atomicity

同目录 temp + `os.replace` 提供当前本地文件系统上的最小 atomic replacement 语义。网络文件系统或非标准文件系统的特殊保证不在 R02 v1 范围内。

### 22.5 Single-process Writer Assumption

v1 以 Ocria 本地单进程、顺序配置操作为前提。stale result protection 比较 connection check 的实际输入与写回时当前配置；不支持多个进程并发写入，也不引入 lock/revision/concurrency framework。

### 22.6 Packaging Visibility

R02 暂不接 startup，因此当前 PyInstaller entry 不会主动 import 该模块。本 Requirement 的交付是配置基础设施源码与测试；R03 接入时通过正常 import 消费。R02 不为尚未接入的模块修改 spec 或执行 package build。

## 23. Open Technical Questions

Open Technical Questions: None

AM7-R02 TID v0.1 已完成 Human Review，并正式冻结为 Terra / Codex 后续实施的技术合同。未经下一步明确指令，不实施 Change 1，不修改产品代码，不运行测试，也不执行 commit、push、PR、merge、rebase、tag 或 release。
