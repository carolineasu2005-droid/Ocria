# BossOCR R07 技术实施设计：OCR 扫描状态与动态结束（最终收敛版）

## 1. 实施边界

| 项目 | 值 |
|---|---|
| 文档版本 | 1.2（最终逻辑修订） |
| 基线 | `main` / `c843a8e98ca3f1992955f1846695657cf6150326` |
| 默认模式 | `shadow` |
| 授权 | synthetic 实现与自动化测试；无真实页面、真实 record 或生产启用 |
| 当前阶段 | 设计；不进入 Change 1 |

R07 v1 只改有关键词 OCR 扫描路径。无关键词分支、R01、R05/R06 算法、batch rollover、候选人动作和完整上层生命周期不改。不要实现强结束标志、preview/clone 事务、CandidateCompletionGuard、post-save receipt、Sidecar、跨文件审计或完整 event ledger。

## 2. 已核实的接口

| 文件 / 符号 | 当前事实 | R07 接线 |
|---|---|---|
| `ocr_detector.py: OCRKeywordDetector.capture_observation()` | 一次截图/识别产生 `ScanObservation`，已有 R03 fingerprint 与 R04 normalization。 | 一次 capture 复用，绝不为 R07 重新 OCR/hash/normalization。 |
| `ocr_detector.py: _match_observation()` / `detect()` | 槽位中先规则判断，再通过 `_notify_observation()`；规则确认成功立即返回 `DetectionResult`。 | 保留该规则早停；协调器扩展为兼容 `ScanResult`。 |
| `simple_brush.py: record_ocr_observation()` | 调用 `CandidateOcrBuilder.build_screen_record()`，再调用 `JsonlOcrRecordStore.save_screen()`；异常记录 error。 | 改为一次构建/投影/分类/附加/保存，并向 detector 返回结果。 |
| `simple_brush.py: record_detection_observation()` | 是 detector observation callback。 | 返回 `RecordedObservationResult`，不再丢弃 store bool。 |
| `simple_brush.py: detect_keywords()` | 调用 detector 并读取 `DetectionResult` 的规则结果。 | 保持规则调用者契约，读取兼容扫描结果。 |
| `simple_brush.py: restore_candidate_page_focus()` | 现有正文区域 helper，内部两次点击，返回 bool。 | safe/full 每候选人最多调用 helper 一次。 |
| `simple_brush.py: confirm_candidate_switch()` | 一次上层切换请求内，至多两次物理 next 尝试和现有验证。 | R07 不调用、不重跑、不改写。 |
| `simple_brush.py: finalize_current_candidate_recording()` 与主循环 | 扫描后负责动作、finalize/save、停留、switch/refresh。 | R07 仅返回，继续走当前上层一次。 |
| `ocr_candidate.py` / `ocr_records.py` / `ocr_store.py` | 既有 Builder、schema、JSONL store 与兼容读取。 | additive 字段和一次性 save-status 反馈，不做二阶段交易。 |
| `ocr_replay.py` | 既有纯内存 R05/R06 replay 模式。 | 加 CandidateOcrDocument 级 R07 pure replay。 |

候选人在进入扫描前已经经 P0/R02 或 R01 confirmed context 建立。R07 的 `load_health` 仅读取该通过事实和当前 observation 的现有 OCR 框数、文本/正文锚点或既有健康字段；`identity_health` 仅读取已成功进入的候选人上下文或已确认 R01 context。不得对每屏运行 `run_detail_load_gate()`、P0 retry、R01、`confirm_candidate_switch()` 或新增候选人身份 OCR；bottom 也不能调用 next/switch。

## 3. 最小结果、状态与字段

在 `ocr_detector.py` 增加小型 `DynamicEndState`，只保存：mode、`scan_slot_count`、`normal_scroll_count`、`unique_position_count`、`ocr_attempt_count`、`scroll_retry_count`、`focus_restore_count`、连续 no-new、最后可比较 record/hash、first prediction 及恢复额度已用标记。它不是候选人生命周期 reducer。

