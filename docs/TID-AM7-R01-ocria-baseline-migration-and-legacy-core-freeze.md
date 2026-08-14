# Ocria Am7 AM7-R01：Baseline Migration 与 Legacy Core Freeze——Technical Implementation Document

| 字段 | 值 |
|---|---|
| Requirement | AM7-R01 |
| TID 版本 | 0.7 |
| 状态 | Approved |
| 上游需求 | `RPD-AM7-R01-ocria-baseline-migration-and-legacy-core-freeze.md` 0.3 / Approved |
| 审计窗口 | 2026-08-11—2026-08-13，Asia/Shanghai |
| 当前阶段 | TID 0.7 已 Approved；允许进入 C01 |

## 1. 目的、授权边界与结论

本 TID 以当前 `F:\Ocria` 本地仓库、其完整 Git 历史和可核验的 GitHub 远端事实为准，定义 AM7-R01 后续 Change 的唯一技术边界。它不实现 Change，也不授权生产代码、测试代码、打包、工作流、remote 或发布状态发生变化。

审计结论如下：

1. BossOCR Source Baseline 可唯一候选为 `carolineasu2005-droid/Boss-OCR` 的 `main`、完整 commit `a7c941989a038d7a998ccee707e14b4fd9125cda`、tree `b3ddfa62cf1673ffc59887b06517baacf9c79cd7`、tag/release `V1.3.1`。
2. 该候选同时具备 Git 对象、远端 branch/tag、GitHub Release、发布包摘要和历史验收材料，但当前 TID 环境没有完整运行依赖，尚不能把历史测试数字替代为一次当前环境的 Full Legacy Regression。正式锁定必须在 Change 1 按第 14 节重新执行。
3. 审计时点的 Ocria `HEAD` 与 `V1.3.1` 均指向候选 baseline commit，`bossocr-upstream/main` 当时也恰好指向该 commit；前两者连同完整 commit/tree 构成不可变 baseline 证据，upstream main 只是可移动 Source Branch ref 的观测快照。当前没有 Ocria `origin`，唯一 remote `bossocr-upstream` 同时配置了 fetch 和 push URL；最终写入边界由 Change 2 处理。
4. Legacy OCR/浏览器自动化实现和合同已经形成可冻结边界。AM7-R01 只允许最小产品身份迁移、治理文档版本化、只增不改的回归屏障和本地/远端边界保护，不允许顺手重构。
5. 当前没有可提交的、脱敏的真实 OCR replay fixture。Golden Replay 可行，但只能以明确标注的纯合成资料建立，不能把 `data/ocr_runs`、日志、截图、候选人姓名、简历文字、邮箱或其他真实业务数据带入仓库。


## 2. 不可变实施原则

- AM7-R01 不开发 AI，不实现 AM7-R06 完整扫描接口，不定义 Ocria AI Runtime 的失败降级。
- BossOCR fallback 是独立 BossOCR Legacy Stable 产品线的产品级、人工回退，不是 Ocria 内置的自动 Keyword Mode fallback。
- 不重命名 Legacy Python 模块、类、函数、CLI 参数或持久化字段；不做目录重构、依赖升级、格式化清扫或技术债修复。
- 除 C03 唯一批准的 startup-menu 品牌 expectation `开始运行 BossOCR`→`开始运行 Ocria Am7` 外，不修改既有测试的断言、fixture、mock、skip 或预期值来“适配”品牌迁移。唯一允许的新测试是 AM7-R01 自身的品牌/边界/Golden 回归屏障。
- Codex / Terra 不登录真实 BOSS 账号，不自动执行真实收藏或真实转发。正式真实页面操作仅允许作为最终人工 Smoke，由人工在受控条件下决定是否执行。
- 每个 Change 只能修改其允许清单；出现 Stop Condition 必须立即停止该 Change，不得越界补救。
- 历史发布说明和历史测试计数是来源证据，不是当前 Change 的通过证明。

## 3. 仓库审计范围与方法

### 3.1 已审计对象

审计覆盖：tracked/ignored 工作区、所有顶层 source、`tests/`、`docs/`、Git refs/log/tags/branches、GitHub commit/PR/issue/release、requirements、Windows setup/start/build、PyInstaller spec、GitHub Actions、benchmark、Stage-0 记录链、`CandidateOcrDocument`、JSONL store/replay、历史 smoke/acceptance/TID/RPD、fixture/runtime data 和 `.gitignore`。

主要只读方法的审计记录包括以下命令形态；其中 `rg` 的 scope 是实际审计时按 source/tests/docs/build/workflow 分组展开的记录，不属于 C01—C05 blocking gate：

```text
git status --short --branch
git remote -v
git branch -a -vv
git tag --list --format="%(refname:short) %(objecttype) %(objectname)"
git log --graph --decorate --oneline --all
git ls-files
git status --short --ignored --untracked-files=all
rg --files
rg -n "..." <scoped paths>
gh release list --repo carolineasu2005-droid/Boss-OCR
gh release view V1.3.1 --repo carolineasu2005-droid/Boss-OCR
```

GitHub connector另行核对了 repository 元数据、default branch、最新 commits、PR #11 及不存在的 Ocria repository。GitHub 与本地结论一致。

### 3.2 当前仓库事实快照

| 对象 | 审计事实 |
|---|---|
| 本地 branch | `main` |
| tracked 工作区 | clean；AM7-R01 RPD 因 `*.md` 被忽略而不显示为 tracked change |
| `HEAD` | `a7c941989a038d7a998ccee707e14b4fd9125cda` |
| parent | `79bc98e9fac5de3ee50d081125b66f1c73aa6c61` |
| tree | `b3ddfa62cf1673ffc59887b06517baacf9c79cd7` |
| commit time / subject | `2026-08-11T21:45:20+08:00` / `fix(focus): use safe region for candidate focus recovery` |
| baseline tag | lightweight `V1.3.1`，直接指向 `a7c9419...` |
| 前一稳定 tag | `V1.3` → `4096e542bd71b927c082d2146ca1358f3a06519b` |
| 当前 remote | 仅 `bossocr-upstream` → `https://github.com/carolineasu2005-droid/Boss-OCR.git`；fetch/push 相同 |
| Ocria remote | 未配置；GitHub 上没有可访问的 `carolineasu2005-droid/Ocria` repository |
| GitHub release | `BossOCR v1.3.1 — Final Stable Hotfix`，发布于 `2026-08-11T13:52:42Z` |
| Windows asset | `BossOCR-Windows-x64.zip`，123,421,312 bytes |
| asset SHA-256 | `1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9`；与 release API digest 及 `.sha256` asset 一致 |
| tracked 文件 | 127；其中 `test_*.py` 16 个；历史设计/验收材料已大量版本化 |
| workflow | 仅 `.github/workflows/windows-release.yml` |
| runtime evidence | 默认路径 `data/ocr_runs`；被忽略；当前工作区未发现可用 run/log/screenshot fixture |
| Markdown ignore | `.gitignore` 全局 `*.md`；仅少数现有文档例外；AM7-R01 RPD 当前被忽略 |

### 3.3 测试现状与审计限制

当前工作区不存在 `venv` / `.venv`。只读探测试用了系统 Python 3.14.4：

```text
python -m unittest discover -s tests -q
Ran 458 tests
FAILED (errors=3)
```

三个 collection/import error 来自 `test_mouse_motion`、`test_ocr_stage0_integration`、`test_simple_brush_ocr` 共同缺少 `pyautogui`。这说明当前环境前置条件不满足；它既不是 Legacy 回归失败的代码结论，也不是通过证据。本 TID 没有安装依赖、没有执行 Change。GitHub V1.3.1 release 记录的 `776` 项 full suite、`263` 项 targeted suite，以及 PR #11 记录的 `766` 项 full suite / `324` 项 targeted suite，因提交和测试集合不同，仅作为历史证据。

### 3.4 与 RPD 假设的差异及设计处理

| 仓库事实 | 与 RPD 的关系 | TID 处理 |
|---|---|---|
| `a7c9419...` 的 release/tag/remote 证据成立，但当前环境未完成全量回归 | 强化基线候选，但不满足独立复验 | Change 1 在固定 Python 3.11 环境重跑；全绿后才写 `confirmed` |
| 没有 Ocria `origin`，BossOCR remote 可 push | RPD 要求独立边界尚未完全实现 | Change 2 使用人类授权 URL；无 URL 时记录 `absent_pending_human` 并进入 `BLOCKED / Pending Human Repository Setup`，绝不猜测、创建或 push；C02 不能 Accepted |
| `docs/README.md` 仍称 BossOCR v1.2，构建产物仍为 BossOCR | 符合 RPD 所述品牌尚未迁移 | Change 3 只改用户可见身份和产物名；历史文档中的 BossOCR 不改 |
| `.gitignore` 使一般 Markdown（包括 AM7 RPD）不可版本化 | RPD Open Item 已确认 | Change 1 加精确 allowlist；不取消全局规则，不纳入临时 Markdown |
| 没有可复用的 Golden OCR 资产 | RPD 要求研究可行性 | Change 4 只新增纯合成 fixture 和独立新测试；不复制真实 run |
| 当前运行时 `R05=record`、`R06=record`、`R07=full` | 是当前 V1.3.1 行为，而非所有历史版本行为 | 纳入 Observable/Parameter Freeze；品牌 Change 不得调整 mode |
| workflow 内联 release title 仍含旧 BossOCR / Issue #1；`--notes-file` 指向未跟踪且当前不存在的 `release-notes/Issue-1-BossOCR-release-notes.md`；tracked 的 `docs/Issue-1-BossOCR-release-notes.md` 未被 workflow 引用 | 品牌陈旧与既有 notes path 缺口必须分开 | Change 3 只迁移 workflow 内联用户可见身份；保持 `--notes-file` 命令和路径不变，不创建 notes 文件；tracked 历史 notes 保持不改；该 missing notes file 是 intentional non-blocking technical debt，故 AM7-R01 不得宣称 release workflow 已实际可发布 |

## 4. BossOCR Source Baseline 的确认方法与证据链

### 4.1 唯一候选

```text
repository: https://github.com/carolineasu2005-droid/Boss-OCR.git
branch:     main
commit:     a7c941989a038d7a998ccee707e14b4fd9125cda
tree:       b3ddfa62cf1673ffc59887b06517baacf9c79cd7
tag:        V1.3.1
release:    https://github.com/carolineasu2005-droid/Boss-OCR/releases/tag/V1.3.1
asset:      BossOCR-Windows-x64.zip
asset sha:  1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9
```

`V1.3.1` 是 lightweight tag，不包含独立签名；release checksum 也不是发布者签名。因此证据链的含义是“Git object identity + GitHub repository/release identity + hash consistency + regression + human approval”，不夸大为密码学签名供应链。

### 4.2 Change 1 的精确确认命令

必须在 clean tracked worktree、联网可访问 GitHub 且尚未产生品牌代码差异时运行：

```powershell
$baseline = 'a7c941989a038d7a998ccee707e14b4fd9125cda'
$frozenAssetSha256 = '1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9'
git fetch bossocr-upstream --tags --prune
git status --short --branch
git status --porcelain --untracked-files=all
git status --short --ignored --untracked-files=all
git rev-parse HEAD
git rev-parse bossocr-upstream/main
git rev-list -n 1 V1.3.1
git show -s --format="%H%n%P%n%T%n%aI%n%cI%n%s" a7c941989a038d7a998ccee707e14b4fd9125cda
git cat-file -t V1.3.1
git diff --exit-code a7c941989a038d7a998ccee707e14b4fd9125cda -- .
if ($LASTEXITCODE -ne 0) { throw 'pristine baseline tracked diff is not clean' }
$headCommit = (git rev-parse HEAD).Trim()
$tagCommit = (git rev-list -n 1 V1.3.1).Trim()
$baselineTree = (git rev-parse ($baseline + '^{tree}')).Trim()
$baselineParent = (git show -s --format='%P' $baseline).Trim()
$baselineSubject = (git show -s --format='%s' $baseline).Trim()
$baselineAuthorTime = (git show -s --format='%aI' $baseline).Trim()
$tagObjectType = (git cat-file -t V1.3.1).Trim()
if ($headCommit -ne $baseline -or $tagCommit -ne $baseline) {
  throw 'local HEAD or V1.3.1 does not equal the frozen baseline commit'
}
if ($baselineTree -ne 'b3ddfa62cf1673ffc59887b06517baacf9c79cd7' -or
    $baselineParent -ne '79bc98e9fac5de3ee50d081125b66f1c73aa6c61' -or
    $baselineSubject -ne 'fix(focus): use safe region for candidate focus recovery' -or
    $baselineAuthorTime -ne '2026-08-11T21:45:20+08:00' -or $tagObjectType -ne 'commit') {
  throw 'baseline tree, parent, subject, time, or lightweight-tag type mismatch'
}

$remoteTagLine = @(git ls-remote bossocr-upstream refs/tags/V1.3.1)
if ($LASTEXITCODE -ne 0 -or $remoteTagLine.Count -ne 1) {
  throw 'remote V1.3.1 tag lookup failed or was not unique'
}
$remoteTagParts = $remoteTagLine[0] -split '\s+'
if ($remoteTagParts[0] -ne $baseline -or $remoteTagParts[1] -ne 'refs/tags/V1.3.1') {
  throw 'remote V1.3.1 does not resolve to the frozen baseline commit'
}
$upstreamMain = (git rev-parse bossocr-upstream/main).Trim()
if ($LASTEXITCODE -ne 0) { throw 'cannot resolve bossocr-upstream/main' }
if ($upstreamMain -ne $baseline) {
  git merge-base --is-ancestor $baseline bossocr-upstream/main
  if ($LASTEXITCODE -ne 0) { throw 'baseline is not traceable as an ancestor of bossocr-upstream/main' }
}

gh release view V1.3.1 --repo carolineasu2005-droid/Boss-OCR
$releaseRaw = gh api repos/carolineasu2005-droid/Boss-OCR/releases/tags/V1.3.1
if ($LASTEXITCODE -ne 0) { throw 'GitHub Release API lookup failed' }
$release = $releaseRaw | ConvertFrom-Json
if ($release.tag_name -ne 'V1.3.1' -or
    $release.name -ne 'BossOCR v1.3.1 — Final Stable Hotfix' -or
    $release.published_at -ne '2026-08-11T13:52:42Z') {
  throw 'GitHub Release identity or timestamp mismatch'
}
$remoteTagCommitRaw = gh api repos/carolineasu2005-droid/Boss-OCR/git/ref/tags/V1.3.1 --jq '.object.sha'
if ($LASTEXITCODE -ne 0 -or @($remoteTagCommitRaw).Count -ne 1 -or $remoteTagCommitRaw.Trim() -ne $baseline) {
  throw 'GitHub tag ref does not resolve to the frozen baseline commit'
}
$zipAsset = @($release.assets | Where-Object { $_.name -eq 'BossOCR-Windows-x64.zip' })
$checksumAsset = @($release.assets | Where-Object { $_.name -eq 'BossOCR-Windows-x64.sha256.txt' })
if ($zipAsset.Count -ne 1 -or $checksumAsset.Count -ne 1 -or
    [int64]$zipAsset[0].size -ne 123421312 -or
    [int64]$checksumAsset[0].size -ne 91 -or
    $zipAsset[0].digest -ne ('sha256:' + $frozenAssetSha256)) {
  throw 'release asset identity, size, or API digest mismatch'
}

$assetAuditDir = Join-Path ([IO.Path]::GetTempPath()) ('am7-r01-c01-release-' + [guid]::NewGuid())
try {
  New-Item -ItemType Directory -Path $assetAuditDir -ErrorAction Stop | Out-Null
  gh release download V1.3.1 --repo carolineasu2005-droid/Boss-OCR --pattern 'BossOCR-Windows-x64*' --dir $assetAuditDir
  if ($LASTEXITCODE -ne 0) { throw 'release asset download failed' }
  $zipPath = Join-Path $assetAuditDir 'BossOCR-Windows-x64.zip'
  $checksumPath = Join-Path $assetAuditDir 'BossOCR-Windows-x64.sha256.txt'
  $actualZipSha256 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
  $checksumText = (Get-Content -Raw -Encoding ASCII -LiteralPath $checksumPath).Trim()
  if ($checksumText -notmatch '^(?<sha>[0-9a-fA-F]{64})\s+BossOCR-Windows-x64\.zip$') {
    throw 'checksum asset content has an unexpected format or filename'
  }
  $checksumSha256 = $Matches.sha.ToLowerInvariant()
  if ($checksumSha256 -ne $actualZipSha256 -or
      $actualZipSha256 -ne $frozenAssetSha256 -or
      $zipAsset[0].digest -ne ('sha256:' + $actualZipSha256)) {
    throw 'checksum asset, downloaded ZIP, API digest, and frozen digest are not identical'
  }
}
finally {
  if (Test-Path -LiteralPath $assetAuditDir) {
    $resolvedAuditDir = (Resolve-Path -LiteralPath $assetAuditDir).Path
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    $safeLeaf = (Split-Path -Leaf $resolvedAuditDir) -like 'am7-r01-c01-release-*'
    if ($safeLeaf -and $resolvedAuditDir.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
      Remove-Item -LiteralPath $resolvedAuditDir -Recurse -Force
    } else {
      throw 'refusing to clean an unverified release-audit directory'
    }
  }
}
```

