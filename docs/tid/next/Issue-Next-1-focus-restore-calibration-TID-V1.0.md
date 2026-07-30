# [Next-1] TID V1.0：转发流程点击区域启动前校准

## 1. 目标与范围

### 1.1 目标

将邮件转发流程结束后的“详情页焦点恢复点击”从固定点改为运行期可校准区域：

- 默认区域：`X:400-500, Y:350-400`。
- 普通交互模式启动时询问用户是否校准。
- 用户选择校准后，在第一位候选人详情页打开后显示框选界面。
- 校准成功后，本次运行从校准区域内选择点击点恢复焦点。
- 跳过、取消或校准失败时继续使用默认区域。
- 校准数据只保存在内存中，不持久化。

### 1.2 本轮范围

仅校准候选人详情页空白区域，即 `forward_one_candidate()` 退出前执行的焦点恢复点击。

### 1.3 非目标

本轮不处理：

- 其他转发按钮和输入框坐标。
- 关键词 `not`。
- macOS Chrome。
- P3 日志或 P4 数值匹配。
- DOM 读取或浏览器自动化驱动。
- 页面状态识别或转发成功检测。
- 整体转发流程重构。
- 校准结果持久化。
- `--auto` 模式的交互校准。
- Windows Edge 之外的平台适配。

## 2. 当前代码分析

### 2.1 仓库状态

- 当前分支：`main`
- 跟踪分支：`origin/main`
- 分析时工作区：干净
- Issue：`[Next-1] P1：转发流程点击区域启动前校准`
- Issue 状态：Open

### 2.2 焦点恢复实现

文件：`simple_brush.py`

当前以 `FOCUS_RESTORE_X = 450`、`FOCUS_RESTORE_Y = 375` 保存固定点，注释声明有效空白区域为 `X:400-500, Y:350-400`。`forward_one_candidate()` 的 `finally` 当前固定执行：

```python
human_click(FOCUS_RESTORE_X, FOCUS_RESTORE_Y, offset=3)
human_delay(0.3, 0.5)
```

因此无论转发成功、提前退出还是发生异常，只要进入该函数都会尝试恢复焦点。`tests/test_simple_brush_ocr.py` 已覆盖成功、连续转发上限、无备选邮箱、等待中断和异常路径，并验证焦点恢复是最后一次点击且只执行一次。

### 2.3 OCR 区域校准实现

文件：`ocr_calibration.py`

现有可复用能力：

- `ScreenRegion`：不可变矩形区域数据结构。
- `primary_monitor_region()`：取得主显示器物理像素范围。
- `physical_point_from_overlay()`：将 Tk 坐标转换为物理像素坐标。
- `region_from_points()`：根据拖动起止点生成区域。
- `select_screen_region()`：显示全屏半透明 Tk 框选层。
- `CalibrationCancelled`：表示用户按 Esc 取消校准。
- Windows DPI awareness 和缩放坐标转换。

OCR 校准由 `simple_brush.py` 的 `ensure_ocr_region_calibrated()` 管理。当前在第一位候选人详情页打开、首次关键词检测时弹出框选层；成功后创建 `OCRKeywordDetector`，取消或失败时安全禁用本次 OCR 转发。

### 2.4 启动流程与插入位置

`run()` 当前顺序为：解析参数、`get_user_input()`、初始化 OCR、启动键盘监听、激活 Edge、倒计时、打开第一位候选人详情页、进入 `view_candidate()`。

适合的接入方式是：

1. 在 `get_user_input()` 中询问是否需要焦点恢复区域校准。
2. 在 `click_first_candidate()` 成功后、首次 `view_candidate()` 前执行实际框选。

这样既符合“启动时询问”，也保证框选时第一位候选人详情页已经可见。不建议在激活 Edge 或打开详情页前直接框选。

### 2.5 数据结构复用

直接复用：

```python
ScreenRegion(left=400, top=350, width=100, height=50)
```

`ScreenRegion` 虽位于名称偏 OCR 的模块中，但结构本身通用。本 issue 不移动模块或重构目录。`select_screen_region()` 的提示文字和错误信息目前写死为 OCR 详情正文区域，需要做小范围参数化。焦点区域校准不调用 `save_region_preview()`，避免产生新的页面截图。

### 2.6 Issue 与现状差异

Issue 将兜底描述为默认“区域”，但当前代码实际保存中心点 `(450, 375)`，点击时增加 `±3` 像素偏移。本轮应将该范围提升为真正的运行期 `ScreenRegion`。

文件中另有 `RIGHT_CLICK_X/Y`，但实际焦点恢复使用 `FOCUS_RESTORE_X/Y` 和普通 `human_click()`。本 issue 不顺带清理旧常量，避免扩大需求。

## 3. 方案设计

### 3.1 运行期状态

