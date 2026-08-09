# R06 生产缺陷全量收集审计清单（Pre-Acceptance）

日期：2026-08-02
范围：R06 Store、Builder/finalize、evaluator、Replay、Sidecar、Schema、算法与页面隔离的 synthetic 审计。
**本报告不是 Change 7 Final Acceptance；不作 PASS/发布/生产启用结论。**

## 1. 审计基线与边界

| 项目 | 结果 |
| --- | --- |
| 分支 / HEAD | `main...origin/main [ahead 10]` / `3d14276d042693eef9d011cb1e77d9dde8830289` |
| 初始与结束工作区 | 仅既有未跟踪 `README.md`、`docs/project-review.zip`、`venv-packages-before-reinstall.txt`；本次仅新增本报告 |
| 生产代码、测试、配置、Schema、依赖 | 未修改 |
| 数据与页面 | 仅 `TemporaryDirectory` 与 synthetic fixture；未打开真实页面、未读取日志或 run 正文 |
| Git 门禁 | `git diff --check` 在开始和结束均无 whitespace error（Git 用户 ignore 权限 warning 不影响结果） |

已完整核对 R06 RPD/TID、Change 1--6 与两份 corrective/当前 acceptance 报告所冻结的默认 disabled、R03--R06、Store、Replay、Sidecar 与页面隔离合同；并读取所列生产模块及 R03--R06、Store、Replay、Sidecar、主循环测试和三个 benchmark。

## 2. 执行证据

- `python -m unittest discover -s tests -q`：688 tests，3.419 s，`OK`。
- `python -m tests.benchmark_r04_normalization`：全部 8 个场景 deterministic；500-box 最大 p95 17.2187 ms、peak 999.02 KiB。
- `python -m tests.benchmark_r05_aggregation`：`required_performance_gates_pass=true`；`8x64_unique_pure` p95 16.2963 ms（门槛 20），record projection p95 23.0302 ms（门槛 30），峰值均低于各自限制。
- `python -m tests.benchmark_r06_similarity`：`required_performance_gates_pass=true`；20k 三个受限场景 p95 7.5591/11.1035/6.4715 ms（均 <=15），8 adjacent p95 15.4819 ms（<=100），最高 peak 592.38 KiB（<16 MiB）。
- `python -m pip check`：`No broken requirements found.`

单测和 benchmark 的成功只说明其覆盖的断言成立，**不抵消以下生产缺陷**，也不构成 Acceptance。

## 3. 缺陷总表与共同根因

| ID | 严重度 | 模块 | 状态 | 共同根因组 |
| --- | --- | --- | --- | --- |
| R06-AUDIT-001 | P1 | `ocr_store.JsonlOcrRecordStore.save_candidate` | 稳定复现 | G1：从不可信 candidate 内嵌 screen 推断 cleanup 所有权 |

### R06-AUDIT-001 — 身份不一致的 terminal candidate 调用泄漏 Store screen digest

