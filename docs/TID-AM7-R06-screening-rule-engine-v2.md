# AM7-R06 — Screening Rule Engine V2

## 1. Metadata

| Field | Value |
|---|---|
| Product | Ocria |
| Generation | Am7 |
| Requirement | AM7-R06 |
| Document Type | Technical Implementation Design |
| Version | 0.1 |
| Status | Frozen |
| Prepared On | 2026-08-18（Asia/Shanghai） |
| Requirement Branch | am7-r06-screening-rule-engine-v2 |
| Upstream Baseline | 45aed52 / AM7-R05 merged main |
| Source RPD | AM7-R06 v0.1 Frozen（docs/RPD-AM7-R06-screening-rule-engine-v2.md） |
| Governing Document | CODEX-CONSTITUTION.md v1.0 |

## 2. Document Status

本 TID 将 Frozen RPD 映射为 AM7-R06 的最小技术实现合同，已经通过 Human Review，当前状态为 Frozen。

本次 Human Review clarification 没有实施产品代码或测试，没有执行完整回归、commit、push、merge、tag 或 release。

## 3. Frozen Inputs

Implementation 必须同时遵守：

1. `CODEX-CONSTITUTION.md` v1.0；
2. `docs/RPD-AM7-R06-screening-rule-engine-v2.md` v0.1 Frozen；
3. R05 已接受的 Criterion ID、ScreeningProfile、criteria digest、Run binding 与 Candidate isolation 合同；
4. upstream baseline `45aed52` 的根级 module 和 `unittest` layout。

若这些输入发生真实矛盾，不得自行增加 compatibility workaround、Gate、Guard、Scanner、Wrapper、Validator framework 或其它架构；应只停止受影响合同点并报告 Human。

## 4. Implementation Objective

AM7-R06 的最小实现只包含：

~~~text
immutable Rule value
+ immutable one-or-more Rule collection
+ local tokenizer / parser
+ complete RuleSet and Boolean mapping validation
+ deterministic Boolean evaluator
~~~

成功路径：

~~~text
ScreeningRuleSet
+ Mapping[Criterion ID, actual bool]
→ tokenize and parse every Rule
→ validate every supplied mapping entry
→ validate every referenced ID is present
→ evaluate each Rule
→ fixed ANY across Rules
→ bool
~~~

本实现不接收 ScreeningProfile、Candidate、OCR text 或 LLM result object；它只接收 RuleSet 与 Boolean mapping。

## 5. Targeted Repository Findings

本轮只检查了 R06 最小实现直接依赖的文件和 layout，没有执行 repository-wide audit。

### 5.1 Python module layout

当前仓库的 product modules 直接位于 repository root，例如：

- `screening_profile.py`；
- `ocr_text.py`；
- `llm_provider_runtime.py`；
- `ai_provider_config.py`。

Tests 位于 `tests/test_*.py`，使用标准库 `unittest`，并直接 import root modules。R06 因此使用同一最小 layout，不创建 package subtree、service layer 或 repository layer。

### 5.2 R05 Criterion ID contract

`screening_profile.py` 当前使用：

~~~python
_CRITERION_ID_PATTERN = re.compile(r"C([0-9]{3,})\Z")
~~~

并要求捕获的数字值大于 0。该合同接受 `C001`、`C025`、`C999`、`C1000`，拒绝 `C01`、lowercase `c001` 和 `C000`。

R05 的 `_numeric_criterion_id()` 是 private helper；构造 `Criterion` 又需要 criterion_text 和 rule，不适合作为 R06 ID-only validation dependency。

### 5.3 Error conventions

直接相关现有 conventions 为：

- `KeywordRuleSyntaxError(ValueError)`：旧 keyword syntax failure；
- `ScreeningProfileValidationError(ValueError)`：R05 domain validation failure；
- `ScreeningProfileIOError(RuntimeError)`：R05 persistence failure。

R06 没有 I/O，因此只需要本地 `ValueError` subclasses，不增加 Runtime error/result framework。

### 5.4 Legacy keyword parser isolation

`ocr_text.py` 的 `KeywordRule` / `parse_keyword_rules()`：

- operand 是 quoted keyword 或 `any(...)`；
- 支持 case-insensitive `and`、`or`、`not`；
- 分号分隔多条 rules；
- evaluator 读取 normalized OCR text 并返回 first matching rule。

