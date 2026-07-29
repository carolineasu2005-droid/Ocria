# BossOCR R03：基础 OCR 页面指纹——详细版 RPD

## 1. 文档信息和基线

| 项目 | 内容 |
| --- | --- |
| 文档类型 | RPD（需求与产品设计；事实审计 + 冻结语义） |
| 需求编号 | R03：基础 OCR 页面指纹 |
| Change | Change 0A：仓库审计与详细 RPD |
| 状态 | 待 TID；本 Change 不实现代码、测试、配置或构建变更 |
| 审计基线 | `b9029bc022ae258ab62e2bc28ae64ead2dea2f35`（`feat(r02): add detail page load detection`） |
| 基线分支 | `main`；该提交也是审计时的 `HEAD` 和 `origin/main` |
| 正式平台范围 | Windows 10/11 x64 + Microsoft Edge；仅公共 OCR 纯单元测试具有非 GUI 可移植性 |
| 本文件 | `docs/RPD-R03-basic-ocr-page-fingerprint.md` |

本文件基于 `b9029bc` 的已提交内容审计。审计开始时工作区已经存在、且不属于本 Change 的改动：`.gitignore`、`docs/Issue-Next-6-human-mouse-motion-acceptance-report.md`、`simple_brush.py`、`docs/project-review.zip`、`docs/project-review/`、`docs/tid/` 和 `venv-packages-before-reinstall.txt`。其中当前未提交的 `simple_brush.py` 只改变停留期滚动步数；本 RPD 的代码事实一律以 `b9029bc` 版本为准。

本 Change 只新增本 RPD。不得据此修改生产代码、测试、构建脚本、已有配置、`.gitignore`，不得创建 TID、实现 hash/sort/helper/dataclass 或 commit。

## 2. 当前仓库事实

### 2.1 OCR 数据结构、backend 和坐标

`OCRItem` 定义在 `ocr_text.py`：

```python
@dataclass(frozen=True)
class OCRItem:
    text: str
    confidence: float = 1.0
    box: Optional[Sequence[Sequence[float]]] = None
```

它还提供：

- `anchor -> Tuple[float, float]`：`box is None` 或空时返回 `(0.0, 0.0)`；否则对每个 point 强制 `float(point[0])`、`float(point[1])`，返回 `(min_x, min_y)`。
- `vertical_bounds -> Optional[Tuple[float, float]]`：`box is None` 或空时返回 `None`；否则返回 `(min_y, max_y)`。

`RapidOCRBackend.recognize()` 位于 `ocr_detector.py`，把两类 upstream 结果统一为 `Sequence[OCRItem]`：

1. RapidOCR 3.x：从 `result.txts`、`result.scores`、`result.boxes` 以 `zip()` 构造 `OCRItem(str(text), float(score), box)`。缺少 scores 时补 `1.0`，缺少 boxes 时补 `None`。
2. 旧结果：从 `(lines, elapsed)` 或 `lines` 解析每个 `[box, text, score]`；缺少 score 时补 `1.0`。只跳过不是 list/tuple 或长度小于 2 的 line；不验证 box 的形状或数值。

当前测试证明现代 backend 的正常 box 是四点坐标（例如 `[[0,0], [20,0], [20,10], [0,10]]`），并证明 NumPy ndarray 四点 box 可被 `OCRItem` 使用。它是通常的四点旋转框/多边形表示，而不是项目保证的 axis-aligned rectangle：类型只承诺可选嵌套坐标序列，backend 没有把它归一化成矩形。

因此当前可靠的几何派生方式是：对每个可解析 point 取 `x=float(point[0])`、`y=float(point[1])`，再取 `left=min(x)`、`right=max(x)`、`top=min(y)`、`bottom=max(y)`、`width=right-left`、`height=bottom-top`、`center_y=(top+bottom)/2`。它同时适用于正常四点旋转框和其他可解析多点框。

当前没有完整的 box 校验。已知情况包括：

- `None` 和 `[]` 被 `vertical_bounds` 视为无坐标；`order_items()` 把这些 item 放在所有有坐标 item 之后，保持 backend 原始顺序。
- 非空但 point 缺 x/y、不可下标、不可转为 float、含 NaN/Infinity 或 box 自身没有可用长度时，`anchor`/`vertical_bounds` 可以抛出 `TypeError`、`IndexError`、`ValueError` 或相关异常；没有当前代码把它们转换成专门的 box 状态。
- `RapidOCRBackend` 可以因为 3.x boxes 缺失产生 `box=None`，也可以将旧 wrapper 的任意 box 原样传递。
- 退化框（`left == right` 或 `top == bottom`）当前未被拒绝；只要 point 可解析，现有属性仍可计算。

`RapidOCRBackend` 只保留 upstream 返回的迭代顺序；仓库没有证据表明 RapidOCR 对阅读顺序提供合同保证。项目已有 `ocr_text.order_items()`：先按 `vertical_bounds`/`anchor` 建立自适应行，再同一行从左到右；但它对无坐标 item 依赖 backend 原始顺序，并且未处理不可解析非空 box。现有规则搜索通过 `searchable_text()` 调用该 helper。

### 2.2 R02 的采集、过滤、指标和搜索文本

R02 在 `ocr_detector.py` 添加了以下纯 helper：

