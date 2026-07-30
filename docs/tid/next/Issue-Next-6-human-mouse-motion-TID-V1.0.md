# [Next-6][P2] TID V1.0：优化鼠标移动轨迹——贝塞尔路径、途中抖动与慢-快-慢三段变速

## 1. 背景与目标

BossOCR 当前通过 `simple_brush.py::human_click()` 完成转发区域、批次筛选区域和焦点恢复区域的主要点击。该函数先计算最终点击点，再调用一次 `pyautogui.moveTo(..., duration=0.15~0.35)`，随后执行短暂停顿和按下/抬起。移动过程完全交给 PyAutoGUI 的直线匀速实现，不利于用户观察程序当前准备点击哪个控件，也不便于统一约束关键按钮附近的最终落点。

本需求新增统一的 `human_move_to()` 底层移动封装，在单次移动内部提供：

1. 三次贝塞尔曲线路径。
2. 慢—快—慢的单次移动速度分布。
3. 仅发生在中间路径点的轻微随机抖动。
4. 最后一步强制落到调用方给定的目标坐标。
5. 根据移动距离计算总时长和采样步数。
6. `--simple-mouse` 运行期回退开关，恢复现有简单直线移动/点击行为。

目标是提升 GUI 操作的可观察性、统一主要点击路径的底层移动实现，并确保已经由区域校准选出的安全落点不会因路径抖动而在最终点击时偏移。

本设计只讨论本地 GUI 自动化的可读性、可测试性和落点稳定性。不得在代码、日志、README 或发布说明中将其描述为规避验证码、风控、反自动化策略或平台检测的手段，也不对这类效果作任何承诺或暗示。

## 2. 非目标

本 issue 明确不做：

- 不新增 `fast` / `normal` / `slow` 等全局速度 profile。
- 不根据页面、按钮类型或业务步骤选择不同速度档位。
- 不识别页面状态、控件文字或图片，不读取 DOM。
- 不引入 Selenium、Playwright、WebDriver 或其他浏览器驱动。
- 不改变点击目标区域、随机落点范围或 `offset` 语义。
- 不修改鼠标滚轮、键盘、暂停/停止、OCR、关键词、邮件转发内部、Next-5 批次筛选业务、打包或 macOS Chrome 逻辑。
- 不迁移 `human_scroll_once()`、`next_candidate()` 等非点击输入路径。
- 不创建 tag、GitHub Release 或发布产物。

## 3. 现有鼠标封装入口分析

### 3.1 主要入口

| 文件 / 函数 | 当前实现 | 下游调用 | 本 issue 处理方式 |
| --- | --- | --- | --- |
| `simple_brush.py::human_click(x, y, offset=5)` | 计算一次最终偏移点，直接 `pyautogui.moveTo()`，再 `mouseDown()` / `mouseUp()` | 转发、焦点恢复 | 内部改为调用 `human_move_to()`；保留偏移、停顿和按压时长语义 |
| `simple_brush.py::click_in_region(region)` | 区域内随机取点，再 `human_click(..., offset=0)` | Next-3 转发区域、Next-5 筛选区域、校准导航 | 调用点不改；自动获得新移动轨迹 |
| `forward_one_candidate()` 的焦点恢复 | 两次区域取点，各调用 `human_click(..., offset=0)` | 所有进入转发函数的退出路径 | 调用点不改；继续执行两次且最终点不偏移 |
| `simple_brush.py::click_first_candidate(x, y)` | 直接 `pyautogui.click(x, y, duration=0)` | 未启用 Next-5 时的旧首位坐标路径 | 第一版保留，避免改变旧流程的即时点击语义；Change 3 明确做兼容回归 |
| `human_scroll_once()` | `pyautogui.scroll()` | 浏览过程随机滚动 | 不属于鼠标指针移动，不修改 |

### 3.2 结论

主要区域点击已经集中到 `human_click()`，因此无需批量修改转发或 Next-5 调用点。`human_click()` 内部复用 `human_move_to()` 后，`click_in_region()`、五个转发点击区域、批次筛选四区域和双次焦点恢复会自然获得一致移动行为。

现有唯一直接点击绕行是旧路径 `click_first_candidate()`。V1.0 不强制迁移该函数，原因是它当前承担 `--auto`、CLI keywords、`--no-batch-filter` 和校准回退路径的兼容行为；将其迁移到带按下/抬起停顿的 `human_click()` 会扩大行为变化。若后续希望所有点击完全统一，应另行验收，不能顺手混入 Change 1/2。

