# BossOCR R05 技术实施设计：OCR 多屏新增内容识别与全文聚合

## 设计状态与判定标签

本文是 R05 的冻结实施设计，目标读者是没有本次会话上下文的后续 Codex/Terra。维护者批准前不得进入 Change 1；任何 Change 完成后必须停止，禁止自动进入下一 Change。

技术结论使用以下标签：

- **[仓库确认]**：由当前代码、测试、Git 或持久化数据直接确认。
- **[需求冻结]**：产品范围要求，实施不得偏离。
- **[首版保守默认]**：缺少受治理真实样本时冻结的安全默认；Terra 不得自行调整。
- **[待真实样本验证]**：不阻塞纯函数/自动化实施，但阻塞生产 shadow 或正式验收。
- **[明确禁止]**：超出 R05 范围或会破坏既有不变量。

为避免在伪代码和大型表格中机械重复标签，以下继承规则也是本文契约：仓库基线/“当前职责”事实默认继承 **[仓库确认]**；含“必须/不得/禁止/冻结”的规范默认继承 **[需求冻结]** 或 **[明确禁止]**；第 11、23 节新增数值默认继承 **[首版保守默认][待真实样本验证]**。其余真正未决事项只允许出现在第 30 节门禁中。

## 1. 仓库基线

勘察日期为 2026-08-01，基线如下：

| 项目 | 已确认事实 |
| --- | --- |
| 分支 | `main`，与 `origin/main` 同步 |
| HEAD | `6987b19dfb5f1523b1789564a7e2d6dbc76fba86` |
| R04 提交 | `6987b19 feat(ocr): implement R04 normalization and legacy shadow` |
| 前序相关提交 | `54ae064 fix(ocr): reset candidate recording after load recovery`；`ba0eb4d` Stage 0；`8be06ce` R03 |
| Git 工作区 | 无 tracked diff；既有未跟踪 `docs/project-review.zip`、`venv-packages-before-reinstall.txt`，必须保持不动 |
| 完整测试 | `python -m unittest discover -s tests -v`：594/594，`OK` |
| 当前 Schema | `1.1.0`；兼容读取 `1.0.0` |
| R04 identity | `r04-v1` / `r04-config-v1` / `3597727e595b16c3aba7bfa41653b617f11277e78ce52379c99ee3afafcb84d5` |
| R03 identity | `r03-v1` exact fingerprint；输入、算法和版本与 R04/R05 隔离 |
| Candidate document | `stage0-v1`；document 字段仍为 `not_implemented` 占位 |
| 正式平台 | Windows；`simple_brush.py` 顶层依赖 Windows/GUI 库 |
| 动作权威 | `legacy_shadow` 是唯一在用 R04 模式；legacy 结果独占动作权威 |
| 日志边界 | 普通日志只允许脱敏 metadata；JSONL 是单独的敏感运行数据 |

**[仓库确认]** 当前 R04 基准重跑结果包括：100 boxes p95 3.0532 ms，500 boxes p95 16.9182 ms，所有场景 deterministic。直接用脚本路径运行会因调用目录下的导入路径失败；可从仓库根目录用 `python -c`/模块上下文执行，R05 新基准必须提供不依赖调用目录的稳定入口。

**[仓库确认][待真实样本验证]** `data/ocr_runs` 当前只有一个 run 目录，`run.json`、`screens.jsonl`、`candidates.jsonl`、`errors.jsonl` 均为 0 字节；R04 Acceptance Report 存在并通过代码/自动化验收，但未完成正式 Windows real shadow。因此没有可用于 R05 阈值校准的正式历史数据。

## 2. 当前架构映射

| 需求概念 | 仓库类/函数 | 文件/位置 | 当前职责 | R05 修改 |
| --- | --- | --- | --- | --- |
| OCR box | `OcrBox` | `ocr_records.py` | raw text、confidence、bbox、original/screen index | 不改语义 |
| R04 输入 box | `NormalizationBox` | `ocr_normalization.py` | pure normalizer 输入 | 不改 |
| R04 screen result | `TextNormalizationResult`、`normalize_ocr_text()` | `ocr_normalization.py:1565` | 排序、标准化、同屏 duplicate、视觉行 | 不改 |
| R04 segment | `OcrTextSegment` | `ocr_records.py`；`normalization_record_fields()` | 持久化视觉行、comparison、box 来源 | 直接复用为 screen segment |
| screen record | `OcrScreenRecord` | `ocr_records.py:440` | 一次 capture 的 raw/R03/R04 及后续占位字段 | 增加 R05 状态/ID/evidence |
| candidate document | `CandidateOcrDocument` | `ocr_records.py:859` | 候选人 screens 快照与尚未实现的 document 字段 | 激活 document 语义、新 document segment |
| candidate builder | `CandidateOcrBuilder` | `ocr_candidate.py:245` | 当前候选人 screen 构建、attempt 计数、one-shot finalize | 组合一个纯 R05 aggregator |
| R04 投影 | `normalization_record_fields()` | `ocr_candidate.py:100` | `TextNormalizationResult` → record fields/视觉行 | 输入适配点，不重算 R04 |
| Store | `OcrRecordStore`、`JsonlOcrRecordStore` | `ocr_store.py:46,71` | append-only screen/candidate/error JSONL | 只接受完整 1.2 record |
| Run identity | `RunManifest` | `ocr_records.py:969` | schema、R04 config、计数和文件身份 | 增加 R05 config identity |
| Replay | `load_ocr_run()` | `ocr_replay.py:522` | strict/tolerant 读取，返回 source records | 扩展 1.2 读取 |
| R04 replay | `replay_screen_normalization()` | `ocr_replay.py:383` | 用同一 normalizer 显式重算 R04 | 保持不变 |
| AI payload | 不存在 | 全仓库搜索 | 无 `build_ai_payload()`；无审核字段接口 | 维护者批准后才新增纯函数 |
| 正式屏判定 | `CaptureType.FORMAL_SCREEN` + `is_formal_screen` | `ocr_records.py`、`simple_brush.py:717` | capture 分类和记录 | 双条件严格 gate |
| 在线 capture | `OcrDetector.capture_observation()` | `ocr_detector.py:610` | 一次截图/OCR，同时形成 R03/R04 结果 | 不改 |
| 扫描循环 | `OcrDetector.detect()` | `ocr_detector.py:725` | 最多 8 屏、confirmation、滚动 | 不改 |
| screen 保存点 | `record_ocr_observation()` | `simple_brush.py:717` | builder 构建后立即 `save_screen()` | R05 必须在此保存前完成 |
| builder 创建 | `start_candidate_ocr_recording()` | `simple_brush.py:691` | store enabled 时每候选人创建一次 | 不跨候选人 |
| candidate finalize | `finalize_current_candidate_recording()` | `simple_brush.py:819` | 清全局引用、builder finalize、save candidate | 聚合 finalize 接入点 |
| ESC/异常 finalize | `finalize_active_candidate_for_stop()` | `simple_brush.py:855` | 映射 interrupted/aborted 并结束当前 builder | 保持调用时机 |

**[仓库确认]** `ocr_detector.ScanObservation` 同时携带同一次 OCR 的 raw items、R03 fingerprint 与 R04 normalization；online/offline R04 都调用 `normalize_ocr_text()`。R04 segment ID 为 `{screen_id}:line:{order}`，来源 box 覆盖可稳定验证。

**[明确禁止]** 不增加第二套 screen/record/store/replay 系统，不修改 `ocr_detector.py` 的 capture、OCR 或滚动调用链。

## 3. 最终数据流

### 3.1 在线

**[需求冻结]** 下列聚合调用流只在显式 `R05_AGGREGATION_MODE="record"` 时运行。首次实现合并后的生产默认值是 `disabled`；disabled 必须在创建/调用 `CandidateDocumentAggregator` 前短路，只生成符合 `not_attempted` 合同的 R05 空状态，不执行聚合算法。

冻结调用流如下：

```text
OcrDetector.capture_observation()
  -> 已有 TextNormalizationResult
record_ocr_observation()
  -> CandidateOcrBuilder.build_screen_record()
     -> normalization_record_fields()              # 只投影 R04
     -> 构造尚未保存的 OcrScreenRecord
     -> CandidateDocumentAggregator.add_screen()   # pure R05
     -> dataclasses.replace(record, R05 fields)     # 形成最终不可变 record
     -> builder 才把最终 record 加入 _screens
  -> JsonlOcrRecordStore.save_screen(final_record)
finalize_current_candidate_recording()
  -> CandidateDocumentAggregator.finalize()
  -> CandidateOcrBuilder.finalize()
  -> JsonlOcrRecordStore.save_candidate(document)
build_ai_payload(document)                          # 仅显式调用；主流程不自动调用
```

**[需求冻结]** screen R05 结果必须在第一次且唯一一次 `save_screen()` 前完成。append-only JSONL 不允许保存后补字段、原地改行或另写补丁 record。

### 3.2 离线

```text
load_ocr_run(strict=...)
  -> 读取 manifest/screens/candidates，不改 source
replay_candidate_aggregation(candidate, manifest, strict=...)
  -> resolve_aggregation_config(manifest)
  -> adapt_r04_screen_segments()
  -> 与在线相同 CandidateDocumentAggregator.add_screen()/finalize()
  -> CandidateAggregationReplay（内存派生结果 + issues）
```

**[需求冻结]** 在线/离线共用 `ocr_aggregation.py` 中的 config canonicalization、adapter、字符计数、exact、fuzzy、historical、add/finalize 纯函数。Replay 不得复制算法。

**[明确禁止]** R05 replay 不调用 OCR、截图、页面、AI，也不写回源 run。

## 4. 类型复用决策

1. **[仓库确认]** 仓库已有 frozen `OcrTextSegment`。
2. **[仓库确认]** 它由 R04 `normalized_lines` 投影，是视觉行，不是语义段落。
3. **[需求冻结]** R05 直接复用它作为 screen segment；禁止重新分行或生成平行 screen segment。
4. **[需求冻结]** 新增 frozen `OcrDocumentSegment`，因为文档单元必须保存候选人级 order、稳定 ID 和多 source occurrences；现有 `OcrTextSegment` 无法表达这些语义。
5. **[需求冻结]** screen segment 只属于一个 screen，ID 与 R04 不变；document segment 只属于一个 candidate，可能由多个 screen segment 共同证实。
6. **[需求冻结]** `CandidateOcrDocument.document_segments` 从 `Tuple[OcrTextSegment, ...]` 升级为 `Tuple[OcrDocumentSegment, ...]`，旧 `stage0-v1` 仍按旧类型读取；不另建 `R05CandidateDocument`。

新增记录类型放在 `ocr_records.py`：

```python
@dataclass(frozen=True)
class OcrSourceOccurrence:
    occurrence_order: int
    source_screen_id: str
    source_screen_index: int
    source_segment_ids: Tuple[str, ...]
    source_ocr_box_ids: Tuple[str, ...]
    occurrence_role: AggregationOccurrenceRole
    match_id: Optional[str]

@dataclass(frozen=True)
class OcrDocumentSegment:
    document_segment_id: str
    order: int
    normalized_text: str
    comparison_text: str
    comparison_char_count: int
    source_occurrences: Tuple[OcrSourceOccurrence, ...]
```

