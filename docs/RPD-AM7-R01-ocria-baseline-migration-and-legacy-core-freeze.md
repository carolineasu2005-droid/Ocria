# Ocria Am7 AM7-R01 产品需求文档：基线迁移与 Legacy Core 冻结

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 产品 | Ocria |
| Generation / Codename | Am7 |
| Requirement | AM7-R01 |
| 文档类型 | RPD（Requirement / Product Design） |
| 文档版本 | 0.3 |
| 编写日期 | 2026-08-11（Asia/Shanghai） |
| 当前阶段 | RPD 已 Approved；已进入 TID；未执行 Change |
| Requirement 状态 | Approved |
| 当前产品形态 | Python CLI 驱动的浏览器招聘页面自动化工具 |
| 当前基线候选 | BossOCR `main` / `a7c941989a038d7a998ccee707e14b4fd9125cda` / tag `V1.3.1` |
| 当前基线结论 | 仅为本地仓库可验证的候选，不等同于已批准的最终 Stable Baseline |

本文只定义 AM7-R01 的业务必要性、产品边界、冻结原则、回归屏障和 Requirement 级验收标准。本文不是 TID，不授权修改生产代码、测试、构建、发布流程或运行数据，也不授权实施任何 Change。

只有在本文通过人工审查，且维护者明确指示“RPD 已通过，现在开始 TID”后，才可进入仓库全面技术审计和 TID 编写阶段。

## 2. 执行摘要

BossOCR 已形成一条稳定运行的 Legacy 产品线，具备候选人页面准备、OCR、关键词筛选、候选人切换验证、收藏、转发、焦点恢复、校准、批次刷新以及 R02—R07 OCR 证据链等能力。Ocria 是从这条稳定基线独立出来、用于承载 Am7 后续开发的新产品主线。

AM7-R01 不开发 AI，也不重构 BossOCR。它要先把一个经过确认的 BossOCR 状态完整、可追溯地确立为 Ocria Am7 的 Legacy Baseline，并用冻结合同和回归屏障约束后续所有 Am7 Requirement。这样，后续 AI 能力只能在明确的新区域或受控集成缝中加入，不能以“接入 AI”为由改变 Legacy 算法、参数、数据语义或用户可观察行为。

AM7-R01 完成后，Ocria 仍应保持 BossOCR Legacy 业务能力。变化只应体现在：Ocria 具备独立产品身份、明确的仓库继承关系、可复核的 Source Baseline、正式的 Legacy Freeze Contract，以及可重复执行的 Regression Barrier。

## 3. 为什么必须先完成 AM7-R01

### 3.1 避免基线漂移

如果 Ocria 只以“当前代码看起来来自 BossOCR”为依据开始 Am7 开发，后续将无法可靠判断某个行为差异来自基线本身、迁移过程，还是 AI Change。当前最新提交、某个 tag、某份发布说明和真实稳定运行状态也不天然等价。必须先建立带来源、分支、提交、时间和证据的唯一继承锚点。

### 3.2 保护已验证的 Legacy 运行语义

BossOCR 的价值不仅在于文件存在，还在于多个相互约束的运行语义已经稳定：页面加载与切换、OCR 采集与标准化、多屏聚合、相似度、动态结束、动作安全门、焦点恢复、停止机制和失败降级。后续 AI 接入如果顺手调整其中任一算法或阈值，会把“新增 AI”与“修改 Legacy”混成无法归因的一次变化。

### 3.3 保留可用的 fallback 产品

BossOCR 需要继续作为独立的 Legacy Stable 产品维护。当 Ocria 尚不稳定、AI 服务不可用、AI 结果不符合预期或需要紧急回退时，BossOCR 应能继续提供现有关键词筛选和浏览器自动化能力。Ocria 开发不得污染 BossOCR 仓库或破坏其可维护性。

这里的 fallback 是独立 BossOCR Legacy Stable 产品线所提供的产品级、人工回退选择，不代表 Ocria Am7 必须内置“AI 失败后自动切换 BossOCR Keyword Mode”。Ocria 自身 AI Runtime 的失败降级策略由后续独立 Requirement 定义，不属于 AM7-R01。

### 3.4 为后续 Requirement 建立共同安全门

Am7 后续 Requirement 将逐步引入新数据、新模块和新的筛选决策。若没有统一的 Legacy Regression Barrier，每个 Requirement 都会重复争论“什么必须保持不变”，而且测试失败容易被局部修改 expected、skip 或降低断言掩盖。R01 必须一次建立后续共同依赖的安全合同。

## 4. 当前产品背景与仓库事实

### 4.1 产品形态

Ocria 当前不是 GUI 产品，也不是桌面图形界面产品。当前形态是：

- 用户从终端或批处理入口启动 Python CLI；
- 用户通过 CLI 参数和交互完成运行模式、关键词、时长及校准选择；
- 程序使用 pyautogui、MSS、RapidOCR、WindMouse 等能力操作真实浏览器中的 BOSS 页面；
- 程序基于屏幕像素和本地 OCR 工作，不以 DOM、浏览器注入或 BOSS API 作为当前主路径；
- 浏览器页面动作仍是产品运行的一部分，但产品自身没有 GUI。