C01 必须逐项审查两个 status 输出，而不只检查 tracked diff；ignored 输出使用 `--untracked-files=all` 展开目录内容。已知可允许项仅包括当前 AM7-R01 RPD/TID、隔离 `venv/.venv`、Python/test 缓存，以及经人工确认且不参与本次 import、test discovery、configuration 或 runtime 的受控 ignored runtime/build 目录。任何未知 untracked/ignored 文件，只要可能遮蔽 Python module、改变测试发现、注入配置或影响运行行为，即为 Stop Condition。只停止并报告，不执行 `git clean`，不删除、移动或改写用户文件。

然后按第 13.1 节建立 Python 3.11 x64 隔离环境，并按第 14.1 节执行 Full Legacy Regression、benchmark、compile 和 dependency check。仅当以下条件全部成立，才能在 metadata 中写入 `confirmation.status = "confirmed"`：

1. Ocria pristine `HEAD` 与 `V1.3.1` 都精确等于候选 baseline commit；
2. 完整 Source Commit SHA、tree、parent、commit time/subject 与本 TID一致；
3. 远端 `refs/tags/V1.3.1` 精确解析到 baseline；GitHub Release identity/timestamp、ZIP/checksum asset identity/size 均精确匹配；下载 ZIP 的实际 SHA-256、Release API ZIP digest、checksum asset 内容和本 TID frozen digest 四者程序化相等；
4. `bossocr-upstream/main` 的观测 SHA 被记录：若等于 baseline 正常记录；若已向前推进，则 baseline 必须仍是该 ref 的 ancestor，并在 provenance/evidence 中记录 BossOCR 在 Ocria derivation 后继续演进；
5. Full Legacy Regression 0 failure、0 error，且测试发现/收集无异常；
6. 三个 benchmark contract、`pip check`、`compileall` 均通过；
7. 人工在 Source Baseline 报告中签署批准。

Ocria `HEAD` 偏离候选 commit、`V1.3.1` tag 漂移、release 缺失、摘要不一致、baseline 不再是 `bossocr-upstream/main` 的 ancestor、检测到 upstream history rewrite 或来源关系无法可靠证明，以及工作区/测试门禁异常，均是 Stop Condition。`bossocr-upstream/main` 单纯向前推进不是 baseline 漂移；不得把 baseline 改成“最新 main”，也不得以修代码继续锁基线。

### 4.3 持久化证据

Change 1 产生：

- `docs/am7/baselines/AM7-R01-source-baseline.json`：机器可读事实；
- `docs/am7/baselines/AM7-R01-source-baseline.md`：命令、结果摘要、限制和人工签署；
- `docs/am7/acceptance/evidence/AM7-R01-C01/`：脱敏原始命令输出和测试日志；
- release asset 不提交仓库，只记录 URL、size、digest 和核对时间。

## 5. Provenance、Baseline Metadata 与仓库边界

### 5.1 机器可读 metadata 合同

`AM7-R01-source-baseline.json` 使用 `am7-source-baseline-v1`，至少包含：

```json
{
  "schema_version": "am7-source-baseline-v1",
  "product": {"name": "Ocria", "generation": "Am7"},
  "source": {
    "product": "BossOCR",
    "repository": "https://github.com/carolineasu2005-droid/Boss-OCR.git",
    "branch": "main",
    "commit": "a7c941989a038d7a998ccee707e14b4fd9125cda",
    "parent": "79bc98e9fac5de3ee50d081125b66f1c73aa6c61",
    "tree": "b3ddfa62cf1673ffc59887b06517baacf9c79cd7",
    "tag": "V1.3.1",
    "release_url": "https://github.com/carolineasu2005-droid/Boss-OCR/releases/tag/V1.3.1",
    "release_published_at": "2026-08-11T13:52:42Z",
    "asset": {
      "name": "BossOCR-Windows-x64.zip",
      "size_bytes": 123421312,
      "sha256": "1be803a15af01779786585c7bc84fd1dc1722a002f146762d6e8f9e2f11f22a9"
    }
  },
  "relationship": {
    "type": "history-preserving-derived-repository",
    "bossocr_role": "legacy_stable_fallback",
    "ocria_role": "am7_development_mainline",
    "fallback_mode": "manual_product_line",
    "automatic_runtime_fallback": false
  },
  "repository_boundary": {
    "origin_status": "absent_pending_human",
    "origin_url": null,
    "upstream_remote_name": "bossocr-upstream",
    "upstream_fetch_url": "https://github.com/carolineasu2005-droid/Boss-OCR.git",
    "upstream_push_disabled": false
  },
  "confirmation": {
    "status": "confirmed",
    "confirmed_at": "<RFC3339 offset timestamp>",
    "python": "3.11.x x64",
    "evidence_refs": ["<repository-relative paths>"],
    "human_approver": "<required>"
  }
}
```

`repository_boundary.origin_status` 只允许 `absent_pending_human` 或 `configured`。C01 创建 metadata 时必须描述当时真实状态：`origin_status=absent_pending_human`、`origin_url=null`、`upstream_push_disabled=false`；这不阻止 Source Baseline 的 `confirmation.status=confirmed` 独立成立。C02 只有在人工批准 URL 已配置且 upstream push 已实际禁用后，才更新为 `origin_status=configured`、`origin_url=<人工批准的独立 Ocria repository URL>`、`upstream_push_disabled=true`。第一种只能表示 C02 Pending；C02 及 AM7-R01 最终 Acceptance 要求第二种。metadata 不得提前描述未来目标状态。

占位值不得提交为 `confirmed`。JSON 由测试验证必填键、40/64 位小写 hex、RFC3339 时间、固定来源关系和 evidence path；不得把 access token、邮箱、主机用户名或本机绝对路径写入。

### 5.2 人类可读 provenance

新增 `docs/am7/PROVENANCE.md`，说明：

- Ocria Am7 保留 BossOCR 到基线 commit 的完整祖先历史；
- 后续 Ocria commit 只进入 Ocria 产品线；BossOCR 继续独立维护；
- BossOCR 是人工选择的产品级 fallback；不存在自动 runtime fallback 承诺；
- 如何验证 metadata、如何只读拉取上游、禁止向上游 push；
- Ocria `origin` 尚未配置时明确写 `absent_pending_human`，不能写虚构 URL。

### 5.3 remote / repository 边界方案

最终命名固定为：

| remote | 用途 | 写入规则 |
|---|---|---|
| `origin` | 人工批准的独立 Ocria repository | 仅 Ocria Change；URL 必须由人工提供/批准 |
| `bossocr-upstream` | BossOCR 来源核对和将来人工评估上游差异 | fetch-only；AM7 自动化与执行者禁止 push |

Change 2 可执行的本地配置为：

```powershell
$rewriteOutput = @(git config --show-origin --get-regexp '^url\..*\.(insteadOf|pushInsteadOf)$')
$rewriteExit = $LASTEXITCODE
if ($rewriteExit -notin @(0,1)) { throw 'Git URL rewrite audit command failed' }
$rewriteOutput
# exit 1 + no output means未配置 rewrite；exit 0 时每项都必须人工解释，任何未知或指向 BossOCR 的 rewrite 均停止。
$approvedOcriaUrl = (Read-Host 'Paste the already human-approved independent Ocria repository URL').Trim()
if ([string]::IsNullOrWhiteSpace($approvedOcriaUrl)) { throw 'approved Ocria URL was not provided' }
git remote set-url --push bossocr-upstream no_push://bossocr-upstream
if ($LASTEXITCODE -ne 0) { throw 'failed to disable bossocr-upstream push' }
$remoteNames = @(git remote)
if ($remoteNames -contains 'origin') {
  $currentOriginUrl = (git remote get-url origin).Trim()
  if ($LASTEXITCODE -ne 0 -or $currentOriginUrl -ne $approvedOcriaUrl) { throw 'existing origin differs from the human-approved Ocria URL' }
} else {
  git remote add origin $approvedOcriaUrl
  if ($LASTEXITCODE -ne 0) { throw 'failed to add approved Ocria origin' }
}
git remote -v
$originUrl = (git remote get-url origin).Trim()
$upstreamFetchUrl = (git remote get-url bossocr-upstream).Trim()
$upstreamPushUrl = (git remote get-url --push bossocr-upstream).Trim()
if ($originUrl -ne $approvedOcriaUrl -or
    $upstreamFetchUrl -ne 'https://github.com/carolineasu2005-droid/Boss-OCR.git' -or
    $upstreamPushUrl -ne 'no_push://bossocr-upstream') {
  throw 'final repository boundary does not match the approved contract'
}
git merge-base --is-ancestor a7c941989a038d7a998ccee707e14b4fd9125cda HEAD
if ($LASTEXITCODE -ne 0) { throw 'source baseline is not an ancestor of current HEAD' }
```

`git config --get-regexp` 没有匹配时按 Git 语义返回 `1`，这是“没有 rewrite”，不是失败；其他非零或无法解释的输出才是 Stop。若 `origin` 已存在，不执行 literal `git remote add origin`，只用 `git remote get-url origin` 与人工批准 URL 做精确比较。`no_push://bossocr-upstream` 必须作为最终 push URL 原样返回；任何 `insteadOf` / `pushInsteadOf` 将其或 `origin` 重写到 BossOCR 均为 Stop。

“C02 期间 0 push”的证据是执行前批准的 command manifest、完整 Change transcript 及人工审查，其中不得出现 `git push`、`gh repo create`、发布或上传命令；Git 本地配置不能证明整个历史上从未 push，TID 不作这种声明。

`.git/config` 不是可 clone 的持久证据，所以必须同时提交 metadata 与 `PROVENANCE.md`。如果没有人工批准的 Ocria URL，metadata 必须保持 `origin_status=absent_pending_human` 和 `origin_url=null`，C02 进入 `BLOCKED / Pending Human Repository Setup` 并停止；不得创建 GitHub repository、不得选择 namespace、不得 push。人工创建/提供并批准独立 Ocria repository URL、配置 `origin` 后，才可改为 `configured` 并继续 C02 Acceptance。

AM7-R01 不做 BossOCR→Ocria 历史重写、subtree、submodule、squash import 或双向同步。继承点由完整 commit/tree 固定，后续两个产品线自然分叉。

## 6. 四区 Freeze Matrix

同一文件可按区域同时属于 Frozen/Protected/Migration；区域级规则优先于粗粒度文件分类。

| 区域 | 精确文件/区域 | 技术合同 | AM7-R01 权限 |
|---|---|---|---|
| Frozen Core | `ocr_text.py` | keyword grammar、`not > and > or`、`any(...)`、精确匹配/二次确认输入语义 | 禁止修改 |
| Frozen Core | `ocr_normalization.py` | R04 geometry/reading order/文本与 comparison/dedup、config snapshot/digest | 禁止修改 |
| Frozen Core | `ocr_aggregation.py` | R05 exact/fuzzy/historical boundary aggregation、document projection、config | 禁止修改 |
| Frozen Core | `ocr_similarity.py` | R06 reference resolution、n-gram Dice、SimHash、effective-new、summary | 禁止修改 |
| Frozen Core | `ocr_records.py` | enums、JSON dataclass、schema/version/validation、`OcrScreenRecord`、`CandidateOcrDocument`、`RunManifest` | 禁止修改 |
| Frozen Core | `ocr_candidate.py` | `CandidateOcrBuilder` lifecycle、screen commit/rollback/finalize | 禁止修改 |
| Frozen Core | `ocr_store.py` | `JsonlOcrRecordStore` 文件名、append/flush/failure/diagnostic privacy 合同 | 禁止修改 |
| Frozen Core | `ocr_replay.py` | strict/tolerant reader、normalization/aggregation/similarity/dynamic-end replay | 禁止修改 |
| Frozen Core | `ocr_similarity_sidecar.py` | sidecar 投影合同 | 禁止修改 |
| Frozen Core | `ocr_calibration.py`、`calibration_profiles.py`、`calibration_steps.py`、`calibration_template.py` | 校准 region/profile/schema/步骤/原子发布 | 禁止修改，纯产品标题例外须单独批准；当前未发现必要例外 |
| Frozen Core | `mouse_motion.py` | WindMouse/Bezier fallback、最终落点与 click safety | 禁止修改 |
| Frozen Core + Protected Integration | `ocr_detector.py` 全文件 | R02/R03/R07 算法和参数冻结；`OCRKeywordDetector` 是受保护接缝 | AM7-R01 禁止修改 |
| Protected Integration | `simple_brush.py` 全文件 | CLI、动作、焦点、OCR、candidate lifecycle、batch/switch/recovery/run orchestration | 默认禁止；仅第 9.2 节列出的 3 处显示字符串允许改 |
| Protected Integration | `ocr_calibration.py`、browser/window glue、PyAutoGUI/MSS/RapidOCR adapters | 平台与 UI 接缝 | 禁止行为修改 |
| Migration Zone | `.gitignore` | AM7 文档与 fixture 可版本化；runtime evidence 仍忽略 | 仅精确 allowlist |
| Migration Zone | `docs/README.md`，新增根 `README.md`、`docs/am7/**` | Ocria 身份、provenance、freeze、acceptance | 允许最小文档变更；历史 RPD/TID/acceptance 正文不改 |
| Migration Zone | `setup.bat`、`start.bat`、`build-windows.bat` | 显示名、产物路径；命令顺序和安全 smoke 语义冻结 | 仅品牌/产物路径 |
| Migration Zone | `BossOCR.spec` | spec 文件名与 analysis 输入保持；EXE/COLLECT 用户可见名可迁移 | 仅 `name="Ocria"` 两处 |
| Migration Zone | `.github/workflows/windows-release.yml` | Ocria workflow/tag/artifact/release identity；测试/build/safe smoke 步骤冻结 | 仅第 9.2 节精确项 |
| Greenfield | `docs/am7/**` 新文件 | AM7 治理和证据 | 可新增，不得反向定义 Legacy 行为 |
| Greenfield | `tests/fixtures/am7_r01/**`、`tests/test_am7_r01_*.py` | 纯合成 golden、metadata/brand/repository-boundary guard | 除 C03 唯一批准的 startup-menu 品牌 expectation migration 外，只增不改既有测试；不得接入真实业务数据 |

