# [Next-5] TID V1.0：启动及批次刷新后自动应用「最近没看过」筛选并点击首位候选人

## 1. 背景与目标

BossOCR 当前在 Windows + Microsoft Edge 环境中运行。主循环每批浏览 `BATCH_SIZE = 100` 位候选人，批次结束后按 F5 刷新页面，再使用启动时保存的固定坐标点击首位候选人。页面刷新本身不会主动选择“最近没看过”，后续批次可能重新出现已浏览候选人。

本需求新增一组仅运行期有效的候选人列表导航区域：

1. 首位候选人卡片点击区域。
2. “打开筛选”按钮区域。
3. “最近没看过”选项区域。
4. “筛选确定”按钮区域。

四个区域全部校准成功后，程序在首次浏览及每个 100 人批次刷新后自动执行：

```text
打开筛选
→ 选择“最近没看过”
→ 点击筛选确定
→ 等待候选人列表刷新
→ 从首位候选人区域内取点点击
→ 等待详情页稳定
```

然后继续既有焦点恢复/完整转发点击区域校准、OCR、关键词判断、转发和右方向键浏览流程。

四个区域必须作为一个原子配置发布。任一框选取消或失败，本次运行禁用自动筛选归位，使用现有人工首位坐标流程；取消校准不停止整个程序。

### 1.1 当前行为与需求背景的差异

当前 `run()` 并不是每批次重新读取鼠标位置。程序只在启动倒计时后执行一次：

```python
click_x, click_y = pyautogui.position()
```

之后每一批都复用该坐标。因此，捕获完成后外部移动鼠标不会改变已保存的首位坐标；真正的依赖是用户必须在首次捕获时把鼠标放对位置，且后续页面布局必须继续与该单点坐标一致。

本需求仍然有明确价值：成功校准后不再依赖首次人工摆放鼠标，首位候选人使用一个可随机取点的区域，且批次刷新后会重新应用“最近没看过”筛选。

## 2. 非目标

- 不读取 DOM、按钮文字、页面 URL、可访问性树或 BOSS 接口。
- 不引入 Selenium、Playwright、WebDriver、浏览器调试端口或 JavaScript 注入。
- 不新增页面状态识别、图片识别或筛选结果检测。
- 不判断筛选是否成功、候选人列表是否加载完成或详情页是否真的打开。
- 不修改 OCR 初始化、区域、滚动、扫描、二次确认或失败关闭逻辑。
- 不修改关键词 parser/matcher，包括 `and`、`or`、`not`、`any(...)`。
- 不修改邮件转发、备用邮箱、转发结果、完整转发点击校准或双击焦点恢复逻辑。
- 不修改右方向键切换下一位候选人的逻辑。
- 不做区域持久化，不跨运行或跨分辨率复用。
- 不修改 `ocr_calibration.py` 的 Tk 区域选择界面；只复用现有 `select_screen_region()`。
- 不修改 Windows 打包脚本，不处理 macOS Chrome，不创建 tag 或 release。

## 3. 现有代码插入点分析

### 3.1 相关数据结构与基础设施

文件：`ocr_calibration.py`

- `ScreenRegion(left, top, width, height)`：现有统一屏幕区域结构，可直接复用。
- `select_screen_region(min_size, instruction, subtitle)`：主显示器 Tk 半透明框选层，返回物理像素区域；Esc 抛出 `CalibrationCancelled`。
- `enable_windows_dpi_awareness()` 与坐标换算：已确保 Tk 与 MSS 使用一致的 Windows 物理像素坐标。

文件：`simple_brush.py`

- `random_point_in_region(region)`：按半开区间从区域内随机取点。
- `click_in_region(region)`：取点后调用 `human_click(..., offset=0)`，不会产生二次偏移越界。
- `human_delay(min_s, max_s)`：随机等待并委托 `safe_wait()`。
- `safe_wait(seconds)`：等待期间响应暂停和停止。
- `BATCH_SIZE = 100`：每批候选人数。
- `CLICK_WAIT_SECONDS = 2`：打开首位详情后的现有等待。
- `REFRESH_WAIT_SECONDS = 5`：F5 后现有等待。

