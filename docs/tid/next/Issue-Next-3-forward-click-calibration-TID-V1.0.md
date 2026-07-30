# [Next-3] TID V1.0：转发流程全部关键点击点启动前校准

## 1. 目标与范围

### 1.1 目标

将 `forward_one_candidate()` 中仍依赖固定屏幕坐标的五类关键点击改为运行期区域点击，并在普通交互模式下允许用户于第一位候选人详情页打开后、首次真实转发前完成引导式校准：

1. `FORWARD_ICON_X/Y`
2. `EMAIL_TAB_X/Y`
3. `INPUT_BOX_X/Y`
4. `RECENT_EMAIL_X/Y`
5. `FORWARD_BTN_X/Y`

每个对象使用小型 `ScreenRegion`，实际点击点由 `random_point_in_region()` 从运行期区域内选择，并调用 `human_click(..., offset=0)`，避免区域取点后再次偏移越界。

未校准、用户跳过、校准取消或校准失败时，必须回退到由现有坐标和现有偏移范围推导出的默认区域，保持当前 Windows Edge 点击行为。

Next-1 已完成的 `DEFAULT_FOCUS_RESTORE_REGION`、运行期状态、区域选择器和统一 `finally` 焦点恢复继续复用，不重新设计或移除。

### 1.2 本轮范围

- 完整盘点当前邮件转发固定坐标及调用位置。
- 为五类实际转发点击建立默认区域和运行期区域。
- 普通交互模式提供一次完整转发点击校准选择。
- 在首位候选人详情可见后执行逐步引导校准。
- 复用现有区域框选、DPI 换算、区域内取点和运行期回退设计。
- 将五类固定坐标调用替换为运行期区域点击。
- 增加默认、校准、取消、失败、`--auto`、`--no-forward` 和转发路径测试。
- 更新 README。

### 1.3 非目标

- 不处理 macOS Chrome。
- 不处理关键词规则。
- 不实现 P3 候选人日志或 P4 数值匹配。
- 不读取 DOM。
- 不引入 Selenium、Playwright、WebDriver 或其他浏览器自动化驱动。
- 不新增页面状态识别。
- 不检测转发成功或失败。
- 不重构整体转发流程。
- 不持久化校准配置。
- 不自动识别按钮边界、颜色、文字或弹窗状态。
- 不删除 `RIGHT_CLICK_X/Y`；本 TID 只标记其当前状态。

## 2. 当前转发坐标盘点

当前分支为 `main`，本地与 `origin/main` 一致，分析前工作区干净。目标 GitHub Issue 为 Open 的 Issue #5。

| 常量/区域 | 当前默认值 | UI 意义 | 文件/函数 | 当前是否支持校准 | 是否纳入本 Issue |
| --- | --- | --- | --- | --- | --- |
| `FORWARD_ICON_X/Y` | `(1670, 260)` | 顶部右上角转发图标 / 转发牛人入口 | `simple_brush.py` / `forward_one_candidate()` 步骤 1 | 否；调用 `human_click()` 默认 `offset=5` | 是 |
| `EMAIL_TAB_X/Y` | `(700, 600)` | 弹窗左侧“邮件转发”Tab | `simple_brush.py` / `forward_one_candidate()` 步骤 2 | 否；默认 `offset=5` | 是 |
| `INPUT_BOX_X/Y` | `(900, 390)` | 弹窗顶部邮箱输入框 | `simple_brush.py` / `forward_one_candidate()` 步骤 3 | 否；实际有两处调用，均显式 `offset=3` | 是 |
| `RECENT_EMAIL_X/Y` | `(1000, 440)` | 最近联系人区域右侧第一个邮箱标签 / 最近转发对象 | `simple_brush.py` / `forward_one_candidate()` 步骤 3 | 否；默认 `offset=5` | 是 |
| `FORWARD_BTN_X/Y` | `(1210, 740)` | 弹窗右下角“转发”按钮 | `simple_brush.py` / `forward_one_candidate()` 步骤 4 | 否；默认 `offset=5` | 是 |
| `RIGHT_CLICK_X/Y` | `(960, 500)` | 注释为转发后恢复键盘焦点位置 | `simple_brush.py` 常量区；当前无调用 | 否；已被 Next-1 的区域焦点恢复路径替代 | 否；标记为遗留常量，不在本 Issue 删除 |
| `DEFAULT_FOCUS_RESTORE_REGION` | `left=400, top=350, width=101, height=51` | 候选人详情页空白区域 / 转发函数退出前统一恢复焦点 | `simple_brush.py` / `forward_one_candidate()` 唯一 `finally` | 是；Next-1 已实现运行期校准 | 复用现状，不重做 |

