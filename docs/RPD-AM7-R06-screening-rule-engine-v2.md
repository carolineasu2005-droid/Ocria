# AM7-R06 — Screening Rule Engine V2

## 1. Metadata

| Field | Value |
|---|---|
| Product | Ocria |
| Generation | Am7 |
| Requirement | AM7-R06 |
| Document Type | Requirement / Product Design |
| Version | 0.1 |
| Status | Frozen |
| Prepared On | 2026-08-18（Asia/Shanghai） |
| Requirement Branch | am7-r06-screening-rule-engine-v2 |
| Upstream Baseline | 45aed52 / AM7-R05 merged main |
| Governing Document | CODEX-CONSTITUTION.md |

## 2. Document Status

本 RPD 定义 AM7-R06 的产品合同，已经通过 Human Review，当前状态为 Frozen。

本次冻结没有实施产品代码或测试，没有修改 R05 文档、依赖、打包或发布资产，也没有执行 commit、push、merge、tag 或 release。

本 RPD 是后续 AM7-R06 TID 的 Frozen product source；Implementation 仍须等待 TID 通过 Human Review 并明确冻结。

## 3. Requirement Summary

AM7-R06 在 R05 ScreeningProfile 与未来 Candidate Decision 之间增加一个独立、纯本地、确定性的 Boolean-combination layer：

~~~text
R05 ScreeningProfile
“应当判断哪些自然语言命题？”
        ↓
Future Criterion Evaluation
“每个 Criterion 的 Boolean 答案是什么？”
        ↓
R06 Screening Rule Engine V2
“这些 Boolean 答案如何组合？”
        ↓
Future Candidate Decision
“对 pass / fail 做什么？”
~~~

R06 的业务输入是以 R05 Criterion ID 为 key 的实际 Boolean 值；规则只引用 Criterion ID，并使用 `AND`、`OR` 和括号表达组合关系。

例如：

~~~text
Criterion Boolean input:
C001 = true
C002 = false
C003 = true

Rule:
C001 AND (C002 OR C003)

Result:
true AND (false OR true)
→ pass = true
~~~

R06 不理解 Criterion 文本含义，不生成 Boolean 值，也不决定任何 Candidate 或页面动作。

## 4. Goals

AM7-R06 v1 的目标是：

1. 定义只由合法 Criterion ID、`AND`、`OR` 和 grouping 组成的最小表达式语言；
2. 冻结括号高于 `AND`、`AND` 高于 `OR` 的运算优先级；
3. 定义一个 Rule 为一条独立 Pass Path；
4. 定义一个非空 RuleSet 为一条或多条独立 Rules；
5. 冻结多 Rule 的固定 ANY 语义；
6. 接收以 Criterion ID 为 key、以实际 Boolean 为 value 的逻辑输入；
7. 在成功时只返回确定性的 Boolean pass 结果；
8. 明确区分业务 `false` 与 missing/invalid input；
9. 严格拒绝 malformed 或 unsupported rules，不修复、不猜测；
10. 保持 R05、Future Evaluation、Future Decision 和页面 Action 的边界不变。

## 5. Non-Goals

AM7-R06 v1 明确不包含：

- Criterion Evaluation；
- LLM call、Prompt design 或 AI Provider selection；
- Candidate document、resume text 或 OCR evidence interpretation；
- OCR、keyword matching、text matching 或 fuzzy matching；
- Candidate Decision；
- favorite、forward、reject、skip、next candidate、retry AI 或其它页面 Action；
- `NOT`、`XOR`、implication、`NAND`、`NOR` 或任意其它 Boolean operator；
- `must_not_match`、exclude、negative operator 或 unary negation；
- `ANY(...)` expression keyword；
- RuleSet-level ALL/ANY mode selector；
- N-of-M、threshold、voting、score、weight 或 priority；
- confidence、unknown、manual_review 或第三种业务结果；
- Boolean algebra optimizer、simplifier 或 canonical rewrite；
- generic expression、Rule、AST、Gate、Guard、Scanner、Wrapper 或 Validator framework；
- Rule persistence、database、ORM 或 migration framework；
- Rule runtime editing、hot reload、GUI 或 Candidate-specific rules；
- RuleSet-to-Run binding；
- ScreeningProfile、Criterion、Candidate 或 Run lifecycle mutation；
- Rule Engine actions；
- R07–R14 的预实现。

