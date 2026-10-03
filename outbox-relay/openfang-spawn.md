# squawk-relay agent instantiation — READY TO EXECUTE (blocked on daemon LLM path)

The relay pipeline (sink → outbox → forwarder) runs WITHOUT the agent.
This step adds the rig-side relay AGENT (owns control.json, watches the
pipeline, handles pause/resume/filter requests). It is fully prepared;
execute once the daemon LLM path is unblocked.

## Blocker

`openfang agent spawn` needs a working model for the agent. Per the
openfang track: the daemon NVIDIA_API_KEY is stale (401), anthropic
invalid, groq/cerebras 403, deepseek 402, and the `fast` local model
(1.2B) cannot tool-call — this agent needs `shell_exec`. Unblock = the
NVIDIA key refresh (worker 1) or a tool-capable local model.

## Exact command (run on awrawr-pc as toxic)

```bash
openfang agent spawn /home/toxic/.fleet-bus/squawk-relay/agent.toml
```

The manifest is checked in at `/home/toxic/.fleet-bus/squawk-relay/agent.toml`
(v1.0.0, provider=nvidia, model=openai/gpt-oss-20b, full system prompt with
the work loop and standing rules). No flags needed; the manifest is
self-contained. `relay-agent.toml` (v0.1.0) is the superseded draft — use
`agent.toml`.

## Preflight (before spawning)

1. `openfang agent list` — confirm no `squawk-relay` agent already exists
   (idempotent tasks only; never spawn a duplicate).
2. Daemon LLM path healthy: the configured provider/model for the manifest
   resolves (NVIDIA key installed by worker 1).
3. Pipeline daemons alive: `pitchfork status` shows
   `sovereign/squawk-relay-sink` and `sovereign/squawk-relay-forward`
   running (lane: main d23c8a01).

## Post-spawn verify

1. `openfang agent list` shows `squawk-relay` running.
2. Ask it (via openfang agent message, per that CLI's surface) to report
   relay status; it should read state.json / forward-state.json and the
   feed `/squawk-feed/seq` endpoint.
3. Have it exercise control.json: set `paused=true`, post a test message
   to #fleet, confirm the outbox does NOT grow; set `paused=false`,
   confirm catch-up. Then record the result in todos.md under
   `[squawk-relay]`.

## Rollback

`openfang agent stop squawk-relay` (confirm exact subcommand via
`openfang agent --help` at execution time). The pipeline keeps running
without the agent; only the control-plane ownership lapses.
