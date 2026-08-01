# R04 OCR 文本标准化与原始证据保留 Acceptance Report

## 1. 报告信息与分层结论

| 项目 | 结果 |
|---|---|
| 验收范围 | R04 pure implementation、automated integration、性能、隐私和 Change 5A `legacy_shadow` 静态/自动化边界 |
| 分支 / HEAD | `main` / `54ae0648ccf9c7066d363bd986dfc9b16671af44` |
| 自动化环境 | Windows，仓库本地 `venv`，Python unittest；无真实 BOSS 页面操作 |
| pure implementation | **passed** |
| automated integration | **passed** |
| shadow deployment | **未执行，不放行** |
| Change 5B enforce | **未批准、未实现、不得进入** |
| formal production | **不放行** |

本报告关闭修复 Change A—D 以及提交前 readable normalization 合同/测试日志隔离收尾所覆盖的纯实现、自动化、性能和未来普通日志隐私阻塞。它不把自动化全绿解释成真实 shadow、enforce 或生产批准。首次阻塞状态另见 `docs/R04-change7-blocking-audit-report.md`。

## 2. 实际实现文件与核心接口

### 2.1 生产文件

| 文件 | R04 职责 |
|---|---|
| `ocr_normalization.py` | immutable bbox adapter、阅读顺序、文本标准化、comparison text、exact text + geometry 同屏重复框、配置快照/digest |
| `ocr_detector.py` | accepted OCR evidence 适配；每 observation 一次 normalizer；R03 指纹；legacy/R04 shadow 双计算 |
| `ocr_text.py` | legacy 关键词字符合同与 comparison helper 对齐，不改变规则 parser/matcher 业务语义 |
| `ocr_records.py` | storage 1.0/1.1、三态、screen/candidate/manifest schema、trace、summary |
| `ocr_candidate.py` | 创建 `OcrScreenRecord`、投影 normalization/shadow、candidate finalize |
| `ocr_store.py` | JSONL writer、manifest 历史配置、screen/manifest identity 拒写、脱敏错误 |
| `ocr_replay.py` | strict/tolerant reader 和显式 `replay_screen_normalization()` |
| `simple_brush.py` | 单点在线接入、Store 装配、固定 `legacy_shadow`、未来普通日志脱敏、显式且可注入的文件日志装配/关闭边界 |

### 2.2 自动化与验收辅助文件

R04 覆盖 `tests/test_ocr_normalization.py`、`test_ocr_records.py`、`test_ocr_candidate.py`、`test_ocr_detector.py`、`test_ocr_text.py`、`test_ocr_store.py`、`test_ocr_replay.py`、`test_ocr_stage0_integration.py` 和 `test_simple_brush_ocr.py`。冻结性能矩阵由 `tests/benchmark_r04_normalization.py` 重复执行。

## 3. 算法、配置和存储版本

| 身份 | 当前值 |
|---|---|
| R03 fingerprint | `r03-v1` |
| R04 normalization | `r04-v1` |
| R04 config | `r04-config-v1` |
| canonical config digest | `3597727e595b16c3aba7bfa41653b617f11277e78ce52379c99ee3afafcb84d5` |
| 当前 storage schema | `1.1.0` |
| legacy storage schema | `1.0.0` |
| rule mode | `legacy_shadow` |

完整当前配置：

| 配置 | 值 |
|---|---:|
| `effective_min_confidence` | 0.85 |
| `unknown_confidence_policy` | `include` |
| `line_tolerance_height_ratio` | 0.45 |
| `line_tolerance_min_px` / `max_px` | 4.0 / 18.0 |
| `line_pair_height_ratio` | 0.50 |
| `same_line_vertical_overlap_ratio` | 0.50 |
| `compact_join_gap_height_ratio` | 0.25 |
| `symbol_join_gap_height_ratio` | 0.75 |
| `duplicate_candidate_margin_height_ratio` | 1.00 |
| confirm IoU / center / size | 0.85 / 0.20 / 0.90 |
| secondary IoU / size | 0.70 / 0.95 |
| gray IoU / center / size | 0.65 / 0.35 / 0.80 |

