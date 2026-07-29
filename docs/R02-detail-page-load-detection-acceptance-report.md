# BossOCR R02：详情页加载完成检测验收报告

## 1. 文档信息

- 需求：BossOCR R02「详情页加载完成检测」
- 验收范围：Change 1—Change 6 最终实现与回归
- 验收日期：2026-07-29
- 正式平台范围：Windows 10/11 x64 + Microsoft Edge
- 分支：`main`
- 基线 HEAD：`c36d6e7549e5098a4381861de40b271e718d5f20`
- RPD：`docs/RPD-R02-detail-page-load-detection.md`
- TID：`docs/TID-R02-detail-page-load-detection.md`
- 当前结论：附条件通过——自动化与静态验收通过，真实 Windows Edge 人工冒烟待执行

本报告不声称完成 macOS R02 正式候选人流程适配或端到端验收。

## 2. 基线与实际修改文件

Change 1—5 的 R02 实际修改文件：

| 文件 | 最终职责 |
| --- | --- |
| `ocr_detector.py` | 指标 helper、纯加载判定、observation 最小扩展、纯采集与 prefetched 首屏消费 |
| `simple_brush.py` | R02 常量、有限重试门禁、页面硬恢复、连续恢复计数、安全停止和结构化日志 |
| `tests/test_ocr_detector.py` | 指标边界、纯采集、observation 字段和首屏复用测试 |
| `tests/test_simple_brush_ocr.py` | 重试、停止、模式、恢复、计数、日志和主循环回归测试 |

Change 6 额外修改：

| 文件 | 修改 |
| --- | --- |
| `simple_brush.py` | 将加载判定日志值从非冻结的 `not_ready`/`failed` 最小修正为 `not_loaded`/`error` |
| `tests/test_simple_brush_ocr.py` | 更新冻结值断言，并新增完整 `detail_load_check` 字段及 OCR 正文不泄露测试 |
| `docs/R02-detail-page-load-detection-acceptance-report.md` | 本验收报告 |

本轮开始前已有的 `.gitignore`、其他验收报告、项目审计资料和环境清单改动均未整理、覆盖或回退。当前 `.gitignore` 忽略一般 Markdown，因此 RPD、TID 和本报告存在于工作区，但不会出现在普通 `git status --short` 中；本轮按 TID 边界未修改 `.gitignore`、未暂存文件。

## 3. 最终调用链

有关键词的 favorite、forward 和 forward + `--no-forward` 共用历史条件 `forward_enabled and forward_keywords`：

```text
run()
→ 既有候选人打开/切换等待
→ run_detail_load_gate()
   → capture_observation(1)
      → capture
      → backend.recognize
      → accepted_ocr_items
      → calculate_load_metrics
      → searchable_text
   → evaluate_detail_page_load
   → 失败时最多 3 次 safe_wait(1.5) + 同区域重新采集
→ loaded
   → total_viewed += 1
   → detail_load_check(state=loaded)
   → 硬恢复后才记录 detail_load_recovery_confirmed 并清零计数
   → view_candidate(first_observation)
      → detect_keywords(first_observation)
      → OCRKeywordDetector.detect(first_observation)
```

无关键词纯浏览路径不初始化/校准 OCR，不执行加载门，保留原统计、停留、随机滚动、下一候选人和正常刷新行为。

## 4. 配置、指标与判定

冻结配置：

| 常量 | 值 |
| --- | ---: |
| `OCR_BOX_COUNT_THRESHOLD` | 5 |
| `OCR_TEXT_LENGTH_THRESHOLD` | 30 |
| `LOAD_RETRY_WAIT_SECONDS` | 1.5 |
| `MAX_LOAD_RETRIES` | 3 |
| `MAX_CONSECUTIVE_LOAD_RECOVERIES` | 1 |

指标仅使用两个字段：

- `ocr_box_count`：`confidence >= min_confidence` 的框数，空文本有效框仍计数。
- `ocr_text_length`：对每个有效框的 `item.text.strip()` 单独计 Python 字符数，空文本不贡献长度。

`ScanObservation.item_count` 继续是过滤前数量；规则搜索继续使用既有 `searchable_text()`，不参与加载长度计算。

未加载条件：

```text
ocr_box_count == 0
OR
(ocr_box_count <= 5 AND ocr_text_length < 30)
```