因此，AM7-R01 的产品描述统一为：

> Ocria 是基于 Python CLI 运行、自动操作浏览器招聘页面并执行 OCR、筛选和页面动作的自动化工具。

### 4.2 BossOCR 与 Ocria 的产品关系

| 产品 | 定位 | 责任 |
| --- | --- | --- |
| BossOCR | Legacy Stable；独立仓库；持续维护 | 保持现有关键词筛选和浏览器自动化能力，作为稳定运行与紧急 fallback 产品 |
| Ocria | 新开发主线；独立本地仓库；Am7 工作区 | 继承经确认的 BossOCR Stable Baseline，承载后续 Am7 能力 |

这种关系是“有明确来源的继承”，不是覆盖、改名后替代或共享一个可被两条产品线同时修改的工作区。BossOCR 的历史和稳定版本继续独立存在；Ocria 保留来源证明，但后续建立自己的产品身份和版本演进。

### 4.3 2026-08-11 的只读仓库观察

以下信息是编写 RPD 时从当前本地仓库得到的事实快照，用于确定需求背景，不构成最终基线批准：

| 观察项 | 当前事实 |
| --- | --- |
| 当前分支 | `main` |
| 当前 HEAD | `a7c941989a038d7a998ccee707e14b4fd9125cda` |
| HEAD message | `fix(focus): use safe region for candidate focus recovery` |
| HEAD author / commit time | 2026-08-11 21:45:20 +08:00 |
| 当前 tag | `V1.3.1` 指向 HEAD |
| BossOCR remote | `bossocr-upstream` → `https://github.com/carolineasu2005-droid/Boss-OCR.git` |
| 分支关系 | 本地 `main` 与 `bossocr-upstream/main` 当前指向同一提交 |
| Ocria 独立 remote | 当前未观察到 |
| 工作树 | RPD 编写前为 clean |
| CLI 主入口 | `simple_brush.py`，批处理启动入口为 `start.bat` |
| 当前用户身份 | 启动脚本、打包配置、工作流和用户文档仍以 BossOCR / BOSS 直聘自动刷简历为主要显示身份 |
| 自动化测试资产 | 当前有 16 个 `test_*.py` 文件；另有 R04—R06 benchmark 文件 |
| OCR 证据能力 | 仓库存在 R02—R07、CandidateOcrDocument、Stage-0、OCR Store 和 OCR Replay 的代码、测试及设计/验收材料 |
| 实机验收边界 | 既有材料多次区分自动化测试与真实 BOSS 页面人工验证，不能互相替代 |

当前状态使 `a7c9419...` 成为强基线候选，但仍不能只因它同时是 HEAD、远端 main 和最新 tag 就自动判定为最终 Stable Baseline。后续 TID 必须设计并执行对历史、发布、测试、人工验收声明和必要外部证据的交叉确认。

### 4.4 当前证据的限制

- 当前 checkout 是完整历史的一个观察点，不等于全部产品历史。
- tag、commit message 和文档声明分别只能证明其直接记录的事实。
- 历史自动化通过记录不能证明当前 checkout 的测试仍通过。
- Smoke Checklist 的存在不能证明 Smoke 已执行。
- mock、fixture 或打包 smoke 不能证明真实 BOSS 页面行为通过。
- 当前未观察到 Ocria 独立 remote，意味着独立仓库身份尚需在 R01 中固化，而不能仅凭本地目录名宣称完成。

## 5. 用户、维护者与利益相关方

### 5.1 直接用户

通过 CLI 启动和配置工具、在受控浏览器环境中运行候选人浏览、OCR、收藏或转发流程的操作者。

他们需要：

- Ocria 迁移后仍能按既有方式安全启动和停止；
- 既有校准、候选人切换、OCR、筛选和页面动作不因品牌或仓库迁移发生意外变化；
- 当 Ocria 不适用时仍能回退到独立维护的 BossOCR；
- 从 CLI 用户可见信息中明确知道当前运行的是 Ocria Am7，而不是 BossOCR Stable。

### 5.2 产品维护者与开发者

他们需要：

- 精确知道 Ocria 继承自哪个 BossOCR 状态；
- 能区分不可随意变化的 Legacy Core、受控集成点、迁移基础设施和 Am7 新增区域；
- 能用一致的自动化证据证明后续 Change 没有破坏 Legacy；
- 能把真正需要改变 Legacy 的事项拆成独立 Requirement，而不是夹带在 AI 接入中。

### 5.3 验收者

人工审查 RPD、TID、Change 结果和最终真实页面 Smoke 的维护者。他们需要同时看到自动化证据和人工 Smoke 证据，并能确认两者的作用域没有被混淆。

## 6. Requirement 目标

### 6.1 用户层目标

1. Ocria 在建立独立产品身份后，继续提供 BossOCR 当前已稳定的 CLI 与浏览器自动化能力。
2. 品牌迁移不改变操作流程、安全停止、校准、OCR、筛选、收藏、转发和焦点恢复语义。
3. 用户能从 CLI Banner、帮助、文档、版本或发布信息中识别 Ocria / Am7 身份。
4. BossOCR 保持独立可用，不被 Ocria 开发污染，并继续承担 fallback 角色。

### 6.2 产品与开发层目标

