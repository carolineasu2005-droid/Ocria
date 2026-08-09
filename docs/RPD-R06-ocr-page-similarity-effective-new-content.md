# RPD — R06 OCR 页面相似度、文本重叠率与有效新增量

## 1. 文档信息

| 项目 | 值 |
|---|---|
| 需求编号 | R06 |
| 需求名称 | OCR 页面相似度、文本重叠率与有效新增量 |
| 文档类型 | Product Requirements Document |
| 文档状态 | Change 1 设计门禁基线 |
| 版本 | 1.0 |
| 日期 | 2026-08-01 |
| 前置需求 | R03、R04、R05 |
| 后续需求 | R07 |
| 本 Change 范围 | 仓库勘察、前置能力验证、正式 RPD/TID；不实施 R06 |

本文定义 R06 的产品语义、边界和验收口径。算法、Schema、真实文件和后续 Change 计划以配套 TID 为准。

## 2. 背景

BossOCR 当前固定扫描最多 8 屏。R03 为每次 OCR 页面提供唯一权威的 SHA-256 精确指纹；R04 保留原始证据并生成稳定的 `normalized_text`、`comparison_text` 和视觉行 segment；R05 在候选人范围内把当前屏 segment 分类为 `matched`、`new`、`uncertain`，并可生成候选人全文。

现有能力能回答“页面是否完全相同”和“哪些视觉行可能重复”，但尚不能用统一、可回放、可校准的数据回答：

- 当前正式屏与可靠基准屏有多相似；
- 当前有效文本中重叠、新增和不确定分别占多少；
- R05 标为新增的内容中，哪些更可能是业务有效新增，哪些有强证据表明只是格式或 OCR 伪影；
- 页面变化应如何以中性类别记录，供离线分析和未来 R07 使用。

## 3. 当前问题

1. 只有 exact hash 时，任何一个字符变化都会变成“不同”，无法表达近似程度。
2. 只报告比例而不保存分子、分母，无法审计零分母、字符会计和算法升级。
3. OCR 的重复框、格式字符、低置信度孤立乱码可能被误记为有效新增；split/merge 已由 R05 识别并归入 matched，R06 不得重新猜测。
4. 短文本既可能是 UI 噪声，也可能是年份、日期、版本号、技术栈或岗位词，不能用简单长度阈值删除。
5. 若 reference 只靠 JSONL 行顺序或列表前一项猜测，在线与离线结果会漂移。
6. R06 若进入滚动结束或候选人动作控制，会越界提前实现 R07，并可能改变现有业务行为。

## 4. 产品目标

R06 必须：

- 复用 R03 唯一权威 `exact_hash`，比较当前屏与可靠 reference 是否完全相同；
- 基于 R04 `comparison_text` 计算 0—1 的主要字符 n-gram 页面相似度；
- 生成跨进程稳定的 SimHash 辅助指纹和辅助相似度，且不让 SimHash 成为唯一判断；
- 复用 R05 `matched/new/uncertain` 权威分类，计算字符数、segment 数和比例；
- 保存比例的分子、分母，并验证字符与 segment 会计关系；
- 对 R05 `new` segment 做可解释的有效新增分类；
- 对 R05 `uncertain` 保持保守语义，不把证据不足误判为无效；
- 保护年份、日期、版本号、技术词、公司名、项目名和岗位名等短文本；
- 不建立 UI 文字黑名单；
- 输出中性的 `comparison_class`，只计算和记录；
- 保存 reference、算法、配置、参数、版本、digest 和脱敏 warning；
- 写入现有 screen、candidate、RunManifest 和 JSONL 体系；
- 在线和离线调用同一 evaluator；
- 支持不改写源记录的 sidecar 重新计算和参数校准；
- 在 R06 失败时保留 R03/R04/R05，并让固定扫描和候选人主流程继续。

## 5. 非目标

R06 不负责：

