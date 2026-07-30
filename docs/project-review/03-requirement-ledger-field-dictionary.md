# 阶段 1：需求台账字段字典

## 1. 规范数据结构

后续 `requirement-ledger.json` 是唯一可编辑的规范需求台账，根结构固定为：

```json
{
  "schema_version": "1.0.0",
  "project": "BossOCR",
  "generated_at": null,
  "requirements": []
}
```

本段是结构示例，不是正式台账，也不包含项目历史日期。`requirement-ledger.csv`、`requirement-ledger.md`、流程图和 HTML 原型必须从通过 Schema 和外部一致性检查的规范 JSON 生成。

## 2. 根对象字段

| 中文名称 | 英文字段名 | 数据类型 | 是否必填 | 是否允许多值 | 允许值 | 字段用途 | 填写规则 | 空值处理 | 示例 | 常见错误 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Schema 版本 | `schema_version` | string | 是 | 否 | 固定 `1.0.0` | 让生成器和 HTML 判断兼容性 | 语义或结构破坏兼容时按语义化版本提升，并同步全部规则文件 | 不允许空值 | `"1.0.0"` | 用项目 release `v1.2` 代替；只改 Schema 不改字典 |
| 项目名 | `project` | string | 是 | 否 | 固定 `BossOCR` | 防止消费者误读其他项目数据 | 大小写固定 | 不允许空值 | `"BossOCR"` | 写分支、平台或仓库 URL |
| 生成时间 | `generated_at` | string(date-time) 或 null | 是 | 否 | 带时区的 RFC 3339 date-time 或 JSON null | 表示这份数据实例生成/刷新时间，不是项目历史时间 | 生成器实际写出数据时记录；规则模板保持 null | `null` 表示尚未生成正式数据；不允许 `unknown`/`not_applicable` | `"2026-07-25T16:30:00+08:00"` | 用文件创建时间冒充需求日期；写无时区时间；在 Schema 文件中硬写历史日期 |
| 需求条目 | `requirements` | array<object> | 是 | 是 | 符合 `requirement` 定义的对象；本阶段允许空数组 | 保存全部规范 `R-xxx` | 按编号数值升序；每个 ID 唯一 | 根集合可以 `[]`，这是“尚无条目”，不使用三种字段空值 | `[]` | 把 CSV 行对象放在根；混入决策或证据对象；依标题排序造成 diff 抖动 |
| 根扩展 | `extensions` | object | 否 | 是 | 显式命名空间键 | 为实验性消费者保留不进入核心契约的数据 | 只有已登记、带命名空间的键；消费者必须可忽略 | 缺少键等于没有根扩展；不使用字符串 sentinel | `{"prototype.view":"compact"}` | 在根对象随意增加字段；把核心事实长期藏在扩展中 |

## 3. 空值与集合编码

### 3.1 三种空值

| 值 | 精确定义 | 使用示例 |
| --- | --- | --- |
| JSON `null` | 已检查的证据中不存在该字段对应的事实或材料 | 当前证据没有 Implementation Report，`implementation_reports: null` |
| 字符串 `"unknown"` | 该值理论上应存在，或有迹象表明存在，但当前无法确认 | 已知有首次提出时点但无法定位，`first_observed_date: "unknown"` |
| 字符串 `"not_applicable"` | 该字段对该条目的概念或终态不适用 | 一个纯业务需要没有实现方案，`selected_solution: "not_applicable"` |

不得用空字符串、空白、`"null"`、`N/A`、`none`、`TBD`、`待确认` 或 `-` 代替。`null` 是 JSON 原生值，不是字符串。

字段数组有实际值时必须至少一个元素且去重；没有值时用整个字段的 `null`、`"unknown"` 或 `"not_applicable"`。禁止空数组 `[]`，禁止 `['unknown']`，也禁止把实际值与 sentinel 混在同一数组。唯一例外是根对象 `requirements: []`，用于本阶段或确实没有条目的数据集。

### 3.2 “必填”的含义

需求对象的 48 个规范字段键都结构性必填，以保证 CSV 列、Markdown 表和 HTML 消费稳定。“必填”不表示必须捏造实际值；字段字典允许时应使用三种空值。`requirement_id`、`title`、`summary`、`confidence`、`first_observed_evidence_ids` 和 `evidence_ids` 不接受空值，因为没有身份、可读摘要或最低证据的候选项不应进入正式台账。

## 4. 标识、分类与时间字段

以下所有示例只说明语法，不是在本轮分配正式 BossOCR 需求编号。

