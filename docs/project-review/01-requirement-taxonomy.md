# 阶段 1：需求分类体系

## 1. 台账纳入判据

### 1.1 什么可以成为需求条目

后续 `requirements` 中的每个 `R-xxx` 都必须是一个可独立追溯的需求中心单元。至少满足以下条件中的一项，并且有可定位证据：

- 描述了要解决的业务问题、用户目标或运行风险；
- 规定了可观察的产品或系统行为；
- 规定了安全、稳定性、兼容性、性能、隐私、可维护性或交付能力约束；
- 记录了实际行为偏离既有预期的缺陷；
- 建立了可独立验收的测试保护、发布能力或维护能力。

同时应能回答至少两个问题：为何需要、完成后什么不同、如何判断完成、与哪些证据或需求有关。只有文件名、commit、函数、类、参数、依赖或测试方法，而没有独立问题和验收结果的内容，不建立 `R-xxx`。

### 1.2 需求粒度

- 一个 Business Need 可以通过 `decomposed_into` 产生多个可独立验收的具体需求；每个具体需求用 `derived_from` 反向引用一个或多个上位需求。例如“避免错误处理候选人”可以产生局部 OCR、二次确认、焦点恢复和安全停止等不同约束。
- 一个需求可以包含多个 Implementation Change；Change 是实施拆分，不按数量复制需求。
- 一个条目应围绕一组稳定的预期结果。若各部分可以独立接受、拒绝、发布或替代，应拆分。
- 多份 PRD、TID、验收或 release notes 描述同一预期结果时，应合并证据，不因文档数量重复建项。
- 同一能力在 Windows Edge 与 macOS Chrome 有不同约束、状态或实现路径时，可以拆成平台子需求；不能仅因文件名不同而拆分。

### 1.3 需求中心与事件中心

需求台账不是所有仓库事件的清单。Technical Decision、Implementation Change、Release Event、Operational Incident 和 Documentation Change 通常作为 `E-xxx` 证据或 `D-xxx` 决策连接到 `R-xxx`。只有当事件本身形成独立、持续、可验收的能力或约束时，才提升为需求条目，并选择本文件定义的 `requirement_type`。

## 2. 概念区别

| 概念 | 规范定义 | 通常是否建立 `R-xxx` | 与需求的连接方式 |
| --- | --- | --- | --- |
| Business Need（业务需求） | 业务或使用层面的目标、痛点、风险或机会，不预设具体技术方案 | 是，可作为上位条目 | `requirement_type: business_need`；通过 `decomposed_into` 连接多个下位 Requirement，下位用 `derived_from` 互惠引用 |
| Requirement（产品或系统需求） | 对产品行为、系统能力、质量属性或约束的可验收陈述 | 是 | 产品行为使用 `product_requirement`，内部系统约束使用 `system_requirement` |
| Defect（缺陷） | 已有预期与实际行为之间有证据的偏差 | 是，若需独立追踪；也可只作为既有需求的事件证据 | `requirement_type: defect`；说明是恢复预期还是触发新需求 |
| Technical Decision（技术决策） | 在已识别约束和替代方案之间作出的技术选择及理由 | 通常否 | 使用 `D-xxx`，由 `decision_ids` 关联；若决定新增持续系统约束，再建立 `system_requirement` |
| Implementation Change（实现改动） | 为满足需求而进行的代码、配置、依赖、重构或文件变更 | 通常否 | 通过代码路径、commit 和 Implementation Report 作为证据 |
| Test Protection（测试保护） | 防止已知行为或安全约束回归的自动化或人工验证 | 通常作为证据；具有独立质量门禁能力时可以建项 | 普通测试进入 `tests`/`smoke_tests`；独立工程目标使用 `test_protection` |
| Release Event（发布事件） | 某个版本、tag、产物或 Release 在特定时点的形成或分发 | 否，除非需求本身是建立/改变发布能力 | 作为 `released` 状态证据；独立交付能力使用 `release_enablement` |
| Operational Incident（运行事件） | 实际运行中观察到的误操作、失败、中断、异常或用户反馈 | 通常否 | 作为问题证据；确认偏离后可产生 `defect` 或新需求 |
| Documentation Change（文档改动） | README、PRD、TID、报告、指南或交接材料的创建、修改或搬迁 | 通常否 | 作为意图、验收或说明证据；改变维护/交接能力时使用 `maintenance_enablement` |