### 2.1 实际点击顺序

当前 `forward_one_candidate()` 的点击顺序为：

1. `FORWARD_ICON_X/Y`
2. `EMAIL_TAB_X/Y`
3. `RECENT_EMAIL_X/Y`
4. `INPUT_BOX_X/Y`，用于读取当前邮箱内容
5. 如需要备选邮箱，再次点击 `INPUT_BOX_X/Y`
6. `FORWARD_BTN_X/Y`
7. 所有退出路径在 `finally` 中从 `focus_restore_region` 取点恢复焦点

本 Issue 只替换坐标来源，不改变上述业务顺序、等待时间、剪贴板检查、返回值或统一焦点恢复结构。

### 2.2 RIGHT_CLICK 状态

全仓检索显示 `RIGHT_CLICK_X` 和 `RIGHT_CLICK_Y` 只在常量区定义，没有任何读取或点击调用。实际焦点恢复已经由：

```python
focus_x, focus_y = random_point_in_region(focus_restore_region)
human_click(focus_x, focus_y, offset=0)
```

完成。因此 `RIGHT_CLICK_X/Y` 是遗留常量或待清理项，不需要纳入校准。本 Issue 不擅自删除；后续若清理，应作为独立、低风险维护 change，并先确认没有外部脚本依赖。

## 3. 当前 Next-1 校准机制复用分析

### 3.1 可直接复用的数据结构

`ocr_calibration.py` 中已有：

```python
@dataclass(frozen=True)
class ScreenRegion:
    left: int
    top: int
    width: int
    height: int
```

该结构已用于 OCR 区域和焦点恢复区域，可以直接表示每个转发点击小区域，不新增重复坐标类型。

### 3.2 可直接复用的区域选择器

`select_screen_region()` 已支持：

- 主显示器 Tk 半透明覆盖层。
- 自定义 `instruction` 和 `subtitle`。
- 自定义 `min_size`。
- Windows DPI awareness。
- Tk overlay 坐标到物理像素坐标换算。
- Esc 取消并抛出 `CalibrationCancelled`。

五个点击对象可复用该函数，建议 `min_size=12` 或 `20`。为避免框选过大，提示文字必须明确要求“只框选按钮/输入框内部安全点击区域”。本 Issue 不增加视觉校验。

### 3.3 可复用的区域内取点

`random_point_in_region(region)` 已按半开区间语义从区域内取点，并拒绝非正尺寸区域。所有新区域点击应复用它，再调用：

```python
human_click(x, y, offset=0)
```

不能继续叠加 `human_click()` 的默认偏移，否则可能越出用户框选区域。

### 3.4 可复用的运行期状态模式

Next-1 已采用：

- 默认区域常量。
- 当前运行期区域。
- requested / attempted / in_progress 状态。
- 每次 `run()` 开始重置。
- 取消和异常时回退默认区域。
- `--auto` 不请求校准。
- 校准期间 Esc 由 Tk 处理，不停止浏览。

完整转发校准应采用相同模式，但五个新区域建议作为一份原子配置管理，避免部分使用校准值、部分使用未知值。

### 3.5 不直接复用的部分