```python
accepted_ocr_items(items: Iterable[OCRItem], min_confidence: float) -> List[OCRItem]
calculate_load_metrics(accepted_items: Iterable[OCRItem]) -> Tuple[int, int]
```

`accepted_ocr_items()` 是唯一 confidence 过滤：保留 `item.confidence >= min_confidence`。默认阈值由 `simple_brush.py:OCR_MIN_CONFIDENCE = 0.85` 注入 `OCRKeywordDetector`。阈值相等的 item 被保留。

`calculate_load_metrics()` 只接收已经过滤的 iterable，物化为 list 后返回：

```text
ocr_box_count  = len(accepted_items)
ocr_text_length = sum(len(item.text.strip())
                      for item in accepted_items
                      if item.text.strip())
```

因此空文本或只含空白的有效 item 计入 `ocr_box_count`，但不贡献 R02 的 `ocr_text_length`。`ScanObservation.item_count` 不同：它是 confidence 过滤前 `len(raw_items)`，不能代替 R02/R03 的有效框数。

`OCRKeywordDetector.capture_observation(scan_number: int) -> ScanObservation` 的当前顺序为：

```text
time.perf_counter 开始
→ self.capture.capture(self.region)
→ list(self.backend.recognize(image)) 为 raw_items
→ accepted_ocr_items(raw_items, self.min_confidence)
→ calculate_load_metrics(accepted_items)
→ searchable_text(accepted_items)
→ 返回 ScanObservation
```

一次调用只执行一次 capture 和一次 backend recognize；它不调用 matcher、scroll 或 wait。`tests/test_ocr_detector.py` 已覆盖这条一次性采集合同。

`searchable_text()` 会再次以默认 `min_confidence=0.0` 过滤传入的已过滤 list，调用 `order_items()`，用换行拼接 item.text，最后执行现有 `normalize_text()`。后者执行 Unicode NFKC、转小写并删除全部空白。它依赖排序后的文字，且已不是原始文本，不能用于 R03 的 raw_text、normalized_text、长度或 exact_hash。

### 2.3 ScanObservation、DetectionResult 和异常边界

当前 `ScanObservation` 定义在 `ocr_detector.py`，字段按声明顺序为：

```python
@dataclass
class ScanObservation:
    scan_number: int
    text: str
    item_count: int
    elapsed_seconds: float
    matched_keyword: Optional[str] = None
    matched_rule: Optional[KeywordRule] = None
    ocr_box_count: Optional[int] = None
    ocr_text_length: Optional[int] = None
```

构造发生在 `capture_observation()`；随后 `_match_observation()` 在同一个可变 object 上填写 `matched_keyword` 与 `matched_rule`。现有测试明确断言它不保存 `ocr_items`、`raw_items`、`accepted_items` 或 `evidence` 列表。

`DetectionResult` 包含 `success`、`confirmed_match`、`matched_keyword`、`scans_completed`、`observations: List[ScanObservation]` 和 `error`。它没有候选人 ID、批次 ID 或持久化职责。

异常边界当前为：

- capture/backend 或现有 `searchable_text()` 处理在正式 `OCRKeywordDetector.detect()` 内发生异常时，由该方法的 outer `try/except` 记录 `OCR keyword detection failed`，返回 `DetectionResult(success=False, error=str(exc))`。
- 同类异常若发生在 R02 `run_detail_load_gate()` 调用 `capture_observation()` 时，则被该 gate 捕获为 `reason=ocr_error`、未知 R02 指标，消耗 R02 的一次有限重试预算。
- 成功 OCR 的空列表不是异常：有效 item 列表为空，R02 得到 `ocr_box_count=0`、`ocr_text_length=0` 与 `zero_ocr_boxes`。

R03 不能改变这些已经存在的 capture/backend/现有文本处理异常边界。

## 3. 当前 OCR/R02 调用链

有关键词的 favorite、forward 和 forward + `--no-forward` 共用历史条件 `forward_enabled and forward_keywords`。当前已实现的调用链为：

```text
run()
→ 首位打开或 next_candidate() 的既有等待
→ run_detail_load_gate(candidate_in_batch, total_viewed, ...)
   → ocr_detector.capture_observation(1)
   → evaluate_detail_page_load(ocr_box_count, ocr_text_length, 5, 30)
   → 未加载/ocr_error 时最多 3 次 safe_wait(1.5) + 同位置新采集
→ loaded 时返回同一个 first_observation
→ total_viewed += 1
→ view_candidate(i, first_observation=...)
→ detect_keywords(first_observation=...)
→ ocr_detector.detect(rules, first_observation=...)
```

`OCRKeywordDetector.detect()` 的真实控制流：

```text
for scan_number in 1..max_scans:
  scan_number > 1: scroll(); wait(settle_seconds)
  scan 1 且有 first_observation: _match_observation(first_observation, rules)
  否则: _observe(scan_number, rules)
  append first observation
  未命中：继续
  命中：wait(confirmation_seconds)
        _observe(same scan_number, [first.matched_rule])
        append confirmation
        返回确认结果
```

`_observe()` 是 `capture_observation()` 后接 `_match_observation()` 的兼容包装。首次 prefetch observation 按对象身份直接复用：不再次 capture/backend，不重复首屏 scan log，只 match 和 append 一次。首屏命中仍会执行独立二次 OCR；首屏未命中才在第 2 屏前滚动。

### 3.1 正式候选人扫描生命周期