这些能力足够实现本需求，不需要改区域选择器 GUI。

### 3.2 现有启动流程

`simple_brush.py::run()` 当前顺序：

1. 重置焦点恢复和完整转发点击校准状态。
2. 解析参数并执行 `get_user_input()`。
3. 关键词存在时提前初始化 OCR 引擎。
4. 启动键盘监听。
5. `bring_edge_foreground()` 置前 Edge。
6. 启动可选运行计时器。
7. 提示用户把鼠标移到第一位候选人，等待 `COUNTDOWN_SECONDS`。
8. 读取一次 `pyautogui.position()` 保存固定 `(click_x, click_y)`。
9. 每轮 `while` 顶部调用 `click_first_candidate(click_x, click_y)`。
10. 首位详情可见后，按需校准焦点恢复和完整转发点击区域。
11. 进入 100 人浏览循环。

新增四区域校准应放在 Edge 置前、候选人列表可见之后，首次打开候选人详情之前。这样用户可以框选列表页元素，成功后由程序自动筛选并打开首位详情，再原样进入既有转发相关校准。

### 3.3 现有校准机制

#### OCR 区域

`ensure_ocr_region_calibrated()` 在第一位详情可见后惰性执行，取消/失败会禁用 OCR 转发但继续浏览。它包含 attempted/in-progress 状态和 Esc 隔离。

#### 焦点恢复区域

`ensure_focus_restore_region_calibrated()` 使用单区域框选，取消/失败回退 `DEFAULT_FOCUS_RESTORE_REGION`。

#### 完整转发点击区域

`ensure_forward_click_regions_calibrated()` 使用局部变量依次框选五个区域，仅全部成功后原子发布 `ForwardClickRegions`。校准中会点击已框选的转发入口和邮件 Tab 以进入后续 UI，最后程序化 Esc 关闭弹窗；取消/失败整组回退默认区域。

本需求最接近完整转发点击校准：筛选面板中的“最近没看过”和“筛选确定”在面板关闭时不可框选，因此需要在校准期间点击刚框选的“打开筛选”区域完成导航。不得点击“最近没看过”或“筛选确定”来完成校准；它们只框选，首次真实应用由后续自动筛选函数完成。

### 3.4 100 人批次边界

当前精确代码路径：

```text
for i in range(BATCH_SIZE)
  → view_candidate(i)
  → i < BATCH_SIZE - 1 时 next_candidate()
for 结束
  → forward_consecutive = 0
  → refresh_page()          # F5 + REFRESH_WAIT_SECONDS
while 下一轮顶部
  → click_first_candidate(click_x, click_y)
```

推荐插入点为：保留 `refresh_page()`，在它成功返回后的下一轮开始处，用统一的“打开本批首位候选人”分支替代直接固定坐标点击：

```text
自动筛选启用：apply_batch_filter_and_open_first_candidate()
自动筛选禁用：click_first_candidate(legacy_x, legacy_y)
```

因此批次实际顺序为：

```text
第 100 位完成
→ 现有 F5 刷新并等待
→ 打开筛选
→ 最近没看过
→ 确定并等待列表刷新
→ 点击首位候选人区域
→ 下一批第 1 位
```

第一版不删除 F5。筛选确定本身可能也刷新列表，但保留 F5 能最大限度维持现有批次边界行为；若实机证明重复刷新有明显副作用，应另开需求评估，不能在本 issue 中静默移除。

## 4. 新增数据结构

建议在 `simple_brush.py` 中新增：

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

设计说明：