`ensure_focus_restore_region_calibrated()` 只负责单个详情页空白区域，不能直接承担需要逐步打开弹窗、切换 Tab 的五阶段流程。应复用其基础设施和失败策略，但新增独立的完整转发校准协调函数，不把多阶段 UI 导航塞入焦点恢复函数。

## 4. 校准对象设计

### 4.1 配置结构

建议新增 frozen dataclass：

```python
@dataclass(frozen=True)
class ForwardClickRegions:
    forward_icon: ScreenRegion
    email_tab: ScreenRegion
    input_box: ScreenRegion
    recent_email: ScreenRegion
    forward_button: ScreenRegion
```

运行期状态：

```python
DEFAULT_FORWARD_CLICK_REGIONS = ForwardClickRegions(...)
forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
forward_click_calibration_requested = False
forward_click_calibration_attempted = False
forward_click_calibration_in_progress = False
```

配置只保存在内存中，每次 `run()` 开始恢复默认值。

### 4.2 默认区域

为严格保持当前点击行为，默认区域不应随意扩大。当前 `human_click()` 对四类坐标默认使用 `±5` 偏移，对 `INPUT_BOX` 使用 `±3`。因此建议把现有实际点击范围等价转换为区域：

| 对象 | 当前中心点与偏移 | 建议默认区域 | 实际覆盖范围 |
| --- | --- | --- | --- |
| `forward_icon` | `(1670,260) ±5` | `ScreenRegion(1665,255,11,11)` | X `1665-1675`，Y `255-265` |
| `email_tab` | `(700,600) ±5` | `ScreenRegion(695,595,11,11)` | X `695-705`，Y `595-605` |
| `input_box` | `(900,390) ±3` | `ScreenRegion(897,387,7,7)` | X `897-903`，Y `387-393` |
| `recent_email` | `(1000,440) ±5` | `ScreenRegion(995,435,11,11)` | X `995-1005`，Y `435-445` |
| `forward_button` | `(1210,740) ±5` | `ScreenRegion(1205,735,11,11)` | X `1205-1215`，Y `735-745` |

这样在未校准和 `--auto` 模式下，区域内随机取点与当前中心点加偏移的有效范围一致。调用端统一改为 `offset=0`，避免双重随机。

若实现阶段认为“回退固定中心点”比保留现有抖动更安全，也可使用 `1×1` 默认区域，但这会改变当前行为，必须在实现前明确并补充回归测试。本 TID 推荐等价保留现有有效范围。

### 4.3 校准后区域

用户框选小型安全区域，结果直接写入临时 `ForwardClickRegions`。所有五项都成功后，才一次性替换全局 `forward_click_regions`。

建议采用原子提交策略：

- 任一步取消或失败，丢弃本轮五项临时结果。
- 五项全部回退 `DEFAULT_FORWARD_CLICK_REGIONS`。
- 不保留半完成配置。
- Next-1 的 `focus_restore_region` 独立保留其既有成功或默认状态。

原子策略便于测试和解释，也避免用户误以为五项全部完成而实际混用未知区域。

### 4.4 校准必要性

| 对象 | 是否必须提供校准能力 | 原因 |
| --- | --- | --- |
| `forward_icon` | 是 | 打开转发弹窗的入口，也是后续校准导航前置步骤 |
| `email_tab` | 是 | 切换到邮件转发界面，决定后三项是否可见 |
| `input_box` | 是 | 实际点击两次，影响邮箱读取和备选邮箱输入 |
| `recent_email` | 是 | 尝试填入最近联系人邮箱 |
| `forward_button` | 是 | 真实发送动作，误点风险最高 |
| `focus_restore_region` | 已有 | 继续使用 Next-1 机制 |
| `RIGHT_CLICK_X/Y` | 否 | 当前未调用 |

## 5. 交互流程设计

### 5.1 普通交互模式

建议将当前只询问焦点恢复区域的启动问题升级为一个完整校准入口，避免连续出现两个含义相近的问题：

```text
是否校准完整邮件转发点击区域（包含焦点恢复区域）？[y/N]
```

