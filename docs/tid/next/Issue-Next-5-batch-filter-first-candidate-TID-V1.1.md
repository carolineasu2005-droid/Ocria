# [Next-5] TID V1.1：启动及批次刷新后自动应用「最近没看过」筛选并点击首位候选人

> 本文档基于 V1.0 修订。保留 V1.0 的运行期区域、原子校准、自动筛选归位、旧流程回退及无页面状态检测方案；V1.1 重点明确计时器顺序、首次执行失败行为、已确认 UI 事实和四段式 Change 拆分。

## 1. 背景与目标

BossOCR 当前每批浏览 `BATCH_SIZE = 100` 位候选人，批次结束后按 F5 刷新页面，再使用启动时保存的单点坐标打开首位候选人。页面刷新不会主动应用“最近没看过”，后续批次可能再次出现旧候选人。

本需求新增四个仅当前运行期有效的区域：

1. 首位候选人卡片区域。
2. “打开筛选”按钮区域。
3. “最近没看过”选项区域。
4. “筛选确定”按钮区域。

四项全部校准成功后，启动阶段及每个完整批次刷新后自动执行：

```text
点击打开筛选
→ 点击最近没看过
→ 点击筛选确定
→ 等待候选人列表刷新
→ 点击首位候选人卡片
→ 等待详情页稳定
```

之后继续既有焦点恢复、完整转发点击、OCR 校准、关键词、转发和右方向键浏览流程。

校准采用原子提交。任一新增区域取消或失败，本次运行禁用自动筛选归位，回退现有人工首位坐标流程；校准取消不导致程序整体退出。

### 1.1 当前代码事实

当前 `run()` 只在启动时执行一次 `pyautogui.position()`，后续批次复用该坐标。外部移动鼠标不会改变已保存坐标；现有依赖实际发生在首次捕获阶段，以及后续页面布局是否仍与该单点一致。

100 人边界当前为：

```text
for i in range(BATCH_SIZE)
→ forward_consecutive = 0
→ refresh_page()  # F5 + REFRESH_WAIT_SECONDS
→ while 下一轮顶部 click_first_candidate(click_x, click_y)
```

新流程应替换下一轮顶部的首位打开动作，不修改批内 `next_candidate()`。

## 2. 非目标

- 不读取 DOM、按钮文字、页面 URL、可访问性树或 BOSS 接口。
- 不引入 Selenium、Playwright、WebDriver、浏览器调试端口或 JavaScript。
- 不新增页面状态识别、图片识别、加载完成检测或筛选结果检测。
- 不判断筛选是否生效、面板是否打开或详情是否真的进入。
- 不修改 OCR 内部识别、滚动、扫描、二次确认或失败关闭逻辑。
- 不修改关键词 `and` / `or` / `not` / `any(...)` parser 或 matcher。
- 不修改邮件转发、备用邮箱、转发结果、完整转发校准或双击焦点恢复逻辑。
- 不修改右方向键切换下一位候选人的逻辑。
- 不持久化区域，不跨运行、窗口位置、缩放或分辨率复用。
- 不修改 `ocr_calibration.py` 的 Tk GUI，只复用 `select_screen_region()`。
- 不修改 Windows 打包，不处理 macOS Chrome，不创建 tag 或 release。

## 3. 现有代码插入点分析

### 3.1 可复用基础设施

`ocr_calibration.py`：

- `ScreenRegion(left, top, width, height)`。
- `select_screen_region(min_size, instruction, subtitle)`。
- `CalibrationCancelled`。
- Windows DPI 感知和主显示器物理像素换算。

`simple_brush.py`：

- `random_point_in_region()`：按半开区间取点。
- `click_in_region()`：区域取点后使用 `human_click(..., offset=0)`。
- `human_delay()` / `safe_wait()`：可响应暂停和停止。
- `BATCH_SIZE = 100`。
- `CLICK_WAIT_SECONDS = 2`。
- `REFRESH_WAIT_SECONDS = 5`。

### 3.2 新校准插入点

四区域属于候选人列表页，应在以下位置执行：

```text
get_user_input()
→ listener.start()
→ bring_edge_foreground()
→ 四区域校准
→ 自动筛选并打开首位候选人
```

