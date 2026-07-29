# BossOCR R03：基础 OCR 页面指纹验收报告

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 需求 | R03：基础 OCR 页面指纹 |
| 验收范围 | Change 1—4 最终实现；Change 5 设计审计、自动化回归与本报告 |
| 验收日期 | 2026-07-30 |
| RPD | `docs/RPD-R03-basic-ocr-page-fingerprint.md` |
| TID | `docs/TID-R03-basic-ocr-page-fingerprint.md` |
| 正式平台范围 | Windows 10/11 x64 + Microsoft Edge |
| 自动化解释范围 | Windows 项目 venv 中的本地 `unittest`；不等同于真实 Edge 页面 E2E |

本报告只验收 R03 的基础页面指纹事实能力，不把 exact hash 解释为候选人切换、页面加载、页面到底、扫描结束或动作许可。

## 2. 基线、分支、工作区和范围

- 分支：`main`
- HEAD / 正式实施基线：`b9029bc022ae258ab62e2bc28ae64ead2dea2f35`（`feat(r02): add detail page load detection`）
- 根目录 `README.md` 不存在；实际项目说明为 `docs/README.md`，已审计。
- 已完整审计 R03 RPD/TID、R02 RPD/TID/验收报告、`ocr_detector.py`、`ocr_text.py`、`simple_brush.py` 和相关 unittest，以及相对 `b9029bc` 的全部 diff。

本 Change 开始前已有、并受保护的工作区内容为 `.gitignore`、`docs/Issue-Next-6-human-mouse-motion-acceptance-report.md`、`simple_brush.py`、`docs/project-review.zip`、`docs/project-review/`、`docs/tid/` 和 `venv-packages-before-reinstall.txt`。本 Change 未整理、恢复、暂存或修改它们。

相对基线的可见 diff 为 `.gitignore`、上述 Next-6 报告、`simple_brush.py`、`ocr_detector.py`、`tests/test_ocr_detector.py`；其中 R03 Change 1—4 的实现范围是后两项。`simple_brush.py` 的 4 行改动在 R03 开始前已经存在，且本 R03 未修改该文件。

Markdown 被现有 `.gitignore` 的 `*.md` 规则忽略。因此本报告、RPD 和 TID 通过 `Test-Path` / 文件读取确认存在，未因未出现在普通 `git status` 而误判为缺失。

## 3. 实际修改文件

| 文件 | R03 最终职责 |
| --- | --- |
| `ocr_detector.py` | frozen `ScreenFingerprint`、几何/排序/文本/SHA-256/三态纯 helper、observation 接入、正式 index 后置绑定、三项脱敏结构化日志 |
| `tests/test_ocr_detector.py` | 纯算法、单次采集、R02 兼容、生命周期、日志隐私和无 production comparison caller 覆盖 |
| `docs/R03-basic-ocr-page-fingerprint-acceptance-report.md` | 本 Change 5 验收报告 |

Change 5 设计审计未发现 RPD/TID 直接冲突或覆盖缺口，故未修改生产代码或测试代码。

## 4. 最终数据结构

`ScreenFingerprint` 是 frozen dataclass，保存：

- `raw_text`、`normalized_text`；
- `raw_text_length`、`normalized_text_length`；
- `ocr_box_count`；
- 带时区 ISO 8601 字符串 `captured_at`；
- `exact_hash`；
- `fingerprint_version="r03-v1"`；
- 可选 `screen_index`。

`ScanObservation` 只在末尾增加 `fingerprint: Optional[ScreenFingerprint] = None`。两者均不保存 `OCRItem`、raw/accepted 列表、box、单框 confidence、候选人或批次信息。`DetectionResult.observations` 仍是当前候选人的唯一局部 observation 容器。

## 5. 最终调用链和 R02 兼容性

```text
capture_observation(scan_number)
→ 一次 capture.capture(region)
→ 一次 backend.recognize(image)
→ 一次 accepted_ocr_items(raw_items, min_confidence)
→ 同一个 accepted_items list
   ├→ calculate_load_metrics（R02）
   ├→ searchable_text（既有规则文本）
   └→ build_screen_fingerprint（R03）
→ 一个 ScanObservation
```

审计和测试确认：

- `ScanObservation.text` 仍是既有 `searchable_text` 的规则文本，未替换为 raw/normalized 文本；
- `item_count` 仍是过滤前 raw item 数；R02 `ocr_box_count` 和 `ocr_text_length` 未改变；
- builder 位于既有 `searchable_text()` 后，避免把原本的 capture/backend/规则文本异常误变成 R03 降级；
- 同一 accepted list 对 R02、搜索文本和 R03 按对象身份复用；不增加 matcher、wait、scroll、next、refresh、favorite 或 forward；
- R02 loaded 的 prefetched 首屏按对象身份进入 `detect()`，不二次 OCR。

