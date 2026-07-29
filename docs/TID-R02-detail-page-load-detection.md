# BossOCR R02：详情页加载完成检测——Technical Implementation Document

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档类型 | TID（Technical Implementation Document） |
| 需求编号 | R02 |
| Change | Change 0B：技术实现设计 |
| 状态 | 待评审；不得据此自动开始 Change 1 |
| 编写日期 | 2026-07-28 |
| 当前分支 | `main` |
| 仓库基线 | `c36d6e7549e5098a4381861de40b271e718d5f20`（tag `v1.2`，与 `origin/main` 一致） |
| 上游产品文档 | `docs/RPD-R02-detail-page-load-detection.md` |
| RPD 版本 | Change 0A 已批准修订版，文档日期 2026-07-28；RPD 未设置独立语义版本号 |
| 正式实现与验收平台 | Windows 10/11 x64 + Microsoft Edge |
| TID 路径 | `docs/TID-R02-detail-page-load-detection.md` |

本 TID 只把已经批准的 RPD 映射为可实施的文件、函数、数据流、控制流和测试计划，不重新定义产品规则，不授权 Change 0B 修改业务代码、测试、配置、构建脚本或其他文档。

### 1.1 文档命名依据

仓库已有已跟踪的根目录 TID，例如：

- `docs/TID-Action-Mode-Favorite-Forward.md`
- `docs/TID-Windows-WindMouse-Observable-Motion.md`

因此使用 Change 0B 指定的回退路径 `docs/TID-R02-detail-page-load-detection.md`，不写入当前未跟踪的 `docs/tid/` 用户目录，也不修改其索引。

### 1.2 Change 0B 开始时的仓库状态

开始时 `git status --short --branch` 为：

```text
## main...origin/main
 M .gitignore
 M docs/Issue-Next-6-human-mouse-motion-acceptance-report.md
?? docs/project-review.zip
?? docs/project-review/
?? docs/tid/
?? venv-packages-before-reinstall.txt
```

以上均为 Change 0B 开始前已有的用户改动或未跟踪文件；本 Change 必须保护且不得修改。Change 0A 已生成 `docs/RPD-R02-detail-page-load-detection.md`，但仓库现有 `.gitignore:19:*.md` 会忽略它和本 TID，因此二者不会出现在普通 `git status` 或 `git diff --stat` 中。本 Change 不修改 `.gitignore`、不执行 `git add -f`、不暂存文件。

## 2. 实施范围与非目标

### 2.1 实施范围

后续 Change 1—Change 6 只为启用 OCR 关键词规则的候选人流程增加：

- `ocr_box_count`、`ocr_text_length` 提取与纯判定；
- 第一次正式 OCR 规则判断前的首屏加载门；
- 首次检测加最多 3 次原位置重试；
- 成功 OCR 直接作为正式首屏；
- 完整批次筛选区域可用时的一次连续页面级硬恢复；
- 恢复不可用或连续失败时的受控 `load_failed`；
- `total_viewed` 新统计时点、最小停止原因和结构化日志；
- 单元测试、主流程 mock 测试、Windows + Edge 人工冒烟和 Acceptance Report。

有关键词的 favorite、forward、forward + `--no-forward` 均纳入。无关键词纯浏览模式保持现有 OCR 初始化、校准、浏览、停留、随机滚动和构建 smoke 行为。

### 2.2 非目标

本 TID 不设计或实施：

- R01、R03—R13；
- 候选人身份、去重、姓名、正文锚点或加载占位页识别；
- 页面指纹、相似度、AI、JSON、数据库或精确进度恢复；
- 新 GUI、CLI 或配置系统；
- 新线程、异步框架、调度器、通用重试框架或统一退出码协议；
- macOS 正式候选人主流程、Chrome 移植或端到端验收；
- 无关重命名、格式化、类型补全、日志框架重做或架构清理。

## 3. 当前代码技术审计

### 3.1 当前调用链

关键词候选人的当前主链为：

```text
simple_brush.run()
→ total_viewed += 1
→ simple_brush.view_candidate(i)
→ simple_brush.detect_keywords()
→ OCRKeywordDetector.detect(forward_keywords)
→ OCRKeywordDetector._observe(scan_number, rules)
→ MSSScreenCapture.capture(region)
→ RapidOCRBackend.recognize(image)
→ searchable_text(items, min_confidence)
→ matching_keyword_rule(text, rules)
→ 可能二次确认或向下滚动至最多 8 屏
→ view_candidate() 分发 favorite/forward
→ 停留与 human_scroll_once()
→ next_candidate()
```

首位候选人由 `open_first_candidate_for_batch()` 打开；启用批次筛选时转入 `apply_batch_filter_and_open_first_candidate()`，否则使用 `legacy_point`。正常满 100 人后，`run()` 清零 `forward_consecutive`，调用 `refresh_page()`，下次外层循环再调用 `open_first_candidate_for_batch()`。

### 3.2 首屏 OCR 责任边界

| 责任 | 当前函数 | 结论 |
| --- | --- | --- |
| 截图 | `OCRKeywordDetector._observe()` → `ScreenCapture.capture()` | `_observe()` 直接执行，有屏幕读取副作用。 |
| OCR | `_observe()` → `OCRBackend.recognize()` | `_observe()` 直接执行，异常由外层 `detect()` 捕获。 |
| 置信度过滤 | `ocr_text.searchable_text()` | 使用 `item.confidence >= self.min_confidence`。 |
| 文本提取 | `searchable_text()` | 过滤、排序、拼接并 `normalize_text()`；返回的是规则搜索文本。 |
| 规则判断 | `_observe()` → `matching_keyword_rule()` | 与 OCR 获取耦合，不适合直接用于加载重试。 |
| 屏幕计数 | `OCRKeywordDetector.detect()` | `for scan_number in 1..max_scans`；确认扫描与首扫使用相同编号。 |
| OCR 滚动 | `detect()` → `self.scroll()` → `ocr_scroll_down()` | 第二屏前开始；加载重试不得进入。 |
| 收藏/转发 | `view_candidate()` | detector 不执行动作；命中后由主流程分发。 |
| 停留随机滚动 | `view_candidate()` → `human_scroll_once()` | 加载门失败必须在到达该位置前返回控制。 |
| 日志 | `detect()` 与 `detect_keywords()` | detector 记录扫描，主流程再次遍历 observations 记录中文日志；首屏复用不得再增加第三份重复日志。 |

结论：最小不可避免重构是把 `_observe()` 拆成“纯 OCR 采集”和“正式规则消费”。屏幕循环、滚动、二次确认和动作分发保持在现有层级，不迁移到新框架。

### 3.3 当前数据结构与指标缺口

- `RapidOCRBackend.recognize()` 返回 `Sequence[OCRItem]`；实际字段是 `OCRItem.text`、`OCRItem.confidence`、`OCRItem.box`。
- `ScanObservation.item_count` 当前等于过滤前的 `len(items)`，必须保留其现有含义，不能充当 `ocr_box_count`。
- `ScanObservation.text` 已经排序、拼接、NFKC、转小写并删除空白，不能充当简单 `ocr_text_length` 的输入。
- `ScanObservation` 没有保存 R02 两个加载指标；`detect()` 也没有接收已采集首屏的入口，因此成功加载结果目前无法直接复用。
- `DetectionResult` 已能承载正式 observations、成功、命中、屏数和错误；无需新增第二套正式扫描结果类型。

### 3.4 当前停止与清理

- ESC：`on_press()` 设置全局 `stop_event=True`，正常 ESC 会停止 keyboard listener；程序触发的 ESC 与校准 ESC 有现有隔离。
- 暂停：空格切换全局 `paused`。
- 固定等待：`safe_wait()` 每 0.2 秒检查停止并在暂停期间循环；`human_delay()` 复用它。
- OCR 等待：`ocr_wait()` 把 `safe_wait(False)` 转成 `OCRInterrupted`。
- 运行时间：`start_run_timer()` 使用既有 daemon `threading.Timer`，`request_timed_stop()` 设置同一个 `stop_event`。
- 清理：`run()` 的 `finally` 取消 timer 并记录累计人数；`__main__` 的 `finally` 停止 listener。

R02 不新增线程。同步的 MSS/RapidOCR 调用本身无法被 `stop_event` 抢占；实现只能在调用前和返回/抛错后立即检查停止，这是不引入异步执行的既有技术边界。

### 3.5 当前测试落点