当前正式首屏进入 `view_candidate()` 前，已经在 `run()` 的 R02 gate 内创建。该 observation 只有在判定 `loaded` 后才被传入 `view_candidate()` 并在 detector 中成为正式 scan 1；R02 未加载和 retry observation 没有进入 detector 的 `DetectionResult.observations`。

- 后续正式屏由 `OCRKeywordDetector.detect()` 的 `_observe(scan_number, rules)` 创建，`scan_number` 为 2—8。
- `OCR_MAX_SCANS = 8` 在 `ensure_ocr_region_calibrated()` 创建 detector 时注入；`for range(1, max_scans + 1)` 限制最多 8 个正式 scan number。
- `scan_number > 1` 才调用 `scroll()`；因此最多 7 次 OCR 有序滚动。
- 二次确认使用与命中屏相同的 `scan_number`，但会产生另一个 `ScanObservation` 并被 append 到 `DetectionResult.observations`。它不是一张新增的正式屏。
- 无关键词纯浏览不初始化/校准 OCR、不运行 R02 gate、不进入上述 OCR 正式扫描；R03 不改变这个范围。

当前没有长期存在的 `Candidate` 对象或“当前候选人正式 observation 列表”。`DetectionResult.observations` 是一次 `detect_keywords()` 内局部 result 的 observation 列表，包含正式扫描及可能的二次确认，返回后没有被 `run()` 保存。`ocr_detector` 是跨候选人复用的长寿命对象，但只保留 backend、capture、region 和配置，不保留 observations。`first_observation` 只作为本次 `view_candidate()` 调用参数；下一候选人会生成新局部变量。按当前引用图，候选人处理结束后其 observations 及其中任何后续 fingerprint 可由 Python 正常释放；未发现跨候选人列表泄漏的证据。

### 3.2 日志与隐私现状

`simple_brush.py` 在导入时建立 `logs/` 并使用标准 logging：

```text
文件：logs/simple_brush.log，UTF-8 append
格式：%(asctime)s [%(levelname)s] %(message)s
控制台：%(asctime)s %(message)s（%H:%M:%S）
```

R02 结构化事件使用参数化的 key=value 消息。冻结事件为 `detail_load_check`、`detail_load_recovery_start`、`detail_load_recovery_reopen_completed`、`detail_load_recovery_confirmed`、`detail_load_failed`。R02 的 `detail_load_check` 冻结 `decision=ready|not_loaded|error`，加载状态为 `loading|load_retrying|loaded|load_recovering|load_failed`；OCR 异常指标写 `-`，不会伪造为 0。

当前 `detect_keywords()` 的普通 OCR log 会输出 scan number、elapsed、过滤前 `item_count`、是否命中及规则，不输出 `ScanObservation.text`。R02 已有 `test_detail_load_check_logs_frozen_fields_without_ocr_text`：以唯一标记 `PRIVATE_OCR_BODY` 验证结构化加载日志不含 OCR 正文。这是 R03 隐私测试应沿用的模式。

## 4. 问题定义

R02 只能回答“本次 OCR 的有效框数/文本长度是否达到最低加载门”。现有规则文本是为关键词匹配而作的 NFKC、小写与去空白结果，不能作为可重放的页面证据；backend 返回顺序也不是项目确认的阅读顺序。

R03 要为每次成功获得的 OCR 屏幕 observation 提供最小、可比较的基础事实：在**同一版本**的机械排序、机械文本规范化和 SHA-256 规则下，两个 observation 的文字证据是否精确相同、精确不同，或无法比较。它不把这一事实解释为候选人已切换、页面已加载、页面到底、扫描应结束或应当执行动作。

## 5. 目标和非目标

### 5.1 目标

R03 v1 必须：

1. 只复用一次既有 `accepted_ocr_items()` 的 confidence 结果；不新增阈值、不重复过滤。
2. 对 accepted items 按本 RPD 的坐标规则恢复确定性阅读顺序。
3. 生成内存中的 `raw_text`、`normalized_text`、两种长度、`ocr_box_count`、可选 `screen_index`、带时区 `captured_at`、`fingerprint_version` 与 `exact_hash`。
4. 固定第一版 `fingerprint_version = "r03-v1"`。
5. 对 `normalized_text` 的 UTF-8 bytes 用标准库 SHA-256 生成 lowercase hexadecimal `exact_hash`。
6. 提供精确相同 `True`、精确不同 `False`、不可比较 `None` 的三态比较基础事实。
7. 将正文只保存在本次进程内存；普通日志最多记录 hash 和无正文元数据。
8. 生成失败时让既有 ScanObservation、R02、规则扫描、候选人浏览和既有动作门继续按原语义运行。

### 5.2 非目标

R03 明确不实现：

- R01 的右方向键候选人切换成功验证，或任何“前后 hash 不同即换人成功”的推断；
- R02 的加载判定、重试、硬恢复、计数或 `ocr_error` 语义变更；
- R04 的业务/匹配文本规范化升级；
- R05 的多屏去重或聚合；
- R06 的 SimHash、编辑距离、相似度或阈值比较；
- R07 的页面到底、动态扫描结束、停止滚动或扫描结束决策；
- R08 的候选人统一 JSON、跨候选人模型、导出或证据文件；
- R13 的 SQLite、数据库 migration 或任何永久存储；
- 姓名、正文锚点、DOM、浏览器 API、Selenium/Playwright/WebDriver、OCR 自动点击、候选人身份去重、动作决策；
- 为 R03 新增 CLI/GUI、配置文件、后台线程、通用状态机或隐私上传。

