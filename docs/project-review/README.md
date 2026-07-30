# BossOCR 项目复盘规则入口

## 目录用途与当前阶段

本目录是《BossOCR 项目复盘与原型图制作计划》的规则与数据契约入口。它先冻结“复盘什么、如何分类、如何判断状态与证据、台账如何编码”，再允许后续流程读取仓库并生成需求事件数据。

当前已完成：

- 阶段 0：冻结复盘目标、受众与交付边界；
- 阶段 1：建立需求分类、状态、风险、证据与字段规范；
- 阶段 2A：递归盘点当前仓库、其他分支、重要历史对象与可访问的远程对象，并登记全文阅读状态和资料缺口。

当前仍没有正式需求或证据条目，两份 Schema 的示例根对象分别保持 `requirements: []` 与 `evidence: []`、`decisions: []`。`source-inventory.*` 中的 `SRC-xxx` 只是在阶段 2A 内定位资料的来源编号，不是正式 `R-xxx`、`D-xxx` 或 `E-xxx`。完成资料盘点不代表任何历史需求已经被识别、合并、编号或验收。

## 唯一事实数据源

> 需求台账是流程图和原型的唯一事实数据源。
> 流程图和原型不得独立维护一套需求事实。

后续以 `requirement-ledger.json` 作为需求台账的规范序列化；`requirement-ledger.csv`、`requirement-ledger.md`、流程图、HTML 原型和静态导出均由同一份经确认的数据生成。展示层可以增加布局、筛选、聚合和叙事，但不得新增、删改或覆盖需求事实。证据与决策详情由 `evidence-index.json` 提供，并分别通过 `E-xxx`、`D-xxx` 与台账关联。

需求层级也属于台账事实：`derived_from` 与 `decomposed_into` 保存业务需要到可独立验收需求的派生关系。演进图和原型只读取这些字段，不得根据标题、日期、目录或叙事顺序自行推断父子关系；生成前必须通过互惠、无自引用与无环 lint。

## 文件职责

| 文件 | 层次 | 职责 | 规范性 |
| --- | --- | --- | --- |
| `README.md` | 规则入口 | 说明阶段、文件关系、门禁、更新顺序和消费约束 | 规范性 |
| `00-review-scope.md` | 规则源 | 冻结目标、读者、核心问题、交付边界、复盘原则和本轮 Git 基线 | 规范性 |
| `01-requirement-taxonomy.md` | 规则源 | 定义纳入判据、需求与非需求事件、模块、平台、类型和标签 | 规范性 |
| `02-status-risk-evidence-definition.md` | 规则源 | 定义状态、风险、证据类型、可信度、问题相关的证据选择和冲突处理 | 规范性 |
| `03-requirement-ledger-field-dictionary.md` | 规则源 | 定义编号、字段、空值、关系、路径和 CSV/JSON/Markdown 编码规则 | 规范性 |
| `requirement-ledger.schema.json` | 机器规则源 | 以 JSON Schema Draft 2020-12 约束规范 JSON 的根结构、字段和枚举 | 规范性 |
| `evidence-index.schema.json` | 机器规则源 | 以同一 Schema 版本约束证据、决策、路径、日期、置信度和扩展区 | 规范性 |
| `source-inventory.json` | 发现数据源 | 阶段 2A 的规范资料清单，记录来源定位、Git/文件时间、哈希、读取状态、可证明边界与访问问题 | 描述性，不是需求事实 |
| `source-inventory.csv` | 发现数据视图 | 从同批数据生成的一行一来源 CSV，供人工筛选和后续批处理 | 生成视图，不单独维护 |
| `source-reading-log.md` | 阅读登记 | 按主题记录已发现资料的阅读摘要、可证明事实与待交叉验证点 | 描述性 |
| `source-gaps.md` | 缺口登记 | 记录远程不可访问、版本关系、时间、平台状态、发布资产和人工材料缺口 | 描述性 |

语义解释以对应 Markdown 规则为准，机器可接受结构以 JSON Schema 为准。两者不一致时不得自行选择其一继续抽取；应先修正规则和 Schema，使其在同一次 `schema_version` 更新中重新一致。

## 后续预计生成的文件