## 6. Product Context and Targeted Repository Findings

本轮只检查了 R06 所需的直接上下文，没有执行 repository-wide audit。

### 6.1 R05 frozen and accepted boundary

R05 已提供并接受：

- `Criterion(criterion_id, criterion_text, rule=must_match)`；
- immutable `ScreeningProfileVersion`；
- Configuration-only in-memory Draft；
- Criterion ID 自动分配和正式历史；
- `criteria_digest`；
- Run-level `screening_profile_id + profile_version + criteria_digest` binding；
- Candidate 只通过既有 `run_id` 间接对齐 Profile；
- Candidate Schema 与岗位条件隔离。

R05 Acceptance Report 的 AC-01–AC-20 均已通过；报告也明确 R05 没有 Criterion evaluator、Rule Engine V2 或 Candidate Decision。

当前实现对 Criterion ID 的直接约束为：大写 `C` 后跟至少三位十进制数字，数字值大于 0。生成序列包含 `C001` 至 `C999`，并自然延伸到 `C1000`。

### 6.2 Existing BossOCR keyword-rule concept

现有 `ocr_text.py` 中的旧逻辑直接针对 OCR text：

- expression atom 是 quoted keyword 或 `any(...)` keyword group；
- 支持 `and`、`or` 和 `not`；
- `AND` 高于 `OR`；
- 分号分隔多条独立 keyword rules；
- matching 返回第一条命中的 keyword rule；
- text normalization、keyword containment 和 OCR detector 与规则判断相连。

R06 只继承“Boolean combination”和“多条独立 Pass Path”这两个产品概念。R06 不复用或继承 quoted keyword、`any(...)`、`not`、text normalization、keyword containment、semicolon input format、first-match output、OCR detector 或任何转发动作。

### 6.3 Candidate and Run placement

当前 `CandidateOcrDocument` 是 Candidate/OCR evidence object，并通过 `run_id` 关联 Run；它没有 R05 Profile business fields。当前 `RunManifest` 的 R05 binding 只包含 Profile ID、Version 和 criteria digest。

R06 不修改这两个对象，也不在本 Requirement 增加 RuleSet persistence 或 Run binding。它是未来 Evaluation output 与未来 Decision input 之间的独立纯逻辑层。

## 7. Core Concepts

### 7.1 Criterion Reference

Criterion Reference 是表达式中对一个 R05 Criterion ID 的精确文本引用，例如 `C001` 或 `C1000`。

它不包含 criterion_text，不携带 rule、score、weight、priority、action 或 Profile identity。

### 7.2 Criterion Boolean Result

Criterion Boolean Result 是 Future Evaluation 对某个 Criterion 产生的实际 Boolean：

~~~text
C001 = true
C002 = false
~~~

`false` 表示该 Criterion 已经得到业务 Boolean false；它不等于“没有结果”。

### 7.3 Rule

Rule 是一个非空、语法合法的 Boolean expression，只能由 Criterion References、`AND`、`OR` 和括号组成。

每个 Rule 表示一条独立 Pass Path。Rule 本身没有 name、ID、priority、weight、score 或 action。

### 7.4 RuleSet

RuleSet 是 one-or-more Rule collection，即一条或多条独立 Rules 的 collection。名称中的 `Set` 不表示 mathematical set：duplicate Rules 允许存在，不要求 uniqueness，也不自动 deduplicate。空 RuleSet 无法表达任何有效 Pass Path，因此是 invalid configuration / invalid evaluation input。

### 7.5 Successful Pass Result

当完整 RuleSet 和 Boolean input 均合法时，R06 只产生一个 Boolean：

~~~text
pass = true
~~~

或：

~~~text
pass = false
~~~

invalid rule 或 invalid input 是失败条件，不是第三种业务结果。

## 8. Rule Product Contract

一个合法 Rule 必须满足：

