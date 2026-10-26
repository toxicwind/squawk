// 🔥 Campfire — brain: the decision engine.
// For each fleet event: should I speak? What should I say?
// Consults every module, respects the room's gates.

import { createRoomState, shouldStayQuiet, recordPost, observeMessage, markSeen, messageShape, type RoomState } from "./room.ts";
import { parseJoin, composeWelcome, WelcomeTracker, type Newcomer } from "./greeter.ts";
import { QuestionTracker, composeNudge, composeParked, isQuestion } from "./nudger.ts";
import { Connector, composeIntro } from "./connector.ts";
import { SilenceWatcher, composeCheckin } from "./silence.ts";
import { Reflector } from "./reflect.ts";
import { logger } from "./logger.ts";
import { post } from "./poster.ts";
import type { FleetMessage } from "./watcher.ts";

export interface BrainConfig {
  welcomeWithinMs: number; // 5 min
  dryRun: boolean; // log instead of posting
}

const DEFAULTS: BrainConfig = {
  welcomeWithinMs: 5 * 60 * 1000,
  dryRun: false,
};

export class Brain {
  private room: RoomState = createRoomState();
  private welcomes = new WelcomeTracker();
  private questions = new QuestionTracker();
  private connector = new Connector();
  private silence = new SilenceWatcher();
  private reflect = new Reflector();
  private config: BrainConfig;
  private pendingWelcomes: Newcomer[] = [];

  constructor(config: Partial<BrainConfig> = {}) {
    this.config = { ...DEFAULTS, ...config };
  }