扫描结果保留现有 `DetectionResult` 消费者所需的 `success`、`confirmed_match`、`scans_completed`、`observations`、`error`，并增加或等价承载：

```python
dynamic_end_reason: Optional[str]  # scroll_bottom/no_new_text/max_screen_limit 或 None
abort_reason: Optional[str]
interrupt_reason: Optional[str]
```

规则确认成功时，所有模式返回 `confirmed_match=True` 与既有规则完成语义，`dynamic_end_reason=None`。它优先于任何后续 R07 scroll/no-new 决策，绝不转换成 `max_screen_limit`、`scroll_bottom` 或 `no_new_text`。

普通槽位的 capture type 固定为 `formal_screen`；其它为 `load_check`、`load_retry`、`rule_confirmation`、`position_confirmation`、`switch_check`。`scroll_confirmation` 只被旧 schema reader 接受。R07 v1 不增加或写出 `position_observation`。

计数规则：普通槽位完成才增加 `scan_slot_count`（最大 8）；槽位 2—8 的现有滚动增加 `normal_scroll_count`（最大 7）；首屏 initial 和每次 changed 增加 `unique_position_count`；每次真实 capture（含规则/位置确认）增加 `ocr_attempt_count`；first-same 只允许一次 `focus_restore_count` 和 `scroll_retry_count`。same/unavailable 不增加 unique count，不进入 full no-new。

## 4. 单次 record 处理顺序

为消除“保存后才得到 position”的顺序缺口，将 `record_ocr_observation()` / `record_detection_observation()` 改为一个最小、同步的 record callback。每个普通槽位严格一次执行：

```text
1. detector.capture_observation() 一次
2. detector 现有规则判断一次
3. record_ocr_observation() 以同一 observation 构建 canonical OcrScreenRecord 一次
4. CandidateOcrBuilder 按现有语义在该 record 上完成 R03—R06 一次
5. 使用该 record 已生成的 R03—R06 和已有 health 计算 PositionDecision 一次
6. 将 R07 最小字段附加到同一 record
7. JsonlOcrRecordStore.save_screen(record) 一次
8. callback 返回 record、saved 与 PositionDecision
9. detector 仅据此更新 DynamicEndState
```

建议返回类型：

```python
RecordedObservationResult(
    record: OcrScreenRecord | None,
    saved: bool,
    position_decision: PositionDecision | None,
)
```

名称可按现有仓库风格调整。它不是 token、revision 或 accept 协议。严禁 build 两次、规则判断两次、R05/R06 两次、save 两次，或同一 screen Store 失败后 retry。same/uncertain 屏仍以 canonical `formal_screen` 进入现有 Builder/R05/R06 并保存；R07 不 rollback 已有聚合。

Store 失败时 callback 必须返回 `saved=False`。detector 不得把该 record 当成已保存的动态结束、no-new 或 false 漏采证据；同时调用现有错误记录路径，不创建补偿性 UI 动作。

首屏在 Change 5 使用相同 observation，顺序改为规则判断一次后再通过上述 path 保存一次，修复 rule 字段为空；不增加 OCR，也不改变规则命中。

## 5. 纯位置分类

实现单一纯 helper：

```python
classify_position(previous_record, current_record, *, load_health,
                  ocr_health, identity_health) -> PositionDecision
```

它只读取 canonical record 内已存在的 R03—R06 和 health，不做 OCR、滚动、Store 或调用前序算法。

1. 首屏为 `initial`。
2. R03、load、OCR 或 identity 不可用，结果 `unavailable`。
3. 有 R05/R06 时，如有 definite conflict、possible 或 uncertain，结果 `uncertain`。
4. exact 相同且没有有效新增/短文本/冲突，结果 `same`。
5. exact 不同，或现有结果明确有效新增/受保护短文本，结果 `changed`。
6. 其余保守为 `uncertain`。