`occurrence_role` 仅为 `origin`、`matched`、`uncertain_origin`。document segment 正文永远来自首次创建它的 screen segment；后续 occurrence 不改正文。

## 5. Segment ID 与来源规则

### 5.1 Screen segment

**[仓库确认]** 沿用 R04 `{screen_id}:line:{zero_based_order}`。R05 必须验证 ID、order、`screen_index`、`comparison_text` 和 `ocr_box_ids` 与 screen record 一致，不得重编号。

### 5.2 Document segment

**[需求冻结]** ID 为 `document:segment:{zero_based_order}`，作用域是 `candidate_record_id`。全局引用使用 `(candidate_record_id, document_segment_id)`。禁止 UUID、时间、随机数或文本 hash；相同文字在不同合法位置获得不同 order/ID。

### 5.3 Match ID

**[需求冻结]** ID 为 `match:{screen_index}:{zero_based_match_order}`，同样以 candidate 为作用域。它只标识当前 screen 的一组映射，不参与 segment 身份。

### 5.4 来源与稳定性

- 每个新 document segment 的首个 occurrence 必须引用一个且仅一个 source screen segment 及其完整 `ocr_box_ids`。
- 1→2 occurrence 可含两个当前 source segment ID；2→1 的同一个当前 segment occurrence 可分别附到两个 document segment，并共享 match ID。
- `source_ocr_box_ids` 按 screen segment 顺序展开、首次出现去重；不得排序为 set。
- replay 用候选人内顺序重新生成相同 document/match ID，不使用当前时间。
- 输入 record、R04 segment、raw box 和 bbox 全部不可变。

## 6. `char_count` 口径

**[需求冻结]** R05 唯一字符函数放在 `ocr_aggregation.py`：

```python
def aggregation_char_count(comparison_text: str) -> int:
    return len(comparison_text)
```

调用前必须验证 `comparison_text == build_comparison_text(normalized_text)`。R04 `build_comparison_text()` 已做 NFKC、lower 并删除 Unicode whitespace；因此 R05 计数是去 whitespace 后的 Python Unicode code point 数，不是 UTF-8 bytes、UTF-16 units 或 grapheme 数。

**[仓库确认]** R04 `OcrTextSegment.char_count` 当前是可读 `normalized_text` 长度。R05 不改变它，也不把它用于阈值；新增 `OcrDocumentSegment.comparison_char_count` 与 screen R05 count 均调用上述函数，避免悄悄重释 R04 字段。

**[需求冻结]** R06 若需要相同口径，必须显式复用该公开函数；R05 不提前计算 R06 ratio。

## 7. 正式屏幕选择

### 7.1 进入条件

`is_r05_formal_screen(record)` 必须同时检查：

```python
record.capture_type is CaptureType.FORMAL_SCREEN
and record.is_formal_screen is True
and record.run_id == aggregator.run_id
and record.candidate_record_id == aggregator.candidate_record_id
and isinstance(record.screen_index, int)
and 1 <= record.screen_index <= manifest.max_screen_count  # 当前为 8
```

任一不成立时不得把 segment 加入全文。非正式 capture 持久化 `aggregation_status=not_attempted`，R05 identity/null、分类 tuple 为空、R05 text/count/risk 为 null；R04/R03/raw 字段不变。

**[仓库确认]** 实际 `CaptureType` 为 `formal_screen/load_check/load_retry/switch_check/scroll_confirmation/scroll_retry/other`；没有单独的 `switch_recovery` 值，恢复路径继续使用已有 load/switch capture，二者均不得进入全文。

### 7.2 顺序与重复

- **[仓库确认]** `screen_index` 是当前候选人的正式扫描序号 1—8；confirmation 可能复用 scan number，但 `is_formal_screen=false`。
- **[仓库确认]** 当前 `recorded_observation_ids` 只按 Python observation 对象身份避免同一对象重复保存，`CandidateOcrBuilder` 尚无 durable `screen_id` 去重；R05 必须补充候选人内 ID/index 检查，但不改变已有 prefetched observation 复用。
- **[需求冻结]** 正常 online 输入必须严格递增。首个出现的 `(screen_index, screen_id)` 是 append-order 权威。
- 相同 `screen_id`、相同完整输入重复 add：幂等跳过，不重复聚合或保存。
- 相同 `screen_id`、内容不同：首条不覆盖；记录 `duplicate_screen_id_conflict`，candidate partial，第二条不保存为另一正式 screen。
- 不同 `screen_id`、相同 `screen_index`：两条 screen evidence 均可保存；首条是 index 权威，后条不得执行抑制，全部非空 segment 作为 uncertain 追加，screen/candidate partial、risk elevated。
- out-of-order online 输入：保留 screen evidence，全部 segment uncertain 追加，禁止用错误边界抑制。
- strict replay 对 duplicate index、ID 冲突或乱序直接失败。
- tolerant replay 以 candidate 内 `screens` tuple 的原位置为 tie-breaker，先按 `(screen_index, original_position)` 稳定排序；首条为 index 权威，后续冲突按 uncertain 追加并产生 issue，candidate partial。

**[仓库确认]** candidate 内嵌 `screens` tuple 决定候选人成员关系，是 candidate replay 的权威；run-level `screens.jsonl` 只用于存在时的交叉校验。orphan run-level screen 不自动加入某 candidate；两份相同 ID 的内容不一致时 strict 失败，tolerant 使用 candidate 内嵌首条并报 issue。由于既有 best-effort Store 可能先丢失 screen append、后成功保存自足的 candidate，run-level 缺少对应 screen 不阻止 candidate 聚合；完整性审计可单独报告缺行。

## 8. R05 状态机

### 8.1 Screen `AggregationStatus`

| 值 | 含义 | 主要不变量 |
| --- | --- | --- |
| `not_attempted` | 非正式、旧 schema 或 R05 disabled | 无 version/config、分类/evidence 为空、text/count/risk null |
| `completed` | 全部 segment 已确定分类，无 R05 warning | version/config 完整；每个非空 R04 segment 恰属 matched/new；uncertain 为空 |
| `partial` | 内容安全保留，但存在 uncertain、顺序/重复异常或某阶段 fail-open | version/config 完整；每个可用 segment 恰属 matched/new/uncertain；uncertain 全部贡献正文 |
| `failed` | R04 未完成或无法建立可信 segment 映射 | 不生成 match/new/uncertain；保留 raw/R04 evidence；固定 warning 非空 |

R04 completed 空屏可为 R05 `completed` 且分类为空。`partial` 不代表内容缺失，而是“不允许把某些当前内容抑制”。

### 8.2 Candidate `DocumentBuildStatus`

| 值 | 含义 | 文档字段 |
| --- | --- | --- |
| `not_attempted` | 无正式 screen、旧 schema 或 aggregation disabled | `document_text=None`，segments 空 |
| `completed` | 至少一正式 screen，所有参与 screen completed；正常 capture 完成 | segments 权威；合法空文档为 `""` |
| `partial` | 至少一个安全输入可建文档，但 screen partial/failed、ESC、abort 或顺序异常 | segments/text 必须一致；warning/risk 非空 |
| `failed` | 有正式输入但没有任何可安全构建的 screen，或 finalize 不变量失败 | `document_text=None`，segments 空，不伪造 fallback |

若存在已建 document segment，则 candidate 不得为 failed；若只有 R04 completed 空屏，可 completed/partial 空文档。capture status 为 `interrupted/aborted` 时即使 screens 均完成，document 也标为 partial，反映候选人采集不完整。

**[需求冻结]** `NormalizationStatus` 枚举与 R04 字段完全不改；绝不添加 R04 partial。

## 9. Exact overlap 算法

### 9.1 输入与证据门槛

只取当前 document 尾部和 current screen 头部的 `comparison_text` key。最大候选长度为 `min(len(document_segments), len(current_segments), max_screen_segments)`，从大到小。

常规候选可接受条件：

```text
k >= exact_min_segment_count (=2)
min(tail_chars, head_chars) >= exact_min_char_count (=24)
至少一个 current segment 字符数 > short_segment_char_threshold (=8)
```

单行例外只用于“当前屏仅一个非空 segment 且整个屏与 document 尾行重复”，并要求至少 48 字符。任何其他单行 exact 不抑制。

### 9.2 冻结伪代码

```python
def find_exact_boundary(document, current, config):
    doc_keys = tuple(seg.comparison_text for seg in document)
    cur_keys = tuple(seg.comparison_text for seg in current)
    max_k = min(len(doc_keys), len(cur_keys), config.max_screen_segments)
    longest_inadmissible = 0

    for k in range(max_k, 0, -1):
        if doc_keys[-k:] != cur_keys[:k]:
            continue
        if normal_exact_evidence(k, document[-k:], current[:k], config):
            return exact_match(k, basis="comparison_sequence_equal")
        if (
            k == 1
            and len(cur_keys) == 1
            and aggregation_char_count(cur_keys[0])
                >= config.exact_single_segment_min_char_count
        ):
            return exact_match(1, basis="single_full_screen_equal")
        longest_inadmissible = max(longest_inadmissible, k)

    return no_match_with_uncertain_prefix(longest_inadmissible)
```

`longest_inadmissible` 大于 0 时，对应 current 头部具有“看似重复但证据不足”的事实，必须分类 uncertain 并追加，不能降为普通 new。fuzzy 的 1→1 exact-equal 候选不得绕过这里的短文本/单行保护。

命中后，current 头部 k 个 segment 一对一映射到 document 尾部 k 个 segment；每个 document segment 追加 matched occurrence；screen evidence 的 `match_type=adjacent_exact`、`score=None`、`exact_basis=comparison_sequence_equal|single_full_screen_equal`。exact 一旦接受，本屏不再运行相邻 fuzzy；剩余 current segment 只进入 historical/new 处理。只有 exact 没有可接受候选时才运行 fuzzy。

### 9.3 确定性与复杂度

最长 k 唯一决定 tie-breaker，不搜索文档中间。预先计算 key/char count；tuple 比较的最坏 segment-key 工作量为 O(S²)，`S<=256`，内存 O(S)。禁止使用 set 或全文 `find()`。

## 10. Fuzzy overlap 算法

### 10.1 允许范围

**[需求冻结]** R04 禁止模糊 OCR box 删除，因为同屏空间证据不足时误删风险高；R05 只在相邻滚动边界、连续单调、小窗口和高证据下识别同一内容再次出现，两者不冲突。

使用标准库 `difflib.SequenceMatcher(autojunk=False)`。输入是 R04 `comparison_text`；同组多个 segment 用 LF 拼接。R04 comparison 已移除所有 whitespace，因此 LF 不会与正文冲突，并保留行边界信号。原 `normalized_text` 不修改。

人工插入的 LF 有且只有“为 `SequenceMatcher` 保留视觉行边界信号”的职责。它可以保留在 matcher 输入和 matching blocks 中，但不是 OCR 正文字符；R05 的 fuzzy 长度、消费量、排序权重、unmatched 和阈值判断必须排除该 LF。冻结辅助函数语义：