| 中文名称 | 英文字段名 | 数据类型 | 是否必填 | 是否允许多值 | 允许值 | 字段用途 | 填写规则 | 空值处理 | 示例 | 常见错误 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 需求主编号 | `requirement_id` | string | 是 | 否 | `R-001` 至 `R-999`，之后为 `R-1000` 起；禁止 000 和多余前导零 | 稳定连接台账、图、原型和证据 | 使用下一未用序号；编号不含模块、平台、年份或优先级 | 不允许 | `"R-001"` | 使用 `Next-3`/`R4` 作主键；写 `R-000`/`R-0001`；标题变化后换号；复用删除号 |
| 历史编号 | `legacy_ids` | array<string> 或空值状态 | 是 | 是 | 带命名空间的原始标识 | 保留 Issue、Next、PRD 局部编号等历史映射 | 格式 `<namespace>:<original>`；保留原 token 和上下文 | 无历史编号且已核对用 `not_applicable`；材料未查全用 `unknown`；证据未记载用 null | `["github_issue:#5","roadmap:Next-3"]` | 把不同文档的 `R1` 合并；把 P0、tag 或 commit 当旧需求号；去掉 `#`/`Next-` 原文 |
| 标题 | `title` | string | 是 | 否 | 非空、非 sentinel 文本 | 供人阅读的中性工作标题 | 描述预期结果，不写状态、风险或未经证实的结论；可改标题但不改 ID | 不允许 | `"纯示例：在动作前验证页面状态"` | 把文件名直接当标题；用宣传文案；因改标题重新编号 |
| 摘要 | `summary` | string | 是 | 否 | 非空、非 sentinel 文本 | 一至三句说明问题、结果和边界 | 只写证据支持的最小结论，明确平台/非目标 | 不允许 | `"纯示例：失败时停止动作并保留诊断证据。"` | 复制整份 TID；把方案写成业务问题；隐去未完成门禁 |
| 需求类型 | `requirement_type` | string | 是 | 否 | `business_need`、`product_requirement`、`system_requirement`、`defect`、`engineering_enablement`、`test_protection`、`release_enablement`、`maintenance_enablement`、`unknown` | 区分需求性质 | 按 taxonomy 的提升规则选择；Technical Decision/Change/Release Event 通常不建 R | 仅允许 sentinel `unknown`，并必须有 open question | `"system_requirement"` | 把 source type、状态或模块写入；把每个 Change 标成需求 |
| 首次观察值 | `first_observed_date` | string、null 或 `unknown` | 是 | 否 | 由 `date_precision` 决定 | 保存证据支持的最早时点、范围或顺序 | 与 `first_observed_evidence_ids` 绑定；不得用当前文件创建时间代替历史时点 | 证据完全不含日期用 null；有日期迹象但不能确认用 unknown；不允许 not_applicable | `"2026-07"` | Git commit 时间等同首次提出；只知月份却填日；后期总结日期当需求日期 |
| 日期精度 | `date_precision` | string | 是 | 否 | `exact_day`、`exact_month`、`approximate_range`、`sequence_only`、`unknown` | 让时间线保留真实精度 | `exact_day`=`YYYY-MM-DD`；`exact_month`=`YYYY-MM`；range=`起点/终点`；sequence=`sequence:<正整数>` | 只有 `unknown` 可配 date 的 null/unknown；不允许 not_applicable | `"exact_month"` | 把估计日期标 exact；sequence 值伪装成日期；range 起止反转 |
| 首次观察证据 | `first_observed_evidence_ids` | array<string> | 是 | 是 | `E-001` 起的规范 E 编号，无 000 或多余前导零 | 证明日期和最早来源类型 | 至少一个；必须同时出现在 `evidence_ids`；类型应覆盖 `source_type` | 不允许空值或空数组 | `["E-001"]` | 引用后来验收作为首次提出；不在 evidence_ids；仅凭文件时间 |
| 最早来源类型 | `source_type` | array<enum> | 是 | 是 | taxonomy 定义的 23 个来源值 | 快速筛选条目的首次观察来源 | 只汇总 `first_observed_evidence_ids` 对应类型；全量来源看 evidence index | 不允许空值或空数组 | `["github_issue","tid"]` | 写文件名；把所有证据类型堆入；与 E 类型不一致 |
| 主模块 | `module_primary` | string | 是 | 否 | taxonomy 的 13 个模块或 `unknown` | 决定条目主要职责 | 用“删除后最直接消失的结果”判断 | 仅允许 `unknown`，并记录问题 | `"focus_page_state"` | 多主类；按文件目录分类；把 safety 当模块 |
| 辅助模块 | `module_secondary` | array<enum> 或空值状态 | 是 | 是 | taxonomy 模块，不含 `unknown` | 表示复用或受影响的其他职责 | 不得重复主模块；只记录有实质关系的模块 | 无辅助模块用 not_applicable；材料未说明用 null/unknown | `["stability_recovery"]` | 复制主模块；把所有可能模块都列上；用模块代替横切标签 |
| 平台组合 | `platforms` | array<enum> 或 `unknown` | 是 | 是 | `windows_edge`、`macos_chrome`、`platform_agnostic`、`cross_platform_core` | 限定需求证据适用平台，不表达成熟度 | Windows/Edge 与 macOS/Chrome 按实际证据标；两个具体平台可并列；agnostic/cross-platform 总结值必须单独使用；成熟度只看 status、confidence、releases 和 E 证据 | 不确定用 unknown；不允许 null/not_applicable | `["windows_edge"]` | 仅因代码看似通用标跨平台；由文件名或当前分支推断某平台已发布、未完成或 experimental；把总结值与具体平台混用 |
| 横切关注点 | `cross_cutting_concerns` | array<enum> 或空值状态 | 是 | 是 | taxonomy 定义的 14 个值 | 标记跨模块安全、隐私、兼容、可观测等约束 | 只标直接相关项；不代替模块、风险或状态 | 无横切项用 not_applicable；材料不足用 null/unknown | `["safety_guard","fail_closed"]` | 写 P0 或 module；为了检索把所有标签都加上 |
| 风险等级 | `risk_level` | string | 是 | 否 | `P0`、`P1`、`P2`、`experimental`、`unknown` | 描述失败后果 | 按 02 文件的判断问题重评历史 P 标签 | 仅允许 unknown，且记录缺口 | `"P0"` | 按实现难度、业务价值、标题 P 标签或排期填写 |
| 当前状态 | `status` | string | 是 | 否 | 11 个生命周期状态或 `unknown` | 表示 generated_at 时点进展 | 使用能证明进入状态的证据；跨平台状态差异大时拆项 | 仅允许 unknown，且记录缺口 | `"testing"` | 代码改了即 accepted；tag 存在即 released；把历史状态串写进字段 |
| 置信度 | `confidence` | string | 是 | 否 | `confirmed`、`estimated`、`uncertain`、`conflicting` | 描述核心事实的证据质量 | 按问题相关性和冲突情况判断；不是文档票数 | 不允许 | `"conflicting"` | 用 confirmed 表示完成；冲突时删掉一个说法；用风险值 |

