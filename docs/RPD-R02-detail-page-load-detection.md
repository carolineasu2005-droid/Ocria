# BossOCR R02：详情页加载完成检测——详细版 RPD

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档类型 | RPD（详细版需求与产品设计） |
| 需求编号 | R02 |
| Change | Change 0A：仓库审计与详细版 RPD |
| 状态 | 待评审；本 Change 不进入 TID 或代码实施 |
| 编写日期 | 2026-07-28 |
| 当前分支 | `main` |
| 基线提交 | `c36d6e7549e5098a4381861de40b271e718d5f20`（tag `v1.2`，与 `origin/main` 一致） |
| 当前稳定版 | Windows Stable `v1.2`，依据 `docs/README.md` 与 `docs/releases/windows-stable-v1.2.md` |
| 建议实现平台 | 当前正式候选人处理主流程所支持的 Windows 10/11 x64 + Microsoft Edge |
| 文档路径选择依据 | 仓库已有需求、TID、验收报告均使用 Markdown，但没有已跟踪的 RPD 命名规范；因此采用 Change 0A 指定的回退路径 `docs/RPD-R02-detail-page-load-detection.md` |

本文件只冻结 R02 的需求、边界、验收方式和基于真实代码的集成约束，不是 TID，不授权修改业务代码、测试代码、配置或构建脚本。

### 1.1 Change 0A 开始时的仓库状态

审计开始时 `git status --short --branch` 为：

```text
## main...origin/main
 M .gitignore
 M docs/Issue-Next-6-human-mouse-motion-acceptance-report.md
?? docs/project-review.zip
?? docs/project-review/
?? docs/tid/
?? venv-packages-before-reinstall.txt
```

以上均为本 Change 开始前已有的用户改动或未跟踪文件。本 Change 不修改它们。

仓库当前已跟踪的 `.gitignore` 规则包含全局 `*.md`，且没有为本 RPD 路径设置例外。因此本文件虽已创建在指定位置，但默认不会出现在普通 `git status` 或 `git diff --stat` 中。Change 0A 禁止修改配置文件，也未授权暂存文件，所以本轮不改 `.gitignore`、不执行强制暂存；交付时必须显式报告这一事实，后续由维护者决定是否 `git add -f` 或另行增加精确例外。

### 1.2 Python、入口与测试基线

- 系统 `python`：Python 3.14.4。
- 项目虚拟环境 `venv\Scripts\python.exe`：Python 3.13.14。
- 用户启动入口：`start.bat`，它调用 `venv\Scripts\python.exe simple_brush.py`。
- Python 入口：`simple_brush.py:main()`；实际运行主流程：`simple_brush.py:run()`。
- Windows 构建入口：`build-windows.bat` 与 `BossOCR.spec`。
- 测试框架：标准库 `unittest` 与 `unittest.mock`。
- Change 0A 审计时执行 `venv\Scripts\python.exe -m unittest discover -s tests -v`，结果为 273 项全部通过、0 failure、0 error。
- 当前没有对真实 BOSS 页面执行的自动化端到端测试。`build-windows.bat` 的打包 smoke 使用无关键词、`--no-forward --auto`，且注释明确“不与 BOSS 窗口交互”，不能作为详情页加载检测证据。

## 2. 当前稳定版基线

`docs/README.md` 将当前 Windows 正式版标为 `v1.2`；`docs/releases/windows-stable-v1.2.md` 说明该版本新增通用校准模板，但不改变收藏、转发、筛选、OCR 和鼠标轨迹逻辑。当前代码基线的主要行为如下：

- `simple_brush.py:run()` 置顶 Microsoft Edge，打开首位候选人，再进入每批 100 人的处理循环。
- `simple_brush.py:view_candidate()` 在配置了关键词时先调用 `detect_keywords()`，随后执行收藏或转发，最后完成剩余停留和随机滚动。
- 没有配置关键词时，`view_candidate()` 不调用 `detect_keywords()`，也不初始化或校准候选人 OCR，而是保持现有纯浏览、停留和随机滚动行为。
- `ocr_detector.py:OCRKeywordDetector.detect()` 对同一 OCR 区域最多扫描 8 屏；首次命中后在原屏进行一次二次确认。
- `simple_brush.py:next_candidate()` 通过右方向键切换候选人，仅固定等待 0.5 秒，不验证切换成功或详情正文加载完成。
- `simple_brush.py:refresh_page()` 每 100 人按 F5 并等待 `REFRESH_WAIT_SECONDS=5`；下一轮通过 `open_first_candidate_for_batch()` 重开首位候选人。
- `simple_brush.py:apply_batch_filter_and_open_first_candidate()` 在启用批次筛选时执行“打开筛选 → 最近没看过 → 确定 → 首位候选人”。

### 2.1 Windows 与 macOS 关系

Windows 与 macOS **没有共用候选人处理核心流程**。

- 正式主流程 `simple_brush.py` 在模块顶层直接导入 `win32gui`、`win32con`、`win32clipboard` 和 `win32process`，并在 `bring_edge_foreground()` 中要求进程为 `msedge.exe`；因此该模块是 Windows + Edge 实现。
- `ocr_calibration.py` 的 `ScreenRegion`、拖框和 DPI 辅助以及 `ocr_detector.py` 的 MSS/RapidOCR 层具有部分跨平台性质。
- `ocr_mac_demo.py` 只是“校准一个区域并运行一次 OCR”的开发演示入口，不包含首位候选人打开、右键切换、100 人批次、收藏、转发或安全停止主循环。
- `docs/README.md` 的“当前限制”也明确 macOS Chrome 适配尚未完成。

因此，R02 第一版的正式实现与验收平台冻结为 **Windows 10/11 x64 + Microsoft Edge**；不得声称它同时覆盖 macOS 候选人处理，也不要求 macOS 候选人流程端到端测试。

## 3. 实际代码流程审计

### 3.1 候选人打开、切换与批次循环

| 审计项 | 当前真实实现 | 证据与 R02 含义 |
| --- | --- | --- |
| 打开首位候选人 | `run()` 在 `bring_edge_foreground()` 后，优先调用 `ensure_batch_filter_regions_calibrated()`；若 `batch_filter_enabled` 为真，则经 `open_first_candidate_for_batch()` 进入自动筛选路径，否则记录鼠标当前位置为 `legacy_point` 并调用 `click_first_candidate()`。 | `simple_brush.py:run()`、`open_first_candidate_for_batch()`、`click_first_candidate()`；首位详情打开后才进行焦点、转发、收藏和 OCR 区域校准。 |
| 自动筛选并打开首位 | `apply_batch_filter_and_open_first_candidate()` 依次点击 `open_filter`、`unseen_filter`、`confirm_filter`、`first_candidate`，中间使用 `human_delay()`，最终使用 `safe_wait(CLICK_WAIT_SECONDS)`。 | `simple_brush.py:apply_batch_filter_and_open_first_candidate()`；这是页面级硬恢复应复用的现有“最近 14 天没看过 + 首位候选人”流程。 |
| 切换到下一位 | `next_candidate()` 调用 `pyautogui.press('right')` 后 `safe_wait(0.5)`。 | `simple_brush.py:next_candidate()`；没有 R01 切换成功验证，也没有加载完成验证。R02 检测必须位于下一次 `view_candidate()` 的滚动和规则判断之前。 |
| 每批处理 | `run()` 使用 `for i in range(BATCH_SIZE)`，`BATCH_SIZE=100`；`i` 是批次内零基序号。 | 当前没有显式 `batch_number`。R02 需要能重置批次内处理位置，但第一版不强制新增全局或单调递增批次编号。 |
| 总处理人数 | `total_viewed` 是 `run()` 局部整数；每轮在调用 `view_candidate(i)` **之前**执行 `total_viewed += 1`。 | 当前会把没有通过加载检测的候选人计入累计查看数。R02 冻结为：候选人第一次通过加载门、成功 OCR 成为正式首屏并准备进入规则扫描时只增加 1；失败尝试和硬恢复不增加，硬恢复也绝不能清零。 |
| 100 人刷新 | 内层循环退出且 `stop_event` 未置位后，先将 `forward_consecutive=0`，再调用 `refresh_page()`；下一次外层循环调用 `open_first_candidate_for_batch(legacy_point)`。 | `simple_brush.py:run()`、`refresh_page()`；`refresh_page()` 的日志文案写死“已查看 100 位”，直接用于加载故障恢复会产生错误日志语义。 |
| 重新设置“最近没看过” | 不是 `refresh_page()` 自身完成，而是刷新后下一轮调用 `open_first_candidate_for_batch()`，再由 `apply_batch_filter_and_open_first_candidate()` 完成。 | 页面级硬恢复必须复用这条组合路径，不能只调用 F5，也不能复制另一套筛选点击序列。 |
| 首位候选人重新打开 | 自动路径点击 `BatchFilterRegions.first_candidate`；legacy 路径复用启动时记录的 `legacy_point`。 | 完整硬恢复要求重新设置筛选并点击校准首位区域；legacy/`--no-batch-filter` 缺少条件时仍执行加载重试，但 4 次失败后以 `reason=hard_recovery_unavailable` 进入 `load_failed`，不得用旧坐标模拟恢复。 |