不能放到首位详情打开后，因为筛选入口和首位卡片位于列表页。

### 3.3 既有详情校准衔接

首位候选人打开并稳定后，继续执行：

1. `ensure_focus_restore_region_calibrated()`（如请求）。
2. `ensure_forward_click_regions_calibrated()`（如请求）。
3. `ensure_ocr_region_calibrated()`（有关键词时）。
4. 启动运行计时器。
5. 进入第一次 `view_candidate(0)`。

V1.1 推荐在第一次浏览前显式调用现有 `ensure_ocr_region_calibrated()`，使 OCR 框选也属于启动准备动作。`detect_keywords()` 后续再次调用时会因现有 detector/attempted 状态直接复用，不修改 OCR 内部逻辑。

### 3.4 批次边界插入点

保留现有 `refresh_page()`。它成功返回后，下一轮打开首位候选人时走统一分支：

```text
batch_filter_enabled=True
  → apply_batch_filter_and_open_first_candidate()

batch_filter_enabled=False
  → click_first_candidate(legacy_x, legacy_y)
```

实际顺序：

```text
第 100 位完成
→ F5 并等待
→ 打开筛选
→ 最近没看过
→ 筛选确定并等待
→ 点击首位候选人
→ 下一批 view_candidate(0)
```

第一版不删除 F5。若实机证明 F5 与筛选确定的双重刷新存在明显问题，应另行评估，不在本 issue 中静默改变旧刷新语义。

## 4. 新增数据结构

```python
@dataclass(frozen=True)
class BatchFilterRegions:
    first_candidate: ScreenRegion
    open_filter: ScreenRegion
    unseen_filter: ScreenRegion
    confirm_filter: ScreenRegion
```

运行期状态：

```python
batch_filter_regions: Optional[BatchFilterRegions] = None
batch_filter_calibration_requested = False
batch_filter_calibration_attempted = False
batch_filter_calibration_in_progress = False
batch_filter_enabled = False
```

约束：

- 不提供四区域的硬编码默认值。
- `batch_filter_regions` 仅在四项全部成功后赋值。
- `batch_filter_enabled` 仅在原子校准成功且筛选面板完成最佳努力关闭后设为 `True`。
- `reset_batch_filter_calibration()` 在每次 `run()` 开头清空全部状态。
- `on_press()` 增加 `batch_filter_calibration_in_progress` 判断，Tk 中 Esc 只取消框选。
- 程序化关闭面板继续使用 `_programmatic_esc` 隔离全局 Esc 监听。

### 4.1 禁用开关

建议新增 `--no-batch-filter`：

- 普通交互模式：不传时询问是否校准；传入后不询问、不弹框，使用旧流程。
- `--auto`：始终不弹新增框选层，使用旧流程。
- 通过 `--keywords` 进入现有非交互输入分支时，同样不突然弹框。
- `--no-forward` 不禁用筛选功能，两者职责独立。
- 无关键词的普通交互模式仍可启用筛选归位。

该开关是页面变化时的快速止损手段，不是区域持久化配置。

## 5. 新增校准流程

新增 `ensure_batch_filter_regions_calibrated()`，只尝试一次并原子发布。

### 5.1 顺序

1. 框选首位候选人卡片内部安全区域，建议 `min_size=20`。
2. 框选“打开筛选”按钮内部安全区域，建议 `min_size=12`。
3. 用局部 `open_filter` 调用 `click_in_region()` 打开筛选面板。
4. `human_delay()` 等待面板动画，不检测状态。
5. 框选“最近没看过”内部安全区域，建议 `min_size=12`。
6. 框选“筛选确定”内部安全区域，建议 `min_size=12`。
7. 程序化 Esc，最佳努力关闭面板。
8. 仅全部成功后发布四个区域并启用功能。

校准期间只点击“打开筛选”。首位候选人、“最近没看过”和“筛选确定”只框选，不点击。

### 5.2 原子回退

任一框选取消、点击异常、等待中断或关闭面板异常：