`source_type` 固定枚举为：`source_code`、`automated_test`、`ci_result`、`build_script`、`release_artifact`、`runtime_log`、`git_commit`、`git_tag`、`github_issue`、`pull_request`、`prd`、`investigation_report`、`tid`、`implementation_report`、`acceptance_report`、`smoke_test`、`release_notes`、`readme`、`maintenance_document`、`baseline_handoff_document`、`environment_setup_report`、`user_operation_feedback`、`manual_historical_note`。

为避免生成器只读取表格中的简称，其他固定枚举完整列示如下：

```text
module:
core_automation, ocr_capture, keyword_rules, candidate_actions,
page_filter_refresh, calibration, mouse_interaction, focus_page_state,
cross_platform, stability_recovery, candidate_profile_parsing,
test_build_release, documentation_handoff

cross_cutting_concern:
safety_guard, privacy_compliance, fail_closed, backward_compatibility,
observability, performance, coordinate_dpi, human_in_the_loop,
rollback_fallback, data_integrity, page_state_integrity,
long_running_stability, licensing, maintainability

status:
proposed, investigating, designed, implementing, testing, accepted,
released, superseded, rejected, deferred, abandoned

risk:
P0, P1, P2, experimental

confidence:
confirmed, estimated, uncertain, conflicting
```

`unknown` 是 module primary、status 和 risk 允许的空值状态，不增加新的模块、生命周期状态或风险等级。

## 5. 问题、方案与约束字段