已验证 0/0、5/29、5/30、6/10、2/100 五个边界，以及 confidence 等于/低于阈值、空文本、首尾空格、多框求和、过滤前后框数和自定义阈值。

## 5. 需求与复杂度审计

| 核对项 | 结论 |
| --- | --- |
| 只使用 `ocr_box_count`、`ocr_text_length` | 通过 |
| `ScanObservation` 只追加两个可选整数指标 | 通过 |
| 不保存 OCRItem/raw/accepted/evidence 列表 | 通过；列表只存在于采集函数局部变量 |
| 不实现姓名、锚点、占位页、加载文案或 R03 | 通过 |
| 不为加载指标做排序、NFKC、大小写、标点、UI 删除或去重 | 通过 |
| 有关键词三种模式接入、无关键词不接入 | 通过 |
| 首次 + 最多 3 次重试，重试前固定 1.5 秒 | 通过 |
| OCR 异常共享 4 次预算，指标输出 `-` 而非 0 | 通过 |
| 重试期间无 matcher、滚动、动作、next、正常刷新和正式屏追加 | 通过 |
| 成功首屏按对象身份直接复用 | 通过 |
| 首屏二次确认、最多 8 屏和最多 7 次滚动保持 | 通过 |
| 硬恢复只在启用筛选且完整 regions 可用时发生 | 通过 |
| legacy/`--no-batch-filter` 不模拟硬恢复 | 通过 |
| `first_candidate_opened` 与 `restart_current_batch` 职责分离 | 通过 |
| Change 4 只使用一个 `consecutive_load_recovery_count` | 通过 |
| `reopen_completed` 与 `confirmed` 时点分离 | 通过 |
| 只有 confirmed 后清零，持续故障安全停止 | 通过 |
| `total_viewed` 仅在 loaded 后增加一次 | 通过 |
| 硬恢复不清零 `forward_consecutive`；正常满 100 人才清零 | 通过 |
| 无新状态机、结果 dataclass、通用重试器或配置框架 | 通过 |
| 正式平台仅 Windows 10/11 x64 + Edge | 通过 |

Change 2/3 中间版本的临时结果和停止原因不是最终产品状态，未在最终生产代码中保留 feature flag 或死分支。其安全边界继续由当前测试覆盖：单次失败只产生加载检查且不进入 matcher/动作；四次耗尽没有第 5 次 OCR；最终 `run()` 在不可恢复/持续失败时受控返回 0、执行 finally，且不调用 view/next/正常 refresh。Change 5 最终 `load_failed` 语义按 TID 替代了中间版本“不设置最终原因”的临时断言。

## 6. 重试、OCR 错误与停止

- 首次检测前不增加 R02 等待。
- retry 1—3 各自在 OCR 前调用一次 `safe_wait(1.5)`，最大 OCR 次数严格为 4。
- 阈值失败与 `ocr_error` 使用同一预算，不建立独立异常重试。
- OCR 成功返回空列表得到 `0/0` 和 `zero_ocr_boxes`；异常得到未知指标和 `ocr_error`，两者不混淆。
- ESC/timer 在等待时阻止下一次 OCR；同步 OCR 无法中途抢占，但返回后立即检查停止，不进入规则或动作。
- 首个实际停止原因保持为 `esc`、`run_duration_elapsed` 或 `load_failed`，互不覆盖。
- 最终加载故障调用 `request_load_failed_stop()`，记录 ERROR、设置 `stop_reason=load_failed` 和 `stop_event=True`，随后沿既有 finally 返回 0。

## 7. 首屏复用

`capture_observation()` 每次只调用一次 capture 和 backend，不调用 matcher、scroll 或 wait。通过门禁的同一 `ScanObservation` 传入 `view_candidate()`、`detect_keywords()` 和 detector；正式首屏只匹配、append 和计屏一次，也不会重复首屏结构化日志。

首屏命中后仍执行一次独立 OCR 二次确认；首屏未命中时，从第 2 屏前才滚动，正式扫描总数最多 8，滚动最多 7 次。

## 8. 页面硬恢复和状态生命周期

四次耗尽且恢复可用时：

```text
detail_load_recovery_start
→ refresh_page(reason=详情页加载检测重试耗尽)
→ F5 + 既有 5 秒等待
→ apply_batch_filter_and_open_first_candidate()
→ 筛选、结果等待、首位点击
→ detail_load_recovery_reopen_completed
→ first_candidate_opened=True
→ restart_current_batch=True
→ 跳过正常 100 人刷新
→ 新 for 从 candidate_in_batch=1 重新执行 R02
```

