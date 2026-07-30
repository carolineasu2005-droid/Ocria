# 阶段 1：状态、风险与证据定义

## 1. 使用总则

`status`、`risk_level`、`confidence` 和 `requirement_type` 是四个独立维度：

- `status`：在台账 `generated_at` 时点，需求走到了哪里；
- `risk_level`：该需求相关能力失败时的后果；
- `confidence`：复盘核心结论得到怎样的证据支持；
- `requirement_type`：这是什么性质的需求中心条目。

不得用 P0 表示“马上做”，不得用 `accepted` 表示“代码看起来完成”，不得用 `confirmed` 表示“风险很高”，也不得用 `defect` 代替状态。

同一需求在不同平台有实质不同状态时，原则上拆分平台条目并建立关系；例如在证据已经分别确认“平台 A 已发布、平台 B 未开始”的纯条件场景中，不得把二者压成一个含糊状态。`status` 是当前状态，不是完整历史；历史发布仍保存在 `releases` 和证据中，被替代后当前状态可为 `superseded`。

## 2. 需求状态

规范状态：

```text
proposed
investigating
designed
implementing
testing
accepted
released
superseded
rejected
deferred
abandoned
```

证据不足以选择状态时可以使用空值状态 `unknown`，但 `unknown` 不是生命周期状态，必须在 `open_questions` 说明缺口。

### 2.1 状态判定表

| 状态 | 准入条件 | 退出条件 | 可用证据 | 与相邻状态的区别 |
| --- | --- | --- | --- | --- |
| `proposed` | 已有可识别的问题、目标或预期结果，至少一个 `E-xxx` 证明它被提出；尚无证据表明进入系统调查或方案冻结 | 开始调查进入 `investigating`；方案已冻结进入 `designed`；也可进入 `rejected`、`deferred` 或 `abandoned` | GitHub Issue、PRD、用户反馈、Manual Historical Note、早期 README/计划 | 不是随口猜测；与 `investigating` 的差别是尚未形成有证据的调查活动，与 `designed` 的差别是尚无选定方案和验收边界 |
| `investigating` | 有明确调查范围，正在确认根因、现状、约束、替代方案或实机事实 | 形成可执行设计进入 `designed`；直接实施进入 `implementing`；确认不做可进入 `rejected`、`deferred` 或 `abandoned` | Investigation Report、代码审计、运行日志、用户操作反馈、实验结果、Issue 讨论 | 不等于已有方案；调查结论可以为 `confirmed`，但需求状态仍可能只是 `investigating` |
| `designed` | 已记录选定方案、范围/非目标、主要约束和可验证标准；尚无可靠证据表明实施已开始 | 首个与方案有关的实现改动进入 `implementing`；决定暂缓/放弃/拒绝则进入对应状态 | TID、PRD、`D-xxx` 决策、批准的 Issue/PR 设计讨论 | 与 `investigating` 的差别是方案和验收边界已收敛；与 `implementing` 的差别是不能仅凭计划中的 Change 或 commit 计划声称已开工 |
| `implementing` | 至少有一个可定位实现改动正在满足该需求，且完整实施/测试门禁尚未完成 | 实现范围具备验证条件进入 `testing`；停止则进入 `deferred` 或 `abandoned` | 目标 commit、source code、Implementation Report、PR 变更 | “代码已修改”最多证明进入实现，不证明测试、验收或发布；局部单测随代码提交也不自动进入 `testing`，除非实现范围已准备验收 |
| `testing` | 预定实现范围已进入系统验证，正在执行自动化、CI、构建、手工冒烟或验收核对；仍有必需验证未结束 | 所有适用验收条件满足进入 `accepted`；发现问题可回到 `implementing`；暂停/停止进入 `deferred`/`abandoned` | automated test、CI result、构建结果、Smoke Test 执行记录、Acceptance Report 草稿、人工反馈 | 测试命令存在或清单写好不等于已执行；若真实 GUI 冒烟是验收条件而仍待执行，不能因为 263 项单测通过就进入 `accepted` |
| `accepted` | 所有适用验收标准已有明确结论；需要的自动化、实机或人工验证均完成，残余风险已记录；结论可与实现证据交叉验证 | 形成并确认发布事实后进入 `released`；后续被替代进入 `superseded`；验收发现失实时回到 `implementing`/`testing` | Acceptance Report、通过的测试/CI、实际 Smoke Test 结果、目标 commit、人工操作反馈 | 与 `testing` 的差别是不存在未完成的必需验收；与 `released` 的差别是尚不能证明已形成或分发目标发布产物 |
| `released` | 有证据证明需求包含在特定可识别发布中；至少能连接目标代码快照与 tag、产物或 Release 事实，外部分发声称还需产物/发布证据 | 后续由新需求替代进入 `superseded`；普通缺陷不会抹去历史 release，应另建/关联缺陷 | Git tag、release artifact、hash/manifest、Release Notes、CI 发布结果、GitHub Release、目标 commit | tag 单独只能证明 ref；release notes 单独只能证明声明。`released` 不等于没有已知缺陷，也不表示所有平台均发布 |
| `superseded` | 有明确后继需求、设计或行为替代本条目；`superseded_by` 至少包含一个有效 `R-xxx`，且证据说明替代关系 | 终态；只有发现分类错误或替代判断被撤销时经人工复核更正 | 后续 TID/PRD/决策、代码行为变化、验收、release、明确的弃用说明 | 与 `abandoned` 的差别是存在后继；与 `released` 的差别是它可以曾经发布，但当前规范行为已由别的需求承接 |
| `rejected` | 在采纳或实质实施前，经过评估后明确决定不做，并记录理由 | 终态；若未来重新提出，原则上建立新 `R-xxx` 并关联旧条目，除非人工决定恢复原条目 | Issue 关闭理由、决策记录、PRD/TID 评审、维护者明确记录 | 与 `deferred` 的差别是当前决定为“不采纳”；与 `abandoned` 的差别是通常未进入实质实施 |
| `deferred` | 需求仍被认为有效，但因时机、资源、依赖或风险明确暂缓；应记录恢复条件或未知项 | 恢复工作后进入 `proposed`、`investigating`、`designed` 或 `implementing`；明确不做则 `rejected`/`abandoned` | Issue 状态、评审记录、路线说明、依赖阻塞证据 | 不是“没有最近 commit”；与 `abandoned` 的差别是仍保留恢复意图，与 `proposed` 的差别是已有明确暂缓决定 |
| `abandoned` | 已经开始调查、设计或实施，但明确停止，且没有被另一个需求承接；或原意图失效并不再继续 | 终态；重新启动时默认建立新条目并关联，人工确认语义完全相同才可恢复 | 关闭说明、停止实施的 commit/PR、维护者记录、后期基线的明确排除 | 与 `rejected` 的差别是通常已有投入或曾被采纳；与 `superseded` 的差别是没有后继需求承接 |