Digest 输入是完整 snapshot 的 UTF-8、排序 key、紧凑 JSON，不包含 digest 自身。删除 comparison path 的冗余自定义标点表以及本次删除 readable path 的越界全角 ASCII 映射后重新计算 digest，结果仍为 `3597727e595b16c3aba7bfa41653b617f11277e78ce52379c99ee3afafcb84d5`，因为 canonical config snapshot 没有变化。Readable 字符语义由 `normalization_version` 管理；本次是在 R04 首个正式提交和生产放行前纠正未放行实现，不存在两个已发布、被视为正式历史的不同 `r04-v1` JSONL（工作区也不存在 `data/ocr_runs/`），因此保留唯一当前 `r04-v1` / `r04-config-v1` 身份。Manifest 现在拒绝不完整、非法或 digest 不一致的 snapshot。

## 4. Schema 1.0/1.1 与三态

### 4.1 `not_attempted`

`processing_status=raw_only`；算法/config/mode 身份、派生文本、segments、错误和 R04 统计均为空。旧 `1.0.0` 缺少 R04 字段时映射到此视图，不伪造历史执行。

### 4.2 `completed`

`processing_status=normalized`；算法/config/digest/实际 threshold/mode 完整；`normalized_text` 和 `comparison_text` 必须是字符串，合法空结果为 `""`；segments、ordered/effective IDs、line mapping 和计数互相校验。

### 4.3 `failed`

`processing_status=raw_only`；保留 `raw_boxes/raw_text`；配置身份完整；派生文本和 segments 为空；只保存固定技术错误类型，不保存 exception message 或正文。

生产 schema 不存在 `partial`。静态扫描中仅有一个用来证明非法状态被拒绝的负向测试字符串，以及两个“不得写 partial JSONL line”的测试名称。

## 5. R03 不变证据

`ocr_detector.py::FINGERPRINT_VERSION` 仍为 `r03-v1`。数据流保持：

```text
confidence accepted OCR items
→ build_screen_fingerprint(accepted_items)
→ R03 normalized text
→ SHA-256 exact_hash
```

R04 `normalized_text`、`comparison_text`、segments、duplicate survivors 和 normalization status 均不进入 R03。自动化覆盖 completed、合法空、failed、not-attempted 以及 fingerprint builder failure；R01 的 formal/pre-switch/post-switch/confirmation 仍消费原 R03 exact hash。

## 6. Legacy shadow 与动作权威

`simple_brush.py::R04_RULE_EVALUATION_MODE` 固定为 `legacy_shadow`，detector 拒绝其他 mode。对规则 capture：

```text
legacy_result = matching_keyword_rule(observation.text, rules)
r04_result = matching_keyword_rule(comparison_text, rules)  # 仅 completed
production_result = legacy_result
```

结构化保存 `legacy_match`、`r04_match`、`comparison_outcome`、`legacy_rule_index`、`r04_rule_index`；不保存规则原文、命中关键词或正文。非规则 capture 的 shadow scalar/index 全为 null。`r04_only` 不触发 confirmation/action，`legacy_only` 和 normalization failure 保留旧 confirmation/action 预算。

本轮没有 `r04_enforce` CLI、GUI、配置或可启用代码路径。

## 7. Normalization 算法验收

- bbox 无损支持 LTRB 和任意一个或多个 point 的 polygon；全部坐标必须 finite；原 shape/value 不覆盖。
- 派生 bounds/center/width/height；不可用 geometry 导致整屏 `failed`，raw evidence 由上层保存。
- 有效框高 median 形成动态容差；line candidate 使用 `center_y <= tolerance` 或 `vertical overlap >= threshold`。
- 行上到下、行内左到右；平局使用 `original_index` 和稳定 geometry/box ID 规则。
- gap ratio 使用全屏 median height；CJK、ASCII、数字、单位、开闭标点和 symbol connector 按冻结顺序连接。
- `normalized_text` 来自视觉行和单框低风险处理：Unicode NFC → 删除框内首尾 Unicode whitespace → 将内部连续 Unicode whitespace 折叠为一个 ASCII space；保留英文大小写、全角字母/数字/标点及其余全部非 whitespace 字符，不执行兼容性宽度转换。全角空格只因其 Unicode whitespace 属性参与 trim/折叠。
- `comparison_text` 只从成功生成的 `normalized_text` 派生，固定顺序为 Unicode NFKC → Python `lower()` → 删除全部 Unicode whitespace。除此之外不执行额外标点替换或删除；NFKC 后的全部非空白字符均保留，包括 `+ # . / - _`、数字、UI 与业务文字。这里不使用 `casefold()`。
- UI、按钮、标题、内部导航全部保留；不纠错、不做语义实体识别、不建立 UI 黑名单。
- C++、C#、.NET、SLG+X、0-1、2D/3D、Unity 2022.3、UE5、iOS、3A、日期和版本号由保护测试覆盖。
- 相同 evidence/config 重复执行幂等，raw object、bbox、confidence、original index 不变。

