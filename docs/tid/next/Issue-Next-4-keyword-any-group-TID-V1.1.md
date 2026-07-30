# [Next-4] TID V1.1：关键词规则支持 `any(...)` 分组表达式

## 1. 背景与目标

BossOCR 当前支持英文双引号关键词及 `not > and > or` 规则，内部采用 OR-of-AND 结构。每个 OR 分支必须至少包含一个正向条件，纯 `not` OR 分支会被拒绝。

真实岗位筛选常需要表达“任意目标公司” AND “任意能力词” AND “不包含任意排除词”。现有语法需要展开大量重复 OR 分支，维护成本高且容易遗漏排除条件。

本需求新增 `any(...)` 原子条件：括号内任意一个英文双引号关键词命中，即视为该原子命中。例如：

```text
any("魔方","九州","剧点","星火","天桥","麦芽")
and any("短剧原片","内容创作","正剧剪辑","全流程制作","短剧","漫剧","仿真人")
and not any("消耗","35岁","36岁","37岁","38岁","39岁","40岁","投放","分销")
```

目标：

- `any(...)` 作为一个 atom 参与外层 `not`、`and`、`or`。
- 保持 `not > and > or` 优先级及原有表达式行为。
- 保留 `or` 连接完整筛选分支的职责。
- 保留“每个 OR 分支至少包含一个正向 atom”的安全约束。
- 非法 `any(...)` 返回带位置和原因的明确错误。
- OCR 继续使用现有 matcher 对完整 `KeywordRule` 进行二次确认，不改 OCR 流程。

### 1.1 V1.1 硬约束：禁止展开为顶层 OR

`any(...)` 必须在 AST/规则数据中保留为一个不可拆散的 atom。严禁在 parser 中将它展开为多个顶层 `or_groups`，也严禁在 matcher 前将其改写为外层 OR 分支。

例如：

```text
any("魔方","九州") and any("短剧","漫剧")
```

正确语义是：

```text
(魔方 OR 九州) AND (短剧 OR 漫剧)
```

如果错误展开为顶层 OR，则可能退化为：

```text
魔方 OR 九州 OR 短剧 OR 漫剧
```

这样仅出现 `魔方` 或仅出现 `短剧` 就会误命中，直接破坏外层 AND 约束。该约束属于实现和验收的阻断条件，不是优化建议。

## 2. 非目标

- 不实现完整括号表达式，例如 `("A" or "B") and "C"`。
- 不支持嵌套 `any(...)`。
- 不支持在 `any(...)` 内使用 `and`、`or`、`not` 或组合表达式。
- 不支持未加英文双引号或使用单引号的参数。
- 不引入通用表达式引擎、parser generator 或 `eval`。
- 不移除、弱化或隐式替换现有 `or`。
- 不修改 GUI、OCR 扫描/确认流程、转发流程或打包脚本。
- 不处理 macOS Chrome、DOM、浏览器驱动、页面状态识别、P3/P4。
- 不增加模糊匹配、分词、词边界或关键词权重。

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

约束：

- `and`、`or`、`not`、`any` 大小写不敏感，canonical source 统一为小写。
- `any` 与 `(` 之间允许空白；括号内允许逗号两侧空白。
- `not` 可修饰普通关键词或完整 `any(...)` atom，不能修饰 AND/OR 组合。
- 英文双引号内的逗号和连接符均属于关键词正文。
- 第一版沿用当前行为，不定义英文双引号转义。

### 3.2 支持的写法

```text
any("A","B")
"A" and any("B","C")
any("A","B") and any("C","D")
any("A","B") or "C"
"A" and not any("B","C")
"A" and any("B","C") or "D" and any("E","F")
```

`not any("A","B")` 是可解析的否定 atom，但不能单独构成 OR 分支。因此：

- `"C" and not any("A","B")`：合法。
- `not any("A","B")`：非法，纯排除分支。
- `not any("A","B") or "C"`：非法，第一个 OR 分支为纯排除分支。
- `"C" or not any("A","B")`：非法，第二个 OR 分支为纯排除分支。

### 3.3 单项 any

`any("A")` 第一版合法但不推荐，语义严格等价于普通关键词 `"A"`。

