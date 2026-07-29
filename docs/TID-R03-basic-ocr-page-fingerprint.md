# BossOCR R03：基础 OCR 页面指纹——Technical Implementation Document

## 1. 文档信息、批准来源和基线

| 项目 | 内容 |
| --- | --- |
| 文档类型 | TID（可直接实施的技术设计） |
| 需求编号 | R03：基础 OCR 页面指纹 |
| Change | Change 0B：技术设计文档 |
| 批准来源 | 用户已批准 `docs/RPD-R03-basic-ocr-page-fingerprint.md` |
| 实施基线 | `main@b9029bc022ae258ab62e2bc28ae64ead2dea2f35` |
| 基线提交说明 | `feat(r02): add detail page load detection` |
| 正式平台 | Windows 10/11 x64 + Microsoft Edge；OCR 纯测试仍不依赖 GUI |
| 本 TID | `docs/TID-R03-basic-ocr-page-fingerprint.md` |

Change 0B 开始时 `HEAD` 已核对为 `b9029bc`。工作区已有且不属于本 Change 的改动包括 `.gitignore`、`docs/Issue-Next-6-human-mouse-motion-acceptance-report.md`、`simple_brush.py`、`docs/project-review.zip`、`docs/project-review/`、`docs/tid/` 和 `venv-packages-before-reinstall.txt`。当前未提交的 `simple_brush.py` 改动只涉及停留期滚动步数，不改变本 TID 的 OCR/R02 调用链；以下设计仍以已提交基线为准。

本 Change 只创建本 TID。它不授权修改生产代码、测试、构建脚本、配置或 `.gitignore`，不实施 Change 1，不修改已批准 RPD，不提交。

## 2. 当前实现摘要

### 2.1 OCR 采集和 R02

`ocr_detector.py` 当前拥有完整 OCR observation 采集边界：

```text
OCRKeywordDetector.capture_observation(scan_number)
→ capture.capture(region) 一次
→ backend.recognize(image) 一次
→ accepted_ocr_items(raw_items, min_confidence) 一次
→ calculate_load_metrics(accepted_items)
→ searchable_text(accepted_items)
→ ScanObservation
```

`accepted_ocr_items()` 保留 `confidence >= min_confidence` 的 item。R02 的 `ocr_box_count` 是该 accepted list 的长度；`ocr_text_length` 是各 accepted `item.text.strip()` 非空后的字符数求和。`ScanObservation.text` 是现有 `searchable_text()` 的 NFKC、小写、删除空白的规则搜索文本，R03 不得改变它。

`simple_brush.run_detail_load_gate()` 以 `capture_observation(1)` 进行 R02 首次/最多三次 retry。未加载或 backend/capture 异常不会进入正式 detector result；成功 `loaded` observation 按对象身份传入 `view_candidate()`、`detect_keywords()` 和 `OCRKeywordDetector.detect(first_observation=...)`，不得再次 OCR。

### 2.2 正式扫描和现有对象生命周期

`OCRKeywordDetector.detect()` 对正式 scan number 1—8 循环；只有 2—8 屏前调用 scroll，所以最多 7 次滚动。首屏命中后会在相同 `scan_number` 产生一个独立 confirmation observation；它 append 到 `DetectionResult.observations`，但不是新增正式屏。

`ScanObservation` 当前是可变 dataclass，`_match_observation()` 会在原对象填写规则命中。`DetectionResult.observations` 是一次 detect 调用的局部列表；`simple_brush` 不保存该 result，也没有 Candidate 模型、跨候选人 observation list 或永久存储。这个事实允许 R03 把 fingerprint 作为 observation 的小字段，而不需要新的候选人容器。

### 2.3 现有错误和日志边界

capture/backend/既有 `searchable_text()` 异常在 R02 gate 被归为 `ocr_error`，在正式 detector 被转成 `DetectionResult(success=False)`。成功 OCR 的空列表则是正常 observation，R02 指标为 `0/0`。

日志使用现有 module logger 和 key=value 参数化消息。R02 已证明结构化日志不得输出 `ScanObservation.text`：测试使用唯一正文标记 `PRIVATE_OCR_BODY` 并断言其不泄露。R03 复用这一隐私测试模式。

## 3. 设计原则

1. **单次采集**：一次 observation 只 capture、recognize、confidence filter 一次；R03 只消费该 accepted list。
2. **值对象而非框架**：一个相邻 dataclass、若干纯函数和最小日志函数即可；禁止 service/provider/registry/pipeline/repository/state machine/configuration framework。
3. **R02 不变**：R02 两项指标、`ocr_error`、四次预算、首屏复用、加载恢复和 `total_viewed` 时点不改变。
4. **数据与流程分离**：hash/compare 只是事实，不驱动 next、refresh、scroll、动作或候选人切换结论。
5. **默认不可比较**：无 fingerprint、版本不同或 hash 无效一律 `None`；不伪造空 hash。
6. **隐私最小化**：正文仅在 observation 存活期间内存保存；日志仅允许 hash 和摘要元数据。
7. **局部失败开放**：指纹生成失败只得到 `fingerprint=None`，不成为 OCR/R02 失败。

## 4. 最终文件范围

R03 实施的常规生产修改只需 `ocr_detector.py`。`simple_brush.py` 不修改：R02 已在 detector 外完成首屏 prefetch，正式 index 可在 detector 的 `detect()` 消费对象时绑定；这样不需要在主循环增加候选人列表、screen counter 或新控制分支。