## 8. 同屏重复框：exact text + geometry

文字证据固定为单框 `build_comparison_text()` 的非空 exact key；不存在 `SequenceMatcher` 或模糊文字删除。按 exact key 分桶、left sweep 生成局部候选，只把新框与实际 survivors 直接确认，不构造完整 pair matrix，不做传递闭包。

几何综合 IoU、横纵重叠、中心距离和尺寸相似。只有 exact text 与 confirm geometry 同时成立才抑制；灰区、远距同文、重叠异文、标题/正文同文和 A-B-C 非传递情况保留。survivor 优先级为 finite confidence、面积、original index、geometry key。raw boxes 永不删除。

## 9. 性能与确定性

命令：

```powershell
.\venv\Scripts\python.exe -m tests.benchmark_r04_normalization
```

计时与 `tracemalloc` 分开；普通场景预热 3 次、计时 25 次，重复场景计时 100 次。内存为单次 normalization 的 tracemalloc 增量，GC retained 在删除 result 并执行 `gc.collect()` 后测量。

| 场景 | median ms | p95 ms | candidates | confirmations | survivors | suppressed | gray | peak KiB | GC retained KiB | deterministic |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 unique | 0.0273 | 0.0465 | 0 | 0 | 0 | 0 | 0 | 7.70 | 0.23 | true |
| 1 unique | 0.0726 | 0.0850 | 0 | 0 | 1 | 0 | 0 | 10.57 | 0.23 | true |
| 8 unique | 0.2438 | 0.2703 | 0 | 0 | 8 | 0 | 0 | 21.46 | 0.23 | true |
| 100 unique | 2.5703 | 3.1110 | 0 | 0 | 100 | 0 | 0 | 185.93 | 0.23 | true |
| 500 unique | 15.2931 | 16.0280 | 0 | 0 | 500 | 0 | 0 | 888.64 | 0.26 | true |
| 500 far same-text | 11.4769 | 14.0956 | 0 | 0 | 500 | 0 | 0 | 900.96 | 0.26 | true |
| 500 dense same-position/text | 11.8500 | 13.1761 | 499 | 499 | 1 | 499 | 0 | 999.02 | 0.32 | true |
| 100 dense，重复 100 次 | 2.3168 | 3.2618 | 99 | 99 | 1 | 99 | 0 | 207.76 | 0.23 | true |

门槛结果：100 框 p95 `3.1110ms < 10ms`；500 框 p95 `16.0280ms < 50ms`，均通过。dense 500 只进行 499 次 survivor confirmation，没有退化到 124,750 pair materialization。

## 10. Store、JSONL 与 Replay

- Manifest 是 run-level 历史 config 唯一权威，保存完整 snapshot/digest/threshold/mode。
- completed/failed screen 保存五项 config identity；not-attempted 全为空。
- `save_screen()` 和 `save_candidate()` 在写盘前核对 screen/manifest identity；不一致拒写且不留下部分 JSONL line，业务主流程继续。
- `raw_boxes/raw_text/exact_hash/fingerprint_version` 保持原证据；新记录 round-trip 不丢字段。
- 新 1.1 replay 必须使用历史 manifest，或调用方提供与 screen digest 完全相符的显式 config；禁止当前默认值漂移。
- 旧 1.0 replay 默认 0.85 并标记 `legacy_stage0_assumption`，显式覆盖标记 `caller_override`。
- strict 对 config/status/bbox/version/schema 错误抛脱敏错误；tolerant 返回结构化 issue 和合法 failed/raw-only view或跳过坏行。
- replay 不写文件、不执行 OCR、不覆盖 exact hash、不修改 source。

## 11. Online/Offline 等价

同一 raw evidence、screen ID、历史 config 和算法版本，测试逐字段验证 status、normalized/comparison text、segment text/ID/source box IDs、ordered/effective/suppressed IDs、gray/eligible/low-confidence/empty 计数、config identity 和 threshold 一致。历史自定义阈值/config replay 不受当前默认值影响；source JSON、raw boxes、raw text 和 R03 hash 在 replay 后不变。

