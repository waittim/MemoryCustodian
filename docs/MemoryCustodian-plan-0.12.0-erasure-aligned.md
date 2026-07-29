# MemoryCustodian v0.12.0 实施指南

## Protocol 0.8：事务恢复、统一审计、冲突治理、Erasure Contract 与跨 Agent 一致性

你正在继续修改已经完成以下版本的 MemoryCustodian：

* v0.10 / Protocol 0.6

  * Entry ID
  * Evidence
  * Candidate admission
  * Mutation lock
  * Plan ID
  * Trust boundary
* v0.11 / Protocol 0.7

  * Local overlay
  * Deterministic area routing
  * Explain
  * Freshness and reachability audit
  * ID-based operations
  * Canonical Subject registry and Facet
  * Structural conflict detection
  * Merge-aware reconciliation review
  * Explicit exception and Subject merge workflows
  * Unified ErasureScope and optional Git history exposure inspection
  * Accurate local-reset and distributed-copy boundaries

本阶段的目标不是发布 MemoryCustodian 1.0，而是在进入 1.0 之前，对现有能力进行生产化加固和系统性验证。重点是事务恢复、统一审计、跨平台确定性与跨 Agent 一致性；本阶段仍允许在未来通过显式迁移继续调整协议，不作长期冻结承诺。

不要询问更多信息。先检查前两阶段是否完整实现。发现缺失时，应在本任务中补齐，不得绕过或降低验收标准。

目标版本：

* Package version：`0.12.0`
* Protocol version：`0.8`
* Entry schema version：`1`
* Subject schema version：`1`
* Conflict schema version：`1`
* Routing schema version：`1`（继承 Protocol 0.7）
* Local overlay schema version：`1`（仅 local manifest）
* Transaction schema version：`1`
* Audit schema version：`1`
* Output schema version：`1`
* Erasure scope schema version：`1`

---

## 一、v0.12 版本目标与可验证能力

MemoryCustodian v0.12 必须实现并通过仓库内测试、fixtures、audit 与文档证据验证以下能力。只有存在相应实现和验证证据时，README 与 release notes 才能陈述这些能力：

1. Project memory 是 plain Markdown，repo-native，可审查、可 diff。
2. Manifest 是运行时路由的唯一 shared authority。
3. 相同 shared memory、canonical task、paths、explicit areas/rules/profiles 和 local mode 会产生确定的 shared context pack。
4. Active memory 有稳定身份和可审查依据。
5. Agent inference 不会静默升级为正式记忆。
6. 多 agent 同时写入不会静默丢失更新。
7. Preview 后内容变化会阻止旧计划被 Apply。
8. Multi-file mutation 发生进程崩溃后可以检测和恢复。
9. Local preference 不会进入 shared repo。
10. Forgetting 可以按完整语义单元或稳定 ID 执行。
11. Hard forget 与 purge 不泄露被删除 topic。
12. Memory 不会扩大 agent 权限。
13. Protocol 0.5、0.6、0.7 项目存在明确迁移路径。
14. 核心运行不依赖网络、数据库、embedding、daemon 或第三方 runtime package。
15. Codex、Claude Code、Gemini 和 generic agent 使用同一协议与 context pack 规则。
16. 每个 enabled module 都有可审计的 loaded、skipped、missing 或 omitted disposition。
17. 缺少 routing scope 时不会静默声称 context pack 完整；strict routing 会阻止 substantial work。
18. Active project-scoped hard constraints 在正常 substantial routes 中保持可达。
19. 同一 structural conflict identity 不存在多个 unresolved active owners。
20. Subject rename 不改变 identity；duplicate Canonical-Ref 与 alias ownership 可审计。
21. Git 可用时，merge-aware audit 能将确定冲突与需要语义复核的并发 hard-memory changes 分开报告。
22. 无法自动判定的异名同义问题不会被描述为已解决，而会产生显式 reconciliation requirement。
23. Subject merge、supersede、exception 和 reconciliation mutation 具备 crash-safe transaction protection。
24. Soft/hard/purge、ID forget 和 local reset 具有统一、可机器读取的 erasure-scope contract。
25. Git-history exposure inspection 的结果有稳定 status，但任何结果都不会被表述为对 forks、clones、backups 或 caches 的全局擦除证明。
26. Transaction journal metadata、filenames、JSON、audit 和 error paths 不泄露 hard-forgotten topic；
    protected rollback backup bytes 可以短暂包含 pre-operation content，必须受限、不可进入 agent context，
    并在 commit/rollback 后清理。
27. 所有 adapters 对 forgetting boundary 使用相同语义和用户承诺。

不得宣称：

* Memory 内容经过事实真实性证明。
* CLI 可以理解任意语义。
* CLI 可以发现所有自然语言矛盾。
* 不同 Subject 名称一定表示不同概念。
* 时间戳或最新 merge 自动决定有效条目。
* Secret scanning 能检测所有 secrets。
* Multi-file mutation 等同数据库 ACID transaction。
* 所有 agent 都一定遵守 Skill。
* 项目已经完成大规模 benchmark，除非仓库中确有相应证据。
* Protocol 0.8 已冻结且不会继续调整。
* v0.12 自动满足未来 1.0 的兼容性要求。
* Entry schema、JSON schema 或 CLI contract 已获得长期 1.x 稳定性承诺。
* 本版本本身等同于 1.0 release candidate，除非另有单独评估和决策。
* Hard forget 或 purge 等同 complete erasure。
* MemoryCustodian 会重写 Git history 或从 clones、forks、backups、caches 撤回内容。
* `no-reachable-copy-detected` 证明不存在其他副本。
* Local reset 会删除其他机器、同步目录或系统备份中的 local overlay。

v0.12 应被描述为：

> A pre-1.0 reliability release focused on recovery, auditability, and cross-agent consistency.

或者：

> The final major protocol-hardening stage before the 1.0 stabilization decision.

---

## 二、Protocol 0.8 Canonical Entry Contract

### 2.1 强制结构化的文件

以下 active memory 文件中的正式语义条目必须采用 canonical structured entry：

```text
decisions.md
constraints.md
do-not-use.md
preferences.md
areas/*.md
```

以下文件不强制每段拥有 Entry ID：