- 改变候选人切换、详情页加载检测、OCR/截图/滚动/等待次数；
- 决定是否停止滚动、提前结束 8 屏扫描或实现动态结束；
- 改变关键词、AND/OR/NOT/ANY、收藏、转发、下一位、action mode；
- 改变 ESC、运行时长、异常停止；
- 语义模型、AI、embedding、LLM 或外部 API；
- SQLite、索引数据库或数据迁移服务；
- UI 文案字典或黑名单；
- 修改 R04 三层文本、R05 `document_text` 或 `document_segments`；
- 修改 R03 `exact_hash` 的权威定义。

## 6. R03—R07 边界

```text
R03 页面精确指纹
  → R04 稳定三层文本与视觉行 segment
    → R05 matched/new/uncertain 与候选人全文
      → R06 相似度、比例、有效新增信号（只计算和记录）
        → R07 扫描状态机与动态结束（本需求不实现）
```

- R03：权威回答“完全相同吗”。
- R04：权威提供可比较文本和 segment 来源映射。
- R05：权威提供当前屏 segment 的三分分类、1→1/1→2/2→1 split/merge match evidence 和候选人聚合证据；有完整 split/merge evidence 的当前 segment 属于 `matched`。
- R06：在以上结果上派生相似度、比例、有效新增和中性类别；只为 `new/uncertain` 生成有效新增 decision，不重算、推断、覆盖或修正 R05 split/merge。
- R07：未来才可消费 R06 信号并控制扫描。

## 7. 用户场景

### 7.1 首个正式屏

首个正式屏没有上一正式屏。R06 记录 `no_reference`；不得拿 load check、switch check、其他候选人屏或 JSONL 前一行代替。

### 7.2 后续正式屏

当前正式屏只与同一 `run_id`、同一 `candidate_record_id`、`screen_index` 正好小 1 的唯一正式屏比较。若目标缺失、重复、冲突或不是正式屏，则为 `unavailable`。

### 7.3 非正式 OCR

load retry、switch check、scroll confirmation 等只有在记录里存在显式 reference ID，且 reference 通过身份和 capture 规则校验时才比较。否则为 `unavailable`。不得从行顺序推断。

### 7.4 近似重复页面

页面不是 exact same，但大部分 `comparison_text` 相同。R06 给出主相似度、SimHash 辅助信号和重叠/新增/不确定比例，不作停止决定。

### 7.5 少量业务新增

页面高度相似，但新增 segment 包含年份、日期、版本、技术词、公司/项目/岗位短词。R06 应保护这些内容，不因“短”而删除。

### 7.6 OCR 伪影或证据不足

明确格式伪影、重复框或满足组合证据的低置信度孤立乱码可以标为无效。split/merge 由 R05 以 match evidence 识别并归入 `matched`，不进入 R06 new/uncertain 有效新增 decision；证据不足时必须标为 `uncertain`，并保守视为“可能有效”。

## 8. Reference screen 产品规则

### 8.1 正式屏

- 首个正式屏：`no_reference`。
- 后续正式屏：上一正式屏。
- “上一”由显式 `screen_index - 1`、candidate/run 身份和唯一 screen ID 共同确定，不由容器或 JSONL 顺序确定。
- 缺号、重复 index、重复/冲突 screen ID、身份不一致：`unavailable`。

### 8.2 非正式屏

- 只有显式保存的 `reference_screen_id` 可用。
- scroll confirmation 可显式指向同 screen index 的正式屏。
- load retry 可显式指向同候选人前一次已记录的 load observation。
- 当前流程中的 switch check 若没有同候选人显式基准，必须 `unavailable`；不得跨候选人猜测。

### 8.3 Replay

- 新 Schema 必须验证持久化 reference ID。
- 旧 Schema sidecar 只可用 candidate/run 身份与唯一正式 `screen_index` 重建正式屏关系。
- 旧 Schema 的非正式屏没有显式 reference 时不可重建。

## 9. Exact same 定义

`exact_same` 只复用 R03 `exact_hash`：

