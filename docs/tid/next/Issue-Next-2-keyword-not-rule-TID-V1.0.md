# [Next-2] TID V1.0：关键词规则新增 not 排除逻辑

## 1. 目标与范围

### 1.1 目标

在现有英文双引号关键词规则中增加 `not` 排除逻辑：

- 优先级：`not` > `and` > `or`。
- `not` 只能修饰一个英文双引号关键词。
- 每条规则至少包含一个正向关键词。
- 每个 OR 分支至少包含一个正向关键词。
- OCR 首次检测和二次确认均使用完整规则。
- 旧版 `and`、`or` 规则行为保持不变。
- 非法格式必须返回包含位置的明确错误。

### 1.2 本轮范围

- 关键词规则数据结构。
- `not` 解析和规范化输出。
- 正向、排除关键词匹配。
- OCR 二次确认回归测试。
- `simple_brush.py` 输入接入和错误提示测试。
- README 规则文档。

### 1.3 非目标

- 括号、数值比较或 `not` 修饰组合表达式。
- 通用表达式引擎或 `eval`。
- macOS Chrome。
- Next-1 焦点恢复校准。
- P3 日志或 P4 数值匹配。
- OCR 或转发流程重构。
- DOM 读取、浏览器自动化驱动或页面状态识别。
- 模糊匹配、词法分词或语义匹配。

## 2. 当前代码分析

### 2.1 仓库状态

- 当前分支：`main`。
- 跟踪分支：`origin/main`。
- 本地与远程一致，工作区干净。
- 目标 Issue：`[Next-2] P2：关键词规则新增 not 排除逻辑`，状态 Open。

### 2.2 关键词解析器与规则结构

文件：`ocr_text.py`

当前结构：

```python
@dataclass(frozen=True)
class KeywordRule:
    source: str
    or_groups: Tuple[Tuple[str, ...], ...]
```

当前使用 OR-of-AND 结构。例如：

```text
"A" or "B" and "C"
```

表示为：

```python
(
    ("A",),
    ("B", "C"),
)
```

解析入口 `parse_keyword_rules()` 是小型顺序扫描器，支持分号、英文双引号、大小写不敏感的 `and`/`or`、`and` 优先于 `or`、稳定 canonical source 和带位置错误。本方案继续扩展该扫描器，不引入通用解析引擎。

### 2.3 匹配逻辑

`keyword_rule_matches()` 当前等价于：

```python
any(
    all(keyword in text for keyword in and_group)
    for and_group in rule.or_groups
)
```

组内只有字符串，无法区分正向和排除 term，需要最小新增 term 数据结构。匹配继续复用 `normalize_text()` 的 NFKC、小写、去空白和精确子串语义，不新增模糊匹配。

### 2.4 OCR 二次确认

文件：`ocr_detector.py`

首次检测调用：

```python
matched_rule = matching_keyword_rule(text, rules)
```

首次命中后，二次确认调用：

```python
confirmation = self._observe(scan_number, [first.matched_rule])
confirmed = confirmation.matched_rule == first.matched_rule
```

当前已经重新判断完整 `KeywordRule`，没有降级为单关键词。只要新规则保存完整正负条件并由 `keyword_rule_matches()` 正确求值，主算法原则上无需修改，但必须增加负向条件二次确认测试。

### 2.5 simple_brush 接入

`simple_brush.py` 使用 `parse_keyword_rules()` 保存 `forward_keywords`，再原样传给 `ocr_detector.detect()`。`keyword_rule_sources()` 使用 `rule.source` 展示完整规则。因此只需保持 `KeywordRule.source` 接口稳定，并更新输入示例及接入测试。

### 2.6 现有测试

相关文件：

- `tests/test_ocr_text.py`
- `tests/test_ocr_detector.py`
- `tests/test_simple_brush_ocr.py`

已覆盖单关键词、AND、OR、优先级、分号规则、canonical source、NFKC、错误位置、完整 AND 二次确认、不同规则不能互相确认，以及交互/自动模式解析。

### 2.7 Issue 描述差异

GitHub Issue 当前正文中的部分示例显示为未加引号形式，但 Issue 规则说明和本次明确要求都规定关键词必须使用英文双引号。本 TID 以本次要求为准：

```text
"短剧" and not "销售"
```

未加英文双引号的形式继续视为非法，不做自动迁移。

## 3. 规则语法设计

### 3.1 语法

```text
rules          := rule (";" rule)* ";"?
rule           := and_group ("or" and_group)*
and_group      := term ("and" term)*
term           := quoted_keyword | "not" quoted_keyword
quoted_keyword := '"' non_empty_text '"'
```

- 关键词与连接符之间必须有空格。
- `not` 与关键词之间必须有空格。
- 引号内的 `and`、`or`、`not` 都属于关键词正文。

### 3.2 优先级

```text
not > and > or
```

```text
"A" or "B" and not "C"
```

等价于：