保留单项 any 的原因：

- 配置生成器可以对统一的数据结构输出 any，而无需为单项集合增加特殊分支。
- 用户临时删除组内其他关键词后，剩余配置仍保持语法有效。
- 单项 any 不引入歧义，也不改变匹配安全性。

第一版不拒绝单项 any，也不自动改写为普通关键词；canonical source 保留 `any("A")`，以保留用户配置意图。

### 3.4 第一版不支持

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

当规范化文本包含 A、B、C 中至少一个关键词时，该 atom 为真：

```text
contains("A") OR contains("B") OR contains("C")
```

该 OR 只存在于 atom 内部，不能提升或展开为规则的顶层 OR。

### 4.2 否定 any

```text
not any("A","B")
```

语义为：

```text
NOT (contains("A") OR contains("B"))
```

即 A、B 任一出现，该 atom 都为假。它不等价于 `not "A" or not "B"`。

直观示例：

```text
规则："魔方" and not any("投放","消耗")
```

| 文本 | 预期 | 原因 |
| --- | --- | --- |
| `魔方 投放` | 不命中 | 排除组命中“投放” |
| `魔方 剪辑` | 命中 | 正向词命中且排除组均未命中 |

### 4.3 外层组合

```text
"A" and any("B","C") or "D" and any("E","F")
```

按既有优先级解析为：

```text
("A" and any("B","C")) or ("D" and any("E","F"))
```

`any(...)` 不改变 `not > and > or`，也不替代外层 `or`。

## 5. 与现有 `and` / `or` / `not` 的关系

优先级保持：

```text
not > and > or
```

层级关系：

- `quoted_keyword` 和 `any_group` 都是 atom。
- `not` 只修饰紧随其后的一个 atom。
- `and` 连接多个 atom，形成一个完整 AND group。
- `or` 连接多个完整 AND group。

正向分支校验由“至少一个非 negated `KeywordTerm`”泛化为“至少一个非 negated atom”。`KeywordAnyGroup` 即使包含多个关键词，在分支正向性判断中仍只算一个 atom。

## 6. 解析方案

继续扩展 `ocr_text.py::parse_keyword_rules()` 的顺序扫描器，不引入完整括号 parser。建议职责：

```text
parse_quoted_keyword(position)
parse_any_group(position)
parse_atom(position)
parse_term(position)
finish_group(group, position)
build_rule(groups)
```

解析规则：

- `parse_atom()` 遇到 `"` 时解析普通关键词。
- 遇到独立 token `any`，且后续可选空白后为 `(` 时解析 any group。
- `anywhere`、`any_value` 等不得被误识别为 `any`。
- `parse_term()` 先处理可选 `not`，再调用 `parse_atom()`。
- `parse_any_group()` 仅接受逗号分隔的英文双引号关键词。
- parser 必须构造一个 `KeywordAnyGroup` atom，禁止向当前或新的顶层 OR group 注入参数。
- 普通位置的 `(`、`)` 继续报错，不借此实现通用括号。

canonical source 建议统一为：

```text
any("A", "B") and not any("C", "D")
```

操作符与 `any` 使用小写，参数分隔统一为逗号加一个空格，保留引号内原始文本，不展开 any。

### 6.1 重复项策略

第一版推荐拒绝重复项，而不是自动去重并 warning。

理由：

- 项目暂无统一且可靠的 parser warning 通道。
- 静默去重可能让用户误以为重复关键词具有权重。
- 明确错误更容易定位配置生成或人工维护问题。
- 从严格拒绝放宽为 warning 比后续反向收紧更安全。

重复判断采用当前 matcher 的规范化语义：NFKC、大小写折叠、去空白。因此 `"Ａ"` 与 `"A"`、`"A B"` 与 `"AB"` 视为语义重复；错误位置指向第二个重复项。只检查同一 `any(...)` 内部，不禁止不同 atom 之间重复。

## 7. 数据结构影响

当前结构：

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

推荐最小扩展：

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

硬约束：`KeywordAnyGroup.keywords` 始终留在一个 atom 内。不得为其中每个 keyword 创建独立 `or_groups` 元素。

该结构的优点：

