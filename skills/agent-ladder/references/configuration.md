# Configuration

Agent Ladder treats model names and capability levels as data. This lets users register future models without changing the skill.

## Configuration Precedence

The resolver deep-merges these sources in order:

1. Bundled `assets/default-config.toml`
2. User override at `$CODEX_HOME/agent-ladder.toml`, or `~/.codex/agent-ladder.toml` when `CODEX_HOME` is unset
3. Project override at `<cwd>/.codex/agent-ladder.toml`
4. An explicit file passed with `--config`

Tables merge recursively. Scalars and arrays in later sources replace earlier values.

Runtime mode files are applied after TOML configuration. The user mode file is `$CODEX_HOME/agent-ladder.mode` (or `~/.codex/agent-ladder.mode`), and the project mode file is `<cwd>/.codex/agent-ladder.mode`. The project mode file has final precedence.

## Register a Future Model

Add a model alias and place it in selected route fallback chains:

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

The resolver never guesses that a model is stronger from its name. Set `tier` explicitly. A larger tier means greater configured capability, not a verified benchmark or price claim.

## Preserve the Minimum Floor

`minimum_tier` is the global capability floor. A route may raise, but not lower, that floor. The validator enforces tier 100 as a hard minimum, so an override cannot select a model below Terra's default tier.

`denied_model_patterns` applies case-insensitive regular expressions to both aliases and model IDs. Luna is also hard-denied by the resolver, so clearing the configurable array cannot re-enable it.

## Configure a Route

```toml
[routes.complex_implementation]
models = ["sol"]
reasoning_effort = "high"
minimum_tier = 200
```

Candidates are tried in listed order. `minimum_tier` removes candidates below the route's required level. If no eligible candidate remains, the resolver returns an error and the coordinator must stop rather than silently downgrade.

Supported reasoning efforts are `low`, `medium`, `high`, `xhigh`, `max`, and `ultra`. Runtime availability still depends on the selected model and Codex environment.

## Policy Controls

```toml
[policy]
mode = "auto"
auto_upgrade = true
review_mode = "risk_based"
max_parallel_agents = 2
max_child_calls = 4
max_depth = 1
max_retries = 1
reserve_required_review_call = true
```

- Keep `max_depth = 1` to prevent recursive child delegation.
- Count implementation retries and reviewer calls toward `max_child_calls`.
- Reserve one call for a required Reviewer before spending calls on implementation retries.
- Keep `reserve_required_review_call = true`; the validator rejects persistent disabling. A user may explicitly waive critical review only for the current task.
- Set `review_mode` to `risk_based`, `always`, or `off`. `off` disables automatic noncritical review, but not critical review or review explicitly requested by the user.
- Disabling `auto_upgrade` requires the coordinator to ask before selecting a stronger route.

## Runtime Modes

- `auto`: allow both automatically matched and explicit `$agent-ladder` routing.
- `manual`: allow routing only when the current user request explicitly names or invokes Agent Ladder.
- `off`: block all subagent routing while leaving status and configuration commands available.

Use a project soft switch by default:

```bash
python scripts/agent_ladder_config.py set-mode auto --scope project
python scripts/agent_ladder_config.py set-mode manual --scope project
python scripts/agent_ladder_config.py set-mode off --scope project
```

Use `--scope user` only when the user requests the same default across projects. The command writes one validated word to `agent-ladder.mode` using a temporary file and replacement. It does not rewrite TOML. Use the Codex plugin toggle when the user wants a hard disable that prevents the Skill from loading.

## Commands

```bash
python scripts/agent_ladder_config.py effective
python scripts/agent_ladder_config.py status
python scripts/agent_ladder_config.py resolve complex_implementation --invocation implicit
python scripts/agent_ladder_config.py resolve complex_implementation --invocation explicit
python scripts/agent_ladder_config.py set-mode manual --scope project
python scripts/agent_ladder_config.py validate .codex/agent-ladder.toml
python scripts/agent_ladder_config.py paths
```

The commands emit JSON so the coordinator can use the result without parsing prose.
