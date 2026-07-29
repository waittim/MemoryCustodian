# MemoryCustodian v0.11.0 实施指南

## Protocol 0.7：确定性路由、可解释上下文、Local Overlay 与冲突检测

你正在继续修改已经完成 v0.10 / Protocol 0.6 的 MemoryCustodian。

v0.10 已提供：

* Stable Entry ID
* Evidence-backed active memory
* Candidate admission
* Project-level mutation lock
* Preview Plan ID
* Trust boundary
* Privacy/security checks
* Protocol 0.5 → 0.6 migration
* Stable module identity 与 routing reason model 基础
* Stable Subject registry、Canonical-Ref、aliases 与 controlled Facet
* Structural conflict identity：Scope + Subject ID + Facet
* Current-memory mutation preflight prevents a second exact active owner
* Structured `ErasureScope` contract for soft、hard 与 purge operations
* Forgetting output explicitly excludes Git-history rewrite and revocation of distributed copies

当前阶段要解决的核心问题是：

> 对于给定 task 与显式 scope，MemoryCustodian 如何确定加载哪些 memory；当某个 module 没有被加载时，用户如何看到它被排除的可验证原因；当 task scope 不足时，系统如何避免静默地产生一个看似完整、实际可能漏载的 context pack。

同时解决另一类静默失败：

> 当前 worktree 或两个分支中的 hard-memory changes 是否形成可确定的结构冲突；当 CLI 无法证明它们相同或不同，如何明确产生 reconciliation requirement，而不是静默声明 conflict-free。

v0.11 的治理能力以**检测、解释、inventory 与 preview**为主。会跨多个 governance files 改写身份或关系的操作，例如 Subject merge apply、reconciliation acknowledgement apply、Exception-To mutation apply 与 multi-file promotion apply，统一推迟到 v0.12 transaction journal 可用之后。v0.11 不得发布一个只能依靠 partial-write reporting 维持一致性的复杂治理 apply workflow。

不要询问更多信息。先完整检查 v0.10 的实现、测试、模板、Skill、references、examples、evals、dogfood memory 和 adapters，再按照本指南完成端到端实现。

不要发布 release、push 远程分支或修改产品定位。完成代码、测试、迁移、文档和版本更新即可。

目标版本：

* Package version：`0.11.0`
* Protocol version：`0.7`
* Entry schema version：`1`
* Routing schema version：`1`
* Subject schema version：`1`
* Conflict schema version：`1`
* Local overlay schema version：`1`

`local_overlay_schema_version` 只存在于 repo 外 local manifest；shared manifest 不以当前机器是否存在 overlay 作为 validity 条件。Shared manifest 只声明 shared Protocol、routing 与 conflict contracts。

### Protocol 0.7 实施前置条件

在写入 `protocol_version: 0.7` 之前，必须先验证或补齐以下 Protocol 0.6 基础能力：

* 所有 mutating commands 使用同一个 project mutation guard。
* bootstrap lock 到 permanent project lock 的 handoff 在同一 guard 中完成。
* 最终写入 manifest 的 `project_id` 与持有的 permanent lock identity 完全一致。
* `init`、`repair`、`migrate`、`enable` 与 Protocol 0.5 compatibility writes 不得各自维护不同 lock-selection 逻辑。
* Structured entry parser 必须拒绝 duplicate scalar fields、duplicate Evidence blocks 与缺失 typed body。
* Entry type、storage path 与 typed body 必须一致。
* Repo 外 state directory 在 POSIX 上使用 `0700`；state files 使用 exclusive private write 与 `0600`。
* State helper 必须拒绝 symlink replacement，并对 fallback path 使用相同权限规则。
* Canonical Plan 中的 path 与 path-like arguments 使用 repo-relative POSIX representation。
* Internal execution plan、public preview representation 与未来 transaction journal representation 必须分离。
* Hard/purge public plan 不包含 raw topic；不得直接公开序列化内部 canonical execution arguments。

如果这些能力尚未回补到 v0.10，必须作为 v0.11 Phase 0 完成，并保留相应 regression tests。

## 一、版本目标

MemoryCustodian v0.11 必须实现以下保障：

1. Shared routing 对给定 canonical task、touched paths 和显式 optional inputs 是确定的。
2. Root project constraints 成为 substantial work 的安全基线，不再依赖 agent 逐条判断 relevance。
3. Area memory 只通过 manifest 中声明的 path matchers 或显式 `--area` 确定性加载。
4. Rules 只通过 canonical task 或显式 rule route 加载。
5. Profiles 默认只通过显式请求加载，不依赖隐藏的 workflow guessing。
6. `read --explain` 为每个 enabled module 分配且仅分配一个 module disposition，并单独报告 entry-level budget omissions。
7. 当项目启用了 path-routed area，但 substantial task 没有提供 paths 或 explicit areas 时，输出必须标记 routing INCOMPLETE。
8. `--strict-routing` 在 routing INCOMPLETE、AMBIGUOUS 或 INVALID 时拒绝把 context pack 视为成功。
9. Reachability check 能发现永远无法加载的 active memory，尤其是 unreachable hard constraints。
10. Freshness check 能提示 Evidence 或 relation 可能陈旧，但不自动改写 memory。
11. Local user/machine preferences 可以存在 repo 外，不污染 shared memory，也不覆盖 shared hard memory。
12. ID-based list、show 与 forget 可以操作 canonical entries；promotion 与治理关系修改在 v0.11 只提供验证和 preview。
13. 现有 Protocol 0.6 项目可以保守迁移，不丢失 custom routes、entries、Evidence 或 human-readable descriptions。
14. 不引入 semantic search、embedding、LLM runtime relevance scoring 或后台索引。
15. `check --conflicts` 能确定性发现 current-worktree structural conflicts 与 invalid relations。
16. Git 可用时，`check --conflicts --merge-base <ref>` 能只读发现两个分支的 deterministic conflicts 与 reconciliation risks。
17. 两个分支分别创建不同 Subject ID 时，exact Canonical-Ref 或 alias collision 被确定性发现；异名 Subject 不被自动合并。
18. Subject merge、reconciliation 与 Exception-To workflows 在 v0.11 具有规范数据模型、完整 inventory 和 preview，但 transactional apply 推迟到 Protocol 0.8。
19. Topic forget、`forget --id`、purge 与 local-reset preview 使用同一 ErasureScope model，不产生不同删除承诺。
20. Git 可用时，用户可以显式请求 best-effort history exposure inspection；不可用或未检查时不得被解释为安全擦除证明。
21. Local overlay 使用 explicit root binding；公开的 `project_id` 只是 namespace identifier，不是 authentication secret。

v0.11 解决的是：

> deterministic and explainable context routing for supplied task and scope, plus structural conflict detection

v0.11 不声称解决：

> automatically understanding every piece of memory relevant to an arbitrary natural-language task

也不声称解决：

> proving that every pair of differently named natural-language entries is semantically contradictory

也不声称提供：

> crash-recoverable multi-file governance mutation; that guarantee begins in Protocol 0.8

## 二、必须保留的产品边界

不得引入：

* 第三方 Python runtime dependency
* 网络依赖
* Git 作为必要运行条件
* 数据库或持久化索引
* embedding
* vector database
* semantic search
* LLM runtime dependency
* 自由文本 task description relevance scoring
* 自动扫描聊天历史
* 自动推断 touched paths 后静默继续
* 自动为旧 area 猜测 path glob
* 自动把 local preference 写入 repo
* 自动把 optional module 提升为 always-load
* 自动删除 unreachable memory
* 自动修复 freshness warning
* 自动 commit、push、merge 或 release
* 依赖时间戳或 merge order 自动选择冲突 winner
* 根据编辑距离、关键词或正文相似度自动合并 Subject
* 自动判断两个任意自然语言 constraints 是否语义矛盾
* 在 merge-aware review 未完成时静默声明 hard-memory conflict-free
* 在 transaction journal 可用前执行 Subject merge、reconciliation acknowledgement、Exception-To mutation 或 multi-file promotion apply
* 在 v0.11 建立一个随后由 v0.12 重新定义的第二套正式 `audit` namespace
* 自动运行 Git history rewrite、force push、删除远程 refs 或清理其他 clones/forks
* 将 `no reachable copy detected` 表述为不存在外部副本的证明
* 将 local overlay 当作 secret store，或声称 `local reset` 能清除其他机器上的副本

