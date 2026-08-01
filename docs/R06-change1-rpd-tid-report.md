# R06 Change 1 — 仓库调查、前置能力验证与 RPD/TID 报告

## 1. 总体结果

R06 Change 1 已完成仓库勘察、前置能力验证、测试/benchmark 基线和正式 RPD/TID 编写。本 Change 没有实施 R06 生产代码、测试代码、Schema、算法、配置、依赖、构建、workflow 或主流程接入，也没有运行真实 BOSS 页面。

结论：**Change 1 设计门禁可交付，Change 2 不自动开始。**

没有发现 exact hash 冲突实现、R04 comparison text 不稳定、R05 三分分类无权威来源、旧 Schema 不可读或测试污染真实日志/data。发现的前置风险已在第 16 节列出，其中 R05 生产 record 尚未获准是未来 R06 在线激活的明确阻塞，不妨碍本次设计文档完成。

交付文档：

- `docs/RPD-R06-ocr-page-similarity-effective-new-content.md`
- `docs/TID-R06-ocr-page-similarity-effective-new-content.md`
- `docs/R06-change1-rpd-tid-report.md`

## 2. Git 基线

开始前按要求执行：

```text
git status -sb
git status --short
git rev-parse HEAD
git log -5 --oneline --decorate
git diff --stat
git diff --check
```

基线：

```text
branch: main...origin/main
HEAD: cd5d96c731caed07f7b841c437b2ee9f5086ffd0

cd5d96c (HEAD -> main, origin/main, origin/HEAD) docs(ocr): define R05 multiscreen aggregation
6987b19 feat(ocr): implement R04 normalization and legacy shadow
54ae064 fix(ocr): reset candidate recording after load recovery
b36009b docs: add OCR design and project review records
ba0eb4d feat(ocr): add stage 0 records and JSONL persistence
```

开始前已有 tracked 修改：

```text
ocr_candidate.py
ocr_records.py
ocr_replay.py
ocr_store.py
simple_brush.py
tests/test_ocr_candidate.py
tests/test_ocr_normalization.py
tests/test_ocr_records.py
tests/test_ocr_replay.py
tests/test_ocr_store.py
```

开始前已有 untracked：

```text
README.md
docs/project-review.zip
ocr_aggregation.py
tests/benchmark_r05_aggregation.py
tests/test_ocr_aggregation.py
venv-packages-before-reinstall.txt
```

只读 diff 核对表明这些 tracked 修改与 `ocr_aggregation.py`、R05 tests/benchmark 共同构成连贯的 R05 Schema 1.2、聚合、Store、Replay 和接入实现，主题与 HEAD 的 R05 设计一致，可明确归属为既有 R05 工作，不是本 Change 产生的杂散修改。所有这些文件均保持不动。

`git diff --check` 通过，仅报告 Git 的 LF→CRLF 提示和用户级 ignore 文件权限 warning；没有 whitespace error。

## 3. 调查文件

主要读取：

```text
ocr_detector.py
ocr_text.py
ocr_normalization.py
ocr_records.py
ocr_candidate.py
ocr_aggregation.py
ocr_store.py
ocr_replay.py
simple_brush.py

tests/test_ocr_detector.py
tests/test_ocr_normalization.py
tests/test_ocr_records.py
tests/test_ocr_candidate.py
tests/test_ocr_aggregation.py
tests/test_ocr_store.py
tests/test_ocr_replay.py
tests/test_ocr_stage0_integration.py
tests/test_ocr_text.py
tests/test_simple_brush_ocr.py
tests/benchmark_r04_normalization.py
tests/benchmark_r05_aggregation.py

docs/RPD-R03-basic-ocr-page-fingerprint.md
docs/TID-R03-basic-ocr-page-fingerprint.md
docs/RPD-R04-ocr-text-normalization-and-raw-evidence.md
docs/TID-R04-ocr-text-normalization-and-raw-evidence.md
docs/RPD-R05-ocr-multiscreen-incremental-aggregation.md
docs/TID-R05-ocr-multiscreen-incremental-aggregation.md
docs/R05-change1-baseline-report.md
docs/R05-ocr-multiscreen-incremental-aggregation-acceptance-report.md
docs/R05-fail-open-contract-corrective-report.md
docs/R05-performance-benchmark-corrective-report.md
```