## 6. 推荐数据结构

### 6.1 推荐方案：小型 ScreenFingerprint 由 ScanObservation 持有

推荐后续 TID 采用方案二：在 `ocr_detector.py` 定义相邻的小型 `ScreenFingerprint`，并在 `ScanObservation` 的**末尾**新增 `fingerprint: Optional[ScreenFingerprint] = None`。建议形状如下，仅为产品字段合同，不构成本 Change 的实现授权：

```python
@dataclass
class ScreenFingerprint:
    fingerprint_version: str
    exact_hash: str
    raw_text: str
    normalized_text: str
    raw_text_length: int
    normalized_text_length: int
    ocr_box_count: int
    screen_index: Optional[int]
    captured_at: str
```

生成失败时 `ScanObservation.fingerprint` 必须为 `None`；不得创建带空字符串 hash 的伪 fingerprint。合法的空 OCR 文本是例外：它可产生真实的 SHA-256 空字节 hash，见第 9 节。

`ScreenFingerprint` 不保存 `OCRItem`、原始/accepted item list、box、单框 confidence、候选人号码或批次号码。它也不拥有扫描、匹配、动作或持久化职责。

### 6.2 方案比较

| 维度 | 方案一：直接扩展 ScanObservation | 方案二：ScreenFingerprint + Optional 字段 | 结论 |
| --- | --- | --- | --- |
| 字段数量与职责 | 将 9 个指纹/文本/时间字段混入 scan、规则匹配和 R02 指标。 | observation 继续代表采集/扫描；fingerprint 聚合仅 R03 证据。 | 方案二职责更清晰。 |
| 现有 dataclass 风格 | `ScanObservation` 已是可变、少字段的运行 observation。 | 仓库已有 OCR/校准小 dataclass；新增一个相邻、小范围 dataclass 符合风格。 | 方案二不是引入框架。 |
| 首屏复用 | 直接字段可随 R02 的对象身份复用。 | fingerprint 随同一个 observation 复用，无二次 OCR。 | 两者都可行；方案二同样满足。 |
| 指纹失败降级 | 多个可选字段容易留下半成品状态。 | 一个明确的 `fingerprint=None` 即表示生成不可用。 | 方案二更易 fail-open。 |
| 正式 screen_index 后置赋值 | observation 混合“采集时未知”和“正式后已知”。 | 只修改 fingerprint 的可选 `screen_index`，不污染 scan_number。 | 方案二更贴合 R02 promote 生命周期。 |
| 内存 | 两者均保存两段文本；对象额外开销可忽略。 | 同等正文内存，只有一个很小 object。 | 无实质差异。 |
| 测试复杂度 | 需要在已很长的 observation 字段顺序断言中塞入很多字段。 | 可独立测试 builder/compare，observation 只测持有和 `None` 降级。 | 方案二更局部。 |
| OCRItem 列表 | 若直接扩展容易诱导把列表塞进 observation。 | 明确禁止列表，只保存所需文本和摘要。 | 方案二更能维持 R02 边界。 |
| 未来 R01/R07 接入 | 可能使“scan observation”变成隐性候选人状态桶。 | R01/R07 可读取三态事实，但不能把 fingerprint object 变成流程裁决器。 | 方案二保留清晰边界。 |
| 是否过度设计 | 一个 dataclass 仍是最小封装。 | 没有 registry、protocol、enum、service、repository 或跨进程模型。 | 方案二不属于过度设计。 |

推荐方案二。它只把已经需要共同存在、共同释放的 R03 字段放在一个相邻 object 中；不新增候选人实体、全局列表或抽象层。

## 7. 数据语义：坐标排序需求

### 7.1 输入和可解析几何

输入只可以是同一次 `capture_observation()` 已经得到的 `accepted_items`。R03 不得重新执行 `accepted_ocr_items()`，也不得使用低 confidence item。

每个 accepted item 都必须有可解析几何，才可以生成该次 fingerprint。可解析的定义为：

1. `box` 是非空可迭代 point 序列；
2. 每个 point 至少具有 `[0]` 与 `[1]`；
3. 每个 x/y 可转为有限 `float`；
4. 可从全部 point 计算 min/max。

`width == 0` 或 `height == 0` 的退化框仍是可解析几何：它参与排序，行高计算使用 `max(1.0, height)`，不被删除。任何 accepted item 是 `box=None`、空 box 或不可解析/非有限坐标时，R03 builder 判为**指纹生成失败**，使该 observation 的 `fingerprint=None`。它不删除该 item，不改变 R02 `ocr_box_count`，不改变现有 searchable_text，也不伪造 backend 顺序的 canonical hash。

这比把无坐标 item 按 backend 返回顺序附在末尾更符合“确定性坐标阅读顺序”：当前 upstream 顺序无保证，缺失坐标无法可靠恢复空间顺序。

### 7.2 固定排序算法

对每一个可解析 item，先计算：

```text
left     = min(x)
right    = max(x)
top      = min(y)
bottom   = max(y)
height   = max(1.0, bottom - top)
center_y = (top + bottom) / 2.0
```

固定算法与既有 `order_items()` 的自适应行意图相容，但不修改该 helper 的规则文本行为：