```python
FUZZY_LINE_SEPARATOR = "\n"

def fuzzy_content_char_count(value: str) -> int:
    return sum(1 for character in value if character != FUZZY_LINE_SEPARATOR)

def fuzzy_unmatched_content_count(value: str, unmatched_ranges) -> int:
    return sum(
        fuzzy_content_char_count(value[start:end])
        for start, end in unmatched_ranges
    )
```

R04 `comparison_text` 自身不含正文换行；出现于 fuzzy 拼接值中的 LF 只能由 R05 内部加入。LF 可以参与 `SequenceMatcher` 的相似度/匹配块计算，但不得增加或减少正文字符数，不得单独导致 unmatched 超过 2，也不得把 1→2/2→1 的纯行边界变化记作 OCR 字符差异。

允许组形状固定为 `(1,1)`、`(1,2)`、`(2,1)`；每组左右 segment 数之和不超过 3。不允许 2→2 或一般 N→M。

### 10.2 候选生成伪代码

```python
ALLOWED_STEPS = ((1, 1), (1, 2), (2, 1))

def fuzzy_boundary_candidates(document, current, config):
    tail = document[-config.fuzzy_max_tail_segments:]
    head = current[:config.fuzzy_max_head_segments]
    candidates = []

    # d/c 是必须完整消费的尾部/头部长度；路径连续、单调。
    for d in range(1, len(tail) + 1):
        for c in range(1, len(head) + 1):
            for path in enumerate_tilings(d, c, ALLOWED_STEPS):
                groups = []
                eligible = True
                for left_count, right_count, left_span, right_span in path:
                    left_text = "\n".join(x.comparison_text for x in left_span)
                    right_text = "\n".join(x.comparison_text for x in right_span)
                    if (left_count, right_count) == (1, 1) \
                            and left_text == right_text:
                        # 不得绕过 exact 的单行/短证据保护。
                        eligible = False
                        break
                    left_content_chars = fuzzy_content_char_count(left_text)
                    right_content_chars = fuzzy_content_char_count(right_text)
                    if min(left_content_chars, right_content_chars) \
                            < config.fuzzy_min_char_count:
                        eligible = False
                        break
                    if max(left_content_chars, right_content_chars) \
                            > config.fuzzy_max_group_char_count:
                        eligible = False
                        break
                    matcher = SequenceMatcher(None, left_text, right_text,
                                              autojunk=False)
                    score = matcher.ratio()
                    left_ranges, right_ranges = unmatched_ranges(matcher)
                    left_unmatched = fuzzy_unmatched_content_count(
                        left_text, left_ranges
                    )
                    right_unmatched = fuzzy_unmatched_content_count(
                        right_text, right_ranges
                    )
                    groups.append((score, left_unmatched, right_unmatched))
                if eligible:
                    candidates.append(score_path(path, groups))
                if len(candidates) > config.fuzzy_candidate_limit:
                    return candidate_limit_exceeded()
    return candidates
```

LF 仅作 matcher 行分隔，`fuzzy_content_char_count()` 和 `fuzzy_unmatched_content_count()` 均不计算 LF。候选必须以 document 末尾结束、以 current 开头开始，不允许跳 segment 或逆序。

### 10.3 接受、排序与灰区

每组必须同时满足：

- score `>=0.94`；
- 两侧正文字符均 `>=32`；
- 每侧 unmatched 正文字符 `<=2`；
- 组文本长度各 `<=512`。

路径总分按 `max(left_content_chars, right_content_chars)` 加权平均；这里及下列排序中的“字符”一律是排除人工 LF 的正文字符。候选排序键固定为：

1. 消费 current 比较字符更多；
2. 消费 current segment 更多；
3. 消费 document 比较字符更多；
4. 加权 score 更高；
5. group 更少；
6. 形状序列按 `(1,1) < (1,2) < (2,1)` 字典序。

前 3 项消费证据和 group 数相同、score 差不超过 `0.005` 且映射不同，视为同分冲突：不得用最后的字典序强行抑制，只用它稳定记录候选，涉及的 current prefix 全部 uncertain 并追加。`0.88 <= score < 0.94`，或 score 达标但 unmatched/长度保护失败，均为灰区 uncertain。低于 0.88 且无其他重复证据视为 new。

接受路径按组生成 `adjacent_fuzzy_1_1`、`adjacent_fuzzy_1_2` 或 `adjacent_fuzzy_2_1` evidence。2→1 的 current occurrence 同时附到两个历史 document segment；1→2 的两个 current segments 作为一组 occurrence 附到一个历史 document segment。冲突新内容不得被截断：R05 只能保留或抑制完整 screen segment 组。

### 10.4 上界

tail/head 各最多 4，允许形状固定，候选硬上限 128，每组文本最多 512 字符。任何上限触发都停止 fuzzy，对未决前缀保留为 uncertain；禁止继续退化到全文 pair matrix。

## 11. 阈值冻结

所有值属于 frozen `OcrAggregationConfig`，位于 `ocr_aggregation.py`；canonical snapshot 使用稳定字段顺序，digest 为小写 SHA-256 hex。除 `max_formal_screen_count` 是仓库既有值外，以下均为 **[首版保守默认][待真实样本验证]**：

| 字段 | 值 | 依据/行为 |
| --- | ---: | --- |
| `max_formal_screen_count` | 8 | [仓库确认] 当前 detector 固定上限 |
| `max_screen_segments` | 256 | 安全上限；超限保留 uncertain |
| `exact_min_segment_count` | 2 | 防止单个标题/职责误删 |
| `exact_min_char_count` | 24 | 两行仍需足够总证据 |
| `exact_min_nonshort_segment_count` | 1 | 至少一行大于短行阈值 |
| `exact_single_segment_min_char_count` | 48 | 仅完整单行屏重复例外 |
| `short_segment_char_threshold` | 8 | `<=8` 视为短 segment |
| `fuzzy_similarity_threshold` | 0.94 | 高阈值才抑制 |
| `fuzzy_uncertain_similarity_floor` | 0.88 | 灰区下限；只保留 |
| `fuzzy_tie_epsilon` | 0.005 | 近同分且映射冲突不抑制 |
| `fuzzy_min_char_count` | 32 | 每组两侧最小正文字符；不计人工 LF |
| `fuzzy_max_tail_segments` | 4 | 只看 document 尾部 |
| `fuzzy_max_head_segments` | 4 | 只看 current 头部 |
| `fuzzy_max_combined_segments` | 3 | 单组左右合计；限定 1↔2 |
| `fuzzy_max_unmatched_chars_per_side` | 2 | 每侧 unmatched 正文字符；不计人工 LF |
| `fuzzy_max_group_char_count` | 512 | 每侧正文字符上限；不计人工 LF；限制 SequenceMatcher 输入规模 |
| `fuzzy_candidate_limit` | 128 | 超限 fail-open |
| `historical_min_segment_count` | 2 | 禁止单行历史去重 |
| `historical_max_segment_count` | 4 | 有界 sequence index |
| `historical_min_char_count` | 48 | 历史抑制需要更强证据 |
| `historical_context_anchor_count` | 2 | 必须前后两个外部 exact 锚点 |

**[需求冻结]** Terra 不得增加隐藏常量或自行改值。任何输出相关字段变化都要升级 `aggregation_config_version` 并生成新 digest；真实样本校准必须作为维护者批准的独立 Change。

## 12. 历史保守重复检查

### 12.1 首版规则

**[需求冻结]** 首版只允许 exact historical；fuzzy historical 明确禁止。检查对象是 adjacent 阶段后仍未分类的 current 连续 segment。

构建 candidate-local sequence index：对已存在 document 中长度 2—4 的连续 comparison key tuple 建立 `key -> tuple[start_order]`。每次追加新 document segment 后增量更新包含新尾部的 key；时间 O(D×3)，空间 O(D×3)，其中 D 最大 2048。

### 12.2 冻结伪代码

```python
def classify_historical(document, current_remaining, index, config):
    classifications = all_new()
    for length in range(config.historical_max_segment_count,
                        config.historical_min_segment_count - 1, -1):
        for current_start in stable_current_order(current_remaining, length):
            span = current_remaining[current_start:current_start + length]
            key = tuple(x.comparison_text for x in span)
            if sum(aggregation_char_count(value) for value in key) \
                    < config.historical_min_char_count:
                continue
            if any(char_count(x.comparison_text)
                   <= config.short_segment_char_threshold for x in span):
                mark_uncertain_if_candidate_exists(span)
                continue
            positions = index.get(key, ())
            positions = exclude_adjacent_tail_positions(positions, document)
            if len(positions) != 1:
                if positions:
                    mark_uncertain(span, "historical_duplicate_ambiguous")
                continue
            history_start = positions[0]
            if not has_exact_external_anchor_before(
                    document, history_start, current_remaining, current_start):
                mark_uncertain(span, "historical_context_insufficient")
                continue
            if not has_exact_external_anchor_after(
                    document, history_start + length,
                    current_remaining, current_start + length):
                mark_uncertain(span, "historical_context_insufficient")
                continue
            if overlaps_existing_classification(span):
                mark_uncertain(span, "historical_mapping_conflict")
                continue
            suppress_one_to_one(span, document[history_start:history_start+length],
                                match_type="historical_exact")
    return classifications
```

两个锚点是 matched span 外紧邻的一前一后 current segment，并分别与历史位置外紧邻 document segment exact 相同。current 或历史位于边界、缺任一锚点时不得抑制。全短序列、技能词/模块标题的孤立重复、token 列表、常见短句、来源多于一处、不同上下文或需要语义判断的重复全部 uncertain 或 new。算法不识别公司/项目语义；正因如此，不能绕过双锚点用文本相同作结论。

历史匹配一对一追加 occurrence/evidence，不能改历史正文。处理候选按 length 降序、current_start 升序；任何重叠分类冲突均保留，不用贪心删除合法文本。

## 13. Source occurrence 与 match history

### 13.1 Match evidence 模型

在 `ocr_records.py` 新增：

```python
@dataclass(frozen=True)
class OcrSegmentMatchEvidence:
    match_id: str
    match_type: AggregationMatchType
    current_screen_id: str
    current_screen_index: int
    current_segment_ids: Tuple[str, ...]
    current_ocr_box_ids: Tuple[str, ...]
    matched_document_segment_ids: Tuple[str, ...]
    score: Optional[float]
    exact_basis: Optional[str]
    risk: AggregationDuplicateRisk
    warning_codes: Tuple[str, ...]
```

枚举值：

- `AggregationMatchType`: `adjacent_exact`、`adjacent_fuzzy_1_1`、`adjacent_fuzzy_1_2`、`adjacent_fuzzy_2_1`、`historical_exact`。
- `AggregationDuplicateRisk`: `none`、`low`、`elevated`。exact accepted=`none`；fuzzy accepted=`low`；任何 uncertain/顺序/重复异常=`elevated`。screen/candidate risk 取其内容/子项最大值。

