# BossOCR 阶段 2A 资料阅读登记

- 登记日期：2026-07-25
- 资料总数：79
- 说明：本文件只登记来源与阅读边界，不创建需求条目或正式证据编号。
- 隐私：运行日志仅做结构性抽查，不摘录候选人、邮箱或简历原文。

## 发现基线与扫描边界

- 当前 checkout：`main`。
- 已扫描 Git refs：`feature/rapidocr-mac`、`feature/rapidocr-windows`、`local/rapidocr-windows-original-history`、`local/rapidocr-windows-with-docs`、`main`、`windows`、`origin`、`origin/feature/rapidocr-mac`、`origin/main`、`origin/windows`。
- 已扫描本地 tags：`Boss`、`v1.0.0`、`issue-1-v1.0`、`windows-stable-v1.0`、`windows-stable-v1.1`、`v1.1`、`v1.2`。
- Remote：`origin	https://github.com/carolineasu2005-droid/Boss-OCR.git (fetch)`；`origin	https://github.com/carolineasu2005-droid/Boss-OCR.git (push)`。
- 文件范围：仓库根目录、`docs/`、`docs/tid/next/`、`tests/`、`.github/workflows/`、构建/打包脚本、ignored/untracked 文本、分支独有与历史移动/删除文档；仓库当前没有 `scripts/` 目录。
- 排除：`venv/`、`dist/`、`build/`、release 内第三方依赖、缓存、二进制与自动生成内容。`docs/project-review.zip` 和 `venv-packages-before-reinstall.txt` 按任务要求保留但不作为历史来源。
- GitHub：Issue、PR、Release、Actions 已尝试只读访问，但因无效 `gh` 凭据及代理连接失败登记为 `inaccessible`。

## 八份 Issue-Next TID

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-029 | [Next-1] TID V1.0：转发流程点击区域启动前校准 | docs/tid/next/Issue-Next-1-focus-restore-calibration-TID-V1.0.md | fully_read | 设计运行期焦点恢复区域校准，取消或失败回退默认区域，且所有转发退出路径统一使用区域内精确落点。 | Windows；Next-1 | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-030 | [Next-2] TID V1.0：关键词规则新增 not 排除逻辑 | docs/tid/next/Issue-Next-2-keyword-not-rule-TID-V1.0.md | fully_read | 设计 not 原子、not > and > or 优先级、每个 OR 分支必须含正向条件和完整规则 OCR 二次确认。 | Windows；Next-2 | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-031 | [Next-3] TID V1.0：转发流程全部关键点击点启动前校准 | docs/tid/next/Issue-Next-3-forward-click-calibration-TID-V1.0.md | fully_read | 设计五个转发点击区域的原子校准、最小导航点击、默认回退和转发按钮校准期不点击的安全门。 | Windows；Next-3 | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-032 | [Next-4] TID V1.0：关键词规则支持 `any(...)` 分组表达式 | docs/tid/next/Issue-Next-4-keyword-any-group-TID-V1.0.md | fully_read | 设计 any(...) 作为独立原子参与外层逻辑，禁止展开为顶层 OR，并覆盖 parser/matcher 反例。 V1.0/V1.1 的修订或替代关系未见正文明确声明，本轮不建立 previous_version/next_version。 | Windows；Next-4 | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-033 | [Next-4] TID V1.1：关键词规则支持 `any(...)` 分组表达式 | docs/tid/next/Issue-Next-4-keyword-any-group-TID-V1.1.md | fully_read | 强化 any 原子不可展开、parser/matcher 必须同时可发布、重复项规范化拒绝和阻断验收反例。 V1.0/V1.1 的修订或替代关系未见正文明确声明，本轮不建立 previous_version/next_version。 | Windows；Next-4 | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-034 | [Next-5] TID V1.0：启动及批次刷新后自动应用「最近没看过」筛选并点击首位候选人 | docs/tid/next/Issue-Next-5-batch-filter-first-candidate-TID-V1.0.md | fully_read | 设计四区域筛选归位、启动与批次边界接入、原子回退以及运行中失败安全停止。 | Windows；Next-5 | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-035 | [Next-5] TID V1.1：启动及批次刷新后自动应用「最近没看过」筛选并点击首位候选人 | docs/tid/next/Issue-Next-5-batch-filter-first-candidate-TID-V1.1.md | fully_read | 明确基于 V1.0 修订，补充启动准备不计时、首次 apply 失败不可回退、UI 事实与四段式 Change。 | Windows；Next-5 | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-036 | [Next-6][P2] TID V1.0：优化鼠标移动轨迹——贝塞尔路径、途中抖动与慢-快-慢三段变速 | docs/tid/next/Issue-Next-6-human-mouse-motion-TID-V1.0.md | fully_read | 设计贝塞尔路径、smoothstep 慢快慢、途中抖动、精确终点和 --simple-mouse 回退，强调仅用于可观察性。 | Windows；Next-6 | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |

