# BossOCR R05 产品需求文档：OCR 多屏新增内容识别与全文聚合

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 标题 | BossOCR R05：OCR 多屏新增内容识别与全文聚合 |
| Requirement ID | R05 |
| 优先级 | P1（OCR 采集层核心能力；R06、R07 与候选人级 AI 数据接口的前置） |
| 状态 | 正式设计，等待维护者审阅；未批准实施 |
| 依赖 | 阶段 0 OCR 记录与 JSONL；R03 exact hash；R04 `r04-v1` 标准化及视觉行 segment |
| 后续需求 | R06 页面相似度与有效新增量；R07 基于历史状态的动态滚动结束 |
| 正式平台 | Windows 正式运行路径；纯聚合层保持平台中立 |
| 文档版本 | 1.0，2026-08-01 |

本文件定义产品语义和验收边界。实施接口、算法、阈值、Schema 与逐 Change 文件范围见配套 TID。

## 2. 背景与问题

BossOCR 在同一候选人详情页最多连续采集八个正式 OCR 屏幕。滚动距离小于一屏高度，因此相邻屏经常重复显示公司、项目、职责或段落边界。阶段 0 已保存屏幕证据，R03 为单屏生成 exact hash，R04 将每个屏幕稳定标准化为视觉行；但这些能力都不判断一行是否已在前一屏出现。

若直接依屏幕顺序拼接 `normalized_text`，同一经历会被多次写入候选人全文。这会扩大规则或 AI 的输入噪声，夸大重复信息，降低结构化结果质量，增加持久化数据和人工复核成本。R04 不能独立解决该问题，因为它只处理同一屏幕内的阅读顺序、文本标准化和同位置重复 OCR box，不具有候选人级历史。

R05 也不能使用全局字符串去重。不同公司可以具有相同职责，不同项目可以使用相同工具，模块标题和技能词本来就会重复。脱离滚动边界、连续顺序和来源上下文的全局去重会删除合法内容，并破坏原始叙事顺序。

## 3. 用户价值

R05 提供以下用户价值：

- 生成一份候选人级、顺序稳定的完整 OCR 文档，而不是互不关联的屏幕文本。
- 降低同一经历因滚动重叠产生的重复，同时对证据不足的内容优先保留。
- 为后续 AI 结构化提供低噪声、确定性的文本输入，但本需求不调用 AI。
- 保留从文档段落到屏幕、屏幕 segment 和 OCR box 的审计来源。
- 为 R06 的页面相似度/有效新增量计算和 R07 的历史状态控制提供稳定文本基础。
- 通过 matched/new/uncertain 分类减少人工定位重复来源的成本。

## 4. 目标

R05 必须实现并验收以下产品能力：

1. 直接消费 R04 正式屏幕的视觉行 segment，保持原文和来源不变。
2. 在聚合文档尾部与当前屏幕头部之间识别最长、连续、精确的边界重叠。
3. 在严格小窗口内处理少量 OCR 差异以及 1 行拆 2 行、2 行合 1 行。
4. 对非相邻历史内容只做极保守的精确序列检查。
5. 为每个正式屏幕输出 matched、new、uncertain、warning 和风险结果。
6. 生成候选人级 `document_segments`，并由其唯一生成 `document_text`。
7. 为新建、抑制或合并的内容保存 source occurrence 与 match history。
8. 将 R05 结果写入现有 `screens.jsonl`、`candidates.jsonl` 和 `RunManifest` 体系。
9. 允许离线回放使用与在线相同的纯聚合函数，且不修改源记录。
10. 定义完成文档进入 AI payload 的纯数据边界，不执行 AI 调用或判断。

## 5. 非目标

以下内容明确不属于 R05：