仓库没有 `AGENTS.md`。

## 4. 阶段0结论

| 对象/能力 | 真实位置 | 结论 |
|---|---|---|
| `OcrBox` | `ocr_records.py:402` | 保留 box raw text、confidence、bbox、original/screen index |
| `OcrTextSegment` | `ocr_records.py:418` | R04 视觉行，ID/order/text/box 来源可追溯 |
| `OcrScreenRecord` | `ocr_records.py:758` | screen 主记录；已有 R03/R04/R05 和 R06 占位字段 |
| `CandidateOcrDocument` | `ocr_records.py:1414` | 内嵌 screens 和 R05 candidate document |
| `RunManifest` | `ocr_records.py:1660` | run/schema/R04/R05 identity 与 data file map |
| `OcrRecordStore` | `ocr_store.py:59` | `save_screen/save_candidate/save_error/close` |
| `JsonlOcrRecordStore` | `ocr_store.py:80` | append-only screen/candidate/error；manifest 原子写 |
| JSONL reader | `OcrRunReader`，`ocr_replay.py:94` | strict/tolerant、逐行 version validation/filter |
| 离线 replay | `load_ocr_run()`、`replay_screen_normalization()`、`replay_candidate_aggregation()` | 原始装载与 R04/R05 纯重算分离 |

在线调用链是 detector 完成一次 observation → builder 构建最终 screen → Store 保存一次 → candidate finalize 保存 document。Store 失败为 best-effort，不改变业务动作。

当前工作区 writer Schema 为 `1.2.0`，reader 支持 1.0/1.1/1.2。旧版由 `from_dict()` 显式投影为 R04/R05 `not_attempted/null/empty`，读取兼容稳定。

## 5. R03 结论

唯一权威实现是 `ocr_detector.py`：

- version：`r03-v1`；
- builder：`build_screen_fingerprint()`；
- hash helper：`sha256_normalized_text()`；
- 算法：SHA-256(UTF-8 R03 normalized text)，小写 64 hex；
- compare：`compare_screen_fingerprints()`。

所有生产 fingerprint 都从 `OCRKeywordDetector.capture_observation()` 生成。候选人切换和稳定性检查复用同一 compare helper；screen record 保存同一 observation 的 hash/version。没有两套冲突 exact hash。

加载检测本身不使用 hash，只用 OCR box/text 长度；切换验证复用 hash。

关键差异：R03 hash 输入是 R03 自己的 reading order + item whitespace normalized text，**不是** R04 `comparison_text`。TID 已冻结最小只读 adapter：R06 只校验/消费已保存 hash，不修改、重算或覆盖 R03。

## 6. R04 结论

`ocr_normalization.py` 提供稳定三层文本、配置 identity、几何 reading order、视觉行、duplicate evidence 和保护词元：

- raw evidence 保持原样；
- `normalized_text`：NFC、保守 whitespace 处理和视觉行；
- `comparison_text`：NFKC、lower、去 Unicode whitespace，保留标点、符号、UI 和短词；
- `normalization_version=r04-v1`、config `r04-config-v1` + digest；
- 同屏重复框仅在文本+几何证据满足时从 derived text 抑制；raw box 不删除；
- `normalization_record_fields()` 生成 `{screen_id}:line:{order}` segment，并保存 `ocr_box_ids`；
- segment char count 可由 `len(comparison_text)` 稳定复算。

R04 测试和 benchmark 均确定性通过，没有发现 comparison text 不稳定。

## 7. R05 结论

R05 权威分类来源是 `CandidateDocumentAggregator.add_screen()` 返回的 `ScreenAggregationResult`，随后由 `aggregation_screen_record_fields()` 投影到 screen：

- `matched_segment_ids`
- `new_segment_ids`
- `uncertain_segment_ids`
- `match_evidence`
- `overlap_text/new_text` 和 counts

三组 ID 由 `OcrScreenRecord._validate_r05_contract()` 强制互斥、完整覆盖并保持 source order。`aggregation_char_count()` 是 R05 字符计数权威，计算 R04 comparison Unicode code points。`document_segments/document_text` 保存 source occurrence 和 match evidence。版本/config/digest 可从 manifest replay。

失败路径保留当前 segment 并降级 uncertain/partial，属于 fail open。在线 builder 和离线 `replay_candidate_aggregation()` 使用同一 aggregator。

