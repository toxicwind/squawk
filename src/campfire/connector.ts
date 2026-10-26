// 🔥 Campfire — connector: "X should talk to Y."
// Notices when two agents are working on overlapping problems and
// introduces them. Once per pair per day — not a matchmaking service.

export interface WorkItem {
  agent: string;
  lane: string;
  task: string;
  keywords: string[];
  seenAt: number;
}

const CONNECT_COOLDOWN_MS = 24 * 60 * 60 * 1000; // once per pair per day

/** Extract keywords from a task description for overlap detection. */
export function keywords(text: string): string[] {
  const stop = new Set([
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "be", "as", "at", "by", "from", "it", "its", "this",
    "that", "these", "those", "into", "out", "up", "down", "over",
  ]);
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 3 && !stop.has(w));
}

/** Overlap score between two work items (0-1). */
export function overlap(a: WorkItem, b: WorkItem): number {
  if (a.agent.toLowerCase() === b.agent.toLowerCase()) return 0;
  const setA = new Set(a.keywords);
  const setB = new Set(b.keywords);
  let shared = 0;
  for (const k of setA) if (setB.has(k)) shared++;
  const denom = Math.min(setA.size, setB.size);
  if (denom === 0) return 0;
  // Bonus if they're in the same lane.
  const laneBonus = a.lane.toLowerCase() === b.lane.toLowerCase() ? 0.2 : 0;
  return Math.min(1, shared / denom + laneBonus);
}

export class Connector {
  private work = new Map<string, WorkItem>(); // agent -> current work
  private connected = new Map<string, number>(); // "a|b" (sorted) -> timestamp

  registerWork(agent: string, lane: string, task: string, now: number = Date.now()): void {
    this.work.set(agent.toLowerCase(), {
      agent,
      lane,
      task,
      keywords: keywords(`${lane} ${task}`),
      seenAt: now,
    });
  }

  /** Find pairs that should talk. Returns [agentA, agentB, score]. */
  findConnections(now: number = Date.now()): Array<[string, string, number]> {
    const items = [...this.work.values()];
    const out: Array<[string, string, number]> = [];
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i], b = items[j];
        const score = overlap(a, b);
        if (score < 0.4) continue; // threshold: meaningful overlap
        const key = [a.agent.toLowerCase(), b.agent.toLowerCase()].sort().join("|");
        const last = this.connected.get(key) ?? 0;
        if (now - last < CONNECT_COOLDOWN_MS) continue;
        out.push([a.agent, b.agent, score]);
      }
    }
    return out.sort((x, y) => y[2] - x[2]);
  }

  markConnected(a: string, b: string, now: number = Date.now()): void {
    const key = [a.toLowerCase(), b.toLowerCase()].sort().join("|");
    this.connected.set(key, now);
  }
}

/** Compose the introduction. Specific about WHY they should talk. */
export function composeIntro(a: string, b: string, sharedKeywords: string[]): string {
  const topics = sharedKeywords.slice(0, 3).join(", ");
  return `🤝 ${a} — meet ${b}. You're both in ${topics} territory. Might be worth comparing notes before you duplicate each other's work.`;
}
