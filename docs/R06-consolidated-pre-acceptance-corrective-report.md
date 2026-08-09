# R06 Consolidated Pre-Acceptance Corrective

日期：2026-08-02
范围：集中修复 pre-acceptance inventory 的生产缺陷；不是 Change 7。
**本报告不修改 `R06-ocr-page-similarity-effective-new-content-acceptance-report.md` 的 BLOCKED 结论，不启用 production record。**

## 1. 输入、缺陷映射与完成状态

缺陷清单版本：`docs/R06-pre-acceptance-defect-inventory-report.md`，审计基线 `3d14276`。

| 缺陷 ID | 根因组 | 修改位置 | 稳定回归 | 完成 |
| --- | --- | --- | --- | --- |
| R06-AUDIT-001（P1） | G1：terminal cleanup 由未验证 embedded screen 推断 ownership | `ocr_store.py`、`simple_brush.py` | `test_r06_audit_001_identity_matrix_releases_trusted_owner_only`；`test_r06_audit_001_thousand_terminal_paths_release_all_store_state` | 完成 |

缺陷清单未列出其他 P0/P1。集中核查 Builder/finalize、evaluator fail-open、Replay、Sidecar、Schema、context release 与页面隔离的既有覆盖后，未发现第二个可独立复现的生产缺陷；未对这些模块作无关修改。

## 2. 根因与修复

旧实现只从 `CandidateOcrDocument.screens` 推出要释放的 digest keys。embedded screen 尚未通过 strict identity/JSONL validation：一旦其 run、candidate 或 screen identity 被改变，正确的已保存 A key 可能无法找到；另一个相邻缺口是 document B 加 embedded screen A 可在旧验证中缺少 document--screen candidate identity gate。

修复建立统一 Store-owned 生命周期模型：

```text
screen digest key:      (run_id, candidate_record_id, screen_id)
candidate ownership:    (run_id, candidate_record_id)
ownership index:        owner -> set(saved screen digest keys)
```

`save_screen()` 仅在 screen JSONL 成功 append 后，同时写入 digest mapping 与 ownership index。`save_candidate()` 在进入验证前取得 terminal owner：生产主循环从尚未 finalize 前的 Builder 传入 `owner_candidate_record_id`；兼容 fallback 只接受 document 与所有 embedded screens 已一致的情况。它绝不由不可信 embedded screen 选择 owner。

无论 strict validation、digest comparison 或 candidate append 的结果如何，`finally` 都以 Store ownership index `pop(owner)`，然后只释放该 owner 的全部 digest keys。`close()` 清空两个内存映射。没有全局 clear 掩盖单 candidate 失败；没有放宽 Schema、identity 或 JSONL digest 验证。

同时新增 document--embedded-screen `run_id` / `candidate_record_id` strict validation。故 document B + screen A、A/B mixed screen 均返回 `False`、不写 candidate、不改 screen JSONL。

## 3. 生命周期覆盖与测试映射

| 路径 | 回归证据 |
| --- | --- |
| 1/8 screens、success、A 后 B、乱序 | 既有 Store success/8-screen tests；owner index 只释放当前 owner |
| digest mismatch、缺失 digest、duplicate ID | 既有 validation/missing/duplicate tests；terminal owner cleanup 保持为零 |
| document run/candidate mismatch | `R06-AUDIT-001` identity matrix，可信 Builder owner A 被释放 |
| embedded run/candidate/screen-ID mismatch | 同一 identity matrix，严格 false、A 释放、B/C 不受影响 |
| A/B mixed screen | 同一 identity matrix，strict document--screen identity gate |
| serialization / candidate append failure | 既有 serialization/append test与 1000 append-failure stress；无 partial candidate 行、后续可继续 |
| failure limit / Store disabled | 既有 Store disk-failure/disabled tests；新 stress 使用 limit 1001 验证每种连续失败结束前仍 enabled |
| close before finalize / repeated close | 既有 close test扩展断言 digest 与 ownership index 均为空 |
| 主循环调用链 | `simple_brush.finalize_current_candidate_recording()` 传递 Builder candidate identity；summary fail-open integration assertion 覆盖该参数且无页面动作 |

## 4. 1000 次压力与资源结果

新增单一 synthetic `TemporaryDirectory` 测试执行以下各 1000 次：

| 场景 | 结果 |
| --- | --- |
| Store success（同时为 1000 candidate finalize） | 每次 candidate 写入成功；digest cache=0、ownership index=0 |
| digest mismatch | 每次 strict false、无 candidate 行；两项内存状态=0 |
| embedded identity mismatch | 每次 strict false、无跨 candidate key；两项内存状态=0 |
| candidate append failure | 每次 best-effort false、无 candidate 行；两项内存状态=0 |