- R06 所属的页面相似度、SimHash、字符 n-gram、`similarity_score`、`overlap_ratio`、`new_text_ratio`、`has_effective_new_text` 和有效短实体判断。
- R07 所属的连续无新增计数、滚动到底判断、动态结束、扫描状态机、新强结束标志和 R07 shadow。
- 新的 OCR、截图、等待、滚动、点击、页面失焦重试或任何浏览器行为。
- 收藏、转发、下一位、`--no-forward`、规则动作权威或 legacy 动作权威的改变。
- AI 调用、AI 决策、`qualified`、`rejected`、`manual_review`。
- SQLite、跨候选人去重、跨候选人缓存、长期截图保存。
- UI 文本黑名单、OCR 错字纠正、NER、语义段落识别或内容改写。

阶段边界固定为：R05 构建全文；R06 计算页面相似度与有效新增量；R07 才根据历史状态决定是否继续滚动。即使 R05 判定某屏没有新增 segment，也不得结束扫描。

## 6. 术语定义

| 术语 | 产品定义 |
| --- | --- |
| formal screen | 同时满足 `capture_type=formal_screen` 与 `is_formal_screen=true` 的候选人扫描屏幕 |
| non-formal screen | load、switch、confirmation、retry 或其他诊断/确认 capture，不进入全文 |
| screen segment | R04 在单屏内生成的稳定视觉行 `OcrTextSegment` |
| document segment | R05 按候选人文档顺序建立的独立段落单元；可拥有多个来源 occurrence |
| source occurrence | 一次 screen segment 对某个 document segment 的原始或再次出现证据 |
| matched segment | 证据充分，可映射到既有 document segment 且不再次追加正文的当前 screen segment |
| new segment | 未发现可信重叠，作为新的 document segment 追加的当前 screen segment |
| uncertain segment | 存在重复可能或处理异常，但证据不足以抑制；仍追加正文并提高风险 |
| exact overlap | 文档尾部与当前屏头部的连续 comparison 文本完全相同 |
| fuzzy overlap | 仅在相邻边界小窗口内，以高阈值确认的有限文本差异或 1↔2 行变化 |
| historical duplicate | 与非相邻历史 document segment 序列一致、且满足唯一来源和上下文条件的重复 |
| duplicate risk | R05 对“文档可能仍含重复或匹配存在不确定性”的分级，不是动作信号 |
| aggregation status | 单屏 R05 处理状态，与 R04 normalization 状态独立 |
| document build status | 候选人文档聚合的整体状态，与候选人捕获状态独立 |

## 7. 正式屏幕边界

仓库真实枚举 `CaptureType` 包含 `formal_screen`、`load_check`、`load_retry`、`switch_check`、`scroll_confirmation`、`scroll_retry` 和 `other`。仓库没有独立的 `switch_recovery` 枚举；恢复过程使用现有 load/switch capture 语义。

只有同时满足下列条件的记录可进入全文：

- `capture_type == CaptureType.FORMAL_SCREEN`；
- `is_formal_screen is True`；
- 属于当前 `run_id` 和 `candidate_record_id`；
- `screen_index` 是当前候选人的正式扫描序号。

confirmation、load check/retry、switch check/recovery、scroll retry 和 other 均继续保存其原始/R04证据，但 R05 状态为 `not_attempted`，不得影响 document。双条件不一致的 record 视为结构异常，不进入正文。

## 8. Segment 产品语义

R05 的输入基础粒度直接复用 R04 视觉行，不重新对 OCR box 分行，也不做语义段落识别。screen segment 保持 R04 已有 ID、顺序、`normalized_text`、`comparison_text` 和 `ocr_box_ids`。空视觉行不进入聚合。

document segment 是候选人级的新类型，因为它必须表达文档顺序、一个或多个来源 occurrence，以及 1↔2 模糊匹配关系；不能把 screen segment 原地改造成多屏对象。同样文字出现在不同位置是合法的，不能以文本 hash 作为身份或全局去重依据。每个 document segment 至少有一个可回到 screen segment 与 OCR box 的来源。

## 9. 相邻精确重叠

精确重叠只比较“当前 document 的连续尾部”与“当前正式屏幕的连续头部”。从最长候选开始，选择首个满足证据门槛的精确序列；不得在屏幕中间或文档中间寻找更好看的匹配。

产品规则如下：