1. expression 非空，且去除外围空白后仍非空；
2. 至少引用一个合法 Criterion ID；
3. 所有 operand 都是 Criterion Reference；
4. 所有 operator 都是 `AND` 或 `OR`；
5. grouping 只能使用成对圆括号；
6. operator 与 operand 的位置合法；
7. 不包含隐式 operator、unsupported token 或自由文本。

单 Criterion Rule 合法：

~~~text
C001
~~~

全 mandatory 条件使用同一个 Rule 表达：

~~~text
C001 AND C002 AND C003
~~~

有替代条件时使用 Rule 内部 `OR` 或 grouping：

~~~text
C001 AND (C002 OR C003)
~~~

重复引用合法：

~~~text
C001 AND C001
~~~

逻辑冗余表达式也合法：

~~~text
C001 OR (C001 AND C002)
~~~

R06 按表达式语义计算，不拒绝、优化、简化或重写这类冗余。

## 9. RuleSet / Independent Pass Path Contract

一个合法 RuleSet 必须包含至少一条合法 Rule。`RuleSet` 是产品命名，不具有 mathematical-set uniqueness 语义；相同 Rule 可以作为多个 collection entries 保留。

每条 Rule 都是独立 Pass Path；RuleSet-level 组合语义固定为 ANY：

- 任意一条 Rule = true → overall `pass = true`；
- 所有 Rules = false → overall `pass = false`。

例如：

~~~text
Rule 1: C001 AND C002
Rule 2: C001 AND C003
Rule 3: C004
~~~

整体语义等价于：

~~~text
(Rule 1) OR (Rule 2) OR (Rule 3)
~~~

但 R06 v1 不增加 `ANY(...)` keyword，也不增加 RuleSet mode 字段。

Rule collection 的顺序不改变 overall Boolean result。重复的 Rules 可以存在，其效果只是逻辑冗余；R06 不要求 deduplication。

若 RuleSet 中任何一条 Rule invalid，整个 RuleSet invalid；不得因为另一条 Rule 已经为 true 而忽略 invalid Rule。

## 10. Boolean Input Contract

R06 的逻辑输入是 Criterion ID → Boolean 的 mapping，例如：

~~~json
{
  "C001": true,
  "C002": false,
  "C003": true
}
~~~

冻结约束：

1. 每个 key 必须是合法 R05-compatible Criterion ID；
2. 每个 value 必须是实际 Boolean；
3. 不接受 truthy/falsy coercion；
4. RuleSet 中每个被引用的 ID 都必须在 mapping 中存在；
5. reference matching 使用 Criterion ID 的精确字符串，不做 case folding、numeric aliasing 或自动 zero-padding；
6. mapping 可以包含 RuleSet 未引用的其它合法 Boolean Criterion Results；这些额外结果被忽略，不改变 pass；
7. mapping 的 insertion order 不影响结果。

R06 core 不接收完整 ScreeningProfile，也不靠读取 criterion_text 判断 membership。R06 自己冻结的有效性边界是：reference 形式合法，并且每个 reference 都有实际 Boolean input。

未来 Profile-aware integration 如果持有 frozen Profile 的 allowed Criterion-ID set，应在其外层 integration boundary 验证 Evaluation output 与 Profile 的一致性；这不是 R06 core 对 ScreeningProfile 内容的依赖，也不授权 R06 修改 Profile。

## 11. Expression Language

AM7-R06 v1 的概念 grammar 为：

~~~text
rule           := or_expression
or_expression  := and_expression (OR and_expression)*
and_expression := primary (AND primary)*
primary        := criterion_id | "(" or_expression ")"
criterion_id   := "C" + at least three decimal digits, numeric value > 0
~~~

产品级 lexical contract：

- Criterion ID 的 `C` 必须大写；
- operator token 精确使用大写 ASCII `AND`、`OR`；
- Criterion ID 与 `AND` / `OR` 必须分别构成完整、独立的 lexical token，不能嵌入 arbitrary identifier；
- expression start/end、whitespace、`(` 和 `)` 可以形成 lexical token boundary；
- token 之间允许空白，外围空白不改变语义；whitespace 可以分隔相邻的 Criterion/operator tokens；
- Criterion ID 或 operator 内部不能插入空白；
- `(` / `)` 本身可以分隔相邻 token，因此圆括号可直接邻接 Criterion ID 或 operator；
- 不支持 quoted text、keyword、comma、semicolon、function call 或其它 punctuation；
- 不执行自动分词、大小写修复、同义词替换、malformed rule repair 或 intent guessing。