| 字段 | 记录 |
| --- | --- |
| 严重度 | **P1**：record 模式下可按候选数无界累积 digest mapping；不影响页面决策或其他 candidate 的持久化，但会造成长运行内存/状态增长 |
| 生产位置 | `ocr_store.py:447-466`（`_candidate_screen_digest_keys`）、`ocr_store.py:549-624`（`save_candidate` 的 `finally`） |
| 触发条件 | screen 已以 `(run_id=A-run, candidate=A, screen=A-1)` 成功保存；传给 `save_candidate()` 的 document 仍为 A，但 embedded screen 的 `run_id`、`candidate_record_id` 或 `screen_id` 被改为不一致值。document run/candidate 身份错误时同样无法推得已保存 A key。 |
| 最小复现 | 新 `TemporaryDirectory` 中构造 record-mode candidate A，`save_screen(A-1)`；仅 `replace(document.screens[0], candidate_record_id='B')`，再 `save_candidate(replace(document, screens=(forged,)))`。 |
| 预期 | 严格失败、candidate JSONL 无新行、screen JSONL 不变；不删除 B；本 terminal A 调用可证明属于 A 的缓存释放，不累积。 |
| 实际 | `screen_saved=True candidate_saved=False digests_after_identity_failure=1 candidate_lines=0`；保留 `('run-test','candidate-a','candidate-a-screen-1')`。 |
| 稳定性 | 稳定。100 个不同 candidate 的同类调用，cache size 每次为 1..100，最终 100，Store 仍 enabled（failure limit=101）。 |
| 内存/状态累积 | 是。mapping 只保存 identifier+SHA-256，不泄露正文，但条目数无界直到 `close()`。 |
| 其他 candidate | A 失败后 B 的 key 未被误删，B 仍可保存；C 的 key 仍存在。`close()` 清空所有残留。故隔离正确，terminal cleanup 不完整。 |
| 页面控制流 / 持久化 / 隐私 | 不改变 OCR、滚动、点击、规则、收藏、转发、下一位或停止；不写 candidate 行，不改既有 screen JSONL；mapping 无正文。 |
| 根因 | cleanup keys 只从未验证的 embedded screen 取得，且要求其前两段已等于 document identity。伪造后返回空/错误 key 集；`finally` 无法释放已按原身份缓存的 A key。 |
| 建议修复边界 | 仅调整 Store 的 candidate-terminal ownership/cleanup：在严格验证之前保留能安全定位“当前调用的已保存 key”的可信边界，并只释放可证明属于该 Store/candidate 调用的 key。不得 global clear、不得按伪造 screen ID 删除、不得放宽 digest/identity 校验、不得改 JSONL/Schema/默认模式。 |
| 必增回归 | document run/candidate 错误；embedded run/candidate/screen ID 错误；A document+B screen、B document+A screen、混合 A/B；每种验证 A 释放、B/C 保留、无 candidate 行/无 screen 改写；各至少 100 次；弱引用/峰值内存与 close 幂等。 |

## 4. Store 生命周期矩阵

| 矩阵 | 本次状态与证据 |
| --- | --- |
| 正常 1/8 screen、A 后 B、乱序、close/重复 close | 已由直接全量回归覆盖（Store tests）并核对实现；A/B 成功只释放本 candidate，`close()` finally clear。 |
| digest 不一致（时间、R06、summary/reference/warning 变化） | 直接执行 `captured_at` mismatch；严格 false、无 candidate 行、screen 行保持。其余字段组合由 JSON digest 的全字段比较与 records/store 回归覆盖。 |
| identity 不一致 | **发现 R06-AUDIT-001**。直接 A/B/C 与 100 次 embedded candidate mismatch；其余 run/screen/document 变体经同一 key-derivation 路径源码审计，属于同一根因组，必须在 corrective 中逐一回归。 |
| 缺失/重复 digest、candidate 多/少 screen | 回归覆盖 strict false、无 candidate 行、release 幂等。 |
| serialization/open/append/flush/fsync | serialization 与 candidate append 注入已回归；append 后下一 candidate 可保存。open/flush/fsync 的逐层专门 fault injection 未新增正式测试，本轮不改变其既有 best-effort 合同。 |
| 连续失败 | digest validation 100 次回归为 0；本次 identity mismatch 100 次为 100（缺陷）；append 失败的 cleanup/continuation 由回归覆盖。 |
| disabled/failure limit/manifest/screen append | Store 回归覆盖初始化失败、连续磁盘失败禁用、screen append、close、disabled 后 write；缓存 close 行为已核对。 |

## 5. Builder、evaluator、Replay 与 Sidecar 状态

