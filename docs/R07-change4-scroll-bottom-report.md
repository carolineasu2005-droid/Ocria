# R07 Change 4：First-Same 恢复与 Bottom 确认报告

## 基线

- 权威设计：`RPD-R07-ocr-scan-state-machine-dynamic-end.md` 与
  `TID-R07-ocr-scan-state-machine-dynamic-end.md`，均为 1.2 最终逻辑修订。
- 前序基线 commit：`76bb3db409fbb2e53c52a176cbc34e789ca0b72d`
  (`feat(ocr): classify R07 scan positions`)。
- 默认 `DynamicEndConfig.mode` 仍为 `shadow`；本 Change 没有将 R05/R06
  自动启用，也没有在 `shadow` / `off` 中产生恢复、重试滚动或确认 OCR 副作用。

## 修改范围

- `ocr_detector.py`
  - 增加有界的 `PositionConfirmationResult` 与 safe/full first-same 恢复能力。
  - `DetectionResult` 增加兼容的 `scroll_bottom_candidate`、`recovery_reason`。
  - 仅当普通槽位在一次正常滚动后为 `same`、恢复额度未用、已保存槽位小于 8、
    健康且未中断时执行恢复；计数受 8 槽、7 次正常滚动、一次焦点恢复、一次
    retry scroll、一次 confirmation OCR 限制。
- `simple_brush.py`
  - 接入现有 `restore_candidate_page_focus()` 和运行中断原因提供器。
  - 同一既有 record 回调携带 load/OCR/identity 健康事实；confirmation 使用单次
    build/classify/save 路径。恢复已用后的普通 `same` 写入
    `insufficient_evidence_after_recovery`。
- `tests/test_ocr_detector.py` 与 `tests/test_ocr_stage0_integration.py`
  - 增加恢复、失败映射、Store 失败、槽位边界及无 P0/R01/next 调用覆盖。

## 实际流程与边界

满足触发条件时，顺序为：已有健康事实检查 → 一次
`restore_candidate_page_focus()` → 一次既有下滚 → 一次 settle wait → 一次确认
OCR/规则判断 → 一次既有 record 回调与保存 → confirmation 分类。未重跑 P0、R01
或身份 OCR，未调用 `next`。

确认 `same` 写为 `position_confirmation`，不占普通 scan slot 或 unique position，
但计入 OCR attempt；仅当健康、无冲突且 Store 成功时标记
`scroll_bottom_candidate`。本 Change 不使用该候选执行动态提前结束。

确认内容变更时仅保存一次，写为紧邻下一个 `formal_screen` 槽位，并跳过随后循环中
对该已消耗槽位的重复采集。第 8 槽 `same` 不触发恢复；恢复额度消耗后出现的 later
`same` 不再恢复、重试或判 bottom，扫描继续。

失败精确记录为 `load_failed`、`switch_failed`、`ocr_failed`、
`focus_restore_failed`、`scroll_failed`、`position_unresolved`、`store_failed`、
`user_interrupted` 或 `runtime_expired`，均不会伪装为 bottom。

## 验证

通过：

- `python -m compileall -q ocr_detector.py simple_brush.py tests`
- 相关 detector / Stage0 / brush / candidate / records / store 回归测试。
- `python -m unittest discover -s tests -q`：710 tests，23.054s，OK。

覆盖包括 off/shadow 零恢复，safe/full first-same，same/changed confirmation，单次
保存与槽位计数，第 8 槽边界，later same，所有恢复失败映射，实际 Store 保存失败，
ESC/runtime，以及 P0/R01/`next` 均不被恢复路径调用。

## 后续注意事项

- `scroll_bottom_candidate` 目前只提供可审计的确认能力；safe/full 的实际提前结束和
  full no-new 策略仍留给后续 Change，不能据此改变现有扫描返回语义。
- 无关键词、R01、batch rollover 与 next 流程未修改。R05/R06 仍按既有配置执行，且
  没有被本 Change 自动开启。
