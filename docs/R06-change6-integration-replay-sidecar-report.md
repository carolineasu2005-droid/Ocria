# R06 Change 6 — 集成、Replay 与 Sidecar 报告

## 总体结果

Change 6 已完成。R06 仅在 `similarity_mode="record"` 时被动接入既有 Builder；默认 R05 与 R06 模式仍均为 `disabled`。没有新增 OCR、截图、等待、点击、滚动、页面控制或候选人业务判断。

**R05 formal final Acceptance remains BLOCKED.**

**R05 was accepted for this limited integration through a maintainer waiver.**

**R05 and R06 production defaults remain disabled.**

**Real-page production record activation was not tested or approved.**

## Git 基线与授权

- branch：`main...origin/main [ahead 4]`
- HEAD：`c5ac8dc32e38770f0729f5006ed4f21e072769a7`（R05 Change 6 maintainer waiver）
- R05 implementation：`f02209c`
- R05 performance stability corrective：`ac3d7d4`
- R05 waiver：`c5ac8dc`
- R06 Changes 2—5：`0e0deca`

已完整核验并使用 `docs/R05-change6-prerequisite-maintainer-waiver.md`。R05 的前置条件是通过该维护者豁免满足，而不是通过正式 R05 final Acceptance PASS。豁免只覆盖 synthetic R05/R06 record 集成；未变更 R05 的 20 ms 冻结门槛，未启用 production record，也未运行真实页面。

## 修改文件

- `ocr_candidate.py`：R05 后唯一的 R06 Builder 接入、candidate-local context 与 summary。
- `ocr_similarity.py`：在线/Replay 共用的组合 evaluator、固定失败结果、空 summary。
- `ocr_store.py`：manifest identity、screen/candidate identity 与 JSONL 等价校验。
- `ocr_replay.py`：R06 replay、旧 Schema 阶段推进、strict/tolerant 结果。
- `ocr_similarity_sidecar.py`：新建 exclusive-create sidecar 与脱敏统计。
- `simple_brush.py`：只透传静态 R06 mode/config；默认 disabled。
- `tests/test_ocr_similarity.py`、`tests/test_ocr_replay.py`、`tests/benchmark_r06_similarity.py`：synthetic 集成、失败、Replay、sidecar、性能覆盖。

未修改 `ocr_detector.py`、`ocr_normalization.py`、`ocr_aggregation.py` 或 R05 配置/门槛；`ocr_records.py` 本 Change 未修改。

## 在线顺序、disabled 与 fail-open

`CandidateOcrBuilder.build_screen_record()` 的唯一调用顺序为 R03/R04 已有结果 → R05 projection（record 时）→ R06 resolve/evaluate 一次 → 同一 `OcrScreenRecord` nested result/top-level compatibility projection → append → 原有的一次 `save_screen()`。`add_screen()` 为 Replay 使用同一顺序。

disabled 在构造 `CandidateSimilarityEvaluator` 前短路：不建立 context、不运行 resolver/n-gram/SimHash/accounting/effective-new、不写 sidecar；screen result 与 candidate summary 均为 null，manifest 只记录 `similarity_mode=disabled`，其余 R06 identity 为 null。

每个 record-mode screen 调用 evaluator 不超过一次；异常不重试，生成只含 `evaluation_failed` 的脱敏 failed result，保留 R03/R04/R05。reference、n-gram、SimHash、R05 accounting 与 effective-new 均在该 fail-open 边界内。finalize 释放 R05/R06 context；Store 失败沿用既有 best-effort 行为，不改变页面流。

## Reference、summary、identity 与 Store

reference resolution 仍按 persisted identity：首个正式屏为 `no_reference`；后续正式屏只接受同 run/candidate、唯一 `screen_index - 1` 正式屏；不依赖 JSONL 行、列表顺序或 Store 返回顺序。结果持久化 `reference_screen_id/index/capture_type/source`，Replay 重新解析并逐字段比较。

每 candidate 的 context 最多保留八个正式屏，按 exact comparison text 建 UI evidence 索引，不跨 candidate 共享，finalize/异常时清理。summary 只由 `screens[*].similarity_result` 纯重算；record 模式零 screen 保存合法空 summary。