### 2.1 需求关系的语义边界

- `derived_from` / `decomposed_into` 表示语义派生：上位需求描述较宽的问题或目标，下位需求把它细化为可独立验收的结果。两端互惠，允许多父和多子，父子可以同时有效，不因派生自动改变状态。
- `dependencies` 表示前置条件：没有该 R、D、package、platform 或 external 条件时，本需求不能成立或实施；前置不等于“更抽象的父需求”。
- `related_requirements` 表示显著但非层级、非前置、非替代的对称关系。
- `supersedes` / `superseded_by` 表示新需求边界取代旧需求边界，影响生命周期；后期拆分、合并或替换使用该关系，不得用派生关系隐藏替代事实。
- 同一对需求不得同时被写成派生、普通相关和替代关系。派生图、依赖图和替代图分别检查无环；`related_requirements` 的双向关系不参加有向无环检查。
- 文档来源、TID Change、代码改动或测试用例不是上位需求，不能填入 `derived_from` 或 `decomposed_into`。

强制解释规则：

- 一个缺陷可能触发新需求，也可能只是恢复既有预期行为。恢复行为时，缺陷条目应关联原需求，不得伪装为功能首次提出。
- 测试本身通常不是需求，但可能代表工程化或质量保障需求。仅增加一个回归用例通常是证据；建立发布前必须执行的全量测试门禁可能是 `test_protection`。
- 打包、发布和文档变更只有在改变交付能力、维护能力或平台支持时，才可能独立成为需求。
- TID 中的 `Change 1…n`、commit 数量和文件数量不是需求数量。
- 优先级标签、风险标签、版本号、分支名或旧 `R1` 小节号都不能单独证明存在一项需求。

## 3. `requirement_type` 枚举

| 值 | 使用条件 | 不使用的情况 |
| --- | --- | --- |
| `business_need` | 上位业务问题、目标或安全结果，可通过 `decomposed_into` 产生多个具体需求 | 已经描述具体系统行为时；不得只靠文档层级虚构派生关系 |
| `product_requirement` | 用户可观察的流程、输入、输出、动作、交互或能力 | 纯内部技术结构或代码选择 |
| `system_requirement` | 安全、稳定性、性能、兼容性、数据、错误处理或架构约束 | 仅记录某次实现方式 |
| `defect` | 有证据表明实际行为偏离既有预期 | 只是新功能愿望或未确认异常 |
| `engineering_enablement` | 独立提升开发、诊断、可观测或工程执行能力 | 普通重构、日志文本微调或依赖更新 |
| `test_protection` | 测试或质量门禁本身是独立、持续、可验收的工程能力 | 为其他需求补充的普通测试证据 |
| `release_enablement` | 新建或实质改变构建、打包、签名、产物校验或分发能力 | 某次 tag/Release 事件本身 |
| `maintenance_enablement` | 新建或实质改变交接、维护、配置复用或可持续管理能力 | 单次说明文案或文件搬迁 |
| `unknown` | 证据足以保留条目，但不足以判断上述类型 | 为省事而跳过分类；必须同时记录 `open_questions` |

`requirement_type` 描述需求性质；它不表示证据来源、当前状态、风险后果或实现难度。

## 4. 模块分类总则

`module_primary` 必须是一个一级模块；`module_secondary` 可为一个或多个辅助模块，或使用规范空值。选择规则：

1. 先问“如果删除这项需求，最直接消失的用户/系统结果是什么”，该结果所属模块为主分类。
2. 复用的底层能力、受影响但不是目标的流程进入辅助模块。
3. 安全、隐私、fail-closed、兼容、可观测等跨模块属性使用 `cross_cutting_concerns`，不能为了表达风险而重复主模块。
4. 同一事实不得复制成多个需求来回避主分类选择。
5. 无法确定时使用 `module_primary: unknown`，在 `open_questions` 记录冲突，不凭文件所在目录猜测。