- 不发布局部区域。
- `batch_filter_regions=None`。
- `batch_filter_enabled=False`。
- 面板可能打开时，程序化 Esc 最佳努力关闭。
- 关闭失败只记录 warning，不猜测其他关闭动作。
- `batch_filter_calibration_attempted=True`，本轮不重复弹框。
- `batch_filter_calibration_in_progress=False`。
- 返回旧首位坐标流程，不退出程序。

## 6. 启动阶段流程调整

### 6.1 V1.1 最终计时器方案

采用“启动准备不计入运行时间”的方案。

最终顺序：

```text
解析输入
→ 置前 Edge
→ 四区域校准
→ 自动筛选并点击首位候选人
→ 等待详情页稳定
→ 既有焦点恢复区域校准
→ 既有完整转发点击区域校准
→ 既有 OCR 区域校准（有关键词时）
→ start_run_timer(run_duration_seconds)
→ 真正开始 view_candidate(0)
```

四区域框选、筛选导航、首位打开、焦点/转发/OCR 框选均属于启动准备，不消耗用户设置的运行秒数。

实现注意：

- `run_timer` 应在进入准备流程前初始化为 `None`。
- 只有准备成功、即将进入第一次 `view_candidate()` 时才赋值为真实 Timer。
- `finally` 中继续采用 `if run_timer is not None: run_timer.cancel()`。
- 用户在准备阶段按 Esc 停止时，不应创建 Timer。
- OCR 不可用或 OCR 校准取消时，沿用现有“禁用 OCR/转发并继续浏览”策略；准备尝试结束后再启动 Timer。

不采用旧语义。若保留当前 `bring_edge_foreground()` 后立即启动 Timer，四区域框选及后续校准会计入运行时间，慢速人工校准可能耗尽短时任务，甚至在第一次浏览前触发停止。这与“运行时间”直觉不符，因此 V1.1 不推荐也不采用。

### 6.2 自动筛选成功路径

```text
ensure_batch_filter_regions_calibrated()
→ apply_batch_filter_and_open_first_candidate()
→ 详情页稳定
→ 既有详情校准
→ start_run_timer()
→ view_candidate(0)
```

成功校准后不再提示人工放置鼠标，也不读取 `pyautogui.position()`。

### 6.3 校准取消/失败的旧流程

校准未请求、取消或失败时：

```text
提示用户把鼠标移到第一位候选人
→ 现有倒计时
→ pyautogui.position()
→ click_first_candidate(legacy_x, legacy_y)
→ 既有详情校准
→ start_run_timer()
→ view_candidate(0)
```

“回退旧流程”指保留人工坐标和后续批次行为；V1.1 对计时器做统一修正，旧路径的倒计时和校准同样不消耗用户运行时间。

必须在新校准结束后才捕获 legacy 坐标，因为框选会移动鼠标。

### 6.4 首次 apply 失败：安全停止

四区域校准成功后，如果首次 `apply_batch_filter_and_open_first_candidate()` 任一步失败：

- 不得回退旧鼠标坐标。
- 不得调用 `pyautogui.position()` 补救。
- 不得继续焦点恢复、完整转发或 OCR 校准。
- 不得启动运行 Timer。
- 不得进入 `view_candidate()`。
- 记录失败步骤并安全结束本轮 `run()`。

原因：筛选面板可能停留在未知中间状态，旧坐标可能落在面板控件上。没有页面状态识别时，停止比盲目点击安全。

### 6.5 自动筛选执行函数

新增 `apply_batch_filter_and_open_first_candidate()`：

```text
检查 stop_event、enabled、regions
→ click_in_region(open_filter)
→ human_delay
→ click_in_region(unseen_filter)
→ human_delay
→ click_in_region(confirm_filter)
→ 等待列表刷新
→ click_in_region(first_candidate)
→ safe_wait(CLICK_WAIT_SECONDS)
→ 返回 True
```

每次等待后检查停止状态。所有点击均使用 `click_in_region()`，最终 `human_click(..., offset=0)`。

首次或后续批次运行中出现异常/等待中断都返回 `False`。主循环停止，不中途切换旧坐标。

## 7. 每批次刷新后的流程调整

统一本批首位打开入口：