1. 为每个 item 记录本 observation 内的原始 index，仅用于完全坐标相等的最终 tie-breaker。
2. 先按 `(center_y, top, left, bottom, right, original_index)` 排序。
3. 依该顺序依次放入第一条满足条件的既有行；一行的中心和高度是已放入 item 的算术均值，容差为 `max(8.0, min(item_height, line_height) * 0.5)`。当 `abs(item.center_y - line.center_y) <= tolerance` 时属于该行；否则创建新行。
4. 行按 `(line.center_y, first_item_top, first_item_left)` 排序；同一行 item 按 `(left, top, right, bottom, original_index)` 排序。
5. 依行序、再同行 item 序输出，即为 R03 读取顺序。

这个算法可处理四点旋转框的轴对齐包围范围，也对同 observation 的相同输入给出确定输出。若两个 item 的所有几何值完全相同，`original_index` 只能保证该次 backend 输出内的确定性；跨两次 OCR 的这种完美重合框仍可能受 upstream 返回顺序影响。这是第 16 节明确的 R03 限制，而不是候选人或页面状态结论。

## 8. 最小文本规范化

### 8.1 固定分隔符和 raw_text

固定框间分隔符为单个 LF 字符 `"\n"`（U+000A）。按第 7 节顺序的全部 accepted item 都参与 raw_text，包括空文本和只含空白的文本：

```text
raw_text = "\n".join(item.text for item in ordered_accepted_items)
raw_text_length = sum(len(item.text) for item in ordered_accepted_items)
```

`raw_text` 是源文本证据：不做 `strip()`、空白压缩、NFKC、大小写、标点删除、UI 删除、去重、翻译或语义改写。`raw_text_length` 是参与指纹生成的原始 item.text 的 Python 字符数总和，**不包含**程序插入的 LF 分隔符。

### 8.2 fixed normalized_text

每个 item.text 独立执行以下纯机械步骤：

1. `value = item.text.strip()`；
2. `value = re.sub(r"\s+", " ", value)`，把连续 Python/Unicode 正则空白压缩为一个普通 ASCII 空格 U+0020；
3. 若 `value == ""`，忽略它；否则保留。

最后：

```text
normalized_text = "\n".join(non_empty_normalized_values)
normalized_text_length = len(normalized_text)
```

`normalized_text_length` 是最终字符串的 Python `len()`，因此包含实际保留下来的 LF 分隔符。R03 v1 不执行 NFKC、lower、标点删除、全半角变化、行间语义重排、重复消除、UI 删除或任意模糊/语义处理；它和现有 `ocr_text.normalize_text()` 是不同且不得互相替换的契约。

## 9. SHA-256 语义

`fingerprint_version` 第一版固定为 `r03-v1`。对由第 8 节得到的 `normalized_text` 精确执行：

```python
hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
```

结果是标准库 SHA-256 的完整 64 个 lowercase hexadecimal 字符串，记为 `exact_hash`。不得加入 salt、随机数、候选人信息、时间或任何非文本字段。

以下字段**不参与 hash**：`captured_at`、`screen_index`、`ocr_box_count`、`raw_text_length`、`normalized_text_length`、候选人序号、批次序号、任一 confidence、scan_number、elapsed、版本号和坐标。坐标只决定 item 的拼接顺序。

合法的空结果和失败必须严格区分：若 OCR 调用成功、accepted items 为空且排序/构建正常，则 `raw_text==""`、`normalized_text==""`、长度为 0、`ocr_box_count==0`，并且 `exact_hash` 是 SHA-256 的真实空 UTF-8 byte hash。这是有效 fingerprint。若 builder 自身失败，必须使用 `fingerprint=None`，绝不能以 `""`、空文本 hash 或任何默认 hash 伪装失败。

`captured_at` 是 observation 完成时间，而不是 capture 开始时间；使用带 UTC offset 的 ISO 8601 字符串（例如 `2026-07-29T21:46:56.123456+08:00`）。它必须由具备时区的当前时间构造，不能使用无时区 `datetime.now()` 字符串；不参与 hash。

## 10. screen_index、存储和生命周期

### 10.1 正式 screen_index

`screen_index` 是 R03 的正式页面编号，不等同于 `ScanObservation.scan_number`：

| observation 来源 | `screen_index` | 保留规则 |
| --- | ---: | --- |
| R02 初次加载检测，尚未判定 loaded | `None` | 仅当前 gate 调用；不是正式屏。 |
| R02 retry observation | `None` | 不进入正式 1—8 屏；不因生成 hash 而成为页面。 |
| R02 成功、随后按对象身份复用的同一首屏 | `1` | 原 observation 被 promote 为正式首屏，不重复 OCR。 |
| detector 的正式第 2—8 屏 | `2`—`8` | 与正式 scan_number 相同。 |
| 命中规则后的独立二次确认 OCR | `None` | 可以产生临时 fingerprint，但不额外占一张正式屏，也不进入最多 8 个正式保留项。 |

对新创建的 observation，fingerprint builder 初始设置 `screen_index=None`；只有进入正式扫描的对象才后置赋值。首屏 promotion 必须发生在 R02 `loaded` 后、正式规则匹配前。R03 不得让失败 R02 retry 计入 1—8，也不得因为二次确认产生第 9 张正式屏。

### 10.2 内存和释放

R03 v1 的正文和 fingerprint 只保存在进程内存：

