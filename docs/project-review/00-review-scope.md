# 阶段 0：复盘目标、受众与交付边界

## 1. 复盘目标

本次复盘要建立一条可复核的 BossOCR 演进链：从业务问题和运行事件出发，连接需求、调查、设计决策、实现、测试、验收与发布，并清楚保留未完成、被替代、相互冲突或无法确认的部分。

复盘的成功标准不是“故事完整”，而是三年后接手者能定位事实、重建上下文、理解约束，并知道哪些结论仍需重新验证。招聘或作品集展示是次要用途，不能改变事实选择、风险表述或置信度。

本轮只制定规则与数据契约，不抽取正式需求，不评价项目整体成败，也不制作图或原型。

## 2. 读者

### 2.1 核心读者

- 三年后接手 BossOCR 的开发者。

核心读者应能从复盘结果中恢复：需求为何出现、系统当前实际支持范围、关键安全门、回退路径、证据位置、未解决问题，以及哪些测试或人工条件必须重跑。

### 2.2 次要读者

- 招聘团队；
- 项目维护者；
- 技术面试官或作品集评审者；
- 未来重新回顾项目的原开发者。

次要读者可获得不同粒度的视图，但所有视图必须由同一份已确认台账生成，不得为展示效果改写事实。

## 3. 必须回答的核心问题

最终复盘必须能够用证据回答：

1. 为什么会开发 BossOCR；
2. 项目如何一步步演进；
3. 为什么形成今天的架构；
4. 为什么做出关键设计决策；
5. 已经踩过哪些坑；
6. 哪些设计和测试约束不能被轻易推翻；
7. 项目形成了怎样的需求分析、实施、测试和验收工作模式。

如果某个问题的仓库证据不足，最终答案应明确为 `unknown`、`uncertain` 或 `conflicting`，而不是补写合理但未被记录的叙事。

## 4. 最终交付物

本次复盘的最终交付物至少包括：

- 需求事件台账；
- 证据索引；
- 标准需求分析流程图；
- 项目需求演进图；
- 重点需求追溯图；
- 原型信息架构；
- 低保真可点击原型；
- 高保真复盘原型；
- SVG、PNG、PDF 等静态导出版；
- 最终事实验证报告。

其中规范 JSON 台账是事实主文件；CSV 和 Markdown 是评审视图；图、原型和静态导出是展示视图；证据索引用于证明和限定台账中的声明。

## 5. 明确不属于本次复盘的内容

- 新版 README；
- Changelog；
- 单纯功能说明书；
- 单纯提交记录罗列；
- 重新编写全部维护文档；
- 没有因果关系的时间流水账；
- 没有证据支持的项目故事包装。

复盘可以引用 `docs/README.md`、发布说明和维护近似资料，但不以改写它们为目标。Git 提交是证据的一类，不是天然的需求单位；功能清单只有在连接问题、决策、验证和发布时才构成复盘内容。

## 6. 本轮工作边界

### 6.1 本轮产出

- 冻结范围、读者、核心问题和阶段门禁；
- 定义需求纳入与非需求事件识别规则；
- 定义模块、平台、类型、状态、风险、证据、置信度和冲突处理；
- 定义稳定编号、字段、空值和三种台账视图的序列化规则；
- 提供可由标准 JSON 工具读取的需求台账与证据索引 Schema。

### 6.2 本轮不做

- 不给历史事项分配正式 `R-xxx`；
- 不建立正式需求或证据清单；
- 不推导完整项目时间线；
- 不判断所有已有文档的真伪或完成度；
- 除为本目录 Markdown 建立可跟踪例外所需的最小 `.gitignore` 修改外，不修改 `docs/project-review/` 以外的文件；
- 不提交、打标签、发布或推送。

## 7. 复盘原则

### 7.1 证据优先

每个关键事实应引用一个或多个 `E-xxx`。没有可定位证据时，允许记录问题或人工历史说明，但必须降低置信度并说明不可复核范围。