文件系统和 manifest 仍是唯一 shared source of truth。

Agent 可以负责：

* 选择 canonical task
* 提供 touched paths
* 显式选择 profile、area 或 rule
* 根据 explain 输出修正 scope

但这些选择必须成为可观察的 CLI 输入，不能仅存在于 agent 的隐藏判断中。

---

## 三、Protocol 0.7 Manifest Contract

新初始化或迁移后的 `manifest.md` 必须包含：

```md
## MemoryCustodian Protocol
- protocol_version: 0.7
- entry_schema_version: 1
- subject_schema_version: 1
- subject_registry: subjects.md
- routing_schema_version: 1
- conflict_schema_version: 1
- initialized_with: memory-custodian <version>
- last_migrated_with: memory-custodian <version>
- project_id: <UUIDv4>
- admission_policy: evidence-required
- routing_policy: explicit-task-and-scope
- conflict_policy: canonical-subject-and-review
```

必须保留 v0.10 的合法：

* `project_id`
* Entry IDs
* Subject IDs、Canonical-Refs、aliases、Facets
* Evidence
* custom routes
* optional module files

`init --repair` 不得：

* 更换 `project_id`
* 删除 custom routes
* 自动为 custom areas 猜测 paths
* 将 optional module 静默变为 default load
* 覆盖用户维护的 manifest prose

---

## 四、Shared Routing Model

### 4.1 Canonical task

继续使用有限 canonical task，不接受任意字符串作为 routing category。

至少支持：

```text
general
planning
implementation
artifact
preferences
history
maintenance
```

现有 aliases 可以继续兼容，但必须在 routing model 中规范化为 canonical value。

要求：

* `read` 输出同时显示 supplied task 与 canonical task。
* Alias normalization 必须确定。
* Unsupported task 明确报错。
* CLI 不读取 task description 进行语义分类。
* Adapter 或 agent 选择 task category 时，该选择属于显式输入边界。
* `--explain` 必须注明 task-derived routes 使用的 canonical task。

### 4.2 Global hard-memory baseline

新默认 manifest 中，substantial task 至少包括：

```text
planning
implementation
artifact
history
```

这些 task 必须默认加载：

```text
brief.md
constraints.md
```

理由：

* `brief.md` 提供当前项目形状。
* root `constraints.md` 只保存 project-wide hard requirements。
* 全局 hard constraints 不应依赖 agent 判断它们是否 relevant。
* `constraints.md` 必须保持预算受控；如果内容属于单一 subsystem，应移动到 matched `areas/*.md`。

`general` task 至少加载 `brief.md`。是否加载 `constraints.md` 可由 manifest 明确声明，但新模板应优先安全基线。

`maintenance` task 继续按 manifest 加载 maintenance memory，不得自动加载所有 archive。

Migration 要求：

* 不强制改写 custom Protocol 0.6 manifest。
* 如果 custom manifest 的 substantial routes 不包含 root `constraints.md`，preview 必须报告：
  * `Routing safety review required`
* 用户可选择保持 custom behavior，但 `check --routing` 应持续显示 WARNING。
* 如果 active project-scoped hard constraint 只能通过 optional route 到达，`check --reachability` 报 ERROR。

### 4.3 Enabled module index

每个 enabled optional module 必须在 manifest 中有唯一声明。

Canonical module identity 使用规范化 repo-relative path：

```text
rules/output.md
profiles/git.md
areas/frontend.md
```

Module index 必须可机器解析，并包含与 module type 相符的 route metadata。

规范格式：

```md
## Optional module index

### Enabled rules

- `rules/output.md`
  - activation: task
  - tasks: artifact

- `rules/review.md`
  - activation: task-or-explicit
  - tasks: planning, implementation

### Enabled profiles

- `profiles/git.md`
  - activation: explicit-only

- `profiles/release.md`
  - activation: explicit-only

### Enabled areas

- `areas/frontend.md`
  - activation: path-or-explicit
  - paths: `web/**`, `frontend/**`, `tests/frontend/**`

- `areas/backend.md`
  - activation: path-or-explicit
  - paths: `cli/**`, `server/**`, `tests/backend/**`
```

规范性 activation vocabulary：

```text
task
explicit-only
task-or-explicit
path
path-or-explicit
```

Module compatibility matrix：

| Module type | Allowed activation | Required metadata | Forbidden metadata |
| --- | --- | --- | --- |
| `rules/` | `task`, `task-or-explicit`, `explicit-only` | `tasks` when activation includes `task` | `paths` |
| `profiles/` | `explicit-only` | none | `tasks`, `paths` |
| `areas/` | `path`, `path-or-explicit`, `explicit-only` | `paths` when activation includes `path` | `tasks` |

要求：

* Module path 必须唯一。
* 路径必须位于允许目录。
* Path metadata 必须是 repo-relative POSIX-style path。
* 不允许同时维护 `activation` 与第二套 `explicit: allowed` vocabulary。
* 不允许仅依赖自然语言描述如 “load when clearly relevant” 作为唯一 machine route。
* Human-readable description 可以保留，但不能影响 CLI routing result。
* Manifest parser 必须拒绝同一 module 的矛盾重复声明。
* 该 nested-bullet grammar 是 Protocol 0.7 的规范性 machine grammar：
  * module 行必须是 subsection 下 column-zero 的 `- \`path\``。
  * metadata 行固定缩进两个空格，并使用 `- key: value`。
  * allowed keys 固定为 `activation`、`tasks`、`paths` 与 `description`。
  * scalar key 在同一 module 内不得重复；重复 module path 一律 INVALID。
  * key 顺序不影响语义；canonical renderer 按 `activation`、`tasks`、`paths`、`description` 顺序输出。
  * task list 使用逗号分隔的 unquoted canonical tokens。
  * path glob 必须使用 Markdown code span。
  * unknown machine key 一律 INVALID。
  * parser error 不得 fallback 到 natural-language route guessing。

`description` 规则：

* 单行 UTF-8 文本。
* 不允许 continuation line。
* 可以包含逗号，但不得被解析为 tasks 或 paths。
* 不参与 route identity、reason code 或 Plan ID。
* Canonical renderer 必须保留其语义文本，但 routing tests 不依赖 description。

### 4.4 Area path matching

新增可重复参数：

```bash
memory-custodian read \
  --task implementation \
  --path cli/memory_custodian/read.py \
  --path tests/test_read.py
```

Protocol 0.7 固定 glob dialect：

```text
/    canonical segment separator
*    zero or more characters within one segment
?    exactly one character within one segment
**   zero or more complete path segments
```

要求：

* 不支持 character class、brace expansion、extglob 或 shell-specific escaping。
* `**/*.py` 必须匹配根目录与任意子目录中的 `.py` 文件。
* Dotfiles 与普通 segment 使用相同匹配规则，不采用 shell 隐藏文件特例。
* Matching 对 canonical repo path 大小写敏感，跨平台保持一致。
* Backslash 输入先按 CLI path normalization 转换为 `/`；manifest glob 中出现 backslash 一律 INVALID。
* Absolute path、drive-prefixed manifest glob、空 segment、`.` 或 `..` segment 一律 INVALID。
* 输入 path 规范化为 project-relative POSIX path。
* 拒绝 project 外路径与 traversal。
* 不要求 path 已存在，允许用于 planned files；输出必须标记 `missing-on-disk`。
* 对不存在 path 先做 lexical containment，再 resolve nearest existing parent，拒绝 symlink escape。
* 对已存在 path 重新检查 realpath，不能逃逸 project root。
* Glob matching 不依赖 OS shell expansion、filesystem enumeration order 或 Python hash order。
* 同一 area 被多个 path 命中时只加载一次，并稳定列出全部 matching inputs 与 patterns。
* 显式 `--area <slug>` 可以加载 area，即使没有 path match；reason 必须标记 `MC-ROUTE-EXPLICIT-AREA`。
* Path match 不读取文件内容，不执行 semantic inspection。
* 不在 Protocol 0.7 引入静态 area-overlap group 或 glob-intersection theorem。不同 areas 默认独立；如果同一次 read 的 supplied paths 同时激活多个 areas，并且它们拥有相同 Subject/Facet，产生 matched-context REVIEW。

### 4.5 Rules 与 Profiles

Rules：

* task-routed rule 根据 manifest 中 `tasks:` 确定性加载。
* explicit rule 使用：

```bash
--rule output
```

* 未匹配 canonical task 的 rule 不加载。
* Human-readable description 不参与 routing。

Profiles：

* 使用：

```bash
--profile git
--profile release
```

* Profile 默认仅显式加载。
* Adapter 不得根据自由文本 workflow 自动偷偷添加 profile。
* Agent 可以选择 profile，但必须把选择作为 CLI 参数，使 explain 可见。

### 4.6 Archive 与 Inbox

继续保持：

* `archive/` 只在用户显式请求或 archive maintenance 时加载。
* `inbox.md` 只在 candidate review、compaction 或 memory maintenance 时加载。
* Candidate 永远不进入 normal task context。
* Explain 必须显示 archive/inbox 的 policy exclusion，但无需枚举 archive 中每个文件，除非 manifest 将其作为 enabled module 错误声明。

---

## 五、Routing Completeness 与 Strict Mode

### 5.1 Completeness 状态

每次 `read` 必须计算：

```text
COMPLETE
INCOMPLETE
AMBIGUOUS
INVALID
```

含义：

* `COMPLETE`：所有当前 enabled routing dimensions 都获得足够显式输入，且 manifest 与参数合法。
* `INCOMPLETE`：存在可能影响 context pack 的 scope 输入缺失。
* `AMBIGUOUS`：manifest 与参数语法都合法，但当前 invocation 激活多个由协议明确声明为互斥、且无法唯一裁决的 route interpretation。
* `INVALID`：manifest、grammar、metadata combination 或参数违反协议。

至少以下情况为 `INCOMPLETE`：

* substantial task 启用了一个或多个 path-routed area，但未提供任何 `--path` 或 `--area`。
* adapter 表示正在修改项目文件，却未传递 touched paths 或 explicit area。
* manifest 声明 scope input required，但命令未提供。
* supplied scope inputs 全部缺失；非法 path 本身归入 INVALID，不得通过丢弃非法输入后继续显示 COMPLETE。

至少以下情况为 `AMBIGUOUS`：

* 同一次 invocation 的 supplied path 激活多个被 manifest 中合法 policy 明确标记为 mutually exclusive 的 route；Protocol 0.7 默认 manifest 不生成此 policy。
* 一个保留的 legacy task alias 在明确 compatibility table 中映射到多个 canonical tasks。

以下情况必须为 `INVALID`，不得降级为 AMBIGUOUS：

* duplicate module declaration。
* contradictory route metadata。
* unsupported activation combination。
* task-only 与 explicit-only 同时声明。
* unknown machine key。
* malformed nested-bullet grammar。
* invalid task、path 或 glob。
* duplicate scalar key。
* module type 与 metadata 不兼容。

实现应尽量在 manifest parse 阶段消除 ambiguity；不得将 parser error 描述为 routing uncertainty。

### 5.2 默认行为

普通 `read`：

* 仍可渲染已有的安全基线 context。
* 必须在输出顶部清晰显示 routing completeness。
* `INCOMPLETE` 或 `AMBIGUOUS` 时必须输出 WARNING。
* 不得使用 “all relevant memory loaded” 或等价表述。
* Exit code：
  * COMPLETE：0
  * INCOMPLETE：0，但有结构化 warning
  * AMBIGUOUS：1
  * INVALID：2

### 5.3 Strict routing

新增：

```bash
memory-custodian read \
  --task implementation \
  --strict-routing