- 通过把 fingerprint 挂在 `ScanObservation`，复用本次 detector result 的既有局部生命周期；不建立按候选人、按批次或全局的平行 hash/text 列表。
- 当前候选人最多保留 8 个**正式**屏 fingerprint；confirmation 与加载/retry observation 只能是临时对象，不得形成第 9 个正式保留项。
- `DetectionResult.observations` 在当前实现中还可能持有一条 confirmation observation；TID 必须确保“最多 8 个正式屏”的规则按 `screen_index is not None` 理解，而不是误把 result list 总长度当作正式页数。
- `detect_keywords()` 返回后没有当前候选人的 result 持久化位置；候选人处理结束后，局部 result/observation/fingerprint 允许正常释放。不得将其写入模块全局、日志正文、JSON、SQLite、截图证据或独立文件。

本 RPD 不要求为历史追踪保留 fingerprint；后续 R08/R13 若需要持久化，必须另行定义字段脱敏、保留期、访问和删除策略。

## 11. 比较三态

R03 只提供下列三态基础事实，推荐使用 `Optional[bool]` 而不是新 Enum：

| 返回值 | 条件 | 语义 |
| --- | --- | --- |
| `True` | 两个有效 fingerprint 的 `fingerprint_version` 相同且 `exact_hash` 完全相同 | 精确相同。 |
| `False` | 两个有效 fingerprint 的版本相同且 hash 不同 | 精确不同。 |
| `None` | 任一 fingerprint 缺失、hash 缺失/无效、版本不同，或调用者没有两个有效对象 | 不可比较。 |

两个 `None` 绝不能返回 `True`。版本不同也不能返回 `False`：它表示算法/语义不一致，而非内容不同。比较不读取 raw_text，不进行 fallback 文本比较、前缀比较、长度比较、相似度比较或 hash 截断。

当前 R03 不把比较结果接入 `next_candidate()`、`run_detail_load_gate()`、`evaluate_detail_page_load()`、`OCRKeywordDetector.detect()` 的滚动分支、`view_candidate()` 的动作分支或 `refresh_page()`。调用者最多得到一个事实；任何流程含义必须由未来明确需求另行定义。

## 12. 失败降级

### 12.1 分层原则

| 情况 | 处理层 | R03 行为 |
| --- | --- | --- |
| MSS capture 或 OCR backend 异常 | 既有 R02/正式 detector 边界 | R03 不得捕获或吞掉；保持现有 `ocr_error` / `DetectionResult(success=False)`。 |
| 既有 `searchable_text()` 因非空 malformed box 异常 | 既有 R02/正式 detector 边界 | 不改变现有异常传播；R03 不得为了 hash 改写 R02。 |
| 已成功生成 ScanObservation 后，R03 坐标解析、排序、文本规范化、时间或 SHA-256 builder 异常 | 新增 R03 局部 builder 边界 | 记录安全失败元数据，令 `observation.fingerprint=None`，随后返回既有 observation。 |
| 比较输入不可用 | R03 compare helper | 返回 `None`；不抛出、不卡住扫描、不产生结论。 |

### 12.2 运行行为

fingerprint builder 异常不得：

- 触发 R02 retry、`load_recovering`、`load_failed`、候选人跳过、ESC 或程序停止；
- 改写 `ScanObservation.text`、`item_count`、R02 两项指标、`matched_rule`、`matched_keyword` 或 `DetectionResult.success`；
- 重复 capture、backend recognize、confidence 过滤、规则匹配、滚动或二次确认；
- 伪造 `exact_hash=""`、空 hash 或把失败判作同一页面。

这保证 R03 是现有成功 OCR observation 上的附加证据，而不是新的 OCR 运行门。

## 13. 日志和隐私

### 13.1 最小安全日志

R03 继续使用现有 `logger` 和 key=value 参数化格式，不引入日志框架。最小、安全的记录位置为：

1. **生成成功/失败**：紧邻 R03 builder 的唯一调用处（预期为 `capture_observation()` 的既有一次采集路径）。这样每次成功 OCR observation 最多记录一次，不会因 R02 首屏复用再生成一次。
2. **比较**：只有未来业务显式调用 compare helper 的调用点才记录。compare helper 本身保持纯函数，避免单元测试或未知调用产生日志副作用；R03 当前不强制创建任何比较调用点。

建议冻结字段：

```text
event=ocr_fingerprint_generated
fingerprint_version=r03-v1
exact_hash=<64 hex>
ocr_box_count=<integer>
raw_text_length=<integer>
normalized_text_length=<integer>
screen_index=<integer-or-none>
captured_at=<timezone ISO-8601>
scan_number=<integer>
```

```text
event=ocr_fingerprint_generation_failed
fingerprint_version=r03-v1
scan_number=<integer>
error_type=<exception class name>
```

```text
event=ocr_fingerprint_comparison
comparison=same|different|not_comparable
left_version=<version-or-none>
right_version=<version-or-none>
left_hash=<hash-or-none>
right_hash=<hash-or-none>
```

R03 不要求 `candidate_in_batch` 或 `batch`：当前 builder 和 detector 都没有该上下文，当前 R02 也没有 batch number。未来调用点若已有候选人/批次上下文，可以在不扩大保存范围的前提下附加；无论是否记录，它们都不参与 hash。

### 13.2 禁止泄露

普通日志、console、异常消息和结构化字段不得写入：