- `tests/test_ocr_detector.py`：FakeCapture/FakeBackend、最多 8 屏、滚动、二次确认、低置信度、空结果、backend 错误和 RapidOCR 适配。
- `tests/test_ocr_text.py`：过滤、排序、标准化和规则表达式；R02 不改变这些规则语义。
- `tests/test_simple_brush_ocr.py`：`detect_keywords()`、favorite/forward/`--no-forward` 分发、焦点恢复、筛选归位、run 事件顺序、正常刷新、ESC/计时和全局状态保存恢复。
- 当前主流程测试主要使用 `patch.object()`、事件列表、`Mock` 和 `call`；R02 继续采用该风格。

## 4. RPD 与代码差异及最小对齐

未发现需要改写 RPD 的产品冲突；发现的是实现尚未具备 RPD 要求的能力：

| 差异 | 当前代码 | 最小对齐方案 |
| --- | --- | --- |
| 首屏采集与规则耦合 | `_observe()` 采集后立即匹配 | 在同一类内拆出 `capture_observation()` 与 `_match_observation()`；保留 `_observe()` 作为组合包装。 |
| 首屏不可复用 | observation 不持有加载指标，`detect()` 也不能消费预取首屏 | 向现有 `ScanObservation` 末尾只追加两个指标字段，并给 `detect()` 增加可选首屏入口；不保存 OCRItem 列表，不新增并行扫描对象。 |
| OCR 错误被折算 | `detect_keywords()` 把 detector 错误折算成普通 `False` | 加载门直接调用纯采集方法并在当前尝试边界捕获异常；正式扫描仍保持原 fail-closed 结果。 |
| 统计过早 | `run()` 在 `view_candidate()` 前无条件加 1 | 仅关键词路径改为 `loaded` 后加 1；无关键词路径保留当前时点。 |
| 刷新日志绑定 100 人 | `refresh_page()` 文案写死 | 给现有函数增加有默认值的原因参数；正常无参调用行为不变，硬恢复提供准确原因。 |
| 主循环失败或恢复后的控制不足 | 内层 `for` 失败且 `stop_event=False` 时可能落入正常刷新；硬恢复已打开首位后，外层循环还可能重复打开 | Change 2/3 的中间失败必须从 `run()` 的主 try 内受控 `return 0`；Change 4 硬恢复成功后同时设置既有 `first_candidate_opened=True` 和新增 `restart_current_batch=True`。 |
| 停止原因不可区分 | 只有 `stop_event` | 新增一个短字符串全局 `stop_reason`；不新增 Enum、状态机或退出码。 |
| OCR 校准返回值被忽略 | `run()` 调用 `ensure_ocr_region_calibrated()` 后不检查结果 | 关键词路径必须在 timer 前确认 detector 已就绪；失败沿现有受控启动返回停止，不进入候选人加载门。 |

OCR 初始化或区域校准失败发生在候选人加载检测开始前，不伪造成 4 次 `ocr_error`。最小方案是沿现有启动失败路径安全返回；真正进入加载门后的 capture/backend 异常才按 RPD 消耗检测预算。

## 5. 总体技术设计

### 5.1 设计原则

1. 新代码跟随 `simple_brush.py` 的局部函数、字符串常量、布尔和整数风格。
2. 复用现有 `ScanObservation`、`DetectionResult`、`safe_wait()`、`refresh_page()`、`apply_batch_filter_and_open_first_candidate()`、logging 和 unittest fake/mock。
3. 不新增 dataclass、Enum、Protocol、状态机、运行上下文对象或通用 retry helper。
4. 只在现有 `ScanObservation` 追加必要字段；保持前五个位置参数兼容现有测试。
5. 加载指标和判定是纯函数；屏幕采集只负责一次截图/OCR/文本准备，不执行规则、滚动或动作。
6. 正式 detector 消费已加载首屏，同一对象只匹配、计数、追加和记录一次。
7. R02 硬恢复只编排现有 F5、筛选、结果等待和首位点击，不复制坐标点击序列。
8. 内部函数信任上游已保证的结构，不重复做深层区域或规则校验。
9. 不为低概率竞态、OCR 卡死或未来平台提前建立线程、锁或超时框架。
10. 每个实施 Change 保持可验证；Change 2/3/4 的安全中间版本必须从 `run()` 的主 try 内受控 `return 0`，确保执行 finally，不得只返回普通 `False`、滚动、动作或误入正常刷新。

### 5.2 已冻结的技术选择

- 纯指标函数与加载判定放在 `ocr_detector.py`，因为输入是 `OCRItem` 且 detector 已拥有实际 `min_confidence`。
- 不修改 `ocr_text.py` 的规则搜索接口；采集层把已过滤 items 传给 `searchable_text()`，保持既有排序与标准化。
- `ScanObservation` 只追加 `ocr_box_count`、`ocr_text_length`，不保存原始或过滤后的 OCRItem 列表，也不新增 `LoadResult` dataclass。
- 加载门由 `run()` 在 `view_candidate()` 前调用；`view_candidate()` 继续负责规则、动作和停留。
- 加载门返回普通四元组 `(outcome, observation, retry_number, reason)`；`outcome` 是给 `run()` 的控制结果，不等同日志中的五个加载状态。Change 3 中间版本可返回 `retries_exhausted`；最终版本返回 `loaded`、`load_recovering` 或 `load_failed`。停止中断返回 `outcome=None`，由既有 `stop_event` 解释。
- `total_viewed` 仍是 `run()` 局部整数，由 `run()` 在收到 `loaded` 后增加。
- `consecutive_load_recovery_count` 是 `run()` 局部整数：Change 4 直接引入最终变量和一次上限，Change 5 只在同一变量上补齐 loaded 后清零。
- `stop_reason` 采用最小全局短字符串，以便 keyboard 回调、timer 回调和主循环共同设置。
- 不增加 `batch` 日志字段；现有代码没有批次变量，为可选字段改造主循环得不偿失。

## 6. 文件级修改清单

### 6.1 后续计划修改的现有文件

| 文件 | 修改目的 | 主要函数/结构 |
| --- | --- | --- |
| `ocr_detector.py` | 指标、纯判定、一次 OCR 采集、首屏 observation 复用 | `ScanObservation`、`OCRKeywordDetector._observe()`、`OCRKeywordDetector.detect()`；新增纯 helper、`capture_observation()`、`_match_observation()` |
| `simple_brush.py` | 配置、加载门、重试、计数、恢复、停止原因和日志接入 | 常量区、运行时状态、`on_press()`、`request_timed_stop()`、`detect_keywords()`、`view_candidate()`、`refresh_page()`、`run()`；新增 R02 局部 helper |
| `tests/test_ocr_detector.py` | 指标边界、纯采集、预取首屏复用、8 屏与确认回归 | 复用/扩展 `FakeCapture`、`FakeBackend`、`DetectorTests` |
| `tests/test_simple_brush_ocr.py` | 门禁、重试、禁止动作、恢复、计数、停止、模式和刷新回归 | 扩展 `SimpleBrushOCRTests` 及其全局状态保存集合 |

`ocr_text.py`、`ocr_calibration.py`、`mouse_motion.py`、`calibration_profiles.py`、`build-windows.bat` 和 `BossOCR.spec` 不计划修改。它们只作为公共回归边界。

### 6.2 后续计划新增的文件

| 文件 | Change | 用途 |
| --- | --- | --- |
| `docs/R02-detail-page-load-detection-acceptance-report.md` | Change 6 | 记录自动化结果、Windows + Edge 冒烟、已知风险和最终验收。 |

不新增生产模块或独立测试文件。Change 0B 实际只新增本 TID。

## 7. 配置项与实际放置位置

全部放在 `simple_brush.py` 现有 `# OCR 关键词检测` 常量区，使用仓库的 `UPPER_SNAKE_CASE` 风格：

| RPD 逻辑配置 | 代码常量 | 默认值 | 处理 |
| --- | --- | ---: | --- |
| `ocr_box_count_threshold` | `OCR_BOX_COUNT_THRESHOLD` | `5` | 新增。 |
| `ocr_text_length_threshold` | `OCR_TEXT_LENGTH_THRESHOLD` | `30` | 新增。 |
| 首次详情等待时间 | `CLICK_WAIT_SECONDS` | `2` 秒 | 复用；首位打开后已有等待，不新增第二份。 |
| 下一候选人切换等待 | `next_candidate()` 现有 `0.5` 秒 | `0.5` 秒 | R02 保持原值和位置，不借机配置化。 |
| 加载重试等待 | `LOAD_RETRY_WAIT_SECONDS` | `1.5` 秒 | 新增；每次重试前固定使用。 |
| `max_load_retries` | `MAX_LOAD_RETRIES` | `3` | 新增；不含首次检测。 |
| 页面硬恢复等待 | `REFRESH_WAIT_SECONDS` | `5` 秒 | 复用；F5 后等待不新增同义常量。 |
| 筛选步骤等待 | `FILTER_*_DELAY_*` | 现有值 | 复用 `apply_batch_filter_and_open_first_candidate()`。 |
| `max_consecutive_load_recoveries` | `MAX_CONSECUTIVE_LOAD_RECOVERIES` | `1` | 新增。 |

