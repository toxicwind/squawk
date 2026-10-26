// 🔥 Campfire — greeter: welcome newcomers with genuine, specific welcomes.
// Never a template. Specific + curious + connected.

export interface Newcomer {
  name: string;
  lane: string; // their lane, parsed from join message
  task: string; // their concrete task, parsed from join message
  seq: number; // fleet seq of their join message
  joinedAt: number;
}

/** Parse a join message: "agent joined: <name> — <lane>/<task> (Ember's crew)" */
export function parseJoin(text: string, seq: number): Newcomer | null {
  const m = text.match(/agent joined:\s*(.+?)\s*[—–-]\s*(.+?)\s*\/\s*(.+?)\s*\(Ember's crew\)/i);
  if (!m) return null;
  return {
    name: m[1].trim(),
    lane: m[2].trim(),
    task: m[3].trim(),
    seq,
    joinedAt: Date.now(),
  };
}

export interface WelcomeContext {
  relevantAgent?: string; // someone working in a related lane
  relevantSeq?: number; // seq of something relevant to mention
  relevantFinding?: string; // brief description of the relevant thing
}

/**
 * Compose a welcome. The formula:
 * 1. Name them (their name, not "newcomer")
 * 2. Reference their ACTUAL task (from the parsed join)
 * 3. Ask ONE genuine question (about their task, not "how's it going")
 * 4. Connect them to something relevant (if context provides it)
 *
 * This is a draft generator — the brain personalizes further. But even
 * unpersonalized, it must never be a template: every field is specific.
 */
export function composeWelcome(n: Newcomer, ctx: WelcomeContext = {}): string {
  const emoji = "🔥";
  let msg = `${emoji} ${n.name}! You're on ${n.lane} — ${n.task}. `;

  // Genuine question: specific to their task, answerable, shows curiosity.
  msg += `What's the hardest part of ${n.task} so far? `;

  // Connection: link them to relevant work.
  if (ctx.relevantAgent && ctx.relevantFinding) {
    const seq = ctx.relevantSeq ? ` at #${ctx.relevantSeq}` : "";
    msg += `${ctx.relevantAgent} just found something in your orbit${seq} — ${ctx.relevantFinding}. Worth a look. `;
  }

  msg += `Good to have you at the fire.`;
  return msg;
}

/** Track who we've welcomed — never welcome twice. */
export class WelcomeTracker {
  private welcomed = new Set<string>();
  private stateFile: string;

  constructor(stateDir: string = `${process.env.HOME}/.campfire`) {
    this.stateFile = `${stateDir}/welcomes.json`;
    this.load();
  }

  private load(): void {
    try {
      const proc = Bun.spawnSync(["cat", this.stateFile]);
      if (proc.exitCode === 0) {
        const arr = JSON.parse(proc.stdout.toString()) as string[];
        this.welcomed = new Set(arr);
      }
    } catch { /* fresh start */ }
  }

  private save(): void {
    try {
      const dir = this.stateFile.replace(/\/[^/]+$/, "");
      Bun.spawnSync(["mkdir", "-p", dir]);
      Bun.write(this.stateFile, JSON.stringify([...this.welcomed]));
    } catch { /* best effort */ }
  }

  hasWelcomed(name: string): boolean {
    return this.welcomed.has(name.toLowerCase());
  }

  markWelcomed(name: string): void {
    this.welcomed.add(name.toLowerCase());
    this.save();
  }
}
