# BossOCR R07 产品需求文档：OCR 扫描状态与动态结束（最终收敛版）

## 1. 文档信息

| 项目 | 值 |
|---|---|
| 需求编号 | R07 |
| 文档版本 | 1.2（最终逻辑修订） |
| 日期 | 2026-08-02 |
| 基线分支 / 提交 | `main` / `c843a8e98ca3f1992955f1846695657cf6150326` |
| 默认模式 | `shadow` |
| 本阶段 | 仅修订 RPD/TID；未进入 Change 1 |

权威顺序为：本次维护者决议 > R07 产品边界 > 当前 TID > 当前代码 > 历史 R07 设计。本文只冻结后续 Change 1—7 的最小实施合同。

## 2. 背景与目标

有关键词 OCR 路径的 `OCRKeywordDetector.detect()` 当前固定最多执行 8 个扫描槽位：首屏 OCR，之后每槽位先向下滚动、等待，再 OCR。它不判断滚动是否进入新视觉位置，可能重复 OCR 同一位置；页面未变化也无法区分真正到底、滚动/焦点失效、加载异常、OCR 异常或候选人身份异常。

R07 v1 只在这条**有关键词 OCR 扫描路径**中：

- 保留最多 8 个扫描槽位与最多 7 次正常向下滚动；
- 标注 `initial`、`changed`、`same`、`uncertain`、`unavailable` 五种视觉位置状态；
- 不把第一次 same 直接认定为到底；
- 在 safe/full 中以一次焦点恢复、一次重试滚动和一次确认 OCR 保守确认 `scroll_bottom`；
- 在 full 中以连续两个健康的新位置无有效新增确认 `no_new_text`；
- 默认 shadow 仅记录预测及漏采风险，保持旧页面调用序列；
- 从扫描函数返回结构化结果，复用既有动作、保存、停留、下一位和 batch 流程；
- 持久化最少状态、模式、预测、结束原因和计数，并支持纯离线 Replay。

R03 exact hash、R04 归一化、R05 聚合、R06 相似度/有效新增继续按现有实现消费；R07 不重做这些算法。

## 3. 非目标与不变边界

R07 不改 R01—R06 算法或默认启用状态，不重构收藏、转发、候选人切换、保存、停留或 batch 生命周期；无关键词分支保持原状。

R07 v1 不实现强结束标志、同事沟通记录、视频简历、正文边界截断、marker；不采用 clone/preview/persist/accept/discard 事务；不建立完整候选人生命周期状态机、post-save receipt、完整 event ledger 或 Sidecar/跨文件 digest；不新增数值硬性能门。真实页面、真实 record 和 safe/full 生产启用仍未批准。R07.1 可另行评估 Sidecar、跨文件审计或 R05 重复聚合证据问题。

## 4. 扫描槽位与视觉位置

扫描槽位是旧计划实际完成的一次普通 OCR 采集；所有普通槽位照现有 Builder/Store 路径进入 R03—R06 并保存。视觉位置与保存正交：同位置或不确定的屏幕也可保存为现有证据，R07 不 rollback 既有聚合结果。

每个后续槽位相对于最后可比较位置记录：

```text
initial | changed | same | uncertain | unavailable
```

同位置屏幕不增加 `unique_position_count`，不参与 full 的连续无新增；可用于 shadow 预测与 bottom 判断。至少区分 `scan_slot_count`、`normal_scroll_count`、`unique_position_count`、`ocr_attempt_count`、`scroll_retry_count`、`focus_restore_count`。这些是有限计数，不是事件账本。

位置基础是当前 observation 的 R03 exact、OCR/加载健康和已知候选人身份健康；现有 R05/R06 record 若存在可提供冲突、新增、possible 与短文本信息。R07 不重新运行 P0/R02、load retry、R01 或候选人身份 OCR：它只读取候选人进入扫描前已经通过的 P0/R01 上下文和当前 observation 的已有健康数据。

## 5. 模式

| 模式 | 行为 |
|---|---|
| `off` | 完全保留旧扫描、规则早停与 legacy 结束语义；可仅写兼容字段。 |
| `shadow`（默认） | 使用旧路径已生成证据记录 `possible_scroll_bottom`、`no_new_text_candidate` 或 `insufficient_evidence` 及漏采分析；不新增 OCR、滚动、等待、点击、焦点恢复或提前返回。 |
| `safe` | 包含 shadow；仅允许已确认的 `scroll_bottom` 从扫描层提前返回。 |
| `full` | 包含 safe；额外允许连续两个健康新位置无有效新增的 `no_new_text`。 |

默认始终 `shadow`，不得自动启用 R05/R06。safe bottom 以 R03、加载/OCR/身份健康与恢复确认作核心证据；R05/R06 有明确冲突、有效新增或 uncertain 时阻止 bottom，但它们 disabled 不得使 safe 永久不可用。full no-new 必须有 completed R05 record 与 R06 record；二者未启用只禁用 no-new，不降级 safe。

