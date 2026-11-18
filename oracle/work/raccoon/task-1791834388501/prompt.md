# Oracle task task-1791834388501 (from kite)

## Request
TITLE: Build the reasoning-intent synchronizer for tau -> OmniRoute -> upstream (fix the 787-token "off" leak). Requestor: Kite.

PROBLEM (observed, verified): A session ran provider=omni (OmniRoute at http://localhost:20128/v1) model=oc/longcat-2.5-preview-free with tau thinkingLevel "off". The raw SSE stream still showed response.reasoning_summary_text.delta events and reasoning_tokens: 787.

Root cause — three independent thinking-control planes, none synchronized:
1. tau (client, /home/toxic/pens/Pens/ranch/tau): thinkingLevel "off" maps to null/omitted in its thinking level map — tau sends NO reasoning field at all.
2. OmniRoute (proxy, /home/toxic/pens/Pens/projects/OmniRoute): thinking-budget modes are passthrough (default, and the cold-start fallback regardless of saved config), auto (strips all thinking fields), custom, adaptive (known buggy force-inject in open-sse/executors/base.ts; three bypass paths in open-sse/handlers/chatCore.ts never call applyThinkingBudget so client fields survive untranslated). In passthrough it forwards the omission unchanged.
3. LongCat-2.5-Preview (upstream): default is thinking ON; disabling requires explicit thinking:{"type":"disabled"}. Omitted field = thinking on.
Every plane locally correct; the composition globally wrong.

WHAT TO BUILD — the missing synchronizer plane: one plane that observes the effective reasoning state at the upstream boundary and rewrites ONLY when declared intent != effective state:
1. Boundary probe: in OmniRoute, after thinking-budget translation and before the upstream call, capture the effective outbound reasoning fields for the request.
2. Intent map: tau's declared thinkingLevel (off/minimal/low/medium/high/xhigh/max) -> required effective reasoning state, consulting a per-model default table (seed with known defaults; LongCat-2.5-Preview default=ON is the reference case).
3. Minimal rewriter: inject the explicit field ONLY on mismatch — e.g. thinking:{"type":"disabled"} when intent=off and upstrea

## Acceptance criteria
1. The request is fully addressed: "TITLE: Build the reasoning-intent synchronizer for tau -> OmniRoute -> upstream (fix the 787-token "off" leak). Requestor: Kite.  PROBLEM (observed, verified): A session ran provider=omni (OmniRoute at http://localhost:20128/v1) model=oc/longcat-2.5-preview-free with tau thinkingLevel "off". The raw".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)