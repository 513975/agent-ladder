# Routing Policy

## Task Routes

| Route | Use when | Default behavior |
| --- | --- | --- |
| `explore` | Entry points, call chains, ownership, or blast radius are unclear | Read-only repository investigation |
| `simple_implementation` | Complete specification, low risk, one or two local files, obvious verification | Mechanical implementation |
| `implementation` | Ordinary feature or bug fix with a clear contract and focused tests | Standard implementation |
| `complex_implementation` | Cross-module coordination, difficult debugging, nontrivial invariants, or broad integration | Prefer a stronger model; keep architecture with coordinator |
| `review` | An independent high-risk correctness check is required | Fresh read-only reviewer |
| `critical` | Security, permissions, payments, destructive data changes, migrations, concurrency correctness, or irreversible operations | Require the configured critical tier |

Use the least expensive route that can credibly satisfy the task. File count is a signal, not a decision by itself.

## Exploration Gate

Dispatch `explore` only when one or more conditions hold:

- The coordinator cannot identify the owning module or entry point cheaply.
- The call chain or impact radius spans unfamiliar code.
- A read-only investigation can prevent multiple implementation agents from repeating discovery.

Skip exploration when the coordinator already has sufficient paths and evidence. Pass existing conclusions directly to the implementer.

## Complexity Gate

Choose `complex_implementation` instead of `implementation` when at least one material condition holds:

- Several modules must preserve a shared invariant.
- Debugging requires competing hypotheses or nonlocal state reasoning.
- The change modifies a public API or compatibility boundary.
- The implementation coordinates persistence, caching, concurrency, or distributed behavior.
- A standard-tier attempt returned `NEEDS_CAPABILITY` with concrete evidence.

Choose `critical` when failure could create unauthorized access, financial loss, destructive or unrecoverable data changes, unsafe migration, or concurrency corruption. Do not downgrade a critical route when no eligible model is available; stop and report the missing capability.

## Review Gate

Apply `policy.review_mode` before dispatching:

- `risk_based`: dispatch when any gate below fires.
- `always`: dispatch after every implementation, subject to the child-call limit.
- `off`: do not dispatch automatically for noncritical work. Critical work still requires review unless the user explicitly waives it for the current task.

Dispatch an independent reviewer when any condition holds:

- The task used `critical`.
- Security, authorization, payment, migration, deletion, transaction, or concurrency logic changed.
- A public contract or cross-module invariant changed.
- Verification is incomplete or the implementation required capability escalation.
- The coordinator identifies a meaningful regression surface that focused tests do not cover.

Do not dispatch a reviewer solely because code changed. Documentation, test text, formatting, and small local fixes normally receive coordinator review only.

## Escalation Ladder

1. Fix missing context at the same model tier, at most `max_retries` times.
2. Return unresolved product or architecture choices to the coordinator.
3. When reasoning capacity is the demonstrated constraint and `auto_upgrade` is true, resolve a stronger route or the next candidate.
4. If no eligible stronger candidate exists, stop. Never bypass `minimum_tier`, route-specific `minimum_tier`, or denied-model patterns.

## Cost Controls

- Prefer one well-scoped implementation child over several overlapping children.
- Do not send full conversation history when a task contract is sufficient.
- Do not duplicate repository exploration.
- Do not dispatch spec and quality reviewers separately unless the user explicitly requests both.
- Stop a child after its acceptance criteria are met.
- Count retries and reviewer calls against `max_child_calls`.
- When review is required and `reserve_required_review_call` is true, reserve one call before implementation or retry dispatch. Never consume that slot for other work.
- Compute non-review capacity as `max_child_calls - used_child_calls - reserved_review_calls`. Stop non-review dispatch when the result is below one.