**[仓库确认]** `OcrScreenRecord.duplicate_risk` 已属于 R04 同屏 duplicate 灰区语义，R05 不得复用或改义；新增字段必须命名 `aggregation_duplicate_risk`。

### 13.2 保存位置与一致性

- 每个 `OcrScreenRecord` 保存本屏 `match_evidence`，因此 screen JSONL 在 append 时即自足。
- `CandidateOcrDocument.screens` 已内嵌同一 screen records；candidate 不再额外复制第三份 match history。
- `OcrDocumentSegment.source_occurrences` 保存来源，`match_id` 引用内嵌 screen evidence。
- 所有上述字段进入 JSONL；纯算法索引、SequenceMatcher 对象、候选 score 排序表只在内存。
- source occurrence 再次看到时按 screen/order 追加；不得修改、合并或重排旧 occurrence。
- score 仅 fuzzy 使用，范围 `[0,1]`；exact 的 `score=None` 且 `exact_basis` 必填。禁止用 `1.0` 混淆 exact 与 fuzzy。
- 不保存规则文本；普通日志不保存 evidence、source ID tuple 或任何正文。

固定 warning code 全集：

```text
no_formal_screen
r04_not_completed
segment_mapping_invalid
formal_screen_index_invalid
formal_screen_out_of_order
duplicate_screen_id_conflict
duplicate_formal_screen_index
screen_segment_limit_exceeded
fuzzy_below_threshold
fuzzy_ambiguous_tie
fuzzy_candidate_limit_exceeded
historical_duplicate_ambiguous
historical_context_insufficient
historical_mapping_conflict
exact_stage_failed
fuzzy_stage_failed
historical_stage_failed
candidate_interrupted
candidate_aborted
screen_aggregation_partial
screen_aggregation_failed
mixed_aggregation_version
finalize_failed
```

warning 只保存 code；禁止附带正文、screen 坐标、confidence、规则、邮箱或手机号。

## 14. Document builder 生命周期

### 14.1 创建与隔离

**[仓库确认]** `start_candidate_ocr_recording()` 当前仅在 Store 可用且 enabled 时创建一个 `CandidateOcrBuilder`。R05 保持该行为：仅在显式 `record` 模式下由 builder 构造 `CandidateDocumentAggregator(run_id, candidate_record_id, config)`；生产默认 `disabled` 时不得创建或调用 aggregator，只写 R05 `not_attempted` 空状态。未启用记录时不为业务流程额外创建候选人全文对象。

**[仓库确认]** 首位候选人的成功 load observation 会作为正式屏 1 复用，后续候选人的成功 switch observation 同样作为正式屏 1 复用；callback 对同一对象的再次上报由现有 object-ID guard 跳过。当前候选人在切换下一位前还可能记录一个 non-formal pre-switch baseline，然后立即 finalize；load recovery 会 abort 当前 builder 并为恢复后的候选人新建 builder。R05 保持这些真实时机，不把 baseline/switch/confirmation 加入全文。

aggregator 只持有当前 candidate 的 document segments、seen screen 身份、轻量 historical index 与 warnings。`run_id/candidate_record_id` 不匹配立即拒绝。正常 finalize、ESC、异常或 load recovery 后，`finalize_current_candidate_recording()` 仍先清除全局 builder/observation ID 映射，再完成 finalize；下一候选人必须构造全新实例。禁止 module-global 文档、跨 candidate index 或 cache。

### 14.2 add 时机

- 每个 observation 仍只构建一个 screen record。
- 非正式 record 加入 candidate `screens` 证据，但 aggregator 不消费其 segment，并写 `not_attempted`。
- 正式 record 在 `save_screen()` 前调用一次 `add_screen()`；add 返回带完整 R05 字段的不可变 record。
- 正常递增 screen 进入 exact→fuzzy→historical→append 流程。
- duplicate/out-of-order 按第 7 节 fail-open，不改变页面流程。
- stage exception 只降级本屏；已经建立的 document state 不回滚或重写。

### 14.3 finalize 与异常

`CandidateDocumentAggregator.finalize(capture_status)` 必须幂等：第一次验证并缓存 frozen `CandidateAggregationResult`，相同 `capture_status` 的重复调用返回同一值；不同 capture status 的重复调用抛脱敏 `AggregationFinalizeConflictError`。finalize 后禁止 add。

**[仓库确认][需求冻结]** 外层 `CandidateOcrBuilder.finalize()` 继续保持既有 one-shot 契约，重复调用抛 `CandidateBuilderFinalizedError`，以保持当前测试和 screen reference 释放行为。也就是说：内部 R05 聚合 finalize 幂等，公开既有 builder finalize 仍受控拒绝；不得为满足“幂等”而改变整个 Stage 0 builder 生命周期。

正常结束使用现有 `CaptureStatus`；ESC 映射 `INTERRUPTED/user_interrupted`；候选人中途异常映射 interrupted/aborted 的既有规则。只要已有安全 document segment，ESC/abort 的 document 为 partial；没有正式 screen 为 not_attempted；有正式 screen 但全失败为 failed。

R05 stage failure 的 fallback 是把受影响的完整 R04 segment 作为 uncertain document segment 追加。禁止 fallback 到 `raw_text`、重新 OCR、重新分行或另外拼一份正文。Store 在创建后关闭/禁用/失败时，内存 finalize 仍可完成，但保存继续按 Store 既有 best-effort 返回 false；不得重试页面或改变动作。

## 15. `document_text` 生成规则

唯一生成函数位于 `ocr_aggregation.py`：

```python
def build_document_text(segments: Sequence[OcrDocumentSegment]) -> str:
    if any(not segment.normalized_text for segment in segments):
        raise AggregationInvariantError("empty_document_segment")
    return "\n".join(segment.normalized_text for segment in segments)
```

规则固定如下：

- `document_segments` order 必须为连续的 `0..n-1`，tuple 顺序与 order 相同。
- R04 空行不建立 document segment；合法空文档生成 `""`。
- segment 之间恰好一个 LF；末尾无 LF；不做平台换行转换。
- 序列化和读取时重新生成，并逐字符验证 `document_text`。
- 禁止 set、字典 key 去重、全局字符串 unique、`normalized_text` 直接屏幕拼接或单独维护第二正文。
- occurrence、comparison 和 evidence 不进入 `document_text`。

## 16. Screen 级 R05 结果

**[需求冻结]** R05 字段直接扩展现有 `OcrScreenRecord`，不新增平行 screen result 文件。新增/激活字段如下：

| 字段 | 类型/语义 |
| --- | --- |
| `aggregation_status` | `AggregationStatus` |
| `aggregation_version` | 已有占位；attempted 时 `r05-v1` |
| `aggregation_config_version` | attempted 时 `r05-config-v1` |
| `aggregation_config_digest` | 与 manifest 相同的 canonical SHA-256 |
| `matched_segment_ids` | 引用本屏 R04 `segments`，不贡献新正文 |
| `new_segment_ids` | 确定为新并贡献正文 |
| `uncertain_segment_ids` | 保守保留并贡献正文 |
| `match_evidence` | 本屏 frozen `OcrSegmentMatchEvidence` tuple |
| `aggregation_warning_codes` | 固定 code，稳定去重并按首次出现排序 |
| `aggregation_duplicate_risk` | `none/low/elevated`；与 R04 `duplicate_risk` 分离 |
| `overlap_text` | 已有占位；按本屏顺序 LF join matched segment 原文 |
| `new_text` | 已有占位；按本屏顺序 LF join `new + uncertain` 贡献原文 |
| `overlap_char_count` | matched 投影的 R05 comparison 字符数 |
| `new_text_char_count` | `new + uncertain` 投影的 R05 comparison 字符数 |
| `overlap_segment_count` | `len(matched_segment_ids)` |
| `new_segment_count` | `len(new_segment_ids)+len(uncertain_segment_ids)` |
| `certain_new_segment_count` | `len(new_segment_ids)` |
| `uncertain_segment_count` | `len(uncertain_segment_ids)` |
| `uncertain_char_count` | uncertain 的 R05 comparison 字符数 |

已有 R04 `segments` 是 screen 文本的唯一权威；分类只保存 ID。`overlap_text/new_text` 是产品需要的确定性缓存投影，不包含另一套 segment，并必须在 model `__post_init__`/reader 中由 ID 重建验证。failed/not_attempted 时两者为 null；completed/partial 时允许空字符串。

所有非空 R04 segment 在 attempted screen 中必须恰好属于 matched/new/uncertain 一个集合；三个 tuple 无重复、无交集，并保持 R04 order。matched evidence 必须覆盖每个 matched ID。new/uncertain 建立的 document segment ID 在 screen evidence/内部 add result 中确定，但 screen 不重复保存 document 正文。

**[明确禁止]** `similarity_hash`、`similarity_score`、`overlap_ratio`、`new_text_ratio`、`has_effective_new_text` 及 `similarity_version/dynamic_end_version` 在 R05 仍为 null/未实现。`overlap_text` 是 R05 的边界匹配文本，不等于 R06 ratio。

## 17. Candidate 级 R05 结果

`CandidateOcrDocument` 是唯一 candidate 容器，核心字段为：

| 字段 | R05 契约 |
| --- | --- |
| `document_version` | 新写入为 `r05-document-v1`；旧 `stage0-v1` 可读 |
| `storage_schema_version` | 新写入 `1.2.0` |
| `screens` | 与 screen JSONL 一致的最终 records，保留非正式 capture |
| `document_segments` | `Tuple[OcrDocumentSegment, ...]`，权威正文/来源 |
| `document_text` | 第 15 节的确定性投影 |
| `document_build_status` | `not_attempted/completed/partial/failed` |
| `versions["aggregation"]` | attempted candidate 为 `r05-v1`，否则 null |
| `aggregation_config_version/digest` | attempted candidate 必填并与 manifest/screens 一致 |
| `aggregation_warning_codes` | candidate 固定 warning 并集 |
| `aggregation_duplicate_risk` | screens/自身风险最大值 |
| `aggregation_summary` | formal、completed/partial/failed screen 数及 matched/new/uncertain segment/char 数 |

核心数据不得塞进自由 `metadata`。`normalization_summary` 与 `versions["normalization"]` 继续按 R04 规则重算；aggregation 使用独立 summary/version key。candidate model 验证每个 occurrence 指向本 candidate 的已存在 screen/segment/box，match ID 指向内嵌 screen evidence，document ID/order 连续，文本投影一致。

AI payload 只依赖 `document_build_status=completed`、新 document version 和上述不变量；partial/failed/not_attempted 不能绕过。

## 18. Schema 与版本

### 18.1 冻结决定

- **[仓库确认]** 当前 writer Schema 是 `1.1.0`。
- **[需求冻结]** R05 升级 writer 到 `1.2.0`，因为新增嵌套 document/source/evidence 类型、状态枚举、config identity，并激活原占位字段；这不是可安全解释的 1.1 additive null。
- `AGGREGATION_VERSION = "r05-v1"`。
- `AGGREGATION_CONFIG_VERSION = "r05-config-v1"`。
- `R05_DOCUMENT_VERSION = "r05-document-v1"`。
- supported storage 为 `1.0.0/1.1.0/1.2.0`；supported document 为 `stage0-v1/r05-document-v1`。

