# BossOCR Issue-Next TID 索引

## 目录用途

本目录集中保存 BossOCR 历史 `Issue-Next` 系列技术实现设计（TID），便于从统一位置查阅原始设计材料。这里的 8 份 TID 均由仓库根目录归档而来，原始文件名和文件正文完整保留。

本 README 只提供文档导航，不据此判断需求当前状态、发布时间、验收结果、最终实现范围或平台成熟度。正式需求主编号将在项目复盘需求台账中另行分配；`Next-1` 至 `Next-6` 等旧编号应按证据和命名空间保存到 `legacy_ids`，不能直接作为复盘主编号。

## 文件列表

| Issue-Next | 主题 | 文档版本 | 文件 |
| --- | --- | --- | --- |
| Next-1 | 转发流程点击区域启动前校准 | V1.0 | [Issue-Next-1-focus-restore-calibration-TID-V1.0.md](Issue-Next-1-focus-restore-calibration-TID-V1.0.md) |
| Next-2 | 关键词规则新增 `not` 排除逻辑 | V1.0 | [Issue-Next-2-keyword-not-rule-TID-V1.0.md](Issue-Next-2-keyword-not-rule-TID-V1.0.md) |
| Next-3 | 转发流程全部关键点击点启动前校准 | V1.0 | [Issue-Next-3-forward-click-calibration-TID-V1.0.md](Issue-Next-3-forward-click-calibration-TID-V1.0.md) |
| Next-4 | 关键词规则支持 `any(...)` 分组表达式 | V1.0 | [Issue-Next-4-keyword-any-group-TID-V1.0.md](Issue-Next-4-keyword-any-group-TID-V1.0.md) |
| Next-4 | 关键词规则支持 `any(...)` 分组表达式 | V1.1 | [Issue-Next-4-keyword-any-group-TID-V1.1.md](Issue-Next-4-keyword-any-group-TID-V1.1.md) |
| Next-5 | 启动及批次刷新后自动应用“最近没看过”筛选并点击首位候选人 | V1.0 | [Issue-Next-5-batch-filter-first-candidate-TID-V1.0.md](Issue-Next-5-batch-filter-first-candidate-TID-V1.0.md) |
| Next-5 | 启动及批次刷新后自动应用“最近没看过”筛选并点击首位候选人 | V1.1 | [Issue-Next-5-batch-filter-first-candidate-TID-V1.1.md](Issue-Next-5-batch-filter-first-candidate-TID-V1.1.md) |
| Next-6 | 优化鼠标移动轨迹：贝塞尔路径、途中抖动与慢—快—慢三段变速 | V1.0 | [Issue-Next-6-human-mouse-motion-TID-V1.0.md](Issue-Next-6-human-mouse-motion-TID-V1.0.md) |

## 文档版本说明

V1.0 与 V1.1 表示同一 Issue-Next 主题下的历史文档版本，不自动构成两个独立需求，也不因版本号较新就自动证明旧版本已被完全替代。

- Next-4 同时保留 V1.0 和 V1.1；正文未提供足以在本索引中确定两者完整修订或替代边界的明确声明，具体关系留待证据阶段核对。
- Next-5 同时保留 V1.0 和 V1.1；V1.1 正文明确声明“基于 V1.0 修订”并列出保留内容与重点调整，但其实施、验收、发布及是否完全替代 V1.0 仍需在证据阶段分别核对。