`PositionDecision` 含 `position_status`、`page_change_status`、`reference_screen_id`、`prediction_reason` 与不足证据标记。safe bottom 不把 disabled R05/R06 作为自动失败；full no-new 必须要求 completed R05/R06 record。

## 6. 扫描、规则早停与终止优先级

`OCRKeywordDetector.detect()` 保持唯一 8 槽协调循环。每个槽位先完成本节规则处理和第 4 节 record callback，再更新 R07 state。规则命中走既有一次 `rule_confirmation`；一旦 confirmed，立即以 legacy 规则完成结果返回，`dynamic_end_reason=None`，不启动之后的 normal scroll、bottom 或 no-new。四模式行为一致，调用者仍只执行一次既有动作。

safe/full 的每槽位完整处理后按以下顺序解析：

```text
1. user_interrupted / runtime_expired
2. 已发生技术失败或关键 Store 失败
3. confirmed_match → legacy rule completion, dynamic_end_reason=None
4. 已成功保存第 8 槽 → max_screen_limit
5. confirmed scroll_bottom
6. full confirmed no_new_text
7. continue
```

同槽位仅有一个正常原因。off/shadow 不执行第 4—6 项 R07 控制，仍按 legacy 流程和早停。现有 `existing_flow_completed` 保留 legacy 事实，不强行映射 R07 原因。

## 7. first-same、confirmation 与额度

仅 safe/full 可在非第 8 槽的首次 same 后执行一次：读取已有 load/OCR/identity health → `restore_candidate_page_focus()` 一次 → 现有 scroll 原语一次 → 原 settle wait → confirmation OCR 一次。confirmation 同样先做规则判断，随后走第 4 节的一次 canonical path。

| confirmation 结果 | 保存与计数 | 控制 |
|---|---|---|
| same，且健康、已保存、无 known new/conflict | `position_confirmation`；不增 slot/unique，增 OCR attempt | `scroll_bottom`。 |
| same 但证据不足 / unresolved | `position_confirmation`；不增 slot/unique，增 OCR attempt | 不判 bottom；按 typed failure 或不足证据处理。 |
| changed | 同一个 capture 仅保存为 `formal_screen`；提升为紧邻的下一普通槽位，增加 slot/unique | 继续；不再 OCR、不立即再 normal scroll。 |

例：已完成 slot 4，normal scroll 后 slot 5 为 same；恢复 confirmation changed 则是 slot 6，下一次 normal scroll 才是 slot 7。总 slot 永不超过 8。confirmation changed 不得同时写 position-confirmation 和 formal-screen 两条记录。

当第 8 个普通槽位已成功保存，直接进入 `max_screen_limit`，不再启动 focus/retry/confirmation。每候选人仅一套恢复额度；若恢复后 later same，再也不恢复、不重试、不确认、不判 bottom、也不提前 `position_unresolved`。记录 `insufficient_evidence_after_recovery`（或等价不足证据），不增 unique、不参与 no-new、不覆盖 first prediction，继续剩余 legacy 槽位至规则早停或第 8 槽。

动作异常分别为 `load_failed`、`switch_failed`、`ocr_failed`、`focus_restore_failed`、`scroll_failed`、`position_unresolved`；ESC/runtime 优先为中断。shadow/off 绝不执行恢复序列。

## 8. full no-new、shadow 与可空漏采结论

`full` 的纯 no-new 谓词仅接受已保存、`changed` 的普通槽位，且 R05/R06 completed、`effective_new_status=none`、无 possible/uncertain/有效短文本，并且 load/OCR/identity 健康。阈值 2；任一新增、短文本、possible、uncertain、R05/R06 缺失/失败、same/unavailable、confirmation 或异常即清零。

shadow 只消费 legacy 已生成证据。它冻结 first prediction，继续旧扫描到规则早停或正常终点。Candidate 字段：

```text
prediction_would_miss_content: bool | null
prediction_would_miss_rule_match: bool | null
prediction_observation_complete: bool | null
prediction_evidence_complete: bool | null
```