- 两侧 hash 都是合法小写 64 位十六进制 SHA-256；
- 两侧 `fingerprint_version` 相同；
- 满足时比较 hash，结果为 `true` 或 `false`；
- 任一条件不满足则为 `null` 并记录 warning；
- R06 不重新计算、覆盖或创建第二套名为 `exact_hash` 的实现。

当前仓库 R03 hash 的输入不是 R04 `comparison_text`。R06 接受这一真实前置，使用最小只读 adapter 校验和消费已保存 hash；不得在 R06 Change 1 或后续实现中暗改 R03 定义。

## 10. 模糊相似度定义

主要 `similarity_score`：

- 输入为当前屏和 reference 的 R04 `comparison_text`；
- 使用确定性的字符 n-gram 多重集合相似度；
- 结果范围为 `[0.0, 1.0]`；
- 重复字符/短语的出现次数必须保留，不退化为纯集合；
- 各 n 的分数按冻结权重归一化聚合；
- 双空文本定义为 1.0，单侧空文本定义为 0.0；
- 超长文本触发有界保护，不静默截断并伪造分数；
- 参数和公式在 TID 中冻结并写入 RunManifest。

SimHash 是辅助信号：它可帮助离线观察整体接近程度，但不得覆盖 exact hash 或主要 n-gram 分数。

## 11. overlap/new/uncertain 比例定义

R06 复用 R05 segment ID 三分集合，按 R04 `comparison_text` Unicode code point 数计数：

- `overlap_char_count`：`matched_segment_ids` 的字符数；
- `new_char_count`：仅 `new_segment_ids` 的字符数；
- `uncertain_char_count`：仅 `uncertain_segment_ids` 的字符数；
- `current_effective_char_count`：当前屏所有 R04 segment 的字符数。

必须满足：

```text
overlap_char_count + new_char_count + uncertain_char_count
= current_effective_char_count
```

比例为各自字符数除以同一 `current_effective_char_count`。每个比例保存自己的 numerator 和 denominator。零分母时比例为 `null`，不得写 0 或 1 冒充有效比例。

segment 数也保存并满足同样三分会计关系。R05 现有 `new_text_char_count` 包含 `new + uncertain`；R06 不改变该字段，而是从 segment ID 权威重算独立 `new_char_count`，并验证：

```text
R05 new_text_char_count = R06 new_char_count + R06 uncertain_char_count
```

## 12. 有效新增定义

有效新增是 R05 `new` segment 中，没有强证据表明属于伪影或重复，且包含可保留内容的 segment。它是可解释的本地规则结果，不是语义理解结论。

每个被评估 segment 必须保存：来源分类、有效性状态、reason code 和用到的证据。候选人级状态至少区分：

- `present`：存在明确有效新增；
- `possible`：没有明确有效新增，但存在 uncertain/证据不足的可能新增；
- `none`：所有新增均有充分无效证据，且没有 uncertain；
- `unavailable`：前置结果不可用或会计失败。

## 13. 无效新增定义

只有可审计证据满足时，新增 segment 才可标为无效：

1. `format_only`：只有格式/分隔结构，无受保护词元或业务字符；
2. `duplicate_artifact`：R04 重复框几何与文本证据共同支持；
3. `low_confidence_noise`：孤立、低置信度、无结构、无保护命中的组合证据支持；
4. `likely_repeated_ui_noise`：跨至少 3 个正式屏的文本、几何稳定性和重复位置组合证据支持。

`split_merge_artifact` 在 `r06-v1` 是 reserved / never emitted：合法 R05 split/merge evidence 已属于 matched，而 R06 不对 matched 生成 `EffectiveNewDecision`。R05 仍标为 new 的内容不得仅凭 fuzzy 分数、文本相似、相邻拼接或 document ID 被 R06 猜测为 split/merge 伪影。

仅凭文本短、常见、重复或“看起来像 UI”均不足以判无效。

## 14. uncertain 保守原则