因此：

- `C001 AND C002` 合法；
- `C001 AND(C002 OR C003)` 合法，`AND` 与 `(` 之间由括号形成 token boundary；
- `C001ANDC002` 非法，Criterion ID 与 `AND` 之间没有 token boundary；
- `C001OR(C002)` 非法，Criterion ID 与 `OR` 之间没有 token boundary。

`C01` 不满足至少三位数字；`C000` 的数字值不是正数；两者均 invalid。符合形式的 ID 仍按精确字符串匹配，不把 `C0001` 自动改写为 `C001`。

## 12. AND / OR / Grouping Semantics

### 12.1 AND

`A AND B` 只有在 A 与 B 都是 true 时为 true：

| A | B | A AND B |
|---|---|---|
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

连续 `AND` 表示所有 operands 都必须为 true。

### 12.2 OR

`A OR B` 在 A 或 B 任意一个为 true 时为 true：

| A | B | A OR B |
|---|---|---|
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

连续 `OR` 表示任意 operand 为 true 即为 true。

### 12.3 Grouping

圆括号建立显式 grouping，并优先计算括号内表达式：

~~~text
C001 AND (C002 OR C003)
~~~

括号只改变 Boolean grouping，不创建 sub-rule、priority、score 或独立 action。

## 13. Operator Precedence

优先级从高到低冻结为：

1. parentheses；
2. `AND`；
3. `OR`。

因此：

~~~text
C001 OR C002 AND C003
~~~

必须解释为：

~~~text
C001 OR (C002 AND C003)
~~~

而不是：

~~~text
(C001 OR C002) AND C003
~~~

Human 可以使用括号覆盖默认优先级，但正常优先级已经唯一确定时不强制增加括号。同一优先级的连续 operator 按从左到右组合；由于 `AND` 和 `OR` 各自满足结合律，这不改变 Boolean result。

## 14. NOT Exclusion and Negative Criterion Principle

`NOT` 在 R06 v1 中是 hard unsupported。以下 Rule 必须 invalid：

~~~text
NOT C001
~~~

原因是 Future Evaluation 可能把 insufficient evidence 映射为 Criterion Boolean false。若 Rule Engine 允许 `NOT C001`，缺乏证据就可能被反转为 passing condition。

负向业务要求继续遵循 R05 已冻结原则：把要求本身写成一个正向 Boolean proposition。

例如：

~~~text
C004 = “没有棋牌游戏项目经历”
~~~

Future Evaluation 判断该完整命题是否为 true；R06 只使用：

~~~text
C001 AND C004
~~~

R06 不增加 `must_not_match`、exclude、negative flag、unary negation 或其它等价旁路。

## 15. Multiple Independent Rule / ANY Semantics

固定 ANY 语义既覆盖 alternative Pass Paths，也避免新增 RuleSet-level configuration。

若所有条件 mandatory，Human 写一条 Rule：

~~~text
C001 AND C002 AND C003
~~~

若存在 alternative path，Human 可以写多个独立 Rules：

~~~text
Rule 1: C001 AND C002
Rule 2: C001 AND C003
~~~

或在单 Rule 内表达局部 alternative：

~~~text
C001 AND (C002 OR C003)
~~~

R06 不提供 ALL_RULES、ANY_RULES、mode selector、N-of-M、threshold 或 voting。RuleSet 的多 Rule ANY 是固定产品语义，不是可配置策略。

## 16. Deterministic Evaluation Contract

对同一组 Rule expression 文本和同一组 Criterion Boolean mappings，R06 必须总是返回相同 Boolean result。

结果不得依赖：

- time 或 timezone；
- random value；
- network；
- Provider 或 LLM；
- OCR、browser 或 clipboard state；
- Candidate ordering；
- mapping insertion order；
- Rule collection order；
- action mode；
- persistence state。