- 不提供硬编码默认区域。需求明确要求任一新增区域失败时回退旧流程，而不是用未知默认坐标继续自动筛选。
- `batch_filter_regions is not None` 表示四项已经完整校准；不允许保存或使用部分区域。
- `batch_filter_enabled` 只在原子校准成功且筛选面板已完成最佳努力关闭后设为 `True`。
- `reset_batch_filter_calibration()` 在每次 `run()` 开头清空全部运行期状态，防止同一进程重复调用 `run()` 时复用旧坐标。
- `on_press()` 的校准判断增加 `batch_filter_calibration_in_progress`。用户在 Tk 框选层按 Esc 时只取消校准，不设置全局 `stop_event`。
- 继续使用现有 `_programmatic_esc`，避免程序关闭筛选面板时被全局键盘监听误判为停止命令。

### 4.1 是否新增 `--no-batch-filter`

建议新增 `--no-batch-filter`，作为明确的运行期开关，但不新增任何区域参数或持久化配置。

推荐语义：

- 普通交互模式：默认询问是否校准并启用自动筛选归位；传入 `--no-batch-filter` 时不询问、不弹框，直接使用旧流程。
- `--auto`：始终不弹交互框选层，自动筛选归位禁用，使用旧流程；`--no-batch-filter` 在此模式下只是显式确认。
- 通过 `--keywords` 进入现有非交互输入分支时，同样不应突然弹框；除非未来新增明确的交互启用参数，否则使用旧流程。
- 无关键词时仍可在普通交互模式使用自动筛选，因为该功能属于候选人浏览导航，不依赖 OCR 或转发。

增加禁用开关的理由：该功能没有页面状态检测，BOSS UI 变化时需要一种无需改代码的快速停用方式。开关只控制新导航，不改变 `--no-forward`。

## 5. 新增校准流程

新增 `ensure_batch_filter_regions_calibrated()`，只尝试一次并原子发布。

### 5.1 校准顺序

候选人列表初始可见时：

1. 框选首位候选人卡片内部安全区域，建议 `min_size=20`。
2. 框选“打开筛选”按钮内部安全区域，建议 `min_size=12`。
3. 使用局部 `open_filter` 区域调用 `click_in_region(open_filter)`。
4. 调用 `human_delay()`，等待筛选面板出现；不判断是否真的出现。
5. 框选“最近没看过”选项内部安全区域，建议 `min_size=12`。
6. 框选“筛选确定”按钮内部安全区域，建议 `min_size=12`。
7. 程序化按 Esc，最佳努力关闭筛选面板，恢复候选人列表基线。
8. 只有上述步骤全部无异常，才构造并发布 `BatchFilterRegions`，设置 `batch_filter_enabled=True`。

校准期间只允许导航点击“打开筛选”。“最近没看过”“筛选确定”和首位候选人都只框选，不点击，避免校准阶段提前改变筛选或进入详情页。

### 5.2 原子性和面板清理

四个区域先保存在局部变量。任一 `select_screen_region()` 抛出 `CalibrationCancelled`、等待被停止、点击异常或其他异常时：

- 不发布任何局部区域。
- `batch_filter_regions=None`。
- `batch_filter_enabled=False`。
- 若筛选面板可能已打开，则使用 `_programmatic_esc` 最佳努力关闭。
- 关闭失败只记录 warning，不做第二种关闭动作，不猜测页面状态。
- `batch_filter_calibration_attempted=True`，本次运行不自动反复弹框。
- 清除 `batch_filter_calibration_in_progress`。

校准成功后也必须先执行最佳努力关闭，再启用自动流程。若程序化 Esc 本身抛出异常，建议将本次校准视为失败并回退旧流程，因为后续完整点击序列需要从“筛选面板关闭”的已知操作基线开始。这里的“已知”仅指程序执行顺序，不代表页面状态检测。

### 5.3 与既有校准的关系