相关主循环测试集中在 `tests/test_simple_brush_ocr.py`：

- `test_run_calibrates_after_first_detail_opens_before_viewing`
- `test_apply_batch_filter_clicks_regions_in_order`
- `test_run_batch_filter_success_prepares_before_timer_and_view`
- `test_run_reapplies_batch_filter_after_refresh_before_next_batch`
- `test_run_does_not_filter_next_batch_when_refresh_fails`
- `test_run_stops_before_next_view_when_batch_filter_reapply_fails`
- `test_run_legacy_path_reuses_same_point_after_refresh`

### 3.2 OCR 截图、引擎、返回值、过滤与文本

| 审计项 | 当前真实实现 | 证据与 R02 含义 |
| --- | --- | --- |
| 首屏 OCR 准确入口 | `view_candidate()` → `detect_keywords()` → `ocr_detector.detect(forward_keywords)` → `OCRKeywordDetector.detect()` 在 `scan_number=1` 时调用 `_observe(1, rules)`。 | `simple_brush.py:view_candidate()`、`detect_keywords()`；`ocr_detector.py:OCRKeywordDetector.detect()`、`_observe()`。当前入口只在有关键词时运行。 |
| OCR 截图函数 | `_observe()` 调用 `self.capture.capture(self.region)`；实际对象是 `MSSScreenCapture`。`MSSScreenCapture.capture()` 使用 `mss.MSS().grab(region.as_mss_monitor())`，将 BGRA 转成 BGR NumPy 数组。 | `ocr_detector.py:MSSScreenCapture.capture()`；R02 重试必须对相同 `self.region` 重新调用此入口。 |
| OCR 引擎调用 | `_observe()` 调用 `self.backend.recognize(image)`；实际对象为 `RapidOCRBackend`，内部调用复用的 `self.engine(image)`。 | `ocr_detector.py:RapidOCRBackend.recognize()`；`simple_brush.py:initialize_ocr()` 只在进程内创建一次 `RapidOCRBackend`。 |
| OCR 原始返回结构 | `RapidOCRBackend.recognize()` 统一返回 `Sequence[OCRItem]`。`OCRItem` 是冻结 dataclass，字段为 `text: str`、`confidence: float`、`box`，并提供 `anchor`、`vertical_bounds`。适配器支持 RapidOCR 3.x 的 `txts/scores/boxes` 和旧版 `[box,text,score]` 结构。 | `ocr_text.py:OCRItem`、`ocr_detector.py:RapidOCRBackend`；R02 两个指标必须从 `OCRItem` 列表计算。 |
| Detector 返回结构 | `detect()` 返回 `DetectionResult(success, confirmed_match, matched_keyword, scans_completed, observations, error)`；每个 `ScanObservation` 包含 `scan_number`、`text`、`item_count`、`elapsed_seconds`、`matched_keyword`、`matched_rule`。 | `ocr_detector.py:DetectionResult`、`ScanObservation`。当前结构没有 `ocr_text_length`，也没有保留有效 `OCRItem` 列表。 |
| OCR 置信度过滤 | `_observe()` 把完整 `items` 交给 `ocr_text.searchable_text(items, min_confidence)`；`searchable_text()` 使用 `item.confidence >= min_confidence` 过滤，然后排序、拼接并标准化。阈值来自 `simple_brush.py:OCR_MIN_CONFIDENCE=0.85`，注入 `OCRKeywordDetector.min_confidence`。 | R02 不得建立第二套置信度阈值；应复用同一比较条件与同一阈值。 |
| 当前文字框计数口径 | `_observe()` 设置 `item_count=len(items)`，发生在置信度过滤之外，包含低置信度框。 | `ScanObservation.item_count` **不能**直接作为 R02 的 `ocr_box_count`。当前没有直接暴露的“过滤后框数”。 |
| 当前文本提取/拼接 | `searchable_text()` 对过滤后的框调用 `order_items()`，按自适应行高和 x 坐标排序，以换行拼接后调用 `normalize_text()`；后者执行 NFKC、转小写和删除空白。 | `ocr_text.py:order_items()`、`searchable_text()`、`normalize_text()`。R02 的 `ocr_text_length` 不能从 `ScanObservation.text` 计算，因为该字段已标准化。 |
| 规则表达式判断 | `_observe()` 用 `matching_keyword_rule(text, rules)`；它逐规则调用 `keyword_rule_matches()`，遵守解析后的 and/or/not/any 语义。 | `ocr_text.py:matching_keyword_rule()`、`keyword_rule_matches()`、`parse_keyword_rules()`；R02 只增加规则判断前的加载门，不修改规则引擎。 |

相关 OCR 测试：

- `tests/test_ocr_detector.py` 使用 `FakeCapture`、`FakeBackend` 测试固定屏数、滚动、二次确认、空结果、低置信度和后端异常；关键测试包括 `test_scans_fixed_number_and_scrolls_between_pages`、`test_eight_screens_without_keyword_never_match`、`test_backend_failure_is_fail_closed`、`test_low_confidence_match_does_not_trigger`。
- `tests/test_ocr_detector.py:RapidOCRAdapterTests` 覆盖现代与 legacy RapidOCR 结果结构。
- `tests/test_ocr_text.py:OCRTextTests` 覆盖低置信度过滤、框排序、NumPy box、标准化和规则表达式。
- `tests/test_simple_brush_ocr.py:test_detect_keywords_uses_ocr_without_clipboard` 验证候选人 OCR 不使用剪贴板。

### 3.3 第一次滚动与最多 8 屏扫描

1. 有关键词时，第一次潜在滚动发生在 `OCRKeywordDetector.detect()` 的第二屏之前：当 `scan_number > 1` 时调用 `self.scroll()`；实际注入的 `simple_brush.py:ocr_scroll_down()` 随机向下滚动 100—140 格并等待 `OCR_SETTLE_SECONDS=0.6`。
2. `OCR_MAX_SCANS=8` 由 `ensure_ocr_region_calibrated()` 注入 `OCRKeywordDetector(max_scans=8)`；首屏未命中后最多再扫描 7 屏。
3. 首次命中规则时不滚动，等待 `OCR_CONFIRMATION_SECONDS=0.7` 后在同一位置再次 `_observe()`；二次确认不增加 `scan_number`。
4. OCR 流程结束后，`view_candidate()` 计算剩余停留预算，再由 `human_scroll_once()` 执行随机浏览滚动。
5. 没有关键词时，当前不会调用 `detect_keywords()`，第一次滚动直接来自 `view_candidate()` 停留循环中的 `human_scroll_once()`；R02 第一版不改变该路径。

对每名进入 OCR 关键词规则正式筛选流程的候选人，R02 加载门必须位于第一次正式规则判断和 OCR 滚动之前，并继续阻止该候选人在失败期间进入停留期随机滚动。加载失败的 OCR 尝试不算正式首屏，也不占用最多 8 屏的正式扫描额度；首次通过加载门的 OCR 才是正式第 1 屏。无关键词纯浏览模式保持当前行为，本轮不接入 R02。

### 3.4 收藏、转发与焦点恢复

- 收藏动作入口：`view_candidate()` 在 `keyword_hit=True` 且 `action_mode == ACTION_MODE_FAVORITE` 时调用 `perform_favorite_action()`。
- 收藏实现：`perform_favorite_action()` 在 `favorite_button_region` 中间 60% 取点，经 `human_click()` 点击，等待 0.5 秒，然后调用 `restore_candidate_page_focus_after_favorite()`。
- 收藏焦点恢复：`restore_candidate_page_focus_after_favorite()` 复用 `ocr_detector.region`，连续点击 OCR 正文区域内部两次。
- 转发动作入口：`view_candidate()` 在 forward 模式且不处于 `no_forward_mode` 时调用 `forward_one_candidate()`。
- 转发实现：`forward_one_candidate()` 点击转发入口、邮件 Tab、最近联系人/输入框、转发按钮；其 `finally` 对 `focus_restore_region` 执行两次独立焦点恢复尝试，所以所有已进入转发函数的成功、失败和早退路径都会恢复焦点。
- `--no-forward` 命中时只记录日志，不调用 `forward_one_candidate()`，因此也不会触发转发 `finally` 的焦点恢复。

相关测试包括：

- `test_favorite_mode_keyword_hit_calls_favorite_action_only`
- `test_forward_mode_keyword_hit_calls_forward_action`
- `test_no_forward_mode_never_calls_real_forward`
- `test_perform_favorite_action_restores_focus_after_favorite_click`
- `test_restore_candidate_page_focus_after_favorite_clicks_ocr_inner_region_twice`
- `test_forward_restores_focus_after_success`
- `test_forward_restores_focus_when_forwarding_raises`
- `test_second_focus_restore_is_attempted_when_first_click_raises`