### 2.2 状态证据规则

- 选择能证明“进入该状态”的证据，而不是只证明前一阶段发生过的材料。
- 当前工作树内容不能自动证明历史时点状态；应查看目标 commit 或 tag 快照。
- Acceptance Report 标题中的“验收”不是自动准入。若报告写明“自动化通过、真实 GUI 冒烟待执行”，且 GUI 是验收条件，状态仍为 `testing`。
- Smoke Test 清单只证明计划；必须有日期、执行环境和结果才证明人工冒烟通过。
- release notes 写“包含”需要与 tag/commit/产物交叉验证；本地 one-dir 构建不能证明 ZIP、tag 或 GitHub Release 已创建。
- 后期发现 defect 不把原需求自动降回 `implementing`；保留其 release 历史，另建缺陷或后继需求。

## 3. 风险等级

> 风险等级描述失败后果，不等同于实现难度，也不等同于业务价值。

风险以“该需求所保护的行为失败时会发生什么”判断，不以文件中的历史 P 标签机械复制。历史 `[P0]`、`[P1]`、`[P2]` 先保留为证据，再由本节规则重新分类。修复优先级还受暴露概率、可检测性、可回退性、依赖和发布时间影响；需求价值还受用户收益与战略影响，二者都不是 `risk_level`。

### 3.1 P0