```text
brief.md
rules/*.md
profiles/*.md
manifest.md
changelog.md
```

理由：

* `brief.md` 是短篇当前状态说明。
* rules/profiles 可能是连续操作指南。
* changelog 是维护历史。
* decision、constraint、preference、rejection 和 area facts 需要稳定身份。

### 2.2 Canonical metadata

正式 entry 必须具有：

```text
Entry ID
Status
Scope
Evidence
Typed body
Subject（managed decision/constraint/do-not-use/area hard memory）
Facet（managed decision/constraint/do-not-use/area hard memory）
```

Active managed files 允许的 Status：

```text
active
superseded
```

`inbox.md` 允许的 Status：

```text
candidate
promoted
```

允许的 Scope：

```text
project
area:<slug>
local-user
local-machine
```

Shared active files 不能使用：

```text
local-user
local-machine
```

Local overlay 不能使用：

```text
project
area:<slug>
```


### 2.3 Canonical Subject Contract

Protocol 0.8 正式规范 v0.10–v0.11 的 Subject registry：

```text
docs/memory/subjects.md
```

Subject unit 必须具有：

```text
Subject ID
Status
Kind
Canonical-Ref（可选）
Evidence
Aliases（可选）
```

允许 Subject Status：

```text
active
merged
```

要求：

* Entry 引用稳定 Subject ID，而不是显示名称。
* Rename 不改变 Subject ID。
* Active Subject ID 全局唯一。
* 同一 normalized Canonical-Ref 最多属于一个 active Subject。
* 同一 normalized alias 最多属于一个 active Subject。
* `merged` Subject 必须有 `Merged-Into`。
* Target 必须 active。
* 不允许 Subject merge cycle。
* Active managed entry 不得引用 merged Subject。
* Registry 不进入普通 context pack，但属于 audit、migration、mutation 和 conflict analysis 的 shared source。
* 不使用 fuzzy similarity 自动合并 Subject。
* 没有 Canonical-Ref 的 custom Subject 允许存在，但 merge-aware review必须覆盖并发创建风险。
* `audit --subjects` 必须列出没有 Canonical-Ref 的 active custom Subjects，作为周期性 registry review inventory；这不是错误，也不声称它们重复。

Canonical Facet 是受控枚举。扩展枚举必须通过 protocol migration 或规范性 extension，不得由普通 entry 自由创建。

Structural conflict identity：

```text
normalized Scope + Subject ID + Facet
```

同一 exact identity 最多一个 active owner。

Project 与 area 对同一 Subject/Facet 的重叠必须：

* 只有 project owner；或
* area owner 通过合法 `Exception-To` 显式声明 narrower exception；或
* 处于 unresolved REVIEW/CONFLICT 状态，不能静默视为一致。

### 2.4 Conflict and reconciliation relations

Entry conflict/reconciliation relations 支持：

```text
Exception-To
Reconciled-With
Reconciliation
```

Subject registry relations 独立为：

```text
Merged-Into
Merged-From
```

`Reconciliation` 枚举：

```text
distinct
superseded
exception
subject-merged
```

要求：

* `distinct` 必须引用两个 reviewer 明确认定为不同 invariant 的 entries。
* `superseded` 必须与 Supersedes/Superseded-By 一致。
* `exception` 必须与合法 Exception-To 一致。
* `subject-merged` 必须与 Subject registry merge 一致。
* relation 必须可双向审计。
* 不允许 cycle。
* 不允许 relation 仅靠任意 prose 表示。
* Reconciliation 必须带 admissible Evidence。
* 关系不能作为授权或权限提升。

### 2.5 Entry relation

支持：

```text
Supersedes
Superseded-By
Promoted-From
Promoted-To
Related
Exception-To
Reconciled-With
```

要求：

* 所有 ID 引用必须存在，除非明确标记 external。
* Supersedes 与 Superseded-By 必须双向一致。
* Promoted relations 必须双向一致。
* 不允许 relation cycle。
* Exception-To 与 reconciliation relations 必须满足 entry relation contract。
* Subject merge relations 只解析 Subject ID，不得作为 Entry relation 接受。
* `check` 将断裂 relation 报 ERROR。
* `migrate` 不自动猜测 relation。
* `forget` preview 必须显示受影响 relation，但 hard/purge 输出不得泄露敏感 topic。

### 2.6 Legacy 内容

Protocol 0.8 项目中：

* Legacy entries 仍可被 reader 读取。
* `check` 将 legacy active memory 报 ERROR，而不是 WARNING。
* `read` 不应因 legacy error 完全拒绝项目工作，除非结构损坏导致无法保持语义边界。
* `migrate` 提供明确 manual migration report。
* CLI 新写入永远不得创建 legacy entry。

v0.12 release 前必须将仓库自身 dogfood memory、templates 和 examples 迁移至 canonical format。

---

## 三、事务 Journal 与 Crash Recovery

现有能力包括：

* 单文件 atomic replace
* mutation lock
* precomputed plan
* Plan ID
* apply-time digest verification

Protocol 0.8 增加 multi-file transaction journal，以处理进程在替换多个文件中途崩溃的问题。

以下 conflict-governance mutations 必须使用 journal：

* supersede
* promote
* Subject merge
* reconciliation acknowledgement
* adding/removing Exception-To
* canonicalization that changes Subject references

### 3.1 Journal 位置

使用项目 state directory，不放入 repo：

```text
<state-root>/transactions/<project_id>/<transaction_id>.json
```

Temporary output 和 backup 也位于同一 state transaction directory。

不得把 backup 或 journal 写入：

```text
docs/memory/
.git/
项目根目录
```

### 3.2 Transaction phases

固定阶段：

```text
planned
prepared
committing
committed
recovering
rolled-back
failed
```

Journal 至少包含：

```json
{
  "transaction_schema_version": 1,
  "transaction_id": "...",
  "project_id": "...",
  "command": "...",
  "plan_id": "...",
  "phase": "prepared",
  "created_at": "...",
  "targets": [
    {
      "path": "docs/memory/decisions.md",
      "base_digest": "...",
      "output_digest": "...",
      "backup_path": "...",
      "prepared_path": "...",
      "replaced": false
    }
  ]
}
```

