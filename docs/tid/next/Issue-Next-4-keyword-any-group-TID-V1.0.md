# [Next-4] TID V1.0：关键词规则支持 `any(...)` 分组表达式

## 1. 背景与目标

BossOCR 当前在 `ocr_text.py` 中支持英文双引号关键词以及 `not > and > or` 优先级，规则内部采用“OR 分支包含多个 AND 条件”的结构。每个 OR 分支必须至少包含一个未被 `not` 修饰的正向条件，因此纯排除分支会被拒绝。

实际岗位筛选常需要同时表达“目标公司集合”“能力词集合”和“排除词集合”。现有语法只能将集合展开为大量完整 OR 分支，例如 6 家公司乘 7 个能力词需要维护 42 个分支，并重复写入排除条件，容易遗漏或写错。

本需求新增 `any(...)` 原子条件：括号内任意一个英文双引号关键词命中，即视为该原子命中。目标表达式可简化为：

```text
any("魔方","九州","剧点","星火","天桥","麦芽")
and any("短剧原片","内容创作","正剧剪辑","全流程制作","短剧","漫剧","仿真人")
and not any("消耗","35岁","36岁","37岁","38岁","39岁","40岁","41岁","42岁","43岁","44岁","45岁","46岁","47岁","48岁","49岁","50岁","投放","分销")
```

实现目标：

- `any(...)` 作为单个原子条件参与既有 `not`、`and`、`or` 运算。
- 保持 `not > and > or`，不改变原有表达式行为。
- 保留 `or` 连接完整筛选分支的职责。
- 保留“每个 OR 分支至少有一个正向条件”的安全约束。
- 非法 `any(...)` 返回带位置和原因的明确错误。
- OCR 仍通过现有 matcher 判断完整规则；本需求不改 OCR 流程。

## 2. 非目标

- 不实现通用括号表达式，例如 `("A" or "B") and "C"`。
- 不支持嵌套 `any(...)`。
- 不支持在 `any(...)` 内使用 `and`、`or`、`not` 或其他表达式。
- 不支持未加英文双引号或使用单引号的参数。
- 不引入通用表达式引擎、解析器生成器或 `eval`。
- 不移除、不弱化、不改写现有 `or`。
- 不修改 GUI、转发流程、OCR 扫描/二次确认逻辑或打包脚本。
- 不处理 macOS Chrome、DOM、浏览器驱动、页面状态识别、P3/P4。
- 不增加模糊匹配、词边界、分词或关键词权重。

## 3. 用户语法

### 3.1 第一版文法

```text
rules          := rule (WS? ";" WS? rule)* WS? ";"?
rule           := and_group (WS "or" WS and_group)*
and_group      := term (WS "and" WS term)*
term           := ["not" WS] atom
atom           := quoted_keyword | any_group
any_group      := "any" WS? "(" WS? quoted_keyword
                  (WS? "," WS? quoted_keyword)* WS? ")"
quoted_keyword := '"' non_empty_text '"'
WS             := one_or_more_whitespace
```

设计约束：

- `and`、`or`、`not`、`any` 大小写不敏感，canonical source 统一输出小写。
- `any` 与 `(` 之间允许空白；括号内允许逗号两侧空白。
- `any(...)` 至少包含一个非空英文双引号关键词；`any("A")` 合法但冗余。
- `not` 可修饰一个普通关键词或一个完整 `any(...)` 原子，不能修饰 AND/OR 组合。
- 英文双引号内的逗号和 `and`/`or`/`not`/`any` 均属于关键词正文。
- 第一版不定义转义引号，沿用当前“下一个英文双引号结束关键词”的行为。

### 3.2 明确支持

```text
any("A","B")
"A" and any("B","C")
any("A","B") and any("C","D")
any("A","B") or "C"
"A" and not any("B","C")
"A" and any("B","C") or "D" and any("E","F")
```

`not any("A","B")` 是受支持的原子写法，但它不能单独构成一个 OR 分支。也就是说，它可出现在含正向条件的分支中，如 `"C" and not any("A","B")`；单独规则 `not any("A","B")` 仍因“纯 not 分支”而非法。

### 3.3 第一版明确不支持