重要状态：生产默认 `R05_AGGREGATION_MODE="disabled"`。已有 R05 Change 7 报告为 blocked，后续 corrective benchmark 已通过，但报告明确未批准生产 record。R06 在线 record 必须等待独立前置批准。

## 8. Accounting 可行性

结论：**可复算，但不能直接使用 R05 字段名做三项相加。**

合法 R05 screen 可按三组 ID 映射回 `record.segments`，对每段调用 `aggregation_char_count(comparison_text)`：

```text
count(matched) + count(new) + count(uncertain)
= count(all current segments)
```

当前 R05 `new_text_char_count` 与 `new_segment_count` 的含义是 `new + uncertain`，而非仅 `new`。R06 必须保存独立 `new_char_count`，并验证：

```text
R05 new_text_char_count
= R06 new_char_count + R06 uncertain_char_count
```

这使 R06 所需会计关系可稳定实现，无需修改 R05 分类或字段语义。

## 9. Reference 关系

当前 screen 字段足以可靠解析正式屏：

- 同 `run_id`、同 `candidate_record_id`；
- 双 gate `capture_type=formal_screen` 且 `is_formal_screen=true`；
- 首屏 index 1 → no_reference；
- 后续屏只找唯一 index-1 正式屏；
- 缺失/重复/冲突 → unavailable。

这不依赖 JSONL 行顺序。

当前 Schema 没有 `reference_screen_id`，因此旧非正式 load retry/switch check/scroll confirmation 不能统一可靠重建。正式 screen 可按唯一 index 重建；非正式 screen 无显式 link 时必须 unavailable。当前 switch check 的 pre-switch baseline 和 post-next observation 位于不同 candidate，R06 candidate isolation 禁止跨候选人猜 reference。

TID 已冻结 1.3 持久化 reference ID、online resolver 和 replay 复核规则。

## 10. Schema 现状与 R06 决策

现有 `OcrScreenRecord` 已有少量 R06 占位：`similarity_hash`、`similarity_score`、`overlap_ratio`、`new_text_ratio`、`has_effective_new_text`、`similarity_version`。它们不足以保存 reference、状态、分子/分母、uncertain ratio、算法明细、effective evidence、class、config 和 warnings。

TID 冻结：

- 目标 Schema `1.3.0`；
- screen 权威 nested `OcrSimilarityResult`；
- candidate `R06CandidateSummary`；
- manifest 完整 mode/version/config/digest/snapshot；
- 旧顶层 placeholder 仅作为 nested result 的兼容投影，不形成双权威；
- reader 保留 1.0—1.2；
- JSON 序列化沿用 dataclass 字段声明顺序。

## 11. RPD 关键决策

- R06 只计算和记录，不控制滚动、候选人或动作。
- exact same 只复用 R03。
- 主相似度基于 R04 comparison character n-gram；SimHash 辅助。
- R05 ID 是 overlap/new/uncertain 权威；分子/分母全部保存。
- uncertain 保守视为可能有效。
- 不建立 UI 文字黑名单。
- 年份、日期、版本、技术/公司/项目/岗位短词受保护。
- comparison class 是中性记录，不等于继续/停止/合格/拒绝。
- online/replay/sidecar 同 evaluator；sidecar 不改源记录。
- R06 failure 保留 R03/R04/R05 并 fail open。
- 明确不实现 R07、AI、SQLite。

## 12. TID 关键决策

| 项目 | 冻结决定 |
|---|---|
| 主 n-gram | char multiset `(2,3,4)`，weights `(0.20,0.30,0.50)`，weighted Dice |
| 空文本 | 双空 1.0、单空 0.0；比例零分母 null |
| 长度保护 | 单侧最多 100,000 codepoints，超限不截断、分数 null |
| SimHash | 64-bit，3-gram，SHA-256 前 8 bytes，Hamming，禁止 Python hash |
| ratio | 三项共同 denominator，容限 `1e-12` |
| high threshold | `0.85`，未校准，只记录/离线分析 |
| UI evidence | 至少 3 正式屏 + exact text + 几何/尺寸稳定 + 无反证 |
| 业务短词版本 | `r06-business-short-v1` |
| evaluator | pure `evaluate_screen_similarity()`；builder 每屏一次 |
| online 接入 | R05 projection 后、builder append/save 前 |
| sidecar | `<run>/r06-sidecar-<digest>.jsonl`，exclusive create，不改源 |
| 初始 mode | `disabled`；record 需 R05 前置和独立批准 |
| 性能门槛 | pair p95 ≤15 ms；8 屏 ≤100 ms；峰值 ≤16 MiB |

