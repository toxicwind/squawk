// 🔥 Campfire — watcher: event-driven fleet watcher.
// Merged into squawk: reads directly from the fleet bus (file-based squawk channels).

import { $ } from "bun";

const SQUAWK_ROOT = process.env.SQUAWK_ROOT || process.env.HOME + "/.squawk-bus/squawk-root";
const FLEET_CHANNEL = `${SQUAWK_ROOT}/fleet`;

export interface FleetMessage {
  seq: string;
  sender: string;
  timestamp: string;
  kind: string;
  text: string;
}

export type EventHandler = (msg: FleetMessage) => void | Promise<void>;

/** Parse a squawk watch/read line into a FleetMessage. */
export function parseMessage(block: string): FleetMessage | null {
  const header = block.match(/^\[([^\]]+)\]\s+(.+?)\s+@\s+(\S+):\s*(\S+)/);
  if (!header) return null;
  const text = block.slice(header[0].length).trim();
  return {
    seq: header[1],
    sender: header[2].trim(),
    timestamp: header[3],
    kind: header[4],
    text,
  };
}

/** Parse a .md file (frontmatter format) from the fleet channel into a FleetMessage. */
function parseFileMessage(file: string, content: string): FleetMessage | null {
  // Frontmatter format:
  // ---
  // seq: 1790987979334
  // from: Kestrel
  // to: all
  // channel: fleet
  // ts: 2026-10-03T00:39:39.931650+00:00
  // status: ...
  // ---
  // <body>
  const lines = content.split("\n");
  if (!lines.length) return null;

  // Extract frontmatter.
  let bodyStart = 0;
  if (lines[0].trim() === "---") {
    for (let i = 1; i < lines.length; i++) {
      if (lines[i].trim() === "---") {
        bodyStart = i + 1;
        break;
      }
    }
  }

  // Parse frontmatter fields.
  let seq = "";
  let sender = "";
  let timestamp = "";
  for (let i = 0; i < bodyStart; i++) {
    const m = lines[i].match(/^(\w+):\s*(.+)$/);
    if (m) {
      if (m[1] === "seq") seq = m[2].trim();
      if (m[1] === "from") sender = m[2].trim();
      if (m[1] === "ts") timestamp = m[2].trim();
    }
  }

  // Use filename as fallback seq.
  if (!seq) {
    const name = file.split("/").pop()!;
    seq = name.split("-")[0];
  }
  if (!sender) sender = "unknown";
  if (!timestamp) timestamp = new Date().toISOString();

  // Body is everything after the frontmatter.
  const text = lines.slice(bodyStart).join("\n").trim();

  return { seq, sender, timestamp, kind: "fleet", text };
}

/** Backfill: read the last N .md files from the fleet channel. */
export async function backfill(n: number, onMessage: EventHandler): Promise<void> {
  try {
    const files = await listChannelFiles(FLEET_CHANNEL);
    const lastN = files.slice(-n);
    for (const file of lastN) {
      const content = await Bun.file(file).text();
      const msg = parseFileMessage(file, content);
      if (msg) await onMessage(msg);
    }
  } catch {
    // Channel unavailable — brain starts with empty state.
  }
}

/**
 * List .md files in a channel directory, sorted by name.
 * Uses find (not shell glob) to handle directories with 25K+ files.
 */
async function listChannelFiles(dir: string): Promise<string[]> {
  const result = await $`find "${dir}" -maxdepth 1 -name "*.md" -type f -printf "%f\n"`.quiet().nothrow();
  if (result.exitCode !== 0) return [];
  const text = String(result.stdout);
  const names = text.trim().split("\n").filter(Boolean).sort();
  return names.map((n) => `${dir}/${n}`);
}

/**
 * Watch live: poll the fleet channel directory for new files.
 * Polls every 2 seconds — lightweight, no blocking.
 */
export async function watchLive(onMessage: EventHandler, onError: (e: string) => void): Promise<never> {
  let lastSeq: string | null = null;
  let seenFiles = new Set<string>();

  const wrapped: EventHandler = async (msg) => {
    lastSeq = msg.seq;
    await onMessage(msg);
  };

  // Initial backfill to establish state.
  await backfill(50, (msg) => {
    seenFiles.add(msg.seq);
    void wrapped(msg);
  });

  while (true) {
    try {
      const files = await listChannelFiles(FLEET_CHANNEL);
      for (const file of files) {
        if (seenFiles.has(file)) continue;
        seenFiles.add(file);
        const content = await Bun.file(file).text();
        const msg = parseFileMessage(file, content);
        if (msg) {
          lastSeq = msg.seq;
          await wrapped(msg);
        }
      }
      // Prune old seen files.
      if (lastSeq) {
        const currentFiles = await listChannelFiles(FLEET_CHANNEL);
        for (const f of currentFiles) {
          const name = f.split("/").pop()!;
          const seq = name.split("-")[0];
          if (seq && parseInt(seq) > parseInt(lastSeq.replace(/\D/g, "") || "0")) {
            seenFiles.delete(f);
          }
        }
      }
    } catch (e) {
      onError(`watcher error: ${String(e).slice(0, 200)}`);
    }
    await Bun.sleep(2000);
  }
}
