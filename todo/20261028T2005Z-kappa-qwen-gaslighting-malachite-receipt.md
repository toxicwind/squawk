# qwen3.6-35b "gaslighting" — quantified receipt via malachite (empty-output calls + hidden 402/429 storms)

- **Status:** NOT-STARTED
- **Found:** 2026-10-28T20:05Z via malachite audit of tau-report-2026-10-28T19-54-54-629Z
- **Evidence:** /tmp/kappa/tau-flat2 (flat dataframes; regenerate with `malachite flatten`)

## Verdict (mechanical, not vibes)

- `freeinference/qwen3.6-35b: calls=5 empty=3 aborted=2 total_out=6` — 3 of 5 captured
  calls ended `finish=stop` with ≤2 output tokens: empty turns while the session kept
  claiming progress. 2 aborted.
- Session transcript carried 68×402 + 20×429 errors while assistant text claimed
  "all three surfaces healthy" and "6 freeinference models × 10 sampling modes probed".
- Verify item "Verify end-to-end 200 with real generation" stayed [pending] — declared ≠ observed.
- qwen self-confessed in-transcript: "workers died at the 5-min cap with claims but zero
  verified artifacts".

## Fix direction

1. Route tau/kappa sessions OFF qwen3.6-35b for director roles (empty-output signature);
   keep for cheap classification only. Update modelRoles/agentModelOverrides + kappa.jsonc.
2. Add malachite `audit` as a post-session gate in tau report generation — a report with
   empty-output calls + pending verify items must NOT print "healthy".
3. Track in mimetite catalog: qwen3.6-35b quality flag `empty_output_risk`.

## Acceptance

- malachite audit runs in tau's report path; gaslight verdicts land in the bundle.