| 中文名称 | 英文字段名 | 数据类型 | 是否必填 | 是否允许多值 | 允许值 | 字段用途 | 填写规则 | 空值处理 | 示例 | 常见错误 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 原始问题 | `original_problem` | string、null 或 `unknown` | 是 | 否 | 非空文本或允许空值 | 保留最初可观察痛点，不被后期方案覆盖 | 尽量使用同期材料措辞，区分事实与解释 | 证据没写用 null；确认应有但找不到用 unknown；不允许 not_applicable | `"纯示例：页面焦点丢失后无法切到下一位。"` | 写成“新增某函数”；用后期架构解释覆盖现场问题 |
| 业务目标 | `business_goal` | string、null 或 `unknown` | 是 | 否 | 非空文本或允许空值 | 说明为什么值得解决 | 写用户/业务/安全结果，不写实现 | 同上；不允许 not_applicable | `"纯示例：避免重复处理同一候选人。"` | 把技术选型或测试数量当目标 |
| 用户场景 | `user_scenario` | string 或空值状态 | 是 | 否 | 非空文本、null、unknown、not_applicable | 限定触发者、环境、前置和可观察结果 | 产品行为写具体场景；纯内部工程能力可 not_applicable | 按三种空值定义 | `"纯示例：操作员在 Windows Edge 安全模式下运行。"` | 只写“用户使用功能”；把测试步骤当场景 |
| 已考虑替代方案 | `alternatives_considered` | array<string> 或空值状态 | 是 | 是 | 非空文本数组 | 记录当时确实被考虑的可行选项 | 每项应可由 D/E 证明，保留来源顺序 | 无证据提及用 null；疑似存在用 unknown；概念不适用用 not_applicable | `["纯示例：固定坐标","纯示例：运行期校准"]` | 复盘者事后补合理方案；用空数组；与 rejected_solutions 重复无解释 |
| 选定方案 | `selected_solution` | string 或空值状态 | 是 | 否 | 非空文本或三种空值 | 概括最终选用的方案，不复制实现细节 | 只在有设计/实现证据时填写；说明边界和回退 | 尚未选择且证据无值用 null；有迹象但不清楚用 unknown；无需方案用 not_applicable | `"纯示例：从已校准区域内取点恢复焦点。"` | 把计划当最终实现；把多个历史方案混成一个 |
| 决策理由 | `decision_rationale` | string 或空值状态 | 是 | 否 | 非空文本或三种空值 | 解释为什么选择该方案 | 优先同期 PRD/TID/Investigation/D 证据；后期解释要标明 | 按三种空值定义 | `"纯示例：避免依赖整页复制文本。"` | 由代码反推动机并写 confirmed；把业务目标原样重复 |
| 被拒绝方案 | `rejected_solutions` | array<string> 或空值状态 | 是 | 是 | 非空文本数组 | 记录明确排除的选项及必要原因 | 只收有拒绝证据的方案；可含 D/E 引用文本 | 按三种空值定义 | `["纯示例：失败时回退到旧全页复制"]` | 把“未选择”自动写成“被拒绝”；事后创造反面方案 |
| 不可轻易破坏约束 | `non_breakable_constraints` | array<string> 或空值状态 | 是 | 是 | 非空、可验证约束 | 保存安全门、兼容、隐私和回退底线 | 写成“必须/不得 + 条件 + 可验证结果”，并有证据 | 按三种空值定义 | `["纯示例：OCR 不可靠时不得执行真实动作。"]` | 把当前类名/函数名当永恒约束；写模糊口号；无证据扩大范围 |

## 6. 关系字段

| 中文名称 | 英文字段名 | 数据类型 | 是否必填 | 是否允许多值 | 允许值 | 字段用途 | 填写规则 | 空值处理 | 示例 | 常见错误 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 依赖 | `dependencies` | array<string> 或空值状态 | 是 | 是 | `R-xxx`、`D-xxx` 或带前缀 `package:`/`platform:`/`external:` 的非空引用 | 表示本需求成立或实施所需前置 | 优先引用规范 ID；外部依赖必须有命名空间 | 无依赖用 not_applicable；证据未提用 null；疑似有用 unknown | `["R-002","platform:windows_edge"]` | 用标题作关系键；把 related 当 dependency；无前缀自由文本 |
| 派生自 | `derived_from` | array<string> 或空值状态 | 是 | 是 | `R-xxx` | 表示本需求是一个或多个较宽上位需求的可独立验收细化 | 与每个父条目的 `decomposed_into` 互惠；允许多父；不得自引用；只依据需求语义和证据填写 | 已核对无父需求用 not_applicable；证据未记载用 null；疑似有但未确认用 unknown | `["R-002"]` | 把依赖、文档来源、TID Change 或旧实现写成父需求；只写一边；形成环 |
| 分解为 | `decomposed_into` | array<string> 或空值状态 | 是 | 是 | `R-xxx` | 表示本需求分解出的一个或多个可独立验收子需求 | 与每个子条目的 `derived_from` 互惠；允许多子；不得自引用；父子可同时有效 | 已核对无子需求用 not_applicable；证据未记载用 null；疑似有但未确认用 unknown | `["R-010","R-011"]` | 把 Implementation Change 当子需求；用派生表示后来替代；只写一边；形成环 |
| 相关需求 | `related_requirements` | array<string> 或空值状态 | 是 | 是 | `R-xxx` | 表示非层级、非依赖、非替代的显著关系 | 两边应对称；不得自引用 | 按三种空值定义 | `["R-004"]` | 用 legacy ID；只写一边；拿它代替派生、依赖或 supersedes |
| 替代了 | `supersedes` | array<string> 或空值状态 | 是 | 是 | `R-xxx` | 表示本条目取代的旧需求 | 与旧条目的 `superseded_by` 互惠；拆分/合并可多值 | 无替代关系用 not_applicable；未确认用 null/unknown | `["R-003"]` | 把普通实现升级写成需求替代；自引用；只写一边 |
| 被替代为 | `superseded_by` | array<string> 或空值状态 | 是 | 是 | `R-xxx` | 表示承接本条目的后继需求 | `status: superseded` 时必须实际非空；与后继 `supersedes` 互惠 | 非 superseded 且无关系用 not_applicable；疑似替代用 unknown | `["R-010","R-011"]` | status superseded 却为空；删除旧条目；用 release 名称代替 R ID |
| 决策引用 | `decision_ids` | array<string> 或空值状态 | 是 | 是 | `D-001` 起的规范 D 编号，无 000 或多余前导零 | 连接独立技术决策 | 每个 D 必须存在于未来决策/证据索引并链接相关 E | 无独立决策用 not_applicable；证据缺失用 null/unknown | `["D-001"]` | 把 commit hash 当 D；写 `D-000`；同一决定重复编号；决策没有证据 |