1. 确认一个精确、可追溯、经批准的 BossOCR Source Baseline。
2. 固化 Source Repository、Source Branch、Source Commit SHA、Commit Message 和 Baseline 时间。
3. 记录 Ocria 与 BossOCR 的继承关系及仓库边界。
4. 建立 Ocria Am7 产品身份，但不把品牌迁移扩展为大规模代码重构。
5. 定义 Frozen Legacy Core、Protected Integration Zone、Migration / Infrastructure Zone 和 Am7 Greenfield Zone。
6. 建立 Algorithm、Parameter、Schema 和 Observable Behavior 四类冻结合同。
7. 完整保留并执行 Legacy 自动化测试，建立 Full、Critical 和 Golden Replay / Fixture 三层回归屏障。
8. 把真实 BOSS 页面人工 Smoke 设为 Requirement 最终 Acceptance 的必要证据。
9. 为后续 Am7 Requirement 建立必须继承的回归门禁。

### 6.3 完成后必须能回答的问题

AM7-R01 的最终证据必须让维护者无歧义回答：

1. Ocria Am7 精确继承自哪个 BossOCR Commit？
2. Ocria 与 BossOCR 的仓库、远端、版本和维护关系是什么？
3. 哪些 Legacy 运行语义默认禁止修改？
4. 哪些接口或 orchestration seam 允许后续 Requirement 受控集成？
5. 哪些区域专用于 Ocria / Am7 新能力？
6. 如何证明后续 AI 开发没有破坏 BossOCR Legacy 行为？

## 7. Requirement Scope

AM7-R01 包含以下产品级工作成果：

### 7.1 Source Baseline 与 provenance

- 基于真实仓库和可用历史证据确认 BossOCR Stable Baseline；
- 记录来源仓库、来源分支、完整 Commit SHA、Commit Message、Commit 时间及基线确认时间；
- 记录 tag 或 release 等辅助定位，但不得用它们替代完整 SHA；
- 保留 Ocria 从 BossOCR 继承的可审计链路；
- 明确当前基线候选与最终批准基线之间的状态差异；
- 确认 Ocria 与 BossOCR 的仓库写入边界和版本关系。

### 7.2 Ocria Am7 产品身份

- 建立 `Product = Ocria`、`Generation / Codename = Am7` 的用户与发布身份；
- 在不改变 Legacy 业务行为的前提下迁移必要的 CLI、文档、版本、构建和发布显示信息；
- 保留 Legacy 内部 provenance，不因品牌整洁而抹去来源历史。

### 7.3 Legacy Core Freeze Contract

- 对 Algorithm、Parameter、Schema、Observable Behavior 建立正式冻结原则；
- 建立四区模型及默认变更权限；
- 明确 Protected Integration 不是自由修改区；
- 规定任何改变 Frozen Legacy 语义的事项必须由独立 Requirement 明确授权。

### 7.4 Regression Barrier

- 完整保留现有 Legacy Tests；
- 建立全量测试屏障；
- 从真实测试资产中建立关键回归屏障；
- 评估并建立可行的 Golden Replay / Fixture 基线；
- 记录回归证据、环境、基线身份和结果；
- 禁止通过弱化测试来获得通过结果。

### 7.5 Manual Real BOSS Page Smoke

- 形成 Requirement 级人工 Smoke 要求；
- 在后续 TID 中形成可执行的 Manual Smoke Checklist；
- 将人工执行结果作为最终 Acceptance 的必要证据；
- 明确 Codex / Terra 不执行正式真实页面 Smoke，也不得把模拟结果宣称为人工通过。

## 8. Out of Scope

AM7-R01 明确不包含：

- GUI、桌面图形界面、GUI 配置页、窗口、按钮、菜单或主题设计；
- DeepSeek 或任何 AI Provider；
- API Key、Provider Config 或 AI 连接管理；
- ScreeningProfile、Criterion、Screening Rule Engine V2；
- AI Prompt、AI Boolean Contract、AI Screening Runtime；
- AI Store、AI Replay、Candidate AI Processor；
- AI 自动收藏、AI 自动转发；
- 候选人完整扫描的新接口；
- `scan_candidate()` 或等价“纯完整扫描路径”，该能力属于后续 AM7-R06；
- 为清理技术债而重写 Legacy Core；
- 仅为品牌原因进行大范围文件、symbol、import 或模块重命名；
- 调整 R02—R07 算法、OCR/相似度/聚合阈值、滚动与等待预算或 WindMouse 参数；
- Codex / Terra 登录真实 BOSS 账号或自动执行真实收藏、真实转发；正式真实页面操作仅允许作为最终人工 Smoke，由人工在受控条件下决定是否执行。
- 在当前 RPD 编写阶段编写 TID、Change 级方案、Terra 初始化提示词或 Terra Change Prompt；
- 在当前 RPD 编写阶段修改生产代码、测试代码、打包、工作流或发布配置。

## 9. Legacy Baseline 的业务定义

### 9.1 Baseline 不是“最新代码”

Legacy Baseline 是一个经证据确认、经人工批准、可被精确检出和重复验证的 BossOCR 产品状态。它至少同时满足：

