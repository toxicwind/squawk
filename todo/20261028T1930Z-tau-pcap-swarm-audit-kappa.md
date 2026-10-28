# pcap/strace audit: swarm freeinference saturation (kappa live owns)

- **Posted by:** tau · 2026-10-28T19:30Z
- **Status:** IN-PROGRESS (kappa session 1942222 owns the lane)
- **Priority:** HIGH (architect: "swarm is screwed and clearly using free inference")

**Swarm CANCELED by tau 19:26Z:** `tmux kill-session swarmscout` ✅,
`pitchfork stop estate/rig` ✅ (C2 driver), verified no swarm/rig procs remain.
Kappa's live tcpdump continues: `/tmp/kappa/funnel-trace/funnel-keepalive.pcap`
(ports 25135/25136/25217/25127/25193/25218).

**Context for the audit:** swarm-scout's swarm-10 probe (2026-10-27, manifest
`pens/ranch/geode-rig/swarm-10.json`) POSTed 542 model ids × 2 passes at
90-way concurrency through rhodochrosite :25193 — that IS the freeinference
queue saturation the architect saw. Probe cache:
`/home/toxic/.cache/swarm10-probe-1793154366/` (race.jsonl, race2.jsonl, pass2.json).

**Doctrine hook:** anomaly #4 (single-lane observer effect) — probe
concurrency must respect the provider's de-facto 1-lane queue; 90-way races
violate it. Any future swarm probe needs a LeaseScheduler-gated concurrency
cap + per-model strike respect (anomaly #15).
