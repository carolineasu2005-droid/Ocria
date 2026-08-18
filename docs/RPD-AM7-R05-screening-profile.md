# AM7-R05 ScreeningProfile Dynamic Screening Criteria

## 1. Document Status

| Field | Value |
|---|---|
| Product | Ocria |
| Generation | Am7 |
| Requirement | AM7-R05 — ScreeningProfile 动态筛选标准 |
| Document Type | Requirement / Product Design |
| Version | 0.2 |
| Status | Frozen |
| Prepared On | 2026-08-18（Asia/Shanghai） |
| Requirement Branch | am7-r05-screening-profile |
| Upstream Baseline | AM7-R04 model benchmark closeout / 9b0ebe9 |
| Governing Document | CODEX-CONSTITUTION.md v1.0 |

本 RPD 只定义 AM7-R05 的产品合同，回答“运行级动态筛选标准是什么、如何形成历史版本、如何与 Run 和 Candidate 对齐”。本 RPD 不规定 Python 模块、函数签名、文件路径、canonical JSON 算法或 SHA-256 实现细节；这些属于后续 TID。

本文件不授权代码实施、测试修改、commit、push、merge、tag 或 release。

## 2. Requirement Summary

AM7-R05 建立运行级 ScreeningProfile，使 Ocria 在不修改代码、不向 Candidate Schema 增加岗位专属字段的前提下，能够描述不同岗位、不同招聘轮次和不同筛选要求。

三个概念必须分离：

~~~text
ScreeningProfile
“本轮招聘想找什么样的人”

CandidateOcrDocument
“这个候选人的 OCR 证据和简历内容是什么”

Future Evaluation
CandidateOcrDocument + ScreeningProfile
→ Criterion Evaluation
→ C001=true / C002=false / ...
~~~

R05 只定义前两个输入之间的产品边界以及 ScreeningProfile 的生命周期。R05 不执行 Evaluation，也不产生 Candidate Decision。

每个正式 Profile Version 是一份不可变的筛选语义快照。每个新 Run 在进入执行态前必须绑定一份已经保存的 Profile Version，并在整个 Run 生命周期中保持该绑定不变。

## 3. Goals

AM7-R05 的目标是：

1. 定义 ScreeningProfile 与 Criterion 的最小产品数据模型。
2. 允许 Human 在 Configuration Mode 中创建、编辑和保存动态 Criteria。
3. 让 Criterion 使用统一、可理解的自然语言 Boolean 命题。
4. 为每个 Criterion 分配程序生成 ID，并保证正式版本历史中已经出现的 ID 稳定且不复用。
5. 建立 Draft → Human Save → immutable Profile Version 的线性版本生命周期。
6. 为每个正式 Version 生成能够识别 Criteria 语义内容的 criteria_digest。
7. 让同一 Run 冻结并使用唯一的一份正式 ScreeningProfile Version。
8. 通过 Run 将所有 Candidate 与同一 Profile Version 对齐。
9. 保持 CandidateOcrDocument 只描述 Candidate/OCR 自身事实。
10. 保存足够的正式版本历史，使历史 Run 可追溯到当时使用的 Criteria。
11. 明确 Configuration Mode 与 Execution Mode 的产品边界。
12. 为后续 TID 和 Evaluation Requirement 提供具体、可测试的 Acceptance Contract。

## 4. Non-Goals

AM7-R05 不负责：

- AI Prompt；
- LLM 调用；
- AI Provider 配置或 Runtime；
- Candidate 是否满足 Criterion；
- Boolean Evaluation runtime；
- Rule Engine 执行；
- AND / OR expression；
- N-of-M；
- scoring、weight 或 priority；
- condition tree 或 arbitrary Boolean expression；
- Candidate Decision；
- qualified、rejected 或 manual review；
- favorite、forward、next candidate 或其它页面 Action；
- AI Screening Runtime；
- OCR、Candidate scanning、Candidate switch 或页面行为修改；
- 向 Candidate Schema 添加岗位专属 Boolean 字段；
- Candidate-specific Profile；
- 在每个 Candidate record 中复制 Profile 或 Profile Snapshot；
- Runtime Profile Switch；
- Runtime Hot Reload；
- Run 中查看、创建、修改或删除 Profile；
- Active、Published、Archived 或 Default Profile 状态；
- Concurrent Draft、并发编辑状态机或 Profile Lock UI；
- GUI；
- Profile branching、merge 或 software semver；
- must_not_match、NOT、exclude 或独立 negative rule；
- 模型质量、Screening 质量、FP/FN 或 benchmark 评估；
- 补做、迁移或重写 AM7-R04 benchmark；
- release、deployment 或 packaging。

## 5. Product Context and Targeted Repository Findings

本节只记录 R05 直接需要的仓库事实，不构成 repository-wide audit。

### 5.1 Current Run and run.json

当前 OCR Store 为每个 Run 创建独立目录，核心文件为：

~~~text
data/ocr_runs/<timestamp>_<run_id>/
├─ run.json
├─ screens.jsonl
├─ candidates.jsonl
└─ errors.jsonl
~~~

run.json 当前由 RunManifest 表达，至少包含：

- run_id；
- started_at / ended_at；
- status；
- platform / python_version；
- data_files；
- action_mode / max_screen_count；
- normalization、aggregation、similarity 和 dynamic-end 的版本、配置与 digest；
- error/candidate/screen counts。

当前 RunStatus 为 running、completed、interrupted、error 和 disabled。RunManifest 当前没有 screening_profile_id、profile_version 或 criteria_digest。

RunManifest 已经建立“运行级配置 snapshot + digest”的命名和追溯先例。R05 不复用任何旧 OCR config/version 字段，但可以沿用“运行级冻结配置身份”的产品模式。

### 5.2 Current CandidateOcrDocument and candidates.jsonl

CandidateOcrDocument 当前是 Candidate/OCR 事实容器，包含：

- run_id；
- candidate_record_id；
- sequence_number；
- created_at / completed_at；
- capture_status；
- screens / capture_summary；
- document_text / document_segments / document_build_status；
- normalization / aggregation / similarity；
- OCR provenance versions、metadata；
- dynamic-end counts、reasons 和 prediction facts。