```python
def open_first_candidate_for_batch(legacy_point=None):
    if batch_filter_enabled:
        return apply_batch_filter_and_open_first_candidate()
    return click_first_candidate(*legacy_point)
```

主循环保持：

```text
while not stop_event:
    open_first_candidate_for_batch()
    首次才执行详情校准
    for i in range(BATCH_SIZE):
        view_candidate(i)
        非最后一位时 next_candidate()
    forward_consecutive = 0
    refresh_page()
    # 下一轮顶部再次筛选归位或走旧坐标
```

批次顺序测试必须证明：

```text
首次 filter/open
→ view(0)
→ next
→ view(1)
→ refresh
→ 第二次 filter/open
→ 下一批 view(0)
```

`refresh=False` 或筛选 helper 返回 `False` 时，不进入下一批浏览。

## 8. 回退策略

### 8.1 可回退场景

只有自动筛选尚未开始前的以下情况允许回退旧首位坐标：

- 用户拒绝校准。
- `--no-batch-filter`。
- `--auto` 或现有 CLI 非交互路径。
- 四区域任一校准取消。
- 四区域校准或校准后的面板关闭失败。

### 8.2 不可回退场景

一旦四区域成功发布并开始首次或后续 `apply_batch_filter_and_open_first_candidate()`，任一步失败都停止本轮，不切换旧坐标。面板中间态无法安全推断。

### 8.3 重启要求

区域仅存内存。窗口移动、缩放、分辨率、DPI 或 BOSS 布局变化后必须停止并重新启动校准。

## 9. 延迟与等待策略

建议常量：

```python
FILTER_OPEN_DELAY_MIN = 0.5
FILTER_OPEN_DELAY_MAX = 1.0
FILTER_OPTION_DELAY_MIN = 0.3
FILTER_OPTION_DELAY_MAX = 0.7
FILTER_RESULTS_DELAY_MIN = 2.0
FILTER_RESULTS_DELAY_MAX = 3.0
```

| 动作 | 等待 |
| --- | --- |
| 打开筛选后 | `human_delay(0.5, 1.0)` |
| 选择最近没看过后 | `human_delay(0.3, 0.7)` |
| 筛选确定后 | `human_delay(2.0, 3.0)` |
| 点击首位候选人后 | `safe_wait(CLICK_WAIT_SECONDS)` |
| 批次 F5 后 | 保留 `safe_wait(REFRESH_WAIT_SECONDS)` |

第一版不轮询加载状态、不按网络速度调整、不自动重试。任一等待返回 `False`，立即停止后续点击。

## 10. 测试计划

测试放在 `tests/test_simple_brush_ocr.py` 或独立 `tests/test_batch_filter.py`。所有真实副作用必须 mock：

- `select_screen_region()`。
- `click_in_region()`。
- `human_delay()` / `safe_wait()`。
- `pyautogui.position()` / `press()` / `click()`。
- `listener.start()` / `bring_edge_foreground()`。
- OCR backend、剪贴板和转发入口。

不得触发真实 GUI、鼠标、键盘、剪贴板、OCR 或邮件转发。

### 10.1 校准状态与原子性

- reset 清空全部 batch filter 状态。
- 选择顺序为 first、open、unseen、confirm。
- 校准期间只点击 open filter。
- 四项全部成功后一次性发布并 enabled。
- 第 1/2/3/4 项取消均清空整组、禁用且不退出。
- 面板打开后取消会最佳努力 Esc；打开前取消不发送多余 Esc。
- 普通异常、关闭异常、等待中断均原子回退。
- attempted 防止重复弹框。
- 校准期间 Esc 不设置 `stop_event`。

### 10.2 启动调用顺序

成功事件：

```text
bring_edge
→ batch_filter_calibrate
→ open_filter
→ unseen_filter
→ confirm_filter
→ first_candidate
→ focus_restore_calibrate
→ forward_click_calibrate
→ ocr_calibrate（有关键词）
→ timer_start
→ view(0)
```

回退事件：

```text
batch_filter_calibrate（取消/失败）
→ legacy countdown
→ position
→ legacy click first
→ 既有详情校准
→ timer_start
→ view(0)
```