- 新校准发生在列表页，早于首位候选人详情打开。
- 首位候选人自动打开后，既有焦点恢复和完整转发点击校准仍在详情页按原顺序执行。
- OCR 区域仍由首次 `view_candidate()` 中的现有检测路径惰性校准。
- 不合并四个新区域与 `ForwardClickRegions`，避免列表导航和邮件转发配置耦合。

## 6. 启动阶段流程调整

建议将“打开本批首位候选人”封装为统一分支，而不是复制启动和批次逻辑：

```python
def open_first_candidate_for_batch(legacy_point=None):
    if batch_filter_enabled:
        return apply_batch_filter_and_open_first_candidate()
    return click_first_candidate(*legacy_point)
```

该 helper 只负责选择新旧路径，不修改现有 `click_first_candidate()`，以保留旧流程和已有测试。

### 6.1 普通交互模式且用户选择校准

推荐顺序：

```text
解析输入
→ 置前 Edge
→ 启动运行计时器（保持现有计时语义）
→ 执行四区域校准
→ 校准成功：不再要求人工摆放鼠标
→ apply_batch_filter_and_open_first_candidate()
→ 详情页稳定
→ 既有焦点恢复区域校准
→ 既有完整转发点击区域校准
→ view_candidate(0)，其中 OCR 仍按现有逻辑惰性校准
```

### 6.2 校准未请求、取消或失败

只有确认 `batch_filter_enabled=False` 后，才显示现有提示：

```text
请将鼠标移到第一位候选人卡片上，3 秒后开始...
```

随后等待并捕获一次 `pyautogui.position()`，整次运行继续使用旧固定点。不能在新校准之前捕获旧坐标，因为框选和校准导航会移动鼠标，导致捕获值失效。

### 6.3 `--auto`、命令行关键词与 `--no-forward`

- `--auto` 不询问、不弹框、不执行筛选校准导航，继续旧首位坐标流程。
- 现有 `get_user_input()` 在 `keywords_str` 非空时也走非交互分支；为避免命令行调用突然出现 Tk 框选，该路径默认禁用新功能。
- `--no-forward` 只禁止真实邮件转发，不应禁止普通交互模式下的新筛选校准和自动归位；两者职责独立。
- 无关键词的普通交互模式仍可启用新功能，只浏览、不 OCR、不转发。

### 6.4 自动筛选执行函数

新增 `apply_batch_filter_and_open_first_candidate()`：

```text
检查 stop_event、enabled 和完整 regions
→ click_in_region(open_filter)
→ human_delay
→ 再检查 stop_event
→ click_in_region(unseen_filter)
→ human_delay
→ 再检查 stop_event
→ click_in_region(confirm_filter)
→ 等待列表刷新
→ 再检查 stop_event
→ click_in_region(first_candidate)
→ 等待详情页稳定
→ 返回 True
```

所有点击都必须经 `click_in_region()`，从运行期区域取点并最终使用 `human_click(..., offset=0)`。函数不识别页面，不读文字，不重试同一步骤，不点击其他兜底坐标。

若运行中出现点击异常或等待中断，记录具体步骤并返回 `False`，主循环安全停止。此时不能中途切换到旧坐标：筛选面板可能处于未知打开状态，盲点首位区域可能误点面板内容。

## 7. 每批次刷新后的流程调整

保留现有 100 人循环、`next_candidate()` 和 `refresh_page()`。推荐主循环结构：

```text
while not stop_event:
    open_first_candidate_for_batch()
    首次详情校准（现有 attempted 状态保证只执行一次）

    for i in range(BATCH_SIZE):
        view_candidate(i)
        非最后一位时 next_candidate()

    forward_consecutive = 0
    refresh_page()
    记录累计数量
    # 下一轮 while 顶部重新筛选并打开首位
```

启用新功能时，第二轮及以后由 `apply_batch_filter_and_open_first_candidate()` 完整执行筛选和首位点击。禁用时仍调用原有 `click_first_candidate(legacy_x, legacy_y)`。