R02 重试期间必须在这些动作入口之前返回控制，不得让加载失败被折算成 `keyword_hit=False` 后继续停留或滚动。

### 3.5 计时、ESC、暂停与其他安全停止

- `run_duration_seconds` 是全局配置；`start_run_timer()` 创建 daemon `threading.Timer`，到期后 `request_timed_stop()` 只把全局 `stop_event=True`。
- 运行总计时在首位候选人打开及运行期校准全部完成后才开始；`run_timer` 是 `run()` 局部变量，`finally` 调用 `cancel()`。
- ESC 由 `pynput.keyboard.Listener` 调用 `on_press()`；正常 ESC 把 `stop_event=True`、记录“收到 ESC”并停止 listener。校准中的 ESC 交给 Tk，只取消校准。
- 空格切换全局 `paused`。`safe_wait()` 每 0.2 秒检查 stop/pause；`ocr_wait()` 将被停止的等待转换为 `OCRInterrupted`。
- `click_first_candidate()`、`next_candidate()`、`refresh_page()`、`human_scroll_once()` 和转发步骤均在动作前检查 `stop_event`。
- `run()` 捕获所有 `Exception` 并记录 `logger.exception('运行异常...')`；`finally` 取消计时器并记录累计人数。`__main__` 的 `finally` 设置 `stop_event=True` 并调用 `listener.stop()`。

现有停止状态只有一个布尔 `stop_event`，没有区分 ESC、定时停止、启动失败、运行异常或不可恢复加载故障。R02 最终失败必须增加最小的可区分原因，避免把页面级不可恢复故障记录成正常 ESC，同时仍复用 `run()`/`__main__` 的清理路径。

相关测试：`test_timed_stop_sets_existing_stop_flag`、`test_stop_prevents_new_navigation_actions`、`test_ocr_wait_stops_when_escape_was_requested`、`test_run_does_not_start_timer_when_countdown_is_interrupted`。

### 3.6 日志器、等级与格式

`simple_brush.py` 在导入时创建 `logs/`，使用 `logging.basicConfig()` 写入 `logs/simple_brush.log`：

- 文件格式：`%(asctime)s [%(levelname)s] %(message)s`；等级 `INFO`；追加写入；UTF-8。
- 控制台 handler：`%(asctime)s %(message)s`，时间格式 `%H:%M:%S`。
- 普通流程使用 `logger.info()`；可安全回退使用 `warning()`；阻断失败使用 `error()`；带堆栈异常使用 `exception()`。
- `ocr_detector.py` 使用模块级 `logger=logging.getLogger(__name__)`；检测异常在 detector 层记录一次堆栈，主流程再记录安全跳过原因，当前存在同一异常跨层多条日志的情况。

现有文件 formatter 已提供时间戳，R02 不需要新增数据库或日志框架，但每条加载判断日志必须包含可检索的命名字段。

## 4. 现有代码风格审计

| 风格项 | 审计结论与代码依据 | R02 约束 |
| --- | --- | --- |
| 函数和变量命名 | 函数/变量以 `snake_case` 为主，如 `view_candidate`、`forward_consecutive`、`remaining_stay_seconds`；内部辅助使用前导下划线，如 `OCRKeywordDetector._observe()`、`_format_system_info_mismatches()`。 | 新函数和字段沿用 `snake_case`；不做全项目重命名。 |
| 常量与配置组织 | `simple_brush.py` 顶部按功能分组放置 `UPPER_SNAKE_CASE` 常量，如 `BATCH_SIZE`、`OCR_MIN_CONFIDENCE`、`FILTER_RESULTS_DELAY_MIN/MAX`；没有独立配置框架。 | R02 阈值放在现有 OCR 配置分组，使用有含义的常量，不引入配置系统或新增 GUI/CLI 参数。 |
| 类型注解程度 | `simple_brush.py` 大量流程函数没有注解；`ocr_detector.py`、`ocr_text.py`、`ocr_calibration.py` 对数据模型和公共纯函数使用较多注解。 | 只在新增 OCR 结构/纯函数与相邻模块一致时加注解；不补全旧主流程注解。 |
| 参数和返回值 | 主流程常用简单参数和 `True/False`，如 `open_first_candidate_for_batch()`、`view_candidate()`、`refresh_page()`；OCR 层用 `DetectionResult`/`ScanObservation` 返回结构化结果。 | 加载检测结果需要携带 OCR 数据和原因时，可最小扩展现有 OCR 结果；不为单一布尔不足而建立通用状态框架。 |
| 状态值 | `action_mode` 使用字符串常量；停止、暂停和校准状态使用布尔；计数使用整数；没有 `Enum`。 | 最小状态优先用现有布尔、整数或短字符串；不得仅为 R02 引入 Enum 状态机。 |
| 日志调用 | 同时存在 f-string 和 logging 参数化写法；消息多为中文，常带 emoji 和动作说明。OCR 详情日志使用参数化格式。 | R02 延续中文可检索日志；字段名保持英文固定键，原因/下一步用稳定短值，避免只写自然语言。 |
| 异常处理 | 外部边界常 `try/except Exception` 后记录并安全返回，如 `initialize_ocr()`、筛选/校准函数；纯解析和输入错误抛 `ValueError`；`forward_one_candidate()` 用 `finally` 保证焦点恢复。 | OCR 捕获/识别异常不得未捕获崩溃；停止中断与页面未加载要区分；不重复捕获上游已转为结果的异常。 |
| 等待、重试、停止 | 等待统一优先用 `safe_wait()`/`human_delay()`；OCR 用注入的 `wait` 和 `OCRInterrupted`；重试多为局部 `for`，如转发焦点恢复 `for attempt in range(1,3)`，没有通用重试库。 | R02 使用局部有限循环和可注入等待；每次等待前后响应 `stop_event`，不引入 retry 框架。 |
| 平台分支 | 正式主流程是 Windows 专用；少量跨平台差异集中在 `ocr_calibration.enable_windows_dpi_awareness()` 的 `platform.system()` 分支。 | 不在 R02 内启动 macOS 移植，也不复制 Windows 主循环建立伪跨平台层。 |
| 测试命名与 mock | 测试类继承 `unittest.TestCase`；测试名为 `test_<行为>`；主流程使用 `patch.object()`、`Mock`、`call` 和事件列表验证顺序；OCR 使用 `FakeCapture`/`FakeBackend`。 | 新测试沿用 `unittest`、小型 fake 和 `patch.object()`，明确断言禁止的 GUI/动作调用未发生。 |
| 注释和 docstring | 模块/类/函数多有短 docstring；`simple_brush.py` 用中文分段注释和步骤注释，OCR 模块用英文 docstring。 | 与目标文件相邻风格一致；只注释非显然的重试/计数语义。 |
| 主流程拆分粒度 | `run()` 负责整体编排；筛选、OCR、动作、刷新各有函数，但 `view_candidate()` 仍把规则、动作和停留滚动串联；`OCRKeywordDetector._observe()` 把 OCR 获取、文本加工和规则判断耦合在一起。 | 只允许为“纯 OCR 获取/指标”和“可复用刷新归位”做必要最小拆分。 |
| 配置存放 | 运行常量在 `simple_brush.py`；校准模板持久化在 `calibration_profiles.py` 的 `PROFILE_DIR`/schema；没有通用 settings 文件。 | R02 默认值继续放 `simple_brush.py` OCR 常量区，不写校准 JSON，不新增配置文件。 |
| dataclass/Enum/Protocol 使用 | OCR 和校准数据使用少量 dataclass，如 `OCRItem`、`ScanObservation`、`DetectionResult`、`ScreenRegion`、`ForwardClickRegions`；`Protocol` 仅用于 `OCRBackend`/`ScreenCapture` 注入；仓库没有 Enum，主流程也没有复杂类型体系。 | 复用已有结构即可；不新增通用 class、Enum、Protocol、规则引擎或状态机框架。 |

R02 实现必须保持目标模块及相邻代码的主流风格；不得借机全项目格式化、重命名、补类型注解或清理无关代码。

## 5. 问题背景

当前首位候选人打开后只等待 `CLICK_WAIT_SECONDS=2`，后续候选人切换后只等待 0.5 秒。等待结束不代表详情正文已加载。配置了关键词规则时，`view_candidate()` 会立即进入关键词 OCR；首屏为空或只有少量 UI 时会被当作普通“未命中”，随后 OCR detector 可能滚动，最终还会进入停留期随机滚动。

因此，“页面还没加载”与“页面已加载但规则不匹配”在当前控制流中没有被区分。R02 在规则判断之前增加最低可用性门，避免对未就绪页面执行任何不可逆或会改变页面位置的处理。

## 6. 复现现象

