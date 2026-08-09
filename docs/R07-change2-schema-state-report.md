# BossOCR R07 Change 2：最小 Schema、状态与 Store 反馈报告

## 1. 基线与范围

| 项目 | 值 |
|---|---|
| 基线提交 | `dd60156ab224f3ea3e6d0f4ebf3c2ee5a4e58a84` |
| 基线说明 | `test(ocr): establish R07 implementation baseline` |
| R07 设计 | RPD/TID 1.2（最终逻辑修订） |
| 本 Change | 最小数据、兼容 schema、模式/状态、Store bool 反馈 |

本 Change 未接入位置分类、first-same 恢复、额外 OCR/滚动、shadow 控制、safe/full 提前返回、R07 Replay、R01、无关键词路径或 batch rollover。

## 2. 修改文件

| 文件 | 变更 |
|---|---|
| `ocr_detector.py` | 增加纯 `DynamicEndConfig`、`DynamicEndState`、四模式常量及兼容 `DetectionResult` nullable R07 原因字段；`_notify_observation()` 可原样返回 callback 结果。 |
| `ocr_records.py` | schema 升至 1.4.0，保留 1.0—1.3 readers；新增 R07 screen/candidate/manifest additive fields 与旧 schema unknown/null 恢复。 |
| `ocr_store.py` | `JsonlOcrRecordStore` 接收并写入最小 dynamic-end manifest 配置。 |
| `simple_brush.py` | 默认 `shadow` 配置进入新 manifest；新增 `RecordedObservationResult`，callback 可返回 record 与 `save_screen()` bool，旧直接 record 调用仍返回 record。 |
| `ocr_similarity.py` / `ocr_replay.py` | 仅扩展既有 R06 schema 1.3 reader 到 1.4 的版本兼容；未实现 R07 Replay。 |
| `tests/test_ocr_detector.py` | 覆盖模式、默认 shadow、非法模式、状态边界和 legacy rule completion 的 nullable R07 reason。 |
| `tests/test_ocr_records.py` | 覆盖 R07 screen/candidate/manifest round-trip、1.3 screen reader unknown/null 语义和 schema 版本更新。 |
| `tests/test_ocr_stage0_integration.py` | 覆盖 callback 返回成功/失败 Store bool，且不引入扫描控制。 |
| `tests/test_ocr_normalization.py` | 更新 1.4 schema 基线断言。 |

## 3. 最小模式、状态和扫描结果

四种受校验模式为 `off`、`shadow`、`safe`、`full`；`DYNAMIC_END_DEFAULT_MODE` 为 `shadow`。`DynamicEndConfig` 只有 mode、no-new threshold（默认 2）与版本；它不会启用 R05/R06，现有 `R05_AGGREGATION_MODE`、`R06_SIMILARITY_MODE` 仍为 `disabled`。

`DynamicEndState` 只保存最终 TID 所列的模式、六项扫描/滚动/焦点计数、连续 no-new、最后可比较 record/hash、first prediction 和 `recovery_used`。它校验 8 槽、7 正常滚动、一次 retry/focus 的边界，但没有 transition、effect 或生命周期逻辑。

`DetectionResult` 保留原有 `success`、`confirmed_match`、`matched_keyword`、`scans_completed`、`observations`、`error`，并新增 nullable `dynamic_end_reason`、`abort_reason`、`interrupt_reason`。当前 detector 不给它们赋控制值，因此 legacy 规则确认仍为 `confirmed_match=True` 且 `dynamic_end_reason=None`。

## 4. Schema 1.4 与兼容策略

当前 `STORAGE_SCHEMA_VERSION` 为 `1.4.0`；显式保留 `R06_STORAGE_SCHEMA_VERSION="1.3.0"` 和 1.0—1.2 版本。所有既有 R04/R05/R06 validation gates 均覆盖 1.3 与 1.4，避免历史 R06 record 被降级或误读。

新增字段：

| 记录 | additive 字段 |
|---|---|
| Screen | `dynamic_end_version`、`position_status`、`page_change_status`、`reference_screen_id`、`is_position_confirmation`、`prediction_reason`。 |
| CandidateOcrDocument | `dynamic_end_mode`、`dynamic_end_reason`、`abort_reason`、六项计数、first prediction、两项 nullable miss 与两项 complete 字段。 |
| RunManifest | `dynamic_end_version`、`dynamic_end_mode`、`dynamic_end_config`。 |

1.0—1.3 reader 会把所有 R07 fields 恢复为 `None`/unknown，不伪造动态结束、健康结论或 false 漏采。1.4 的 nullable miss/complete 字段也默认 `None`。schema round-trip 保留所有已提供的 R07 字段。

## 5. Store 反馈基础

`JsonlOcrRecordStore.save_screen()` 仍只调用一次、不会 retry。Change 2 新增：

```text
record_detection_observation()
→ _record_ocr_observation_result()
→ build_screen_record() 一次
→ save_screen() 一次
→ RecordedObservationResult(record, saved, position_decision=None)
```

`OCRKeywordDetector._notify_observation()` 现在可返回这个结果，但 `detect()` 仍忽略它；因此本 Change 没有 Store failure、mode 或动态结束控制分支。为了保护旧非 callback 调用者，`record_ocr_observation()` 仍返回原 `OcrScreenRecord | None`。

## 6. 验证

| 命令 | 结果 |
|---|---|
| `.\venv\Scripts\python.exe -m unittest tests.test_ocr_records tests.test_ocr_replay tests.test_ocr_candidate tests.test_ocr_aggregation tests.test_ocr_similarity -q` | PASS：134 tests。 |
| `.\venv\Scripts\python.exe -m unittest tests.test_ocr_records tests.test_ocr_detector tests.test_ocr_stage0_integration tests.test_ocr_store -q` | PASS：145 tests。 |
| `.\venv\Scripts\python.exe -m unittest discover -s tests -q` | PASS：698 tests，17.968 s。 |
| `.\venv\Scripts\python.exe -m compileall -q ocr_detector.py simple_brush.py ocr_records.py ocr_store.py ocr_replay.py ocr_candidate.py tests` | PASS。 |

第一次全量运行发现一个既有断言仍期望 schema `1.3.0`；仅更新该基线断言到 `1.4.0` 后，最终全量通过。测试日志中的 mock Store failure、fingerprint failure 和页面操作输出为既有 synthetic coverage，不是本 Change 未处理失败。

## 7. 未处理问题与 Change 3 注意事项

没有 Change 2 核心失败或已知未修复的兼容问题。

Change 3 必须在不二次 build/save/R05/R06 的前提下，使用本 Change 的 `RecordedObservationResult` 在同一 canonical record 保存前写入 position fields；本 Change 尚未传入 `position_decision`。Change 5 仍需修正首屏 rule→record 时序。safe/full 不得在 Change 4/6 前读取 Store bool 改变控制流。

## 8. 声明

本报告与上述代码/测试是 Change 2 的全部产出。未进入 Change 3；未执行真实页面、真实 record、push、tag 或 Release。
