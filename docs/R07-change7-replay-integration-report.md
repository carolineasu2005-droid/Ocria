# R07 Change 7：Replay、兼容与实施收口报告

## 范围与基线

- 基线提交：`e51da01a4aaec5f12a02d819ab562d658dcc62e1`
  (`feat(ocr): enable R07 safe and full scan returns`)。
- 权威设计已复读：RPD/TID 均为 1.2（最终逻辑修订）；本 Change 未采用 preview、clone、
  生命周期 reducer、Sidecar 或 event ledger。
- 开始时 `main` 比 `origin/main` ahead 20；已有未跟踪的 `README.md`、
  `docs/project-review.zip`、`venv-packages-before-reinstall.txt` 保持未修改、未暂存。

## Replay

`ocr_replay.replay_dynamic_end(candidate)` 新增 CandidateOcrDocument 级纯内存入口，按
`candidate.screens` 已保存的原有顺序读取并重放：R07 position、full no-new 谓词及 shadow
first-prediction/miss 事实。返回独立的 `DynamicEndReplayResult`，不引用或改写 source。

- 只读取已持久化的 R03/R05/R06 投影；不重跑 R03--R06，不 OCR、截图、滚动、等待、点击、
  焦点恢复或 Store 写入。
- 离线 bottom 结果严格限于 `possible_scroll_bottom` 或 `insufficient_evidence`；不会产生
  在线 `scroll_bottom` 确认。
- 旧记录缺少 R07 position 时，首条仅按顺序标为 `initial`，其余为 `unavailable`，并设置
  `insufficient_evidence`；不会伪造健康或负向漏采结论。
- Replay 保留 source 中的 nullable prediction/miss/complete 字段；预测后的 legacy 规则命中
  可重放为 `prediction_would_miss_rule_match=true`，内容窗口未完整时保持 `null`。
- `abort_reason=store_failed`（或已有 abort/interrupted）会使离线 conclusion 为不足证据，且
  不会二次保存。

## 修改文件

- `ocr_replay.py`
- `tests/test_ocr_replay.py`
- 本报告

没有修改生产扫描控制流、Schema、Store writer、R01、无关键词路径、batch 或上层动作。

## 兼容、平台与隐私覆盖

- Screen、Candidate、Manifest R07 round-trip 与旧 Schema reader 回归通过；旧字段恢复为
  `None`，legacy rule completion 保留 `dynamic_end_reason=null`。
- 覆盖 Store false、四个 nullable prediction 字段、Unicode、顺序重放、连续 no-new、
  offline-bottom 限制及 source 不变。
- Windows mock（`win32`）与 macOS pure（`darwin`）重放结果相同；Replay 无平台或 UI 依赖。
- Replay 不记录 OCR 正文、手机号或邮箱；测试以 Unicode、手机号和邮箱样本断言返回对象不含
  原始 OCR 文本。测试日志中的 Store failure 是既有负向 Store 用例的受控事件，不是新日志格式。

## 测试

| 命令 | 结果 |
| --- | --- |
| `python -m unittest tests.test_ocr_replay -q` | PASS，28 tests，0.206s |
| `python -m unittest tests.test_ocr_replay tests.test_ocr_records tests.test_ocr_store -q` | PASS，77 tests，15.305s |
| `python -m unittest discover -s tests -q` | PASS，729 tests，17.213s |
| `python -m pip check` | PASS：No broken requirements found |
| `git diff --check` | PASS |

全量测试输出中的 `ocr_store_write_failed`、`ocr_store_disabled` 和
`r06_candidate_summary_failed` 来自既有失败分支测试；全量命令以退出码 0 完成。

## Benchmark

### R04 normalization

所有场景均 deterministic：`unique-0` 0.0262/0.0322ms、`unique-1` 0.0719/0.0789ms、
`unique-8` 0.2463/0.2587ms、`unique-100` 2.4948/3.3271ms、`unique-500`
15.3238/16.9055ms、`far-same-text-500` 11.1881/12.5679ms、
`dense-same-position-text-500` 11.8635/14.0906ms、
`dense-100-repeated-identical` 2.3914/3.2919ms（数值为 median/p95）。

### R05 aggregation