该压力测试运行 9.508 s。所有 fixture 都在退出时关闭 Store；mapping 只保存 key/digest，且每一轮断言清空，故无随 candidate 数量线性残留。既有 Builder corrective 的 context clear/weakref 回归仍覆盖 finalize 的 aggregator/evaluator/screen release；本次未改变其实现。

## 5. 未改变的模块与页面隔离

Builder/finalize、evaluator、Replay、Sidecar、Schema、R03/R04/R05 算法、阈值、默认模式与页面动作均未修改。`simple_brush` 唯一行为变化是把已有 Builder identity 作为 Store cleanup context 传递；它不增加 OCR、截图、等待、滚动、刷新、规则、点击、收藏、转发、下一位、ESC 或计时调用。

R05 default=`disabled`，R06 default=`disabled`；production record 仍 **NOT APPROVED**。真实页面 **NOT RUN**，真实候选人数据 **NOT USED**。

## 6. 验证

本 corrective 运行的命令及结果：

- 定向 Store/Stage0/main-loop suites：291 tests，OK。
- 新 identity matrix：6 个身份/混合变体，OK。
- 新 4×1000 terminal-path stress：OK。
- 完整 `unittest discover -s tests -q`：690 tests，13.397 s，OK。
- R04 benchmark：所有场景 deterministic；500-box 最大 p95 18.2287 ms、peak 999.02 KiB。
- R05 benchmark：`required_performance_gates_pass=true`、`contract_blockers=[]`。
- R06 benchmark：`required_performance_gates_pass=true`；三个 20k 受限场景 p95 8.5394/12.2157/6.7245 ms（均 <=15），eight-adjacent p95 15.3173 ms（<=100），最高 peak 592.38 KiB（<16 MiB）。
- `python -m pip check`：`No broken requirements found.`；`git diff --check`：通过。

## 7. Git、隐私、未解决项与后续

修改生产文件：`ocr_store.py`、`simple_brush.py`。修改测试：`tests/test_ocr_store.py`、`tests/test_ocr_stage0_integration.py`、`tests/test_simple_brush_ocr.py`。新增本报告。没有 add、commit、push、tag 或 release。

两个报告文件受仓库既有 `*.md` ignore 规则影响，会以 ignored untracked 文件存在；未修改 ignore 规则。

未解决的生产缺陷：无（inventory 中的唯一 P1 已修复并回归）。尚未作 Change 7；建议在 maintainer 审阅本集中 corrective 后，以全新 Git/metadata 基线进行一次独立最终 Change 7。该建议不是 Acceptance PASS，也不授权 production activation。

## 8. R06-AUDIT-002 trusted owner binding addendum

Change 7 subsequently found `R06-AUDIT-002`: with the new Store-owned index,
`save_candidate(document_B, owner_candidate_record_id="candidate-a")` accepted
and wrote B, released A, and retained B's digest/index state. The direct cause
was that an explicit owner selected terminal cleanup but was not bound to the
candidate document before candidate serialization or append.

The corrective adds a pre-persistence validation inside `save_candidate()`'s
existing `try/finally` boundary. When an owner is supplied it must equal
`document.candidate_record_id`; a mismatch raises the same sanitized strict
identity failure, returns `False`, and reaches the existing `finally`. Thus A
is released while B's digest/index remains untouched. The fallback remains
unchanged: without an explicit owner it can derive one only from a Store-run
document whose embedded screens all agree with its run/candidate identity.

New synthetic regressions prove:

- A-owner/B-document and the reverse B-owner/A-document reject before
  candidate serialization or candidate append; screens JSONL is unchanged and
  cleanup executes once for the supplied owner.
- A/B/C isolation releases only A, preserves B/C, then lets B and C finalize
  normally.
- 1,000 distinct A/B mismatches leave no A state, do not delete B, and let all
  B documents finalize; final cache and ownership index are empty and `close()`
  remains idempotent.
- The existing `R06-AUDIT-001` identity matrix and 4 x 1000
  success/digest/identity/append stress remain covered without regression.
- The sole production call in `simple_brush.py` passes
  `owner_candidate_record_id=builder.candidate_record_id`; normal and
  summary-fail-open test spies confirm the owner equals the finalized document
  identity.

Validation after this addendum: the specified Store/Stage0/simple-brush suites
and full discovery passed (694 tests); R04/R05/R06 benchmarks passed their
frozen gates; `compileall` and `pip check` passed. `git diff --check` passed.
The pre-existing staged forms of the two corrective reports still make
`git diff --cached --check` fail on four trailing-whitespace locations. The
working copy is whitespace-clean, so `git diff --check` and
`git diff HEAD --check` pass. This task forbids `git add`, so the index was not
modified; the cached check will pass after a maintainer stages the corrected
report text.

R06 Change 7 final Acceptance remains **BLOCKED** pending a new independent
Acceptance rerun from a clean, committed baseline. R05/R06 defaults remain
disabled; production record and real-page activation remain **NOT APPROVED**.