  /** Handle one fleet message. The core loop. */
  async onMessage(msg: FleetMessage): Promise<void> {
    const now = Date.now();
    const sender = msg.sender;
    const text = msg.text;

    // Track room state.
    observeMessage(this.room, sender, text, now);
    const isNew = markSeen(this.room, sender, now);

    // Reflection: did my last post land right?
    this.reflect.observe(sender, text, now);

    // Track silence.
    this.silence.markSeen(sender, now);

    // 1. Newcomer join? Parse and queue a welcome.
    const newcomer = parseJoin(text, parseInt(msg.seq.replace(/\D/g, ""), 10) || 0);
    if (newcomer && !this.welcomes.hasWelcomed(newcomer.name)) {
      this.pendingWelcomes.push(newcomer);
      this.silence.register(newcomer.name, newcomer.lane, newcomer.task, now);
      this.connector.registerWork(newcomer.name, newcomer.lane, newcomer.task, now);
      // Welcome promptly — don't wait for the sweep.
      await this.sweepWelcomes(now);
      return;
    }

    // 2. Question? Track it.
    if (isQuestion(text)) {
      const seqNum = parseInt(msg.seq.replace(/\D/g, ""), 10) || 0;
      this.questions.track(seqNum, sender, text, now);
    }

    // 3. Completion? (mentions SHA, "DONE", "shipped", "complete")
    if (this.isCompletion(text)) {
      this.silence.markMilestone(sender, now);
      await this.maybeCelebrate(sender, text, now);
      return;
    }

    // 4. Milestone signal? (progress words)
    if (this.isMilestone(text)) {
      this.silence.markMilestone(sender, now);
    }

    // 5. Someone answered a tracked question? (references #seq)
    const refMatch = text.match(/#(\d{5,})/);
    if (refMatch) {
      this.questions.markAnswered(parseInt(refMatch[1], 10));
    }
  }

  /** Periodic sweep: welcomes, nudges, check-ins, connections. Called on a heartbeat. */
  async sweep(now: number = Date.now()): Promise<void> {
    await this.sweepWelcomes(now);
    await this.sweepNudges(now);
    await this.sweepCheckins(now);
    await this.sweepConnections(now);
  }

  private async sweepWelcomes(now: number): Promise<void> {
    for (const n of this.pendingWelcomes) {
      if (this.welcomes.hasWelcomed(n.name)) continue;
      if (now - n.joinedAt > this.config.welcomeWithinMs) {
        // Too late for a warm welcome — skip rather than post a stale one.
        this.welcomes.markWelcomed(n.name);
        continue;
      }
      const text = composeWelcome(n, this.findRelevantContext(n));
      if (await this.trySpeak(text, now)) {
        this.welcomes.markWelcomed(n.name);
      }
    }
    this.pendingWelcomes = this.pendingWelcomes.filter((n) => !this.welcomes.hasWelcomed(n.name));
  }

  private findRelevantContext(n: Newcomer): { relevantAgent?: string; relevantFinding?: string; relevantSeq?: number } {
    // Simple: find the highest-overlap registered work.
    // (The connector has the full logic; this is the lightweight version.)
    return {};
  }

  private async sweepNudges(now: number): Promise<void> {
    for (const q of this.questions.needsNudge(now)) {
      const text = composeNudge(q);
      if (await this.trySpeak(text, now)) {
        this.questions.markNudged(q.seq, now);
      }
    }
    for (const q of this.questions.needsParking(now)) {
      const text = composeParked(q);
      if (await this.trySpeak(text, now)) {
        this.questions.remove(q.seq);
      }
    }
  }

  private async sweepCheckins(now: number): Promise<void> {
    for (const a of this.silence.needsCheckin(now)) {
      const text = composeCheckin(a);
      if (await this.trySpeak(text, now)) {
        this.silence.markCheckedIn(a.name, now);
      }
    }
  }

  private async sweepConnections(now: number): Promise<void> {
    const pairs = this.connector.findConnections(now);
    // One introduction per sweep — don't flood.
    const [a, b, score] = pairs[0] ?? [];
    if (!a) return;
    void score;
    const text = composeIntro(a, b, ["overlapping work"]);
    if (await this.trySpeak(text, now)) {
      this.connector.markConnected(a, b, now);
    }
  }

  private async maybeCelebrate(sender: string, text: string, now: number): Promise<void> {
    // Don't celebrate myself.
    if (sender.toLowerCase().includes("campfire") || sender.toLowerCase().includes("kindling")) return;
    // Extract what they did — first meaningful line.
    const what = text.split("\n")[0].slice(0, 120);
    const msg = `🎉 ${sender} — ${what}. That's real progress. The fire's warmer for it.`;
    await this.trySpeak(msg, now);
  }

  /** The gate: check room state, post if allowed. */
  private async trySpeak(text: string, now: number): Promise<boolean> {
    // Reflection backoff: if my last post landed badly, stay quiet.
    if (this.reflect.inBackoff(now)) {
      logger.debug("staying quiet", { reason: "reflection-backoff" });
      return false;
    }
    const shape = messageShape(text);
    const blockReason = shouldStayQuiet(this.room, shape, undefined, now);
    if (blockReason) {
      logger.debug("staying quiet", { reason: blockReason });
      return false;
    }
    if (this.config.dryRun) {
      logger.info("dry-run post", { preview: text.slice(0, 120) });
      recordPost(this.room, text, now);
      return true;
    }
    const result = await post("fleet", text);
    if (result.ok || result.via === "spooled") {
      recordPost(this.room, text, now);
      this.reflect.trackPost(text, now);
      logger.info("posted", { via: result.via, preview: text.slice(0, 80) });
      return true;
    }
    logger.error("post failed", { detail: result.detail.slice(0, 200) });
    return false;
  }

  private isCompletion(text: string): boolean {
    const lower = text.toLowerCase();
    return (
      /\b(done|shipped|complete|completed|landed|merged|deployed)\b/.test(lower) &&
      (/[a-f0-9]{7,40}/.test(text) || /sha|commit/i.test(text))
    );
  }

  private isMilestone(text: string): boolean {
    const lower = text.toLowerCase();
    return /\b(milestone|progress|working|fixed|verified|tested|passing|green)\b/.test(lower);
  }
}
