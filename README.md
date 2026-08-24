# Ocria Am7

Ocria Am7 是一个面向 Windows 的 BOSS 候选人审核工具。它在已登录的 Chrome 或 Edge 窗口中执行可见界面自动化，使用本地 RapidOCR 对候选人详情执行有界 Complete Scan，把聚合的 OCR 文本交给配置的 AI Provider 逐项判断筛选条件，再由确定性的 Screening Rule 决定候选人是否合格；合格后才进入 Human 预先选择的收藏或转发路径。

Ocria 的当前原则是：

> OCR 负责看见，AI 负责理解，规则负责判断，程序负责动作。

AI **不会**点击收藏或转发，也不直接决定执行哪种动作。AI 只为每个 Criterion 返回严格的 Boolean；Rule Engine 把成功结果确定性合成为业务资格，程序再形成 `qualified`、`rejected` 或 `ai_failed` Decision；只有 `qualified` 才能进入所选动作路径。

本文描述当前 Am7 source 的实际行为。核对基线为分支 `am7-r14-final-integration-acceptance`、提交 `855f7125ebc7b1e62d5a35232892a7d29e28a258`。Am7 的产品能力在 R13 后已经 Feature Complete；本文不承诺未来功能，也不代表已经发布了当前基线的 Windows 安装包。

## 目录

