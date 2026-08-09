# TID — R06 OCR 页面相似度、文本重叠率与有效新增量

## 1. 文档信息与设计状态

| 项目 | 值 |
|---|---|
| 需求 | R06 OCR 页面相似度、文本重叠率与有效新增量 |
| 文档版本 | 1.1 |
| 日期 | 2026-08-01 |
| 状态 | Change 2 前置合同 Corrective 已冻结；尚未实施 |
| 当前 HEAD | `cd5d96c731caed07f7b841c437b2ee9f5086ffd0` |
| 当前 writer Schema | 工作区 R05 `1.2.0`；HEAD `1.1.0` |
| R06 目标 Schema | `1.3.0` |
| 明确排除 | R07、AI、SQLite、真实页面、生产启用 |

标记约定：

- **[仓库确认]**：由 2026-08-01 工作区真实代码和测试确认。
- **[设计冻结]**：后续 Change 必须按本文实现；变更需独立设计审查。
- **[待校准]**：可用于记录/离线分析，不能进入页面或动作控制流。
- **[前置阻塞]**：不妨碍本 TID 完成，但阻塞指定后续接入或验收。

## 2. 当前架构

### 2.1 OCR 到 screen record 的真实数据流

**[仓库确认]** 当前在线链路是：

```text
OCRKeywordDetector.capture_observation()            ocr_detector.py
  -> backend.recognize(image)                       一次既有 OCR
  -> accepted_ocr_items()
  -> build_screen_fingerprint()                     R03
  -> normalize_ocr_text()                           R04
  -> ScanObservation(raw_items/fingerprint/normalization)
  -> observation_callback                           formal/confirmation

simple_brush.record_ocr_observation()
  -> CandidateOcrBuilder.build_screen_record()      ocr_candidate.py
     -> OcrBox / raw_text
     -> normalization_record_fields()               R04 segment 投影
     -> OcrScreenRecord
     -> CandidateDocumentAggregator.add_screen()    仅 R05 record 模式
     -> aggregation_screen_record_fields()
     -> builder._screens.append(final_record)
  -> JsonlOcrRecordStore.save_screen(final_record)  ocr_store.py

simple_brush.finalize_current_candidate_recording()
  -> CandidateOcrBuilder.finalize()
  -> JsonlOcrRecordStore.save_candidate()
```

`simple_brush.py:719-789` 的 `record_ocr_observation()` 复用已经完成的 observation，不触发第二次 OCR 或截图。`ocr_detector.py:584-679` 同一次 capture 同时生成 R03 与 R04。`ocr_candidate.py:342-484` 在 builder 内形成最终 screen object，`simple_brush.py:777` 只保存一次。

### 2.2 阶段0真实类型与序列化

| 能力 | 定义文件与真实接口 | 当前职责 |
|---|---|---|
| `OcrBox` | `ocr_records.py:402` | `raw_text`、confidence、bbox、original/screen index |
| `OcrTextSegment` | `ocr_records.py:418` | 视觉行 ID、order、R04 文本、box 来源、char_count |
| `OcrScreenRecord` | `ocr_records.py:758` | 一次 capture 的阶段0/R03/R04/R05 证据与后续占位 |
| `CandidateOcrDocument` | `ocr_records.py:1414` | 候选人 screens、capture summary、R05 document |
| `RunManifest` | `ocr_records.py:1660` | run/schema/config/data_files/counts |
| `OcrRecordStore` | `ocr_store.py:59` | `save_screen/save_candidate/save_error/close` 边界 |
| `JsonlOcrRecordStore` | `ocr_store.py:80` | append-only JSONL、manifest 原子覆盖、best-effort fail-open |
| JSON 转换 | `to_json_compatible()`、`json_dumps()`，`ocr_records.py:270-307` | dataclass 字段声明顺序序列化 |
| Reader | `OcrRunReader`，`ocr_replay.py:94` | strict/tolerant 读取和过滤 |
| 离线装载 | `load_ocr_run()`，`ocr_replay.py:736` | 物化 manifest/screens/candidates/errors |
| R04 replay | `replay_screen_normalization()`，`ocr_replay.py:401` | 从 raw evidence 重算 R04，不写盘 |
| R05 replay | `replay_candidate_aggregation()`，`ocr_replay.py:646` | 同一 aggregator 重建 candidate，不写盘 |

存储文件由 `ocr_store.py` 冻结为 `run.json`、`screens.jsonl`、`candidates.jsonl`、`errors.jsonl`。`_append_line()` 完整序列化后单行 append/flush；不存在 update/backfill API。

### 2.3 当前 Schema 和旧记录兼容

**[仓库确认]** 工作区定义：

- `1.0.0`：Stage 0 legacy；
- `1.1.0`：R04；
- `1.2.0`：R05；
- candidate document 支持 `stage0-v1`、`r05-document-v1`。

`OcrScreenRecord.from_dict()`、`CandidateOcrDocument.from_dict()` 和 `RunManifest.from_dict()` 先校验版本，再为旧版本显式恢复 `not_attempted/null/empty`，同时 `_known_values()` 忽略 additive unknown fields。`OcrRunReader` 在逐行构造对象前也检查版本。旧 Schema 可稳定读取；R06 不得删除 1.0/1.1/1.2 reader。

### 2.4 R03 exact hash 真实接口

**[仓库确认]** 唯一实现位于 `ocr_detector.py`：

- `FINGERPRINT_VERSION = "r03-v1"`；
- `build_screen_fingerprint(accepted_items, captured_at=...)`；
- `build_fingerprint_normalized_text()`：按 R03 reading order，对每个 accepted item 使用 R03 whitespace normalization，以 `\n` 连接；
- `sha256_normalized_text(text)`：`hashlib.sha256(text.encode("utf-8")).hexdigest()`；
- `compare_screen_fingerprints(left, right)`：校验版本和 64 位小写 hash 后比较。

所有生产调用由 `OCRKeywordDetector.capture_observation()` 进入；`simple_brush.py` 的切换验证、稳定确认、加载后的 observation 复用均消费同一个 `ScreenFingerprint`，没有第二套 exact hash。`record_ocr_observation()` 把同一 fingerprint 的 `exact_hash/fingerprint_version` 投影进 `OcrScreenRecord`。

加载检测 `evaluate_detail_page_load()` 使用 box/text 长度阈值，不使用 exact hash。候选人切换和 ready 稳定性复用 `compare_screen_fingerprints()`。

**关键结论**：R03 exact hash 当前不是基于 R04 `comparison_text`，而是 R03 自己的 normalized text。R06 的最小适配是新增纯 `R03ExactHashAdapter`（可为 `ocr_similarity.py` 私有 helper）：只校验并消费两个 record 已保存的 hash/version；不得修改 `ocr_detector.py`、不得重算或覆盖 `exact_hash`、不得把 R04 hash 冒充 R03。

### 2.5 R04 真实接口

**[仓库确认]** `ocr_normalization.py`：