```text
"A" or ("B" and (not "C"))
```

```text
"A" and not "B" or "C"
```

等价于：

```text
("A" and (not "B")) or "C"
```

### 3.3 合法示例

```text
"短剧" and not "销售"
"AIGC" and not "运营"
"仿真人" and not "主播"
"A" or "B" and not "C"
"A" and not "B" or "C"
"A" and not "B" and not "C"
```

### 3.4 非法示例

```text
not "销售"
not "销售" or "短剧"
"短剧" or not "销售"
"短剧" and not
"短剧" not "销售"
"短剧" and not not "销售"
not ("销售" or "运营")
"短剧" and not ("销售")
```

每个 OR 分支都必须至少包含一个正向关键词。该约束避免纯排除分支匹配几乎所有不含排除词的文本。

## 4. 数据结构设计

### 4.1 KeywordTerm

```python
@dataclass(frozen=True)
class KeywordTerm:
    keyword: str
    negated: bool = False
```

- `negated=False`：文本必须包含关键词。
- `negated=True`：文本必须不包含关键词。

### 4.2 AND group 与 OR rule

AND group 继续使用 tuple：

```python
Tuple[KeywordTerm, ...]
```

`KeywordRule` 保留现有名称和字段：

```python
@dataclass(frozen=True)
class KeywordRule:
    source: str
    or_groups: Tuple[Tuple[KeywordTerm, ...], ...]
```

例如：

```text
"A" or "B" and not "C"
```

表示为：

```python
KeywordRule(
    source='"A" or "B" and not "C"',
    or_groups=(
        (KeywordTerm("A", False),),
        (KeywordTerm("B", False), KeywordTerm("C", True)),
    ),
)
```

该方案保留现有 OR-of-AND 模型，结构上限定 `not` 只能作用于单个 term，并保持 frozen dataclass 的完整规则相等比较。

## 5. 解析逻辑设计

### 5.1 扫描器扩展

建议将现有扫描逻辑局部拆分为：

```python
parse_quoted_keyword(position)
parse_operator(position)
parse_term(position)
finish_group(group, position)
build_source(groups)
```

- `parse_term()` 识别正向关键词或 `not` + 英文双引号关键词。
- `finish_group()` 在遇到 `or`、分号或输入结束时验证分支至少包含一个正向 term。
- `build_source()` 为 `not`、`and`、`or` 生成小写 canonical source。

### 5.2 not token

`not` 大小写不敏感，必须作为 term 前缀；后面必须有空白及英文双引号关键词。禁止重复 `not`、跟随括号或代替 `and`。

```text
"短剧" AND NOT "销售"
```

规范化为：

```text
"短剧" and not "销售"
```

### 5.3 OR 分支验证

每次完成 AND group 时执行：

```python
if not any(not term.negated for term in current_group):
    raise ...
```

该检查统一拒绝首个、中间或末尾纯 not 分支。更严格的分支约束自然满足“整条规则至少包含一个正向关键词”。

### 5.4 旧规则兼容

旧规则全部转换为 `negated=False` 的 `KeywordTerm`。必须保持旧 canonical source、优先级、分号、大小写、英文引号、输入顺序和错误行为不变。

## 6. 匹配逻辑设计

### 6.1 term 匹配

```python
contains = normalize_text(term.keyword) in normalized_text
return not contains if term.negated else contains
```

### 6.2 group 和 rule 匹配

```python
group_matches = all(term_matches(term) for term in group)
rule_matches = any(group_matches(group) for group in rule.or_groups)
```

示例规则：

```text
"短剧" and not "销售"
```

| 文本 | 结果 |
| --- | --- |
| `短剧编导` | 命中 |
| `短剧销售` | 不命中 |
| `销售` | 不命中 |
| `其他岗位` | 不命中 |

### 6.3 二次确认

`OCRKeywordDetector.detect()` 已经将首次匹配的完整 `KeywordRule` 传给二次 `_observe()`，无需改变主算法。必须增加测试证明第二次出现排除词、缺少正向词或只满足另一条规则时不能确认。

## 7. 错误处理

所有错误继续抛出 `KeywordRuleSyntaxError`，并带一基位置。

| 输入 | 建议错误 |
| --- | --- |
| `not "销售"` | 每个 OR 分支至少需要一个正向关键词 |
| `not "销售" or "短剧"` | 首个 OR 分支缺少正向关键词 |
| `"短剧" or not "销售"` | 后续 OR 分支缺少正向关键词 |
| `"短剧" and not` | `not` 后缺少英文双引号关键词 |
| `"短剧" not "销售"` | `not` 不能代替 `and`/`or` 连接符 |
| `"短剧" and not not "销售"` | `not` 只能修饰一个英文双引号关键词 |
| `not ("销售" or "运营")` | 不支持 `not` 修饰组合表达式 |

其他继续拒绝：中文引号、未加引号、空关键词、未闭合引号、连续分号、空规则、缺少操作数、未知操作符、缺少空格、括号和数值比较。不得静默删除 `not`、把它当普通关键词或自动改写规则。