关系语义固定如下：`derived_from`/`decomposed_into` 是上位问题到可验收细化项的语义派生；`dependencies` 是成立或实施前置；`related_requirements` 是对称、非层级关联；`supersedes`/`superseded_by` 是需求边界被后继取代。父子需求可以同时有效，派生不自动触发 `superseded`。同一需求对不得同时使用派生、普通相关和替代关系。

关系中的 `R-xxx` 必须存在且不能自引用。派生关系与替代关系必须互惠，普通相关必须对称；派生图、依赖图和替代图分别不得有环。JSON Schema 只能检查字符串形状，不能检查存在性、互惠性和环，因此必须执行第 11 节的外部 lint。

## 7. 文档、代码、测试与发布证据字段

所有仓库路径使用相对于仓库根的 POSIX 路径：不以 `/` 开头，不含盘符、反斜杠或 `..`。历史文件当前不存在时仍可记录它在目标 commit 的路径，并在证据索引标明历史定位；不要把绝对路径 `F:\BOSSOCR\...` 写入数据。

| 中文名称 | 英文字段名 | 数据类型 | 是否必填 | 是否允许多值 | 允许值 | 字段用途 | 填写规则 | 空值处理 | 示例 | 常见错误 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 调查报告 | `investigation_documents` | array<path> 或空值状态 | 是 | 是 | 仓库相对 POSIX 路径 | 定位 Investigation Report | 只列实际调查材料，详细章节由 E 记录 | 按三种空值定义；通常无材料用 null | `["docs/INVESTIGATION_REPORT.md"]` | 写绝对路径；把所有报告塞入；认为报告结论就是实现 |
| PRD 文档 | `prd_documents` | array<path> 或空值状态 | 是 | 是 | 仓库相对 POSIX 路径 | 保存仓库实际存在的业务需求文档 | PRD 与 TID 分栏，局部 Rn 进 legacy_ids | 按三种空值定义 | `["PRD-calibration-template-module.md"]` | 把 PRD 当 TID；因被 ignore 就不记录；用当前文件时间定历史日期 |
| TID 文档 | `tid_documents` | array<path> 或空值状态 | 是 | 是 | 仓库相对 POSIX 路径 | 定位技术设计与 Change 计划 | 多版本均可列出，不能只保留最新版而隐藏修订 | 按三种空值定义 | `["docs/tid/next/Issue-Next-5-batch-filter-first-candidate-TID-V1.1.md"]` | TID 计划当最终实现；V1.1 当产品 release；路径用反斜杠 |
| 实施报告 | `implementation_reports` | array<path> 或空值状态 | 是 | 是 | 仓库相对 POSIX 路径 | 定位实施结果、环境和未完成事项 | 与 code/commit/test 交叉验证 | 按三种空值定义 | `["WINDOWS_OCR_IMPLEMENTATION_REPORT.md"]` | 报告自述替代代码；忽略其未完成部分 |
| 代码文件 | `code_files` | array<path> 或空值状态 | 是 | 是 | 仓库相对 POSIX 路径 | 指向实现该需求的主要代码 | 只列能支持核心结论的文件；具体行/commit 在 E | 按三种空值定义 | `["ocr_detector.py","simple_brush.py"]` | 列整个仓库；用文件存在证明动机；绝对路径 |
| 提交 | `commits` | array<string> 或空值状态 | 是 | 是 | 40 位小写 Git SHA-1 | 固定实现或文档证据快照 | 规范数据存完整 hash，界面可显示短 hash；顺序按提交时间 | 按三种空值定义 | `["0123456789abcdef0123456789abcdef01234567"]` | 只存 7 位导致歧义；存分支名；把提交时间当首次提出 |
| 自动化测试 | `tests` | array<string> 或空值状态 | 是 | 是 | 稳定测试 locator | 连接回归保护 | 建议 `tests/file.py::Class::method` 或文件级 locator；记录 mock 边界在 E | 按三种空值定义 | `["tests/test_ocr_detector.py::OCRDetectorTests::test_failure_closes"]` | 只写“263 tests passed”；复制一次性终端命令；当作真实 GUI 证明 |
| 冒烟测试 | `smoke_tests` | array<path/locator> 或空值状态 | 是 | 是 | 仓库相对路径或稳定外部 locator | 连接人工/低风险冒烟计划和结果 | 清单与执行结果用不同 E；字段可指同一文档不同证据 | 按三种空值定义 | `["docs/calibration-template-smoke-test.md"]` | 清单存在即认定通过；遗漏设备/平台/日期 |
| 验收报告 | `acceptance_reports` | array<path> 或空值状态 | 是 | 是 | 仓库相对 POSIX 路径 | 定位验收范围、结论和残余风险 | 核对是否仍有人工门禁待执行 | 按三种空值定义 | `["docs/Issue-calibration-template-module-acceptance-report.md"]` | 文件名含 acceptance 就设 accepted/released；不看结论范围 |
| 发布说明 | `release_notes` | array<path> 或空值状态 | 是 | 是 | 仓库相对 POSIX 路径 | 定位 release 的声明范围 | 必须在对应 tag/commit 上读取；与 releases/产物交叉 | 按三种空值定义 | `["docs/releases/windows-stable-v1.2.md"]` | 把 tag 写这里；用当前工作树内容倒推旧 tag |
| 发布标识 | `releases` | array<string> 或空值状态 | 是 | 是 | 精确 tag 或 Release 标识原文 | 连接需求到实际发布 | 不归一化覆盖 `Boss`、`v1.0.0`、`windows-stable-v1.1` 等原名；`released` 必须非空 | 未发布且仍可能发布用 null；终态不适用可 not_applicable；不清楚用 unknown | `["v1.2"]` | 把多套 tag 强行改成连续版本；本地构建名当 release；released 却为空 |
| 全量证据 ID | `evidence_ids` | array<string> | 是 | 是 | `E-001` 起的规范 E 编号，无 000 或多余前导零 | 连接所有核心事实到证据索引 | 至少一个、去重、按数值排序；覆盖问题、状态和关键结论 | 不允许空值或空数组 | `["E-001","E-004"]` | 悬空 E；写 `E-000`；只覆盖标题不覆盖状态；把 reviewer note 当证据；复制隐私日志原文 |