- `normalize_ocr_text()` 生成 `raw_text`、`normalized_text`、`comparison_text`；
- `NORMALIZATION_VERSION = "r04-v1"`，config 为 `r04-config-v1` + SHA-256 digest；
- `normalize_box_text()`：NFC、trim、box 内 whitespace collapse，不做语义改写；
- `build_reading_order()`：几何视觉行；
- `detect_duplicate_boxes()`：保留 raw evidence，仅从 derived text 抑制有强几何证据的重复框；
- `build_comparison_text()`：NFKC、lower、删除 Unicode whitespace，保留其余字母、数字、标点、符号、UI 文本和短词；
- `protect_comparison_tokens()`：识别 Unicode 字母/数字与 `. + # - / _` 组成的符号型词元，恢复时不丢字符。

`ocr_candidate.normalization_record_fields()` 把 `normalized_lines` 投影为 `OcrTextSegment`：ID 为 `{screen_id}:line:{zero_based_order}`，保存 `normalized_text`、`comparison_text`、`ocr_box_ids`、`char_count`。`OcrScreenRecord._validate_r04_contract()` 验证 segment 顺序、ID、box 来源和 survivor 覆盖。

### 2.6 R05 分类、计数和 replay 真实接口

**[仓库确认]** `ocr_aggregation.py`：

- `CandidateDocumentAggregator.add_screen()` 是候选人作用域权威分类入口；
- `ScreenAggregationResult` 给出 `matched_segment_ids/new_segment_ids/uncertain_segment_ids`；
- `aggregation_screen_record_fields()` 把结果投影到同一 `OcrScreenRecord`；
- `aggregation_char_count(comparison_text)` 是字符计数权威 helper：拒绝 whitespace 后返回 Python `len()`，即 Unicode code point 数；
- `match_evidence` 保存 adjacent exact/fuzzy、historical exact、source segment/box 与 document segment；
- `CandidateDocumentAggregator.finalize()` 生成 `document_segments/document_text` 和 source occurrence；
- 版本为 `r05-v1`、config `r05-config-v1`、config digest 为 canonical JSON SHA-256；
- 任一匹配阶段失败时 fail open，把可验证当前 segment 追加为 uncertain/partial。

`OcrScreenRecord._validate_r05_contract()` 强制三个 ID 集合无重叠、完整覆盖当前 screen segments，并验证 evidence。当前 R05 字段语义为：

- `overlap_text/count` = matched；
- `new_text/new_text_char_count/new_segment_count` = new + uncertain；
- `certain_new_segment_count` = new；
- `uncertain_segment_count/uncertain_char_count` = uncertain。

因此 R06 不可把 R05 `new_text_char_count` 当“确定 new”直接进入三项相加。R06 必须按 ID 重新投影，并额外验证：

```text
r05.overlap_char_count == count(matched)
r05.new_text_char_count == count(new) + count(uncertain)
r05.uncertain_char_count == count(uncertain)
```

在线 R05 由 builder 调用，离线 R05 由 `replay_candidate_aggregation()` 构造同一 `CandidateOcrBuilder(..., aggregation_mode="record")`，所以可以共用数据和算法。当前生产默认 `R05_AGGREGATION_MODE = "disabled"`；record 模式只在测试/benchmark/另行批准 shadow 中启用。

### 2.7 Reference 字段与当前关系

**[仓库确认]** 每条 screen 已有 `run_id`、`candidate_record_id`、`screen_id`、`screen_index`、`attempt_index`、`capture_type`、`is_formal_screen`。

- 正式 detector scan 绑定 `screen_index=1..8`，capture 为 `formal_screen`、formal 为 true。
- scroll confirmation 保存相同 scan number 的 `screen_index`，但 formal 为 false。
- load check/retry 的 `screen_index=None`，attempt key 共享 `load` 序列。
- switch check 的 `screen_index=None`；pre-switch baseline 属于旧 candidate，post-next observation 属于新 candidate。
- 当前 record 没有 `reference_screen_id`。

因此正式屏可用显式 index/身份集合可靠解析；非正式屏在旧 Schema 中无法可靠推断。只靠 candidate.screens 顺序或 JSONL 前一行不合格。

### 2.8 R06 唯一在线接入点

**[设计冻结]** 唯一接入点是 `CandidateOcrBuilder.build_screen_record()` 内 R05 projection 完成之后、`self._screens.append(record)` 之前。顺序必须是：

```text
R04 final record
  -> R05 add_screen + projection（如启用）
  -> R06 resolve reference + evaluate once + projection（如启用）
  -> self._screens.append(final record)
  -> save_screen(final record) once
```

禁止在 Store、detector、页面循环、candidate finalize 时为同一 screen 重算。candidate finalize 只聚合已保存的 R06 screen results。

## 3. 文件级修改计划总表

| 文件 | 真实/计划类或函数 | R06 计划 |
|---|---|---|
| `ocr_records.py` | `OcrScreenRecord`、`CandidateOcrDocument`、`RunManifest`、`from_dict()`、验证 helpers | Schema 1.3、新枚举/value types、result/summary/config identity、旧版兼容 |
| `ocr_similarity.py`（新增） | `OcrSimilarityConfig`、`resolve_reference()`、`evaluate_screen_similarity()`、`CandidateSimilarityEvaluator` | 唯一纯 R06 算法与候选人有界状态 |
| `ocr_candidate.py` | `CandidateOcrBuilder.__init__()`、`build_screen_record()`、`add_screen()`、`finalize()` | R05 后唯一接入、显式 reference hint、candidate summary |
| `ocr_store.py` | `JsonlOcrRecordStore.__init__()`、`_validate_screen_identity()`、`save_candidate()` | manifest config、R06 identity 校验、一次写入 |
| `ocr_replay.py` | `OcrRunReader`、`load_ocr_run()`、`replay_candidate_aggregation()` 后的新 replay API | 同一 resolver/evaluator、旧版正式屏重建、sidecar 输入 |
| `ocr_similarity_sidecar.py`（新增） | `write_similarity_sidecar()`、CLI `main()` | 新文件输出，不改源 run/JSONL |
| `simple_brush.py` | `create_ocr_record_store()`、`start_candidate_ocr_recording()`、`record_ocr_observation()` | 仅静态 mode/config 透传；不得改变 page flow |
| `tests/test_ocr_similarity.py`（新增） | 纯算法、reference、计数、分类、失败测试 | R06 主要测试 |
| `tests/benchmark_r06_similarity.py`（新增） | 合成 benchmark | 单 pair、8 屏、长文本、内存、确定性 |
| `tests/test_ocr_records.py` | model/round-trip/compat | 1.3 与 1.0—1.2 |
| `tests/test_ocr_candidate.py` | builder/add/finalize | 每屏一次、candidate 隔离、fail-open |
| `tests/test_ocr_store.py` | identity/append/failure | manifest/result mismatch、disabled |
| `tests/test_ocr_replay.py` | strict/tolerant/replay | online/offline 等价、sidecar |
| `tests/test_ocr_stage0_integration.py` | stage0 main integration | 次数/行为零变化 |
| `tests/test_simple_brush_ocr.py` | 页面调用 spies | OCR/截图/滚动/动作/ESC/timer 零差异 |

不得修改 `ocr_detector.py`、`ocr_normalization.py` 或 `ocr_aggregation.py` 的生产语义。若实现必须修改其算法/字段才能继续，应触发停止条件并另开前置 Change。

