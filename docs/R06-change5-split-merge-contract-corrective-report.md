# R06 Change 5 前置 Split/Merge 合同 Corrective 报告

## 总体结果

维护者批准的 Corrective 已完成。本轮仅修订 RPD、TID 与本报告；未实施 Change 5 代码或测试，未修改 Schema 1.3、配置、依赖、构建、workflow 或任何生产文件。

## 原阻塞与 R05 真实证据合同

此前 Change 5 正确停止：它要求只为 R05 `new/uncertain` 输出 `EffectiveNewDecision`，却要求 new 侧 `split_merge_artifact` 必须有 R05 1→2/2→1 evidence 与 document/reference 组合等价。

只读核验当前 R05 合同后确认：

1. `OcrScreenRecord._validate_r05_contract()` 汇总所有 `match_evidence.current_segment_ids`，并要求其集合严格等于 `matched_segment_ids`；
2. 因而 `new_segment_ids`、`uncertain_segment_ids` 不能合法作为 match evidence 的 current IDs；
3. `tests/test_ocr_aggregation.py` 已覆盖 R05 的 `ADJACENT_FUZZY_1_2` 与 `ADJACENT_FUZZY_2_1`；R05 是 1→1、1→2、2→1、split/merge 与三分 partition 的唯一权威；
4. R06 不得重新执行 diff，也不得猜测、覆盖或修正 R05 分类。

因此，R06 new 无法合法取得 split/merge evidence；仅凭 fuzzy 分数、文本相似、相邻拼接或 opaque document ID 都不构成证据。

## 批准修正与新边界

- 完整 split/merge evidence 属于 R05 matched，继续保留在 `match_evidence`、`document_segments`、source occurrence。
- `r06-v1` 只评估 R05 new/uncertain，永不为 matched 生成 `EffectiveNewDecision`。
- `split_merge_artifact` 是普通字符串 reason code 的 **r06-v1 reserved / never emitted** 值：不再是决策分支、正例或 benchmark 覆盖目标。
- R05 new 若没有其他充分无效证据，只能按余下规则得到 effective 或 uncertain；R06 不得再次猜 split/merge。
- 未来只有 R05 Schema 显式增加 new→reference/document 组合的完整映射、comparison-equality evidence 与稳定来源，并升级 R05/R06 版本后，才能重新讨论该分类。

修正后的固定决策顺序为：

1. `format_only`
2. `duplicate_artifact`
3. `low_confidence_noise`
4. `likely_repeated_ui_noise`
5. `short_text_protected`
6. `effective`
7. `uncertain`

## 非法证据关系

若 new/uncertain ID 出现在 `match_evidence.current_segment_ids`，这是前序 R05 partition/evidence 合同冲突，不是 split/merge 正例。后续 Change 5 必须停止全部有效新增 decision，使用 `segment_partition_invalid` 或 `r05_projection_mismatch`，使 status 至少 partial、effective status unavailable、boolean projection null、class uncertain，并保持 R05 源对象不变。

## 文档修改

- RPD：修正当前问题、R05/R06 边界、伪影语义、无效新增、uncertain 保守原则、风险和验收标准，删除 R06 可对 new 判 split/merge 的暗示。
- TID：修正第 9 节输入/顺序/证据表/低置信度前置；冻结 reserved/never-emitted 语义和非法关系降级；明确 evaluator 不接收 candidate document 且不重建 split/merge；更新 Change 5 与 Change 7 测试矩阵和停止条件。

## Schema、代码与测试

Schema 无变化。`reason_code` 是普通字符串，本 Corrective 没有修改生产 enum，也没有为 enum 覆盖伪造正例。未修改生产代码、测试代码或任何其他文件。

## Git 状态与检查

- branch: `main...origin/main`
- HEAD: `afc41d8f279e0218d892f7973d3e39b2d86bdf90`
- tracked 文档修改：RPD 与 TID；其他 tracked/untracked 项均为已归属的 Change 2—4 或既有文件。
- 已执行 `git diff -- docs/RPD... docs/TID...`、`git diff --check`、`git status -sb`、`git status --short --untracked-files=all`；无 whitespace error（仅既有 LF/CRLF warning）。
- 未读取真实正文、未修改日志/data、未执行 git add、commit、push、tag 或 release。

## 是否具备重新执行 Change 5 的条件

**具备。** 在维护者审核本 Corrective 后，可从 Change 5 重新开始；必须重新读取当前代码、修正后的 RPD/TID、Change 1—5 报告，并按新测试合同证明 `split_merge_artifact` 永不输出。此报告完成后停止，不进入 Change 5。