| Change | 允许修改的文件 | 不允许修改的相邻文件 | 说明 |
| --- | --- | --- | --- |
| Change 1 | `ocr_detector.py`、`tests/test_ocr_detector.py` | `simple_brush.py`、`ocr_text.py`、其他 tests | 纯数据/算法/比较能力，无生产调用。 |
| Change 2 | `ocr_detector.py`、`tests/test_ocr_detector.py` | `simple_brush.py`、`ocr_text.py`、其他 tests | 在既有 observation 采集点接入，不增加 OCR 或副作用。 |
| Change 3 | `ocr_detector.py`、`tests/test_ocr_detector.py` | `simple_brush.py`、`ocr_text.py`、其他 tests | detector 内完成正式 screen_index 与候选人局部生命周期。 |
| Change 4 | `ocr_detector.py`、`tests/test_ocr_detector.py` | `simple_brush.py`、`ocr_text.py`、其他 tests | 新增 R03 结构化日志和最终隐私/异常收口。 |
| Change 5 | 新增 `docs/R03-basic-ocr-page-fingerprint-acceptance-report.md`；只有测试暴露 R03 直接缺陷时才可最小修改 `ocr_detector.py`、`tests/test_ocr_detector.py` | 所有其他生产/测试/配置/构建文件 | 完整回归、审计和验收；不得顺手重构。 |

`tests/test_ocr_text.py`、`tests/test_simple_brush_ocr.py`、`tests/test_mouse_motion.py` 不计划编辑；Change 5 必须运行它们验证关键词、R02、模式、焦点恢复、正常刷新和鼠标路径不回归。`ocr_text.order_items()` 不修改，因为它是已有 searchable text 的合同，且无坐标 item 的既有行为不能被 R03 顺手改变。

## 5. 数据结构

### 5.1 常量

在 `ocr_detector.py` 的现有 helper 区域末尾，即 `evaluate_detail_page_load()` 后、`OCRBackend` protocol 前，增加仅供 R03 使用的常量：

```python
FINGERPRINT_VERSION = "r03-v1"
FINGERPRINT_SEPARATOR = "\n"
FINGERPRINT_MIN_LINE_TOLERANCE = 8.0
FINGERPRINT_LINE_HEIGHT_RATIO = 0.5
FINGERPRINT_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
FINGERPRINT_WHITESPACE_PATTERN = re.compile(r"\s+")
```

它们不是用户配置、CLI 参数或运行期 profile。数值 `8.0` 和 `0.5` 是第 7 节冻结的排序合同，必须通过具名常量使用。

### 5.2 ScreenFingerprint

选择 RPD 推荐的方案二：在同一 protocol 前 helper 区域、R03 常量之后新增小型 immutable value object，并由既有可变 observation 可选持有。

```python
@dataclass(frozen=True)
class ScreenFingerprint:
    raw_text: str
    normalized_text: str
    raw_text_length: int
    normalized_text_length: int
    ocr_box_count: int
    captured_at: str
    exact_hash: str
    fingerprint_version: str = FINGERPRINT_VERSION
    screen_index: Optional[int] = None
```

字段语义：

| 字段 | 类型/默认值 | 语义 |
| --- | --- | --- |
| `raw_text` | `str`，必填 | 已排序 accepted item 的原始源文本证据。 |
| `normalized_text` | `str`，必填 | R03 最小机械规范化后的文本。 |
| `raw_text_length` | `int`，必填 | 原始 item.text Python 字符数之和，不含插入分隔符。 |
| `normalized_text_length` | `int`，必填 | `len(normalized_text)`，含实际存在的分隔符。 |
| `ocr_box_count` | `int`，必填 | 已过滤 accepted list 的长度；与 R02 完全同口径。 |
| `captured_at` | `str`，必填 | observation 完成时的带 UTC offset ISO 8601。 |
| `exact_hash` | `str`，必填 | 64 个 lowercase SHA-256 hex；有效 fingerprint 不可缺失。 |
| `fingerprint_version` | `str`，默认 `FINGERPRINT_VERSION` | 算法/文本语义版本，v1 为 `r03-v1`。 |
| `screen_index` | `Optional[int]`，默认 `None` | `None` 表示尚未/从未成为正式 1—8 屏；正整数是正式屏号。 |

`ScreenFingerprint` frozen 的原因是 raw/normalized/hash/captured_at 是采集事实，不应被后续匹配或主循环误改。`screen_index` 的后置绑定使用 `dataclasses.replace()` 产生新 value object，再回写到可变 `ScanObservation`；不重新排序、规范化、hash 或 OCR。

在 `ScanObservation` 的**最后**追加：

```python
fingerprint: Optional[ScreenFingerprint] = None
```

`None` 只表示 R03 builder 不可用/失败，不表示空 OCR 文本。没有 `OCRItem`、raw_items、accepted_items、box/point list、单框 confidence list、候选人号码或批次号码进入任一长期 observation 字段。

### 5.3 内部失败类型

在同一 protocol 前 helper 区域增加：

```python
class FingerprintBuildError(ValueError):
    """Raised for an R03-only fingerprint construction failure."""
```

它的 message 只使用固定技术原因，不拼接 item、box、文本或 upstream object repr。`capture_observation()` 只以 `type(exc).__name__` 记录它；外部 API 不依赖其 message。

## 6. 函数签名和落点

采用按运行时依赖顺序放置的最小方案，而非 postponed annotations、字符串类型注解或移动既有 `ScanObservation`。R03 常量、`FingerprintBuildError`、`ScreenFingerprint` 以及不依赖 `ScanObservation` 的纯 helper 位于现有 helper 区域末尾：`evaluate_detail_page_load()` 后、`OCRBackend` protocol 前。`bind_fingerprint_screen_index()` 和 `_log_fingerprint_generated()` 的参数直接注解 `ScanObservation`，必须位于既有 `ScanObservation` 定义之后。`_log_fingerprint_generation_failed()` 与 `log_fingerprint_comparison()` 不依赖 `ScanObservation`，但为保持日志 helper 连续，冻结为同在 `ScanObservation` 后、`DetectionResult` 前的统一 R03 日志 helper 区域。

除日志函数和 `bind_fingerprint_screen_index()` 外，其余 R03 helper 均为小型纯函数；不访问 MSS、RapidOCR、scroll、wait 或 `simple_brush` 全局状态。`bind_fingerprint_screen_index()` 会以新的 frozen value object 回写可变 `ScanObservation.fingerprint`，因此不是纯函数；它只在 Change 3 实现。Change 1 不实现该 helper、不修改 `detect()`，也不执行任何正式 `screen_index=1—8` 赋值。

