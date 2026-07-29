# MemoryCustodian v0.11.0 实施指南

## Protocol 0.7：Local Overlay、确定性路由、冲突审计与完整解释

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

当前阶段要解决的核心问题是：

> 对于给定 task，MemoryCustodian 如何确定加载哪些 memory；当某个 module 没有被加载时，用户如何看到它被排除的原因；当 task scope 不足时，系统如何避免静默地产生一个看似完整、实际可能漏载的 context pack。

同时解决另一类静默失败：

> 两个分支分别新增可以干净合并、但可能互相矛盾的 active hard-memory entries 时，如何检测确定性的结构冲突，并让无法自动判断的并发语义变化强制进入人工或 agent reconciliation。

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

---

## 一、版本目标

MemoryCustodian v0.11 必须实现以下保障：

1. Shared routing 对给定 canonical task、touched paths 和显式 optional inputs 是确定的。
2. Root project constraints 成为 substantial work 的安全基线，不再依赖 agent 逐条判断其 relevance。
3. Area memory 通过 manifest 中声明的 path matchers 确定性加载。
4. Rules 通过 canonical task 或显式 rule route 加载。
5. Profiles 通过显式请求加载，不依赖隐藏的 workflow guessing。
6. `read --explain` 枚举所有 enabled modules，并说明每个 module 被 loaded、skipped、missing 或 omitted 的原因。
7. 当项目启用了 area memory，但 substantial task 没有提供 paths 或 explicit areas 时，输出必须标记 routing incomplete。
8. `--strict-routing` 在 routing incomplete 或 ambiguous 时拒绝把 context pack 视为成功。
9. Reachability audit 能发现永远无法加载的 active memory，尤其是 unreachable hard constraints。
10. Freshness audit 能提示证据或条目可能陈旧，但不自动改写 memory。
11. Local user/machine preferences 可以存在 repo 外，不污染 shared memory。
12. ID-based list、show、forget 和 promotion/supersede workflows 可操作 canonical entries。
13. 现有 Protocol 0.6 项目可以保守迁移，不丢失 custom routes、entries 或 Evidence。
14. 不引入 semantic search、embedding、LLM runtime relevance scoring 或后台索引。
15. `check --conflicts` 能确定性发现同一或重叠 Scope 下的 Subject/Facet active ownership 冲突。
16. Git 可用时，`audit --merge-base <ref>` 能发现两个分支并发修改 hard memory 的 reconciliation risk。
17. 两个分支分别创建不同 Subject ID 时，exact Canonical-Ref 或 alias collision 被确定性发现；无法证明同义的异名 Subject 被标记为 review，而不是静默视为无冲突。
18. Subject merge、scope exception 和 supersede 使用显式关系与 preview-first multi-file mutation。

v0.11 解决的是：

> deterministic and explainable routing for supplied task and scope

v0.11 不声称解决：

> automatically understanding every piece of memory relevant to an arbitrary natural-language task

也不声称解决：

> proving that every pair of differently named natural-language entries is semantically contradictory

---

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

推荐格式：