一级模块枚举固定为：

```text
core_automation
ocr_capture
keyword_rules
candidate_actions
page_filter_refresh
calibration
mouse_interaction
focus_page_state
cross_platform
stability_recovery
candidate_profile_parsing
test_build_release
documentation_handoff
unknown
```

## 5. 一级模块定义

### 5.1 基础自动化（`core_automation`）

- 定义：BossOCR 启动、运行控制、候选人遍历和批次主循环的基础编排。
- 纳入内容：启动输入、运行时长、暂停/继续、Esc 停止、候选人顺序切换、停留预算、计数与批次循环。
- 不纳入内容：OCR 识别细节、关键词语法、收藏/转发动作、具体筛选面板点击、鼠标轨迹算法。
- 与其他模块的边界：主循环“何时调用”归本模块；被调用能力“做什么”归其业务模块。每 100 人触发刷新若目标是筛选归位，主类为 `page_filter_refresh`。
- 典型示例（说明分类，不是正式条目）：用户设置 `duration-seconds` 后安全停止；空格暂停和 Esc 停止在等待期间仍响应。
- 常见冲突：与页面筛选、稳定性、焦点恢复冲突；不要把所有 `simple_brush.py` 变更都归基础自动化。
- 主辅规则：编排本身是目标时主类为本模块；只是在主循环接入 OCR/动作时，本模块为辅助类。

### 5.2 OCR 与截图（`ocr_capture`）

- 定义：从当前可见屏幕区域获取像素、执行本地 OCR、排序文字框并形成可供规则匹配的文本与置信结果。
- 纳入内容：MSS 局部截图、RapidOCR/ONNX Runtime、OCR 实例复用、置信度阈值、最多 8 屏扫描、同区域二次识别、截图失败关闭、OCR 预览与隐私边界。
- 不纳入内容：`and/or/not/any(...)` 语法、收藏/转发、通用点击区域模板、结构化工作/教育经历解析。
- 与其他模块的边界：OCR 正文区域拖框服务于识别时主类可为本模块；通用 `ScreenRegion` 框架、11 个点击区域和模板持久化归 `calibration`。
- 典型示例（说明分类，不是正式条目）：只分析当前可见详情像素，避免旧全页剪贴板把底层候选人文本混入当前候选人。
- 常见冲突：与关键词规则、校准、候选人经历解析和稳定性冲突；OCR 返回文本不代表已完成语义解析。
- 主辅规则：输入像素、识别质量或扫描策略是主要结果时归本模块；规则语义是主要结果时归 `keyword_rules`。

### 5.3 关键词和规则表达式（`keyword_rules`）

- 定义：把用户输入解析为规范规则，并对标准化后的 OCR 文本执行确定性匹配。
- 纳入内容：英文双引号词、分号、`not > and > or`、`any(...)`、NFKC、大小写与布局空白标准化、非法语法和精确子串语义。
- 不纳入内容：OCR 引擎初始化、截图、页面滚动、命中后的收藏或邮件转发。
- 与其他模块的边界：二次确认需要“同一规则再次命中”时，识别过程归 OCR，规则等价性归本模块。
- 典型示例（说明分类，不是正式条目）：`any("魔方","九州") and not any("投放","消耗")` 保持 any 原子语义，不能错误展开为顶层 OR。
- 常见冲突：与候选人信息解析、OCR 和产品输入体验冲突；出现教育/工作词不代表结构化解析。
- 主辅规则：语法、匹配或错误提示是验收核心时主类为本模块；OCR 仅为输入来源。

### 5.4 候选人动作（`candidate_actions`）