Evaluation 必须 side-effect free。它不写 Profile、Candidate、Run、Rule 或 Action state。

完整 RuleSet、所有 Rule 和整个 supplied mapping 必须先满足产品合同，才能产生成功 Boolean result。实现是否内部 short-circuit 属于 TID detail，但 short-circuit 不得隐藏 invalid rule、missing referenced input 或 non-Boolean input。

## 17. Invalid Rule Behavior

Invalid Rule 或包含 Invalid Rule 的 RuleSet 必须被拒绝，不产生成功 pass result。

至少以下形式 invalid：

~~~text
NOT C001
C001 XOR C002
C001 && C002
C001 || C002
C001 AND
OR C001
(C001 OR C002
C001 OR )
SLG AND C001
C01
C000
C001 C002
"C001" AND C002
~~~

invalid 包括：

- empty 或 whitespace-only expression；
- malformed/unbalanced/empty parentheses；
- missing operand 或 operator；
- unsupported operator、identifier、literal、punctuation 或 function；
- Criterion ID 形式错误；
- implicit concatenation；
- arbitrary business text。

R06 不 silent repair、不补括号、不补 operand、不替换 operator、不把 keyword 猜成 Criterion ID，也不通过 Boolean simplification 使 malformed rule 看似可执行。

具体 exception class、error code 或 diagnostic object 属于 TID；本 RPD 只冻结“明确失败且没有 Boolean success result”。

## 18. Invalid / Missing Boolean Input Behavior

Rule 引用了不存在于 Boolean mapping 的 Criterion ID 时，整体 evaluation 必须失败。

例如：

~~~text
Rule: C001 AND C002
Input: {"C001": true}
~~~

`C002` missing 不得解释为 `C002=false`。

以下值都不是合法 Boolean Criterion Result：

~~~text
1
0
"true"
"false"
null
[]
{}
~~~

不得执行 truthy/falsy coercion。

validation 覆盖完整 supplied mapping 与全部 Rule references：

- 即使 `C001=true` 已足以令 `C001 OR C002` 为 true，missing `C002` 仍是 invalid input；
- 即使 Rule 1 已经为 true，Rule 2 的 missing input 或 invalid syntax 仍使整体 evaluation 失败；
- 未被 Rule 引用的额外 mapping value 也必须是实际 Boolean，不能借“未使用”绕过输入合同。

invalid input / evaluation failure 与成功业务 `pass=false` 是不同结果。R06 不增加 unknown/manual_review 等第三种业务结果，也不决定 failure 后的 Candidate action。

## 19. ScreeningProfile Boundary

R05 与 R06 保持独立：

| R05 owns | R06 owns |
|---|---|
| Criterion identity and natural-language proposition | Criterion ID references in Boolean expressions |
| `criterion_id`, `criterion_text`, `rule=must_match` | `AND`, `OR`, grouping and fixed multi-Rule ANY |
| Profile Draft/Save/version/history | Pure Rule validation and Boolean combination semantics |
| `criteria_digest` | Boolean pass result on successful evaluation |
| Run-level frozen Profile binding | No Run binding in R06 v1 |

R06 不修改：

- `screening_profile_id`；
- `profile_version`；
- Criterion fields 或 ID allocation；
- criterion_text / must_match semantics；
- `criteria_digest` inputs 或 output；
- Draft lifecycle；
- Profile persistence；
- Run Profile binding；
- Candidate Schema boundary。

Rule 或 RuleSet 的变化不改变 R05 `criteria_digest`，因为该 digest 只覆盖 R05 Criterion content。R06 也不把 expression、RuleSet reference、priority、weight、score 或 action 写入 Criterion。

## 20. Candidate / Evaluation / Decision Boundary

### 20.1 Future Criterion Evaluation

Future Evaluation owns：

- 读取 frozen Profile Criteria；
- 解释 criterion_text；
- 检查 Candidate/OCR/其它 evidence；
- 必要时调用 LLM Runtime；
- 决定 evidence 是否足够；
- 产生 Criterion ID → Boolean mapping；
- 保证 mapping 与相应 frozen Profile 的一致性。

R06 不决定某个 Criterion 为什么是 true 或 false。