在 `simple_brush.py` 中新增：

```python
DEFAULT_FOCUS_RESTORE_REGION = ScreenRegion(
    left=400,
    top=350,
    width=100,
    height=50,
)

focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
focus_restore_calibration_requested = False
focus_restore_calibration_attempted = False
focus_restore_calibration_in_progress = False
```

- `focus_restore_region`：本次运行实际使用的区域。
- `focus_restore_calibration_requested`：用户是否选择校准。
- `focus_restore_calibration_attempted`：防止重复弹出。
- `focus_restore_calibration_in_progress`：让 Esc 只取消 Tk 校准，不停止主循环。

每次 `run()` 开始时恢复默认状态，避免测试或同一进程重复调用污染状态。

### 3.2 区域内点击点

新增纯函数 `random_point_in_region(region)`，采用与截图一致的半开区间语义：

```text
x ∈ [left, left + width - 1]
y ∈ [top, top + height - 1]
```

焦点恢复时：

```python
x, y = random_point_in_region(focus_restore_region)
human_click(x, y, offset=0)
```

必须显式使用 `offset=0`，避免二次随机偏移落到区域外。

### 3.3 校准界面复用

为 `select_screen_region()` 增加可选显示参数，例如：

```python
def select_screen_region(
    min_size=80,
    instruction="拖动框选候选人详情区域 · Esc 取消",
    subtitle="第一版仅支持主显示器",
):
```

OCR 调用不传参数，保持现有行为。焦点校准使用“拖动框选候选人详情页空白区域 · Esc 使用默认区域”，并建议设置 `min_size=20`。坐标转换、DPI awareness 和主显示器限制保持不变。

### 3.4 校准和回退函数

在 `simple_brush.py` 新增 `ensure_focus_restore_region_calibrated()`：

1. 未请求校准时返回默认区域。
2. 已尝试过时不再弹窗。
3. 设置 `focus_restore_calibration_in_progress=True`。
4. 调用参数化后的 `select_screen_region()`。
5. 成功后替换 `focus_restore_region`。
6. 用户取消或发生异常时记录信息并保留默认区域。
7. `finally` 中恢复进行状态。
8. 不禁用 OCR、浏览或转发。

这与 OCR 校准失败逻辑不同：OCR 区域缺失时不能安全判断关键词；焦点恢复校准失败时已有明确兜底区域，可以继续当前 Windows Edge 流程。

### 3.5 与转发流程连接

只替换 `forward_one_candidate()` 的 `finally` 中点击坐标来源，保留：

- `finally` 结构。
- 点击次数。
- 点击后的等待。
- 成功和失败返回值。
- 异常传播行为。
- 其他转发坐标。

## 4. 交互设计

### 4.1 普通交互模式

已配置关键词时询问：

```text
是否校准转发结束后的焦点恢复点击区域？[y/N]
```

默认 `N`。选择 `y` 后先记录请求；Edge 激活并打开第一位候选人详情页后才显示框选层。即使启用 `--no-forward`，普通模式也可执行校准，以安全验证交互。未设置关键词时不询问。

### 4.2 `--auto` 模式

- 不调用 `input()`。
- 不弹出焦点恢复校准层。
- 始终使用默认区域。
- 不新增命令行参数。
- 不影响无人值守运行和构建冒烟测试。

### 4.3 各结果处理

- **成功**：更新 `focus_restore_region`，记录坐标和尺寸，不保存预览。
- **跳过**：直接使用默认区域。
- **取消**：关闭框选层，不设置 `stop_event`，继续运行且不重复弹出。
- **失败**：记录异常，保留默认区域，不关闭 OCR、浏览或转发。

`on_press()` 需要同时识别 OCR 校准和焦点区域校准的进行状态。

## 5. 技术步骤拆解

### Change 1：通用化区域选择界面

修改文件：`ocr_calibration.py`、`tests/test_ocr_calibration.py`

- 参数化提示文字。
- 保持 OCR 默认提示不变。
- 允许焦点区域使用较小 `min_size`。
- 不修改坐标转换和预览逻辑。

验收：现有校准测试通过，OCR 默认行为不变，专用提示和较小有效区域可用。

### Change 2：增加运行期区域与回退

修改文件：`simple_brush.py`、`tests/test_simple_brush_ocr.py`

- 增加默认区域和运行期状态。
- 增加 `random_point_in_region()`。
- 增加 `ensure_focus_restore_region_calibrated()`。
- 扩展 Esc 校准状态处理。
- 在 `run()` 开始时重置状态。

验收：选点不越界；成功更新区域；取消、异常保留默认区域；同一运行只尝试一次。

### Change 3：接入启动交互和首位详情页时机

修改文件：`simple_brush.py`、`tests/test_simple_brush_ocr.py`

