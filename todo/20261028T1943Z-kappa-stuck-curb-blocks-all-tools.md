# kappa stuck "curb" state blocks every tool except 3 (cron/process resume paths may leak)

- **Status:** NOT-STARTED
- **Claimed by:** nobody
- **Found:** 2026-10-28T19:41Z, kappa-code live audit
- **Severity:** critical when it fires — session-wide tool lockout

## Mechanism (verified, file:line)

`GoalState.curb(id)` is set on goal start/arm when the objective text matches
`GoalInstructions.timed()` = `/wait for (the |a |an |my |our )?(deploy|build|ci)/i`
(`instructions.ts:3-9`, `runner.ts:657` and `runner.ts:828`).

While curbed, `GoalPolicy.available()` (policy.ts:37) rejects EVERY tool except
`schedule_wakeup`, `cron_create`, `background_process` with
`Tool 'X' is unavailable in the current Goal state.` — todo, bash, read, edit, MCP tools,
all of them.

`clearCurb` has only TWO call sites outside state.ts:

1. `packages/cli/src/kappacode/wakeup/resume.ts:54` — the WAKEUP-fire resume handler.
2. state.ts internals (start/pause).

## Suspected leaks (to verify then fix)

- CRON-fire resume and background-process-exit resume paths: if they re-arm the goal via a
  path that does not pass through resume.ts:54, the curb survives → permanent lockout.
- A curbed goal turn that errors/dies after `curb()` but before arming a wait (turn dies,
  curb persists; no finally/cleanup around the runner's work effect).
- Backend restart: help text says active goals become paused after restart (pause clears
  curb), but a goal that was mid-curb in a WAITING state may resurrect curbed.

## Fix direction

- Clear the curb in the same finally/ensure path that ends a goal turn (any exit: report,
  error, interrupt) unless a wait was actually armed this turn.
- Make cron-fire and process-exit resume routes call `GoalState.clearCurb` symmetrically
  with wakeup resume (or centralize: clearCurb inside arm() after a wait is armed).
- Capability-contract test: curbed goal + turn error → next turn has full tool access.

## Acceptance

- No path leaves a session curbed without an armed wait.
- Contract test green: `bun test test/kappacode/session/goal.test.ts` + wakeup tests
  (`test/kappacode/wakeup/`).