可按以下方式人工复现当前风险，不要求 Change 0A 实际操作真实页面：

1. 在网络较慢或 BOSS 详情加载延迟时打开首位候选人，或按右方向键切换下一位。
2. 固定等待结束时，OCR 正文区域仍为空、只显示少量框架/UI，或只加载出极少文字。
3. 当前 `detect_keywords()` 将该结果作为正式首屏；未命中时 `OCRKeywordDetector.detect()` 会继续滚动并扫描后续屏。
4. 最终 `view_candidate()` 把结果等同普通未命中，重置 `forward_consecutive`，再进入剩余停留和随机滚动。
5. 主循环增加累计人数并继续下一候选人；日志无法区分“未加载”与“规则未匹配”。

## 7. 业务影响

- 未加载页面可能被滚动，破坏后续重试时的原始首屏位置。
- 未加载候选人可能被错误记录为规则不匹配，降低筛选召回。
- 页面/UI 文本意外命中规则时，理论上可能进入收藏或转发安全门。
- 计数继续前进，导致候选人被跳过，且当前没有精确进度恢复能力。
- 连续加载故障没有页面级恢复和明确停止原因，操作员难以从日志判断故障性质。

## 8. 需求目标

R02 第一版只保护已经启用 OCR 关键词规则筛选的候选人处理流程。每名进入该正式筛选流程的候选人，必须在第一次正式规则判断和 OCR 滚动前，对已经校准的 OCR 正文区域做本地 OCR 最低可用性检测。只有检测通过，当前 OCR 结果才成为正式首屏，并允许规则判断、后续最多 8 屏扫描、收藏/转发和浏览滚动。

若未通过：原位置固定等待 1.5 秒并重新 OCR，默认最多重试 3 次；首次检测与 3 次重试全部失败后，在完整筛选归位条件可用时执行一次页面级硬恢复。条件不可用或恢复后立即再次发生完整加载失败时，进入 `load_failed`，通过现有安全停止和资源清理路径结束运行。

## 9. 需求范围

R02 本轮范围仅包括：

- 已启用关键词规则的收藏模式、转发模式，以及转发模式下有关键词的 `--no-forward` 安全测试路径。
- 两个最低可用性指标：`ocr_box_count`、`ocr_text_length`。
- 配置化阈值与冻结的组合判定。
- 首次检测 1 次 + 最多重试 3 次。
- 每次重试前固定等待 `LOAD_RETRY_WAIT_SECONDS=1.5`，且继续响应 ESC、暂停和运行时间结束。
- 重试期间的严格动作禁令。
- 成功 OCR 结果直接复用为正式首屏。
- 一次连续页面硬恢复额度、成功后清零、再次独立故障重新获得额度。
- OCR 截图/识别异常消耗同一检测预算；恢复条件不可用时的 fail-closed 安全停止。
- `total_viewed` 改为首次通过加载门时增加，失败尝试不计数。
- 最终失败的受控安全终止、统计保留和明确日志。
- 对应单元测试、主流程 mock 测试，以及 Windows 10/11 x64 + Microsoft Edge 人工冒烟。

无关键词纯浏览模式保持当前行为，不因 R02 初始化 OCR、触发 OCR 区域校准或改变构建 smoke 范围。未来若需保护纯浏览模式，必须单独扩展需求。

## 10. 非目标 / 不在本轮范围

以下明确不实现：

- R01 候选人切换成功验证。
- R03 基础 OCR 页面指纹。
- R04 OCR 文本标准化。
- R05 多屏内容去重和聚合。
- R06 相似度指纹。
- R07 动态扫描结束。
- R08 候选人统一 JSON。
- R09—R12 AI 接入。
- R13 SQLite。
- 候选人姓名识别、`candidate_name_detected`、姓名正则或姓名区域语义判断。
- 正文锚点识别、`body_anchor_detected`、个人优势/工作经历/项目经历判断。
- 骨架屏、“加载中”、网络错误页、空白模板或加载占位页识别。
- 与上一候选人比较。
- 自动恢复到精确候选人进度。
- 新增 GUI 或 CLI 配置入口。
- 无关键词纯浏览模式的加载检测、OCR 初始化或 OCR 区域校准。
- macOS 正式候选人处理流程适配或端到端验收。
- 为 R02 新增非零退出码或建立统一进程退出码协议；未来如建立外部调用接口或运行状态协议，再统一设计。
- OCR 固定 UI 删除、标点删除、全半角统一、大小写统一、坐标排序后标准化全文、重复文本去重。
- SHA-256、SimHash 或其他页面指纹。
- 数据库写入、候选人统一 JSON。
- 无关性能优化、代码清理、格式化、重命名或架构升级。

未来字段可以在后续 RPD/TID 中定义，但 R02 当前不得执行姓名或正文锚点检测，不得伪造为 `true`，也不得因其未实现而阻止页面放行。

## 11. 术语与字段定义

| 术语/字段 | 冻结定义 |
| --- | --- |
| 加载检测 | 对进入 OCR 关键词规则正式筛选流程的当前候选人，在校准 OCR 区域截图、运行本地 OCR、计算两个指标并执行本 RPD 判定；不含规则判断。 |
| 首次检测 | 现有候选人打开或切换等待结束后，在未滚动、且不额外增加 R02 等待的情况下执行的第 1 次加载检测。 |
| 重试 | 首次检测失败后，在同一位置固定等待 `LOAD_RETRY_WAIT_SECONDS=1.5` 再重新截图/OCR；`max_load_retries=3` 不包含首次检测。 |
| OCR 异常 | 单次截图或识别没有成功完成；本次机会按失败消耗，`reason=ocr_error`，两个指标未知且不得伪造为 0。 |
| 完整加载失败 | 首次检测与 3 次重试共 4 次均未通过；成功 OCR 的阈值失败和 `ocr_error` 可以任意组合。 |
| 正式首屏 | 第一次通过加载判定的 OCR 结果；失败尝试不属于正式扫描结果。 |
| 页面级硬恢复 | 当前进程内刷新 Boss 页面、重新应用“最近 14 天没看过”、重新打开校准首位候选人，并从批次内第 1 位重新进入处理循环。 |
| 连续恢复次数 | 自上一次候选人加载成功以来，已经执行的页面级硬恢复次数；不是整场运行累计恢复总数。 |
| `ocr_box_count` | 当前 OCR 区域内，经过既有置信度过滤后剩余的 OCR 文字框数量。 |
| `ocr_text_length` | 所有置信度有效框的 `text` 分别去除首尾空格后，忽略空文本，按字符数求和。字段名只能是 `ocr_text_length`。 |

禁止使用 `normalized_text_length` 作为字段名或计算口径。

加载状态只使用以下五个短字符串，不引入 Enum 或状态机框架：

| 状态 | 定义 |
| --- | --- |
| `loading` | 正在执行首次加载检测。 |
| `load_retrying` | 首次检测未通过，正在等待或执行有限重试。 |
| `loaded` | 某次检测通过，成功 OCR 将作为正式首屏。 |
| `load_recovering` | 4 次检测失败，正在执行页面级硬恢复。 |
| `load_failed` | 无法执行硬恢复、恢复步骤失败，或恢复后再次完整失败，准备安全终止。 |

## 12. OCR 指标口径

设 `items` 为 `RapidOCRBackend.recognize()` 返回的 `OCRItem` 序列，`min_confidence` 为现有 `OCRKeywordDetector.min_confidence`，当前默认由 `OCR_MIN_CONFIDENCE=0.85` 注入。

```text
accepted_items = [item for item in items if item.confidence >= min_confidence]
ocr_box_count = len(accepted_items)
ocr_text_length = sum(len(item.text.strip()) for item in accepted_items if item.text.strip())
```

冻结说明：

1. `ocr_box_count` 只应用现有置信度过滤，不额外删除空文本框、UI 框、重复框或按位置过滤。
2. `ocr_text_length` 对每个有效框单独 `strip()`，忽略 `strip()` 后为空的文本，再求 Python 字符数总和。
3. 不先排序，不拼接分隔符，不对字符做 NFKC、大小写、全半角、标点或空白标准化。
4. 不能使用 `ScanObservation.item_count`，因为当前它是过滤前的 `len(items)`。
5. 不能使用 `ScanObservation.text` 计算长度，因为当前它已经经过 `order_items()` 和 `normalize_text()`。
6. R02 指标计算不改变规则匹配现有的 `searchable_text()`、`normalize_text()` 与框排序行为。

## 13. 加载判定规则

逻辑配置名与默认值：

| 配置 | 默认值 | 说明 |
| --- | ---: | --- |
| `ocr_box_count_threshold` | 5 | 少量文字框阈值 |
| `ocr_text_length_threshold` | 30 | 少量文本长度阈值 |
| `max_load_retries` | 3 | 首次检测之后允许的重试次数 |
| `max_consecutive_load_recoveries` | 1 | 连续完整失败允许的页面级硬恢复次数 |
| `LOAD_RETRY_WAIT_SECONDS` | 1.5 秒 | 每次加载重试前的固定等待；不替代现有打开、切换、刷新或筛选等待 |