## 8. 技术步骤拆解

### Change 1：扩展数据结构、解析与匹配

修改：`ocr_text.py`、`tests/test_ocr_text.py`

- 新增 frozen `KeywordTerm`。
- 增加 `not` term 解析和分支正向词验证。
- 生成 canonical source。
- 更新匹配逻辑。
- 覆盖合法、非法、优先级和旧规则兼容。

验收：旧测试通过，新规则正确解析和匹配，非法格式带位置。

### Change 2：OCR 二次确认测试

修改：`tests/test_ocr_detector.py`；只有测试暴露缺陷时才最小修改 `ocr_detector.py`。

- 两次均满足正负规则时确认。
- 第二次出现排除词或缺少正向词时不确认。
- 混合 OR/AND/NOT 使用完整规则。

验收：二次确认不降级为单关键词，现有 AND 确认测试继续通过。

### Change 3：simple_brush 接入和错误重试

修改：`simple_brush.py`、`tests/test_simple_brush_ocr.py`

- 更新输入格式示例。
- 验证交互和 `--auto` 都使用同一解析器。
- 非法纯 not 规则明确报错并重试或阻止启动。
- `detect_keywords()` 继续传递完整规则。

验收：不修改 OCR、转发或 Next-1 流程。

### Change 4：README

修改：`README.md`

- 增加语法、优先级、合法/非法示例和限制。
- 说明每个 OR 分支必须有正向词。
- 说明短排除词风险和 `--no-forward` 验证。

### Change 5：全量回归与范围验收

- 运行全量测试和 `git diff --check`。
- 核对旧规则、完整二次确认和非目标范围。
- 如无需文件变更，不创建空 commit。

## 9. 测试计划

### 9.1 ocr_text 单元测试

覆盖：

- 合法解析和 canonical source。
- `not > and > or`。
- 多个排除 term。
- 首个、中间、末尾纯 not OR 分支。
- 缺少操作数、重复 not、隐式连接、括号。
- 连接符大小写和引号内 connector。
- 所有旧规则回归。

### 9.2 OCR detector 测试

规则：

```text
"短剧" and not "销售"
```

| 首次 OCR | 二次 OCR | 结果 |
| --- | --- | --- |
| `短剧编导` | `短剧制作` | 确认 |
| `短剧编导` | `短剧销售` | 不确认 |
| `短剧编导` | `其他岗位` | 不确认 |
| `短剧销售` | 不执行二次确认 | 首次不命中 |

### 9.3 simple_brush 接入测试

- 交互输入合法 not 规则并保存完整 source。
- 非法规则提示错误后重试。
- `--auto` 合法规则解析。
- `--auto` 非法规则在激活 Edge 前失败。
- detector 接收完整 `forward_keywords`。
- `--no-forward` 不调用真实转发。
- Next-1 测试保持通过。

### 9.4 全量测试

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

### 9.5 手工测试

优先使用：

```powershell
.\venv\Scripts\python.exe simple_brush.py --no-forward
```

检查合法规则命中、排除词阻止命中、纯 not 启动报错、错误后重试、日志显示完整 source，以及二次确认出现排除词时失败。本 Issue 不需要真实邮件转发测试。

## 10. 风险与回退

- **排除词过度匹配**：短词如 `not "A"` 可能过度排除；不在本 Issue 增加分词或词边界，README 提醒使用具体词并先安全验证。
- **OCR 漏识别排除词**：可能错误命中；保留完整规则二次确认，但不宣称消除所有 OCR 误差。
- **OCR 误识别排除词**：可能错误排除；继续使用当前置信度和精确匹配，不增加模糊逻辑。
- **旧规则兼容**：group 元素类型变化可能影响调用方；保留 `KeywordRule`、`source`、`or_groups` 名称并全仓检索直接访问。
- **错误位置偏差**：继续传递原始索引并增加关键错误位置测试。
- **纯 not 分支误触发**：每次完成 AND group 都强制正向词验证，覆盖不同分支位置。
- **回退原则**：验收失败时停止，不静默忽略 `not`，不允许解析成功但匹配缺失。

## 11. Git 提交计划

### Commit 1

```text
feat: add not keyword rule parsing and matching
```

范围：数据结构、解析、匹配和 `ocr_text` 测试。

### Commit 2

```text
test: verify not rules during OCR confirmation
```

范围：完整 not 规则二次确认测试；仅在必要时最小修正 detector。

### Commit 3

```text
feat: expose not keyword rules in startup input
```

范围：`simple_brush` 输入提示、交互/自动模式接入测试。

### Commit 4

```text
docs: explain not keyword rule syntax
```

范围：README 规则和安全说明。

### Commit 5

全量回归和范围验收；无文件变更时不创建空 commit。如另行生成验收报告，可使用：

```text
docs: add Next-2 acceptance report
```