## macOS 相关材料

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-051 | ocr_mac_demo.py | ocr_mac_demo.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | macOS；OCR、demo | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-065 | RapidOCR Mac 阶段实施报告 | origin/feature/rapidocr-mac:OCR_MAC_IMPLEMENTATION_REPORT.md | fully_read | 记录 macOS 分支 OCR 核心、13 项 mock 测试与依赖/Retina/真实模型尚未联调的边界。 | macOS；RapidOCR、implementation | 有 | 有声明/事实，需与代码交叉 | 无 | 无 | 报告所声称的实现范围、环境、测试结果和未完成边界 | 原始业务动机的完整讨论；未执行的实机验证结果；正式发布状态 |
| SRC-066 | BOSS 直聘自动刷简历工具 | origin/feature/rapidocr-mac:README.md | fully_read | macOS 分支上的早期 Windows 用户说明，仍描述剪贴板全文检测和未接通的 --no-forward，可作为旧行为快照。 | macOS-branch；early-Windows、clipboard | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 该版本面向用户声明的能力、用法、约束与支持平台 | 代码一定符合文档；功能首次提出时间；远程发布对象状态 |
| SRC-067 | Use Python 3.10+ for the Mac OCR development environment. | origin/feature/rapidocr-mac:requirements-ocr-mac.txt | fully_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | macOS；RapidOCR | 未作为主要内容 | 无或不适用 | 无 | 无 | 该版本声明的直接依赖与版本约束 | 依赖已成功安装；运行时实际加载版本；功能验收结果 |

## Windows 发布材料

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-005 | Issue #1 BossOCR minimal changes v1.0 | docs/Issue-1-BossOCR-release-notes.md | fully_read | 记录 Issue #1 最小发布范围、迁移说明、64 项测试声明和 Windows x64 使用限制。 | Windows；Issue-1 | 未作为主要内容 | 有声明/事实，需与代码交叉 | 含验收声明，需核对 | 有发布声明，远程待核 | 发布说明声称的功能范围、使用边界、资产名称与校验信息 | 远程 Release 当前是否存在且附件是否仍一致；代码真实执行细节 |
| SRC-019 | BossOCR Windows Stable v1.1 | docs/windows-stable-release.md | fully_read | 记录 Windows Stable v1.1 功能、110 项测试、GUI 冒烟、单候选人真实转发验证和发布 SHA。 | Windows；v1.1 | 未作为主要内容 | 有声明/事实，需与代码交叉 | 含验收声明，需核对 | 有发布声明，远程待核 | 发布说明声称的功能范围、使用边界、资产名称与校验信息 | 远程 Release 当前是否存在且附件是否仍一致；代码真实执行细节 |
| SRC-020 | BossOCR Windows Edge Release Notes - 2026-07-02 | docs/releases/windows-edge-release-notes-2026-07-02.md | fully_read | 记录 2026-07-02 Windows Edge 发布范围、人工验证、资产大小与 SHA，以及后续发布步骤。 | Windows；2026-07-02 | 未作为主要内容 | 有声明/事实，需与代码交叉 | 含验收声明，需核对 | 有发布声明，远程待核 | 发布说明声称的功能范围、使用边界、资产名称与校验信息 | 远程 Release 当前是否存在且附件是否仍一致；代码真实执行细节 |
| SRC-021 | BossOCR Windows Stable v1.2 | docs/releases/windows-stable-v1.2.md | fully_read | 记录 v1.2 校准模板能力、兼容边界、人工 Windows 冒烟和发布文件名。 | Windows；v1.2、calibration-profile | 未作为主要内容 | 有声明/事实，需与代码交叉 | 含验收声明，需核对 | 有发布声明，远程待核 | 发布说明声称的功能范围、使用边界、资产名称与校验信息 | 远程 Release 当前是否存在且附件是否仍一致；代码真实执行细节 |
| SRC-028 | BossOCR Windows 正式版 v1.0 发布前基线 | Windows-current-baseline-before-official-v1.0.md | fully_read | 冻结 2026-07-03 Windows 正式版候选基线，汇总 Issue #1、Next-1 至 Next-6、P0 hotfix、测试和发布前门槛。 | Windows；baseline、v1.0 | 未作为主要内容 | 无或不适用 | 无 | 仅发布候选 | 文档声称的基线 commit、功能范围、测试与冻结边界 | 远程分支/Release 当前状态；文档之后发生的变更 |
| SRC-045 | BossOCR-Windows-x64.sha256.txt | release/BossOCR-Windows-x64.sha256.txt | fully_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | 按正文或跨平台；sha256 | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地校验文件记录的摘要值和目标文件名 | 该摘要对应哪一个正式 Release；远程附件仍存在且内容一致 |