## 6. 坐标排序

每个 accepted item 必须具有非空、有限且可解析的点坐标。R03 取 `left/right/top/bottom` 的 min/max、`height=max(1.0, bottom-top)` 和 `center_y`。无坐标、空、缺坐标、不可转换、NaN 或 Infinity 只使该 builder 失败，不影响 R02 或规则搜索；退化框仍有效。

排序与 TID 一致：先按 `(center_y, top, left, bottom, right, original_index)`，再按首个满足 `abs(center_y-line_center_y) <= max(8.0, min(item_height, line_height)*0.5)` 的行归类；行均值动态更新；行按 `(line_center_y, first_item_top, first_item_left)`，同行按 `(left, top, right, bottom, original_index)` 输出。完全几何相同的框使用本次 source index，跨 OCR 调用仍受 backend 顺序限制。

## 7. 文本规范化和 SHA-256

- 固定框间分隔符为单个 LF（`"\n"`）。
- `raw_text` 按阅读顺序拼接全部 accepted `item.text`，不 strip 或压缩空白；`raw_text_length` 为原文本 `len()` 求和，不含程序插入 LF。
- 对每个 item，`normalized_text` 只执行 `strip()` 和 `re.sub(r"\s+", " ", value)`；规范化后为空的 item 忽略，保留项以 LF 拼接；最终长度为 `len(normalized_text)`，因此含实际 LF。
- 不执行 NFKC、lower、标点/全半角修改、去重或语义处理；既有关键词 `normalize_text()` 未被修改。
- `exact_hash` 精确为 `hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()`，即 64 位小写十六进制。
- 时间、screen index、框数、长度、版本、scan number、confidence 和坐标均不参与 hash。成功的空 OCR 结果产生真实空文本 SHA-256，不与 builder 失败混同。

## 8. 存储和生命周期

初次加载门与 retry observation 的 fingerprint `screen_index=None`。R02 成功的 prefetched 首屏仅在进入正式 matcher/append 前按对象身份绑定为 1；正式后续屏为 2—8。确认 OCR 不绑定 index，不占第 9 个正式屏。

`bind_fingerprint_screen_index()` 仅以 `dataclasses.replace()` 更新 frozen fingerprint 的 index，不重新截图、OCR、过滤、排序、hash 或改写 `captured_at`。正式 fingerprint 的数量按 `screen_index is not None` 计数，最多 8；确认 observation 可在同一 result 中但不计入正式屏。detector 不持有 observations 字段，不建立并行 fingerprint list、跨候选人缓存或 previous fingerprint 状态；当前候选人结束后，既有局部 result/observation 引用可自然释放。

没有 JSON、SQLite、TXT、截图、证据文件或其他 R03 持久化。

## 9. 三态比较和 comparison logger

`compare_screen_fingerprints()` 的语义为：

| 输入 | 返回 |
| --- | --- |
| 同版本、有效且 hash 相同 | `True` |
| 同版本、有效且 hash 不同 | `False` |
| 任一缺失/无效、版本不同或两个 `None` | `None` |

`log_fingerprint_comparison(left, right, comparison)` 只记录已得到的比较结果：`True → same`、`False → different`、`None → not_comparable`。它不调用 compare、OCR 或 hash，缺失 fingerprint 的 version/hash 记为 `-`。

静态搜索证据：生产代码中 `compare_screen_fingerprints()` 和 `log_fingerprint_comparison()` 均仅有定义；它们的调用只出现在 `tests/test_ocr_detector.py`。因此 `capture_observation()`、`detect()`、`_observe()`、正式屏循环、`simple_brush` 主流程和 `DetectionResult` 处理均无 comparison 调用者、相邻屏循环或控制流分支。

## 10. 失败降级

capture、backend 和既有 `searchable_text()` 异常发生在 builder 之前，保持 R02 的 `ocr_error` 或 detector 的既有失败语义，绝不记录为 R03 generation failure。只有成功 OCR 且成功生成规则文本后 builder 的狭窄 `except Exception` 才：

```text
fingerprint = None
→ ocr_fingerprint_generation_failed（安全元数据）
→ 返回既有 observation
```

该路径不伪造空 hash，不触发 R02 retry/recovery、候选人跳过、停止、额外 OCR、规则匹配、滚动或动作。测试覆盖 builder 失败后 observation、R02 指标和确认扫描仍继续，以及 backend/capture/searchable error 不记录 R03 failure。

