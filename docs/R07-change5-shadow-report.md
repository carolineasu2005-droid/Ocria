# R07 Change 5：Shadow 接入、首屏与漏采分析报告

## 基线与范围

- 基线提交：`8b1e6dabce22debb5e97a75ae1d8580d9d92495d`
  (`feat(ocr): add R07 scroll bottom confirmation`)。
- 权威设计：RPD/TID 1.2（最终逻辑修订）。默认模式仍为 `shadow`；R05/R06
  仍为既有 disabled 默认值。
- 只修改有关键词 OCR 扫描的 shadow 分析与其候选摘要投影；没有进入 Change 6，
  没有启用 safe/full 提前返回、R01、无关键词或 batch 修改。

## 实现

### 首屏与规则早停

首屏复用同一个 observation，固定为：规则判断一次 → canonical Builder（含既有
R03—R06）一次 → `initial` 分类与 R07 字段附加 → `save_screen()` 一次。首屏规则
comparison 字段在同一已保存 record 上完整保留；没有新增 OCR 或二次规则判断。

所有模式的已确认规则命中仍使用一次 `rule_confirmation` 后立即 legacy 返回：
`confirmed_match=true`，`dynamic_end_reason=null`。shadow 不继续扫描，也不将规则
结果映射为 R07 原因。

### Shadow 分析与候选字段

`OCRKeywordDetector` 新增小型、仅内存的 `ShadowPredictionAnalysis`。它只消费
已完成的 callback record 与既有 R03—R06 投影，不触发 OCR、R03—R06、Store、滚动、
等待、点击、焦点恢复或返回控制。

- 健康且已保存的普通 `same` 冻结首个 `possible_scroll_bottom` 预测；完整 R05/R06
  证据下连续 changed/no-new 可冻结 `no_new_text_candidate`。
- `DynamicEndState.first_predicted_end_screen/reason` 仅首次写入，后续候选不会覆盖。
- 预测后既有有效新增或 `short_text_protected` 标记 content=true；规则确认命中标记
  rule=true，content 因早停保持 null。
- 正常完成并具备相应证据时写 false。R05/R06 disabled/不完整、uncertain、
  unavailable、技术失败、ESC/runtime、Store false 或窗口不完整时，相关漏采字段为
  null；两个 complete 字段分别表达观察窗口和证据完整性。
- `DetectionResult` 携带兼容的模式、计数、首个预测与 nullable 漏采字段；
  `finalize_current_candidate_recording()` 仅在已有关键词扫描结果存在时将其投影到
  `CandidateOcrDocument` 和 `versions["dynamic_end"]`，不改变 finalize 的次数或顺序。

Store false 不重试、不提前退出、不产生新 UI 动作；已冻结预测的 false 结论会被
撤销为 null。R07 仍不直接执行 action、finalize、next 或 refresh。

## 修改文件

- `ocr_detector.py`
- `simple_brush.py`
- `tests/test_ocr_detector.py`
- `tests/test_ocr_stage0_integration.py`
- 本报告

## 验证

- `python -m compileall -q ocr_detector.py simple_brush.py tests`：PASS。
- 相关 detector / Stage0 / brush / candidate / records / store 回归：435 tests，PASS。
- `python -m unittest discover -s tests -q`：717 tests，20.359s，PASS。
- `python -m pip check`：PASS。

测试以 off/shadow golden effect sequence 对比 OCR、scroll、wait 与规则确认；同时
断言 shadow 无 focus/click、action、finalize、next 或 refresh 调用。覆盖首屏 rule
字段与一次 OCR、R05/R06 disabled、有效新增与受保护短文本、uncertain/unavailable、
第 7/8 槽新增、预测后规则命中、Store 失败、runtime 中断、true/false/null、首个
预测不可覆盖及候选摘要 round-trip 投影。

## 后续注意事项

本 Change 只记录 shadow 预测，绝不以它提前结束扫描。Change 6 才能在 safe/full
中按冻结优先级处理已确认 bottom/no-new 与关键 Store 失败；仍须保持规则命中优先
legacy 返回，并复用同一上层出口。