## 12. 隐私验收

### 12.1 未来普通日志

Change D 删除了以下直接输出：完整备选邮箱、自动填入邮箱/input box 内容、规则原文、命中关键词、OCR error message 和通用运行 exception message/traceback。替代字段只包括：

```text
email_provided=<true|false>
alternate_email_provided=<true|false>
email_source=<recent_contact|manual>
rule_count=<n>
matched=<true|false>
rule_index=<index|->
error_type=<class-or-fixed-code>
```

两个唯一邮箱 marker 测试分别覆盖 manual fallback 和 recent-contact 路径；完整邮箱、用户名和域名均不进入捕获日志。`type_text_human()` 仍精确收到原 fallback 邮箱，点击、发送和焦点恢复序列不变。独立规则 marker 证明规则原文和 matched keyword 不进入日志。

### 12.2 JSONL、error context 和自动化日志隔离

Raw JSONL 按产品合同保留 evidence；它不是普通日志，必须按运行数据隐私策略管理。shadow 只保存 scalar/enum/index。Store/replay error 测试证明正文、邮箱、手机号、坐标、confidence 和异常 message 不进入 error context/issue。

`simple_brush.py` import 不再创建目录、调用 `basicConfig()` 或安装默认文件 handler。只有生产 `__main__` 显式调用 `configure_file_logging(DEFAULT_LOG_PATH)`；相同绝对路径只安装一个 handler，退出时 `close_file_logging()` 从 root logger 移除并 flush/close。生产默认路径仍为 `logs/simple_brush.log`，格式仍为 `%(asctime)s [%(levelname)s] %(message)s`。

日志自动化全部使用无文件 handler 的 import 状态、logger mock 或显式 `TemporaryDirectory` handler；测试结束将临时 handler 移除并关闭，Windows 上临时目录可正常删除。日志相关自动化整体覆盖规则匹配、manual fallback、recent-contact、OCR/运行异常、favorite、forward 和 no-forward 既有路径；专项临时日志证明唯一邮箱、规则和 OCR 正文 marker 均不落盘，而真实邮箱仍精确传给业务输入。

整个本轮定向、Schema/Replay、OCR/动作、全量、benchmark、compileall 和静态核验前后，真实 `logs/simple_brush.log` 始终为 7,363,884 bytes，`mtime` UTC ticks 始终为 `639211620664710221`，SHA-256 始终为 `b03b57ef9ecbf50c5ba8bd85699afdb3e14dbe587dcb2aaa69f66e96bbf46b80`。不存在默认日志时的隔离测试也证明自动化不会创建该路径；当前方案不创建、追加、截断或删除真实运营日志。此前追加后再截除测试后缀是已关闭的历史问题，不是当前测试方法。维护者仍须另行决定既有历史日志的轮转、归档或删除，本轮不具备该授权。

Git 没有跟踪 `data/ocr_runs`、普通日志或真实候选人正文。

## 13. 正式自动化结果

| 命令 | 结果 |
|---|---:|
| `python -m unittest tests.test_ocr_normalization -v` | 86/86，0.816s，OK |
| `python -m unittest tests.test_simple_brush_ocr.LoggingIsolationTests -v` | 4/4，0.032s，OK |
| `python -m unittest tests.test_ocr_normalization tests.test_ocr_text tests.test_simple_brush_ocr -v` | 374/374，0.998s，OK |
| `python -m unittest tests.test_ocr_records tests.test_ocr_candidate tests.test_ocr_store tests.test_ocr_replay tests.test_ocr_stage0_integration -v` | 77/77，0.315s，OK |
| `python -m unittest tests.test_ocr_detector tests.test_ocr_text tests.test_simple_brush_ocr -v` | 365/365，0.247s，OK |
| `python -m unittest discover -s tests -v` | 594/594，1.521s，OK |
| `python -m compileall -q ...` | 通过 |
| `python -m pip check` | `No broken requirements found` |
| `git diff --check` | 最终执行结果见第 17 节 |

OCR/动作组第一次重跑时有 1 个旧测试仍直接检查参数化日志模板而非渲染结果；生产行为没有失败。测试改为检查渲染后的“第 1 次”和 `error_type=RuntimeError` 后，同一完整命令 360/360 通过。该修复属于 Change D 日志格式变更的直接测试适配。