这些 input、output 与 OCR coupling 都不属于 R06。R06 不 import、wrap、extend 或 modify `ocr_text.py`，只独立实现 Frozen Criterion-ID Boolean grammar。

### 5.5 Dependencies and current gap

当前 repository 没有 `screening_rule_engine.py` 或对应 test file，也没有 parser-framework dependency。R06 语法规模不需要第三方 parser；标准库足够。

## 6. Implementation Constraints

实现必须遵守：

- smallest local implementation；
- Python 3.10+ / current Python 3.11 development baseline compatible；
- standard library only；
- handwritten tokenizer and parser；
- no generic Rule、AST、Gate、Guard、Scanner、Wrapper 或 Validator framework；
- no reusable expression infrastructure；
- no persistence、database 或 ORM；
- no Rule ID、RuleSet ID、version 或 digest；
- no CLI/UI authoring；
- no Run binding；
- no ScreeningProfile mutation；
- no Candidate schema change；
- no Criterion Evaluation、LLM、Decision 或 Action integration；
- no Legacy keyword behavior change；
- no OCR、browser、mouse 或 action module change；
- no dependency、packaging 或 PyInstaller change。

## 7. Final Module and File Layout

### 7.1 New implementation files

~~~text
screening_rule_engine.py
tests/test_screening_rule_engine.py
~~~

`screening_rule_engine.py` 集中包含 R06 public value types、two error types、private tokenizer/parser 与 evaluator。当前规模不得拆为 token、parser、AST、service 或 validation submodules。

`tests/test_screening_rule_engine.py` 使用 `unittest` 覆盖 RPD AC-01–AC-24。

### 7.2 Modified implementation files

None.

R06 是独立纯逻辑能力，没有当前 runtime integration；因此不需要修改任何现有 production 或 test file。

### 7.3 Dependency and packaging files

不修改：

- `requirements.txt`；
- `requirements-ocr.txt`；
- `BossOCR.spec`；
- `.gitignore`。

## 8. Public Rule and RuleSet Types

### 8.1 ScreeningRule

~~~python
@dataclass(frozen=True)
class ScreeningRule:
    expression: str
~~~

Constructor shape validation：

- `expression` 必须是 string；
- `expression` 去除 whitespace 后必须非空；
- source string 原样保留，不 trim、不 case-fold、不 canonicalize；
- full lexical/grammar validation 在 `evaluate_rule_set()` 的完整 validation phase 执行。

`ScreeningRule` 不增加 name、ID、priority、weight、score、action、Profile reference、parsed AST 或 serialization method。

### 8.2 ScreeningRuleSet

~~~python
@dataclass(frozen=True)
class ScreeningRuleSet:
    rules: tuple[ScreeningRule, ...]
~~~

Constructor shape validation：

- `rules` 必须是 tuple；
- tuple 至少包含一项；
- 每项必须是 `ScreeningRule`；
- tuple 顺序保留；
- duplicate Rules 允许存在；
- 不要求 expression uniqueness，不自动 deduplicate。

名称中的 `Set` 不映射为 Python `set` / `frozenset`，也不表示 mathematical-set uniqueness。使用 tuple 是为了表达 one-or-more immutable collection 并保留 duplicate entries。

`ScreeningRuleSet` 不增加 mode、ID、version、digest、Profile reference 或 Run reference。

`ScreeningRule` / `ScreeningRuleSet` constructor success 只表示以上 public value shape validation 成功，不表示其中 expression 已通过完整 lexical 或 grammar validation。Constructors 不调用 tokenizer/parser，也不把 shape-valid object 宣称为 semantic-valid Rule/RuleSet；完整 Rule semantic validation 统一由 `evaluate_rule_set()` 的 validation phase 完成。

因此，一个 non-empty string 即使包含 `C001ANDC002` 等 lexical-invalid source，仍满足 `ScreeningRule` constructor 的 value shape；当它进入 `evaluate_rule_set()` 时，必须由完整 tokenizer/parser validation 拒绝且不产生 Boolean success result。

## 9. Public Minimal API

唯一 public operation 冻结为：