## 4. Schema 设计

### 4.1 版本与 result 放置

**[设计冻结]** writer 升级为 `STORAGE_SCHEMA_VERSION = "1.3.0"`，保留 1.0/1.1/1.2 reader。R06 权威结果放在：

- `OcrScreenRecord.similarity_result: Optional[OcrSimilarityResult]`；
- `CandidateOcrDocument.similarity_summary: Optional[R06CandidateSummary]`，screens 内嵌同一结果；
- `RunManifest` 的 R06 mode/version/config/digest/snapshot；
- 在线仍写 `screens.jsonl`、`candidates.jsonl` 和 `run.json`。

旧顶层占位 `similarity_hash/similarity_score/overlap_ratio/new_text_ratio/has_effective_new_text/similarity_version` 在 1.3 作为只读兼容投影，必须与 nested result 相等或同为 null，不能成为第二权威。R05 顶层 counts/text 不改语义。

### 4.2 状态枚举

```text
SimilarityStatus:
  not_attempted | completed | partial | failed | unavailable | no_reference

ComparisonClass:
  exact_same
  high_similarity_with_effective_new
  high_similarity_without_effective_new
  changed_with_effective_new
  changed_without_effective_new
  empty_or_unavailable
  uncertain

EffectiveNewStatus:
  present | possible | none | unavailable

EffectiveDecision:
  effective | ineffective | uncertain

ReferenceResolutionStatus:
  resolved | no_reference | unavailable

ReferenceSource:
  none | formal_previous_index | explicit_record | reconstructed_formal_index
```

### 4.3 `ReferenceResolution` 字段与状态合同

**[设计冻结]** `ReferenceResolution` 是 resolver 的唯一返回 value type。字段声明顺序即 dataclass/JSON 序列化顺序：

```text
1. status: ReferenceResolutionStatus
2. reference_screen_id: Optional[str]
3. reference_screen_index: Optional[int]
4. reference_capture_type: Optional[CaptureType]
5. reference_source: ReferenceSource
6. warning_codes: tuple[str, ...]
```

状态合同：

| status | 字段合同 |
|---|---|
| `resolved` | `reference_screen_id` 和 `reference_capture_type` 非 null；`reference_source != none`；正式屏 reference 的 `reference_screen_index` 非 null；`warning_codes` 通常为空，若存在只能是不会否定 resolution 的白名单 warning |
| `no_reference` | 仅用于首个正式屏；三个 reference 目标字段均为 null；`reference_source=none`；`warning_codes=()` |
| `unavailable` | 三个 reference 目标字段均为 null；`warning_codes` 至少一个；`reference_source` 保存本次尝试的策略且不得为 `none`，不得用一个未验证目标冒充 resolved reference |

投影合同：

```text
resolved
  -> OcrSimilarityResult 复制 reference_screen_id、reference_screen_index、
     reference_capture_type、reference_source
  -> evaluator 再根据 R03/R04/R05 和算法结果决定 completed/partial/failed

no_reference
  -> similarity_status = no_reference
  -> comparison_class = empty_or_unavailable

unavailable
  -> similarity_status = unavailable
  -> comparison_class = empty_or_unavailable
```

resolution 的 `warning_codes` 必须合并到 result `warning_codes`。合并只允许第 4.6 节白名单成员，按白名单声明顺序稳定去重；同一 code 无论 resolver/evaluator 出现多少次，在同一 result 中只保存一次。

### 4.4 `OcrSimilarityResult` 字段顺序、类型与 null

以下顺序即 dataclass/JSON 序列化顺序：

| 字段 | 类型 | null/空语义 |
|---|---|---|
| `similarity_status` | enum | 永不 null |
| `reference_screen_id` | `str?` | no_reference/unavailable 时 null |
| `reference_screen_index` | `int?` | 非正式或无 ref 可 null |
| `reference_capture_type` | enum? | 无可靠 ref 时 null |
| `reference_source` | `ReferenceSource` | `none/formal_previous_index/explicit_record/reconstructed_formal_index` |
| `exact_same` | `bool?` | hash/version 不可比时 null |
| `reference_fingerprint_version` | `str?` | 无可靠 ref/hash 时 null |
| `reference_exact_hash` | `str?` | 无可靠 ref/hash 时 null |
| `similarity_score` | `float?` | `[0,1]`；R04/长度/失败不可算时 null |
| `ngram_scores` | tuple value type | 未计算为空；按 n 升序 |
| `current_simhash` | `str?` | 16 位小写 hex；当前空/失败 null |
| `reference_simhash` | `str?` | reference 空/失败 null |
| `simhash_hamming_distance` | `int?` | 0—64；任一 hash null 时 null |
| `simhash_similarity_score` | `float?` | `[0,1]`；任一 hash null 时 null |
| `overlap_char_count` | `int?` | R05 不可验证时 null |
| `new_char_count` | `int?` | 仅 R05 `new`；不可验证时 null |
| `uncertain_char_count` | `int?` | 仅 R05 `uncertain`；不可验证时 null |
| `current_effective_char_count` | `int?` | 当前全部 R04 segment；不可验证时 null |
| `overlap_segment_count` | `int?` | R05 不可验证时 null |
| `new_segment_count` | `int?` | 仅 R05 `new` |
| `uncertain_segment_count` | `int?` | 仅 R05 `uncertain` |
| `current_effective_segment_count` | `int?` | 当前全部 R04 segment |
| `overlap_ratio_numerator` | `int?` | 等于 overlap chars |
| `overlap_ratio_denominator` | `int?` | 等于 current effective chars |
| `overlap_ratio` | `float?` | 零分母/不可用 null |
| `new_text_ratio_numerator` | `int?` | 等于 new chars |
| `new_text_ratio_denominator` | `int?` | 同一 denominator |
| `new_text_ratio` | `float?` | 零分母/不可用 null |
| `uncertain_ratio_numerator` | `int?` | 等于 uncertain chars |
| `uncertain_ratio_denominator` | `int?` | 同一 denominator |
| `uncertain_ratio` | `float?` | 零分母/不可用 null |
| `effective_new_status` | enum | 永不 null；前置失败为 unavailable |
| `effective_new_decisions` | tuple | 每个 new/uncertain segment 一项，source order |
| `effective_new_segment_count` | `int?` | 不可用 null |
| `ineffective_new_segment_count` | `int?` | 不可用 null |
| `possible_new_segment_count` | `int?` | uncertain/证据不足 |
| `effective_new_char_count` | `int?` | 不可用 null |
| `possible_new_char_count` | `int?` | 不可用 null |
| `has_effective_new_text` | `bool?` | present/possible=true，none=false，unavailable=null |
| `comparison_class` | enum | 永不 null |
| `similarity_version` | `str?` | not_attempted 时 null，其余 `r06-v1` |
| `similarity_config_version` | `str?` | not_attempted 时 null |
| `similarity_config_digest` | `str?` | not_attempted 时 null；64 位小写 hex |
| `warning_codes` | tuple[str] | 有序去重、只允许白名单 code |