### 7.2 区分事实、解释和推断

- 事实：证据直接声明或可重复观察的内容，例如某个 tag 指向的 commit、某份测试报告记录的结果。
- 解释：材料作者当时给出的因果或理由，例如 Investigation Report 对根因的解释。
- 推断：复盘者根据多个事实得出的结论；必须标记为推断并列出依据，不能伪装成早期原话。

一个来源可以同时包含三类内容，不能因为文件名是“报告”就把全文都当作同等确定的事实。

### 7.3 不用后期认知覆盖早期真实决策

后期 README、release notes 或总结文档可以说明后来结果，但不能自动替代早期 PRD、Issue、TID 或 Investigation 中的真实约束。若后期认识修正了早期判断，应保留两者及修正关系。

### 7.4 不把实现细节自动升级为独立需求

函数拆分、变量改名、依赖升级、文件搬迁、测试 mock 或某次 commit 通常只是实现或证据。只有当它改变可观察行为、交付能力、维护能力、平台支持或形成独立且可验收的约束时，才评估是否建立需求条目。

### 7.5 不为追求故事完整性而虚构缺失环节

缺少最初提案、Issue 讨论、人工冒烟原始记录或发布产物时，保留缺口。文件内容合理、提交顺序连续或后期总结完整，都不能替代缺失证据。

### 7.6 允许保留不确定项

字段使用 `null`、`unknown`、`not_applicable`，结论使用 `confirmed`、`estimated`、`uncertain`、`conflicting`。不确定项进入 `open_questions`，不得用空字符串、`N/A`、`TBD` 或未经说明的默认值掩盖。

### 7.7 尽量完整追溯生命周期

需求、实现、测试、验收和发布必须尽量可追溯。任何一个环节缺失都应被显式记录；“代码已经修改”不等同于测试、验收或发布已经完成。

### 7.8 结论限定在证据作用域内

自动化 mock 测试只能证明被覆盖的调用与分支；本地 one-dir 构建不等于 ZIP 或 Release 已发布；人工检查清单的存在不等于检查已执行；任一平台的结果只在对应版本、环境和证据作用域内成立，Windows 结果不能外推 macOS，macOS 结果也不能外推 Windows。

## 8. 仓库实际资料边界

本轮盘点确认：

- 当前没有根目录 `README.md`，项目入口文档是 `docs/README.md`；历史材料中的 `README.md` 路径必须结合对应 commit 解释。
- 已有 Investigation Report、TID、Acceptance Report、Smoke Test、Release Notes 和当前 README。
- 根目录还可见 PRD、Next 系列 TID、Windows Implementation/Setup Report 和发布前基线等本地材料；现有 `.gitignore` 的 `*.md` 规则会忽略其中多份文件。后续证据索引必须记录材料是否被 Git 跟踪以及可复核 commit，不能把“当前工作区可见”直接当作历史提交事实。
- 没有独立命名的 Development History、正式维护指南、正式交接文档或项目级统一测试指南。
- `Windows-current-baseline-before-official-v1.0.md` 可作为发布冻结/交接近似资料，`docs/RAPIDOCR_DETAILED_EXECUTION_GUIDE.md` 可作为专项实施维护近似资料，`docs/calibration-template-smoke-test.md` 是专项测试指南；这些近似关系不得改写为文件原本没有声明的文档类型。
- 当前检出的 `main` 分支及其入口文档以 Windows Edge 为稳定产品路径。macOS Chrome 的实现、验收、构建和发布状态尚未在本轮完成跨分支证据核对，因此不得提前判断为已发布、未完成或 experimental。
- 当前检出的 `main` 代码与入口文档没有形成结构化“候选人经历解析”能力；该结论不外推到尚未核对的其他分支。可见文本 OCR 和关键词匹配不等于结构化经历解析。

### 8.1 当前检出范围限制

