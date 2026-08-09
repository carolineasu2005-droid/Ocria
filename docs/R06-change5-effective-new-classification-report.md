# R06 Change 5 — 有效新增与中性分类报告

## 总体结果

Change 5 已完成，交付纯内存有效新增 evaluator、最多 8 个正式屏的 candidate UI context、EffectiveNewStatus/兼容布尔投影、neutral comparison class 与跨层冲突降级。未接入 Builder、Store、Replay、sidecar 或页面流程。

## Corrective 与 R05/R06 边界

此前 split/merge 阻塞已由维护者 Corrective 解决：R05 是 1→1、1→2、2→1、split/merge 与 partition 的唯一权威，完整 evidence 只覆盖 `matched_segment_ids`。R06 只对 new/uncertain 输出 decision，不重跑 diff；`split_merge_artifact` 在 r06-v1 为 reserved / never emitted。若 new/uncertain 非法出现于 R05 evidence，则停止 decision、unavailable/null/uncertain 并记录 partition warning。

## 决策与证据

new 的顺序是 format-only、duplicate artifact、frozen-config low-confidence noise、UI 组合证据、short-text protection、effective、uncertain；uncertain source 直接输出 `source_uncertain`。每条结果保存 segment ID、source classification、decision、reason 与枚举 evidence，并按 screen source order 输出。

format-only 只接受 Unicode punctuation/separator/format 且无保护内容。duplicate 只消费既有 R04 duplicate group/pair 的 exact/geometry/source-box evidence。低置信度只使用 `OcrSimilarityConfig` 中冻结的 0.85/0.03/2，不读运行时全局。短文本保护覆盖 versioned business list、年份、日期、范围、版本与 R04 protected token；未知内容保守为 uncertain。不存在 UI 文案黑名单。

UI context 按 exact comparison 建索引、按 candidate 隔离、最多 8 正式屏，不做 screen 两两比较；三屏且几何/尺寸满足才无效，二屏或几何缺失给 `ui_evidence_insufficient`/uncertain，保护内容阻止 UI 无效判断。`clear()` 释放 context。

## 状态与类别

存在 effective 为 present/true；无 effective 但有 uncertain 为 possible/true；全 new ineffective 且无 R05 uncertain 为 none/false；R05/accounting/partition 不可验证为 unavailable/null。class 按冻结优先级处理 no-reference/unavailable/failed/空文本、冲突/possible、exact、high/changed × present/none。R03 exact 与 R04/R05 不一致时保留前序结果，加入 `cross_layer_similarity_conflict`、至少 partial 且 class uncertain。

## 修改与验证

- 修改：`ocr_similarity.py`、`tests/test_ocr_similarity.py`、本报告；未修改 R03/R04/R05/Schema 或在线文件。
- `python -m unittest tests.test_ocr_similarity -v`: PASS。
- `python -m tests.benchmark_r06_similarity`: PASS；20k pair p95 8.63/13.67/7.16 ms，8 adjacent p95 通过，峰值低于 16 MiB。
- `python -m unittest discover -s tests -q`: PASS，673 tests。
- R04/R05 benchmark、compileall、pip check、`git diff --check`: PASS。

仅使用合成 fixture。未读取候选人正文；日志/data 仅允许 inventory。未执行 git add、commit、push、tag 或 release。

## Git 状态与后续

HEAD 为 `afc41d8f279e0218d892f7973d3e39b2d86bdf90`，branch 为 `main...origin/main`。本 Change 的代码/测试修改可归属；RPD/TID Corrective 和 Change 2—4 既有修改保持可归属。

**允许进入 Change 6，但必须重新核验 R05 record 的独立最终验收与生产批准；R06 默认仍为 disabled。**