`NgramScore` 固定字段顺序为 `n:int`、`weight:float`、`left_feature_count:int`、`right_feature_count:int`、`dice_score:float`。

`EffectiveNewDecision` 固定字段顺序为 `segment_id`、`source_classification` (`new/uncertain`)、`decision`、`reason_code`、`evidence_codes`。

### 4.5 `R06CandidateSummary` 字段、存在语义与会计

**[设计冻结]** `R06CandidateSummary` 字段声明顺序即 dataclass/JSON 序列化顺序：

```text
1. similarity_version: str
2. similarity_config_version: str
3. similarity_config_digest: str
4. screen_count: int
5. not_attempted_screen_count: int
6. completed_screen_count: int
7. partial_screen_count: int
8. failed_screen_count: int
9. unavailable_screen_count: int
10. no_reference_screen_count: int
11. exact_same_screen_count: int
12. high_similarity_with_effective_new_screen_count: int
13. high_similarity_without_effective_new_screen_count: int
14. changed_with_effective_new_screen_count: int
15. changed_without_effective_new_screen_count: int
16. empty_or_unavailable_screen_count: int
17. uncertain_screen_count: int
18. effective_present_screen_count: int
19. effective_possible_screen_count: int
20. effective_none_screen_count: int
21. effective_unavailable_screen_count: int
22. warning_count: int
23. warning_code_counts: tuple[R06WarningCodeCount, ...]
```

`R06WarningCodeCount` 字段声明/JSON 顺序为：

```text
1. warning_code: str
2. count: int
```

`warning_code_counts` 只保存 `count > 0` 的 warning，按第 4.6 节 warning 白名单声明顺序排列。同一 screen 的同一 warning 最多计数一次；这与 screen result 内 warning 已稳定去重的合同一致。

存在语义：

| Schema/mode | `similarity_summary` |
|---|---|
| Schema 1.0—1.2 | null |
| Schema 1.3 disabled | null |
| Schema 1.3 record | 必须存在 |

Schema 1.3 record 即使没有 screen 也必须保存合法空 summary：identity 三字段与 RunManifest 完全一致，`screen_count=0`，所有 count 为 0，`warning_code_counts=()`。

Summary 会计合同：

```text
not_attempted_screen_count
  + completed_screen_count
  + partial_screen_count
  + failed_screen_count
  + unavailable_screen_count
  + no_reference_screen_count
= screen_count

exact_same_screen_count
  + high_similarity_with_effective_new_screen_count
  + high_similarity_without_effective_new_screen_count
  + changed_with_effective_new_screen_count
  + changed_without_effective_new_screen_count
  + empty_or_unavailable_screen_count
  + uncertain_screen_count
= screen_count

effective_present_screen_count
  + effective_possible_screen_count
  + effective_none_screen_count
  + effective_unavailable_screen_count
= screen_count

sum(item.count for item in warning_code_counts) = warning_count
```

Summary 只能从 `CandidateOcrDocument.screens[*].similarity_result` 纯重算。不得读取页面状态、日志、OCR/候选人正文、module global、Store manifest counters 或其他全局计数。Schema 1.3 record 中任一 screen 缺失合法 `similarity_result`，candidate 合同即无效；不得跳过该 screen 以凑出 summary。

### 4.6 Warning codes

首版白名单冻结为：

```text
reference_missing
reference_conflict
reference_run_mismatch
reference_candidate_mismatch
reference_capture_invalid
reference_index_invalid
duplicate_screen_id_conflict
exact_hash_unavailable
fingerprint_version_mismatch
r04_not_completed
r05_not_attempted
r05_partial
r05_failed
r05_projection_mismatch
segment_partition_invalid
accounting_mismatch
zero_effective_char_denominator
comparison_text_too_long
simhash_unavailable
effective_evidence_insufficient
ui_evidence_insufficient
config_identity_mismatch
legacy_reference_unavailable
sidecar_source_mismatch
cross_layer_similarity_conflict
evaluation_failed
```

warning 不得包含 OCR 文本、异常消息或候选人标识以外的私密内容。

### 4.7 旧 JSONL 兼容

- 1.0/1.1/1.2 `from_dict()`：`similarity_result=None`、candidate summary null、manifest mode `disabled`。
- 1.3 要求所有新增 R06 manifest 字段和 screen `similarity_result` key 存在；disabled 时值为 null/not_attempted 合同。
- 不回写、不迁移旧行；sidecar 可读取旧记录。
- 1.3 reader 继续忽略未来 additive unknown fields，但缺少本版本 required keys 必须 strict 失败、tolerant 记录 issue。

## 5. Reference resolver

### 5.1 纯接口

```python
def resolve_reference(
    current: OcrScreenRecord,
    candidate_screens_by_id: Mapping[str, OcrScreenRecord],
    formal_screen_id_by_index: Mapping[int, str],
    *,
    explicit_reference_screen_id: Optional[str],
    source_schema_version: str,
) -> ReferenceResolution:
    ...
```

函数无 I/O、无时钟、无全局状态，不读取列表相邻项。

resolver 必须只返回第 4.3 节冻结的 `ReferenceResolution`。resolver 不得直接构造 `OcrSimilarityResult`，evaluator 也不得重新选择 reference；两者通过该 value type 形成唯一边界。

### 5.2 正式屏规则

1. 必须同时满足 `capture_type == FORMAL_SCREEN` 和 `is_formal_screen is True`。
2. `screen_index == 1`：`no_reference`，source=`none`。
3. `screen_index > 1`：目标 index 固定为 `screen_index - 1`。
4. 目标必须在同 run/candidate 映射中唯一、ID 唯一、也是正式屏、index 精确匹配。
5. 缺失/重复/冲突/跳号：`unavailable`，不得退回其他屏。
6. 1.3 在线保存 `reference_screen_id`；Replay 同时验证保存 ID 与 index 规则一致。

### 5.3 非正式 OCR

- 仅接受 `explicit_reference_screen_id`。
- reference 必须同 run、同 candidate，且在候选人已记录屏集合中唯一。
- scroll confirmation 的显式 reference 应是同 `screen_index` 的正式屏。
- load retry 的显式 reference 应是同 candidate 前一个 load attempt；以持久化 ID 证明关系，不以 JSONL 顺序证明。
- switch check 在当前真实流程中跨 candidate 分隔，若没有同 candidate 显式 reference，返回 unavailable；禁止跨候选人引用 R01 context。
- `scroll_retry/other` 没有批准规则时 unavailable。

### 5.4 Replay 重建

- 1.3：以保存 ID 为权威，并用 formal index/capture/identity 复核；冲突为 unavailable。
- 1.2/1.1：可先按 `(run_id,candidate_record_id,screen_index)` 建唯一正式屏 map，再为 index>1 重建 reference，source=`reconstructed_formal_index`。
- 旧非正式屏：`legacy_reference_unavailable`。
- standalone `screens.jsonl` 必须先按 candidate 分组和建立 map；不得流式把上一行当 reference。
- candidate JSONL 与 screens JSONL 同 ID 内容冲突时 strict 失败，tolerant unavailable。

## 6. 主要相似度

### 6.1 输入准备