```python
# At the end of the existing helper region, before OCRBackend.
def fingerprint_box_bounds(
    box: Optional[Sequence[Sequence[float]]],
) -> Tuple[float, float, float, float, float, float, float]:
    """Return left, top, right, bottom, width, height, center_y."""

def order_fingerprint_items(
    accepted_items: Sequence[OCRItem],
) -> List[OCRItem]:
    """Return accepted OCR items in the R03 coordinate reading order."""

def normalize_fingerprint_item_text(text: str) -> str:
    """Apply only the R03 per-item strip and whitespace compression."""

def build_fingerprint_raw_text(
    ordered_items: Sequence[OCRItem],
) -> Tuple[str, int]:
    """Return raw_text and raw_text_length without separator length."""

def build_fingerprint_normalized_text(
    ordered_items: Sequence[OCRItem],
) -> Tuple[str, int]:
    """Return normalized_text and normalized_text_length."""

def sha256_normalized_text(normalized_text: str) -> str:
    """Return the SHA-256 lowercase hex digest of UTF-8 text."""

def build_screen_fingerprint(
    accepted_items: Sequence[OCRItem],
    *,
    captured_at: Optional[datetime] = None,
) -> ScreenFingerprint:
    """Build one valid r03-v1 fingerprint or raise FingerprintBuildError."""

def compare_screen_fingerprints(
    left: Optional[ScreenFingerprint],
    right: Optional[ScreenFingerprint],
) -> Optional[bool]:
    """Return True, False, or None for exact R03 comparison."""
```

既有 `OCRBackend` 与 `ScreenCapture` protocol 随后保持原位；既有 `ScanObservation` 定义保持原位。紧随 `ScanObservation`、在 `DetectionResult` 前放置以下非纯 bind 与统一日志 helper：

```python
# Immediately after ScanObservation, before DetectionResult.

def bind_fingerprint_screen_index(
    observation: ScanObservation,
    screen_index: int,
) -> None:
    """Replace a valid observation fingerprint with its formal screen index."""

def _log_fingerprint_generated(observation: ScanObservation) -> None:
    """Write R03 generated metadata only; never body/evidence."""

# Same unified R03 logging-helper region; these two do not require ScanObservation.
def _log_fingerprint_generation_failed(
    scan_number: int,
    error_type: str,
) -> None:
    """Write the sanitised R03 failure event."""

def log_fingerprint_comparison(
    left: Optional[ScreenFingerprint],
    right: Optional[ScreenFingerprint],
    comparison: Optional[bool],
) -> None:
    """Write a future caller's R03 comparison fact without flow effects."""
```

`datetime` is imported from the standard library `datetime` module; `hashlib`、`math`、`re` and `dataclasses.replace` are likewise standard-library imports. No dependency file changes are permitted.

### 6.1 Captured time injection

`build_screen_fingerprint()` is the only automatic time source. It freezes this order:

```text
if caller supplied captured_at:
    validate it is an aware datetime, but do not yet create its string
→ order_fingerprint_items(accepted_items)
→ build_fingerprint_raw_text(ordered)
→ build_fingerprint_normalized_text(ordered)
→ sha256_normalized_text(normalized_text)
→ if captured_at was not supplied:
      captured_at = datetime.now().astimezone()
→ captured_at.isoformat()
→ ScreenFingerprint(...)
```

An injected `captured_at` is primarily for deterministic tests. It must be aware (`tzinfo is not None` and `utcoffset() is not None`), otherwise raise `FingerprintBuildError("fingerprint timestamp must include a timezone")`; the validation occurs before ordering, but no output string or fingerprint is created before the text and hash steps succeed. When the builder generates time itself, it samples `datetime.now().astimezone()` only after sorting, both text constructions and SHA-256 have succeeded. That value is the final time immediately before successful fingerprint construction/observation return, i.e. the R03 observation/fingerprint completion time. `captured_at` never enters the hash, and later screen-index binding must not rewrite it. A failed builder creates neither a `ScreenFingerprint` nor a fabricated completion time.

### 6.2 Binding contract

`bind_fingerprint_screen_index()` must:

1. require `screen_index >= 1`, otherwise raise `ValueError`;
2. return immediately if `observation.fingerprint is None`;
3. replace only `screen_index` via `replace(observation.fingerprint, screen_index=screen_index)`;
4. assign that new fingerprint to `observation.fingerprint` and return `None`.

It must not touch `scan_number`、`text`、R02 metrics、matched fields、hash、captured_at or textual evidence. It deliberately does not enforce `<= 8`; `detect()` already owns the max-scan loop, while the helper remains usable in direct detector tests.

## 7. 坐标排序算法

### 7.1 Box 边界提取和无效 box

`fingerprint_box_bounds(box)` accepts the real current `OCRItem.box` shape: an optional nested sequence; normal RapidOCR data is a four-point rotated polygon, and NumPy arrays are supported through iteration.

Implementation steps:

1. Reject `None`.
2. Materialize the iterable into points; reject zero points.
3. For every point, read `[0]` and `[1]`, convert both to `float`, and require `math.isfinite(x)` and `math.isfinite(y)`.
4. Compute `left=min(xs)`、`right=max(xs)`、`top=min(ys)`、`bottom=max(ys)`、`width=right-left`、`height=bottom-top`、`center_y=(top+bottom)/2.0`.
5. Return the seven values in the signature order.

Missing point components, non-iterable data, nonnumeric values, NaN, Infinity and empty boxes raise `FingerprintBuildError("fingerprint box geometry is invalid")`. Degenerate boxes (`width == 0` or `height == 0`) are valid; later line-height math uses `max(1.0, height)`.

The helper supports rotated boxes by calculating their axis-aligned min/max extent. It does not need perspective correction, OCR angle inference, visual clustering, AI or any extra geometric model.

### 7.2 Record construction and line grouping

`order_fingerprint_items()` consumes only the already filtered `accepted_items` sequence. For each item it stores a local, non-persisted record:

```text
(item, original_index, left, top, right, bottom,
 width, effective_height=max(1.0, height), center_y)
```