选择 `y`：

- 设置 `forward_click_calibration_requested=True`。
- 复用 Next-1，设置 `focus_restore_calibration_requested=True`。
- 实际框选延迟到第一位候选人详情打开后。

选择空输入或 `n`：

- 五个转发点击对象使用默认区域。
- 焦点恢复继续使用默认区域。
- 不弹出任何新增框选层。

如果实现阶段为了降低改动选择保留 Next-1 原问题，也可以增加独立的“是否校准其余五个转发点击区域”问题，但会产生重复交互。优先推荐单一完整校准入口，同时保持现有状态变量和函数复用。

### 5.2 首位详情打开后的引导顺序

五个对象不会同时出现在同一页面，因此不能在程序启动、详情页尚未打开时一次框选。建议程序按现有 UI 操作顺序引导，不依赖页面状态识别：

1. 第一位候选人详情页打开。
2. 先调用现有 `ensure_focus_restore_region_calibrated()`，框选详情页安全空白区域。
3. 框选 `FORWARD_ICON` 小区域。
4. 从刚框选的 `FORWARD_ICON` 区域取点，仅用于打开转发弹窗。
5. 等待现有固定时长，不判断弹窗状态。
6. 框选 `EMAIL_TAB` 小区域。
7. 从刚框选的 `EMAIL_TAB` 区域取点，进入邮件转发界面。
8. 等待现有固定时长，不判断 Tab 状态。
9. 依次框选 `INPUT_BOX`、`RECENT_EMAIL`、`FORWARD_BTN` 的内部安全区域。
10. 不点击 `FORWARD_BTN`；框选覆盖层会拦截拖动，不触发底层真实发送。
11. 使用程序化 Esc 关闭弹窗，避免触发全局停止监听。
12. 五项全部成功后原子写入运行期配置。
13. 开始正常 OCR 浏览流程。

这种方式由程序逐步引导进入对应 UI，不要求用户手动在终端和浏览器之间猜测状态；同时只执行现有点击序列中的“打开入口”和“切换 Tab”，不执行发送动作。

### 5.3 无页面状态识别约束

程序不能判断弹窗或 Tab 是否真的打开。每一步仅：

- 输出明确提示。
- 使用现有等待时长。
- 显示区域选择层。
- 允许用户按 Esc 取消并回退。

如果页面未进入预期状态，用户应取消本轮校准。不得为提高自动化程度新增截图识别、DOM 读取或转发结果判断。

### 5.4 `--auto` 模式

`--auto` 必须：

- 不调用新增 `input()`。
- 不显示新增框选层。
- 不执行校准导航点击。
- 使用 `DEFAULT_FORWARD_CLICK_REGIONS`。
- 焦点恢复继续使用 Next-1 默认区域。

本 Issue 不新增命令行区域参数或配置文件。

### 5.5 `--no-forward` 模式

普通交互方式的 `--no-forward` 可以用于安全验证完整校准：

- 允许询问和显示框选层。
- 校准导航可点击 `FORWARD_ICON` 和 `EMAIL_TAB` 以展示控件。
- 只框选 `FORWARD_BTN`，绝不点击它。
- 校准结束后用 Esc 关闭弹窗。
- 后续 OCR 命中仍不会调用 `forward_one_candidate()`。

因此 `--no-forward` 可安全验证校准交互、区域记录和默认回退，但不能验证真实转发路径使用这些区域。真实路径由 mock 测试覆盖，最终只做极小规模人工验证。

### 5.6 取消与失败

- 用户在任意新区域框选时按 Esc：取消完整五项校准，全部回退默认区域。
- Tk、DPI、显示器或点击导航异常：记录异常，全部回退默认区域。
- 尝试使用程序化 Esc 关闭可能已打开的弹窗。
- 不设置 `stop_event`。
- 本次运行不重复弹出校准。
- 不禁用 OCR 或转发；继续使用默认区域。

## 6. 技术方案

### 6.1 新增运行期配置与通用点击助手