本次 comparison 补充核验的首轮新增标点测试有 1 个测试自身的预期错误：它错误要求 U+2026 在 NFKC 后仍为 U+2026，而 Python NFKC 合法地产生 `...`。测试改为直接用 `unicodedata.normalize("NFKC", value)` 计算冻结预期后，针对性 121/121、正式分组与全量均通过；生产算法没有为该测试错误做适配。

本次提交前收尾的加强日志测试首跑暴露两个测试夹具事实错误：使用了 `DetectionResult` 不存在的字段，且未开启 fixture 的 `forward_enabled`。只校正测试夹具为真实数据结构/运行状态后通过；生产检测、规则和动作实现没有为夹具错误做适配。

## 14. Windows + Edge 状态

本轮运行环境是 Windows，但没有打开或操作真实 Microsoft Edge/BOSS 页面，没有读取真实候选人数据，也没有执行真实 favorite/forward/no-forward shadow 采样。mock、synthetic boxes 和 unittest 只证明 pure/integration 合同，不能冒充 Windows + Edge 人工验收。

结论：**Windows + Edge 人工验收未执行。** 因此 shadow deployment、Change 5B 和 formal production 均不能放行。

## 15. Shadow acceptance plan（待维护者批准后执行）

### 15.1 样本与时段

- 目标至少 2,400 条真实 shadow screen record、至少 300 个受控候选人会话。每条实际 screen record 以唯一 record identity 计入 2,400 总数且只计一次；formal screen 至少 1,200 条、confirmation 至少 300 条、load check/retry 至少 300 条、switch check/recovery 至少 300 条，第 7/8 屏、特殊 token、重复/灰区等是可与 capture type 重叠的 coverage tag。各类别/tag 计数允许重叠，其和不要求等于 2,400，但不能把同一实际 record 重复累加到总数。
- 连续 5 个工作日，每日早/晚两个时段，每日累计至少 2 小时，总观察时间至少 10 小时。
- 动作覆盖：favorite、forward 和 `--no-forward` 每种模式各至少 200 个 rule decision，其中至少 100 个 hit、至少 100 个 no-hit，共至少 600 个带动作模式标签的决策。rule decision、screen record 与 candidate session 不是 1:1：一次候选人会话可产生多个 screen record 和多个 rule decision，一个 decision 也可由 formal/confirmation 等多条记录支持；因此 300 个会话下限与 600 个决策下限分别核算，不用二者互相推导。真实 forward 必须使用维护者批准的测试账号/测试收件地址和人工监控，不能对真实候选人盲发。

### 15.2 分辨率与缩放

至少覆盖：

- 1920×1080：Windows 100%/125%，Edge 100%/125%；
- 2560×1440：Windows 100%/125%/150%，Edge 100%/125%；
- 每个组合至少 50 个 formal screen，并记录显示器、DPI、Edge zoom 和校准 profile 身份。

### 15.3 必须覆盖的业务/算法类别

formal screen、confirmation screen、load check/retry、switch check、favorite、forward、no-forward、`same_match`、`same_no_match`、`legacy_only`、`r04_only`、`normalization_failed`、特殊 token、UI 与正文远距同文、重复确认、重复灰区、第 7/8 屏、硬恢复都必须出现；自然数据未出现的类别只能用受控人工页面补样，不能用 mock 计入真实配额。

### 15.4 差异分类

每个非 same outcome 和“双方命中但 rule index 不同”记录由两人复核，分类为：legacy 规则缺口、R04 normalization 回归、OCR evidence 质量、approved duplicate suppression、UI/正文布局、config/platform、业务规则歧义或未解释。只读取最小必要 raw evidence；差异工作表不得复制完整候选人正文。

高风险 `legacy_only` 定义：在 R04 `completed`、evidence/config 合法的 formal/confirmation 中，legacy 会进入 confirmation/action 而 R04 不命中，且差异不能由已批准 normalization/duplicate 规则解释；特殊 token 被破坏、业务文字被错误抑制或远距同文误删一律按高风险处理。

### 15.5 Change 5B 提议批准标准

以下标准须由维护者先批准，实际采样全部满足后仍需单独书面授权：