实现时应按当前代码风格将新增配置放入 `simple_brush.py` OCR 配置区并使用具名大写常量；不得把 5、30、3、1 或 1.5 散落在流程中。`LOAD_RETRY_WAIT_SECONDS` 的名称和值已经冻结。

判定为未加载，当且仅当：

```text
ocr_box_count == 0
OR
(ocr_box_count <= 5 AND ocr_text_length < 30)
```

其他情况暂时放行。边界真值表：

| `ocr_box_count` | `ocr_text_length` | 结果 | 原因 |
| ---: | ---: | --- | --- |
| 0 | 任意 | 未加载 | `zero_ocr_boxes` |
| 1—5 | 0—29 | 未加载 | `low_box_count_and_short_text` |
| 1—5 | 30 或更大 | 放行 | 文本长度达到阈值 |
| 6 或更大 | 任意 | 放行 | 框数超过阈值 |

明确边界包括：0 框未加载；5 框、29 字未加载；5 框、30 字放行；6 框、10 字放行；2 框、100 字放行。

最后两行可能产生经验性误放行，但属于本轮冻结规则；R02 不得自行增加姓名、正文锚点、UI 删除或占位页判断来“修正”它。

## 14. 等待与重试流程

对每名进入 OCR 关键词规则正式筛选流程的候选人执行以下顺序；无关键词纯浏览模式不进入本流程：

1. 先完成现有候选人打开等待（首位 `CLICK_WAIT_SECONDS`）或下一候选人切换等待（当前 0.5 秒）。R02 不修改这些等待，也不在首次检测前叠加新等待。
2. 保持当前首屏位置，状态设为 `loading`，立即执行首次加载检测，记为 `attempt=initial`、`retry_number=0`。
3. 若通过，状态设为 `loaded`，直接进入第 16 节的成功结果复用。
4. 若阈值未通过或发生 `ocr_error`，且未收到 ESC/运行时间结束，状态设为 `load_retrying`，进入最多 3 次重试。每次重试必须：
   1. 调用可响应 ESC、暂停和运行时间结束的固定等待 `LOAD_RETRY_WAIT_SECONDS=1.5`；
   2. 对同一个校准 OCR 区域重新截图；
   3. 重新调用同一个进程内 RapidOCR backend；
   4. 重新计算两个指标；
   5. 重新判断并记录日志。
5. 单次截图或 OCR 识别异常消耗当前一次检测机会，记录 `reason=ocr_error`；两个指标保持未知，内部可用 `None` 或相邻代码风格的等效值，文本日志显示 `-` 或 `unavailable`，不得伪造为 0。异常不建立独立预算或恢复流程。
6. 任意重试通过，状态设为 `loaded` 并立即停止重试，不再额外 OCR。
7. 首次 + 3 次重试全部失败，总 OCR 加载检测次数恰好为 4，进入页面级硬恢复判断。
8. ESC/运行时间结束发生时立即按现有停止语义退出；停止中断不是加载失败，不消耗尚未开始的下一次检测，不触发页面硬恢复。

统一时序为：

```text
现有候选人打开或切换等待
→ 首次加载 OCR
→ 未加载或 ocr_error
→ 等待 1.5 秒
→ 重试 1
→ 未加载或 ocr_error
→ 等待 1.5 秒
→ 重试 2
→ 未加载或 ocr_error
→ 等待 1.5 秒
→ 重试 3
```

页面级硬恢复继续使用现有刷新、筛选和首位打开等待，不由 `LOAD_RETRY_WAIT_SECONDS` 替代。

## 15. 重试期间禁止行为

从一次加载检测判定失败，到下一次检测通过、开始硬恢复或最终停止之前，禁止：

- OCR 扫描滚动 `ocr_scroll_down()`；
- 停留期随机滚动 `human_scroll_once()`；
- 点击正文或其他页面区域；
- 调用 `matching_keyword_rule()` 或任何规则判断；
- 将失败 OCR 放入正式 `DetectionResult.observations`；
- 将候选人记为规则不匹配或重置 `forward_consecutive`；
- 调用 `perform_favorite_action()`；
- 调用 `forward_one_candidate()`；
- 按右方向键进入下一候选人；
- 执行收藏后或转发后的焦点恢复；
- 增加正式扫描屏数；
- 进入下一批次或正常 100 人刷新路径。

允许的操作只有：原位置固定等待 1.5 秒、同区域截图、本地 OCR、指标计算、判定、日志、停止检查，以及 4 次失败后按恢复条件进入页面级硬恢复或 `load_failed`。单次 `ocr_error` 只消耗同一检测预算，不解除任何禁令。

## 16. 成功结果复用

任意加载检测通过后：

1. 当次截图、OCR 原始 `OCRItem` 列表及由其生成的规则搜索文本，直接成为正式扫描第 1 屏结果。
2. 不允许为了进入规则判断而立即重复截图或重复 OCR。
3. 若配置了规则，使用现有置信度、排序、`searchable_text()` 和 `matching_keyword_rule()` 对该结果执行规则判断。
4. 若正式首屏命中规则，仍按现有要求等待 `OCR_CONFIRMATION_SECONDS` 并进行一次独立二次确认；加载成功本身不能替代关键词二次确认。
5. 若正式首屏未命中，后续才允许现有 `OCRKeywordDetector.detect()` 的最多 8 屏流程向下滚动。正式首屏计入 8 屏，之前的加载失败尝试不计入。
6. 加载成功后立即将 `consecutive_load_recoveries` 清零，即使之后该候选人的规则不匹配或动作失败。
7. 在成功 OCR 被确认为正式首屏、准备进入正式 OCR 规则扫描时，将 `total_viewed` 增加 1；同一候选人的加载重试只增加一次。通过加载门后，即使规则不匹配或后续规则扫描、收藏、转发发生其他失败，该候选人仍算已查看。

当前 `_observe()` 同时做 OCR 获取和规则判断，且不保留有效 `OCRItem`。允许的最小结构调整是抽取“一次纯 OCR 获取/观察”，或让 detector 接受一个已获取的首屏 observation；不得复制 OCR 调用，也不得建立通用扫描框架。

## 17. 页面级硬恢复

首次检测加 3 次重试全部失败后，不得简单跳过候选人。只有完整 `BatchFilterRegions` 可用、`batch_filter_enabled=True`，且 `consecutive_load_recoveries < max_consecutive_load_recoveries` 时，才执行一次完整硬恢复：

1. 将当前状态记为 `load_recovering`，连续恢复次数加 1 并记录日志。
2. 通过现有 F5 刷新能力刷新当前 Boss 页面；R02 需要复用或最小参数化 `refresh_page()`，避免沿用“已查看 100 位”的错误原因文案。
3. 使用现有 `REFRESH_WAIT_SECONDS`/可停止等待等待候选人列表加载。
4. 复用 `apply_batch_filter_and_open_first_candidate()`：打开筛选、选择“最近没看过”、确认、等待筛选结果、点击 `BatchFilterRegions.first_candidate`。
5. 将当前 100 人批次内序号清零，从新首位候选人重新进入加载检测与候选人处理循环。
6. 继续使用本次运行已创建的 `ocr_backend`、`ocr_capture`、`ocr_detector.region` 和所有校准区域。
7. 刷新、筛选或首位打开任一步失败时，不切换 legacy 路径、不复制恢复动作，状态进入 `load_failed` 并安全终止。

硬恢复不是：

- 重启 Python 进程；
- 重启浏览器；
- 重新校准 OCR 或任何点击区域；
- 重置运行计时器、已用时间或总处理人数；
- 重新选择收藏/转发模式；
- 重新输入关键词规则或邮箱；
- 恢复到失败前的精确候选人。

### 17.1 与 legacy/`--no-batch-filter` 路径的约束

当前 `open_first_candidate_for_batch()` 在 `batch_filter_enabled=False` 时只能点击 `legacy_point`，无法重新设置“最近没看过”；`--no-batch-filter` 即使加载模板也明确禁用筛选归位。冻结的硬恢复步骤要求筛选区域和校准首位区域，因此这些路径不具备完整硬恢复条件。

产品策略现已冻结：`batch_filter_enabled=False`、使用 `--no-batch-filter`、完整 `BatchFilterRegions` 不可用或筛选归位区域缺失时，不在运行前禁止该模式，R02 首次检测和最多 3 次原位置重试仍然有效；加载成功后正常进入正式 OCR 扫描。

若 4 次检测全部失败，则完整硬恢复不可用，必须：

1. 记录 `reason=hard_recovery_unavailable`；
2. 将其视为页面级不可恢复加载故障；
3. 状态进入 `load_failed`；
4. 使用现有安全停止和资源清理路径终止；
5. 不滚动、不执行规则、不收藏、不转发、不进入下一候选人。