| 文件或产物 | 层次 | 生成关系 |
| --- | --- | --- |
| `requirement-ledger.json` | 规范数据源 | 按字段字典和 Schema 生成，人工确认后成为需求事实主文件 |
| `requirement-ledger.csv` | 数据视图 | 从规范 JSON 无损导出，一行一个 `R-xxx` 条目 |
| `requirement-ledger.md` | 数据视图 | 从规范 JSON 生成的便于人工评审版本，不单独维护 |
| `evidence-index.json` | 证据数据源 | 按证据 Schema 保存 `E-xxx` 证据、定位、可复核状态和 `D-xxx` 决策记录 |
| 标准需求分析流程图 | 展示层 | 读取已确认台账与规则，不写回新事实 |
| 项目需求演进图 | 展示层 | 读取日期、`derived_from`/`decomposed_into`、替代关系、状态和 release 数据 |
| 重点需求追溯图 | 展示层 | 读取需求、决策、代码、测试、验收和发布引用 |
| 原型信息架构 | 展示层设计 | 只组织已确认数据的页面与导航 |
| 低保真可点击原型 | 展示层 | 读取规范 JSON 或其确定性转换结果 |
| 高保真复盘原型 | 展示层 | 在低保真路径确认后制作 |
| SVG、PNG、PDF 静态导出 | 展示层导出 | 从确认后的图和原型生成 |
| 最终事实验证报告 | 复核产物 | 记录外部展示前的逐项事实与证据复核 |

规则源定义“允许怎样记录”；数据源记录“仓库证据支持了什么”；展示层只负责“怎样呈现”。CSV、Markdown 和 HTML 不是并列事实库。

## 阶段门禁

1. 范围与分类体系未确认，不进入需求抽取；
2. 需求台账未人工确认，不进入流程图制作；
3. 流程图结构未人工确认，不进入原型设计；
4. 低保真路径未确认，不进入高保真；
5. 事实复核未完成，不对外正式展示。

“人工确认”必须留下可定位的评审记录；仅有文件生成成功、Schema 校验通过或自动化测试通过不等同于人工确认。

## 更新顺序和依赖关系

规则变更按以下顺序执行：

1. 先修改 `00-review-scope.md` 中受众、目标或边界；若这些内容不变，不应为了字段调整而改写范围。
2. 再修改 `01-requirement-taxonomy.md` 中概念、模块、平台、类型或标签。
3. 再修改 `02-status-risk-evidence-definition.md` 中状态、风险、证据和冲突规则。
4. 再修改 `03-requirement-ledger-field-dictionary.md` 中字段语义与序列化约束。
5. 同步修改 `requirement-ledger.schema.json` 与 `evidence-index.schema.json`，校验共享术语、枚举、ID 和日期规则完全一致；破坏兼容性的修改必须提升对应 `schema_version`。
6. 对现有台账与证据索引执行迁移、引用检查和关系 lint，人工确认后才重新生成 CSV、Markdown、图和原型。

阶段 2A 的发现资料按 `source-inventory.json` → `source-inventory.csv` / `source-reading-log.md` → `source-gaps.md` 的顺序更新。CSV 不允许手工产生与 JSON 不一致的条目；资料缺口解决后，应先更新来源清单和读取状态，再进入对应需求事实的抽取与复核。

不得先修改展示层，再反向把展示需要包装成历史事实。不得手工修补生成后的 CSV、Markdown、流程图或 HTML 来绕过规范 JSON。

## 当前阶段禁止进行的工作

阶段 2A 完成后、正式需求抽取获准前仍禁止：

- 批量抽取历史需求或分配正式 `R-xxx`；
- 创建或填充正式 `requirement-ledger.csv`、`requirement-ledger.json`、`requirement-ledger.md` 或 `evidence-index.json`；
- 绘制 Mermaid、draw.io 或其他流程图；
- 制作低保真、高保真或 HTML 原型；
- 修改业务代码、测试代码、现有 README、TID、报告、发布文档、工作流、构建或打包脚本；
- 创建 commit、tag、Release 或推送远程。

允许在规则文件中使用明确标注为“纯示例”的虚构条目，但示例不得被后续程序当成 BossOCR 历史事实。

## 后续消费约束

- 消费程序必须先检查根对象的 `schema_version` 和 `project`，不支持的版本应明确失败。
- `requirement_id`、`D-xxx` 和 `E-xxx` 是连接键；标题、文件路径和 release 名称都不是稳定主键。
- `derived_from`/`decomposed_into` 是有向互惠关系；消费者不得用 `dependencies`、`related_requirements` 或 `supersedes` 猜测需求层级。
- 数组、`null`、`unknown` 与 `not_applicable` 必须按字段字典解释，不得在展示层合并为空白。
- `confidence: conflicting` 的结论必须显示冲突提示；不得在图或原型中静默选择更顺故事的说法。
- `extensions` 中的数据默认不是跨消费者契约；核心事实若被多个产物依赖，必须先提升为正式字段并更新 Schema。
