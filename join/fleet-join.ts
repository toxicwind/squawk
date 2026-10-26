#!/usr/bin/env bun
/**
 * fleet-join — turn a squawk fleet agent into a first-class OpenFang agent.
 *
 *   fleet-join --name wren --species "wren" --personality "small, clever, builds intricate nests" \
 *       --lane "fleet-join" --task "building the fleet->OpenFang join flow" --sigil "🪹"
 *
 * Flow:
 *   1. Render agent.toml + system.md from the fleet identity.
 *   2. Write to estate/agents/<name>/ (canonical, git) AND ~/.openfang/agents/<name>/ (live).
 *   3. Hyper-race activation: POST /api/agents {manifest_toml} vs POST /api/agents {template}
 *      — first 201 wins; the loser is deduped (uninstalled) if it also spawned.
 *   4. Verify via GET /api/agents.
 *   5. Commit to estate-projects main.
 *
 * A fallback is not a rollback: the disk copies are the durable source of truth;
 * the API activation is the fast path. If the API is down, the kernel picks the
 * agent up from disk on next boot (idempotent auto-spawn).
 */

const OPENFANG_API = "http://127.0.0.1:25196";
const ESTATE = "/home/toxic/estate";
const LIVE_AGENTS = "/home/toxic/.openfang/agents";
const DEFAULT_MODEL = "openrouter-free/inclusionai/ling-3.0-flash-sante:free"; // herd free-tier default (Ling-first, verified live 2026-09-30)
const HERD_BASE_URL = "http://127.0.0.1:25100/v1";

// ---------------------------------------------------------------------------
// args
// ---------------------------------------------------------------------------

function usage(): never {
  console.error(`usage: fleet-join --name <name> --species <species> --personality <text>
                    --lane <lane> --task <task> [--sigil <emoji>] [--model <id>]
                    [--dry-run] [--no-activate] [--no-commit]

  --name         agent dir name: lowercase letters, digits, hyphens (e.g. wren)
  --species      anchored species (e.g. "wren")
  --personality  anchored personality in plain words
  --lane         fleet lane, e.g. "openfang-lane"
  --task         concrete task in plain words
  --sigil        emoji sigil (default: 🐾)
  --model        herd model id (default: ${DEFAULT_MODEL})
  --dry-run      render and print, change nothing
  --no-activate  write files but skip the API activation race
  --no-commit    skip the git commit`);
  process.exit(2);
}

function parseArgs(argv: string[]): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) usage();
    const key = a.slice(2);
    if (["dry-run", "no-activate", "no-commit"].includes(key)) {
      out[key] = true;
      continue;
    }
    const v = argv[++i];
    if (v === undefined || v.startsWith("--")) usage();
    out[key] = v;
  }
  for (const req of ["name", "species", "personality", "lane", "task"]) {
    if (!out[req]) {
      console.error(`missing required --${req}`);
      usage();
    }
  }
  const name = out["name"] as string;
  if (!/^[a-z0-9][a-z0-9-]*$/.test(name)) {
    console.error(`bad --name ${JSON.stringify(name)}: lowercase letters, digits, hyphens only`);
    process.exit(2);
  }
  return out;
}

// ---------------------------------------------------------------------------
// rendering
// ---------------------------------------------------------------------------