只接受两侧 R04 `normalization_status == completed` 且 `comparison_text` 为字符串。不得重新 normalize，特征直接按 Python Unicode code point 滑窗。最大单侧 `comparison_text` 为 100,000 code points；超限不截断，主要分数 null + `comparison_text_too_long`。

### 6.2 n-gram 和公式

**[设计冻结][待校准]**：

- n sizes：`(2, 3, 4)`；
- 原始权重：`{2: 0.20, 3: 0.30, 4: 0.50}`；
- 特征：字符 n-gram 多重集合 `Counter`；
- 每 n 使用 multiset Dice：

```text
dice_n = 2 * Σ_g min(count_left[g], count_right[g])
         / (Σ_g count_left[g] + Σ_g count_right[g])
```

- 双侧该 n 都无特征时，从聚合中排除；仅单侧无特征时该 n 分数为 0；
- 可用 n 的权重重新归一化：`score = Σ(w_n * dice_n) / Σ(w_n)`；
- 两个完整 comparison text 都为空：1.0；仅一侧为空：0.0；
- 两侧均非空但所有 n 都无特征（仅可能双方长度 1）：文本完全相等为 1.0，否则 0.0；
- 最终用 `min(1.0,max(0.0,score))` 防浮点边界，不做阈值 round；JSON 保存完整 finite float。

复杂度：时间 `O((n_count)*(L+R))`，额外内存 `O(distinct ngrams)`；禁止全历史两两页面比较。

## 7. SimHash

**[设计冻结]**：

- 位数：64；
- 正常特征：当前 `comparison_text` 的字符 3-gram occurrence；
- 长度 1—2 的非空文本：整个文本作为一个带 domain prefix 的 fallback feature；
- feature bytes：`b"r06-simhash-3gram-v1\0" + feature.encode("utf-8")`；
- feature hash：SHA-256 digest 前 8 bytes，big-endian 64-bit；禁止 Python `hash()`；
- 每 occurrence 权重为 1；每 bit 的正负票相加，票数 `>0` 置 1，`<=0` 置 0；
- 输出 16 位小写 hex；
- Hamming：`(left_int ^ right_int).bit_count()`；
- 辅助分数：`1.0 - distance / 64.0`；
- 空文本 SimHash 为 null；任一侧 null 时 distance/score 为 null；
- 相同文本/config 必须在 Windows/macOS、不同进程和不同 `PYTHONHASHSEED` 下相同。

SimHash 只记录，不参与 exact same；`comparison_class` 首版也只使用主要 n-gram 分数，避免双阈值不可解释。

## 8. R05 计数复用与会计

### 8.1 权威映射

1. 以 `record.segments` 建 `segment_id -> OcrTextSegment`，必须唯一。
2. `matched + new + uncertain` 必须无重叠并完整覆盖，保持 source order。
3. 每个 segment 用 `ocr_aggregation.aggregation_char_count(segment.comparison_text)` 计数；后续若为避免模块方向依赖，可在 R06 私有 helper 实现完全相同校验，但测试必须证明等价，R05 helper 仍为合同权威。
4. 不使用 `normalized_text` 长度、不计算换行、不重新 normalize。

### 8.2 会计关系

```text
overlap_chars = sum(matched)
new_chars = sum(new)
uncertain_chars = sum(uncertain)
current_effective_chars = sum(all current segments)

overlap_chars + new_chars + uncertain_chars == current_effective_chars
overlap_segments + new_segments + uncertain_segments == len(record.segments)
```

并验证 R05 stored projections。任一差异：所有 R06 count/ratio null，status 至少 partial，warning `r05_projection_mismatch/accounting_mismatch`，class `uncertain`；不得修补 R05 原对象。

### 8.3 跨层一致性冲突

`cross_layer_similarity_conflict` 与 `accounting_mismatch` 分工如下：

- `accounting_mismatch` 只表示 R05 segment partition、stored projection、字符数或 segment 数的内部会计不成立；
- `cross_layer_similarity_conflict` 表示各层内部合同分别可验证，但 R03 exact 结论与 R04/R05 派生信号互相矛盾。

首版正式触发条件：reference 已 `resolved`、`exact_same is True`，且满足任一项：

1. 已计算的 `similarity_score` 与 1.0 的差大于 `float_tolerance`；
2. R05 `new_segment_ids` 或 `uncertain_segment_ids` 非空；
3. 等价的合法 R06 `new_char_count/new_segment_count/uncertain_char_count/uncertain_segment_count` 任一大于 0。

投影语义：

- result 加入 `cross_layer_similarity_conflict`；
- `similarity_status=partial`；若已有更严重的 `failed/unavailable/no_reference`，不得用 partial 覆盖，但 resolved exact 场景正常不会产生后两者；
- `comparison_class=uncertain`，不允许投影为 `exact_same` 或 with/without effective-new 类；
- `exact_same=True` 原样保留；R04 similarity、R05 counts/ratios 和 effective 结果只要各自内部合同成立也原样保留，不因跨层冲突伪造 null 或改写 R03/R05；
- warning 进入 candidate summary，按同一 screen 最多一次计数；
- 该 warning 只影响记录解释，不进入扫描、动作或停止控制流。

### 8.4 比例、零分母与容限

分母统一为 `current_effective_char_count`。分母大于 0 时：

```text
overlap_ratio = overlap_chars / denominator
new_text_ratio = new_chars / denominator
uncertain_ratio = uncertain_chars / denominator
```

保存三个独立 numerator/denominator。验证每项 `[0,1]` 且比例和与 1 的差不超过 `1e-12`。分母 0 时 counts 为 0、三个 ratio 为 null、warning `zero_effective_char_denominator`，class `empty_or_unavailable`。

## 9. 有效新增分类

### 9.1 输入和输出范围

评估 R05 `new_segment_ids`；同时为 `uncertain_segment_ids` 生成 source=`uncertain`、decision=`uncertain` 的保守条目。不得改变 R05 分类。R05 是 1→1、1→2、2→1 与 split/merge match evidence 的唯一权威；合法 split/merge evidence 的 current IDs 属于 `matched_segment_ids`，R06 v1 不对 matched 生成 `EffectiveNewDecision`。

### 9.2 逐 segment 决策顺序

顺序固定，第一项具有充分证据的结论返回；灰区继续到 `uncertain`：

1. `format_only`
2. `duplicate_artifact`
3. `low_confidence_noise`
4. `likely_repeated_ui_noise`
5. `short_text_protected`
6. `effective`
7. `uncertain`

### 9.3 各类证据

| reason | 必需证据 | 禁止的单独证据 |
|---|---|---|
| `format_only` | comparison 内容全为 Unicode separator/punctuation/format，且无字母数字、无受保护 token | 仅“很短” |
| `duplicate_artifact` | 相同 comparison + R04 duplicate pair/group 的文本与几何确认，source box 可追溯 | 仅另一处有相同文字 |
| `low_confidence_noise` | 单 segment、孤立 box、全部 confidence 位于 `[effective_min_confidence, +0.03]`、有效字符不超过 2、无结构/保护、邻接无支持 | 仅 confidence 低或字符少 |
| `likely_repeated_ui_noise` | 同 exact comparison 跨至少 3 个正式屏；box 中心差不超过 `max(8px,0.5*median_height)`；尺寸相似度至少 0.90；来源均可追溯；无业务反证 | 具体 UI 文案、仅出现两次 |
| `short_text_protected` | 命中第 10 节任一保护器 | 保护命中不得因长度降级 |
| `effective` | 有字母/数字/业务字符，且所有无效检查均有足够输入并不成立 | evidence 缺失时不可直接 effective |
| `uncertain` | 前置证据缺失、冲突、阈值灰区、异常或 R05 source uncertain | 不得强制转无效 |