`ocr_fixture_demo.py`、`ocr_mac_demo.py` 和三个 benchmark 属 Legacy 验证/工具边界，AM7-R01 不修改。`data/ocr_runs/**`、`logs/**`、截图和本地 calibration profile 不是 Greenfield，仍属于本地敏感运行资产，禁止提交。

## 7. 函数级 Protected Boundary

### 7.1 `ocr_detector.py`

`ocr_detector.py` 在 AM7-R01 中整文件不可修改。以下函数/合同是以后 Requirement 也必须显式申请授权才能接入的边界：

| 对象 | 当前职责 | 保护规则 |
|---|---|---|
| `accepted_ocr_items()`、`calculate_load_metrics()`、`evaluate_detail_page_load()` | R02 load gate 的 confidence/box/text 计算 | 返回语义、阈值边界、过滤顺序冻结 |
| `fingerprint_box_bounds()`、`order_fingerprint_items()`、`normalize_fingerprint_item_text()`、`build_fingerprint_raw_text()`、`build_fingerprint_normalized_text()`、`sha256_normalized_text()`、`build_screen_fingerprint()`、`compare_screen_fingerprints()` | R03 单屏指纹和三态比较 | 排序、文本、hash、错误语义冻结 |
| `classify_position()`、`DynamicEndConfig`、`DynamicEndState`、`PositionDecision` | R07 position/dynamic-end 的有界事实与分类 | mode、计数上限、no-new 规则和 fail-open/closed 语义冻结 |
| `OCRBackend`、`ScreenCapture`、`MSSScreenCapture`、`RapidOCRBackend` | OCR/capture adapter | 输入输出类型和一次 capture/recognize 语义受保护；R01 不替换 backend |
| `ScanObservation`、`DetectionResult`、`PositionConfirmationResult`、`ObservationCallbackFailure` | detector 与 Stage-0/主循环的数据接缝 | 字段、nullable、失败表示和回调顺序冻结 |
| `OCRKeywordDetector.__init__()` | 注入 `backend`、`capture`、`region`、scan/confidence/timing、`observation_callback`、normalization、dynamic-end、focus/interrupt callback | 这是后续受控接入缝，不是 R01 修改点；参数、默认值、callback 合同冻结 |
| `OCRKeywordDetector.capture_observation()` | 单次 observation | 一次 OCR、证据生成、日志/错误语义冻结 |
| `OCRKeywordDetector.detect()` | 最多八屏扫描、关键词二次确认、滚动/恢复/结束 | action authority、scan budget、顺序、return 语义冻结 |
| `OCRKeywordDetector` 内所有 `_...` 私有函数 | 回调、dynamic state、confirmation、recovery 和 effect sequencing | 未列出的私有实现同样 Frozen，不可借“内部函数”规避边界 |

构造器当前关键默认值为 `max_scans=8`、`min_confidence=0.85`、`settle_seconds=0.6`、`confirmation_seconds=0.7`、`rule_evaluation_mode="legacy_shadow"`、`DynamicEndConfig()` 默认 shadow；`simple_brush.py` 在产品路径显式注入 `DynamicEndConfig(mode="full")`。两者差异是有意的合同层次，不能“统一默认值”。

### 7.2 `simple_brush.py`

`simple_brush.py` 是 Legacy orchestration 的主 Protected Boundary。除第 9.2 节三个纯显示字符串外，AM7-R01 不得修改。

| 函数/区域 | 保护对象 |
|---|---|
| `parse_args()`、`is_noninteractive_startup()`、`run()`、`main()` 与 startup menu/input helpers | CLI flags、默认 action mode、交互顺序、无交互启动判定和 fail-closed |
| `on_press()`、timer/stop/wait helpers | Space 暂停、ESC、限时停止和中断传播 |
| `bring_boss_foreground()` 及 compatibility wrapper `bring_edge_foreground()` | Chrome 优先、Edge fallback、窗口匹配和无窗口安全失败 |
| `human_move_to()`、`human_click()`、`mouse_motion.move_to_observable()` 及 region point helpers | WindMouse/Bezier fallback、最终整数落点、按下/抬起顺序 |
| calibration/profile/reset/ensure helpers | region 采集顺序、原子发布、取消/异常 fallback、最小区域 |
| `initialize_ocr()`、`run_detail_load_gate()`、`detect_keywords()` | backend 创建、load retry、OCR 参数、callback 和 detector wiring |
| `start_candidate_ocr_recording()`、`record_ocr_observation()`、`record_detection_observation()`、`finalize_current_candidate_recording()`、`finalize_active_candidate_for_stop()`、store close helpers | Stage-0 的 candidate/screen/run lifecycle、一次写入、失败诊断隐私 |
| `perform_favorite_action()`、`forward_one_candidate()`、`restore_candidate_detail_focus()` | favorite/forward 动作、连续上限、成功/失败都恢复焦点、安全 region |
| `click_first_candidate()`、`apply_batch_filter_and_open_first_candidate()`、`open_first_candidate_for_batch()` | batch filter 与首候选人准备顺序 |
| `view_candidate()` | load→OCR→动作→停留预算；OCR 失败不执行真实动作 |
| `next_candidate()`、`prepare_candidate_switch_context()`、`confirm_candidate_switch()` | 候选人切换前基线、观察、确认、两次 action budget |
| `refresh_page()`、detail recovery helpers | 100 人批次刷新、单次 hard recovery 和停止语义 |
| `run()`、`main()` | 完整启动、校准、候选人循环、finally/finalization |

以下是允许未来 Requirement 使用、但 AM7-R01 不实现的受控 seam：`observation_callback` / `record_detection_observation()` 的证据接缝，以及 `detect_keywords()` 返回到 `view_candidate()` 的决策接缝。任何 AI 接入必须另有 Requirement，不能复用本 TID 作为授权。

## 8. 四类 Freeze 的技术级保护对象

### 8.1 Algorithm Freeze

冻结以下算法和处理顺序：

- R02：confidence 过滤后以 box count / text length 判定详情页 load；retry/failure 不触发业务动作。
- R03：box geometry→阅读顺序→raw/normalized text→UTF-8 SHA-256→`same/different/unavailable`。
- R04：geometry adapter、视觉行、文本 normalization/comparison、duplicate confirmation/gray risk、Legacy shadow rule authority。
- R05：相邻 exact overlap、受限 fuzzy 1↔1/1↔2/2↔1、historical bounded match、new/uncertain/matched partition、candidate document projection。
- R06：formal reference resolution、2/3/4-gram weighted multiset Dice、64-bit SimHash、R05 accounting、effective-new 的保守判定。
- R07：最多八个正式 scan slot、最多七次正常 scroll、一次 scroll retry、一次 focus restore、first-same recovery、两次连续 no-new 才可动态结束、Legacy rule 优先。
- keyword grammar/精确匹配/完整规则二次确认；favorite/forward action gate；候选人切换确认；100 人 batch/filter/refresh；停止/finalization。
- Store→Replay 必须使用 manifest snapshot，而不是当前默认参数；strict/tolerant 的失败与隐私语义不变。

### 8.2 Parameter Freeze

以下参数值本身是保护对象；同义重排、移入 config、改默认值或依据环境动态调整都算行为变更：

凡本节表格或 TID 其他 Freeze 表述使用“保持现值”“现有值”“current value”等未展开字面数值的参数，其唯一权威值均为最终批准的 Source Baseline commit 中对应生产路径实际生效的值。实现者不得自行解释、重新选择或以执行时工作区值替代；若无法唯一定位对应文件、符号和有效值，必须停止并提交人工审查。

| 领域 | 冻结值 |
|---|---|
| 主循环 | `BATCH_SIZE=100`、refresh wait `5s`、click wait `2s`、countdown `3s`、候选停留预算保持现值 |
| OCR | `max_scans=8`、`min_confidence=0.85`、load boxes `5`、load text length `30`、scroll `600..1000`、settle `0.6s`、confirmation `0.7s` |
| runtime modes | R04 rule `legacy_shadow`、R05 aggregation `record`、R06 similarity `record`、R07 dynamic end `full` |
| R07 | `no_new_text_threshold=2`；scan/scroll/unique/retry/focus bounds `8/7/8/1/1` |
| candidate switch | max actions `2`、observations/action `6`、stable observations `2`、wait `0.8s` |
| forward | delay `0.5..1.5s`、consecutive max `5`、现有 click regions/offsets |
| favorite/focus | `favorite_button_region` 与 `focus_restore_region` 校准合同；safe region 内点；focus restore 两次 click 尝试 |
| R04 config | version `r04-config-v1`；confidence `0.85`；include unknown；line tolerance ratio/min/max `.45/4/18`；line pair `.5`；vertical overlap `.5`；join `.25/.75`；duplicate margin `1.0`；primary/secondary/gray duplicate 阈值保持代码 snapshot（`.85/.2/.9`、`.7/.95`、`.65/.35/.8`） |
| R05 config | max screens/segments `8/256`；exact `2 segments / 24 chars / 1 nonshort / 48 single`；short `8`；fuzzy `.94/.88/.005/32`、tail/head `4/4`、combined `3`、unmatched `2`、group `512`、candidate `128`；historical `2..4 segments / 48 chars / 2 anchors` |
| R06 config | n-grams `(2,3,4)` weights `(.20,.30,.50)`；metric `weighted_multiset_dice`；SimHash `64`, 3-gram, `sha256_first_8_bytes_big_endian`, prefix `r06-simhash-3gram-v1`；similarity `.85`；confidence `.85`；low confidence `.03/2 chars`；UI `3 occurrences / 8px / .5 / .90`；float `1e-12`；max text `100000`；max screens `8`；business short-term tuple/version/digest |
| mouse | `mouse_motion.py` 的 WindMouse/Bezier 参数、distance 分支、approach 范围、jitter/easing/最终点；`--simple-mouse` fallback |

精确 config snapshot/digest 是比本表更权威的机器合同；本表不授权遗漏字段变化。

### 8.3 Schema Freeze

冻结：

- storage versions：`1.0.0`、R04 `1.1.0`、R05 `1.2.0`、R06 `1.3.0`、R07/current `1.4.0`；document versions `stage0-v1` 与 `r05-document-v1`。
- JSONL 路径和文件名：`data/ocr_runs/<run_id>/run.json`、`screens.jsonl`、`candidates.jsonl`、`errors.jsonl`。
- `OcrScreenRecord` 的 identity/capture/raw evidence、R04 text/segment/mapping/hash、rule comparison、R05 partition/evidence、R06 similarity、R07 position/prediction 字段及 nullable/default/validation 语义。
- `CandidateOcrDocument` 的 `run_id`、`candidate_record_id`、`sequence_number`、timestamps、`capture_status`、`screens`、`capture_summary`、document/normalization/aggregation/similarity、`versions`、`metadata`、dynamic-end counts/reasons/prediction 字段。
- `RunManifest` 的 run/platform/python/data files、action/max/app/git、normalization/aggregation/similarity/dynamic config snapshot+digest、status/counts。
- enums、warning/error codes、record type、screen/candidate ordering、timezone-aware timestamp、canonical digest 和 older-schema restore 合同。
- `JsonlOcrRecordStore` 失败三次禁用、原子/完整单行、close 幂等、错误上下文 allowlist；candidate builder 的 commit-after-store-success 和释放语义。

AM7-R01 新增的 baseline metadata 使用独立 `am7-source-baseline-v1`，不得塞进 Legacy `RunManifest` 或 `CandidateOcrDocument`。Golden expected summary 也是 test-only schema，不改 Legacy reader。

### 8.4 Observable Behavior Freeze

从用户和外部系统可观察的以下行为冻结，唯一例外是显式批准的 Ocria 产品显示身份：

- CLI flags、默认值、interactive/auto 菜单顺序、错误码、暂停/ESC/限时停止；
- Chrome 优先、Edge fallback；无匹配 BOSS 窗口安全停止；
- load gate、八屏扫描、OCR 二次确认、scroll/bottom/dynamic-end 和日志事件顺序；
- favorite 与 forward 两条 Legacy 路径；`--no-forward` 永不调用真实 forward；OCR/校准/切换失败不得调用业务动作；
- forward 连续上限和 favorite/forward 后 shared safe focus restore；
- candidate next/switch validation、batch filter、100 人刷新与一次 hard recovery；
- Stage-0 原始证据保持、候选人一次 finalize、run close；Replay 纯离线、无 UI/网络副作用；
- build 是 Windows x64 Python 3.11 PyInstaller one-dir；safe executable smoke 的参数仍为 `--no-forward --auto --duration-seconds 0`；
- 日志/错误材料不得泄漏关键词命中正文、邮箱或候选人 OCR 内容。

## 9. Ocria Am7 Brand Migration 的精确范围

### 9.1 统一身份