~~~python
def evaluate_rule_set(
    rule_set: ScreeningRuleSet,
    criterion_results: Mapping[str, bool],
) -> bool:
    ...
~~~

API contract：

- `rule_set` 必须是 `ScreeningRuleSet`；
- `criterion_results` 必须是 `collections.abc.Mapping`；
- 成功只返回 exact `bool`；
- invalid Rule/RuleSet 抛出 `ScreeningRuleValidationError`；
- invalid/missing Boolean input 抛出 `ScreeningRuleInputError`；
- failure 不返回 bool、partial result、matched Rule 或 diagnostic object。

Parsing 与 evaluation 不提供两个 public calls。`evaluate_rule_set()` 在一次调用内先完成 parse/validate，再 evaluation；tokenizer、parser 和 Criterion-ID helper 都保持 module-private。

不增加 `validate_rule()`、`parse_rule()`、`compile_rule()`、`explain()` 或 generic evaluator API。

## 10. Exception and Failure Types

模块只定义：

~~~python
class ScreeningRuleValidationError(ValueError):
    ...

class ScreeningRuleInputError(ValueError):
    ...
~~~

### 10.1 ScreeningRuleValidationError

用于：

- Rule expression type invalid 或 empty；
- RuleSet type/shape invalid 或 empty；
- invalid token boundary；
- unsupported token/operator；
- malformed Criterion ID token；
- malformed grammar、operand/operator order 或 parentheses；
- RuleSet 中任一 Rule invalid。

### 10.2 ScreeningRuleInputError

用于：

- `criterion_results` 不是 Mapping；
- 任一 supplied key 不是合法 Criterion ID；
- 任一 supplied value 不是 exact bool；
- 任一 referenced Criterion ID missing。

异常消息只需简短识别失败原因；exact wording、structured error code、position object 和 source excerpt 不属于 public contract。不得增加 recovery、error taxonomy framework、partial-result、trace 或 user-facing diagnostic system。

未预期的 programming error 不得被 catch-all 后伪装成 validation result。

## 11. Criterion ID Validation

R06 在 `screening_rule_engine.py` 内定义一个 private、ID-only helper，精确镜像 Frozen R05 形式：

~~~python
_CRITERION_ID_PATTERN = re.compile(r"C([0-9]{3,})\Z")
~~~

Validation：

1. value 必须是 string；
2. fullmatch 必须成功；
3. captured decimal integer 必须大于 0。

同一 helper 同时用于：

- expression Criterion token validation；
- supplied mapping key validation。

R06 不 import R05 private `_numeric_criterion_id()`，也不构造 `Criterion` 来验证 ID。这样保持 exact product contract，同时避免依赖 criterion_text、rule 或完整 ScreeningProfile。

Reference lookup 使用 exact string。不得把 `C0001` canonicalize 为 `C001`，不得自动补零、case-fold 或 numeric-alias。

## 12. Exact Tokenization Contract

### 12.1 Token kinds

Tokenizer 只产生五种 string tokens：

- valid Criterion ID；
- `AND`；
- `OR`；
- `(`；
- `)`。

不定义 public Token class。

### 12.2 Lexical boundary

Lexical token boundary 精确为：

- expression start；
- expression end；
- Python `str.isspace()` character；
- `(`；
- `)`。

Criterion ID 与 `AND` / `OR` 必须是完整独立 token。Parentheses 自身既是 token，也可形成相邻 token boundary。

### 12.3 Scan algorithm

Tokenizer 从左到右执行：

1. 跳过连续 `str.isspace()`；
2. 遇到 `(` 或 `)`，直接发出单字符 token；
3. 遇到 `C`，读取其后 maximal ASCII `[0-9]` run，使用第 11 节 helper 验证完整 ID，并要求下一字符是 boundary 或 expression end；
4. 遇到 `A` 或 `O`，只尝试 exact uppercase `AND` 或 `OR`，并要求 token 前后均由 start/end、whitespace 或 parentheses 分隔；
5. 其它 character、partial token 或 token 后没有 boundary 时抛出 `ScreeningRuleValidationError`。

Examples：