It first sorts records by:

```text
(center_y, top, left, bottom, right, original_index)
```

It then consumes this order to build lines. A line holds its members plus the arithmetic mean `line_center_y` and arithmetic mean `line_height` of already assigned members. For a candidate record, the tolerance is exactly:

```text
max(FINGERPRINT_MIN_LINE_TOLERANCE,
    min(candidate.effective_height, line.line_height)
    * FINGERPRINT_LINE_HEIGHT_RATIO)
```

With frozen values, that is `max(8.0, min(candidate_height, line_height) * 0.5)`. The candidate belongs to the **first existing line in current line order** for which:

```text
abs(candidate.center_y - line.line_center_y) <= tolerance
```

Otherwise it starts a new line. After appending, recompute the target line's center/height as arithmetic means; do not use weighted/median/cluster library behavior.

Finally sort lines by:

```text
(line_center_y, first_member.top, first_member.left)
```

and sort each line's members by:

```text
(left, top, right, bottom, original_index)
```

Concatenate line members in that order and return their original `OCRItem` values. The local geometry records are discarded at return; they never enter `ScanObservation` or `ScreenFingerprint`.

### 7.3 Determinism and the approved tie limitation

For distinct geometry keys, the result is independent of input array permutation. Change 1 tests must shuffle the same non-tied OCR items and assert identical output, raw text and hash; it must also cover small y variation within the exact tolerance formula.

The approved RPD explicitly makes `original_index` the final tie-breaker for items whose coordinate keys are completely equal. Therefore a permutation of two **different-text** items with completely equal `(left, top, right, bottom)` intentionally preserves that observation's source order and can produce a different textual sequence. This is the approved, documented limitation of absent spatial information; it must not be hidden by adding a text/AI tie-breaker or silently changing the approved RPD algorithm. The tie-breaker test asserts source-order behavior, and the shuffled-input stability test excludes complete coordinate ties. Two fully tied items with identical text produce the same text sequence regardless.

This is the sole scoped qualification to “shuffled input stability”; it is not a reason to change backend order, R02, candidate flow or the RPD in this Change.

## 8. 文本规范化和长度

### 8.1 Accepted item reuse

`capture_observation()` performs the only confidence filter:

```python
accepted_items = accepted_ocr_items(raw_items, self.min_confidence)
```

The exact same list object is passed to all three consumers in this fixed order:

```text
calculate_load_metrics(accepted_items)  # existing R02 values
searchable_text(accepted_items)         # existing ScanObservation.text
build_screen_fingerprint(accepted_items)
```

`build_screen_fingerprint()` must not inspect `item.confidence`, call `accepted_ocr_items()` or receive raw_items. This prevents a second threshold and proves R03 `ocr_box_count == len(accepted_items)` is exactly R02's value.

### 8.2 raw_text

`FINGERPRINT_SEPARATOR` is exactly `"\n"` (one U+000A LF). Given `ordered_items` from section 7:

```python
raw_text = FINGERPRINT_SEPARATOR.join(item.text for item in ordered_items)
raw_text_length = sum(len(item.text) for item in ordered_items)
```

All accepted items contribute to raw_text, including `""` and whitespace-only text. No strip/NFKC/lowercase/punctuation removal/UI removal/deduplication occurs. `raw_text_length` never includes separators inserted by join.

### 8.3 normalized_text

`normalize_fingerprint_item_text(text)` does exactly:

```python
return FINGERPRINT_WHITESPACE_PATTERN.sub(" ", text.strip())
```

where `FINGERPRINT_WHITESPACE_PATTERN` is `re.compile(r"\s+")`. `build_fingerprint_normalized_text()` applies it independently to each ordered item, drops only results equal to `""`, then uses the same LF separator:

```python
values = [value for value in normalized_values if value]
normalized_text = FINGERPRINT_SEPARATOR.join(values)
normalized_text_length = len(normalized_text)
```

Thus a whitespace-only accepted box counts in `ocr_box_count`, appears as its unchanged source text in raw_text, affects raw_text_length, but contributes neither normalized value nor normalized length/separator. Punctuation, case, Unicode width and all non-whitespace characters are preserved. This must not call existing `ocr_text.normalize_text()`.

## 9. SHA-256 和三态比较

### 9.1 Exact hash

`sha256_normalized_text()` is exactly:

```python
return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
```

Only `normalized_text` bytes enter the hash. `raw_text`、raw/normalized lengths、ocr_box_count、captured_at、screen_index、scan_number、elapsed、candidate number、batch number、confidence、coordinates and fingerprint_version do not.

An empty accepted list is successful input: both text fields are empty, both lengths and count are zero, and exact_hash is the real SHA-256 of `b""`. This is valid and distinct from `fingerprint=None`.

### 9.2 Builder order

`build_screen_fingerprint()` executes:

```text
if supplied, validate aware captured_at but do not serialize it
→ order_fingerprint_items(accepted_items)
→ build_fingerprint_raw_text(ordered)
→ build_fingerprint_normalized_text(ordered)
→ sha256_normalized_text(normalized_text)
→ if not supplied, sample datetime.now().astimezone()
→ captured_at.isoformat()
→ ScreenFingerprint(..., fingerprint_version="r03-v1", screen_index=None)
```

Automatically generated time is therefore sampled after a successful hash, not at OCR capture start or before fingerprint work. An externally injected aware time is test input; it is serialized only after the same successful hash. `captured_at` never participates in hashing, and Change 3 index binding must preserve it unchanged. The builder never logs, catches no own error and returns only a complete valid object. Invalid geometry/time raises `FingerprintBuildError`; unexpected standard exceptions may also propagate to the immediately surrounding R03-only catch in `capture_observation()`. A failure before object construction must not manufacture a timestamp.

### 9.3 Three-state comparison

`compare_screen_fingerprints(left, right) -> Optional[bool]` is pure. A fingerprint is valid for comparison only when it exists, `fingerprint_version` is a nonempty string and `exact_hash` is a `str` full-matching `FINGERPRINT_HASH_PATTERN`.