- 来源明确：能定位到唯一 Source Repository 和 Source Branch；
- 内容唯一：以完整 Commit SHA 为主标识；
- 语义明确：知道该状态承载哪些 Legacy 能力和已知限制；
- 验证明确：有与该状态关联的自动化结果及适当的人工证据；
- 时间明确：区分 commit 时间、tag/release 时间和 R01 基线确认时间；
- 关系明确：知道 Ocria 如何继承它，BossOCR 又如何继续独立维护；
- 可复核：未来维护者无需依赖聊天记忆即可重建上述结论。

最新 HEAD、远端默认分支、最新 tag 或最新 release 可以成为候选证据，但任何一个都不能单独代替上述确认。

### 9.2 Provenance 的产品要求

Ocria 必须保留足够的来源信息，使未来能够：

- 定位继承点；
- 区分 Baseline 原有内容与 Ocria 后续新增内容；
- 对照 BossOCR 继续演进的独立历史；
- 在回归或事故调查时判断差异首次出现在哪条产品线；
- 证明 Ocria 没有反向污染 BossOCR Stable 仓库。

Provenance 应是仓库内可审查的持久信息，而不是只存在于本聊天框、某台机器的 remote 配置或维护者记忆中。

## 10. 四区代码治理模型

四区模型定义的是变更权限和语义边界。最终文件与函数映射必须在 TID 阶段基于真实代码、调用路径和测试审计后冻结；RPD 不把候选文件名直接升级为最终技术结论。

### 10.1 A 区：Frozen Legacy Core

该区域承载已稳定且后续 AI 接入不应改变的 Legacy 运行语义。默认禁止行为变化；只有独立 Requirement 明确说明动机、兼容性、迁移和专门验收时才能改变。

当前强候选包括鼠标移动、校准、R04 标准化、R05 聚合、R06 相似度、R07 动态结束、Candidate / Record / Store / Replay 等模块。TID 必须确认每个候选是否仍在稳定运行路径、是否遗漏其他核心模块、是否存在废弃文件，以及冻结应按文件、函数、数据合同还是可观察行为表达。

### 10.2 B 区：Protected Integration Zone

该区域承载 Legacy Core 与上层 CLI / orchestration 的连接。它允许后续 Am7 Requirement 在明确的接口或集成缝中做最小、受控的接入，但不允许顺手重写周围 Legacy 行为。

当前重点候选是 `ocr_detector.py` 和 `simple_brush.py`。两者体量和职责较多，不能简单按“整个文件可改”处理。TID 必须识别后续允许集成的职责边界，同时把 R02—R07 算法、候选人循环、动作安全门、停止行为和恢复预算等受保护语义明确排除。

### 10.3 C 区：Migration / Infrastructure Zone

该区域服务于 Ocria 身份、文档、依赖、构建、发布和维护基础设施。它可以为 R01 目标进行必要修改，但不得借迁移改变 Legacy 业务行为。

典型内容包括 README / docs、ignore 规则、requirements、spec、build/setup/start scripts、release workflow、version/release metadata、CLI Banner、CLI help 和其他终端用户可见文字。最终修改范围由 TID 审计后确定。

### 10.4 D 区：Am7 Greenfield Zone

该区域用于后续 Am7 新能力，优先通过新增模块和独立数据结构承载。未来可能出现 `ai_*`、`screening_*`、`providers/` 或候选人处理协调模块，但这些名称只是方向示例，不是 R01 的创建任务。

AM7-R01 不实现 Greenfield 功能。它只建立“新能力应优先在新区域开发、通过受控接口消费 Legacy Evidence”的产品原则。

## 11. Legacy Core Freeze 原则

冻结的对象是运行语义，不是“任何文件一个字符都不能修改”。纯文档、注释、产品显示文字或经证明不影响行为的迁移可以在获得 TID 授权后发生；任何可能影响下述合同的变化都视为行为变化，必须停止并重新确认授权。

### 11.1 Algorithm Freeze

AM7-R01 及后续未专项授权的 Am7 Requirement 不得改变：

- R02 详情页加载检测算法；
- R03 页面内容指纹算法；
- R04 OCR 文本标准化算法；
- R05 多屏增量聚合算法；
- R06 页面相似度与有效新增判断算法；
- R07 OCR 扫描状态机与动态结束算法；
- 与上述算法共同决定 Legacy 扫描、证据和退出结果的既有逻辑。

### 11.2 Parameter Freeze

不得借 R01 或 AI 接入顺手调整：

- OCR confidence；
- 加载、聚合、相似度、SimHash 和有效新增 threshold；
- R05 / R06 配置；
- 最大 OCR 屏数和最大滚动次数；
- scroll 范围；
- wait timing；
- retry budget；
- candidate switch / load / focus recovery budget；
- WindMouse 或 fallback 鼠标轨迹参数；
- 其他会影响 Legacy 结果或浏览器动作节奏的常量。

### 11.3 Schema Freeze

不得因 AI 接入改变已有数据结构和字段的意义，包括但不限于：

- `CandidateOcrDocument` 字段语义；
- `OcrScreenRecord` 及相关 record 语义；
- Stage-0 Evidence 语义；
- R02—R07 已有字段含义和可空性解释；
- OCR Store 当前数据语义；
- OCR Replay 对当前和 legacy 数据的解释。