`required_performance_gates_pass=true`、`contract_blockers=[]`、所有场景
`contract_ok=true`、deterministic=true；有门槛的 p95 均通过：

| 场景 | p50/p95 ms | 门槛 |
| --- | ---: | --- |
| 8x64_unique_pure | 14.6327 / 15.6857 | 20，PASS |
| 8x128_unique_pure | 25.6661 / 28.2860 | 无 |
| 8x256_unique_pure | 49.8991 / 52.2533 | 150，PASS |
| 8x64_unique_record_projection_candidate_finalize | 18.8773 / 20.7718 | 30，PASS |
| 8x64_exact_50_percent | 11.2616 / 12.4343 | 无 |
| 8x64_exact_90_percent | 10.1240 / 12.2100 | 无 |
| complete_screen_duplicate | 9.7511 / 11.5528 | 无 |
| one_new_line_per_screen | 9.7551 / 10.7791 | 无 |
| single_screen_fuzzy_1_to_1 | 0.3379 / 0.5241 | 50，PASS |
| single_screen_fuzzy_1_to_2 | 0.3619 / 0.4127 | 50，PASS |
| single_screen_fuzzy_2_to_1 | 0.3872 / 0.5150 | 50，PASS |
| single_screen_fuzzy_uncertain | 0.3186 / 0.5090 | 50，PASS |
| 8x64_near_duplicate_fuzzy_stress | 35.9079 / 38.0675 | 无 |
| historical_n_minus_2 | 0.3662 / 0.4672 | 无 |
| historical_ambiguous | 0.7814 / 1.2733 | 无 |
| 8x256_exact_50_percent | 50.9167 / 56.0426 | 无 |
| fuzzy_candidate_limit_1_contract | 0.2487 / 0.2859 | 无 |
| 257_segment_limit_contract | 3.8582 / 4.7710 | 无 |

除最后一个无设定 memory gate 的 contract 场景外，R05 所有场景 `memory_pass=true`。

### R06 similarity

`required_performance_gates_pass=true`。全部场景结果（p50/p95 ms）：
`20k_exact_same` 5.8020/7.4254（15，PASS）；`20k_50_percent_changed`
9.1989/11.8151（15，PASS）；`20k_repeated_ngram_stress` 5.2203/7.0516（15，PASS）；
`short_pair` 0.0338/0.0351；`unicode_pair` 8.3439/11.4341；`100k_boundary`
63.8699/69.7403；`100001_reject` 0.0126/0.0136；`r05_accounting_64_segments`
0.1171/0.1370；`8_adjacent_pairs` 12.7894/16.6400（100，PASS）；
`r05_record_only_8_screens` 1.7938/2.7670；`r06_calculation_only_8_screens`
2.9621/3.7726；`r05_r06_record_builder_8_screens` 5.4120/6.6492；
`r05_r06_disabled_builder_8_screens` 0.0428/0.0458；`r05_r06_replay_8_screens`
3.2461/4.4234；`r06_sidecar_synthetic_8_screens` 14.2499/16.5949。

## Change 1--7 提交链

1. `00adbc1` `docs(ocr): finalize R07 dynamic ending design`
2. `dd60156` `test(ocr): establish R07 implementation baseline`
3. `1fcacdb` `feat(ocr): add R07 schema and state foundations`
4. `76bb3db` `feat(ocr): classify R07 scan positions`
5. `8b1e6da` `feat(ocr): add R07 scroll bottom confirmation`
6. `2557064` `feat(ocr): integrate R07 shadow analysis`
7. `e51da01` `feat(ocr): enable R07 safe and full scan returns`
8. 本 Change 的提交将追加为 `feat(ocr): add R07 replay and integration coverage`。

## 已知问题与 Queue 8

- 本任务未进行最终独立 Acceptance，未运行真实页面或真实 record，也没有集中修复。
- Change 1 所记的 R05 历史 Acceptance 状态仍应由 Queue 8 独立审查；本次执行的当前 R05
  benchmark 门槛通过并不替代该审查。
- 实现与阶段性回归已收口，可以进入 Queue 8 完整审查；这不是最终 Acceptance PASS 或生产
  发布结论。