```text
any(any("A","B"),"C")
any("A" and "B","C")
("A" or "B") and "C"
any(A,B,C)
any('A','B')
```

## 4. 语义定义

### 4.1 正向 any

```text
any("A","B","C")
```

当且仅当当前规范化文本包含 A、B、C 中至少一个关键词时命中。其局部布尔语义等价于：

```text
contains("A") or contains("B") or contains("C")
```

这种等价只描述该原子的匹配结果，不表示 parser 将其展开为顶层 OR 分支。保留原子结构可避免破坏外层 AND 分组。

### 4.2 否定 any

```text
not any("A","B")
```

等价于：

```text
not (contains("A") or contains("B"))
```

即文本同时不包含 A 且不包含 B 时为真。它不是 `not "A" or not "B"`。

### 4.3 示例目标规则

```text
any("公司A","公司B")
and any("能力A","能力B")
and not any("排除A","排除B")
```

命中条件为：公司组至少命中一项，能力组至少命中一项，排除组一项也未命中。

## 5. 与现有 `and` / `or` / `not` 的关系

优先级保持：

```text
not > and > or
```

`any(...)` 与普通英文双引号关键词处于相同的 atom 层级。示例：

```text
"A" and any("B","C") or "D" and any("E","F")
```

解析为两个完整 OR 分支：

```text
("A" and any("B","C")) or ("D" and any("E","F"))
```

现有 `or` 不会被 `any(...)` 替代：

- `any(...)`：一个条件组内部的可替代关键词。
- `or`：连接多个完整筛选分支。

正向分支校验从“至少一个非 negated `KeywordTerm`”泛化为“至少一个非 negated 原子”。因此：

- `not any("A","B")`：非法，纯排除分支。
- `not any("A","B") or "C"`：非法，第一个 OR 分支为纯排除分支。
- `"C" or not any("A","B")`：非法，第二个 OR 分支为纯排除分支。
- `"C" and not any("A","B")`：合法。

## 6. 解析方案

### 6.1 保持顺序扫描器

继续扩展 `ocr_text.py::parse_keyword_rules()` 的现有顺序扫描器，不引入完整括号解析。建议将局部职责明确为：

```text
parse_quoted_keyword(position)
parse_any_group(position)
parse_atom(position)
parse_term(position)
finish_group(group, position)
build_rule(groups)
```

### 6.2 token 判定

- `parse_atom()` 在当前位置为 `"` 时解析普通关键词。
- 当前位置为独立 token `any` 且后续可选空白后为 `(` 时，调用 `parse_any_group()`。
- `anywhere`、`any_value` 等不能被识别为 `any` token。
- `parse_term()` 先处理可选 `not`，再调用 `parse_atom()`；由此自然支持 `not any(...)`，同时继续拒绝 `not (...)`。
- `parse_any_group()` 只接受逗号分隔的 quoted keyword；遇到 `and`、`not`、嵌套 `any`、裸词或缺少逗号时立即报错。

### 6.3 canonical source

`KeywordRule.source` 继续是完整规则的稳定展示值。建议规范化为：

```text
any("A", "B") and not any("C", "D")
```

- 操作符和 `any` 输出小写。
- 参数间统一为逗号加一个空格。
- 保留关键词引号内原始文本，延续现有 source 行为。
- 不将 `any(...)` 展开成多个 `or`，避免 source 膨胀并保留用户意图。

### 6.4 重复项策略

推荐第一版采用方案 A：拒绝重复项，而不是自动去重 warning。

理由：

- 当前项目没有统一、稳定且用户可见的 parser warning 通道；自动去重 warning 可能在 CLI、自动模式或日志中被忽略。
- 重复项没有权重语义，拒绝可避免用户误以为重复会提高命中优先级或置信度。
- 显式错误更容易定位配置维护问题，也不会静默改变用户输入。
- 后续若确有兼容需求，可在独立变更中引入 warning 机制；从严格拒绝放宽为去重比反向收紧更安全。

重复判断应使用现有匹配规范化语义（NFKC、大小写折叠、移除空白），因此 `"Ａ"` 与 `"A"`、`"A B"` 与 `"AB"` 都视为语义重复。错误需指出第二个重复项的位置和对应关键词。普通表达式跨原子的重复不在本需求中禁止，仅校验同一个 `any(...)` 内部。