```text
left/right invalid or absent                    → None
valid but fingerprint_version differs           → None
same version and exact_hash equal               → True
same version and exact_hash differs             → False
```

Two `None` values return `None`, never `True`. Callers must compare against `is True`/`is False`/`is None`; no production branch may use `bool(result)`. There is no enum and no state machine.

## 10. Observation 接入调用链

### 10.1 Change 2 code path

Change 2 modifies only `OCRKeywordDetector.capture_observation()` after the existing searchable text call:

```text
started = perf_counter()
→ image = capture.capture(region)                         [unchanged]
→ raw_items = list(backend.recognize(image))               [unchanged]
→ accepted_items = accepted_ocr_items(raw_items, threshold) [once]
→ R02 metrics = calculate_load_metrics(accepted_items)     [unchanged]
→ text = searchable_text(accepted_items)                   [unchanged]
→ try build_screen_fingerprint(accepted_items)
     except Exception: fingerprint = None                  [R03 only]
→ ScanObservation(existing fields..., fingerprint=fingerprint)
```

The fingerprint builder call must be **after** `searchable_text()`. Therefore an existing malformed nonempty box that already makes searchable text fail continues to follow existing R02/official detector error handling; R03 must not reorder work to convert that historical OCR failure into a fingerprint-only failure.

The `except Exception` surrounding the builder is narrow: it starts immediately before builder invocation and ends before `ScanObservation` construction. It must not include capture, backend, confidence filtering, R02 metrics, searchable text, matcher, scroll or wait. In Change 2 it assigns `None` and returns the otherwise unchanged observation; Change 4 adds only sanitised logs inside the same catch/success paths.

### 10.2 Explicit invariants

The final path must prove all of the following:

- one `capture.capture()` and one `backend.recognize()` per `capture_observation()`;
- one `accepted_ocr_items()` call and one shared accepted list object;
- R02 `ocr_box_count`/`ocr_text_length` unchanged;
- `ScanObservation.text` remains existing `searchable_text(accepted_items)`;
- R03 does not call matcher, wait, scroll, next, refresh, favorite or forward;
- builder failure returns an observation with `fingerprint=None`, not a second OCR or a raised R02 error;
- capture/backend errors occur before R03 builder and remain R02 `ocr_error`/detector failure;
- prefetch first observation remains the same `ScanObservation` object through R02 and `detect()`.

## 11. 正式屏生命周期

### 11.1 Binding positions in detect

Change 3 changes `OCRKeywordDetector.detect()` only. For every candidate `first` observation, bind before `_match_observation()` and before append:

```text
scan_number == 1 and first_observation is not None
  → first = first_observation
  → bind_fingerprint_screen_index(first, 1)
  → _match_observation(first, rules)

otherwise (normal scan 1 or formal scan 2—8)
  → first = capture_observation(scan_number)
  → bind_fingerprint_screen_index(first, scan_number)
  → _match_observation(first, rules)
```

The actual code may retain `_observe()` only for paths without an index bind by splitting it minimally into existing `capture_observation()` followed by `_match_observation()`. It must not call `_observe()` and then capture/recognize again. The TID-approved result is exactly one observation object, one fingerprint, one bind and one matcher call per formal screen.

For confirmation, retain existing:

```text
confirmation = _observe(scan_number, [first.matched_rule])
```

Do **not** call `bind_fingerprint_screen_index()` for confirmation. Its valid fingerprint remains `screen_index=None`; it does not claim a new formal page and does not become page 9.

### 11.2 R02 prefetch lifecycle

| Phase | `scan_number` | fingerprint screen_index | Action |
| --- | ---: | --- | --- |
| R02 initial load gate observation | 1 | `None` | Builder can produce a fingerprint; it is non-formal until gate passes. |
| R02 retry 1—3 | 1 | `None` | Never reaches detector observations; normal local release. |
| R02 loaded prefetch consumed by detect | 1 | `1` | Same observation object is bound, then matched/appended once; no rehash/OCR. |
| Normal formal first screen without prefetch | 1 | `1` | Capture once, bind once, match once. |
| Formal later scans | 2—8 | same integer | Capture once, bind once, match once. |
| Independent confirmation | matching scan number | `None` | Capture once; never binds or increases formal count. |

`bind_fingerprint_screen_index()` uses `replace`, so assigning 1—8 never recomputes raw/normalized text, hash, timestamp or confidence filtering.

### 11.3 Candidate-local storage and release

No new candidate list is added. The existing `DetectionResult.observations` is the one candidate-local carrier; formal fingerprint count is the number of contained observations with `fingerprint is not None and fingerprint.screen_index is not None`, at most eight. A confirmation may be in the same result list but has `screen_index=None` and is not a ninth formal item.

After `detect_keywords()` consumes the result, existing local references naturally end; `OCRKeywordDetector` does not acquire an observations field. The next candidate begins a fresh `observations=[]` in `detect()`. R03 must not cache prior screen hashes, keep the previous candidate's first screen, or compare candidates. Such continuity belongs to a future R01 requirement. R03 also never interprets same/different comparison as an early-scroll/end-of-scan condition; all 8-screen/7-scroll behavior stays unchanged.

## 12. 内存、日志和隐私

### 12.1 In-memory rule

`raw_text` and `normalized_text` exist only inside `ScreenFingerprint` while their containing observation/result is reachable. They are not written to JSON, SQLite, evidence files, screenshots, temporary text files, console output or normal logs. Coordinates and confidence details are only ephemeral builder inputs.

### 12.2 Final R03 events

Change 4 freezes three event schemas, but only the first two are connected to the current R03 production flow:

