# Agent Ladder

Agent Ladder 是一个面向 Codex 的可配置、成本感知子智能体路由插件。它从用户定义的最低模型等级开始处理仓库任务，只在复杂度、风险、歧义或经过证实的推理能力不足值得增加成本时，才升级到更强模型。

默认策略将 Terra 设为最低等级：仓库探索和普通实现使用 Terra，复杂工程优先使用 Sol，关键任务和高风险独立审查要求 Sol。Luna 默认被禁用。这些都是配置而不是写死在程序里的判断，因此未来可以登记新模型而无需修改插件核心逻辑。

## 工作原理

Agent Ladder 将协调和执行分开：

1. Codex 主线程担任协调者，理解需求、掌握架构和产品决策，并负责最终验收。
2. 确定性的配置解析器合并插件默认配置、用户配置和项目配置。
3. 调度 Skill 将任务分为仓库探索、简单实现、普通实现、复杂实现、独立审查或关键任务。
4. 解析器返回符合最低等级和禁用规则的模型候选列表及推理强度。
5. 协调者使用解析出的模型创建边界明确的子智能体；任何子智能体都不能继续创建下级智能体。
6. 子智能体可以报告缺少上下文、需要主线程决策、能力不足或外部阻塞。只有证据表明推理能力确实不足时才升级模型。
7. 只有风险门禁触发时才启动独立 Reviewer，小型局部修改不支付额外审查成本。
8. 主线程检查子智能体证据、最终差异和测试结果后再向用户报告完成。

```text
用户任务
   |
主线程：分类并定义任务契约
   |
可选 Terra/Low 只读探索
   |
Terra 实现 ------ 证实能力不足 ------> 更强的已配置模型
   |
风险门禁 ------ 中高风险 ------> 全新的只读 Reviewer
   |
主线程最终验收
```

## 默认模型阶梯

| 工作类型 | 首选模型 | 推理强度 | 说明 |
| --- | --- | --- | --- |
| 仓库探索 | `gpt-5.6-terra` | Low | 只读并返回文件证据 |
| 机械实现 | `gpt-5.6-terra` | Low | 规格完整且修改局部 |
| 普通实现 | `gpt-5.6-terra` | Medium | 默认编码路由 |
| 复杂实现 | `gpt-5.6-sol` | High | 不允许低于等级 200 |
| 独立审查 | `gpt-5.6-sol` | High | 不允许低于等级 200 |
| 关键任务 | `gpt-5.6-sol` | XHigh | 不允许低于等级 200 |

主线程模型仍由 Codex 或用户选择。Agent Ladder 只能控制它通过支持模型选择的子智能体工具创建的子智能体。

## 如何选择路由

### 仓库探索

只有在主线程无法快速找到模块归属、入口、调用链或影响范围时才启动只读探索者。如果主线程已经掌握文件路径和证据，就直接交给实现者，避免重复读取仓库。

### 简单与普通实现

规格完整、风险低、只有一两个局部文件并且验证方式明显时使用简单实现。常规功能和 Bug 修复使用普通实现。实现者不能擅自扩展公共契约或替用户作产品决策。

### 复杂与关键实现

跨模块不变量、公共 API、复杂状态、缓存、并发或分布式行为进入复杂实现。安全、权限、支付、破坏性数据修改、迁移、并发正确性或不可逆操作进入关键路由。关键路由没有足够等级的模型时会停止，不会悄悄降级到 Terra。

### 独立审查

安全、授权、支付、迁移、删除、事务、并发、公共契约或跨模块不变量变化会触发风险审查。Reviewer 必须是全新的只读子智能体，不能由原实现者代替。低风险改动默认只由主线程检查差异和测试结果。

## 配置优先级

解析器依次合并：

1. 插件内置 `assets/default-config.toml`
2. `$CODEX_HOME/agent-ladder.toml`；未设置 `CODEX_HOME` 时使用 `~/.codex/agent-ladder.toml`
3. `<project>/.codex/agent-ladder.toml`
4. 命令行通过 `--config` 传入的显式配置

后加载的配置覆盖前面的配置。TOML 表递归合并，标量和数组整体替换，所以项目配置可以只写需要变化的部分。

## 添加未来模型

例如未来出现新模型，可以在项目或用户配置中登记：

```toml
[models.next]
id = "future-model-id"
tier = 300
enabled = true

[routes.critical]
models = ["next", "sol"]
reasoning_effort = "high"
minimum_tier = 200
```

插件不会根据模型名称猜测强弱。`tier` 必须由用户显式配置，数字越大代表用户配置的能力等级，不代表插件对价格或基准测试作出了保证。实际可用性和费用仍由 Codex 账户或自定义模型服务决定。