此路径不使用 `legacy_point` 模拟硬恢复，不盲点筛选区域，不只执行 F5 后继续，不新增另一套筛选实现，也不新增 GUI 或 CLI。

## 18. 计数和状态保留规则

| 状态 | 硬恢复时规则 |
| --- | --- |
| 批次内候选人序号 | 重置为 0；重新打开的首位候选人对外日志为 1。 |
| 批次序号 | R02 第一版不强制新增全局或单调递增编号。若 TID 能用一个简单整数且不重构主循环地提供 `batch`，可作为可选日志增强；不得建立复杂批次对象。 |
| `total_viewed` | 仅在候选人第一次进入 `loaded`、成功 OCR 成为正式首屏并准备规则扫描时增加 1。首次/重试失败、4 次失败、硬恢复本身均不增加；恢复后首位候选人通过加载门才增加；硬恢复不清零。 |
| 运行总计时 | 原 `run_timer` 继续运行，不取消、不重启；恢复和重试时间计入本次运行。 |
| `action_mode`、`forward_keywords`、`backup_email`、`no_forward_mode` | 全部保留。 |
| OCR 引擎/截图器/区域 | `ocr_backend`、`ocr_capture`、`ocr_detector`、已校准 `region` 全部保留，不重新初始化或校准。 |
| 校准模板与点击区域 | `selected_calibration_profile`、筛选、收藏、转发、焦点恢复区域全部保留。 |
| `forward_consecutive` | 页面加载故障不是规则未命中，也不是正常 100 人批次结束；默认保留，避免硬恢复绕过连续转发安全上限。正常 100 人刷新仍维持现有清零行为。 |
| 当前候选人加载重试序号 | 硬恢复后新首位候选人从首次检测重新开始。 |
| 连续页面恢复次数 | 刷新后保持为 1；直到任一候选人加载成功才清零。 |

## 19. 连续恢复限制

默认 `max_consecutive_load_recoveries=1`，语义如下：

1. 初始 `consecutive_load_recoveries=0`。
2. 第一次完整加载失败在恢复条件可用时允许进入 `load_recovering` 并执行硬恢复，计数变为 1；恢复条件不可用时直接进入 `load_failed`，不伪造一次恢复。
3. 硬恢复后，如果任意候选人加载成功并进入 `loaded`，立即将计数清零。
4. 若硬恢复后新首位候选人又连续 4 次检测失败，因为计数已达到 1，不再 F5，状态进入 `load_failed`。
5. 如果恢复后已成功处理过至少一位候选人，后来独立出现新的完整加载失败，则计数此前已清零，允许再次执行一次硬恢复。

该计数不是整场运行累计次数，不得在进程首次恢复后永久禁用恢复。

## 20. 最终失败处理

最终失败状态统一为 `load_failed`。它表示页面级不可恢复加载故障，包括：连续恢复额度已耗尽后再次完整失败；`batch_filter_enabled=False`、`--no-batch-filter`、完整恢复区域缺失导致 `hard_recovery_unavailable`；以及刷新、筛选或首位重开步骤失败。

必须：

- 设置可区分于 ESC 和运行时间结束的最小停止原因 `load_failed`，并停止候选人内外层循环；
- 将 `stop_event` 用作现有动作/等待安全门时，保留独立原因，绝不输出“收到 ESC”；
- 不再滚动、规则判断、收藏、转发、焦点恢复、下一候选人导航或额外刷新；
- 使用 `logger.error()` 写明页面级不可恢复加载故障、最后可用指标或未知标记、候选人序号、`total_viewed`、连续恢复次数和下一步 `safe_stop`；
- 保留 `total_viewed`、运行计时信息和所有既有运行统计；
- 进入 `run()` 的 `finally`，取消计时器并输出最终累计统计；随后由 `__main__` 的 `finally` 停止 keyboard listener；
- 以现有受控返回结束，不以未捕获异常崩溃，不专门为 R02 新增非零退出码或进程退出码协议；
- 不记录为规则不匹配，不重置 `forward_consecutive`，不记录为正常 ESC。

最终 `load_failed` 保持现有进程退出码语义，通过最小停止原因与 ERROR 日志区分 ESC 和运行时间结束，并继续复用 `run()` 与 `__main__` 的资源清理路径。

## 21. 日志要求

R02 继续使用现有 logging 配置。每次加载检测至少记录以下字段：

| 字段 | 要求 |
| --- | --- |
| 时间戳 | 由现有 formatter 自动提供。 |
| `batch` | 可选增强；仅当一个简单整数即可提供且无需重构主循环时记录，不作为 R02 第一版验收条件。 |
| `candidate_in_batch` | 1 基批次内序号。 |
| `total_viewed` | 当前已通过加载门的累计候选人数；当前失败候选人尚未通过时不得提前增加。 |
| `attempt` | `initial` 或 `retry`。 |
| `retry_number` | 首次为 0，重试为 1—3。 |
| `ocr_box_count` | OCR 成功时记录第 12 节口径的整数；发生 `ocr_error` 时为未知，文本日志使用 `-` 或 `unavailable`，不得伪造 0。 |
| `ocr_text_length` | OCR 成功时记录第 12 节口径的整数；发生 `ocr_error` 时为未知，文本日志使用 `-` 或 `unavailable`，不得伪造 0。 |
| `decision` | `ready`、`not_loaded` 或 `error`；它是单次判断结果，不是加载状态名。 |
| `reason` | 至少支持 `zero_ocr_boxes`、`low_box_count_and_short_text`、`threshold_passed`、`ocr_error`、`hard_recovery_unavailable`。 |
| `state` | 只能是 `loading`、`load_retrying`、`loaded`、`load_recovering`、`load_failed` 之一；不引入 Enum。 |
| `recovery_count` | 当前连续硬恢复次数。 |
| `next_action` | 如 `reuse_first_scan`、`wait_and_retry`、`hard_refresh`、`safe_stop`。 |

`reuse_first_scan`、`wait_and_retry`、`hard_refresh`、`safe_stop` 只能作为 `next_action`，不能作为加载状态。即使不记录可选 `batch`，时间戳、`candidate_in_batch`、`total_viewed`、`recovery_count` 和 `retry_number` 也必须能够定位故障。页面硬恢复还要记录每个关键步骤的开始、成功或失败；最终失败必须用 ERROR。日志不写完整 OCR 文本、候选人姓名、JSON 或数据库，避免扩大隐私面。

## 22. 与 R01、R03、R08、R13 的边界

- R01：R02 不验证右方向键是否切换到新候选人。即使实际仍是上一候选人，只要当前 OCR 指标满足阈值，R02 会放行；这是已知限制。
- R03：R02 不创建基础 OCR 页面指纹，不与前后页面比较，不做哈希/相似度。
- R08：R02 不定义候选人统一 JSON，也不把加载检测结果封装成跨需求候选人对象。
- R13：R02 不写 SQLite；日志文件是本轮唯一持久化诊断输出。
- 平台：R02 第一版正式范围为 Windows 10/11 x64 + Microsoft Edge；公共 OCR 单元测试仍需回归，但不要求 macOS 正式候选人流程或端到端覆盖。

## 23. 风险和已知限制

1. 冻结规则是经验阈值：6 个很短/空文本框仍会放行；1 个长度 30 的框也会放行。R02 不在本轮修正。
2. 固定 UI 可能贡献框数和长度；本轮不删除 UI。
3. 页面已加载但正文很短时可能被判为未加载，触发重试/恢复。
4. 当前 `ScanObservation.item_count` 是过滤前数量，误用会违反冻结口径。
5. 当前 `ScanObservation.text` 已标准化，误用会违反 `ocr_text_length` 口径。
6. 当前 `_observe()` 把 OCR、文本处理和规则判断耦合；若实现不做最小拆分，就无法保证重试期间不执行规则。
7. 当前 `view_candidate()` 的 `False` 返回若未伴随 `stop_event=True`，内层循环退出后仍可能进入正常刷新；最终失败必须显式阻断外层流程。
8. `refresh_page()` 日志写死“已查看 100 位”，需要最小参数化或抽取低层 F5 动作。
9. legacy/`--no-batch-filter` 没有完整硬恢复所需区域；R02 已冻结为重试仍有效、4 次失败后以 `hard_recovery_unavailable` 安全终止，无法提供页面恢复能力。
10. 当前没有显式批次序号，只有 `for i`；R02 不强制新增批次编号，日志定位必须依靠候选人序号、累计人数、恢复/重试计数和时间戳。
11. `total_viewed` 当前在处理前增加；R02 必须把增加时点调整到成功进入 `loaded`，这是本需求必要改动而非无关重构。
12. `stop_event` 不含原因；需要最小区分，不应扩展为通用状态机。
13. R02 不解决候选人切换失败、页面重复、动态结束、精确进度恢复或页面占位识别。
14. 无关键词纯浏览模式不受 R02 保护，仍可能在详情未加载时进入现有停留和随机滚动；这是第一版明确范围边界，未来需单独扩展。
15. 自动化测试均为 mock/fake，不能替代真实 Windows Edge 页面在网络延迟下的人工冒烟。
16. R02 第一版不覆盖 macOS 正式候选人流程，不能从公共 OCR 测试推断 macOS 候选人处理可用。

