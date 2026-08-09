# BossOCR R07 Change 1：仓库基线与集成点复核报告

## 1. 范围、设计基线与结论

本 Change 仅进行只读复核、基线自动化验证和本报告。未实施 R07 生产代码、测试、配置或 schema。

已完整读取下列权威设计：

| 文档 | 版本 | HEAD 状态 |
|---|---|---|
| `docs/RPD-R07-ocr-scan-state-machine-dynamic-end.md` | 1.2（最终逻辑修订） | 已跟踪，存在于 HEAD |
| `docs/TID-R07-ocr-scan-state-machine-dynamic-end.md` | 1.2（最终逻辑修订） | 已跟踪，存在于 HEAD |

两份设计已在 `00adbc1c11817f7f27acb895f4b7da46619776db`（`docs(ocr): finalize R07 dynamic ending design`）提交。本 Change 未重复创建设计提交。

结论：当前生产代码仍是 R07 前的固定 8 槽 legacy 扫描；它具备 R03—R06 record、Store、Replay、P0/R01 和上层流程集成点，但尚无 R07 状态、位置分类、动态结束或 Store bool 回传。这与 RPD/TID 的“后续 Change 2—7 实施目标”一致，不是 Change 1 阻塞。

## 2. Git 基线

开始时：

```text
branch: main
HEAD: 00adbc1c11817f7f27acb895f4b7da46619776db
status: ## main...origin/main [ahead 14]
untracked (pre-existing): README.md, docs/project-review.zip,
                         venv-packages-before-reinstall.txt
```

开始前 `git diff --stat` 与 `git diff --check` 均无输出。最近提交中的相关项为：

```text
00adbc1 docs(ocr): finalize R07 dynamic ending design
c843a8e test(ocr): complete R06 final acceptance
3751e6c fix(ocr): bind R06 store ownership to candidate identity
ce33f34 feat(ocr): integrate R06 replay and sidecar
```

未整理、删除、暂存或修改开始前的三个无关未跟踪文件。

## 3. 当前有关键词扫描路径

```text
首位：run_detail_load_gate() 的 ready observation
后续位：confirm_candidate_switch() 的 confirmed observation
→ 主循环 start_candidate_ocr_recording()
→ 主循环 record_ocr_observation(first_observation, formal_screen, True, 1)
→ view_candidate(..., first_observation)
→ detect_keywords(first_observation)
→ OCRKeywordDetector.detect()
→ 规则结果
→ favorite / forward / 无动作
→ 剩余停留和 human_scroll_once()
→ prepare_candidate_switch_context()
→ finalize_current_candidate_recording()
→ 下一轮 confirm_candidate_switch() 或第 100 人 refresh_page()
```

`simple_brush.py:detect_keywords()` 是当前有关键词扫描入口；它在 OCR 已校准时调用 `ocr_detector.detect(forward_keywords, first_observation=...)`。`view_candidate()` 将命中结果一次性用于既有 favorite/forward 动作，随后按原停留时间执行 `human_scroll_once()`；该停留滚动不是 detector 的 7 次正常扫描滚动。

无关键词分支不调用 P0/正式 detector/R01 scan 路径：它调用 `view_candidate(i)`，以 `existing_flow_completed` finalize，并在非末位直接调用 `next_candidate()`。这是 R07 B-01 保持不变的边界。

## 4. 8 槽、规则确认和 legacy 早停

`ocr_detector.py:OCRKeywordDetector.detect()` 的实际循环为 `for scan_number in range(1, self.max_scans + 1)`，默认 `max_scans=8`。槽位 1 复用 `first_observation`（若有），其余槽位依次：

```text
self.scroll()
→ self.wait(self.settle_seconds)
→ capture_observation(scan_number)
→ bind_fingerprint_screen_index(..., scan_number)
→ _match_observation(...)
→ _notify_observation(..., formal_screen, True, scan_number)
```

因此完整无早停扫描最多有 8 个普通槽位和发生在槽位 2—8 前的 7 次 `self.scroll()`。`scroll is None` 时循环在后续槽位前 break。

`_match_observation()` 先以 legacy `matching_keyword_rule(observation.text, rules)` 判定，再计算仅观察性的 R04 comparison，并写入 `RuleComparisonResult`、`matched_keyword` 与 `matched_rule`。若普通槽位命中，detector 执行一次 `wait(confirmation_seconds)`、以该规则再次 `_observe()`、通知 `scroll_confirmation` 非正式记录，然后返回 `DetectionResult`；确认成功时 `confirmed_match=True`，不会继续后续槽位。这个 legacy early return 是 R07 必须保留并与可空 `dynamic_end_reason` 分离的真实行为。

当前 `DetectionResult` 字段为：`success`、`confirmed_match`、`matched_keyword`、`scans_completed`、`observations`、`error`；尚无 R07 end/abort/interrupt 字段。

## 5. 记录、Builder、R03—R06 与 Store 顺序

