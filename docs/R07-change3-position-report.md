# BossOCR R07 Change 3：单次 Record 路径与视觉位置分类报告

## 基线与范围

| 项目 | 值 |
|---|---|
| 基线提交 | `1fcacdbd84a381366e4fd2ce494064aaf9a8c670` |
| 基线说明 | `feat(ocr): add R07 schema and state foundations` |
| 设计 | RPD/TID 1.2（最终逻辑修订） |
| 本 Change | 单次 canonical record 路径、五态位置分类、无副作用状态更新 |

开始时分支为 `main`，HEAD 为上述基线。开始前的未跟踪文件 `README.md`、`docs/project-review.zip` 与 `venv-packages-before-reinstall.txt` 保持未修改。

本 Change 不实现 first-same 恢复、确认 OCR、额外滚动、shadow 漏采结论、safe/full 提前返回、R07 Replay、R01、无关键词路径或 batch rollover。

## 修改文件

| 文件 | 变更 |
|---|---|
| `ocr_detector.py` | 新增纯 `PositionDecision`/`classify_position()`；每次 callback 后仅更新有界 `DynamicEndState`，不参与控制决策；规则确认新写为 `rule_confirmation`。 |
| `simple_brush.py` | 将普通 formal screen 的 record 路径固定为 build → classify → 附加 R07 字段 → save；移除主循环在规则判断前预先保存首屏的重复路径。 |
| `ocr_candidate.py` | 提供仅可替换刚构建最新 record 的小型 API，使 Builder 最终持有的 canonical record 与 Store 保存对象完全相同，不重新 build/R03—R06。 |
| `tests/test_ocr_detector.py` | 覆盖五态分类、健康/R03 不可用、有效新增、受保护短文本、possible/uncertain 和 R05/R06 disabled。 |
| `tests/test_ocr_stage0_integration.py` | 覆盖普通槽位 capture/rule/build/classify/save 各一次、同一 record 保存、Store bool 回到 detector、formal `same` 与 `rule_confirmation` writer。 |

## 实际调用顺序

普通槽位现在按以下同步顺序执行：

```text
capture_observation（或复用既有首屏 observation）一次
→ _match_observation 一次
→ CandidateOcrBuilder.build_screen_record 一次（含既有 R03—R06）
→ classify_position(previous canonical record, current record) 一次
→ replace 同一 record 的 R07 position fields
→ JsonlOcrRecordStore.save_screen 一次
→ RecordedObservationResult(record, saved, decision)
→ detector 仅更新 DynamicEndState
```

`save_screen()` 为 false 时不会重试；该 record 不会成为 detector 的 last comparable evidence。位置分类没有 OCR、Store、滚动、等待、点击、R01 或候选人切换调用。普通 `initial`/`changed`/`same`/`uncertain`/`unavailable` 全部保留 `formal_screen`。没有生产 writer 使用 `position_observation`；旧 `scroll_confirmation` 不再写出，仅保留 reader enum 兼容。

## 分类规则

`classify_position()` 只读取当前 canonical record 已完成的 R03—R06 投影以及调用者提供的已有 health：

1. 无前序 record 为 `initial`。
2. R03 exact、load、OCR 或 identity health 缺失为 `unavailable`。
3. 现有 R05/R06 的 possible、uncertain、partial/failed、冲突/不一致 warning 或 elevated duplicate risk 为 `uncertain`。
4. exact 相同且无有效新增/受保护短文本/冲突为 `same`。
5. exact 不同，或已有 R06 有效新增（含 `short_text_protected`）为 `changed`。
6. 无法满足以上确定条件时保守为 `uncertain`。

`page_change_status` 记录 R03 的 `initial`/`same`/`changed`/`unavailable` 事实；`reference_screen_id` 指向上一条可比较屏；`prediction_reason` 仅记录本次分类依据，尚未接入 shadow 预测或结束控制。load health 使用当前 observation 已有的 OCR box/text 指标和既有阈值，identity health 只由已成功建立的候选人 Builder 上下文提供；不重新执行 P0/load retry/R01/identity OCR。

## Store 反馈与状态

`RecordedObservationResult` 仍为 `(record, saved, position_decision)`。detector 保存 callback 返回值为 `last_observation_result`，并在已保存的 `initial`/`same`/`changed` formal record 后更新 last comparable record/hash、scan/OCR/scroll/unique counters。该状态不改变任何循环、规则早停、滚动、等待或上层动作。

既有规则命中仍按一次 confirmation 后立即返回，`DetectionResult.dynamic_end_reason` 仍为 null；本 Change 没有任何动态结束或 abort 分支。

## 验证

| 命令 | 结果 |
|---|---|
| `./venv/Scripts/python.exe -m compileall -q ocr_detector.py simple_brush.py ocr_candidate.py tests` | PASS。 |
| `./venv/Scripts/python.exe -m unittest tests.test_ocr_detector tests.test_ocr_stage0_integration tests.test_ocr_candidate -q` | PASS：119 tests。 |
| `./venv/Scripts/python.exe -m unittest discover -s tests -q` | PASS：703 tests，20.591 s。 |

全量输出中的 mock Store failure、fingerprint failure 和页面操作日志均来自既有 synthetic coverage；最终没有失败。

## 暂留问题与 Change 4 注意事项

本 Change 没有已知核心失败。Change 4 才能在 safe/full 的 first-same 后使用一次 focus/scroll/position-confirmation 额度；不得把本 Change 的 `same` 直接当作 bottom，且不得改变 shadow/off 的现有页面序列。Change 5 负责 shadow 预测、漏采字段与其完整性语义；Change 6 才能使用 Store bool 参与 safe/full 终止优先级。

本 Change 未执行真实页面、真实 record、push、tag 或 Release，也未进入 Change 4。