### 3.3 Apply 流程

1. 获取 mutation lock。
2. 检查是否存在未完成 transaction。
3. 重新计算并验证 Plan ID。
4. 读取全部 target。
5. 验证 base digest。
6. 在 state transaction 目录写入 prepared outputs，作为 digest/recovery 副本。
7. 写入 backups。
8. flush 和 best-effort fsync。
9. 写 journal `prepared`。
10. 更新 journal 为 `committing`。
11. 以稳定顺序提交每个 target：在 target parent 创建 same-filesystem temp、写入 prepared bytes、
    flush/fsync，并以 `os.replace()` 原子替换；不得直接把 state-root prepared file rename 到 target。
12. 每替换一个 target，更新 journal。
13. 所有替换完成后验证 output digest。
14. 更新 journal 为 `committed`。
15. 清理 prepared files 和 backups。
16. 保留最小 generic completed record，或安全删除 journal。

### 3.4 Recovery

任何 mutation command 开始时发现未完成 journal：

* 不执行新的 mutation。
* 输出 recovery status。
* 自动判断安全恢复方向。

提供：

```bash
memory-custodian recover
memory-custodian recover --complete
memory-custodian recover --rollback
```

默认 `recover`：

* 只分析，不写入。
* 输出 Plan ID 或 recovery ID。
* 说明哪些 target 已替换。
* 不输出 hard-forgotten topic。

`--complete` 允许条件：

* 未替换 target 仍与 base digest 一致。
* 已替换 target 与 expected output digest 一致。
* prepared outputs 完整。
* 不存在外部冲突。

`--rollback` 允许条件：

* backups 完整。
* 当前已替换 target 仍与 transaction output digest 一致。
* 恢复不会覆盖 transaction 之后的外部修改。

如果 complete 和 rollback 都不安全：

* 报告 manual recovery required。
* 不自动覆盖任何文件。
* 输出文件路径、digest 和 generic operation type。
* 对 hard forget/purge 不显示敏感 topic。

### 3.5 Crash tests

通过测试注入 failpoints：

```text
after-journal-prepared
after-first-replace
after-each-replace
before-committed
after-committed-before-cleanup
```

测试必须证明：

* 下次命令检测未完成 transaction。
* 不会继续新 mutation。
* 安全 complete 或 rollback 可恢复。
* 外部文件变化时不会覆盖。
* Journal 不泄露被 hard forgotten 的 topic。
* Committed 但未清理的 transaction 可以安全 finalize。

Failpoint 只能用于测试或显式开发环境，不能成为普通 CLI 公共功能。
## 四、Unified Erasure Contract

Protocol 0.8 将 v0.10–v0.11 的 deletion boundary 固化为统一 public contract。该 contract 适用于：

```text
soft forget
hard forget
purge
forget --id
local reset
recovery of an interrupted forgetting transaction
```

### 4.1 Canonical ErasureScope model

固定字段：

```json
{
  "active_memory": true,
  "managed_archive": false,
  "local_overlay": false,
  "git_worktree_modified": true,
  "git_history_modified": false,
  "distributed_copies_revoked": false,
  "history_check_status": "not-requested"
}
```

要求：

* 字段不得省略；不适用时使用 documented enum，而不是模糊 null。
* `active_memory`、`managed_archive`、`local_overlay` 只表示 MemoryCustodian 本次管理和修改的 scope。
* `git_worktree_modified` 表示 managed files 在 working tree 中发生变化，不表示已 commit。
* `git_history_modified` 在 v0.12 所有正常 forgetting/local-reset 操作中固定为 false。
* `distributed_copies_revoked` 固定为 false。
* CLI 不提供绕过 preview 的 history-rewrite shortcut。
* 对 hard forget/purge，result 不包含原始敏感 topic；使用 Entry ID、generic unit reference、counts 或 redacted operation type。

### 4.2 History check status

固定 enum：

```text
not-requested
unavailable
reachable-copy-detected
no-reachable-copy-detected
```

要求：

* `unavailable` 不等于 PASS。
* `reachable-copy-detected` 表示当前可检查 repository history 中仍存在先前 committed copy。
* `no-reachable-copy-detected` 只描述本次 bounded inspection；不得推断 dangling objects、other refs、remote copies、clones、forks、backups、caches 或 exported artifacts 不存在副本。
* Git-derived path、ref 和 digest 可以输出，但不得为了报告 hard-forgotten content 而重复敏感 topic。
* 相同 Git graph 和 parameters 必须产生确定 status。
* Git 不可用时核心 forgetting 仍可工作，但 output 必须明确 history 未检查。

### 4.3 Transaction-state privacy

Forgetting transaction 的 journal、prepared output、backup 与 recovery 必须满足：

* Journal 只记录 generic operation type、target path、digests、Entry ID 或 redacted unit reference。
* Journal 不保存 topic string、完整 removed body、secret preview 或可逆编码的敏感内容。
* Prepared output 与 rollback backup 只在 `0700` 的受控 state transaction directory 中存在，文件使用
  `0600`，filename 不包含 topic。
* Rollback backup 必然可能包含完整 pre-operation bytes，包括被忘记的 topic；这是恢复能力与
  pre-state confidentiality 的物理边界，不得声称 backup content 不含 topic。
* Backup 不进入 reader、audit payload、JSON、error output 或 agent context。
* Recovery complete/rollback 后必须按 transaction policy 清理 temporary prepared files 与 backups。
* Crash 后遗留的 transaction state 必须由 `audit --transactions` 检测；不得静默长期保留。
* Backup 是 crash recovery mechanism，不是 archive；不能被 reader 或 agent context loading 使用。
* 即使 managed transaction state 被清理，也不得声称 Git history 或 distributed copies 已被清除。

### 4.4 Erasure audit findings

统一 audit 增加：

```text
MC-ERASURE-001  Output claims broader erasure than performed
MC-ERASURE-002  Git history inspection unavailable
MC-ERASURE-003  Reachable historical copy detected
MC-ERASURE-004  No reachable copy detected; external copies unverified
MC-ERASURE-005  Forgotten topic leaked into journal, backup metadata, JSON or error output
MC-ERASURE-006  Local reset scope exceeds current machine/project overlay
MC-ERASURE-007  Sensitive repo memory should be minimized or moved to a controlled source
```