- 定义：影响核心链路，可能导致错误操作、数据错误、账号风险、无法停止或不可控行为，或者会让程序在错误候选人上执行动作。
- 判断问题：失败是否可能把另一个候选人的内容归给当前人？是否可能真实收藏/转发错误对象？Esc 或安全门是否可能失效？错误能否在动作前可靠阻断？是否涉及账号、隐私或不可逆外部副作用？
- BossOCR 场景示例：旧 `Ctrl+A/C` 全页文本使底层候选人关键词触发当前候选人转发；`--no-forward` 看似启用但仍可能进入真实转发；焦点未恢复导致右方向键无效并重复处理同一候选人；页面中间状态下继续盲点可能操作错误对象。
- 常见误判：因为改动代码多就定 P0；因为标题带 Hotfix/P0 就不重新评估；把单纯启动失败定 P0，尽管它安全地在任何真实动作前停止。
- 与优先级/价值的区别：低开发成本的安全门也可为 P0；高价值新功能若失败只是不提供功能，未必是 P0。

### 3.2 P1

- 定义：重要功能失效、跨平台阻塞、稳定性严重下降、长时间运行失败，或者存在大面积回归风险，但通常不会直接在错误候选人上产生不可逆动作。
- 判断问题：核心浏览、OCR、校准或目标平台是否被阻断？长运行是否会大面积停滞？错误是否迫使人工中止但仍能保持安全？改动是否影响多个关键路径且回归面大？
- BossOCR 场景示例：窗口识别无法可靠置前目标浏览器，导致自动化无法运行但安全停止；候选人切换长期不稳定、模板兼容错误阻断目标设备运行；若已有证据表明某目标平台被承诺支持而该路径完全不可用、但系统仍能安全停止；批次刷新后无法继续浏览且不执行错误动作。
- 常见误判：只要跨平台就定 P1，即使该平台从未承诺支持；把可通过明确回退开关规避的局部体验问题夸大为核心阻断；把潜在 P0 后果因发生概率低而降为 P1，却没有记录概率和安全闸。
- 与优先级/价值的区别：P1 可能需要先于高价值 P2 优化修复，也可能因未进入承诺平台而延期；风险本身不决定排期。

### 3.3 P2

- 定义：效率、体验、可维护性、可观测性、文档性或局部稳定性优化；失败通常不会破坏核心正确性或造成错误候选人动作。
- 判断问题：失败是否主要增加人工成本、配置复杂度、诊断难度或轻微延迟？是否有稳定回退且核心链路仍正确？影响是否局部、可见并易于人工纠正？
- BossOCR 场景示例：`any(...)` 减少大量重复规则配置；可观察鼠标轨迹和 `--simple-mouse` 回退；日志、字段注册表、维护文档和提示文案改进；不影响落点正确性的轻微移动观感问题。
- 常见误判：因为功能“只是体验”就忽略它可能造成误点的 P0 后果；把所有文档、测试和构建事项都默认为 P2，而不检查它们是否是发布阻断或安全门。
- 与优先级/价值的区别：P2 可以有很高业务价值并优先交付；它只说明失败后果相对可控。

### 3.4 experimental

- 定义：尚未进入稳定版本，仍处于调查、原型或验证阶段，且当前证据不足以对稳定运行失败后果作可靠 P0/P1/P2 归类的能力。
- 判断问题：能力是否明确标为 beta/实验/计划？是否缺少目标平台、真实页面或稳定发布证据？失败边界是否仍在探索，尚不能合理量化？
- BossOCR 场景示例：某个平台移植能力只有技术探针或原型，且完成跨分支核对后仍缺少实现、验收、构建与稳定发布证据时，才可考虑归为 `experimental`；只完成技术探针、尚未进入稳定版本的其他能力同理。
- 常见误判：把所有 `investigating` 状态都设为 experimental；用 experimental 隐藏已知 P0 后果；功能一旦有原型就声称已进入平台支持。
- 与优先级/价值的区别：`experimental` 是临时成熟度/证据桶，不是第四档严重度。即使功能仍实验，只要失败后果已经能判断，就应使用 P0/P1/P2，并用 `status` 表达阶段。

## 4. 证据类型

所有证据都应在未来 `evidence-index.json` 获得 `E-xxx`，记录仓库相对路径或外部定位、目标 commit、章节/行、是否被 Git 跟踪、声明范围和底层材料是否仍可复核。台账只保存引用，不复制含候选人隐私的日志或截图原文。