在 `simple_brush.py` 中新增 `ForwardClickRegions`、默认配置和运行期状态。

新增助手：

```python
def click_in_region(region):
    x, y = random_point_in_region(region)
    human_click(x, y, offset=0)
```

该助手只负责区域内点击，不做页面状态判断或等待。

### 6.2 替换固定坐标调用

`forward_one_candidate()` 中仅替换坐标来源：

```python
click_in_region(forward_click_regions.forward_icon)
click_in_region(forward_click_regions.email_tab)
click_in_region(forward_click_regions.recent_email)
click_in_region(forward_click_regions.input_box)
click_in_region(forward_click_regions.forward_button)
```

`input_box` 的两处点击都必须使用同一个运行期区域。

保留：

- 转发步骤顺序。
- `human_delay()` 和现有时间参数。
- 剪贴板检查。
- 备选邮箱输入。
- 连续转发限制。
- 返回值和异常行为。
- `finally` 中唯一焦点恢复点击。

### 6.3 默认常量关系

现有 X/Y 常量继续作为默认区域的来源，避免复制魔法数字：

```python
DEFAULT_FORWARD_CLICK_REGIONS = ForwardClickRegions(
    forward_icon=region_around(FORWARD_ICON_X, FORWARD_ICON_Y, 5),
    email_tab=region_around(EMAIL_TAB_X, EMAIL_TAB_Y, 5),
    input_box=region_around(INPUT_BOX_X, INPUT_BOX_Y, 3),
    recent_email=region_around(RECENT_EMAIL_X, RECENT_EMAIL_Y, 5),
    forward_button=region_around(FORWARD_BTN_X, FORWARD_BTN_Y, 5),
)
```

可增加纯函数：

```python
def region_around(x, y, radius):
    return ScreenRegion(x - radius, y - radius, radius * 2 + 1, radius * 2 + 1)
```

测试必须验证范围与旧 `human_click` 偏移一致。

### 6.4 校准协调函数

建议新增：

```python
def reset_forward_click_calibration()
def ensure_forward_click_regions_calibrated()
```

`ensure_forward_click_regions_calibrated()`：

- 未请求时直接返回默认/当前配置。
- 已尝试时不重复。
- 使用局部变量收集五个区域。
- 只在全部成功时写入全局配置。
- 取消或失败时恢复默认配置。
- `finally` 恢复 in-progress 状态并关闭弹窗。

### 6.5 Esc 处理

`on_press()` 增加 `forward_click_calibration_in_progress` 判断，使校准期间 Esc 交给 Tk，而不是停止主循环。

关闭弹窗继续复用 `_programmatic_esc`，避免程序发送的 Esc 触发全局停止。

### 6.6 接入时机

在 `run()`：

1. 启动时重置完整转发校准状态。
2. `get_user_input()` 只记录请求，不显示框选层。
3. 第一位 `click_first_candidate()` 成功后执行完整校准。
4. 校准完成或回退后再进入首次 `view_candidate()`。

该时机与 Next-1 一致，确保详情页可见，并早于首次可能的真实转发。

## 7. 技术步骤拆解

### Change 1：默认区域配置和区域点击基础设施

修改文件：

- `simple_brush.py`
- `tests/test_simple_brush_ocr.py`

内容：

- 新增 `ForwardClickRegions`。
- 新增 `region_around()`。
- 从现有常量和偏移生成五个默认区域。
- 新增运行期配置和 reset 函数。
- 新增 `click_in_region()`。
- 暂不替换转发流程调用。

验收：

- 五个默认区域严格等价于现有中心点与偏移范围。
- 区域点击只随机一次并使用 `offset=0`。
- 每次运行重置为默认配置。
- 不修改 Next-1 状态和行为。

### Change 2：完整转发点击区域引导校准

修改文件：

- `simple_brush.py`
- `tests/test_simple_brush_ocr.py`

内容：