## 6. 既有规则命中与 R07 动态结束

既有规则命中完成**不等于** R07 动态结束。四种模式中，规则命中并通过现有规则确认后，均立即沿既有路径返回扫描函数：`confirmed_match=true`，legacy 规则完成状态保持，`dynamic_end_reason=null`。不得把规则命中伪装为 `max_screen_limit`、`scroll_bottom` 或 `no_new_text`，也不得在 safe/full 中强制继续扫描。

R07 的 `dynamic_end_reason` 只有 R07 实际控制扫描结束时才可为：

```text
scroll_bottom | no_new_text | max_screen_limit
```

规则确认优先于后续 R07 滚动判断。扫描返回后继续复用既有上层规则动作，动作只执行一次。

## 7. 首次 same、确认与槽位边界

第一次正常滚动后的 `same` 不能直接判到底。off/shadow 继续旧槽位计划且不增加恢复副作用。safe/full 仅在尚未用尽恢复额度、且当前槽位不是第 8 槽时，依序：检查已有 load/OCR/identity 健康 → 现有焦点恢复 helper 一次 → 现有下滚原语一次 → 现有 settle 等待 → 确认 OCR 一次。

- 确认页仍 same：为 `position_confirmation`，不增加 `scan_slot_count` 或 `unique_position_count`，增加 `ocr_attempt_count`；所有健康门满足且无 known new/conflict 才为 `scroll_bottom`。
- 确认页 changed：该同一次 capture 作为下一个普通槽位处理及保存，增加 `scan_slot_count` 与 `unique_position_count`，不再 OCR、也不立即再 normal scroll。例如 slot 5 first-same 后 confirmation changed 成为 slot 6；下一次正常滚动才产生 slot 7。
- 第 8 槽完成并保存后，直接 `max_screen_limit`；不得启动焦点恢复、重试滚动或确认 OCR。
- 每候选人最多一次 focus restore、一次 retry scroll、一次确认 OCR。额度用完后再次 same 时，既不恢复、不重试、不确认、不判 bottom、也不以 `position_unresolved` 提前中止；写 `insufficient_evidence_after_recovery`（或等价不足证据），继续旧剩余槽位直到规则命中或第 8 槽。

确认页 same/unresolved 的 capture type 为 `position_confirmation`。确认页 changed 仅作为一个 `formal_screen` 保存，不能同时保存两条记录。R07 v1 不使用新的 `position_observation`；普通 same/uncertain 槽位仍为普通 `formal_screen`，以保留当前 R05/R06 语义。旧 `scroll_confirmation` 只作 reader 兼容。

技术失败只能如实记录为 `load_failed`、`switch_failed`、`scroll_failed`、`ocr_failed`、`focus_restore_failed`、`position_unresolved`、`store_failed` 或 `unexpected_error`；中断为 `user_interrupted`、`runtime_expired`。

## 8. full `no_new_text`

仅 full 可用，阈值为 2。计数屏必须是确认的 `changed` 普通槽位，R05/R06 均 completed、`effective_new_status=none`、无 possible/uncertain/有效受保护短文本，且加载、OCR、身份健康。有效新增、短文本、possible、uncertain、R05/R06 缺失/失败、same/unavailable、非正式 position confirmation 或任一健康异常均清零。单次无新增不结束。

## 9. 保存、预测与 Replay

每个普通槽位按现有语义只构建并保存一次；R07 在同一待保存 record 上附加位置与最小元数据。Store 失败不重试同一 screen，也不能把未保存 record 当作动态结束或 false 漏采结论的证据。

off/shadow 中，R07 metadata 保存失败只通过既有错误记录报告、将 R07 证据视为不足，且不得增加控制流或页面副作用；现有主流程若自身有 Store 行为，仍按其既有合同。safe/full 中，如果将用于 `scroll_bottom`、`no_new_text` 或第 8 槽 limit 的 record 未成功保存，则为 `abort_reason=store_failed`，不得正常结束。

capture type 仅为：`formal_screen`、`load_check`、`load_retry`、`rule_confirmation`、`position_confirmation`、`switch_check`。Screen 评估 additive 的版本、位置、页面变化、reference、是否 position confirmation 与预测原因；Candidate 评估模式、可空 dynamic end reason、abort、计数、首个预测和 nullable 漏采字段；Manifest 评估版本、模式与最小配置。旧 schema 可读，缺失 R07 字段为未知，不伪造健康结论。

漏采字段 `prediction_would_miss_content`、`prediction_would_miss_rule_match` 是 nullable boolean。预测后出现有效新增/短文本，content=true；预测后首次规则确认命中，rule=true。false 仅在存在 first prediction、旧控制流完整至正常终点、预测后相关槽位处理完整、所需 R05/R06/规则证据完整且未发现相应内容/命中时填写。没有预测、规则早停导致窗口未完整、技术失败、ESC/runtime、Store 失败、R05/R06 disabled/不完整或窗口不足时为 null。新增最小 `prediction_observation_complete` 与 `prediction_evidence_complete` 字段表达这两个完整性事实；预测后规则命中时 rule=true，而 content 仍可为 null。