| Event | Level | Exact call time | Fields |
| --- | --- | --- | --- |
| `ocr_fingerprint_generated` | INFO | Each successful `build_screen_fingerprint()` in `capture_observation()`, before observation return. | `event`, `fingerprint_version`, `exact_hash`, `ocr_box_count`, `raw_text_length`, `normalized_text_length`, `screen_index`, `captured_at`, `scan_number` |
| `ocr_fingerprint_generation_failed` | WARNING | Builder-only exception in `capture_observation()`; capture/backend/searchable failures never use this event. | `event`, `fingerprint_version=r03-v1`, `scan_number`, `error_type` |
| `ocr_fingerprint_comparison` | INFO | Only an explicit future caller after `compare_screen_fingerprints()`; no R03 production flow invokes comparison yet. | `event`, `comparison`, `left_version`, `right_version`, `left_hash`, `right_hash` |

Generated occurs for every successfully captured observation, including an R02 initial/retry observation and a confirmation. At construction time no observation has yet been promoted, so generated must render `screen_index=-` for `None`. It must not emit a second generated event merely because Change 3 later binds a formal index. This field means “index at fingerprint construction”, not a retroactive lifecycle log.

Current production code calls only `_log_fingerprint_generated()` and `_log_fingerprint_generation_failed()` from the narrow builder success/except paths in `capture_observation()`. `log_fingerprint_comparison()` is a future explicit-caller helper only: Change 4 implements it and tests it directly, but must not call it from `capture_observation()`、`detect()`、`_observe()`、the formal-screen loop、`simple_brush` main flow or any other production call site. Current R03 does not proactively compare adjacent formal screens and does not invoke `compare_screen_fingerprints()` in production.

`_log_fingerprint_generated()` must use parameterised logging and only direct scalar fields from a non-None fingerprint. `_log_fingerprint_generation_failed()` receives only `scan_number` and `type(exc).__name__`; it must never render `str(exc)`, `repr(exc)`, item/box repr or traceback. `log_fingerprint_comparison()` maps an already supplied `True`/`False`/`None` exactly to `same`/`different`/`not_comparable`; it logs existing hash/version scalars or `-` for a missing fingerprint. It neither calls compare nor changes a control-flow result.

### 12.3 Absolute log prohibitions

No R03 event, console message or exception text may include raw_text, normalized_text, any OCR body substring, `OCRItem`/list repr, box/point/bounds, width/height/center_y or confidence details. Hashes and scalar count/length/version/time/scan metadata are allowed. The code must never use an f-string containing an item, fingerprint object or exception object.

## 13. 失败降级

### 13.1 Error separation

| Event | R03 action | Existing system action |
| --- | --- | --- |
| MSS capture fails | Builder is not entered. | R02 gate records `ocr_error` / official detector returns failure. |
| backend.recognize fails | Builder is not entered. | Same existing R02/detector behavior. |
| existing searchable_text fails | Builder is not entered because it is later. | Same existing R02/detector behavior. |
| R03 bounds/order/normalize/hash/timestamp builder fails | `fingerprint=None`; Change 4 logs only R03 failure type. | Existing observation/text/R02 metrics continue unchanged. |
| R03 comparison input is unavailable | return `None`; optional log says `not_comparable`. | No scan/action/navigation effect. |

### 13.2 Forbidden consequences

R03 failure must not initiate R02 retry/recovery/`load_failed`, candidate skip, `next_candidate()`, refresh, scroll, matcher, favorite, forward, focus restore, stop event or a second capture/backend call. It must not alter `DetectionResult.success`, `ScanObservation.text`, `item_count`, R02 metrics, matched rule or matched keyword. `fingerprint=None` is the only production data consequence.

## 14. Change-by-Change 实施计划

### Change 1：纯指纹能力和纯测试

**Allowed files:** `ocr_detector.py`, `tests/test_ocr_detector.py`.

Implement the constants, `FingerprintBuildError`, frozen `ScreenFingerprint` and every section-6 pure helper in the existing helper region after `evaluate_detail_page_load()` and before `OCRBackend`; append the optional `ScanObservation.fingerprint` field at its existing later definition. Exclude all logging helpers and `bind_fingerprint_screen_index()`. Change 1 must not implement `bind_fingerprint_screen_index()`; it must not change `capture_observation()`、`_observe()`、`detect()`、`simple_brush.py` or any logging, and must not assign formal `screen_index=1—8`.

Add pure tests for geometry/sorting/text/hash/compare and dataclass field semantics. Confirm `ScanObservation` still has no item/evidence list.

**Forbidden:** capture integration, implementation or invocation of `bind_fingerprint_screen_index()`, any formal screen-index assignment, logging, R02 changes, OCR/GUI invocation, new modules/configuration.

**Intermediate safe state:** imported code has no caller. Existing production behavior is byte-for-byte unchanged except an unused optional dataclass field; no dead control branch or partial fingerprint is observable.

### Change 2：接入 observation，不增加 OCR 或副作用

**Allowed files:** `ocr_detector.py`, `tests/test_ocr_detector.py`.

Modify only `capture_observation()` as section 10. It constructs a complete fingerprint from the one accepted list after existing searchable text. On builder exception, set `fingerprint=None`; do not log until Change 4. No index is bound, so every new valid fingerprint has `screen_index=None`.

Tests prove capture/backend/filter each occur once; the same accepted list object feeds R02 metrics, searchable text and fingerprint; current `text`/R02 metrics stay unchanged; backend error bypasses R03 and remains error; builder failure is fail-open with no matcher/wait/scroll.

**Forbidden:** `detect()` lifecycle changes, screen binding, logs, `simple_brush.py`, any extra OCR/matcher/wait/scroll/navigation/action.

**Intermediate safe state:** R03 data is attached to successful observations but has no formal page meaning. Failed builders safely produce `None`; existing R02 and rule scanning work unchanged.

### Change 3：正式 screen_index 和候选人局部生命周期

**Allowed files:** `ocr_detector.py`, `tests/test_ocr_detector.py`.

Implement `bind_fingerprint_screen_index()` for the first time immediately after the existing `ScanObservation` definition and before `DetectionResult`, then add the exact `detect()` binding positions from section 11. This is the only Change that adds formal `screen_index=1—8` assignment. Reuse the current result list; do not create a parallel per-candidate list or write to `simple_brush.py`.

