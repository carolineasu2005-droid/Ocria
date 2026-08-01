# R04 Change 7 阻塞审计报告

> **Pre-acceptance blocking audit**
>
> **不是最终 Acceptance Report。** 本文保存修复 Change A—D 之前的阻塞事实和证据边界。后续修复结果单列，不反写为“当时已经通过”。

## 1. 报告性质与证据口径

本报告归档首次执行 R04 Change 7 时发现的阻塞项。该次验收没有把完整控制台输出或 benchmark JSON 保存到仓库；现存可恢复证据来自后续修复 Change A—D 的冻结请求、获批 RPD/TID、修复链开始时保留的工作区和对应代码差异。因此：

- 能由这些材料确认的旧状态按事实记录；
- 原始命令的精确测试数量、逐项耗时若没有持久化证据，明确写“未持久化”，不以修复后的数字代替；
- 旧性能热点采用 Change B 中冻结的阻塞数值，不用本次新 benchmark 反写；
- 本文不授予 shadow deployment、enforce 或正式生产放行。

## 2. 当时验收结论

结论：**阻塞。** 阻塞不是单一 unittest 失败，而是实现偏离获批 RPD/TID 的安全边界、算法合同、数据合同与日志隐私边界。尤其是 R03 exact hash 和本地规则动作权威曾被错误改变，因此即使部分自动化断言通过，也不能形成 R04 验收结论。

### 2.1 当时测试结果

| 项目 | 当时可恢复状态 |
|---|---|
| R04/阶段 0/OCR 自动化 | 曾执行，但原始逐命令 stdout、精确数量和耗时没有保存为文件，当前不可审计地恢复；不得用修复后的 586 项结果代替。 |
| 静态合同审计 | 未通过：发现混合 R03/R04 指纹、非纯 legacy shadow、`partial`、模糊重复删除及日志隐私问题。 |
| 性能验收 | 未通过：dense 500 同位同文路径物化约 124,750 个完整 pair，对应约 2 秒 normalization、约 148 MiB 峰值。 |
| Windows + Edge 人工验收 | 未执行，不能由 mock 或纯合成数据替代。 |

缺少原始测试 stdout 本身是旧验收归档缺口；Change D 通过正式 Acceptance Report 和可重复 benchmark 脚本补上未来证据，但不会伪造旧数字。

## 3. 当时设计偏差

### 3.1 R03 与动作权威

- R03 `r03-v1` 曾被混合为类似 `r03-v1+r04-v1` 的身份，R04 派生文本进入了本应只消费 confidence-accepted OCR items 的 exact hash 路径。
- R01 候选人切换依赖的 R03 指纹因此存在被 R04 normalization 结果改变的风险。
- 本地规则曾出现 R04 结果影响生产动作的近似 enforce 行为，不符合 Change 5A 的 `legacy_shadow`。
- normalization 失败时的回退与动作权威没有清晰区分，不能证明 `r04_only` 不触发 confirmation，也不能证明 `legacy_only` 完全保留旧动作。

### 3.2 Pure normalization

- 出现未获批准的 `partial` 状态；部分派生正文可能继续参与下游。
- bbox 合同没有完整覆盖任意点数 polygon、non-finite、零面积和原 shape 不变。
- 行分组等号边界不符合冻结的 `<=`/`>=` 语义。
- 同行连接 gap ratio 没有统一使用全屏有效框高的 median。
- 重复框使用 `SequenceMatcher`/模糊文字相似，可能删除只相似而非 exact 的业务文字。
- survivor 优先级、A-B-C 非传递合同与灰区保留不完整。
- dense 场景构造完整 pair matrix，造成上述时间和内存阻塞。

### 3.3 Schema、Store 与 Replay