Replay 只从 `CandidateOcrDocument` 已保存屏幕按保存顺序重放位置/no-new/预测的纯判断；不执行 UI、不修改源对象、不新确认 bottom。它必须支持 legacy 规则完成、空 dynamic end reason 和 nullable 漏采字段；证据不足输出 `insufficient_evidence`。不创建 Sidecar。

## 10. 返回、优先级与维护者决议

R07 只从现有扫描函数返回结构化结果；后续既有上层继续负责动作、candidate finalize/save、停留、`confirm_candidate_switch()` 与 batch rollover。R07 不直接 next，不得重复动作、finalize 或上层 next 请求。第 100 人后的 F5、重筛与首位点击保持原流程。

safe/full 在每槽位完整处理后的优先级为：

```text
1. user_interrupted / runtime_expired
2. 技术失败或 Store 失败
3. 已确认规则命中 → legacy 规则完成，dynamic_end_reason=null
4. 当前已成功保存第 8 槽 → max_screen_limit
5. confirmed scroll_bottom
6. full confirmed no_new_text
7. continue
```

同一槽位不能产生两个正常原因。off/shadow 不执行第 4—6 项 R07 控制，只保留 legacy 控制。

| 决议 | 冻结内容 |
|---|---|
| B-01 | 只改有关键词 OCR 路径；无关键词分支不变。 |
| B-02 | 一次 next 是一次上层候选人切换请求；继续复用 `confirm_candidate_switch()`，其最多两次物理按键恢复不改。 |
| B-03 | off/shadow 保留 legacy 结束语义；规则完成与可空 R07 dynamic end reason 分离。 |
| B-04 | 各屏照现有 R03—R06/Store 语义执行并保存，不采用事务或 rollback。 |
| B-05 | batch rollover 不变；R07 返回上层。 |
| B-06 | 仅 synthetic 实现与自动化测试获批；真实页面/record/生产启用未获批。 |

## 11. Change 1—7

1. **基线与集成点复核**：只读代码/测试，创建且只创建 `docs/R07-change1-baseline-report.md`，记录实际 branch/HEAD、git 状态、扫描入口、record/build/save 顺序、首屏 rule 现状、R03—R06 位置、测试基线、预计文件和与设计一致性；允许 checkpoint commit `test(ocr): establish R07 implementation baseline` 或仓库等价消息。
2. **最小 Schema、模式、状态与计数**：支持可空 dynamic end reason、规则完成分离、nullable miss/完整性字段、Store save-status 反馈；不改变扫描行为。
3. **单次记录与位置分类**：实现 capture→rule→build/R03—R06→classify→附加→save→反馈；每屏 build/save 一次；删除 `position_observation`。
4. **first-same 恢复与 bottom**：实现第 7 节的额度、confirmation 提升、8 槽上限与再次 same 继续规则；默认 shadow。
5. **shadow 接入与漏采**：首屏 rule 字段完整；规则命中仍 legacy 早停且 reason null；nullable miss 正确；effect sequence 零增量。
6. **safe/full 返回**：规则命中优先 legacy；bottom/no-new 仅未命中时控制；同一扫描出口；关键 Store 失败不正常结束。
7. **Replay、兼容与收口**：支持 legacy rule completion、空 R07 reason、nullable miss/完整性字段和离线不确认 bottom；Store/JSONL、全量回归、既有 benchmark、性能记录、隐私、Windows mock、macOS 纯逻辑及实施报告；不做 Sidecar 或独立最终 Acceptance。

后续 Terra 会话按 Change 1→7 连续实施，每项定向测试及 checkpoint commit 后自动进入下一项；全部完成后由独立会话集中验收/修复。本次文档修订不创建 Change 1 report、不进入 Change 1、不 commit。

## 12. 验收重点与本阶段声明

测试必须覆盖四模式规则命中早停/确认次数/空 dynamic reason/一次动作；单次 build/save、同一 record 的 position 字段、Store bool 反馈；confirmation same 不占槽、changed 占下一槽、第 8 槽不恢复；恢复后再次 same 不二次恢复且继续；不重跑 P0 或 R01；nullable miss 的 true/false/null 与预测后规则命中；off/shadow Store 失败零新增控制、safe/full 关键证据 Store failure；动态返回后上层仅一次、R07 不 direct next、batch 与无关键词不变；旧 schema、无 UI Replay、ESC/runtime、隐私及全量回归。

本阶段仅修改两份 R07 设计文档；未修改生产/测试/配置/schema/运行数据，未创建 Change 1 report，未进入 Change 1，未 commit、push、tag 或 Release。
