# BossOCR 阶段 2A 资料缺口

本文件只记录会影响后续需求抽取或事实判断的缺口，不把“无法访问”写成“未发现”。

| 编号 | 缺失或冲突 | 为什么重要 | 是否阻塞需求台账 | 下一步 |
| --- | --- | --- | --- | --- |
| GAP-01 | GitHub Issues 无法读取：`gh` 当前账户令牌无效，且 GitHub 网络连接经 127.0.0.1 代理失败。 | Issue 可能包含最早提出时间、原始问题、讨论、状态和关闭原因。 | 阻塞依赖 Issue 原文的条目；不阻塞只由仓库证据支持的条目。 | 修复 `gh auth login` 并恢复网络后，只读导出 open/closed Issue 的编号、时间、正文、评论和状态。 |
| GAP-02 | GitHub Pull Requests 无法读取。 | PR 可证明评审语境、合并时间、变更归属和被否决方案。 | 阻塞需要 PR 评审或合并结论的字段。 | GitHub 恢复后读取 merged/closed PR、review 与检查结果；不得用 commit message 替代评审。 |
| GAP-03 | GitHub Releases、附件和 Actions/Checks 无法读取。 | 本地 tag 与发布说明不能单独证明远程 Release、附件、发布时间或 CI 实际通过。 | 阻塞正式 released 状态和远程构建结论。 | GitHub 恢复后核对 Release/tag/asset SHA、发布时间和关联 Actions。 |
| GAP-04 | 旧编号 R26/R27 等仅在规则评审语境中被提及，本轮仓库扫描未取得可定位原始资料。 | 旧编号关系影响 legacy_ids 映射，不能凭编号形态推定主题或状态。 | 阻塞对应旧编号映射。 | 由原开发者提供原 Issue/文档定位，或在 GitHub 恢复后按全文检索核对。 |
| GAP-05 | Next-4 TID V1.0 与 V1.1 同属一个主题，但正文未像 Next-5 V1.1 那样明确声明“基于 V1.0 修订”。 | 错误写成 supersedes/revises 会制造版本因果。 | 不阻塞两个来源登记；阻塞正式版本关系。 | 人工确认或补充同期评审记录；确认前保留两份并将关系标为待核对。 |
| GAP-06 | Next-5 V1.1 明确基于 V1.0 修订，但两份 TID 当前均为未跟踪归档，缺少其自身 Git 首次出现时间。 | 只能确认文本版本关系，不能确认准确创作/评审时间。 | 不阻塞主题抽取；阻塞 exact_day 排序。 | 通过原始文件、聊天/Issue 时间或后续 GitHub 记录补充；当前日期精度降级。 |
| GAP-07 | 多份根目录 PRD/TID/Windows 报告与 2026-07-02 release notes 为 ignored/untracked，历史来源和首次形成时间不能由 Git 证明。 | 文件系统修改时间不等于历史日期，后期搬移也可能改变 mtime。 | 不阻塞内容主题；阻塞精确时间与发布归属。 | 以正文日期仅作为 historical_date_claim，并用原作者记录、GitHub 或旧备份交叉验证。 |
| GAP-08 | Next-1 至 Next-6 多数没有独立 Implementation Report；实现事实主要由 commit、代码、测试与 Acceptance Report 拼接。 | TID 只能证明计划，验收报告也需要与代码/提交交叉验证。 | 不阻塞，但提高逐条抽取工作量和不确定性。 | 阶段 2B 按每个主题核对提交、代码、测试和报告，不把 TID 直接标为完成。 |
| GAP-09 | Next-7 有 TID、代码、测试、构建与验收报告，但报告明确 Windows Edge 实机观感待验证；远程 Release 又不可访问。 | 自动化与构建通过不等于真实 GUI 或正式发布。 | 阻塞 accepted/released 的最终判断边界。 | 保留 automated acceptance 与 manual smoke/release 为不同事实，等待人工记录和远程核对。 |
| GAP-10 | macOS 资料证明 OCR 核心与 mock 测试，但明确未完成真实 RapidOCR、屏幕录制、Retina 坐标和主程序接入。 | “存在 macOS 分支”不能推导“macOS 产品已支持”。 | 阻塞 macOS released/accepted 结论。 | 后续条目将 platform 状态拆开，并只在获得真实联调/发布证据后提升状态。 |
| GAP-11 | 校准模板验收报告称自动化通过，但列出的 12 项真实 Boss 页面冒烟仍待执行；v1.2 release notes 又声称人工 Windows 冒烟通过。 | 同一能力的人工验收状态存在时间层次，需要区分报告生成先后和具体范围。 | 阻塞笼统的“人工验收全部通过”结论。 | 阶段 2B 核对后续冒烟记录、commit 和 Release 时间；在此之前并列保留两个说法。 |
| GAP-12 | Windows Stable v1.1 文档/2026-07-02 notes 声称 ZIP SHA 为 `795D...`，当前本地 `release/BossOCR-Windows-x64.sha256.txt` 为 `93E5...`。 | 可能对应不同构建或 v1.2；不能把当前 checksum 反写到旧发布。 | 阻塞本地 artifact 与具体 release 的自动关联。 | 按资产文件时间、Release 附件和 tag 逐版核对；没有远程证据前保持冲突。 |
| GAP-13 | `logs/simple_brush.log` 含潜在候选人和邮箱等个人信息，只进行了结构性抽查。 | 日志可能提供运行事件，但不应把隐私原文带入台账。 | 不阻塞；个别事故若仅依赖日志会需要受控复核。 | 由授权人员在本地做脱敏摘要，只记录事件计数、错误类型和时间范围。 |
| GAP-14 | 未发现独立 Development History、完整 Maintenance Document 或原开发者人工历史说明。 | 后期接手者需要把设计演进与维护禁区串联，但不能由后期叙事替代同期证据。 | 不阻塞逐项抽取；阻塞完整叙事。 | 后续从台账生成演进视图，并向原开发者定向补问缺失因果，不预先编故事。 |

## 禁止继续推导的情形

出现下列情况时，阶段 2B 必须停止该条因果推导并标记人工确认：远程原始对象不可访问且本地资料互相冲突；唯一来源是后期总结且无同期材料；版本关系只由文件名推测；发布资产 SHA 无法对应具体版本；平台“计划/核心代码存在”被误当成可交付支持。