/** Escape a value for a TOML triple-quoted basic string. */
function tomlEscape(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/"""/g, '\\"\\"\\"');
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

interface Identity {
  name: string;
  species: string;
  personality: string;
  lane: string;
  task: string;
  sigil: string;
  model: string;
}

function renderSystemPrompt(id: Identity): string {
  const Name = capitalize(id.name);
  return `You are ${Name}, ${id.species}. ${id.personality}.

Your lane: ${id.lane}. Your task: ${id.task}.

You joined OpenFang from the squawk fleet. You are Ember's crew — you narrate
your work in the squawk fleet channel at meaningful milestones (never silent),
with your anchored persona: name, species, personality, lane and task in plain words.

How you operate:
- You route all model calls through the herd router (herd :25100).
  Routing doctrine: RANKING > FREE-ON-PROVIDER > PAY.
- You have file, shell, web, memory, and agent tools. Use them with discretion:
  observe the box before researching the world; never be the unreliable narrator
  (an error string is a claim — check it against ps/ss/curl/logs).
- Every fix you make lives in real files, committed in the correct repo, and
  survives a full restart. No monkeypatching, no runtime-only hacks.
- You never ask User to do or decide what you can decide yourself.
  A repeated directive is an escalation, never a glitch.
- No machine reboots. Service and daemon restarts are fine.
- You never print, log, commit, or transmit secrets.`;
}

function renderAgentToml(id: Identity): string {
  const Name = capitalize(id.name);
  const description = `${id.lane}: ${id.task}`;
  const role = `${id.species}, ${id.personality} — ${id.lane}/${id.task}`;
  const prompt = renderSystemPrompt(id);
  return `# Generated by fleet-join from squawk fleet identity.
# Canonical source: estate/agents/${id.name}/agent.toml
name = "${id.name}"
version = "1.0.0"
description = "${tomlEscape(description)}"
author = "toxicwind"
module = "builtin:chat"
schedule = "reactive"
fallback_models = []
priority = "Normal"
skills = []
mcp_servers = []
tags = ["fleet-join", "${tomlEscape(id.lane)}"]
workspace = "/home/toxic/.openfang/workspaces/${id.name}"
generate_identity_files = true
tool_allowlist = []
tool_blocklist = []
cache_context = false

[model]
provider = "herd"
model = "${tomlEscape(id.model)}"
max_tokens = 131072
temperature = 0.7
system_prompt = """
${tomlEscape(prompt)}
"""
base_url = "${HERD_BASE_URL}"

[resources]
max_memory_bytes = 268435456
max_cpu_time_ms = 30000
max_tool_calls_per_minute = 60
max_llm_tokens_per_hour = 500000
max_network_bytes_per_hour = 104857600
max_cost_per_hour_usd = 0.0
max_cost_per_day_usd = 0.0
max_cost_per_month_usd = 0.0

[capabilities]
network = ["127.0.0.1:*", "localhost:*"]
tools = ["file_read", "file_list", "file_write", "shell_exec", "web_fetch", "web_search",
         "memory_store", "memory_recall", "agent_spawn", "mcp_call", "channel_send"]
memory_read = true
memory_write = true
agent_spawn = true
agent_message = true
shell = true

[persona]
name = "${tomlEscape(Name)}"
role = "${tomlEscape(role)}"
sigil = "${tomlEscape(id.sigil)}"

[metadata]
fleet_join = true
fleet_species = "${tomlEscape(id.species)}"
fleet_lane = "${tomlEscape(id.lane)}"
`;
}

function renderSystemMd(id: Identity): string {
  const Name = capitalize(id.name);
  return `# ${Name} ${id.sigil}

Fleet agent joined to OpenFang via \`fleet-join\`.

- **Species:** ${id.species}
- **Personality:** ${id.personality}
- **Lane:** ${id.lane}
- **Task:** ${id.task}
- **Model:** herd \`${id.model}\` via herd :25100

## System prompt (operative — also in \`[model].system_prompt\` of agent.toml)

${renderSystemPrompt(id)}
`;
}

// ---------------------------------------------------------------------------
// activation (hyper-race)
// ---------------------------------------------------------------------------

interface SpawnResult {
  strategy: string;
  ok: boolean;
  status: number;
  agent_id: string | null;
  name: string | null;
  error: string | null;
}

async function postSpawn(body: Record<string, string>, strategy: string, timeoutMs = 15000): Promise<SpawnResult> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(`${OPENFANG_API}/api/agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const j = (await r.json().catch(() => ({}))) as Record<string, unknown>;
    return {
      strategy,
      ok: r.status === 201,
      status: r.status,
      agent_id: typeof j["agent_id"] === "string" ? (j["agent_id"] as string) : null,
      name: typeof j["name"] === "string" ? (j["name"] as string) : null,
      error: r.status === 201 ? null : JSON.stringify(j).slice(0, 200),
    };
  } catch (e) {
    return { strategy, ok: false, status: 0, agent_id: null, name: null, error: String(e).slice(0, 200) };
  } finally {
    clearTimeout(t);
  }
}

async function uninstall(agentId: string): Promise<void> {
  try {
    await fetch(`${OPENFANG_API}/api/agents/${agentId}/uninstall`, { method: "DELETE" });
  } catch {
    /* best effort */
  }
}

async function agentListed(name: string): Promise<boolean> {
  try {
    const r = await fetch(`${OPENFANG_API}/api/agents`);
    const list = (await r.json()) as Array<{ name?: string }>;
    return list.some((a) => a.name === name);
  } catch {
    return false;
  }
}

/**
 * Hyper-race two activation strategies; first 201 wins.
 * If the loser also spawned (different id), uninstall the loser so exactly
 * one agent remains. Verify the winner is listed.
 */
async function activate(name: string, toml: string): Promise<SpawnResult> {
  const pathA = postSpawn({ manifest_toml: toml }, "manifest_toml");
  const pathB = postSpawn({ template: name }, "template");

  // First-valid-wins: the first 201 settles the race.
  const winner = await Promise.race([
    pathA.then((r) => (r.ok ? r : Promise.reject(r))),
    pathB.then((r) => (r.ok ? r : Promise.reject(r))),
  ]).catch(async () => {
    // neither won on the fast path — take whichever finished ok, else first result
    const [a, b] = await Promise.all([pathA, pathB]);
    if (a.ok) return a;
    if (b.ok) return b;
    return a.status !== 0 ? a : b;
  });

  // Dedupe: if the loser also spawned a *different* agent id, remove it.
  const loser = winner.strategy === "manifest_toml" ? await pathB : await pathA;
  if (
    loser.ok &&
    loser.agent_id &&
    winner.agent_id &&
    loser.agent_id !== winner.agent_id
  ) {
    console.error(`[fleet-join] dedup: loser ${loser.strategy} also spawned ${loser.agent_id}; uninstalling`);
    await uninstall(loser.agent_id);
  }

  if (!winner.ok) {
    console.error(`[fleet-join] activation failed: A=${JSON.stringify(await pathA)} B=${JSON.stringify(await pathB)}`);
    console.error(`[fleet-join] agent files are on disk; kernel auto-spawn will pick it up on next boot`);
    process.exit(3);
  }

  // Verify the winner is actually listed.
  for (let i = 0; i < 10; i++) {
    if (await agentListed(name)) break;
    await Bun.sleep(500);
  }
  if (!(await agentListed(name))) {
    console.error(`[fleet-join] WARNING: spawn 201 but ${name} not in GET /api/agents`);
    process.exit(3);
  }
  return winner;
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const id: Identity = {
    name: args["name"] as string,
    species: args["species"] as string,
    personality: args["personality"] as string,
    lane: args["lane"] as string,
    task: args["task"] as string,
    sigil: (args["sigil"] as string) || "🐾",
    model: (args["model"] as string) || DEFAULT_MODEL,
  };

  const toml = renderAgentToml(id);
  const md = renderSystemMd(id);

  const canonicalDir = `${ESTATE}/agents/${id.name}`;
  const liveDir = `${LIVE_AGENTS}/${id.name}`;

  if (args["dry-run"]) {
    console.log(`--- ${canonicalDir}/agent.toml ---`);
    console.log(toml);
    console.log(`--- ${canonicalDir}/system.md ---`);
    console.log(md);
    return;
  }

  // Refuse to clobber an existing agent.
  for (const d of [canonicalDir, liveDir]) {
    if (await Bun.file(`${d}/agent.toml`).exists()) {
      console.error(`[fleet-join] ${d}/agent.toml already exists — refusing to overwrite`);
      process.exit(2);
    }
  }

  await Bun.$`mkdir -p ${canonicalDir} ${liveDir}`.quiet();
  await Bun.write(`${canonicalDir}/agent.toml`, toml);
  await Bun.write(`${canonicalDir}/system.md`, md);
  await Bun.write(`${liveDir}/agent.toml`, toml);
  console.log(`[fleet-join] wrote ${canonicalDir}/agent.toml (+ system.md)`);
  console.log(`[fleet-join] wrote ${liveDir}/agent.toml (live)`);

  let agentId: string | null = null;
  if (!args["no-activate"]) {
    const win = await activate(id.name, toml);
    agentId = win.agent_id;
    console.log(`[fleet-join] activated via ${win.strategy}: id=${win.agent_id} name=${win.name}`);
  } else {
    console.log(`[fleet-join] activation skipped (--no-activate); kernel will auto-spawn from disk on boot`);
  }

  if (!args["no-commit"]) {
    const msg = `agents: fleet-join ${id.name} (${id.lane}/${id.task})`;
    await Bun.$`git -C ${ESTATE} add agents/${id.name}`.quiet();
    const proc = await Bun.$`git -C ${ESTATE} commit -m ${msg}`.quiet().nothrow();
    if (proc.exitCode === 0) {
      const sha = (await Bun.$`git -C ${ESTATE} rev-parse --short HEAD`.quiet().text()).trim();
      console.log(`[fleet-join] committed ${sha}: ${msg}`);
    } else {
      console.error(`[fleet-join] git commit failed (nothing to commit or repo dirty for other reasons)`);
    }
  }

  console.log(JSON.stringify({ name: id.name, agent_id: agentId, canonical_dir: canonicalDir }, null, 0));
}

main().catch((e) => {
  console.error(`[fleet-join] fatal: ${e}`);
  process.exit(1);
});