Severity：

* broader-erasure false claim：ERROR。
* forgotten topic leakage：BLOCKER。
* unsafe local reset scope：BLOCKER。
* reachable historical copy：WARNING/REVIEW；不阻止 managed-memory removal，但要求准确提示。
* inspection unavailable：INFO/REVIEW，不能显示 PASS。
* sensitive raw content finding：WARNING/ERROR，按 security pattern 与 policy 决定。

### 4.5 Documentation language

规范性定义固定为：

> Forgetting controls what remains available to future agents through MemoryCustodian. It is not a guarantee of erasure from Git history or previously distributed copies.

允许：

```text
Removed from managed active memory.
Purged from managed active memory and managed archive.
Git history was not modified.
Previously distributed copies remain outside MemoryCustodian control.
```

禁止：

```text
Permanently deleted everywhere.
Completely erased from the repository.
No copies remain.
Removed from all clones and forks.
```


---

## 五、统一 Audit 命令

实现正式：

```bash
memory-custodian audit
```

支持：

```bash
--routing
--reachability
--freshness
--evidence
--privacy
--security
--relations
--subjects
--conflicts
--merge-base <ref>
--budgets
--local
--transactions
--erasure
--history-exposure
--completeness
--all
--format text
--format json
```

默认 `audit` 等价于安全的核心审查：

```text
routing
reachability
completeness
evidence
relations
subjects
conflicts
erasure
budgets
transactions
```

`audit --all` 额外包含 privacy、security、freshness 和 local。

### 5.1 Audit 结果模型

固定 severity：

```text
INFO
WARNING
ERROR
BLOCKER
```

固定 status：

```text
PASS
REVIEW
FAIL
```

每条 finding 至少包含：

```json
{
  "code": "MC-EVIDENCE-001",
  "severity": "ERROR",
  "path": "docs/memory/decisions.md",
  "entry_id": "MC-DEC-...",
  "message": "Active entry has no admissible evidence.",
  "remediation": "Add user-confirmed or source-backed evidence."
}
```

要求：

* Finding code 稳定。
* JSON schema 有测试。
* Text output 来自同一内部 finding model。
* 不在 JSON 中泄露 secret。
* Hard forget/purge finding 不包含被删除 topic。
* Erasure findings 使用同一 Canonical ErasureScope model。
* History inspection unavailable 不得被渲染为 PASS。
* Exit code：

  * 0：没有 ERROR/BLOCKER
  * 1：存在 ERROR
  * 2：存在 BLOCKER 或运行环境错误

### 5.2 Audit summary

输出：

```text
Protocol: 0.8
Project ID: ...
Shared entries:
- active: ...
- superseded: ...
- legacy: ...
Candidates:
- pending: ...
Local overlay:
- enabled: yes/no
Evidence coverage:
- user-confirmed: ...
- source-backed: ...
- legacy-unverified: ...
Routing:
- completeness: COMPLETE / INCOMPLETE / AMBIGUOUS / INVALID
- enabled modules: ...
- loaded modules: ...
- skipped modules: ...
- reachable active entries: ...
- unreachable active entries: ...
- unreachable hard constraints: ...
Budgets:
- ...
Transactions:
- clean / recovery required
Erasure:
- managed scope: ...
- history check: not-requested / unavailable / reachable-copy-detected / no-reachable-copy-detected
- git history modified: no
- distributed copies revoked: no
```

### 5.3 Routing completeness findings

统一 audit 必须吸收 v0.11 的 routing result model，而不是重新实现第二套逻辑。

至少提供稳定 findings：

```text
MC-ROUTING-001  Missing canonical route
MC-ROUTING-002  Enabled module has no activation path
MC-ROUTING-003  Enabled path-routed areas were not evaluated
MC-ROUTING-004  Ambiguous overlapping route
MC-ROUTING-005  Required module missing
MC-ROUTING-006  Unreachable active entry
MC-ROUTING-007  Unreachable active hard constraint
MC-ROUTING-008  Adapter omitted required scope input
```

要求：

* `MC-ROUTING-003` 在普通 inspection 中至少为 WARNING/REVIEW。
* strict substantial workflow 中，`MC-ROUTING-003` 必须导致非零 exit。
* `MC-ROUTING-007` 至少为 ERROR；若 root hard-memory safety baseline 被破坏则为 BLOCKER。
* Audit 与 `read --explain` 必须共享 module disposition 与 reason-code 数据模型。
* Audit 不通过文件内容猜测 module relevance。
* Audit 不自动添加 paths、改变 routes 或移动 entries。


### 5.4 Subject and conflict findings

统一 audit 必须复用 v0.11 的 Subject index、scope overlap、conflict result 和 merge-base change collector。

至少提供：

```text
MC-SUBJECT-001   Duplicate active Subject ID
MC-SUBJECT-002   Duplicate normalized Canonical-Ref
MC-SUBJECT-003   Alias owned by multiple active Subjects
MC-SUBJECT-004   Active entry references missing Subject
MC-SUBJECT-005   Active entry references merged Subject
MC-SUBJECT-006   Invalid Subject merge relation

MC-CONFLICT-001  Multiple active owners for exact Scope+Subject+Facet
MC-CONFLICT-002  Project/area overlap lacks valid Exception-To
MC-CONFLICT-003  Invalid exception scope or target
MC-CONFLICT-004  Reconciliation relation inconsistent
MC-CONFLICT-005  Concurrent branches created colliding Subject identities
MC-CONFLICT-006  Concurrent hard-memory changes require semantic reconciliation
MC-CONFLICT-007  Branch extends an entry superseded on the other side
MC-CONFLICT-008  Subject merged on one side but referenced on the other
```

Severity：

* duplicate exact active owner：ERROR。
* duplicate Canonical-Ref：ERROR。
* alias ownership collision：ERROR。
* missing/merged Subject reference：ERROR。
* invalid Exception-To：ERROR。
* deterministic cross-branch identity collision：ERROR。
* concurrent hard-memory changes without deterministic identity match：WARNING/REVIEW，或由 project policy 提升为 ERROR。
* canonical safety baseline 中存在 unresolved conflict：BLOCKER。