- `raw_text`、`normalized_text` 或任一完整/片段 OCR 正文；
- `OCRItem` 或 raw/accepted item list 的 repr；
- box/point/left/top/right/bottom/width/height/center_y；
- 单框 confidence 或任何逐框明细；
- 截图、JSON、SQLite 记录、证据文件或临时正文文件。

完整 hash 与无正文长度/数量/版本/时间元数据允许写普通日志，但仍可能是可关联标识，应沿用现有 `logs/` 的本地敏感数据处理说明，不上传或提交。

测试必须使用不可能自然出现在固定日志模板中的唯一正文标记（例如 `R03_PRIVATE_BODY_7f4a`）。测试应 render 所有新增 R03 logger 调用后断言该标记、坐标值、`OCRItem(` 和 confidence 明细均不出现；同时断言 hash/允许元数据出现。R02 现有 `PRIVATE_OCR_BODY` 模式可作为直接先例。

## 14. 与 R01、R02、R04、R06、R07、R08、R13 的边界

| 需求 | R03 边界 |
| --- | --- |
| R01 候选人切换 | hash 相同/不同都不证明右方向键是否已切换到新人；R03 不调用或影响 `next_candidate()`。 |
| R02 页面加载 | R02 的 box count/text length、四次预算、`ocr_error`、恢复、`total_viewed` 与结构化日志保持冻结；R03 builder 失败 fail-open。R02 success 首屏只被对象身份复用。 |
| R04 文本标准化 | R03 只采用第 8 节 strip + 空白压缩。它不改变现有关键词 NFKC/lower/去空白，亦不预先实施 R04 的任何可能扩展。 |
| R06 相似度指纹 | R03 仅 SHA-256 exact hash；不做 SimHash、相似度、距离、阈值或近似相同判断。 |
| R07 动态扫描结束 | 8 屏/7 滚动仍由当前 detector 既有边界保障。R03 不把重复 hash 解释为页面到底、重复屏或停止滚动。 |
| R08 候选人统一 JSON | 不创建 Candidate schema、不输出 JSON、不定义跨候选人/跨运行字段。只有内存 observation 可暂持 fingerprint。 |
| R13 SQLite | 不创建 DB、表、migration 或写入；本轮没有永久化。 |

仓库基线中没有单独的 R01/R04/R06/R07/R08/R13 RPD/TID 文件可作为更细事实来源；上述边界来自本任务冻结目标以及 R02 RPD/TID 对未来需求的明确排除，不能被解读为已完成的未来设计。

## 15. 建议修改文件（供后续 TID，不是本 Change 的授权）

| 文件 | 建议的最小职责 |
| --- | --- |
| `ocr_detector.py` | 添加相邻的 `ScreenFingerprint`、R03 纯 builder/geometry/compare helper，在已过滤的 `capture_observation()` 内构建并挂到 `ScanObservation`；保留 capture/backend 异常边界。 |
| `simple_brush.py` | 仅在必要的 R02 promote/正式 scan 生命周期点后置 `screen_index`，并在不重复日志的前提下接入允许的无正文日志；不得把比较用于流程决策。 |
| `tests/test_ocr_detector.py` | 覆盖排序、文本语义、SHA-256、空合法文本、box 失败降级、三态 compare、单次 capture/backend、首屏复用、8 屏/7 滚动和无 OCRItem 列表。 |
| `tests/test_simple_brush_ocr.py` | 覆盖 R02 initial/retry `None`、loaded 首屏=1、后续=2—8、confirmation=None、candidate-local释放语义和日志正文不泄露。 |
| `docs/RPD-R03-basic-ocr-page-fingerprint.md` | 本 Change 已新增；后续只在批准的需求澄清中维护。 |

不建议新建全局 fingerprint service、repository、JSON writer、SQLite 模块、候选人类、Enum 状态机或配置文件。`ocr_text.order_items()` 服务既有关键词搜索，R03 应在自己的纯 helper 中落实第 7 节严格失败/确定性 contract，避免无关改变现有 matcher 文本。

## 16. 风险和限制

1. SHA-256 相同只表示同版本 normalized_text bytes 相同，不证明候选人身份、完整视觉页面、DOM、加载完成或任何动作成功。
2. OCR 识别误差、可见区域、缩放、字体、动画、遮挡、网络加载和固定 UI 变化都会导致不同 hash；R03 不试图修正。
3. 完全重叠且几何相同的多个框只能用当前 backend 原始 index 打破平手；upstream 未保证跨调用排序，故跨调用可能不同。这是精确比较的保守限制。
4. 缺少/不可解析 box 会使 R03 fingerprint 缺失；R03 宁可不可比较，也不把 backend 顺序伪装成空间顺序。
5. raw_text/normalized_text 包含候选人可能的个人信息，即使只在内存也应最小化引用并在候选人结束后释放；日志 hash 仍可能关联内容。
6. 现有 OCR backend 同步，ESC/timer 不能中断正在执行的一次 OCR；R03 不改变这一限制。
7. 当前没有真实 BOSS 页面 E2E 自动化；mock/fake 只能验证调用、数据和隐私边界，不能证明真实 Edge 排版或 RapidOCR 返回顺序稳定。
8. 目前正式主循环是 Windows + Edge；不得从纯 OCR 单测推断 macOS Chrome 候选人流程已适配。

## 17. 自动化验收矩阵