### 20.2 R06 Rule Engine

R06 owns：

- Rule / RuleSet validity；
- Criterion Reference 与 Boolean mapping 对齐；
- `AND`、`OR`、grouping 与 precedence；
- fixed multi-Rule ANY；
- successful Boolean pass result。

### 20.3 Future Candidate Decision / Action

Future Decision owns：

- pass / fail 对应的产品 Decision；
- invalid evaluation failure 的处置；
- favorite、forward、reject、skip、manual review、retry 或 stop；
- 页面 Action ordering 和 fail-safe behavior。

R06 不创建 Candidate Decision，不触发 Candidate switch，不操作浏览器，也不写页面 Action。

## 21. Persistence / Runtime Integration Deferral

AM7-R06 v1 只冻结 parse / validate / evaluate 的产品语义。

本 Requirement 不增加：

- Rule 或 RuleSet persistence schema/path；
- Rule ID、RuleSet ID、version、digest 或 lifecycle；
- Profile-to-RuleSet relation；
- RuleSet-to-Run binding；
- startup selection 或 active/default RuleSet；
- CLI/UI authoring；
- runtime editing 或 hot reload；
- Candidate-specific RuleSet；
- audit/event storage。

这些能力不是当前 Rule Engine 合同成立的必要条件，因此全部延期到有明确产品 Requirement 时处理。TID 不得以实现方便为由把它们回填到 R06。

## 22. Compatibility

### 22.1 R05 compatibility

R06 只复用 R05 Criterion ID 形式，并消费未来以这些 ID 为 key 的 Boolean results。R05 的 accepted schema、persistence、version、digest、Configuration/Execution separation 和 Run binding 均保持不变。

### 22.2 Legacy keyword logic compatibility

旧 BossOCR keyword rules 保持其既有 OCR/action用途；R06 RPD 不修改、迁移或兼容读取该语法。

R06 Rule 不是旧 KeywordRule 的新 serialization version。quoted keywords、`not`、`any(...)`、semicolon rule input、normalization 和 first matching rule 都不属于 R06 contract。

### 22.3 Candidate and Run compatibility

R06 不向 `CandidateOcrDocument`、Candidate metadata、candidates.jsonl 或 `RunManifest` 增加字段。现有 R05 binding 也不增加 RuleSet reference。

### 22.4 Runtime compatibility

R06 的纯 Boolean semantics 不依赖 OpenAI-compatible Runtime、Provider config、OCR backend、browser automation 或 action mode。当前 Requirement 不改变这些系统。

## 23. Invariants

以下为 AM7-R06 v1 硬性不变量：

1. R06 只组合已经存在的 Criterion Boolean Results。
2. R06 不生成或推断 Criterion Boolean Result。
3. Rule 是一条非空、合法的独立 Pass Path。
4. Rule 只包含合法 Criterion ID、`AND`、`OR` 和圆括号。
5. RuleSet 包含至少一条 Rule。
6. 多 Rule 的 overall semantics 永远是 fixed ANY。
7. 任一 Rule true 时 overall pass=true；全部 Rules false 时 overall pass=false。
8. RuleSet 不存在 configurable ALL/ANY mode。
9. 全 mandatory 条件在一条 Rule 内用 `AND` 表达。
10. Parentheses 高于 `AND`，`AND` 高于 `OR`。
11. `NOT` 和所有等价 negative operator 均 unsupported。
12. 负向业务条件继续由 R05 natural-language positive proposition 表达。
13. 每个 Rule reference 必须具有实际 Boolean input。
14. Missing reference 是 invalid input，不是 false。
15. 所有 supplied logical values 必须是 actual Boolean，不执行 coercion。
16. Invalid rule/input 不产生成功 Boolean result，也不是第三种业务结果。
17. 成功结果只有 Boolean pass=true 或 pass=false。
18. Duplicate references、duplicate Rules 和 logically redundant expressions 可以存在。
19. R06 不做 Boolean optimizer、simplification 或 canonical rewrite。
20. 相同 Rules 与相同 Boolean inputs 必须得到相同结果。
21. Rule collection order、mapping order、time、network 和 external state 不影响结果。
22. Evaluation side-effect free。
23. R06 不读取 criterion_text、Candidate/OCR text 或 browser state。
24. R06 不调用 LLM、Provider、OCR 或页面 Action。
25. R06 不修改 R05 Criterion schema、criteria_digest、Profile lifecycle 或 Run binding。
26. R06 不修改 Candidate Schema。
27. R06 v1 不持久化 Rule/RuleSet，不提供 runtime editing，也不绑定 Run。
28. Future Decision 独立拥有 pass/fail 或 evaluation failure 之后的动作。