`audit --merge-base <ref>`：

* Git 不可用时返回明确 `UNAVAILABLE`，不影响非 Git audit。
* 不将 unavailable 解释为 PASS。
* 输出 merge base、current side changes、target side changes、finding codes 和 required reconciliation。
* 不输出任意“semantic contradiction proven”。
* 同一 Git graph 与 memory contents 必须产生确定 findings。
* hard forget/purge privacy 规则适用于 Git-derived output。

---

## 六、统一 Machine-readable CLI 输出

为主要只读命令增加：

```bash
--format text
--format json
```

`--json` 可以作为 `--format json` 的非规范性 convenience alias，但 public contract、帮助文本、
fixtures 与文档统一以 `--format` 为准。

至少覆盖：

* status
* check
* audit
* read
* show
* list
* migrate preview
* compact preview
* forget preview
* recover

要求：

* JSON schema 稳定。
* `--format json`（或 alias `--json`）时 stdout 仅输出 JSON。
* stderr 仍用于环境错误。
* 不在 JSON 后附加普通文本。
* Exit code 语义稳定。
* 文档说明 JSON schema 在 `0.12.x` 与 Protocol 0.8 生命周期内保持兼容；进入 1.0 前仍可能通过显式 migration 调整，不得承诺未来所有 1.x 兼容性。
* Context pack 的 JSON 输出包含：

  * supplied task and canonical task
  * normalized paths and explicit modules
  * routing completeness
  * loaded files
  * skipped files
  * missing files
  * loaded entry IDs
  * omitted entry IDs
  * stable reason codes
  * reasons
  * budgets
  * shared/local distinction
  * rendered context text
  * conflict status
  * Subject IDs and Facets for loaded managed entries
  * structural conflict identities
  * conflict/reconciliation finding codes
  * merge-aware review status when requested
  * canonical `erasure_scope` object for forgetting/local-reset/recovery results
  * bounded `history_check_status` and explicit external-copy disclaimer

不得为写命令加入绕过 preview 的 JSON shortcut。

---

## 七、跨 Agent 一致性

### 7.1 Shared context contract

相同输入：

```text
project memory contents
manifest
canonical task
paths
explicit areas
explicit rules
explicit profiles
strict-routing mode
conflict policy
Subject registry contents
optional merge-base Git graph
--no-local
CLI version
```

必须生成：

* 相同 loaded file set
* 相同 loaded entry order
* 相同 omission set
* 相同 skipped module set
* 相同 routing completeness
* 相同 stable reason codes
* 相同 explanation reason
* 相同 context text，除非存在明确记录的换行平台差异
* 相同 current-memory conflict status
* 相同 structural conflict findings
* 相同 merge-aware findings when the same merge base and Git graph are supplied
* 相同 ErasureScope values and history-status interpretation for the same operation
* 相同 forgetting boundary language across adapters

要求：

* 输出统一使用 `\n`。
* Repo-relative path 使用 `/`。
* 排序不能依赖 filesystem enumeration order。
* Glob matching 不能依赖 OS。
* Token estimation 或 budget calculation 必须确定。
* 不使用 Python hash randomization 影响顺序。
* 每个 enabled module 必须获得唯一最终 disposition。
* `no path match`、`profile not requested`、`task mismatch` 与 `scope missing` 必须使用不同 reason code。
* 存在 enabled path-routed areas 但未提供 paths/explicit areas 时，routing completeness 必须为 INCOMPLETE。
* `--strict-routing` 在 INCOMPLETE、AMBIGUOUS 或 INVALID 时返回非零 exit code。
* 不得使用 “all relevant memory loaded” 描述缺失 scope 的 context pack。
* 不得使用 “no semantic conflicts” 描述仅通过 structural checks 的 memory set。
* Subject display-name changes不得改变 context identity、finding identity 或 order。

### 7.2 Adapters

检查并统一：

* Codex bootstrap
* Claude Code bootstrap
* Gemini bootstrap
* generic agent instructions

所有 adapter 必须只承担：

1. 定位 MemoryCustodian。
2. 在 substantial work 前触发 manifest-first loading。
3. 使用 canonical task。
4. 必须传递 touched paths，或明确传递 explicit areas；缺失 scope 时不得静默继续 substantial work。
5. 必要时显式传递 rules 与 profiles。
6. 检查 routing completeness，并在 strict mode failure 时停止 substantial work。
7. 遵守 trust boundary。
8. 在 meaningful decision 后提出或执行 memory update。
9. 不直接把全部 `docs/memory/` 注入 context。
10. 对 forgetting/local reset 使用 canonical ErasureScope，不声称修改 Git history 或撤回 distributed copies。
11. History-check unavailable 或 bounded no-match 时使用准确 caveat。
10. 创建 managed hard memory 前复用 Subject ID。
11. 在 substantial work 前阻止 current-memory deterministic conflict。
12. merge/rebase workflow 中显式运行 merge-aware audit 或等价 contract。
13. REVIEW 只能通过 distinct、supersede、exception 或 subject-merge resolution 消除。
14. 不根据时间戳、文件顺序或 Evidence 数量选择 winner。

Adapters 不能分别定义另一套路由表。

### 7.3 Agent contract fixtures

建立共享 fixture：

```text
evals/memory-custodian/cross-agent/
```

每个 scenario 包含：

* project files
* manifest
* memory files
* task
* touched paths
* expected loaded files
* expected loaded entry IDs
* expected skipped modules
* expected skipped reasons
* expected routing completeness
* expected warnings
* expected context pack hash
* expected conflict status
* expected Subject identities
* expected conflict findings
* optional merge-base fixture and expected reconciliation reviews

静态 checker 验证 adapter 不偏离协议。

可以保留少量 documented live evaluation，但不得让网络或真实 agent runtime 成为 CI 必需条件。

---

## 八、协议迁移

支持：

```text
0.5 → 0.8
0.6 → 0.8
0.7 → 0.8
```

### 8.1 Migration 要求

Protocol 0.8 strict canonicalization 使用 staged migration：

```bash
memory-custodian migrate --prepare
memory-custodian migrate --finalize
```