- 新增 requested / attempted / in-progress 状态。
- 增加普通模式完整校准询问。
- 新增 `ensure_forward_click_regions_calibrated()`。
- 按顺序框选并引导打开弹窗和邮件 Tab。
- 成功时原子提交五项配置。
- 取消/失败时全部回退默认配置。
- 程序化 Esc 关闭弹窗。
- `--auto` 不交互、不框选、不执行导航点击。
- `--no-forward` 允许安全校准但不点击发送按钮。

验收：

- 框选顺序和导航顺序正确。
- `FORWARD_BTN` 在校准期间从不被点击。
- 取消和异常不设置 `stop_event`。
- 同一运行只尝试一次。
- 第一位详情打开失败时不校准。

### Change 3：转发流程接入运行期区域

修改文件：

- `simple_brush.py`
- `tests/test_simple_brush_ocr.py`

内容：

- 将五类固定坐标点击替换为 `click_in_region()`。
- 两处 `INPUT_BOX` 调用均接入同一区域。
- 不改等待、剪贴板、返回值或异常结构。
- 保持 Next-1 唯一 `finally` 焦点恢复。

验收：

- 默认配置覆盖当前点击范围。
- 校准配置被所有对应步骤使用。
- 早退和异常路径仍只恢复一次焦点。
- 其他转发行为不变。

### Change 4：README

修改文件：

- `README.md`

内容：

- 说明完整转发点击校准对象和交互顺序。
- 说明结果只在当前运行有效。
- 说明取消/失败和 `--auto` 默认回退。
- 说明校准后不要移动或缩放窗口。
- 说明 `--no-forward` 能验证的范围。
- 强调真实转发只允许测试账号、测试邮箱、小规模、人工监控。
- 明确其余平台适配仍未完成。

### Change 5：全量回归和范围验收

- 运行全量测试。
- 检查累计 diff 和非目标范围。
- 核对 `RIGHT_CLICK_X/Y` 未被误接入或擅自删除。
- 核对 Next-1 焦点恢复测试全部通过。
- 无文件变更时不创建空 commit。

## 8. 测试计划

### 8.1 单元测试

- `region_around(1670,260,5)` 等于 `ScreenRegion(1665,255,11,11)`。
- `INPUT_BOX` 默认区域使用半径 3，其余使用半径 5。
- 所有默认区域包含原中心点和原偏移边界。
- `ForwardClickRegions` 为不可变配置。
- reset 恢复全部默认区域和状态。
- `click_in_region()` 调用 `random_point_in_region()` 一次。
- `human_click()` 收到 `offset=0`。

### 8.2 校准 mock 测试

- 成功时按 `focus_restore → forward_icon → click icon → email_tab → click tab → input_box → recent_email → forward_button` 顺序执行。
- 五项全部成功后才替换运行期配置。
- 任一步 Esc 取消时全部五项回退默认配置。
- 任一步异常时全部五项回退默认配置。
- 取消和失败后 in-progress 状态恢复。
- 同一运行只尝试一次。
- 校准期间 Esc 不设置 `stop_event`。
- 结束时程序化 Esc 不触发停止。
- 校准过程中不点击 `forward_button`。
- 第一位详情打开失败时不校准。

### 8.3 转发流程 mock 测试

- 成功路径依次使用五个运行期区域。
- `INPUT_BOX` 第一次读取和备选邮箱路径第二次输入都使用 `input_box` 区域。
- 默认配置路径使用默认区域。
- 校准配置路径使用用户区域。
- 连续转发上限、等待中断、无备选邮箱、异常路径保持原行为。
- 所有进入 `forward_one_candidate()` 的退出路径仍恰好执行一次焦点恢复。
- 焦点恢复仍从 `focus_restore_region` 取点并使用 `offset=0`。

### 8.4 模式测试

- 普通模式选择 `y` 记录完整校准请求。
- 普通模式空输入或 `n` 使用默认区域。
- `--auto` 不调用 `input()`、selector 或校准导航点击。
- 普通 `--no-forward` 可执行校准流程，但 OCR 命中不调用真实转发。
- 无关键词、转发禁用时不询问完整转发校准。