## 11. 日志和隐私

当前生产流程只有以下两项 R03 事件：

| 事件 | 级别 | 调用时点 | 字段 |
| --- | --- | --- | --- |
| `ocr_fingerprint_generated` | INFO | 每次 builder 成功后、`capture_observation()` 返回前 | `event`、`fingerprint_version`、`exact_hash`、`ocr_box_count`、`raw_text_length`、`normalized_text_length`、`screen_index`、`captured_at`、`scan_number` |
| `ocr_fingerprint_generation_failed` | WARNING | 仅 builder 异常的狭窄 except | `event`、`fingerprint_version`、`scan_number`、`error_type` |

生成时尚未正式化，故 `screen_index=None` 记录为 `-`；后续绑定不重复记录 generated。failure 只取 `type(exc).__name__`，不记录 `str(exc)`、repr 或 traceback。comparison 事件已实现且直接单测，但没有生产调用者。

单元测试以唯一正文标记 `PRIVATE_R03_OCR_BODY_9F3A` 渲染 generated、generation_failed 和三态 comparison 日志，断言不出现原文、normalized 文本、`OCRItem`/`ScreenFingerprint`/异常 repr、列表、box/point/bounds/width/height/center_y 或 confidence 明细；同时验证 hash、长度、数量、版本、时间和 scan number 可记录。日志没有候选人切换、加载完成或页面到底结论。

## 12. 需求范围和复杂度审计

| 审计项 | 结论 |
| --- | --- |
| R01 候选人切换验证 | 未实现；无 cross-candidate state 或 hash 控制流。 |
| R02 判定/预算/恢复/日志语义 | 未修改；R03 只复用 observation。 |
| R04 文本规范化 | 未实现；既有关键词 NFKC/lower/去空白不变。 |
| R06 SimHash/相似度 | 未实现；只有 SHA-256 exact hash。 |
| R07 动态结束/到底 | 未实现；8 屏/7 滚动不读取 hash。 |
| R08/R13 JSON、SQLite、永久保存 | 未实现。 |
| AI、云端、图像 hash、DOM/browser hash | 未实现。 |
| 新 GUI、CLI、配置系统、后台线程 | 未实现。 |
| macOS 正式候选人 E2E | 未实现。 |
| 无关重构 | 未发现；R03 实现局限于 detector 和其单测。 |

没有引入 candidate class、repository、registry、状态机、平行列表或新的模块。复杂度与批准的最小 ScreenFingerprint 方案一致。

## 13. 设计审计结果和最小修复

审计完成以下对照：RPD/TID 字段、默认版本、UTF-8 SHA-256、正则源码、行容差、source-index tie 限制、raw/normalized 长度、合法空 hash、三态、采集顺序、R02 异常边界、prefetch 对象复用、正式 index、候选人释放、事件字段/级别/时点和 comparison 无调用者。

结论：**未发现与批准 RPD/TID 直接冲突的生产缺陷，也未发现必须补测的覆盖缺口。** 因此 Change 5 没有生产或测试修复；仅创建本报告。测试中出现的 `FingerprintBuildError` 日志来自无 box 的既有 fake OCR fixture，符合“成功 OCR、规则文本成功、R03 不可建立确定空间顺序时 fail-open 并警告”的冻结语义，并非 R02 OCR error 或阻断问题。

## 14. 自动化测试结果

所有命令在 Windows PowerShell、`venv\Scripts\python.exe` 下执行。仓库未配置 Ruff、Flake8、Mypy、Pylint、tox 或 pytest；未虚构或新增检查器。测试目录中也未发现 skip/expected-failure 标记。

| 命令 | passed | failed | skipped | 结论 |
| --- | ---: | ---: | ---: | --- |
| `-m unittest tests.test_ocr_detector -v` | 70 | 0 | 0 | 通过 |
| `-m unittest tests.test_ocr_text -v` | 36 | 0 | 0 | 通过 |
| `-m unittest tests.test_simple_brush_ocr -v` | 186 | 0 | 0 | 通过 |
| `-m unittest tests.test_mouse_motion -v` | 28 | 0 | 0 | 通过 |
| `-m unittest discover -s tests -v` | 358 | 0 | 0 | Windows 全量通过 |
| `-m compileall -q ocr_detector.py simple_brush.py tests` | 1 command | 0 | 0 | 通过 |
| `-m pip check` | 1 command | 0 | 0 | `No broken requirements found.` |
| `git diff --check` | 1 command | 0 | 0 | 通过；仅有既有 CRLF 提示，无 whitespace error |