## 8. 失败、经验与评审字段

| 中文名称 | 英文字段名 | 数据类型 | 是否必填 | 是否允许多值 | 允许值 | 字段用途 | 填写规则 | 空值处理 | 示例 | 常见错误 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 已知失败 | `known_failures` | array<string> 或空值状态 | 是 | 是 | 非空文本数组 | 记录已发生或仍存在的失败模式与作用域 | 区分历史已修复、当前残留和未验证；关联 E/R | 按三种空值定义 | `["纯示例：特定页面中间状态下安全停止。"]` | 把推测写成发生过；隐藏已知限制；复制敏感数据 |
| 经验教训 | `lessons_learned` | array<string> 或空值状态 | 是 | 是 | 非空文本数组 | 提炼可由证据支持、对未来有用的原则 | 写清事实基础和适用范围，不写泛化口号 | 按三种空值定义 | `["纯示例：人工检查清单与执行结果必须分开记录。"]` | 事后美化；把个人偏好写成普遍结论；无证据 |
| 开放问题 | `open_questions` | array<string> 或空值状态 | 是 | 是 | 非空文本数组；冲突用固定前缀 | 保存真正影响分类、日期、状态、因果或验收的未知项 | 冲突格式 `[CONFLICT:<主题>] ...`；问题应可回答并说明所需证据 | 无问题且完成复核用 not_applicable；证据未查完用 unknown；材料无记录用 null | `["[CONFLICT:人工冒烟] E-010 记为待执行；E-020 记为通过；需核对设备记录。"]` | 用问题逃避可直接判断事项；写 TBD；冲突不列双方 E |
| 评审备注 | `reviewer_notes` | array<string> 或空值状态 | 是 | 是 | 非空文本数组 | 记录复盘者的范围限定、临时主结论和人工决定 | 明确“复盘解释”而非原始事实；不能替代 E | 无备注且已复核用 not_applicable；未评审用 unknown；材料没有备注不应误用 null | `["复盘说明：纯示例标题为中性改写，未改变来源语义。"]` | 当作证据；写未经标识的历史事实；清除冲突痕迹 |
| 条目扩展 | `extensions` | object | 是 | 是 | `{}` 或带命名空间的键值 | 容纳实验性消费者字段而不放开任意属性 | 键使用 `x-...` 或至少含一个点的命名空间；核心字段不得重复 | 无扩展使用 `{}`；这是容器空态，不使用 null/unknown/not_applicable | `{"prototype.group":"safety"}` | 随意新增顶层字段；用扩展绕过 enum；消费者依赖未版本化扩展 |

## 9. 日期精度规则