candidates.jsonl 每行保存一个 CandidateOcrDocument。Candidate 与 Run 的既有正式关联是 run_id；Candidate 与内嵌 screen 还通过 candidate_record_id 对齐。

R05 不改变上述字段的含义，也不把 ScreeningProfile、Criterion、岗位 Boolean 或未来 Evaluation Result 塞入 CandidateOcrDocument，包括其通用 metadata。

### 5.3 Current OCR Store relationship

当前 JsonlOcrRecordStore：

- 在 Run 开始时创建 run_id 和 RunManifest；
- 将 screen 和 candidate 记录写入同一 Run 目录；
- 校验 Candidate/Screen 与 Run 的 run_id；
- 在 close 时更新 Run status、ended_at 和 counts；
- 保持 run.json 为运行级 metadata，candidates.jsonl 为 Candidate 级事实。

因此 R05 的 Candidate/Profile 对齐无需 Candidate 新字段：

~~~text
CandidateOcrDocument.run_id
→ Run-level screening profile binding
→ Frozen ScreeningProfile Version
~~~

### 5.4 AM7-R01 through R04 boundaries

AM7-R01 冻结 Legacy OCR algorithms、CandidateOcrDocument 既有字段语义、OCR Store/Replay 语义和页面 Action 行为，同时建立 Greenfield 原则：新 AI/Screening 能力优先进入独立结构，并通过明确引用消费 Legacy Evidence。

AM7-R02 的 AIProviderConfig 是独立本地配置，不属于 OCR Store、Run Manifest、Candidate data 或 ScreeningProfile。R05 不复用或扩展该配置 Schema。

AM7-R03 的 Provider Runtime 只提供 list_models、test_connection 和 complete；它明确不定义 ScreeningProfile、Criterion、Evaluation 或 Candidate Decision。R05 不修改其 public contract。

当前 AM7-R04 baseline 是离线 model benchmark closeout：

- 从既有 candidates.jsonl 读取 Candidate text；
- 将 benchmark 结果写入独立 benchmark JSONL/summary；
- 没有修改 CandidateOcrDocument 或 OCR Store；
- benchmark prompt 使用 C01–C04 和固定 criteria_version，仅属于该 benchmark session。

R05 的 C001、C002... 是新的 ScreeningProfile Criterion identity，不迁移、不重解释 R04 benchmark 的 C01–C04，也不把 R04 固定 prompt 当作 R05 Profile persistence contract。

### 5.5 Existing OCR R05 naming

仓库中已存在旧 BossOCR OCR Pipeline 命名：

- document_version = r05-document-v1；
- aggregation_config_version = r05-config-v1；
- versions["aggregation"] = r05-v1。

它们表示 OCR 多屏聚合和 Candidate document pipeline，不表示 AM7-R05 ScreeningProfile。

AM7-R05 必须只使用独立名称：

- screening_profile_id；
- profile_version；
- criteria；
- criteria_digest；
- created_at。

## 6. Core Concepts

### 6.1 ScreeningProfile

ScreeningProfile 表示一个稳定的招聘筛选主题及其线性版本历史。

screening_profile_id 回答：

> 这是哪一个 ScreeningProfile？

同一 screening_profile_id 下可以存在 v1、v2、v3...。不同 screening_profile_id 的 Criterion ID 空间与版本历史彼此独立。

R05 不增加 Profile name、description、active、default、published 或 archived 字段。

### 6.2 Criterion

Criterion 是一条自然语言命题，回答：

> Candidate 是否满足 criterion_text 所描述的命题？

每条 Criterion 具有：

- 稳定 criterion_id；
- 可编辑的 criterion_text；
- v1 固定 rule = must_match。

Criterion 不携带 score、weight、priority、expression 或 action。

### 6.3 Draft

Draft 是某个 ScreeningProfile 当前可编辑的工作状态。

Draft：

- 可以新增、删除和修改 Criterion；
- 可以调整 Criteria 的呈现顺序；
- 不是正式 Profile Version；
- 没有可供 Run 绑定的正式 profile_version；
- 没有权威 criteria_digest；
- 不会因为每次编辑而增加 Version；
- 在同一 Profile lineage 中最多存在一个当前 Draft。

Draft 只存在于 Configuration Mode。进入 Execution Mode 后不能创建或修改 Draft，也不能通过 Save 产生新 Profile Version。

Criterion ID 的持久不复用范围只覆盖正式历史 Version 中已经出现过的 ID。当前 Draft 内的 ID 必须唯一；从未进入任何正式 Version、且已随纯临时 Draft 被放弃的 ID，不要求跨进程永久保留。

### 6.4 Profile Version

Profile Version 是 Human 明确 Save 后形成的 immutable ScreeningProfile snapshot。

profile_version：

- 从整数 1 开始；
- 每次成功保存下一个正式版本时恰好增加 1；
- 不使用 1.2.3 等 semver；
- 不 branch、不 merge；
- 不能原地覆盖。

### 6.5 criteria_digest

criteria_digest 是正式 Profile Version 的 Criteria 语义内容身份。

它用于证明：

- 某个 Profile Version 的 Criteria 内容没有被原地改变；
- 某个 Run 绑定的 id/version 确实对应当时的 Criteria 内容；
- 两个 canonical Criteria 内容相同的 snapshot 能得到相同 digest。

### 6.6 Frozen Run Binding

Frozen Run Binding 是 Run 开始时持久化的最小三元组：

~~~text
screening_profile_id
profile_version
criteria_digest
~~~

该三元组在 Run 生命周期中 immutable。

### 6.7 Frozen Run Snapshot

Run-level metadata 可以进一步保存该正式 Version 的完整 Frozen ScreeningProfile Snapshot：

~~~text
screening_profile_id
profile_version
criteria
criteria_digest
created_at
~~~

Snapshot 若保存，只能属于 Run-level metadata，且必须与三元组一致。它不得复制到每个 Candidate record。

## 7. Data Model / Product Contract

### 7.1 Formal ScreeningProfile Version

正式 Version 的最小产品形态：