- 旧表达式继续生成相同的 `KeywordTerm`。
- any 的内部 OR 与规则顶层 OR 在类型上明确分离。
- 两种 atom 都有 `negated`，可统一进行分支正向校验。
- frozen dataclass 保持值相等语义，OCR 二次确认仍可比较完整规则。

不建议把 `KeywordTerm.keyword` 改成字符串/tuple 混合类型，也不建议通过隐式展开复用旧结构；两者都会增加误用和语义放宽风险。

## 8. 匹配逻辑影响

建议抽取 atom matcher：

```text
KeywordTerm:
    contains = normalized_keyword in normalized_text

KeywordAnyGroup:
    contains = any(normalized_keyword in normalized_text
                   for keyword in atom.keywords)

atom_result:
    not contains if atom.negated else contains

and_group:
    all(atom_matches(atom) for atom in group)

rule:
    any(group_matches(group) for group in rule.or_groups)
```

文本仍只规范化一次。any 参数依次进行现有精确子串检查，不引入权重、模糊匹配或短路之外的新行为。

`ocr_detector.py` 无需修改：首次检测和二次确认都通过现有 matcher 处理完整 `KeywordRule`。新增 atom 必须保持 frozen，matcher 不得修改规则内容。

## 9. 错误提示设计

继续抛出 `KeywordRuleSyntaxError`，沿用一基位置格式 `原因（位置 N）`。不得静默跳过、自动改写或将非法 any 当作普通关键词。

| 输入 | 建议错误 |
| --- | --- |
| `any()` / `any( )` | `any(...) 至少需要一个关键词` |
| `any("")` | `any(...) 中的关键词不能为空` |
| `any("A",)` | `逗号后缺少英文双引号关键词` |
| `any(,"A")` | `首个参数必须是英文双引号关键词` |
| `any("A" "B")` | `参数之间必须使用英文逗号分隔` |
| `any("A", not "B")` | `any(...) 内只支持英文双引号关键词` |
| `any("A" and "B")` | `any(...) 内不支持组合表达式` |
| `any(any("A","B"))` | `any(...) 不支持嵌套` |
| `any(A,B,C)` | `参数必须使用英文双引号包裹` |
| `any('A','B')` | `参数必须使用英文双引号包裹` |
| `any("A","A")` | `any(...) 中存在重复关键词 "A"` |
| `not any("A","B")` | `每个 OR 分支至少需要一个正向条件` |
| `any("A","B"` | `any(...) 缺少右括号` |

错误测试可断言关键原因和位置，不必绑定整句中文文案。

## 10. 测试计划

本需求以 parser 和 matcher 单元测试为必需范围，不需要 GUI 测试，也不得触发真实键鼠、剪贴板或转发操作。

### 10.1 Parser 测试

- `any("A","B")` 解析为一个 `KeywordAnyGroup`，而非两个顶层 OR group。
- 普通 term、any term、`not any` 的混合表达式。
- `not > and > or` 及 OR-of-AND 结构。
- canonical source、大小写不敏感、可选内部空白。
- `any("A")` 合法、保留为 any atom，语义说明等价于 `"A"`。
- 引号内逗号或连接符仍属于关键词正文。
- 空参数、尾逗号、缺逗号、嵌套、组合表达式、裸词、单引号报错。
- 同一 any 内按规范化语义拒绝重复项。
- `not any(...)` 单独或作为纯 not OR 分支被拒绝。
- 所有不含 any 的现有 parser 测试保持通过。

### 10.2 Matcher 核心验收

目标规则：

```text
any("公司A","公司B")
and any("能力A","能力B")
and not any("排除A","排除B")
```

| 场景 | 文本 | 预期 |
| --- | --- | --- |
| 公司组、能力组命中且排除组未命中 | `公司A 能力B` | 命中 |
| 公司组未命中 | `其他公司 能力A` | 不命中 |
| 能力组未命中 | `公司B 其他能力` | 不命中 |
| 排除组命中 | `公司A 能力A 排除B` | 不命中 |
| 多个正向组命中且排除组命中 | `公司A 公司B 能力A 能力B 排除A` | 不命中 |

### 10.3 防止错误展开的强制反例

