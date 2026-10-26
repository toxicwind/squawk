// 🔥 Campfire — reflect: did my last post land right?
// HUMA (2511.17315): split decide / speak / reflect into three roles.
// After posting, watch the next few messages:
//   - Someone replies, reacts, or builds on it → good, keep the calibration.
//   - Thread dies, or someone pushes back → back off temporarily.
//
// This is the learning loop. Not ML — just honest bookkeeping that
// tunes the room's gates based on observed outcomes.

export interface PostOutcome {
  text: string;
  postedAt: number;
  replies: number; // messages referencing or following within 5 min
  positive: boolean; // someone reacted well (thanks, +1 with substance, answered)
  negative: boolean; // pushback ("shut up", "not now", thread died after)
  resolved: boolean;
}

const OUTCOME_WINDOW_MS = 5 * 60 * 1000;

import { logger } from "./logger.ts";

export class Reflector {
  private pending: PostOutcome[] = [];
  private backoffUntil: number = 0;
  private backoffFactor: number = 1;

  /** Call after every post. */
  trackPost(text: string, now: number = Date.now()): void {
    this.pending.push({ text, postedAt: now, replies: 0, positive: false, negative: false, resolved: false });
  }

  /** Call for every fleet message after my posts. */
  observe(sender: string, text: string, now: number = Date.now()): void {
    const lower = text.toLowerCase();
    for (const p of this.pending) {
      if (p.resolved) continue;
      if (now - p.postedAt > OUTCOME_WINDOW_MS) {
        this.resolve(p, now);
        continue;
      }
      p.replies++;

      // Positive signals: thanks, answers, building on it.
      if (/\b(thanks|thank you|good (call|point)|agreed|will do|on it)\b/.test(lower)) {
        p.positive = true;
      }
      // Negative signals: pushback, "not now", dismissal.
      if (/\b(shut up|not now|stop|spam|quiet|unnecessary)\b/.test(lower)) {
        p.negative = true;
      }
    }
    // Prune resolved.
    this.pending = this.pending.filter((p) => !p.resolved);
  }

  private resolve(p: PostOutcome, now: number): void {
    p.resolved = true;
    if (p.negative) {
      // Back off: double the quiet period, up to 1h.
      this.backoffFactor = Math.min(8, this.backoffFactor * 2);
      this.backoffUntil = now + 15 * 60 * 1000 * this.backoffFactor;
      logger.warn("negative outcome, backing off", { minutes: 15 * this.backoffFactor });
    } else if (p.positive || p.replies > 0) {
      // Landed well — decay backoff toward normal.
      this.backoffFactor = Math.max(1, this.backoffFactor / 2);
    }
    // Silence (no replies, not negative): neutral. The post may have been
    // fine but unneeded. Don't punish, don't reward.
  }

  /** Am I in backoff? If so, stay quiet regardless of the brain's decision. */
  inBackoff(now: number = Date.now()): boolean {
    return now < this.backoffUntil;
  }

  /** Stats for the room. */
  get stats(): { pending: number; backoffFactor: number; inBackoff: boolean } {
    return {
      pending: this.pending.length,
      backoffFactor: this.backoffFactor,
      inBackoff: this.inBackoff(),
    };
  }
}
