# R06 Change 2 — Schema、Reference 与配置报告

## 总体结果

Change 2 已完成，仅交付 Schema 1.3、冻结 value types、纯 reference resolver、R03 只读 adapter、不可变配置及旧 Schema reader 兼容；未实现 n-gram、SimHash、比例/会计、有效新增、分类器、Builder/Store/Replay/sidecar 或任何在线主流程接入。

## Git 基线与设计权威

- branch: `main...origin/main`
- HEAD/RPD 初始 TID commit: `afc41d8f279e0218d892f7973d3e39b2d86bdf90` (`docs(ocr): define R06 page similarity`)
- R05 固定实现基线: `f02209c feat(ocr): implement R05 multiscreen aggregation`
- Change 2 前置合同 Corrective: 当前工作区 `docs/TID-R06-ocr-page-similarity-effective-new-content.md` 的维护者已提交修改（版本 1.1；本 Change 未改动该文件）。它补齐了 `ReferenceResolution`、`R06CandidateSummary`、warning count、跨层冲突与低置信度合同。
- 开始时没有无法归属的 tracked 修改。既有未跟踪文件为 `README.md`、`docs/project-review.zip` 和 `venv-packages-before-reinstall.txt`；受保护的后两项未读取。

## 修改文件

- `ocr_records.py`: writer Schema 1.3、1.0—1.3 reader、R06 enums/value types、nested projection、candidate summary、manifest identity 与 disabled/record validation。
- `ocr_similarity.py`（新增）: `OcrSimilarityConfig`、canonical snapshot/digest/restore、纯 reference resolver 与 R03 persisted-hash adapter。
- `tests/test_ocr_records.py`、`tests/test_ocr_similarity.py`（新增）: Schema、value type、projection、reader、config、resolver 与 hash adapter 覆盖。
- `tests/test_ocr_normalization.py`: 两处 writer-version 断言从 1.2 更新为 1.3；没有改变 R04 行为、文本或算法。

## Schema 与兼容

- `STORAGE_SCHEMA_VERSION = "1.3.0"`；reader 保留 `1.0.0`、`1.1.0`、`1.2.0`、`1.3.0`。
- screen 的唯一 R06 权威是 `similarity_result`；candidate 为 `similarity_summary`；RunManifest 保存 mode、版本、config digest/snapshot 与业务短词 identity。
- 旧顶层 `similarity_hash`、`similarity_score`、`overlap_ratio`、`new_text_ratio`、`has_effective_new_text`、`similarity_version` 仅为 nested result projection。nested 不存在时它们强制为 null；存在时逐字段一致。
- 旧 1.0—1.2 读取恢复为 result/summary null、mode disabled；reader 忽略未来 additive 字段并拒绝缺失 1.3 required 字段。

## Value types、warning 与 reference

- 实现 TID 冻结的 similarity/effective/reference enums、`NgramScore`、`EffectiveNewDecision`、`ReferenceResolution`、`OcrSimilarityResult`、`R06WarningCodeCount` 与 `R06CandidateSummary`，保持 TID 声明顺序和 summary 三组会计。
- 字段顺序：`ReferenceResolution` 为 `status, reference_screen_id, reference_screen_index, reference_capture_type, reference_source, warning_codes`；`OcrSimilarityResult` 依次为状态/reference/R03、主要分数与 ngram、SimHash、R05 counts、三个 ratio numerator/denominator/value、effective-new、class、identity、warnings；`R06CandidateSummary` 依次为 identity、screen 总数、status 分区、class 分区、effective-new 分区、warning 总数和按白名单顺序的 warning counts。测试还直接断言 result 起始字段顺序及 summary 的全分区会计。
- warning 为白名单、稳定白名单顺序、去重；含批准项 `cross_layer_similarity_conflict`，不接受自由文本。
- resolver 不读 JSONL、不依赖容器顺序、不修改输入：正式首屏为 no-reference；后续只接受同 run/候选人的唯一 `screen_index - 1` 正式屏；旧正式 Schema 使用 `reconstructed_formal_index`。非正式屏只接受合法显式 reference；旧非正式无 link 返回 `legacy_reference_unavailable`。
- R03 adapter 只校验 persisted 64 位小写 hash 和 `r03-v1`，返回 true/false/null 与固定 warning；不重算、不覆盖 hash。

## Config 与 disabled

`OcrSimilarityConfig` 是 frozen dataclass。snapshot 使用 UTF-8、sort keys、紧凑 separators、`allow_nan=False`，digest 为 SHA-256 小写 hex；测试覆盖跨进程/PYTHONHASHSEED 稳定及参数变化改变 digest。

低置信度参数固定保存：`effective_min_confidence=0.85` 来自 `ocr_normalization.DEFAULT_OCR_NORMALIZATION_CONFIG` 的唯一 R04 OCR acceptance threshold；`low_confidence_delta=0.03`、`low_confidence_max_chars=2` 来自 TID 9.4。它们均为 config 的显式字段、进入 snapshot/digest 和 record manifest；此 Change 未接入 Replay，故未发生运行时全局读取。

默认 `R06_SIMILARITY_MODE` 为 `disabled`。disabled 1.3 screen/candidate/manifest 分别为 result null、summary null，以及除 mode 外所有 R06 manifest identity null；未伪造 0、false 或 completed。

## 验证

- `python -m unittest tests.test_ocr_records tests.test_ocr_similarity tests.test_ocr_candidate -v`: PASS，44 tests。
- `python -m unittest discover -s tests -q`: PASS，660 tests。
- `python -m tests.benchmark_r04_normalization`: PASS。
- `python -m tests.benchmark_r05_aggregation`: PASS。
- `python -m compileall -q ocr_records.py ocr_similarity.py tests`: PASS。
- `python -m pip check`: PASS (`No broken requirements found`)。
- `git diff --check`: PASS；只有既有 Git LF/CRLF warning，无 whitespace error。

## 日志/data 隔离与最终状态

未读取真实正文。测试后 inventory 与开始前一致：`logs/simple_brush.log` 为 7,372,745 bytes、mtime `2026-08-01T07:15:54.4076423Z`、SHA-256 `1be253b07b246aa1b9f3f207f5c22876fa8116a13da13959221eccc2ac62af96`；`data/ocr_runs` 保持同一目录和四个 0-byte 文件、mtime/SHA-256 unchanged。

最终 tracked 修改：维护者的 TID Corrective、`ocr_records.py`、`tests/test_ocr_normalization.py`、`tests/test_ocr_records.py`；新增未跟踪实现/测试：`ocr_similarity.py`、`tests/test_ocr_similarity.py`。未执行 git add、commit、push、tag 或 release。

## 是否允许进入 Change 3

**允许进入 Change 3，但本聊天框在 Change 2 后停止，等待维护者审阅。**