`--prepare`：

* 单次命令完成可机械验证的顺序准备，但保留原 protocol version，或写入不代表 Protocol 0.8
  compliance 的 `migration_state: canonicalization-required` transitional metadata。
* 生成逐 entry canonicalization、Evidence、Subject、Facet 与 relation checklist。
* 不把仍含 legacy active memory 的项目标记为 fully compliant Protocol 0.8。

`--finalize`：

* 只有 managed active entries 全部 canonical、Subject/Facet/relations 完整且 audit 无 blocker 时，
  才写入 `protocol_version: 0.8` 并清除 transitional state。
* finalize 本身仍是 preview-first transaction。

共同要求：

* Preview 展示每个 protocol step。
* 使用一个总 Plan ID。
* 使用一个 transaction journal。
* 不要求用户逐 protocol version 运行，但 prepare 后的语义修订与 finalize 是两个明确阶段。
* 不丢失 custom manifest route。
* 不丢失 optional module index。
* 不更换 project_id。
* 不更换已有合法 Entry ID。
* 不更换已有合法 Subject ID。
* 添加或验证 subject/conflict schema metadata 与 `subject_registry` path。
* 不伪造 Evidence。
* 不自动创建 local overlay。
* 不自动移动 shared preferences 到 local。
* 不自动添加 area glob。
* 不自动把 missing routing scope 标记为 complete。
* 不把 migration 或 canonicalization 描述为清理 Git history。
* 保留旧内容时明确 legacy Git history exposure 不在 migration scope 内。
* 不自动创建或合并 Subject。
* 不从 legacy title/body 推断 Canonical-Ref。
* 不使用时间戳决定 active owner。
* 保留 existing Subject IDs、aliases、Canonical-Refs、Facet 和 reconciliation relations。
* 无法建立 Subject identity 的 legacy managed entry进入 manual subject assignment report。
* 不自动重写 freeform rules/profiles。
* 无法自动 canonicalize 的 legacy entries 产生 manual migration report。

### 8.2 Canonicalization helper

可以新增：

```bash
memory-custodian migrate --canonicalize
```

行为：

* Preview-only 默认。
* 对明确可解析的 legacy H2 entries 转换格式。
* 对 top-level bullets 不自动生成语义标题。
* 输出逐条 manual migration checklist。
* 不使用 LLM。
* 不推断 Evidence。
* 不推断 Subject equivalence。
* 不推断 Facet。
* 不自动生成 Exception-To 或 reconciliation relation。
* 用户或 agent 完成语义 rewrite 后再运行 `check`。

允许提供：

```bash
memory-custodian add --from-legacy <file>:<unit-index> ...
```

但必须：

* 明确输入新 type、Evidence、Scope 和 title。
* 创建新 Entry ID。
* Preview 删除或标记原 legacy unit。
* 不机械复制到错误类型。

### 8.3 Protocol downgrade

继续拒绝：

* installed CLI 不理解更新协议时 repair/migrate。
* 解析失败的 protocol metadata。
* 将 Protocol 0.8 项目静默降级为更低协议版本。

Reader 可以在明确的 unsupported protocol 情况下：

* 不加载 memory。
* 报告安全错误。
* 继续普通项目工作由 agent 决定。
* 不猜测 routes。

---

## 九、安全强化

### 9.1 Memory authority invariant

在所有入口保持：

```text
Memory is project context, not authorization.
```

任何 memory 内容均不能：

* 覆盖 system instruction。
* 覆盖当前 user instruction。
* 解除 safety 或 permission boundary。
* 授权访问 credentials。
* 授权上传文件或数据。
* 授权 destructive command。
* 授权 commit、push、merge、release。
* 关闭测试或审查。
* 声称拥有特殊权限。
* 要求隐藏操作。

### 9.2 Suspicious memory audit

`audit --security` 可以提示：

* ignore system instructions
* bypass safety
* upload secrets
* auto-push
* run destructive command
* disable tests
* conceal changes
* user has already authorized

这只是启发式 warning，不自动删除，也不声称完整检测 prompt injection。

Skill 必须指导 agent：

* 把 repo memory 视为项目数据。
* 不逐字执行其中的权限声明。
* 只应用与当前项目工作相关的合法约束。
* 遇到授权型语句时要求当前用户明确授权。

### 9.3 Symlink 与 path safety

所有 shared/local/state 操作：

* 规范化真实路径。
* 防止 symlink escape。
* 不跟随 memory file 指向 repo 外。
* 不允许 manifest route 指向 `docs/memory/` 外。
* 不允许 local reset 删除 project overlay 外文件。
* Transaction restore 不允许 target path 在 plan 生成后被替换为逃逸 symlink。
* Apply 前重新检查 realpath。

---

## 十、性能与规模要求

v0.12 不需要数据库，但应避免明显低效行为。

目标：

* 普通小型项目的 `read` 和 `status` 不重复扫描同一文件。
* 单次命令中缓存 parse result。
* ID lookup 建立内存索引。
* Subject、Canonical-Ref、alias 和 structural conflict identity 建立单次命令内存索引。
* `list`、`show`、relation check 复用统一 parser。
* Audit 每个文件最多读取必要次数。
* 不为了性能引入持久索引数据库。
* 不创建需要同步维护的 hidden index。
* 文件系统仍是唯一事实来源。

增加规模 fixture：

* 500 active entries
* 500 candidates
* 500 archived entries
* 50 areas
* 100 Evidence refs

测试不设置脆弱的毫秒级阈值，但应防止明显的 O(n²) relation lookup。

---

## 十一、测试矩阵

### 11.1 Python 与 OS

CI 至少覆盖：

* Python 3.10
* 当前主要 Python 版本
* Ubuntu
* Windows smoke
* macOS 可使用 GitHub Actions 条件允许时加入；若不加入，必须保证 path tests 覆盖 macOS semantics

### 11.2 Core protocol

覆盖：