- 定义：在候选人通过条件后执行的受控业务动作及模式分发。
- 纳入内容：收藏/转发互斥模式、收藏按钮动作、邮件转发入口/Tab/输入/联系人/确认流程、`--no-forward` 对真实转发的动作门禁。
- 不纳入内容：决定是否命中的 OCR/规则、鼠标移动轨迹、动作结束后的通用焦点恢复机制。
- 与其他模块的边界：点击目标和动作顺序归本模块；区域如何校准归 `calibration`；指针如何到达归 `mouse_interaction`；退出后如何恢复键盘焦点归 `focus_page_state`。
- 典型示例（说明分类，不是正式条目）：收藏模式命中后只收藏，不进入邮箱流程；转发模式保持既有邮件流程。
- 常见冲突：与安全门、焦点恢复和校准冲突；`--no-forward` 已被解析但未生效的历史问题是动作安全缺陷，不是 CLI 实现细节。
- 主辅规则：业务动作或模式是用户可观察结果时主类为本模块，并按需添加 `safety_guard` 或 `human_in_the_loop`。

### 5.5 页面筛选与刷新（`page_filter_refresh`）

- 定义：对候选人列表进行筛选、刷新、首位归位和批次边界导航。
- 纳入内容：“最近没看过”、打开/确认筛选、首位候选人、每 100 人 F5、刷新后重新筛选、`--no-batch-filter`。
- 不纳入内容：一般候选人右方向键遍历、通用区域选择、鼠标轨迹、页面状态验证的通用机制。
- 与其他模块的边界：四个区域的业务顺序归本模块，区域保存与原子校准归 `calibration`；刷新失败后的安全策略可辅助归 `stability_recovery`。
- 典型示例（说明分类，不是正式条目）：启动和批次刷新后按固定顺序应用未看筛选并打开首位候选人。
- 常见冲突：与基础自动化、焦点/页面状态和稳定性冲突；“每 100 人”出现于主循环不代表主类一定是基础自动化。
- 主辅规则：用户要解决“从正确候选人集合和首位开始”时主类为本模块；仅改变调用时机才考虑 `core_automation`。

### 5.6 校准系统（`calibration`）

- 定义：把页面上的安全区域转为可校验、可加载的 `ScreenRegion`，并管理运行期或持久化校准数据。
- 纳入内容：Tk 拖框、DPI 坐标换算、区域最小尺寸、运行期区域、原子取消/回退、11 区域模板、模板 JSON、步骤注册表、模板选择和环境匹配。
- 不纳入内容：区域代表的业务动作、OCR 识别本身、鼠标轨迹；当前通用模板明确不包含 OCR 正文区域。
- 与其他模块的边界：坐标/模板生命周期归本模块；`forward_icon` 被点击后的业务语义归 `candidate_actions`；DPI 平台差异可辅助归 `cross_platform`。
- 典型示例（说明分类，不是正式条目）：模板复用 `first_candidate`、`focus_restore_region`、`favorite_button_region` 等现有字段，并在环境不匹配时安全失败或回退。
- 常见冲突：与鼠标交互、页面筛选、候选人动作和跨平台冲突；不要按模板包含的 11 个区域拆成 11 项需求。
- 主辅规则：可保存、校验、选择或复用区域是主要能力时主类为本模块；某动作只是模板消费者时作为辅助模块。

### 5.7 鼠标与交互行为（`mouse_interaction`）

- 定义：物理指针从当前位置移动到已选目标并点击的行为封装与可观察轨迹。
- 纳入内容：`human_move_to()`、`human_click()`、WindMouse、贝塞尔 fallback、简单直线回退、时长/easing、终点校准和区域内随机落点。
- 不纳入内容：目标区域定义、点击业务顺序、键盘焦点语义、规避验证码或平台风控的声称。
- 与其他模块的边界：校准回答“点哪里”，本模块回答“怎样移动并落点”，候选人动作回答“为什么点”。
- 典型示例（说明分类，不是正式条目）：远距离移动使用两段式轨迹并最终强制落到选定整数坐标；失败时回退既有贝塞尔路径。
- 常见冲突：与校准、候选人动作、稳定性和合规冲突；可观察鼠标移动不能被描述为绕过自动化检测。
- 主辅规则：轨迹、时长或点击封装本身是验收对象时主类为本模块；业务误点后果用风险与跨领域标签表达。