## 15. 自动化覆盖矩阵

| 范围 | 主要自动化证据 |
| --- | --- |
| 数据、排序和 hash | 四点/NumPy/退化 box、无效 box、行容差边界、乱序稳定、完全 tie、raw/normalized 文本和长度、空 hash、元数据不入 hash |
| 比较 | 同/不同/不可比较、两个 `None`、版本/非法 hash，comparison 三态日志映射 |
| 单次 observation | capture/backend/filter 各一次；同一 accepted list 供 R02、searchable_text、R03；无 matcher/motion |
| R02 兼容与异常 | 原 R02 指标/规则文本保持；builder fail-open；capture/backend/searchable 异常不伪装为 R03 failure |
| 生命周期 | R02/retry `None`、prefetch identity reuse、正式 1—8、确认 `None`、不 rehash/re-OCR、连续 detector 无状态泄漏 |
| 日志/隐私 | 三事件 schema、INFO/WARNING、construction index `-`、绑定不重复 generated、唯一私密正文不泄露 |
| 主流程回归 | favorite、forward、`--no-forward`、无关键词、ESC、timer、焦点恢复、正常刷新、R02 recovery 和鼠标行为的全量 unittest |

## 16. Windows + Edge 人工冒烟延期

当前 BOSS 账号正在公司环境运行，无法安全登录测试。R03 人工冒烟与 R01、R02 一并延期；以下均为**待人工执行**，不得解释为通过。

| 场景 | 状态 |
| --- | --- |
| 同一静止页面的 hash 稳定率 | 待人工执行 |
| 正常滚动后的 hash 变化 | 待人工执行 |
| 页面到底后的相邻 hash | 待人工执行 |
| 候选人切换前后的变化率 | 待人工执行 |
| 加载中低内容 hash | 待人工执行 |
| OCR 抖动、缩放和动画影响 | 待人工执行 |
| 性能卡顿与同步 OCR 停止响应 | 待人工执行 |
| generated/failure 日志隐私 | 待人工执行 |
| favorite、forward、`--no-forward` 与无关键词集成回归 | 待人工执行；优先测试账号、小样本和 `--no-forward` |

人工验收应在 Windows 10/11 x64、Microsoft Edge、测试账号、受控页面状态和人工监控下进行；不应对真实候选人执行默认转发。

## 17. 已知限制

1. 同 hash 仅表示同版本 normalized UTF-8 bytes 相同，不证明候选人身份、DOM、页面完整性、加载完成或动作成功。
2. OCR 误差、可见区域、缩放、动画、网络加载和固定 UI 都可能改变 hash；R03 不做模糊处理。
3. 完全相同几何的多框只能按本次 backend source index 定序，跨 OCR 调用可能不稳定。
4. 缺失/不可解析 box 使 fingerprint 不可用；R03 保守地不采用 backend 原始顺序伪造空间 hash。
5. raw/normalized text 虽只在内存，仍可能包含个人信息；hash 也可能成为可关联标识，日志应按现有本地敏感信息规则处理。
6. 同步 OCR 仍不能被 ESC/timer 中途抢占；R03 未改变该既有限制。

## 18. RPD/TID 一致性

| 冻结合同 | 审计结果 |
| --- | --- |
| `r03-v1`、frozen value object、可选 observation 字段 | 一致 |
| 机械坐标排序、LF 文本口径、UTF-8 SHA-256 | 一致 |
| 正式 1—8、R02/retry/confirmation 为 `None` | 一致 |
| 仅内存、无 OCRItem 列表、候选人局部释放 | 一致 |
| 三态事实但无流程解释 | 一致 |
| builder fail-open；OCR 错误保留 R02/既有 detector 语义 | 一致 |
| generated/failure 接入；comparison 仅单测且无生产 caller | 一致 |
| 不改变 R02、动作、滚动、候选人切换或停止行为 | 一致 |

## 19. 最终结论

**附条件通过——自动化与静态验收通过，R01—R03 Windows + Edge 集成实机冒烟待执行。**

所有定向测试和 358 项 Windows 全量 unittest 通过；编译、依赖和 whitespace 检查通过；设计审计确认无正文泄露、无额外 OCR 或业务副作用、无 comparison 生产调用者和无超范围实现。没有未修复的生产阻断问题。由于真实 Edge/BOSS 测试环境未获安全授权，不能给出无条件或实机通过结论。

## 20. 版本控制声明

本 Change 未 commit、push、创建 tag 或 Release；也未修改 `.gitignore` 或受保护的既有工作区内容。