## 校准模板相关材料

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-007 | 校准模板模块验收报告 | docs/Issue-calibration-template-module-acceptance-report.md | fully_read | 确认模板数据层、步骤层、主程序注入和 263 项测试通过；真实 Boss 页面 12 项冒烟仍未执行。 | Windows（macOS 仅设计边界）；calibration-profile、v1.2 | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-016 | 通用校准模板冒烟验收说明 | docs/calibration-template-smoke-test.md | fully_read | 给出模板模块自动化覆盖、人工冒烟、非交互错误处理和打包边界清单。 | Windows（macOS 仅设计边界）；calibration-profile、manual-smoke | 未作为主要内容 | 无或不适用 | 仅步骤，无最终结论 | 无 | 该 smoke_test 资料直接记录的项目事实 | 未由该资料直接记录的动机、实现或发布事实 |
| SRC-024 | PRD-calibration-template-module | PRD-calibration-template-module.md | fully_read | 定义通用、跨动作模式的 11 区域校准模板、现有字段复用、旧手工流程保留和模板异常回退。 | Windows（macOS 仅设计边界）；calibration-profile、persistence | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-025 | TID-calibration-template-module | TID-calibration-template-module.md | fully_read | 设计多文件 JSON 模板、步骤注册表、独立生成入口、主程序注入、非交互加载和 9 个实施 Change。 | Windows（macOS 仅设计边界）；calibration-profile、JSON、registry | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-053 | calibration_profiles.py | calibration_profiles.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | Windows（macOS 仅设计边界）；calibration-profile、JSON | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-054 | calibration_steps.py | calibration_steps.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | Windows（macOS 仅设计边界）；calibration-profile、registry | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-055 | calibration_template.py | calibration_template.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | Windows（macOS 仅设计边界）；calibration-profile、entrypoint | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-056 | test_calibration_profiles.py | tests/test_calibration_profiles.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | Windows（macOS 仅设计边界）；calibration-profile | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前测试保护的行为契约与异常分支 | 真实 GUI、浏览器和邮件环境已通过；设计动机 |
| SRC-057 | test_calibration_steps.py | tests/test_calibration_steps.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | Windows（macOS 仅设计边界）；calibration-profile | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前测试保护的行为契约与异常分支 | 真实 GUI、浏览器和邮件环境已通过；设计动机 |
| SRC-058 | test_calibration_template.py | tests/test_calibration_template.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | Windows（macOS 仅设计边界）；calibration-profile | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前测试保护的行为契约与异常分支 | 真实 GUI、浏览器和邮件环境已通过；设计动机 |