## 24. 自动化测试场景

### 24.1 指标与判定纯测试

建议在 `tests/test_ocr_detector.py` 或与 OCR 纯函数相邻的测试中覆盖：

1. 低于 `min_confidence` 的框不计入 `ocr_box_count` 和 `ocr_text_length`。
2. 等于 `min_confidence` 的框计入。
3. `ocr_text_length` 对每框独立去首尾空格并忽略空文本。
4. 中文、英文、标点和内部空格按原字符数计数，不执行 NFKC、大小写、全半角或标点删除。
5. 原始 10 框、过滤后 3 框时 `ocr_box_count=3`，证明没有使用 `ScanObservation.item_count`。
6. 真值表覆盖 `(0,任意)`、`(5,29)`、`(5,30)`、`(6,10)`、`(2,100)`。

### 24.2 重试与成功复用

使用 `FakeCapture`/`FakeBackend` 或最小 fake 序列覆盖：

1. 现有候选人打开/切换等待之后立即执行首次检测，不额外调用 `LOAD_RETRY_WAIT_SECONDS`；首次成功只 OCR 1 次，状态从 `loading` 进入 `loaded`。
2. 首次失败、重试 1 成功共 OCR 2 次，且只在重试 1 前等待一次 1.5 秒。
3. 重试 3 成功共 OCR 4 次，三次重试前分别、且仅等待 1.5 秒。
4. 4 次均失败不执行第 5 次 OCR，返回硬恢复信号。
5. 每次重试使用同一 `ScreenRegion`。
6. 重试期间 `scroll`、规则 matcher、favorite、forward、focus restore、next candidate 全部未调用。
7. 成功的那次 OCR 直接作为正式首屏，规则判断不触发额外 recognize/capture。
8. 正式首屏命中规则时，现有二次确认仍额外 OCR 1 次且保持同屏。
9. 正式首屏未命中时，最多 8 屏总数仍包含该首屏；失败加载尝试不计入 8 屏。
10. ESC/定时停止打断固定等待时不继续 OCR、不恢复、不动作。
11. capture 或 backend 单次异常记录 `reason=ocr_error`、消耗当前机会，两个指标内部为未知且日志不是 0；仍有预算时只等待 1.5 秒后继续。
12. 阈值失败与 `ocr_error` 任意组合占满 4 次时进入相同硬恢复判断，不创建独立 OCR 异常预算。
13. `loading → load_retrying → loaded`、`loading/load_retrying → load_recovering` 和失败状态流转使用第 11 节五个固定状态名。

### 24.3 主流程、恢复与安全停止

在 `tests/test_simple_brush_ocr.py` 沿用事件列表和 `patch.object()` 覆盖：

1. 只有 `forward_enabled and forward_keywords` 的候选人才在正式规则/动作/OCR 滚动前调用加载门；有关键词 favorite、forward、forward + `--no-forward` 均覆盖。
2. 无关键词纯浏览模式不调用 R02 加载门，不新增 OCR 初始化或 OCR 区域校准，保持现有构建 smoke 和浏览路径。
3. 完整恢复条件可用时，失败后的调用顺序为 F5 → 现有刷新等待 → 打开筛选 → 最近没看过 → 确定 → 现有结果等待 → 首位候选人。
4. `batch_filter_enabled=False`、`--no-batch-filter`、完整区域缺失时，首次 + 3 次重试仍执行；4 次失败后记录 `hard_recovery_unavailable`、进入 `load_failed`，不调用 F5、legacy 点击、规则、滚动或动作。
5. 硬恢复时批次内序号清零，timer、规则、模式、OCR detector/region 和 `forward_consecutive` 保持。
6. 硬恢复不调用 `initialize_ocr()`、`select_screen_region()`、`get_user_input()`、`start_run_timer()`。
7. `total_viewed` 在候选人首次进入 `loaded` 时恰好增加 1；失败检测、4 次失败和硬恢复本身不增加，恢复后首位成功才增加。
8. 通过加载门后，即使规则不匹配或后续扫描/动作失败，`total_viewed` 也不回退；硬恢复不清零既有累计值。
9. 第一次硬恢复后首位候选人加载成功，连续恢复计数清零。
10. 成功后后来发生独立故障，允许再次恢复一次。
11. 硬恢复后立即再次完整失败，不调用第二次 F5；进入 `load_failed`、记录 ERROR 并进入 finally 清理。
12. 最终失败后不调用 `next_candidate()`、正常批次刷新、favorite、forward 或焦点恢复，也不进入规则不匹配路径或重置 `forward_consecutive`。
13. 正常 100 人刷新仍重置 `forward_consecutive` 并重开首位候选人，现有回归测试继续通过。
14. `load_failed` 与 ESC、运行时间结束可由最小原因区分，但保持现有受控返回和进程退出码语义。
15. 日志无需 `batch` 也能通过时间戳、`candidate_in_batch`、`total_viewed`、`recovery_count`、`retry_number` 定位；如无主循环重构即可提供简单 `batch`，只作为可选增强测试。
16. 所有受影响的公共 OCR 单元测试继续运行；不增加 macOS 正式候选人流程 E2E 要求。

## 25. 人工冒烟场景

所有真实页面验证限定在 Windows 10/11 x64 + Microsoft Edge，先使用测试账号、有效关键词规则和 `--no-forward`，全程人工监控；不要求 macOS 正式候选人流程冒烟：

1. **正常立即加载**：打开 3—5 位候选人，确认每位首屏只有一次加载 OCR，随后规则/滚动行为与 v1.2 一致。
2. **短暂延迟后成功**：通过受控网络延迟或手工时序让首次 OCR 内容不足，确认首次检测前没有新增 R02 等待，失败后每次固定等待 1.5 秒，原位置无滚动/点击，1—3 次重试内成功后直接进入规则判断。
3. **首次完整失败后恢复成功**：让 4 次检测均不足，确认只 F5 一次、重新应用“最近没看过”、点击首位、批次内序号从 1 开始，运行计时和累计人数未清零。
4. **恢复不可用**：在 `--no-batch-filter` 或完整筛选区域缺失的受控场景制造 4 次失败，确认不 F5、不使用 legacy 点击，记录 `hard_recovery_unavailable` 并进入 `load_failed`。
5. **恢复后再次完整失败**：确认不执行第二次 F5，不收藏、不转发、不滚动，以明确 ERROR 和非 ESC/非运行时间结束原因安全结束。
6. **成功后独立故障**：恢复成功处理至少一位后再次制造完整失败，确认重新获得一次恢复额度。
7. **ESC/运行时间结束中断**：在重试等待和恢复等待中触发停止，确认立即结束，不误记 `load_failed`。
8. **模式回归**：在有关键词 favorite、forward + `--no-forward` 下各检查一次加载成功后的分发；本轮不建议真实邮件转发。
9. **无关键词回归**：确认纯浏览模式不新增 OCR 初始化、区域校准或加载检测，保持现有行为。
10. **统计与日志**：确认失败候选人不增加 `total_viewed`、首次 `loaded` 后只增加 1；日志包含候选人序号、累计人数、attempt/retry、两个指标或未知标记、结果、原因、五种状态之一、恢复次数、下一步和时间戳；`batch` 可缺省。

## 26. 完整验收标准

### 26.1 文档与范围

- [ ] RPD 只使用 `ocr_box_count` 与 `ocr_text_length`，字段名准确。
- [ ] 两个指标完全按第 12 节计算，不使用另一套置信度或标准化。
- [ ] 判定条件严格为 `box_count==0 OR (box_count<=5 AND text_length<30)`。
- [ ] 姓名、正文锚点、占位页、指纹、数据库和统一 JSON 均未实现。
- [ ] 阈值和次数配置化，无散落魔法数字。
- [ ] R02 第一版只覆盖启用 OCR 关键词规则的 favorite、forward 和 forward + `--no-forward` 流程。
- [ ] 无关键词纯浏览模式不新增 OCR 初始化、区域校准或加载门。
- [ ] 正式实现和人工验收平台为 Windows 10/11 x64 + Microsoft Edge，不要求 macOS 候选人流程 E2E。

### 26.2 检测、重试与动作门