| `source_type` | 定义及适合证明的问题 | 不能单独证明的内容 |
| --- | --- | --- |
| `source_code` | 目标 commit 下的实际逻辑、数据结构、默认值和调用路径 | 当时为什么选择该方案；真实 GUI 一定按预期工作；代码已发布 |
| `automated_test` | 被覆盖输入、分支、调用约束和回归保护；需记录是否 mock 外部副作用 | 未覆盖场景、真实 BOSS 页面、真实邮件、人工观感或发布完成 |
| `ci_result` | 特定 commit 和 workflow run 在特定环境的执行结果 | workflow 未覆盖的步骤；产物内容；当前文件仍与当时 workflow 一致 |
| `build_script` | 构建、测试、打包和冒烟的预期步骤与参数 | 脚本曾成功执行；产物已生成或上传；引用路径仍有效 |
| `release_artifact` | 实际 ZIP/EXE、manifest、hash 与可检查内容 | 动机、首次提出时间；若无可信来源和 hash，也不能证明对外分发 |
| `runtime_log` | 特定运行中的顺序、错误和观察值；BossOCR 日志可能包含候选人隐私 | 一般性设计动机；未出现即不存在；脱离版本/环境的普遍结论 |
| `git_commit` | 某个快照发生的差异、作者记录和提交先后 | 需求首次出现时间；完整验收；commit message 所称功能一定正确 |
| `git_tag` | 一个不可变或当前可解析 ref 指向的 commit 及 tag 元数据 | 对应 artifact 已上传、release notes 正确、tag 之前未被移动 |
| `github_issue` | 问题提出、讨论、标签、关闭理由和时间线 | 最终代码或发布内容；Issue 号与 Next 号自动相同 |
| `pull_request` | 方案讨论、审查、diff 范围、合并和检查上下文 | 未合并实现已生效；外部发布完成 |
| `prd` | 业务背景、目标、非目标、用户流程和验收意图 | 最终技术方案、实现或发布；PRD 内局部 `R1` 是全局编号 |
| `investigation_report` | 调查范围、现场材料、根因解释、排除假说和建议验收 | 建议已经实施；底层日志仍可复核；所有文中推断均为事实 |
| `tid` | 技术意图、方案、Change 拆分、测试计划、风险和回滚 | Change 已实施、测试已执行、最终行为与计划完全一致 |
| `implementation_report` | 实施范围、修改文件、环境、测试结果、已验证和未完成事项 | 独立证明作者动机或对外发布；报告引用的底层结果仍存在 |
| `acceptance_report` | 具名范围的验收结论、标准对照、测试和残余风险 | 自动等于 `released`；报告标题自动证明所有人工验收均完成 |
| `smoke_test` | 冒烟前置条件、步骤；有执行记录时可证明目标环境人工结果 | 仅有检查清单时不能证明已执行；单次设备结果不能外推所有环境 |
| `release_notes` | 某 release 声称包含/不包含的功能、平台、验证和限制 | 实际 tag/产物内容；更晚工作树中的文件能代表旧 tag 当时内容 |
| `readme` | 特定快照面向用户的当前使用方式、支持范围和已知限制 | 最早提出时间、早期动机；当前 README 覆盖所有历史版本 |
| `maintenance_document` | 维护步骤、实现指南、约束和长期操作知识 | 需求已实现或发布；建议步骤已执行 |
| `baseline_handoff_document` | 发布前冻结、当前能力、回退、测试和已知限制的交接近似记录 | 正式 Release 已完成；被 `.gitignore` 的本地文件有可复核历史 commit |
| `environment_setup_report` | 特定操作系统、Python、依赖、DPI 或工具环境的初始化和验证 | 产品功能在真实页面已验收；其他机器/平台同样可用 |
| `user_operation_feedback` | 用户或操作人员在明确环境中的实际体验、失败、截图或确认 | 未记录版本下的普遍行为；单一口述直接证明根因 |
| `manual_historical_note` | 无其他材料时，由知情者补录的历史说明，必须记录作者、补录时间和记忆范围 | 与同期材料同等的时间精度；代码、测试、发布或动机的独立确认 |

## 5. 证据可信度

### 5.1 `confidence` 枚举

