# AM7-R05 — ScreeningProfile 动态筛选标准

## 1. Metadata

| Field | Value |
|---|---|
| Product | Ocria |
| Generation | Am7 |
| Requirement | AM7-R05 |
| Document Type | Technical Implementation Design |
| Version | 0.1 |
| Status | Frozen for Implementation |
| Prepared On | 2026-08-18（Asia/Shanghai） |
| Requirement Branch | am7-r05-screening-profile |
| Upstream Baseline | 9b0ebe9 |
| Source of Truth | docs/RPD-AM7-R05-screening-profile.md v0.2 Frozen |
| Governing Document | CODEX-CONSTITUTION.md v1.0 |

本 TID 只把 Frozen RPD 映射为最小技术实现。本次文档修订没有修改产品代码或测试代码，也没有执行 commit、push、merge、tag 或 release；后续 Implementation 仅可按本 TID 的冻结范围进行。

## 2. Frozen Inputs

实现必须同时遵守：

1. `CODEX-CONSTITUTION.md` v1.0；
2. `docs/RPD-AM7-R05-screening-profile.md` v0.2 Frozen；
3. AM7-R01 已冻结的 Candidate/OCR evidence、算法和页面 Action 边界；
4. 当前 `9b0ebe9` baseline 上的 Run、Store、Replay 与 startup 调用关系。

发生矛盾时不得自行增加 workaround、Gate、Guard、Scanner、Wrapper、Validator、Safety Layer 或 Stop Condition；必须按本 TID 的 escalation 条件交回 Human。

## 3. Implementation Objective

AM7-R05 的最小实现由三部分组成：

~~~text
Independent ScreeningProfile model/store
+ Configuration-only CLI
+ RunManifest binding optional for legacy/unbound compatibility,
  but mandatory for every production R05 Run
~~~

实现范围只覆盖：

- Criterion、Draft 与 immutable formal Profile Version；
- latest-based linear editing 与 Human Save；
- Criterion ID 自动生成；
- R05 专用 criteria digest；
- 独立本地正式版本历史；
- Run-level Profile binding；
- Run Start 前的 binding freeze；
- Candidate 通过既有 run_id 间接对齐；
- legacy unbound run 读取；
- Configuration / Execution Mode 的最小 startup wiring；
- terminally stopped 后下一次启动重新具备配置资格。

R05 不执行 Criterion Evaluation，不调用 LLM，不产生 Candidate Decision，也不触发页面 Action。

## 4. Targeted Repository Findings

本节只记录实现 R05 所必需的当前代码事实，不构成 repository-wide audit。

### 4.1 Branch and runtime baseline

- 当前分支为 `am7-r05-screening-profile`；
- 当前 baseline 为 `9b0ebe9`；
- repository 支持 Python 3.10+，当前批准的 Windows 开发/构建基线为 Python 3.11 x64；
- R05 只需要 Python 标准库，不需要 dependency change。

### 4.2 Run records

`ocr_records.py` 当前定义：

- `RunStatus`：`running`、`completed`、`interrupted`、`error`、`disabled`；
- `CandidateOcrDocument`：Candidate/OCR 事实对象，已通过 `run_id` 关联 Run；
- `RunManifest`：`run.json` 的对象合同；
- `_known_values()`：读取时忽略 additive unknown fields；
- `JsonRecordMixin` / `to_json_compatible()`：dataclass、Enum、Path 与 tuple 的 JSON conversion；
- 当前 OCR `STORAGE_SCHEMA_VERSION = 1.4.0`。

`RunManifest` 当前没有 ScreeningProfile binding。`CandidateOcrDocument` 也没有、并且不得新增任何 Profile 或 Criterion 字段。

### 4.3 Run persistence

`ocr_store.py` 中的 `JsonlOcrRecordStore`：

- 默认根目录为 `data/ocr_runs/`；
- constructor 创建 `RunManifest(status=running)`；
- `_initialize_files()` 先创建 Run 目录和三个 JSONL 文件，再通过 `_write_manifest_atomic()` 写 `run.json`；
- manifest 使用同目录 temporary file + `os.replace()` 完整替换；
- 初始化失败会保留 disabled Store，而不是抛出到 production caller；
- 后续 screen/candidate/error 写入保持 best-effort；
- `close()` 写入 `ended_at` 与 terminal `RunStatus`。

R05 不改变后续 OCR record 的 best-effort 语义；它只要求 production R05 Run 在初始、带 binding 的 manifest 未成功写入时停止于 Execution Mode 之前。

### 4.4 Replay and legacy compatibility

`ocr_replay.py` 的 `OcrRunReader.read_manifest()` 直接调用 `RunManifest.from_dict()`。因此 additive optional binding 可以在 `RunManifest` 层完成 restore；`ocr_replay.py` 本身不需要修改。

旧 `run.json` 缺少 binding 时必须 restore 为 `screening_profile_binding=None`。读取操作不得 backfill、猜测或改写旧文件。

### 4.5 Startup and execution boundary

`simple_brush.py` 当前调用顺序为：

~~~text
parse/get configuration input
→ initialize_run_ocr_storage()
→ initialize OCR when needed
→ start keyboard listener
→ foreground browser
→ candidate loop
→ close_run_ocr_storage(status)
~~~

因此最小 freeze 点已经存在：把已验证 binding 传入 Store constructor，并在 `initialize_run_ocr_storage()` 返回 disabled/None 时于 `initialize_ocr()`、listener 和 browser 操作之前返回即可。