- 最长匹配优先，顺序必须连续且一致。
- comparison 文本完全一致，但展示和保存的原文不被修改。
- 常规证据至少为 2 个 segment 且不少于 24 个 R05 比较字符，并至少含一个非短 segment。
- 单行完整屏重复只有在该行不少于 48 个比较字符时才允许抑制。
- 短标题、短职责或常见短句即使相同，也不因单独出现而删除；它们进入 uncertain 或 new。
- 完整屏重复可全部映射为 matched，但来源 occurrence 必须追加。
- 第 7/8 屏只有少量新增时，重叠头部被抑制，新增尾部仍按原顺序追加。

## 10. 有限模糊重叠

精确边界失败后，R05 可在文档尾部最多 4 个 segment 和当前屏头部最多 4 个 segment 内进行有限模糊匹配。允许处理少量 OCR 错字、漏字、多字、标点差异、大小写/空白差异，以及 1→2、2→1 的视觉行拆分/合并。

模糊匹配仍必须连续、单调并位于相邻边界；首版只允许 1→1、1→2、2→1，不允许一般 N→M 或 2→2。高置信候选才可抑制；同分、映射冲突、低于高阈值但达到灰区下限的候选全部保留为 uncertain。R05 只保存匹配关系，不修正或重写任一 OCR 原文。

## 11. 非相邻历史保守检查

相邻边界处理后，R05 可对剩余 segment 做非相邻历史 exact sequence 检查。首版不允许历史 fuzzy。只有 2—4 个连续 segment、至少 48 个比较字符、历史来源唯一、并具有两个连续的外部精确上下文锚点时，才可抑制并追加 occurrence。

以下内容不得仅凭历史文字相同而删除：

- 不同公司中的相同职责；
- 不同项目中的相同工具；
- 常见短句；
- 技能词或仅由分隔符连接的技能列表；
- 模块标题；
- 全部由短 segment 构成的序列；
- 没有双侧上下文、来源不唯一或无法确定唯一映射的内容。

任何未满足全部条件的历史候选均保留为 uncertain；没有候选的内容为 new。保守保留造成的少量重复优先于误删合法经历。

## 12. 每屏输出

正式屏幕的 R05 结果必须覆盖：

- `aggregation_status`、算法/config 身份；
- matched、new、uncertain screen segment ID；
- 指向 document segment 的 match evidence；
- 由 segment 确定性生成的 overlap text 与 document contribution text；
- matched、contributed、uncertain segment/字符计数；
- 固定 warning code；
- 独立的 aggregation duplicate risk。

screen 仍只保存一份 R04 `segments`；R05 分类通过 ID 引用这些 segment。文本投影必须能由 ID 重建并在读取时校验，不能出现另一套权威正文。非正式屏幕保存显式 `not_attempted` 和空分类。R06 的四个比率/有效新增字段继续保持未实现。

## 13. Candidate 文档输出

`CandidateOcrDocument` 是候选人级结果的既有容器。R05 必须在其中提供：

- 按文档顺序排列的 `document_segments`；
- 由上述 segments 唯一生成的 `document_text`；
- `document_build_status`；
- aggregation version/config identity；
- 固定 aggregation warnings；
- aggregation duplicate risk 和分类汇总。

`document_segments` 是权威数据，`document_text` 只是确定性投影。uncertain segment 必须进入 document，避免因不确定匹配丢失候选人内容。

## 14. 来源追溯

任何新建、抑制或合并的内容都必须可追溯到：

- 当前 `screen_id`、`screen_index`；
- 当前 screen segment ID；
- 当前 segment 的 OCR box ID；
- 对应历史 document segment ID；
- match type；
- fuzzy score，或 exact 的固定依据；
- 风险级别与固定 warning code。

同一 document segment 再次出现时，不复制正文，而是追加 occurrence 和 match evidence。1→2、2→1 必须保留组级映射，不能伪装成不相关的一对一匹配。

## 15. 状态与降级