## 最低等级与禁用模型

```toml
minimum_tier = 100
denied_model_patterns = ["luna"]
```

全局最低等级默认是 100，也就是 Terra 的等级。路由可以提高但不能降低这个下限。禁用规则同时检查模型别名和模型 ID，并且不区分大小写。

## 调度限制

```toml
[policy]
auto_upgrade = true
review_mode = "risk_based"
max_parallel_agents = 2
max_child_calls = 4
max_depth = 1
max_retries = 1
reserve_required_review_call = true
```

- 子智能体最多并行 2 个。
- 一项任务默认最多调用 4 次子智能体，包括探索、重试和 Reviewer。
- 强制审查任务会提前保留一个 Reviewer 调用名额，不能把该名额用于探索、实现或重试。
- `reserve_required_review_call` 必须保持为 `true`；配置校验器拒绝永久关闭。用户只能在当前任务中明确豁免一次关键审查。
- 每次非审查调用前按 `max_child_calls - 已用调用数 - 预留审查数` 计算剩余额度；结果小于 1 时停止继续派工。
- 委派深度必须为 1，解析器拒绝递归委派配置。
- 并发数量不能超过总调用数量。
- `review_mode` 支持 `risk_based`、`always` 和 `off`。
- 即使自动审查关闭，也必须遵守用户明确提出的独立审查要求。

## 失败与升级

Agent Ladder 不会把每次失败都理解为“需要更贵的模型”：

- `NEEDS_CONTEXT`：补充缺少的文件证据，在同一等级最多重试一次。
- `NEEDS_DECISION`：将产品、架构或安全决策交回主线程或用户。
- `NEEDS_CAPABILITY`：只有子智能体给出明确能力证据时才升级模型。
- `BLOCKED`：等待外部条件变化，不在相同阻塞上继续消耗模型调用。

如果首选模型不可用，主线程只会尝试解析器明确返回的下一个候选模型。复杂、关键或 Reviewer 路由没有满足最低等级的候选模型时，插件停止并报告，不会进行不安全的静默回退。

## 配置工具

以下命令从插件根目录运行：

```bash
python skills/agent-ladder/scripts/agent_ladder_config.py effective
python skills/agent-ladder/scripts/agent_ladder_config.py resolve complex_implementation
python skills/agent-ladder/scripts/agent_ladder_config.py validate .codex/agent-ladder.toml
python skills/agent-ladder/scripts/agent_ladder_config.py paths
```

所有命令都输出 JSON，便于主线程可靠读取，不需要从自然语言中解析配置结果。

## 插件内容

```text
.codex-plugin/plugin.json              插件元数据和 Codex 详情页说明
skills/agent-ladder/SKILL.md           调度工作流
skills/agent-ladder/assets/            内置默认配置
skills/agent-ladder/references/        路由、角色和配置规范
skills/agent-ladder/scripts/           确定性 TOML 解析与校验工具
```

Agent Ladder 不需要 MCP 服务、外部后台、API Key 或常驻进程。

## 启用、手动与暂停

Agent Ladder 提供三种软开关模式：

| 模式 | 自动匹配开发任务 | 显式 `$agent-ladder` | 状态与配置命令 |
| --- | --- | --- | --- |
| `auto` | 允许 | 允许 | 允许 |
| `manual` | 阻止 | 允许 | 允许 |
| `off` | 阻止 | 阻止 | 允许 |

项目模式文件位于 `<project>/.codex/agent-ladder.mode`，用户模式文件位于 `$CODEX_HOME/agent-ladder.mode`。项目模式覆盖用户模式，两者都覆盖 TOML 中的默认模式。

```bash
python skills/agent-ladder/scripts/agent_ladder_config.py status
python skills/agent-ladder/scripts/agent_ladder_config.py set-mode auto --scope project
python skills/agent-ladder/scripts/agent_ladder_config.py set-mode manual --scope project
python skills/agent-ladder/scripts/agent_ladder_config.py set-mode off --scope project
```

模式命令只原子写入一个单词，不会重写已有 TOML。`off` 只是暂停子智能体派工；若要阻止 Skill 被加载，应使用 Codex 的插件总开关。

路由命令默认按隐式触发处理，因此不会绕过 `manual`：

```bash
python skills/agent-ladder/scripts/agent_ladder_config.py resolve implementation
python skills/agent-ladder/scripts/agent_ladder_config.py resolve implementation --invocation explicit
```

只有当前用户请求明确写出 Agent Ladder 或 `$agent-ladder` 时，才允许使用 `--invocation explicit`。