```

行为：

* COMPLETE：正常输出，exit 0。
* INCOMPLETE：不把 context pack 视为成功，exit 1。
* AMBIGUOUS 或 INVALID：exit 2。
* 可以输出安全基线和 explain diagnostics，但必须明确：
  * `Context pack not approved for substantial work`
* Skill 和 adapters 必须要求 substantial planning、implementation、debugging 和 review 默认使用 strict routing，或等价地先补齐 paths/areas 再继续。
* 用户显式选择非 strict inspection 时允许查看 partial pack，但不能将其描述为完整。

---

## 六、完整 `read --explain`

### 6.1 CLI

支持：

```bash
memory-custodian read \
  --task implementation \
  --path cli/memory_custodian/read.py \
  --explain
```

`--names-only` 与 `--explain` 可以组合。

Explain 必须包含：

```text
Routing inputs
Routing completeness
Loaded modules
Skipped modules
Missing modules
Budget omissions
Warnings
```

### 6.2 全枚举要求

Explain 必须枚举：

* Always-load modules
* 当前 task route 中的 modules
* Optional index 中所有 enabled rules
* Optional index 中所有 enabled profiles
* Optional index 中所有 enabled areas
* 显式请求但未启用的 modules
* Required but missing files
* Optional but missing files
* 因 budget 省略的完整 entries

不能只显示 loaded files。

每个 enabled module 必须有且仅有一个最终 disposition：

```text
loaded
skipped
missing-required
missing-optional
invalid
```

一个 loaded file 内部的部分 entries 因 budget 未进入 context 时：

* file disposition 仍为 loaded
* omitted entries 单独列出
* 有 Entry ID 时显示 ID
* legacy unit 没有 ID 时显示稳定 unit reference，不生成伪 ID

Entry disposition 使用独立 namespace：

```text
loaded
omitted-by-budget
inactive
```

### 6.3 Stable reason codes

内部 finding 至少支持：

```text
MC-ROUTE-ALWAYS
MC-ROUTE-TASK
MC-ROUTE-PATH
MC-ROUTE-EXPLICIT-AREA
MC-ROUTE-EXPLICIT-PROFILE
MC-ROUTE-EXPLICIT-RULE
MC-SKIP-TASK-MISMATCH
MC-SKIP-NO-PATH-MATCH
MC-SKIP-NOT-REQUESTED
MC-SKIP-SCOPE-MISSING
MC-MISSING-REQUIRED
MC-MISSING-OPTIONAL
MC-OMIT-BUDGET
MC-ROUTE-AMBIGUOUS
MC-ROUTE-INVALID
```

要求：

* Reason code 与 human message 分离。
* Text output 由统一内部 result model 渲染。
* v0.11 不必承诺 public JSON schema；v0.12 将把同一 model 暴露为稳定 JSON。
* 同样输入产生同样 reason codes 与顺序。
* Human-readable message 不得把 skipped module 描述为“不 relevant”；应说明可验证原因，例如：
  * no supplied path matched
  * profile not explicitly requested
  * canonical task did not match
  * scope input missing

### 6.4 示例输出

```text
Task: implementation
Canonical task: implementation
Paths:
- cli/memory_custodian/read.py

Routing completeness: COMPLETE

Loaded:
- brief.md
  Reason: MC-ROUTE-ALWAYS
- constraints.md
  Reason: MC-ROUTE-ALWAYS
- decisions.md
  Reason: MC-ROUTE-TASK
- do-not-use.md
  Reason: MC-ROUTE-TASK