三个状态域必须严格分离：R04 `normalization_status` 仍只有 `not_attempted/completed/failed`；R05 screen `aggregation_status` 可为 `not_attempted/completed/partial/failed`；R05 candidate `document_build_status` 可为 `not_attempted/completed/partial/failed`。R05 的 `partial` 不得写回或扩展 R04 状态。

降级原则如下：

| 场景 | R05 产品行为 |
| --- | --- |
| 无正式屏幕 | document `not_attempted`，warning=`no_formal_screen`，无伪造正文 |
| R04 failed | 对应 screen `failed`；保留 raw/R04 evidence；其他可用屏继续 |
| R04 completed 的空屏 | screen `completed`，无 segment；不是错误 |
| segment 映射失败 | screen `failed`；不猜测来源；其他屏继续 |
| 顺序异常/重复 index | 首条为顺序权威；冲突内容保守追加为 uncertain，candidate `partial` |
| 同一 screen ID 重复 | 相同输入幂等跳过；内容冲突则 `partial` 且不覆盖首条 |
| exact/fuzzy/history 阶段异常 | 受影响内容全部保留为 uncertain，screen/candidate `partial` |
| 中途 ESC | 有可信文档则 `partial`；无正式输入则 `not_attempted` |
| 候选人中途异常/abort | 可安全生成则 `partial`，否则 `failed` |
| finalize 异常 | 不伪造 candidate 文档；记录脱敏错误，主流程按现有异常策略处理 |
| Store 失败 | 不改变页面和动作；内存对象不反向修改，按既有 best-effort 降级 |
| replay 失败 | strict 拒绝；tolerant 报脱敏 issue，源 JSONL 不变 |

## 16. 隐私与数据治理

raw boxes、screen text、document text、source occurrence 和 match history 都属于敏感运行数据，只能存在于受治理的 JSONL 运行目录或明确的内存对象中。普通日志仅允许状态、计数、version/config identity、固定 warning code 和异常类型，不得写全文、segment 文本、规则文本、邮箱、手机号、坐标或 confidence。

source occurrence 不得进入普通日志。真实 shadow 前必须单独批准访问范围、留存期限、删除方式和样本脱敏方案；真实运行数据不得进入 Git。当前仓库只有一个全空的 R04 run，尚不能用于产品阈值校准。

## 17. 跨平台

R05 pure aggregator 必须平台中立，使用 Unicode 字符串与固定 LF 生成正文，不依赖 Windows 路径、GUI、OCR backend 或页面自动化。JSONL 继续为 UTF-8。

Windows 仍是唯一正式运行路径。macOS 只维持仓库现有纯模块/测试兼容边界，不声明 GUI、截图、浏览器控制或发布包的正式支持。

## 18. 性能

每名候选人最多处理现有的 8 个正式屏幕。R05 不得进行无界全文 fuzzy 两两比较，不得枚举任意 N→M 窗口，也不得随候选人数量累积状态。候选人 finalize 后必须释放 builder/aggregator 对 screen 的引用。

单屏 segment 安全上限、fuzzy 窗口和历史序列长度均由集中配置给出；超限时保留文本并降级为 partial，而不是继续无界计算。产品验收要求典型 8×64 segment 的聚合 p95 不高于 20 ms，最大 8×256 segment 的 p95 不高于 150 ms，峰值附加内存不高于 32 MiB；这些是首版实验门槛，须在真实样本治理完成后复核。

## 19. Change 1—7 产品验收

### Change 1：仓库验证、基线与接口确认

- 复核本文事实、Git 基线、R04 identity、正式屏判定、保存顺序与缺失 AI 接口。
- 不改任何生产/测试行为；产出可审阅的差异与门禁报告。

### Change 2：segment 模型与确定性适配

- R04 screen segment 原样适配为 R05 输入；新增 document segment/source occurrence 模型。
- ID、顺序、字符口径、box 来源和输入不可变性可重复验证。

### Change 3：相邻精确重叠

- 最长边界 exact、完整屏重复、短文本保护和第 7/8 屏少量新增均有确定结果。
- 非边界相同文本不得被 exact 阶段抑制。

### Change 4：有限模糊重叠