未来 AI 数据应优先进入独立新增结构，通过明确引用关联 Legacy Evidence，不应把 AI 结果回填成 Legacy 原始事实。

### 11.4 Observable Behavior Freeze

不得非预期改变用户或页面能够观察到的 Legacy 行为：

- CLI 启动、参数、交互、帮助和错误退出语义；
- 浏览器页面准备与前台窗口选择；
- 校准模板读取、运行期校准与取消/失败回退；
- 首位 Candidate 打开与后续 Candidate 切换验证；
- R02 加载检测、OCR、滚动、二次确认和 R07 结束；
- 收藏、转发及其互斥和安全门；
- 收藏/转发后的焦点恢复；
- Pause、ESC、Duration Stop 与正常退出；
- 100 人后的刷新、最近没看过筛选和首位归位；
- 已有异常处理、fail-open / fail-closed 选择和安全降级行为；
- 已有隐私边界和不泄露候选人内容的日志要求。

品牌显示文字是 R01 明确允许评估的例外，但文字迁移不得改变参数、分支、等待、点击、退出码或其他运行语义。

## 12. Protected Integration 原则

Protected Integration Zone 必须遵循以下产品级规则：

1. 后续 Requirement 只能修改其 TID 明确授权的接口、orchestration 或 integration seam。
2. 被授权的接入范围必须能与 Frozen Legacy 行为分开验证。
3. 不得以“减少重复”“统一抽象”“顺便清理”为理由扩大到周围 Legacy 逻辑。
4. 新能力优先消费已有 Legacy 输出，不反向改变 Legacy Evidence 的生成和解释。
5. 新失败模式不得绕过 Legacy 的 ESC、Pause、Duration Stop、安全停止或动作门禁。
6. 任何无法证明无行为影响的变化，应按 Legacy 行为变化处理并停止，等待独立 Requirement。
7. `simple_brush.py` 之类多职责文件必须按职责或函数边界保护，不能赋予整文件自由修改权。

## 13. Regression Barrier 业务要求

Regression Barrier 是后续 Am7 Requirement 的共同准入门。它不只在 R01 建立时执行一次；后续每个可能接触 Legacy 或 Protected Integration 的 Change 都必须按适用范围重复执行并保存结果。

### 13.1 Barrier A：Full Legacy Test Suite

要求：

- 完整保留基线中已有的 Legacy Tests 和测试数据；
- 使用统一、可重复的方式执行全量测试；
- 结果必须为 0 failure、0 error；
- 记录实际执行环境、基线或待验收提交、命令、实际测试总数和结果；
- 实际测试总数必须由执行结果获得，不在 RPD 中写死；
- 新增测试不得替代或掩盖原有测试。

禁止：

- 删除失败测试；
- 使用 skip、xfail、条件屏蔽或不收集来规避失败；
- 降低 assert 强度；
- 修改 expected 迎合非授权行为变化；
- 删除或替换测试数据来制造通过；
- 只运行新增测试后宣称 Full Legacy Suite 通过。

若确有测试本身错误，必须停止当前 Change，并以独立、可审查的证据说明问题；不得在同一次功能 Change 中静默修正后继续宣称无回归。

### 13.2 Barrier B：Critical Legacy Regression Suite

R01 必须从真实仓库测试和稳定运行路径中确定一组高价值、快速、可重复的关键测试。它至少需要考虑覆盖：

- mouse motion 与点击最终落点；
- calibration profiles / steps / template / OCR region；
- OCR text 与 normalization；
- aggregation；
- similarity；
- candidate、records、store、replay；
- detector 与 R02—R07 关键合同；
- Stage-0 integration；
- `simple_brush` orchestration；
- Candidate Switch Verification；
- favorite、forward、focus restore；
- Pause、ESC、Duration Stop、100 人批次和 CLI 关键路径。

RPD 不指定测试文件名或命令。最终名单必须由 TID 对当前真实测试资产、覆盖内容和运行时间审计后确定，且不能因未来某个 Change 不方便而临时缩减。

### 13.3 Barrier C：Golden Replay / Fixture

R01 必须审计仓库内已有 fixture、OCR Replay、CandidateOcrDocument、历史 OCR sample、smoke fixture 和历史 acceptance 数据，评估哪些数据可以合法、稳定且不泄露个人信息地形成 Golden Baseline。

在证据充分且数据合规时，Golden 对照应优先覆盖：

- screen count；
- scan / dynamic end reason；
- aggregated text 或其稳定、隐私安全的等价摘要；
- `CandidateOcrDocument` 的关键结构和字段语义；
- R02—R07 critical summary；
- Store → Replay 的一致解释。

Golden 的目标是识别未授权变化，不是阻止所有允许的扩展。若当前仓库没有合适数据，R01 必须记录评估结论、缺口和后续可接受方案，不能伪造真实历史样本，也不能把包含候选人个人信息的运行数据直接纳入仓库。

### 13.4 Barrier 结果解释

- Full Suite 通过证明当前自动化覆盖内没有已知失败，不等于真实页面通过。
- Critical Suite 用于快速发现高价值回归，不替代 Full Suite。
- Golden Replay / Fixture 证明给定输入和数据解释的稳定性，不证明真实浏览器动作可用。
- 三层自动化结果都不能替代 Manual Real BOSS Page Smoke。