| 值 | 定义 | 使用规则 |
| --- | --- | --- |
| `confirmed` | 核心结论由直接且作用域匹配的证据支持，关键跨层声明已有必要交叉验证，且没有未解决的实质冲突 | 不表示绝对正确；需说明确认到哪个 commit、平台、场景或 release |
| `estimated` | 结论由一致但不完整的证据推算，可给出明确假设、上下界或近似范围 | 适合近似日期、缺一环的实现范围；不得写成精确事实 |
| `uncertain` | 有迹象支持，但证据弱、不可复核、语义含糊或关键材料缺失；尚无两个可信来源直接冲突 | 保留条目与问题，避免选择更完整的故事 |
| `conflicting` | 两个或多个与问题相关且有一定可信度的来源给出不能同时成立的说法，尚未解决 | 必须保留所有说法、证据 ID、冲突主题和待人工确认项 |

置信度针对条目的核心事实组合，而不是给文件类型打永久分数。文档数量多不等于 `confirmed`；一个作用域准确的 tag 快照可能比多份后期总结更适合回答版本内容，但不一定更适合回答动机。

### 5.2 按问题选择证据

不存在单一、机械的全局证据优先级。按要回答的问题选择：

| 问题 | 首选组合 | 选择和交叉验证规则 |
| --- | --- | --- |
| 某个版本实际包含什么 | 目标 tag/commit 快照 + release artifact/manifest/hash + 对应 release notes；必要时 CI 发布 run | 先限定版本和平台。当前工作树不能代表旧 tag；tag 不能单独证明产物已上传，release notes 不能单独证明代码包含 |
| 代码实际执行什么 | 目标 commit 的 source code + 对应 automated test；涉及 GUI/外部动作时加运行日志或人工操作反馈 | 代码可以证明实现结果，但通常不能单独证明设计动机；mock 测试只证明模拟边界内行为 |
| 当时为什么做某个决定 | 同期 GitHub Issue/PRD/Investigation/TID/PR 讨论 + `D-xxx`；commit message 作补充 | 优先同期材料，并保留替代方案。后期 README/总结只能作为回顾，需与早期材料交叉验证 |
| 需求最早何时提出 | 最早可定位的 Issue/PRD/反馈/文档历史 + Git 历史边界；用 `first_observed_evidence_ids` 绑定 | Git 提交时间不一定等于需求首次出现时间；新文件创建时间不一定等于内容对应历史时间；只能确定顺序时用 `sequence_only` |
| 人工冒烟是否通过 | 有日期、设备/平台、前置条件、实际结果的 Smoke Test 执行记录、Acceptance Report 或用户操作反馈 | 检查清单存在、建议命令或自动化测试不能证明人工冒烟；明确“待执行”即未通过该门禁 |
| 某项设计后来是否被替代 | 明确后继 PRD/TID/决策 + 代码行为变化 + 验收/发布或弃用说明 | 仅找不到旧代码不是替代证据；必须记录 `supersedes`/`superseded_by`，若后继只改变实现而语义不变则不是需求替代 |

固定警示：

- 代码可以证明实现结果，但通常不能单独证明设计动机；
- TID 可以证明计划和意图，但不能单独证明最终实现；
- Acceptance Report 可以证明验收结论，但需要与代码、测试或发布事实交叉验证；
- Git 提交时间不一定等于需求首次出现时间；
- 新文件的创建时间不一定等于文档内容对应的历史时间；
- 后期总结文档可能包含准确回顾，也可能带有事后解释，需要与早期材料交叉验证。

BossOCR 特别警示：根目录多份 Markdown 受现有 `.gitignore` 的 `*.md` 规则影响。当前工作区可见、文件时间或报告内自述日期都不能替代可解析的 Git 历史定位；证据索引应记录 `tracked_state` 和底层材料是否可用。

## 6. 证据冲突处理

### 6.1 记录步骤