| Expression | Tokenization result |
|---|---|
| `C001 AND C002` | valid: `C001`, `AND`, `C002` |
| `C001 AND(C002 OR C003)` | valid: `C001`, `AND`, `(`, `C002`, `OR`, `C003`, `)` |
| `C001ANDC002` | invalid: no boundary after `C001` |
| `C001OR(C002)` | invalid: no boundary after `C001` |
| `C001(C002)` | lexical tokens exist, but grammar invalid because operator is missing |

Tokenizer 不执行 automatic word splitting、longest recovery、lowercase repair、operator substitution 或 intent guessing。`and`、`or`、`NOT`、`XOR`、`&&`、`||`、quoted text、comma、semicolon 与 arbitrary identifier 全部 invalid。

## 13. Parser and Grammar Implementation

### 13.1 Frozen grammar

~~~text
rule           := or_expression
or_expression  := and_expression (OR and_expression)*
and_expression := primary (AND primary)*
primary        := criterion_id | "(" or_expression ")"
~~~

该 grammar 直接实现：

1. parentheses；
2. `AND`；
3. `OR`；

的 frozen precedence。

### 13.2 Parser strategy

使用 module-private recursive-descent parser：

- `_parse_or_expression()`；
- `_parse_and_expression()`；
- `_parse_primary()`。

Parser 维护 token index，并在解析时生成 postfix instruction tuple：

~~~text
C001 C002 C003 OR AND
~~~

同时收集 `frozenset[str]` referenced Criterion IDs。

每条 Rule 的 private parse result 是：

~~~text
(postfix_tokens, referenced_ids)
~~~

不建立 AST/node classes。当前 grammar 不需要 reusable AST；postfix tuple 足以保存 precedence 并支持确定性 evaluation。

### 13.3 Full consumption and malformed grammar

每条 Rule 必须消费全部 tokens。以下情况均抛出 `ScreeningRuleValidationError`：

- empty token stream；
- Rule 以 operator 开始或结束；
- adjacent operands 没有 operator；
- adjacent operators；
- empty parentheses；
- missing `)` 或 extra `)`；
- valid lexical tokens 形成 invalid grammar；
- parse 完成后仍有 leftover token。

Parser 不修复 expression，不做 Boolean simplification，不生成 normalized source。

## 14. Complete Validation Ordering

`evaluate_rule_set()` 必须按以下顺序执行：

1. 验证 `rule_set` public type 与 RuleSet one-or-more shape；
2. 按 collection order tokenize/parse 每条 Rule，并建立全部 private parse results；
3. 在任何 Boolean evaluation 前确认整个 RuleSet 所有 Rules 均合法；
4. 验证 `criterion_results` 是 Mapping；
5. materialize 当前 supplied entries 的 local snapshot；
6. 遍历并验证 snapshot 中每一个 key 和每一个 value；
7. 合并所有 Rules 的 referenced IDs；
8. 检查每个 referenced ID 都存在于 validated mapping；
9. 只有步骤 1–8 全部成功后，才执行 Boolean evaluation；
10. 对所有 Rule results 使用 fixed ANY 返回 bool。

Validation 使用 first-error exception，不聚合多个 diagnostics；但不得在发现一条 true path 后跳过尚未完成的 Rule syntax、mapping 或 missing-reference validation。

## 15. Complete Boolean Mapping Validation

Mapping validation 冻结为：

- 接受实现 `collections.abc.Mapping` 的 object；
- 对 supplied mapping 的全部 entries 建立一次 local snapshot；
- 每个 key 必须通过第 11 节 Criterion ID helper；
- 每个 value 必须满足 `type(value) is bool`；
- `1`、`0`、string、`None`、list、dict 或其它 truthy/falsy value 均 invalid；
- RuleSet 未引用的合法 ID→bool entries 允许存在，evaluation 忽略它们；
- mapping insertion order 不影响 valid result。

完整 mapping 验证之后，计算：

~~~text
missing_ids = all_referenced_ids - supplied_mapping_keys
~~~

非空时抛出 `ScreeningRuleInputError`。Missing 不填充 false，也不产生第三种 business result。

## 16. Deterministic Boolean Evaluation

### 16.1 One Rule

对一条已验证 Rule，使用 local bool stack 顺序执行 postfix tokens：

- Criterion ID：push corresponding actual bool；
- `AND`：pop two bools，push logical AND；
- `OR`：pop two bools，push logical OR。

