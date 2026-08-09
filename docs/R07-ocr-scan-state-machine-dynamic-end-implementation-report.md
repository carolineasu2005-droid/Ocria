# BossOCR R07 OCR 扫描状态与动态结束 — 实施完成报告

## 1. 基线 HEAD

- 基线提交：`b9b7d7c9ff173a9c5ce5c7c019d35d3a2ddb9d25`
  （`feat(ocr): add R07 replay and integration coverage`）
- 分支：`r07-claude-corrective`（从 main 创建，ahead 21）

## 2. 修复后 HEAD

- 修复提交 SHA：`[见 git log]`
- 所有修复在本地分支 `r07-claude-corrective` 上

## 3. 修改文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `ocr_replay.py` | 生产代码 | G1：legacy_rule_completed 只来自 rule_confirmation；G2：evidence completeness gate |
| `ocr_detector.py` | 生产代码 | G3：_final_confirmation_capture_type；G5：safe/full 规则分支 Store 优先级 |
| `simple_brush.py` | 生产代码 | G3：confirmation changed promotion；G4：manifest mode 使用 DYNAMIC_END_CONFIG.mode |
| `tests/test_ocr_replay.py` | 测试 | G1/G2 回归测试（IMP-001/IMP-002） |
| `tests/test_ocr_detector.py` | 测试 | G3/G5 回归测试（IMP-003/IMP-005） |

## 4. 5 个缺陷状态

| 缺陷 | 根因组 | 状态 |
|---|---|---|
| R07-IMPL-001 | G1 Replay rule completion | **CLOSED** |
| R07-IMPL-002 | G2 Replay evidence completeness | **CLOSED** |
| R07-IMPL-003 | G3 Confirmation capture type | **CLOSED** |
| R07-IMPL-004 | G4 Manifest config source | **CLOSED** |
| R07-IMPL-005 | G5 Safe/full Store priority | **CLOSED** |

## 5. Replay 规则完成语义

`replay_dynamic_end()` 现在只在 `capture_type == rule_confirmation` 且 `legacy_match is True` 的已保存 record 上认定 legacy 规则完成。`formal_screen.legacy_match=True`（首次规则候选命中）不能使 completion 或 rule_miss 为 true。确认失败时 rule_miss 保持 null。旧 schema 没有 rule_confirmation record 时 completion 为 false。

## 6. Replay 证据完整性

`replay_dynamic_end()` 现在将以下情况视为 insufficient_evidence：
- `prediction_observation_complete is False` 或 `prediction_evidence_complete is False`
- 两个 complete 字段均为 null 的旧 schema
- Store 失败导致证据不完整但 abort 为 null
- 持久化字段间不一致

健康的 possible_scroll_bottom 只在两个 complete 字段均不为 False/null，且 prediction 存在的条件下输出。

## 7. Confirmation Changed 路径

- `_position_confirmation_capture_type()`：pre-classification（仅基于 raw exact hash）
- `_final_confirmation_capture_type()`：final classification（基于 canonical PositionDecision）
- `_attempt_position_confirmation()`：pre → callback → 获得 decision → final → 更新 state
- `_record_ocr_observation_result()`：position_confirmation + decision changed → promote 为 formal_screen
- 同一次 capture 只 build/save 一次

## 8. Manifest 配置来源

`create_ocr_record_store()` 现在使用 `DYNAMIC_END_CONFIG.mode`（与 detector 同一来源），而不是独立的 `DYNAMIC_END_DEFAULT_MODE`。

## 9. Safe/Full Store 优先级

`detect()` 在 safe/full 规则命中分支调用 `_rule_confirmation_result()` 前先调用 `_safe_full_control_result()`。Store 失败（saved=False）优先于规则确认。off/shadow 不受影响。

## 10. 默认 Shadow

全局默认仍然是 `shadow`（`DYNAMIC_END_DEFAULT_MODE = "shadow"`）。未增加自动启用逻辑。

## 11. 定向测试

```
tests.test_ocr_replay       — 40 tests — PASS
tests.test_ocr_detector     — 111 tests — PASS
tests.test_ocr_stage0_integration — 26 tests — PASS
```

## 12. 综合回归

```
tests.test_ocr_detector tests.test_ocr_stage0_integration tests.test_ocr_replay
tests.test_ocr_records tests.test_ocr_store tests.test_ocr_candidate
tests.test_ocr_aggregation tests.test_ocr_similarity tests.test_ocr_normalization
tests.test_simple_brush_ocr
```
652 tests — **PASS**，20.310s

## 13. 全量测试

`python -m unittest discover -s tests -q`
755 tests — **PASS**，18.757s

## 14. Benchmark

- R04 归一化：PASS，deterministic，最大 peak 999.02 KiB
- R05 聚合：PASS，`required_performance_gates_pass=true`，`contract_blockers=[]`
- R06 相似度：PASS，`required_performance_gates_pass=true`
- 未降低任何已有门槛

## 15. Compile / Pip Check

- `python -m compileall`：通过
- `python -m pip check`：通过
- `git diff --check`：通过（仅 CRLF 转换提示）

## 16. 隐私

- 新代码和日志中没有新增完整 OCR 正文、姓名、手机号或邮箱
- 所有测试使用 synthetic mock 数据

## 17. Windows/macOS 声明

- Windows：所有合成自动化测试实际运行通过
- macOS：`replay_dynamic_end` 在 darwin 平台上纯逻辑验证通过（现有测试中已包含 `sys.platform` patch）

## 18. NOT RUN 项目

- 真实 BOSS 页面测试
- 真实候选人 record 测试
- 真实收藏/转发操作
- 生产 OCR run
- push/tag/Release

## 19. 是否建议进入 Shadow 冒烟

**是**。5 个缺陷全部关闭，全量验证通过。Shadow 不新增 OCR/滚动/等待/焦点恢复副作用，现有 legacy 控制流未改变。建议进行短程受控冒烟（≤5 个 synthetic 候选人）。

## 20. 是否建议进入 Safe 冒烟

**是**。Safe Store 优先级已按 TID 第 6 节冻结顺序修正。Confirmation changed 不再产生 `position_unresolved`。建议进行受控 safe bottom 冒烟（≤5 个 synthetic 候选人）。

## 21. 是否建议进入 Full 冒烟

**是**。Full 与 safe 共享同一优先级路径，no-new 计数逻辑未变。建议进行受控 full no-new 冒烟（≤5 个 synthetic 候选人）。

## 22. 剩余风险

1. **真实页面 OCR 波动**：synthetic 测试覆盖了控制流，但真实页面渲染差异可能导致 same/changed 分类边界变化
2. **R05/R06 disabled 场景**：大部分 synthetic 测试启用 R05/R06；disabled 场景的 shadow prediction 需要更多覆盖
3. **100 人 batch rollover**：未在合成测试中覆盖批量边界
4. **macOS 仅逻辑验证**：未在 macOS 上运行实际 OCR 引擎
5. **Confirmation 路径的单次 build/save 合同**：在 simple_brush callback 中通过 `replace_latest_screen_record` 实现，依赖 builder 内部状态正确性

---

## 最终声明

```text
R07 concentrated corrective completed
```

不是 `R07 final Acceptance PASS`。未声明生产启用。5 个缺陷全部关闭，全量验证通过。

修复人员：Claude Fable 5
日期：2026-08-02