record-mode manifest 保存完整 R06 snapshot、digest、version、business short terms identity 与三个 frozen confidence 参数。Store 验证 screen result、candidate summary、manifest identity；同时缓存已写 screen 的 JSON digest，以验证 candidate JSONL 内嵌 screen 与 screens JSONL 逐字段相同，然后立即释放该 digest。

## Replay 与 Sidecar

`replay_candidate_similarity()` 与在线共享 resolver、`CandidateSimilarityEvaluator`、R05 accounting、effective-new、summary code：

- 1.3 record 从 manifest 恢复 config 并要求逐字段相等；1.3 disabled 不构造 evaluator。
- 1.2 要求 caller config，并只消费已保存的 R05 projection。
- 1.1 在内存中先执行 R05；1.0 先 R04、再 R05，未提供历史 config 不猜测。
- strict 返回脱敏 `OcrReplayError`；tolerant 返回结构化 issue，不修改 source。

`ocr_similarity_sidecar.py` 默认创建 `<run_dir>/r06-sidecar-<digest>.jsonl`；使用 exclusive create，首行是 sidecar manifest，后续按 candidate sequence、formal screen index、screen ID 排序。sidecar 仅含 source identity/digest、reference identity、版本与 R06 result；不复制 OCR 正文、联系方式或 bbox。override 只生成新 sidecar digest，不写回 source manifest/JSONL。`similarity_statistics()` 仅产生 status/class/effective/reason/warning/score/ratio 分布和样本数。

## 测试、性能与回归

全部使用 synthetic fixtures 与 `TemporaryDirectory`：

- R06 定向套件：365 PASS。
- R05 回归套件：102 PASS。
- 全量：678 PASS。
- R04 benchmark：PASS、所有场景 deterministic。
- R05 benchmark：`required_performance_gates_pass=true`；本次 `8x64_unique_pure p95=15.8355 ms`（20 ms）、record projection p95=20.5388 ms（30 ms），无新非豁免失败。该当前测量不改变历史正式 Acceptance 的 BLOCKED 状态。
- R06 benchmark：20k exact/50%-changed/repeated p95 分别为 7.3869/11.7341/6.7163 ms（均 ≤15 ms）；8 adjacent pairs p95=14.4171 ms（≤100 ms）；最高附加峰值 592.38 KiB（≤16 MiB）。
- 组合 benchmark（p50/p95 ms）：R05-only 1.7803/2.6072，R06-only 3.0995/3.8799，R05+R06 Builder 5.3002/6.1061，双 disabled 0.0393/0.1171，Replay 3.3966/4.0172，sidecar 14.6469/17.7031。没有重复调用或非线性八屏增长证据。
- `compileall` 与 `pip check`：PASS。
- `git diff --check`：PASS。

定向测试涵盖 disabled 不构造 evaluator、每 screen 一次、首屏/连续 reference、summary、Store/JSONL、online/Replay equality、strict/tolerant、1.0 阶段推进、sidecar exclusive create/排序/override/无正文、统计无正文，以及 evaluator 注入异常仍保留 R05 projection。原有 stage0/simple_brush 测试在五种既有页面流路径下通过；代码审计确认 R06 字段没有进入滚动、到底、切换候选人、收藏、转发或关键词规则。

## 隐私、平台与 Git 状态

未读取 `logs/simple_brush.log` 或 `data/ocr_runs` 正文。测试前后仅做 inventory；`logs/simple_brush.log` 保持 7,372,745 bytes、mtime 不变、SHA-256 为 `1BE253B07B246AA1B9F3F207F5C22876FA8116A13DA13959221ECCC2AC62AF96`；`data/ocr_runs` inventory 的四个空 JSON/JSONL 文件保持相同 size/mtime/SHA-256。

Windows 真实页面：**NOT RUN**。macOS：未运行真实页面；纯 Python 单元/Replay/sidecar 实现保持平台中立。当前 tracked 修改均归属 Change 6；既有未跟踪 `README.md`、`docs/project-review.zip`、`venv-packages-before-reinstall.txt` 未读取、未修改。未执行 git add、commit、push、tag 或 release。

## 是否允许进入 Change 7

**允许进入 Change 7 审计。** 前提仍是维护者审阅本 Change 6；Change 7 不得将 R05 formal final Acceptance 从 BLOCKED 改写为 PASS，也不得启用 R05/R06 production record 或真实页面测试。
