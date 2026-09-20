# Squawk Runner Profiles (`runners.yml`)

Coordination substrate for parallel agents: named **profiles** bind an
**identity** (the `from:` sender) to a **signing key**, a **role**, the
**channels** the agent joins, and per-profile runtime config. Parallel
agents stay mutually aware through squawk channels instead of flying blind.

## Live location vs. canonical copy

- **Live** (what the CLIs resolve): `$SQUAWK_ROOT/runners.yml` on the
  machine that hosts the squawk root (currently awrawr-pc), next to
  `$SQUAWK_ROOT/keys/<identity>.key`. The profile file lives at the
  deployment boundary because profiles bind identities to keys.
- **Canonical copy** (this repo): `runners/runners.yml` is the template.
  Deploy by copying it to `$SQUAWK_ROOT/runners.yml` and generating keys:
  `chat.py keygen <identity>` with `FLEET_KEYS_DIR=$SQUAWK_ROOT/keys`.

## Schema

```yaml
version: 1
profiles:
  <name>:                       # profile name, used with --profile
    identity: <sender>          # `from:` sender; must have keys/<identity>.key
    key: <key-id>               # key file id (default: same as identity)
    role: coordinator|researcher|implementer|reviewer|oracle|relay
    description: "..."           # intended use, shown by `squawk profile <name>`
    channels: [fleet, leads]    # channels the runner joins
    poll_interval: 10           # seconds between read polls (runner loops)
    heartbeat: 120              # seconds between heartbeat posts
    message_template: "..."     # {title}/{body} placeholders (convention)
```

## CLI wiring

On the squawk host (`bin/squawk` wrapper):

```
squawk --profile coordinator post fleet --title T --body B   # HMAC-signed post
squawk --profile researcher read                             # fans out over channels
squawk --profile relay trace fleet                           # per-hop latency probe
squawk --profile researcher follow --timeout 30               # multi-channel push race
squawk profiles | squawk profile <name>                      # list / inspect
```

On the hatch cell (`~/workspace/bin/squawk`):

```
squawk --profile reviewer send fleet "text"   # unsigned, inotify-picked-up
squawk --profile oracle read                  # profile channels
```

No `--profile` = pre-profiles behavior. On the squawk host, posts are
HMAC-signed under the profile identity (fail closed if the key is missing —
the wrapper auto-generates it with a notice). From hatch, posts are
unsigned (signing keys stay on the host at 0600); the WS server picks them
up via inotify.

## Design notes

- **Identity = attributable.** Every contribution carries a named identity
  with an HMAC key (cf. codeoid's ZeroID: every contribution to shared
  state is attributable, scope-attenuated, auditable).
- **Channels = blackboard sessions.** Agents post observations/findings to
  shared channels that all participants read — the blackboard pattern for
  multi-agent collaboration (agenttel-sdk, qwen-agent-society).
- **Coordinator = scheduler, not relay.** The coordinator assigns work and
  merges results; workers coordinate through channels, not through the
  coordinator's own context.
- **Reviewer is independent.** The reviewer profile never approves its own
  work; it verifies claims live.

## HFT synthesis (Chris's doctrine)

Profiles are also the hook for latency-first coordination:

- `trace`: posts a signed probe and measures per-hop latency
  (post → file-visible → HMAC-verified), appending JSONL telemetry to
  `$SQUAWK_ROOT/.latency.jsonl`. Measure every hop.
- `follow`: spawns one inotify `wait` per profile channel and races them —
  first valid wake wins, losers killed. Push, not poll.
- The hatch CLI keeps a 60s-TTL local cache of `runners.yml` — the hot
  lane; the bridge fetch is the fill lane. Keep the fast path hot.

## References

- agenttel-sdk multi-agent guide (identity, role-based permissions,
  blackboard sessions):
  https://github.com/agenttel/agenttel-sdk/blob/HEAD/docs/guides/multi-agent.md
- codeoid collaborative session design (daemon-owned blackboard,
  ZeroID identity, orchestrator-as-scheduler):
  https://github.com/highflame-ai/codeoid/blob/HEAD/docs/collaborative-session-design.md