### 8.5 全量测试

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

### 8.6 手工安全测试

第一阶段仅使用：

```powershell
.\venv\Scripts\python.exe simple_brush.py --no-forward
```

验证：

1. 第一位详情打开后依次显示正确的框选提示。
2. 点击转发入口后弹窗可见。
3. 点击邮件 Tab 后输入框、最近联系人和转发按钮可见。
4. 校准 `FORWARD_BTN` 时不会真实点击按钮。
5. 校准完成后弹窗关闭，浏览继续。
6. Esc 取消后使用默认区域且程序继续。
7. 重启程序后配置恢复默认。
8. `--auto` 不显示新增询问或框选层。

真实转发验证必须满足：

- 使用测试账号。
- 使用测试邮箱。
- 首次只测试一位候选人。
- 人工全程监控。
- 完成后立即停止并检查所有点击位置。
- 不进行无人值守或批量真实转发。

## 9. 风险与回退

### 9.1 校准导航依赖固定 UI 顺序

程序仍假设点击转发入口后出现弹窗、点击邮件 Tab 后出现邮件界面，但不检测页面状态。如果 UI 未按预期出现，后续提示可能对应错误页面。

回退：用户按 Esc 取消，五项全部恢复默认区域；不新增页面状态识别。

### 9.2 误框选交互元素边缘

用户可能框选按钮边缘、邻近按钮或不可点击空白。

控制：提示要求框选控件内部安全区域，并设置合理最小尺寸；本 Issue 不自动识别控件。

### 9.3 校准期间误发送

`FORWARD_BTN` 风险最高。

控制：只用覆盖层框选，不调用该区域的点击助手；完成后用 Esc 关闭弹窗。自动化测试必须断言校准期间没有发送按钮点击。

### 9.4 窗口移动和缩放

所有区域是绝对物理像素坐标。校准后移动、缩放、最小化或改变浏览器缩放会使配置失效。

控制：README 明确校准后保持窗口位置和尺寸；本轮不实现窗口相对坐标。

### 9.5 DPI 和多显示器

继续复用现有 Windows DPI awareness，但区域选择器第一版仅支持主显示器。混合 DPI 或 Edge 位于副屏时可能失准。

回退：要求 Edge 位于主显示器；本 Issue 不处理跨平台或多显示器增强。

### 9.6 `--auto` 默认区域风险

自动模式无法交互校准，只能使用默认区域。在非默认窗口布局下存在误点风险。

控制：运行前先用普通 `--no-forward` 验证；本轮不增加持久化或命令行坐标参数。

### 9.7 取消和部分成功

若采用逐项保留，用户难以判断哪些区域有效。

控制：五项采用原子配置；任一步失败全部回退默认。Next-1 焦点区域保持独立状态。

### 9.8 遗留 RIGHT_CLICK 常量

`RIGHT_CLICK_X/Y` 当前未调用，但保留会造成理解成本。

控制：TID 和 README/代码注释中标记为遗留；本 Issue 不擅自删除，避免扩大范围。

## 10. Git 提交计划

### Commit 1

范围：默认区域配置、运行期配置、区域点击助手和基础测试。

```text
feat: add runtime regions for forwarding clicks
```

### Commit 2

范围：普通模式询问、完整引导校准、原子回退、`--auto`/`--no-forward` 和校准测试。

```text
feat: calibrate forwarding click regions before browsing
```

### Commit 3

范围：`forward_one_candidate()` 五类点击接入运行期区域及完整路径测试。

```text
feat: use calibrated regions in forwarding workflow
```

### Commit 4

范围：README 使用方式、默认回退、限制和安全验证。

```text
docs: explain full forwarding click calibration
```

### Commit 5

范围：全量回归和范围验收；无文件变更时不创建空 commit。若另行生成验收报告，可使用：

```text
docs: add Next-3 forwarding calibration acceptance report
```