## 13. Change 2—7 计划

| Change | 内容 | 主要文件 | 报告 |
|---|---|---|---|
| 2 | Schema、Reference、配置 | `ocr_records.py`、新增 `ocr_similarity.py`、model/similarity tests | `R06-change2-schema-reference-config-report.md` |
| 3 | n-gram、SimHash | `ocr_similarity.py`、新 test/benchmark | `R06-change3-ngram-simhash-report.md` |
| 4 | counts、会计、比例 | similarity/records + tests | `R06-change4-accounting-ratios-report.md` |
| 5 | 有效新增、中性分类 | similarity/records + tests/benchmark | `R06-change5-effective-new-classification-report.md` |
| 6 | online、JSONL、Replay、sidecar、summary | candidate/store/replay/simple_brush/sidecar + integration tests | `R06-change6-integration-replay-sidecar-report.md` |
| 7 | 全量验收 | 仅测试/benchmark/报告；生产缺陷另开 Change | `R06-ocr-page-similarity-effective-new-content-acceptance-report.md` |

每个 Change 的进入条件、禁止事项、测试和退出条件已在 TID 第 17 节逐项冻结。

## 14. 测试基线

所有测试均使用 `F:\BOSSOCR\venv\Scripts\python.exe`，未运行真实页面。

| 基线 | 命令摘要 | 结果 |
|---|---|---|
| 全量 unittest | `-m unittest discover -s tests -q` | PASS，649 tests，2.167s |
| 阶段0模型/集成 | records + candidate + stage0 integration | PASS，49 tests，0.044s |
| R03 fingerprint | `ScreenFingerprintTests` | PASS，17 tests，0.002s |
| R04 normalization | `tests.test_ocr_normalization` | PASS，86 tests，0.794s |
| R05 aggregation | `tests.test_ocr_aggregation` | PASS，47 tests，0.750s |
| Store | `tests.test_ocr_store` | PASS，14 tests，0.226s |
| Replay | `tests.test_ocr_replay` | PASS，22 tests，0.129s |
| 加载检测 | load helper + load gate cases | PASS，16 tests，0.006s |
| 候选人切换 | `CandidateSwitchPureTests` | PASS，23 tests，0.001s |
| 主循环/收藏/转发/ESC/时长 | `SimpleBrushOCRTests` | PASS，217 tests，0.184s |
| 规则引擎/Unicode | OCR text + detector | PASS，82 tests，0.022s |
| Windows/平台中立 | calibration + normalizer dependency test | PASS，26 tests，0.030s |
| compileall | production OCR modules + tests | PASS |
| pip check | `-m pip check` | PASS，No broken requirements found |
| diff check | `git diff --check` | PASS，无 whitespace error |

仓库没有独立 macOS 专用测试文件或当前 macOS runner；本轮验证的是纯模块无 platform/side-effect dependency 和现有平台配置测试。正式 Change 7 必须补充 macOS 环境证据或明确 NOT RUN，不能把 Windows 本机结果宣称为 macOS 实测。

分组测试最初误指定了 normalizer 的 class 名，产生 1 个 test loader error；纠正为真实 `OcrReadingOrderTests.test_module_has_no_platform_or_side_effect_dependencies` 后 26 tests 全部通过。该命令错误不是产品测试失败。

## 15. Benchmark

### 15.1 R04

直接运行 `python tests/benchmark_r04_normalization.py` 因 Python 将 `tests` 作为 import root 而找不到仓库模块，返回 `ModuleNotFoundError`。改用仓库可用的模块调用：

```text
python -m tests.benchmark_r04_normalization
```

后通过。所有场景 `deterministic=true`：

| 场景 | p95 ms | peak KiB |
|---|---:|---:|
| unique-0 | 0.0292 | 7.70 |
| unique-1 | 0.0960 | 10.57 |
| unique-8 | 0.2996 | 21.46 |
| unique-100 | 2.9688 | 185.93 |
| unique-500 | 17.1048 | 888.64 |
| far-same-text-500 | 13.1113 | 900.96 |
| dense-same-position-text-500 | 12.9163 | 999.02 |
| dense-100-repeated-identical | 3.0374 | 207.76 |