### 7.1 批次边界的精确顺序验收

测试应把 `BATCH_SIZE` patch 为 2 或 3，并记录事件，至少验证：

```text
首次 apply-filter/open-first
→ view(0)
→ next
→ view(1)
→ refresh
→ 第二次 apply-filter/open-first
→ 下一批 view(0)
```

`refresh` 必须先于第二次 `open_filter`；第二次 `first_candidate` 必须晚于 `confirm_filter` 和列表刷新等待。不得在批次最后一位后额外按右方向键。

### 7.2 不完整批次和停止

本 issue 不改变现有 `view_candidate()` / `next_candidate()` 的 break 语义。任意等待返回 `False` 或 `stop_event=True` 时，不开始新的筛选动作。若现有循环在非 stop 的 `view_candidate=False` 后仍刷新，该行为应先由回归测试记录；除非测试证明会触发本需求新增的危险点击，否则不在本 issue 顺带重构。

## 8. 回退策略

### 8.1 校准阶段回退

以下任一情况禁用本次自动筛选归位：

- 用户选择不校准。
- 任一四区域按 Esc。
- 框选区域过小或区域选择器异常。
- 校准导航点击“打开筛选”异常。
- 校准导航等待被停止。
- 筛选面板最佳努力关闭抛出异常。

回退后：

- 清空全部新区域，不保留部分成功结果。
- 不退出程序。
- 提示用户重新把鼠标放到首位候选人卡片。
- 延续现有一次捕获 `(click_x, click_y)`、每批 F5、固定坐标点首位的流程。
- 不影响焦点恢复、完整转发、OCR 或关键词状态。

### 8.2 运行阶段失败

校准成功但批次运行中某一步点击或等待失败时，建议安全停止主循环，而不是自动回退旧流程。原因是页面可能停留在筛选面板中间状态，没有页面检测时无法证明旧首位坐标仍安全。

### 8.3 重启回退

全部新区域仅在内存中保存。窗口移动、系统/浏览器缩放、分辨率、页面布局变化后，用户必须停止程序、恢复合适页面并重新启动校准。

## 9. 延迟与等待策略

建议新增命名常量，数值最终以安全实机验证调整：

```python
FILTER_OPEN_DELAY_MIN = 0.5
FILTER_OPEN_DELAY_MAX = 1.0
FILTER_OPTION_DELAY_MIN = 0.3
FILTER_OPTION_DELAY_MAX = 0.7
FILTER_RESULTS_DELAY_MIN = 2.0
FILTER_RESULTS_DELAY_MAX = 3.0
```

执行策略：

| 动作 | 等待建议 | 原因 |
| --- | --- | --- |
| 点击打开筛选后 | `human_delay(0.5, 1.0)` | 给面板展开动画留时间 |
| 点击最近没看过后 | `human_delay(0.3, 0.7)` | 给选中状态留时间 |
| 点击筛选确定后 | `human_delay(2.0, 3.0)` | 给候选人列表刷新留时间 |
| 点击首位候选人后 | 复用 `safe_wait(CLICK_WAIT_SECONDS)` | 保持现有详情稳定等待 |
| 批次 F5 后 | 保留 `safe_wait(REFRESH_WAIT_SECONDS)` | 不改变现有刷新行为 |

`human_delay()` 和 `safe_wait()` 都能响应暂停/停止。每次等待返回 `False` 后必须立即中止后续点击。第一版不轮询加载状态、不根据网络速度自适应、不自动重试。

## 10. 测试计划

测试主要放在 `tests/test_simple_brush_ocr.py`，尽管文件名带 OCR，它当前已经覆盖主循环、校准、导航和转发安全门。若新增测试过多，可在不改变测试发现方式的前提下拆出 `tests/test_batch_filter.py`。

所有测试必须 mock：

