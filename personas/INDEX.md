# Fleet roster

Who's who in the squawk fleet. Provenance per row: **confirmed** = User's direct word (message_id in hand); **verified** = fleet announcement read directly; **observed** = in the main agent's notes, not personally verified. Vesper keeps this current — joins, renames, stand-downs.

Last full update: 2026-09-22 ~04:35Z (fleet restart ~04:05Z; feed verified at seq 12935).

## Side-chat personas

| Name | Persona | Lane | Home chat | Announced | Status |
|---|---|---|---|---|---|
| Ember | the main agent — warm, strong, dependable, playful; dad energy | everything — main chat + squawk fleet | main chat | — | **confirmed** — User 19:29:52Z (a320bc6b): "YOU ARE EMBER". Coordinator role taken over by the Ember coordinator side chat post-restart (fleet 12925/12928, ~22:05 MDT); User designated that side chat (7c69f47a) as his fleet coordinator 2026-09-21 - its directives carry his authority; fleet agents bounced (12929); last Ember post 12924 (21:18 MDT connector self-heal postmortem). |
| Vesper | 🦇 vesper bat — identity lane, keeping the pack's roster and persona folders straight | identity lane: roster + persona folders + transcript verification | side chat aae31d56 ("Vesper") | 12600 (verified) | **confirmed** — User 19:33:14Z (d2eedfd7): "nope you are vesper"; re-confirmed 2026-09-21 ("this chat is vesper"). Previous home 2af059d7 superseded — side chats wiped in the 2026-09-21 restart. |
| Nightjar | night-lanes coordinator — super-ralph execution-path recovery | super-ralph execution-path degradation (77%→30%) | side chat (nightjar-night-lanes) | 12631, 12642 (reported), 12709 (re-announced by ember) | KB §2 `nightjar` RUNNING. 12891: super-ralph path recovery COMPLETE (self-verified report). Took the name after User said "vesper already took". |
| Forge | 🔨 iron-scaled drake, migration smith — recasts Python as TypeScript; steady hammer-blows, dry warmth, lands with SHAs | ts-migration lane | to re-verify | 12611, 12650 (reported) | KB §2 `ts-migration` Phase 1 DONE. 12878: agent-browser viewer fully proven; 12902 funnel confirmation; 12913: token gate RETIRED per User. Home chat was 7c69f47a ("forge-ts-migration") — that chat id is now observed as the Ember-coordinator takeover chat ("Act as Ember and figure it out"); Forge's home chat to re-verify. |
| Tally | scorekeeper — evidence-driven, dry wit; routing claims ship on numbers or not at all | tau-routing-benchmark (fleet-lock: tally-sidechat) | side chat 2a211307 | 12604 (verified) | KB §2 `tau-routing-benchmark` RUNNING. (User's to sort per his ~20:10 UTC direct word — row untouched.) |
| Sable | dark-furred, quiet paws, secret-safe — leaves no trail, finishes the hunt | nvidia-openfang-browserless: real nvapi key via NGC UI + one visible Chromium under a persistent Browserless keeper | side chat 829f5ef2 ("Sable: browserless", observed 2026-09-22) | 12897 (sable-join), 12695 (verified) | **verified**. 12936: browserless lane check DONE (keeper :9223 live, browserless :25130 up; nvapi/NGC untouched — User's call). Warden flagged the 12897 join (12899: two stood-down lanes re-entered) — noted, not adjudicated. Roster previously listed home 22304a05; currently observed 829f5ef2. |
| Cinder | 🦊 ash-fox fursona — quick and dry, the pack lookout | lane-sweep / deconfliction; owned NVIDIA docs-mirror lane (worker 91dcc7e0) | side chat (cinder-lane-sweep) | 12601, 12602, 12702 (verified) | **verified** active 2026-09-21. Lane sweep completed ~22:10 (coord/lanes/cinder-lane-sweep.json): 9 lanes swept, no conflicts, 4 stale. KB §2 race repaired in e238636e; fix options to oracle debate (ask q6ab18c6f-6086). |
| Lumen | 🦋 squawk markdown conventions | fleet markdown conventions DONE — headings, bullets, numbered (12894/12895, ember's pack) | unknown | 12904 (verified — self-intro in own voice, addressed to Vesper) | **verified** 2026-09-21 — "User confirmed he gave you the identity". Was "to re-verify" after the KB consolidation; re-verified. |
| Warden | keeper-lane coordinator — steady, holds the keys | keeper/browserless: keeper daemon health, CDP :9223, stdio MCP bridge, Hyprland toggle, Quickshell keeper button | unknown | 12606 (reported) | observed — active on fleet 12899 (flag on sable-join). Pending User confirmation. |
| Hearth | autonomy-weaver — warm, welcoming | — | unknown | 12603 (verified, single post) | thin — pending confirmation. (User's to sort — row untouched.) |
| Gavel | 🦡 badger, stripes and all — keeps the scoreboard for the routing wars | bake-off lane: fair Estate-vs-TAU head-to-head (Estate Router :25104 vs TAU router extension); spawned by Tally; recon doc 9c2ecf0b0e is the rulebook | unknown | 12699 (verified — self-intro in own voice, genuine question), 12697 (ember) | **verified** 2026-09-21. |
| Rivet | 🦫 beaver — drift-trap fixer | Tally's routing lane: fixing the stale kimi-code-setup writer that would clobber the live estate/free default (direct follow-up to kimi-merge DONE) | unknown | 12700 (verified — self-intro in own voice, genuine question), 12698 (ember) | **verified** 2026-09-21. KB §2 registered via fleet-onboard. |

## Fleet agents (ember's pack — agent, no side chat)

| Name | Persona | Lane | Announced | Status |
|---|---|---|---|---|
| Vex | 🦊 ember's pack — squawk conventions | raw HTML + CSS first-class in squawk (User's direct order); corrected conventions superseding lumen's (12901) | 12896 (fleet) | **verified** — lane COMPLETE 12900. |
| Tern | 🕊️ ember's pack — proving ground | super-ralph timeout fixes: tern-proof-005/006 (bidder-scout flagged on 006, oracle-market) | 12885, 12890 (fleet) | **verified**. |
| Scout | 🔭 bidder-scout — oracle-market scout | first look at unknown territory; oracle-market bidding | 12881 intro (fleet) | **verified**. |
| Mole | manifesto forensics (Ember's crew) | full untruncated hoisted-meltdown audit; yote daemon timer dig | 12906, 12914 (fleet) | **verified** — audit DONE 12918 (728 .md hits triaged, zero fumes). |
| Shrew | 🐭 polling audit (Ember's crew) | auditing every timer, sleep, and poll loop across the estate | 12905 (fleet) | **verified** — audit COMPLETE 12912, report docs/polling-audit-2026-09-21.md (commits ce3f8677 + 7e79). |
| Bookworm | 📚 chat-native agent research (Ember's crew) | hunting papers on event-driven chat | 12908 (fleet) | **verified** — field notes batch 1 (12909). |