另一个现状风险是 `FORWARD_CLICK_OFFSET` 上方注释含“反检测”措辞。Next-6 实施或文档更新时应将相关表述改为中性的“鼠标点击配置”或“操作可观察性”，但不得借此修改参数行为。

## 4. 新增 `human_move_to()` 设计

建议接口：

```python
def human_move_to(x, y, *, simple=None):
    """Move the pointer to the exact target using the active movement mode."""
```

- `x`、`y` 为最终目标屏幕坐标。
- `simple=None` 表示读取当前运行期 `simple_mouse_enabled`；测试可以显式传入布尔值，避免依赖全局状态。
- 不向业务调用方暴露速度 profile、曲率、时长或抖动参数，避免调用点逐渐形成不可控的局部配置。
- 函数通过 `pyautogui.position()` 获取起点；起点和终点在函数开始时各确定一次。
- 增强模式生成多个中间点并逐点移动，最后无条件执行一次 `pyautogui.moveTo(target_x, target_y, duration=0)`。
- 简单模式只执行现有语义：`pyautogui.moveTo(x, y, duration=random.uniform(0.15, 0.35))`。
- 函数只负责移动，不负责点击、业务等待或页面判断。
- PyAutoGUI 异常保持向上传播，由现有调用层决定是否记录并停止；不能吞掉失败后继续点击。

短距离和零距离策略：

- 起点等于终点时，不生成控制点或抖动，只执行一次精确终点 `moveTo(..., duration=0)`。
- 距离小于 `8 px` 时采用退化直线贝塞尔或少量无抖动中间点，避免曲率和抖动大于实际位移。
- 所有生成坐标在调用 PyAutoGUI 前四舍五入为整数。

## 5. 贝塞尔路径设计

使用三次贝塞尔曲线：

```text
B(t) = (1-t)^3 P0
     + 3(1-t)^2 t P1
     + 3(1-t)t^2 P2
     + t^3 P3
```

- `P0`：`pyautogui.position()` 返回的起点。
- `P3`：调用方目标点。
- `P1`、`P2`：沿起点到终点方向前进，并在垂直方向加入同侧的小幅曲率。

建议控制点生成规则：

1. 计算方向单位向量 `d` 和垂直单位向量 `n`。
2. `P1` 位于路径长度的 `25%~40%`，`P2` 位于 `60%~75%`。
3. 单次移动只随机一次曲线方向，符号为 `-1` 或 `+1`；两个控制点使用同侧偏移，避免 S 形绕行和关键控件附近的不必要摆动。
4. 垂直偏移建议为距离的 `4%~10%`，并限制在 `4~40 px`；距离小于 `40 px` 时进一步收敛或设为 `0`。
5. 控制点只影响移动途中轨迹，不改变 `P3`。

禁止把每个采样点完全独立随机化，否则路径会变成锯齿。曲率随机量应在一次移动开始时固定，途中仅叠加受限抖动。

## 6. 慢-快-慢 easing 设计

第一版采用无额外依赖的 smoothstep：

```text
e(u) = 3u² - 2u³,  u ∈ [0, 1]
```

以固定时间间隔遍历 `u`，将 `t = e(u)` 代入贝塞尔曲线：

- 起步阶段 `e'(u)` 较小，空间步长较短。
- 中段 `e'(u)` 较大，空间步长较长。
- 结束阶段再次减速，靠近目标点时步长收敛。

这里的“慢—快—慢”只描述单次移动内部的速度分布，不是全局速度档位。不得增加 profile 枚举、环境变量或按业务步骤切换速度。

每个中间点使用 `pyautogui.moveTo(px, py, duration=0)`，再通过可 mock 的 `time.sleep(step_interval)` 控制采样间隔。这样不依赖 PyAutoGUI 对小于其 `MINIMUM_DURATION` 的 duration 如何处理，并便于单元测试验证调用序列。最后的精确落点不再额外 sleep；现有 `human_click()` 的点击前停顿继续保留。

## 7. 距离到时长/步数的计算方案

建议第一版使用连续公式并做上下界裁剪：

```python
distance = hypot(target_x - start_x, target_y - start_y)
duration = clamp(0.18 + distance / 1800.0, 0.20, 0.75)
steps = clamp(round(duration * 60), 12, 45)
```

推荐默认范围：

| 参数 | 建议范围 | 说明 |
| --- | --- | --- |
| 总时长 | `0.20~0.75 s` | 短移动仍可观察，长移动不拖慢流程过多 |
| 距离换算 | `distance / 1800` | 连续变化，不形成全局速度 profile |
| 采样率 | 约 `60 steps/s` | 与常见屏幕刷新节奏接近，测试和运行成本可控 |
| 步数 | `12~45` | 限制 PyAutoGUI 调用次数 |
| 曲率 | 距离的 `4%~10%` | 再裁剪到 `4~40 px` |
| 途中抖动 | 每轴 `±0.5~1.5 px` | 仅内部点；短距离关闭 |