content=true 表示预测后观察到有效新增或有效短文本；rule=true 表示预测后首次规则确认命中。false 只在有 first prediction、legacy 完整到正常终点、预测后相关槽位全部处理、所需 R05/R06 或规则证据完整且未见相应事件时成立。没有 first prediction、规则早停、技术失败、ESC/runtime、Store 失败、disabled/不完整 R05/R06、或窗口不完整时写 null。预测后发生规则命中时，rule=true；因之后内容窗口不完整，content 可以为 null。

`prediction_observation_complete` 只表达预测后的旧控制流观察窗口是否完整；`prediction_evidence_complete` 只表达得到结论所需 R05/R06/规则证据是否完整。二者不扩展为旧版 coverage/ledger 系统。shadow 的 effect spy 必须证明 OCR、scroll、wait、click/focus、规则确认、动作、finalize、next、refresh 调用序列为零增量。

## 9. 最小 schema、Store 分支与 Replay

`ocr_records.py` 按当前 additive reader/writer 方式在 screen、candidate/summary、manifest 增加最小字段。screen：版本、position、page change、reference、is-position-confirmation、prediction reason。candidate：mode、可空 dynamic end reason、abort、六项计数、first prediction、两个 nullable miss 和两个 complete 字段。manifest：版本、mode、最小 config。旧记录缺失字段为未知 null，不能伪造健康、完成或 dynamic end。

off/shadow 的 metadata Store failure：报告既有 error、R07 evidence 视为不足、无新 UI/提前控制/重试；若主流程本来有 Store 停止合同则原样尊重。safe/full 的当前普通/confirmation record 一旦会作为 bottom、no-new 或 max-limit 证据而 `saved=False`，返回 `abort_reason=store_failed`，不产生正常结束、不做第二次 save。故接口合同是 build 一次、save 一次、save result 回传一次。

`ocr_replay.py` 新增如 `replay_dynamic_end(candidate_document)` 的纯内存入口，按已保存屏序重放位置/no-new/prediction。它不 OCR/UI/Store、不会修改 source、不重跑 R05/R06、也不能确认 bottom；缺证据为 `insufficient_evidence`。它读取 legacy rule completion、空 dynamic end reason 与所有 nullable 预测字段。无 Sidecar。

## 10. 上层边界

R07 返回兼容扫描结果给 `detect_keywords()`；现有调用者继续处理规则动作、`finalize_current_candidate_recording()`、停留、`prepare_candidate_switch_context()`、`confirm_candidate_switch()` 和 100 人 refresh。动态返回和旧 8 槽返回走同一扫描出口。

测试和实现都必须保证：R07 不调用 `next_candidate()`/`confirm_candidate_switch()`；返回后动作、finalize 和上层 next 请求最多一次；无关键词 `view_candidate()` 分支不变；第 100 人 F5、重筛、首位点击仍走原 batch 路径。R01 的“一次”仍是一次上层请求，其内部最多两次物理键行为保留。

## 11. Change 1—7 文件计划

### Change 1：基线报告

只读当前 RPD/TID、相关代码和 tests；创建且只创建 `docs/R07-change1-baseline-report.md`。报告记录 branch/HEAD、git 状态、真实扫描入口、record/build/save 顺序、首屏 rule 现状、R03—R06 接口位置、测试基线、预计 Change 2—7 文件和与本设计一致性。不得改生产、测试、配置或 schema。允许 checkpoint commit `test(ocr): establish R07 implementation baseline` 或仓库等价消息。

### Change 2：最小数据与反馈

预计：`ocr_records.py`、`ocr_detector.py`、`simple_brush.py` 和 records/store tests。加入四模式、状态/计数、可空 dynamic end/漏采/完整性字段及一次 Store bool 反馈；不改变扫描控制。

### Change 3：一次 record 与位置

预计：`ocr_detector.py`、`simple_brush.py`、必要的 `ocr_candidate.py`/`ocr_records.py` 与 detector/records tests。实现第 4 节顺序与五态分类，取消 `position_observation`；无预览、回滚、额外 OCR/scroll。