不新增 CLI、GUI、JSON、环境变量或配置文件。数字 5、30、3、1、1.5 不散落到流程逻辑和测试外的实现代码中。

## 8. OCR 数据结构与指标设计

### 8.1 置信度过滤 helper

在 `ocr_detector.py` 增加模块级纯函数：

```python
def accepted_ocr_items(items, min_confidence):
    return [
        item for item in items
        if item.confidence >= min_confidence
    ]
```

它是本次 OCR 采集唯一使用业务阈值的位置。`searchable_text()` 接收已经过滤的列表并使用默认 `min_confidence=0.0`，继续完成既有排序、拼接和规则文本标准化；不建立第二个阈值。

### 8.2 指标 helper

在同一模块增加：

```python
def calculate_load_metrics(accepted_items):
    accepted_items = list(accepted_items)
    return (
        len(accepted_items),
        sum(
            len(item.text.strip())
            for item in accepted_items
            if item.text.strip()
        ),
    )
```

调用者保证输入已经过相同置信度过滤；helper 不重复校验 confidence。空文本框仍计入 `ocr_box_count`，但 `strip()` 后为空的文本不贡献 `ocr_text_length`。字段使用实际的 `OCRItem.text`。

### 8.3 纯加载判定

在 `ocr_detector.py` 增加：

```python
def evaluate_detail_page_load(
    ocr_box_count,
    ocr_text_length,
    box_count_threshold,
    text_length_threshold,
):
    if ocr_box_count == 0:
        return False, "zero_ocr_boxes"
    if (
        ocr_box_count <= box_count_threshold
        and ocr_text_length < text_length_threshold
    ):
        return False, "low_box_count_and_short_text"
    return True, "threshold_passed"
```

函数只接受成功 OCR 后的整数指标。OCR 异常不调用本函数，由加载门记录 `reason=ocr_error` 和未知指标。

### 8.4 `ScanObservation` 最小扩展

在现有字段末尾追加：

```python
ocr_box_count: Optional[int] = None
ocr_text_length: Optional[int] = None
```

约束：

- 保留 `item_count=len(raw_items)` 的现有含义。
- 保留 `text` 为规则搜索文本的现有含义。
- 成功 `capture_observation()` 必须把两个新增字段填为真实整数。
- capture/backend 异常不创建伪 observation；加载门使用 `observation=None` 和两个 `None` 指标。
- 字段追加在末尾，避免破坏当前测试对 `ScanObservation(...)` 的位置参数构造。
- 原始 `raw_items` 和过滤后的 `accepted_items` 只存在于 `capture_observation()` 局部作用域，不写入 observation；构造完成后由 Python 正常释放局部引用。

## 9. 纯 OCR 采集与正式首屏消费

### 9.1 `capture_observation()`

在 `OCRKeywordDetector` 增加公开方法 `capture_observation(scan_number)`：

```text
开始计时
→ self.capture.capture(self.region)
→ list(self.backend.recognize(image)) 得到 raw_items
→ accepted_ocr_items(raw_items, self.min_confidence)
→ searchable_text(accepted_items) 得到既有规则搜索文本
→ calculate_load_metrics(accepted_items)
→ 构建只含 text、过滤前 item_count、两个加载指标及既有字段的 ScanObservation
→ 返回未做规则匹配的 ScanObservation
```

首屏复用的是已经生成的 `ScanObservation`。后续规则判断只读取 `observation.text`，加载判断和日志只读取两个指标；不需要再次截图、OCR 或访问临时 OCRItem 列表。

此方法不得：

- 调用 `matching_keyword_rule()`；
- 增加正式扫描屏数；
- 调用 scroll/wait；
- 执行二次确认；
- 触发收藏、转发、焦点恢复或候选人切换；
- 捕获并折算 OCR 异常。

异常原样交给调用边界：加载门负责消耗一次预算；正式 detector 仍由 `detect()` 的现有 try/except 转成 `DetectionResult(success=False)`。

### 9.2 `_match_observation()` 与 `_observe()`

新增私有 `_match_observation(observation, rules)`，只调用一次 `matching_keyword_rule(observation.text, rules)`，并在同一个可变 `ScanObservation` 上填写 `matched_rule`、`matched_keyword` 后返回它。

现有 `_observe(scan_number, rules)` 保留为兼容包装：

```text
capture_observation(scan_number)
→ _match_observation(observation, rules)
```

这样后续正式第 2—8 屏和二次确认仍走原有入口，改动集中在首屏复用点。

### 9.3 `detect(..., first_observation=None)`

给现有 `OCRKeywordDetector.detect()` 增加可选关键字参数 `first_observation=None`：

- 未传入时，所有行为和现有调用一致。
- 传入时，正式 `scan_number=1` 不截图、不 OCR，只调用 `_match_observation(first_observation, rules)`。
- 该对象只 append 到 `DetectionResult.observations` 一次，正式屏数只计一次，规则只判断一次。
- 首屏命中后，仍等待 `confirmation_seconds` 并独立 `_observe()` 二次确认。
- 首屏未命中后，从 `scan_number=2` 起才滚动并继续原有最多 8 屏。
- 预取首屏已由加载门写结构化判断日志；`detect()` 和 `detect_keywords()` 对该同一对象跳过重复首屏扫描日志。后续屏和二次确认保留现有日志。

这一个可选参数同时保证不重复截图、OCR、规则判断、屏数、observation、首屏日志或动作。

### 9.4 主流程传递

`detect_keywords(first_observation=None)` 把参数传给 `ocr_detector.detect(..., first_observation=first_observation)`；`view_candidate(index_in_batch, first_observation=None)` 再把它传给 `detect_keywords()`。两者保持原有布尔命中/完成返回语义，不承担重试或硬恢复。

## 10. 修改后的函数级调用链

### 10.1 有关键词路径

```text
run()
→ 现有首位打开或 next_candidate() 等待
→ run_detail_load_gate(...)
   → 首次：ocr_detector.capture_observation(1)
   → 指标 + evaluate_detail_page_load()
   → 失败时 safe_wait(1.5) 后重试，最多 3 次
→ loaded
→ total_viewed += 1
→ 记录一次 loaded 判断日志
→ 若 recovery_count > 0，记录 detail_load_recovery_confirmed
→ Change 5 将 consecutive_load_recovery_count = 0
→ view_candidate(i, first_observation)
→ detect_keywords(first_observation)
→ ocr_detector.detect(rules, first_observation=...)
→ 正式消费首屏；必要时二次确认或滚动到第 2—8 屏
→ favorite/forward/--no-forward 分发
→ 停留与随机滚动
→ next_candidate()
```

### 10.2 四次失败路径

```text
run_detail_load_gate()
→ 4 次均为 threshold failure 或 ocr_error
→ run() 确认完整恢复条件和连续额度可用
→ consecutive_load_recovery_count += 1
→ recover_detail_page()
   → refresh_page(reason=...)
   → apply_batch_filter_and_open_first_candidate()
   → 记录 detail_load_recovery_reopen_completed
→ first_candidate_opened=True
→ restart_current_batch=True
→ break 当前内层 for
→ 检查 stop_event
→ 检查 restart_current_batch
→ 跳过正常 100 人刷新
→ continue 外层 while
→ 因 first_candidate_opened=True，不调用 open_first_candidate_for_batch()
→ first_candidate_opened=False
→ 新 for 从 i=0 重新加载检测
```

`recover_detail_page()` 负责完成 F5、筛选和首位候选人打开；`run()` 负责设置 `first_candidate_opened=True`。`restart_current_batch` 只负责跳过正常刷新并重启内层 for。两个变量职责不同，必须同时存在，并复用现有 `first_candidate_opened`，不新增同义标志。

Change 5 完成后的最终不可恢复路径为：

```text
run_detail_load_gate() 返回 load_failed
→ request_load_failed_stop(...)
→ stop_event=True，stop_reason="load_failed"
→ 不进入 view_candidate()/next_candidate()/正常 refresh
→ run() finally
→ __main__ finally
→ 保持现有返回码语义
```

Change 2/3/4 尚未具备最终停止语义时，不提前进入上述 `load_failed` 分支：Change 2 首次失败、Change 3 `retries_exhausted`、Change 4 恢复不可用/步骤失败/连续额度已用尽，都在记录各自最小日志后从 `run()` 主 try 内直接 `return 0`，由 Python 保证先执行 `run()` 的 finally；不得只让 `view_candidate()` 返回 `False`。