## 7. 数据结构影响

### 7.1 当前结构

```python
@dataclass(frozen=True)
class KeywordTerm:
    keyword: str
    negated: bool = False

@dataclass(frozen=True)
class KeywordRule:
    source: str
    or_groups: Tuple[Tuple[KeywordTerm, ...], ...]
```

仓库检索显示，`KeywordTerm` 和 `or_groups` 的直接结构断言仅存在于 `tests/test_ocr_text.py`；生产调用方通过 `KeywordRule` 和 matcher 使用规则。`ocr_detector.py` 会保存并在二次确认中重新匹配完整 `KeywordRule`。

### 7.2 推荐最小新增结构

不建议把 `any(...)` 展开为多个顶层 OR group，也不建议让 `KeywordTerm.keyword` 同时接受字符串和 tuple。推荐新增独立 atom 类型：

```python
@dataclass(frozen=True)
class KeywordAnyGroup:
    keywords: Tuple[str, ...]
    negated: bool = False

KeywordAtom = Union[KeywordTerm, KeywordAnyGroup]

@dataclass(frozen=True)
class KeywordRule:
    source: str
    or_groups: Tuple[Tuple[KeywordAtom, ...], ...]
```

优点：

- 旧表达式仍生成完全相同的 `KeywordTerm`，降低兼容风险。
- `KeywordAnyGroup` 明确表达“组内 OR、外部为一个 atom”，无需魔法字段或混合类型。
- 两种 atom 都具有 `negated`，`finish_group()` 可统一检查正向原子。
- frozen dataclass 保持规则可比较，OCR 二次确认现有的完整规则相等判断继续成立。

如果项目 Python 版本不适合类型别名，可仅在注解中使用 `Union[KeywordTerm, KeywordAnyGroup]`，不改变运行时设计。

## 8. 匹配逻辑影响

将 `keyword_rule_matches()` 中的单一 term 判断抽取为 atom 判断：

```text
KeywordTerm:
    contains = normalized_keyword in normalized_text

KeywordAnyGroup:
    contains = any(normalized_keyword in normalized_text
                   for keyword in atom.keywords)

atom result:
    not contains if atom.negated else contains

AND group:
    all(atom_matches(atom) for atom in group)

OR rule:
    any(group_matches(group) for group in rule.or_groups)
```

文本仍只规范化一次；`any(...)` 参数可在一次 atom 求值中依次检查。第一版不需要预编译集合或引入缓存，避免过度设计。

`ocr_detector.py` 无需修改：首次检测调用 `matching_keyword_rule()`，二次确认将首次命中的完整 `KeywordRule` 再次传入 `_observe()`。新增 atom 是 frozen 数据结构，因此完整规则比较语义不变。应由回归测试确认 any 规则不会在二次确认中降级或丢失排除组，但验收要求不依赖 GUI 测试。

## 9. 错误提示设计

继续抛出 `KeywordRuleSyntaxError`，沿用一基位置格式：`原因（位置 N）`。不得静默跳过、自动改写或把非法内容当普通关键词。

| 输入 | 建议错误原因 |
| --- | --- |
| `any()` | `any(...) 至少需要一个关键词` |
| `any( )` | `any(...) 至少需要一个关键词` |
| `any("")` | `any(...) 中的关键词不能为空` |
| `any("A",)` | `逗号后缺少英文双引号关键词` |
| `any(,"A")` | `any(...) 的首个参数必须是英文双引号关键词` |
| `any("A" "B")` | `any(...) 参数之间必须使用英文逗号分隔` |
| `any("A", not "B")` | `any(...) 内只支持英文双引号关键词` |
| `any("A" and "B")` | `any(...) 内不支持 and/or/not 表达式` |
| `any(any("A","B"))` | `any(...) 不支持嵌套` |
| `any(A,B,C)` | `any(...) 参数必须使用英文双引号包裹` |
| `any('A','B')` | `any(...) 参数必须使用英文双引号包裹` |
| `any("A","A")` | `any(...) 中存在重复关键词 "A"`，位置指向第二项 |
| `not any("A","B")` | `每个 OR 分支至少需要一个正向条件` |
| `any("A","B"` | `any(...) 缺少右括号` |
| `any "A"` | `any 后必须跟随括号参数` |