## WindMouse 相关材料

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-015 | [Next-7] WindMouse 可观察鼠标移动验收报告 | docs/Issue-Next-7-windmouse-observable-motion-acceptance-report.md | fully_read | 确认 WindMouse 行为、175 项测试、PyInstaller one-dir 构建和许可证收集；实机观感待发布前人工验证。 | Windows；Next-7、WindMouse、build | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-018 | Windows WindMouse 可观察鼠标移动 TID | docs/TID-Windows-WindMouse-Observable-Motion.md | fully_read | 设计 WindMouse 1.0.2 两段移动、稳定收尾、贝塞尔回退、精确终点、打包收集和 GPL 边界。 | Windows；WindMouse、license | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-039 | -*- mode: python ; coding: utf-8 -*- | BossOCR.spec | fully_read | 定义 one-dir PyInstaller 收集 RapidOCR、WindMouse PyAutoGUI backend、metadata/许可证和 GUI 自动化依赖。 | 按正文或跨平台；PyInstaller、WindMouse、RapidOCR | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前构建、测试、打包与发布自动化步骤 | 某次远程运行实际成功；历史发布附件当前可下载 |
| SRC-042 | requirements.txt | requirements.txt | fully_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | 按正文或跨平台；WindMouse | 未作为主要内容 | 无或不适用 | 无 | 无 | 该版本声明的直接依赖与版本约束 | 依赖已成功安装；运行时实际加载版本；功能验收结果 |
| SRC-047 | mouse_motion.py | mouse_motion.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | 按正文或跨平台；WindMouse、bezier | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-059 | test_mouse_motion.py | tests/test_mouse_motion.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | 按正文或跨平台；mouse、WindMouse | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前测试保护的行为契约与异常分支 | 真实 GUI、浏览器和邮件环境已通过；设计动机 |

## 收藏与转发模式相关材料

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-006 | Issue-Action-Mode-Favorite-Forward Acceptance Report | docs/Issue-Action-Mode-Favorite-Forward-acceptance-report.md | fully_read | 确认收藏/转发模式、入口贯通、运行期收藏校准、0.5 秒等待和 202 项全量回归；人工冒烟仍建议执行。 | Windows（macOS 未验证）；favorite、forward、action_mode | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-017 | TID-Action-Mode-Favorite-Forward | docs/TID-Action-Mode-Favorite-Forward.md | fully_read | 结合现有代码细化 action_mode 输入、CLI 兼容、运行期收藏校准、互斥分发和测试拆分。 | Windows（macOS 未验证）；favorite、forward、action_mode | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-023 | BossOCR PRD：新增收藏处理模式与 Codex TID 生成提示词 | PRD-and-Codex-Prompt-Favorite-Action-Mode.md | fully_read | 提出互斥 favorite/forward action_mode、收藏按钮区域校准、中间 60% 落点和保留原转发链路。 | Windows（macOS 未验证）；favorite、forward、action_mode | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |

## 测试、构建和发布相关材料

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-037 | windows-release.yml | .github/workflows/windows-release.yml | fully_read | 定义 issue-* tag 触发的 Windows GitHub Actions：安装、测试、PyInstaller、安全冒烟、压缩、校验和 Release 创建。 | 按正文或跨平台；CI | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前构建、测试、打包与发布自动化步骤 | 某次远程运行实际成功；历史发布附件当前可下载 |
| SRC-038 | build-windows.bat | build-windows.bat | fully_read | 定义本地 Windows 构建链：安装依赖、全量 unittest、PyInstaller、安全冒烟、ZIP 和 SHA 查看。 | Windows；build、smoke | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前构建、测试、打包与发布自动化步骤 | 某次远程运行实际成功；历史发布附件当前可下载 |
| SRC-060 | test_ocr_calibration.py | tests/test_ocr_calibration.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | 按正文或跨平台；OCR、calibration | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前测试保护的行为契约与异常分支 | 真实 GUI、浏览器和邮件环境已通过；设计动机 |
| SRC-061 | test_ocr_detector.py | tests/test_ocr_detector.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | 按正文或跨平台；OCR、detector | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前测试保护的行为契约与异常分支 | 真实 GUI、浏览器和邮件环境已通过；设计动机 |
| SRC-062 | test_ocr_text.py | tests/test_ocr_text.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | 按正文或跨平台；keyword-rule | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前测试保护的行为契约与异常分支 | 真实 GUI、浏览器和邮件环境已通过；设计动机 |
| SRC-063 | test_simple_brush_ocr.py | tests/test_simple_brush_ocr.py | partially_read | 已登记来源、定位、读取状态与可证明边界；正式需求抽取时需按主题与相邻材料交叉验证。 | 按正文或跨平台；main-loop、safety | 未作为主要内容 | 无或不适用 | 无 | 无 | 当前测试保护的行为契约与异常分支 | 真实 GUI、浏览器和邮件环境已通过；设计动机 |