1. 把冲突拆成原子命题，例如“v1.0 tag 是否包含功能 X”“真实 GUI 冒烟是否已执行”，不要笼统写“文档不一致”。
2. 为每个说法建立独立 `E-xxx`，保存原文定位、目标 commit/时间、平台、声明范围、是否被 Git 跟踪和底层证据是否可复核。
3. 在相关 `R-xxx` 的 `evidence_ids` 保留全部证据，设置 `confidence: conflicting`。
4. 在 `open_questions` 使用固定前缀：`[CONFLICT:<简短主题>] <E-xxx> 主张……；<E-yyy> 主张……；需确认……`。
5. 对 `confidence: conflicting` 的 evidence 或 decision，也必须在其 `notes` 中至少保留一项 `[CONFLICT:<简短主题>] ...` 冲突说明。
6. `reviewer_notes` 可以记录临时主结论、选择理由和适用范围，但不得删除或改写落选说法。

### 6.2 是否保留多个说法

必须保留。后来的文档可以修正早期结论，但“后来”不是自动正确。`docs/INVESTIGATION_REPORT.md` 明确修正旧报告对“候选人未切换”的过强推断，是应保留“旧解释—新证据—修正结论”链路的实际例子。

### 6.3 如何选择主结论

只在以下条件满足时选择临时或最终主结论：

- 证据回答的是同一个问题、版本、平台和场景；
- 直接观察或目标快照比转述更贴近该问题；
- 结论得到另一种独立证据交叉支持；
- 能解释冲突来源，例如文档修订、路径搬迁、测试范围不同或发布阶段不同；
- 选择理由写入 `reviewer_notes`。

不能用“source code 永远高于文档”或“Acceptance Report 永远高于测试”一类全局规则。若代码证明行为 A，而同期 TID 说明选择 A 的动机，两者回答不同问题，不构成高低竞争。

### 6.4 人工确认

以下情况必须标记待人工确认：

- 两个目标版本材料对包含范围相反；
- Acceptance Report 的“通过”范围与未完成人工门禁冲突；
- tag、release notes 和 artifact 无法互相对应；
- 旧编号可能指向多个不同需求；
- 需求首次时间只能由未跟踪本地文件或回忆说明支持；
- 替代、拆分或合并关系会改变多个 `R-xxx` 的身份。

人工确认必须新增可定位证据或评审记录，而不是直接清除 `conflicting`。

### 6.5 禁止继续推导因果关系的条件

当冲突会改变以下任一内容且没有可辩护的主结论时，停止相关因果推导：

- 条目是否为同一需求；
- 哪个问题先出现、哪个决定由其触发；
- 决策动机或被考虑的替代方案；
- 实现、验收、人工冒烟或发布是否发生；
- 后继需求是否真正替代旧需求；
- 某项安全约束在错误动作之前是否有效。

允许继续记录独立事实和并列说法，但流程图、原型和对外叙事不得绘制未经确认的因果箭头。冲突解决后仍保留全部 `E-xxx`，更新 `confidence`、`open_questions` 和 `reviewer_notes`，不删除历史证据。

## 7. `evidence-index.json` 最小契约

本轮不创建或填充证据索引数据，但下一阶段必须按 `evidence-index.schema.json` 使用以下最小根结构，以便 `E-xxx`、`D-xxx` 与需求台账直接连接：

```json
{
  "schema_version": "1.0.0",
  "project": "BossOCR",
  "generated_at": null,
  "evidence": [],
  "decisions": []
}
```

根对象五个字段均必填；`schema_version`、`project`、`generated_at` 的规则与需求台账相同。`evidence` 和 `decisions` 是对象数组，允许在尚未抽取数据时为空。每个 evidence 对象的字段全部结构性必填：