`recover_detail_page()` 不接收 legacy 坐标，不复制筛选点击序列。`reopen_completed` 仅说明导航归位，恢复计数仍为 1；新候选人真正 loaded 后才依次记录 loaded、`detail_load_recovery_confirmed`、清零，然后进入 `view_candidate()`。

硬恢复保留 `total_viewed`、timer、OCR/backend/region、校准区域、模式、规则、邮箱、启动参数、`forward_consecutive` 和停止状态。新首位的候选人局部重试从 0 开始。清零后未来独立故障重新获得一次恢复额度；未确认的连续第二次完整失败不再 F5。

最终原因覆盖 `hard_recovery_unavailable`、`max_consecutive_load_recoveries_reached`、`refresh_failed` 和 `batch_reopen_failed`。

## 9. 日志验收

最终事件：

- `detail_load_check`
- `detail_load_recovery_start`
- `detail_load_recovery_reopen_completed`
- `detail_load_recovery_confirmed`
- `detail_load_failed`

每次加载检查包含 candidate、累计人数、attempt、retry number、两个指标、decision、reason、state、recovery count 和 next action。判定值已对齐为 `ready`、`not_loaded`、`error`；加载状态只使用 `loading`、`load_retrying`、`loaded`、`load_recovering`、`load_failed`。OCR 异常指标为 `-`，日志不输出 `ScanObservation.text` 或完整 OCR 正文。

Change 6 审计发现并修复了 `decision=not_ready`/`decision=failed` 与 RPD 冻结值不一致的问题。恢复步骤的 `decision=started/completed/failed` 是步骤执行结果，不是 `detail_load_check` 的加载判定值，保持既有最小日志设计。

## 10. 自动化测试结果

最终命令与结果：

| 命令 | passed | failed | skipped | 结论 |
| --- | ---: | ---: | ---: | --- |
| `.\venv\Scripts\python.exe -m unittest tests.test_ocr_detector -v` | 39 | 0 | 0 | 通过 |
| `.\venv\Scripts\python.exe -m unittest tests.test_ocr_text -v` | 36 | 0 | 0 | 通过 |
| `.\venv\Scripts\python.exe -m unittest tests.test_simple_brush_ocr -v` | 186 | 0 | 0 | 通过 |
| `.\venv\Scripts\python.exe -m unittest tests.test_mouse_motion -v` | 28 | 0 | 0 | 通过；覆盖直接导入 `simple_brush`、筛选点击和 CLI |
| `.\venv\Scripts\python.exe -m unittest discover -s tests -v` | 327 | 0 | 0 | Windows 全量通过 |

静态与环境检查：

| 命令 | 结果 |
| --- | --- |
| `.\venv\Scripts\python.exe -m compileall -q ocr_detector.py simple_brush.py tests` | 通过 |
| `.\venv\Scripts\python.exe -m pip check` | 通过；`No broken requirements found.` |
| `git diff --check` | 通过；无 whitespace error，仅有现有 LF→CRLF 提示 |

仓库未发现 Ruff、Flake8、Mypy、Pylint、tox 或 `pyproject.toml` 中的额外静态检查配置，因此没有虚构或新增检查器。

失败与修复过程：

1. 修复前既有三个定向文件分别为 39/39、36/36、185/185 通过，说明原测试未捕获冻结日志值偏差。
2. 设计审计发现 `not_ready`/`failed` 偏离 RPD 的 `not_loaded`/`error`，做两处生产字符串最小修复并更新断言。
3. 新增 3 项日志定向运行首次为 2 passed、1 failed；失败原因是测试用词 `short` 也合法出现在 `low_box_count_and_short_text`，不是生产正文泄露。
4. 将测试正文替换为唯一标记 `PRIVATE_OCR_BODY` 后，3/3 通过；随后定向和全量均通过。

## 11. 自动化覆盖矩阵