当前 checkout 只是完整项目历史的一个观察点，不等于完整项目历史。当前 `main` 缺少某项实现、测试、文档、构建或发布材料，不能据此否定其他分支或远端历史可能已有相应工作；反之，其他分支或本地文件中出现材料，也不能自动外推为 `main` 已包含、稳定支持或已发布。任何跨平台、跨分支结论都必须限定 ref、commit、平台、环境和证据作用域。

### 8.2 下一阶段只读证据访问边界

进入正式需求抽取后，为避免由当前 checkout 作单向推断，允许且要求进行以下只读核对：

- 检查所有本地分支、远程跟踪分支及可访问的远端 Git 历史，并读取相关 commit、tag 和目标 ref 下的文件快照；
- 核对 macOS 与 Windows 相关的 TID、Implementation Report、Acceptance Report、自动化测试、构建与冒烟记录、发布产物、Release Notes 和发布阻塞说明，而不是按分支名或文件名判断成熟度；
- 只读查看开放和已关闭的 GitHub Issue、Pull Request、Release 及相关 check/CI 结果，并保存稳定定位；
- 检查工作区中被忽略或未跟踪的本地历史文档，将其作为候选证据并记录 `tracked_state`；文件修改时间或创建时间不得作为项目历史日期；
- 将本地材料与 Git 历史、GitHub 记录、代码、测试、验收和发布事实交叉验证；不可复核的底层日志、截图或口述按证据规则降级或保留不确定性。

以上授权只允许读取、索引和交叉验证。不得修改 GitHub Issue、PR、Release 或 check 状态，不得向远端写入，也不得创建 commit、tag、Release 或 push。若只读远端访问不可用，应记录证据缺口，不得以本地结果替代远端结论。

## 9. 开始前 Git 基线记录

记录时间：2026-07-25，Asia/Shanghai。以下内容是本轮开始前的只读命令结果；未跟踪文件 `venv-packages-before-reinstall.txt` 为原有工作区内容，不属于本轮产物。

### 9.1 `git status --short`

```text
?? venv-packages-before-reinstall.txt
```

### 9.2 `git branch --show-current`

```text
main
```

### 9.3 `git log --oneline --decorate -20`

```text
c36d6e7 (HEAD -> main, tag: v1.2, origin/main, origin/HEAD) feat: finalize Windows calibration template workflow
8082d04 整理文案
c3840b8 feat: add reusable calibration profile workflow
90365ca (tag: v1.1) Add favorite mode and observable mouse motion
b8d2ef3 docs: add Next-6 human mouse motion acceptance report
6d1cafa docs: explain human mouse movement option
fc80c7b test: cover human mouse integration paths
8df66d0 feat: use human mouse paths for region clicks
5a4df35 feat: add observable bezier mouse movement
4e179e7 docs: add Next-5 batch filter acceptance report
cc85c34 docs: explain batch filter navigation
c8bb321 feat: reapply unseen filter at batch boundaries
3fd9866 feat: apply unseen filter before timed browsing
ddd5ea2 feat: calibrate batch filter navigation regions
38c303e docs: add Next-4 any keyword group acceptance report
df172a4 docs: explain any keyword group syntax
5115ede feat: match any keyword groups
d954a2e feat: parse any keyword groups
335dcf7 (tag: windows-stable-v1.1, origin/windows, windows) docs: add Windows stable v1.1 release notes
dfe1617 docs: add P0 double focus restore acceptance report
```

### 9.4 `git tag --sort=-creatordate`

```text
v1.2
v1.1
windows-stable-v1.1
windows-stable-v1.0
issue-1-v1.0
v1.0.0
Boss
```

这些 tag 属于多个命名系列，后续必须保留原文，并用 commit、tag 快照、产物和 release notes 交叉判断发布事实，不能先把它们重写成单一版本序列。

## 10. 阶段 0 完成判据

只有在读者、核心问题、范围、非目标、复盘原则和唯一事实数据源原则得到确认后，才允许进入正式需求抽取。若之后改变这些边界，应先评估是否需要重做已抽取数据，而不是只更新展示文案。