UI 跨屏索引按 exact comparison 建有界 map，最多 8 个正式屏，不做页面两两比较。

`split_merge_artifact` 是普通字符串 reason code 中的 **r06-v1 reserved / never emitted** 值，不是本版本的决策分支或测试正例。R05 matched 的 1→2/2→1 evidence 继续由 `match_evidence`、`document_segments` 和 source occurrence 保存。R05 new 不得仅凭 fuzzy score、文本相似、相邻拼接或 document segment ID 被 R06 推断为 split/merge；其他无效证据不足时只能得到 effective 或 uncertain。

若 new 或 uncertain ID 同时出现于 `match_evidence.current_segment_ids`，这是前序 R05 partition/evidence 合同冲突，而不是 split/merge 正例。R06 必须停止全部有效新增 decision，warning 使用 `segment_partition_invalid` 或 `r05_projection_mismatch`，status 至少 partial，effective status unavailable、boolean null、class uncertain；不得修改 R05 源对象。

### 9.4 低置信度配置与缺失证据语义

**[设计冻结]** 下列三项属于 `OcrSimilarityConfig`：

```text
effective_min_confidence = 0.85
low_confidence_delta = 0.03
low_confidence_max_chars = 2
```

- `effective_min_confidence=0.85` 的记录来源是当前 R04 `DEFAULT_OCR_NORMALIZATION_CONFIG` 的有效 OCR 最低置信度；
- `low_confidence_delta=0.03` 与 `low_confidence_max_chars=2` 的记录来源是 R06 有效新增合同；
- 低置信度区间固定为 `[effective_min_confidence, effective_min_confidence + low_confidence_delta]`，有效字符上限固定使用 `low_confidence_max_chars`，不得在算法中另写字面量。

三项必须进入 canonical config snapshot 和 config digest，并通过 `RunManifest.similarity_config` 随 run 持久化。Replay 必须从 manifest snapshot 恢复三项；online、Replay 和 sidecar 禁止动态读取当前 module global/default 来替代历史值。

旧记录缺少完整 R06 config，或 segment/source box 缺少可验证 confidence 证据时：在依次排除此前已由充分证据成立的 `format_only`、`duplicate_artifact` 后，不得判 `low_confidence_noise`，该 segment 必须直接输出 `decision=uncertain`，不得继续降为 UI noise、short-text protected 或 effective；候选人侧按 `possible` 保守汇总。

## 10. 短文本保护

### 10.1 结构模式

冻结识别器类别：

- 年份：`19xx/20xx`，可带 `年`；
- 日期：`YYYY-MM-DD`、`YYYY/MM/DD`、`YYYY.MM.DD`、`YYYY年M月D日` 及月日结构；
- 时间/数值范围：数字两侧以 `- ~ – —` 连接，可带年/月/天/小时/h/%；
- 数字结构：数字与 `- / . + : #` 的结构组合；
- 版本：可选 `v/version` + 两段以上点号数字，可带 pre-release/build suffix；
- R04 token：调用 `protect_comparison_tokens(normalized_text)`，保留带 `. + # - / _` 的字母数字词元；
- 中文/英文未知短实体：无法证明伪影时走 uncertain，不因长度删除。

### 10.2 业务短词

`business_short_terms_version = "r06-business-short-v1"`，首版 canonical 列表：

```text
SLG, UE5, 3D, C++, C#, .NET, Unity, 主美, UI, TA, 3A, 0-1, 2D/3D
```

匹配使用 R04 `build_comparison_text()` 后的 canonical 值；配置 snapshot 保存完整列表、version 和 canonical digest。增加/删除词必须升级业务词版本。

## 11. UI 处理

禁止 UI 文字黑名单、正则文案表或按词义猜 UI。`likely_repeated_ui_noise` 的组合证据参数固定进入 config：

- `ui_min_formal_screen_occurrences = 3`；
- `ui_center_tolerance_min_px = 8.0`；
- `ui_center_tolerance_height_ratio = 0.5`；
- `ui_min_size_similarity = 0.90`；
- 必须 exact comparison 相同且来源 box 几何有效；
- 任一保护命中使 UI 无效结论不得成立，并继续进入短文本保护；只有证据本身缺失或冲突时才降为 uncertain；
- evidence 不完整时 warning `ui_evidence_insufficient`。

## 12. Comparison class

### 12.1 分析阈值

`high_similarity_threshold = 0.85` **[待校准]**。它只决定记录类别，不控制页面。真实样本校准后必须升级 config version/digest；不得静默替换。

### 12.2 优先级

```text
1. status in (no_reference, unavailable, failed) 或任一 comparison text 空
     -> empty_or_unavailable
2. accounting/R05/effective evidence 有冲突，或 effective_new_status=possible/unavailable
     -> uncertain
3. exact_same is True
     -> exact_same
4. similarity_score >= high threshold and effective_new_status=present
     -> high_similarity_with_effective_new
5. similarity_score >= high threshold and effective_new_status=none
     -> high_similarity_without_effective_new
6. similarity_score < high threshold and effective_new_status=present
     -> changed_with_effective_new
7. similarity_score < high threshold and effective_new_status=none
     -> changed_without_effective_new
8. 其余
     -> uncertain
```

若 `exact_same=True` 却 R04 similarity 非 1 或 R05 报告 new/uncertain 非零，按第 8.3 节记录 `cross_layer_similarity_conflict` 并走 uncertain。不得把跨层矛盾误报为 R05 内部 `accounting_mismatch`。

## 13. 配置和版本

### 13.1 版本

```text
SIMILARITY_VERSION = "r06-v1"
SIMILARITY_CONFIG_VERSION = "r06-config-v1"
BUSINESS_SHORT_TERMS_VERSION = "r06-business-short-v1"
R06_SIMILARITY_MODE = "disabled" | "record"
```

首轮合并后的生产默认必须是 `disabled`；改成 `record` 需要 R05 record 前置通过和独立批准。

### 13.2 config snapshot

snapshot 至少含：n sizes/weights、SimHash bits/n/hash/domain、high threshold、业务短词 version/list/digest、format 类别、`effective_min_confidence=0.85`、`low_confidence_delta=0.03`、`low_confidence_max_chars=2`、UI 组合证据参数、float tolerance、max comparison length、max formal screens、算法版本。canonical JSON 使用 UTF-8、sort keys、紧凑 separators、`allow_nan=False`，digest 为小写 SHA-256。

`RunManifest` 新增顺序：

```text
similarity_mode
similarity_version
similarity_config_version
similarity_config_digest
similarity_config
business_short_terms_version
business_short_terms_digest
```