Targeted exit-code inspection 同时确认：`parse_args()` 对缺失参数或非法 `--action-mode` 抛出 `ValueError`，`run()` / `main()` 当前在这一条参数解析路径返回 2；但项目没有把 Profile missing、stored data invalid、digest mismatch 或初始 persistence failure 统一冻结为 exit code 2。R05 因此不扩展该数字合同，只复用现有 startup/noninteractive failure handling，并冻结“不进入 Execution”的可观察结果。

### 4.6 Current stop, pause, and terminal behavior

- Space 只切换进程内 `paused`；RunManifest 仍为 `running`，没有配置菜单入口；
- `candidate_switch_failed` 写入 `stop_reason`，最终关闭为 `RunStatus.ERROR`；
- Human ESC 与 `run_duration_elapsed` 当前关闭为 `RunStatus.INTERRUPTED`；
- 未捕获的运行异常关闭为 `RunStatus.ERROR`；
- 正常结束关闭为 `RunStatus.COMPLETED`；
- 当前没有通用 crash resume 入口；`run()` 结束后进程退出，下一次启动重新进入 startup Configuration Mode。

R05 不增加 RunStatus 或 stop_reason。

### 4.7 Existing local persistence pattern

`AIProviderConfigStore` 已使用 `config/ai_provider.json` 和 temporary file + `os.replace()`。ScreeningProfile 是可追溯的运行数据历史，不是单一 current config，因此采用独立的 `data/screening_profiles/` 根目录，但复用同样简单的 same-directory atomic replace 写法。

### 4.8 Test layout and one required assertion migration

直接相关测试文件为：

- `tests/test_ocr_records.py`；
- `tests/test_ocr_store.py`；
- `tests/test_ocr_replay.py`；
- `tests/test_ocr_stage0_integration.py`；
- `tests/test_simple_brush_ocr.py`。

现有 `test_run_enabled_and_disabled_storage_keep_view_call_count_unchanged` 冻结的是 R05 之前“初始 Store disabled 仍继续浏览”的行为。Frozen RPD 已明确授权新 R05-bound production Run 在 binding persistence failure 时不得开始 Execution；该断言必须定向迁移为“disabled initial Store 不启动 listener/browser/view”。这不是未解决合同冲突：直接构造 Store 的 disabled 结果与 Run 开始后的 OCR append best-effort 行为仍保持不变。

## 5. Implementation Constraints

实现必须遵守：

- 独立 Profile persistence；
- 最小 RunManifest additive evolution；
- 最小 startup/CLI wiring；
- 单机、单进程、一次一个 Draft；
- Python 3.10+ / 3.11 compatible standard-library code；
- 不增加 database、ORM、migration framework、service layer、repository framework、event bus 或 plugin system；
- 不增加 generic version、rule、integrity、resume 或 state-machine framework；
- 不改变 OCR、Candidate scan、candidate switch、favorite、forward、WindMouse、threshold、scroll、retry 或 timing。

## 6. Final Module and File Layout

### 6.1 New implementation files

~~~text
screening_profile.py
screening_profile_cli.py
tests/test_screening_profile.py
tests/test_screening_profile_cli.py
~~~

`screening_profile.py` 集中包含 R05 domain objects、digest helper 与 local Store；当前规模不拆分 service/repository/version 子层。

`screening_profile_cli.py` 只提供 Configuration Mode 的交互，不被 Execution loop 调用。

### 6.2 Modified implementation files

~~~text
ocr_records.py
ocr_store.py
simple_brush.py
.gitignore
tests/test_ocr_records.py
tests/test_ocr_store.py
tests/test_ocr_replay.py
tests/test_ocr_stage0_integration.py
tests/test_simple_brush_ocr.py
~~~

### 6.3 No dependency or packaging file changes

以下文件不修改：

- `requirements.txt`；
- `requirements-ocr.txt`；
- `requirements-build.txt`；
- `BossOCR.spec`。

新模块由 `simple_brush.py` 的静态 import 可达，不增加 hidden import。

`.gitignore` 只在现有 runtime data rules 附近增加 `/data/screening_profiles/`，不修改任何既有 ignore rule。该规则只防止 Human 创建的本地正式 Profile 历史进入 Git tracking 或污染 `git status`，不改变 Profile persistence behavior。

## 7. ScreeningProfile Domain Model

所有 public type 和 signature 放在 `screening_profile.py`。

### 7.1 Constants

~~~python
RULE_MUST_MATCH = "must_match"
DEFAULT_SCREENING_PROFILE_ROOT = Path("data") / "screening_profiles"
~~~

不增加 rule registry 或 profile state enum。

### 7.2 Criterion

~~~python
@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    criterion_text: str
    rule: str = RULE_MUST_MATCH
~~~

构造约束：

- `criterion_id` 匹配 `C` + 至少三位十进制数字，数值大于 0；
- `criterion_text` 必须是非空且不全为空白的字符串；
- 保存原始 `criterion_text`，不自动 trim 或 Unicode normalize；
- `rule` 精确等于 `must_match`。

Criterion 不增加 score、weight、priority、category、expression 或 action。

`Criterion.to_dict()` / `Criterion.from_dict()` 只接受并输出 `criterion_id`、`criterion_text`、`rule` 三个 key；不接受同义字段或 additive business fields。

### 7.3 Formal ScreeningProfileVersion

~~~python
@dataclass(frozen=True)
class ScreeningProfileVersion:
    screening_profile_id: str
    profile_version: int
    criteria: tuple[Criterion, ...]
    criteria_digest: str
    created_at: str
~~~

构造/restore 约束：

- `screening_profile_id` 是本实现生成的 opaque string，精确匹配 `sp_[0-9a-f]{32}`，生成方式为 `sp_` + `uuid4().hex`；
- `profile_version` 是大于 0 的非 bool integer；
- `criteria` 至少一项，criterion_id 在该 Version 内唯一；
- `criteria_digest` 必须等于本 Version criteria 的重新计算结果；
- `created_at` 是 timezone-aware ISO 8601 string；
- object frozen，不提供 mutation method。