### 5.8 焦点与页面状态恢复（`focus_page_state`）

- 定义：确保键盘、窗口和页面处于下一步可安全执行的预期状态，并在动作后恢复。
- 纳入内容：按进程置前 Edge、转发退出路径焦点恢复、双次恢复、候选人是否切换、弹窗/详情状态、页面状态失败后的停止。
- 不纳入内容：一般鼠标轨迹、区域校准数据模型、候选人动作的业务内容。
- 与其他模块的边界：恢复区域的获取归 `calibration`，两次点击的焦点结果归本模块，错误候选人动作的后果通过 P0 风险表达。
- 典型示例（说明分类，不是正式条目）：转发所有退出路径都尝试两次恢复详情页焦点，以降低右方向键失效后重复处理同一候选人的风险。
- 常见冲突：与基础自动化、候选人动作和稳定性冲突；页面状态恢复不是“任意点击两次”的实现细节，而应看是否维持候选人切换约束。
- 主辅规则：正确窗口/焦点/页面状态是直接目标时主类为本模块；通用重试框架才主归 `stability_recovery`。

### 5.9 跨平台适配（`cross_platform`）

- 定义：处理操作系统、浏览器、显示器、DPI、依赖和打包差异，使明确的平台组合获得可验证支持。
- 纳入内容：Windows Edge 与 macOS Chrome 的平台适配工作及其经证据确认的约束或状态、Per-Monitor V2 DPI、主显示器约束、平台依赖和平台专属入口。
- 不纳入内容：仅文件名含 `mac`/`windows`、平台无关规则逻辑、某次 Windows 发布事件。
- 与其他模块的边界：平台差异是主要目标时归本模块；Windows 构建产物归 `test_build_release`；校准坐标算法归 `calibration` 并辅助标平台。
- 典型示例（说明分类，不是正式条目）：`ocr_mac_demo.py` 的名称或某个 macOS 分支名只能证明材料或工作线存在，不能独立证明 macOS Chrome 已发布、未完成或处于 `experimental`；状态必须跨分支核对实现、测试、验收、构建和发布证据。
- 常见冲突：与构建发布、校准和 OCR 冲突；不得把“可导入”当作完整平台支持。
- 主辅规则：新增/取消平台支持或解决平台阻断时主类为本模块；单平台功能只在 `platforms` 标注实际组合。

### 5.10 稳定性与异常恢复（`stability_recovery`）

- 定义：在初始化、识别、页面操作、配置或长时间运行失败时保持可控、可停止、可诊断或安全回退。
- 纳入内容：fail-closed、安全停止、异常隔离、重试上限、原子回退、模板损坏处理、兼容开关、长运行恢复和关键日志。
- 不纳入内容：某模块内部的普通参数校验、单一业务动作、没有运行风险的代码清理。
- 与其他模块的边界：具体故障属于一个业务模块时，业务模块通常为主类，稳定性为辅助或 `cross_cutting_concern`；跨多个链路的恢复框架才主归本模块。
- 典型示例（说明分类，不是正式条目）：OCR 初始化、截图、空结果或二次确认失败时禁止进入真实动作，且不回退到旧全页复制方案。
- 常见冲突：与所有业务模块均可能冲突；不要把所有缺陷都放进稳定性，也不要把风险等级当模块。
- 主辅规则：恢复/停止/回退能力本身是验收目标时主类为本模块；局部缺陷按直接行为模块分类。

### 5.11 候选人信息与经历解析（`candidate_profile_parsing`）

- 定义：从候选人内容中识别并结构化姓名、身份、教育、工作或项目经历及其归属关系。
- 纳入内容：候选人指纹、字段边界、工作/教育经历结构化、跨屏段落归属和结构化输出。
- 不纳入内容：OCR 原始文本、关键词是否出现、底层列表中出现“教育经历/工作经历”字样。
- 与其他模块的边界：OCR 提供文本，规则模块做布尔匹配，本模块要求结构化字段和候选人归属。
- 典型示例（纯分类假设，不表示仓库已有需求）：提取“候选人身份 + 教育经历”形成稳定指纹，用于防重复处理。
- 常见冲突：最容易与 OCR 和关键词匹配混淆；本轮已读取的当前 `main` 材料没有证明完整结构化解析能力，该局部结论不得外推到尚未核对的分支。
- 主辅规则：只有验收结果包含结构化字段或身份归属时才主归本模块；否则保持 OCR/规则分类。

