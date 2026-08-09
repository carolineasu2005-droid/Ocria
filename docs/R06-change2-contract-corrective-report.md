# R06 Change 2 前置合同补全 Corrective Report

## 1. 本轮范围与原阻塞

本轮只补齐 R06 正式 TID 中 Change 2 实施前缺失的数据合同，不实施 Schema、resolver、evaluator、summary builder 或其他生产逻辑。

Change 2 原阻塞来自正式 TID 的两个合同缺口：

1. `ReferenceResolution` 只有 resolver 返回类型名称和零散引用规则，缺少完整状态枚举、字段/JSON 顺序、各状态不变量及到 result 的投影；
2. `R06CandidateSummary` 只有概念性描述，缺少完整字段/JSON 顺序、存在语义、空 summary、warning 聚合和全分区会计合同。

此外，维护者批准的跨层 warning 与低置信度配置 identity 也尚未完整冻结，因而不能安全进入 Change 2 实施。

## 2. 新增 `ReferenceResolution` 合同

正式 TID 已冻结：

- `ReferenceResolutionStatus`：`resolved`、`no_reference`、`unavailable`；
- `ReferenceSource`：`none`、`formal_previous_index`、`explicit_record`、`reconstructed_formal_index`；
- 六个字段及其声明/JSON 序列化顺序；
- `resolved`、`no_reference`、`unavailable` 的字段不变量；
- 三种 resolution 状态到 `OcrSimilarityResult` 的投影；
- resolver 只能返回该 value type，evaluator 不得重新选择 reference；
- resolution warning 必须合并进 result warning，并按 warning 白名单顺序稳定去重。

`OcrSimilarityResult.reference_source` 的类型也已明确为 `ReferenceSource`，与 resolution 合同一致。

## 3. 新增 `R06CandidateSummary` 合同

正式 TID 已冻结 `R06CandidateSummary` 的 23 个字段及声明/JSON 顺序，并冻结 `R06WarningCodeCount` 的字段顺序：

1. `warning_code: str`；
2. `count: int`。

`warning_code_counts` 只保存正计数项，按 warning 白名单声明顺序排列；同一 screen 的同一 warning 最多计数一次。

存在语义已冻结为：

- Schema 1.0—1.2：`similarity_summary=null`；
- Schema 1.3 disabled：`similarity_summary=null`；
- Schema 1.3 record：`similarity_summary` 必须存在。

record 模式没有 screen 时仍须保存合法空 summary：identity 与 `RunManifest` 一致，所有 count 为 0，`warning_code_counts=()`。

## 4. Summary 会计与来源

正式 TID 已冻结四项会计关系：

1. 所有 `SimilarityStatus` 计数之和等于 `screen_count`；
2. 所有 `ComparisonClass` 计数之和等于 `screen_count`；
3. 所有 `EffectiveNewStatus` 计数之和等于 `screen_count`；
4. `warning_code_counts` 的 count 总和等于 `warning_count`。

Summary 只能从 `CandidateOcrDocument.screens[*].similarity_result` 纯重算，不得读取页面状态、日志、正文、module global、Store manifest counters 或其他全局计数。record 模式下不能跳过缺少合法 result 的 screen 来拼出 summary。

## 5. 跨层 warning

`cross_layer_similarity_conflict` 已正式加入 warning 白名单。

TID 已明确它与 `accounting_mismatch` 的边界：前者表示各层内部合同可验证、但 R03 exact 结论与 R04/R05 派生信号互相矛盾；后者只表示 R05 内部会计或 stored projection 不成立。

维护者批准的触发与投影语义已冻结：命中时记录该 warning，投影为 `partial`/`uncertain`，保留各层内部仍合法的 exact、similarity、count、ratio 和 effective 证据，并进入 candidate summary；它不影响扫描、动作或停止控制流。

## 6. 低置信度配置

正式 TID 已冻结：

```text
effective_min_confidence = 0.85
low_confidence_delta = 0.03
low_confidence_max_chars = 2
```

三项均属于 `OcrSimilarityConfig`，必须进入 canonical config snapshot、config digest 和 `RunManifest.similarity_config`。Replay 必须从 manifest snapshot 恢复，禁止动态读取当前全局默认值补写历史记录。

来源已记录：`effective_min_confidence` 来自当前 R04 `DEFAULT_OCR_NORMALIZATION_CONFIG` 的有效 OCR 最低置信度；其余两项来自 R06 有效新增合同。

旧记录缺失完整配置或 confidence 证据时，不得判为 `low_confidence_noise`，必须保守输出 `uncertain`。

## 7. 修改文件

本轮文件范围仅为：

- 修改：`docs/TID-R06-ocr-page-similarity-effective-new-content.md`；
- 新增：`docs/R06-change2-contract-corrective-report.md`。

## 8. Git 状态与检查

检查基线：

- branch：`main`；
- HEAD：`afc41d8f279e0218d892f7973d3e39b2d86bdf90`；
- `main...origin/main`。

最终执行：

```powershell
git diff -- docs/TID-R06-ocr-page-similarity-effective-new-content.md
git diff --check
git status -sb
git status --short --untracked-files=all
```

结果：TID 是唯一 tracked 修改；`git diff --check` 通过。下列三个无关未跟踪项在本轮开始前已存在并保持不变：

```text
README.md
docs/project-review.zip
venv-packages-before-reinstall.txt
```

新报告受仓库 `.gitignore` 第 20 行 `*.md` 规则忽略，因此普通 `git status` 不列出它；已单独核对文件存在。若后续需要纳入提交，应在提交阶段显式处理 ignored 文件，本轮不改 `.gitignore`。

## 9. 未实施声明

本轮未修改生产代码、测试代码、Schema 常量、配置、依赖、构建脚本或 workflow；未新增或修改任何运行时 Schema 实现，也未进入 Change 2 实施。

由于这是纯文档合同 corrective，本轮未运行生产/测试套件；只执行请求规定的 Git 与格式检查。

## 10. Change 2 重新执行条件

结论：**原数据合同阻塞已补齐，已具备重新执行 Change 2 的合同条件。**

这不代表 Change 2 已实施或验收。重新执行时仍须从 Change 2 起点开始，并满足 TID 中原有进入条件：Change 1 文档及本 corrective 获批准、工作区 R05 变更归属明确、R05 Schema/reader 测试通过。本文档在此停止，不继续实施 Change 2。