- [先看安全边界](#先看安全边界)
- [产品流程](#产品流程)
- [运行要求](#运行要求)
- [安装与启动](#安装与启动)
- [安全的首次运行](#安全的首次运行)
- [启动菜单](#启动菜单)
- [AI Provider 配置](#ai-provider-配置)
- [ScreeningProfile 与 Criteria](#screeningprofile-与-criteria)
- [Screening Rules](#screening-rules)
- [校准](#校准)
- [最近没看过与批次流程](#最近没看过与批次流程)
- [OCR、Dynamic End 与候选人切换](#ocrdynamic-end-与候选人切换)
- [Decision、动作与 AI 失败](#decision动作与-ai-失败)
- [暂停、停止与运行时间](#暂停停止与运行时间)
- [输出与数据文件](#输出与数据文件)
- [完整 CLI 参考](#完整-cli-参考)
- [故障排查](#故障排查)
- [当前限制](#当前限制)
- [Ocria 与 BossOCR Legacy](#ocria-与-bossocr-legacy)
- [开发者参考](#开发者参考)

## 先看安全边界

Ocria 会移动鼠标、点击 BOSS 页面，并可能执行真实收藏或邮件转发。开始前请确认当前账号、页面、筛选条件、校准区域、ScreeningProfile、Rule 和动作模式都正确。

- `--no-forward` 只禁止 **真实邮件转发**；它不会把 `forward` 改成 `favorite`，也不会禁止 `favorite` 模式的真实收藏。
- 当前没有覆盖所有动作的通用 dry-run。首次验证应选择 `forward` 并启用 `--no-forward`，不要选择 `favorite`。
- 即使启用 `--no-forward`，程序仍会点击筛选、候选人卡片、滚动和切换候选人；它不是无交互预览模式。
- Legacy 关键词提示只保留在 Advanced/manual 与非交互兼容路径；R15 正常 Preset 路径不会提示或解析它。当前 Am7 的最终动作授权不读取 Legacy 关键词结果；留空关键词 **不能**作为禁止动作的安全措施。
- OCR 正文会发送给选定的第三方 AI Provider。运行目录还会保留 OCR 原文和框坐标，可能包含候选人个人信息。请按组织的数据、招聘和隐私规则使用并保护这些文件。
- `config/ai_provider.json` 中的 API Key 是本地明文。配置界面会遮蔽显示，但文件本身没有加密；不要提交、分享或截图传播它。

## 产品流程

一次候选人处理按以下边界执行：

```text
BOSS 可见页面
  → Detail Load 检查
  → Complete Scan（本地 RapidOCR，多屏）
  → CandidateOcrDocument
  → 最多 3 次有界 AI attempt
      └─ 内部 AICandidateInput（candidate_record_id + document_text）
         → Provider Prompt（Criteria + resume_text，不含 candidate_record_id）
         → 严格 Boolean contract（或 classified technical failure）
  → 最终 AI outcome 持久化
  → completed 时由 ScreeningRuleSet 求值；failed 时直接映射 ai_failed
  → CandidateDecision 持久化
  → qualified 时执行 favorite 或 forward
  → Candidate Switch Verification
  → 下一位候选人
```

关键责任分界：

| 层 | 做什么 | 不做什么 |
| --- | --- | --- |
| OCR | 从可见屏幕读取并聚合简历文字 | 不判断招聘条件，不抓取 DOM |
| AI | 独立判断每个 Criterion 是否有充分简历证据 | 不解释 Rule 表达式，不执行动作 |
| Rule Engine | 对 Criterion Boolean 执行 `AND` / `OR` 组合 | 不调用 Provider，不重新理解简历 |
| 程序 | 记录 Decision，并按已选模式控制点击 | 不把 `rejected` 与技术失败混为一类 |

## 运行要求

### 系统和 Python

- Windows 10/11 x64。运行时代码直接依赖 Win32 API，其他操作系统不是当前支持目标。
- Python 3.10 或更高版本；Python 3.11 x64 是仓库脚本给出的首选环境。`setup.bat` 只检查 `python` 是否在 `PATH`，不会主动验证版本或 64 位架构。
- 主显示器需要能正常截屏；坐标、分辨率和 DPI 信息均以主显示器为基准。

### 浏览器和 BOSS 页面

仅支持下列顶层进程：

1. `chrome.exe`（优先）
2. `msedge.exe`（Chrome 不可用时回退）

窗口标题还必须包含区分大小写的 `BOSS`，或不区分大小写的 `zhipin`。程序会尝试恢复最小化窗口并置前，但不会验证 URL、登录状态或页面 DOM，也不会持续强制窗口保持前台。

如果有多个匹配窗口，程序直接选择找到的第一个 Chrome；没有匹配 Chrome 时才选择第一个 Edge，不会按 URL、Tab 或账号消歧。运行前请关闭其他匹配的 BOSS 窗口，或确保唯一匹配的 Chrome 就是目标账号/页面。

运行期间应保持：

- 已登录并打开正确的 BOSS 候选人列表/详情页面；
- 浏览器窗口可见、无遮挡；
- 窗口位置、大小、页面缩放、显示缩放和分辨率与校准时一致；
- 不要让通知、远程桌面缩放或其他窗口覆盖 OCR 与点击区域。

### 依赖

`requirements.txt` 包含 Windows 自动化、OpenAI-compatible Client 和基础图像依赖；`requirements-ocr.txt` 包含 RapidOCR 与 ONNX Runtime；本地打包另使用 `requirements-build.txt` 中的 PyInstaller 6。

## 安装与启动

在仓库根目录打开 PowerShell 或 Command Prompt。

### 推荐：仓库初始化脚本

```bat
.\setup.bat
```

脚本会创建 `venv`，并安装 `requirements.txt` 与 `requirements-ocr.txt`。随后可启动交互菜单：

```bat
.\start.bat
```

`start.bat` 能正确启动 `simple_brush.py`，但它打印的“三步开始”说明仍是 Legacy 文案；实际启动流程以本文和程序显示的 R15 七项菜单为准。

### 手动安装

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr.txt
.\venv\Scripts\python.exe simple_brush.py
```

请始终从项目根目录启动。配置、日志、Profile 和 Run 数据使用相对当前工作目录的路径。

### 已构建可执行文件

如果维护者已用当前 source 本地构建 one-dir 版本，入口是：

```powershell
.\dist\Ocria\Ocria.exe
```

Python 与可执行文件使用相同参数，例如：

```powershell
.\venv\Scripts\python.exe simple_brush.py --no-forward
.\dist\Ocria\Ocria.exe --no-forward
```

仓库当前的自动打包脚本有已知 smoke 命令不兼容，不能据此断言现有 `release`/`dist` 文件是本基线的已验证发布物；详情见[构建](#构建)。

## 安全的首次运行

以下流程会禁止真实邮件转发，但仍会操作 BOSS 页面。请使用你有权操作的测试环境，并全程观察。

1. 先打开 Chrome 或 Edge，登录 BOSS，进入正确的候选人页面，并固定窗口位置、大小和缩放。
2. 从项目根目录运行：

   ```powershell
   .\venv\Scripts\python.exe simple_brush.py --no-forward
   ```

   `--no-forward` 本身不会跳过启动菜单。
3. 在菜单选择 `4`，配置并保存 AI Provider。可做非推理 Connection Test，但不要把它当成实际模型推理保证。
4. 在菜单选择 `3` 创建 ScreeningPreset：选择或新建一个精确的 ScreeningProfile Version，选择 ALL、ANY 或 Custom 正式 Rule，并在预览后 Human Save。Preset 只保存名称、精确 Profile Version 和 Rule；不保存 API Key、校准、邮件或 Legacy 关键词。
5. 如需复用点击区域，返回主菜单选择 `5` 创建完整 Calibration Profile；根据屏幕提示手动切换列表页、详情页、转发弹窗和筛选面板。校准流程只框选，不会点击确认转发。
6. 选择 `2` 并选中刚保存的 Preset，设置动作、时长、`no_forward` 和批次筛选开关。检查 UUID-free Run Summary 后选择 Confirm。首次成功 Confirm 后，`1. Quick Start` 才可使用。
7. 动作模式选择 `forward` 并保持 `--no-forward` 生效。**不要选择 `favorite`**，因为 `--no-forward` 不抑制收藏。
8. Summary Confirm 后才进入既有邮件/校准准备；正常 Preset 路径不再提示 Legacy 关键词。选择已有 Calibration Profile，或完成本次手动点击区域校准。
9. 程序打开首位候选人详情后，按提示手动框选 OCR 正文区域。该区域不会保存在 Calibration Profile 中，每次进程都需要重新选择。
10. 观察 `logs/simple_brush.log`、Run 目录和 `decisions.jsonl`。确认 Decision、翻页与筛选行为正确后按 `Esc` 安全停止。

可复用 Profile 的非交互示例：

```powershell
.\venv\Scripts\python.exe simple_brush.py `
  --auto `
  --screening-profile-id sp_0123456789abcdef0123456789abcdef `
  --screening-rule "C001 AND C002" `
  --action-mode forward `
  --no-forward `
  --calibration-profile office-1080p `
  --duration-seconds 600
```

这仍不是 headless 运行：启动后仍需打开正确的 BOSS 页面，并手动框选 OCR 正文区域。

## 启动菜单

无非交互触发参数时，实际菜单是：

```text
1. Quick Start
2. Choose ScreeningPreset and Run
3. ScreeningPreset Management
4. AI Provider Configuration
5. Calibration
6. Advanced
0. 退出
```

- `1`：只使用最近一次 Confirm 的 Preset 和五项 Run settings。它重新验证精确 Profile Version、Rule 和当前 Provider，显示 Summary 后仍要求 Confirm；没有状态、状态损坏或引用失效时不会回退到其他 Preset、latest Profile 或 Legacy Run。
- `2`：按临时编号或名称选择已保存的 ScreeningPreset，设置 Action、duration、`no_forward` 和 batch filter 后显示 Summary。Edit 会丢弃旧的 resolved value 并重新解析；Cancel 不会启动 Run 或写入 last-used state。
- `3`：列出、创建、编辑、删除或查看 ScreeningPreset。Human Save 前不会写入 Preset。编辑 Criteria 必须基于当前 latest Profile，并需要明确重新绑定和保存 Preset。
- `4`：编辑、保存、刷新或测试本地 AI Provider 配置，之后回到菜单。
- `5`：创建或覆盖一个包含全部 11 个点击区域的 Calibration Profile，完成或取消后回到菜单。
- `6`：进入 Advanced：保留 Existing manual Am7 Run（Legacy Profile Prepare/Rule/关键词兼容路径）以及 Advanced ScreeningProfile Management。
- `0`：退出，不启动 Run。

Preset 保存在 `data/screening_presets.json`。该 JSON 只有 `presets` 和 `last_used_run_settings` 两个顶层键；Preset 绑定精确 Profile ID + Version，而不是 latest。last-used 只在 Summary Confirm 后、进入 Run 前写入；写入失败只会警告，已经确认的 Run 仍可继续。

Run Summary 只显示 Preset 名、Profile Version、Criteria、Rule、Provider/Model、动作、转发抑制、批次开关和时长；不显示 Profile UUID、API Key、校准、邮件、Legacy 关键词或候选人数据。Summary/Resolver 不读取或选择 Calibration；Confirm 后才进入既有 Calibration 流程。

只有 `--auto`、非空 `--keywords` 或非空 `--calibration-profile` 会跳过该菜单。仅传 `--screening-profile-id`、`--screening-rule`、`--action-mode`、`--duration-seconds` 或安全开关仍会进入交互菜单。R15 没有 `--screening-preset` 参数。

## AI Provider 配置

### 支持的 Provider

当前配置界面和运行时只支持两个 Provider：

| Provider 固定值 | Base URL 说明 |
| --- | --- |
| `aliyun-bailian` | 使用阿里云百炼/OpenAI-compatible endpoint；URL 取决于账号区域、Workspace 和套餐 |
| `deepseek` | 界面建议 `https://api.deepseek.com` |

每份可运行配置必须同时有四个非空字段：

- Provider；
- Base URL（绝对 `http://` 或 `https://` URL）；
- API Key，例如 `YOUR_API_KEY`；
- Model，即 Provider 实际接受的模型标识符。

配置保存在 `config/ai_provider.json`。API Key 在配置菜单中通过隐藏输入读取、在状态输出中遮蔽，但磁盘文件仍是明文。请依赖文件权限和本地密钥管理，不要把该文件提交到版本库。

### 配置步骤

在主菜单选择 `3. AI Provider Configuration`。子菜单支持：

1. 显示当前暂存状态；
2. 选择 `aliyun-bailian` 或 `deepseek`；
3. 修改 API Key；
4. 修改 Base URL；
5. 通过网络列出模型；
6. 从最近一次模型列表选择；
7. 手工输入模型标识符；
8. 保存；
9. Test Connection；
10. 从磁盘刷新状态；
0. 返回启动菜单。

修改 Provider、API Key 或 Base URL 会使旧的 Connection Verification 失效；只修改 Model 不会。模型列表不可用时仍可手工输入 Model。部分百炼 endpoint 对模型列表接口返回 `404`/`405` 时会被视为“该验证能力不可用”，程序不会转而发起一次推理。

### “配置有效”与“连接已验证”不是同一件事

配置加载状态可能是 `not_configured`、`incomplete`、`invalid`、`unsupported_version` 或 `valid`。`valid` 只表示 schema 和四个运行字段完整，不表示：

- 凭据已通过服务端认证；
- Base URL 可达；
- 手工写入的 Provider 名称一定受 runtime 支持（配置 schema 可接受其他合法 kebab-case 名称，但 runtime 只接受上表两项）；
- 配置的 Model 存在或有权限；
- 一次真实 Completion 一定成功。

Test Connection 会先保存整个 staged 配置（包括 Model），再调用 Provider 的非推理模型列表能力；网络检查本身只使用 Provider、API Key 和 Base URL。它不发送候选人简历，也不验证已配置 Model 的推理结果。Run 要求配置状态为 `valid`，但不要求 Verification 为 `verified`。

Connection Verification 的状态是 `unverified`、`verified` 或 `failed`。模型列表请求成功时，即使列表为空，也会尝试写回 `verified`；多数规范化远端故障会尝试写回 `failed`。百炼模型列表 `404`/`405` 的 `capability_unavailable` 不写回失败状态；测试期间 Provider/API Key/Base URL 已被其他进程修改时，旧结果也不会覆盖新 Connection（Model 不属于该并发写回比较 tuple）。

每个正式 AI attempt **至多**发起一次非流式 Completion：候选人输入构建失败时不会到达 Provider。客户端超时为 120 秒、SDK 自动重试为 0；Am7 自己负责候选人级的最多 3 次正式 attempt。当前没有自动 Provider fallback 或自动 Model fallback。

## ScreeningProfile 与 Criteria

ScreeningProfile 定义“AI 要分别判断哪些事实”。Screening Rule 则定义“这些事实如何组合成录用动作资格”。二者不要混用。

### Criterion 语义与 ID

每个 Criterion 包含：

- `criterion_id`：固定格式 `C` 加至少三位 ASCII 数字，数值必须大于 0，例如 `C001`、`C012`、`C1000`；
- `criterion_text`：本地验证要求非空；Human 应把它写成可独立判断、语义明确的自然语言条件；
- `rule`：Profile 内固定为 `must_match`，它不是 Screening Rule 表达式。

`game_ui_5y` 之类业务名称不是合法 Criterion ID。Configuration CLI 会自动分配 ID。一个可用的合成示例是：

```text
C001: 候选人是否具有不少于 5 年的游戏 UI 工作经验
C002: 候选人简历是否明确展示移动端游戏项目经验
C003: 候选人是否具有团队管理经验
```

Prompt 要求 AI 逐项独立判断。只有简历中有充分证据时才返回 `true`；缺失、模糊、证据不足、需要外部知识或猜测时必须返回 `false`。

### 创建、保存与选择

从 `3. ScreeningPreset Management` 创建或编辑 Preset 时，可以选择已保存的精确 Profile Version，或创建一个新的 Draft；日常运行不要求输入 Profile UUID。Advanced 子菜单的 `Advanced ScreeningProfile Management` 仍保留原有 Configuration CLI，可用于维护 Draft/Version 和 Legacy manual Run 的当前进程 Prepare 状态。

1. 列出 Profile ID 和最新 Version；
2. 创建新 Draft；
3. 按 ID 从现有最新 Version 创建编辑 Draft；
4. 添加 Criterion；
5. 编辑 `criterion_text`；
6. 删除 Criterion；
7. 查看当前 Draft；
8. Human Save；
9. 按 ID Prepare 给下一次 Run；
0. 返回。

新 Profile ID 形如 `sp_0123456789abcdef0123456789abcdef`。保存位置是：

```text
data/screening_profiles/<screening_profile_id>/versions/<N>.json
```

已保存的 `ScreeningProfileVersion` 是不可变快照，并带有 Criteria digest：

- Configuration CLI 同一时间只允许一个 create/edit Draft 处于进行中，正式 Save 至少需要一个 Criterion；
- 第一次有内容的 Human Save 创建 v1；
- 编辑现有 Profile 总是从最新 Version 建 Draft；
- 有实际内容变化时创建下一个 Version；
- 没有内容变化时不创建新 Version；
- 删除过的历史 Criterion ID 不会被重新分配。

R15 Preset 始终绑定保存时明确选择的精确 Profile ID + Version；新 Profile Version 不会自动替换任何 Preset binding。Quick Start/Choose-Preset 在 Summary 前再次加载该精确 Version，绝不以 latest 替代。Advanced Prepare 仍只对当前进程的 Existing manual Am7 Run 生效；非交互运行改用 `--screening-profile-id`。

## Screening Rules

AI 不解析 Rule。它只返回每个 Criterion 的 Boolean；Rule Engine 随后用纯 Boolean 运算确定最终资格。

### 语法

当前语法只接受：

- 合法 Criterion ID，例如 `C001`；
- 大写 `AND`；
- 大写 `OR`；
- 圆括号 `(`、`)`。

不支持 `NOT`、小写 `and/or`、比较运算、分数、权重或任意业务变量。`AND` 优先级高于 `OR`，括号可显式改变顺序。

合法示例：

```text
C001
C001 AND C002
C001 OR C003
(C001 AND C002) OR C003
C001 AND (C002 OR C003)
```

规则中的 ID 必须能在本次 Profile 返回的 Criterion Boolean 中找到。R15 Preset 的 Create/Save 和 Summary resolution 会以完整的 `false` Criterion Mapping 执行 R06 验证；错误不会被修复或替代。Advanced/manual 与非交互路径保留既有 Run-bound RuleSet 行为；无论哪条路径，Rule 错误都不是业务 `rejected`。

### 多条 Rule 的固定 ANY 语义

一次 Run 必须有一条或多条 Rule。交互模式逐行输入，空行结束；非交互模式重复使用 `--screening-rule`。多条 Rule 的外层组合固定为 ANY，即任意一条为 `true` 就通过：

```powershell
--screening-rule "C001 AND C002" `
--screening-rule "C003"
```

上例等价于 `(C001 AND C002) OR C003`。没有可切换的 ALL 模式。

### Run-bound authority

Run 开始前创建一个不可变 `ScreeningRuleSet` 对象；该 Run 内所有候选人都使用同一个对象。当前没有 `rule_set_id`、`rule_set_version`、`rule_set_digest`，RuleSet 也不会写入 `run.json` 或独立持久化。若需要审计本次表达式，应在运行前另行安全记录启动命令或人工配置；不要从现有 JSONL 推断 Rule 原文已经保存。

## 校准

Ocria 是像素坐标自动化工具。校准决定程序在哪些矩形内随机选点点击；OCR 正文区域则决定截取屏幕的哪一部分。

### Calibration Profile：可复用的 11 个点击区域

主菜单选项 `5. Calibration`（也可独立运行 `python calibration_template.py`）会引导创建完整模板：

| 阶段 | 字段 | 用途 |
| --- | --- | --- |
| 候选人基础 | `first_candidate` | 打开列表中的首位候选人 |
| 候选人基础 | `focus_restore_region` | 点击详情页安全空白区，恢复键盘焦点 |
| 候选人基础 | `favorite_button_region` | 执行收藏动作 |
| 转发弹窗 | `forward_icon` | 打开“转发牛人”入口 |
| 转发弹窗 | `email_tab` | 进入邮件转发 Tab |
| 转发弹窗 | `recent_email` | 选择最近联系邮箱 |
| 转发弹窗 | `input_box` | 检查或输入邮箱 |
| 转发弹窗 | `forward_button` | 确认转发 |
| 筛选面板 | `open_filter` | 打开筛选面板 |
| 筛选面板 | `unseen_filter` | 选择“最近没看过” |
| 筛选面板 | `confirm_filter` | 确认筛选 |

流程需要 Human 按提示在列表页、详情页、转发弹窗和筛选面板之间手工切换。每个步骤开始前有倒计时；校准只框选区域，不会替你应用筛选或点击最终转发。按 `Esc` 会取消当前校准并且不保存不完整模板。

模板保存在：

```text
calibration_profiles/<经过安全化处理的模板名>.json
```

同名模板只有在 Human 确认后才覆盖。文件保存 11 个区域以及 OS、主屏幕宽高和 DPI。交互选择时，环境不匹配会让 Human 选择继续、重新选择或回到手动流程；`--calibration-profile` 的非交互加载在缺失、损坏或环境不匹配时直接失败关闭。

### OCR 正文区域不会写入模板

Calibration Profile **不包含**候选人详情正文的 OCR 截图区域。每个新进程在首位详情页稳定后仍会要求 Human 手动框选正文；成功后会覆盖写入 `logs/ocr_calibration_preview.png` 供目视确认。因此 `--auto` 只是跳过启动输入和点击区域交互的一部分，不是 headless/unattended 模式。

### 不使用模板时

- `favorite`：首位详情打开后校准焦点恢复区域和收藏按钮区域。
- `forward` 且未使用 `--no-forward`：可选择是否校准完整的五个转发区域（同时包含焦点恢复校准）；拒绝时使用代码中的 Legacy 默认区域。
- “最近没看过”：可选择校准四个列表/筛选区域；若拒绝或使用 `--no-batch-filter`，改走固定首位候选人点击点流程。
- 所有模式：仍需手工框选 OCR 正文区域。

### 何时必须重新校准

模板的环境匹配只能比较 OS、主屏幕尺寸和 DPI，无法识别浏览器位置、窗口大小、页面缩放、BOSS 布局、遮挡或按钮移动。发生下列任一变化时应重新校准：

- 浏览器窗口移动、改变大小或从另一个显示器切回；
- Windows 显示缩放、分辨率或 DPI 改变；
- 浏览器 zoom 改变；
- BOSS 页面布局、侧栏、弹窗或按钮位置变化；
- OCR preview 截到错误区域、点击出现偏移或候选人切换不稳定。

## “最近没看过”与批次流程

启用经过校准的批次筛选时，程序在每批开始按固定顺序点击：

```text
打开筛选面板 → “最近没看过” → 确认筛选 → 首位候选人
```

这些点击是自动的，但区域选择、页面准备和环境正确性由 Human 负责。四个必要区域是 `open_filter`、`unseen_filter`、`confirm_filter` 和 `first_candidate`。

每批最多处理 100 位候选人：

- 第 100 位会正常完成 OCR、AI、Decision 和可能的动作；程序不会在她/他之后再尝试一次 Right Arrow 切换。
- 一批完成后执行硬刷新，等待页面恢复，并把程序维护的连续转发计数重置为 0。
- 批次筛选可用时，刷新后重新应用“最近没看过”并打开首位候选人。
- 使用 `--no-batch-filter` 或未校准筛选时，启动前会要求把鼠标移到首位候选人卡片；倒计时后记录这个固定点击点，刷新后继续使用同一点。
- 当前没有语义化“候选人列表已到底”检测；批次模型只知道 100 人边界、停止信号和错误状态。

首位详情加载失败时，只有启用完整批次筛选区域的 Run 才能做一次有界硬恢复：刷新、重新应用筛选、重新打开首位候选人并重试。固定点流程没有这项恢复能力，失败后会安全停止。

## OCR、Dynamic End 与候选人切换

### 给使用者的简单解释

Ocria 不读取网页 DOM。它用 MSS 截取 Human 选定的可见矩形，在本机用 RapidOCR 识别文字，然后滚动详情页并继续读取。识别结果经规范化、同屏重复处理和跨屏聚合后，形成一个 `CandidateOcrDocument`。内部 `AICandidateInput` 保留 `candidate_record_id` 与 `document_text`，用于本地 identity/persistence；实际发给 Provider 的消息是固定 system instructions，以及包含 `criteria`（ID 与原文）和 `resume_text` 的 user JSON。Provider 不会收到 candidate record ID、截图、框坐标或浏览器 DOM。

OCR 的默认最低置信度是 `0.85`。低置信度 raw box 可以留在原始证据中，但不会进入派生的规范化正文。OCR 质量受字体、缩放、遮挡、动画、页面加载和选区影响；“有文字被识别”不等于“简历被完整正确理解”。

### Detail Load gate

首位详情页必须先通过内容门槛：零 OCR box 一定失败，其他结果还需满足实现中的 box/text 可读门槛。正式行为是首次检查加最多 3 次重试，即最多 4 次检查；重试间隔为 1.5 秒。

若检查耗尽：

- 批次筛选恢复可用时，可以进行一次硬刷新/重开恢复；
- 否则记录 `load_failed` 并安全停止；
- 不会在“详情是否已经加载”无法确认时继续对下一位做动作。

### Complete Scan 与 Dynamic End

每位候选人最多有 8 个 formal scan slot。每屏 OCR 证据会先写入 Run storage，再提交到候选人聚合状态。生产配置使用完整 Dynamic End，可在以下边界结束：

- `scroll_bottom`：保守的同位置确认判定已经到底；
- `no_new_text`：连续两次健康扫描没有有效新增文字；
- `max_screen_limit`：用完最多 8 屏。

这些有界结束会形成 Python `CaptureStatus.COMPLETED_WITH_LIMIT`（JSON 中为 `"completed_with_limit"`）候选人，仍可进入 AI；JSON status 为 `"aborted"` 或 `"interrupted"` 的候选人不进入 AI。位置/指纹证据缺失或不确定时不会乐观宣称到底。相同位置可能触发一次有界焦点恢复和额外滚动确认。

`CandidateOcrDocument` 汇总屏幕证据、按阅读顺序规范化的文字、去重/相似性结果、document segments 和最终 `document_text`。原始 OCR 证据仍单独持久化，聚合不会覆写 raw text/box。

### Candidate Switch Verification

程序不会把一次 Right Arrow 按键等同于“已切换”。完成当前候选人后，它保存全部正式旧指纹和一个切换前基线，然后：

- 最多执行 2 次 Right Arrow action；
- 每次 action 最多观察 6 次；
- 新详情必须通过 Detail Load，并连续两次观察到稳定的同一新指纹；
- 新指纹必须不同于所有旧候选人参考指纹；
- 第一个完整观察预算仍稳定停在旧候选人时，最多做一次焦点恢复；
- 成功确认的观察会复用为下一位的第一次 scan，避免重复截图。

无法确认、只能得到不确定比较或缺少可信指纹时，程序记录 `candidate_switch_failed` 并安全停止。它不会在候选人身份可能仍旧相同时继续 AI 或动作。

## Decision、动作与 AI 失败

### 严格 AI 输出

Provider 必须只返回一个 JSON 对象，顶层只能有 `criteria_results`。每项只能包含准确的 `criterion_id` 与真正的 JSON Boolean `passed`。所有 Profile Criterion 必须各出现一次；缺失、重复、未知 ID、额外字段、字符串 Boolean、理由、Markdown 或其他文本都会被视为 response-contract 技术失败。

### 三种 Decision status

| `decision_status` | 含义 | 动作 |
| --- | --- | --- |
| `qualified` | AI 成功返回全部 Criterion Boolean，且 Run-bound RuleSet 求值为 `true` | 进入当前 `favorite` 或 `forward` 路径 |
| `rejected` | AI 技术处理成功，但 RuleSet 求值为 `false` | 零动作 |
| `ai_failed` | 最多 3 次正式 AI attempt 后仍是已分类的候选人输入、Provider runtime 或响应 contract 技术失败 | 零动作 |

`rejected` 不是 AI 故障；`ai_failed` 也不是业务不合格。Decision 表示动作授权结果，不是实际点击成功收据。

### 最多 3 次 attempt，总计而非“3 次重试”

对一位可进入 AI 的候选人，Am7 最多执行 **3 次正式 AI attempt 总计**。可接受的失败阶段包括：

- `candidate_input`：聚合正文无法构成有效 AI 输入；
- `provider_runtime`：认证、网络、限流、服务、timeout 或模型错误；
- `response_contract`：返回内容不符合严格 Boolean JSON contract。

attempt 之间没有人为 delay、backoff 或 jitter，也不会切换 Provider、Model、Profile、Candidate input 或 Prompt。每个被分类为上述三种 accepted technical failure 的 attempt 先写入 `ai_errors.jsonl`。任一 attempt 成功即停止尝试，并写最终 AI outcome；三次全部属于这些失败则写最终 failed outcome 和 `ai_failed` Decision。未被该边界接受的 Prompt/Provider/validator/programming 异常会直接成为 Run 级错误，不会自动重试、写成 attempt error 或降级为 `ai_failed`。

若候选人级技术失败的必要持久化全部成功，程序不会执行动作，并继续下一位。若 `ai_errors.jsonl`、`ai_results.jsonl` 或 `decisions.jsonl` 的必要初始化/追加写入失败，则属于 Run 级持久化完整性故障：后续候选人和动作停止，Run 以错误状态关闭。不要把这两种路径都简写成“AI 失败后继续”。

### 动作模式

当前只有两个动作模式：

#### `favorite`

`qualified` 后点击校准的 `favorite_button_region`。`--no-forward` 对该模式没有影响，因此这不是安全预览模式。

#### `forward`

`qualified` 后依次打开转发入口、邮件转发 Tab、选择最近联系邮箱、检查输入框并点击确认转发。如果最近联系没有有效邮箱且配置了备选邮箱，程序会输入备选邮箱；没有可用邮箱则关闭弹窗并跳过本次发送。

程序计数的连续转发上限为 5：点击确认按钮并完成等待后计数加一，但没有服务端送达确认。达到上限后，后续 qualified 候选人的转发会被跳过，直到出现 `rejected`/`ai_failed` 或批次刷新将计数归零。

启用 `--no-forward` 时，`qualified` Decision 仍照常持久化，但真实邮件转发函数不会被调用。它不会改走收藏，也不会影响筛选、OCR、AI、Rule 或候选人切换。

动作函数的返回结果当前不会改变已写入的 `qualified` Decision，也没有 `action_results.jsonl`。按钮偏移、邮箱缺失、连续上限、点击失败，或 Decision 写入后收到停止请求，都可能导致“Decision qualified，但物理动作未完成”；请结合日志核查。

## 暂停、停止与运行时间

键盘控制只在 live Run 启动监听后生效：

- `Space`：在暂停/继续间切换；
- `Esc`：请求正常安全停止；
- 主菜单的独立模板生成器中，`Esc` 会取消模板流程并且不保存不完整模板；
- live Run 的 OCR、焦点恢复、转发和批次筛选 overlay 中，global listener 会把 `Esc` 交给校准窗口。取消批次/焦点/转发区域会分别回退到固定点或默认区域并继续；取消必需的 OCR 校准会结束本次 Run 准备。收藏按钮校准没有相同的 listener guard：取消后不会盲点收藏按钮并结束准备，而键盘 `Esc` 还可能同时请求停止 Run。因此校准期间应把 `Esc` 视为“取消当前步骤，且本次 Run 可能结束”，完成后检查日志/状态；
- 程序为关闭转发或筛选弹窗而发送的内部 `Esc` 会被忽略，不会停止 Run。

暂停是协作式的，不是硬锁：程序会在安全等待和 AI attempt 边界检查暂停，但无法中途取消已经发出的 Provider HTTP 请求，也不保证立刻冻结正在执行的 GUI 步骤。暂停期间 Run duration 计时继续，`safe_wait` 的原始 deadline 也不会延长。

运行时间接受 `0`、留空或非负整数秒：

- `0`/留空表示持续运行；
- 正整数表示到期后请求停止；
- timer 在首位详情打开、批次/动作点击区域校准和 OCR 正文区域校准完成后才启动；
- 到期或按 `Esc` 时，正在进行的 Provider 请求仍可能一直返回或等到 120 秒 timeout 后，Run 才能收尾。

Run 状态语义：

- 正常结束使用 Python `RunStatus.COMPLETED`，`run.json` 写 `"completed"`；
- `Esc`、duration 到期或普通停止信号使用 `RunStatus.INTERRUPTED`，JSON 写 `"interrupted"`；
- Detail Load、Candidate Switch、必要 AI/Decision 持久化完整性故障或被主循环捕获的异常使用 `RunStatus.ERROR`，JSON 写 `"error"`。部分 Stage-0 OCR evidence 记录采用 best-effort 路径，不能把所有 OCR 写入告警都概括为相同的 Run-fatal 状态。

存在需要查日志而不能只看 exit code/status 的例外：找不到支持的 BOSS 窗口时，Run 会以 `"completed"` 关闭并返回 0；必需 OCR/收藏区域校准被取消或失败时，Run 可在零候选人情况下返回 0，若没有 stop reason 还会写 `"completed"`；主循环捕获的运行异常会把 `run.json` 标成 `"error"`，但进程仍可能返回 0。

## 输出与数据文件

所有相对路径都以启动时的当前工作目录为基准。

### 每次 OCR Run

```text
data/ocr_runs/<timestamp>_<run_id>/
├── run.json
├── screens.jsonl
├── candidates.jsonl
├── errors.jsonl
├── ai_errors.jsonl
├── ai_results.jsonl
└── decisions.jsonl
```

| 文件 | 实际职责 |
| --- | --- |
| `run.json` | Run manifest、Profile binding、生命周期状态与汇总信息 |
| `screens.jsonl` | 每个正式屏幕的 raw OCR/规范化证据、box、指纹与扫描元数据 |
| `candidates.jsonl` | 最终化的候选人 OCR 文档记录 |
| `errors.jsonl` | OCR/Run evidence 错误记录 |
| `ai_errors.jsonl` | 每个被 accepted failure boundary 分类的失败正式 AI attempt；包含 attempt number、failure stage 和有界诊断字段 |
| `ai_results.jsonl` | 每个已完成 AI 处理候选人恰好一个最终 AI outcome；记录 attempts used、Profile binding、Provider/Model 和 completed/failed 结果 |
| `decisions.jsonl` | 每个最终 Decision 的 `run_id`、`candidate_record_id` 和三态 `decision_status` |

三个 AI/Decision JSONL 在 Run storage 初始化时创建，即使最终没有对应记录也可能是空文件。相同 `run_id` 和 `candidate_record_id` 用于连接 OCR、AI attempt、最终 AI outcome 与 Decision。当前没有 action result 文件、RuleSet 文件、Replay 数据库或 cache 文件。

Run storage 初始化失败会阻止开始动作；正式 screen evidence 写入失败会中止 Complete Scan。最终 candidate record 的追加采用记录错误的 best-effort 路径，因此不要把 `candidates.jsonl` 的每次后期写入与 R13 三个必要 AI/Decision 写入视为完全相同的 fatal contract。

### 其他文件

| 路径 | 内容 |
| --- | --- |
| `logs/simple_brush.log` | 人类可读运行日志和结构化事件摘要 |
| `logs/ocr_calibration_preview.png` | 最近一次 OCR 正文选区预览；固定文件名，会覆盖 |
| `config/ai_provider.json` | AI Provider 配置和明文 API Key |
| `calibration_profiles/*.json` | 可复用点击区域模板 |
| `data/screening_presets.json` | R15 ScreeningPreset collection 与最近一次 Confirm 的五项 Run settings；不含 API Key、校准、邮件或 Legacy 关键词 |
| `data/screening_profiles/<id>/versions/*.json` | 不可变 ScreeningProfile Version |

`data/ocr_runs` 可能含简历原文、OCR box 和故障上下文；`config/ai_provider.json` 含密钥。它们虽然由当前 `.gitignore` 排除，仍需由操作者负责访问控制、备份、保留周期和安全删除。

## 完整 CLI 参考

Python 与 one-dir executable 的参数相同：

```powershell
.\venv\Scripts\python.exe simple_brush.py [参数]
.\dist\Ocria\Ocria.exe [参数]
```

当前 `parse_args()` 支持 **11 个参数**：

| 参数 | 语法 | 实际作用与约束 |
| --- | --- | --- |
| `--keywords` | `--keywords '<Legacy 表达式>'` | Legacy 关键词兼容输入；非空时触发非交互启动，但不参与当前 Am7 的最终 Decision/动作授权。不要用它做安全开关。 |
| `--email` | `--email YOUR_BACKUP_EMAIL` | 非交互 `forward` 流程的备选邮箱；最近联系邮箱无效时才使用。它本身不触发非交互启动；交互流程仅在 `forward` 且未启用 `--no-forward` 时重新提示，否则清空备选邮箱。 |
| `--duration-seconds` | `--duration-seconds 600` | 非交互 Run 的非负 ASCII 整数秒数；`0` 表示持续运行，不表示立即退出。它本身不跳过菜单；交互流程会重新提示时长。 |
| `--no-forward` | `--no-forward` | 禁止真实邮件转发；保留 qualified Decision。不会抑制 `favorite`，不会把 forward 改成 favorite，也不跳过菜单。 |
| `--no-batch-filter` | `--no-batch-filter` | 禁用自动“最近没看过”筛选/归位，改用 Human 指定的首位候选人固定点击点。即使加载模板，模板中的筛选区域也不会启用。 |
| `--simple-mouse` | `--simple-mouse` | 对 `human_move_to()` 驱动的区域点击使用直接线性移动。默认使用 WindMouse；WindMouse 出错时回退到 Bezier。它不改变键盘切换、滚轮或 Legacy 首位候选人直接点击。 |
| `--auto` | `--auto` | 触发非交互启动，跳过启动菜单和运行配置提示；仍需手工选择 OCR 正文区域，不是 headless。必须同时提供 Profile ID 和至少一条 Rule。 |
| `--calibration-profile` | `--calibration-profile office-1080p` | 按模板名加载点击区域，并触发非交互启动。缺失、损坏、必要区域不足或系统信息不匹配时失败关闭；不包含 OCR 正文区域。 |
| `--screening-profile-id` | `--screening-profile-id sp_<32位小写十六进制>` | 指定要加载的最新 ScreeningProfile Version。非交互启动必需；仅传本参数不会跳过菜单。 |
| `--screening-rule` | `--screening-rule "C001 AND C002"` | 添加一条正式 Rule；可重复，一条或多条必需，多条固定 ANY。仅传 Rule 不会跳过菜单。PowerShell 中建议用引号包住空格和括号。 |
| `--action-mode` | `--action-mode favorite` 或 `--action-mode forward` | 非交互动作模式；省略时默认 `forward`。交互模式会重新要求选择。其他值在参数解析时返回错误。 |

### 非交互启动规则

触发非交互的条件只有以下任意一个：

```text
--auto
非空 --keywords
非空 --calibration-profile
```

一旦触发，`main()` 还要求同时存在：

```text
--screening-profile-id <id>
至少一个 --screening-rule <expression>
```

缺少任一项会在操作 BOSS 前返回 2。为了可读性与意图明确，自动化命令应显式使用 `--auto`，不要靠 Legacy `--keywords` 或模板名的副作用触发。

如果没有触发非交互，程序进入启动菜单。此时已传入的 Profile ID/Rule 不会替代 R15 的 Preset 选择与 Confirm，也不会替代 Advanced manual Run 的 Prepare/逐行 Rule 路径；没有 `--screening-preset`。正常 Preset 路径中的确认值优先于 CLI 的 Action/duration，只有 `--no-forward`、`--no-batch-filter` 与 `--simple-mouse` 等既有安全/物理运行开关仍按其既有语义生效。

### 参数解析注意事项

- 当前没有内置 `--help` 页面；`--help` 和其他未知参数会被静默忽略。
- 拼错参数可能不会报错，请对照上表并检查启动摘要/日志。
- `--keywords` 或 `--email` 位于 argv 末尾、没有任何后续 token 时会被静默忽略；若后面紧跟另一个 flag，parser 会把那个 flag 字面量当成它的值。其他需要值的已知参数在 argv 末尾缺值时会报错。
- CLI 不是 shell parser；参数值中的空格或括号必须由 PowerShell/Command Prompt 正确引用。

未传参时，字符串值和 Rule 列表为空、四个 Boolean 开关为 `false`、`action_mode` 为 `None`；进入非交互 Run 后，未指定的动作模式才落到 `forward` 默认值。

### 常用命令

保持交互菜单、禁止真实 forward：

```powershell
.\venv\Scripts\python.exe simple_brush.py --no-forward
```

非交互 `forward` 安全验证（仍需 OCR 正文手工框选）：

```powershell
.\venv\Scripts\python.exe simple_brush.py `
  --auto `
  --screening-profile-id sp_0123456789abcdef0123456789abcdef `
  --screening-rule "C001 AND C002" `
  --screening-rule "C003" `
  --action-mode forward `
  --no-forward `
  --calibration-profile office-1080p `
  --duration-seconds 300
```

真实收藏示例（**会点击收藏**）：

```powershell
.\venv\Scripts\python.exe simple_brush.py `
  --auto `
  --screening-profile-id sp_0123456789abcdef0123456789abcdef `
  --screening-rule "C001 AND C002" `
  --action-mode favorite `
  --calibration-profile office-1080p `
  --duration-seconds 600
```

## 故障排查

先按 `Esc` 请求安全停止，再查看 `logs/simple_brush.log`、对应 Run 的 `run.json`、`errors.jsonl` 和 AI JSONL。不要在进程仍写入时手工修改 Run 文件。

| 症状 | 通常表示 | 安全处理 |
| --- | --- | --- |
| 提示找不到 BOSS 浏览器，或没有处理任何候选人 | 没有可见的 `chrome.exe`/`msedge.exe` 顶层窗口，标题不匹配，或必需校准在候选人循环前结束 | 打开并登录唯一的正确页面，取消最小化/遮挡并检查校准日志后重新开始；注意这些路径可能仍返回 0，部分还会把 Run 标成 `"completed"` |
| 点击落在错误按钮、弹窗或候选人上 | 窗口、缩放、DPI、分辨率或 BOSS 布局与校准不同 | 立即停止，恢复相同环境或重建 Calibration Profile；不要继续试错点击 |
| OCR preview 为空、截错区域或正文很少 | Human 框选不正确、窗口被遮挡、详情未稳定，或 OCR 置信度不足 | 重新 Run 并框选只包含可见简历正文的区域；保持前台并检查 preview |
| `load_failed` | 最多 4 次 Detail Load 检查仍未达到内容门槛；固定点流程无法硬恢复 | 检查页面/网络/选区；校准批次筛选后可获得一次有界硬恢复，再重新 Run |
| `candidate_switch_failed` | Right Arrow 后无法以两次稳定新指纹证明已到下一位 | 不要手工强行续跑；检查焦点恢复区、详情加载、遮挡与 OCR 区域后重新开始 |
| Provider 认证失败 | API Key、Base URL、账号区域、权限或 endpoint 不匹配 | 回到 Provider Configuration，核对字段并重新做 Connection Test；不要在日志或 issue 中粘贴密钥 |
| timeout、网络或限流错误 | 本次 Completion 在 120 秒内失败或服务不可用 | 等待服务恢复或 Human 修改配置后开始新 Run；当前 attempt 间无 backoff，也不会自动切换 Provider/Model |
| Model unavailable | Model ID 不存在、不可访问或 endpoint 不支持 | 用模型列表能力确认，若该能力不可用则按 Provider 控制台手工核对 ID；Connection Test 成功不能排除此问题 |
| `provider_runtime` / `malformed_response` | OpenAI-compatible 响应缺少 choices、message 或非空 content，尚未进入 Boolean contract 校验 | 核对 endpoint/Model 兼容性并新建 Run；这是 classified Provider failure，不会被当成业务 rejection |
| `response_contract` | 已取得 response content，但它含 Markdown、额外字段、理由、错误 ID 或非 Boolean | 选择能稳定遵循严格 JSON contract 的模型并新建 Run；程序最多尝试 3 次，不会宽松解析 |
| Profile 无法加载或 digest 不匹配 | ID/Version 文件缺失、损坏、schema 无效或内容被手工篡改 | 从 Configuration CLI 重新加载/保存合法 Version；不要直接修补不可变 Version 文件 |
| Rule 在第一位候选人后触发 Run error | 表达式大小写/括号/token 错误，或引用了 Profile 不提供的 ID | 对照 `C001`、大写 `AND`/`OR` 语法并在新 Run 前人工核对；它不是业务 rejection |
| persistence integrity failure | Run 目录不可写、磁盘满、文件被占用/提前创建，或 AI/Decision JSONL 追加失败 | 停止，保留现有证据，检查磁盘与权限；不要忽略后继续动作，然后从新 Run 重试 |
| `qualified` 但没有实际转发 | `--no-forward`、程序计数上限、无可用邮箱、Decision 后收到停止请求、校准偏移或点击流程失败 | 先查日志；Decision 不是 action receipt。确认原因前不要重复发送 |
| Space 看似没有立即暂停，或 duration 在暂停中到期 | 暂停是协作式；在途 Provider 请求不可取消，timer 继续计时 | 等待当前 bounded 操作返回；需要停止时按 `Esc`，同时预留最长请求 timeout |

## 当前限制

- **Windows 与可见像素依赖**：只支持当前 Win32/主屏幕路径，只识别 Chrome 和 Edge；没有跨平台运行、后台浏览器或 headless 支持。
- **坐标敏感**：点击依赖绝对物理像素；系统信息相同不代表页面布局仍相同。Human 对 live 页面、账号和校准正确性负责。
- **不是 DOM 自动化**：没有 DOM access、Selenium 或 Playwright，无法通过元素语义自愈布局变化。
- **OCR 有不确定性**：可见像素、OCR 置信度、规范化与相似性是有界工程判断，不保证简历文字完整无误。
- **依赖第三方 AI**：正文发送给所选 Provider；没有自动 Provider fallback、自动 Model fallback、Prompt A/B 或自动 Prompt-version framework。
- **没有全局 dry-run**：`--no-forward` 只抑制 forward；favorite 仍会真实点击。
- **没有动作收据**：Decision 在动作前持久化，动作返回值未持久化；没有 `action_results.jsonl`。
- **Rule 可审计性有限**：Run-bound RuleSet 只在内存中存在，当前 Run manifest/JSONL 不保存 Rule 原文或 RuleSet identity。
- **批次边界固定**：每批最多 100 位，没有语义化列表终点检测。
- **自动模式仍需 Human**：`--auto` 不保存/恢复 OCR 正文区域，也不负责确认 BOSS 页面、遮挡或登录状态。
- **本地敏感数据**：API Key 明文存储；Run evidence 可能含候选人 PII。仓库不提供独立密钥库或数据保留管理器。
- **退出状态有例外**：浏览器未找到或必需校准提前结束可得到 0/`"completed"`；主循环异常可写 `"error"` 但仍返回 0，自动化必须结合 Run manifest 和日志。
- **没有历史再处理系统**：当前不存在 AI Replay、Replay Cache、Historical Candidate Rescreening、数据库、SQLite/PostgreSQL 或 Talent Library。测试中的 OCR replay fixture 只用于离线回归，不是产品功能。
- **没有 GUI**：配置与运行使用 console、键盘监听和屏幕框选 overlay，没有独立桌面管理界面。
- **当前 release 自动化不闭合**：checked-in build/workflow 的 smoke 参数与 Am7 非交互必需参数不兼容；在修复并重新验收前不能把历史本地包当作当前生产发布物。

Feature Complete 表示 Am7 当前产品能力边界已经实现，不等于每个 live 环境都无需 Human 校准，也不等于当前 source 已完成 R14 最终自动化验收或公开发布。

## Ocria 与 BossOCR Legacy

Ocria 保留 BossOCR 的 Git 历史来源，但已经是独立产品线：

- 来源产品：BossOCR；
- 来源仓库：`https://github.com/carolineasu2005-droid/Boss-OCR.git`；
- 来源基线：`main` / `V1.3.1` / commit `a7c941989a038d7a998ccee707e14b4fd9125cda`；
- Ocria：Am7 development mainline；
- BossOCR：独立维护的 Legacy Stable 与**人工选择**的产品线 fallback。

Ocria 运行时不会在故障后自动启动或降级到 BossOCR，两条产品线也不是 subtree、submodule、vendored copy 或双向同步关系。完整的 source/remote 边界见 [Ocria Am7 Provenance](docs/am7/PROVENANCE.md)。

Legacy 关键词解析、历史 `detect_keywords()` 和部分旧 console/docstring 文案仍保留在仓库中，但当前 production candidate path 调用 rule-free `scan_candidate()`；最终动作授权只来自 AI Boolean → ScreeningRuleSet → CandidateDecision。维护者不应根据残留名称或旧文档重新引入关键词 gate。

## 开发者参考

### 模块地图

| 模块 | 责任 |
| --- | --- |
| [`simple_brush.py`](simple_brush.py) | CLI、启动菜单、Run orchestration、浏览器/键盘控制、批次流程、AI/Decision/动作集成和安全停止 |
| [`ocr_detector.py`](ocr_detector.py) | RapidOCR capture、Detail Load、formal scan、fingerprint、Dynamic End 与 Complete Scan |
| [`ocr_candidate.py`](ocr_candidate.py) | 逐屏候选人状态、相似性/aggregation pipeline 编排与 `CandidateOcrDocument` 最终化 |
| [`ocr_aggregation.py`](ocr_aggregation.py) | 跨屏 overlap/segment 聚合、文档摘要与最终 `document_text` 构造 |
| [`ocr_records.py`](ocr_records.py) | OCR/Run schema、枚举、验证与序列化 contract |
| [`ocr_store.py`](ocr_store.py) | Run 目录、manifest、screen/candidate/error JSONL 写入和完整性检查 |
| [`ocr_normalization.py`](ocr_normalization.py) | Unicode/空白规范化、阅读顺序和同屏几何重复处理 |
| [`ocr_similarity.py`](ocr_similarity.py) | 跨屏相似性、有效新增文字分类与聚合投影 |
| [`ai_provider_config.py`](ai_provider_config.py) / [`ai_provider_cli.py`](ai_provider_cli.py) | 本地 Provider 配置 schema/store、staged CLI、状态与 Connection Verification |
| [`screening_preset.py`](screening_preset.py) / [`run_configuration.py`](run_configuration.py) / [`screening_preset_cli.py`](screening_preset_cli.py) | R15 Preset/last-used state、精确 Profile/Rule/Provider resolution、UUID-free Summary 与正常启动 UX |
| [`llm_provider_runtime.py`](llm_provider_runtime.py) | OpenAI-compatible Client、Provider 操作、模型列表、非推理检查和 Completion 错误边界 |
| [`screening_profile.py`](screening_profile.py) / [`screening_profile_cli.py`](screening_profile_cli.py) | Criterion、immutable Version、digest、Profile store 和 Human Draft/Save/Prepare 流程 |
| [`screening_rule_engine.py`](screening_rule_engine.py) | `AND`/`OR` parser、优先级、Boolean 输入验证和多 Rule ANY 求值 |
| [`ai_candidate_input.py`](ai_candidate_input.py) | 从候选人文档建立最小 AI 输入，只包含 identity 与正文 |
| [`ai_screening_prompt.py`](ai_screening_prompt.py) | 固定 `v1` Prompt、逐 Criterion 充分证据语义与 injection/data 边界 |
| [`ai_screening_contract.py`](ai_screening_contract.py) | 严格 JSON/Boolean/ID/字段验证，拒绝宽松输出 |
| [`ai_screening_runtime.py`](ai_screening_runtime.py) | 单次 AI attempt，区分 candidate input、Provider 和 response contract failure |
| [`ai_screening_persistence.py`](ai_screening_persistence.py) | 三个 R13 JSONL 的 typed record 与必要写入完整性 |
| [`candidate_decision.py`](candidate_decision.py) | 把 AI final status 与 Run-bound RuleSet 转成唯一三态 Decision |
| [`ocr_calibration.py`](ocr_calibration.py) / [`calibration_profiles.py`](calibration_profiles.py) | 屏幕区域选择、Profile schema/store 与环境匹配 |
| [`calibration_steps.py`](calibration_steps.py) / [`calibration_template.py`](calibration_template.py) | 11 个校准步骤、阶段顺序、Human transition 和独立模板生成器 |
| [`mouse_motion.py`](mouse_motion.py) | 默认 WindMouse 轨迹封装；主程序另提供 direct 与 Bezier fallback |

### 重要 contract

- OCR screen 必须先成功持久化，才提交到候选人聚合状态。
- AI 输入只来自已最终化、AI-eligible 的 `CandidateOcrDocument`。
- 每个 formal AI attempt 至多一次 Provider Completion 请求（candidate-input failure 为零次）；最多 3 attempts total。
- AI final outcome 在 Decision 前持久化，Decision 在任何 qualified 动作前持久化。
- `rejected` 与 `ai_failed` 都是零动作，但含义和持久化证据不同。
- 同一 Run 使用同一 immutable ScreeningRuleSet；当前只持久化 Profile binding，不持久化 RuleSet。
- Candidate Switch 未被保守确认时 fail closed，不扫描可能仍是旧候选人的页面。

### 测试

当前全量本地回归命令是：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

测试覆盖 Provider config/runtime、Profile/Rule、AI input/prompt/contract/runtime/persistence、Decision/action boundary、OCR records/store/normalization/similarity/Dynamic End、Detail Load、Candidate Switch、校准和鼠标移动。`tests/fixtures` 中的 replay/golden data 是离线 OCR 回归证据，不会连接 live BOSS 或调用 live AI。

标准回归命令不应附带真实 Provider 凭据，也不应作为 live BOSS 自动化入口。需要人工 live smoke 时，应由 Human 使用本 README 的安全流程、授权账号和隔离环境单独执行。

### 构建

`BossOCR.spec` 是保留的历史文件名，但当前 PyInstaller target 为 console one-dir `Ocria`，预期入口为 `dist/Ocria/Ocria.exe`。只构建本地目录可使用：

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\venv\Scripts\python.exe -m PyInstaller --clean --noconfirm BossOCR.spec
```

这只说明 source 中存在可执行的打包定义，不等于输出已经通过生产验收。当前 `build-windows.bat` 和 `.github/workflows/windows-release.yml` 都使用以下 smoke：

```text
Ocria.exe --no-forward --auto --duration-seconds 0
```

该命令缺少非交互必需的 `--screening-profile-id` 和 `--screening-rule`，当前程序会在启动校验返回 2，导致脚本无法完成压缩发布。Workflow 还引用了不存在的 `release-notes/Issue-1-BossOCR-release-notes.md`。这两个问题需要在独立获批的实现/发布任务中修复；本文不会修改 build 或 workflow，也不会把旧的 `Ocria-Am7-Windows-x64.zip` 宣称为当前已验证产物。

---

使用 live 招聘数据和执行真实动作前，请由 Human 最终复核 Provider、Profile Version、每条 Rule、动作模式、`--no-forward` 状态、校准 preview 与 BOSS 页面。
