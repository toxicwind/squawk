import { readFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

/**
 * @fleet/chat-native — chat-native agent shim over the squawk feed.
 *
 * An agent subclasses ChatAgent (or uses one directly), supplies lane keywords,
 * and lets the transport wake it: the squawk feed's /subscribe endpoint parks
 * server-side (inotify-driven) and returns the moment a new message lands.
 * This client re-issues the long-poll recursively — event-driven, zero timers.
 *
 * Usage:
 *
 *   import { ChatAgent } from "@fleet/chat-native";
 *
 *   class MyAgent extends ChatAgent {
 *     override name = "myagent";
 *     override laneKeywords = ["paper", "arxiv"];
 *     override laneDescription = "researches academic papers and citation ranking";
 *     override async onTask(task) { console.log("doing", task.id, task.what); }
 *   }
 *
 *   const agent = new MyAgent({ token: process.env.SQUAWK_FEED_TOKEN! });
 *   agent.start();
 *   const task = await agent.tasks.take(); // blocks until chat delivers work
 */

export interface ChatMessage {
  seq: number;
  sender?: string;
  from?: string;
  title?: string;
  body?: string;
  text?: string;
  [k: string]: unknown;
}

export interface ChatTask {
  id: string;
  what: string;
  why?: string;
  seq: number;
  from_msg?: ChatMessage;
}

export type FetchFn = (
  input: string | URL,
  init?: RequestInit
) => Promise<Response>;

export interface AgentOptions {
  /** squawk feed base, e.g. http://127.0.0.1:25135 */
  feedBase?: string;
  /** bearer token; or rely on SQUAWK_FEED_TOKEN env */
  token?: string;
  channels?: string[];
  /** where per-channel cursors persist, e.g. /var/lib/chat-native */
  cursorDir?: string;
  /** injectable fetch for tests */
  fetchFn?: FetchFn;
  /** hook for the expensive tier-2 classifier */
  classifyExpensive?: (msg: ChatMessage) => Promise<boolean> | boolean;
  /** how many transport failures before the loop dies (supervisor restarts) */
  maxTransportFailures?: number;
  /** ms for the parked long-poll (a deadline, not a poll) */
  holdMs?: number;
}

/** Async MPSC queue: take() parks on a promise until put() resolves it.
 *  No timers, no polling — the event loop stays idle until work arrives. */
export class AsyncQueue<T> {
  private items: T[] = [];
  private waiters: Array<(v: T) => void> = [];

  put(item: T): void {
    const w = this.waiters.shift();
    if (w) w(item);
    else this.items.push(item);
  }

  take(): Promise<T> {
    const item = this.items.shift();
    if (item !== undefined) return Promise.resolve(item);
    return new Promise<T>((resolve) => this.waiters.push(resolve));
  }

  get size(): number {
    return this.items.length;
  }
}

const MENTION_RE = /(?:^|\s)@([a-zA-Z0-9_-]+)\b/;
const TASK_RE =
  /^TASK\s+([A-Za-z0-9_.\-]{1,64})\s*:\s*(.+?)(?:\s*\/\/\s*(.+))?\s*$/im;
const STOPWORDS = new Set(
  "the a an and or of to in on for with is are was were be as at by from that this it its we you they he she i me my our your their them us".split(
    " "
  )
);

function tokens(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^a-z0-9_]+/)
      .filter((t) => t && !STOPWORDS.has(t))
  );
}

export class ChatAgent {
  /** unique agent handle — set per agent */
  name = "unnamed";
  /** words that make a message lane-relevant */
  laneKeywords: string[] = [];
  /** plain-words lane description, tokenized for cheap tier-1 matching */
  laneDescription = "";
  /** public work queue — take() blocks until chat delivers a task */
  readonly tasks = new AsyncQueue<ChatTask>();

  protected feedBase: string;
  protected token: string;
  protected channels: string[];
  protected cursorDir?: string;
  protected fetchFn: FetchFn;
  protected classifyExpensive?: (msg: ChatMessage) => Promise<boolean> | boolean;
  protected maxTransportFailures: number;
  protected holdMs: number;
  private cursors = new Map<string, number>();
  private stopped = false;

  constructor(opts: AgentOptions = {}) {
    this.feedBase = opts.feedBase ?? "http://127.0.0.1:25135";
    this.token =
      opts.token ?? process.env.SQUAWK_FEED_TOKEN ?? "";
    this.channels = opts.channels ?? ["fleet"];
    this.cursorDir = opts.cursorDir;
    this.fetchFn = opts.fetchFn ?? fetch;
    this.classifyExpensive = opts.classifyExpensive;
    this.maxTransportFailures = opts.maxTransportFailures ?? 5;
    this.holdMs = opts.holdMs ?? 70_000;
  }

  /** Last fatal transport error, if a channel loop died. */
  transportError: unknown = null;

  /** Start all channel subscribe loops (fire-and-forget). */
  start(): void {
    for (const ch of this.channels) {
      void this.channelLoop(ch).catch((err) => {
        this.transportError = err;
        console.error(`[${this.name}] channel ${ch} transport dead:`, err);
        this.onTransportDead(err);
      });
    }
  }

  /** Override: react to a dead transport. Default crashes the process so
   *  the supervisor restarts the agent — fail fast, never retry-spin. */
  onTransportDead(_err: unknown): void {
    process.exit(1);
  }

  /** Stop all channel subscribe loops. In-flight parked requests finish
   *  their current hold (configurable via holdMs) then the loops exit. */
  stop(): void {
    this.stopped = true;
  }

  /** Override: do the work. Default just logs. */
  async onTask(_task: ChatTask): Promise<void> {
    console.log(`[${this.name}] task queued (override onTask to act)`);
  }