### 10.3 无关键词路径

```text
run()
→ 保持当前 total_viewed += 1
→ view_candidate(i) 但不调用 detect_keywords()
→ 停留与随机滚动
→ next_candidate()/正常 100 人刷新
```

无关键词路径不调用 R02 helper，不初始化或校准 OCR，也不受 R02 指标、重试、恢复或统计新时点影响。

## 11. 加载门与重试循环

### 11.1 helper 契约

在 `simple_brush.py` 增加：

```python
run_detail_load_gate(
    candidate_in_batch,
    total_viewed,
    recovery_count,
    recovery_available,
)
```

返回普通四元组：

```text
(outcome, observation, retry_number, reason)
```

- `outcome="loaded"`：`observation` 是成功首屏。
- Change 2 的一次门禁失败返回 `outcome="initial_check_failed"`，`reason` 保留 `not_loaded` 的具体阈值原因或 `ocr_error`；它是中间控制结果，不是加载状态。
- Change 3 四次耗尽返回 `outcome="retries_exhausted"`；它是中间控制结果，不是加载状态。
- Change 4 接入恢复后，完整条件和额度可用时返回 `outcome="load_recovering"`；不可恢复的中间分支仍由 run 受控返回，不提前设置最终停止原因。
- Change 5 完成后，不可恢复结果统一为 `outcome="load_failed"`。
- `outcome=None`：ESC 或运行时间结束已设置 `stop_event`；这只是既有停止控制结果，不是加载状态。
- `loading` 和 `load_retrying` 是循环内当前状态及日志标签，不需要跨函数持久化。

日志中的 `state` 始终只使用 RPD 五个名称；`initial_check_failed`、`retries_exhausted` 只存在于对应中间 Change 的内部控制流和最小日志 reason/outcome，不成为最终产品状态。

### 11.2 精确循环

```text
for retry_number in range(MAX_LOAD_RETRIES + 1):
    state = loading if retry_number == 0 else load_retrying

    if retry_number > 0:
        safe_wait(LOAD_RETRY_WAIT_SECONDS)

    停止检查
    capture_observation(scan_number=1)
    停止检查

    成功 OCR：evaluate_detail_page_load(...)
    OCR 异常：reason=ocr_error，指标=None

    未通过且仍有预算：记录判断，next_action=wait_and_retry
    通过：返回 loaded + observation
    最后一次失败：Change 3 返回 retries_exhausted；Change 4/5 再接入恢复判断
```

首次检测前没有 R02 等待。三次重试各且仅各调用一次 `safe_wait(1.5)`。`safe_wait(False)` 立即返回 `outcome=None`，不开始下一次截图。

### 11.3 OCR 异常

对 `capture_observation()` 的单次 `Exception`：

- 当前机会已经开始并被消耗；
- `observation=None`；
- `ocr_box_count=None`、`ocr_text_length=None`；
- `decision=error`、`reason=ocr_error`；
- 日志格式化为 `-` 或 `unavailable`；
- 不调用加载纯判定、matcher、scroll、动作或 next；
- 尚有预算时进入同一个 1.5 秒等待；无单独异常预算。

不得把 OCR 成功返回空列表与异常混淆：空列表得到 `ocr_box_count=0`、`ocr_text_length=0`、`reason=zero_ocr_boxes`。

### 11.4 成功日志与 `total_viewed` 原子顺序

失败和错误尝试由加载门立即记录，因为 `total_viewed` 不变。成功尝试返回 `run()` 后按以下连续顺序处理：

1. `total_viewed += 1`；
2. 记录本次 `state=loaded`、`decision=ready`、`next_action=reuse_first_scan`，日志中的 `total_viewed` 使用已增加值；
3. 若 `consecutive_load_recovery_count > 0`，Change 5 记录 `detail_load_recovery_confirmed`，表示硬恢复后至少一名候选人真正通过加载门；
4. 只有记录 `detail_load_recovery_confirmed` 后，Change 5 才执行 `consecutive_load_recovery_count = 0`；
5. 调用 `view_candidate(..., first_observation=observation)`。

Change 4 中间版本尚未实现步骤 3—4，loaded 后计数暂时保持 1；这保证 Change 4 不提前实施 Change 5。最终顺序中没有 GUI 动作或可能重复增加计数的分支。

## 12. 主循环接入与中间状态安全

### 12.1 `run()` 最小控制改动

保留现有外层 `while` 和内层 `for`，新增局部：

```text
consecutive_load_recovery_count = 0
restart_current_batch = False  # 每个外层 while 开始时重置
```

内层每名候选人：

- 若 `forward_enabled and forward_keywords`，先运行加载门；只有 `loaded` 才增加 `total_viewed` 并调用 `view_candidate()`。
- 否则保持当前先增加 `total_viewed` 再调用 `view_candidate()` 的无关键词路径。
- `load_recovering` 在 run 层执行硬恢复；成功后依次设置 `first_candidate_opened=True`、`restart_current_batch=True` 并 break 当前 for。
- `load_failed` 设置停止原因与 stop_event 后 break。
- for 后先检查 `stop_event`，再检查 `restart_current_batch`；后者为真时直接 continue 外层 while，绝不能落入正常满 100 人刷新。

`first_candidate_opened` 与 `restart_current_batch` 不可合并：前者告诉下一轮 while“首位已经由恢复函数打开，不要再次点击”；后者告诉当前轮 for 之后“跳过正常刷新并从新的 for 开始”。

### 12.2 各 Change 的安全落地顺序

- **Change 2**：只有一次检测。首次 `not_loaded` 或 `ocr_error` 时记录最小 fail-closed 日志，不调用 `view_candidate()`/规则/滚动/动作/next，不再次打开首位，不进入正常刷新；从 `run()` 主 try 内直接 `return 0`，finally 取消 timer 并输出当前统计。不设置临时 `load_failed`、不改变 `stop_event`、不抛异常。
- **Change 3**：加入完整四次预算。耗尽时加载门返回 `retries_exhausted`；run 记录最小耗尽日志，不调用 `view_candidate()`、next、正常刷新或恢复，并从主 try 内直接 `return 0`，确保 finally。不设置最终停止原因、不新增临时恢复、不抛异常。
- **Change 4**：直接新增最终变量 `consecutive_load_recovery_count=0`，不使用临时布尔锁。首次完整失败且恢复可用时增至 1 并恢复；恢复后暂不清零。再次连续耗尽、恢复不可用或恢复步骤失败时不再 F5，记录最小日志并从 run 受控 `return 0`；尚不设置 `stop_reason` 或完整 `detail_load_failed` ERROR。
- **Change 5**：不重写计数结构，只在同一变量上增加 `detail_load_recovery_confirmed` 后清零，并补齐 `stop_reason`、最终 `load_failed`、ERROR 日志和 ESC/timer 区分。

不得用 feature flag、临时 CLI 或未测试的 fallback 隐藏中间行为。

## 13. 页面级硬恢复与 100 人流程复用

### 13.1 现有可复用能力

现有代码已经分别封装：

- `refresh_page()`：F5 + `REFRESH_WAIT_SECONDS`；
- `apply_batch_filter_and_open_first_candidate()`：打开筛选、最近没看过、确定、结果等待、首位点击、`CLICK_WAIT_SECONDS`；
- `open_first_candidate_for_batch()`：正常批次在自动/legacy 之间分发。

因此不再抽取大型“批次管理器”。必要改动只有：

1. 将 `refresh_page()` 改为接受带默认值的 `reason` 参数；无参时继续输出正常 100 人文案。
2. 新增小型 `recover_detail_page()`，顺序调用 `refresh_page(reason=...)` 和 `apply_batch_filter_and_open_first_candidate()`。
3. `recover_detail_page()` 不接受 `legacy_point`，避免错误 fallback。

### 13.2 恢复可用条件

调用加载门前由 `run()` 计算：

```text
recovery_available = (
    batch_filter_enabled
    and batch_filter_regions is not None
)
```

`BatchFilterRegions` 是完整四字段 dataclass，正常校准/模板加载已经保证结构；R02 不重复逐字段校验。`--no-batch-filter` 会令 `batch_filter_enabled=False`。

四次失败且不可用时不得调用 `refresh_page()`、`open_first_candidate_for_batch(legacy_point)` 或任何点击。Change 4 中间版本记录 `reason=hard_recovery_unavailable` 后由 run 受控 `return 0`；Change 5 才把同一分支统一映射为 `load_failed` 并设置最终停止原因。

最终判断顺序固定为：先检查 `recovery_available`；不可用时使用 `hard_recovery_unavailable`。只有完整恢复条件可用但 `recovery_count >= MAX_CONSECUTIVE_LOAD_RECOVERIES` 时，才使用 `max_consecutive_load_recoveries_reached`。不得因计数检查遮蔽恢复区域缺失。

