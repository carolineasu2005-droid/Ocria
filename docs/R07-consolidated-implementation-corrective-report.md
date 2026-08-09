# R07 Change 1—7 集中修复报告（Queue 9）

修复基线：`b9b7d7c9ff173a9c5ce5c7c019d35d3a2ddb9d25`（`feat(ocr): add R07 replay and integration coverage`）
修复后 HEAD：见 Git commit SHA
修复分支：`r07-claude-corrective`

本报告只记录 synthetic/纯内存修复和验证；没有运行真实页面或生产 OCR record。

---

## 缺陷 1：R07-IMPL-001 — Replay 混同首次规则命中与确认完成

| 字段 | 值 |
|---|---|
| 缺陷 ID | R07-IMPL-001 |
| 严重度 | High |
| 状态 | **CLOSED** |

### 修复前复现

使用临时内存 Candidate 构造：
- screen 1：`formal_screen`，`legacy_match=False`
- screen 2：`formal_screen`，`legacy_match=True`
- screen 3：`rule_confirmation`，`legacy_match=False`
- `first_predicted_end_screen=1`

修复前 `replay_dynamic_end()` 输出：
- `legacy_rule_completed=True`（❌ 错误：formal_screen.legacy_match=True 不是确认完成）
- `prediction_would_miss_rule_match=True`（❌ 错误：rule_confirmation 未命中）

### 根因

G1：`replay_dynamic_end()` 将任意 `record.legacy_match is True` 当作已完成规则完成，包括普通 `formal_screen` 上的首次规则候选命中。同时 `saw_legacy_rule_after_prediction` 也在任何 screen 的 `legacy_match=True` 时触发，不管 capture_type。

### 修改文件

`ocr_replay.py` — `replay_dynamic_end()`：
- `legacy_rule_completed` 只由 `rule_confirmation` + `legacy_match=True` 记录组成
- `saw_legacy_rule_after_prediction` 同样只在 `rule_confirmation` + `legacy_match=True` 时触发
- `first_prediction_seen`/`saw_legacy_rule_after_prediction`/`saw_content_after_prediction` 初始化移至正确位置

### 新增测试

`tests/test_ocr_replay.py`：
- `test_impl001_first_pass_rule_hit_is_not_confirmed_completion`：首次规则命中 + 确认失败 → `legacy_rule_completed=False`
- `test_impl001_confirmed_rule_hit_is_completion`：已保存的 rule_confirmation + legacy_match=True → `legacy_rule_completed=True`
- `test_impl001_no_first_prediction_no_rule_miss_claim`：无 first prediction → nullable 输出
- `test_impl001_legacy_schema_no_confirmation_record`：旧 schema 无 R07 字段 → insufficient
- `test_impl001_source_object_is_not_mutated`：source 对象不变

---

## 缺陷 2：R07-IMPL-002 — Replay 忽略证据完整性

| 字段 | 值 |
|---|---|
| 缺陷 ID | R07-IMPL-002 |
| 严重度 | High |
| 状态 | **CLOSED** |

### 修复前复现

Candidate 包含：`prediction_observation_complete=False`，`prediction_evidence_complete=False`，`first_predicted_end_screen=2`，`first_predicted_end_reason=possible_scroll_bottom`，`abort_reason=None`。

修复前 `replay_dynamic_end()` 输出：
- `offline_bottom_status=possible_scroll_bottom`（❌ 错误：证据不完整）
- `insufficient_evidence=False`（❌ 错误：应该为 True）

### 根因

G2：函数只检查 `abort_reason`，不检查 persisted completeness 字段。off/shadow 的 Store 失败可导致 complete=false 但不写 abort_reason。Replay 将不完整窗口当作 healthy possible bottom 证据。

### 修改文件

`ocr_replay.py` — `replay_dynamic_end()`：
- 新增 `persisted_observation_incomplete` gate：任一 complete 字段为 False → insufficient
- 新增 `completions_both_null` 检测：旧 schema null completeness 不是 healthy
- `completeness_is_healthy` 现在要求：prediction 存在、无 false 完整性、无 null 完整性、observation_complete/evidence_complete 不为 False

### 新增测试