### 5.12 测试、构建与发布（`test_build_release`）

- 定义：验证代码、构建 Windows one-dir、形成可校验产物并完成受控发布的工程链路。
- 纳入内容：`tests/`、CI、`build-windows.bat`、`BossOCR.spec`、依赖锁定/许可、ZIP、SHA-256、tag 和 Release 门禁。
- 不纳入内容：业务测试所保护的需求语义、普通 release notes 文案、仅在报告中列出的建议命令。
- 与其他模块的边界：测试用例通常是其他模块的证据；只有建立质量门禁时才主归本模块。跨平台打包阻断可辅助归 `cross_platform`。
- 典型示例（说明分类，不是正式条目）：构建前运行全量测试、生成 one-dir 并对安全模式做低风险冒烟；产物和 hash 需单独核对。
- 常见冲突：与发布事件、平台适配和文档冲突；workflow 存在、测试通过、本地构建、ZIP 生成和 GitHub Release 是不同事实。
- 主辅规则：交付链能力改变时主类为本模块；某功能的测试和 release 只作为该功能的证据。

### 5.13 文档、交接与维护性（`documentation_handoff`）

- 定义：使后续开发者能够理解、复核、操作和维护项目的持续性资料与结构。
- 纳入内容：PRD/TID 规范、调查/实施/验收/冒烟/发布基线、维护指南、交接资料、字段注册表和文档路径治理。
- 不纳入内容：单次措辞修正、无语义变化的文件搬迁、为其他需求补充的一段 README。
- 与其他模块的边界：文档通常是证据；只有维护能力本身改变时才建立 `maintenance_enablement`。模板字段注册表若主要改变运行配置复用，主归 `calibration`。
- 典型示例（说明分类，不是正式条目）：建立统一复盘规则和机器 Schema，使三年后的维护者能重建需求因果与证据。
- 常见冲突：与所有报告型证据、测试指南和发布说明冲突；文件名不能自动决定它是独立维护需求。
- 主辅规则：维护/交接能力是直接结果时主类为本模块；其他文档变化作为所属需求的证据。

## 6. 标签体系

### 6.1 `platform`

字段名为 `platforms`，允许多值。固定值：

- `windows_edge`：Windows 10/11 x64 与 Microsoft Edge 的平台组合标签。
- `macos_chrome`：macOS 与 Chrome 的平台组合标签。
- `platform_agnostic`：需求语义不依赖操作系统或浏览器，例如纯规则文法。
- `cross_platform_core`：同一已验证核心明确服务多个平台；不能由“看起来可移植”推断。
- `unknown`：证据不足以确定平台，必须记录问题。

`platform_agnostic` 和 `cross_platform_core` 都是总结值，必须各自单独成数组，不能与具体平台混用。需求分别适用于 Windows Edge 与 macOS Chrome、但实现未证明共用核心时，可以同时列两个具体值；只有证据证明同一核心跨平台时才改用单独的 `cross_platform_core`。

`windows_edge` 和 `macos_chrome` 只标识适用的平台组合，不内置成熟度。是否提出、实施、验收或发布，只能由 `status`、`confidence`、`releases` 和对应 `E-xxx` 证据确定；不得根据当前 checkout、分支名或文件名向任一方向提前判断。

### 6.2 `module`

使用第 4 节固定模块值。`module_primary` 单值，`module_secondary` 多值；模块表示职责，不表示目录位置、风险或平台。

### 6.3 `source_type`