### 13.3 `recover_detail_page()` 契约

返回 `(success, reason)`：

- `(True, "reopen_completed")`：F5、等待、筛选和首位打开全部成功；只表示导航归位完成，尚未证明详情正文恢复。
- `(False, "refresh_failed")` 或 `(False, "batch_reopen_failed")`：非停止故障。Change 4 中间版本由 run 受控 `return 0`；Change 5 才进入最终 `load_failed`。
- `(None, "stopped")`：步骤因 ESC/计时设置 stop_event 而中断，不改记 `load_failed`。

helper 在 R02 恢复边界捕获 F5 或调用编排的异常并返回失败，避免未捕获异常；筛选函数内部现有异常处理继续保留，不重复记录完整堆栈。

`recover_detail_page()` 的最后一步是 `apply_batch_filter_and_open_first_candidate()` 完成首位点击和现有等待，然后记录 `detail_load_recovery_reopen_completed`。此事件只表示即将重新进入 R02；恢复计数保持 1。helper 返回后由 `run()` 设置 `first_candidate_opened=True` 和 `restart_current_batch=True`，避免外层循环再次打开首位。

### 13.4 正常 100 人刷新不变证明

正常路径仍执行：

```text
forward_consecutive = 0
→ refresh_page()  # 无参数，默认原文案与 5 秒等待
→ 下一外层循环 open_first_candidate_for_batch(legacy_point)
```

不会改成硬恢复 helper，也不会改变 legacy 重开、自动筛选重开、事件顺序或累计日志位置。现有四个 run 刷新测试保留，并增加断言 `refresh_page()` 的无参调用仍成立。

## 14. 状态与计数生命周期

### 14.1 五个加载状态的代码表现

| 状态 | 代码表现 | 生命周期 |
| --- | --- | --- |
| `loading` | 加载门首次循环的局部字符串与日志标签 | 首次尝试期间。 |
| `load_retrying` | retry 1—3 的局部字符串与日志标签 | 对应等待和当前重试。 |
| `loaded` | 加载门成功返回值与成功日志 | 被 `run()` 消费一次后不持久化。 |
| `load_recovering` | 四次耗尽后的返回值、恢复日志 | run 执行硬恢复期间。 |
| `load_failed` | 最终返回值、`stop_reason` 和 ERROR 日志 | 直到 finally 清理完成。 |

不新增 Enum 或状态对象。`reuse_first_scan`、`wait_and_retry`、`hard_refresh`、`safe_stop` 只写入 `next_action`。

### 14.2 生命周期表

| 数据 | 候选人切换后 | 硬恢复后 | 任一候选人 `loaded` 后 | 整场运行 |
| --- | --- | --- | --- | --- |
| `retry_number` | 新候选人从 0 开始 | 新首位从 0 开始 | 当前门结束 | 不保留 |
| 当前加载状态 | 新候选人 `loading` | 新首位 `loading` | 转为 `loaded` 后消费 | 不做全局状态 |
| `consecutive_load_recovery_count` | 保留 | Change 4 已增加为 1 并保留 | Change 4 暂不清零；Change 5 记录 `detail_load_recovery_confirmed` 后清零 | Change 4 起一直使用同一个 run 局部整数 |
| `i` / `candidate_in_batch` | 正常加 1 | `restart_current_batch` 令新 for 从 0 开始 | 不额外改变 | 每个 100 人批次局部 |
| `first_candidate_opened` | 正常切换不使用 | run 在恢复完成后设为 True；下一轮 while 跳过重复打开后立即设回 False | 不额外改变 | 复用现有局部标志 |
| `restart_current_batch` | 每轮 while 开始为 False | 恢复完成后设 True；for 后优先 continue，跳过正常刷新 | 下一轮 while 重置 False | R02 新增局部控制标志 |
| `total_viewed` | 只在 loaded 后增加 | 不增加、不清零 | 增加一次 | run 局部累计 |
| `forward_consecutive` | 保持现有动作语义 | 保留 | 由现有规则/动作语义处理 | 仅正常满 100 人刷新清零 |
| `run_timer` | 保留 | 保留，不重启 | 保留 | finally 取消 |
| OCR/backend/region | 保留 | 保留，不校准 | 保留 | 每次运行一套 |
| 模式、规则、邮箱 | 保留 | 保留 | 保留 | 每次运行配置 |
| `stop_reason` | 通常为 `None` | 保留 | 保留 | run 开始重置，最终日志读取 |

## 15. 最终失败与停止原因

### 15.1 最小 `stop_reason`

在 `simple_brush.py` 运行时状态区增加：

```python
stop_reason = None
```

并在现有入口最小赋值：

- `on_press()`：首次正常 ESC 设置 `"esc"`，再设置 `stop_event=True`。
- `request_timed_stop()`：设置 `"run_duration_elapsed"`，再设置 `stop_event=True`。
- `request_load_failed_stop()`：设置 `"load_failed"`，再设置 `stop_event=True`。
- `run()` 开始与 `stop_event` 一起重置。

不引入锁或通用 stop manager；各入口只在原因尚未设置时写入，保持“第一个实际停止原因”语义。

### 15.2 `request_load_failed_stop()`

新增 R02 专用小 helper，参数只包含日志所需定位字段和最终 reason。它必须：

1. 记录一条 `logger.error()`，`state=load_failed`、`next_action=safe_stop`；
2. 设置 `stop_reason="load_failed"`；
3. 设置 `stop_event=True`；
4. 不抛异常、不调用 GUI、不修改统计和 `forward_consecutive`。

触发原因至少包括：

- `hard_recovery_unavailable`；
- `max_consecutive_load_recoveries_reached`；
- `refresh_failed`；
- `batch_reopen_failed`。

### 15.3 清理与退出码

最终失败只让 run 循环自然退出并进入现有 `finally`。`run()` 仍返回 `0`，`__main__` 仍走现有 listener 清理；不抛未捕获异常，不新增 `sys.exit(nonzero)`。最终停止日志增加 `stop_reason`，避免把 `load_failed` 误写成 ESC。

## 16. 日志设计

### 16.1 事件

| 事件 | 等级 | 说明 |
| --- | --- | --- |
| `detail_load_check` | INFO；`ocr_error` 可 WARNING | 每次首次/重试判断恰好一条。 |
| `detail_load_recovery_start` | WARNING | 四次耗尽且开始硬恢复。 |
| `detail_load_recovery_step` | INFO/ERROR | F5、等待、筛选首位的开始与结果；复用函数既有日志，不重复完整 OCR 文本。 |
| `detail_load_recovery_reopen_completed` | INFO | F5、筛选和首位点击已完成，即将重新进入 R02；不代表详情已加载，不清零恢复计数。 |
| `detail_load_recovery_confirmed` | INFO | 硬恢复后的新首位或后续任一候选人真正进入 `loaded`；记录后才清零恢复计数。 |
| `detail_load_failed` | ERROR | 最终故障，下一步 `safe_stop`。 |

最终恢复日志时序固定为：

```text
detail_load_recovery_start
→ refresh/filter/reopen step logs
→ detail_load_recovery_reopen_completed
→ 新候选人 loading / load_retrying
→ loaded
→ detail_load_recovery_confirmed
→ consecutive_load_recovery_count = 0
```

若重新打开后再次完整失败，则从 `detail_load_recovery_reopen_completed` 进入加载尝试和最终 `detail_load_failed`，不得记录 `detail_load_recovery_confirmed`。全文不使用“首位打开即加载恢复成功”的事件。

### 16.2 固定字段

每次判断：

```text
event
candidate_in_batch
total_viewed
attempt
retry_number
ocr_box_count
ocr_text_length
decision
reason
state
recovery_count
next_action
```

时间戳由现有 formatter 提供。`candidate_in_batch` 为 1 基；`attempt` 为 `initial` 或 `retry`；未知指标输出 `-`。不记录完整 OCR 文本、姓名、JSON 或数据库。

最终决定不实现可选 `batch` 字段：当前没有批次变量，而时间戳、`candidate_in_batch`、`total_viewed`、`recovery_count`、`retry_number` 已满足 RPD 故障定位要求。

### 16.3 避免首屏重复日志

- 加载失败/错误：只记录加载判断，不进入正式 scan log。
- 加载成功：加载门的成功记录是该首屏唯一新增结构化判断日志。
- 正式 detector 消费同一个 prefetched observation 时跳过原有首屏扫描日志；`detect_keywords()` 遍历结果时也跳过对象身份相同的 prefetched observation。
- 第 2—8 屏和二次确认继续使用现有日志。