- 普通模式询问是否校准。
- `--auto` 不询问、不弹窗。
- 第一位详情打开后、首次 `view_candidate()` 前校准。
- 未启用关键词时不询问。
- `--no-forward` 普通模式允许安全验证。

验收：各交互分支符合设计；详情打开失败时不校准；校准失败后主循环继续。

### Change 4：接入焦点恢复流程

修改文件：`simple_brush.py`、`tests/test_simple_brush_ocr.py`

- 从运行期区域选择点击点。
- 使用 `human_click(..., offset=0)`。
- 保留现有 `finally` 和等待逻辑。

验收：所有退出路径仍恢复一次，恢复点击仍为最后一次，点击不越界，Windows Edge 主流程不变。

### Change 5：补充说明

修改文件：`README.md`

- 说明询问和框选时机。
- 说明默认区域、取消和失败回退。
- 说明仅当前运行有效。
- 说明 `--auto` 不交互。
- 强调先用 `--no-forward` 验证。

验收：不宣称其他坐标已校准，不引入 macOS、DOM 或持久化承诺。

## 6. 测试计划

### 6.1 单元测试

- 保持反向拖动和 DPI 坐标转换测试。
- 验证焦点区域允许较小有效选择，零面积和过小区域仍被拒绝。
- 验证默认区域值。
- 验证区域内随机点不越界。
- 验证成功、取消、异常和只尝试一次。
- 验证校准期间 Esc 不停止程序。
- 验证 `--auto` 不触发交互或选择器。

### 6.2 Mock 测试

Mock `select_screen_region()`、`human_click()`、随机数和输入：

- 默认和校准区域均用于恢复点击。
- `human_click()` 使用 `offset=0`。
- 成功、连续上限、无邮箱、等待中断、异常路径均只恢复一次。
- 恢复点击是最后一次点击。
- 第一位详情打开失败时不弹出校准。
- 焦点恢复自身异常只记录错误，不破坏原流程结果。

### 6.3 自动回归

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

确认 OCR 校准、二次确认、`--no-forward`、旧关键词规则、计时停止和 Windows Edge 窗口测试全部通过。

### 6.4 手工安全测试

优先使用：

```powershell
.\venv\Scripts\python.exe simple_brush.py --keywords '"测试关键词"' --no-forward
```

验证成功框选、Esc 取消、过小区域失败回退、窗口位置变化后重新启动校准。框选区域必须是无按钮、无链接的详情页空白处。

`--no-forward` 不调用 `forward_one_candidate()`，因此它只能安全验证启动交互、框选和运行期配置；真实点击路径主要由 mock 测试覆盖。如必须进行真实页面验证，只能使用测试账号、测试邮箱和人工监控的小规模测试，不得批量转发。

## 7. 风险与回退

### 7.1 默认区域误点

默认区域只适用于当前 Windows Edge 布局。分辨率、缩放、窗口位置或页面布局变化仍可能误点。保留默认区域用于兼容，正式运行前建议人工校准并先用 `--no-forward`。

### 7.2 用户框选到交互元素

程序不做页面状态或 DOM 检查。提示必须明确要求选择空白区域，并以合理最小尺寸降低误选风险。

### 7.3 随机点越界

区域内随机化只执行一次，随后以 `offset=0` 点击；单元测试覆盖边界。

### 7.4 DPI 和系统缩放

复用现有 DPI awareness 和 `physical_point_from_overlay()`，保留 150% 缩放测试。本轮仍只支持主显示器。

### 7.5 运行中移动窗口

校准结果是绝对屏幕坐标。校准后移动或缩放 Edge 会使区域失效。启动提示应要求校准后不要改变窗口位置；本轮不实现窗口相对坐标。

### 7.6 取消或异常

保留 `DEFAULT_FOCUS_RESTORE_REGION`；取消和异常只记录信息，不禁用 OCR、浏览或转发，也不重复弹窗。

### 7.7 自动模式被阻塞

`--auto` 必须跳过询问和 Tk 框选，并由 mock 测试保证交互函数未被调用。

## 8. Git 提交计划

### Commit 1

范围：参数化通用屏幕区域框选提示并补充测试。

```text
refactor: make screen region calibration prompts reusable
```

### Commit 2

范围：增加默认焦点区域、运行期状态、选点及失败回退。

```text
feat: add runtime focus restore region calibration
```

### Commit 3

范围：接入普通模式询问和首位详情页后的校准，保证 `--auto` 无交互。

```text
feat: prompt for focus restore calibration at startup
```

### Commit 4

范围：将 `forward_one_candidate()` 接入运行期区域并更新退出路径测试。

```text
feat: restore candidate focus within calibrated region
```

### Commit 5

范围：更新 README 使用、安全验证和限制说明。

```text
docs: explain focus restore region calibration
```