- [ ] 每名进入 OCR 关键词规则正式筛选流程的候选人在第一次正式规则判断和 OCR 滚动前完成加载检测。
- [ ] 首次 1 次 + 重试最多 3 次，最大总检测次数 4。
- [ ] 现有打开/切换等待保持不变，首次检测前不叠加 R02 等待；每次重试前固定等待 `LOAD_RETRY_WAIT_SECONDS=1.5`。
- [ ] 重试只在原位置等待、截图、OCR、判断。
- [ ] OCR 截图/识别异常消耗同一检测预算，记录 `ocr_error`，未知指标不伪造为 0，也不建立独立重试流程。
- [ ] 重试期间所有第 15 节禁止行为均有自动化未调用断言。
- [ ] 任意一次成功即停止重试，成功 OCR 直接作为正式首屏，无重复 OCR。
- [ ] 正式 8 屏和关键词二次确认语义保持不变。

### 26.3 恢复、状态与停止

- [ ] 4 次失败不跳过候选人；完整恢复条件可用时执行页面级硬恢复。
- [ ] 硬恢复复用 F5、筛选和首位打开函数，不复制长期可能漂移的点击序列。
- [ ] `--no-batch-filter`、`batch_filter_enabled=False` 或完整区域不可用时，重试仍执行，4 次失败后记录 `hard_recovery_unavailable` 并进入 `load_failed`；不 F5、不使用 legacy 点击模拟恢复。
- [ ] 批次内计数清零；总计时、模式、规则、邮箱、OCR 区域、校准状态和 `forward_consecutive` 保留。
- [ ] `total_viewed` 只在首次 `loaded` 时增加 1；失败检测和硬恢复不增加、不清零。
- [ ] `max_consecutive_load_recoveries=1` 是连续计数，任一候选人加载成功后清零。
- [ ] 恢复后立即再完整失败时不再刷新，受控安全终止。
- [ ] 最终失败不是 ESC、不是规则不匹配、不是未捕获异常，并保留统计。
- [ ] 最终失败后不再滚动、收藏、转发、切换候选人或恢复焦点。
- [ ] 最终故障状态为 `load_failed`，与 ESC、运行时间结束区分；保持现有受控返回和退出码语义，不新增退出码协议。
- [ ] 加载状态全文只使用 `loading`、`load_retrying`、`loaded`、`load_recovering`、`load_failed`，不引入 Enum/状态机。

### 26.4 日志、测试与回归

- [ ] 每次判断记录第 21 节全部必需字段，最终失败使用 ERROR；`batch` 仅为可选增强。
- [ ] OCR 指标、边界真值、重试次数、成功复用、恢复次数和停止路径均有单元测试。
- [ ] `tests/test_ocr_detector.py`、`tests/test_ocr_text.py`、`tests/test_simple_brush_ocr.py` 相关既有测试不回归。
- [ ] 全量 `unittest discover` 通过。
- [ ] Windows `--no-forward` 人工冒烟覆盖第 25 节关键场景。
- [ ] 未新增真实页面自动化、DOM/浏览器驱动或真实转发测试副作用。

## 27. 后续 Change 固定拆分

下一步是 **Change 0B：编写 TID**；Change 0B 不属于以下实施 Change。R02 后续实施严格使用已经批准的六段拆分，不得合并、减少或改名：

### Change 1：加载判定基础能力

- 增加 R02 配置项。
- 提取 `ocr_box_count` 和 `ocr_text_length`。
- 实现纯加载判定逻辑与边界单元测试。
- 不改变生产运行流程。

### Change 2：首屏加载门禁

- 将加载检测接入第一次正式 OCR 扫描之前。
- 未加载时禁止规则判断、滚动和动作。
- 正常加载页面维持原有正式流程。

### Change 3：原位置有限重试与 OCR 结果复用

- 首次检测 1 次、最多重试 3 次。
- 每次重试前固定等待 1.5 秒，ESC、暂停和运行时间结束仍有效。
- 成功 OCR 直接作为正式首屏。
- 重试耗尽向上层返回明确结果。

### Change 4：页面级硬恢复

- 重试耗尽后，在完整恢复条件可用时刷新当前页面。
- 复用现有 100 人刷新、重新筛选和首位候选人打开流程。
- 重置当前批次状态。
- 保留总运行计时、总统计、动作模式、规则、邮箱和校准。

### Change 5：连续恢复限制、安全终止和日志

- 实现连续页面硬恢复次数限制和成功后清零。
- 持续失败或硬恢复不可用时安全终止。
- 区分 ESC、运行时间结束和 `load_failed`。
- 补齐完整加载检测与恢复日志。

### Change 6：完整测试与验收

- 完成自动化测试与全量回归。
- 完成 Windows 10/11 x64 + Microsoft Edge 人工冒烟。
- 编写 Acceptance Report。
- 只修复 R02 直接导致的问题，不要求 macOS 正式候选人流程覆盖。

每个 Change 只实现自己的验收目标；发现非本轮问题时记录，不直接修复。

## 28. 非本轮发现的问题

以下为仓库审计发现，不授权在 Change 0A 或 R02 实现中顺手修复无关部分：

1. `ScanObservation.item_count` 的名称容易让人误认为是有效框数，实际是置信度过滤前框数。
2. `ScanObservation.text` 只保留标准化搜索文本，原始有效框与原始长度没有保留。
3. `view_candidate()` 将 OCR 错误/空结果统一折算成 `False`，上层无法区分规则未命中与页面未加载。
4. `run()` 在处理前增加 `total_viewed`，统计可能包含未完成处理的候选人；R02 已冻结为首次进入 `loaded` 时增加，后续实现必须调整该时点。
5. `view_candidate()` 返回 `False` 且 `stop_event=False` 时，主循环可能继续执行正常批次刷新。
6. `refresh_page()` 的日志原因与函数动作耦合，无法准确用于非 100 人恢复。
7. 当前没有显式批次序号或停止原因；R02 只要求最小 `load_failed` 原因，不强制新增批次编号。
8. legacy/`--no-batch-filter` 路径无法执行完整页面级硬恢复；R02 已冻结为 4 次失败后 `hard_recovery_unavailable` 安全终止。
9. 当前无真实 BOSS 页面 E2E 自动化；打包 smoke 不覆盖 OCR 或候选人处理。
10. `ocr_mac_demo.py` 仍把分号文本直接传给 detector，而当前 detector 类型约定为 `KeywordRule`；它不是正式候选人主流程，也没有相关端到端覆盖。本轮只记录。

## 29. TID 前仍需确认的技术问题

以下只涉及最小代码落点，不重新打开已经冻结的产品决策：

1. **一次纯 OCR 结果的最小承载方式**：确定是最小扩展 `ScanObservation`/`DetectionResult`，还是增加相邻的小型返回结构，以同时保留原始 `OCRItem`、指标和规则搜索文本，并确保成功首屏不重复 OCR。
2. **加载门与 detector 的函数边界**：确定从 `_observe()` 中抽取纯 OCR 获取，或让 `detect()` 接受已取得的首屏 observation；必须避免重试期间调用 `matching_keyword_rule()`。
3. **主循环恢复控制的最小写法**：确定如何从 `view_candidate()`/加载门向 `run()` 最小传递“已进入 `loaded`、请求进入 `load_recovering`、已进入 `load_failed`、被 ESC/计时停止”等控制结果，并在不建立状态机的前提下重置批次内位置，避免现有 `False` 返回落入正常 100 人刷新。
4. **`total_viewed` 增加动作的代码归属**：产品时点已冻结为首次 `loaded`；TID 只需决定由加载结果通知 `run()` 增加，还是由一个保证仅调用一次的相邻流程增加。
5. **最小停止原因存放位置**：确定使用 `run()` 局部短字符串还是现有风格的最小运行期变量，以区分 ESC、运行时间结束和 `load_failed`；不得新增统一退出码协议、Enum 或状态机。
6. **OCR 异常未知指标的内部表示**：语义已冻结为未知且日志不得写 0；TID 可在 `None` 与相邻代码风格的等效值中选择，并统一格式化为 `-` 或 `unavailable`。
7. **刷新动作的最小复用方式**：确定参数化 `refresh_page()` 的原因文案，还是抽取一个低层 F5 + 等待 helper，以复用现有流程且不复制筛选/首位点击序列。
8. **可选 `batch` 日志字段**：只有在一个简单整数即可提供且不需要重构主循环时才纳入；否则省略，不影响 R02 第一版验收。

## 30. 代码与设计原则

R02 后续实现必须遵守：

1. 新代码保持与目标模块及相邻代码一致的风格。
2. 优先复用现有函数。
3. 只做实现 R02 所需的最小结构调整。
4. 不引入不必要的类、dataclass、Enum、Protocol 或通用框架。
5. 不为未来需求提前建立接口层。
6. 不进行过度防御，只处理已确认或高概率异常。
7. 内部函数不重复校验上游已保证的数据。
8. 每个 Change 只实现自己的验收目标。
9. 发现非本轮问题时只记录，不直接修复。
10. 允许的最小重构仅限：抽取纯 OCR 获取；抽取/参数化现有 100 人刷新归位；增加最小测试参数注入；把新增阈值放入现有配置位置。