规则：

```text
any("魔方","九州") and any("短剧","漫剧")
```

| 文本 | 预期 |
| --- | --- |
| `魔方` | 不命中 |
| `短剧` | 不命中 |
| `魔方 短剧` | 命中 |

这三项必须作为 matcher 的独立测试。前两项用于捕获 any 被错误提升或展开为顶层 OR 的实现；任一反例误命中均阻断验收。

### 10.4 `not any(...)` 直观验收

规则：

```text
"魔方" and not any("投放","消耗")
```

| 文本 | 预期 |
| --- | --- |
| `魔方 投放` | 不命中 |
| `魔方 剪辑` | 命中 |

另需覆盖 `魔方 消耗` 不命中，以及缺少正向词 `剪辑` 不命中。

### 10.5 兼容性与外层 OR

- `any("A","B") or "C"` 的两个完整 OR 分支可独立命中。
- `"A" and any("B","C") or "D" and any("E","F")` 保持既有优先级。
- `any("A")` 与 `"A"` 匹配结果相同。
- NFKC、大小写和去空白与普通关键词一致。
- 原有 `"A" and "B" or "C"`、not 规则及分号多规则完全兼容。

### 10.6 可选 detector 回归

可在 `tests/test_ocr_detector.py` 增加纯 mock 回归，证明首次和二次 OCR 均使用完整 any + not 规则。原则上不修改 `ocr_detector.py`；parser/matcher 单元测试仍是最低必需范围。