- `select_screen_region`
- `click_in_region`
- `human_delay` / `safe_wait`
- `pyautogui.position` / `pyautogui.press` / `pyautogui.click`
- `listener.start`、`bring_edge_foreground`
- 任何可能到达 OCR、剪贴板或转发的调用

不得出现真实 GUI、鼠标、键盘、剪贴板或邮件转发。

### 10.1 数据结构与 reset

- `BatchFilterRegions` 保存四个独立 `ScreenRegion`。
- `reset_batch_filter_calibration()` 清空 regions、requested、attempted、in-progress、enabled。
- 重复调用 `run()` 不复用上次运行区域。
- 校准期间 Esc 交给 Tk，不设置 `stop_event`。

### 10.2 校准成功

- `select_screen_region()` 按 first candidate、open filter、unseen filter、confirm filter 顺序调用。
- 校准期间只调用一次 `click_in_region(open_filter)`。
- 不点击 first candidate、unseen filter 或 confirm filter。
- 打开筛选后调用规定等待。
- 程序化 Esc 不触发全局停止。
- 四项全部成功后一次性发布，`enabled=True`。
- 第二次调用不会重新弹框。

### 10.3 校准取消与失败

参数化覆盖在第 1、2、3、4 个区域取消。

- 任何位置取消都清空整组区域并禁用功能。
- 面板已打开时尝试程序化 Esc；未打开时不发送多余 Esc。
- 普通异常同样原子回退并记录，不向外抛出导致程序退出。
- `attempted=True`，后续调用不重复框选。
- 关闭面板异常时功能保持禁用。

### 10.4 自动筛选 helper

- 点击顺序严格为 open filter、unseen filter、confirm filter、first candidate。
- 每次点击参数都是对应运行期 `ScreenRegion`。
- 通过 `click_in_region()` 间接验证区域内取点和 `offset=0`；保留其已有单元测试。
- open/option/results/detail 等待顺序正确。
- 任一步等待返回 `False` 时不执行后续点击。
- 任一步点击抛出异常时返回 `False`，不调用旧首位坐标。
- disabled 或 regions 缺失时不执行任何新点击。

### 10.5 启动调用顺序

成功路径事件：

```text
bring_edge
→ batch_filter_calibrate
→ open_filter
→ unseen_filter
→ confirm_filter
→ first_candidate
→ focus_restore_calibrate（如请求）
→ forward_click_calibrate（如请求）
→ view(0)
```

回退路径事件：

```text
batch_filter_calibrate（取消/失败）
→ legacy countdown
→ pyautogui.position
→ click_first_candidate(legacy point)
→ 既有详情校准
→ view(0)
```

另覆盖：

- `--auto` 不询问、不框选、不执行筛选导航。
- `--no-batch-filter` 不询问、不框选。
- CLI keywords 非交互路径不突然弹框。
- 无关键词普通交互模式仍可选择校准。
- `--no-forward` 不妨碍筛选校准，但仍不调用真实转发。

### 10.6 批次边界调用顺序

- patch `BATCH_SIZE=2`，验证首次和刷新后各调用一次完整筛选 helper。
- 验证 `view(0) → next_candidate → view(1) → refresh_page → filter/open first → view(0)`。
- 验证最后一位后不调用 `next_candidate()`。
- 验证 `refresh_page=False` 后不执行下一批筛选。
- 验证筛选 helper 返回 `False` 后不进入下一批 `view_candidate()`。
- 验证 `forward_consecutive` 仍在批次刷新点归零。