~~~json
{
  "screening_profile_id": "sp_abc123",
  "profile_version": 1,
  "criteria": [
    {
      "criterion_id": "C001",
      "criterion_text": "具有 SLG 游戏项目经验",
      "rule": "must_match"
    },
    {
      "criterion_id": "C002",
      "criterion_text": "具有完整上线游戏项目经验",
      "rule": "must_match"
    },
    {
      "criterion_id": "C003",
      "criterion_text": "实际承担过主美或同等级美术负责人职责",
      "rule": "must_match"
    },
    {
      "criterion_id": "C004",
      "criterion_text": "具有团队管理经验",
      "rule": "must_match"
    }
  ],
  "criteria_digest": "sha256:...",
  "created_at": "2026-08-17T10:00:00+08:00"
}
~~~

### 7.2 ScreeningProfile fields

| Field | Product meaning | Formal Version constraint |
|---|---|---|
| screening_profile_id | Profile lineage 的稳定、不透明 identity |非空字符串；同一 lineage 所有版本相同；不同 Profile 不得碰撞；具体生成算法由 TID 决定 |
| profile_version |该 lineage 的正式历史版本 |正整数；首次为 1；后续成功 Save 为 previous + 1 |
| criteria |该 Version 冻结的 Criterion collection |至少一项；criterion_id 在该 Version 内唯一；列表顺序不表示 priority 或 Boolean expression |
| criteria_digest | Criteria 语义内容的 SHA-256 identity |正式 Version 必填；与 criteria 的 canonical 内容一致 |
| created_at |该正式 Version 成功创建的时间 | timezone-aware ISO 8601；保存后 immutable |

screening_profile_id 的 sp_abc123 只是可读示例。RPD 冻结的是稳定、不透明、唯一的 identity；随机数、UUID 或其它具体生成方式由 TID 选择。

### 7.3 Criterion fields

| Field | Product meaning | Constraint |
|---|---|---|
| criterion_id | Profile lineage 内稳定的 Criterion identity |系统生成；C001、C002...；当前 Draft 与同一正式 Version 内唯一；正式历史中出现后跨版本稳定且删除后不复用 |
| criterion_text |待判断的自然语言命题 |非空字符串；Human 可在 Draft 修改；正式 Version 中 immutable |
| rule | v1 的匹配规则标记 |精确固定为 must_match |

字段名统一为 criterion_text。不得增加 criteria_text、description、prompt、condition 等同义字段。

### 7.4 Collection order

Criteria 的列表顺序可以用于一致展示，但不是：

- priority；
- score；
- evaluation order；
- AND / OR；
- action order。

Criterion identity 由 criterion_id 决定。相同 Criterion triplets 的 canonical 内容必须产生相同 digest；具体 canonical ordering 和 serialization 由 TID 冻结。

### 7.5 No additional v1 business fields

R05 v1 不在 Profile 或 Criterion 中增加：

- profile name / description；
- active/default/published/archived status；
- Criterion weight/priority/category；
- expression/operator；
- created_by/updated_by；
- Candidate fields；
- Provider/model/prompt fields；
- Evaluation result。

如果后续业务确实需要这些字段，必须由后续 Requirement 单独设计。

## 8. Criterion Semantics

### 8.1 Unified Boolean meaning

所有 Criterion 统一解释为：

> 如果 Candidate 满足 criterion_text 描述的命题，则该 Criterion = true；否则 = false。

示例：

~~~text
C001：具有团队管理经验

有明确团队管理证据
→ true

没有明确证据
→ false
~~~

“证据不足=false”属于后续 Evaluation contract；R05 只冻结 Criterion 的命题方向，不执行证据分析。

### 8.2 Negative business conditions

负向业务条件直接写成自然语言命题：

~~~text
C002：没有棋牌游戏项目经历

没有棋牌经历
→ true

存在棋牌经历
→ false
~~~

这仍然是 must_match：Candidate 必须满足“没有棋牌游戏项目经历”这条自然语言命题。

R05 不设计 must_not_match、NOT、exclude、negative rule 或双重否定机制。

### 8.3 No expression language

每个 Criterion 独立表达一条命题。R05 不定义：

- 多 Criterion 的 AND / OR；
- 嵌套条件；
- N-of-M；
- 总分；
- 权重；
- 优先级；
- 通过/淘汰规则。

未来 Evaluation 可以针对每个 criterion_id 产生 Boolean，但如何组合这些 Boolean 不属于 R05。

### 8.4 criterion_text editing

Human 可以在 Draft 中修改 criterion_text，且 criterion_id 保持不变。

例如：

~~~text
v3 / C003
具有团队管理经验

Draft 修改
具有至少 5 人团队管理经验

Human Save
v4 / C003
具有至少 5 人团队管理经验
~~~

这表示同一 Criterion identity 的语义演化，而不是创建新 Criterion。

## 9. Criterion ID Lifecycle

### 9.1 Generation

Criterion ID 由程序自动生成。编号从 C001 开始：

~~~text
C001
C002
C003
...
C999
C1000
...
~~~

数字部分至少三位，不设置人为 999 上限。

### 9.2 Scope and stability

Criterion ID 的正式 identity 作用域是一个 screening_profile_id 的完整正式版本历史。

规则：

1. 当前 Draft 和同一正式 Version 内不得重复。
2. 同一 Profile 的历史版本中，同一 Criterion 保持相同 ID。
3. 修改 criterion_text 不改变 ID。
4. 已进入正式历史 Version 的 Criterion 删除后，该 ID 永久不复用。
5. 新增 Criterion 使用基于正式历史和当前 Draft 可确定的下一个编号。
6. 从未进入任何正式 Version、且已随纯临时 Draft 被放弃的 ID，允许以后重新使用。
7. 不同 Profile 可以各自拥有 C001，因为它们由 screening_profile_id 区分。

### 9.3 Deletion and addition

示例：

~~~text
v1
C001
C002
C003
C004

Draft 删除 C002
Human Save → v2
C001
C003
C004

Draft 新增
Human Save → v3
C001
C003
C004
C005
~~~

C002 不得复用。即使后来新增与 C002 原文本相同的命题，也必须获得新的 Criterion ID。

### 9.4 Temporary Draft IDs

纯临时 Draft ID 不需要永久烧号。

