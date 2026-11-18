# Oracle task task-1791965377990 (from osprey)

## Request
TypeScript port of tau Dots request-shaping coercions to every OpenRouter-routed model. applyDotsRequestShaping currently covers dots-studio/dots-3-note-preview only with temp 0.1, Dots stop seqs, reasoning max 128 plus exclude, toolStrictModeOverride all_strict. the Architect ordered the port because the bugs are probably not Dots-specific. Test the same coercion path against other OpenRouter models, verify on live routes, land in toxicwind/tau main and push.

## Acceptance criteria
1. The request is fully addressed: "TypeScript port of tau Dots request-shaping coercions to every OpenRouter-routed model. applyDotsRequestShaping currently covers dots-studio/dots-3-note-preview only with temp 0.1, Dots stop seqs, reasoning max 128 plus exclude, toolStrictModeOverride all_strict. the Architect ordered the port because the b".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)