### 15.2 R05

命令：

```text
python -m tests.benchmark_r05_aggregation
```

总体：`required_performance_gates_pass=true`、`contract_blockers=[]`、`determinism_100=true`、`reference_release_100_full_candidates=true`、`disabled_does_not_construct_aggregator=true`、`fair_record_semantics_equal=true`。

关键门槛：

| 场景 | p95 ms | 门槛 | peak KiB | 结果 |
|---|---:|---:|---:|---|
| 8×64 unique pure | 16.9623 | ≤20 | 709.47 | PASS |
| 8×256 unique pure | 55.5690 | ≤150 | 2717.53 | PASS |
| 8×64 record projection + candidate finalize | 21.4985 | ≤30 | 759.75 | PASS |
| fuzzy 1→1 | 0.5799 | ≤50 | 44.80 | PASS |
| fuzzy 1→2 | 0.4802 | ≤50 | 51.00 | PASS |
| fuzzy 2→1 | 0.6056 | ≤50 | 51.87 | PASS |
| fuzzy uncertain | 0.4381 | ≤50 | 42.95 | PASS |

## 16. 日志和 data 隔离

测试前后 `logs/simple_brush.log` 完全一致：

```text
size: 7,372,745 bytes
mtime UTC: 2026-08-01T07:15:54.4076423Z
SHA-256: 1be253b07b246aa1b9f3f207f5c22876fa8116a13da13959221eccc2ac62af96
```

`data/ocr_runs` 前后 inventory 完全一致：一个既有 run 目录，4 个 0-byte 文件：

```text
candidates.jsonl
errors.jsonl
run.json
screens.jsonl
```

四个文件前后 size 均为 0、mtime 不变、SHA-256 均为 SHA-256(empty)：

```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

结论：测试和 benchmark 没有污染真实日志或 data 目录。

## 17. 阻塞项

### 17.1 阻塞未来在线 record，不阻塞 Change 1

1. R05 生产默认仍为 disabled；R05 Change 7 历史 blocking audit 没有批准生产 record。R06 Change 6 不得夹带启用。
2. 当前没有非空正式 R04/R05 JSONL 样本，无法正式校准 `high_similarity_threshold`、UI evidence 和 low-confidence 参数。
3. 当前没有 macOS 实机/runner 证据。
4. 当前 R05 实现位于未提交工作区；进入 Change 2 前必须重新确认基线、归属和审批状态。

### 17.2 已设计处理、未触发 Change 1 停止

- R03 hash 非 R04 comparison hash：使用只读 adapter，不改 R03。
- 非正式旧 record 无 reference link：返回 unavailable，不靠顺序猜；1.3 再显式保存 link。
- R05 `new_text_char_count` 包含 uncertain：按 ID 重算独立 new 并交叉验证。

## 18. 待人工决定项

1. 是否以及何时完成 R05 Change 7 独立复验，并批准 R05/R06 production record mode。
2. 是否授权真实 OCR 样本的采集、访问、留存、脱敏和删除；未授权时仅使用合成 fixture。
3. R06 分析阈值在真实样本上的校准结论。
4. R06 Change 7 的 macOS 验证环境；没有环境时必须记录 NOT RUN。

## 19. 最终 Git 状态说明

本 Change 在工作区只新增本报告和两份 R06 设计文档。现有 `.gitignore:20` 的 `*.md` 规则会忽略这三个新文件；`git check-ignore -v` 已确认三者均命中该规则，所以它们不会出现在普通 `git status --short` 中，也不是 tracked 文件。本 Change 按禁止事项没有修改 `.gitignore`、没有使用 `git add -f`。若未来要纳入版本控制，必须由获授权的后续操作显式处理。

开始前已有 R05 tracked/untracked 工作、`docs/project-review.zip`、`venv-packages-before-reinstall.txt`、`logs/simple_brush.log` 和 `data/ocr_runs` 均未修改、删除或暂存。最终普通 Git 状态相对开始前没有新增可见条目，HEAD 仍为 `cd5d96c731caed07f7b841c437b2ee9f5086ffd0`。

没有执行 `git add`、commit、push、tag 或 release。完成后停止，不进入 Change 2。