| 字段 | 类型与允许值 | 多值 | 填写与空值规则 |
| --- | --- | --- | --- |
| `evidence_id` | string，`E-001` 起；1–999 固定三位、1000 起无前导零 | 否 | 实际值必填、永不复用；禁止 `E-000`/`E-0001`，不允许空值 |
| `source_type` | 本文件和 taxonomy 的同一 source type enum | 否 | 实际值必填，不允许空值；一个 E 只选择其主要证据形态 |
| `title` | 非空 string | 否 | 中性证据标题，不允许空值 |
| `repository_path` | repo-relative POSIX path 或三种空值 | 否 | 当前仓库路径；外部证据用 `not_applicable`，当前找不到但应存在用 `unknown` |
| `path_at_commit` | repo-relative POSIX path 或三种空值 | 否 | 证据在目标 commit 的路径；文件搬迁后不得只保存当前路径 |
| `commit` | 40 位小写 Git hash 或三种空值 | 否 | 证据绑定快照时填；纯外部/人工证据可 `not_applicable` |
| `external_locator` | 非空 string 或三种空值 | 否 | GitHub Issue/PR/Release、人工记录或受控日志的稳定定位；仓库内文件可 `not_applicable` |
| `section_or_lines` | 非空 string 或三种空值 | 否 | 章节、测试 locator 或紧凑行范围，不保存模糊“全文” |
| `observed_at` | 日期/范围/sequence string、null 或 `unknown` | 否 | 使用需求台账相同日期格式；不允许 `not_applicable` |
| `date_precision` | `exact_day`、`exact_month`、`approximate_range`、`sequence_only`、`unknown` | 否 | 必须与 `observed_at` 匹配 |
| `evidence_scope` | 非空 string | 否 | 写明能证明的原子命题、版本、平台和场景，不允许空值 |
| `tracked_state` | `tracked`、`ignored`、`untracked`、`external`、`historical_missing`、`unknown` | 否 | 按目标证据实际状态填写；`unknown` 需在 notes 说明 |
| `underlying_evidence_available` | `yes`、`partial`、`no`、`unknown` | 否 | 报告引用的日志/截图若不可复核，不能写 yes |
| `confidentiality` | `normal`、`sensitive`、`restricted` | 否 | 候选人日志、截图和邮箱相关定位至少为 sensitive；restricted 表示只可受控访问 |
| `confidence` | `confirmed`、`estimated`、`uncertain`、`conflicting` | 否 | 针对 `evidence_scope` 判断，不允许空值 |
| `notes` | array<string> 或三种空值 | 是 | 只记录范围限定；不复制候选人简历、邮箱、截图或敏感日志原文 |
| `extensions` | object | 是 | 无扩展用 `{}`；只允许可忽略的命名空间键 |

每个 decision 对象的字段也全部结构性必填：

| 字段 | 类型与允许值 | 多值 | 填写与空值规则 |
| --- | --- | --- | --- |
| `decision_id` | string，`D-001` 起；1–999 固定三位、1000 起无前导零 | 否 | 实际值必填、永不复用；禁止 `D-000`/`D-0001` |
| `title` | 非空 string | 否 | 中性决策标题 |
| `selected_solution` | 非空 string 或三种空值 | 否 | 已形成决策时应为实际值；仅占位的调查事项不创建 D |
| `alternatives_considered` | array<string> 或三种空值 | 是 | 只记录证据中实际出现的替代项 |
| `decision_rationale` | 非空 string 或三种空值 | 否 | 区分同期理由和后期解释 |
| `evidence_ids` | 非空 array<E-ID> | 是 | 至少一个，无悬空引用 |
| `related_requirements` | 非空 array<R-ID> 或三种空值 | 是 | 无需求关系用 `not_applicable`，不得用 legacy ID |
| `confidence` | 四级 confidence enum | 否 | 决策存在与理由可分别在 notes 限定，但本字段给核心判断 |
| `notes` | array<string> 或三种空值 | 是 | 记录范围、冲突和人工评审说明 |
| `extensions` | object | 是 | 无扩展用 `{}` |

Decision 不是 Requirement；只有形成独立持续约束时，才另外建立 `R-xxx`。对象内部数组也遵守“不使用空数组作为字段空值”的规则，禁止空字符串和 sentinel 数组。`evidence-index.schema.json` 是本契约的机器约束；若它与本节不一致，必须先同步修正规则，不能继续抽取。HTML 只能通过 `E-xxx`/`D-xxx` 读取该索引，不能临时把原始文件路径散落到展示代码中。

JSON Schema 不负责跨对象和仓库事实校验。下一阶段的外部 lint 还必须检查：E/D ID 全局唯一并按数值排序；D 的 `evidence_ids` 与 `related_requirements` 均存在；需求台账中的 E/D 引用均存在；首次证据是全量证据的子集且 `source_type` 对齐；日期范围起点不晚于终点；冲突说明引用的双方证据存在；敏感原文没有被复制进数据。`observed_at`、commit、路径和 `tracked_state` 仍需与目标 ref 或外部定位实际核对。