错误分类测试不应过度绑定完整中文文案，但必须断言关键原因和位置，保证错误可操作。

## 10. 测试计划

本需求以 parser 和 matcher 单元测试为主，不需要 GUI 测试，不运行真实键鼠、剪贴板或转发操作。

### 10.1 Parser 测试

- 解析 `any("A","B")` 为一个 `KeywordAnyGroup`。
- 解析普通 term、any term、`not any` 的混合表达式。
- 验证 `not > and > or` 和 OR-of-AND 结构。
- 验证 canonical source、大小写不敏感和可选内部空白。
- 验证英文双引号内逗号/连接符仍是关键词正文。
- 验证所有列出的非法输入均抛出带位置错误。
- 验证嵌套、组合表达式、裸词、单引号均被拒绝。
- 验证同一 any 内按规范化语义拒绝重复项。
- 验证 `not any(...)` 单独或作为纯 not OR 分支被拒绝。
- 验证所有不含 any 的现有 parser 测试保持不变。

### 10.2 Matcher 测试

目标规则：

```text
any("公司A","公司B")
and any("能力A","能力B")
and not any("排除A","排除B")
```

| 场景 | 文本示例 | 预期 |
| --- | --- | --- |
| 公司组命中 + 能力组命中 + not 未命中 | `公司A 能力B` | 命中 |
| 公司组未命中 | `其他公司 能力A` | 不命中 |
| 能力组未命中 | `公司B 其他能力` | 不命中 |
| not 组命中 | `公司A 能力A 排除B` | 不命中 |
| 多个正向组命中且 not 命中 | `公司A 公司B 能力A 能力B 排除A` | 不命中 |

另需覆盖：

- `any("A","B") or "C"` 的两个完整 OR 分支均可独立命中。
- `"A" and any("B","C") or "D" and any("E","F")` 保持 AND/OR 优先级。
- `"A" and not any("B","C")` 的排除语义。
- `any("A")` 与普通 `"A"` 匹配结果一致。
- NFKC、大小写和去空白行为与普通关键词一致。
- 原有 `"A" and "B" or "C"`、not 规则及分号多规则全部兼容。

### 10.3 可选 detector 回归

验收不要求 GUI 测试。可在 `tests/test_ocr_detector.py` 增加一项纯 mock 回归，证明首次和二次 OCR 都使用完整 any + not 规则；原则上不修改 `ocr_detector.py`。若时间有限，parser/matcher 覆盖是本 issue 的最低必需范围。