Tests cover R02 initial/retry `None`, prefetched loaded first=1 by object identity, direct first=1, later formal 2—8, confirmation=None, no rehash/re-OCR on binding, maximum eight formal indexes, and two sequential detect calls with no retained prior fingerprint state.

**Forbidden:** comparison caller, scroll-end/dedup decision, candidate identity state, R01 behavior, logs, persistence.

**Intermediate safe state:** every formal observation is labelled locally; no code reads comparison or index to change behavior. Confirmation and R02 retries remain explicitly non-formal.

### Change 4：结构化日志、隐私和最终异常收口

**Allowed files:** `ocr_detector.py`, `tests/test_ocr_detector.py`.

Add the three section-12 logging helpers in the unified R03 logging-helper region immediately after existing `ScanObservation` and before `DetectionResult`: `_log_fingerprint_generated()` first, then `_log_fingerprint_generation_failed()` and `log_fingerprint_comparison()`. Call generated/failure only in the existing narrow builder success/except locations. For comparison, Change 4 only implements `log_fingerprint_comparison()` and its direct, pure logging tests: it must remain callable but unconnected to the current scan/main flow. It must not call the comparison logger from `capture_observation()`、`detect()`、`_observe()`、the formal-screen loop、`simple_brush` main flow or any other production call site, and must not add adjacent-screen comparison. Update the builder catch only to log sanitized metadata before returning the existing `fingerprint=None` observation.

Tests render logger parameter calls with a unique private marker and assert no body, item repr, coordinate or confidence leakage; verify exact event/level/field values, `screen_index=-` at construction, safe `error_type`, and direct comparison-helper mappings. The comparison logger tests call only the helper and verify `True → same`、`False → different`、`None → not_comparable`, with no control-flow side effect or production registration. Re-run the R02 failure invariants to prove no recovery/next/stop behavior appears.

**Forbidden:** logging `str(exc)`/traceback for R03 builder failures, storing evidence, modifying R02 events/fields, calling comparison or its logger from any current production path, adding a comparison business branch, modifying simple_brush.

**Intermediate safe state:** R03 has final observable, private metadata but still no control-flow consumer. Generation failure remains one local `None` outcome.

### Change 5：完整回归、设计审计和验收报告

**Allowed files:** new `docs/R03-basic-ocr-page-fingerprint-acceptance-report.md`. Only if a test demonstrates an R03 direct defect, the minimal repair may touch `ocr_detector.py` and/or `tests/test_ocr_detector.py`; document the exact reason and rerun all checks.

Run all section-16 tests and perform a diff/RPD/TID scope audit. The report must record baseline, platform, exact commands/results, RPD/TID field agreement, event/privacy evidence, known tie limitation, no-persistence result, and Windows + Edge manual status. It must explicitly state that R03 did not implement R01/R04/R06/R07/R08/R13.

**Forbidden:** opportunistic cleanup, `simple_brush.py` or other test edits, real browser automation, real forwarding, config/build changes, commit/tag/release.

**Intermediate safe state:** no feature change beyond a directly proven minimal R03 fix; all behavior is fully documented and regressions checked.

## 15. 自动化测试矩阵

All new tests belong to a new `ScreenFingerprintTests(unittest.TestCase)` in `tests/test_ocr_detector.py`, except where an existing `DetectorTests` name better directly extends capture/detect lifecycle. Keep existing `DetailPageLoadHelperTests` and `RapidOCRAdapterTests` unchanged. Change 1 contains no bind-helper implementation, invocation or `detect()` test; all bind coverage belongs to Change 3. Change 4 tests invoke `log_fingerprint_comparison()` directly only and do not register it with a production path.

| Change | Test class / representative test | Required assertion |
| --- | --- | --- |
| 1 | `ScreenFingerprintTests.test_box_bounds_supports_rotated_and_numpy_boxes` | min/max bounds, width/height/center_y for real four-point and ndarray boxes. |
| 1 | `test_invalid_boxes_raise_fingerprint_build_error` | None, empty, missing coordinate, nonnumeric, NaN and Infinity fail only builder. |
| 1 | `test_order_is_stable_when_non_tied_input_is_shuffled` | shuffled distinct coordinates create same order/raw/hash. |
| 1 | `test_order_groups_small_y_variation_by_frozen_tolerance` | exact `max(8, min(height)*.5)` boundary, including equality. |
| 1 | `test_order_uses_source_index_for_complete_coordinate_tie` | approved tie behavior and limitation are explicit. |
| 1 | `test_raw_text_preserves_whitespace_and_excludes_separator_from_length` | LF, empty/whitespace box and length contract. |
| 1 | `test_normalized_text_strips_and_compresses_whitespace_only` | strip, `re.sub(r"\s+", " ")`, ignored normalized empties and LF length. |
| 1 | `test_normalization_preserves_case_width_and_punctuation` | no NFKC/lower/punctuation deletion. |
| 1 | `test_hash_is_lowercase_sha256_of_utf8_normalized_text` | 64 lowercase hex and exact hashlib result. |
| 1 | `test_metadata_does_not_change_exact_hash` | time/index/count/length/version metadata do not enter hash. |
| 1 | `test_empty_normalized_text_has_valid_empty_sha256` | empty is valid, not `None`. |
| 1 | `test_compare_screen_fingerprints_is_three_state` | equal=True, unequal=False, missing/invalid/version mismatch/two None=None. |
| 1 | `test_screen_fingerprint_is_frozen_and_observation_field_defaults_none` | immutable value object; no OCR item lists added. |
| 2 | `DetectorTests.test_capture_observation_builds_fingerprint_from_same_accepted_items_once` | capture/backend/filter each once; identity of accepted list passed to R02/search/search fingerprint; no matcher/wait/scroll. |
| 2 | `DetectorTests.test_capture_observation_keeps_r02_metrics_and_searchable_text_semantics` | confidence at/below boundary, blank count, `ocr_text_length` and existing text unchanged. |
| 2 | `DetectorTests.test_fingerprint_build_failure_keeps_observation_and_does_not_repeat_ocr` | `fingerprint=None`, existing fields valid, no extra operations. |
| 2 | `DetectorTests.test_backend_failure_does_not_attempt_fingerprint_build` | backend exception follows existing detector failure; R03 builder uncalled. |
| 3 | `DetectorTests.test_prefetched_loaded_first_observation_is_bound_to_one` | identity reuse, one capture total, first index=1. |
| 3 | `DetectorTests.test_direct_detection_assigns_one_through_eight_to_formal_scans` | indices 1—8 and exactly seven scrolls. |
| 3 | `DetectorTests.test_confirmation_fingerprint_has_no_formal_screen_index` | confirmation None and no ninth formal index. |
| 3 | `DetectorTests.test_binding_replaces_index_without_rehash_or_recapture` | original hash/time/text equal, only index changes. |
| 3 | `DetectorTests.test_sequential_detection_results_do_not_retain_prior_candidate_fingerprints` | fresh result/index 1, no detector cross-candidate cache. |
| 4 | `DetectorTests.test_fingerprint_generated_log_has_only_allowed_metadata` | INFO event and all fields; private body/coords/confidence absent; index `-`. |
| 4 | `DetectorTests.test_fingerprint_failure_log_is_sanitised_and_fail_open` | WARNING event, type only, no `str(exc)`/body, R02 fields survive. |
| 4 | `ScreenFingerprintTests.test_comparison_log_maps_all_three_states_without_body` | Direct helper call maps `True`/`False`/`None` to same/different/not_comparable, logs no text and has no control-flow or production-call-site effect. |
| 4 | Existing `SimpleBrushOCRTests` (run unchanged) | R02 OCR error, retry, prefetched reuse, favorite, forward, `--no-forward`, no-keyword, focus restore and normal refresh regressions remain green. |
| 5 | Full suite + acceptance audit | All targeted/public/Windows suite commands pass; no unexpected files or behavior. |

