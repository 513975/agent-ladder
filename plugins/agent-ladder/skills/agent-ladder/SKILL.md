---
name: agent-ladder
description: Route software-development work across configurable Codex subagent model tiers with a minimum capability floor, stronger-model escalation, bounded concurrency, role isolation, fallback chains, and risk-based independent review. Use for coding, debugging, repository exploration, implementation planning, refactoring, testing, code review, or requests to view or change Agent Ladder routing configuration. Do not use for simple factual questions that require no repository work.
---

# Agent Ladder

Coordinate development work while spending stronger-model capacity only where it changes the outcome.

## Start Every Routed Task

1. Query the effective mode and configuration before choosing a child model:

   ```bash
   python scripts/agent_ladder_config.py status
   python scripts/agent_ladder_config.py effective
   ```

   Resolve `scripts/` relative to this `SKILL.md`. On systems without `python`, use the available Python 3 executable.

   - Treat an automatically matched development request as `implicit` invocation.
   - Treat the request as `explicit` only when the user names Agent Ladder or invokes `$agent-ladder` in the current request.
   - In `manual` mode, stop implicit routing. In `off` mode, stop all routing. Status and configuration operations remain available in every mode.

2. Read [routing-policy.md](references/routing-policy.md) to classify the task and apply escalation and review gates.
3. Read only the relevant role section in [roles.md](references/roles.md) before dispatching that role.
4. Resolve the selected route deterministically:

   ```bash
   python scripts/agent_ladder_config.py resolve implementation --invocation implicit
   python scripts/agent_ladder_config.py resolve implementation --invocation explicit
   ```

   Use exactly one command matching the actual invocation source. The resolver defaults to `implicit` when the flag is omitted.

5. Use the first returned candidate supported by the current Codex runtime and account. If dispatch rejects it as unavailable, try the next returned candidate only when the resolver supplied one. Never invent a model ID, lower a route floor, or silently use a candidate omitted by the resolver.

## Dispatch Children

- Use the available subagent or collaboration tool and pass the exact resolved model ID and reasoning effort.
- Give each child a bounded task, relevant paths, known evidence, acceptance criteria, and required verification.
- Prefer isolated or minimal context. Do not make a child rediscover conclusions already established by the coordinator.
- Add the role rule `Do not spawn additional agents` to every child prompt.
- Keep delegation depth at one. Enforce `max_parallel_agents`, `max_child_calls`, and `max_retries` from the effective configuration.
- When a required review gate fires and `reserve_required_review_call` is true, reserve one remaining child call before dispatching or retrying implementation. Do not spend the reserved call on exploration, retries, or fixes. If no slot can be reserved, stop and report the budget conflict instead of completing an unreviewed critical change.
- Track `used_child_calls` from zero. Before any non-review dispatch, calculate `max_child_calls - used_child_calls - reserved_review_calls`; dispatch only when the result is at least one. Increment the counter for every attempted child call, including unavailable-model attempts, retries, fixes, and reviewers.
- Dispatch independent tasks in parallel only when their write sets cannot conflict. Otherwise work sequentially.
- If no child-dispatch tool with model selection is available, state that limitation and continue only when the user accepts main-thread execution. Do not claim that routing occurred.

## Escalate Deliberately

Treat these outcomes differently:

- `NEEDS_CONTEXT`: supply missing evidence and retry the same tier up to `policy.max_retries`, while preserving any required review reservation.
- `NEEDS_DECISION`: return the architectural or product choice to the coordinator or user.
- `NEEDS_CAPABILITY`: when `policy.auto_upgrade` is true, resolve the next stronger configured route or candidate; otherwise ask before upgrading.
- `BLOCKED`: report the external blocker; do not spend another model call on an unchanged condition.

Never upgrade merely because a child failed. Diagnose whether the failure came from context, authority, environment, or reasoning capacity first.

## Review by Risk

Apply `policy.review_mode`, then use the `review` route when required by [routing-policy.md](references/routing-policy.md). The reviewer must be a fresh, read-only child and must not be the implementer reviewing its own work. For low-risk changes under `risk_based`, let the coordinator inspect the diff and focused test result without paying for a separate reviewer. Always honor an explicit user request for independent review even when automatic review is off.

## Configure Agent Ladder

When the user asks to inspect, update, or add models, read [configuration.md](references/configuration.md). Validate an override before treating it as active:

```bash
python scripts/agent_ladder_config.py validate path/to/agent-ladder.toml
```

Show the intended diff before writing a user-level or project-level override. Never edit the bundled default configuration for a user preference.

For mode changes, use the deterministic soft-switch command after confirming the requested scope:

```bash
python scripts/agent_ladder_config.py set-mode auto --scope project
python scripts/agent_ladder_config.py set-mode manual --scope user
python scripts/agent_ladder_config.py set-mode off --scope project
```

Project mode overrides user mode. Explain that `off` pauses Agent Ladder dispatch but does not disable the plugin itself; use the Codex plugin toggle for a hard disable.

## Finish

Inspect child results, the final diff, and verification evidence in the coordinator. Report which routes and model IDs were actually used, any fallback or escalation, tests run, and unresolved risk. Do not describe a planned dispatch as completed work.