例如正式历史最高为 C004：

~~~text
Draft 临时创建 C005
→ 未 Save
→ 删除并放弃 Draft

以后再次新增
→ 允许使用 C005
~~~

因为该 C005 从未进入正式 Version，它不是正式历史 identity。相反，只要 C005 曾出现在任一正式 Version，之后即使删除也不得再用于新的 Criterion。

新增 ID 只需根据正式历史和当前 Draft 确定。R05 不要求 allocation ledger、tombstone system、general ID framework 或 Draft ID durability mechanism。

## 10. Profile Lifecycle

### 10.1 New Profile

创建新 Profile 的生命周期：

~~~text
Create Profile
→ assign screening_profile_id
→ Draft
→ add/edit/delete Criteria
→ Human Save
→ profile_version = 1
~~~

空 Draft 允许存在，但不能保存为空的正式 Version。

### 10.2 Editing an existing Profile

一个 Profile 的正式历史是单线性的：

~~~text
v1
→ Draft based on v1
→ Human Save
→ v2
→ Draft based on v2
→ Human Save
→ v3
~~~

修改已有 ScreeningProfile 时，新的 Draft 必须基于该 Profile 当前最新的正式 Version。若当前最新正式 Version 是 v3，下一次可编辑 Draft 必须基于 v3。

历史 v1、v2 仍然可持久化、可追溯、immutable，并可由 screening_profile_id + profile_version 定位，但不能作为新的编辑分支起点。

R05 v1 不从历史旧 Version 建立修改分支，不允许跳过当前最新正式 Version 派生后续 Version，也不同时维护多个 Draft；不提供 Profile branching、merge、rollback、restore 或 history branch selector。

### 10.3 Draft behavior

Draft 中允许：

- 新增 Criterion；
- 删除 Criterion；
- 修改 criterion_text；
- 调整展示顺序；
- 继续编辑而不增加 version。

Draft 不是 Run 可选对象。只有正式保存后的 Version 才能绑定 Run。

### 10.4 Human Save

Human Save 是产生正式 Version 的唯一动作。

Save 成功必须同时形成：

- 准确的 screening_profile_id；
- 下一个 profile_version；
- 完整、有效且 immutable 的 criteria；
- 对应 criteria_digest；
- created_at。

Save 完成后该 Draft 关闭，并形成下一个正式 Version。没有新的 Draft 编辑时，重复调用 Save 不得凭空制造重复 Version。

### 10.5 Version immutability

正式保存后的 Version：

- 不能修改；
- 不能覆盖；
- 不能补写 Criterion；
- 不能改变 criterion_text；
- 不能改变 rule；
- 不能改变 criteria_digest；
- 不能改变 created_at。

所有后续变化必须通过新 Draft 和下一个 Version。

### 10.6 Run binding eligibility

Run 开始前必须绑定一份有效、已经保存的正式 ScreeningProfile Version。

正式历史 Version 必须：

- 可持久化；
- 可追溯；
- immutable；
- 可由 screening_profile_id + profile_version 唯一定位。

R05 v1 不强制 CLI/UI 提供任意历史 Version 浏览器或选择器。具体绑定入口由后续 TID 采用最简单实现决定，但不得引入 Active、Default、Published 或其它 Profile 状态。

## 11. criteria_digest Product Contract

### 11.1 Covered semantic content

每个正式 Version 必须生成 criteria_digest。digest 只覆盖每条 Criterion 的：

- criterion_id；
- criterion_text；
- rule。

digest 不覆盖：

- screening_profile_id；
- profile_version；
- created_at；
- Draft metadata；
- Run identity；
- Profile storage path。

### 11.2 Required change behavior

以下任何变化都必须改变 criteria_digest：

- 任一 criterion_text 改变；
- 新增 Criterion；
- 删除 Criterion；
- 任一 rule 改变。

R05 v1 虽然 rule 固定为 must_match，rule 仍属于 digest 覆盖内容。

### 11.3 Determinism

相同 canonical Criterion triplets 必须得到相同 criteria_digest，与以下因素无关：

- 保存时间；
- profile_version；
- Profile ID；
- Draft 中编辑操作的先后历史；
- 存储文件位置。

列表展示顺序不具有优先级语义；canonical serialization 如何处理 ordering 由 TID 明确冻结。

### 11.4 Algorithm boundary

算法固定使用 SHA-256。具体：

- canonical serialization；
- Unicode 表示；
- whitespace 保留或规范化；
- key ordering；
- list ordering；
- digest 字符串前缀与 hex 表示；

均由 TID 决定。TID 必须满足本节产品语义，不得扩大为通用 integrity framework。

## 12. Run Freeze Lifecycle

### 12.1 Pre-run sequence

一个 R05 profile-bound Run 的正式顺序：

~~~text
CONFIGURATION MODE
→ Create/Edit Draft
→ Human Save formal Version
→ bind a valid saved Profile Version
→ validate bound Version and digest
→ persist Run-level binding
→ Start Run
→ EXECUTION MODE
~~~

没有已保存、有效且可读取的 Profile Version，不得进入 R05 Execution Mode。

### 12.2 Required Run-level binding

Run 开始前必须在 Run-level metadata 持久化至少：

~~~text
screening_profile_id
profile_version
criteria_digest
~~~

该绑定必须在浏览器自动化、OCR 和 Candidate processing 开始前成功形成。

Run-level metadata 写入失败、待绑定 Version 不存在或 digest 不匹配时，不得把该次执行声明为已绑定 R05 Profile 的 Run，也不得进入 R05 Execution Mode。

这是一项 R05 新增的前置产品合同。它不授权改变 OCR algorithms、Candidate scanning 或页面 Action 规则。

### 12.3 Optional full snapshot

为增强历史可追溯，Run-level metadata 可以保存完整 Frozen ScreeningProfile Snapshot。

如果保存 Snapshot：

- Snapshot 必须等于所选正式 Version；
- Snapshot 的 id/version/digest 必须与最小三元组一致；
- Snapshot 在 Run 生命周期中 immutable；
- Snapshot 不得逐 Candidate 复制；
- Snapshot 不得使用旧 OCR config snapshot 字段名。

