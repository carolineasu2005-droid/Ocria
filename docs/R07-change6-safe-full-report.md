# R07 Change 6：Safe/Full 扫描返回报告

## 基线与范围

- 基线提交：`25570645ffa0df4ffb5d237269b2a184669a2345`
  (`feat(ocr): integrate R07 shadow analysis`)。
- 权威设计：RPD/TID 1.2（最终逻辑修订）。默认 `DynamicEndConfig.mode` 仍为
  `shadow`；没有修改 R05/R06 默认 mode，也没有运行真实页面或真实 record。
- 本 Change 只接入 detector 返回与既有 candidate finalize 出口；未进入 Change 7，
  未修改 R01、无关键词分支、候选人 action、next 或 batch rollover。

## 实现

### 返回优先级

safe/full 在每个已处理并获得 Store bool 的普通槽位后，依序处理：中断、关键
Store/健康/位置失败、legacy 规则确认、第 8 槽 limit、已确认 bottom、full no-new。
off/shadow 不使用这些控制分支。

规则命中在所有模式仍先走既有一次 `rule_confirmation` 并立即返回
`confirmed_match=true`、`dynamic_end_reason=null`；不会在其后评估 bottom/no-new。

### Safe 与 Full

- safe 只会因 Change 4 已确认、健康且已保存的 position confirmation 返回
  `scroll_bottom`；不会因 no-new 返回。
- full 额外只接受连续两个已保存 `formal_screen`、`changed`、健康、R05 completed、
  R06 completed、`effective_new_status=none`，且无 possible/uncertain/有效短文本的
  槽位，返回 `no_new_text`。
- 新增、受保护短文本、possible、uncertain、same/unavailable、R05/R06 disabled 或
  failed、健康异常、position confirmation 和 Store false 会清零或阻止 no-new。
- 第 8 槽的已保存普通 record 优先返回 `max_screen_limit`，不触发恢复。
- 用作 bottom/no-new/limit 的关键 screen 未保存，或已有健康/位置事实不足时，返回
  `abort_reason`（包括 `store_failed`），不二次保存或正常结束。ESC/runtime 返回
  `interrupt_reason`。

### 上层出口

`candidate_capture_status()` 将 `scroll_bottom`、`no_new_text`、`max_screen_limit`
统一投影为现有 `COMPLETED_WITH_LIMIT` 出口；abort/interrupt 仍分别使用既有状态。
`finalize_current_candidate_recording()` 只复用该结果投影已有 abort 字段，不改变
action、finalize、停留、next 或 refresh 次数。R07 本身仍不调用 next、switch、收藏、
转发或 batch refresh。

## 修改文件

- `ocr_detector.py`
- `simple_brush.py`
- `tests/test_ocr_detector.py`
- `tests/test_ocr_stage0_integration.py`
- 本报告

## 验证

- `python -m compileall -q ocr_detector.py simple_brush.py tests`：PASS。
- 相关 detector / Stage0 / brush / candidate / records / store 回归：443 tests，PASS。
- `python -m unittest discover -s tests -q`：725 tests，20.797s，PASS。
- `python -m pip check`：PASS。

覆盖 safe bottom、safe no-new 禁止、full 单次与连续双 no-new、有效新增/受保护短
文本/possible/uncertain/same/R05-R06 disabled 重置、规则优先、slot 8 优先、Store
failure、ESC/runtime、默认 shadow、动态与 legacy limit 的同一 candidate 出口，以及
R07 不直接进入上层 action/finalize/next/refresh 流程。既有 synthetic run coverage
继续验证 batch rollover、无关键词路径和 R01 的上层边界未变。

## 后续注意事项

Change 7 才能实现纯离线 Replay、兼容收口与基准记录。本 Change 没有创建 Sidecar、
事件账本或真实生产启用。