`source_type` 是支持条目“首次观察”结论的证据类别摘要，允许多值，并与 `first_observed_evidence_ids` 对齐。它不是全量证据类型汇总；实现、验收和发布等其他来源通过 `evidence_ids` 与证据索引查询。固定值为：

```text
source_code
automated_test
ci_result
build_script
release_artifact
runtime_log
git_commit
git_tag
github_issue
pull_request
prd
investigation_report
tid
implementation_report
acceptance_report
smoke_test
release_notes
readme
maintenance_document
baseline_handoff_document
environment_setup_report
user_operation_feedback
manual_historical_note
```

仓库实际存在 PRD、Windows Setup Report、发布前基线，以及 Investigation Report 所引用的本地运行日志，因此在题目给定类型上增加 `prd`、`baseline_handoff_document`、`environment_setup_report`、`runtime_log`。运行日志可能包含候选人隐私，证据索引只记录受控定位和可复核状态，不把敏感原文复制进台账。来源详细定位仍由 `evidence_ids` 和未来证据索引承担。

### 6.4 `requirement_type`

使用第 3 节固定值。它回答“这是什么性质的需求中心条目”，不回答“材料是什么类型”。

### 6.5 `risk`

字段名为 `risk_level`，规范值为 `P0`、`P1`、`P2`、`experimental`，证据无法支持判断时可使用空值状态 `unknown`。完整定义见 `02-status-risk-evidence-definition.md`。

### 6.6 `status`

规范状态为 `proposed`、`investigating`、`designed`、`implementing`、`testing`、`accepted`、`released`、`superseded`、`rejected`、`deferred`、`abandoned`；证据不足时可使用空值状态 `unknown`。完整定义见 `02-status-risk-evidence-definition.md`。

### 6.7 `confidence`

规范值为 `confirmed`、`estimated`、`uncertain`、`conflicting`。置信度描述核心事实的证据情况，不描述需求状态或风险。

### 6.8 `release`

字段名为 `releases`，保存 tag 或 Release 标识原文，不设全局 enum。BossOCR 已出现 `Boss`、`v1.0.0`、`issue-1-v1.0`、`windows-stable-v1.0`、`windows-stable-v1.1`、`v1.1`、`v1.2` 等多套命名；归一化展示可以另做，但不得覆盖原值。

### 6.9 `cross_cutting_concern`

字段名为 `cross_cutting_concerns`，允许多值，固定值为：

```text
safety_guard
privacy_compliance
fail_closed
backward_compatibility
observability
performance
coordinate_dpi
human_in_the_loop
rollback_fallback
data_integrity
page_state_integrity
long_running_stability
licensing
maintainability
```

横切标签用于跨越多个模块的约束。它不能替代主模块、风险或 requirement type；例如 `fail_closed` 是设计关注点，P0/P1/P2 才描述失败后果。

## 7. 旧命名与分类警示

- `Issue #1`、GitHub Issue `#5`、`Next-3` 是不同命名空间；仓库材料明确出现 `Next-3` 对应 Issue `#5`，不能按数字自动合并。
- PRD 内 `R1…R7` 是文档局部小节号，不是全局需求主键；本轮当前材料中未发现 `R26`、`R27`，这不是错误，也不得凭外部记忆建立正式条目。下一阶段全面扫描仍无仓库或远端证据时不写入台账；若原开发者补充说明，先以 `source_type: manual_historical_note` 建立 `E-xxx`，再依据其是否真实提出、实施、延期或放弃评估是否建立 `R-xxx`。只有证据确认 `R26`/`R27` 确为旧编号时，才以带来源命名空间的原文写入 `legacy_ids`。
- `[Next-6][P2]` 同时包含路线序号和历史优先级标签；`P2` 是否能直接转换为本复盘风险，仍需按失败后果重新判断。
- `Hotfix P0` 是历史标签和问题语境，不是新的编号空间，也不能跳过证据直接设为 `risk_level: P0`。
- 文件名版本 `TID V1.0/V1.1` 表示文档修订，不等于产品 release。
- `README.md` 在历史 commit 与当前 `docs/README.md` 之间发生过搬迁；引用必须记录对应 commit 下的路径。