### 10.4 测试命令

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_text -v
.\venv\Scripts\python.exe -m unittest discover -s tests -v
git diff --check
```

## 11. 变更步骤

### Change 1：新增 any 原子数据结构与解析

修改文件：

- `ocr_text.py`
- `tests/test_ocr_text.py`

内容：

- 新增 frozen `KeywordAnyGroup` 和 `KeywordAtom` 注解。
- 扩展 `parse_atom()` / `parse_any_group()` / `parse_term()`。
- 保留普通 `KeywordTerm` 的结构和旧规则解析结果。
- canonical source 保留 any 结构。
- 拒绝空参数、尾逗号、缺逗号、嵌套、组合表达式、非英文双引号参数和重复项。
- 将 OR 分支正向校验泛化为正向 atom 校验。

验收方式：parser 新增测试和全部既有 `test_ocr_text` parser 测试通过；旧规则对象结构不变。

建议 commit：

```text
feat: parse any keyword groups
```

### Change 2：实现 any 匹配与语义回归

修改文件：

- `ocr_text.py`
- `tests/test_ocr_text.py`
- 可选：`tests/test_ocr_detector.py`（仅增加 mock 回归测试）

内容：

- matcher 支持正向和 negated `KeywordAnyGroup`。
- 覆盖公司组、能力组、排除组和外层 OR 场景。
- 回归普通 `and`/`or`/`not`、规范化及多规则行为。
- 如增加 detector 测试，只证明完整规则二次确认，不改 OCR 业务逻辑。

验收方式：所有验收场景通过；不含 any 的表达式结果与变更前一致；全量单元测试通过。

建议 commit：

```text
feat: match any keyword groups
```

### Change 3：文档与全量范围验收

修改文件：

- `README.md`
- 必要的规则文档/验收报告，不修改 GUI 或业务流程文件

内容：

- 说明 any 语法、与 or 的职责区别、优先级、合法/非法示例。
- 明确纯 `not any(...)` 分支非法、重复项拒绝、第一版不支持完整括号。
- 运行全量测试和 `git diff --check`。
- 全仓检查不包含 GUI、转发、OCR、打包或 macOS 变更。

验收方式：README 示例可直接被 parser 接受；全量测试通过；diff 范围符合本 issue。

建议 commit：

```text
docs: explain any keyword group syntax
```

## 12. 风险与回滚方案

### 12.1 技术风险

- **当前 scanner 的 token 边界只围绕空白设计**：现有 `starts_token()` 认为 token 后需为空白或输入结束，而 `any(` 的 token 后是 `(`。必须为函数式 atom 单独实现边界判断，不能直接复用现有 operator 判定，否则合法 `any(...)` 会被拒绝或 `anywhere(...)` 被误识别。
- **括号引入但不支持通用括号**：parser 必须仅在识别到 `any` atom 后消费其配对右括号；其他位置的 `(` / `)` 继续明确报错，避免意外演变成半套表达式解析器。
- **`not any(...)` 文案存在表面冲突**：需求同时列为“支持写法”并要求纯 not any 分支非法。本 TID 将其定义为“可被 not 修饰，但必须与同一 OR 分支的正向 atom 组合”。实施前应以此作为验收口径。
- **结构相等影响 OCR 二次确认**：新增 atom 必须保持 frozen 和值相等语义；不得在匹配期间修改 keywords。
- **规范化重复项**：按匹配语义拒绝 `"A B"` / `"AB"` 等重复可能比用户预期严格，错误信息应展示原始关键词，便于修正。
- **逗号属于关键词正文**：扫描 any 参数时必须先完整解析英文双引号，再处理分隔逗号，不能简单按字符串逗号切分。
- **旧规则兼容**：普通表达式必须继续生成 `KeywordTerm`，不得为了 any 全量替换旧 AST。

### 12.2 回滚方案

- 三个 Change 独立提交，可按逆序回滚。
- Change 2 匹配异常时，可回滚 matcher 支持而保留未发布的 parser 分支；正式发布必须保证 parser 与 matcher 同时存在，不允许接受 any 后静默错误匹配。
- 若 parser 风险超出预期，整体回滚 Change 1/2，旧 `and`/`or`/`not` 数据结构和行为保持不变。
- 不提供“解析失败后把 any 当普通关键词”的兼容回退，这会产生静默误筛选。

## 13. 验收标准

| 验收项 | 通过条件 |
| --- | --- |
| 正向 any | `any("A","B")` 在包含 A 或 B 时命中，均不包含时不命中 |
| 多正向组 | 公司组与能力组都至少命中一项才命中 |
| 公司组缺失 | 能力组即使命中，规则仍不命中 |
| 能力组缺失 | 公司组即使命中，规则仍不命中 |
| 排除组 | `not any(...)` 中任一关键词出现即令该 atom 为假 |
| 正向与排除同时命中 | 多个正向组命中但排除词出现时，完整规则不命中 |
| 外层 or | `any(...)` 不改变 `or` 连接完整分支的行为 |
| 优先级 | 保持 `not > and > or` |
| 纯 not 安全约束 | 单独 `not any(...)` 及含纯 not any OR 分支均被拒绝 |
| 非法语法 | 需求列出的非法 any 输入均给出包含位置的清晰错误 |
| 重复项 | 同一 any 内语义重复关键词被明确拒绝，不静默去重 |
| 旧规则兼容 | 所有不含 any 的现有 parser、matcher 和 detector 测试保持通过 |
| 数据结构 | 普通规则仍使用现有 `KeywordTerm`；any 使用独立 frozen atom |
| OCR 行为 | 不修改 OCR 扫描流程，完整 `KeywordRule` 仍用于二次确认 |
| 测试范围 | parser 和 matcher 单元测试覆盖全部核心场景，无需 GUI 测试 |
| 非目标 | 未实现通用括号、嵌套 any、GUI/转发/OCR/打包/macOS 变更 |