`steps` 表示包含终点参数的采样数量。实现时可只向 PyAutoGUI发送 `steps - 1` 个中间点，再单独发送精确终点，以便从结构上保证最终落点。

上述参数应定义为模块级常量，便于测试 patch 和后续小范围调参；不得成为用户可选的速度档位。若实机观察发现 45 步造成明显 CPU 或日志压力，应优先降低采样率/上限，而不是引入 profile。

## 8. 途中抖动与最终落点稳定策略

抖动规则必须满足：

1. 仅对 `0 < u < 1` 的中间采样点叠加。
2. 起点、最终点不叠加抖动。
3. 短距离默认关闭抖动。
4. 建议每轴独立限制为 `±0.5~1.5 px`，取整后可能自然成为 `0`。
5. 抖动不得累积到下一个点；每个点都从原始贝塞尔坐标计算。
6. 倒数一个中间点也应限制在目标附近，避免最后一步出现明显跳回；可以按 `sin(πu)` 缩放抖动，使两端自然衰减。
7. 循环结束后强制调用 `pyautogui.moveTo(target_x, target_y, duration=0)`，不能依赖浮点贝塞尔在 `t=1` 时“理论上等于”目标。

点击稳定性由两层保证：

- `human_click()` 只计算一次最终 `tx/ty`，并把该坐标同时交给移动、`mouseDown(tx, ty)` 和 `mouseUp(tx, ty)`。
- `click_in_region()` 继续先在区域内取点再传 `offset=0`，不会因新移动函数产生第二次目标偏移。

不得把途中抖动误用为点击坐标抖动，也不得在到达目标后再随机移动。

## 9. `human_click()` 接入方案

建议保持签名不变：

```python
def human_click(x, y, offset=FORWARD_CLICK_OFFSET):
    tx = x + random.randint(-offset, offset)
    ty = y + random.randint(-offset, offset)
    human_move_to(tx, ty)
    time.sleep(random.uniform(0.03, 0.08))
    pyautogui.mouseDown(tx, ty)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.mouseUp(tx, ty)
```

接入原则：

- 只替换 `human_click()` 内的一行 `pyautogui.moveTo()`，不批量改动现有 `human_click()` / `click_in_region()` 调用点。
- `offset` 的随机次数、范围和半开/闭区间语义不变。
- `offset=0` 仍严格点击调用方选出的区域点。
- 按下前等待、按下时长、`mouseDown` / `mouseUp` 坐标不变。
- `human_move_to()` 失败时不得继续执行 `mouseDown`。
- 双次焦点恢复仍由 `forward_one_candidate()` 负责调用两次，Next-6 不改变次数、异常隔离或间隔。

`click_first_candidate()` 在 V1.0 保持直接 `pyautogui.click()`。Change 3 必须用回归测试记录这一兼容边界，避免审阅者误以为已经覆盖所有直接点击。

## 10. `--simple-mouse` 回退方案

新增：

```text
--simple-mouse
```

运行期状态建议为：

```python
simple_mouse_enabled = False
```

处理方式：

1. `parse_args()` 默认返回 `simple_mouse=False`，识别开关后设为 `True`。
2. `run()` 每次启动时根据 CLI 参数设置 `simple_mouse_enabled`，防止测试或同进程重复调用遗留状态。
3. 不增加交互式提问，不修改 `get_user_input()` 的参数和顺序。
4. 不与 `--auto`、`--no-forward`、`--no-batch-filter`、`--keywords` 建立互斥关系。
5. 开启后，`human_move_to()` 只调用一次旧版 `pyautogui.moveTo(target, duration=0.15~0.35)`；`human_click()` 后续等待、按下和抬起保持旧行为。
6. 由于旧 `click_first_candidate()` 原本就不经过 `human_move_to()`，该路径在两种模式下都保持现状。

该开关是运行时快速回退手段，不持久化，不改变配置文件或发布包结构。README 应明确它是“使用旧版简单直线移动”的兼容开关，不使用“隐身”“反检测”等描述。

## 11. 测试计划

测试优先放在 `tests/test_simple_brush_ocr.py`；若用例数量影响可读性，可独立新增 `tests/test_mouse_motion.py`。所有测试必须 mock `pyautogui.position`、`pyautogui.moveTo`、`pyautogui.mouseDown`、`pyautogui.mouseUp`、`pyautogui.click` 和 `time.sleep`。不得触发真实鼠标、键盘、剪贴板、OCR、浏览器、筛选或邮件转发。