| `date_precision` | `first_observed_date` 格式 | 语义 |
| --- | --- | --- |
| `exact_day` | `YYYY-MM-DD` | 证据直接支持具体日 |
| `exact_month` | `YYYY-MM` | 只支持到月份，不补日 |
| `approximate_range` | `YYYY-MM-DD/YYYY-MM-DD`、`YYYY-MM/YYYY-MM` 或允许两端精度不同的同类闭区间 | 首次出现只能限定在闭区间内；范围起点不得晚于终点 |
| `sequence_only` | `sequence:<正整数>` | 只能确定相对顺序；序号是本次复盘排序键，不是历史日期或需求 ID |
| `unknown` | JSON null 或字符串 `unknown` | 当前无法给出时间或顺序 |

若后续发现更早材料，更新 `first_observed_date` 和证据，但不更改 `requirement_id`。日期精度提升或降低都必须更新 `first_observed_evidence_ids`。新文件的创建时间、当前文件修改时间和 `git log --follow` 的首次可见提交都只能按其实际证明范围使用。

## 10. 编号规则

### 10.1 `R-xxx` 主编号

- 格式为大写 `R-` 加规范十进制序号：1 至 999 固定三位（`R-001`…`R-999`），1000 起不再补前导零（`R-1000`）。`R-000`、`R-0001` 和含换行/空白的值非法。
- 数字只表示台账分配顺序，不编码模块、平台、年份、风险、状态或 release。
- 首批抽取先完成候选项去重和粒度评审，再按可证明的首次顺序、证据位置作稳定排序并依次编号；一旦编号进入人工评审或规范台账，就不可重排。
- 后来发现更早的历史需求时使用下一个未用编号，不插号、不重排既有编号。
- 标题、摘要、模块、状态、日期或证据变化都不更改主编号。

### 10.2 旧编号映射

现有编号全部保留在 `legacy_ids`，并加命名空间：

```text
github_issue:#1
github_issue:#5
roadmap:Next-3
prd:PRD-and-Codex-Prompt-Favorite-Action-Mode#R4
label:Hotfix P0 double-focus-restore
```

这些是格式示例，不表示已建立对应正式条目。`Next-3` 与 GitHub Issue `#5` 已被仓库材料证明属于不同编号空间；PRD 内 `R1…R7` 是局部小节号。本轮当前材料没有发现 `R26`、`R27`，这不是错误，也不允许凭外部记忆建项；下一阶段全面扫描仍无仓库或远端证据时应省略。若原开发者后来补充，先建立 `source_type: manual_historical_note` 的 `E-xxx`，再根据是否真实提出、实施、延期或放弃判断是否建立 R；确认其旧编号身份后才以带来源命名空间的原文写入 `legacy_ids`。P0/P1/P2 单独出现时是历史风险/优先级标签，不是 legacy ID；只有像 `Hotfix P0 double-focus-restore` 这样实际被用作事项标识的完整原文才可按 `label:` 保留。

### 10.3 合并、拆分和替代

- 语义不变的改名、文档修订或实现重写保留原 `R-xxx`。
- 拆分：原条目保留并设为 `superseded`；每个可独立验收的新语义获得新 ID。原条目的 `superseded_by` 与新条目的 `supersedes` 双向记录。
- 合并：默认建立一个新 ID 承接合并后的新边界，旧条目均保留并设为 `superseded`。只有证据明确表明其中一项语义原封不动延续、其他只是重复记录时，才由人工决定保留一个既有 ID。
- 重复项：不删除已进入评审的 ID；保留重复条目和到规范条目的替代/评审说明，避免外部链接失效。
- 后继只改变实现而不改变可观察需求时，不建立新 R，也不使用 supersedes；通过 D/E/commit 记录实现演进。
- 上位 Business Need 首次细化为多个可同时成立的需求时使用 `decomposed_into`/`derived_from`，不是拆分替代；只有后来的新边界取代旧边界才按上述拆分/合并规则使用 supersedes。

### 10.4 删除与复用

已经分配并进入人工评审或规范数据的编号永不复用。条目应按证据标为 `rejected`、`abandoned` 或 `superseded` 并保留。如果在首次对外评审前发现纯录入错误，仍不得把该号码发给另一需求；允许形成编号空洞，并在评审记录中说明。不得为了让编号连续而重写历史引用。

### 10.5 决策和证据编号

- 技术决策使用独立 `D-001`、`D-002` 序列，记录方案、替代项、理由和证据；需求通过 `decision_ids` 引用。
- 证据使用独立 `E-001`、`E-002` 序列；需求通过 `first_observed_evidence_ids` 和 `evidence_ids` 引用。
- R、D、E 各自单调递增、永不复用，数字相同不表示三者自动相关。
- commit、tag、Issue、Next 和 PRD 局部 Rn 保留其原始身份，不转换成 D/E 数字。

## 11. 跨格式序列化与外部校验

### 11.1 JSON