- areas/backend.md
  Reason: MC-ROUTE-PATH (cli/**)

Skipped:
- areas/frontend.md
  Reason: MC-SKIP-NO-PATH-MATCH
- profiles/git.md
  Reason: MC-SKIP-NOT-REQUESTED
- rules/output.md
  Reason: MC-SKIP-TASK-MISMATCH

Omitted entries:
- MC-DEC-20260726-a1b2c3d4
  Reason: MC-OMIT-BUDGET
```

缺少 scope 时：

```text
Routing completeness: INCOMPLETE
Warning: enabled path-routed areas were not evaluated because no paths or explicit areas were supplied.
```

---


## 七、Conflict Identity、Merge Review 与治理 Preview

### 7.1 设计边界

v0.11 不实现通用自然语言 contradiction detector。系统必须区分：

1. **Deterministic structural conflict**：由 Scope、Subject ID、Facet、relations 与 registry metadata 确定。
2. **Potential semantic conflict**：两个分支并发改变 hard memory，但结构身份不同，CLI 无法证明相同或不同。
3. **No detected conflict**：没有确定冲突，也没有触发 reconciliation risk；不等同于证明所有自然语言陈述一致。

不得使用：

* “newer wins”
* 文件中靠后的 entry wins
* merge order wins
* Evidence 数量自动决定 winner
* fuzzy title similarity 自动决定 Subject 等价
* LLM runtime 自动裁决

时间戳、Evidence 与 Git history只用于解释和 review，不赋予 precedence。

v0.11 的 mutation boundary：

* 可以检测、解释、列出 blockers、生成 stable preview 与 Plan ID。
* 可以验证手工维护的 Exception-To 与 reconciliation records。
* 不执行 Subject merge apply、Exception-To add/remove apply、reconciliation acknowledgement apply 或 multi-file promotion apply。
* v0.12 transaction journal 上线后，才允许这些治理操作以 crash-recoverable transaction apply。

### 7.2 Structural conflict identity

沿用 v0.10：

```text
normalized Scope + Subject ID + Facet
```

Scope overlap 规则：

* 相同 `project` scope：exact overlap。
* 相同 `area:<slug>`：exact overlap。
* `project` 与任意 `area:<slug>`：narrower-scope overlap。
* 两个不同 area 在静态 current-worktree audit 中默认独立。
* 如果某次 read 的 supplied paths 同时激活多个 areas，且多个 active owners 使用相同 Subject/Facet，则 matched-context status 为 REVIEW。
* `local-user`、`local-machine` 不参与 shared hard-memory ownership。

Finding：

* exact overlap 下存在多个 active owner：`CONFLICT / ERROR`。
* project 与 area 对同一 Subject/Facet 同时 active，且无合法 Exception-To：`REVIEW`。
* matched context 中两个不同 areas 对同一 Subject/Facet 同时 active：`REVIEW`。
* Superseded、candidate、archive entries 不计为 active owner。
* 正文是否相同不影响 exact conflict；一个 exact invariant identity 只能有一个 active owner。

### 7.3 Explicit exception relation

为 narrower-scope exception 定义：

```text
Exception-To: <ENTRY_ID>
```

要求：

* 只允许 area-scoped active entry 指向 project-scoped active entry。
* 两者必须使用相同 Subject ID 与 Facet。
* 被引用 entry 必须存在且 active。
* `Exception-To` 不表示任意 override，只表示该 area 下有显式、可审查的 narrower policy。
* Explain 必须同时加载并显示 project baseline 与 matched area exception。
* Relation 断裂、scope 不合法、Subject/Facet 不一致或 cycle 为 ERROR。
* Local overlay 不得创建 `Exception-To` 覆盖 shared hard memory。
* v0.11 可以验证已有 relation，并提供 add/remove preview；apply 推迟到 v0.12。

### 7.4 Reconciliation record contract

Protocol 0.7 选择独立 reconciliation record，不使用散落在两个 entries 中的单值 scalar relation作为唯一 acknowledgement。

规范文件：

```text
docs/memory/reconciliations.md
```

Canonical unit：

```md
## MC-REC-20260729-a1b2c3d4 — Distinct invariants

Status: active
Entries:
- MC-CON-...
- MC-CON-...
Resolution: distinct
Evidence:
- user-confirmed
```

`Resolution` 枚举：

```text
distinct
superseded
exception
subject-merged
```

要求：

* 至少引用两个 Entry IDs，排序 canonical。
* `distinct` 表示 reviewer 明确确认 entries 管理不同 invariant。
* `superseded` 必须与 Supersedes/Superseded-By 一致。
* `exception` 必须与合法 Exception-To 一致。
* `subject-merged` 必须与 Subject registry `Merged-Into` 一致。
* Record 必须带 admissible Evidence。
* 不允许 duplicate active reconciliation identity。
* 新的后续修改或 relation change 可以重新触发 REVIEW。
* v0.11 验证手工 record，并提供 preview；record apply 推迟到 v0.12。

### 7.5 `check --conflicts`

新增：

```bash
memory-custodian check --conflicts
```

不依赖 Git，扫描当前 worktree memory set：

* duplicate active Scope+Subject+Facet
* invalid or broken `Exception-To`
* duplicate active Canonical-Ref
* alias simultaneously owned by multiple active Subjects
* Subject registry entry missing、inactive 或 merged
* managed hard-memory entry missing Subject/Facet
* project/area overlap without explicit exception
* invalid reconciliation record
* reconciliation record inconsistent with Supersedes、Exception-To 或 Subject merge

固定结果：

```text
CLEAR
REVIEW
CONFLICT
INVALID
```

Stable findings 至少包括：

```text
MC-CONFLICT-001  Multiple active owners for one structural identity
MC-CONFLICT-002  Project/area overlap requires explicit exception review
MC-CONFLICT-003  Duplicate active Canonical-Ref
MC-CONFLICT-004  Alias owned by multiple active Subjects
MC-CONFLICT-005  Subject reference missing, inactive, or merged
MC-CONFLICT-006  Invalid Exception-To relation
MC-CONFLICT-007  Managed hard-memory entry lacks Subject or Facet
MC-CONFLICT-008  Invalid or inconsistent reconciliation record
MC-CONFLICT-009  Matched areas expose overlapping Subject/Facet ownership
```

行为：

* `CONFLICT` 或 `INVALID` 返回非零 exit。
* `REVIEW` 在普通 inspection 中允许 exit 0，但必须清晰显示。
* 不自动修改 entry、registry 或 reconciliation record。
* 不输出“semantically consistent”。
* 结果模型必须供 `read --explain` 与 v0.12 unified audit 复用。

### 7.6 Strict read 与 conflict status

普通 `read` 除 routing completeness 外，必须显示：

```text
Conflict status: CLEAR / REVIEW / CONFLICT / INVALID
```

要求：

* 当前 context pack 命中 deterministic conflict 时，不能把两个 active owners 当作同时有效指令。
* 普通 inspection 可以输出 metadata 与安全 baseline，但必须标记 `Context pack contains unresolved active-memory conflict`。
* `--strict-routing` 同时执行 matched-context structural conflict gate：
  * CLEAR：按 routing status 处理。
  * REVIEW：输出 warning；matched project/area 或 multi-area overlap 时 substantial work 应先 reconciliation。
  * CONFLICT：exit 2，`Context pack not approved for substantial work`。
  * INVALID：exit 2。
* Explain 显示 Entry IDs、Subject ID、Facet、Scope 和 finding code。
* 不重复 hard-forgotten topic。
* 不根据时间戳自动选择 winner。

### 7.7 Merge-aware read-only review

v0.11 不创建正式 `audit` namespace。使用：

```bash
memory-custodian check --conflicts --merge-base origin/main
```

行为：

1. Git 不可用或 ref 无效：
   * 不影响普通 `check --conflicts`。
   * 输出 `merge review unavailable`。
   * 不伪装为 conflict-free。
2. 计算 current HEAD 与目标 ref 的 merge base。
3. 收集 merge base 后两侧对 `subjects.md`、managed hard-memory files、`areas/*.md` 与 `reconciliations.md` 的完整 semantic-unit changes。
4. 不做逐行语义拼接或 fuzzy text matching。
5. 产生 deterministic conflicts、registry collisions、concurrent hard-memory REVIEW 与 missing-resolution REVIEW。

Deterministic findings：

* 两侧创建相同 Canonical-Ref 的不同 Subject ID。
* 两侧创建相同 normalized alias 的不同 Subject ID。
* 两侧为同一 Scope+Subject+Facet 创建不同 active owner。
* 一侧 supersede 某 entry，另一侧继续建立基于旧 entry 的 active relation。
* 一侧 merge Subject，另一侧继续以 merged Subject 建立 active identity。

Review findings：

* 两侧都在同一 managed hard-memory file 中新增 active entries，但 identity 不同。
* 两侧都修改同一 Subject 的不同 Facet，且没有有效 reconciliation record。
* 两侧创建没有 Canonical-Ref、exact alias 不同的新 custom Subjects。
* 一侧新增 project constraint，另一侧新增可能受其覆盖的 area constraint。
* 两侧 Evidence 指向在另一侧发生变化的 authoritative files。

这些 REVIEW finding 只表示：

```text
Concurrent hard-memory changes require semantic reconciliation.
```

### 7.8 Subject merge inventory 与 preview

新增 preview-only workflow：

```bash
memory-custodian subject merge MC-SUBJ-source \
  --into MC-SUBJ-target
```

Preview 必须列出：

* source 与 target registry units
* 所有引用 source 的 current active 与 candidate entries
* superseded 与 archive historical-reference inventory，但不计划机械重写
* future current-reference mutations
* alias/Canonical-Ref collisions
* resulting conflict identities
* required reconciliation records
* blockers
* Plan ID

v0.11 不接受 `--apply`。输出必须明确：

```text
Transactional Subject merge apply requires Protocol 0.8.
```

Protocol 0.8 apply 语义预先固定为：

* 只更新 current active 与 candidate references。
* source 标记 `Status: merged` 并添加 `Merged-Into`。
* target 可添加 `Merged-From`。
* 不机械重写 superseded 或 archive historical entries。
* historical query 通过 source Subject 的 `Merged-Into` 解析 current canonical identity，并同时显示 historical identity。
* 合并后若产生多个 active structural owners，阻止 apply。

### 7.9 CI 与团队工作流

推荐但不强制 Git 成为核心运行条件：

```bash
memory-custodian check --conflicts
memory-custodian check --conflicts --merge-base origin/main
```

在启用 MemoryCustodian 的团队 CI 中：

* current-memory `CONFLICT/INVALID` 必须失败。
* merge-aware deterministic conflict 必须失败。
* merge-aware REVIEW 是否阻止合并由项目 policy 决定；新模板 SHOULD 默认要求 reconciliation。
* CI 输出不得声称静态检查等同完整语义证明。
* README 必须说明短文件和时间戳只提高 reviewability，不构成 contradiction detection。

## 八、Local Overlay

### 8.1 目标

允许以下内容保持在 repo 外：

* 用户个人输出偏好
* 本机路径
* 编辑器或 shell workflow
* 个人 agent preference
* machine-specific command
* 不适合团队共享但需要跨 session 保存的 local context

Local overlay 不得：

* 覆盖 shared project hard constraints
* 覆盖 do-not-use tombstones
* 授权 destructive action
* 扩大 agent 权限
* 自动进入 Git
* 存储 secrets
* 变成第二个 shared manifest

### 8.2 位置与权限

使用 v0.10 state root：

```text
<state-root>/projects/<project_id>/local/
```

至少包含：

```text
manifest.md
preferences.md
profiles/
```

不得放入项目 repo、`docs/memory/` 或 `.git/`。

要求：

* Local directory 在 POSIX 上使用 `0700`。
* Local files 使用 private atomic write 与 `0600`。
* 不跟随 local path symlink 逃逸 state project directory。
* Local path 由 `project_id` namespace 定位，但 `project_id` 不是 authentication secret。

### 8.3 Root binding

为了避免复制相同 `project_id` 的另一 repository 自动读取本机已有 overlay，增加 repo 外 binding：

```text
<state-root>/projects/<project_id>/bindings.json
```

要求：

* 记录用户显式批准过的 normalized project roots。
* 新 root 首次访问已有 overlay 时状态为 `UNBOUND`，默认不加载 local content。
* CLI 输出 `Local overlay status: UNBOUND` 并要求显式 `local link`。
* 项目正常移动后可通过显式 link 更新 binding。
* 同一 project_id 出现在多个 roots 时至少为 REVIEW，不静默共享。
* Binding 不是防御同一用户账户下恶意进程的安全沙箱，只是防止意外 cross-repository reuse。

### 8.4 Local manifest

Local manifest 只能声明 local modules，不得重新定义 shared routes。

```md
# Local Memory Overlay

- local_overlay_schema_version: 1
- project_id: <same project_id>

## Preferences
- preferences.md

## Profiles
- profiles/my-shell.md
```

要求：

* project_id 必须与 shared manifest 一致。
* Local overlay 缺失时 shared read 正常工作。
* Local overlay corrupt 时分别输出：
  * `Routing completeness: INCOMPLETE`
  * `Local overlay status: REVIEW`
  * 明确 local failure reason
* Local overlay unbound 时分别输出：
  * shared routing completeness 基于 shared inputs正常计算
  * `Local overlay status: UNBOUND`
  * local content 不加载
* Local modules 只能使用 `Scope: local-user` 或 `Scope: local-machine`。
* Shared entries 不能使用 local scope。
* Local manifest 只能引用当前 overlay directory 内规范路径。

### 8.5 Precedence

固定优先级：

1. System、current user、safety 与 permission boundaries
2. Shared project hard constraints 与 do-not-use
3. Shared decisions 与 rules
4. Local preferences/profiles
5. Current task convenience

因此：

* Local preference 可以改变格式风格。
* Local preference 不能解除 shared constraint。
* Local profile 与 shared rule 冲突时 shared rule 优先。
* 冲突必须在 `read --explain` 中显示 warning。
* `--no-local` 必须产生完全不包含 local overlay 的可复现 shared context。

### 8.6 CLI

至少支持：

```bash
memory-custodian local status
memory-custodian local enable
memory-custodian local link
memory-custodian local add "Prefer concise output." \
  --type preference \
  --evidence user-confirmed
memory-custodian local reset
memory-custodian read --no-local
```

v0.11 行为：

* `local status`、`enable`、`link` 与 `add` 可执行，但必须使用 secure state helper 与 project mutation guard。
* `local reset` 默认生成 preview 与 ErasureScope，不接受 `--apply`。
* 输出明确：`Transactional local reset apply requires Protocol 0.8.`
* Security/privacy scan 对 local 内容同样适用。
* Local secrets 仍然拒绝或 ERROR，不因 repo 外而被视为安全。
* Local reset preview 只描述当前机器、当前 project_id 的 overlay。
* 不得声称影响其他机器、同步目录、系统备份或用户自行复制的文件。

## 九、ID-based Operations

新增或完善：

```bash
memory-custodian list
memory-custodian list --status active
memory-custodian list --scope area:frontend
memory-custodian show MC-CON-...
memory-custodian forget --id MC-DNU-...
memory-custodian promote MC-INBOX-... \
  --type constraint \
  --evidence user-confirmed
```

要求：

* ID lookup 跨 canonical shared files、areas、inbox 与 reconciliation records。
* 默认不搜索 archive，除非 `--include-archive`。
* 默认不搜索 local，除非 `--local` 且 root 已绑定。
* Duplicate ID 为 ERROR。
* `show` 显示完整 canonical entry、source path 与 current canonical Subject identity。
* Historical entry 引用 merged Subject 时，同时显示 historical Subject ID 与 current target。
* `forget --id` 比 topic matching 更优先、更精确，并复用现有 forget lock/Plan/stale guard。
* Hard forget/purge 的 public output 与 public Plan 不得泄露敏感 topic。
* Topic forget、`forget --id` 与 purge 输出统一 ErasureScope。
* Legacy unit 可以列出，但没有伪造 ID；使用 stable file/unit reference。
* `promote` 在 v0.11 只生成完整 preview：new active ID、candidate status transition、双向 relation、所有 target files 与 Plan ID。
* `promote --apply` 推迟到 v0.12 transaction journal。

## 十、Erasure Scope 与可选 Git History Inspection

v0.11 必须将 v0.10 的 `ErasureScope` contract 覆盖到所有相关删除入口：

```text
memory-custodian forget <topic>
memory-custodian forget --id <ENTRY_ID>
memory-custodian forget ... --mode hard
memory-custodian forget ... --mode purge
memory-custodian local reset  # preview-only in Protocol 0.7
```

### 10.1 统一 ErasureScope

每个 preview/apply result 至少包含：

```text
active_memory
managed_archive
local_overlay
git_worktree_modified
git_history_modified
distributed_copies_revoked
history_check_status
```

要求：

* 同一操作的 text output 与内部 result model 一致。
* Topic forget 与 ID forget 不得定义不同的删除承诺。
* `purge` 只将 `managed_archive` 设为 true；仍然保持 `git_history_modified: false`。
* `local reset` preview 只将当前机器、当前 project_id 的 `local_overlay` 标记为 planned scope；apply 由 Protocol 0.8 提供。
* 所有操作固定 `distributed_copies_revoked: false`。
* Hard forget/purge 不在 public output、public plan、reconciliation record 或 subject diagnostics 中重复 forgotten topic；internal execution selector 不得被直接序列化为 public result。

### 10.2 可选 Git history exposure inspection

增加显式参数：

```bash
memory-custodian forget --id MC-CON-... \
  --mode hard \
  --history-check
```

或者等价地允许 topic forget 与 purge 使用同一参数。

该检查是 best-effort、read-only、optional：

* Git 不是核心运行依赖。
* 不修改 commits、refs、index、remotes 或 working tree 之外的内容。
* 不自动运行 `git filter-repo`、`git filter-branch`、rebase、gc、force push 或 remote deletion。
* 只检查当前可访问 repository 中的 reachable history；不得扫描网络、forks 或其他 clones。
* 对 hard-forgotten sensitive topic，history check 不得把原始 topic 输出到日志；应使用 Entry ID、file/unit reference 或 generic match count。

固定 `history_check_status`：

```text
not-requested
unavailable
reachable-copy-detected
no-reachable-copy-detected
```

语义：

* `not-requested`：未执行 history inspection。
* `unavailable`：Git 不可用、项目非 Git repo 或检查失败；不得解释为 PASS。
* `reachable-copy-detected`：当前可访问 Git history 中存在先前 committed copy。
* `no-reachable-copy-detected`：在本次有限检查范围内未发现；不证明 dangling objects、other refs、remotes、clones、forks、backups 或 caches 中不存在副本。

示例输出：

```text
History inspection: reachable-copy-detected
Git history was not modified.
Existing clones, forks and backups remain outside MemoryCustodian control.
```

或：

```text
History inspection: no-reachable-copy-detected
No reachable copy was found in the inspected repository history.
This is not proof that no external or previously distributed copy exists.
```

### 10.3 Sensitive-memory guidance

README、Skill 与 policy 必须指导 agent：

* 在写入前优先 redaction、abstraction 和 minimization。
* 不复制 credentials、private keys、完整合同条款、合同编号、个人身份信息或不必要的供应商限额。
* 对必要约束，优先写入抽象、可执行规则，并用 Evidence 指向受控来源。
* 如果必须记录敏感事实，应先获得用户确认，并明确 Git history/distribution 风险。
* Forgetting 是 active-memory governance，不是对已分发信息的撤回机制。

所有删除入口禁止输出：

```text
Permanently deleted everywhere.
Completely erased from the repository.
No copies remain.
Removed from all clones and forks.
```

---

## 十一、Routing、Reachability、Freshness 与 Conflict Checks

v0.11 统一使用 `check` namespace；正式 `audit` namespace 由 v0.12 引入。

```bash
memory-custodian check --routing
memory-custodian check --reachability
memory-custodian check --freshness
memory-custodian check --conflicts
memory-custodian check --conflicts --merge-base origin/main
memory-custodian subject list
memory-custodian subject merge MC-SUBJ-old --into MC-SUBJ-new  # preview-only
```

### 11.1 Routing check

至少检测：

* Missing canonical route
* Duplicate module declaration
* Unsafe module path
* Invalid task name
* Invalid activation/metadata compatibility
* Rule 没有 task 或 explicit-only activation
* Profile 不是 explicit-only
* Area 没有 paths 且不是 explicit-only
* Invalid glob
* Contradictory metadata
* Required module missing
* Root constraints 未在 substantial route 可达

Adapter 是否内置第二套路由表属于 repository static contract check，不属于普通用户项目的 runtime `check --routing`。

### 11.2 Reachability check

建立静态 reachability graph：

```text
canonical tasks
always-load routes
task routes
path-routed areas
explicit rules/profiles/areas
active entries
```

Finding：

* active project entry 从任何 normal route 都不可达：WARNING
* active project-scoped constraint 不可达：ERROR
* active area constraint 的 area 没有 path 或 explicit activation：ERROR
* optional module enabled 但没有 activation path：ERROR
* superseded entry 不作为 active reachability requirement
* candidate、archive 与 historical reconciliation record 不属于 normal reachability

不得自动移动条目、添加 glob、提升为 always-load 或根据正文猜测 area。

### 11.3 Freshness check

Evidence-aware 检查：

* `repo:path@revision` 与当前 Git revision 不一致时，若 Git 可用则 WARNING。
* `repo:path`、`doc:path`、`test:path` 不存在时按 Evidence admissibility 报 ERROR/WARNING。
* issue/pr Evidence 不联网验证。
* 长期未更新的 entry 可以提示 REVIEW，但不能仅因年龄自动判 stale。
* Broken Supersedes、promotion、Exception-To、Subject merge 或 reconciliation reference 为 ERROR。
* Freshness finding 不自动改写 Evidence。
* Git 不可用时显示 INFO，不阻塞非 Git 核心功能。

## 十二、Adapters 与 Agent Workflow

所有 adapters 必须统一为：

1. 定位 `manifest.md`。
2. 识别 canonical task。
3. 在 implementation、debugging 与 review 前收集 touched paths；高层 planning 尚无 path 时显式提供 area，或接受 INCOMPLETE inspection。
4. 调用同一 shared routing implementation。
5. 在 substantial work 前检查 routing completeness。
6. INCOMPLETE 时补齐 paths/areas，或明确报告 scope 不完整；可以查看安全 baseline，但不得开始 substantive modification。
7. 遵守 trust boundary。
8. 不直接加载整个 `docs/memory/`。
9. 不自行维护第二套路由表。
10. meaningful decision 后按 Evidence admission 更新 memory。
11. 创建 hard-memory entry 前复用 existing Subject ID，不凭自由文本创建第二个 identity。
12. merge/rebase 前运行 current-memory conflict check；Git 可用时运行 merge-aware read-only review。
13. 遇到 REVIEW 时说明需要 `distinct`、`superseded`、`exception` 或 `subject-merged` resolution；v0.11 不伪装已自动完成 transactional reconciliation。
14. 对 forgetting/local reset 使用统一 ErasureScope wording，不声称修改 Git history 或撤回 distributed copies。
15. Local overlay 未绑定时不得自动读取。

必须更新：

* Codex bootstrap
* Claude Code bootstrap
* Gemini bootstrap
* generic agent instructions
* `skills/memory-custodian/SKILL.md`

Skill 不得指示 agent：

* 仅凭“看起来 relevant”选择 area
* 隐藏自己选择了哪些 profiles
* 在没有 paths 时假设没有 area relevant
* 将 partial pack 描述为完整
* 将 local preferences 写入 shared repo
* 在 v0.11 直接执行 Subject merge、reconciliation、Exception-To 或 promotion apply

## 十三、协议迁移

实现 Protocol 0.6 → 0.7 migration。

### 13.1 Migration 必须做到

* Preview-first。
* 使用统一 project mutation guard、Plan ID 与 stale digest guard。
* 保留 `project_id`、Entry IDs、Subject IDs、Evidence 与已有合法 relations。
* 保留 custom route source text、enabled optional modules 与 human-readable descriptions。
* 添加 routing/conflict schema metadata。
* 不自动创建 local overlay 或 root binding。
* 不自动添加 area globs。
* 不自动把 root constraints 加入 custom routes。
* 不自动将 shared preferences 移动到 local。
* 不自动合并 legacy 或 duplicate Subjects。
* 不根据 entry title、body 或 timestamp 推断 Subject/Facet。
* 对缺 Subject/Facet 的 managed entries输出 manual assignment checklist。
* 不声称保留旧 agent-inferred routing behavior；缺 machine route 时只能保留 source description 与 explicit reachability。

### 13.2 Optional module migration

对旧 optional index：

* 可识别 module path 时保留。
* 现有 natural-language trigger 保留为 `description`。
* 不从 description、文件内容或目录名称推断 automatic matcher。
* 缺 machine-readable metadata 时迁移为安全合法的 explicit-only：
  * rule：`activation: explicit-only`
  * profile：`activation: explicit-only`
  * area：`activation: explicit-only`
* 输出 `Manual automatic-route mapping required.`
* 模块仍可通过显式 `--rule`、`--profile` 或 `--area` 到达。
* Migration 不得将 grammar-valid 项目留在 route-invalid 状态。

### 13.3 Default template migration

新项目模板必须使用：

* global constraints safety baseline
* canonical task routes
* machine-readable rule activation
* explicit-only profiles
* path-routed areas only after user-supplied paths

`memory-custodian enable area/frontend` 应要求：

```bash
--path 'frontend/**'
```

或者创建 `activation: explicit-only` area，并明确提示尚未配置 automatic matching。

## 十四、实施阶段、门槛与仓库区域

### Phase 0 — Protocol 0.6 prerequisites

* unified project mutation guard
* lock identity handoff
* structured entry validator
* secure state directory/file helpers
* canonical repo-relative Plan paths and path-like arguments
* internal execution plan / public plan separation
* hard/purge public selector redaction

### Phase 1 — Routing core

* canonical task normalization
* normative manifest module parser
* activation compatibility validation
* cross-platform glob matcher
* routing result/disposition model
* completeness calculator

### Phase 2 — Read and explain

* complete module enumeration
* stable reason codes
* entry-level budget omissions
* strict-routing gate
* matched-context conflict status

### Phase 3 — Local overlay

* secure state layout
* local manifest
* root binding
* shared/local precedence
* local status/enable/link/add
* reset preview and ErasureScope boundary

### Phase 4 — Read-only quality and conflict analysis

* ID index/list/show/forget
* reachability
* freshness
* current conflict graph
* reconciliation-record validation
* merge-aware read-only review
* Subject merge inventory and preview

### Phase 5 — Migration、adapters、docs 与 release evidence

* Protocol 0.6 → 0.7 migration
* adapter contract updates
* templates/examples/evals/dogfood
* release notes and version drift checks

每个 phase 必须满足：

* phase unit tests pass
* all previous-phase tests remain green
* dogfood fixture remains readable
* no version bump or release claim before all phases pass
* no new third-party runtime dependency

至少检查并按需要修改：

```text
pyproject.toml
README.md
RELEASE-NOTES.md

cli/memory_custodian/
tests/

skills/memory-custodian/SKILL.md
skills/memory-custodian/references/memory-file-protocol.md
skills/memory-custodian/references/manifest-policy.md
skills/memory-custodian/references/routing-policy.md
skills/memory-custodian/references/local-overlay-policy.md
skills/memory-custodian/references/quality-audit.md
skills/memory-custodian/references/admission-policy.md
skills/memory-custodian/references/examples.md

templates/
examples/
evals/memory-custodian/
docs/memory/
adapters/
```

建议内部职责：

* Project mutation guard
* Secure state writer
* Public/internal Plan representations
* Routing input normalization
* Manifest module declaration parser
* Cross-platform path/glob matcher
* Routing result/disposition model
* Routing completeness calculator
* Explain renderer
* Entry/Subject/reconciliation indexes
* Reachability graph
* Freshness findings
* Local overlay state and root binding
* Shared/local precedence
* Protocol 0.6 → 0.7 migration
* Structural conflict graph
* Scope overlap evaluator
* Exception/reconciliation validation
* Merge-base change collector
* Subject merge preview planner

如现有结构已有类似模块，应扩展现有模块，不要在 adapter 或 `main.py` 中复制逻辑。

## 十五、测试要求

### 15.1 Unit tests

必须覆盖：

* Canonical task normalization。
* Unsupported task。
* Always-load route。
* Root constraints safety baseline。
* Rule task matching。
* Explicit rule。
* Explicit profile。
* Area glob matching。
* Multiple path inputs。
* Planned missing path。
* Traversal rejection。
* Cross-platform path normalization。
* Stable ordering。
* No hidden semantic matching。
* Every enabled module gets one disposition。
* Stable reason codes。
* COMPLETE / INCOMPLETE / AMBIGUOUS / INVALID。
* Strict routing exit codes。
* Missing paths with enabled areas。
* Explicit area without path。
* Budget omitted Entry IDs。
* Legacy unit omission reference。
* Local overlay project_id match。
* Shared/local precedence。
* `--no-local` reproducibility。
* ID list/show/forget/promote。
* Reachability graph。
* Unreachable hard constraint ERROR。
* Freshness missing Evidence path。
* Protocol downgrade guard。
* Duplicate active Scope+Subject+Facet。
* Project/area overlap without Exception-To。
* Valid and invalid Exception-To。
* Duplicate Canonical-Ref。
* Alias ownership collision。
* Missing or merged Subject reference。
* Conflict status CLEAR/REVIEW/CONFLICT/INVALID。
* Strict read blocks deterministic conflict。
* Subject merge preview covers current active/candidate mutations, preserves superseded/archive historical references, and resolves historical identity through `Merged-Into`。
* Topic forget、ID forget 与 purge 生成相同 ErasureScope semantics。
* Git history check statuses and wording。
* Git unavailable 不显示 PASS。
* `no-reachable-copy-detected` 不被渲染为 complete erasure。
* Local reset preview 仅描述当前机器的 current-project overlay；transactional apply 在 Protocol 0.8 测试。

### 15.2 Integration tests

Fixtures 至少包括：

* 默认新项目。
* Custom task routes。
* Enabled rules。
* Explicit profiles。
* Multiple path-routed areas。
* Overlapping area globs。
* Enabled area but no supplied paths。
* Missing required module。
* Optional file absent。
* Budget omission。
* Local overlay enabled。
* Corrupt local overlay。
* Shared/local conflict。
* Legacy Protocol 0.6 optional index。
* Area without machine matcher。
* Project moved to a different absolute path。
* Two branches append conflicting exact identities。
* Two branches create duplicate Canonical-Ref Subjects。
* Two branches create custom Subjects with different names。
* One branch supersedes while the other extends old entry。
* Project constraint and area exception without relation。
* Valid and invalid independent reconciliation records。
* Subject merge preview detects downstream owner conflict and refuses to claim apply support。
* Hard forget removes active memory while committed history remains detectable。
* Purge removes managed archive but not Git history。
* Git unavailable history-check fixture。
* Local root binding prevents an unbound second repository from reading the current-machine overlay。

验证：

* 同样 input 产生同样 loaded/skipped sets。
* 同样 input 产生同样 reason order。
* 不同 OS path 表示规范化为同一 repo path。
* No-path substantial task 不静默显示 complete。
* Strict mode 在 incomplete scope 下失败。
* `--no-local` hash 或 text 可复现。
* Migration 不丢 custom route。

### 15.3 Skill evals

新增场景：

1. Agent supplies touched paths before implementation。
2. Agent does not infer area from prose alone。
3. Global constraint loads for substantial work。
4. Missing paths produces incomplete routing。
5. Strict routing blocks substantial work on incomplete scope。
6. Explain lists skipped modules and reasons。
7. Explicit profile is visible in explain。
8. Candidate remains outside normal context。
9. Local preference does not enter shared repo。
10. Local preference cannot override shared constraint。
11. Unreachable hard constraint is reported。
12. Agent does not claim automatic semantic relevance.
13. Agent reuses existing Subject ID instead of inventing a free-text key。
14. Exact structural conflict blocks substantial work。
15. Concurrent hard-memory changes produce reconciliation review without automatic apply。
16. Agent does not use timestamps to pick a winner。
17. Subject merge is explicit、preview-first and apply-deferred to Protocol 0.8。
18. Agent accurately distinguishes managed-memory removal from Git-history erasure。
19. Agent treats `no-reachable-copy-detected` as limited evidence, not proof。
20. Agent does not claim local reset affects other machines or backups。

静态 checker 不得声称验证真实 agent runtime compliance。

### 15.4 Determinism tests

至少在不同：

* path order
* manifest optional module order
* filesystem enumeration order
* Python hash seed
* Windows/POSIX separators

下验证：

* canonical input normalization stable
* loaded set stable
* loaded order stable
* skipped set stable
* reason code stable
* rendered context stable，除非明确记录换行差异
* conflict status stable
* structural conflict findings stable
* merge-base change classification stable for the same Git graph

---

## 十六、CLI 输出规范

普通 `read` 必须显示：

* Supplied task
* Canonical task
* Paths 或 explicit scope
* Routing completeness
* Loaded files
* Missing required
* Skipped optional
* Budget omissions
* Shared/local distinction

`read --explain` 额外显示：

* 所有 enabled modules
* disposition
* stable reason code
* matching task/path/explicit input
* warnings
* conflicts
* incomplete dimensions
* conflict status
* structural conflict identity
* conflicting Entry IDs
* Subject/Facet/Scope
* merge reconciliation warnings when explicitly requested
* erasure scope for forget results and local-reset preview
* history-check status and bounded interpretation when requested

错误输出：

* Invalid manifest、invalid path、ambiguous route、strict incomplete 输出 stderr。
* 普通 inspect 模式下的 incomplete warning 可在 stdout summary 与 stderr warning 中择一统一实现，但文档必须稳定。
* 不得输出 “nothing relevant found” 作为 no-match reason。
* 不得隐藏 omitted entries。
* 不得把 no path match 与 scope missing 混为同一 reason。

v0.11 可以保持 text-first；v0.12 再提供稳定 machine-readable JSON contract。

---

## 十七、文档要求

README 新增或更新：

* How deterministic routing works
* Canonical task 与 supplied scope
* Why root constraints are a safety baseline
* Area path matching
* Explicit rules and profiles
* `read --explain`
* Routing completeness
* Strict routing
* Shared vs local memory
* Reachability and freshness checks
* Current limitations
* Structural conflict detection vs semantic reconciliation
* Why short files and timestamps help review but do not resolve contradictions
* Subject registry, aliases and canonical references
* `check --conflicts`
* optional `check --conflicts --merge-base`
* explicit supersede、exception、distinct reconciliation 与 subject merge
* Forgetting erasure scope and optional Git history exposure inspection
* Local reset boundary across machines and backups
* Sensitive-memory minimization before content enters Git

README 应使用准确表述：

> The manifest routes a bounded context pack from explicit task and scope inputs.

可以说明：

> For the same manifest, canonical task, paths, and explicit modules, routing is deterministic and inspectable.

不得声称：

* the agent always knows what is relevant
* all relevant memory is guaranteed to load
* path matching proves semantic relevance
* explain can reveal memory that was never indexed or declared
* freshness proves factual correctness

CLI recipes 至少包含：

```bash
memory-custodian read \
  --task implementation \
  --path cli/memory_custodian/read.py \
  --explain

memory-custodian read \
  --task implementation \
  --strict-routing \
  --path cli/memory_custodian/read.py

memory-custodian read \
  --task artifact \
  --rule output \
  --profile docs

memory-custodian read \
  --task implementation \
  --no-local

memory-custodian check --routing
memory-custodian check --reachability
memory-custodian check --freshness

memory-custodian list --status active
memory-custodian show MC-CON-...
memory-custodian forget --id MC-DNU-...
```

Release notes 必须真实描述：

* deterministic routing for supplied task and scope
* full enabled-module explanation
* routing completeness diagnostics
* local overlay
* reachability/freshness checks
* ID operations
* canonical Subject identity and exact structural conflict detection
* merge-aware read-only reconciliation review

不得描述为 automatic semantic retrieval、complete contradiction detection 或 automatic conflict resolution。

同样不得描述为 complete erasure、Git-history removal、clone/fork revocation 或 guaranteed deletion from backups。

---

## 十八、完成标准

只有满足以下全部条件才算完成：

### Protocol prerequisites

* Package version 为 0.11.0，Protocol version 为 0.7。
* Entry、Subject、Conflict、Routing 与 Local Overlay schema versions 均符合本文 authority。
* Unified project mutation guard 已覆盖 init/repair/migrate/enable 与 compatibility writes。
* Manifest `project_id` 与 permanent lock identity 不会分叉。
* Structured entries 拒绝 duplicate fields 与 missing typed bodies。
* Private state permissions 与 symlink protections 有测试。
* Public Plan 不泄露 hard/purge topic，path-like values 使用 canonical repo-relative representation。
* Protocol 0.6 项目仍可安全读取并迁移，不发生 downgrade。

### Routing

* Manifest 是唯一 shared routing authority。
* CLI 不执行 free-text semantic relevance scoring。
* Root constraints 对新模板 substantial tasks 默认加载。
* Area routing 只由 path matcher 或 explicit area 决定。
* Rules 只由 canonical task 或 explicit rule 决定。
* Profiles 默认 explicit-only。
* 每个 enabled module 有唯一 module disposition。
* Budget omission 使用独立 entry disposition。
* `read --explain` 列出 loaded/skipped/missing/invalid 原因与 stable reason code。
* No-path substantial task 不静默显示 COMPLETE。
* `--strict-routing` 对 INCOMPLETE/AMBIGUOUS/INVALID 失败。
* 相同 task、paths、manifest 与 explicit modules 产生确定结果。

### Conflict detection and quality

* `check --conflicts` 检测 duplicate owner、registry collision、invalid exception 与 invalid reconciliation record。
* `read` 显示 matched-context conflict status。
* Strict read 阻止 deterministic conflict 下的 substantial work。
* Merge-aware check 区分 deterministic conflict 与 reconciliation REVIEW。
* 异名且无 exact canonical metadata 的 Subjects 不被自动合并。
* Unreachable active project hard constraint 为 ERROR。
* Candidate 不进入 normal context。
* Superseded/archive entries 不作为 active owner。
* Freshness finding 不自动改写 memory。
* 时间戳不作为 conflict precedence。
* Subject merge 只提供完整 inventory/preview，不接受 apply。
* Exception-To、reconciliation record 与 Subject merge history 可审计。

### Local overlay

* Local overlay 永远在 repo 外并使用 private state permissions。
* Local project_id 与 shared project_id 一致。
* Existing overlay 只对 explicitly bound roots 加载。
* Local preference 不能覆盖 shared hard memory。
* `--no-local` 产生可复现 shared context。
* Local content 同样经过 privacy/security checks。
* Local reset 只提供准确 preview；不声称影响其他机器、备份或 distributed copies。

### Tooling and documentation

* ID-based list/show/forget 可用；promotion/Subject merge/reconciliation/Exception-To apply 明确推迟到 v0.12。
* Topic forget、ID forget、purge 与 local-reset preview 使用统一 ErasureScope。
* Optional history check 只提供 bounded inspection，不修改 Git history。
* `unavailable` 不被当作 PASS；`no-reachable-copy-detected` 不被解释为无外部副本。
* 所有 adapters 使用同一 routing implementation，不包含第二套路由表。
* README、Skill、references、templates、examples、evals 与 dogfood 同步。
* Release notes 不夸大 semantic、transaction 或 erasure capability。
* 全部 unit、integration、determinism、migration、skill eval、CI 与 repository checks 通过。
* 没有新增第三方 runtime dependency。
* 没有改变 local-first、plain-text、repo-native、minimal-context 的产品定位。