| 对象 | 目标值 |
|---|---|
| 用户显示产品名 | `Ocria Am7` |
| 简称 | `Ocria` |
| Windows executable/directory | `Ocria.exe` / `dist\Ocria\` |
| Windows archive | `Ocria-Am7-Windows-x64.zip`；workflow 同时生成同名 `.sha256`，C05 local acceptance 也按第 14.7 节生成该 sidecar |
| workflow/artifact display | `Ocria Am7 Windows Release` / `Ocria-Am7-Windows-x64` |
| release tag filter | `ocria-am7-v*` |
| release title | `Ocria Am7 <tag>` |
| provenance 中来源名 | 继续精确写 `BossOCR`，不得改为 Ocria |
| BOSS 网站/窗口/业务名 | 继续写 `BOSS 直聘`，这不是旧产品品牌残留 |

### 9.2 允许修改的既有位置

| 文件 | 只允许的修改 |
|---|---|
| `simple_brush.py` | startup menu docstring 中 `BossOCR`→`Ocria Am7`；菜单 `开始运行 BossOCR`→`开始运行 Ocria Am7`；`run()` 启动 logger 产品字符串→`Ocria Am7 启动` |
| `setup.bat` | banner 产品名→`Ocria Am7 - 环境初始化` |
| `start.bat` | banner→`Ocria Am7`；浏览器提示校正为 Chrome preferred / Edge fallback；执行命令和 flags 不改 |
| `BossOCR.spec` | `EXE(... name="BossOCR")` 与 `COLLECT(... name="BossOCR")` 两处→`Ocria`；spec 文件名、entry script、hidden imports、datas 不改 |
| `build-windows.bat` | dist/exe/archive/sha/完成提示中的产物路径改为第 9.1 节目标；安装、full test、PyInstaller 与 safe smoke 参数顺序不改 |
| `.github/workflows/windows-release.yml` | workflow 名、tag filter、dist/exe/archive/artifact 及内联 release title 改为 Ocria；保留既有 `--notes-file release-notes/Issue-1-BossOCR-release-notes.md` 命令和路径，不创建额外 notes 文件；Python/test/build/smoke 权限和顺序不改；禁止引入 `--generate-notes` |
| `docs/README.md` | 变为 Ocria Am7 详细用户/构建说明，纠正陈旧 v1.2、产物名和 Chrome/Edge 说明；保留来源链接到 provenance，不把 BossOCR release 伪装成 Ocria release |
| 新 `README.md` | Ocria Am7 仓库入口、能力摘要、来源/fallback 边界、详细文档链接；不复制历史实现细节 |

保留不改：`simple_brush.py`、`BossOCR.spec` 文件名；`_bossocr_console_handler` 等内部兼容标识；`bring_boss_*`、window title 和 BOSS 网站语义；tracked 历史文件 `docs/Issue-1-BossOCR-release-notes.md` 及其他归档 RPD/TID/acceptance/release notes；Python import/module/class/function 名；CLI flags；requirements 和 dependency version。

Release Notes 的已知限制必须保留在 C03/C05 evidence：active workflow 继续引用当前不存在且未跟踪的 `release-notes/Issue-1-BossOCR-release-notes.md`；存在的 `docs/Issue-1-BossOCR-release-notes.md` 只是历史材料，不是替代输入。AM7-R01 不创建、移动或修改任何 notes 文件，也不改变 `--notes-file` 机制，因此只能验收 workflow 的最小身份迁移，不能声称该 workflow 已通过实际发布或当前可成功发布。

Change 3 不能发布 release、不能 push tag、不能登录页面。构建产物的品牌验证在本地完成。

## 10. `.gitignore` 与 AM7 文档版本化

现有 `.gitignore` 第 20 行 `*.md` 保持；现有 `!README.md` 保持。Change 1 只在历史例外区新增：

```gitignore
# Ocria Am7 governed design and acceptance documents
!docs/RPD-AM7-*.md
!docs/TID-AM7-*.md
!docs/am7/
!docs/am7/**/*.md
```

JSON/CSV/TXT 本来不受 `*.md` 影响；无需放宽。必须继续忽略 `logs/`、`calibration_profiles/*.json`、`data/ocr_runs/`、`build/`、`dist/`、`release/`、venv 和一般本地 Markdown。

固定文档拓扑：

```text
README.md
docs/
  RPD-AM7-R01-ocria-baseline-migration-and-legacy-core-freeze.md
  TID-AM7-R01-ocria-baseline-migration-and-legacy-core-freeze.md
  am7/
    README.md
    PROVENANCE.md
    LEGACY-FREEZE-MATRIX.md
    baselines/
      AM7-R01-source-baseline.json
      AM7-R01-source-baseline.md
    acceptance/
      AM7-R01-manual-smoke-checklist.md
      AM7-R01-acceptance-report.md
      evidence/AM7-R01-C01..C05/
```


## 11. Golden Replay / Fixture 设计

### 11.1 可行性结论

可行。`ocr_replay.py` 已能从 `run.json`、`screens.jsonl`、`candidates.jsonl` 离线重建 R04/R05/R06/R07 结果，现有测试也使用临时 synthetic records 验证 online/store/replay 等价。缺口是仓库没有稳定的静态 fixture 和跨 Change digest。

### 11.2 资产选择

Change 4 新增：

```text
tests/fixtures/am7_r01/golden_replay_v1/
  README.md
  run.json
  screens.jsonl
  candidates.jsonl
  errors.jsonl
  expected-summary.json
tests/test_am7_r01_golden_replay.py
```

fixture 必须由现有 test builder 合同生成后人工检查并固定，但内容是纯合成：虚构 `run_id`/candidate id、通用技能片段、合成坐标和确定时间。至少覆盖：一屏 initial、相邻 overlap、新内容、短文本保护、一次 same/position confirmation、R05 document、R06 similarity/effective-new、R07 no-new prediction/terminal summary；不需要也不允许驱动 UI。

`expected-summary.json` 使用 `am7-golden-replay-summary-v1`，比较：record counts/order、schema/version/config digests、每屏 exact hash/normalization/partition/similarity/position 字段、candidate document canonical JSON SHA-256、document text SHA-256、dynamic-end reason/counts、strict reader 0 issue、online frozen expected 与 replay result 等价。文本正文只在 fixture 本身出现合成值，acceptance log 只输出 digest 和计数。

### 11.3 隐私边界

明确禁止：从 `data/ocr_runs` 复制、真实截图/简历、姓名、电话、邮箱、公司+经历组合、真实 BOSS UI OCR body、用户关键词、真实坐标/机器路径、日志中的候选人上下文。自动 guard 检查 fixture 不含 email/手机号样式、`C:\Users\`、真实 run path；人工还要做语义审查。不能仅靠 regex 宣称脱敏完成。

### 11.4 对照方式与限制

Golden Replay 防止算法/参数/schema/离线 observable 漂移，但不能证明浏览器窗口、鼠标落点、页面加载、favorite/forward 或焦点恢复。后者由既有 unit/integration suite、构建 safe smoke 和最终人工真实页面 Smoke 共同覆盖。Golden failure 不允许 regenerate expected；必须先人工判断是未授权 Legacy drift 还是 fixture 错误。

## 12. Manual Real BOSS Page Smoke Checklist

### 12.1 执行权与安全原则

正式真实页面 Smoke 只由人工执行。Codex / Terra 的职责止于生成 checklist、解释步骤和接收人工填写的脱敏结果；不得控制鼠标/键盘、不得登录、不得替人工点击 favorite/forward、不得选择真实候选人或收件人。

favorite 与 forward Legacy 路径必须被验证，但不要求为了 Smoke 对无关真实候选人或真实外部收件人产生业务影响。每条 action path 必须由人工在以下方式中选择其一：

1. `controlled-real`：使用受控测试对象；favorite 可撤销，forward 只发往测试者自有/受控目标，并已确认候选内容允许用于测试；
2. `human-approved-equivalent`：由人工审查者事前批准的等价安全验证，记录替代点、未执行的真实最终动作、为什么仍覆盖该合同以及证据。

“没有执行，也没有替代证据”不能标记 Pass。等价方式的批准权属于人工，不属于 Codex / Terra。

### 12.2 Checklist 文件格式

`docs/am7/acceptance/AM7-R01-manual-smoke-checklist.md` 使用固定头部：Smoke ID、Status、Human executor/approver、执行时间、Ocria commit/tree、build SHA-256、Windows/browser、resolution/DPI、calibration profile identifier、BOSS account authorization、test object classification、敏感证据确认。

每个步骤用表格：`ID | Preconditions | Human action | Expected | Result | Evidence ref | Notes`。结果只能是 `Pass/Fail/Blocked/Not Run`；不得仅写“看起来正常”。Evidence ref 指向脱敏摘要，不嵌入候选人正文、姓名、电话、邮箱或账号信息。

### 12.3 精确步骤

| ID | 人工验证动作 | 预期 |
|---|---|---|
| MS-01 | 从解压后的 `Ocria.exe` 启动 | console/start menu 清楚显示 `Ocria Am7`；不是 BossOCR Stable |
| MS-02 | 选择有效 calibration profile 并进入受控 BOSS 页面 | Chrome 优先；无 Chrome 时 Edge fallback；窗口置前且无错误窗口动作 |
| MS-03 | 打开受控候选人详情 | load gate 后才开始 OCR；未加载完成不执行 favorite/forward |
| MS-04 | 使用不命中的受控关键词运行一位候选人 | 多屏 OCR/scroll 可观察；无业务动作；可正常 next |
| MS-05 | 验证 Space pause/resume 与 ESC stop | 暂停不发出新导航/动作；ESC 走现有 finalization 并安全停止 |
| MS-06 | `--no-forward` 下使用可命中的受控规则 | 即使命中也不调用真实 forward/favorite |
| MS-07 | favorite 路径，记录 `controlled-real` 或已批准 equivalent | 只走 favorite，不走 forward；成功/受控替代后验证 shared focus restore 和 next candidate |
| MS-08 | forward 路径，记录 `controlled-real` 或已批准 equivalent | 受控收件目标；完整 Legacy 二次确认与 forward path；结束后 shared focus restore 和 next candidate |
| MS-09 | 人工制造/观察一次安全失败（如缺失目标窗口或取消校准） | fail-closed；不误点业务动作；错误信息不泄漏 OCR 正文 |
| MS-10 | 验证 batch filter/首候选人打开；如人工批准可验证一次 refresh recovery | 顺序与 V1.3.1 一致；不要求为了 smoke 浏览 100 个无关对象 |
| MS-11 | 核对本次 run 的本地 Stage-0 文件（不提交） | 四个 run 文件合同可读；candidate 一次 finalize；无未说明 schema drift |
| MS-12 | 与 BossOCR V1.3.1 观察基线做人工差异确认 | 除 `Ocria Am7` 显示/产物身份外无未批准可观察差异 |

任一业务误动作、动作目标不受控、焦点恢复后操作了错误候选人、OCR/load/switch 失败仍触发动作、敏感证据进入仓库，立即 Fail 并停止 Smoke。

## 13. 验证环境与证据处理

### 13.1 固定环境

- Windows x64；CPython 3.11.x x64。
- 新建或重建 ignored `venv/`；不得使用本次审计中的 Python 3.14.4 结果作为 acceptance。
- 依赖仅 `requirements.txt`、`requirements-ocr.txt`；构建时加 `requirements-build.txt`。AM7-R01 不改版本范围、不生成 runtime lockfile。
- 每次记录 Python、pointer bits、pip、`pip freeze`、commit/tree 和时间。
- 仓库内 evidence 只保存脱敏内容；未脱敏日志不得进入 Git。

```powershell
py -3.11 -c "import struct, sys; bits = struct.calcsize('P') * 8; print(sys.version); print(bits); assert bits == 64"
py -3.11 -m venv venv
```

```powershell
& .\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr.txt
& .\venv\Scripts\python.exe -m pip check
& .\venv\Scripts\python.exe --version
& .\venv\Scripts\python.exe -m pip freeze
```

构建 Change 再安装 `requirements-build.txt` 并重跑 `pip check`。依赖下载失败、Python 不是 3.11 x64、`pip check` 非零、导入/collection error 均为 Stop Condition；不得删测试绕过。

### 13.2 证据日志最小头部

每份自动化日志包含：Change ID、command、start/end timestamp、repo-relative cwd、commit/tree、package inventory ref、exit code、tests run/fail/error/skip、操作者和脱敏确认。不得包含 token、credential、候选 OCR body 或邮箱。

### 13.3 Stop 与 Change-local recovery 分类

以下情况是 True Stop Conditions：Legacy regression 或冻结 benchmark 合同失败；baseline/tag/release/hash drift；provenance 无法证明；Frozen contract 或 protected diff 失败；出现未授权文件/区域；继续修复需要触碰当前 Change 禁止区域、改变阈值/fixture 预期或扩大 Requirement。发生时必须停止并报告，不能在当前 Change 内绕过。

以下情况只有在根因明确且修复完全位于当前 Change allowlist 时，才是 Change-local recoverable issue：重建隔离 `venv`；对有记录的瞬态依赖准备故障按第 14.1 节规则重试；修正当前 Change 新增 evidence/document 的格式；修正 C04 自己新增 fixture/test 的实现错误。允许流程固定为 `记录失败 → allowlist 内修复 → 从受影响 gate 起重测并保留前后证据`。如果修复要求修改生产代码、既有测试/benchmark、冻结 expected、requirements、build/workflow 或其他禁止区域，立即升级为 True Stop；C03 唯一批准的 startup-menu 品牌 expectation migration 不属于此处的未授权既有测试修改。环境重建或重试不得覆盖已经出现的真实性能、行为或合同失败。

## 14. Regression Barrier 的精确命令

### 14.1 Full Legacy Regression

基线确认时在纯 baseline tree 执行一次；每个代码/测试/构建 Change 后再执行。测试总数不硬编码，因为 Change 4 会只增新 tests；必须记录实际 count，且 0 failure、0 error。任何 unexpected skip 必须人工审查，不能作为通过。

```powershell
& .\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Full Legacy Regression failed' }
& .\venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'pip check failed' }
```

三个 benchmark 保持从 repository root 使用 module invocation，但 process exit `0` 只是必要条件，不能单独代表 PASS。每次 Barrier 每个 benchmark 只执行一次并保留原始 JSON。若 benchmark process 成功、output-contract harness 完整执行，且 contract/performance assertion FAIL，则属于 genuine benchmark contract failure：必须保留失败证据并判 Gate FAIL，禁止重跑 benchmark 刷 PASS。

若 benchmark process 已成功输出 raw JSON，但 assertion wrapper 因 PowerShell syntax、parser、tooling 或 infrastructure error 未完成 contract evaluation，则属于 harness/infrastructure failure：不得标记 Benchmark PASS，也不得标记 genuine benchmark contract failure；必须优先保留并对同一份 raw JSON 修复后重新执行 assertion，不重新运行 benchmark。只有 raw JSON 未保存且无法恢复时，经 Human/Sol 明确授权，才可重新运行一次 benchmark，仅重新获取 raw JSON；此前 harness failure evidence 必须保留，这不视为“刷 benchmark”。任何代码、fixture、threshold、digest、scenario 或配置均不得因此修改。

#### 14.1.1 R04 benchmark output contract

```powershell
$r04Raw = & .\venv\Scripts\python.exe -m tests.benchmark_r04_normalization
$r04Exit = $LASTEXITCODE
if ($r04Exit -ne 0) { throw 'R04 benchmark process failed' }
try { $r04 = $r04Raw | ConvertFrom-Json -ErrorAction Stop } catch { throw 'R04 benchmark did not emit valid JSON' }
$r04Expected = @{
  'unique-0' = @(0,25,0,0,0,0,0); 'unique-1' = @(1,25,0,0,1,0,0)
  'unique-8' = @(8,25,0,0,8,0,0); 'unique-100' = @(100,25,0,0,100,0,0)
  'unique-500' = @(500,25,0,0,500,0,0); 'far-same-text-500' = @(500,25,0,0,500,0,0)
  'dense-same-position-text-500' = @(500,25,499,499,1,499,0)
  'dense-100-repeated-identical' = @(100,100,99,99,1,99,0)
}
if ($r04.normalization_version -ne 'r04-v1' -or $r04.normalization_config_version -ne 'r04-config-v1' -or
    $r04.normalization_config_digest -ne '3597727e595b16c3aba7bfa41653b617f11277e78ce52379c99ee3afafcb84d5' -or
    @($r04.rows).Count -ne 8) { throw 'R04 identity or scenario-count contract failed' }
foreach ($row in @($r04.rows)) {
  if (-not $r04Expected.ContainsKey($row.scenario)) { throw 'unexpected R04 scenario' }
  $expected = $r04Expected[$row.scenario]
  $actual = @($row.boxes,$row.runs,$row.candidate_count,$row.survivor_confirmation_count,$row.survivor_count,$row.suppressed_count,$row.gray_count)
  if ($actual.Count -ne $expected.Count) { throw 'R04 correctness field count failed' }
  for ($fieldIndex = 0; $fieldIndex -lt $expected.Count; $fieldIndex++) {
    if ($actual[$fieldIndex] -ne $expected[$fieldIndex]) { throw 'R04 correctness fields failed' }
  }
  if ($row.deterministic -ne $true) { throw 'R04 determinism failed' }
  foreach ($field in @('median_ms','p95_ms','peak_kib','gc_retained_kib')) {
    $value = [double]$row.$field
    if ([double]::IsNaN($value) -or [double]::IsInfinity($value) -or $value -lt 0) { throw 'R04 numeric output invalid' }
  }
}
if (($r04.rows | Where-Object { $_.scenario -eq 'unique-100' }).p95_ms -ge 10) { throw 'R04 100-box p95 must be less than 10 ms' }
if (@($r04.rows | Where-Object { $_.boxes -eq 500 -and $_.p95_ms -ge 50 }).Count -ne 0) { throw 'every R04 500-box p95 must be less than 50 ms' }
```

R04 历史 Acceptance 冻结的数值性能门槛只有 100 boxes p95 `<10 ms` 与每个 500-box scenario p95 `<50 ms`。baseline 没有批准独立数值 memory threshold，因此本 Requirement 不发明新阈值；`peak_kib` / `gc_retained_kib` 必须存在、有限且非负，并作为 trend evidence 保存。correctness contract 是固定场景集合、boxes/runs、candidate/confirmation/survivor/suppressed/gray 精确值、identity/digest 和全部 `deterministic=true`。

#### 14.1.2 R05 benchmark output contract

```powershell
$r05Raw = & .\venv\Scripts\python.exe -m tests.benchmark_r05_aggregation
$r05Exit = $LASTEXITCODE
if ($r05Exit -ne 0) { throw 'R05 benchmark process failed' }
try { $r05 = $r05Raw | ConvertFrom-Json -ErrorAction Stop } catch { throw 'R05 benchmark did not emit valid JSON' }
$r05Limits = @{
  '8x64_unique_pure' = @(20.0,16.0); '8x256_unique_pure' = @(150.0,32.0)
  '8x64_unique_record_projection_candidate_finalize' = @(30.0,32.0)
  'single_screen_fuzzy_1_to_1' = @(50.0,32.0); 'single_screen_fuzzy_1_to_2' = @(50.0,32.0)
  'single_screen_fuzzy_2_to_1' = @(50.0,32.0); 'single_screen_fuzzy_uncertain' = @(50.0,32.0)
}
$r05ExpectedScenarios = @(
  '8x64_unique_pure','8x128_unique_pure','8x256_unique_pure','8x64_unique_record_projection_candidate_finalize',
  '8x64_exact_50_percent','8x64_exact_90_percent','complete_screen_duplicate','one_new_line_per_screen',
  'single_screen_fuzzy_1_to_1','single_screen_fuzzy_1_to_2','single_screen_fuzzy_2_to_1',
  'single_screen_fuzzy_uncertain','8x64_near_duplicate_fuzzy_stress','historical_n_minus_2',
  'historical_ambiguous','8x256_exact_50_percent','fuzzy_candidate_limit_1_contract','257_segment_limit_contract'
)
if ($r05.aggregation_version -ne 'r05-v1' -or $r05.aggregation_config_version -ne 'r05-config-v1' -or
    $r05.aggregation_config_digest -ne '047ec8c40aab9b28ed3a7a6a63695f416677e1a73c25f3c398d77eca3b31ff7a' -or
    $r05.fixture_generator_version -ne 'r05-benchmark-contract-unique-v2' -or $r05.seed -ne 20260801 -or
    $r05.warmup_iterations -ne 3 -or $r05.reference_iterations -ne 1 -or
    $r05.timed_iterations_per_scenario -ne 25 -or $r05.scenario_order_mode -ne 'declared' -or
    $null -ne $r05.process_scenario_filter -or
    $r05.required_performance_gates_pass -ne $true -or @($r05.contract_blockers).Count -ne 0 -or
    $r05.determinism_100 -ne $true -or $r05.reference_release_100_full_candidates -ne $true -or
    $r05.disabled_does_not_construct_aggregator -ne $true -or $r05.fair_record_semantics_equal -ne $true) {
  throw 'R05 summary contract failed'
}
$r05Rows = @($r05.rows)
if ($r05Rows.Count -ne $r05ExpectedScenarios.Count) { throw 'R05 scenario count failed' }
for ($scenarioIndex = 0; $scenarioIndex -lt $r05ExpectedScenarios.Count; $scenarioIndex++) {
  if ($r05Rows[$scenarioIndex].scenario -ne $r05ExpectedScenarios[$scenarioIndex]) { throw 'R05 scenario set or order failed' }
}
foreach ($row in $r05Rows) {
  if ($row.contract_ok -ne $true -or $row.deterministic -ne $true -or $row.p95_pass -eq $false -or $row.memory_pass -eq $false) {
    throw 'R05 row contract failed'
  }
  $expectedRowDigest = if ($row.scenario -eq 'fuzzy_candidate_limit_1_contract') {
    '83bdaa0b9ce76e9e545f82dcc316fab46a86c7da73c5e4852223890014852671'
  } else {
    '047ec8c40aab9b28ed3a7a6a63695f416677e1a73c25f3c398d77eca3b31ff7a'
  }
  if ($row.aggregation_config_version -ne 'r05-config-v1' -or
      $row.aggregation_config_digest -ne $expectedRowDigest -or $row.timed_iterations -ne 25) {
    throw 'R05 row identity contract failed'
  }
  foreach ($field in @('p50_ms','p95_ms','min_ms','max_ms','peak_kib','retained_kib')) {
    $value = [double]$row.$field
    if ([double]::IsNaN($value) -or [double]::IsInfinity($value) -or $value -lt 0) { throw 'R05 numeric output invalid' }
  }
  if ($row.scenario -ne '257_segment_limit_contract' -and $row.scenario -ne '8x64_unique_pure' -and [double]$row.memory_limit_mib -ne 32.0) {
    throw 'R05 memory limit changed'
  }
  if ($row.scenario -ne '257_segment_limit_contract' -and $row.memory_pass -ne $true) { throw 'R05 memory gate missing or failed' }
  if (-not $r05Limits.ContainsKey($row.scenario) -and $row.scenario -ne '257_segment_limit_contract' -and
      ($null -ne $row.p95_limit_ms -or $null -ne $row.p95_pass)) { throw 'R05 unexpected p95 gate appeared' }
}
foreach ($name in $r05Limits.Keys) {
  $row = @($r05Rows | Where-Object { $_.scenario -eq $name })
  if ($row.Count -ne 1 -or [double]$row[0].p95_limit_ms -ne $r05Limits[$name][0] -or [double]$row[0].memory_limit_mib -ne $r05Limits[$name][1]) {
    throw 'R05 frozen threshold changed'
  }
  if ($row[0].p95_pass -ne $true -or $row[0].memory_pass -ne $true) { throw 'R05 frozen performance or memory gate failed' }
}
$r05NoLimit = @($r05Rows | Where-Object { $_.scenario -eq '257_segment_limit_contract' })[0]
if ($null -ne $r05NoLimit.p95_limit_ms -or $null -ne $r05NoLimit.memory_limit_mib) { throw 'R05 257-segment no-threshold contract changed' }
```

R05 的冻结数值门槛为：8x64 pure p95 `<=20 ms` 且 peak `<=16 MiB`；8x256 pure p95 `<=150 ms`；record projection p95 `<=30 ms`；四个 fuzzy shape p95 各 `<=50 ms`；除 8x64 为 16 MiB、257-segment 明确无 memory gate 外，其余 scenario peak `<=32 MiB`。同时必须满足固定 config digest、declared 全场景运行、所有 row identity/numeric fields、`contract_ok=true`、`deterministic=true`、所有适用 `p95_pass/memory_pass` 不为 false、`contract_blockers=[]`、100 次 deterministic、100 个完整 candidate 可释放、disabled 不构造 aggregator、pure/record 语义相等。

#### 14.1.3 R06 benchmark output contract

```powershell
$r06Raw = & .\venv\Scripts\python.exe -m tests.benchmark_r06_similarity
$r06Exit = $LASTEXITCODE
if ($r06Exit -ne 0) { throw 'R06 benchmark process failed' }
try { $r06 = $r06Raw | ConvertFrom-Json -ErrorAction Stop } catch { throw 'R06 benchmark did not emit valid JSON' }
$r06ExpectedScenarios = @(
  '20k_exact_same','20k_50_percent_changed','20k_repeated_ngram_stress','short_pair','unicode_pair',
  '100k_boundary','100001_reject','r05_accounting_64_segments','8_adjacent_pairs',
  'r05_record_only_8_screens','r06_calculation_only_8_screens','r05_r06_record_builder_8_screens',
  'r05_r06_disabled_builder_8_screens','r05_r06_replay_8_screens','r06_sidecar_synthetic_8_screens'
)
$r06Rows = @($r06.scenarios)
if ($r06.benchmark -ne 'r06_change3_pure_similarity' -or $r06.warmup_iterations -ne 3 -or
    $r06.timed_iterations -ne 25 -or $r06.memory_limit_kib -ne 16384 -or
    $r06.integration_fixture_screen_count -ne 8 -or $r06.required_performance_gates_pass -ne $true -or
    $r06Rows.Count -ne 15) {
  throw 'R06 summary or scenario contract failed'
}
for ($scenarioIndex = 0; $scenarioIndex -lt $r06ExpectedScenarios.Count; $scenarioIndex++) {
  if ($r06Rows[$scenarioIndex].scenario -ne $r06ExpectedScenarios[$scenarioIndex]) { throw 'R06 scenario set or order failed' }
}
foreach ($name in @('20k_exact_same','20k_50_percent_changed','20k_repeated_ngram_stress')) {
  $row = @($r06Rows | Where-Object { $_.scenario -eq $name })[0]
  if ([double]$row.p95_limit_ms -ne 15.0 -or $row.p95_pass -ne $true) { throw 'R06 20k gate failed' }
}
$adjacent = @($r06Rows | Where-Object { $_.scenario -eq '8_adjacent_pairs' })[0]
if ([double]$adjacent.p95_limit_ms -ne 100.0 -or $adjacent.p95_pass -ne $true) { throw 'R06 adjacent-pair gate failed' }
foreach ($row in $r06Rows) {
  if ($row.warmup_iterations -ne 3 -or $row.timed_iterations -ne 25) { throw 'R06 row iteration contract failed' }
  foreach ($field in @('p50_ms','p95_ms','peak_kib')) {
    $value = [double]$row.$field
    if ([double]::IsNaN($value) -or [double]::IsInfinity($value) -or $value -lt 0) { throw 'R06 numeric output invalid' }
  }
  if ([double]$row.peak_kib -gt 16384) { throw 'R06 memory gate failed' }
  if ($row.scenario -notin @('20k_exact_same','20k_50_percent_changed','20k_repeated_ngram_stress','8_adjacent_pairs') -and
      ($null -ne $row.p95_limit_ms -or $null -ne $row.p95_pass)) { throw 'R06 unexpected p95 gate appeared' }
}
```

R06 的冻结数值门槛为三个 20k scenario p95 各 `<=15 ms`、8 adjacent pairs p95 `<=100 ms`、所有 scenario peak `<=16 MiB`。baseline benchmark JSON 没有单独的 `deterministic` 或 `correctness` boolean；不得虚构字段。其 correctness/determinism 合同由固定 15 场景无异常完成、固定 iteration/fixture count、上述 output assertions，以及 Critical/Full 中已固定的 R06 algorithm、online/store/replay/sidecar tests 共同证明。

三个 benchmark 都是 `process exit 0 AND output contract PASS` 才通过；任一 `throw` 都是 Benchmark Gate FAIL。

另执行以下 compile contract；长名单是有意的，避免编译 runtime data 或生成发布副作用。`ocr_fixture_demo.py`、`ocr_mac_demo.py` 是 Freeze Matrix 中的 Python Legacy 工具，故纳入 compile target：

```powershell
$compileTargets = @(
  'calibration_profiles.py','calibration_steps.py','calibration_template.py','mouse_motion.py',
  'ocr_aggregation.py','ocr_calibration.py','ocr_candidate.py','ocr_detector.py','ocr_fixture_demo.py',
  'ocr_mac_demo.py','ocr_normalization.py','ocr_records.py','ocr_replay.py','ocr_similarity_sidecar.py',
  'ocr_similarity.py','ocr_store.py','ocr_text.py','simple_brush.py','tests'
)
$expectedCompileTargets = @(
  'calibration_profiles.py','calibration_steps.py','calibration_template.py','mouse_motion.py',
  'ocr_aggregation.py','ocr_calibration.py','ocr_candidate.py','ocr_detector.py','ocr_fixture_demo.py',
  'ocr_mac_demo.py','ocr_normalization.py','ocr_records.py','ocr_replay.py','ocr_similarity_sidecar.py',
  'ocr_similarity.py','ocr_store.py','ocr_text.py','simple_brush.py','tests'
)
if ($compileTargets.Count -ne $expectedCompileTargets.Count) { throw 'compile target manifest count changed' }
for ($compileIndex = 0; $compileIndex -lt $expectedCompileTargets.Count; $compileIndex++) {
  if ($compileTargets[$compileIndex] -ne $expectedCompileTargets[$compileIndex]) { throw 'compile target manifest changed' }
}
foreach ($target in $compileTargets) {
  if (-not (Test-Path -LiteralPath $target)) { throw 'compile target missing' }
}
$compileOutput = & .\venv\Scripts\python.exe -m compileall -q @compileTargets 2>&1
$compileExit = $LASTEXITCODE
$compileOutput | ForEach-Object { $_ }
$missingOutput = $compileOutput | Select-String -Pattern 'Can.t list|Can.t open|No such file|target missing|target not compiled' -CaseSensitive:$false
if ($compileExit -ne 0 -or $missingOutput) { throw 'compileall failed or did not compile every requested target' }
```

Full suite 必须以 exit code 0 完整结束；`Ran N tests` 之前的 import/collection error 是失败。compileall 出现 `Can't list`、`Can't open`、`No such file`、target missing/not compiled 或等价信息时，即使 process exit code 是 `0` 也必须失败。

### 14.2 Critical Legacy Regression Suite

下列 52 个 existing test 是 AM7-R01 的固定 Critical 名单，覆盖 calibration/mouse、keyword、R02—R07、Stage-0/store/replay、action safety、focus、browser/stop。测试名不得替换为“相似测试”。

```powershell
$criticalTests = @(
  'tests.test_calibration_profiles.CalibrationProfileTests.test_profile_dict_roundtrip_validates_schema_and_areas',
  'tests.test_calibration_steps.CalibrationStepsTests.test_order_keeps_candidate_forward_filter_stage_sequence',
  'tests.test_calibration_template.CalibrationTemplateTests.test_successful_generation_saves_all_registered_areas',
  'tests.test_mouse_motion.HumanMouseMotionTests.test_default_mode_uses_windmouse_branch',
  'tests.test_mouse_motion.HumanMouseMotionTests.test_human_click_does_not_press_when_movement_fails',
  'tests.test_ocr_text.OCRTextTests.test_exact_match_accepts_keyword_split_across_ocr_lines',
  'tests.test_ocr_text.OCRTextTests.test_exact_match_does_not_use_fuzzy_similarity',
  'tests.test_ocr_detector.DetailPageLoadHelperTests.test_five_boxes_thirty_characters_is_loaded',
  'tests.test_ocr_detector.DetailPageLoadHelperTests.test_items_below_confidence_are_excluded',
  'tests.test_ocr_detector.ScreenFingerprintTests.test_hash_is_lowercase_sha256_of_utf8_normalized_text',
  'tests.test_ocr_detector.DetectorTests.test_keyword_on_later_screen_is_confirmed',
  'tests.test_ocr_detector.DetectorTests.test_backend_failure_is_fail_closed',
  'tests.test_ocr_detector.SafeFullReturnTests.test_safe_never_ends_for_no_new_but_full_requires_two_slots',
  'tests.test_ocr_detector.SafeFullStorePriorityTests.test_full_callback_exception_aborts_before_scroll_or_normal_end',
  'tests.test_ocr_detector.ConfirmationCaptureTypeTests.test_changed_confirmation_is_single_record_no_double_save',
  'tests.test_ocr_normalization.OcrGeometryAdapterTests.test_invalid_bbox_shapes_have_sanitized_error_codes',
  'tests.test_ocr_normalization.OcrReadingOrderTests.test_shuffled_input_is_stable_when_original_indexes_are_stable',
  'tests.test_ocr_normalization.OcrTextNormalizationTests.test_engine_screen_raw_text_is_retained_character_for_character',
  'tests.test_ocr_normalization.OcrComparisonTextTests.test_r04_contract_remains_stable_after_r05_schema_activation',
  'tests.test_ocr_normalization.OcrDuplicateDetectionTests.test_normalized_result_suppresses_only_derived_duplicate',
  'tests.test_ocr_aggregation.AggregationConfigTests.test_default_snapshot_restore_and_digest_are_stable',
  'tests.test_ocr_aggregation.ExactBoundaryOverlapTests.test_partial_large_and_complete_screen_overlap_are_longest_first',
  'tests.test_ocr_aggregation.FuzzyBoundaryOverlapTests.test_1_to_2_and_2_to_1_preserve_group_source_mapping',
  'tests.test_ocr_aggregation.HistoricalAndAggregatorTests.test_aggregator_preserves_uncertain_for_out_of_order_and_empty_completed',
  'tests.test_ocr_similarity.SimilarityConfigTests.test_snapshot_round_trip_and_digest_are_stable',
  'tests.test_ocr_similarity.NgramAndSimHashTests.test_simhash_hamming_golden_and_empty_contract',
  'tests.test_ocr_similarity.R05AccountingTests.test_recomputes_r05_partition_counts_and_ratios_without_mutation',
  'tests.test_ocr_similarity.EffectiveNewTests.test_uncertain_and_illegal_evidence_are_fail_open',
  'tests.test_ocr_similarity.OnlineR06IntegrationTests.test_record_mode_evaluates_once_after_r05_and_summarizes_saved_results',
  'tests.test_ocr_records.OcrRecordModelTests.test_screen_round_trip_preserves_raw_text_bbox_enum_and_nulls',
  'tests.test_ocr_records.OcrRecordModelTests.test_r07_screen_fields_round_trip_and_r06_reader_defaults_unknown',
  'tests.test_ocr_records.OcrRecordModelTests.test_candidate_document_round_trip_has_no_fake_aggregation',
  'tests.test_ocr_candidate.CandidateOcrBuilderTests.test_deferred_screen_state_commits_only_after_store_success',
  'tests.test_ocr_candidate.CandidateOcrBuilderTests.test_r06_projection_failure_does_not_half_commit_context',
  'tests.test_ocr_candidate.CandidateOcrBuilderTests.test_eight_formal_screens_report_completed_with_limit',
  'tests.test_ocr_store.JsonlOcrRecordStoreTests.test_record_mode_persists_manifest_and_final_r05_screen_before_candidate',
  'tests.test_ocr_store.JsonlOcrRecordStoreTests.test_repeated_disk_failures_disable_store_without_infinite_retry',
  'tests.test_ocr_store.JsonlOcrRecordStoreTests.test_error_context_discards_unapproved_text_fields',
  'tests.test_ocr_replay.OcrRunReaderTests.test_online_record_and_offline_replay_have_identical_r04_fields',
  'tests.test_ocr_replay.OcrRunReaderTests.test_r06_online_store_replay_and_sidecar_are_identical_for_synthetic_records',
  'tests.test_ocr_replay.OcrRunReaderTests.test_dynamic_end_replay_replays_no_new_and_never_confirms_bottom',
  'tests.test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_detector_callback_saves_formal_and_confirmation_without_extra_ocr',
  'tests.test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_shadow_detector_never_enters_upper_action_finalize_next_or_refresh_flow',
  'tests.test_ocr_stage0_integration.Stage0MainFlowIntegrationTests.test_full_two_healthy_changed_no_new_screens_finalize_candidate',
  'tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_no_forward_mode_never_calls_real_forward',
  'tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_favorite_mode_keyword_hit_calls_favorite_action_only',
  'tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_ocr_failure_never_calls_real_forward',
  'tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_legacy_focus_restore_entry_uses_safe_region_not_ocr_body',
  'tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_r07_detector_receives_shared_safe_focus_restore_callback',
  'tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_perform_favorite_action_restores_focus_after_favorite_click',
  'tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_stop_prevents_new_navigation_actions',
  'tests.test_simple_brush_ocr.BossBrowserWindowTests.test_bring_boss_foreground_prefers_chrome_over_edge_regardless_of_enum_order'
)
& .\venv\Scripts\python.exe -m unittest -v @criticalTests
if ($LASTEXITCODE -ne 0) { throw 'Critical 52 regression failed' }
```

### 14.3 AM7-R01 新增 guard / Golden tests

Change 4 新增且只运行新测试的命令固定为：

```powershell
& .\venv\Scripts\python.exe -m unittest -v tests.test_am7_r01_baseline_metadata tests.test_am7_r01_brand_contract tests.test_am7_r01_golden_replay
if ($LASTEXITCODE -ne 0) { throw 'AM7-R01 guard or Golden test failed' }
```

新测试至少覆盖 metadata schema/commit/tree/relation、C01 的 `absent_pending_human/null/false` 真实边界状态、C02 的 `configured/approved-url/true` 最终状态及 `confirmation.status` 与 boundary 独立性、active surface 品牌与保留的 Legacy identifiers、fixture privacy guard、strict load、expected digest 和完整 replay comparison。新增测试先通过后，再运行 Critical 和 Full；不能用新测试替代 Legacy suite。

### 14.4 Protected diff guard

```powershell
$baseline = 'a7c941989a038d7a998ccee707e14b4fd9125cda'
git diff --exit-code $baseline -- ocr_detector.py ocr_text.py ocr_normalization.py ocr_aggregation.py ocr_similarity.py ocr_records.py ocr_candidate.py ocr_store.py ocr_replay.py ocr_similarity_sidecar.py ocr_calibration.py calibration_profiles.py calibration_steps.py calibration_template.py mouse_motion.py ocr_fixture_demo.py ocr_mac_demo.py tests/benchmark_r04_normalization.py tests/benchmark_r05_aggregation.py tests/benchmark_r06_similarity.py
git diff --exit-code $baseline -- tests/test_calibration_profiles.py tests/test_calibration_steps.py tests/test_calibration_template.py tests/test_mouse_motion.py tests/test_ocr_aggregation.py tests/test_ocr_calibration.py tests/test_ocr_candidate.py tests/test_ocr_detector.py tests/test_ocr_normalization.py tests/test_ocr_records.py tests/test_ocr_replay.py tests/test_ocr_similarity.py tests/test_ocr_stage0_integration.py tests/test_ocr_store.py tests/test_ocr_text.py
$startupMenuTestDiff = @(git diff -U0 $baseline -- tests/test_simple_brush_ocr.py)
$startupMenuTestDiff | ForEach-Object { $_ }
$startupMenuRemoved = @($startupMenuTestDiff | Where-Object { $_ -match '^-' -and $_ -match 'assertIn' -and $_ -match '开始运行 BossOCR' })
$startupMenuAdded = @($startupMenuTestDiff | Where-Object { $_ -match '^\+' -and $_ -match 'assertIn' -and $_ -match '开始运行 Ocria Am7' })
$startupMenuOtherChanges = @($startupMenuTestDiff | Where-Object {
  $_ -match '^[+-]' -and $_ -notmatch '^---|^\+\+\+' -and
  -not ($_ -match '^-' -and $_ -match 'assertIn' -and $_ -match '开始运行 BossOCR') -and
  -not ($_ -match '^\+' -and $_ -match 'assertIn' -and $_ -match '开始运行 Ocria Am7')
})
if ($startupMenuRemoved.Count -ne 1 -or $startupMenuAdded.Count -ne 1 -or $startupMenuOtherChanges.Count -ne 0) {
  throw 'tests/test_simple_brush_ocr.py exceeds the one approved startup-menu brand expectation migration'
}
git diff --check
git diff --cached --check
git diff --check $baseline -- .
$trackedChanges = @(git diff --name-only $baseline -- .)
$untrackedFiles = @(git ls-files --others --exclude-standard)
$deletedTracked = @(git diff --name-only --diff-filter=D $baseline -- .)
$worktreeStatus = @(git status --porcelain --untracked-files=all)
$ignoredEntries = @(git status --short --ignored --untracked-files=all)
$trackedChanges
$untrackedFiles
$deletedTracked
$worktreeStatus
$ignoredEntries
```

前两条 Frozen/source 与 15 个完全冻结的 existing-test 文件必须无 diff；`tests/test_simple_brush_ocr.py` 只允许上述一删一增的 startup-menu 品牌 expectation migration。三条 whitespace guard 分别覆盖 unstaged、staged，以及 baseline→当前 tracked working-tree 状态，均须 exit `0`。`$trackedChanges` 与 `$untrackedFiles` 必须分别逐项匹配当前 Change allowed-file manifest；`$deletedTracked` 必须为空，除非当前 Change 的精确 allowlist 明文授权删除（AM7-R01 当前没有此类授权）；`$worktreeStatus` 用于证明这些分类完整。`$ignoredEntries` 必须逐项归类为已知 venv/cache/runtime/build output，不得拿 ignored 状态隐藏 source、test、config 或范围外文件。任何 scope 外新增/删除文件都是 FAIL；不得执行 `git clean`、删除、移动或自动清理 unknown 用户文件，只停止并报告。

对 C03 的精确 migration scope 另执行并保存逐文件 hunk：

```powershell
$c03MigrationFiles = @(
  'simple_brush.py','setup.bat','start.bat','build-windows.bat','BossOCR.spec',
  '.github/workflows/windows-release.yml','docs/README.md','README.md'
)
foreach ($file in $c03MigrationFiles) {
  git diff -U0 $baseline -- $file
  if ($LASTEXITCODE -ne 0) { throw 'failed to produce C03 scoped diff' }
}
```

除 `tests/test_simple_brush_ocr.py` 中 `StartupMenuTests.test_interactive_menu_shows_and_run_delegates_to_existing_flow` 的唯一 expectation `开始运行 BossOCR`→`开始运行 Ocria Am7` 外，baseline existing tests 必须 byte-for-byte 相同。该例外只允许更新品牌显示 expectation，不允许修改 test logic、structure、coverage、control-flow/CLI/behavior assertion；该方法其余 assertions 和所有 OCR/R02—R07 tests 不变。`simple_brush.py` 只允许第 9.2 节三个字符串；上述每个 migration hunk 必须人工核对为 §9.2 授权项。Change evidence 必须分别保存 tracked、untracked、ignored 三类清单及其 manifest decision，不能只保存合并后的 `git status`。

### 14.5 Active brand audit

C03 结束及 C05 最终 tree 必须从 repository root 执行以下 scoped audit。它只扫描 active product surfaces，不把全仓出现 `BossOCR` 简化为失败：

```powershell
$activeBrandFiles = @(
  'simple_brush.py','setup.bat','start.bat','build-windows.bat','BossOCR.spec',
  '.github/workflows/windows-release.yml','docs/README.md','README.md'
)
foreach ($file in $activeBrandFiles) {
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'active brand target missing' }
}

$brandExpected = @{
  'simple_brush.py' = @('Prompt an interactive user to run Ocria Am7, calibrate, or exit.','1. 开始运行 Ocria Am7','Ocria Am7 启动')
  'setup.bat' = @('Ocria Am7 - 环境初始化')
  'start.bat' = @('Ocria Am7','Chrome','Edge')
  'build-windows.bat' = @('dist\Ocria\Ocria.exe','release\Ocria-Am7-Windows-x64.zip','BossOCR.spec')
  '.github/workflows/windows-release.yml' = @('name: Ocria Am7 Windows Release','ocria-am7-v*','dist\Ocria\Ocria.exe','release\Ocria-Am7-Windows-x64.zip','name: Ocria-Am7-Windows-x64','BossOCR.spec','--notes-file release-notes\Issue-1-BossOCR-release-notes.md')
  'docs/README.md' = @('# Ocria Am7','Ocria.exe','Ocria-Am7-Windows-x64.zip')
  'README.md' = @('# Ocria Am7')
}
foreach ($file in $brandExpected.Keys) {
  $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $file
  foreach ($expected in $brandExpected[$file]) {
    if (-not $text.Contains($expected)) { throw 'required Ocria active identity missing' }
  }
}

$brandForbidden = @{
  'simple_brush.py' = @('Prompt an interactive user to run BossOCR, calibrate, or exit.','1. 开始运行 BossOCR','BOSS 直聘极简刷简历 v4 启动')
  'setup.bat' = @('BOSS 直聘自动刷简历 - 环境初始化')
  'start.bat' = @('BOSS 直聘自动刷简历')
  'build-windows.bat' = @('dist\BossOCR\BossOCR.exe','release\BossOCR-Windows-x64.zip')
  '.github/workflows/windows-release.yml' = @('issue-*-v*','dist\BossOCR\BossOCR.exe','release\BossOCR-Windows-x64.zip','name: BossOCR-Windows-x64','Issue #1 BossOCR minimal changes v1.0','--generate-notes')
  'docs/README.md' = @('# BossOCR','BossOCR.exe','BossOCR-Windows-x64.zip')
  'README.md' = @('# BossOCR','BossOCR.exe','BossOCR-Windows-x64.zip')
}
foreach ($file in $brandForbidden.Keys) {
  $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $file
  foreach ($forbidden in $brandForbidden[$file]) {
    if ($text.Contains($forbidden)) { throw 'stale active BossOCR product identity found' }
  }
}

$specLines = Get-Content -Encoding UTF8 -LiteralPath 'BossOCR.spec'
$specNameAssignments = @($specLines | Where-Object { $_ -match '^\s*name\s*=' })
$specOcriaAssignments = @($specNameAssignments | Where-Object { $_ -match '^\s*name\s*=\s*['']Ocria['']\s*,?\s*$' })
if ($specNameAssignments.Count -ne 2 -or $specOcriaAssignments.Count -ne 2) { throw 'spec active name assignments failed' }
$workflowText = Get-Content -Raw -Encoding UTF8 -LiteralPath '.github/workflows/windows-release.yml'
if ([regex]::Matches($workflowText, '--notes-file\s+release-notes\\Issue-1-BossOCR-release-notes\.md').Count -ne 1) { throw 'retained workflow notes-file contract changed' }

$bossOcrResiduals = foreach ($file in $activeBrandFiles) {
  Select-String -LiteralPath $file -Pattern 'BossOCR' -CaseSensitive | ForEach-Object {
    [pscustomobject]@{ file = $file; line = $_.LineNumber; text = $_.Line.Trim() }
  }
}
$residualViolations = foreach ($item in $bossOcrResiduals) {
  $allowed = switch ($item.file) {
    'build-windows.bat' { $item.text -match 'PyInstaller.*BossOCR\.spec'; break }
    '.github/workflows/windows-release.yml' { $item.text -match 'BossOCR\.spec|--notes-file release-notes\\Issue-1-BossOCR-release-notes\.md'; break }
    'docs/README.md' { $item.text -match '来源|源基线|派生|provenance|fallback|回退|Legacy|历史|产品线|Boss-OCR|BossOCR\.spec'; break }
    'README.md' { $item.text -match '来源|源基线|派生|provenance|fallback|回退|Legacy|历史|产品线|Boss-OCR|BossOCR\.spec'; break }
    default { $false }
  }
  if (-not $allowed) { $item }
}
$bossOcrResiduals | Format-Table -AutoSize
if (@($residualViolations).Count -ne 0) { $residualViolations | Format-Table -AutoSize; throw 'unclassified BossOCR residual in active surface' }
```

PASS 要求所有 expected/forbidden/exact-count assertions 通过，且每条 case-sensitive `BossOCR` residual 只属于：`BossOCR.spec` 冻结文件名、精确保留的 workflow notes path，或 README 中明确写明的 BossOCR source/provenance/Legacy fallback/history。`BOSS 直聘`、窗口 title 规则、`bring_boss_*`、`_bossocr_console_handler` 等业务名或冻结内部标识允许保留；历史 docs 不在 active scan scope 且保持不改。出现无法按上述类别解释的 active residual、缺失目标、旧 EXE/archive/title/tag/artifact 字样，均为 FAIL。保存命令输出和逐条 residual classification 到 EB-07；不得用全仓 `rg BossOCR` 的命中数代替本 gate。

### 14.6 Build 与安全 executable smoke

Change 5 使用：

前置条件是隔离的 build/smoke session 中没有符合真实 product predicate 的 Chrome/Edge 窗口，也没有可被自动化接触的已登录真实页面。每次 executable smoke 前必须先运行同一 frozen predicate 的只读预检：

```powershell
function Assert-NoMatchedBossBrowserWindow {
  $preflightCode = @'
import sys
import win32gui
import simple_brush as app

hits = []
def visit(hwnd, _):
    if win32gui.IsWindowVisible(hwnd):
        title = win32gui.GetWindowText(hwnd)
        process_name = app.get_window_process_name(hwnd)
        if app.is_boss_browser_window(title, process_name):
            hits.append(process_name)
    return True

win32gui.EnumWindows(visit, None)
print('matching_boss_browser_windows={0}'.format(len(hits)))
for process_name in sorted(set(hits)):
    print('matching_process={0}'.format(process_name))
raise SystemExit(1 if hits else 0)
'@
  $preflightOutput = @(& .\venv\Scripts\python.exe -c $preflightCode 2>&1)
  $preflightExit = $LASTEXITCODE
  $preflightOutput | ForEach-Object { $_ }
  if ($preflightExit -ne 0) { throw 'safe smoke preflight failed or found a matched BOSS browser window' }
}

Assert-NoMatchedBossBrowserWindow
cmd /c build-windows.bat
if ($LASTEXITCODE -ne 0) { throw 'build-windows.bat failed' }
Assert-NoMatchedBossBrowserWindow
& .\dist\Ocria\Ocria.exe --no-forward --auto --duration-seconds 0
if ($LASTEXITCODE -ne 0) { throw 'external safe executable smoke failed' }
```

预检 import `simple_brush` 只读取窗口枚举与 frozen predicate；baseline import 不配置文件日志、不启动 keyboard listener、不调用 `run()`。输出只记录匹配数量/进程名，不记录可能含候选信息的窗口标题。枚举失败、import 失败或命中数量非零均为 Stop，且不得继续调用 build/smoke。build 开始至其内置 smoke 完成期间必须保持独占、无人打开 Chrome/Edge 的隔离 session；无法维持这一不变量则不运行 `build-windows.bat`。

`--duration-seconds 0` 的真实语义是“不创建自动停止 timer、持续运行”，不是立即退出或安全保证。安全性来自预检为零且 `bring_boss_foreground()` 在无匹配窗口时返回 `False`，使 `run()` 在首个候选点击、筛选、OCR 和 action 之前以 `0` 返回。`build-windows.bat` 自身包含 Full suite、PyInstaller 和相同参数的 smoke；外部在第二次预检后再调用一次形成独立验收证据。命令不得带 keywords/email，不进入真实 BOSS action，也不是 Manual Real Page Smoke。出现预检误差、进程未按预期返回或任何真实页面动作，立即停止并判定 FAIL。

### 14.7 ZIP、one-dir 与 local checksum audit

C05 明确授权在 ignored `release/` 中生成本地 `Ocria-Am7-Windows-x64.zip.sha256`；它是 local automated acceptance artifact，不是 GitHub workflow run 或 release artifact。build 与两次 safe smoke 通过后执行：

```powershell
$distRoot = (Resolve-Path -LiteralPath '.\dist\Ocria').Path
$exePath = Join-Path $distRoot 'Ocria.exe'
$archivePath = (Resolve-Path -LiteralPath '.\release\Ocria-Am7-Windows-x64.zip').Path
$checksumPath = '.\release\Ocria-Am7-Windows-x64.zip.sha256'
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw 'dist Ocria executable missing' }
if (Test-Path -LiteralPath '.\dist\BossOCR') { throw 'stale BossOCR distribution directory present' }
if (Test-Path -LiteralPath '.\release\BossOCR-Windows-x64.zip') { throw 'stale BossOCR archive present' }

$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToUpperInvariant()
Set-Content -LiteralPath $checksumPath -Value $archiveHash -Encoding ASCII
$checksumText = (Get-Content -Raw -Encoding ASCII -LiteralPath $checksumPath).Trim()
if ($checksumText -notmatch '^[0-9A-F]{64}$' -or $checksumText -ne $archiveHash) { throw 'local checksum sidecar mismatch' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
  $zipFiles = @($zip.Entries | Where-Object { $_.Name } | ForEach-Object { $_.FullName.Replace('\','/') } | Sort-Object)
}
finally {
  $zip.Dispose()
}
if ($zipFiles.Count -le 1) { throw 'archive is not a one-dir package' }
if (@($zipFiles | Where-Object { $_ -eq 'Ocria.exe' }).Count -ne 1) { throw 'archive must contain one root Ocria.exe' }
if (@($zipFiles | Group-Object | Where-Object { $_.Count -gt 1 }).Count -ne 0) { throw 'archive contains duplicate file entries' }
if (@($zipFiles | Where-Object { $_ -match '(^/|^[A-Za-z]:|(^|/)\.\.(/|$))' }).Count -ne 0) { throw 'archive contains absolute or parent traversal entry' }
if (@($zipFiles | Where-Object { $_ -match '(?i)(^|/)BossOCR[^/]*($|/)' }).Count -ne 0) { throw 'archive contains stale BossOCR user artifact identity' }

$distFiles = @(Get-ChildItem -LiteralPath $distRoot -Recurse -File | ForEach-Object {
  $_.FullName.Substring($distRoot.Length).TrimStart([char]'\').Replace('\','/')
} | Sort-Object)
$packageDiff = @(Compare-Object $distFiles $zipFiles)
if ($distFiles.Count -le 1 -or $packageDiff.Count -ne 0) { throw 'ZIP contents do not exactly match dist Ocria one-dir files' }

[pscustomobject]@{
  executable = $exePath
  archive = $archivePath
  sha256 = $archiveHash
  dist_file_count = $distFiles.Count
  zip_file_count = $zipFiles.Count
}
$zipFiles
```

PASS 要求 `dist\Ocria\Ocria.exe` 存在；旧 `dist\BossOCR`/BossOCR archive 不存在；ZIP 根恰有一个 `Ocria.exe`、含其 one-dir companions、无绝对/父路径/重复项/旧 BossOCR 用户产物名；ZIP 文件集合与 `dist\Ocria\` 递归文件集合精确相等；sidecar 是本次 archive 的 64 位 SHA-256。该 gate 不解包、不写未定义临时位置，保存 package inventory 与 hash 到 EB-06。workflow 仍按其原有 PowerShell 步骤生成同名 `.sha256`；AM7-R01 不执行 workflow、上传或发布，也不把 local sidecar 伪装成 workflow/release evidence。

## 15. AM7-R01 最终 Acceptance 证据

| Evidence ID | 必需材料 | 通过条件 |
|---|---|---|
| EB-01 | Source baseline JSON/报告、Git/ref/release/asset 核对日志 | 唯一 commit/tree/tag/release/hash；人工签署；无占位值 |
| EB-02 | `git remote -v`、upstream push URL、ancestor check、provenance | `origin` 指向人工批准的独立 Ocria repository；`bossocr-upstream` 保持 BossOCR fetch source 且 push 禁用；metadata 为 `configured`；本 Requirement 未发生 push |
| EB-03 | `LEGACY-FREEZE-MATRIX.md`、allowed-file manifest、baseline diff、tracked/untracked/ignored 分类清单 | Frozen files 0 diff；除唯一批准的 C03 startup-menu 品牌 expectation 外既有 tests 0 diff；migration hunk 及所有新增文件全部在对应 Change 清单内；whitespace guards 通过 |
| EB-04 | Critical 52 项、Full suite、三 benchmark、compileall、pip check 原始脱敏日志 | Full/Critical/compile/pip process 通过；三 benchmark 同时满足 exit 0 与第 14.1.1—14.1.3 节 output contract；0 failure/error；无未解释 skip/collection/target-missing |
| EB-05 | synthetic fixture review、privacy review、Golden test/replay digest | strict load/replay/expected 全等；无真实业务数据；expected 未因失败而重写 |
| EB-06 | PyInstaller/build log、两次窗口预检、safe smoke、local archive/`.sha256`、ZIP 与 dist inventory | `dist\Ocria\Ocria.exe`；两次预检 0 match、smoke 0；ZIP 与 one-dir 文件集合全等；无 BossOCR 用户产物名；hash 相等；未上传/发布 |
| EB-07 | 第 14.5 节 active-surface brand audit 原始输出、residual classification 与 README review | required/forbidden/exact-count assertions 全通过；用户身份为 Ocria Am7；只保留 provenance/BOSS 网站/Legacy identifiers/notes path 等明确 residual |
| EB-08 | 人工填写的 Manual Real BOSS Page Smoke checklist | MS-01..12 Pass；favorite/forward 各有 controlled 或人工批准 equivalent；执行者/批准者签名 |
| EB-09 | Change 1..5 evidence index、command manifest/transcript、最终 commit/tree、三类 workspace 清单、Acceptance report | 顺序/依赖可追溯；0 push 由 transcript 证明；无范围外文件；所有 Open/Stop 项关闭或明确阻断 |

`docs/am7/acceptance/AM7-R01-acceptance-report.md` 必须逐条映射 RPD AC-01..AC-20 到 Evidence ID、路径、结果和人工决定。自动化执行者最多将状态写成 `Automated Gates Passed / Pending Human Smoke`，不得自行把 AM7-R01 标为最终 Accepted。只有 EB-08 的人工结果和最终人工审查完成后才能批准。

### 15.1 RPD AC-01—AC-20 可执行映射

| AC | Implementation / contract location | 必需证据 | EB |
|---|---|---|---|
| AC-01 | §4.1—4.2、§5.1、C01 | baseline JSON/报告记录 source repository/branch/full SHA，远端 ref 核验及人工批准 | EB-01 |
| AC-02 | §4.2、§5.1、C01 | commit subject/time、confirmation time、tree/tag/release/timestamp/assets | EB-01 |
| AC-03 | §4.2 confirmation criteria、§14.1、C01 | Git/release/hash 四向一致、ancestry、当前独立 regression 与人类 stable rationale；不得以 latest/main 单独证明 | EB-01、EB-04 |
| AC-04 | §5.2、C02 | clone 后可读 `PROVENANCE.md` 与 baseline relationship metadata | EB-02 |
| AC-05 | §5.3、C02 | approved Ocria origin、BossOCR fetch-only/no-push、rewrite audit、0-push transcript、configured metadata | EB-02、EB-09 |
| AC-06 | §9、§14.5、§14.7、C03/C05 | scoped active-brand assertions/residual review、Ocria EXE/dist/archive/inventory | EB-06、EB-07 |
| AC-07 | §2、§6、§9.2、§14.4、C03 | allowed-file/hunk manifest、protected diff 与 review 证明无 GUI/AI/大重命名 | EB-03、EB-07 |
| AC-08 | §7—§8、§14.1—14.4、§12.3、C03—C05 | Frozen files 0 diff、除唯一批准品牌 expectation 外 existing tests 0 diff、Full/Critical/benchmark/Golden、最终人工 observable-behavior smoke | EB-03、EB-04、EB-05、EB-08 |
| AC-09 | §6、C04 | 四区精确文件/区域矩阵及人工 review | EB-03、EB-09 |
| AC-10 | §8、C04 | Algorithm/Parameter/Schema/Observable 四类对象、禁止变化、授权与 regression 对照 | EB-03、EB-04、EB-05 |
| AC-11 | §7.1—7.2、§14.4、C04 | 真实函数级 Protected Boundary、整文件/三字符串例外与 zero-diff guard | EB-03 |
| AC-12 | §2、§14.4、C01/C03/C04/C05 | 除唯一批准的 C03 startup-menu 品牌 expectation migration 外，baseline→final existing tests byte-identical；manifest 与 Full collection 证据 | EB-03、EB-04 |
| AC-13 | §14.1、C05 | 最终 tree Full raw log、实际 count、0 failure/error、无 collection/unreviewed skip | EB-04 |
| AC-14 | §14.2、C05 | 固定 52 qualified names 解析并在最终 tree 全通过 | EB-04 |
| AC-15 | §11、§14.3、C04 | synthetic fixture/digest/strict replay、privacy scan 与人工 privacy review | EB-05 |
| AC-16 | §13.2、§14、C01—C05 | 每份日志的 commit/environment/command/scope/result/time；自动与真实页面作用域明确分离 | EB-01—EB-07、EB-09 |
| AC-17 | §12.1—12.2、C04 | 版本化 checklist 模板、human-only 标识及人工审查 | EB-08、EB-09 |
| AC-18 | §12.3、C05 handoff | 最终 commit 上人工 MS-01..12；favorite/forward 各有受控动作或批准的等价安全证据 | EB-08 |
| AC-19 | §2、§12.1、§14.6、C05 | safe automation 明示非 real-page smoke；人工 executor/approver/signature 与 handoff 记录 | EB-06、EB-08、EB-09 |
| AC-20 | §15、C05 | acceptance report 对 AC-01..20/EB-01..09/路径/结果/人工决定全映射，阻塞项关闭或由新 Requirement 明确承接 | EB-01—EB-09 |

0.5 静态设计复核结论：此前不完整的 AC-06（active identity/package gate）、AC-08（行为回归证据链）、AC-09（四区矩阵）、AC-10（四类 Freeze）、AC-11（真实函数级边界）、AC-16（机器可判定命令与证据头）、AC-20（逐 AC/EB 闭环）已在合同层闭合。这里的“闭合”只表示 TID 已定义可执行路径；实际 Evidence 和人工决定仍须在 C01—C05 与最终人工 Smoke 中产生，不得预先标为通过。

## 16. 最终 Change 计划

最终数量固定为 5，顺序固定为 C01→C02→C03→C04→C05。不得并行合并 C01/C02 与品牌 Change；C05 不得在 C04 之前执行。每个 Change 结束先审查 evidence，再进入下一项。

### C01 — 文档版本化与 Source Baseline 锁定

**目标**：在尚无产品差异的 V1.3.1 tree 上完成独立复验，建立 AM7 文档 allowlist，并持久化唯一 baseline。

**允许修改**：`.gitignore`；当前 AM7-R01 RPD/TID 的 tracked state；新 `docs/am7/README.md`、`docs/am7/baselines/AM7-R01-source-baseline.json`、同名 `.md`、`docs/am7/acceptance/evidence/AM7-R01-C01/**`。

**禁止修改**：所有 `.py`、既有/新增 tests、requirements、BAT/spec/workflow、`docs/README.md`、历史 docs、`.git/config`；禁止创建 remote、commit tag、push、release。

**前置条件**：TID 已 Approved；Ocria pristine `HEAD` 尚为 `a7c9419...`；`V1.3.1` 尚精确指向该 commit；GitHub 可核验；Python 3.11 x64 和完整依赖可建立；人工同意 baseline 候选；已运行并人工审查 `git status --porcelain --untracked-files=all` 与 `git status --short --ignored --untracked-files=all`，所有允许项都属于第 4.2 节明确类别。

**顺序**：先执行第 4.2 节完整 tracked/untracked/ignored 清洁审计；确认没有未知行为影响项后，才在 pristine tree 执行第 13、14.1 节并保存脱敏结果；全部通过后再编辑 `.gitignore` 和 baseline 文档。`confirmation.status` 最后写入，且必须有 human approver。

**Stop Conditions**：按第 13.3 节分类。Ocria `HEAD` 或 `V1.3.1` 偏离候选 baseline；commit/tree/release/hash 不一致；baseline 不是当前 `bossocr-upstream/main` 的 ancestor；检测到 tag 漂移、history rewrite 或来源关系无法证明；origin/source 不明；工作区有未解释 tracked diff；存在可能影响 Python import、test discovery、configuration 或 runtime behavior 的未知 untracked/ignored 文件；collection/full/benchmark contract/compile/pip 任一真实性失败；发现 source evidence 含敏感凭据；人工不批准，均为 True Stop。`bossocr-upstream/main` 仅向前推进且 ancestry 成立时不停止，只记录。隔离 venv 重建和有记录的瞬态依赖准备故障可按 §13.3/§14.1 在 C01 内处理；不得把 Legacy/合同失败归类为环境问题。发现文件时只报告并停止，不执行清理。

**自动化与验收**：执行 §4.2 的 remote tag/release/asset/checksum 四向核验、§14.1 Full/三个 benchmark output contracts/compileall/pip、§14.4 完整 whitespace 与 workspace 分类 guard；`git check-ignore -v` 必须证明 RPD/TID/`docs/am7/**/*.md` 不再忽略且 `data/ocr_runs`/logs 仍忽略；baseline JSON 可解析且精确值匹配，记录 C01 观测到的 `bossocr-upstream/main` SHA 及关系，并如实保持 `origin_status=absent_pending_human`、`origin_url=null`、`upstream_push_disabled=false`。Source Baseline 可在这一 boundary Pending 状态下 confirmed。输出 EB-01 和 C01 evidence，Frozen/生产/测试文件 0 diff。

### C02 — Provenance 与独立 Repository/Remote 边界

**目标**：持久化 Ocria←BossOCR 关系，阻断本地对 BossOCR upstream 的 push，并对 Ocria origin 采用人类授权、不猜测的状态模型。

**允许修改**：新 `docs/am7/PROVENANCE.md`；`docs/am7/README.md`；baseline JSON 的 `repository_boundary`/evidence refs；`docs/am7/acceptance/evidence/AM7-R01-C02/**`；本地 `.git/config` 仅限 `bossocr-upstream.pushurl` 和经人工批准的 `origin`。

**禁止修改**：生产/测试/build/packaging/workflow/requirements、历史 docs；禁止创建 GitHub repository、选择组织/namespace、改写历史、push/fetch 后 merge、向 BossOCR push。无批准 URL 时禁止 `git remote add origin`。

**前置条件**：C01 Accepted；baseline metadata 已 confirmed；remote 仍只有审计到的边界或差异已交人工。C02 可在尚无 URL 时先完成只读核对和 Pending metadata，但最终配置与 Acceptance 前必须由人工创建/提供并书面批准独立 Ocria repository URL。

**Stop Conditions**：尚未提供人工批准的独立 Ocria URL 时，状态为 `BLOCKED / Pending Human Repository Setup`，停止并等待人工，不创建 repository、不猜测 URL；`bossocr-upstream` fetch URL 不再是已核对来源；存在未知 `url.*.insteadOf`/`pushInsteadOf` rewrite；已有 origin 与批准 URL 不同；设置 no-push 后仍解析到 BossOCR push URL；基线不再是 HEAD ancestor；任何命令要求 push 或由 Terra 创建外部 repository。

**自动化与验收**：执行第 5.3 节 remote/ancestor 命令。C02 最终通过同时要求：人工已创建/提供并批准独立 Ocria repository URL；`origin` 精确指向该 repository；`bossocr-upstream` fetch 保持 BossOCR source；其 push URL 为 `no_push://bossocr-upstream`；metadata 更新为 `origin_status=configured`、`origin_url` 等于人工批准 URL、`upstream_push_disabled=true`；整个 C02 没有执行任何 push；provenance/JSON 一致；tracked code/tests 0 diff。`absent_pending_human` 只能产生 Pending evidence，不能输出 C02 Accepted 或 EB-02 Pass。

### C03 — Ocria Am7 最小 Brand/Build Identity Migration

**目标**：把活跃 CLI、启动/安装、用户文档、Windows build/archive/workflow 的产品身份改为第 9 节统一值，同时保持全部 Legacy 行为。

**允许修改**：`simple_brush.py` 仅第 9.2 节三个显示字符串；`tests/test_simple_brush_ocr.py` 仅 `StartupMenuTests.test_interactive_menu_shows_and_run_delegates_to_existing_flow` 中品牌显示 expectation `开始运行 BossOCR`→`开始运行 Ocria Am7`；`setup.bat`、`start.bat`、`build-windows.bat`、`BossOCR.spec`、`.github/workflows/windows-release.yml` 仅第 9.2 节列项；`docs/README.md`；新根 `README.md`；`docs/am7/acceptance/evidence/AM7-R01-C03/**`。不授权任何 Release Notes 文件：workflow 引用的 `release-notes/Issue-1-BossOCR-release-notes.md` 当前不存在且未跟踪，`docs/Issue-1-BossOCR-release-notes.md` 是未被 workflow 引用的 tracked 历史材料。

**禁止修改**：其余 source；除上述唯一 expectation 外所有既有 test 内容，以及所有新增 test；禁止修改 test logic、structure、coverage、control-flow/CLI/behavior assertion、OCR/R02—R07 tests；禁止修改 requirements、fixture、Legacy docs（包括 `docs/Issue-1-BossOCR-release-notes.md`）、算法/参数/schema/CLI flags、Python/module/function/internal compatibility identifiers；禁止创建或修改 notes 文件、改变 `--notes-file` 路径/来源/生成机制、引入 `--generate-notes`；禁止 rename `simple_brush.py`/`BossOCR.spec`；禁止 tag/push/release/真实页面。

**前置条件**：C01/C02 Accepted；baseline/provenance 可查；allowed-file manifest 已生成；Critical/Full baseline 证据有效。

**Stop Conditions**：需要改变函数控制流或 import 才能完成品牌；需要创建/修改 Release Notes 文件或改变 `--notes-file` 命令、路径、来源、生成机制；grep 出现无法分类的 BossOCR active surface；workflow/build 需要依赖升级；任一 Frozen file 有 diff；任一 existing test 出现超出唯一批准 startup-menu expectation 的 diff；任何回归失败；需要真实页面才能继续。

**自动化与验收**：运行 Critical 52（集合不得减少或替换）、Full、三个 benchmark 的 exit+output contracts、compileall、pip check、§14.4 protected/workspace diff guard、§14.5 active brand audit。`simple_brush.py` diff 必须只有三个字符串；`tests/test_simple_brush_ocr.py` diff 必须只有唯一品牌 expectation 的一删一增，方法内其余 assertions 不变；spec analysis/hidden imports/datas 不变；BAT/workflow 的 test/build/safe-smoke 顺序和 flags 不变；workflow 继续使用原样的 `--notes-file release-notes/Issue-1-BossOCR-release-notes.md` 且不存在 `--generate-notes`；不存在任何新增/修改的 Release Notes 文件。Full Regression 仍必须全部 PASS。此 Change 不要求生成最终包，由 C05 完成。输出 EB-03/EB-07 的 C03 部分。

### C04 — Freeze Contract 与 Golden Regression Barrier

**目标**：把本 TID 的四区/四类 Freeze 固化为可 clone 文档和只增测试；建立纯合成 Golden Store→Replay 防漂移资产。

**允许修改**：新 `docs/am7/LEGACY-FREEZE-MATRIX.md`、`docs/am7/acceptance/AM7-R01-manual-smoke-checklist.md` 模板、`tests/fixtures/am7_r01/**`、`tests/test_am7_r01_baseline_metadata.py`、`tests/test_am7_r01_brand_contract.py`、`tests/test_am7_r01_golden_replay.py`、`docs/am7/acceptance/evidence/AM7-R01-C04/**`。

**禁止修改**：所有生产 source、既有 tests/benchmarks、requirements/build/workflow、Golden 所调用的 Legacy reader/records/algorithms；禁止真实 OCR run/screenshot/log/候选数据；禁止为匹配 expected 改算法或旧断言。

**前置条件**：C03 Accepted 且 protected diff clean；fixture 设计和合成文本由人工预审；baseline config snapshot/digest 已可读取；不存在来源不明的本地 runtime asset。

**Stop Conditions**：fixture 出现 PII/真实业务组合/本机绝对路径；必须从真实页面采集才能覆盖；existing test 被改；测试促使放宽 schema/threshold；性能或 Full/Critical/冻结 Golden 合同失败，均为 True Stop。仅当 mismatch 已证明源自 C04 自己新建 fixture/test 的实现错误，且不改变已人工预审的合成语义、expected contract 或任何禁止区域时，才可按 §13.3 `fix → retest`；原因不明或需要改 Legacy reader/records/algorithm 时立即 Stop。

**自动化与验收**：先运行 §14.3 三个 AM7 test modules，再运行 Critical 52、Full、§14.1.1—14.1.3 benchmark contracts、compileall、pip check、privacy scan 和 §14.4 diff/workspace guard。strict reader 0 issue；candidate canonical digest、各 R04—R07 summary 与 expected 完全相等；人工 privacy review 签署。输出 EB-03/EB-05 和可供人执行但仍 Pending 的 Smoke 模板。

### C05 — Final Automated Acceptance、Build 与 Human Smoke Handoff

**目标**：在最终 tree 上重跑全部自动门禁、生成本地 Ocria Windows 包和摘要，汇总 acceptance；随后停止自动化，把真实页面 checklist 交给人工。

**允许修改**：ignored `build/`、`dist/`、`release/`；`docs/am7/acceptance/evidence/AM7-R01-C05/**`；`docs/am7/acceptance/AM7-R01-acceptance-report.md`；人工执行后由人工更新 Smoke checklist/脱敏 evidence。若只运行验收，生产/测试文件不得再变。

**禁止修改**：所有 source/test/fixture/requirements/build scripts/workflow/provenance/baseline/freeze contract；禁止自动登录/真实页面/收藏/转发；禁止 tag、push、GitHub release、上传 artifact；禁止因 build/test 失败回到文件内修复。修复必须停止 C05，并由人工决定回退到相应 Change。

**前置条件**：C01—C04 Accepted；final diff/allowed manifest 已审；Python 3.11 x64/依赖可复现；本地没有真实页面自动化进程；人工 Smoke 执行者、受控对象/目标或等价方案另行确定。

**Stop Conditions**：任一自动门禁失败；窗口预检不能证明 0 match；build archive 名/内容错误；safe smoke 产生页面动作或未按预期返回；hash/sidecar/ZIP 与 dist one-dir 内容不可复核；工作区出现范围外 diff；证据含敏感内容；没有人类 Smoke 授权时尝试继续真实页面步骤。

**自动化与验收**：AM7 新 tests→Critical 52→Full→三个 benchmark exit+output contracts→compileall→pip check→§14.4 protected/workspace diff→§14.5 active brand audit→§14.6 第一次窗口预检/`build-windows.bat`/第二次预检/独立 safe executable smoke→§14.7 local `.sha256` 与 ZIP/dist one-dir audit。全部通过后只写 `Automated Gates Passed / Pending Human Smoke`。Codex / Terra 此时必须停止。人工完成 MS-01..12 并签署后，人工审查 EB-01..09，才能把 Requirement 最终标为 Accepted。active workflow 的 notes input 仍缺失，所以本验收不证明 workflow 当前可发布。

### 16.1 顺序与依赖摘要

```text
C01 baseline+docs
  → C02 provenance+remote guard
    → C03 minimal brand/build identity
      → C04 freeze+synthetic golden
        → C05 final automation/build
          → human-only real page smoke
            → human final acceptance
```

失败回退规则：先按 §13.3 分类。当前 Change allowlist 内的明确可恢复问题可保留失败证据后 `fix → retest`；True Stop 不得就地绕过。C02 问题回 C02；品牌/active surface 回 C03；fixture/guard 回 C04；C05 发现任何早期范围问题，不在 C05 修，停止并由人工重新授权对应 Change。

## 17. 本次 TID 要求覆盖映射

| 请求项 | TID 位置 |
|---|---|
| 1. Baseline 确认与证据链 | 第 4、13、14 节；C01 |
| 2. Provenance / metadata 持久化 | 第 5.1—5.2 节；C01/C02 |
| 3. 独立 remote/repository 边界 | 第 5.3 节；C02 |
| 4. 四区文件/函数/数据合同 | 第 6 节 |
| 5. 两个核心文件函数级 Protected Boundary | 第 7 节 |
| 6. 四类 Freeze 技术保护对象 | 第 8 节 |
| 7. Brand Migration 精确范围 | 第 9 节；C03 |
| 8. `.gitignore` 与文档版本化 | 第 10 节；C01 |
| 9. Full Legacy Regression 命令 | 第 14.1 节 |
| 10. Critical Suite 名单/命令 | 第 14.2 节 |
| 11. Golden/fixture/隐私/对照 | 第 11、14.3 节；C04 |
| 12. 人工真实页面 Smoke 格式 | 第 12 节；C04/C05 |
| 13. Change 数量、顺序、依赖 | 第 16、16.1 节 |
| 14—19. 每个 Change 的目标、允许/禁止、前置、Stop、测试/验收 | C01—C05 各段 |
| 20. 最终 Acceptance 证据 | 第 15 节 |

逐项 Acceptance 的 implementation/evidence/EB 精确映射见 §15.1；第 17 节只保留最初 TID 工作项索引，不替代 AC-01—AC-20 gate。

## 18. TID 审查时仍需人工确认的执行输入

这些不是授权扩大 Scope 的 Open Design：

1. 是否批准 `a7c941989a038d7a998ccee707e14b4fd9125cda` 在 C01 全量复验通过后成为最终 Source Baseline；
2. 独立 Ocria repository URL 何时由人工创建/提供并批准；在此之前只能保持 `origin_status=absent_pending_human`，C02 为 `BLOCKED / Pending Human Repository Setup`；
3. Ocria remote 的 owner/visibility/branch protection 由谁在 AM7-R01 外部创建和批准；
4. synthetic Golden 文本和 expected digest 的人工隐私/语义审查者；
5. Manual Smoke 的人工执行者、受控测试对象/收件目标，或 favorite/forward 各自的等价安全验证批准；
6. 最终 acceptance approver 身份。

若这些输入在对应 Change 前缺失，按该 Change 的规则停止或记录 pending；不得由实现者自行填入。