disabled 时除 mode 外均 null。record 时必须完整匹配。未经校准的阈值仍完整保存，但不进入任何 control flow。

record manifest 的 `similarity_config` 必须包含第 9.4 节三项，digest 覆盖其名称、类型和值；缺失、额外替代字段、类型不符或 digest 不匹配均为 config identity error。Replay 只从该 manifest snapshot 恢复，不以当前 R04/R06 默认值补洞。旧 Schema 或 sidecar source 没有完整历史 config 时，只能由 caller 显式提供一份完整、独立标识的 sidecar config；不得把 override 冒充原 run 在线 identity。

## 14. 在线、离线和 sidecar

### 14.1 evaluator 纯接口

```python
def evaluate_screen_similarity(
    current: OcrScreenRecord,
    reference: Optional[OcrScreenRecord],
    reference_resolution: ReferenceResolution,
    candidate_context: R06CandidateContext,
    config: OcrSimilarityConfig,
) -> OcrSimilarityResult:
    ...
```

输入/输出 immutable；无 I/O、日志、时钟、环境、页面状态或动作权限。`CandidateSimilarityEvaluator.add_screen()` 只维护当前 candidate 最多 8 屏的 reference map 和 UI evidence index；finalize 后 clear。它不接收 candidate document/document segments，也不为 R05 new 重建 split/merge；R05 evidence 仅用于验证非法 new/uncertain evidence 关系。

### 14.2 在线

- builder 只在 `similarity_mode="record"` 时构造 evaluator；disabled 在构造前短路。
- record 模式的正式屏若 R05 未 attempted，R06 状态 unavailable/partial，不伪造比例。
- 每 screen 只调用一次 evaluator，发生异常由 builder 捕获并投影 failed result。
- `save_screen()` 接收最终对象；candidate 内嵌逐字段相同 screen。
- candidate summary 严格按第 4.5 节从 screens 纯重算，保存冻结 identity、status/class/effective 全分区计数和按白名单顺序的 warning counts；record 空 candidate 也保存空 summary。
- Store 校验 result 与 manifest config identity。

### 14.3 离线 Replay

新增 `replay_candidate_similarity(candidate, manifest, *, strict=True, similarity_config=None)`：

- 1.3 record：只能使用 manifest config，结果必须与 source 相等；
- 1.3 disabled：返回 not_attempted source view；
- 1.2：caller 必须提供 config，R05 record 数据可直接评估；R05 disabled 数据则 unavailable；
- 1.1：须先显式 R05 replay，不能跳过 R05 猜分类；
- 1.0：须先 R04、R05 replay；任一前置不可用则 unavailable；
- strict 遇 identity/conflict 抛 sanitized error，tolerant 返回 issue/result unavailable。

### 14.4 Sidecar

`ocr_similarity_sidecar.py` 默认写 `<run_dir>/r06-sidecar-<config_digest>.jsonl`：

- 使用 exclusive create，存在则失败，不覆盖；
- 第一行 `r06_sidecar_manifest`，随后按 `(candidate sequence, formal screen_index, screen_id)` 确定顺序写 result；
- 每条保存 source schema/run/candidate/screen ID、source record digest、reference ID、config identity、result；
- 参数 override 只改变 sidecar config identity，不修改源 run manifest；
- strict/tolerant 语义与 replay 一致；
- online 与 offline 对同一 source/config/reference resolution 必须逐字段相同。

## 15. 失败降级

R06 任何异常不得冒泡到 detector、页面或动作：

| 失败 | R06 结果 | 保留 |
|---|---|---|
| 无 ref | `no_reference/unavailable`，pair 数值 null | R03/R04/R05、固定扫描 |
| R04 不可用 | `unavailable` | raw/R03/R05 已有字段 |
| R05 not attempted/failed | `unavailable/partial`，count/ratio/effective null | R03/R04/R05 原状态 |
| 会计差异 | `partial`，count/ratio null，class uncertain | 相似度中可独立验证的部分 |
| evaluator 异常 | `failed`，所有 R06 数值 null，`evaluation_failed` | 完整前序 record |
| Store 失败 | 沿用 Store best-effort/disable | 页面和候选人主流程继续 |

warning 只记录脱敏 code。禁止为 R06 失败触发 OCR、截图、滚动、等待、refresh、next、favorite 或 forward 重试。

## 16. 性能

### 16.1 门槛

**[设计冻结][待校准]** 在 release interpreter、预热 3 次、至少 25 次、inclusive p95 下：

- 单 screen pair（两侧各 20,000 code points、256 segments）：R06 evaluator p95 `<= 15 ms`；
- 8 屏 candidate（7 个正式 pair + 首屏）：R06-only p95 `<= 100 ms`；
- 8 屏 R06 峰值附加内存 `<= 16 MiB`；
- 100,000 codepoint 边界不得崩溃或无界增长；超限必须在建 Counter 前拒绝；
- 相同合成输入 100 次结果完全相同；reference release 后 evaluator 不保留完整 candidate。

### 16.2 benchmark 场景

`tests/benchmark_r06_similarity.py` 至少覆盖：exact same、单字符、双空/单空、20k identical、20k 50% changed、重复 n-gram stress、8×256 segments、all new、all overlap、uncertain partition、short-term protection、UI 3-screen evidence、100k boundary、100001 reject、record projection/finalize、disabled constructor spy、跨进程 SimHash fixture。

禁止把所有历史 screen 两两比较；正式相似度只比较 resolved reference，UI evidence 用 exact-text 索引累计。

## 17. Change 2—7 实施计划

### Change 2：Schema、Reference、配置

**进入条件**：Change 1 三文档批准；本次 Change 2 前置合同 Corrective 获批准；工作区 R05 变更归属明确；R05 Schema/reader 测试通过。

**修改文件**：`ocr_records.py`、新增 `ocr_similarity.py`、`tests/test_ocr_records.py`、`tests/test_ocr_similarity.py`；如只做 constructor 合同，可更新 `tests/test_ocr_candidate.py`。

**实施内容**：1.3 types/fields/from_dict/validation；完整 `ReferenceResolution`、`R06CandidateSummary`、`R06WarningCodeCount` 合同；config snapshot/digest；warning enums（含 `cross_layer_similarity_conflict`）；纯 reference resolver；R03 hash 只读 adapter；旧版正式屏重建规则；第 9.4 节 confidence 参数 identity。

**禁止事项**：不实现 n-gram/SimHash/比例/有效新增；不接 builder/Store/Replay/main；不改 R03/R04/R05。

**测试**：Schema round-trip/field order/null；1.0—1.2 compat；missing/unknown version；ReferenceResolution 三状态与 result 投影；reference 首屏/上一正式屏/缺失/冲突/跨 candidate/非正式显式 ref；空/非空 summary、三组会计、warning 白名单顺序/去重；cross-layer warning；confidence 三参数 snapshot/digest/manifest/replay/旧证据缺失；hash adapter。

**退出条件**：writer 可构造合法 disabled/not_attempted/record 1.3 value types 和空 summary；旧记录全部可读；resolver 不使用顺序；summary 与 warning 会计严格成立；历史 confidence 不被当前默认值替换。