| 范围 | 最低自动化断言 |
| --- | --- |
| confidence 复用 | 低于阈值不参与 raw/normalized/hash/count；等于阈值参与；不得第二次过滤。 |
| 坐标与旋转框 | 四点旋转框按 min/max 几何恢复行序/同行左至右；NumPy box 可用；退化有效框可排序。 |
| deterministic tie | 同输入重复构建得到相同 raw/normalized/hash；完全几何相同按 source index。 |
| 无效几何 | `None`、空、缺 x/y、不可转 float、NaN/Infinity 各得到 `fingerprint=None`，而 R03 helper 不抛出至调用者。 |
| raw_text | 固定 LF、保留原始空白、空文本 item 仍有其分隔位置；raw length 不含插入 LF。 |
| normalized_text | 单框 strip、连续空白压为 U+0020、规范化空文本忽略、最终 length 包含实际 LF；不 NFKC/lower/去标点/去重。 |
| SHA-256 | 与 `hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()` 完全一致；元数据改变不改变 hash。 |
| 合法空结果 | 成功的零 accepted item 产生真实空文本 SHA-256，不是 failure。 |
| 失败不伪造 | builder 异常/无效 box 为 `None`，不得返回空 hash 或空文本 fingerprint。 |
| compare | 同版本同 hash=True；同版本不同 hash=False；任一 None、hash 无效、版本不同、两个 None 均为 None。 |
| R02 首屏 | initial/retry 初始为 `screen_index=None`；loaded object 被复用并 promote 为 1，capture/backend 不重复。 |
| 8 屏生命周期 | 正式 2—8 依次编号；最多 8 正式 fingerprint、7 滚动；confirmation 有临时 fingerprint 但 screen_index=None。 |
| 不回归 R02 | R02 metrics/text/matcher/4 次预算/ocr_error/动作禁令不改变；fingerprint 失败不触发 R02 恢复或停止。 |
| 内存边界 | `ScanObservation` 不保存 item list；处理结束没有全局或跨候选人 fingerprint list。 |
| 日志与隐私 | generated/failed/compare 仅含允许 hash/元数据；唯一正文标记、box、confidence、OCRItem repr 不出现。 |
| 回归 | `tests/test_ocr_detector.py`、`tests/test_ocr_text.py`、`tests/test_simple_brush_ocr.py`、`tests/test_mouse_motion.py` 与全量 `unittest discover -s tests -v` 通过。 |

## 18. Windows + Edge 人工验收延期说明

本 Change 是需求审计与 RPD，不运行真实 GUI、不会连接真实 BOSS 页面，也不会触发刷新、筛选、收藏或转发。R02 acceptance report 也记录目前缺少可确认的测试账号、有效规则、可控网络延迟/失败环境和受授权安全 Edge 会话，其 Windows + Edge 人工冒烟仍为待执行。

因此 R03 的 Windows + Edge 人工验证延期到后续实现与验收 Change。届时必须在 Windows 10/11 x64、Microsoft Edge、测试账号、小样本、人工监控和优先 `--no-forward` 条件下进行。至少观察：首屏、滚动后第 2—8 屏、命中后二次确认、空/低 confidence OCR、窗口/缩放变化、日志只含 hash/元数据且无正文。任何真实转发不属于默认 R03 冒烟动作。

## 19. 待 TID 冻结的问题

下列是实现落点问题，不重新打开本 RPD 的产品语义：

1. **函数签名和私有名称**：确定 R03 builder、geometry parser、排序 helper 与 compare helper 在 `ocr_detector.py` 的精确名称、类型注解及测试导入面。
2. **screen_index promotion 的最小赋值点**：确定由 `run_detail_load_gate()` 的 loaded 分支、`detect()` 消费 prefetched observation 的分支，还是一个最小相邻 helper 完成后置赋值；必须同时覆盖无 prefetch detector 单测路径。
3. **fingerprint dataclass 的可变性**：产品已要求后置 screen_index；TID 可选用非 frozen dataclass 直接赋值，或 `dataclasses.replace()` 后回写 observation，但不得保存半成品或复制 OCR。
4. **精确日志调用位置与字段格式化**：生成日志需要避免 first-observation reuse 重复；compare 当前无业务调用者，TID 必须不虚构一条比较主链路。版本/hash 缺失的渲染应统一为安全元数据值。
5. **异常类型的内部表示**：RPD 已冻结为 `fingerprint=None` 和无正文 `error_type`；TID 决定使用专用轻量异常、返回哨兵或局部 `try/except`，但不得改变既有 OCR/R02 异常层。
6. **正式 8 项的临时保留表达**：当前 `DetectionResult.observations` 混有 confirmation；TID 需定义如何只在本候选人局部识别 `screen_index is not None` 的最多 8 项，而不增加平行、跨候选人列表。
7. **测试的时间固定方式**：`captured_at` 需要带时区且不进入 hash；TID 应使用注入时钟或 patch，使单测不依赖本机时区/瞬时时间。

## 20. 结论

R03 应以一个由 `ScanObservation` 持有的最小 `ScreenFingerprint` 实现，复用 R02 已接受的 OCR items 和首屏预取对象。它只增加“精确相同、精确不同、不可比较”的数据事实；正文只临时保存在内存，普通日志只记录 hash/元数据。R03 不能把 hash 当成候选人切换、加载完成、页面到底、扫描结束或动作执行的证据。