| 范围 | 证据摘要 |
| --- | --- |
| A 指标和判定 | 五个边界、confidence 边界、空文本/strip、多框求和、过滤前后框数、异常未知指标 |
| B 首屏拆分与复用 | 单次 capture/backend、无 matcher/scroll/wait、无 OCRItem 字段、对象身份复用、确认/8 屏/7 滚动 |
| C 加载与重试 | 初次及 retry 1/2/3 成功、4 次耗尽、1.5 秒次数、混合错误预算、停止中断、同一区域 |
| D Change 安全边界 | 门禁 helper 的中间 outcome 与禁止行为、最终 run 的 finally/无 next/无正常刷新、Change 4/5 生命周期 |
| E 页面硬恢复 | F5/等待/筛选/首位顺序、单次 reopen、两个控制标志、从 i=0、状态保留、故障安全停止 |
| F 日志与停止 | 五事件、reopen/confirmed 时点、最终原因、三类 stop reason、正文不泄露、统计/清理 |
| G 回归 | favorite、forward、`--no-forward`、无关键词、规则表达式、焦点恢复、next、自动筛选、legacy、CLI、交互、ESC、timer、Windows 全量 |

公共 OCR 测试范围包括 `test_ocr_detector.py` 和 `test_ocr_text.py`，验证纯 Python OCR 数据处理及规则回归；这些结果不能推断 macOS 正式候选人 E2E 已适配。

## 12. Windows + Edge 人工冒烟

本次没有可确认的 Boss 测试账号、有效测试规则、可控网络延迟/失败注入环境和经授权的安全 Edge 会话。为避免在真实候选人页面产生刷新、筛选、收藏或转发副作用，以下场景均未执行，状态统一为“待人工执行”，不得解读为通过：

| 场景 | 状态 |
| --- | --- |
| 正常立即加载 | 待人工执行 |
| 短暂延迟后重试成功 | 待人工执行 |
| 四次失败后 F5、筛选和首位重开 | 待人工执行 |
| 恢复不可用 | 待人工执行 |
| 恢复后再次完整失败 | 待人工执行 |
| 恢复确认成功后未来独立故障 | 待人工执行 |
| ESC 在首次/重试/恢复等待 | 待人工执行 |
| timer 在首次/重试/恢复等待 | 待人工执行 |
| favorite、forward、`--no-forward` 分发 | 待人工执行；优先 `--no-forward`，真实转发不作为默认冒烟 |
| 无关键词回归 | 待人工执行 |
| `total_viewed`、恢复计数和日志 | 待人工执行 |
| 正常 100 人刷新 | 待人工执行 |

建议在 Windows 10/11 x64、Microsoft Edge、测试账号、有效规则、小样本和 `--no-forward` 下由人工监控执行，并保留脱敏日志作为最终实机证据。

## 13. RPD/TID 验收结论

自动化可验证的 RPD/TID 项全部通过：文件与函数落点、两个指标、四次预算、1.5 秒等待、OCR 错误、动作门、首屏复用、恢复可用性、唯一连续计数、确认后清零、安全停止、日志、统计、模式与正常刷新均与批准文档一致。

Change 6 未实施姓名/锚点/占位页、R01、R03、AI、JSON、SQLite、候选人身份去重、macOS 正式流程、通用状态机或无关重构。Change 6 修复后，TID 与实际代码未发现剩余直接差异。

## 14. 已知限制与非本轮问题

- 硬恢复从筛选后首位重新开始，R02 不识别候选人身份，可能重复处理已见候选人；一次连续恢复上限和 `--no-forward` 只能降低风险，不能消除重复。
- OCR backend 是同步调用，ESC/timer 无法中途抢占一次正在执行的 OCR；实现只保证返回后第一时间停止。
- 冻结阈值是经验规则，6 个短/空框或 1 个 30 字框会放行；固定 UI 也可能贡献指标。
- 无关键词纯浏览路径按需求不受 R02 保护。
- legacy/`--no-batch-filter` 在四次耗尽后只能安全停止，不能执行完整页面硬恢复。
- 真实页面布局、网络波动、DPI/缩放和浏览器状态只能由待执行的 Windows Edge 冒烟验证。
- 本轮前已有的其他工作区改动和忽略规则不是 R02 直接缺陷，未处理。

## 15. 最终结论

结论：**附条件通过**。

R02 自动化测试、Windows 仓库全量测试、编译检查、依赖检查和 diff whitespace 检查全部通过；实现与 RPD/TID 的最终结构一致，未发现超范围或过度设计。唯一未满足的实机证据是 Windows 10/11 x64 + Microsoft Edge 真实页面人工冒烟，因此当前只能认定“自动化验收通过、人工验收待完成”，不能标记为无条件通过或已发布。

本轮未 commit、push、创建 tag 或 Release。