测试命令：

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_text -v
.\venv\Scripts\python.exe -m unittest discover -s tests -v
git diff --check
```

## 11. 变更步骤

### Change 1：新增 any atom 与 parser

修改文件：

- `ocr_text.py`
- `tests/test_ocr_text.py`

内容：

- 新增 frozen `KeywordAnyGroup` 和 `KeywordAtom` 注解。
- 扩展 `parse_atom()`、`parse_any_group()`、`parse_term()`。
- 普通 `KeywordTerm` 与旧规则解析结果保持不变。
- canonical source 保留 any atom，不展开为顶层 OR。
- 拒绝非法参数、嵌套、组合表达式及重复项。
- 分支正向校验泛化为正向 atom 校验。

边界与发布约束：

- Change 1 可以仅完成 parser 和 parser 测试，便于小步评审。
- Change 1 单独完成时不得视为可发布或可交付状态。
- 在 Change 2 完成前，不得对用户宣称 any 已可用，也不得发布包含“parser 已接受 any、matcher 尚未支持”的版本。
- 若阶段性分支上 parser 已能接受 any，必须确保该分支不会进入正式构建或发布流程。

验收：parser 测试通过；any 保持单一 atom；旧规则 AST 不变。

建议 commit：

```text
feat: parse any keyword groups
```

### Change 2：实现 matcher 与完整语义测试

修改文件：

- `ocr_text.py`
- `tests/test_ocr_text.py`
- 可选 `tests/test_ocr_detector.py`（只增加 mock 回归）

内容：

- matcher 支持正向与 negated `KeywordAnyGroup`。
- 加入双正向组强制反例，防止 any 被错误展开。
- 加入 `"魔方" and not any("投放","消耗")` 直观验收。
- 覆盖公司组、能力组、排除组、单项 any 和外层 OR。
- 回归普通 `and`/`or`/`not`、规范化与多规则行为。

边界与发布约束：

- 正式可用状态必须同时包含 Change 1 parser 和 Change 2 matcher。
- 不允许 parser 接受 `any(...)` 后 matcher 静默忽略、按普通关键词处理、退化为任意单词命中或错误展开为顶层 OR。
- 如 matcher 无法正确处理新的 atom，应让功能保持不可发布，而不是增加兼容性 fallback。
- Change 2 全部 matcher 测试及全量回归通过后，功能才具备进入文档和发布验收的资格。

验收：所有正反例通过；不含 any 的表达式行为不变；全量单元测试通过。

建议 commit：

```text
feat: match any keyword groups
```

### Change 3：文档与范围验收

修改文件：

- `README.md`
- 必要的规则文档或验收报告

内容：

- 说明 any 语法、单项 any、与外层 or 的职责区别。
- 明确禁止顶层 OR 展开、纯 `not any` 分支非法、重复项拒绝。
- 说明第一版不支持完整括号和嵌套 any。
- 运行全量测试与 `git diff --check`。
- 核对没有 GUI、OCR 流程、转发、打包或 macOS 变更。

验收：README 示例可被 parser 接受且 matcher 结果符合文档；全量测试通过；diff 范围正确。

建议 commit：

```text
docs: explain any keyword group syntax
```

## 12. 风险与回滚方案

### 12.1 风险约束

- **顶层 OR 错误展开（最高风险）**：会破坏多组之间的 AND 约束，造成大范围误命中。通过独立 atom 类型、禁止展开硬约束和双正向组反例共同防护。
- **parser/matcher 能力不一致**：parser 先接受 any 而 matcher 未支持，会形成静默错误。Change 1 不得单独发布，正式可用必须包含 Change 1 + Change 2。
- **token 边界**：现有 `starts_token()` 依赖 token 后空白，而合法语法通常是 `any(`。需为函数式 atom 单独判断边界，避免拒绝 `any(` 或误识别 `anywhere(`。
- **半套括号解析**：只允许 `any` 自身消费配对括号；其他括号继续报错，不能顺手实现一般表达式分组。
- **`not any` 表面冲突**：它是可否定的 atom，但纯 `not any` OR 分支仍非法；测试和错误信息必须同时体现两层规则。
- **逗号解析**：必须先解析完整 quoted keyword，再识别分隔逗号，不能直接字符串 split。
- **重复项规范化**：按 NFKC/大小写/去空白拒绝语义重复可能比用户预期严格，错误需展示原始项和位置。
- **旧 AST 兼容**：普通规则继续生成 `KeywordTerm`，不能为了 any 全量替换旧 atom。
- **OCR 完整规则相等性**：新增 atom 必须 frozen，匹配期间不得变更，确保二次确认仍比较同一完整规则。

### 12.2 回滚方案

- 三个 Change 独立提交，可逆序回滚。
- 若 Change 2 未完成或失败，正式发布必须同时回滚/排除 Change 1，不能留下“可解析但不可正确匹配”的状态。
- 若 parser 风险超出预期，整体回滚 Change 1/2，恢复原有 `and`/`or`/`not` 行为。
- 不提供将 any 当普通关键词、静默忽略参数或错误展开的 fallback。

## 13. 验收标准

| 验收项 | 通过条件 |
| --- | --- |
| atom 硬约束 | `any(...)` 在结构和匹配中始终是一个 atom，未展开为顶层 OR group |
| 双正向组 | `魔方`、`短剧` 单独均不命中，`魔方 短剧` 命中 |
| 正向 any | any 内任意关键词出现时该 atom 为真 |
| 多正向组 | 公司组和能力组均至少命中一项才命中 |
| 排除 any | `魔方 投放` 不命中，`魔方 剪辑` 命中 |
| 正向与排除同时命中 | 正向组命中但任一排除词出现时完整规则不命中 |
| 单项 any | `any("A")` 合法且匹配结果等价于 `"A"`，但文档标记不推荐 |
| 外层 or | `any(...)` 不改变 `or` 连接完整筛选分支的行为 |
| 优先级 | 保持 `not > and > or` |
| 纯 not 安全约束 | 单独 `not any(...)` 及含纯 not any OR 分支均被拒绝 |
| 非法语法 | 所有列出的非法输入均给出包含位置的清晰错误 |
| 重复项 | 同一 any 内语义重复项被拒绝，不静默去重 |
| parser/matcher 一致 | 正式可用版本同时包含 Change 1 和 Change 2，不存在只解析不匹配状态 |
| 旧规则兼容 | 所有不含 any 的 parser、matcher、detector 测试保持通过 |
| OCR 行为 | 不修改 OCR 流程，完整 `KeywordRule` 继续用于二次确认 |
| 测试范围 | parser 和 matcher 单元测试覆盖核心场景，无需 GUI 测试 |
| 非目标 | 未实现完整括号、嵌套 any、GUI/转发/OCR流程/打包/macOS 变更 |