## 14. Brand Migration 边界

### 14.1 目标身份

- Product：Ocria
- Generation / Codename：Am7

用户应能在 Ocria 的 CLI 启动、帮助、用户文档、版本和发布信息中识别这一身份，同时仍可从 provenance 文档知道其继承自哪个 BossOCR 基线。

### 14.2 允许的迁移方向

R01 可在 TID 明确授权后迁移：

- README 和用户文档中的当前产品身份；
- CLI 启动 Banner、help / description 和终端用户可见标题；
- version 与 release metadata；
- 必要的打包显示名称和 release asset 身份；
- setup、start、build 和 workflow 中面向 Ocria 的显示信息；
- Frozen 文件中经证明纯用户可见、无行为影响的 BossOCR 品牌文字。

### 14.3 禁止的品牌扩张

Brand Migration 不等于 Code Refactor。R01 不应仅为名称整洁而：

- 大范围重命名 Legacy 文件；
- 大范围重命名 symbol、import 或持久化字段；
- 改写 Legacy schema；
- 改变 CLI 参数或交互；
- 改变运行流程、默认值或安全行为；
- 删除 BossOCR 来源信息；
- 设计或增加 GUI 品牌元素。

Legacy 内部文件名可以继续存在。用户可见身份与内部来源历史可以同时成立。

## 15. Manual Real BOSS Page Smoke

### 15.1 Requirement 级要求

AM7-R01 最终 Acceptance 前，必须由人工在受控环境中执行真实 BOSS 页面 Smoke，以确认仓库迁移、品牌迁移和 Regression Barrier 建立后，Legacy 浏览器自动化行为仍然正常。

该 Smoke 由人工负责，Codex / Terra 不负责登录账号、控制真实浏览器或执行正式收藏/转发。TID 应提供 Checklist，但不能预先宣称执行结果。Smoke 必须验证 favorite / forward Legacy 路径，但不要求为了验证而对无关真实候选人或真实外部收件人产生业务影响；人工可使用受控测试对象、受控目标，或采用经人工认可、能够证明相应 Legacy 路径的等价安全验证方式。

### 15.2 最低检查范围

人工 Checklist 至少覆盖：

- Ocria CLI 正常启动并显示正确产品身份；
- 校准模板读取或运行期校准正常；
- BOSS 页面准备正常；
- Candidate 正常进入；
- R02 加载检测正常；
- OCR 正常；
- 多屏滚动正常；
- R07 正常结束；
- Candidate 切换正常；
- favorite Legacy 路径通过受控对象、受控目标或经人工认可的等价安全方式验证正常；
- forward Legacy 路径通过受控对象、受控目标或经人工认可的等价安全方式验证正常；
- 上述 favorite / forward 验证所覆盖的 focus restore 正常；
- Pause、ESC、Duration Stop 和正常退出正常。

具体候选人数、运行时间、测试账号、邮箱、页面状态和是否进行受控真实动作，由最终人工环境与安全条件决定，不在 RPD 中写死。

### 15.3 证据边界

- 人工 Smoke 必须记录测试对象版本 / commit、环境、时间、检查项、结果和异常。
- 若选择执行真实收藏或转发，只能由获授权人员使用受控测试对象、受控目标并在小范围条件下决定和执行；不得为 Smoke 对无关真实候选人或真实外部收件人制造业务影响。
- 若不适合执行真实业务动作，可由人工认可能够证明 favorite / forward Legacy 路径的等价安全验证方式；必须记录验证方式、适用边界和人工认可结论。
- 自动化、mock、fixture、截图 OCR 或打包 smoke 均不得标记为“真实 BOSS 页面 Smoke 通过”。
- 若安全条件不允许执行某项真实动作，该项不能被自动视为通过；应由人工决定受控测试方式或认可等价安全验证，并留下证据。没有可接受证据时，最终 Acceptance 应等待人工决议或明确的 Requirement 变更。

## 16. 风险与 Failure Mode