## OCR 调查、迁移与平台实施

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-002 | 关键词连续误触发问题调查报告（修订版） | docs/INVESTIGATION_REPORT.md | fully_read | 复核连续关键词误触发事故，确认 Ctrl+A/Ctrl+C 复制了详情覆盖层与底层推荐列表的混合全文，并纠正旧版对翻页失败的过强推断。 | 按正文或跨平台；OCR、clipboard、false-positive、P0 | 有 | 无或不适用 | 无 | 无 | 该 investigation_report 资料直接记录的项目事实 | 未由该资料直接记录的动机、实现或发布事实 |
| SRC-003 | RapidOCR 简历关键词检测实施方案 | docs/RAPIDOCR_IMPLEMENTATION_PLAN.md | fully_read | 提出本地 RapidOCR 替代全页剪贴板方案，冻结局部截图、精确匹配、固定最多 8 屏、二次确认和失败关闭原则。 | 按正文或跨平台；RapidOCR、privacy、exact-match、fail-closed | 有 | 无或不适用 | 无 | 无 | 当时记录的目标、非目标、设计意图、风险与计划验收条件 | 最终代码是否按计划实现；自动化或人工验收是否通过；是否已进入发布 |
| SRC-026 | Windows RapidOCR 接入与验证报告 | WINDOWS_OCR_IMPLEMENTATION_REPORT.md | fully_read | 记录 Windows RapidOCR 接入、DPI 拖框、真实静态图推理、29 项测试与尚未完成的真实 BOSS 页面核对。 | Windows；RapidOCR、DPI | 有 | 有声明/事实，需与代码交叉 | 无 | 无 | 报告所声称的实现范围、环境、测试结果和未完成边界 | 原始业务动机的完整讨论；未执行的实机验证结果；正式发布状态 |
| SRC-027 | Windows 环境初始化与测试报告 | WINDOWS_SETUP_REPORT.md | fully_read | 记录 Windows 环境初始化、依赖版本、13 项测试与真实拖框/DPI 尚待验证的边界。 | Windows；environment、RapidOCR | 未作为主要内容 | 无或不适用 | 无 | 无 | 报告所声称的环境、依赖、导入和测试结果 | 产品功能已完整实现；真实业务页面已验收；正式发布状态 |

## 其他验收与入口材料

| source_id | 文件 / 对象 | 路径或引用 | 阅读状态 | 阅读摘要 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明的核心事实 | 待交叉验证点 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-001 | BossOCR | docs/README.md | fully_read | 当前 v1.2 用户与维护入口，汇总 Windows Edge、OCR、规则语法、收藏/转发、校准模板、构建、隐私和限制。 | Windows；v1.2、usage、architecture | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 该版本面向用户声明的能力、用法、约束与支持平台 | 代码一定符合文档；功能首次提出时间；远程发布对象状态 |
| SRC-008 | [Hotfix] P0 验收报告：转发流程结束后执行两次焦点恢复点击 | docs/Issue-Hotfix-double-focus-restore-acceptance-report.md | fully_read | 确认转发所有退出路径执行两次独立焦点恢复，110 项测试通过，并建议最小真实页面验证。 | Windows；P0、focus-restore、hotfix | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-009 | [Next-1] 验收报告：转发流程点击区域启动前校准 | docs/Issue-Next-1-focus-restore-calibration-acceptance-report.md | fully_read | 确认 Next-1 五个 Change、81 项测试和默认/运行期区域行为；真实 Windows Edge 验证未执行。 | Windows；Next-1、focus-restore | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-010 | [Next-2] 验收报告：关键词规则新增 not 排除逻辑 | docs/Issue-Next-2-keyword-not-rule-acceptance-report.md | fully_read | 确认 not 解析、匹配、完整规则二次确认和 97 项测试；真实 OCR 样本未执行。 | Windows；Next-2、not、keyword-rule | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-011 | [Next-3] 验收报告：转发流程全部关键点击点启动前校准 | docs/Issue-Next-3-forward-click-calibration-acceptance-report.md | fully_read | 确认五区域原子校准、运行期接入和 109 项测试；真实浏览器与邮件验证未在本次执行。 | Windows；Next-3、forward-calibration | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-012 | [Next-4] 关键词规则支持 `any(...)` 分组表达式验收报告 | docs/Issue-Next-4-keyword-any-group-acceptance-report.md | fully_read | 确认 any parser/matcher 核心语义；核心 62 项测试通过，但全量 discover 曾被 KeyboardInterrupt 中断。 | Windows；Next-4、any、keyword-rule | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-013 | [Next-5] 启动及批次刷新后自动应用「最近没看过」筛选并点击首位候选人验收报告 | docs/Issue-Next-5-batch-filter-first-candidate-acceptance-report.md | fully_read | 确认四区域筛选归位、beta 包和人工 GUI 冒烟，并记录为 beta 而非 stable release。 | Windows；Next-5、batch-filter、beta | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-014 | [Next-6][P2] 验收报告：优化鼠标移动轨迹——贝塞尔路径、途中抖动与慢-快-慢三段变速 | docs/Issue-Next-6-human-mouse-motion-acceptance-report.md | fully_read | 确认贝塞尔移动、回退参数、165 项测试和范围审计；未执行真实 GUI。 | Windows；Next-6、bezier、mouse | 有 | 有声明/事实，需与代码交叉 | 有 | 无 | 报告所声称的验收结论、测试命令/数量、提交与残余风险 | 报告之外的实际运行行为；未执行人工测试的结果；远程发布对象当前状态 |
| SRC-068 | BOSS 直聘自动刷简历工具 | 3d09769:README.md | fully_read | 初始提交 README，证明项目早期依赖 Windows Edge、剪贴板全文、固定坐标、右方向键和每 100 人刷新。 | Windows；initial、clipboard、fixed-coordinates | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 该版本面向用户声明的能力、用法、约束与支持平台 | 代码一定符合文档；功能首次提出时间；远程发布对象状态 |