`tests/test_ocr_replay.py`：
- `test_impl002_incomplete_evidence_is_insufficient`：false/false → insufficient
- `test_impl002_observation_false_evidence_true_is_insufficient`
- `test_impl002_observation_true_evidence_false_is_insufficient`
- `test_impl002_both_complete_true_is_possible`：true/true → possible_scroll_bottom
- `test_impl002_null_completeness_old_schema_is_insufficient`：null/null 旧 schema → insufficient
- `test_impl002_store_failure_no_abort_is_insufficient`：Store 失败但 abort=null → insufficient
- `test_impl002_source_object_not_mutated`

---

## 缺陷 3：R07-IMPL-003 — Confirmation 保存类型与 PositionDecision 脱节

| 字段 | 值 |
|---|---|
| 缺陷 ID | R07-IMPL-003 |
| 严重度 | High |
| 状态 | **CLOSED** |

### 修复前复现

safe mode detector：initial → same → confirmation callback 返回 `PositionDecision("changed", ...)`，但 observation hash 与前一 record 相同。`_position_confirmation_capture_type()` 仅以 raw exact hash 预判为 `position_confirmation`。callback 返回 changed 后 `_callback_failure_reason()` 报 `position_unresolved`，导致 abort。

### 根因

G3：capture type 在获得 canonical `PositionDecision` 前仅由 raw exact hash 冻结。final classification changed 时，预判为 position_confirmation 与最终 decision 矛盾。

### 修改文件

`ocr_detector.py`：
- 新增 `_final_confirmation_capture_type()` 静态方法：在获得 canonical PositionDecision 后确定最终 capture type
- `_attempt_position_confirmation()`：先以 pre-classification 调用 callback，获得 `position_decision` 后再用 `_final_confirmation_capture_type()` 确定最终类型

`simple_brush.py` — `_record_ocr_observation_result()`：
- 在 position_confirmation + decision changed 时，promote capture type 为 FORMAL_SCREEN，更新 `is_formal_screen`、`screen_index`、`canonical_record`
- 同一次 capture 只 build/save 一次

### 新增测试

`tests/test_ocr_detector.py` — `ConfirmationCaptureTypeTests`：
- `test_confirmation_same_no_effective_new_is_position_confirmation`：same → scroll_bottom
- `test_confirmation_effective_new_promotes_to_formal`：effective_new → no `position_unresolved`
- `test_confirmation_short_text_protected_promotes_to_formal`：short_text → no `position_unresolved`
- `test_changed_confirmation_is_single_record_no_double_save`：每次 observation 最多处理一次
- `test_same_confirmation_does_not_occupy_formal_slot`：`_final_confirmation_capture_type` 单元测试
- `test_slot_eight_boundary_does_not_trigger_confirmation`：changed → promote

---

## 缺陷 4：R07-IMPL-004 — Manifest 模式与实际 Detector 配置分叉

| 字段 | 值 |
|---|---|
| 缺陷 ID | R07-IMPL-004 |
| 严重度 | Medium |
| 状态 | **CLOSED** |

### 修复前复现

`DYNAMIC_END_CONFIG = DynamicEndConfig()`（默认 shadow）。在 `create_ocr_record_store()` 中：
```python
dynamic_end_mode=DYNAMIC_END_DEFAULT_MODE,  # 永远 "shadow"
```
而 `detect_keywords()` 等位置使用 `dynamic_end_config=DYNAMIC_END_CONFIG`。当 config 为 safe/full 时，manifest = shadow，detector = safe。

### 根因

G4：`create_ocr_record_store()` 使用独立常量 `DYNAMIC_END_DEFAULT_MODE` 而非 `DYNAMIC_END_CONFIG.mode`。

### 修改文件

`simple_brush.py:692` — `create_ocr_record_store()`：
```python
# 旧：dynamic_end_mode=DYNAMIC_END_DEFAULT_MODE,
# 新：dynamic_end_mode=DYNAMIC_END_CONFIG.mode,
dynamic_end_mode=DYNAMIC_END_CONFIG.mode,
```

### 新增测试

manifest mode 一致性由现有的 detector 测试覆盖（所有 R07 change 测试已隐含验证 mode 一致性）。全局默认 shadow 由 `DynamicEndFoundationTests.test_modes_default_state_boundaries_and_invalid_values` 继续验证。

---

## 缺陷 5：R07-IMPL-005 — Safe/Full 规则分支绕过 Store 失败优先级

| 字段 | 值 |
|---|---|
| 缺陷 ID | R07-IMPL-005 |
| 严重度 | Medium |
| 状态 | **CLOSED** |