- R05 `uncertain_segment_ids` 不进入“明确无效”结论。
- 若 new/uncertain segment 非法出现在 R05 `match_evidence.current_segment_ids`，这是前序 partition/evidence 合同冲突，不是 split/merge 正例；R06 停止有效新增分类，输出 unavailable/null/uncertain，并保留 R05 源对象。
- R06 证据缺失、证据冲突、阈值灰区、reference 不可靠或分类异常时使用 `uncertain`。
- `uncertain` 新增在布尔兼容投影中保守视为可能有效，但中性类别优先为 `uncertain`。
- uncertain 只影响记录解释，不影响扫描或业务动作。

## 15. 短文本保护

短文本保护至少覆盖：

`SLG`、`UE5`、`3D`、`C++`、`C#`、`.NET`、`Unity`、`主美`、`UI`、`TA`、`3A`、`0-1`、`2D/3D`、年份、日期、时间/数值范围和版本号。

同时保护 R04 `protect_comparison_tokens()` 可识别的符号型词元，以及公司名、项目名、岗位名等未知短文本的保守语义。业务短词表必须版本化、保存 digest，不得无版本热改。

## 16. UI 文字保留原则

R06 不建立 UI 文字黑名单，不按具体文案删除“收藏”“沟通”“简历”等文字。`likely_repeated_ui_noise` 必须依赖组合证据：同文本、同相对几何区域、跨至少 3 个正式屏稳定重复，并且没有短文本保护或业务上下文反证。证据不足即 `uncertain`。

## 17. comparison_class 中性定义

R06 只输出以下中性类别：

- `exact_same`
- `high_similarity_with_effective_new`
- `high_similarity_without_effective_new`
- `changed_with_effective_new`
- `changed_without_effective_new`
- `empty_or_unavailable`
- `uncertain`

类别不等同于“应继续”“应停止”“合格”“拒绝”或“人工审核”。阈值未经真实数据校准前，只用于记录和离线分析。

## 18. 首屏、空文本、无 reference 与失败语义

| 场景 | 状态 | 关键语义 |
|---|---|---|
| 首个正式屏 | `no_reference` | pair 数值为 null；可保存当前 SimHash 和 R05 计数；class 为 `empty_or_unavailable` |
| 可靠 reference、双空 comparison | `completed` | similarity=1.0；比例分母为 0、比例 null；class 为 `empty_or_unavailable` |
| 可靠 reference、单侧空 | `completed` | similarity=0.0；class 为 `empty_or_unavailable` |
| reference 缺失/冲突 | `unavailable` | pair 数值 null；记录 warning |
| R05 partial | `partial` | 可保留可信相似度，比例/有效新增按可验证程度填写；class 通常 `uncertain` |
| evaluator 异常 | `failed` | R06 数值 null，脱敏 warning；R03/R04/R05 保留，业务继续 |

## 19. 数据保存

R06 结果必须与一次 screen record 同步生成，首次 `save_screen()` 前完成，并嵌入同一 candidate document 的 screen 快照。RunManifest 保存算法、配置、digest 和模式；candidate 保存汇总和同一 screen 结果。

禁止保存临时 screen 后回填 JSONL、原地改行或建立第二套主数据系统。

## 20. 离线回放与参数校准

- 离线 replay 使用与在线相同的纯 evaluator 和 reference resolver。
- 历史 config 由 manifest 恢复；caller override 只允许 sidecar 校准，不冒充原在线结果。
- sidecar 是新增派生文件，不修改源 `run.json`、`screens.jsonl` 或 `candidates.jsonl`。
- sidecar 每条记录包含 source identity、reference、算法/配置 digest、结果和 warning。
- 相同源输入和相同 config 必须跨进程得到相同结果。

## 21. 隐私

- 不调用网络或外部服务。
- 日志和 warning 只保存枚举、版本、digest、计数和 opaque ID，不记录 OCR 正文、候选人姓名、公司名或异常消息。
- JSONL 仍会包含阶段0/R04/R05 已授权的 OCR 原始/派生内容，沿用现有敏感数据治理与访问控制。
- benchmark 使用合成数据，不使用真实 BOSS 页面。