- UTF-8、标准 JSON、不得使用注释或尾逗号。
- 根和 requirement 对象拒绝未定义字段，只有 `extensions` 开放。
- `requirements` 按 R 数字排序；R/D/E 引用按数值排序；路径按字典序；有语义顺序的 alternatives/constraints 保留来源顺序。
- HTML 原型直接读取 JSON，并在加载前校验 `schema_version`、`project` 和 Schema。

### 11.2 CSV

- UTF-8，一行一个 requirement，共 48 列；表头严格按下列规范顺序。该顺序与 Schema 的 `required`/`properties` 排列一致，不以本文各主题表格的展示顺序推断：

```text
requirement_id, legacy_ids, title, summary, requirement_type,
first_observed_date, date_precision, first_observed_evidence_ids, source_type,
original_problem, business_goal, user_scenario,
module_primary, module_secondary, platforms, cross_cutting_concerns,
risk_level, status, confidence,
alternatives_considered, selected_solution, decision_rationale,
rejected_solutions, non_breakable_constraints,
dependencies, derived_from, decomposed_into, related_requirements,
supersedes, superseded_by, decision_ids,
investigation_documents, prd_documents, tid_documents, implementation_reports,
code_files, commits, tests, smoke_tests, acceptance_reports, release_notes,
releases, evidence_ids, known_failures, lessons_learned, open_questions,
reviewer_notes, extensions
```

- 根 metadata 不复制到每行，因此 CSV 是生成视图，不作为单独反向恢复根 metadata 的事实源。
- JSON null 写字面量 `null`；`unknown`、`not_applicable` 写原字符串；禁止空单元格。
- 数组和 `extensions` 使用紧凑 JSON 文本，再按 RFC 4180 对整个单元格引号转义。禁止用逗号、分号、换行或竖线自行 join。
- 标量文本含逗号、引号或换行时按 RFC 4180 转义；不得为了 CSV 方便改写原值。

### 11.3 Markdown

- 从 JSON 生成，不手工维护事实。
- 可把数组渲染为列表或 `<br>`，但必须保持元素边界和顺序。
- 表格单元格先进行 HTML 文本转义，再把 Markdown 管道符转义为 `\|`；字段内部换行确定性渲染为 `<br>`。生成器不得把未转义的 HTML 当展示指令，也不得从 Markdown 反向恢复规范 JSON。
- null、unknown、not_applicable 必须显示为三个可区分的标签，不可都渲染为空白或 `—`。
- `conflicting` 条目必须显示冲突提示和对应 E 引用。

### 11.4 JSON Schema 之外的 lint

标准 JSON Schema 不能验证跨对象与仓库事实，后续生成器还必须检查：

1. `requirement_id` 全局唯一且从不复用；
2. R/D/E 引用存在且无自引用；`derived_from` 与 `decomposed_into` 互惠，`related_requirements` 对称，`supersedes` 与 `superseded_by` 互惠；同一需求对不混用派生、普通相关和替代关系；派生图、依赖图和替代图分别无环；
3. `first_observed_evidence_ids` 是 `evidence_ids` 的子集，`source_type` 与对应 E 类型一致；
4. `module_secondary` 不含 `module_primary`；`platform_agnostic`/`cross_platform_core` 不与具体平台混用；
5. 使用真正的 RFC 3339/日历解析器复核 `generated_at` 和日期字段，不能只依赖 JSON Schema `format`；月份、日、闰年合法，`approximate_range` 起点不晚于终点；
6. repo path 无换行、盘符、反斜杠和 `..`，且在当前或目标 commit 可解析，或由证据索引明确标为历史缺失/本地未跟踪；
7. commit 是无换行、可解析的完整 hash，R/D/E ID 非 000、无多余前导零；tag/release 标识能与目标 commit 和产物证据对应；
8. `status: superseded` 有后继，`status: released` 有 releases；
9. classification、日期或关系字段使用 `unknown` 时，`open_questions` 有对应可回答问题；`confidence: conflicting` 时至少有一个 `[CONFLICT:...]` 项；
10. 不把候选人姓名、简历、邮箱、截图或敏感日志原文复制进台账；
11. JSON、CSV、Markdown 的字段和值在一次生成后进行逐条 round-trip/投影一致性比较。

## 12. 条目准入模板

下一轮只有在候选项满足以下最小条件时才进入正式台账：

- 有可去重的中性 title 和 summary；
- 至少一个可定位 `E-xxx`；
- 能给出 requirement_type、module_primary、risk、status 和 confidence，或按本字典显式使用允许的 unknown；
- 首次时点绑定到 `first_observed_evidence_ids`；
- 旧编号按命名空间保存，未发现则明确空值状态；
- 没有把纯 Change、commit、测试或 release event 自动升级为需求；
- 所有规范字段键均存在，且 Schema 与外部 lint 通过。

本节只是下一阶段的准入规则，本轮不得据此创建或填充正式需求条目。