| 风险 / Failure Mode | 影响 | Requirement 级控制 |
| --- | --- | --- |
| 把当前 HEAD 或 latest tag 直接当 Stable Baseline | 继承点可能错误，后续差异无法归因 | 强制交叉核对 repo、branch、SHA、历史、测试、发布与验收证据，并人工批准 |
| Ocria 与 BossOCR 共用或混淆写入边界 | Ocria Change 污染 Legacy Stable | 固化独立产品线、remote / repo 关系与 provenance；禁止向 BossOCR 仓库实施 Am7 Change |
| 品牌迁移演变为大规模重构 | 引入非必要回归，难以审查 | 只迁移必要用户可见与发布身份；内部 Legacy 名称可保留 |
| Protected Integration 被当作自由修改区 | AI 接入改变 R02—R07 或主循环语义 | 由 TID 建立函数 / 职责级边界；未授权变化立即停止 |
| 顺手调参或优化算法 | Legacy 结果与动作节奏漂移 | Algorithm / Parameter Freeze；需要改变时另立 Requirement |
| AI 数据污染 Legacy Evidence | Replay、审计和历史数据失去原义 | Schema Freeze；AI 数据使用独立结构和明确引用 |
| 为让回归通过而弱化测试 | 产生虚假安全信号 | 禁止删、跳、降 assert、改 expected 迎合回归；保存原始结果 |
| Critical Suite 覆盖不足或被任意缩减 | 快速门无法发现关键回归 | 从真实稳定路径审计形成名单，并受 R01 合同约束 |
| Golden 数据含个人信息 | 隐私和合规风险 | 优先使用合成、脱敏或可合法提交的数据；不得复制真实候选人内容入库 |
| Golden 过度严格 | 合法的新增字段或无害扩展被误判 | 对照稳定语义和关键摘要，明确允许扩展与禁止变化 |
| 自动化通过被误当作实机通过 | 页面布局、焦点、浏览器环境问题被遗漏 | Manual Real BOSS Page Smoke 是独立且必要的最终证据 |
| 人工 Smoke 无版本或环境记录 | 结果不可复核 | Checklist 强制记录 commit、环境、时间、范围和结果 |
| 只迁移文案但遗漏构建 / release 身份 | 用户下载或运行时仍混淆产品 | TID 全面审计 CLI、spec、scripts、workflow、version 和 release metadata |
| 只记录本机 remote，不在仓库保留 provenance | 换机或克隆后继承关系丢失 | provenance 必须成为可审查的仓库持久信息 |
| 技术债诱发 Scope 扩张 | R01 延期且行为变化混入迁移 | 技术债登记但不实施；转为独立 Requirement 评估 |
| 正式 Smoke 误触真实业务动作 | 影响真实候选人或外部收件人 | 仅人工、受控、小范围、可立即 ESC；Codex / Terra 不执行 |

## 17. Requirement 级验收标准

AM7-R01 只有在以下条件全部满足并有可定位证据时，才可进入最终 Accepted。自动化 Change 完成不等于 Requirement Accepted。

### 17.1 Baseline 与仓库关系

- **AC-01**：记录并人工批准唯一 BossOCR Source Repository、Source Branch 和完整 Source Commit SHA。
- **AC-02**：记录 Source Commit Message、commit 时间、R01 baseline 确认时间，以及 tag / release 等辅助定位信息。
- **AC-03**：证据说明为何该提交是 Stable Baseline，而不是只因它是当前 HEAD、latest 或默认分支。
- **AC-04**：仓库内存在持久、可审查的 Ocria ← BossOCR provenance，换机或重新 clone 后仍可理解。
- **AC-05**：BossOCR Legacy Stable 与 Ocria Am7 的仓库、remote、版本和维护边界清晰；没有证据表明 Am7 Change 写入 BossOCR 稳定仓库。

### 17.2 身份与范围

- **AC-06**：用户可见的产品身份为 Ocria，Generation / Codename 为 Am7；必要的 CLI、文档、版本、构建和发布显示范围一致。
- **AC-07**：品牌迁移未引入 GUI，未实施 AI，未进行仅为品牌的 Legacy 文件 / symbol 大规模重构。
- **AC-08**：Ocria 仍保留 BossOCR Legacy 业务能力和可观察操作语义，除明确批准的产品显示身份外无非预期变化。

### 17.3 Freeze Contract

- **AC-09**：形成经人工审查的四区 Freeze Matrix，覆盖 Frozen、Protected、Migration / Infrastructure 和 Greenfield。
- **AC-10**：Algorithm、Parameter、Schema、Observable Behavior 四类冻结合同均有明确对象、禁止变化和授权规则。
- **AC-11**：Protected Integration Zone 有足够精度的受控边界，不能被解释为整个 `ocr_detector.py` 或 `simple_brush.py` 自由修改。

### 17.4 Regression Barrier

- **AC-12**：基线已有 Legacy Tests 和测试数据完整保留，没有删除、skip / xfail、弱化 assert、迎合回归的 expected 修改或收集规避。
- **AC-13**：Full Legacy Test Suite 在最终待验收 Ocria 状态执行，实际执行总数如实记录，结果为 0 failure、0 error。
- **AC-14**：Critical Legacy Regression Suite 由真实仓库审计确定，覆盖关键 Legacy 路径，并在最终待验收状态通过。
- **AC-15**：Golden Replay / Fixture 已完成隐私安全和技术可行性评估；可行时建立并通过稳定对照，不可行时有明确证据、缺口和后续处置，不得伪造或使用不合规真实数据。
- **AC-16**：所有自动化证据都记录对象 commit、环境、命令、范围、实际结果与时间，且没有宣称覆盖其作用域之外的真实页面行为。

### 17.5 人工最终验收

- **AC-17**：Manual Smoke Checklist 已形成，并明确真实 BOSS 页面 Smoke 由人工执行。
- **AC-18**：人工在最终待验收 commit 上完成真实 BOSS 页面 Smoke，记录环境、范围和结果；最低检查范围覆盖 CLI、校准、页面准备、Candidate、R02、OCR、滚动、R07、切换、favorite Legacy 路径、forward Legacy 路径、focus restore、Pause / ESC / Duration Stop / 正常退出。favorite / forward 可使用受控测试对象、受控目标或经人工认可的等价安全验证方式，不要求为了 Smoke 对无关真实候选人或真实外部收件人产生业务影响。
- **AC-19**：没有将 Codex / Terra 的 mock、fixture、自动化或浏览器模拟结果冒充人工真实页面 Smoke。
- **AC-20**：RPD、TID、各 Change 自动化证据和人工 Smoke 证据完成最终人工审查，所有阻塞问题已解决或由新的 Requirement 明确承接。

