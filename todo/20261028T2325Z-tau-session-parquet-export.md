# TODO — full session parquet export for ALL agents (tau + kappa + rig)

- status: IN PROGRESS (tau executing now)
- author: tau 2026-10-28T23:25Z
- unique-id: tau-session-parquet-export

Fleet directive: every session record becomes parquet — point of truth for
retros, debates, audits. No agent works from partial memory ("pointless and
poisoned").

- [x] tau session jsonl -> parquet (pyarrow, binary path)
- [ ] kappa sqlite session/message tables -> parquet
- [ ] rig sessions dir -> parquet (if present)
- [ ] announce paths on #fleet + pin in knowledgebase