### 18.2 兼容映射

| 输入 | 读取行为 |
| --- | --- |
| 1.0.0 | 保留 raw/R03；R04/R05 均映射 not_attempted；旧 `not_implemented` document 在新内存视图映射 R05 not_attempted |
| 1.1.0 | 恢复 R04 全字段；缺少 R05 字段映射 aggregation/document not_attempted，不推断 matched/new |
| 1.2.0 | 严格验证 R04 + R05 状态、引用、projection、version/config identity |
| future/unknown | strict 拒绝；tolerant 产生脱敏 issue，不猜字段 |

`aggregation_status=not_attempted` 仅表示 R05 未运行/被关闭/旧 Schema，不表示“无重复”或“无新增”。不允许一个 attempted candidate 混合 aggregation version/config digest；strict model 拒绝，tolerant replay 报 `mixed_aggregation_version` 并不生成 completed 文档。

### 18.3 RunManifest

保留已有 `aggregation_version` 占位并增加：

```text
aggregation_mode                 disabled | record
aggregation_config_version
aggregation_config_digest
aggregation_config              完整 canonical snapshot
```

`record` 模式四项必须完整且 digest 匹配；`disabled` 模式 version/config/digest/snapshot 均为 null。manifest 的 config 是历史回放权威，不能用当前默认覆盖。R04 config/version/digest 与 R03 identity 不变。

manifest 的 `aggregation_mode` 只能来自静态配置或显式测试注入；首次实现合并后的生产默认固定为 `disabled`。Schema 1.2 reader 无论当前默认模式为何，都必须继续读取历史 `record` 记录。

## 19. Store 语义

**[仓库确认]** `JsonlOcrRecordStore` 是 append-only：先序列化完整对象，再以单次 UTF-8 line + LF 追加；screen 在线先保存，candidate finalize 后再保存；没有 update/backfill。

冻结顺序：

1. observation/R04 result 已存在；
2. builder 构造含 R04 的临时 immutable screen；
3. R05 aggregator 生成最终 screen + 更新 candidate 内存状态；
4. model 完整校验；
5. `save_screen(final_screen)`；
6. candidate 结束时 aggregator finalize；
7. builder 生成并校验 `CandidateOcrDocument`；
8. `save_candidate(document)`。

不允许 Store 内部计算 R05，不允许保存临时 screen 后补，不允许独立 patch JSONL。builder 返回的最终 screen object 是 online 单一权威；candidate 必须嵌入同一对象/逐字段同值。Store 新增 identity 校验：1.2 attempted record 的 schema、aggregation version/config digest 必须与 manifest 一致。

Store 序列化失败不得写半行；磁盘失败沿用“脱敏 error record、连续 3 次后 disable、业务继续”的既有 best-effort。保存失败不撤销已经完成的内存聚合，也不引发 OCR/页面重试；candidate save 失败时不另建不一致副本。

## 20. Replay

### 20.1 入口与输入

在 `ocr_replay.py` 新增：

```python
def replay_candidate_aggregation(
    candidate: CandidateOcrDocument,
    manifest: RunManifest,
    *,
    strict: bool = True,
    aggregation_config: Optional[OcrAggregationConfig] = None,
) -> CandidateAggregationReplay
```

`CandidateAggregationReplay` 保存 rebuilt screen R05 projections、rebuilt candidate document、config source、`Tuple[ReplayIssue,...]`；不改变传入对象。`load_ocr_run()` 仍只读并返回 run。

### 20.2 Config 与旧 Schema

- 1.2 attempted run：必须使用 manifest snapshot 恢复 config，并校验 version/digest；caller 不得覆盖。
- 1.1：没有历史 R05 config。只有显式传入 config 才可做“新算法派生回放”，结果标记 `config_source=caller_override`，不能宣称与历史 online 一致；未传时 strict 抛错、tolerant issue/not_attempted。
- 1.0：先显式调用现有 `replay_screen_normalization()` 得到 R04 派生 screen，再传明确 R05 config；禁止假装原记录含 R04/R05。
- config/version drift：strict 失败；tolerant 返回 issue，不使用当前默认悄悄替代。

### 20.3 顺序、模式与输出

正常 candidate 以 `screen_index` 升序处理正式 screen；candidate `screens` 原位置作为稳定 tie-breaker。strict 要求 unique/monotonic；若 run-level 存在同 ID screen，则内容必须一致。run-level 缺行不改变自足 candidate 的聚合结果。tolerant 按第 7 节恢复、将异常内容 uncertain、保留 issues。

对于同一 1.2 config、有效 source，online/offline 必须逐字段一致：screen status/IDs/evidence/text/count/risk/warnings、document segment ID/order/text/occurrences、document text/status/summary/version/config identity全部相同；时间字段沿用 source，不在 pure replay 生成新时间。

**[需求冻结]** R05 v1 replay 只返回内存派生结果，不写独立派生文件。未来若需要持久化，必须作为单独批准功能写入新的 run/derived 目录，绝不修改 source JSONL。strict error 和 tolerant issue 均不得含正文或来源详情。

## 21. AI payload

### 21.1 当前阻塞

**[仓库确认]** 全仓库没有 `build_ai_payload()`，也没有 `qualified/rejected/manual_review` 占位接口。Change 6 增加该函数需要维护者明确批准；未批准时 Changes 2—5 可实现，但 Change 6 的 AI 数据接口子项必须停止。

### 21.2 冻结的最小接口

经批准后在 `ocr_candidate.py` 新增纯函数：

```python
def build_ai_payload(document: CandidateOcrDocument) -> Dict[str, Any]:
    ...
```

只有以下条件全部满足才可调用：新 `r05-document-v1`、schema 1.2、`document_build_status=completed`、document projection/source 引用/config identity 验证通过。否则抛不含正文的 `DocumentNotReadyError`。

payload 仅包含：

```json
{
  "candidate_record_id": "opaque-id",
  "document_version": "r05-document-v1",
  "aggregation_version": "r05-v1",
  "document_text": "...",
  "document_segments": [
    {"document_segment_id": "document:segment:0", "order": 0,
     "normalized_text": "..."}
  ]
}
```

**[首版保守默认]** source occurrences、raw boxes、comparison text、match evidence、warning 和 screen 数据不进入 AI payload，以降低敏感数据和 token 扩散；审计仍留在 JSONL。合法 completed 空文档可生成空字符串/空列表 payload。

**[明确禁止]** 函数不调用外部 API，不写 Store/日志，不决定 qualified/rejected/manual_review，不接入当前动作主流程。

## 22. 失败与降级

| 场景 | 状态/保留 | 候选人流程 | screen/candidate 写入 | strict/tolerant replay | 允许日志 |
| --- | --- | --- | --- | --- | --- |
| 无正式 screen | doc not_attempted；保留非正式 evidence | 继续 | 无 formal screen；candidate 正常尝试保存 | 可读/not_attempted | status、count、`no_formal_screen` |
| R04 failed | screen failed；raw/R04 error code 保留 | 继续 | screen 是；candidate 是 | strict 可读失败状态；tolerant 同 | error type/version/count |
| R04 completed 空屏 | screen completed empty | 继续 | 均写 | 均正常 | count=0 |
| segment mapping 失败 | screen failed；不猜正文 | 继续 | 均写 | strict 拒绝损坏记录；tolerant issue | `segment_mapping_invalid` |
| duplicate index | 后条 partial/uncertain；首条权威 | 继续 | 两个不同 ID screen 均写；candidate partial | strict 失败；tolerant 稳定恢复 | code/count，不写 ID tuple |
| same screen ID 冲突 | 首条保留，后条拒绝 | 继续 | 不写第二条；candidate partial | strict 失败；tolerant 首条+issue | `duplicate_screen_id_conflict` |
| out-of-order | 当前全 uncertain；candidate partial | 继续 | 均写 | strict 失败；tolerant 排序恢复+issue | code/index count，不写正文 |
| exact 异常 | 当前全未决部分 uncertain；partial | 继续 | 均写 | strict 重算失败；tolerant issue/partial | `exact_stage_failed`、exception type |
| fuzzy 异常 | exact 后剩余 uncertain；partial | 继续 | 均写 | 同上 | `fuzzy_stage_failed` |
| historical 异常 | 其余 uncertain；partial | 继续 | 均写 | 同上 | `historical_stage_failed` |
| 重复 aggregator finalize | 同 status 返回缓存；冲突 status 抛错 | 外层按既有异常策略 | 不重复写 | deterministic | error type only |
| 重复 outer builder finalize | 受控 `CandidateBuilderFinalizedError` | 既有调用者处理 | 不重复写 | 不适用 | error type only |
| Store 失败 | 内存对象不变 | 继续，不重做页面 | 当前 write 可失败；无部分行 | source 缺行按既有 reader | store op/error type/count |
| replay version/config 不兼容 | source 不变 | 不适用 | 不写 | strict 抛错；tolerant issue | path basename/line/version/error type |
| ESC | 有文档 partial；无 formal not_attempted | 按既有安全停止 | finalize/save 尝试一次 | 可重放相同状态 | status/code/count |
| 候选人中途异常 | partial 或 failed | 按既有 abort/stop | finalize/save 尝试一次 | 同 source 状态 | status/code/error type |
| candidate finalize 不变量失败 | doc failed/不生成伪造对象；screen 已保留 | 既有安全停止/继续策略不变 | candidate 不写，error 尝试写 | orphan screens 可见 | `finalize_failed`、error type |

所有错误/issue/log 明确禁止正文、segment text、规则、邮箱、手机号、bbox/坐标和 confidence。异常消息只使用固定 code、类型名、version/config identity、计数、文件 basename/line number 和既有 opaque run/candidate ID。

## 23. 性能与复杂度

### 23.1 上界

- **[仓库确认]** 每 candidate 最多 8 正式 screen。
- **[首版保守默认]** 每 screen 正常目标 64 segment，安全硬上限 256；最大 document 2048 segment。
- exact：每屏最坏 O(S²) segment-key 比较、O(S) 临时内存；8 屏有固定上界。
- fuzzy：每屏最多 4×4 边界、128 paths、每组每侧 512 个正文字符（不计人工 LF）；`SequenceMatcher` 理论最坏近 O(C²)，超 candidate/text 限制 fail-open。
- historical：长度仅 2—4，index 构建/更新 O(D×3)，current lookup O(S×3)，不做 document×current pair matrix。
- source/document state 只在当前 candidate 内；finalize 后释放，内存不随候选人数增长。

禁止以下实现：所有历史 segment×当前 segment、任意窗口组合、全文 fuzzy pair matrix、全 run/cross-candidate cache、无界递归 tiling。

### 23.2 Benchmark

新增 `tests/benchmark_r05_aggregation.py`，从仓库根目录可直接运行，固定随机种子且不依赖 OCR、Store、页面或网络。分别测 timing 与 `tracemalloc`，避免内存探针污染 timing。至少覆盖：