## 18. 后续 Am7 Requirement 对 R01 的依赖

AM7-R01 是后续 Am7 Requirement 的前置安全基础。

### 18.1 统一依赖规则

后续 Requirement 必须：

- 引用 R01 批准的 Source Baseline 与 Freeze Contract；
- 声明将修改的代码区域分类；
- 对任何 Protected Integration 修改给出明确授权边界；
- 优先在 Greenfield Zone 增加新能力和新数据；
- 执行适用的 Critical Barrier，并在最终阶段执行 Full Legacy Barrier；
- 在可能影响 Golden 语义时明确说明这是授权变化还是回归；
- 不得以“AI 需要”为理由跳过 Algorithm、Parameter、Schema 或 Observable Behavior Freeze。

### 18.2 与后续 AI Requirement 的关系

DeepSeek、Provider、Profile、Criterion、Prompt、Boolean Contract、AI Runtime、AI Store / Replay 和 Candidate AI Processor 等能力都必须在各自独立 Requirement 中设计。R01 不预先决定其技术实现，只要求它们：

- 不污染 Legacy Evidence；
- 不改变 Legacy 算法与参数；
- 通过受控 seam 消费 Legacy 输出；
- 保留 Legacy fallback；
- 用 R01 Regression Barrier 证明没有引入未授权回归。

候选人完整扫描的新接口或 `scan_candidate()` 等价能力属于 AM7-R06，不得提前落入 R01。

## 19. TID 阶段必须回答但本 RPD 不预先设计的问题

RPD 人工通过后，TID 阶段必须基于全面仓库审计确定：

- 最终 Source Baseline 的确认方法和证据链；
- provenance 与 baseline metadata 的具体落点；
- 四区的精确文件 / 函数 / 数据合同映射；
- `ocr_detector.py`、`simple_brush.py` 的函数级 Protected Boundary；
- 品牌迁移的精确修改范围；
- Full / Critical Regression 的具体命令和名单；
- Golden fixture / replay 的资产、摘要和隐私策略；
- Manual Smoke Checklist 的具体格式；
- Change 数量、顺序、允许 / 禁止文件、前置条件和 Stop Condition；
- 每个 Change 与最终 Requirement Acceptance 所需证据。

这些问题在 RPD 中只作为后续设计责任，不构成当前实施授权。

## 20. 当前开放项

| 编号 | 开放项 | 当前状态 | 关闭阶段 |
| --- | --- | --- | --- |
| O-01 | `a7c9419...` 是否最终批准为 BossOCR Stable Baseline | 强候选；尚未批准 | TID 审计与后续基线确认 Change |
| O-02 | Ocria 独立 remote、仓库元数据和版本起点如何表达 | 当前未观察到 Ocria remote；未设计 | TID |
| O-03 | 四区最终文件 / 函数边界 | 仅有产品级原则和候选 | TID |
| O-04 | Critical Suite 精确名单与命令 | 未设计 | TID |
| O-05 | 可复用 Golden 数据是否存在且符合隐私要求 | 待全面审计 | TID |
| O-06 | 当前 full suite 的实际测试数和结果 | 本 RPD 阶段未执行，不写死 | Change 执行与最终验收 |
| O-07 | 真实 BOSS 页面 Smoke 的账号、环境、时长和动作范围 | 由最终人工环境决定 | 最终人工验收 |
| O-08 | Am7 RPD / TID / Baseline / Acceptance 文档的仓库版本化方式 | 当前一般 `*.md` 受 `.gitignore` 忽略；RPD 阶段不修改 `.gitignore` | TID |

开放项不是对 Requirement 的降级。凡属于 AC-01—AC-20 的事项，未关闭前 AM7-R01 均不能标记 Accepted。

## 21. RPD 审查门与本阶段声明

人工审查本 RPD 时，应重点确认：

1. Ocria 与 BossOCR 的产品关系是否准确；
2. CLI 产品形态和 GUI Out of Scope 是否明确；
3. Source Baseline 的业务定义是否足以避免“latest = stable”；
4. Freeze Contract 是否完整覆盖算法、参数、schema 和可观察行为；
5. Protected Integration 是否既允许后续受控接入，又没有放开 Legacy Core；
6. 三层 Regression Barrier 和人工真实页面 Smoke 是否边界清晰；
7. Brand Migration 是否保持“身份迁移，不做大规模重构”；
8. Requirement 验收标准是否可由后续 TID 和 Change 提供证据；
9. 是否存在任何提前设计 AI、GUI、AM7-R06 或 Terra 执行步骤的越界内容。

本阶段只新增本 RPD 文档。未编写 AM7-R01 TID，未设计 Terra 初始化提示词或 Change Prompt，未执行 Change，未修改生产代码、测试、构建、发布流程或运行数据，未登录或操作真实 BOSS 页面。

RPD 完成后停止，等待人工审查。