- normalization 状态组合未严格限制为 `not_attempted/completed/failed`。
- manifest 缺少完整历史 config snapshot、canonical digest 和实际阈值权威。
- screen/manifest config identity 未在写盘前拒绝不一致记录。
- candidate 缺少可复算的正式/非正式六项 summary。
- duplicate trace、segment source ID、灰区/eligible/low-confidence/empty 计数不完整。
- replay 可能依赖当前默认值，不能证明使用历史配置、保持 exact hash、保持 source 不变或实现 strict/tolerant 脱敏失败合同。

### 3.4 日志隐私

普通日志曾直接记录：

- 启动配置中的备选邮箱；
- “最近联系”自动填入的完整邮箱或输入框内容；
- 手动回退使用的完整邮箱；
- 规则原文和命中关键词；
- 带原始 exception message/traceback 的异常。

历史 `logs/simple_brush.log` 可能已包含旧地址。该文件不属于 Git 跟踪内容，修复不得删除、截断或改写历史，只能阻止未来日志继续泄露。

## 4. 当时性能数据

| 场景 | 当时阻塞数据 | 阻塞原因 |
|---|---:|---|
| dense 500，同位同文 | 124,750 个完整 pair | 近似完整 O(n²) pair materialization |
| dense 500 normalization | 约 2 秒 | 超过 `500 boxes p95 < 50ms` 门槛数量级 |
| dense 500 峰值内存 | 约 148 MiB | 超过受控 pure normalization 的合理预算 |

当时未留下 0/1/8/100/500 全矩阵的 median、p95、GC retained 和 determinism JSON，因此这些字段在本历史报告中保持“不可恢复”，不引用修复后的数据。

## 5. 当时 Git 状态与范围

修复链开始时继续保留的分支/提交为：

```text
branch: main
HEAD: 54ae0648ccf9c7066d363bd986dfc9b16671af44
```

从 Change A 开始检查及后续连续工作区可确认的路径形态如下；这是对保留工作区的归档，不是重新生成的旧控制台 stdout：

```text
 M ocr_candidate.py
 M ocr_detector.py
 M ocr_records.py
 M ocr_replay.py
 M ocr_store.py
 M ocr_text.py
 M simple_brush.py
 M tests/test_ocr_candidate.py
 M tests/test_ocr_detector.py
 M tests/test_ocr_records.py
 M tests/test_ocr_replay.py
 M tests/test_ocr_stage0_integration.py
 M tests/test_ocr_store.py
 M tests/test_simple_brush_ocr.py
?? docs/project-review.zip
?? ocr_normalization.py
?? tests/test_ocr_normalization.py
?? venv-packages-before-reinstall.txt
```

这些修改当时均未 commit、未 push；本阻塞报告也不改变这一事实。

## 6. 后续修复链（不改写旧状态）

| 修复 | 后续完成内容 | 与旧状态的关系 |
|---|---|---|
| Change A | 恢复 R03 `r03-v1` 原算法/输入；建立真正 `legacy_shadow`；legacy 保持唯一动作权威；R04 shadow 使用 `comparison_text`。 | 修复旧安全边界，不表示旧验收已通过。 |
| Change B | 删除 `partial`；修正 bbox/行边界/median gap；改为 exact text + geometry；survivor sweep；满足性能门槛。 | 修复旧算法和性能阻塞。 |
| Change C | 补齐 1.0/1.1 schema、manifest config、screen identity、Store 拒写、summary、trace 和完整 replay。 | 修复旧数据合同阻塞。 |
| Change D | 修复未来日志邮箱/规则/异常泄露；保存本报告；重新执行正式 Change 7。 | 新结果只写入正式 Acceptance Report。 |

## 7. 阻塞关闭条件

本历史审计中的代码、算法、schema、replay、性能和未来日志阻塞，只有在新的正式 Acceptance Report 提供自动化、性能、隐私及范围证据后才能关闭。即使这些项目关闭：

- 未执行的真实 Windows + Edge shadow 仍保持未通过；
- Change 5B enforce 仍须独立维护者批准；
- 正式生产仍须真实 shadow 数据、差异分类、人工验收和发布批准。

本文到此停止作为历史证据，不承担最终放行结论。