### 11.1 `human_move_to()` 核心

- 起点和目标相同：不生成随机曲率或抖动，最终精确落点一次。
- 普通距离：产生多个中间点，最后一次 `moveTo` 严格等于目标整数坐标。
- 固定随机源后，中间点符合三次贝塞尔计算。
- 所有中间点有限、可转换为整数，无 NaN/除零。
- 短距离关闭曲率/抖动或按设计收敛。
- 长距离时长和步数不超过上限，短距离不低于下限。
- 固定时间间隔下，前段/末段相邻距离小于中段，证明 slow-fast-slow，而不是只验证调用次数。
- 中间抖动不会改变最终坐标；抖动幅度不超过配置上限，并在两端衰减。
- `pyautogui.position()` 或中间 `moveTo()` 抛错时异常向上传播，不继续移动或点击。

### 11.2 简单模式

- `human_move_to(..., simple=True)` 仅调用一次 `pyautogui.moveTo`。
- duration 位于现有 `0.15~0.35` 范围。
- 不调用 `pyautogui.position()`、贝塞尔随机数或逐步 sleep（除非实现读取起点用于日志；第一版不建议）。
- `parse_args()` 能识别 `--simple-mouse`，默认值为 `False`，并兼容其他参数顺序。
- `run()` 每次将 CLI 值写入运行期状态，避免前次运行污染。

### 11.3 `human_click()` 接入

- 目标 offset 只计算一次，`human_move_to`、`mouseDown` 和 `mouseUp` 使用相同 `tx/ty`。
- `offset=0` 不产生目标偏移。
- `human_move_to()` 异常时不调用 `mouseDown` / `mouseUp`。
- 点击前停顿和按压停顿范围保持现状。
- 简单模式仍走旧版单次直线移动后点击。

### 11.4 现有路径回归

- `click_in_region()` 仍只随机取点一次，并调用 `human_click(..., offset=0)`。
- Next-5 筛选点击顺序仍为 open、unseen、confirm、first。
- 转发五个区域和邮箱输入框复用行为不变。
- 所有进入 `forward_one_candidate()` 的退出路径仍执行两次焦点恢复。
- 两次焦点恢复仍来自 `focus_restore_region` 且 `offset=0`。
- `--no-forward` 仍不进入真实转发函数。
- `click_first_candidate()` 旧直接点击路径保持不变。
- `--simple-mouse` 与 `--auto`、`--no-batch-filter`、CLI keywords 组合解析不冲突。

