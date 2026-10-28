# kappa goal tool fully locked while a goal is active (hold gate contradicts tool docs)

- **Status:** NOT-STARTED
- **Claimed by:** nobody
- **Found:** 2026-10-28T19:40Z, kappa-code live audit (wezterm/kappa session)
- **Severity:** high — the goal tool is unusable for its documented purpose

## Symptom

Calling the `goal` tool with action `change`/`pause`/`clear`/`resume` while a goal is
active throws:

```
Tool 'goal' is unavailable in the current Goal state.
```

## Root cause (verified, file:line)

`packages/cli/src/kappacode/session/goal/policy.ts:37-41` — `GoalPolicy.available()`:

```ts
if (tool !== "question" && tool !== "goal") return true;
if (GoalState.hold(id)) return false; // hold = active || waiting
```

`GoalState.hold()` (`state.ts`) is true whenever a goal run is active OR waiting, and the
run token persists across turns. So while ANY goal exists, the ENTIRE goal tool is gated
off — including the actions the tool description explicitly promises ("change replaces the
current objective; pause suspends the current goal; clear drops the goal"). The error comes
from the generic gate in `packages/cli/src/session/tools.ts:195`, not the tool's own
"Goal control rejected: a goal is already active." message (which was written for `start`
duplicates only).

## Fix direction

In `GoalPolicy.available()`, only reject `start` (and duplicate `resume`) while held;
allow `change` / `pause` / `clear` through the hold gate (they already cancel timers and
replace state safely in `runner.ts` arm() — `wasHeld` handling exists). Keep `goal_report`
gating unchanged. TDD: extend `packages/cli/test/kappacode/session/goal.test.ts` with a
"change while active succeeds" + "pause while active succeeds" case.

## Acceptance

- `goal change` on an active goal works from the agent.
- `goal pause` / `goal clear` on an active goal work from the agent.
- Duplicate `start` still rejected.
- `bun test test/kappacode/session/goal.test.ts` green from packages/cli.