已验证 postfix 必须最终只留下一个 exact bool；该值是 Rule result。

### 16.2 RuleSet

RuleSet overall result：

~~~python
any(rule_results)
~~~

- 任一 Rule true → true；
- 全部 Rules false → false；
- duplicate Rule entries 逐项保留，但不改变 fixed ANY 语义；
- collection order 不改变 result。

Rule-level 或 RuleSet-level internal short-circuit 只允许发生在第 14 节完整 validation 结束之后。初始实现可以直接执行 postfix operands，并仅在 `any()` 阶段 short-circuit；不得让 short-circuit 隐藏 invalid Rule、invalid key/value 或 missing reference。

### 16.3 Purity

Evaluator：

- 不修改 `ScreeningRule`、`ScreeningRuleSet` 或 supplied Mapping；
- 不读 time、random、network、environment、disk 或 external state；
- 不 import LLM、OCR、browser、Candidate、Run、Profile Store 或 Action modules；
- 不写 persistence、log trace 或 page Action。

## 17. Explicit Failure Contract

| Failure | Required technical result |
|---|---|
| Empty/whitespace Rule expression | `ScreeningRuleValidationError` |
| Empty RuleSet | `ScreeningRuleValidationError` |
| RuleSet/Rule wrong type | `ScreeningRuleValidationError` |
| Invalid token boundary | `ScreeningRuleValidationError` |
| Unsupported token/operator | `ScreeningRuleValidationError` |
| Malformed Criterion ID in expression | `ScreeningRuleValidationError` |
| Missing operand/operator or malformed parentheses | `ScreeningRuleValidationError` |
| Any invalid Rule in RuleSet | whole evaluation raises `ScreeningRuleValidationError` |
| criterion_results is not Mapping | `ScreeningRuleInputError` |
| Invalid supplied mapping key | `ScreeningRuleInputError` |
| Any non-bool supplied value, referenced or extra | `ScreeningRuleInputError` |
| Any referenced ID missing | `ScreeningRuleInputError` |
| Valid RuleSet and mapping, every Rule false | return `False` |
| Valid RuleSet and mapping, any Rule true | return `True` |

Failure 不返回 Boolean fallback，不把 invalid 转换为 false，不返回 partial result，也不执行 Decision/Action。

## 18. Dependency and Packaging Changes

Dependency Changes: None.

Implementation 只使用：

- `collections.abc.Mapping`；
- `dataclasses`；
- `re`；
- standard typing syntax。

不增加 parser library、runtime dependency、requirements entry、package initialization 或 PyInstaller configuration。

## 19. Targeted Test Plan

只新增 `tests/test_screening_rule_engine.py`，使用 `unittest`。

### 19.1 Public type tests

Constructor tests 只覆盖 public value shape contract，不把 constructor success 当作 lexical/grammar validity。覆盖：

- frozen `ScreeningRule(expression)`；
- frozen one-or-more `ScreeningRuleSet(tuple)`；
- empty/wrong-type rejection；
- duplicate Rules retained in tuple；
- non-empty lexical-invalid expression 可以完成 constructor shape validation；
- public dataclass fields only `expression` and `rules`；
- no ID/version/digest/mode/Profile/Run/action fields。

### 19.2 Tokenizer and parser tests through public API

Private tokenizer/parser 不建立独立 public test contract；全部 token boundary、grammar、unsupported syntax 与完整 Rule semantic validity 都通过 `evaluate_rule_set()` 覆盖：

- `C001 AND C002`；
- `C001 AND(C002 OR C003)`；
- `C001ANDC002` invalid；
- `C001OR(C002)` invalid；
- `C001(C002)` grammar invalid；
- `C001`、`C025`、`C999`、`C1000`；
- `C01`、`C000`、lowercase ID invalid；
- uppercase exact `AND` / `OR`；
- unsupported lowercase operators、`NOT`、`XOR`、`&&`、`||`、quotes、semicolon；
- empty/missing/adjacent tokens；
- balanced、unbalanced 与 empty parentheses；
- full token consumption；
- parentheses > AND > OR。

### 19.3 Boolean mapping tests

覆盖：