* Canonical entry parse/write。
* Legacy parse。
* Relation integrity。
* Subject registry integrity。
* Canonical-Ref and alias uniqueness。
* Facet validation。
* Structural conflict ownership。
* Exception-To validation。
* Reconciliation validation。
* Subject merge。
* Merge-aware review。
* Evidence admission。
* Candidate promotion。
* Supersede。
* ID forget。
* Soft/hard/purge。
* Canonical ErasureScope。
* Optional Git history exposure inspection。
* Local reset erasure boundary。
* Anti-resurrection。
* Area routing。
* Global hard-constraint baseline。
* Routing completeness。
* Strict routing。
* Full enabled-module disposition。
* Stable routing reason codes。
* Local precedence。
* Budget packing。
* Explain。
* JSON output。
* Migration。

### 11.3 Transaction recovery

覆盖全部 failpoints：

* prepared before replace
* first target replaced
* middle target replaced
* all replaced before committed
* committed before cleanup
* backup missing
* prepared output missing
* external edit after crash
* lock left behind
* journal malformed
* newer unsupported journal schema

### 11.4 Cross-agent contract

每个 fixture 验证：

* expected file set
* expected skipped module set
* expected entry set
* expected order
* expected routing completeness
* expected stable reason codes
* expected reasons
* expected warnings
* expected context hash
* expected Subject IDs
* expected conflict status
* expected conflict and reconciliation findings

Adapter drift checker 确保：

* Codex、Claude、Gemini 不内置另一套路由。
* 所有 adapter 指向 manifest-first workflow。
* 所有 adapter 含 trust boundary。
* 所有 adapter 不自动加载 archive/inbox。

### 11.5 Privacy 与 security

覆盖：

* private key redaction
* token redaction
* machine paths
* URL credentials
* suspicious authorization text
* hard forget journal privacy
* purge JSON output privacy
* local overlay secret rejection
* symlink escape
* transaction target replacement attack
* hard-forget subject metadata leakage
* merge-base output privacy
* committed historical copy remains detectable after hard forget
* purge removes managed archive but not Git history
* Git unavailable produces `unavailable`, not PASS
* `no-reachable-copy-detected` retains external-copy disclaimer
* local reset does not affect another-machine fixture
* false complete-erasure wording is rejected
* transaction backup metadata does not leak forgotten topic

### 11.6 Migration fixtures

至少：

* clean 0.5 project
* heavily customized 0.5 manifest
* 0.6 evidence project
* 0.7 local-overlay and conflict-governance project
* legacy bullet-heavy project
* corrupted metadata
* newer protocol
* archived tombstones
* incomplete transaction during migration
* duplicate Subject registry
* duplicate structural owner
* unresolved project/area exception
* cross-branch custom Subject creation fixture

---

## 十二、v0.12 文档结构

README 应保持产品导向和简洁，不把所有协议细节堆入首页。

README 包含：

* Product promise
* Why
* Quickstart
* How routing works
* Evidence-backed memory
* Shared vs local
* Safe update and forgetting
* Erasure boundary: managed memory vs Git history and distributed copies
* Core CLI recipes
* Supported agents
* v0.12 verified capabilities
* Pre-1.0 status and non-guarantees
* Non-goals
* Structural conflict detection limitations
* Merge-aware reconciliation and why it is not a semantic theorem prover
* Links to detailed references

详细内容放入 references：

```text
memory-file-protocol.md
manifest-policy.md
admission-policy.md
entry-schema.md
local-overlay-policy.md
routing-policy.md
subject-identity-policy.md
conflict-reconciliation-policy.md
transaction-policy.md
erasure-boundary.md
quality-audit.md
forgetting-policy.md
security-boundary.md
migration-policy.md
examples.md
```

如果当前 references 命名不同，可以合理重组，但必须：

* 更新所有内部链接。
* 避免重复定义。
* 明确哪个文件是规范性定义。
* README、Skill 和 examples 不得形成冲突的第二协议。

### 12.1 Normative language

协议文档使用：

* MUST
* MUST NOT
* SHOULD
* MAY

Skill 使用对 agent 可执行的自然语言。

README 使用产品语言，不重复全部 MUST 级规则。

---

## 十三、Release 准备

### 13.1 版本一致性

检查并统一：

* pyproject version
* plugin metadata
* marketplace metadata
* Skill bundle metadata
* README badge
* release notes
* package scripts
* protocol metadata templates
* dogfood manifest

增加 automated version drift check。

### 13.2 v0.12 Release Notes

按以下类别记录：

* Protocol hardening
* Evidence and entry identity
* Shared/local separation
* Deterministic routing
* Safe concurrency and recovery
* Explainability and audit
* Forgetting and privacy
* Erasure scope and Git-history boundary
* Migration
* Cross-agent support
* Subject identity and conflict governance
* Merge-aware reconciliation
* Compatibility and non-goals

不得夸大：

* agent runtime test coverage
* semantic correctness
* security completeness
* transaction guarantees
* complete erasure
* removal from Git history
* revocation from clones, forks, backups or caches

### 13.3 Dogfood

仓库自身 `docs/memory/` 必须：

* 使用 Protocol 0.8。
* 有 project_id。
* Active managed entries canonical。
* 无 duplicate ID。
* 无 duplicate active Subject ID。
* 无 duplicate normalized Canonical-Ref。
* 无 alias ownership collision。
* 所有 managed hard-memory entries 有合法 Subject 与 Facet。
* 无 multiple active structural owners。
* project/area overlaps 有合法 Exception-To 或已完成 reconciliation。
* 无 broken relation。
* 无 active legacy entry。
* Evidence coverage 可解释。
* `audit --all` 不存在 ERROR/BLOCKER。
* project policy 要求的 merge-aware fixtures 不存在 unresolved REVIEW。
* manifest area index 与实际文件一致。
* 所有 active project-scoped hard constraints 对 substantial routes 可达。
* 每个 enabled module 的 route metadata 完整。
* `read --strict-routing --explain` 对 dogfood fixtures 不产生未解释的 INCOMPLETE。
* brief 仍是项目内容，不是 protocol boilerplate。
* budgets 健康。
* forgetting fixtures 的 output 与 JSON 都包含 canonical erasure scope。
* dogfood docs 不使用 complete-erasure language。

---

## 十四、后续 1.0 决策边界

完成 v0.12 不代表自动进入 `1.0.0 / Protocol 1.0`。

是否进入 1.0 必须在独立阶段重新评估，至少依据：