```md
## Optional module index

### Enabled rules

- `rules/output.md`
  - tasks: artifact

- `rules/review.md`
  - tasks: planning, implementation
  - explicit: allowed

### Enabled profiles

- `profiles/git.md`
  - activation: explicit

- `profiles/release.md`
  - activation: explicit

### Enabled areas

- `areas/frontend.md`
  - paths: `web/**`, `frontend/**`, `tests/frontend/**`

- `areas/backend.md`
  - paths: `cli/**`, `server/**`, `tests/backend/**`
```

要求：

* Module path 必须唯一。
* 路径必须位于允许目录。
* Path metadata 必须是 repo-relative POSIX-style path。
* `rules/` 必须声明 canonical tasks，或明确 `activation: explicit`。
* `profiles/` 默认 `activation: explicit`。
* `areas/` 必须声明至少一个 path matcher，除非被明确标记 `activation: explicit-only`。
* 不允许仅依赖自然语言描述如 “load when clearly relevant” 作为唯一 machine route。
* 可保留 human-readable description，但它不能影响 CLI routing result。
* Manifest parser 必须拒绝同一 module 的矛盾重复声明。

### 4.4 Area path matching

新增可重复参数：

```bash
memory-custodian read \
  --task implementation \
  --path cli/memory_custodian/read.py \
  --path tests/test_read.py
```

Path routing 规则：

* 输入 path 规范化为 project-relative POSIX path。
* 拒绝 project 外路径。
* 拒绝 traversal。
* 不要求 path 已存在，允许用于 planned files；但输出必须标记 missing-on-disk。
* Glob semantics 由 MemoryCustodian 自己确定，不依赖 OS shell expansion。
* 匹配大小写规则必须文档化并跨平台一致；建议按 repo path 精确大小写处理。
* 排序不依赖 filesystem enumeration。
* 同一 area 被多个 path 命中时只加载一次，并列出全部 relevant matches 或稳定排序后的首要 reason。
* 显式 `--area <slug>` 可以加载 area，即使没有 path match；reason 必须标记 explicit-area。
* Path match 不读取文件内容，不执行 semantic inspection。
* Symlink path 必须按安全 realpath 规则检查，不能逃逸 project root。

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

* `COMPLETE`：所有当前 enabled routing dimensions 都获得足够显式输入，且无冲突。
* `INCOMPLETE`：存在可能影响 context pack 的 scope 输入缺失。
* `AMBIGUOUS`：输入或 manifest 可以产生多种合理 route interpretation。
* `INVALID`：manifest 或参数违反协议。

至少以下情况为 `INCOMPLETE`：

* substantial task 启用了一个或多个 path-routed area，但未提供任何 `--path` 或 `--area`。
* adapter 表示正在修改项目文件，却未传递 touched paths。
* manifest 声明 scope input required，但命令未提供。
* supplied paths 全部被判定为 project 外或无效。

至少以下情况为 `AMBIGUOUS`：

* 同一路径匹配多个互斥 area group。
* 同一 module 有矛盾 route metadata。
* task alias 无法唯一规范化。
* custom route 同时声明 task-only 与 explicit-only 且未定义 precedence。

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
omitted-by-budget
invalid
```

一个 loaded file 内部的部分 entries 因 budget 未进入 context 时：

* file disposition 仍为 loaded
* omitted entries 单独列出
* 有 Entry ID 时显示 ID
* legacy unit 没有 ID 时显示稳定 unit reference，不生成伪 ID

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


## 七、Conflict Identity 与 Merge Reconciliation

### 7.1 设计边界

v0.11 不实现通用自然语言 contradiction detector。系统必须区分：

1. **Deterministic structural conflict**：可以由 Scope、Subject ID、Facet、relations 和 registry metadata 确定。
2. **Potential semantic conflict**：两个分支并发改变 hard memory，但结构身份不同，CLI 无法证明相同或不同。
3. **No detected conflict**：没有确定冲突，也没有触发 merge reconciliation risk；这不等同于证明所有自然语言陈述一致。

不得使用：

* “newer wins”
* 文件中靠后的 entry wins
* merge order wins
* Evidence 数量自动决定 winner
* fuzzy title similarity 自动决定 Subject 等价
* LLM runtime 自动裁决

时间戳、Evidence 和 Git history只用于解释与 review，不赋予 precedence。

### 7.2 Structural conflict identity

沿用 v0.10：

```text
Scope + Subject ID + Facet
```

Scope overlap 规则：

* 相同 `project` scope：exact overlap。
* 相同 `area:<slug>`：exact overlap。
* `project` 与任意 `area:<slug>`：narrower-scope overlap。
* 两个不同 area：默认不 overlap，除非 manifest 显式声明 area overlap group。
* `local-user`、`local-machine` 不参与 shared hard-memory ownership。

Finding：

* exact overlap 下存在多个 active owner：`CONFLICT / ERROR`。
* project 与 area 对同一 Subject/Facet 同时 active，且无显式 exception relation：`REVIEW`。
* 同一 Subject/Facet 在两个声明为互斥或重叠的 area 中 active：按 manifest policy 报 `REVIEW` 或 `CONFLICT`。
* Superseded、candidate、archive entries 不计为 active owner。
* 正文是否相同不影响 exact conflict；一个 invariant identity 只能有一个 active owner。

### 7.3 Explicit exception relation

为 narrower-scope exception 增加：

```text
Exception-To: <ENTRY_ID>
```

要求：

* 只允许 area-scoped active entry 指向 project-scoped active entry。
* 两者必须使用相同 Subject ID 与 Facet。
* 被引用 entry 必须存在且 active。
* `Exception-To` 不代表任意 override，只表示该 area 下有显式、可审查的 narrower policy。
* Explain 必须同时加载并显示 project baseline 与 matched area exception。
* Constraint packing 和 agent workflow 必须明确 narrower exception 的作用范围。
* relation 断裂、scope 不合法或 Subject/Facet 不一致为 ERROR。
* 不允许 exception cycle。
* Local overlay 不得创建 `Exception-To` 覆盖 shared hard memory。

### 7.4 `check --conflicts`

新增：

```bash
memory-custodian check --conflicts
```

不依赖 Git，扫描当前 worktree memory set：

* duplicate active Scope+Subject+Facet
* invalid or broken `Exception-To`
* duplicate active Canonical-Ref
* alias simultaneously owned by multiple active Subjects
* subject registry entry missing or inactive
* managed hard-memory entry missing Subject/Facet
* merged Subject 仍被新 active entry 引用
* project/area overlap without explicit exception
* exact identity owner没有 supersede relation但存在多个 active entries

固定结果至少包括：

```text
CLEAR
REVIEW
CONFLICT
INVALID
```

建议 findings：

```text
MC-CONFLICT-001  Multiple active owners for one structural identity
MC-CONFLICT-002  Project/area overlap requires explicit exception review
MC-CONFLICT-003  Duplicate active Canonical-Ref
MC-CONFLICT-004  Alias owned by multiple active Subjects
MC-CONFLICT-005  Subject reference missing or inactive
MC-CONFLICT-006  Invalid Exception-To relation
MC-CONFLICT-007  Managed hard-memory entry lacks Subject or Facet
MC-CONFLICT-008  Merged Subject still referenced as active identity
```

行为：

* `CONFLICT` 或 `INVALID` 返回非零 exit。
* `REVIEW` 在普通 inspection 中允许 exit 0，但必须清晰显示。
* 不自动修改 entry 或 registry。
* 不输出“semantically consistent”。
* `check --conflicts` 的结果模型必须供 `read --explain` 和 v0.12 audit 复用。

### 7.5 Strict read 与 conflict status

普通 `read` 除 routing completeness 外，必须显示：

```text
Conflict status: CLEAR / REVIEW / CONFLICT / INVALID
```

要求：

* 当前 context pack 命中 deterministic conflict 时，不能把两个 active owners 当作同时有效指令。
* 普通 inspection 可以输出 metadata 和安全 baseline，但必须标记：
  * `Context pack contains unresolved active-memory conflict`
* `--strict-routing` 同时执行当前-memory structural conflict gate：
  * CLEAR：按 routing status 处理。
  * REVIEW：输出 warning；若是 matched project/area overlap，substantial work 应先 reconciliation。
  * CONFLICT：exit 2，`Context pack not approved for substantial work`。
  * INVALID：exit 2。
* Explain 显示冲突 Entry IDs、Subject ID、Facet、Scope 和 finding code。
* 不重复 hard-forgotten topic。
* 不根据时间戳自动选择其中一条加载。

### 7.6 Merge-aware audit

Git 是可选增强。新增：

```bash
memory-custodian audit --merge-base origin/main
```

或在 v0.11 text-first 阶段：

```bash
memory-custodian check --conflicts --merge-base origin/main
```

行为：

1. 若 Git 不可用或 ref 无效：
   * 不影响普通 `check --conflicts`。
   * 输出 `merge review unavailable`。
   * 返回明确环境状态，不伪装为 conflict-free。
2. 计算当前 HEAD 与目标 ref 的 merge base。
3. 分别收集 merge base 之后两侧对以下内容的新增、修改、supersede、删除：
   * `subjects.md`
   * `decisions.md`
   * `constraints.md`
   * `do-not-use.md`
   * `areas/*.md`
4. 只分析完整 semantic entries 和 registry units，不做逐行语义拼接。
5. 产生：
   * deterministic conflicts
   * subject registry collisions
   * concurrent hard-memory reconciliation reviews
   * missing relation reviews

Deterministic findings：

* 两侧创建相同 Canonical-Ref 的不同 Subject ID。
* 两侧创建相同 normalized alias 的不同 Subject ID。
* 两侧为同一 Scope+Subject+Facet 创建不同 active owner。
* 一侧 supersede 某 entry，另一侧仍基于旧 entry 创建 active relation。
* 一侧 merge Subject，另一侧继续引用被合并 Subject。

Review findings：

* 两侧都在同一 managed hard-memory file 中新增 active entries，但 identity 不同。
* 两侧都修改同一 Subject 的不同 Facet，且没有 `Related` 或 process acknowledgement。
* 两侧创建没有 Canonical-Ref、exact alias 不同的新 custom Subjects。
* 一侧新增 project constraint，另一侧新增可能受其覆盖的 area constraint。
* 两侧 Evidence 指向互相变化的 authoritative files。

这些 REVIEW finding 不断言内容矛盾。它们只表示：

```text
Concurrent hard-memory changes require semantic reconciliation.
```

### 7.7 Reconciliation acknowledgement

Merge-aware REVIEW 不能仅靠时间流逝消失。提供显式、可审查的 resolution artifact，推荐使用：

```text
Reconciled-With: <ENTRY_ID>
Reconciliation: distinct | superseded | exception | subject-merged
```

或独立 reconciliation record。实现时选择一种规范性表示，并满足：

* 双方 Entry IDs 可追溯。
* resolution 类型来自枚举。
* `distinct` 表示 reviewer 明确确认两者管理不同 invariant。
* `superseded` 必须与 Supersedes relation 一致。
* `exception` 必须与 Exception-To 一致。
* `subject-merged` 必须与 Subject merge 结果一致。
* Reconciliation mutation preview-first。
* 不能使用空字符串或任意 prose 作为唯一 acknowledgement。
* Evidence 或 `user-confirmed` 记录 reviewer 依据。
* 新的后续修改可以重新触发 review。

### 7.8 Subject merge

新增：

```bash
memory-custodian subject merge MC-SUBJ-source \
  --into MC-SUBJ-target
```

Preview 必须列出：

* source 与 target registry units
* 所有引用 source 的 active、superseded、candidate entries
* 将更新的 files
* alias/canonical-ref collision
* relation changes
* resulting conflict identities
* blockers
* Plan ID

Apply：

* 使用 mutation lock。
* 使用 Plan ID 和 stale digest guard。
* 将引用统一更新到 target。
* source 标记 `Status: merged`。
* 添加 `Merged-Into: <TARGET_ID>`。
* target 可添加 `Merged-From: <SOURCE_ID>`。
* 不删除 source audit history。
* 若合并后产生多个 active Scope+Subject+Facet owner，阻止 apply，要求先 supersede、exception 或 distinct reconciliation。
* 不自动选择 target。
* 不根据较早/较新时间决定 target。
* Hard forget/purge 的 subject privacy rules 继续适用。

### 7.9 CI 与团队工作流

推荐但不强制 Git 成为运行条件：

```bash
memory-custodian check --conflicts
memory-custodian audit --merge-base origin/main
```

在启用 MemoryCustodian 的团队 CI 中：

* 当前-memory deterministic `CONFLICT/INVALID` 必须失败。
* merge-aware deterministic conflict 必须失败。
* merge-aware REVIEW 是否阻止合并由项目 policy 决定；新模板 SHOULD 默认要求 reconciliation。
* CI 输出不得声称静态检查等同完整语义证明。
* README 必须说明短文件和时间戳只提高 reviewability，不构成矛盾检测。

---

## 八、Local Overlay

### 7.1 目标

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

### 7.2 位置

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

不得放入：

```text
项目 repo
docs/memory/
.git/
```

Local path 由 `project_id` 绑定，不由可移动的 project path 作为唯一身份。

### 7.3 Local manifest

Local manifest 只能声明 local modules，不得重新定义 shared routes。

示例：

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
* Local overlay 缺失时 read 正常工作。
* Local overlay corrupt 时 shared context 仍可生成，但 routing completeness 至少为 REVIEW/INCOMPLETE，并明确 local failure。
* Local modules 只能使用 `Scope: local-user` 或 `Scope: local-machine`。
* Shared entries 不能使用 local scope。
* Local overlay 不能引用 repo 外的任意文件作为 runtime module。

### 7.4 Precedence

固定优先级：

1. System、current user、safety 和 permission boundaries
2. Shared project hard constraints 与 do-not-use
3. Shared decisions and rules
4. Local preferences/profiles
5. Current task convenience

因此：

* Local preference 可以改变格式风格。
* Local preference 不能解除 shared constraint。
* Local profile 与 shared rule 冲突时 shared rule 优先。
* 冲突必须在 `read --explain` 中显示 warning。
* `--no-local` 必须产生完全不包含 local overlay 的 shared context。

### 7.5 CLI

至少支持：

```bash
memory-custodian local status
memory-custodian local enable
memory-custodian local add "Prefer concise output." \
  --type preference \
  --evidence user-confirmed
memory-custodian local reset
memory-custodian read --no-local
```

要求：

* `local reset` preview-first。
* 需要 v0.10 Plan ID 与 mutation lock。
* 只能删除当前 project_id 的 local overlay。
* 不影响 shared memory。
* 不影响其他项目。
* Security/privacy scan 对 local 内容同样适用。
* Local secrets 仍然拒绝或 ERROR，不因 repo 外而被视为安全。

---

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

* ID lookup 跨 canonical shared files、areas 和 inbox。
* 默认不搜索 archive，除非 `--include-archive`。
* 默认不搜索 local，除非 `--local`。
* Duplicate ID 为 ERROR。
* `show` 显示完整 canonical entry 与 source path。
* `forget --id` 比 topic matching 更优先、更精确。
* `promote` 创建新的 active ID，并更新双向 promotion relation。
* 所有 multi-file mutation 使用 v0.10 lock、Plan ID 和 stale digest guard。
* Hard forget/purge 的输出不得泄露敏感 topic。
* Legacy unit 可列出，但没有伪造 ID；使用 file/unit reference。

---

## 十、Reachability、Freshness 与 Conflict Audit

v0.11 可以先通过 `check` 子命令提供，v0.12 再统一到正式 `audit`：

```bash
memory-custodian check --routing
memory-custodian check --reachability
memory-custodian check --freshness
memory-custodian check --conflicts
memory-custodian audit --merge-base origin/main
memory-custodian subject list
memory-custodian subject merge MC-SUBJ-old --into MC-SUBJ-new
memory-custodian check --conflicts
memory-custodian audit --merge-base origin/main
```

### 9.1 Routing audit

至少检测：

* Missing canonical route
* Duplicate module declaration
* Unsafe module path
* Invalid task name
* Rule 没有 tasks 或 explicit activation
* Profile 非 explicit activation
* Area 没有 paths 且不是 explicit-only
* Invalid glob
* Contradictory metadata
* Required module missing
* Root constraints 未在 substantial route 可达
* Adapter 内置第二套路由表

### 9.2 Reachability audit

必须建立静态 reachability graph：

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
* optional module enabled 但没有任何 activation path：ERROR
* superseded entry 不作为 active reachability requirement
* candidate 不属于 normal reachability
* archive entry 不属于 active reachability

不得：

* 自动移动条目
* 自动添加 glob
* 自动把 module 改为 always-load
* 根据条目文本猜测它应属于哪个 area

### 9.3 Freshness audit

Evidence-aware 检查：

* `repo:path@revision` 当前 Git revision 不一致时，若 Git 可用则 WARNING。
* `repo:path`、`doc:path`、`test:path` 不存在时 ERROR 或 WARNING，按 Evidence admissibility 规则处理。
* issue/pr Evidence 不联网验证。
* 长期未更新的 entry 可以基于记录时间提示 REVIEW，但不能仅因年龄自动判 stale。
* Superseded relation 指向不存在 entry 时 ERROR。
* Subject、Facet、Exception-To、Merged-Into 和 reconciliation relations 参与 conflict/freshness review。
* Freshness finding 不自动改写 Evidence。
* Git 不可用时显示 INFO，不阻塞核心功能。

---

## 十一、Adapters 与 Agent Workflow

所有 adapters 必须统一为：

1. 定位 `manifest.md`。
2. 识别 canonical task。
3. 收集或声明 touched paths。
4. 调用或遵循同一 shared routing implementation。
5. 在 substantial work 前检查 routing completeness。
6. INCOMPLETE 时补齐 paths/areas，或明确向用户报告 scope 不完整。
7. 遵守 trust boundary。
8. 不直接加载整个 `docs/memory/`。
9. 不自行维护第二套路由表。
10. meaningful decision 后按 Evidence admission 更新 memory。
11. 创建 hard-memory entry 前复用现有 Subject ID，不凭自由文本创建第二个 identity。
12. merge/rebase 前运行 current-memory conflict check；Git 可用时运行 merge-aware review。
13. 遇到 REVIEW 时显式建立 distinct、supersede、exception 或 subject-merge resolution。

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

---

## 十二、协议迁移

实现 Protocol 0.6 → 0.7 migration。

### 11.1 Migration 必须做到

* Preview-first。
* 使用 v0.10 Plan ID。
* 使用 mutation lock。
* 保留 `project_id`。
* 保留所有 Entry IDs、Evidence 和 relations。
* 保留 custom task routes。
* 保留 enabled optional modules。
* 添加 routing schema metadata。
* 不自动创建 local overlay。
* 不自动添加 area globs。
* 不自动改变 custom route semantics。
* 不自动把 root constraints 加入 custom routes。
* 不自动将 shared preferences 移动到 local。
* 保留 v0.10 `subjects.md`、Subject IDs、Canonical-Refs 与 aliases。
* 不自动合并 legacy or duplicate Subjects。
* 不根据 entry 标题、正文或时间戳推断 Subject。
* 添加 conflict schema metadata。
* 对缺 Subject/Facet 的 managed legacy entries输出 manual assignment checklist。
* 不丢失 human-readable module descriptions。

### 11.2 Optional module migration

对旧 optional index：

* 可识别 module path 时保留。
* 现有自然语言 trigger 保留为 description。
* 缺 machine-readable route metadata 时：
  * area：`Manual path mapping required`
  * rule：`Manual task mapping required`
  * profile：可迁移为 `activation: explicit`
* 缺 metadata 不阻塞 protocol migration，但：
  * `check --routing` 报 WARNING 或 ERROR
  * substantial read 可能为 INCOMPLETE
* 不从文件内容、目录名称或 description 自动推断 matcher。

### 11.3 Default template migration

新项目模板必须使用：

* global constraints safety baseline
* canonical task routes
* machine-readable rule tasks
* explicit profiles
* path-routed example areas 仅在 enable 时写入用户指定 paths，不能默认猜测项目结构

`memory-custodian enable area/frontend` 应要求：

```bash
--path 'frontend/**'
```

或创建 explicit-only area，并明确提示尚未配置 automatic matching。

---

## 十三、需要修改的仓库区域

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

* Routing input normalization
* Manifest module declaration parser
* Cross-platform path/glob matcher
* Routing result/disposition model
* Routing completeness calculator
* Explain renderer
* Entry index
* Reachability graph
* Freshness findings
* Local overlay state
* Shared/local precedence
* Protocol 0.6 → 0.7 migration
* Subject registry index
* Structural conflict graph
* Scope overlap evaluator
* Exception relation validation
* Merge-base change collector
* Merge reconciliation finding model
* Subject merge planner

如现有结构已有类似模块，应扩展现有模块，不要在 adapter 或 `main.py` 中复制 routing logic。

---

## 十四、测试要求

### 13.1 Unit tests

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
* Subject merge updates all references atomically。

### 13.2 Integration tests

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
* Reconciled distinct entries。
* Subject merge creates downstream owner conflict。

验证：

* 同样 input 产生同样 loaded/skipped sets。
* 同样 input 产生同样 reason order。
* 不同 OS path 表示规范化为同一 repo path。
* No-path substantial task 不静默显示 complete。
* Strict mode 在 incomplete scope 下失败。
* `--no-local` hash 或 text 可复现。
* Migration 不丢 custom route。

### 13.3 Skill evals

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
15. Concurrent hard-memory changes produce reconciliation review。
16. Agent does not use timestamps to pick a winner。
17. Subject merge is explicit and preview-first。

静态 checker 不得声称验证真实 agent runtime compliance。

### 13.4 Determinism tests

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

## 十五、CLI 输出规范

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

错误输出：

* Invalid manifest、invalid path、ambiguous route、strict incomplete 输出 stderr。
* 普通 inspect 模式下的 incomplete warning 可在 stdout summary 与 stderr warning 中择一统一实现，但文档必须稳定。
* 不得输出 “nothing relevant found” 作为 no-match reason。
* 不得隐藏 omitted entries。
* 不得把 no path match 与 scope missing 混为同一 reason。

v0.11 可以保持 text-first；v0.12 再提供稳定 machine-readable JSON contract。

---

## 十六、文档要求

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
* optional `audit --merge-base`
* explicit supersede、exception、distinct reconciliation 与 subject merge

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
* merge-aware reconciliation review

不得描述为 automatic semantic retrieval、complete contradiction detection 或 automatic conflict resolution。

---

## 十七、完成标准

只有满足以下全部条件才算完成：

### Protocol

* Package version 为 0.11.0。
* Protocol version 为 0.7。
* Entry schema 仍为 1。
* Subject schema version 为 1。
* Conflict schema version 为 1。
* Routing schema version 为 1。
* Local overlay schema version 为 1。
* Protocol 0.6 项目仍可安全读取并迁移。
* 不发生 protocol downgrade。

### Routing

* Manifest 仍是唯一 shared routing authority。
* CLI 不执行自由文本 semantic relevance scoring。
* Root constraints 对新模板 substantial tasks 默认加载。
* Area routing 仅由 path matcher 或 explicit area 决定。
* Rules 仅由 canonical task 或 explicit rule 决定。
* Profiles 默认仅显式加载。
* 每个 enabled module 都有唯一 disposition。
* `read --explain` 列出 loaded 与 skipped 原因。
* No-path substantial task 不静默显示 complete。
* `--strict-routing` 对 incomplete/ambiguous scope 失败。
* 相同 task、paths 与 explicit modules 产生确定结果。
* `check --conflicts` 确定性检测 duplicate active owner、registry collision 和 invalid exception。
* `read` 显示 conflict status。
* `--strict-routing` 阻止 deterministic conflict 下的 substantial work。
* Git 可用时，merge-aware audit 能区分 deterministic conflict 与 reconciliation review。
* 异名且无 exact canonical metadata 的 Subject 不会被错误自动合并。

### Memory quality

* Unreachable active hard constraint 被报告为 ERROR。
* Candidate 不进入 normal context。
* Superseded entries 不作为 active invariant。
* Freshness finding 不自动改写 memory。
* 时间戳不作为冲突 precedence。
* Subject rename 不改变 Subject ID。
* Subject merge preview-first，并在产生 active owner conflict 时拒绝。
* Explicit Exception-To 与 reconciliation relation 可审计。
* Budget omission 显示 Entry IDs 或稳定 legacy references。

### Local overlay

* Local overlay 永远在 repo 外。
* Local project_id 与 shared project_id 一致。
* Local preference 不能覆盖 shared hard memory。
* `--no-local` 产生可复现 shared context。
* Local reset 不影响 shared memory 或其他项目。
* Local content 同样经过 privacy/security checks。

### Tooling and documentation

* ID-based list/show/forget/promote 可用。
* 所有 adapters 使用同一 routing implementation。
* Adapter 不包含第二套路由表。
* README、Skill、references、templates、examples、evals 和 dogfood 同步。
* Release notes 不夸大 semantic capability。
* 全部 unit、integration、determinism、migration、skill eval 和 repository checks 通过。
* 没有新增第三方 runtime dependency。
* 没有改变 local-first、plain-text、repo-native、minimal-context 的产品定位。