最低验收要求仍是三元组；是否默认保存完整 Snapshot由后续 TID 在该边界内选择。

### 12.4 One Run, one Version

同一 Run：

- 只有一个 screening_profile_id；
- 只有一个 profile_version；
- 只有一个 criteria_digest；
- 所有 Candidate 通过相同 run_id 对齐到该绑定；
- 不允许 Candidate-specific Profile；
- 不允许运行中切换 Version；
- 不允许修改被冻结的 Version；
- 不允许 Hot Reload。

不同 Run 可以绑定：

- 同一 Profile 的同一 Version；
- 同一 Profile 的不同 Version；
- 不同 Profile。

### 12.5 No Profile changes during Execution

Run 开始并进入 Execution Mode 后：

- 不允许创建 Draft；
- 不允许修改 Profile；
- 不允许新增或删除 Criterion；
- 不允许 Save；
- 不允许产生新 Profile Version；
- 不允许切换 Profile 或 Version；
- 不存在 Profile 操作入口。

Profile Version 的变化只发生在 Run 与 Run 之间：当前 Run terminally stopped、产品重新进入 Configuration Mode、Human 完成 Draft 编辑并 Save 后，才可能产生下一 Version。

整个 Execution lifecycle 中，原 Run binding、已处理 Candidate 与未处理 Candidate 都保持同一 Frozen Profile Version。

## 13. Run Stop, Pause, Crash, and Resume

### 13.1 Terminally Stopped transition

R05 只消费 Run lifecycle 的“当前 Execution 是否仍可继续”语义，不创建新的 stop_reason 或 Stop Condition。

~~~text
Active / Paused / Resumable Run
→ 不允许配置 ScreeningProfile

Terminally Stopped Run
→ 可以重新进入 Configuration Mode
~~~

Terminally Stopped 可以包括：

- completed；
- Human Explicitly Abort / End；
- error stop；
- candidate_switch_failed stop；
- 其它已经明确终止当前 Run、不会继续该 Execution lifecycle 的 stop result。

Run-level frozen binding 在 Run 终止后仍保留，不能因回到 Configuration Mode 而修改。

### 13.2 Pause

Pause 只是同一 Run 的暂时停顿：

- run_id 不变；
- Profile binding 不变；
- 不出现 Profile 操作入口；
- 继续时恢复原 Run。

Pause ≠ End。

### 13.3 Crash

Crash 本身不授权重新选择 Profile：

- 若产品未来支持恢复原 Run，必须使用原 run_id 和原 Profile binding；
- 不得以 crash 为由把同一 Run 绑定到另一 Version；
- 不得在原 Run 尚未被 Run lifecycle 明确归为 terminally stopped 时，把编辑结果应用到原 Run。

Crash ≠ End。

如果 interrupted/crashed Run 仍被定义为 resumable，它仍保持 Frozen Profile，不能进入 Profile Configuration。只有现有或未来 Run lifecycle 已明确把它归为 terminally stopped 时，下一次才可进入 Configuration Mode。

### 13.4 Resume

Resume 原 Run 必须：

- 读取原 Run-level screening_profile_id；
- 读取原 profile_version；
- 读取原 criteria_digest；
- 若存在 Frozen Snapshot，继续使用同一 Snapshot；
- 不得重新选择或重新绑定 Profile Version；
- 不得重新创建 Version。

Resume ≠ New Run。

### 13.5 Current repository limitation

当前仓库具备进程内 Pause/Continue，但没有 R05 所需的通用 crash resume 产品入口。本 Requirement 不实现通用 Run Resume；本节只冻结任何现有或未来 Resume path 必须遵守的 Profile binding 语义。

## 14. Candidate Schema Boundary

### 14.1 Separation of responsibilities

ScreeningProfile 负责：

> 要判断什么。

CandidateOcrDocument 负责：

> Candidate 的 OCR 证据和简历内容是什么。

Future Evaluation 负责：

> Candidate 是否满足每个 Criterion，以及之后如何处理。

三者不得混合。

### 14.2 Forbidden Candidate fields

禁止在 CandidateOcrDocument、candidates.jsonl 或 Candidate metadata 中加入岗位专属字段，例如：

~~~json
{
  "has_slg_experience": true,
  "has_team_management": false,
  "has_main_artist_experience": true
}
~~~

同样禁止把以下内容逐 Candidate 复制：

- 完整 ScreeningProfile；
- criteria list；
- Frozen Profile Snapshot；
- Profile Version 的 criterion_text；
- 岗位专属 Boolean 占位字段。

### 14.3 Run-based alignment

Candidate 与 Profile 的唯一 R05 对齐路径：

~~~text
CandidateOcrDocument.run_id
→ Run-level Profile binding
→ screening_profile_id + profile_version + criteria_digest
~~~

Candidate 不需要重复 screening_profile_id、profile_version 或 criteria_digest。

### 14.4 Future Evaluation boundary

后续 Evaluation Result 可以引用：

- run_id；
- candidate_record_id；
- screening_profile_id；
- profile_version；
- criteria_digest；
- criterion_id。

但其 Schema、Boolean 输出、Prompt、Provider 调用、错误语义和 Decision 都不属于 R05。本 RPD 不创建 Evaluation sidecar 或结果对象。

## 15. Persistence and Historical Traceability Requirements

### 15.1 Profile persistence boundary

ScreeningProfile 使用独立的本地持久化边界。它不属于：

- AIProviderConfig；
- CandidateOcrDocument；
- candidates.jsonl；
- OCR aggregation/similarity config；
- Provider Runtime result；
- benchmark output。

具体目录、文件划分、class、atomic write 和 reader API 由 TID 冻结。

### 15.2 Required durable information

持久化必须保留：

- 每个 screening_profile_id；
- 每个正式 profile_version；
- 每个 Version 的完整 criteria；
- criteria_digest；
- created_at；
- 正式版本历史中已经出现过的 Criterion ID 信息；
- Run-level frozen binding。

R05 不要求纯临时 Draft ID 跨进程持久化或永久烧号。如果最小实现自然保存 Draft 工作状态，该持久化仍不使 Draft 成为正式 Version，也不建立独立 allocation ledger。