- full AND/OR truth tables；
- grouping and precedence；
- valid extra Boolean entries ignored；
- every non-bool representative rejected；
- invalid extra key/value rejected；
- referenced missing ID rejected even behind true OR branch；
- Rule 1 true does not hide Rule 2 missing/invalid input；
- mapping insertion order independent。

### 19.4 RuleSet and deterministic evaluation tests

覆盖：

- single-Criterion Rule；
- all-mandatory single Rule；
- fixed multi-Rule ANY true/false cases；
- Rule order independence；
- duplicate references and duplicate Rules；
- logically redundant expression；
- repeated call determinism；
- exact bool return type；
- supplied objects remain unchanged。

## 20. AC-01–AC-24 Verification Mapping

| RPD AC | Planned verification |
|---|---|
| AC-01 | `test_single_rule_and_r05_criterion_id_forms` covers C001/C025/C999/C1000 and exact lookup |
| AC-02 | `test_boolean_mapping_and_insertion_order` accepts actual bool mapping and compares reordered input |
| AC-03 | `test_and_truth_table` covers all four Boolean pairs |
| AC-04 | `test_or_truth_table` covers all four Boolean pairs |
| AC-05 | `test_parenthesized_grouping` covers `C001 AND (C002 OR C003)` |
| AC-06 | `test_and_precedence_and_parentheses_override` compares both required groupings |
| AC-07 | `test_multiple_rules_use_fixed_any` covers any-true/all-false and Rule order |
| AC-08 | `test_one_rule_represents_all_mandatory_conditions` and RuleSet shape assertions cover no mode/ANY keyword |
| AC-09 | `test_duplicate_references_rules_and_redundancy` covers preserved duplicates and no rewrite requirement |
| AC-10 | `test_not_is_rejected` covers `NOT C001` and no negative operator |
| AC-11 | `test_token_boundaries_and_unsupported_syntax` calls `evaluate_rule_set()` and covers both valid boundary examples, both concatenated invalid examples, XOR/&&/||/IDs |
| AC-12 | constructor shape tests reject empty expression；`test_malformed_and_empty_rules` uses `evaluate_rule_set()` for malformed operands/operators and parentheses |
| AC-13 | `test_empty_rule_set_is_invalid` |
| AC-14 | `test_missing_reference_is_not_false_or_short_circuited` covers true OR and earlier true Rule cases |
| AC-15 | `test_complete_mapping_rejects_non_bool_values` covers referenced and unreferenced entries plus 1/0/string/None/list/dict |
| AC-16 | `test_extra_valid_boolean_results_are_ignored` |
| AC-17 | `test_success_returns_exact_bool_only` covers true/false and absence of result wrapper |
| AC-18 | `test_evaluation_is_deterministic_and_does_not_mutate_inputs` |
| AC-19 | public signature/type-shape tests prove no criterion_text/evidence input；module dependency review confirms no LLM/Evaluation import |
| AC-20 | new-module-only file scope plus public type-shape test；`screening_profile.py` and its tests remain protected |
| AC-21 | new-module-only file scope plus absence of Candidate/Run fields/imports；existing Run/Candidate modules remain protected |
| AC-22 | public return/API shape plus absence of Decision/browser/action imports；all action modules remain protected |
| AC-23 | public dataclass field assertions prove no score/weight/priority/N-of-M/threshold/mode fields |
| AC-24 | new-module-only scope and public field assertions prove no persistence/ID/version/digest/database/GUI/Candidate-specific rule surface |

AC-19–AC-24 的 negative-scope parts 使用 module import/API shape assertions与 implementation file-scope review，不建立 repository scanner 或额外 framework。

## 21. Implementation Change Plan

### Change 1 — Local Rule Engine and targeted tests

Files：

- new `screening_rule_engine.py`；
- new `tests/test_screening_rule_engine.py`。

Implementation：

- two frozen value types；
- two `ValueError` subclasses；
- local Criterion ID helper；
- exact tokenizer boundaries；
- recursive-descent-to-postfix parser；
- complete validation ordering；
- stack Boolean evaluation；
- fixed multi-Rule ANY；
- AC-01–AC-24 targeted verification。

Preconditions：RPD v0.1 remains Frozen；TID must be Human-approved and Frozen before starting；no existing file modification is authorized。

本 TID 只有一个 implementation Change，不拆分 parser/evaluator/framework Changes。