- 8×64 unique；相邻 50%/90% exact；完整屏 duplicate；每屏只新增 1 行。
- 8×64 1→1/1→2/2→1 fuzzy；灰区和 128 candidate 压力。
- 8×64 unique/multi-source historical；重复 N-2 与 ambiguous source。
- 8×256 最大输入；segment 257 fail-open。
- 100 次相同输入的逐字段 determinism；连续 100 candidate 后无引用增长。

首版门槛（同一 CI/验收机、release interpreter、预热后至少 25 次）：

| 场景 | p95 | 附加峰值内存 |
| --- | ---: | ---: |
| 典型 8×64 aggregate+finalize | `<=20 ms` | `<=16 MiB` |
| 最大 8×256 aggregate+finalize | `<=150 ms` | `<=32 MiB` |
| 单屏 fuzzy 压力 | `<=50 ms` | 包含于 32 MiB |

**[待真实样本验证]** 门槛和阈值在受治理 Windows 样本上复核；未达标只能优化纯算法或更保守 fail-open，禁止扩大窗口/缓存或减少正文来“达标”。

## 24. 隐私与日志

**[需求冻结]** 普通应用日志仅允许：operation/status、screen/candidate 计数、version/config digest、固定 warning code、异常类型、既有 opaque run/candidate ID。不得记录 `document_text`、segment text/comparison、source occurrence、match evidence tuple、raw text、规则文本、邮箱、手机号、confidence、bbox/坐标。

JSONL 是敏感运行数据而非普通日志，可以按 Schema 保存 raw evidence、document 和来源；必须位于既有 run 目录、被 Git ignore、使用现有访问边界。真实 run/样本/派生结果禁止加入 Git。

测试必须 patch 日志与 `data/ocr_runs` 到 `TemporaryDirectory`，断言真实 `logs/simple_brush.log` 的 size/mtime 不变，并对日志捕获执行禁止字段/示例正文扫描。warning 只用第 13 节固定 code，不拼接异常输入。真实 shadow 前另行批准访问、留存和删除策略。

## 25. 跨平台

`ocr_aggregation.py`、新增 record types 和 pure replay 只能依赖平台中立标准库及仓库已有 pure 模块。允许 `dataclasses`、`difflib`、`enum`、`hashlib`、`json`、`typing` 和 `ocr_normalization.build_comparison_text`。

**[明确禁止]** pure 层导入 `pywin32/win32*`、`pyautogui`、`mss`、Tk、GUI、Windows-only path、OCR backend 或 `simple_brush`。模块 import 不得读写文件、创建目录、读取时钟/随机数或初始化线程。

正文固定 Unicode + LF；JSONL UTF-8；path 由 Store/Replay 边界的 `pathlib.Path` 处理。Windows 是唯一正式业务平台。macOS 只要求 pure import/unit test 在仓库当前支持范围内通过，不宣称 GUI、截图、Edge 控制或 release 正式支持。

## 26. 回滚

### 26.1 模式

新增内部 `R05_AGGREGATION_MODE`，仅允许 `record`、`disabled`，并记录在 manifest。首次实现合并后的生产默认值冻结为：

```python
R05_AGGREGATION_MODE = "disabled"
```

它不是动作模式，也不新增页面 CLI：

- `record`：只能由单元测试、集成测试、benchmark 或获得独立授权的受控 shadow 显式注入；运行 pure aggregation 并写 R05。
- `disabled`：不得创建或调用 aggregator、不得运行聚合算法；Schema 1.2 仍可写既有 raw/R03/R04 evidence，但所有 R05 screen/candidate 字段严格为 not_attempted/null/empty，manifest 的 aggregation identity 为 null，matched/new/uncertain 不得填入伪造结果。

该模式只能由静态配置或显式测试注入决定。不得根据 OCR 文本、规则结果、匹配结果、候选人状态或页面状态动态切换。未经维护者单独批准，不得把生产默认改为 `record`；默认值修改必须是未来独立批准 Change，不得夹带在缺陷修复、性能优化或验收中。

### 26.2 回滚不变量

- disabled 后 R04 normalization、R03 exact hash、legacy rule/action、8 屏、滚动/等待/OCR/截图/confirmation/收藏/转发/ESC/timer 全部保持现状。
- 已有 1.2 JSONL 不删除、不改写；新 reader 继续可读 1.0/1.1/1.2，包括显式 `record` 模式产生的历史记录。
- 回滚旧 binary 时只允许其创建新的 1.1 run，不要求旧 binary 读取 1.2；历史 1.2 由新 replay 保留读取能力。
- 不删除 R04 evidence，不把 document 反写为 screen text，不执行迁移清理。
- Store/aggregation disabled 永不改变动作结果；R05 在任何 mode 都没有 action authority。

**[需求冻结]** 若出现生产风险，首选设置 disabled 并保留 1.2 reader，而不是 Git reset、删除 run 或恢复旧 Schema 文件。

## 27. Change 1—7 文件级计划

### 27.0 通用执行规则

每个 Change 开始前执行并记录：`git status -sb`、`git status --short`、`git rev-parse HEAD`、`git diff --stat`、`git diff --check`；结束时再次执行 status/diff/check 与该 Change 指定测试。现有用户文件不得暂存、覆盖或删除。每个 Change 只能修改其允许列表；发现需要跨范围修改时立即停止，请维护者调整计划。

每份 Change 报告固定包含：基线、实际文件、实现结果、不变量证据、测试/性能、隐私检查、Git 状态、阻塞/偏差、明确声明“未自动进入下一 Change”。禁止在一个 commit/工作区中合并后续 Change。

### Change 1：仓库验证、基线与接口确认

**目标**

确认批准后的 HEAD 仍符合本文基线，验证所有真实函数/字段/调用点、R04 acceptance 状态、formal screen 保存顺序、append-only 语义、空历史数据与 AI 接口门禁；不实施代码。

**前置条件**

- 维护者书面批准 RPD/TID 进入 Change 1。
- R04 tracked 工作区干净；既有用户文件已记录且不处理。
- 若 HEAD 已变化，逐项重做事实差异审计，不沿用旧行号。

**允许修改文件**

- 新增 `docs/R05-change1-baseline-report.md`。
- 仅在事实变化经证据确认时修正本 RPD/TID。

**禁止修改文件**

- 所有 `*.py`、测试、配置、依赖、build、README、release、workflow、数据与日志。

**新增类/函数**

- 无。

**必须保持的不变量**

- 不运行真实 OCR/页面动作；不创建正式 run。
- 不调整任何阈值、Schema 或接口设计。
- 不触碰 `docs/project-review.zip`、`venv-packages-before-reinstall.txt` 及其他新发现用户文件。

**测试矩阵**

- 完整 594 基线或当时主干完整 suite。
- pure R04 benchmark；确认真实 log/data size/mtime 不被测试改变。
- 搜索并复核 `build_ai_payload`、审核结果字段是否仍缺失。

**性能要求**

- 只记录 R04 既有基准，不建立 R05 性能结论。

**完成条件**

- 报告逐项确认/纠正第 1—3 节事实；所有门禁有 owner/最小处理。

**停止条件**

- HEAD/R04 Schema 或主流程已实质变化；存在未知 tracked 修改；R04 测试失败；发现实际 AI 接口已出现且与本文冻结边界冲突。

**报告格式与停步**

- 使用通用格式，列出允许/实际文件和命令证据；完成后停止，明确禁止自动进入 Change 2。

### Change 2：segment 模型与确定性适配

**目标**

建立 pure R05 config、document/source/evidence 类型、R04 screen segment adapter、ID/字符/文本投影函数；不做 overlap，不接 Store/主流程。

**前置条件**

- Change 1 已单独批准通过。
- 维护者接受 Schema 1.2、`OcrDocumentSegment` 与 ID/char_count 决策。

**允许修改文件**

- 新增 `ocr_aggregation.py`。
- `ocr_records.py`（只新增尚未接入 writer 的枚举/value types 与验证 helper）。
- `ocr_candidate.py`（只新增 pure adapter/export；不接当前 builder）。
- 新增 `tests/test_ocr_aggregation.py`；更新 `tests/test_ocr_records.py`、`tests/test_ocr_candidate.py` 的新增类型测试。

**禁止修改文件**

- `ocr_normalization.py`、`ocr_detector.py`、`ocr_text.py`、`ocr_store.py`、`ocr_replay.py`、`simple_brush.py`、依赖/配置/build、现有 JSONL、README。

**新增类/函数**

- `OcrAggregationConfig`、canonical snapshot/digest/restore。
- `AggregationStatus`、`DocumentBuildStatus`、`AggregationMatchType`、`AggregationDuplicateRisk`、`AggregationOccurrenceRole`。
- `OcrSourceOccurrence`、`OcrDocumentSegment`、`OcrSegmentMatchEvidence`。
- `adapt_r04_screen_segments()`、`aggregation_char_count()`、`build_document_text()`、deterministic ID helpers。

**必须保持的不变量**

- adapter 不改输入，不重跑 normalizer，不重新分行。
- screen segment ID/box 来源原样；document/match ID 无 UUID/time/hash。
- 当前 writer 仍是 1.1；现有 record round-trip 不变。
- pure module 无平台/IO/AI import。

**测试矩阵**

- 单行、多行、一行多 box、空行/空屏、全/半角、中英文、特殊符号。
- 相同文字不同位置、稳定 ID/order、来源 box 完整、非法 ID/order/box/comparison 映射。
- input/bbox/tuple 不可变；100 次 deterministic；module dependency scan。
- config missing/extra/type/range/digest drift；document LF/空段/末尾换行验证。

**性能要求**

- 256 segment adapter p95 `<=5 ms`，额外内存 `<=4 MiB`；不含 R04 normalization。

**完成条件**

- 新类型与 pure helper 全覆盖；完整旧 suite 通过；无 writer/页面行为变化。

**停止条件**

- 必须修改 R04 segment 或 normalizer 才能继续；发现来源 box 不稳定；需要新增依赖。

**报告格式与停步**

- 通用格式另附类型/ID/config contract 表；停止等待审阅，禁止自动进入 Change 3。

### Change 3：相邻精确重叠

**目标**

只实现第 9 节 longest exact boundary 与 evidence/occurrence 纯结果；不实现 fuzzy/history/builder 集成。

**前置条件**

- Change 2 已批准；config/字符口径/模型冻结无争议。

**允许修改文件**

- `ocr_aggregation.py`。
- `tests/test_ocr_aggregation.py`。

**禁止修改文件**

- 其他所有生产/测试文件，尤其 records/candidate/store/replay/detector/simple_brush/normalization。

**新增类/函数**

- `ExactBoundaryMatch`、`find_exact_boundary_overlap()`、exact evidence/occurrence application helper。

**必须保持的不变量**

- 只比较 tail/head；largest k first；顺序连续；不修改文本。
- 短候选不足门槛不抑制；单行只用 48 字完整屏例外。
- 不调用 SequenceMatcher、不搜索历史中间、不产生 R06 字段。

**测试矩阵**

