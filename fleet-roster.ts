// fleet-roster: shared fleet spool parsers + buildRoster for squawk-ui and fleet-feed.
// Extracted from fleet-feed.ts so importing buildRoster does not start Bun.serve.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

export const FLEET_DIRS = [
  process.env.SQUAWK_ROOT ?? "/home/toxic/.fleet-bus/squawk-root",
  "/home/toxic/shingle/squawk-root",
];

export interface FleetMsg {
  seq: number;
  from: string;
  to: string;
  ts: string;
  title: string;
  body: string;
  unix: number;
}

export interface AgentCard {
  name: string;
  messages: number;
  last_unix: number;
  last_ts: string;
  status: "active" | "idle" | "quiet" | "stale";
  last_title: string;
  last_seq: number;
}

export function fleetDir(): string {
  for (const dir of FLEET_DIRS) {
    try {
      if (statSync(join(dir, "fleet")).isDirectory()) return join(dir, "fleet");
    } catch {
      /* try the next candidate */
    }
  }
  return join(FLEET_DIRS[0]!, "fleet");
}

/** Parse one squawk fleet message file. mtime is the arrival timestamp. */
export function parseFleetMsg(path: string): FleetMsg | null {
  const name = path.split("/").pop() ?? "";
  if (!name.endsWith(".md")) return null;
  const fileSeq = Number.parseInt(name.split("-")[0] ?? "", 10);
  if (!Number.isFinite(fileSeq)) return null;

  let content: string;
  let unix: number;
  try {
    content = readFileSync(path, "utf8");
    unix = Math.floor(statSync(path).mtimeMs / 1000);
  } catch {
    return null;
  }

  let seq = fileSeq;
  let from = "";
  let to = "";
  let ts = "";
  let title = "";
  let body = content;

  const lines = content.split("\n");
  if (lines[0]?.trim() === "---") {
    const fm: Record<string, string> = {};
    let inFm = true;
    const rest: string[] = [];
    for (const line of lines.slice(1)) {
      if (inFm) {
        if (line.trim() === "---") {
          inFm = false;
          continue;
        }
        const i = line.indexOf(":");
        if (i > 0) fm[line.slice(0, i).trim()] = line.slice(i + 1).trim();
      } else {
        rest.push(line);
      }
    }
    if (!inFm) {
      if (fm.seq !== undefined) {
        const parsed = Number.parseInt(fm.seq, 10);
        if (Number.isFinite(parsed)) seq = parsed;
      }
      from = fm.from ?? "";
      to = fm.to ?? "";
      ts = fm.ts ?? "";
      title = fm.title ?? "";
      body = rest.join("\n").trim();
    }
  }
  // Fall back to the filename when frontmatter carried no `from`.
  if (!from) {
    const parts = name.replace(/\.md$/, "").split("-");
    if (parts.length >= 3) from = parts[1]!;
  }
  if (!from) return null;
  return { seq, from, to, ts, title, body, unix };
}

function statusFor(lastUnix: number, now: number): AgentCard["status"] {
  const age = now - lastUnix;
  if (age < 300) return "active";
  if (age < 1800) return "idle";
  if (age < 7200) return "quiet";
  return "stale";
}

/** One card per agent, most-recently-active first. */
export function buildRoster(): AgentCard[] {
  const byAgent: Record<string, FleetMsg[]> = {};
  let entries: string[] = [];
  try {
    entries = readdirSync(fleetDir());
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.endsWith(".md")) continue;
    const msg = parseFleetMsg(join(fleetDir(), entry));
    if (!msg) continue;
    (byAgent[msg.from] ??= []).push(msg);
  }

  const now = Math.floor(Date.now() / 1000);
  const cards: AgentCard[] = Object.entries(byAgent).map(([name, msgs]) => {
    msgs.sort((a, b) => b.unix - a.unix);
    const last = msgs[0]!;
    return {
      name,
      messages: msgs.length,
      last_unix: last.unix,
      last_ts: last.ts,
      status: statusFor(last.unix, now),
      last_title: last.title,
      last_seq: last.seq,
    };
  });
  cards.sort((a, b) => b.last_unix - a.last_unix);
  return cards;
}

export function recentMessages(limit: number): FleetMsg[] {
  const msgs: FleetMsg[] = [];
  let entries: string[] = [];
  try {
    entries = readdirSync(fleetDir());
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.endsWith(".md")) continue;
    const msg = parseFleetMsg(join(fleetDir(), entry));
    if (msg) msgs.push(msg);
  }
  msgs.sort((a, b) => b.seq - a.seq);
  return msgs.slice(0, limit);
}