## 22. File Scope Matrix

### 22.1 Planned New Files

| File | Purpose |
|---|---|
| `screening_rule_engine.py` | R06 value types、errors、private tokenizer/parser、Boolean evaluator |
| `tests/test_screening_rule_engine.py` | R06 AC-01–AC-24 targeted tests |

### 22.2 Planned Modified Files

None.

### 22.3 Protected / Untouched Files

以下必须 untouched：

- `screening_profile.py`；
- `screening_profile_cli.py`；
- `ocr_text.py`；
- `ocr_detector.py`；
- `ocr_candidate.py`；
- `ocr_records.py`；
- `ocr_store.py`；
- `ocr_replay.py`；
- `ocr_normalization.py`；
- `ocr_aggregation.py`；
- `ocr_similarity.py`；
- `simple_brush.py`；
- `mouse_motion.py`；
- `ai_provider_config.py`；
- `ai_provider_cli.py`；
- `llm_provider_runtime.py`；
- all existing tests, including `tests/test_screening_profile.py`、`tests/test_screening_profile_cli.py`、`tests/test_ocr_text.py` 与 `tests/test_simple_brush_ocr.py`；
- requirements files；
- `.gitignore`；
- `BossOCR.spec`；
- R05 documents；
- Frozen `docs/RPD-AM7-R06-screening-rule-engine-v2.md`。

## 23. Targeted Verification Commands

Implementation 只需执行：

~~~powershell
.\venv\Scripts\python.exe -m unittest tests.test_screening_rule_engine -v
.\venv\Scripts\python.exe -m compileall screening_rule_engine.py
~~~

并进行一次 file-scope review，确认 implementation changes 只包含第 22.1 节两个 new files。

本 TID 不要求 existing R05 tests、Legacy OCR tests、full regression、benchmark、network smoke、build、package 或 release。不得为了 evidence 重跑无关 accepted suites。

## 24. Explicit Non-Implementation

本 TID 明确不实现：

- public parser/compiler API；
- AST/node class hierarchy；
- generic expression/Rule framework；
- error code taxonomy、recovery、trace、explanation 或 partial result；
- Profile membership lookup；
- Rule/RuleSet serialization or persistence；
- Rule/RuleSet ID、version 或 digest；
- CLI、UI 或 runtime authoring；
- RuleSet selection、active/default state 或 Run binding；
- ScreeningProfile/Criterion mutation；
- Candidate/Run schema changes；
- Criterion Evaluation 或 LLM integration；
- Candidate Decision 或 Action；
- OCR/keyword/browser/mouse behavior；
- Legacy KeywordRule compatibility layer；
- dependency、packaging 或 release work。

## 25. Risks and Escalation Conditions

Implementation must stop only at the affected contract point and report Human if：

1. Frozen RPD lexical boundaries cannot be implemented without accepting concatenated tokens or adding repair；
2. R05 Criterion ID contract at the implementation baseline differs from the inspected `C([0-9]{3,})` plus positive-number rule；
3. the two-new-file design cannot work without modifying a protected Profile、Candidate、Run、OCR、browser 或 action file；
4. a dependency or generic parser framework becomes technically mandatory；
5. AC-01–AC-24 reveal a real contradiction in the Frozen RPD。

Ordinary invalid Rule/input is expected behavior，不属于 escalation。不得为理论性 future integration 扩大当前设计。

## 26. Open Issues / Contract Conflicts

### 26.1 Open Issues

None.

### 26.2 Contract Conflicts

None.

R05 private ID helper 不构成冲突：R06 使用相同 Frozen regex/positive-number contract 的最小 local helper，而不依赖完整 Profile。Legacy keyword parser 是不同输入域，保持 untouched 即可。

## 27. Human TID Review Handoff

本 TID 当前为 Version 0.1、Frozen。

它已通过 Human Review 并冻结最小技术方案：two new files、two immutable value types、one public evaluation function、two direct validation errors、handwritten tokenizer、recursive-descent-to-postfix parser、complete validation before evaluation、fixed ANY 与 AC-01–AC-24 mapping。

Constructor 只验证 public value shape；完整 lexical/grammar validity 统一由 `evaluate_rule_set()` validation phase 建立。本次 clarification 不包含代码或测试实施。