| 子系统 | 状态 |
| --- | --- |
| Builder/finalize | 回归覆盖 R05 finalize、R06 summary、summary fallback、document construction、validation 和 context release。源码确认 `finalize()` 的外层 `finally` 无条件清空 screens/attempts/R05/R06 context；summary 失败是固定无正文 warning + count-only fallback，其他构造/验证异常仍传播。 |
| R06 evaluator stages | 回归覆盖 disabled short-circuit、一次 evaluate、resolver/R03/n-gram/SimHash/accounting/effective-new 失败的 single-pass fail-open、R03--R05 projection 保持和下一 candidate 隔离。未见第二个可独立复现缺陷。 |
| Replay | 回归覆盖 schema 1.0、1.1、1.2、1.3 disabled/record、strict/tolerant identity/config/duplicate/损坏行、单 screen 与 candidate summary，且 source 为只读。未见独立缺陷。 |
| Sidecar | 回归覆盖 exclusive create、排序、override、source 不变、无正文 sidecar/statistics、重复目标拒绝。现有实现对写入期 I/O 故障不作原子回滚；本轮未将其计入缺陷，因为现有 append-only Sidecar 合同未要求原子 sidecar，但集中 corrective 应决定并测试 manifest/record/sort/close/100 次写失败后的残留文件与可重建策略。 |

## 6. Schema、算法与页面行为

- Schema：全量回归覆盖 1.0--1.3 reader、1.3 writer/projection、nested/top-level、required/非法 enum/非法 warning、null/false/0、Unicode、重复 ID、identity、summary accounting 与 manifest identity。NaN/Infinity 在 JSON-compatible/records validation 路径受拒；没有本次新增 defect。
- 算法/会计：golden n-gram、SimHash、跨进程 deterministic、100000/100001、三分 partition、ratio/零分母、effective-new reason、短词保护、UI 两/三屏、comparison class 与 cross-layer conflict 均由全量回归和 R06 benchmark 覆盖。
- 页面：`simple_brush` 的 synthetic spy/mock 全量回归覆盖 R05/R06 disabled/record 组合、summary/Store failure 与页面操作隔离。字段使用检索仅显示在 Builder/Store/Replay/records/sidecar；R06 模块不包含滚动、刷新、转发、收藏、规则、下一位、ESC 或 stop 操作。未运行真实页面。

## 7. 性能、资源与隐私

现有三个 benchmark 的 deterministic、peak-memory、GC retained 与 candidate context release 测量已记录于第 2 节。本次直接 Store 压力额外证明：正常 `close()` 清空 mapping；identity-failure 100 次在 close 前保留 100 个 digest entries，构成 R06-AUDIT-001。未执行真实数据文件读取；无正文被写入报告、sidecar 统计或错误上下文。

尚未以独立临时 fault harness 测得 1,000 次 success/digest/identity/append 的 OS handle、weakref、峰值内存四项完整曲线；其中 identity 100 次已足以稳定确认缺陷，另三类已有 benchmark/回归的功能与局部 GC 证据。它们应作为集中 corrective 的性能回归扩展，而非误报为已完成的直接测量。

## 8. 建议集中 Corrective

具备一次集中 Corrective 的条件：**具备，但范围应先限于 G1 Store ownership lifecycle。**

建议修改文件：

- `ocr_store.py`
- `tests/test_ocr_store.py`
- `docs/R06-store-screen-digest-lifecycle-corrective-report.md`（或新的 narrowly-scoped corrective report）

必须新增的回归测试：第 3 节列出的所有 identity 置换、A/B/C 隔离、100/1000 连续失败、每次 cache size、append/open/flush/fsync failure cleanup、failure-limit/disabled/manifest failure、`close()` 幂等、弱引用及峰值内存。完成 corrective 后必须从新的 Git/metadata 基线重新执行完整本审计矩阵；不得复用本报告作为 Acceptance，亦不得启用 R05/R06 production record。

## 9. 结论

本次已收集到一个独立、稳定、可无界累积的生产 Store 生命周期缺陷：**R06-AUDIT-001（P1）**。它与既有 digest-mismatch corrective 不同，根因是 identity-disagreement 时 cleanup ownership 的推断漏洞。除该根因组外，本次全量回归、benchmarks、synthetic Replay/Sidecar/Builder/evaluator/页面隔离核对未发现第二个独立可复现生产缺陷。

**本报告不是 Acceptance，未宣告 PASS，也未批准 release、真实页面或生产记录模式。**