## 其余已发现资料

| source_id | 文件 / 对象 | 路径或引用 | 相关性 | 阅读状态 | 平台与模块 | 设计动机 | 最终实现事实 | 验收结果 | 发布结果 | 可证明 | 不能证明 / 待核对 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-004 | RapidOCR 关键词检测改造详细实施文档 | docs/RAPIDOCR_DETAILED_EXECUTION_GUIDE.md | medium | partially_read | 按正文或跨平台；RapidOCR、execution-guide | 未作为主要内容 | 无或不适用 | 无 | 无 | 该 test_guide 资料直接记录的项目事实 | 未由该资料直接记录的动机、实现或发布事实 |
| SRC-022 | BossOCR Issue-Next TID 索引 | docs/tid/next/README.md | low | fully_read | 按正文或跨平台；TID、index | 未作为主要内容 | 无或不适用 | 无 | 无 | 该 documentation_index 资料直接记录的项目事实 | 未由该资料直接记录的动机、实现或发布事实 |
| SRC-040 | setup.bat | setup.bat | medium | fully_read | Windows；setup | 未作为主要内容 | 无或不适用 | 无 | 无 | 该 environment_setup_script 资料直接记录的项目事实 | 未由该资料直接记录的动机、实现或发布事实 |
| SRC-041 | start.bat | start.bat | medium | fully_read | Windows；startup | 未作为主要内容 | 无或不适用 | 无 | 无 | 该 run_script 资料直接记录的项目事实 | 未由该资料直接记录的动机、实现或发布事实 |
| SRC-043 | Cross-platform RapidOCR dependencies. Use Python 3.10+ (3.11 x64 preferred). | requirements-ocr.txt | medium | fully_read | 按正文或跨平台；RapidOCR | 未作为主要内容 | 无或不适用 | 无 | 无 | 该版本声明的直接依赖与版本约束 | 依赖已成功安装；运行时实际加载版本；功能验收结果 |
| SRC-044 | requirements-build.txt | requirements-build.txt | low | fully_read | 按正文或跨平台；PyInstaller | 未作为主要内容 | 无或不适用 | 无 | 无 | 该版本声明的直接依赖与版本约束 | 依赖已成功安装；运行时实际加载版本；功能验收结果 |
| SRC-046 | -*- coding: utf-8 -*- | simple_brush.py | medium | partially_read | 按正文或跨平台；main-loop、actions、automation | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-048 | ocr_calibration.py | ocr_calibration.py | medium | partially_read | 按正文或跨平台；calibration、DPI | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-049 | ocr_detector.py | ocr_detector.py | medium | partially_read | 按正文或跨平台；OCR、scan、confirmation | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-050 | ocr_text.py | ocr_text.py | medium | partially_read | 按正文或跨平台；keyword-rule、parser、matcher | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-052 | ocr_fixture_demo.py | ocr_fixture_demo.py | low | partially_read | 按正文或跨平台；OCR、fixture、demo | 未作为主要内容 | 有声明/事实，需与代码交叉 | 无 | 无 | 当前检出版本实际实现的控制流与数据结构 | 原始业务动机；历史首次提出时间；人工验收结果 |
| SRC-064 | simple_brush.log | logs/simple_brush.log | medium | partially_read | 按正文或跨平台；runtime、diagnostics、privacy | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地运行事件、错误模式与时序的抽象证据 | 无上下文情况下的业务因果；任何个人身份结论 |
| SRC-069 | Git tag Boss | Boss:- | medium | not_applicable | 按正文或跨平台；Boss | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地 Git 仓库中该 tag 名称及其指向的 commit | 对应 GitHub Release 是否存在；远程 tag 是否仍一致 |
| SRC-070 | Git tag v1.0.0 | v1.0.0:- | medium | not_applicable | 按正文或跨平台；v1.0.0 | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地 Git 仓库中该 tag 名称及其指向的 commit | 对应 GitHub Release 是否存在；远程 tag 是否仍一致 |
| SRC-071 | Git tag issue-1-v1.0 | issue-1-v1.0:- | medium | not_applicable | 按正文或跨平台；issue-1-v1.0 | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地 Git 仓库中该 tag 名称及其指向的 commit | 对应 GitHub Release 是否存在；远程 tag 是否仍一致 |
| SRC-072 | Git tag windows-stable-v1.0 | windows-stable-v1.0:- | medium | not_applicable | 按正文或跨平台；windows-stable-v1.0 | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地 Git 仓库中该 tag 名称及其指向的 commit | 对应 GitHub Release 是否存在；远程 tag 是否仍一致 |
| SRC-073 | Git tag windows-stable-v1.1 | windows-stable-v1.1:- | medium | not_applicable | 按正文或跨平台；windows-stable-v1.1 | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地 Git 仓库中该 tag 名称及其指向的 commit | 对应 GitHub Release 是否存在；远程 tag 是否仍一致 |
| SRC-074 | Git tag v1.1 | v1.1:- | medium | not_applicable | 按正文或跨平台；v1.1 | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地 Git 仓库中该 tag 名称及其指向的 commit | 对应 GitHub Release 是否存在；远程 tag 是否仍一致 |
| SRC-075 | Git tag v1.2 | v1.2:- | medium | not_applicable | 按正文或跨平台；v1.2 | 未作为主要内容 | 无或不适用 | 无 | 无 | 本地 Git 仓库中该 tag 名称及其指向的 commit | 对应 GitHub Release 是否存在；远程 tag 是否仍一致 |
| SRC-076 | GitHub Issues（开放与关闭） | origin:- | critical | inaccessible | 按正文或跨平台；GitHub | 未作为主要内容 | 无或不适用 | 无 | 无 | — | 远程对象数量、状态、时间、讨论、附件和检查结论 |
| SRC-077 | GitHub Pull Requests（merged 与 closed） | origin:- | high | inaccessible | 按正文或跨平台；GitHub | 未作为主要内容 | 无或不适用 | 无 | 无 | — | 远程对象数量、状态、时间、讨论、附件和检查结论 |
| SRC-078 | GitHub Releases 与附件 | origin:- | high | inaccessible | 按正文或跨平台；GitHub | 未作为主要内容 | 无或不适用 | 无 | 无 | — | 远程对象数量、状态、时间、讨论、附件和检查结论 |
| SRC-079 | GitHub Actions 与检查结果 | origin:- | high | inaccessible | 按正文或跨平台；GitHub | 未作为主要内容 | 无或不适用 | 无 | 无 | — | 远程对象数量、状态、时间、讨论、附件和检查结论 |

## 阅读判定规则

- `fully_read`：本轮已逐段读完全文；不表示其内容已被其他证据证实。
- `partially_read`：已做结构、定位或代表性片段检查，但没有宣称全文阅读。
- `inaccessible`：对象应存在于远程系统，但当前凭据或网络条件无法读取。
- `not_applicable`：如 Git tag，仅核对对象与指向，不适用“全文阅读”。