### 15.3 Historical immutability

正式 Version 一旦保存：

- 必须可在程序重启后读取；
- 不得原地覆盖；
- 不得被后续 Draft 修改；
- 不得因创建新 Version 而删除；
- 不得因某个 Run 结束而删除；
- 必须能由 screening_profile_id + profile_version 唯一定位；
- stored criteria 重新计算的 digest 必须与 stored criteria_digest 一致。

R05 v1 不提供删除正式 Profile Version 的产品操作。

### 15.4 Save outcome

Human Save 的产品结果必须是二选一：

- 完整的新正式 Version 成功可读；
- 没有新正式 Version，既有历史保持不变，Draft 仍可继续处理。

不得出现：

- profile_version 已增加但 criteria 不完整；
- Version 可见但 digest 缺失；
- 旧 Version 被部分覆盖；
- 同一 id/version 对应两份不同内容。

这只是产品可观察结果，不要求 journal、database transaction、backup rotation、checksum gate 或额外 persistence framework。

### 15.5 Run traceability

对于任一 R05 新 Run：

- run_id 必须唯一指向一份 frozen binding；
- binding 必须能定位正式 Profile Version；
- stored Version 的 digest 必须与 Run binding 一致；
- 若存在 Run Snapshot，它也必须与同一 digest 一致；
- Run terminally stopped 后产生的后续 Version 不改变历史 Run。

### 15.6 Legacy data

R05 之前创建的 run.json 没有 Profile binding，仍应按原 Schema 和 OCR provenance 读取。它们是 legacy unbound runs，不因缺少 R05 字段而被改写或自动 backfill。

Legacy run 不得被伪装为已经绑定 ScreeningProfile 的 R05 Run。

## 16. Configuration Mode vs Execution Mode

### 16.1 Configuration Mode

Configuration Mode 可以提供：

- Create Profile；
- 从当前最新正式 Profile Version 形成或继续 Draft；
- 新增/删除 Criterion；
- 修改 criterion_text；
- Human Save；
- 为下一 Run 准备一份有效、已保存的正式 Version binding；
- Start Run。

R05 定义这些产品动作，不规定 GUI，也不强制历史 Version selector。后续 TID 可以使用符合当前 Ocria 入口风格的最小交互。

### 16.2 Transition to Execution Mode

只有在以下条件全部满足时才能进入 Execution Mode：

1. 已准备绑定一份正式 Version；
2. Version 内容可读取；
3. Criteria 合法；
4. criteria_digest 与内容一致；
5. Run-level binding 已成功持久化。

进入后 Profile configuration surface 从产品流程中消失。

### 16.3 Execution Mode

Execution Mode 不存在以下入口：

- 查看 ScreeningProfile；
- 创建或删除 Profile；
- 创建 Draft；
- 编辑 Draft；
- 新增/删除 Criterion；
- 修改 criterion_text；
- Save Version；
- 切换 Profile/Version；
- 重新配置 Profile。

这不是按钮置灰或只读详情页，而是 Execution Mode 根本没有 ScreeningProfile 操作界面。

### 16.4 Return to Configuration Mode

只有 Run 已经 terminally stopped，产品才允许重新进入 Configuration Mode。

新的 Draft、Version 或 Profile binding 只会在 terminal stop 后的 Configuration Mode 中形成，并只影响下一 Run。

逻辑生命周期：

~~~text
CONFIGURATION MODE
├─ Create/Edit Draft
├─ Save Version
├─ Bind valid saved Version
└─ Start Run
       ↓
EXECUTION MODE
├─ Frozen Profile binding
├─ Browser Automation
├─ OCR / Candidate Processing
└─ Terminal Stop Result
       ↓
CONFIGURATION MODE
~~~

是否在同一进程中自动返回菜单属于 TID/implementation detail；产品约束是原 Run 必须先 terminally stop。

## 17. Failure / Invalid State Product Behavior

| Scenario | Product behavior |
|---|---|
| Draft 没有 Criterion | Draft 可以继续编辑；Human Save 不产生正式 Version |
| criterion_text 为空或只有空白 | Draft 可修正；Human Save 不产生正式 Version |
| criterion_id 缺失、格式无效或同 Version 重复 | Human Save 不产生正式 Version；不得自动猜测替换正式 ID |
| rule 不是 must_match | Human Save 不产生正式 Version |
| Profile Version save 失败 | 不增加 profile_version；不破坏既有版本；Draft 保持可处理 |
| criteria_digest 生成或持久化失败 | 不产生正式 Version |
| stored criteria 与 stored digest 不一致 | 该 Version 不可用于新 Run；不静默重写历史 Version |
| 待绑定 Profile Version 不存在或不可读取 | 不得进入 R05 Execution Mode |
| Run-level binding 持久化失败 | 不得声明 Run 已绑定 Profile；不得进入 R05 Execution Mode |
| Execution Mode 请求创建/修改 Draft、Save 或产生新 Version | 产品流程中没有该入口；不执行操作，也不产生新 Version |
| Active / Paused / Resumable Run | 同一 Run、同一 binding；不可配置 Profile |
| Crash，但 Run 仍可能 resume | 保持 Frozen Profile；Crash 本身不解锁 Configuration Mode |
| Resume | 同一 run_id、同一 binding；不重新选择或绑定 |
| Run 已 terminally stopped | 允许下一次进入 Configuration Mode；不改变已结束 Run 的 binding |
| Legacy run 缺少 binding | 继续按 legacy run 读取；不得自动 backfill 或伪装为 R05 Run |

错误处理只需提供明确、可理解的失败结果。R05 不要求额外 Gate、Guard、Scanner、Wrapper、Validator、Safety Layer 或 Stop Condition framework。

## 18. Compatibility / Existing Ocria Boundary

### 18.1 R01 Legacy Freeze

R05 不改变：

- OCR normalization、aggregation、similarity 或 dynamic-end algorithms；
- CandidateOcrDocument 既有字段含义；
- screens.jsonl / candidates.jsonl 的 Candidate/OCR 事实语义；
- Candidate switch、favorite、forward 或页面动作；
- OCR threshold、retry、scroll 或 timing。