`ScreeningProfileVersion.to_dict()` / `ScreeningProfileVersion.from_dict()` 只接受并输出本节五个 formal fields，并递归使用 Criterion serialization。Draft 不提供 serialization API。

### 7.4 ScreeningProfileDraft

~~~python
@dataclass
class ScreeningProfileDraft:
    screening_profile_id: str
    base_profile_version: int | None
    criteria: list[Criterion]
~~~

Draft 只存在于当前进程的 Configuration Mode：

- new Profile 的 `base_profile_version=None`；
- existing Profile 的 base 必须是创建 Draft 时的 latest formal version；
- Draft 可以为空、可以编辑，不带 criteria_digest/created_at；
- Draft 不序列化、不进入 RunManifest、不写 Candidate；
- 成功 Save 后 CLI 丢弃该 Draft object；
- R05 不保存 Draft allocation history。

### 7.5 Error surface

只增加两个 R05-specific base errors：

~~~python
class ScreeningProfileValidationError(ValueError): ...
class ScreeningProfileIOError(RuntimeError): ...
~~~

找不到 Profile/Version 使用 `ScreeningProfileValidationError` 的明确消息；底层 OSError 只包装为 `ScreeningProfileIOError`。不建立通用 error framework。

## 8. Criterion ID Allocation

### 8.1 Public operations

~~~python
ScreeningProfileStore.next_criterion_id(draft) -> str
ScreeningProfileStore.add_criterion(draft, criterion_text) -> Criterion
ScreeningProfileStore.edit_criterion(draft, criterion_id, criterion_text) -> Criterion
ScreeningProfileStore.delete_criterion(draft, criterion_id) -> None
~~~

### 8.2 Deterministic next-ID algorithm

对给定 `screening_profile_id`：

1. 读取所有正式 Version；
2. 收集正式历史中出现过的所有 criterion_id 数值；
3. 收集当前 Draft 中仍存在的所有 criterion_id 数值；
4. 合并两组数值；
5. 若为空，next number = 1；否则 next number = max + 1；
6. 输出 `f"C{number:03d}"`。

该算法自然满足：

- C001 起；
- C999 后为 C1000；
- 已进入正式历史、后来删除的 ID 仍被历史扫描看见，永不复用；
- 当前 Draft 内不重复；
- 纯 Draft ID 删除后不在正式历史或当前 Draft 中，允许再次生成；
- 不需要 allocation ledger、tombstone 或 Draft durability。

编辑 Criterion 使用 `dataclasses.replace()` 或等价 frozen-object replacement 保留原 criterion_id。删除只从 Draft list 移除。

## 9. criteria_digest Technical Contract

### 9.1 Dedicated helper

~~~python
def criteria_digest(criteria: Sequence[Criterion]) -> str:
    ...
~~~

该 helper 只服务 R05；不得复用或扩展 OCR config digest framework。

### 9.2 Canonical representation

canonical value 是 Criterion object array，每项只包含：

~~~json
{
  "criterion_id": "C001",
  "criterion_text": "具有 SLG 游戏项目经验",
  "rule": "must_match"
}
~~~

冻结规则：

- Criterion ordering：按 criterion_id 的十进制数值升序；
- JSON key ordering：`sort_keys=True`；
- separators：`(",", ":")`；
- Unicode：`ensure_ascii=False`，不做 Unicode normalization；
- whitespace：保留 criterion_text 原始 code points，不 trim、不折叠；
- number/NaN：canonical input 没有 float，仍使用 `allow_nan=False`；
- encoding：UTF-8；
- hash：`hashlib.sha256(canonical_bytes).hexdigest()`；
- output：`sha256:` + 64 位 lowercase hex。

等价伪代码：

