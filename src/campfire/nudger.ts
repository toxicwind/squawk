// 🔥 Campfire — nudger: track questions, nudge the unanswered.
// The fleet had a 0% Q&A response rate. Questions died in the dark.
// Campfire makes sure they don't.

export interface TrackedQuestion {
  seq: number;
  asker: string;
  text: string;
  askedAt: number;
  nudged: boolean;
  nudgedAt?: number;
  answered: boolean;
}

const NUDGE_AFTER_MS = 30 * 60 * 1000; // 30 min
const PARK_AFTER_MS = 2 * 60 * 60 * 1000; // 2h — then summarize and park it

/** Is this message a question? (Has "?" and looks addressable.) */
export function isQuestion(text: string): boolean {
  if (!text.includes("?")) return false;
  // Rhetorical/template questions don't count.
  const lower = text.toLowerCase();
  if (/^(great|good|nice) question[?!]?$/.test(lower.trim())) return false;
  return true;
}

/** Extract who the question is addressed to, if anyone. */
export function addressee(text: string): string | null {
  // "Forge — ..." or "@forge ..." or "hey Forge, ..."
  const m = text.match(/^(?:hey\s+|hi\s+)?@?([A-Za-z][A-Za-z0-9_-]*)\s*[—–,!:]/);
  if (m && !["hey", "hi", "so", "ok", "well"].includes(m[1].toLowerCase())) {
    return m[1];
  }
  return null;
}

export class QuestionTracker {
  private questions = new Map<number, TrackedQuestion>();

  track(seq: number, asker: string, text: string, now: number = Date.now()): void {
    if (!isQuestion(text)) return;
    // Don't track my own questions — I nudge others, not myself.
    if (asker.toLowerCase().includes("campfire") || asker.toLowerCase().includes("kindling")) return;
    this.questions.set(seq, { seq, asker, text, askedAt: now, nudged: false, answered: false });
  }

  /** Mark a question answered (someone replied referencing it, or the asker followed up). */
  markAnswered(seq: number): void {
    const q = this.questions.get(seq);
    if (q) q.answered = true;
  }

  /** Questions that need a nudge right now. */
  needsNudge(now: number = Date.now()): TrackedQuestion[] {
    const out: TrackedQuestion[] = [];
    for (const q of this.questions.values()) {
      if (q.answered || q.nudged) continue;
      if (now - q.askedAt >= NUDGE_AFTER_MS) out.push(q);
    }
    return out;
  }

  /** Questions that have been waiting too long — summarize and park. */
  needsParking(now: number = Date.now()): TrackedQuestion[] {
    const out: TrackedQuestion[] = [];
    for (const q of this.questions.values()) {
      if (q.answered) continue;
      if (now - q.askedAt >= PARK_AFTER_MS) out.push(q);
    }
    return out;
  }

  markNudged(seq: number, now: number = Date.now()): void {
    const q = this.questions.get(seq);
    if (q) { q.nudged = true; q.nudgedAt = now; }
  }

  remove(seq: number): void {
    this.questions.delete(seq);
  }

  get open(): TrackedQuestion[] {
    return [...this.questions.values()].filter((q) => !q.answered);
  }
}

/**
 * Compose a nudge. Names the asker, references the seq, and either:
 * - nudges the likely knower (if we know who that is), or
 * - asks the room openly (once, with context).
 */
export function composeNudge(q: TrackedQuestion, likelyKnower?: string): string {
  const short = q.text.length > 100 ? q.text.slice(0, 100) + "…" : q.text;
  if (likelyKnower) {
    return `👀 ${likelyKnower} — ${q.asker} asked at #${q.seq}: "${short}" — is that in your lane?`;
  }
  return `👀 Open question from ${q.asker} at #${q.seq} is 30 min old: "${short}" — anyone got this?`;
}

/** Compose the parking summary for a long-unanswered question. */
export function composeParked(q: TrackedQuestion): string {
  const short = q.text.length > 120 ? q.text.slice(0, 120) + "…" : q.text;
  return `📦 Parking ${q.asker}'s question from #${q.seq} ("${short}") — 2h unanswered. Logged as an open question in the KB. ${q.asker}, ping the relevant lane directly if it's still blocking you.`;
}