  /** Send a message to chat. */
  async say(
    text: string,
    title = "",
    channel?: string
  ): Promise<Response> {
    const res = await this.fetchFn(`${this.feedBase}/squawk-feed/send`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.token}`,
      },
      body: JSON.stringify({
        channel: channel ?? this.channels[0],
        from: this.name,
        title,
        text,
      }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok)
      throw new Error(`send failed: ${res.status}`);
    return res;
  }

  /** Bounded immediate snapshot — the feed's ?tail=, no blocking. */
  async readChat(tail = 20, channel?: string): Promise<ChatMessage[]> {
    const url =
      `${this.feedBase}/squawk-feed/wait?tail=${tail}` +
      `&channel=${encodeURIComponent(channel ?? this.channels[0])}`;
    const res = await this.fetchFn(url, {
      headers: { Authorization: `Bearer ${this.token}` },
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok)
      throw new Error(`read failed: ${res.status}`);
    return ((await res.json()) as { messages?: ChatMessage[] }).messages ?? [];
  }

  /** One channel's recursive long-poll. Re-issues only when a response
   *  arrives — the wake-up is the server's inotify, never a timer. */
  private async channelLoop(channel: string): Promise<void> {
    let failures = 0;
    while (!this.stopped) {
      try {
        const since = this.cursor(channel);
        const url =
          `${this.feedBase}/squawk-feed/subscribe?since=${since}` +
          `&channel=${encodeURIComponent(channel)}`;
        const res = await this.fetchFn(url, {
          headers: { Authorization: `Bearer ${this.token}` },
          signal: AbortSignal.timeout(this.holdMs),
        });
        if (!res.ok)
          throw new Error(`subscribe failed: ${res.status}`);
        const payload = (await res.json()) as { messages?: ChatMessage[] };
        failures = 0;
        for (const msg of payload.messages ?? []) {
          const seq = msg.seq ?? 0;
          if (seq <= since) continue; // redelivery guard
          this.advance(channel, seq);
          this.dispatch(msg, channel);
        }
      } catch (err) {
        failures += 1;
        if (failures >= this.maxTransportFailures) {
          // Fail fast — never retry-spin. Supervisor restarts.
          throw new Error(
            `transport dead after ${failures} failures: ${
              err instanceof Error ? err.message : err
            }`
          );
        }
        // else: immediately re-issue once; no sleep, no backoff timers
      }
    }
  }

  private dispatch(msg: ChatMessage, _channel: string): void {
    const tier = this.classify(msg);
    if (tier === 0) return;
    const task = this.parseTask(msg);
    if (task) {
      this.tasks.put(task);
      void this.onTask(task);
      return;
    }
    if (tier === 1) {
      this.tasks.put({
        id: `chat-${msg.seq}`,
        what: this.textOf(msg).slice(0, 200),
        why: "mentioned or lane-relevant message",
        seq: msg.seq,
        from_msg: msg,
      });
    }
    // tier 2 (expensive classifier) only queues explicit tasks.
  }

  /** Attention tiers:
   *  0 = ignore (self, unrelated noise)
   *  1 = cheap relevance (mention, bare-name address, lane keyword token overlap)
   *  2 = optional expensive hook (e.g. LLM classifier) — override via option */
  classify(msg: ChatMessage): 0 | 1 | 2 {
    const text = this.textOf(msg);
    const sender = String(msg.sender ?? msg.from ?? "");
    if (sender === this.name) return 0; // never react to self

    const m = text.match(MENTION_RE);
    if (m && m[1].toLowerCase() === this.name.toLowerCase()) return 1;
    if (TASK_RE.test(text)) return 1;

    const lane = new Set([
      ...tokens(this.laneDescription),
      ...this.laneKeywords.map((k) => k.toLowerCase()),
    ]);
    const overlap = [...tokens(text)].filter((t) => lane.has(t)).length;
    if (overlap > 0) return 1;

    if (this.classifyExpensive) {
      // resolved asynchronously by dispatch caller — report 2
      return 2;
    }
    return 0;
  }

  /** Extract a TASK directive. Leading @mention is stripped first. */
  parseTask(msg: ChatMessage): ChatTask | null {
    const text = this.textOf(msg).replace(/^@[A-Za-z0-9_-]+\s+/, "");
    const m = text.match(TASK_RE);
    if (!m) return null;
    return {
      id: m[1],
      what: m[2].trim(),
      why: m[3]?.trim(),
      seq: msg.seq,
      from_msg: msg,
    };
  }

  private textOf(msg: ChatMessage): string {
    return String(msg.body ?? msg.text ?? msg.title ?? "");
  }

  private cursor(channel: string): number {
    if (!this.cursors.has(channel)) {
      this.cursors.set(channel, this.loadCursor(channel));
    }
    return this.cursors.get(channel)!;
  }

  private advance(channel: string, seq: number): void {
    if (seq > this.cursor(channel)) {
      this.cursors.set(channel, seq);
      this.saveCursor(channel, seq);
    }
  }

  private cursorPath(channel: string): string {
    return `${this.cursorDir}/${this.name}.${channel}.cursor`;
  }

  private loadCursor(channel: string): number {
    if (!this.cursorDir) return 0;
    try {
      const raw = readFileSync(this.cursorPath(channel), "utf8").trim();
      const n = parseInt(raw, 10);
      return Number.isFinite(n) ? n : 0;
    } catch {
      return 0;
    }
  }

  private saveCursor(channel: string, seq: number): void {
    if (!this.cursorDir) return;
    try {
      mkdirSync(dirname(this.cursorPath(channel)), { recursive: true });
      Bun.write(this.cursorPath(channel), String(seq)).catch(() => {});
    } catch {
      // cursor persistence is best-effort; the in-memory cursor still works
    }
  }
}