## 17. 模式、平台和稳定流程影响

### 17.1 收藏与转发

- `forward_enabled` 是历史变量名，当前实际含义是“关键词规则已启用”。收藏模式有关键词时同样为 `True`，因此 `forward_enabled and forward_keywords` 同时覆盖有关键词的 favorite、forward 和 forward + `--no-forward`，不得将其误解为仅转发模式，也不得为 R02 顺手改名。
- favorite：加载成功后才可能调用 `perform_favorite_action()`。
- forward：加载成功、规则命中且二次确认后才可能调用 `forward_one_candidate()`。
- forward + `--no-forward`：完整执行加载和规则检测，但继续禁止真实转发。
- 加载失败不重置 `forward_consecutive`；正常规则未命中仍保持现有清零语义。
- R02 不修改 favorite/forward 函数内部、点击区域或焦点恢复 finally。

### 17.2 无关键词模式

必须用 run 测试证明：

- 不调用 `initialize_ocr()`、`ensure_ocr_region_calibrated()` 或加载门；
- 不受硬恢复条件限制；
- `--no-batch-filter` legacy 浏览仍按现有正常 100 人刷新复用 `legacy_point`；
- 构建 smoke 的无关键词路径不变。

### 17.3 Windows 与 macOS

- 正式实现和真实候选人验收只在 Windows 10/11 x64 + Microsoft Edge。
- `simple_brush.py` 仍直接依赖 win32/Edge，不为 R02 添加伪跨平台抽象。
- `tests/test_ocr_detector.py`、`tests/test_ocr_text.py` 等不依赖正式 Windows 候选人主循环的公共 OCR 单元测试继续回归；若 macOS 环境可运行这些纯测试，可作为附加证据。
- 不要求 macOS 候选人流程、Chrome、真实页面或端到端测试。

### 17.4 ESC、计时和暂停

- 首次检测前只使用首位 `CLICK_WAIT_SECONDS` 或下一位现有 0.5 秒等待；两者已复用 `safe_wait()`。
- 每次重试只使用 `safe_wait(LOAD_RETRY_WAIT_SECONDS)`。
- F5 用 `safe_wait(REFRESH_WAIT_SECONDS)`；筛选等待经 `human_delay()` → `safe_wait()`。
- ESC、timer 或 pause 不新增第二套检查机制。
- 同步 capture/OCR 返回后必须再次检查 `stop_event`，避免停止请求后进入规则或动作。

## 18. 重复处理风险

### 18.1 当前事实

- 页面刷新并重新设置“最近没看过”依赖 BOSS 当前 UI 和服务端结果，仓库没有候选人身份、已处理集合或持久化进度。
- `total_viewed` 只是数量，不代表候选人标识。
- `forward_consecutive` 只限制连续转发次数，不去重。
- 当前没有代码能证明刷新后的首位一定未在本次运行出现过。

### 18.2 风险

- 已查看候选人可能因筛选结果延迟、列表更新或页面状态再次出现。
- favorite 再次点击可能重复操作，甚至取决于页面按钮语义改变收藏状态。
- forward 可能对同一候选人重复发送邮件。

### 18.3 R02 最小安全边界

- 只有当前候选人四次加载均失败才硬恢复；该失败候选人尚未进入规则或动作。
- 硬恢复后仍必须先通过加载门和现有规则二次确认。
- 连续恢复上限为 1，避免故障状态无限刷新。
- 真实冒烟优先使用 `--no-forward`，收藏/真实转发只做受控小样本。

这些措施不能实现身份去重。彻底解决需后续候选人身份/切换/页面指纹或持久化需求，明确不在 R02 中扩展。

## 19. 测试矩阵

### 19.1 判定与指标纯测试

在 `tests/test_ocr_detector.py`：

| 场景 | 预期 |
| --- | --- |
| 0 框、0 字 | 未加载，`zero_ocr_boxes`。 |
| 5 框、29 字 | 未加载，`low_box_count_and_short_text`。 |
| 5 框、30 字 | 加载完成。 |
| 6 框、10 字 | 加载完成。 |
| 2 框、100 字 | 加载完成。 |
| 低于 confidence | 不计入框数和长度。 |
| 等于 confidence | 计入。 |
| 有效空文本框 | 计框、不计长度。 |
| 前后空格 | 每框 `strip()` 后计长度。 |
| 原始 10 框、有效 3 框 | `item_count=10`、`ocr_box_count=3`。 |
| OCR 异常 | 不构造 0 指标 observation。 |

### 19.2 首屏拆分和复用

- `capture_observation()` 调用 capture/backend 各一次，不调用 matcher、scroll 或 wait。
- observation 只包含既有字段、`ocr_box_count` 和 `ocr_text_length`；断言 dataclass 字段中没有 `ocr_items`、`raw_items`、`accepted_items` 或 evidence 字段。
- `detect(first_observation=...)` 不再次 capture/recognize。
- 正式规则判断只读取 `observation.text`，不依赖 OCRItem 列表。
- 首屏规则只匹配一次、observation 只 append 一次、`scans_completed` 只计一次。
- 首屏命中仍额外二次确认一次。
- 首屏未命中后总正式屏数最多 8，scroll 最多 7 次。
- prefetched 首屏不重复写正式扫描日志。

### 19.3 加载流程

在 `tests/test_simple_brush_ocr.py` 使用 fake observation 序列：

- 首次成功：1 次 OCR、0 次 1.5 秒等待。
- 重试 1 成功：2 次 OCR、1 次 1.5 秒等待。
- 重试 2 成功：3 次 OCR、2 次等待。
- 重试 3 成功：4 次 OCR、3 次等待。
- 四次全失败：没有第 5 次 OCR。
- 阈值失败与 `ocr_error` 混合：共享同一 4 次预算。
- 每次使用相同 `ocr_detector.region`。
- 任意成功 observation 只消费一次。
- **Change 2 中间版本**：单次 `not_loaded`/`ocr_error` 后 `run()` 返回 0；timer 的 `cancel()` 和最终统计日志证明 finally 已执行；不调用 `view_candidate()`、`next_candidate()`、`refresh_page()`；`open_first_candidate_for_batch()` 除启动时既有的一次外不再调用；`stop_event` 和最终 `stop_reason` 不被临时改写。
- **Change 3 中间版本**：四次耗尽返回 `retries_exhausted`，`run()` 返回 0 且 finally 执行；不调用 `view_candidate()`、`next_candidate()`、`refresh_page()`、正常 100 人刷新或任何恢复；不设置最终 `load_failed` 停止原因。

### 19.4 禁止行为

在首次失败至成功/恢复/停止之间断言未调用：

- `matching_keyword_rule()`；
- `ocr_scroll_down()`、`human_scroll_once()`；
- `perform_favorite_action()`、`forward_one_candidate()`；
- 收藏/转发焦点恢复；
- `next_candidate()`；
- 正常 `refresh_page()`；
- 正式 detector 屏数追加。

### 19.5 恢复与计数

- 四次失败后可用路径事件顺序：F5 → 5 秒等待 → 打开筛选 → 最近没看过 → 确定 → 结果等待 → 首位点击。
- 硬恢复中的 `apply_batch_filter_and_open_first_candidate()` 只调用一次；run 随后设置 `first_candidate_opened=True`，下一轮 while 不再次调用 `open_first_candidate_for_batch()`，首位不重复点击。
- `restart_current_batch=True` 时跳过正常 `refresh_page()`，新 for 从 `i=0` / `candidate_in_batch=1` 开始，并对已打开首位立即执行 R02。
- 正常满 100 人路径仍保持 `first_candidate_opened=False`，下一外层循环按原方式调用 `open_first_candidate_for_batch()`。
- 首位重开后记录 `detail_load_recovery_reopen_completed`，此时恢复计数仍为 1，且不记录 `detail_load_recovery_confirmed`。
- **Change 4 中间版本**：直接使用最终 `consecutive_load_recovery_count`；第一次失败只恢复一次，恢复后计数保持 1；第二次连续失败不再次 F5，`run()` 受控返回 0 并执行 finally；尚不要求 loaded 后清零、`stop_reason=load_failed` 或完整最终 ERROR。
- **Change 5 最终版本**：恢复后任一候选人 loaded 时记录 `detail_load_recovery_confirmed`，只有此事件后计数清零；未来独立故障再次允许恢复；持续失败设置 `stop_reason=load_failed` 并写完整 ERROR。
- 重新打开后再次完整失败不记录 `detail_load_recovery_confirmed`。
- `batch_filter_enabled=False`、`--no-batch-filter`、regions None：四次检测后 `hard_recovery_unavailable`，无 F5/legacy 点击。
- 刷新、筛选、首位打开非停止失败进入 `load_failed`。
- `total_viewed` 只在 loaded 增加；失败/恢复不增加，成功后的规则或动作失败不回退。
- 硬恢复不清零 `forward_consecutive`；正常满 100 人仍清零。
- 正常满 100 人的已有筛选与 legacy 事件顺序不变。