- 1→1、1→2、2→1 和允许的小差异可在固定窗口内识别。
- 灰区、同分、顺序颠倒、短文本和超限全部保留。

### Change 5：历史检查与候选人 builder

- 唯一 exact 历史序列在双侧上下文成立时可抑制；合法重复与不确定项保留。
- 零/一/八屏、异常、ESC、重复 finalize 和候选人隔离满足状态契约。

### Change 6：Schema、Store、Replay、AI 数据接口和主流程集成

- 1.2.0 round-trip、1.0/1.1 兼容、append-only 先算后写、在线/离线一致。
- 经维护者批准后才可新增纯 `build_ai_payload()`；未完成文档必须拒绝，且不执行 AI。
- OCR、截图、等待、滚动、confirmation 和动作调用次数逐项不变。

### Change 7：全量验收

- 全量回归、性能、隐私、跨平台纯模块和 source 不可变全部通过。
- 形成独立 R05 Acceptance Report；未获得维护者批准不得进入生产 shadow 或下一需求。

每个 Change 都必须单独审阅并停止，不得自动进入下一 Change。

## 20. Definition of Done

- [ ] 维护者已审阅并批准本 RPD 与配套 TID。
- [ ] 所有正式屏 selection 与非正式 capture 排除规则已测试。
- [ ] screen/document segment 类型、ID、顺序、字符口径和来源不变量已实现。
- [ ] exact 最长边界匹配与短文本保护矩阵全部通过。
- [ ] fuzzy 固定窗口、1↔2、灰区与冲突保留矩阵全部通过。
- [ ] historical exact 唯一来源/双侧上下文规则及合法重复保护全部通过。
- [ ] 每屏 matched/new/uncertain、warning、risk 与 candidate 文档可完整 round-trip。
- [ ] `document_text` 与 `document_segments` 逐字符一致，无独立拼接路径。
- [ ] Schema 1.2.0、1.0/1.1 兼容、config drift 和 mixed version 行为已验收。
- [ ] Store 无后补、无部分 JSONL；online/offline replay 逐字段一致。
- [ ] AI payload 仅在维护者批准接口且文档完成时生成数据；无 AI 调用/判断字段。
- [ ] 594 项既有测试基线及全部新增测试通过，R03/R04 identity 与 legacy 动作权威不变。
- [ ] OCR、截图、等待、滚动、点击、confirmation、favorite、forward、no-forward、ESC 和 timer 调用行为不变。
- [ ] 典型/最大性能和 32 MiB 内存门槛通过，重复运行确定性通过。
- [ ] 普通日志无正文/segment/source/规则/联系方式/坐标/confidence，测试不污染真实日志。
- [ ] 无真实运行数据进入 Git，真实 shadow 的访问、留存和删除策略已独立批准。
- [ ] R05 Acceptance Report 明确记录 Windows 手工验证、未决门禁和回滚结果。

## 实施门禁与未决问题

以下不是留给实施者自由选择的算法问题，而是必须由维护者提供证据或授权的门禁：

1. **真实样本门禁**：当前 `data/ocr_runs` 只有 0 字节 manifest/JSONL，没有可校准的正式 R04 历史样本；R04 Acceptance Report 也未完成真实 Windows shadow。最小处理是先批准数据治理方案，再以 `--no-forward` 获取受控样本并完成 R04/R05 shadow 校准。它阻塞 R05 生产验收，不阻塞已批准后的纯函数与自动化实现。
2. **AI payload 接口门禁**：仓库不存在 `build_ai_payload()`，也不存在 `qualified/rejected/manual_review` 数据接口。最小处理是维护者在 Change 6 前批准 TID 冻结的纯数据函数签名；禁止借此增加 AI 调用或判断。
3. **阈值校准门禁**：TID 中的新增阈值是首版保守默认；Terra 不得自行更改。只有形成受治理样本报告并经维护者批准，才可在独立 Change 中修改 config/version/digest。

本文件批准前不得进入 Change 1；本文件批准后仍须逐 Change 停止审阅。