## 24. Acceptance Criteria

以下 Acceptance Criteria 可由后续 TID 映射为 targeted automated tests。当前 RPD 不创建测试。

- **AC-01 — Rule and Criterion reference**：单 Criterion Rule `C001` 合法；Rule 可引用 `C001`、`C025`、`C999`、`C1000` 等 R05-compatible ID，并按 exact string lookup。
- **AC-02 — Boolean mapping input**：以合法 Criterion ID 为 key、actual Boolean 为 value 的 mapping 可作为逻辑输入；mapping insertion order 不影响结果。
- **AC-03 — AND semantics**：`C001 AND C002` 仅在两个输入都为 true 时返回 true，其余三个 Boolean 组合均返回 false。
- **AC-04 — OR semantics**：`C001 OR C002` 仅在两个输入都为 false 时返回 false，其余三个 Boolean 组合均返回 true。
- **AC-05 — Grouping semantics**：`C001 AND (C002 OR C003)` 对 `true,false,true` 返回 true，并按括号建立的 grouping 计算。
- **AC-06 — Precedence**：`C001 OR C002 AND C003` 等价于 `C001 OR (C002 AND C003)`；显式 `(C001 OR C002) AND C003` 可以覆盖默认 grouping。
- **AC-07 — Fixed multi-Rule ANY**：一个包含多条合法 Rules 的 RuleSet 在任一 Rule true 时 overall pass=true，在全部 Rules false 时 overall pass=false；Rule order 不改变结果。
- **AC-08 — Mandatory conditions**：所有 mandatory 条件可由单 Rule `C001 AND C002 AND C003` 表达；不存在 RuleSet-level ALL/ANY mode、ANY keyword 或 mode selector。
- **AC-09 — Redundancy**：`C001 AND C001`、重复 Rule 以及 `C001 OR (C001 AND C002)` 均可确定性计算；不要求 deduplication、optimizer、simplifier 或 canonical rewrite。
- **AC-10 — NOT exclusion**：`NOT C001` 及任何等价 unary negative form 均被拒绝；负向业务要求继续由 R05 Criterion natural-language proposition 表达。
- **AC-11 — Unsupported syntax and token boundaries**：`C001 AND C002` 与 `C001 AND(C002 OR C003)` 具有合法 token boundaries；`C001ANDC002`、`C001OR(C002)`、`XOR`、`&&`、`||`、arbitrary identifier、quoted keyword、`C01`、`C000` 和 implicit operator 均被拒绝，不执行自动分词、repair 或 guessing。
- **AC-12 — Malformed or empty Rule**：empty/whitespace-only Rule、missing operand/operator、unbalanced/empty parentheses 均 invalid，不产生成功 Boolean result。
- **AC-13 — Empty RuleSet**：零条 Rules 的 collection invalid，不被解释为 pass 或 fail。
- **AC-14 — Missing reference**：RuleSet 的任一 referenced ID 缺少 mapping entry 时整体 evaluation 失败；missing 不被转换为 false，且不能被 Rule/Boolean short-circuit 隐藏。
- **AC-15 — Strict Boolean values**：`1`、`0`、strings、null、list、object 等 non-Boolean values 均 invalid，不执行 truthy/falsy coercion；该约束也覆盖未被 Rule 引用的 supplied entries。
- **AC-16 — Extra Boolean results**：mapping 中未被 RuleSet 引用的其它合法 ID→Boolean entries 可以存在并被忽略，不改变 pass。
- **AC-17 — Successful output**：合法 evaluation 的 product output 只有 Boolean pass=true/false；不产生 qualified、rejected、unknown、manual_review、confidence、score、explanation 或 action。
- **AC-18 — Determinism and purity**：同一 Rules 与同一 Boolean mapping 重复 evaluation 得到相同 result，且不读取 time/network/random/external state、不产生 side effect。
- **AC-19 — Evaluation boundary**：Rule Engine 不读取 criterion_text 或 Candidate/OCR evidence，不调用 LLM，不生成 Criterion truth；Boolean mapping 由 Future Evaluation 提供。
- **AC-20 — R05 isolation**：R05 Criterion 仍只含 criterion_id、criterion_text、rule=must_match；Profile ID/version、criteria_digest、Draft、persistence 与 Run binding 均不因 R06 改变。
- **AC-21 — Candidate and Run isolation**：Candidate Schema 与 RunManifest 不增加 R06 field；R06 不执行 runtime Profile mutation、Rule editing、hot reload 或 RuleSet-to-Run binding。
- **AC-22 — Decision and Action isolation**：R06 不创建 Candidate Decision，不决定 invalid failure 的业务处置，也不触发 favorite、forward、next candidate、browser 或其它页面 Action。
- **AC-23 — No quantitative modes**：R06 不产生或消费 score、weight、priority、N-of-M、threshold 或 voting configuration。
- **AC-24 — No persistence expansion**：R06 v1 没有 Rule/RuleSet persistence、ID、version、digest、database、ORM、GUI 或 Candidate-specific rules；这些不作为 parse/validate/evaluate 合同的隐藏前置条件。