### 19.6 停止

- ESC 在首位/切换现有等待期间停止，不开始加载 OCR。
- ESC 在重试等待期间停止，不继续 OCR/恢复。
- ESC 在恢复刷新或筛选等待期间停止，不误记 `load_failed`。
- timer 在相同等待点设置停止并保留 `run_duration_elapsed`。
- capture/OCR 期间到达停止请求时，在同步调用返回后不执行规则或动作。
- 最终加载故障 `stop_reason=load_failed`、ERROR 日志、受控返回 0。
- `load_failed` 不输出“收到 ESC”。
- ESC、timer、load_failed 均保留第一个实际停止原因，不互相覆盖。

### 19.7 模式与回归

- 有关键词 favorite、forward、forward + `--no-forward` 均先走加载门。
- 无关键词不走 R02、OCR 初始化或校准。
- 现有 `test_ocr_detector.py`、`test_ocr_text.py` 全部通过。
- 现有最多 8 屏、二次确认、favorite/forward 互斥、焦点恢复测试通过。
- 现有 batch filter、正常刷新、legacy 重新点击和 timer 测试通过。
- Windows 全量 `unittest discover` 通过。
- macOS 只要求受影响的公共 OCR 纯单元测试继续可运行；不要求正式候选人 E2E。

### 19.8 Windows + Edge 人工冒烟

按 RPD 第 25 节执行，优先测试账号 + 有效规则 + `--no-forward`：正常立即加载、延迟后重试成功、完整失败后恢复、恢复不可用、恢复后再次失败、成功后独立故障、ESC/timer、favorite/forward 分发、无关键词回归、统计与日志。真实转发不作为默认冒烟动作。

## 20. Change 1—Change 6 实施计划

### Change 1：加载判定基础能力

- **文件范围**：`ocr_detector.py`、`simple_brush.py`、`tests/test_ocr_detector.py`。
- **允许修改**：新增五个配置常量中的阈值/重试/恢复常量；新增 `accepted_ocr_items()`、`calculate_load_metrics()`、`evaluate_detail_page_load()` 及边界测试。
- **禁止修改**：生产调用链、`ScanObservation`、`detect()`、`run()`、GUI、CLI、OCR 规则和动作。
- **自动化测试**：第 19.1 节全部；现有 detector/text 测试。
- **人工验证**：无生产行为变化；只核对常量位置和测试输出。
- **完成标准**：公式与五个边界精确，低置信度/空文本口径正确，生产行为 diff 仅有未调用能力。
- **可能风险**：误改 `ScanObservation.item_count` 或规则文本过滤；通过独立 helper 测试隔离。
- **是否允许 commit**：Codex 不自行 commit；完成并经用户决定后才可提交。

### Change 2：首屏加载门禁

- **文件范围**：`ocr_detector.py`、`simple_brush.py`、`tests/test_ocr_detector.py`、`tests/test_simple_brush_ocr.py`。
- **允许修改**：只给 `ScanObservation` 追加两个指标；新增 `capture_observation()`、`_match_observation()`；给 detector/view/detect_keywords 增加可选首屏参数；在 `run()` 的关键词路径接入一次加载门并调整关键词路径 `total_viewed` 时点；校准未就绪时安全返回；单次失败在 run 主 try 内受控 `return 0`。
- **禁止修改**：多次重试、页面硬恢复、连续恢复语义、完整停止原因、无关键词路径、动作内部和正常刷新。
- **自动化测试**：纯采集无 matcher/scroll 且 observation 不保存 OCRItem 列表；一次成功只采集/消费一次；一次未加载或异常后 run 返回 0、finally 执行，不进入规则、滚动、动作、next、额外首位打开或正常刷新；无关键词保持原调用链；统计时点。
- **人工验证**：Windows + Edge + `--no-forward` 正常页小样本；受控空首屏确认 fail closed。
- **完成标准**：加载判定位于第一次规则/滚动前；正常首屏不重复 OCR；失败路径从 run 受控返回且执行 finally，不设置临时 `load_failed`/`stop_event`，不跳到下一候选人或正常刷新。
- **可能风险**：给 `detect()` 增加可选输入破坏 8 屏/确认；以未传参数的全量现有测试证明兼容。
- **是否允许 commit**：Codex 不自行 commit；由用户决定。

### Change 3：原位置重试与 OCR 结果复用

- **文件范围**：`simple_brush.py`、`ocr_detector.py`、`tests/test_simple_brush_ocr.py`、`tests/test_ocr_detector.py`。
- **允许修改**：把一次门禁扩展为首次 + 3 次；每次重试前 `safe_wait(1.5)`；统一处理 `ocr_error`；完成任意成功 observation 复用；耗尽向 run 返回 `retries_exhausted`，由 run 受控 `return 0`。
- **禁止修改**：F5/筛选硬恢复、连续恢复清零、通用 retry 框架、异步 OCR、退出码。
- **自动化测试**：第 19.2、19.3、19.4 节；特别断言等待次数、OCR 次数、未知指标、耗尽后 run 返回 0/finally、且无 next、刷新或恢复。
- **人工验证**：Windows + Edge 受控延迟，观察原位置无滚动/点击且重试成功直接进入正式规则。
- **完成标准**：最多 4 次、等待精确、停止可中断、错误共享预算、成功首屏无任何重复消费；耗尽不设置最终 `load_failed`，不落入正常刷新。
- **可能风险**：`OCRInterrupted` 被误算 `ocr_error`；实现使用 `safe_wait()` 布尔分支并在 capture 前后独立检查 stop。
- **是否允许 commit**：Codex 不自行 commit；由用户决定。

### Change 4：页面级硬恢复

- **文件范围**：`simple_brush.py`、`tests/test_simple_brush_ocr.py`。
- **允许修改**：参数化 `refresh_page(reason=...)`；新增 `recover_detail_page()`；在 run 直接新增最终 `consecutive_load_recovery_count=0`、`restart_current_batch`，并复用既有 `first_candidate_opened`；复用筛选首位函数；记录 `detail_load_recovery_reopen_completed`。
- **禁止修改**：legacy 模拟恢复、盲点坐标、第二套筛选、OCR 重初始化/校准、timer 重启、规则/邮箱/模式重置、正常刷新语义。
- **自动化测试**：恢复事件顺序；筛选首位只调用一次；`first_candidate_opened=True` 阻止重复打开；`restart_current_batch` 跳过正常刷新；批次从 0 重启；第一次只恢复一次、第二次连续失败不 F5 并受控返回；计数暂不清零且无最终 stop reason；不可用/步骤失败安全返回；正常 100 人四个回归测试。
- **人工验证**：Windows + Edge 完整失败后一次 F5 + 最近没看过 + 首位重开。
- **完成标准**：恢复只在完整区域可用时发生；使用最终计数且最多一次，不无限刷新；重开后两个控制标志职责正确；总计时/总人数/forward_consecutive/校准保持；暂不实现成功后清零和完整最终日志；正常刷新行为不变。
- **可能风险**：break 后误落入正常刷新或重复打开首位；同时断言 `restart_current_batch` 与既有 `first_candidate_opened` 的事件顺序和调用次数。
- **是否允许 commit**：Codex 不自行 commit；由用户决定。

### Change 5：连续恢复限制、安全终止和日志

- **文件范围**：`simple_brush.py`、`tests/test_simple_brush_ocr.py`。
- **允许修改**：在 Change 4 同一个 `consecutive_load_recovery_count` 上补齐 loaded 后的 `detail_load_recovery_confirmed` 与清零；新增 `stop_reason`、`request_load_failed_stop()`；完成五状态、两阶段恢复事件和最终 ERROR。
- **禁止修改**：新 Enum/状态机、非零退出码、身份去重、R01/R03、JSON/数据库、异常线程。
- **自动化测试**：reopen_completed 时计数仍为 1；loaded 后记录 recovery_confirmed 再清零；重开后失败无 confirmed；成功清零后独立恢复；持续失败的 stop_reason/ERROR；ESC/timer/load_failed 不覆盖；finally 统计和无动作断言。
- **人工验证**：Windows + Edge 连续故障、恢复不可用、ESC/timer 中断和日志定位。
- **完成标准**：不重写 Change 4 计数结构；只有 recovery_confirmed 后清零；最终故障受控结束且不误记 ESC；reopen_completed 不冒充加载成功；日志字段齐全。
- **可能风险**：stop reason 被后续回调覆盖或最终失败进入正常刷新；使用首次原因保留和 run 分支顺序测试。
- **是否允许 commit**：Codex 不自行 commit；由用户决定。