### Change 4：first-same 恢复

预计：`ocr_detector.py`、`simple_brush.py` 和 detector/simple-brush tests。实现单次额度、confirmation same/changed 提升、第 8 槽优先与 later same 继续；默认 shadow。

### Change 5：shadow 与首屏

预计：`ocr_detector.py`、`simple_brush.py`、可能的 `ocr_records.py` 与 integration tests。修正首屏 rule→save，记录 nullable miss/complete；规则命中保持 legacy early return；验证 effect sequence。

### Change 6：safe/full 返回

预计：`ocr_detector.py`、`simple_brush.py` 和 integration tests。接入未命中规则时的 bottom/no-new、优先级、Store failure 和同一上层出口；不改 action/next/batch/无关键词。

### Change 7：Replay 与收口

预计：`ocr_replay.py`、必要的 records/store reader、replay/store tests 和实施报告。覆盖 legacy rule/empty dynamic reason/nullable fields，运行全量、既有 R04/R05/R06 benchmark、R07 性能记录、隐私、Windows mock 与 macOS pure；无 Sidecar、无独立最终 Acceptance。

后续实施按 Change 1→7 连续进行，每项定向测试及 checkpoint commit 后自动进入下一项；全部完成后独立会话集中验收/修复。本次仅修订文档，不创建 baseline report 或 checkpoint。

## 12. 测试矩阵

| 范围 | 必测断言 |
|---|---|
| 规则早停 | off/shadow/safe/full 均一次规则确认、立即 legacy return、`dynamic_end_reason=None`、一次动作。 |
| 单次 record | 每屏一次 capture/rule/build/R03—R06/save；position 写入同一保存 record；Store bool 返回 detector。 |
| 槽位/确认 | confirmation same 不占槽；changed 占下一槽且只存一次；第 8 槽不恢复；最大 8 槽/7 正常滚动。 |
| 恢复额度 | first same 后一次 focus/scroll/confirmation；confirmation changed 后 later same 无第二次恢复/abort，继续至规则或 slot 8。 |
| 健康来源 | R07 不重跑 P0/load retry/R01/identity OCR；bottom 不 next/switch；shadow 零身份副作用。 |
| full | 两个健康 changed/no-new；短文本、新增、possible、uncertain、same、异常和 R05/R06 缺失均清零。 |
| 漏采 | true/false/null；预测后规则命中 rule=true/content 可 null；两个 complete 字段。 |
| Store | off/shadow 无新控制；safe/full 关键证据保存失败为 `store_failed`，无第二次 save/正常结束。 |
| 上层与兼容 | 动态/limit 返回同出口，动作/finalize/next 不重复，batch/无关键词不变，旧 schema/legacy rule 可读。 |
| Replay/回归 | 无 UI/source mutation、不确认 bottom；ESC/runtime、隐私、全量 unittest、R04/R05/R06 benchmark、Windows mock、macOS pure。 |
| Change 1 | baseline report 可唯一文档产物并可 checkpoint commit，不改代码。 |

## 13. 风险与停止条件

真实风险为错误提前结束、滚动误判、7/8 屏漏采、OCR 波动、shadow 侧效应、full 证据不足、Store 失败、ESC/runtime、跨平台及同位置 R05/R06 重复聚合证据。R07 只用 position 过滤自身判断，不 rollback 前序结果。

若实现需要第二个 OCR/hash/R03—R06 算法、任何 preview/clone 事务、shadow 额外 UI 副作用、first same 直接 bottom、R07 direct next、自动启用 R05/R06，或因 Store false 重试同一 screen，应停止并回到本设计。

## 14. 本阶段声明

本 TID 只冻结后续最小实现；本轮仅改 RPD/TID，未创建 Change 1 baseline report，未进入 Change 1，未修改生产/测试/配置/schema/运行数据，未 commit、push、tag 或 Release。