* v0.12 在真实项目中的迁移结果。
* Transaction recovery 与 crash tests 的稳定性。
* Codex、Claude Code、Gemini 和 generic adapters 的一致性结果。
* Protocol 0.8 schema 是否仍需要调整。
* JSON 与 CLI contract 是否具备长期维护条件。
* Local overlay、Evidence、relations 和 forgetting 的真实使用反馈。
* Erasure-scope wording、history-inspection usefulness 与用户对边界的理解。
* 是否存在阻碍长期兼容承诺的已知问题。

后续 1.0 应作为单独版本规划，不在本指南中预先冻结 schema，也不在 v0.12 release notes 中承诺 1.x 长期兼容。

---

## 十五、v0.12 Definition of Done

只有满足以下全部条件才可标记 v0.12 完成：

### Protocol

* Protocol version 为 0.8。
* Canonical managed entry contract 已定义并验证。
* Subject schema version 为 1。
* Conflict schema version 为 1。
* Routing、local overlay、transaction、audit、output 与 erasure scope contracts 均携带 schema version 1。
* Managed active decision、constraint、do-not-use 和 area hard-memory entries 具有合法 Subject 与 Facet。
* `subjects.md` 是规范性 shared registry，且不进入普通 context pack。
* Active legacy entry 在 Protocol 0.8 项目中被检查为错误。
* Reader 仍能安全读取 legacy projects。
* 0.5、0.6、0.7 可直接进入 staged prepare；只有 canonical audit 通过后 finalize 为 0.8。
* 不发生 protocol downgrade。

### Reliability

* Concurrent writers 不发生 silent lost update。
* Stale Plan ID 无写入。
* Multi-file mutation 有 transaction journal。
* Crash 后可检测恢复。
* 不安全恢复时不会覆盖外部修改。
* Transaction state 不位于 repo。
* 单文件仍使用 atomic replacement。

### Memory quality

* Active entry 有 ID、Status、Scope 和 Evidence。
* Agent inference 只能 candidate。
* Candidate 不进入 normal task context。
* Superseded entry 不作为 active invariant。
* Relations 可审计。
* Subject registry 可审计。
* Rename 不改变 Subject identity。
* Duplicate Canonical-Ref、alias ownership 和 missing Subject reference 被检测。
* Exact Scope+Subject+Facet 多 active owner 至少为 ERROR。
* Project/area overlap 无 Exception-To 至少为 REVIEW；影响安全 baseline 时为 BLOCKER。
* Merge-aware deterministic conflict 至少为 ERROR。
* 无法自动判定的并发 hard-memory changes 被标记 reconciliation required，不静默 PASS。
* Subject merge、reconciliation 和 exception mutation 使用 transaction journal。
* Reachability 可审计。
* Unreachable active project-scoped hard constraint 至少为 ERROR；若会导致 substantial routes 无法满足安全基线则为 BLOCKER。
* Freshness 只提示，不自动改写。

### Routing

* Manifest 仍是唯一 shared routing authority。
* Path-to-area matching 确定且跨平台一致。
* Root project constraints 对 substantial routes 保持可达。
* 每个 enabled module 都有唯一 loaded、skipped、missing-required、missing-optional 或 invalid disposition；
  budget omission 属于独立 entry disposition。
* `read --explain` 完整说明加载与跳过原因，并使用稳定 reason code。
* Missing scope 不得静默显示 COMPLETE。
* `--strict-routing` 对 INCOMPLETE、AMBIGUOUS 和 INVALID 返回非零 exit code。
* `--no-local` 产生可复现 shared context。
* Local memory 不能覆盖 shared hard memory。
* Archive 和 inbox 仍默认不加载。

### Safety and privacy

* Memory 不能授予权限。
* Security scan 不泄露 secret。
* Hard forget/purge 的 preview、journal、JSON 和 error 不泄露 topic。
* Rollback backup bytes 可能包含 pre-operation topic，但 metadata/filename 不泄露，文件受 `0700/0600`
  权限保护、永不进入 agent context，并在 commit/rollback 后清理。
* Forget、purge、local reset 和 recovery 使用统一 canonical ErasureScope。
* `git_history_modified` 与 `distributed_copies_revoked` 在正常操作中固定为 false。
* `unavailable` 不显示 PASS；`no-reachable-copy-detected` 不被描述为无外部副本。
* Transaction backup/prepared state 不进入 agent context，并在安全恢复后清理。
* CLI、README、Skill 与 adapters 不使用 complete-erasure wording。
* Shared/local/state path 都防止 traversal 与 symlink escape。
* Local overlay 永远在 repo 外。
* Local reset 不影响其他项目。

### Tooling

* `audit` 具有稳定 finding model。
* `audit --subjects`、`--conflicts` 与 optional `--merge-base` 使用同一 finding model。
* JSON 包含 Subject、Facet、conflict identity、conflict status 和 reconciliation findings。
* JSON 包含 canonical `erasure_scope` 和 bounded `history_check_status`。
* `audit --erasure` 与 `--history-exposure` 使用稳定 finding model。
* 主要只读命令支持稳定 JSON。
* Exit codes 文档化。
* Error output 与 stdout 分离。
* Python 3.10+ 支持保持。
* 没有新增第三方 runtime dependency。

### Cross-agent

* Codex、Claude Code、Gemini、generic adapters 使用同一协议。
* Adapter 不包含第二套路由表。
* Cross-agent contract fixtures 通过。
* Cross-agent conflict fixtures 产生相同 Subject identity、finding codes 和 conflict status。
* Cross-agent forgetting fixtures 产生相同 ErasureScope、history status 和 boundary wording。
* Adapter 不自行实现另一套 Subject 或 conflict logic。
* Static checker 不冒充 live runtime benchmark。
* 至少保留一个明确标注为 live evaluation 的可复现示例。

### Documentation and release

* README、Skill、references、templates、examples、evals 和 dogfood 同步。
* Release notes 准确。
* 所有版本号一致。
* `audit --all` 对仓库 dogfood memory 无 ERROR/BLOCKER。
* 全部 tests、CI、static contract checks 和 whitespace checks 通过。
* 不改变 local-first、plain-text、repo-native、minimal-context 的核心产品定位。