`OCRKeywordDetector._notify_observation()` 调用可选 callback，但返回值为 `None` 且忽略 callback 返回。其 callback 是 `simple_brush.py:record_detection_observation()`，后者也声明返回 `None`，只调用 `record_ocr_observation()`。

当前 `record_ocr_observation()`：

```text
检查 current_candidate_builder / ocr_record_store / observation identity 去重
→ CandidateOcrBuilder.build_screen_record(...) 一次
→ recorded_observation_ids[identity] = observation
→ JsonlOcrRecordStore.save_screen(record) 一次
→ 返回 record（不检查 save_screen() 的 bool）
```

`CandidateOcrBuilder.build_screen_record()` 以同一 record 先投影 R04 normalization/rule comparison；若 R05 record mode，则 `_aggregator.add_screen(record)` 后 replace R05 fields；若 R06 record mode，则 `_apply_similarity()` 在最终 R05 投影后调用现有 evaluator 一次，随后 append 到 builder 的 `_screens`。R06 evaluator 失败为单次 fail-open projection，不重试。当前默认 `R05_AGGREGATION_MODE="disabled"`，`R06_SIMILARITY_MODE="disabled"`，故默认运行不会构造 R05 聚合器或 R06 evaluator。

`JsonlOcrRecordStore.save_screen(record)` 的真实返回类型为 bool：通过 identity 校验和 `_save_record()` 后返回 `saved`，成功时更新 manifest screen count/digest cache，失败时记录 failure 并返回 false。当前调用者丢弃该 bool；这正是 Change 2/3 必须引入单次 save-status 反馈的接口缺口。

### 首屏 rule 字段现状

主循环在 `view_candidate()` 之前先手动保存 `first_observation` 为 `formal_screen`。之后 detector 才在槽位 1 对该同一 observation 调用 `_match_observation()`；但 `recorded_observation_ids` 已按对象 identity 去重，detector callback 不会重新 build/save。因此当前首屏 record 可在 rule comparison/match 写入前保存，rule 字段可能为空；后续 detector 槽位则先规则判断后 callback 保存。Change 5 应依 RPD/TID 复用同一 observation，规则判断一次后通过同一 record path 保存一次。

## 6. 当前数据合同

当前 `STORAGE_SCHEMA_VERSION` 是 `1.3.0`，支持 legacy `1.0.0`、R04 `1.1.0`、R05 `1.2.0` 与当前版本。`OcrScreenRecord` 已有 R03 `exact_hash`、`fingerprint_version`；其 source 是 `ScanObservation.fingerprint`（`r03-v1` exact hash）。

R05 screen/candidate 合同包含 `aggregation_status`、版本/config identity、分段/重复风险与 aggregation summary；R06 screen contract 含 `similarity_result` 和相似度/effective-new 投影字段，candidate 含 `similarity_summary`。R05/R06 仅在对应 record mode 启用时由 `CandidateOcrBuilder` 产生；disabled 是当前生产默认。

`RunManifest` 当前已有 R04/R05/R06 配置 identity、`aggregation_mode`、`similarity_mode` 和一个现存的 `dynamic_end_version` optional 字段；尚无 R07 mode/config、位置、计数、动态结束、预测或漏采完整性合同。`CandidateOcrDocument` 现有 `CaptureSummary` / end/abort 语义和 R05/R06 summaries，但尚无 R07 fields。

`ocr_replay.py` 已提供受 schema/version 合同约束的 R04/R05/R06 内存 replay 入口；没有 R07 CandidateOcrDocument position/no-new/prediction replay。

## 7. 焦点、身份与上层边界

`restore_candidate_page_focus()` 在校准 OCR region 内执行两次 `human_click()` 与 0.15 秒等待，返回 bool；它是 R07 safe/full 的唯一可复用焦点 helper。它目前也被 favorite 路径通过 `restore_candidate_page_focus_after_favorite()` 使用，R07 必须单独计数，不能改变其既有合同。

候选人身份由进入扫描前的 P0/R02 或 `confirm_candidate_switch(context, ...)` 已确认 observation 建立。`confirm_candidate_switch()` 仍拥有一次上层请求内最多两次 `next_candidate()` 物理尝试与有界观察/焦点恢复；R07 不应在每屏或 bottom 中重调该接口。

有关键词主循环在 scan 返回后：先保留 `view_candidate()` 的既有动作与停留；在非末候选人，先 `prepare_candidate_switch_context()`、再 `finalize_current_candidate_recording()`，下一次循环才调用 `confirm_candidate_switch()`；第 100 人后重置上下文/连续转发并调用 `refresh_page()`。R07 只能返回兼容扫描结果，不能直接调用动作、finalize、next 或 batch rollover。

## 8. R03—R06 验收与 waiver

已阅读 R03/R04/R05/R06 最终 Acceptance 与 `R05-change6-prerequisite-maintainer-waiver.md`：