首次 apply 失败事件：

```text
batch_filter_calibrate success
→ apply failure
→ run ends
```

并断言 position、legacy click、焦点/转发/OCR校准、timer_start、view 均未调用。

### 10.3 计时器顺序测试（V1.1 必需）

1. 四区域校准进行期间，`threading.Timer` / `start_run_timer()` 未调用。
2. 自动筛选并打开首位候选人期间，Timer 未启动。
3. 焦点恢复、完整转发和 OCR 校准期间，Timer 未启动。
4. 成功打开首位并完成启动准备后，在第一次 `view_candidate()` 前恰好启动一次 Timer。
5. 校准取消/失败回退旧流程时，倒计时、位置捕获、首位点击和既有详情校准完成后才启动 Timer。
6. 用户在准备阶段停止、首位打开失败或首次 apply 失败时不创建 Timer。
7. Timer 创建后，`finally` 仍恰好取消一次。
8. `duration_seconds=0` 继续不创建 Timer。

建议通过事件列表断言精确顺序，而不仅断言调用次数。

### 10.4 自动筛选 helper

- 点击顺序严格为 open、unseen、confirm、first。
- 参数均为相应 `ScreenRegion`。
- 等待顺序和范围正确。
- 任一步等待 False 或点击异常后无后续点击。
- 不调用 legacy 坐标。
- disabled/regions 缺失时不执行新点击。

### 10.5 批次边界

- patch `BATCH_SIZE=2`，首次及刷新后各执行一次完整筛选 helper。
- `view(0) → next → view(1) → refresh → filter/open → view(0)`。
- 最后一位后不额外 `next_candidate()`。
- `refresh_page=False` 后不筛选下一批。
- helper=False 后不进入下一批 view。
- `forward_consecutive` 仍在边界归零。

### 10.6 模式兼容

- `--auto` 不询问、不框选、不执行筛选导航。
- `--no-batch-filter` 不询问、不框选。
- CLI keywords 非交互路径不突然弹框。
- 无关键词普通模式可启用筛选。
- `--no-forward` 可执行筛选但不调用真实转发。