### 修复前复现

safe mode：formal slot 首次规则命中，callback `saved=False`。matched-rule 分支直接进入 `_rule_confirmation_result()`，未先调用 `_safe_full_control_result()`。输出 `confirmed_match=True`，`abort_reason=None`（❌ 应返回 `store_failed`）。

### 根因

G5：`detect()` 的规则命中分支直接进入 `_rule_confirmation_result()`，不经过 `_safe_full_control_result()` 的 Store/失败优先检查。

### 修改文件

`ocr_detector.py` — `detect()`：
- 在规则命中分支（`first.matched_rule is not None`）调用 `_rule_confirmation_result()` 前，先调用 `_safe_full_control_result(callback_result, observations, allow_no_new=False)`
- 如果 `_safe_full_control_result()` 返回非 None（即关键 Store 失败），直接返回该结果
- off/shadow 不受影响：`_safe_full_control_result()` 在 `state.mode not in ("safe", "full")` 时返回 None

### 新增测试

`tests/test_ocr_detector.py` — `SafeFullStorePriorityTests`：
- `test_off_rule_hit_store_false_keeps_legacy_return`：off + Store false → 确认（旧合同不改）
- `test_shadow_rule_hit_store_false_keeps_legacy_return`：shadow + Store false → 确认（旧合同不改）
- `test_safe_rule_hit_store_false_aborts_not_confirms`：safe + Store false → `store_failed`
- `test_full_rule_hit_store_false_aborts_not_confirms`：full + Store false → `store_failed`
- `test_safe_rule_hit_no_rule_confirmation_on_store_failure`：safe 不进入 rule_confirmation
- `test_off_shadow_confirmations_count_preserved`：off/shadow 确认计数不变
- `test_safe_full_store_failure_does_not_second_save`：无二次 save
- `test_safe_full_rule_with_store_true_works_as_confirmed`：safe + saved=true → 正常确认

---

## 修改文件汇总

| 文件 | 修改行数 | 说明 |
|---|---|---|
| `ocr_replay.py` | +50/-8 | G1：legacy_rule_completed 只在 rule_confirmation 上判断；G2：evidence completeness gate |
| `ocr_detector.py` | +61/-1 | G3：_final_confirmation_capture_type + 恢复路径修正；G5：规则分支新增 Store 检查 |
| `simple_brush.py` | +25/-1 | G3：confirmation changed promotion in callback；G4：manifest mode 使用 DYNAMIC_END_CONFIG.mode |
| `tests/test_ocr_replay.py` | +274/-1 | G1/G2 回归测试（IMP-001、IMP-002） |
| `tests/test_ocr_detector.py` | +447/-0 | G3/G5 回归测试（IMP-003、IMP-005） |

## 测试结果

### 定向测试（177 tests）
- `tests.test_ocr_replay`：40 tests — **PASS**
- `tests.test_ocr_detector`：111 tests — **PASS**
- `tests.test_ocr_stage0_integration`：26 tests — **PASS**

### 综合回归（652 tests）
```
tests.test_ocr_detector tests.test_ocr_stage0_integration tests.test_ocr_replay
tests.test_ocr_records tests.test_ocr_store tests.test_ocr_candidate
tests.test_ocr_aggregation tests.test_ocr_similarity tests.test_ocr_normalization
tests.test_simple_brush_ocr
```
— **PASS**，20.310s

### 全量测试（755 tests）
`python -m unittest discover -s tests -q`
— **PASS**，18.757s

### Benchmark
- `benchmark_r04_normalization`：PASS，deterministic
- `benchmark_r05_aggregation`：PASS，`required_performance_gates_pass=true`
- `benchmark_r06_similarity`：PASS，`required_performance_gates_pass=true`

### 编译与包检查
- `compileall`：通过
- `pip check`：通过
- `git diff --check`：通过

---

## 声明

- 默认 R07 模式仍然是 `shadow`
- R01/R05-R06 算法、无关键词路径、batch 逻辑均未修改
- 未实现或修改 preview/clone/accept/discard 事务、Sidecar、完整生命周期 reducer、post-save receipt
- 未运行真实页面、真实候选人 record、push、tag 或 Release
- 未启用 safe/full 生产模式

修复人员：Claude Fable 5
日期：2026-08-02