R05 是 Greenfield Profile model 加最小 Run-level integration。它明确授权新 R05 Run 增加 profile binding，但不授权其它 Legacy schema/behavior 变化。

### 18.2 Run metadata compatibility

当前 RunManifest 没有 R05 Profile 字段。后续 TID 必须在以下产品边界内选择最小的 schema evolution：

- 新 R05 Run 可表达最小三元组；
- 旧 run.json 继续可读；
- 旧 OCR version/config/digest 字段含义不变；
- exact storage schema version、field placement 和 reader behavior 由 TID 冻结；
- 不得通过 Candidate 字段绕过 Run-level binding。

这不是与 R01 的合同冲突：R01 允许后续专项 Requirement 明确授权受控新增结构；本 RPD 的授权只限 ScreeningProfile 的 Run-level binding。

### 18.3 R02 AI Provider configuration

Profile criteria 不含 API Key、Provider、Base URL 或 Model。R02 当前 Active Provider Configuration 不包含 Profile ID 或 Criterion。

Run-level Profile binding 与 Provider verification 是两个独立产品概念。

### 18.4 R03 Provider Runtime

R05 不调用 list_models、test_connection 或 complete，也不修改 Runtime request/result/error contract。

后续 Evaluation Requirement 可以组合 Candidate evidence、Frozen Profile 与 R03 complete()，但必须另行设计。

### 18.5 R04 benchmark

R04 benchmark 的：

- C01–C04；
- 固定 SYSTEM_PROMPT；
- prompt_version；
- criteria_version；
- benchmark result；

均保持 benchmark-specific。R05 不重写历史 benchmark，也不把 benchmark result 迁入 Profile Store。

未来如需使用 ScreeningProfile 重做 benchmark，必须由单独 Requirement/TID 授权。

### 18.6 OCR R05 name collision

旧 OCR：

~~~text
r05-document-v1
r05-config-v1
r05-v1
~~~

AM7-R05：

~~~text
screening_profile_id
profile_version
criteria_digest
criterion_id
~~~

两者完全独立。不得复用、比较或相互推导版本号。

## 19. Invariants

以下为 AM7-R05 硬性不变量：

1. 岗位专属筛选条件只能存在于 ScreeningProfile。
2. 不向 Candidate Schema 或 Candidate metadata 写入岗位专属字段。
3. Criterion 是一条自然语言命题。
4. Candidate 满足 criterion_text 描述的命题时，该 Criterion 的未来 Boolean Evaluation = true。
5. AM7-R05 v1 的 rule 固定为 must_match。
6. 不提供 must_not_match、NOT、exclude 或其它独立负向 rule。
7. 负向业务条件必须直接写成自然语言命题，并沿用相同 true/false 语义。
8. Criterion ID 由程序自动生成，从 C001 开始，并基于正式历史与当前 Draft 确定下一个编号。
9. Criterion ID 在同一 ScreeningProfile 的历史版本之间保持稳定。
10. 修改 criterion_text 不改变 criterion_id。
11. 正式历史 Version 中已经出现过、之后被删除的 Criterion ID 永不复用。
12. 同一 Profile 的新增 Criterion 使用基于正式历史与当前 Draft 可确定的下一个编号；从未进入正式 Version且已被放弃的纯临时 Draft ID允许重新使用。
13. Draft 编辑不产生正式 Version。
14. Human Save 是产生正式 Version 的唯一动作。
15. 首次成功 Save 产生 profile_version = 1。
16. 后续成功 Save 产生 previous profile_version + 1。
17. profile_version 是单调递增整数，不使用 semver。
18. 正式 Version immutable，禁止原地覆盖。
19. 后续修改必须以当前最新正式 Version 为 Draft 基线并产生下一 Version；历史旧 Version 不能作为编辑分支起点。
20. 每个正式 Version 必须有 criteria_digest。
21. criteria_digest 只覆盖 criterion_id、criterion_text 和 rule 的 canonical 内容。
22. Criterion 文本、Criterion 增删或 rule 变化必须改变 criteria_digest。
23. Run Start 前必须绑定一个已保存、有效的 Profile Version。
24. 同一 Run 只能使用唯一的 Frozen ScreeningProfile Version。
25. Run binding 至少包含 screening_profile_id、profile_version 和 criteria_digest。
26. Execution Mode 不存在 ScreeningProfile 操作入口，也不能产生 Draft 或新 Profile Version。
27. Active、Paused 或 Resumable Run 不允许配置 Profile；只有 Terminally Stopped Run 才能重新进入 Configuration Mode。
28. Pause、Crash 本身和 Resume 不改变原 Frozen Profile binding；Crash 本身不自动解锁 Profile 配置。
29. Resume 原 Run 必须继续使用原 Frozen Profile Version。
30. Candidate 与 Profile 只能通过 Run 对齐。
31. Profile Snapshot 若保存，必须属于 Run-level metadata。
32. 完整 Profile 或 Snapshot 不得复制进每个 Candidate record。
33. R05 不执行 Candidate Screening Evaluation。
34. R05 不产生 Candidate Decision 或页面 Action。
35. 旧 OCR r05-* provenance 与 AM7-R05 Profile 版本体系完全独立。
36. Legacy run 缺少 Profile binding 时保持 legacy unbound，不自动 backfill。

## 20. Acceptance Criteria

以下 Acceptance Criteria 可由后续 TID 映射为自动测试、数据 fixture 或 targeted manual verification。