### Change 6：端到端测试、全量回归和验收报告

- **文件范围**：`tests/test_ocr_detector.py`、`tests/test_simple_brush_ocr.py`；仅修复 R02 直接问题时可修改 `ocr_detector.py`、`simple_brush.py`；新增 `docs/R02-detail-page-load-detection-acceptance-report.md`。
- **允许修改**：补齐本 TID 测试矩阵、修复测试暴露的 R02 直接缺陷、记录自动化与 Windows + Edge 冒烟证据。
- **禁止修改**：借机修复非 R02 问题、增加真实转发自动化副作用、macOS 主流程移植、无关文档/格式化/重构。
- **自动化测试**：相关定向 unittest、全量 `venv\Scripts\python.exe -m unittest discover -s tests -v`、公共 OCR 回归。
- **人工验证**：第 19.8 节 Windows 10/11 x64 + Microsoft Edge 冒烟；macOS 候选人 E2E 不要求。
- **完成标准**：自动化全绿；人工场景记录实际结果；Acceptance Report 明确平台、命令、证据、风险和结论。
- **可能风险**：真实页面不稳定或重复处理；使用测试账号、`--no-forward`、小样本和人工监控。
- **是否允许 commit**：Codex 不自行 commit；全部结果交付后由用户决定何时提交。

## 21. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 指标误用过滤前框数 | 新 helper 与边界测试；保留 `item_count` 语义并新增明确字段。 |
| 文本长度误用 normalized text | 从 accepted `OCRItem.text.strip()` 直接求和。 |
| 成功首屏重复 OCR/匹配/动作 | 同一 `ScanObservation` 对象从加载门传给 detector；capture 计数与 matcher 调用测试。 |
| observation 长期保存 OCR 框 | observation 只追加两个整数指标；raw/accepted 列表只作采集函数局部变量。 |
| 停止被算成 OCR error | `safe_wait` 和 capture 前后先检查 stop；stop 分支返回 `outcome=None`。 |
| OCR 同步调用不能即时抢占 | 不引入线程；返回后第一时间停止，Acceptance Report 记录该边界。 |
| 硬恢复误用 legacy | 恢复 helper 不接受 `legacy_point`，调用前必须完整区域可用。 |
| Change 2/3 中间失败落入正常刷新 | 失败分支从 run 主 try 直接 `return 0`，并测试 finally、refresh/next/额外首位打开均未调用。 |
| 批次重启落入正常刷新或重复打开首位 | run 同时设置 `first_candidate_opened=True` 和 `restart_current_batch=True`；前者阻止重复打开，后者在正常刷新前优先 continue。 |
| Change 4 无限刷新或与 Change 5 重复计数 | Change 4 直接引入唯一最终计数并保持 1；Change 5 只添加 confirmed 后清零。 |
| 首位重开被误报为加载恢复成功 | 分离 `detail_load_recovery_reopen_completed` 与 `detail_load_recovery_confirmed`，并断言失败时无 confirmed。 |
| `total_viewed` 重复或提前增加 | 只由 run 的单一 loaded 分支增加，并在同分支记录成功日志。 |
| `forward_consecutive` 被恢复清零 | 只保留正常满 100 人现有清零语句；硬恢复 helper 不接触该变量。 |
| 正常 100 人流程回归 | `refresh_page()` 默认参数保持原行为，保留现有事件顺序测试。 |
| 重复候选人/重复动作 | 明确不能消除；连续恢复上限、小样本和 `--no-forward` 降低验证风险。 |
| TID 扩大平台范围 | 正式范围只写 Windows + Edge；macOS 只回归公共纯 OCR 测试。 |

## 22. 回滚方案

R02 没有数据迁移、持久化 schema、CLI 或配置文件，回滚只涉及代码与测试：

1. 撤销 Change 5 时，只移除 recovery_confirmed 后清零、`stop_reason` 和最终日志；保留 Change 4 的同一个恢复计数和一次上限，使中间版本仍受控返回。
2. 撤销 Change 4 时，再一起移除恢复计数、恢复 helper、两个批次控制赋值和 reopen_completed；恢复到 Change 3 的 `retries_exhausted → return 0`。
3. 撤销 Change 3 时恢复到 Change 2 的单次失败受控返回；撤销 Change 2 时恢复原 detector/run 调用链和 `ScanObservation` 原字段。
4. 恢复 `run()` 原有 `total_viewed` 与调用链、`detect()` 原签名和 `refresh_page()` 原签名时，必须保护非 R02 用户改动，不使用 `git reset --hard` 或全文件覆盖。
5. 每一级回滚后运行相应定向测试；完整回滚后运行原全量 unittest，确认 v1.2 的 OCR、动作、焦点和正常刷新恢复。

具体回滚必须由用户授权；Codex 不自行 commit 或执行破坏性 Git 操作。

## 23. 尚需人工决定的问题

当前没有阻塞 Change 1 的产品或技术决策：

- RPD 与代码没有需要改写需求的冲突。
- TID 已决定使用现有 `ScanObservation`、四元组返回、run 局部计数、全局短停止原因、参数化刷新、无 `batch` 字段。
- OCR 初始化/校准失败按加载门前的既有受控启动失败处理，不伪造检测次数。
- 同步 OCR 无法中途抢占和候选人可能重复是已记录限制，不扩展范围。

后续只需用户决定每个 Change 何时开始、验收后是否以及何时 commit；这不是实现设计缺口。

## 24. TID 验收清单

- [ ] 文件和函数定位与基线代码一致。
- [ ] 未改变 RPD 的两个指标、判定边界、3 次重试、1.5 秒等待和一次连续恢复语义。
- [ ] 首屏 OCR 纯采集与正式消费边界明确。
- [ ] 成功首屏不会重复截图、OCR、规则、屏数、日志或动作。
- [ ] `ScanObservation` 只追加 `ocr_box_count` 和 `ocr_text_length`，不保存 OCRItem、raw/accepted 列表或 evidence。
- [ ] OCR 异常共享检测预算且未知指标不写 0。
- [ ] 加载门在规则、OCR 滚动和候选人动作之前。
- [ ] Change 2 单次失败从 run 主 try 受控返回 0，执行 finally，不进入下一候选人、额外首位打开或正常刷新，也不设置临时最终停止原因。
- [ ] Change 3 四次耗尽返回 `retries_exhausted`，run 受控返回 0 并执行 finally，不进入恢复、下一候选人或正常刷新。
- [ ] 无关键词模式不接入 R02。
- [ ] 硬恢复复用现有 F5 和筛选首位函数，不使用 legacy 模拟。
- [ ] 硬恢复完成首位打开后，run 同时设置 `first_candidate_opened=True` 与 `restart_current_batch=True`，不会重复打开且跳过正常刷新。
- [ ] Change 4 直接使用最终 `consecutive_load_recovery_count`，只恢复一次，暂不在 loaded 后清零，也不设置最终 stop reason。
- [ ] Change 5 不重写计数结构，只在 `detail_load_recovery_confirmed` 后清零，并补齐最终安全停止。
- [ ] `detail_load_recovery_reopen_completed` 只表示导航归位；`detail_load_recovery_confirmed` 才表示后续 loaded，二者时点和计数语义明确。
- [ ] `total_viewed`、批次位置、连续恢复计数、`forward_consecutive` 和 timer 生命周期明确。
- [ ] ESC、timer、暂停、`load_failed` 和 finally 路径明确。
- [ ] 五个加载状态只用简单字符串，不引入状态机。
- [ ] 日志字段完整，`batch` 明确省略。
- [ ] 重复处理风险被记录但未越界解决。
- [ ] Change 1—6 均包含文件、允许/禁止项、自动化、人工验证、标准、风险和 commit 边界。
- [ ] 正式验收限定 Windows 10/11 x64 + Microsoft Edge。
- [ ] 不实施 R01、R03、AI、JSON、数据库或 macOS 正式流程。
- [ ] `forward_enabled and forward_keywords` 的历史命名和三种有关键词模式覆盖已说明，未顺手改名。
- [ ] Change 0B 只创建或修订本 TID，未修改业务代码、测试、RPD、配置、构建脚本或其他文档。

## 25. Codex 执行边界

- Change 0B 完成后停止，不自动开始 Change 1。
- 后续每个 Change 只实现自己的范围和验收目标。
- 发现非 R02 问题只记录，不顺手修复。
- 不修改 `.gitignore`，不强制暂存被忽略的 Markdown。
- 不 commit、push、创建 tag 或 Release；由用户在验收后决定版本控制动作。