~~~python
canonical = [
    {
        "criterion_id": item.criterion_id,
        "criterion_text": item.criterion_text,
        "rule": item.rule,
    }
    for item in sorted(criteria, key=numeric_criterion_id)
]
payload = json.dumps(
    canonical,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
digest = "sha256:" + hashlib.sha256(payload).hexdigest()
~~~

`screening_profile_id`、`profile_version`、`created_at`、storage path 和 Draft history 不进入 digest。

展示顺序可以保存在 Version 的 criteria tuple 中，但 canonical digest 按 numeric criterion_id 排序；单纯调整展示顺序不会改变 digest。no-op Save 使用完整 criteria tuple 相等判断，因此真正的顺序调整仍可形成下一 Version，而完全相同的 Draft 不形成 Version。

## 10. ScreeningProfile Persistence

### 10.1 Directory and file shape

默认布局冻结为：

~~~text
data/screening_profiles/
└─ <screening_profile_id>/
   └─ versions/
      ├─ 1.json
      ├─ 2.json
      └─ 3.json
~~~

不写 `latest.json`、index、active/default pointer、Draft file、ledger 或 tombstone。latest 由合法 Version filename 的最大整数确定。

### 10.2 Formal Version JSON

每个 Version file 精确保存：

~~~json
{
  "screening_profile_id": "sp_...",
  "profile_version": 1,
  "criteria": [
    {
      "criterion_id": "C001",
      "criterion_text": "具有 SLG 游戏项目经验",
      "rule": "must_match"
    }
  ],
  "criteria_digest": "sha256:...",
  "created_at": "2026-08-18T12:00:00+08:00"
}
~~~

文件使用 UTF-8、`ensure_ascii=False`、`indent=2` 和末尾 newline。该 pretty serialization 不作为 digest input。

### 10.3 Store API

~~~python
class ScreeningProfileStore:
    def __init__(self, root: Path = DEFAULT_SCREENING_PROFILE_ROOT) -> None: ...
    def list_profile_ids(self) -> tuple[str, ...]: ...
    def list_versions(self, screening_profile_id: str) -> tuple[int, ...]: ...
    def load_version(self, screening_profile_id: str, profile_version: int) -> ScreeningProfileVersion: ...
    def load_latest(self, screening_profile_id: str) -> ScreeningProfileVersion: ...
    def create_draft(self) -> ScreeningProfileDraft: ...
    def create_draft_from_latest(self, screening_profile_id: str) -> ScreeningProfileDraft: ...
    def next_criterion_id(self, draft: ScreeningProfileDraft) -> str: ...
    def add_criterion(self, draft: ScreeningProfileDraft, criterion_text: str) -> Criterion: ...
    def edit_criterion(self, draft: ScreeningProfileDraft, criterion_id: str, criterion_text: str) -> Criterion: ...
    def delete_criterion(self, draft: ScreeningProfileDraft, criterion_id: str) -> None: ...
    def save_draft(self, draft: ScreeningProfileDraft) -> ScreeningProfileVersion | None: ...
~~~

`load_version()` 是历史只读定位入口；只有 `create_draft_from_latest()` 能建立 existing Profile Draft，且它不接受 `profile_version` 参数。这从 API 形态上禁止 history branch selector。

### 10.4 Load and history validation

每次 load：

- JSON 必须是 object；
- keys 必须对应 formal Version shape；
- path id/version 必须与内容一致；
- Criterion 与 timestamp 必须合法；
- stored digest 必须重新计算一致；
- `list_versions()` 按整数排序，并要求从 1 连续到 max。

这是 Profile domain 自身的读取合同，不扩展为通用 integrity scanner。

### 10.5 Existing Profile latest-only Draft

`create_draft_from_latest(profile_id)`：

1. 调用 `load_latest(profile_id)`；
2. 复制 latest criteria 为 mutable Draft list；
3. 写入 `base_profile_version=latest.profile_version`；
4. 不提供从任意历史 Version 创建 Draft 的 public path。

`save_draft()` 在写入前重新读取 latest，并要求：

~~~text
draft.base_profile_version == current latest.profile_version
~~~

不相等时拒绝 Save，既有历史不变。该检查只落实 Frozen latest-edit contract，不是 concurrent editing framework。

### 10.6 Save algorithm

New Profile：

1. Draft base 必须为 None；
2. 该 profile_id 不得已有正式 Version；
3. 验证非空 criteria；
4. target version = 1。

Existing Profile：

1. load current latest；
2. Draft base 必须等于 current latest；
3. 若 Draft criteria tuple 与 latest criteria tuple 完全相同，返回 `None`，不写文件；
4. 否则 target version = latest + 1。

共同写入步骤：

1. 构造完整 frozen Version；
2. 计算 digest，并以 `datetime.now().astimezone().isoformat()` 生成 timezone-aware `created_at`；
3. 在 target Version 目录创建 same-directory temporary file；
4. 写完整 JSON 并关闭；
5. 确认 target Version file 尚不存在；
6. 使用 `os.replace()` 将 temporary file 放到 target path；
7. 返回保存的 Version。

R05 v1 明确不支持 concurrent Draft；因此不增加 file lock 或 compare-and-swap framework。target 预存在、write 或 replace 失败时清理 temporary file，抛出 `ScreeningProfileIOError`，不删除、不覆盖任何既有 Version。

## 11. RunManifest Profile Binding

### 11.1 Binding object

在 `ocr_records.py` 增加：

~~~python
@dataclass(frozen=True)
class ScreeningProfileBinding(JsonRecordMixin):
    screening_profile_id: str
    profile_version: int
    criteria_digest: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScreeningProfileBinding": ...
~~~

验证：

- id 精确匹配本实现的 `sp_[0-9a-f]{32}`；
- version 是大于 0 的 non-bool int；
- digest 匹配 `sha256:[0-9a-f]{64}`。

`RunManifest` 增加唯一字段：

~~~python
screening_profile_binding: Optional[ScreeningProfileBinding] = None
~~~

这里的 Optional 只服务 legacy run 与 technical unbound Store 的 backward compatibility。每一个新的 production R05 Run 都必须提供非 None binding；Optional 不表示 production R05 Run 可以无 Profile 启动。

新 bound `run.json` shape：

~~~json
{
  "run_id": "...",
  "status": "running",
  "screening_profile_binding": {
    "screening_profile_id": "sp_...",
    "profile_version": 3,
    "criteria_digest": "sha256:..."
  }
}
~~~

### 11.2 Serialization and legacy behavior

`RunManifest.from_dict()`：

- key 缺失时保留 `None`；
- value 为 object 时调用 `ScreeningProfileBinding.from_dict()`；
- value 非 object 或字段非法时拒绝该 manifest；
- 不 backfill、不猜测 Profile。

`RunManifest.__post_init__()` 只接受 None 或有效 frozen binding。

本 Change 不提升 OCR `STORAGE_SCHEMA_VERSION`：binding 是仅限 RunManifest 的 additive optional metadata，Candidate/Screen/Error schema 均不变化；旧 versioned records 仍由当前兼容表读取。binding presence 本身区分 bound 与 legacy unbound run。

如果实施中证明确实必须提升全局 OCR schema 才能读取 additive field，必须停止该合同点并交回 Human，不得连带迁移 Candidate/OCR schemas。

### 11.3 Frozen Snapshot decision

TID 选择 RPD 允许的方案 A：

> Run metadata 只保存 binding tuple，不保存完整 Profile Snapshot。

理由：

- 正式 Profile Version 已独立持久化且不可删除；
- id + version 可以唯一定位；
- digest 可以验证内容；
- 三元组已满足 RPD 最低 traceability；
- 避免在 Run metadata 重复完整 criteria。

## 12. JsonlOcrRecordStore Integration

`JsonlOcrRecordStore.__init__()` 增加可选 keyword-only 参数：

~~~python
screening_profile_binding: Optional[ScreeningProfileBinding] = None
~~~

它只把 binding 传给 `RunManifest`。不改变：

- Run directory naming；
- screens/candidates/errors filenames；
- screen/candidate validation；
- append behavior；
- failure counters；
- close/finalize behavior。

参数保持 Optional，使现有 offline OCR benchmark/store unit tests 可以建立 unbound technical Store；production `simple_brush.run()` 则必须传入非 None binding。

因此字段层与 Store constructor 层允许 None，production startup contract 不允许 None。

## 13. Configuration Mode CLI

### 13.1 Public entry

`screening_profile_cli.py` 提供：

~~~python
def run_screening_profile_configuration(
    store: ScreeningProfileStore | None = None,
) -> str | None:
    ...
~~~

返回值是为下一 Run 准备的 `screening_profile_id`；没有显式 Prepare 时返回 None。它不持久化 active/default/current selection。

### 13.2 Minimal menu

Configuration CLI 只提供：

1. List Profile IDs and latest version numbers；
2. Create new Profile Draft；
3. Edit existing Profile by ID（始终 `create_draft_from_latest()`）；
4. Add Criterion；
5. Edit criterion_text；
6. Delete Criterion；
7. Show current Draft；
8. Human Save；
9. Prepare Profile by ID for next Run（始终 load latest）；
0. Return。

CLI 不提供历史 Version 浏览/选择、branch、rollback、restore、fork、merge、Profile delete、Draft persistence 或 GUI。

### 13.3 CLI state

- 一个 invocation 最多持有一个 in-memory Draft；
- 切换到另一 Profile 前必须丢弃当前未保存 Draft或继续当前 Draft；不增加 concurrent Draft list；
- Save 返回 Version 时显示 id/version/digest；
- no-op Save 显示“没有内容变化，未创建新 Version”；
- invalid input 或 store error 留在 Configuration Mode，不启动 Run；
- Prepare 只返回 id；真正的 latest load/digest validation 在 Run Start 再执行一次。

## 14. Startup and Run Freeze Ordering

### 14.1 Startup menu integration

`simple_brush.choose_startup_action()` 增加一个 `ScreeningProfile Configuration` 入口。`main()` 维护仅当前进程有效的：

~~~python
prepared_screening_profile_id: Optional[str]
~~~

行为：

- Profile CLI 显式 Prepare 后替换该值；
- Human 选择 Start Run 但没有 prepared id 时，显示明确提示并返回 startup menu；
- Start Run 调用 `run(screening_profile_id=prepared_id)`；
- AI Provider 与 calibration menu 保持原行为。

### 14.2 Noninteractive startup

`parse_args()` 增加：

~~~text
--screening-profile-id <id>
~~~

`--auto`、`--keywords` 或 `--calibration-profile` 触发 noninteractive Run 时必须同时提供该 id。没有 id、Profile 不存在、latest 不可读或 digest mismatch 时，按照现有 startup/noninteractive failure semantics 返回失败；R05 不冻结具体 numeric exit code。

硬性结果是：不初始化 OCR、不启动 keyboard listener、不 foreground browser、不进入 Candidate loop，也不创建错误的 R05-bound execution。

不增加 `--screening-profile-version`，因此 noninteractive path 也不形成历史 Version selector。

### 14.3 Required production ordering

`run(screening_profile_id)` 的冻结顺序：

~~~text
1. Complete existing non-execution input collection
2. ScreeningProfileStore.load_latest(profile_id)
3. Recompute/verify stored criteria_digest
4. Build immutable ScreeningProfileBinding
5. create_ocr_record_store(binding)
6. JsonlOcrRecordStore writes initial run.json with binding
7. Require returned Store.enabled is True
8. initialize_ocr() when needed
9. start keyboard listener
10. foreground browser
11. candidate processing
~~~

Steps 2–7 complete before Browser automation、OCR 或 Candidate processing。

### 14.4 Initialization failure behavior

`create_ocr_record_store()` 接收 binding 并传入 `JsonlOcrRecordStore`。

`initialize_run_ocr_storage(binding)` 仍可捕获 constructor exception 并记录 fixed diagnostic，但 production `run()` 必须检查返回对象且 `enabled=True`。下列任一结果按照现有 startup failure semantics 返回失败，TID 不指定 numeric exit code：

- Profile missing/unreadable；
- formal Version invalid；
- digest mismatch；
- Store constructor exception；
- initial manifest persistence leaves Store disabled。

此时不得调用 `initialize_ocr()`、listener、foreground/browser 或 Candidate loop。无需增加独立 Gate class；这是既有 startup function 的必要 precondition。

Run 已成功开始后的 OCR append/close failure 继续使用现有 best-effort semantics，不由 R05 扩大。

## 15. Configuration and Execution Separation

### 15.1 Configuration Mode

只存在于 `main()` startup menu 和 `screening_profile_cli.py`。Profile Create/Edit/Save/Prepare 在调用 `run()` 前完成。

### 15.2 Execution Mode

`run()`、Candidate loop、keyboard handler 和 OCR flow 不调用 `run_screening_profile_configuration()`，也不提供 View/Edit/Save/Switch/Create Version 入口。

Pause 仍是同一 `run()` 内的 `paused` 状态；不会返回 startup menu，因此不能配置 Profile。

### 15.3 Terminally Stopped mapping

R05 不增加 status。当前最小映射为：

| Current fact | R05 interpretation | Profile behavior |
|---|---|---|
| `RunStatus.RUNNING`, `paused=False` | Active | 不允许配置 |
| `RunStatus.RUNNING`, `paused=True` | Paused / resumable in-process | 不允许配置，binding 不变 |
| `RunStatus.COMPLETED` after close | Terminally Stopped | 下一次 startup 可配置 |
| `RunStatus.ERROR` after close | Terminally Stopped | 下一次 startup 可配置 |
| `candidate_switch_failed` → ERROR | Terminally Stopped | 下一次 startup 可配置 |
| Human ESC / duration → INTERRUPTED after close | 当前实现无 resume 入口，属于 terminal result | 下一次 startup 可配置 |
| `RunStatus.DISABLED` during initial Store creation | Execution 未开始 | 不形成 R05-bound Run；下一次 startup 可配置 |

意外进程 crash 无法执行 `close()`，R05 不回写、不重绑、不修改该历史 Run 的 frozen binding。当前仓库没有任何 crash-resume 入口，因此该进程内 Execution lifecycle 不可继续；后续启动只能创建全新的 Run 和 binding。若未来 Requirement 把该类 Run 定义为 resumable，则必须在恢复原 binding 与允许 Profile 配置之间作出明确生命周期决定；本 Change 不预先实现 persisted lock 或 resume subsystem。

未来若新增真正 resume path，`INTERRUPTED` 是否 resumable 必须由该 Requirement 定义；R05 只要求 resume 使用原 run_id 与原 binding。本 Change 不创建 resume subsystem。

## 16. Candidate Schema Boundary

`CandidateOcrDocument`、`candidates.jsonl` 与 Candidate metadata 不增加：

- screening_profile_id；
- profile_version；
- criteria_digest；
- Criterion；
- criterion_text；
- Criterion Boolean/result；
- Profile Snapshot。

唯一对齐路径保持：

~~~text
CandidateOcrDocument.run_id
→ RunManifest.screening_profile_binding
→ ScreeningProfileStore.load_version(id, version)
~~~

未来 consumer 读取正式 Version 后必须比较 stored digest 与 binding digest；R05 本身不创建 Evaluation consumer。

## 17. Failure Semantics

| Failure | Required result |
|---|---|
| Empty Draft Save | 不写 Version；保留 Draft |
| Invalid text/rule/ID | 不写 Version；明确 Validation error |
| Existing Draft base 不是 current latest | 不写 Version；不建立 branch |
| No-op Save | 返回 None；不增加 version |
| Target Version 已存在 | 不覆盖；报 IO/domain error |
| Temporary write/replace failure | 清理 temporary file；既有历史不变 |
| Stored Profile JSON invalid | 不用于 Draft/Run；不静默修复 |
| Stored digest mismatch | 不用于新 Run；不改写历史 |
| Missing prepared Profile | 不进入 Execution |
| Initial bound run.json persistence failure | 不进入 Execution |
| Legacy run missing binding | 正常读取为 unbound；不 backfill |
| Candidate/OCR later append failure | 保持既有 best-effort behavior |

错误消息不得包含 Candidate OCR 文本；R05 Profile criterion_text 是 Human-authored config content，只显示在 Configuration Mode 的明确 Draft/Profile view 中。

## 18. Dependency and Packaging Changes

Dependency Changes: None.

实现只使用：

- `dataclasses`；
- `datetime`；
- `hashlib`；
- `json`；
- `os`；
- `pathlib`；
- `re`；
- `tempfile`；
- `uuid`；
- `typing`。

不修改 requirements 或 PyInstaller spec。实现阶段只做 targeted import/compile verification，不执行 release/package。

## 19. Targeted Test Plan

### 19.1 `tests/test_screening_profile.py` — new

用一个 `TemporaryDirectory` 覆盖 default root，集中覆盖：

1. Criterion/Profile serialization round-trip；
2. invalid empty text 与 non-must_match rejection；
3. C001 与 C1000 formatting；
4. current Draft uniqueness；
5. ID stability after text edit；
6. deleted formal ID not reused；
7. abandoned Draft-only ID reuse；
8. new Draft Save → v1；
9. latest v1 Draft Save → v2；
10. historical v1 cannot become edit base after v2；
11. immutable formal dataclasses；
12. no-op Save returns None；
13. deterministic digest across input ordering；
14. text/add/delete changes digest；固定 expected-digest fixture 证明 canonical payload 包含 `rule=must_match`；
15. exact whitespace/Unicode behavior；
16. restart/reload, id+version lookup and latest discovery；
17. atomic write failure leaves previous history unchanged；
18. missing/gapped/invalid history rejection。

相邻断言合并在同一 lifecycle test 中，不为每个 bullet 建立重复 fixture。

### 19.2 `tests/test_screening_profile_cli.py` — new

覆盖：

- Create/Edit/Add/Delete/Save/Prepare 最小交互；
- edit existing always calls latest Draft API；
- no historical version prompt/branch path；
- no-op Save message；
- invalid/store failure stays in Configuration Mode；
- Configuration operations do not call LLM Runtime、favorite、forward 或 Candidate functions。

### 19.3 `tests/test_ocr_records.py` — modified

覆盖：

- `ScreeningProfileBinding` validation and JSON round-trip；
- bound RunManifest round-trip；
- missing binding restores as None；
- invalid partial binding is rejected；
- `CandidateOcrDocument.to_dict()` remains free of Profile fields。

### 19.4 `tests/test_ocr_store.py` — modified

覆盖：

- constructor binding is present in the first `run.json`；
- close preserves exactly the same binding；
- unbound technical Store remains supported；
- existing disabled Store unit behavior remains unchanged。

### 19.5 `tests/test_ocr_replay.py` — modified

覆盖：

- current bound manifest read；
- existing legacy fixture/read path returns `binding=None`；
- replay does not mutate or backfill source run.json。

`ocr_replay.py` production source remains unchanged。

### 19.6 `tests/test_ocr_stage0_integration.py` — modified

覆盖：

- enabled bound Store keeps current Candidate flow；
- disabled initial Store stops before listener/browser/view；
- later append failures retain existing best-effort behavior；
- completed/error/interrupted close keeps frozen binding；
- paused path remains inside same Run and does not invoke Profile CLI。

现有“enabled and disabled both keep view count”断言按 Frozen RPD 定向替换，不修改其它 Candidate/OCR assertions。

### 19.7 `tests/test_simple_brush_ocr.py` — modified

覆盖：

- startup menu Profile Configuration dispatch；
- Start without prepared id returns to menu and does not call run；
- prepared id is passed to `run()`；
- noninteractive start requires `--screening-profile-id`；
- missing/invalid Profile and digest mismatch stop before OCR/browser；
- ordering: binding persistence precedes OCR/listener/browser；
- startup failure assertions 不依赖 R05-specific numeric exit code；
- Execution path does not call Profile Configuration；
- terminal return allows a new `main()` invocation to expose Configuration；
- existing AI Provider and calibration menu behavior remains unchanged。

### 19.8 Targeted verification commands

Implementation Change 验证命令冻结为：

~~~powershell
git check-ignore -v --no-index data/screening_profiles/sp_00000000000000000000000000000000/versions/1.json
.\venv\Scripts\python.exe -m unittest tests.test_screening_profile tests.test_screening_profile_cli -v
.\venv\Scripts\python.exe -m unittest tests.test_ocr_records tests.test_ocr_store tests.test_ocr_replay -v
.\venv\Scripts\python.exe -m unittest tests.test_ocr_stage0_integration tests.test_simple_brush_ocr -v
.\venv\Scripts\python.exe -m compileall screening_profile.py screening_profile_cli.py ocr_records.py ocr_store.py simple_brush.py
~~~

本 TID 不要求 R04/R05/R06 benchmark、network smoke、完整 regression、build、package 或 release。

## 20. Change Plan

### Change 1 — Profile domain, digest, and formal history

Files：

- new `screening_profile.py`；
- modify `.gitignore`，只增加 `/data/screening_profiles/`；
- new `tests/test_screening_profile.py`。

Implementation：

- frozen Criterion / formal Version；
- in-memory Draft；
- latest-only edit API；
- deterministic Criterion IDs；
- frozen digest；
- `data/screening_profiles/` formal history；
- runtime Profile root ignored by Git；
- atomic no-overwrite Save。

Preconditions：RPD v0.2 remains Frozen；root path tests use temporary directory。

### Change 2 — Configuration Mode CLI

Files：

- new `screening_profile_cli.py`；
- new `tests/test_screening_profile_cli.py`。

Implementation：只实现 Create/Edit latest/Add/Edit/Delete/Save/Prepare/Return；无 historical selector 或 state machine。

Preconditions：Change 1 APIs and errors stable。

### Change 3 — RunManifest binding and Store persistence

Files：

- modify `ocr_records.py`；
- modify `ocr_store.py`；
- modify `tests/test_ocr_records.py`；
- modify `tests/test_ocr_store.py`；
- modify `tests/test_ocr_replay.py`。

Implementation：additive optional binding、legacy None restore、constructor wiring、first/close manifest verification；不改 Candidate schema 或 replay source。

Preconditions：Change 1 digest output contract frozen。

### Change 4 — Startup freeze and lifecycle integration

Files：

- modify `simple_brush.py`；
- modify `tests/test_ocr_stage0_integration.py`；
- modify `tests/test_simple_brush_ocr.py`。

Implementation：Profile menu、process-local prepared id、noninteractive id、load-latest/freeze ordering、disabled initial Store blocks before Execution、terminal mapping。

Preconditions：Changes 1–3 accepted；不得修改 Candidate scan/switch/action bodies。

## 21. File Scope Matrix

### 21.1 New Files planned

| File | Purpose |
|---|---|
| `screening_profile.py` | R05 models、Draft operations、digest、formal Version Store |
| `screening_profile_cli.py` | Configuration-only local CLI |
| `tests/test_screening_profile.py` | Domain/persistence/lifecycle targeted tests |
| `tests/test_screening_profile_cli.py` | CLI boundary targeted tests |

### 21.2 Modified Files planned

| File | Allowed modification |
|---|---|
| `.gitignore` | Add only `/data/screening_profiles/` for local Profile runtime data |
| `ocr_records.py` | Add frozen binding and one Optional RunManifest field/restore path |
| `ocr_store.py` | Accept binding and include it in initial RunManifest |
| `simple_brush.py` | Startup menu、prepared id、required freeze ordering only |
| `tests/test_ocr_records.py` | Binding/legacy/Candidate-isolation assertions |
| `tests/test_ocr_store.py` | Bound manifest persistence assertions |
| `tests/test_ocr_replay.py` | Bound and legacy-unbound read assertions |
| `tests/test_ocr_stage0_integration.py` | R05-bound startup ordering and one superseded disabled-store assertion |
| `tests/test_simple_brush_ocr.py` | Profile startup/CLI dispatch and Execution separation assertions |

### 21.3 Protected / Untouched Files

以下 production files 必须 untouched：

- `ocr_detector.py`；
- `ocr_candidate.py`；
- `ocr_replay.py`；
- `ocr_normalization.py`；
- `ocr_aggregation.py`；
- `ocr_similarity.py`；
- `ocr_text.py`；
- `mouse_motion.py`；
- `ai_provider_config.py`；
- `ai_provider_cli.py`；
- `llm_provider_runtime.py`；
- R04 benchmark tools/files；
- requirements 与 PyInstaller spec。

`.gitignore` 不属于 untouched scope；但除新增 `/data/screening_profiles/` 外，其它 ignore rules 必须保持原样。

在 `simple_brush.py` 中以下逻辑也必须 untouched：

- OCR engine/detection；
- Candidate builder/scan；
- candidate switch；
- favorite/forward；
- mouse movement；
- threshold、scroll、retry、timing；
- existing stop_reason production logic。

## 22. Acceptance Mapping AC-01–AC-20

| RPD AC | Implementation component | Verification |
|---|---|---|
| AC-01 Formal Profile model | `Criterion`、`ScreeningProfileVersion`、Store Save | `test_screening_profile`: v1 save/round-trip |
| AC-02 Criterion model | Frozen three-field Criterion | field/rule/text validation tests |
| AC-03 Boolean semantics | Natural-language text stored verbatim；no evaluator | exact model-shape tests；no evaluation API |
| AC-04 No expression language | No extra fields/rule engine | constructor and serialization key assertions |
| AC-05 Criterion ID allocation | history + current Draft max algorithm | C001、stability、deleted formal、abandoned Draft tests |
| AC-06 Profile identity and versions | UUID-backed id、latest + 1 Save | new v1 and v1→v2 tests |
| AC-07 Draft lifecycle | in-memory Draft APIs only | edit without file；unsaved Draft not bindable |
| AC-08 Immutability/edit base | frozen Version、`create_draft_from_latest()`、base recheck | frozen mutation and historical branch rejection tests |
| AC-09 Digest contract | dedicated canonical SHA-256 helper | determinism/scope/change/ordering tests |
| AC-10 Persistence outcome | per-Version files + atomic replace；local root covered by `/data/screening_profiles/` ignore rule | reload、injected Save failure and targeted `git check-ignore` verification |
| AC-11 Valid formal binding | prepare id then load latest at Run Start；mandatory for every production R05 Run | CLI prepare and startup load/digest tests |
| AC-12 Run freeze | Optional field for legacy/unbound compatibility；mandatory nested binding written for production R05 Run | records/store/order tests |
| AC-13 One Run, one Profile | frozen binding created once；no Execution mutation | close preserves binding；run has no switch path |
| AC-14 Snapshot placement | TID chooses tuple-only, no full snapshot | run.json exact binding and Candidate key assertions |
| AC-15 Candidate schema isolation | no Candidate code/schema changes | Candidate serialization lacks Profile fields |
| AC-16 Mode separation | Profile CLI only in startup main | startup dispatch and Execution non-call tests |
| AC-17 Terminal stop/resume semantics | existing status/paused mapping, no resume subsystem | pause/terminal/new-main tests |
| AC-18 Failure behavior | validation/no-op/atomic Save/startup refusal | invalid Draft、digest、missing Version、disabled Store tests |
| AC-19 Compatibility | Optional binding default None | legacy run reader test；no source mutation |
| AC-20 Scope isolation | no LLM/evaluation/action dependency in R05 modules | mocked no-call tests and protected-file diff scope |

所有 AC-01–AC-20 均有 implementation component 与 targeted verification；不增加新的 Acceptance Criterion。

## 23. Explicit Non-Implementation

本 TID 明确不实现：

- Rule Engine V2；
- Criterion Evaluation；
- LLM Prompt 或 AI screening；
- Candidate Decision；
- favorite / forward behavior change；
- Candidate-specific Profile；
- scoring、weight、priority；
- AND/OR、N-of-M、must_not_match；
- historical Version branch selector；
- rollback、restore、fork 或 merge；
- Active/Default/Published/Archived Profile state；
- Profile state machine；
- Draft persistence/allocation ledger/tombstone；
- database、ORM 或 migration framework；
- GUI；
- generic resume subsystem；
- full Run Profile Snapshot；
- R04 benchmark change；
- OCR/Candidate algorithm change；
- release/package。

## 24. Risks and Escalation Conditions

Implementation must stop only at the affected contract point and report Human if：

1. additive optional RunManifest binding cannot preserve legacy run loading without a global OCR/Candidate schema migration；
2. latest-only Draft/save contract cannot be implemented without adding branch/default/active state；
3. initial bound manifest cannot be made mandatory without modifying Candidate/OCR algorithms or action logic；
4. current code contains a real resume path that would treat a closed `INTERRUPTED` Run as resumable while discarding its original binding；
5. atomic formal Version Save cannot preserve old history using the existing local filesystem pattern；
6. an approved frozen upstream contract requires new R05 Runs to remain unbound。

普通 invalid input、missing Profile、I/O failure 或 existing targeted test migration 不属于需要扩大架构的理由。

## 25. Open Issues / Contract Conflicts

### 25.1 Open Issues

None.

### 25.2 Contract Conflicts

None.

旧 disabled-Store integration assertion 与 R05 启动合同的差异已经由 Frozen RPD 明确裁决：只迁移 production R05 Run 的初始 persistence assertion，保留 Store 自身和 Run 开始后的 best-effort OCR semantics，因此没有剩余冲突。

## 26. Implementation Handoff

本 TID 当前为 Version 0.1、Frozen for Implementation，可以直接交给 Terra/Codex Implementation。

Implementation 必须严格按本 TID 的 Change 顺序和文件范围执行；本次文档修订不包含任何产品代码或测试代码实施。