- **AC-01 — Formal Profile model**：可以保存一份包含 screening_profile_id、正整数 profile_version、至少一个 Criterion、criteria_digest 和 timezone-aware created_at 的正式 Profile Version。
- **AC-02 — Criterion model**：每个正式 Criterion 只需 criterion_id、非空 criterion_text 和 rule=must_match；字段名使用 criterion_text。
- **AC-03 — Boolean semantics**：正向与负向自然语言 Criterion 都遵循“满足命题=true，不满足=false”；不存在独立 negative rule。
- **AC-04 — No expression language**：R05 数据模型不包含 must_not_match、NOT、AND/OR、N-of-M、score、weight、priority 或 condition tree。
- **AC-05 — Criterion ID allocation**：新 Profile 从 C001 自动分配；当前 Draft 与同一 Version 内唯一；修改正式 Criterion 文本保持 ID；正式历史中出现后删除也不复用；从未进入正式 Version且已放弃的纯临时 Draft ID允许重新使用。
- **AC-06 — Profile identity and versions**：同一 screening_profile_id 下首次 Save 为 v1，后续成功 Save 恰好递增到 v2、v3；不同 Profile 具有独立历史。
- **AC-07 — Draft lifecycle**：Draft 可新增、删除和编辑 Criteria；编辑操作不产生 Version；没有 Human Save 的 Draft 不能被 Run 选择。
- **AC-08 — Version immutability and edit base**：保存后的 Version 不可原地修改；修改已有 Profile 时 Draft 必须基于当前最新正式 Version并生成下一 Version，历史旧 Version 不能作为编辑分支起点，旧 Version 的字段与语义保持不变。
- **AC-09 — Digest contract**：正式 Version 必须有 criteria_digest；任一 criterion_id、criterion_text、Criterion membership 或 rule 变化会改变 digest；screening_profile_id、profile_version 和 created_at 不属于 digest 输入。
- **AC-10 — Persistence outcome**：程序重启后仍可读取正式版本历史以及其中出现过的 Criterion ID；Save 失败不会产生部分新 Version或破坏既有历史；不要求纯临时 Draft ID永久烧号。
- **AC-11 — Valid formal binding**：Run 前必须绑定已保存且 digest 有效的正式 Profile Version；R05 不强制任意历史 Version selector，也不存在 Active/Default Profile 自动选择。
- **AC-12 — Run freeze**：Run 进入 Execution Mode 前已持久化 screening_profile_id、profile_version 和 criteria_digest；其中任何一项缺失或不一致时不进入 R05 Execution Mode。
- **AC-13 — One Run, one Profile**：同一 run_id 的所有 Candidate 始终对齐同一 Profile Version；Execution Mode 不能创建 Draft、Save 或产生新 Version，Version 变化只发生在 Run 与 Run 之间。
- **AC-14 — Snapshot placement**：若实现完整 Frozen Snapshot，它只出现在 Run-level metadata，且与 binding 一致；每个 Candidate record 不包含 Snapshot。
- **AC-15 — Candidate schema isolation**：CandidateOcrDocument 和 candidates.jsonl 不新增岗位专属 Boolean、Criterion text、criteria list 或直接 Profile identity；既有 run_id 完成关联。
- **AC-16 — Mode separation**：Configuration Mode 提供 Profile 编辑、Save 和有效 Version binding；Execution Mode 完全没有查看、创建 Draft、编辑、Save、删除、产生新 Version或切换 Profile 的入口。
- **AC-17 — Terminal stop and resume semantics**：Active、Paused 或 Resumable Run 不解冻 Profile；Crash 本身不自动允许配置；Resume 原 Run 复用原 binding；任何已明确 terminally stopped 的 Run 都允许下一次进入 Configuration Mode。
- **AC-18 — Failure behavior**：invalid Draft、digest mismatch、missing Version 或 Run binding 写入失败均不会产生错误的正式 Version或错误启动一个 R05-bound Run。
- **AC-19 — Compatibility**：旧 run.json 和 Candidate/OCR records 继续按原合同读取；旧 OCR r05-* 与 R04 benchmark C01–C04 不被当作 R05 Profile identity。
- **AC-20 — Scope isolation**：R05 不调用 LLM、不执行 Criterion Evaluation、不产生 Candidate Decision，也不触发 favorite、forward、next candidate 或其它页面 Action。

## 21. Known Limitations / Explicit Deferrals

R05 v1 明确接受以下限制：

- Criterion 只有 must_match；
- 没有 criterion category、priority、weight 或 score；
- 没有 AND/OR 或结果组合；
- 没有 Profile name/description；
- 没有 Active/Default/Published/Archived 状态；
- 没有正式 Version 删除；
- 没有 Profile branching/merge；
- 没有 Concurrent Draft；
- 没有 Draft allocation ledger、tombstone system 或 Draft ID durability mechanism；
- 没有 Execution Mode Profile viewer；
- 没有任意历史 Version selector 的强制 UI 合同；
- 没有 Runtime switch/hot reload；
- 没有 Candidate-specific Profile；
- 没有 Evaluation Result Schema；
- 没有 Prompt 或 AI Runtime integration；
- 没有 Candidate Decision 或 Action；
- 没有通用 crash resume 实现；
- 没有 GUI；
- exact persistence path、Python API、atomic write mechanism、schema version 和 canonical digest serialization 留给 TID；
- 完整 Run Snapshot 是否默认持久化留给 TID，但最小三元组不可省略。

这些是显式 deferral，不构成 Draft 未完成项。

## 22. Open Issues / Contract Conflicts

### 22.1 Open Issues

None.

### 22.2 Contract Conflicts

None.

Targeted inspection 发现的当前实现缺口——RunManifest 尚无 Profile binding、当前产品没有通用 crash resume 入口——均属于 R05/TID 需要处理或明确延期的实现事实，不与本 RPD 冻结产品语义冲突。

R01 对 Legacy Schema/Orchestration 的保护也不构成冲突：AM7-R05 是专项 Requirement，只授权新增独立 ScreeningProfile persistence 与最小 Run-level binding；Candidate/OCR 既有字段语义、算法和页面 Action 仍保持冻结。

## 23. Final Product Conclusion

AM7-R05 建立一条简单、线性、可追溯的产品链：

~~~text
Natural-language Criteria
→ Draft
→ Human Save
→ Immutable Profile Version
→ criteria_digest
→ Run-level Freeze
→ All Candidates aligned by run_id
~~~

ScreeningProfile 定义“要判断什么”；CandidateOcrDocument 保留“Candidate 的证据是什么”；后续 Requirement 才负责“如何判断以及判断后做什么”。

R05 v1 不把岗位条件写死到 Candidate Schema，不在运行中提供 Profile 控制面板，不引入复杂 Rule Engine 或 Profile 状态机，也不触发任何 AI 或页面动作。

本 RPD 当前为 Version 0.2、Frozen。不得据此自行开始代码实施。