### 11.5 回归命令

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_simple_brush_ocr -v
.\venv\Scripts\python.exe -m unittest discover -s tests -v
git diff --check
```

## 12. Change 拆分

### Change 1：新增 `human_move_to()` 核心函数与单元测试

建议修改：`simple_brush.py`、`tests/test_mouse_motion.py` 或直接相关测试文件。

- 新增距离、时长、步数、控制点、smoothstep 和中间路径计算。
- 新增精确终点、短/零距离、异常传播测试。
- mock 全部 PyAutoGUI 与 sleep。
- 此 Change 尚不接入 `human_click()`，不能作为完整功能发布。

建议 commit：

```text
feat: add observable bezier mouse movement
```

复杂度：中高。数学路径本身简单，难点在确定性测试、端点保证和 PyAutoGUI 调用成本。

### Change 2：`human_click()` 接入与 `--simple-mouse`

建议修改：`simple_brush.py`、相关参数和点击测试。

- `human_click()` 内部复用 `human_move_to()`。
- 新增并每次运行初始化 `simple_mouse_enabled`。
- 新增 `--simple-mouse` 解析和旧版移动回退。
- 验证 offset、按压时长和失败不点击。

建议 commit：

```text
feat: use human mouse paths for region clicks
```

复杂度：中。改动点集中，但必须谨慎处理运行期状态和旧行为。

### Change 3：现有点击路径回归与参数兼容性检查

建议修改：以测试文件为主；除发现 Next-6 接入缺陷外不改业务代码。

- 覆盖 Next-3 转发区域、P0 双次焦点恢复、Next-5 筛选区域。
- 覆盖 `offset=0`、`--no-forward` 和各 CLI 组合。
- 明确验证 `click_first_candidate()` 仍是未迁移的旧直接点击边界。
- 不改变转发、筛选或浏览调用顺序。

建议 commit：

```text
test: cover human mouse integration paths
```

复杂度：中低。主要是 mock 隔离和既有调用契约回归。

### Change 4：README 与收尾测试

建议修改：`README.md`。

- 说明增强移动的可观察性、单次移动慢—快—慢和最终落点保证。
- 说明 `--simple-mouse` 回退。
- 明确不用于规避验证码、风控或平台检测。
- 运行全量测试和 `git diff --check`。

建议 commit：

```text
docs: explain human mouse movement option
```

复杂度：低。

四个 Change 均不得混入 OCR、关键词、转发内部、Next-5 业务、打包或 macOS Chrome 修改。Change 1 parser/核心存在但未接入时不可发布；正式可用至少要求 Change 1 和 Change 2 同时完成。

## 13. 风险与回滚

### 13.1 主要风险

- **运行变慢**：每次区域点击增加约 `0.20~0.75s` 移动时间；转发和批次筛选包含多个点击，整体耗时会上升。
- **调用次数增加**：逐点 `moveTo` 可能增加 CPU 和 PyAutoGUI 开销；必须限制最大步数。
- **曲率过大**：路径可能经过不相关控件，但途中不点击；仍应限制横向偏移，减少用户误判和指针越界。
- **最终落点漂移**：浮点、取整和抖动若处理不当可能使关键按钮误点；必须用独立最终 `moveTo(target)` 和一致的 down/up 坐标保证。
- **短距离视觉抖动**：位移很小时抖动会比路径本身更明显；应关闭或衰减。
- **PyAutoGUI fail-safe**：曲线路径若经过屏幕左上角可能触发 fail-safe；异常必须向上传播，不能继续点击。控制点应限制在屏幕合理范围，但不应为此关闭 PyAutoGUI fail-safe。
- **测试非确定性**：随机控制点、抖动、时长和步数会导致脆弱测试；测试应 patch 随机返回值和常量，验证不变量而非依赖真实随机样本。
- **运行期状态污染**：`simple_mouse_enabled` 若未在每次 `run()` 初始化，会污染同进程测试或重复运行。
- **范围认知偏差**：旧 `click_first_candidate()` 不经过 `human_click()`；README 和验收报告必须如实说明第一版覆盖主要区域点击，而非宣称所有鼠标点击均已统一。

### 13.2 回滚方案

- 运行时使用 `--simple-mouse` 立即回到旧版 `human_click()` 直线移动，无需改配置或重新校准。
- Change 4 可独立回滚文档。
- Change 3 可独立回滚补充测试。
- Change 2 可回滚 `human_click()` 接入和 CLI 状态，保留未使用的核心函数供诊断；不可将这种状态发布为已完成 Next-6。
- Change 1 可整体回滚新移动函数。
- 不移动既有 tag，不更新稳定分支，不创建 release。

## 14. 验收标准

| 验收项 | 通过条件 |
| --- | --- |
| 统一入口 | 现有 `human_click()` 内部调用 `human_move_to()`，无需批量修改业务调用点 |
| 贝塞尔路径 | 增强模式使用三次贝塞尔生成连续中间路径 |
| 单次变速 | 每次移动内部呈慢—快—慢，不存在全局速度 profile |
| 距离适配 | 总时长和步数随距离连续变化，并受明确上下界限制 |
| 途中抖动 | 抖动只存在于中间点，幅度受限且靠近两端衰减 |
| 精确终点 | 最后一次移动严格回到目标整数坐标 |
| 点击一致性 | `human_move_to`、`mouseDown`、`mouseUp` 使用同一最终 `tx/ty` |
| 区域安全 | `click_in_region()` 仍只取点一次并使用 `offset=0` |
| 简单回退 | `--simple-mouse` 恢复旧版单次直线 `moveTo` 和原点击行为 |
| 参数兼容 | 新开关与 auto、keywords、no-forward、no-batch-filter 可组合且不新增交互 |
| 旧首位路径 | `click_first_candidate()` 直接点击行为保持不变并有回归测试 |
| 转发回归 | 转发区域、邮箱输入框复用和双次焦点恢复语义不变 |
| Next-5 回归 | 筛选点击顺序、失败停止和批次边界语义不变 |
| 错误处理 | 移动异常向上传播且不会继续按下鼠标 |
| 测试隔离 | 所有 PyAutoGUI、sleep 和其他真实副作用均被 mock |
| 合规表述 | 代码和文档不承诺或暗示规避验证码、风控或平台检测 |
| 非目标 | 未修改 OCR、关键词、转发内部、Next-5 业务、打包或 macOS Chrome |
| 回归 | 相关单测、全量测试和 `git diff --check` 通过 |
