# R06 Change 4 — 会计与比例报告

## 总体结果

Change 4 已完成。实现纯 `compute_r05_accounting()` 与 `apply_r05_accounting()`：只复用 R05 已保存的 matched/new/uncertain ID partition 和 R04 segment，重算 counts、保存三组分子/分母/比例，并在任何不可验证情况 fail-open 为 null/partial/uncertain。未重跑全文 diff，未改 R05 分类、candidate document、R03/R04/R05 生产语义或线上流程。

## Git 基线与修改范围

- branch: `main...origin/main`
- HEAD / RPD/TID commit: `afc41d8f279e0218d892f7973d3e39b2d86bdf90` (`docs(ocr): define R06 page similarity`)
- R05 固定实现基线: `f02209c`
- Change 3 报告明确允许进入 Change 4；n-gram/SimHash、reference resolver、Schema 1.3 与 R05 contract tests 均通过。
- 本 Change 修改：`ocr_similarity.py`、`ocr_records.py`（仅 frozen result validation）、`tests/test_ocr_similarity.py`、`tests/test_ocr_records.py`、`tests/benchmark_r06_similarity.py`、本报告。
- 未修改 `ocr_aggregation.py`、`ocr_normalization.py`、`ocr_candidate.py`、Store/Replay 或 `simple_brush.py`；默认 similarity mode 仍为 disabled。

## R05 权威语义与 ID 映射

`compute_r05_accounting()` 只读取当前 `OcrScreenRecord.segments`、`matched_segment_ids`、`new_segment_ids`、`uncertain_segment_ids`，建立 `segment_id -> segment` 映射并验证：segment ID 唯一、三组 ID 无重复/无未知、完整覆盖且 `matched + new + uncertain` 保持 source order。

R05 `overlap_*` 是 matched；`new_text_char_count` 与 `new_segment_count` 是 `new + uncertain`；`uncertain_*` 是 uncertain。R06 因而单独保存确定 `new_char_count/new_segment_count`，绝不把 R05 的 new-text 投影误作确定新增。

字符数唯一使用 `ocr_aggregation.aggregation_char_count(segment.comparison_text)`；segment 数直接取三组 ID 的长度。合法数据满足：

```text
overlap + new + uncertain = current_effective
```

分别对 characters 和 segments 成立，并交叉验证全部 R05 保存投影：overlap chars/count、new+uncertain chars/count、certain-new count、uncertain chars/count。

## 失败降级、比例与零分母

partition overlap/gap、unknown/duplicate ID 产生 `segment_partition_invalid`；保存 projection 不符产生 `r05_projection_mismatch`；总数或字符计数异常产生 `accounting_mismatch`。任一失败时所有 R06 count、numerator、denominator、ratio 均为 null，effective-new status 为 unavailable，结果至少 partial 且 class 为 uncertain；已有独立 n-gram/SimHash 字段保持不变。

三个 ratio 都以 `current_effective_char_count` 为共同 denominator；numerator 分别为 overlap/new/uncertain chars。分母大于零时直接保存未 round 的 IEEE float，并验证范围和三项和距 1.0 不超过 config 的 `1e-12`。分母为零时四项 char count 为 0，真实 segment count 仍保存，三个 numerator/denominator 均为 0、ratio 为 null、warning 为 `zero_effective_char_denominator`，class 为 `empty_or_unavailable`。

R05 `not_attempted`、`failed`、缺失的旧记录均不可验证；partial 只有在完整可复算时保留 counts，同时带 `r05_partial` 并将 completed result 保守降为 partial/uncertain。

## 不可变性与测试

函数不接受或访问 candidate document/document segments；不会修改传入 screen、其 segment tuple、R05 ID tuples、match evidence 或 source occurrences。测试以调用前 `to_dict()` 对比验证输入 screen 无变化；R05 既有 aggregation tests 覆盖 document text/segments/evidence/occurrence 的 frozen contract。

新增覆盖包括合法全 new、mixed、all uncertain partial、zero denominator、Unicode/emoji、R05 not-attempted/failed、unknown ID、stored projection mismatch、count/ratio value validation，以及失败后独立 similarity score 保留。

## Benchmark 与回归

纯算法 benchmark 保持 release interpreter、预热 3、测量 25、inclusive p95、fixture 计时外。新增 `r05_accounting_64_segments`：p50 0.1158 ms、p95 0.1232 ms、peak 7.96 KiB。既有性能 gate 仍通过：20k pair p95 7.00/11.73/6.80 ms，8 adjacent pair p95 17.37 ms，最大峰值 592.38 KiB（均低于 15 ms / 100 ms / 16 MiB 门槛）。

- `python -m unittest tests.test_ocr_similarity tests.test_ocr_records tests.test_ocr_aggregation -v`: PASS，85 tests。
- `python -m tests.benchmark_r06_similarity`: PASS，全部 gate 通过。
- `python -m unittest discover -s tests -q`: PASS，671 tests。
- `python -m tests.benchmark_r05_aggregation`: PASS。
- `python -m compileall -q ocr_similarity.py ocr_records.py tests`: PASS。
- `python -m pip check`: PASS。
- `git diff --check`: PASS（仅既有 LF/CRLF warning，无 whitespace error）。

## 日志/data 隔离与 Git 状态

未读取或输出候选人正文。仅执行允许的 inventory：`logs/simple_brush.log` 仍为 7,372,745 bytes、mtime `2026-08-01T07:15:54.4076423Z`、SHA-256 `1be253b07b246aa1b9f3f207f5c22876fa8116a13da13959221eccc2ac62af96`；`data/ocr_runs` 保持一个目录条目，mtime `2026-08-01T07:15:54.4066427Z`。

最终 tracked 修改为维护者 TID Corrective、Change 2 的 `ocr_records.py`/`tests/test_ocr_normalization.py`/`tests/test_ocr_records.py`，以及本 Change 对 records tests 的冻结 validation；新增未跟踪 Change 2—4 的 `ocr_similarity.py`、similarity tests 和 benchmark。既有未跟踪 `README.md`、受保护的 zip 与 venv 清单保持未读。没有无法归属的 tracked 修改；未执行 git add、commit、push、tag 或 release。

## 是否允许进入 Change 5

**允许进入 Change 5，但本聊天框在 Change 4 后停止，等待维护者审阅。**