- 无/部分/大量重叠、完整屏重复、只新增一行、最长优先。
- 短标题相同、常见短职责相同、单长行门槛 ±1。
- 文档中间相同但边界不同、顺序颠倒、同文不同位置。
- 第 7/8 屏仅少量新增；全屏空；上限 256；输入不可变/确定性。

**性能要求**

- 8×256 pure exact p95 `<=20 ms`；不得引入全文扫描。

**完成条件**

- exact 分类、source/evidence 与所有边界值测试通过，完整 suite 通过。

**停止条件**

- 需求需要中间匹配/语义判断；性能需 rolling hash 才能达标但设计未批准；发现文本损失。

**报告格式与停步**

- 通用格式另附每个 exact 门槛 ±1 结果；停止，禁止自动进入 Change 4。

### Change 4：有限模糊重叠和行拆分/合并

**目标**

实现第 10 节有界 fuzzy 路径、1→1/1→2/2→1、灰区与冲突 fail-open；不实现历史或线上接入。

**前置条件**

- Change 3 已批准；维护者接受首版 fuzzy 阈值与 SequenceMatcher。

**允许修改文件**

- `ocr_aggregation.py`。
- `tests/test_ocr_aggregation.py`。

**禁止修改文件**

- 其他生产/测试文件、依赖；禁止新增 fuzzy package。

**新增类/函数**

- `FuzzyBoundaryCandidate`、`enumerate_fuzzy_tilings()`、`score_fuzzy_group()`、`find_fuzzy_boundary_overlap()`、unmatched count helper。

**必须保持的不变量**

- exact 先行；tail/head 各 4；candidate<=128；group chars<=512。
- 仅 1→1/1→2/2→1；连续、单调；原文不可变。
- 同分/冲突/灰区/异常全部 uncertain；完整 segment 处理，不截取新增子串。
- R04 不增加 fuzzy box deletion。

**测试矩阵**

- 单字错/漏/多、标点、大小写、空白；0.88/0.94 与 ±边界。
- 1→2、2→1、1→1；2→2/N→M 拒绝；顺序颠倒。
- 每侧 31/32 字、unmatched 2/3、group 512/513。
- 1→2 仅由 R05 多插入一个人工 LF、两侧 OCR 正文完全相同：LF 可进入 matcher，但正文消费/unmatched 均不增加。
- 2→1 仅由 R05 少一个人工 LF、两侧 OCR 正文完全相同：不得把行边界差异计作 OCR 字符差异。
- 32 字最小门槛按非 LF 正文计算；31 个正文字符加一个人工 LF 仍不达标。
- 512 字上限按非 LF 正文计算；512 个正文字符加人工 LF 仍合法，513 个正文字符仍超限。
- 每侧 unmatched `<=2` 只计算非 LF 正文；单独 unmatched 的人工 LF 计数为 0。
- R04 `comparison_text` 不含正文换行；测试只允许 R05 内部拼接产生 LF。
- 候选路径消费量、加权 score 的字符权重和排序字符数全部排除人工 LF。
- 短文本、多个同分、epsilon 边界、冲突新内容、窗口 4/5、candidate 128/129。
- 100 次确定性、输入不可变、超限 fail-open。

**性能要求**

- 单屏 fuzzy 压力 p95 `<=50 ms`，附加内存包含于 32 MiB 总门槛。

**完成条件**

- 所有 shape/阈值/灰区结果逐字段稳定，完整 suite 通过，无新增依赖。

**停止条件**

- 需要一般 N→M、全文 fuzzy 或语义 correction；发现当前额外正文会被高分候选吞掉；门槛只能靠扩大缓存达成。

**报告格式与停步**

- 通用格式另附 candidate 排序和冲突证据；停止，禁止自动进入 Change 5。

### Change 5：历史保守检查与 candidate aggregator

**目标**

实现 exact historical sequence index、双锚/唯一来源规则，以及 `CandidateDocumentAggregator` add/finalize 状态机；仍不接既有 `CandidateOcrBuilder`/Store。

**前置条件**

- Changes 2—4 已分别批准；状态/风险/warning code 冻结。

**允许修改文件**

- `ocr_aggregation.py`。
- `ocr_candidate.py`（只导出/组合 pure aggregator facade；不改在线调用）。
- `tests/test_ocr_aggregation.py`、`tests/test_ocr_candidate.py`。

**禁止修改文件**

- `ocr_records.py`（本 Change 不改 schema）、`ocr_normalization.py`、`ocr_detector.py`、`ocr_text.py`、`ocr_store.py`、`ocr_replay.py`、`simple_brush.py`、依赖/build/data。

**新增类/函数**

- `HistoricalSequenceIndex`、`classify_historical_duplicates()`。
- `CandidateDocumentAggregator`、`CandidateAggregationResult`、screen add/result helper、aggregation exceptions。

**必须保持的不变量**

- historical 只 exact、2—4、48 字、每段>8、唯一 source、双外锚；无 fuzzy。
- uncertain 一律追加；document text 只由 document segments 生成。
- aggregator candidate-local；add 后不可重写旧正文；finalize 内部幂等、finalize 后禁 add。
- outer existing builder 与 online 流程仍未改变。

**测试矩阵**

- N 屏重复 N-2 完整内部序列；唯一/多来源；缺前/后锚；历史尾部排除。
- 不同公司相同职责、不同项目相同工具、技能/标题/短句、token list 保留。
- overlapping historical candidate、最大长度优先、映射冲突、stage exception。
- builder 零/一/八屏、R04 failed、空屏、duplicate ID/index、乱序、candidate ID 隔离。
- normal/interrupted/aborted、重复同 status finalize、冲突 status finalize、finalize 后 add、引用释放。
- document/occurrence/evidence/summary/risk/warning 全不变量。

**性能要求**

- 8×64 全聚合 p95 `<=20 ms`；8×256 `<=150 ms`；peak `<=32 MiB`；100 candidate 无 retained growth。

**完成条件**

- pure candidate 从 screens 生成完整 R05 结果且所有异常 fail-open，无线上行为变化。

**停止条件**

- 历史合法重复被抑制；需要语义分类或 fuzzy history；跨 candidate 引用无法释放。

**报告格式与停步**

- 通用格式另附 lifecycle/state transition 表和 memory 证据；停止，禁止自动进入 Change 6。

### Change 6：Schema、Store、Replay、AI payload 与主流程集成

**目标**

升级 Schema 1.2，以生产默认 `R05_AGGREGATION_MODE="disabled"` 接入现有 record/builder/append-only Store/Replay/主流程，并在维护者单独批准时加入纯 AI payload；页面动作必须零变化。测试路径必须显式注入 `record` 才能运行聚合。

**前置条件**

- Change 5 已批准；Schema migration 与 rollback mode 获批。
- 完成/确认 `build_ai_payload` 门禁决定；若未批准，该子项停止并在报告标阻塞，禁止自创替代接口。
- full suite 仍通过，真实工作区无未知修改。

**允许修改文件**

- `ocr_records.py`、`ocr_candidate.py`、`ocr_store.py`、`ocr_replay.py`、`simple_brush.py`。
- `ocr_aggregation.py` 仅修正已批准集成适配，不改算法/阈值。
- `tests/test_ocr_records.py`、`tests/test_ocr_candidate.py`、`tests/test_ocr_store.py`、`tests/test_ocr_replay.py`、`tests/test_ocr_stage0_integration.py`、`tests/test_simple_brush_ocr.py`、`tests/test_ocr_aggregation.py`。

**禁止修改文件**

- `ocr_normalization.py`、`ocr_detector.py`、`ocr_text.py`、OCR backend/capture、依赖、build、GUI/calibration、README、数据/log。

**新增类/函数/接点**

- Schema 1.2 reader/writer/validation、R05 document/summary fields、manifest config identity。
- `CandidateOcrBuilder` 组合 aggregator；`record_ocr_observation()` 在 save 前接收最终 screen。
- Store 1.2 identity validation；`replay_candidate_aggregation()`/result。
- `R05_AGGREGATION_MODE`，允许值仅 `record/disabled`，生产默认固定为 `disabled`。
- 仅获批时：`build_ai_payload()`、`DocumentNotReadyError`。

**必须保持的不变量**

- 1.0/1.1 read 兼容；1.2 strict validation；无 mixed identity。
- screen 先算后唯一 append，candidate 嵌入同值；无补写/部分 JSONL。
- online/offline 共用 pure aggregator；source 不变。
- disabled 在 aggregator 创建前短路，所有 R05 字段满足 not_attempted，且不伪造 matched/new/uncertain；只有测试显式注入 record 才覆盖聚合路径。
- OCR、截图、等待、滚动、confirmation、favorite、forward、no-forward、ESC、timer、legacy action authority 的次数/顺序/结果不变。
- `ocr_detector.py` 与 R03/R04 identity 零 diff。

**测试矩阵**

- 1.0/1.1/1.2 round-trip，旧缺字段映射，future/missing/mixed/version/config drift。
- manifest config missing/extra/digest；record-manifest identity mismatch。
- append screen/candidate/error、serialization/disk failure、3 次 disable、无部分 line、concurrent append。
- strict/tolerant replay、old schema override、source immutable、online/offline逐字段一致。
- load prefetched dedup、formal/confirmation/load/switch/scroll retry 分类、正常/ESC/异常 finalize。
- 生产默认 disabled 回归；单元/集成/benchmark 显式注入 record；禁止从 OCR/规则/匹配/candidate/page 状态动态切换。
- mock/spy 逐项断言页面调用次数；legacy shadow/action 结果不变。
- AI completed/empty completed/partial/failed/not_attempted、payload 精确白名单、无外部 API。

**性能要求**

- 序列化/校验后的 8×64 端到端聚合+record build p95 建议 `<=30 ms`；pure 门槛仍按第 23 节。
- 页面等待不以性能优化名义变更。

**完成条件**

- Schema/Store/Replay/online 集成矩阵全通过；完整 suite 通过；tracked diff 仅允许文件；页面 spy 零差异；生产默认仍为 disabled。

**停止条件**

- 需要改 detector/normalizer/页面调用；append-only 无法满足；旧记录不可读；AI gate 未批却是验收必需；任何动作结果变化。

**报告格式与停步**

- 通用格式另附 schema 字段表、JSONL round-trip、disabled 默认值证据、显式 record 测试证据、页面调用 diff 与 gate 结果；停止，禁止自动进入 Change 7 或真实运行。

### Change 7：全量回归、性能、隐私与 Acceptance Report

**目标**

只补齐验收测试/benchmark/报告，运行全量自动化并形成正式 R05 Acceptance Report；不顺手改变产品算法或页面行为。

**前置条件**

- Change 6 已批准；所有自动化运行确认隔离真实 log/data。
- 如需真实 Windows shadow，数据治理、`--no-forward`、访问/留存/删除方案和人工窗口明确批准；否则报告必须标未执行。

**允许修改文件**

- 新增/更新 R05 测试文件和 `tests/benchmark_r05_aggregation.py`。
- 新增 `docs/R05-ocr-multiscreen-incremental-aggregation-acceptance-report.md`。
- 仅修正文档事实的本 RPD/TID。

**禁止修改文件**