1. 上述样本数、时段、分辨率、缩放和业务类别无缺项；
2. legacy/R04 匹配布尔一致率至少 99.9%；
3. 未解释高风险 `legacy_only` 为 0；所有 `legacy_only/r04_only` 与不同 rule-index 样本 100% 人工分类；
4. normalization failure 不超过 0.1%，且无 evidence mutation、无无限重试、无动作预算变化；
5. 特殊 token、远距同文、确认重复、灰区和第 7/8 屏人工抽查全部通过；
6. Windows + Edge 人工验收通过，隐私/日志审计无新增泄露；
7. 有明确的 `legacy_shadow` 回滚验证、差异报告、维护者对 Change 5B 的独立批准。

本轮只创建计划，**未部署、未采样、未批准该计划，也未启用 enforce**。

## 16. 已知风险与未完成边界

- 初始阈值只由单元 fixture 和合成性能验证，真实 Windows + Edge 分布仍未知。
- 历史日志包含 email-like 内容，保留/轮转/删除需要独立授权。
- 真实 shadow 数据会包含 raw evidence，必须先确定访问、留存、差异复核和删除策略。
- macOS 仅具备平台中立 pure unit 边界；`simple_brush.py` 仍是 Windows/pywin32 正式入口。
- `ocr_mac_demo.py` 的既有接口兼容问题不属于 R04 production 主流程，本轮未修复。
- 文档受仓库 ignore 规则影响，提交时必须显式逐文件暂存并先审阅 diff；本轮不暂存。
- R05/R06/R07、document aggregation、SimHash、动态结束、AI 和 SQLite 均未实现。

## 17. Git 范围与最终放行

Change A—D 当前工作区包含 R04 production/test 修改、两个正式报告和冻结 benchmark；既有 `docs/project-review.zip` 与 `venv-packages-before-reinstall.txt` 保持未跟踪且未修改。报告文件若被 Markdown ignore 规则隐藏，维护者批准提交后应逐文件使用显式路径暂存，禁止 `git add .`/`git add -A`；本轮不执行暂存或提交。

### 17.1 最终 `git diff --check`

命令最终退出码为 **0**，没有 whitespace error。Git 另输出 15 条“LF will be replaced by CRLF the next time Git touches it”工作区换行提示；这些不是 `diff --check` 失败，本轮没有为消除提示而格式化或改写无关文件。

### 17.2 最终完整 `git status`

```text
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   ocr_candidate.py
	modified:   ocr_detector.py
	modified:   ocr_records.py
	modified:   ocr_replay.py
	modified:   ocr_store.py
	modified:   ocr_text.py
	modified:   simple_brush.py
	modified:   tests/test_ocr_candidate.py
	modified:   tests/test_ocr_detector.py
	modified:   tests/test_ocr_records.py
	modified:   tests/test_ocr_replay.py
	modified:   tests/test_ocr_stage0_integration.py
	modified:   tests/test_ocr_store.py
	modified:   tests/test_ocr_text.py
	modified:   tests/test_simple_brush_ocr.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	docs/project-review.zip
	ocr_normalization.py
	tests/benchmark_r04_normalization.py
	tests/test_ocr_normalization.py
	venv-packages-before-reinstall.txt

no changes added to commit (use "git add" and/or "git commit -a")
warning: unable to access 'C:\Users\Quethoud/.config/git/ignore': Permission denied
warning: unable to access 'C:\Users\Quethoud/.config/git/ignore': Permission denied
```

本 Acceptance Report 命中仓库 `.gitignore` 的 `*.md` 规则，所以不会出现在上述普通 status 中；这不表示文档不存在或没有修正。只有维护者明确授权进入提交后，才可用报告的精确路径显式暂存并复核 staged diff；不得使用 `git add .` 或 `git add -A`。

最终分层结论：

| 层级 | 结论 | 理由 |
|---|---|---|
| R04 pure implementation | **passed** | 算法、确定性、不可变证据和性能门槛通过 |
| R04 automated integration | **passed** | Schema/Store/Replay/R03/P0/规则/动作预算和全量自动化通过 |
| shadow deployment | **not executed / blocked** | 无真实 Windows + Edge shadow 数据 |
| Change 5B enforce | **not approved / blocked** | shadow、差异分类、人工验收和维护者独立批准均缺失 |
| formal production | **blocked** | enforce 与发布门禁未满足 |

本报告不 commit、不 push、不创建 tag 或 Release。上述 status 和 diff-check 是本报告自身包含的补充核验最终证据。