### 10.7 全量回归

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
git diff --check
```

重点确认 OCR、关键词、转发、双击焦点恢复、计时停止和已有校准测试全部通过。

## 11. 变更步骤

V1.1 推荐四段式，业务接入与用户文档分开提交。

### Change 1：运行期区域状态与原子校准

修改：`simple_brush.py`、相关测试。

- 新增 `BatchFilterRegions`、状态和 reset。
- 新增原子四区域校准、校准导航和程序化 Esc 清理。
- 增加 `--no-batch-filter` 及交互/非交互决策。
- 扩展 Esc 校准隔离。
- 覆盖成功、各阶段取消、异常、原子提交和不重复尝试。

建议 commit：

```text
feat: calibrate batch filter navigation regions
```

### Change 2：启动筛选、首位归位与计时器顺序

修改：`simple_brush.py`、启动与计时测试。

- 新增自动筛选 helper 和新旧首位入口。
- 调整启动准备顺序。
- 将 Timer 移到全部启动准备完成后、第一次 view 前。
- 明确首次 apply 失败安全停止，不回退、不继续校准。
- 覆盖成功、旧路径、首次失败和 Timer 精确顺序。

建议 commit：

```text
feat: apply unseen filter before timed browsing
```

### Change 3：100 人批次边界接入与测试

修改：`simple_brush.py`、批次边界测试。

- 现有 F5 后下一轮重新执行筛选归位。
- 保持 `BATCH_SIZE`、`next_candidate()`、`refresh_page()` 和连续转发计数语义。
- 覆盖刷新、下一批顺序、停止和失败。

建议 commit：

```text
feat: reapply unseen filter at batch boundaries
```

### Change 4：README 与使用说明

修改：`README.md`。

- 说明四区域校准顺序、校准期导航和运行期限制。
- 说明 `--auto`、CLI 非交互、`--no-forward`、`--no-batch-filter`。
- 说明校准失败回退与 apply 失败安全停止的区别。
- 说明计时从启动准备完成后开始。
- 说明无页面检测、窗口变化需重启和实机风险。

建议 commit：

```text
docs: explain batch filter navigation
```

四个 Change 均不得混入 OCR、关键词、转发内部、打包或 macOS 变更。若实施时被要求压缩为三段，Change 3 可同时更新 README，但必须保持 diff 只包含本 issue 的批次接入、测试和直接相关文档，不得借机混入无关业务改动；V1.1 首选仍是四段式。

## 12. 风险与回滚方案

### 12.1 已确认 UI 事实

- 已人工确认：“最近没看过”不是反复开关的 toggle，而是筛选面板中的确定项。每批进入面板后点击该项不会因跨批次保留开关状态而反向取消筛选。

因此 V1.0 中“重复点击可能关闭 toggle”的阻断风险已解除。

### 12.2 仍需实机确认

1. Esc 能稳定关闭筛选面板，且不会退出 BOSS 页面或触发其他副作用。
2. 点击“筛选确定”并等待后，首位候选人卡片仍位于已校准区域。

若任一事实不成立，应停止实施或调整交互方案，不能用更多盲点重试掩盖。

### 12.3 其余主要风险

- 无状态检测，无法确认面板、选项、确定、列表或详情的真实状态。
- F5 后再筛选确定可能产生双重刷新。
- 绝对屏幕区域受窗口、缩放、DPI、分辨率和 BOSS 布局变化影响。
- 框选包含邻近控件时，区域随机点可能误触。
- 筛选后空列表、骨架屏或特殊卡片可能占据首位区域。
- 固定随机等待在慢网络下可能不足。
- 首次/批次 apply 失败时只能安全停止，不能自动恢复。
- CLI 非交互兼容需要避免突然弹 Tk。
- Timer 顺序调整必须保证所有提前返回路径都能处理 `run_timer=None`。

### 12.4 回滚

- Change 4 可独立回滚文档。
- Change 3 可回滚批次接入，保留启动功能。
- Change 2 可回滚启动接入和 Timer 调整，恢复旧首位流程。
- Change 1 可整体回滚新状态和校准。
- 运行时可使用 `--no-batch-filter` 回到旧导航。
- 不修改 Windows stable tag/分支；验收前不进入稳定发布。

## 13. 验收标准

| 验收项 | 通过条件 |
| --- | --- |
| 四区域校准 | 可依次框选 first、open、unseen、confirm |
| 原子发布 | 四项全部成功才 enabled，不存在部分配置 |
| 校准导航 | 校准期只点击 open filter，不点击其他三个区域 |
| 校准取消/失败 | 禁用新功能、不退出，回退旧首位流程 |
| 启动自动筛选 | open → unseen → confirm → first 顺序正确 |
| 区域点击 | 全部经 `click_in_region()`，无二次 offset |
| 首次 apply 失败 | 不回退旧坐标、不继续任何详情校准、不启动 Timer、不浏览 |
| 详情校准衔接 | 首位稳定后执行既有焦点/转发/OCR校准 |
| Timer 起点 | 全部启动准备完成后、第一次 view 前启动 |
| 校准计时 | 四区域、筛选、首位打开和既有校准均不消耗运行时间 |
| 旧路径计时 | 回退旧流程时，首位打开和详情准备完成后才启动 Timer |
| 准备阶段停止 | 不创建 Timer |
| 批次边界 | 每 100 人并 F5 成功后重新筛选并打开首位 |
| 右方向键 | 批内逻辑不变，最后一位后不多按 |
| 非交互安全 | auto、CLI keywords、no-batch-filter 不弹新增框选 |
| 无关键词 | 普通浏览仍可选择筛选校准 |
| no-forward | 可筛选，但不真实转发 |
| UI 事实 | “最近没看过”非 toggle 已记录；Esc 和首位位置仍需实机确认 |
| 测试隔离 | 无真实 GUI、键鼠、剪贴板、OCR 或转发调用 |
| 回归 | 全量测试和 `git diff --check` 通过 |
| 非目标 | 未修改 OCR/关键词/转发内部、打包或 macOS Chrome |
| 禁止技术 | 未引入 DOM、文字识别或浏览器驱动 |