## 22. 行为零影响

R06 任何模式都不得改变：

- OCR、截图、滚动、点击和等待的次数与时机；
- 最多 8 屏、滚动距离和详情页加载检测；
- 候选人切换、焦点恢复、关键词和 action mode；
- 收藏、转发、下一位；
- ESC、运行时长和异常停止；
- Windows/macOS 行为；
- R04 三层文本和 R05 candidate document。

R06 失败必须 fail open：保留前序结果、记录脱敏 warning、继续固定扫描。

## 23. 风险

1. R05 当前生产默认 `disabled`，正式在线 R06 必须以前置 R05 record 模式获独立批准并通过验收为条件。
2. 当前 `exact_hash` 输入不是 R04 `comparison_text`；若错误地重算会造成双权威。
3. R05 `new_text_char_count` 包含 uncertain，直接相加会重复计数。
4. 当前非正式 record 没有持久化 reference link，不能靠顺序补猜。
5. 没有非空真实 R04/R05 run 数据，首版阈值只能是分析阈值，不能进入控制流。
6. UI 噪声若证据不足，易伤害公司/项目/岗位短词，必须保守。
7. 超长文本若无界建立 n-gram Counter，会引发性能和内存风险。
8. 当前 R05 工作区实现尚未提交且 Change 7 曾阻塞，R06 后续开发必须先重新确认基线。
9. R06 若对 R05 new 重新猜 split/merge，会制造第二套 diff 权威；r06-v1 必须只保留 R05 matched evidence，未来扩展须先升级 R05/R06 Schema 与版本。

## 24. 验收标准

- [ ] R03 exact hash 只读复用，仓库不存在第二套冲突实现。
- [ ] reference 不依赖 JSONL/列表顺序，candidate/run 隔离和冲突处理有测试。
- [ ] 主 n-gram 分数和 SimHash 跨进程确定，范围和空文本语义有测试。
- [ ] matched/new/uncertain segment 完整三分，字符与 segment 会计成立。
- [ ] 每个比例保存 numerator/denominator，零分母为 null。
- [ ] R05 聚合投影兼容关系通过验证，uncertain 不重复计数。
- [ ] 有效新增逐 segment 有 reason/evidence，未知情况使用 uncertain。
- [ ] R05 1→2/2→1 split/merge evidence 仅保留在 matched；R06 不为 matched 生成 decision，合法 new 不输出 `split_merge_artifact`，非法 new/uncertain evidence 关系降级为前序合同冲突。
- [ ] 所列短文本、年份、日期和版本号全部受保护。
- [ ] 没有 UI 文案黑名单。
- [ ] `comparison_class` 仅使用冻结中性枚举和优先级。
- [ ] online/replay/sidecar 使用同一 evaluator，相同输入/config 结果相同。
- [ ] R06 异常不改变任何 OCR/截图/滚动/动作/停止调用。
- [ ] 全量测试、R03/R04/R05/Store/Replay/规则/模式/ESC/时长/Unicode/平台测试通过。
- [ ] R06 benchmark 满足 TID 门槛，且不做无界历史两两比较。
- [ ] `logs/simple_brush.log` 和 `data/ocr_runs` 在测试前后 inventory、mtime、size、SHA-256 一致。
- [ ] 明确不实现 R07、AI 和 SQLite。

## 25. 待人工决定

1. R05 何时完成独立 Change 7 复验，以及何时允许生产 `record` 模式；未经批准，R06 在线 record 不得启用。
2. 真实 OCR 数据的采集、留存、脱敏和删除授权；没有该授权时，只能做合成数据校准。
3. 首版 `high_similarity_threshold` 等分析阈值在真实样本上的正式校准结论；校准前不得进入 R07 或任何动作控制。

## 26. 明确声明

本需求不实现 R07、AI 或 SQLite。Change 1 只交付调查、RPD、TID 和报告，不实施任何 R06 生产代码、测试代码、配置、依赖、构建或 workflow 变更。