### 10.7 全量回归

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
git diff --check
```

重点确认现有 OCR、关键词、转发、双击焦点恢复、`--no-forward`、计时停止和校准测试全部通过。

手工测试不属于自动验收的替代品。如后续进行，只能在受控 Windows Edge + BOSS 页面、小规模、人工监控环境中使用；先以无关键词或 `--no-forward` 验证导航，不进行真实转发。

## 11. 变更步骤

### Change 1：运行期区域状态与原子校准

修改文件：

- `simple_brush.py`
- `tests/test_simple_brush_ocr.py` 或新增 `tests/test_batch_filter.py`

内容：

- 新增 `BatchFilterRegions` 和运行期状态。
- 新增 reset、requested/attempted/in-progress/enabled 管理。
- 新增 `ensure_batch_filter_regions_calibrated()`。
- 复用 `select_screen_region()`、`click_in_region()`、`human_delay()` 和程序化 Esc。
- 增加 `--no-batch-filter` 参数及交互/非交互决策。
- 扩展 Esc 校准隔离。
- 覆盖成功、各阶段取消、异常、原子提交和不重复尝试。

验收：四区域全部成功才启用；失败不退出；校准阶段不点击确定或首位候选人；无真实 GUI 调用。

建议 commit：

```text
feat: calibrate batch filter navigation regions
```

### Change 2：启动筛选与首位候选人归位

修改文件：

- `simple_brush.py`
- 对应主循环/导航测试

内容：

- 新增 `apply_batch_filter_and_open_first_candidate()`。
- 新增统一新旧路径 helper。
- 调整首次首位候选人打开前后的顺序。
- 成功校准时取消人工鼠标位置依赖。
- 取消/失败时在校准结束后才执行旧倒计时和坐标捕获。
- 保持详情页上的焦点恢复、完整转发点击和 OCR 校准顺序。

验收：启动调用顺序正确；所有新点击使用运行期区域；等待中断后无后续点击；旧流程完整可用。

建议 commit：

```text
feat: apply unseen filter before opening first candidate
```

### Change 3：100 人边界接入、文档与全量回归

修改文件：

- `simple_brush.py`
- 批次边界测试
- `README.md`

内容：

- 在现有 F5 刷新后的下一轮入口重新执行完整筛选归位。
- 保持 `BATCH_SIZE`、`refresh_page()`、`next_candidate()` 和 `forward_consecutive` 语义。
- 增加批次顺序、停止、失败测试。
- README 说明四区域顺序、运行期限制、`--auto`、`--no-batch-filter` 和旧流程回退。
- 运行全量测试及范围检查。

验收：每个完整批次后执行一次筛选并打开首位；禁用时仍走旧流程；无 OCR、关键词、转发、打包或 macOS 变更。

建议 commit：

```text
feat: reapply unseen filter at batch boundaries
```

如希望文档与行为提交严格分离，可将 README 单独提交，但不得把业务范围扩展为第四个功能 Change。

## 12. 风险与回滚方案

### 12.1 主要风险

- **无页面状态检测**：程序无法确认筛选面板是否打开、选项是否选中、确定是否生效或列表是否刷新，只能依赖操作顺序和等待。
- **校准基线不确定**：校准“最近没看过”和“确定”需要先打开筛选面板。校准后程序化 Esc 只能最佳努力关闭；若 BOSS 改变 Esc 行为，首次完整序列可能从错误状态开始。
- **重复刷新**：现有 F5 后再点击筛选确定可能产生两次列表刷新。第一版为保持旧流程而接受该风险，实机需观察加载时间和列表稳定性。
- **页面布局变化**：区域是绝对物理屏幕坐标。窗口移动、缩放、DPI、分辨率、侧栏宽度或 BOSS UI 更新都会使区域失效。
- **随机点误触**：框选范围若覆盖邻近控件，随机点可能落到错误元素。提示必须强调只框选按钮/卡片内部安全区域。
- **筛选选项可能是切换态**：若“最近没看过”是 toggle 且页面保留上次选中状态，每批再次点击可能取消选择。由于需求禁止状态检测，必须通过实机确认该控件是幂等选择还是每次面板初始状态稳定；这是实现前最高优先级的产品风险。
- **首位候选人位置变化**：筛选后空结果、加载骨架、广告卡片或列表布局变化都可能让首位区域不再对应候选人；程序不会识别。
- **等待不足或过长**：网络慢时固定随机等待可能提前点击；等待过长会降低批次效率。
- **运行中失败无法安全回退**：面板可能处于中间状态，不能盲目改走旧坐标，只能停止。
- **无关键词路径**：新功能与 OCR 独立，输入交互和测试必须避免错误地以 `forward_enabled` 作为启用条件。
- **CLI 兼容性**：现有 `keywords_str` 会进入非交互分支；不能让已有自动脚本突然弹 Tk 校准层。

### 12.2 实施前必须人工确认的 UI 事实

在不引入自动状态识别的前提下，至少人工确认一次：

1. “打开筛选”点击后，Esc 能稳定关闭面板且不会退出 BOSS 页面。
2. “最近没看过”重复进入筛选面板时是可重复选择的确定项，而不是点击一次开、下一次关且状态跨批次保留的 toggle。
3. 点击“筛选确定”后，首位候选人卡片回到同一可校准区域。

若第 2 项不成立，本需求在“不做状态检测”的边界下无法安全保证每批筛选，应停止实施并重新确认产品交互，而不是猜测点击。

### 12.3 回滚方案

- 三个 Change 独立提交，可按逆序回滚。
- 运行时可通过 `--no-batch-filter` 或交互选择不校准，立即回到旧流程。
- Change 3 出现批次问题时，可回滚批次接入，保留尚未启用的校准/启动 helper。
- Change 2 出现启动问题时，可回滚启动接入，旧 `click_first_candidate(x, y)` 保持可用。
- Change 1 整体回滚后，现有校准、OCR、转发和批次刷新行为应完全恢复。
- 不修改或移动 Windows stable tag/分支；本功能验收前不得进入稳定发布。

## 13. 验收标准

| 验收项 | 通过条件 |
| --- | --- |
| 四区域校准 | 启动后可依次框选首位候选人、打开筛选、最近没看过、筛选确定 |
| 原子发布 | 四项全部成功才设置 regions 和 enabled，不存在部分配置 |
| 校准导航安全 | 校准期间只点击打开筛选，不点击最近没看过、确定或首位候选人 |
| 校准取消 | 任一阶段 Esc 均禁用新功能但不退出程序，并只尝试一次 |
| 校准失败 | 异常时清空整组区域、最佳努力关闭面板并进入旧流程 |
| 启动自动筛选 | 成功校准后按 open → unseen → confirm → first candidate 顺序点击 |
| 首位区域点击 | 点击从运行期 `ScreenRegion` 取点，经 `click_in_region()` 使用 `offset=0` |
| 详情校准衔接 | 首位详情稳定后才进入既有焦点恢复和完整转发点击校准 |
| OCR 衔接 | OCR 仍由既有首次 view 路径校准和检测，无算法修改 |
| 批次边界 | 每完成 100 人并 F5 成功后，下一批前再次执行完整筛选归位 |
| 右方向键 | 批内仍由现有 `next_candidate()` 切换，最后一位后不多按一次 |
| 旧流程回退 | 禁用、拒绝、取消或校准失败时继续一次捕获坐标的旧流程 |
| 非交互安全 | `--auto`、CLI keywords 和 `--no-batch-filter` 不弹新增框选层 |
| 无关键词 | 普通交互浏览仍可选择筛选校准，不依赖转发关键词 |
| 等待中断 | 任一等待返回 False 后不执行后续新点击 |
| 运行中异常 | 不盲目切换旧坐标，安全停止当前主循环 |
| 测试隔离 | 自动测试不调用真实 GUI、键鼠、剪贴板、OCR 或转发 |
| 回归 | 全量测试和 `git diff --check` 通过 |
| 非目标 | 未修改 OCR、关键词、转发内部、打包或 macOS Chrome 逻辑 |
| 禁止技术 | 未引入 DOM、文字识别、Selenium、Playwright、WebDriver 或页面状态检测 |
