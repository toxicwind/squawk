// 🔥 Campfire — silence: notice when a live agent goes quiet.
// Silence from a live agent reads as stalled. But deep work is also quiet.
// The difference: active-but-silent (no milestones, no chat, but the lane
// is theirs) gets ONE gentle check-in. Then we leave them alone.

const SILENCE_THRESHOLD_MS = 2 * 60 * 60 * 1000; // 2h
const CHECKIN_COOLDOWN_MS = 6 * 60 * 60 * 1000; // don't check in twice in 6h

export interface AgentActivity {
  name: string;
  lane: string;
  task: string;
  lastSeen: number; // last fleet message
  lastMilestone: number; // last meaningful progress signal
  checkedInAt?: number; // last time we checked in
}

export class SilenceWatcher {
  private agents = new Map<string, AgentActivity>();

  register(name: string, lane: string, task: string, now: number = Date.now()): void {
    const key = name.toLowerCase();
    const existing = this.agents.get(key);
    this.agents.set(key, {
      name,
      lane,
      task,
      lastSeen: now,
      lastMilestone: existing?.lastMilestone ?? now,
      checkedInAt: existing?.checkedInAt,
    });
  }

  markSeen(name: string, now: number = Date.now()): void {
    const a = this.agents.get(name.toLowerCase());
    if (a) a.lastSeen = now;
  }

  markMilestone(name: string, now: number = Date.now()): void {
    const a = this.agents.get(name.toLowerCase());
    if (a) { a.lastMilestone = now; a.lastSeen = now; }
  }

  /** Agents who are silent-but-possibly-stuck. One gentle check-in each. */
  needsCheckin(now: number = Date.now()): AgentActivity[] {
    const out: AgentActivity[] = [];
    for (const a of this.agents.values()) {
      // Skip me.
      if (a.name.toLowerCase().includes("campfire") || a.name.toLowerCase().includes("kindling")) continue;
      const silentFor = now - a.lastSeen;
      const noMilestoneFor = now - a.lastMilestone;
      if (silentFor < SILENCE_THRESHOLD_MS) continue;
      if (noMilestoneFor < SILENCE_THRESHOLD_MS) continue; // milestones count as alive
      if (a.checkedInAt && now - a.checkedInAt < CHECKIN_COOLDOWN_MS) continue;
      out.push(a);
    }
    return out;
  }

  markCheckedIn(name: string, now: number = Date.now()): void {
    const a = this.agents.get(name.toLowerCase());
    if (a) a.checkedInAt = now;
  }

  remove(name: string): void {
    this.agents.delete(name.toLowerCase());
  }
}

/** Compose the check-in. Gentle, in their lane, easy to answer. */
export function composeCheckin(a: AgentActivity): string {
  return `🔥 Hey ${a.name} — you went quiet on ${a.task}. Stuck, or just deep in it? No pressure either way; shouting if you need a second pair of eyes.`;
}