## 25. Known Limitations / Explicit Deferrals

R06 v1 明确接受以下限制：

- expression language 只有 Criterion ID、`AND`、`OR` 和 parentheses；
- operator 使用冻结的 uppercase token；
- 没有 `NOT` 或其它 Boolean operator；
- 没有 `ANY(...)` function；
- RuleSet 多 Rule 只支持 fixed ANY；
- 没有 configurable ALL、N-of-M 或 quantitative decision；
- 没有 explanation、matched Rule、trace 或 partial result 产品输出；
- 没有 third business state；
- 没有 Boolean optimizer 或 normalized expression requirement；
- 没有 Profile membership lookup；Profile-aware consistency 属于 outer integration；
- 没有 Rule/RuleSet persistence、identity、version、digest 或 Run binding；
- 没有 runtime editing、hot reload、CLI/UI 或 GUI；
- 没有 Candidate-specific rules；
- 没有 Evaluation implementation；
- 没有 Candidate Decision 或 Action implementation；
- exact Python API、parser representation、error classes 和 test/file layout 留给未来 TID。

这些是显式 deferral，不构成 Draft 未完成项，也不授权 TID 预实现。

## 26. Open Issues / Contract Conflicts

### 26.1 Open Issues

None.

### 26.2 Contract Conflicts

None.

Targeted inspection 显示 R05 明确延期 Rule Engine，当前 R05 Criterion ID 形式可以直接作为 R06 reference；Candidate/Run 边界也不要求 R06 增加 persistence 或 binding。旧 keyword logic 与 R06 是不同输入域和责任层，不构成需要兼容其 `NOT`、`any(...)` 或 OCR coupling 的上游合同。

## 27. Final Product Conclusion

AM7-R06 v1 冻结一条最小、确定性、无副作用的 Boolean-combination 产品合同：

~~~text
Future Criterion Boolean Results
+ one or more independent Criterion-ID Rules
→ validate complete RuleSet and Boolean mapping
→ evaluate parentheses > AND > OR
→ fixed ANY across independent Rules
→ Boolean pass
~~~

R06 回答的唯一问题是“已经得到的 Boolean Criterion answers 如何组合”。它不回答 Criterion 为什么为 true/false，也不决定 pass/fail 后产品做什么。

本设计保持 R05 ScreeningProfile、Future Evaluation、Future Decision 和页面 Action 四个责任层清晰分离；不引入 `NOT`、RuleSet mode、score、persistence、Run binding 或通用 Rule framework。

本 RPD 当前为 Version 0.1、Frozen，已经通过 Human Review，可作为 AM7-R06 TID 的产品合同；在 TID 通过 Human Review 并冻结前仍不得实施代码。