The test that checks R02 `ocr_error` remains in existing `SimpleBrushOCRTests` and is not edited: Change 5 runs it to prove backend errors did not become R03 failures. No test must call real MSS, RapidOCR, Edge, mouse, keyboard, clipboard, favorite or forwarding.

## 16. 完整回归命令和验收门槛

Run from repository root after each relevant Change and again in Change 5:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_detector -v
.\venv\Scripts\python.exe -m unittest tests.test_ocr_text -v
.\venv\Scripts\python.exe -m unittest tests.test_simple_brush_ocr -v
.\venv\Scripts\python.exe -m unittest tests.test_mouse_motion -v
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m compileall -q ocr_detector.py tests
.\venv\Scripts\python.exe -m pip check
git diff --check
git status --short
```

The acceptance gate requires all tests green, compile/pip checks passing, no whitespace error, and a scope check showing only the Change-authorized files. Markdown may be ignored by the current `*.md` rule; use `Test-Path` and `Get-Content -Raw` to confirm TID/acceptance-report existence rather than treating absent `git status` output as absence.

## 17. Windows + Edge 人工冒烟延期

Changes 1—5 do not open Edge or execute live GUI steps. R02 acceptance already records that an authorized safe account, controlled page/network state and real test rules are unavailable; R03 cannot claim a real Windows + Edge outcome from mocks.

After implementation, manual validation remains deferred to a dedicated acceptance session on Windows 10/11 x64 + Microsoft Edge, test account, small sample and `--no-forward` first. Observe first/later/confirmation OCR, no extra scrolling or action, valid hash metadata only, and no body in logs. No real forwarding is part of R03 default validation.

## 18. 验收报告结构

Change 5 creates `docs/R03-basic-ocr-page-fingerprint-acceptance-report.md` with at least:

1. document information, baseline, branch and platform;
2. actual changed-file list and explicit non-changes;
3. approved RPD/TID contract audit for dataclass, sorting, text, hash, indices and compare;
4. capture/recognize/filter-once evidence and R02/pre-fetch compatibility;
5. exact log event/privacy evidence using a unique private marker;
6. test commands, counts and results;
7. scope/diff/status result, including ignored Markdown evidence;
8. Windows + Edge manual status marked executed or deferred with reason;
9. known exact-tie/backend-order limitation and no-persistence statement;
10. evidence that production emitted only generated/failure events: `ocr_fingerprint_comparison` was unit-tested as a direct helper but was not connected to capture, detect, screen-loop or `simple_brush` code;
11. final conclusion, risks and explicit statement that no R01/R04/R06/R07/R08/R13 work was done.

## 19. 非目标和防过度设计审计

Implementation reviewers must reject the following as out of scope:

- changing `ocr_text.normalize_text()` or `order_items()`;
- adding a second confidence threshold, OCR capture, backend call, matcher call, wait or scroll;
- a candidate class, fingerprint store, global previous fingerprint, cross-candidate comparison or dynamic stop condition;
- calling `compare_screen_fingerprints()` or `log_fingerprint_comparison()` from `capture_observation()`、`detect()`、`_observe()`、the formal-screen loop、`simple_brush` or any other current production call site;
- treating equal/different hash as R01 switching proof, R02 readiness, R07 page end or an action trigger;
- SimHash, fuzzy comparison, vector/AI processing, UI removal, NFKC/lower/punctuation normalization beyond R03;
- JSON, SQLite, evidence files, screenshots, persistent cache, configuration/CLI or secret handling;
- logging any body/box/confidence object detail;
- changing favorite/forward/`--no-forward`/focus restore/batch filter/normal refresh behavior;
- refactoring `simple_brush.py`, packaging, calibration, mouse movement or unrelated docs while implementing R03.

The only approved future comparison API is the small pure three-state helper. Its absence from current business control flow is intentional: R03 delivers base facts, not a page/candidate decision system.

## 20. TID conclusion

This TID freezes a minimal implementation: one frozen `ScreenFingerprint`, one optional `ScanObservation` reference, pure deterministic mechanics in `ocr_detector.py`, detector-local formal index binding, and three sanitised event contracts. It preserves R02 capture/error/first-screen behavior, holds body only in current observation memory, and leaves all candidate, scrolling, loading and persistence decisions to later explicitly approved requirements.