- R03 自动化/静态验收附条件通过；exact hash 只表达同版本 normalized UTF-8 bytes，不能单独推导到底、加载或候选人身份。
- R04 pure 与 automated integration 通过；真实 shadow/enforce/production 未放行。
- R05 正式最终 Acceptance 仍 BLOCKED，原因是一项连续 8×64 p95 为 22.0040 ms，高于冻结 20 ms；production default 仍 disabled。
- waiver 仅允许 R05 record mode 作为 R06 Change 6 的 synthetic automated prerequisite，不批准改默认或真实页面/record。
- R06 automated final Acceptance PASS；R05 prerequisite 由 waiver 满足；R05/R06 production defaults 仍 disabled，真实页面/production activation 未批准。

这些事实与 R07 的 disabled-by-default、synthetic-only、safe 不强依 R05/R06 record、full no-new 要求 R05/R06 record 的设计一致。

## 9. 基线验证

全部在 Windows PowerShell、`F:\BOSSOCR`、本地 `venv` 执行。命令与仓库实际可运行入口相同：

| 命令 | 结果 |
|---|---|
| `.\venv\Scripts\python.exe -m unittest discover -s tests -q` | PASS：694 tests，18.500 s。测试会输出预期 mock Store failure/log 行。 |
| `.\venv\Scripts\python.exe -m tests.benchmark_r04_normalization` | PASS：全部场景 deterministic；最大 peak 999.02 KiB。 |
| `.\venv\Scripts\python.exe -m tests.benchmark_r05_aggregation` | PASS：`required_performance_gates_pass=true`、`contract_blockers=[]`；8×64 unique pure p95 16.8720 ms。此当前结果不改变 R05 历史正式 BLOCKED 结论。 |
| `.\venv\Scripts\python.exe -m tests.benchmark_r06_similarity` | PASS：`required_performance_gates_pass=true`；20k required scenarios p95 9.8495/12.7639/10.3458 ms，8 adjacent p95 14.4029 ms。 |
| `.\venv\Scripts\python.exe -m pip check` | PASS：`No broken requirements found.` |

未运行真实 BOSS 页面、真实候选人数据或 macOS GUI。

## 10. Change 2—7 预计修改文件

| Change | 预计文件 |
|---|---|
| 2：最小数据与反馈 | `ocr_records.py`、`ocr_detector.py`、`simple_brush.py`、现有 records/store tests。 |
| 3：单次 record 与位置 | `ocr_detector.py`、`simple_brush.py`、必要时 `ocr_candidate.py`/`ocr_records.py`，detector/records tests。 |
| 4：first-same 恢复 | `ocr_detector.py`、`simple_brush.py`、detector/simple-brush integration tests。 |
| 5：shadow/首屏 | `ocr_detector.py`、`simple_brush.py`、必要时 `ocr_records.py`、integration tests。 |
| 6：safe/full 返回 | `ocr_detector.py`、`simple_brush.py`、integration tests。 |
| 7：Replay 与收口 | `ocr_replay.py`、必要时 `ocr_records.py`/`ocr_store.py` reader、replay/store tests、实施报告。 |

实际测试文件以 Change 开始时仓库现有命名为准；已确认的相关模块包括 `test_ocr_detector.py`、`test_simple_brush_ocr.py`、R04/R05/R06 records/store/replay/candidate/aggregation/similarity 测试和三个 benchmark 模块。

## 11. 设计对照与后续关注

RPD/TID 与真实仓库没有 Change 1 阻塞性冲突：它们正确将 R07 描述为未来最小增量，并保留 current fixed-8 legacy behavior、R01 内部两次物理 next、disabled defaults 和无关键词/batch 边界。

需要后续 Change 关注、但不在 Change 1 修复的事实：

1. 现有首屏在规则结果前保存，且 identity 去重阻止后补；Change 5 必须一次 rule→record 修正。
2. detector callback 和 `record_detection_observation()` 不回传 record/save/position；Change 2/3 必须建立一次性结果反馈。
3. builder 当前在 build 内完成 R05/R06 投影，Store 仅在其后发生；Change 3 必须在同一 record 保存前附加 R07 metadata，不能二次 build/save。
4. 当前 `CaptureType` 仍使用 `scroll_confirmation` 记录既有规则确认；Change 2/3 需保留旧 reader 兼容，同时引入 R07 约定的 `rule_confirmation` / `position_confirmation`，不修改已保存旧数据。
5. `RunManifest` 已有 optional `dynamic_end_version`，Change 2 必须审慎扩展，不把现有 R03—R06 identity 改造成新的事务系统。
6. Store `save_screen()` 已有 bool，但上层/Callback 未传播；Change 2/3/6 必须按模式使用该 bool，且不得 retry 同一 screen。

## 12. Change 1 声明

本报告是本 Change 唯一创建的文件。未进入 Change 2；未修改生产代码、测试、配置、schema、依赖、打包、CI、运行数据或其他文档；未 push、tag 或 Release。