**报告**：`docs/R06-change2-schema-reference-config-report.md`。

### Change 3：n-gram 与 SimHash

**进入条件**：Change 2 通过；算法/config 字段冻结。

**修改文件**：`ocr_similarity.py`、`tests/test_ocr_similarity.py`、新增 `tests/benchmark_r06_similarity.py`。

**实施内容**：特征准备、multiset Dice、权重归一化、空/短/长文本、64-bit stable SimHash/Hamming/辅助分数。

**禁止事项**：不做 R05 计数、有效新增、在线/Store/Replay；不使用 Python hash；不改 detector/normalizer。

**测试**：公式 golden、重复计数、范围、Unicode、空文本、1-char fallback、跨进程/`PYTHONHASHSEED`、100k guard、复杂度 spy、初步 benchmark。

**退出条件**：纯算法确定、范围/空语义正确、初步性能门槛通过。

**报告**：`docs/R06-change3-ngram-simhash-report.md`。

### Change 4：计数、会计和比例

**进入条件**：Change 3 通过；R05 projection 合同测试通过。

**修改文件**：`ocr_similarity.py`、`ocr_records.py`（只补已冻结验证）、`tests/test_ocr_similarity.py`、`tests/test_ocr_records.py`。

**实施内容**：ID map、权威 char count、三分 count、R05 stored projection 交叉验证、numerator/denominator、比例、零分母、浮点容限。

**禁止事项**：不改变 R05 fields/分类/document；不做有效新增或在线接入。

**测试**：all overlap/new/uncertain、mixed、Unicode code points、R05 new 含 uncertain 兼容、partition gap/overlap/unknown ID、accounting mismatch、ratio sum、zero denominator。

**退出条件**：所有合法 fixture 会计严格成立；差异稳定 partial/null，不修改源。

**报告**：`docs/R06-change4-accounting-ratios-report.md`。

### Change 5：有效新增和中性分类

**进入条件**：Change 4 通过；短词/regex/UI 参数人工确认。

**修改文件**：`ocr_similarity.py`、`ocr_records.py`（只补已冻结 value validation）、`tests/test_ocr_similarity.py`、`tests/benchmark_r06_similarity.py`。

**实施内容**：逐 segment 决策序列、evidence codes、短文本保护、UI 组合证据、有界 candidate context、effective status、comparison class priority；R05 matched split/merge evidence只保留在 R05，r06-v1 不输出 `split_merge_artifact`。

**禁止事项**：不建 UI 黑名单；不调用 AI；不控制扫描；证据不足不判无效。

**测试**：每个可发射 reason 正/反例；全部保护词、年份/日期/版本/范围；公司/项目/岗位未知短词 uncertain；UI 2 屏不足/3 屏几何满足/冲突；class 全矩阵和优先级；R05 matched 的 1→2/2→1 evidence 不生成 `EffectiveNewDecision`；合法 R05 new 没有 split/merge evidence且永不输出 `split_merge_artifact`；new/uncertain 非法出现在 match evidence 时触发前序合同冲突并停止有效新增分类。

**退出条件**：每个结论可追溯，保护清单全过，unknown 保守，中性类不含动作语义。

**报告**：`docs/R06-change5-effective-new-classification-report.md`。

### Change 6：在线、JSONL、Replay 和统计

**进入条件**：Changes 2—5 通过；R05 record mode/Change 7 获独立批准；若未批准，只允许完成 disabled 与离线接线，不允许生产 record 激活。

**修改文件**：`ocr_candidate.py`、`ocr_store.py`、`ocr_replay.py`、`simple_brush.py`、新增 `ocr_similarity_sidecar.py`、`ocr_records.py`（冻结字段最终接线）；测试更新 `test_ocr_candidate.py`、`test_ocr_store.py`、`test_ocr_replay.py`、`test_ocr_stage0_integration.py`、`test_simple_brush_ocr.py`、`test_ocr_similarity.py`。

**实施内容**：builder 单次 evaluator；reference hint 持久化；screen/candidate/manifest identity；candidate summary；strict/tolerant replay；sidecar；config override；fail-open；生产默认 disabled。

**禁止事项**：不改 OCR/截图/滚动/等待/动作；不启用 R07；不真实运行；不把阈值放进 control flow。

**测试**：online/offline equality；一次计算；JSONL field order/round-trip；manifest mismatch；old schema sidecar；candidate isolation/finalize release；Store failure；disabled no constructor；页面 spy 全不变量；日志隐私。

**退出条件**：所有数据落在现有体系；source/config 等价；失败不影响业务；生产默认仍 disabled。

**报告**：`docs/R06-change6-integration-replay-sidecar-report.md`。

### Change 7：完整验收

**进入条件**：Change 6 通过；无未归属 tracked diff；R05 前置状态明确；测试数据授权明确。

**修改文件**：只允许 `tests/test_ocr_similarity.py`、`tests/benchmark_r06_similarity.py` 和验收报告；发现生产缺陷停止并另开 corrective Change。

**实施内容**：全量回归、性能、跨进程、Unicode、Windows/macOS 平台中立、隐私、日志/data 隔离、Git 审计；真实页面默认 NOT RUN。

**禁止事项**：不改生产算法/阈值/Schema/配置/依赖/build/workflow；不启用 record；不实现 R07/AI/SQLite；不 commit/push/tag/release。

**测试**：全量 unittest；阶段0、R03、R04+benchmark、R05+benchmark、Store、Replay、load、switch、main loop、rule、favorite/forward、ESC/timer、Windows/macOS、Unicode、compileall、pip check、diff check；R06 benchmark 全矩阵；r06-v1 split/merge boundary contract（matched evidence 无 decision、合法 new never emitted、非法 evidence relation fail-open）。

**退出条件**：所有门槛通过或明确阻塞；日志/data 前后完全一致；最终 Git 仅允许获批文件。

**报告**：`docs/R06-ocr-page-similarity-effective-new-content-acceptance-report.md`。

## 18. 停止条件和前置阻塞

后续任一 Change 遇到下列情况必须停止：

- exact hash 出现第二实现或无法追溯；
- R04 comparison text/segment 不稳定；
- R05 三分集合不是权威完整 partition；
- 计数无法复算；
- reference 只能靠顺序猜；
- 旧 Schema 无法稳定读；
- online/offline 不能共用 evaluator；
- R06 对 R05 new/uncertain 重建、猜测或伪造 split/merge，或将合法 matched split/merge evidence 当作 new-side decision；
- 必须修改 R03/R04/R05 生产语义才能实现；
- 测试污染真实日志/data；
- 工作区 tracked 修改无法归属。

当前已知前置：R05 生产默认 disabled，Change 7 历史报告为 blocked，且工作区 R05 实现未提交。它不阻塞本 Change 1 文档，但阻塞 R06 Change 6 的生产 record 激活和 Change 7 正式在线验收。

## 19. 明确声明

本 TID 没有实施 R06 Schema、n-gram、SimHash、比例、有效新增、在线接入、R07、AI 或 SQLite。所有文件/字段/阈值仅为后续获批 Change 的冻结计划。