- 所有生产代码、配置、依赖、build、README、workflow、真实 data/log。发现生产缺陷必须停止并申请独立 corrective Change，不能塞入验收 Change。

**新增类/函数**

- 仅测试 fixture/helper/benchmark；无生产类/函数。

**必须保持的不变量**

- 不运行真实页面，除非有单独人工授权；默认测试全部 mock/pure。
- benchmark 不 OCR、不写 Store、不联网。
- Acceptance 不把“未执行”写成“通过”，不提交真实样本。
- Change 7 自动验收通过也不得把生产默认值从 disabled 改为 record。

**测试矩阵**

- 第 28 节完整矩阵、全量 unittest、pure import、schema/store/replay、页面 call spy、日志隐私、determinism、memory release。
- 分别验证生产默认 disabled 回归和显式注入 record 的自动化/benchmark。
- 真实 record shadow 默认报告 `NOT RUN`；只有获得独立授权时才可显式 record 并执行 Windows `--no-forward`，验证最多 8 屏、ESC、timer、legacy action 不触发，且只报告脱敏计数/状态。

**性能要求**

- 第 23 节全部门槛；保存 JSON benchmark 原始摘要时只含 synthetic 场景和计数，不含文本。

**完成条件**

- Acceptance Report 对 disabled 回归、显式 record 自动化和真实 record shadow 三项分别给出 PASS/FAIL/NOT RUN，并记录命令、环境、证据、门禁和回滚结果；全量测试通过且 Git 无真实数据，生产默认仍为 disabled。

**停止条件**

- 任一回归/隐私/性能失败；真实数据授权不足；需生产修复；R04 shadow 前置仍未完成。

**报告格式与停步**

- 使用 R04 Acceptance 风格并增加 R05 schema/算法/页面零副作用/隐私/性能/rollback 章节；完成后停止，禁止自动进入 R06、R07、commit、push、tag 或 release。

## 28. 完整测试矩阵

下表是各 Change 测试的并集，Change 7 必须逐项有自动证据或明确 NOT RUN 理由。

### 28.1 Segment

- 单行、多行、一行多 box、R04 completed 空屏/空行过滤。
- 全角/半角、中英文、组合 Unicode、特殊符号、LF 与无末尾换行。
- 相同文字不同位置生成不同 document ID；相同输入 replay ID 稳定。
- source box 完整/顺序稳定；非法 screen/line/order/box/comparison 映射拒绝。
- adapter、bbox、screen segment、输入 tuple 不可变。

### 28.2 Exact overlap

- 无、部分、大量、完整屏重叠；只新增一行；最长优先。
- 1/2 segment、23/24 字、短阈值 8/9、单行 47/48 字边界。
- 短标题、常见职责、边界外相同、顺序颠倒不抑制。
- 第 7/8 屏新增；occurrence/evidence exact basis；输入不可变。

### 28.3 Fuzzy overlap

- 单字错/漏/多、标点、大小写、空白、1→1、1→2、2→1。
- 2→2/N→M/逆序拒绝；短文本；0.88/0.94/epsilon；同分与冲突。
- 4/5 窗口、32 字、unmatched 2/3、512/513 字、128/129 candidate。
- 1→2 只多一个人工 LF且正文相同；2→1 只少一个人工 LF且正文相同。
- 人工 LF 不计入 32 字门槛、512 字上限或每侧 unmatched `<=2`。
- R04 `comparison_text` 无正文换行，仅 R05 内部拼接可产生 LF。
- 候选排序、路径消费字符数和 score 权重字符数排除人工 LF。
- 灰区保留、原文不改、性能上限、重复运行确定性。

### 28.4 Historical

- 第 N 屏重复 N-2 内部完整序列，唯一 source + 双外锚才抑制。
- 不同公司相同职责、不同项目相同工具、技能、标题、token list、远距离短句保留。
- 单/多来源、缺任一锚、历史尾部、重叠候选、映射冲突、不确定保留。
- 无 fuzzy history、sequence index 非 O(n²)。

### 28.5 Builder

- 零/一/八正式屏；含全部 non-formal 类型；R04 failed/空屏。
- duplicate screen ID 相同/冲突、duplicate index、乱序、非法 index。
- stage exception、正常、ESC、abort、外层/内部重复 finalize。
- candidate/run 隔离、finalize 后 add 拒绝、引用释放。
- document text/segments、source occurrences、match references、summary/risk/warning 一致。

### 28.6 Schema、Store、Replay

- 1.0、1.1、1.2、future；round-trip；unknown additive field。
- strict/tolerant；截断/损坏行；config drift/version mismatch/mixed identity。
- Store init/serialize/disk/consecutive failure；无部分 JSONL；close idempotent；并发完整行。
- online/offline 逐字段一致；old schema caller override；source object/file byte 不变；R03 exact hash 不变。

### 28.7 主流程回归

- OCR、截图、等待、滚动次数/参数不变；最多 8 屏和固定结束不变。
- confirmation、load check/retry、switch check/recovery、scroll retry 语义不变。
- favorite、forward、no-forward、焦点恢复、ESC、按秒 timer、异常停止不变。
- AND/OR/NOT/ANY 与 legacy action authority 不变；R05 result 从不控制动作/结束。

### 28.8 性能与隐私

- 8×64、8×256、fuzzy/history 压力、100 次确定性、100 candidate 内存释放。
- pure module import 无平台/side effect 依赖。
- 临时日志/数据；真实日志 size/mtime 不变；日志禁止正文/source/规则/联系方式/坐标/confidence。
- Git status/check-ignore 验证无真实运行数据、benchmark 文本或临时文件进入 Git。

## 29. 高风险问题逐项结论

1. **R04 segment 能否直接复用？** 能，作为 screen segment；[仓库确认] 它已是稳定视觉行并含 box 来源。
2. **是否需要新 DocumentSegment？** 需要 `OcrDocumentSegment`，承载 candidate order 与多 occurrence；不另建平行 candidate。
3. **两类 segment 如何区分？** `OcrTextSegment` 单屏视觉行；`OcrDocumentSegment` 候选人正文单元，ID/字段/生命周期不同。
4. **哪些 screen 进入全文？** 仅 `capture_type=formal_screen && is_formal_screen=true` 且 identity/index 合法。
5. **同一 index 多 record？** 首条 append-order 为 index 权威；后条保留 evidence、全文 uncertain 追加、candidate partial；strict replay 拒绝。
6. **screen 何时保存？** R04 投影和 R05 add 完整结束、model 校验后立即一次 append。
7. **append-only 如何补 R05？** 不补；首次 save 前生成最终 record，禁止 backfill/patch line。
8. **Schema 是否 1.2.0？** 是，冻结升级到 `1.2.0`。
9. **是否需要 config version/digest？** 需要 version、canonical snapshot、SHA-256 digest，manifest/screen/candidate 一致。
10. **阈值如何历史回放？** 1.2 使用 manifest snapshot；1.1/1.0 必须 caller 显式 override 并标派生，禁止当前默认冒充历史。
11. **R05 partial 如何隔离？** 独立 `AggregationStatus/DocumentBuildStatus`；R04 `NormalizationStatus` 不改、无 partial。
12. **exact 最小证据？** 常规 2 segment、24 comparison 字、至少一行>8；单行完整屏例外 48 字。
13. **fuzzy 窗口/阈值？** tail/head 各4、每组32个正文字符、score 0.94、灰区0.88、每侧 unmatched正文字符<=2、正文字符<=512；人工 LF 仅进入 SequenceMatcher，不计上述字符口径或候选排序消费量。
14. **允许 N→M？** 只允许 1→1、1→2、2→1；2→2和一般 N→M 禁止。
15. **同分怎么办？** 主证据同且 score 差<=0.005、映射不同则全部 uncertain，不用排序强删。
16. **历史允许 fuzzy？** 首版明确不允许，只 exact sequence。
17. **哪些永远不能仅凭相同删除？** 不同公司职责、不同项目工具、短句、技能/token list、模块标题、短序列、非唯一/缺上下文内容。
18. **source occurrence 保存什么？** screen ID/index、segment IDs、OCR box IDs、role、order、match ID；evidence 保存映射/type/score或exact/risk/warning。
19. **duplicate risk 如何表示？** 新 `aggregation_duplicate_risk=none/low/elevated`，与 R04 `duplicate_risk` 分离，candidate 取最大。
20. **warning codes？** 仅第 13 节 23 个固定 code；不拼正文。
21. **中途异常如何 finalize？** 已有安全内容则 uncertain/partial；无可用正式输入 failed；调用时机沿用主流程。
22. **ESC 状态？** 有正式安全文档为 partial；无正式输入 not_attempted；现有 capture status/安全停止不变。
23. **重复 finalize 幂等？** 内部 `CandidateDocumentAggregator` 同 status 幂等；既有外层 `CandidateOcrBuilder` 继续 one-shot 受控拒绝。
24. **如何避免 candidate 串数据？** constructor 固定 run/candidate ID、实例内 state、finalize 后禁 add/释放、无 global/cross-candidate cache。
25. **Store 失败影响主流程？** 不影响；沿用 best-effort/三次 disable，不重做 OCR/页面/动作。
26. **Replay 如何一致？** 同一 pure adapter/aggregator + manifest config；1.2 逐字段比较，source/时间不变。
27. **`build_ai_payload` 何时调用？** 仅维护者批准接口后，且文档为 validated completed；当前缺失是 Change 6 门禁。
28. **关闭/回滚旧行为？** `R05_AGGREGATION_MODE` 仅允许 record/disabled，首次生产默认固定 disabled；disabled 不运行 aggregator并写 R05 not_attempted，不伪造分类，R04/R03/legacy/page 完全不变；测试/benchmark/获批 shadow 才可显式注入 record，1.2 reader 始终保留历史 record 读取能力，默认值变更必须是未来独立批准 Change。
29. **性能最坏上界？** 8×256；exact O(S²)，fuzzy<=128×512-char bounded comparisons，history O(D×3)，无跨 candidate state。
30. **Change 1—7 允许文件？** 第 27 节逐 Change 白名单为唯一授权；不在白名单即禁止，需停止申请变更。

## 30. 实施门禁与最终交接

1. **[待真实样本验证]** 当前无非空正式 R04 JSONL，R04 real shadow 未执行。最小前置：先批准敏感数据访问/留存/删除方案，再用 Windows `--no-forward` 受控采样；它阻塞 R05 生产 shadow/阈值正式化，不阻塞批准后的 Changes 2—6 自动化工作。
2. **[仓库确认]** `build_ai_payload()` 缺失。最小前置：Change 6 前由维护者批准第 21 节最小纯函数；未批准则该子项阻塞，禁止增加 AI 系统。
3. **[需求冻结]** 本 TID 的算法、阈值、Schema、ID、warning 和 Change 文件范围已给出默认；Terra 不得以“实现方便”重新设计。发现无法实施时必须报告具体冲突并停止。
4. **[明确禁止]** 未经维护者逐步批准，不得开始 Change 1，不得实施 R05，不得进入 R06/R07，不得 commit/push/tag/release。
