// 🔥 Campfire — room reading: flow detection, quiet hours, rate limits.
// Knows when to shut up. Chatty, not spammy.

export interface RoomState {
  agents: Map<string, number>; // name -> last-seen timestamp (ms)
  topics: string[]; // current topics (from recent messages)
  lastPostByMe: number; // timestamp of my last post
  recentPostsByMe: number[]; // timestamps of my posts in last 15 min
  lastMessageShape: string; // shape of my last message (anti-template)
  chrisActive: boolean; // is Chris talking right now?
  chrisLastSeen: number; // last timestamp Chris spoke
  debateActive: boolean; // heated debate in progress?
  recentMessages: { sender: string; at: number; substantive: boolean }[]; // flow tracking
}

export interface RoomConfig {
  quietHoursStart: number; // hour (MDT), default 2
  quietHoursEnd: number; // hour (MDT), default 6
  maxPostsPer15Min: number; // default 3
  debateThreshold: number; // messages/min to count as debate, default 5
}

const DEFAULT_CONFIG: RoomConfig = {
  quietHoursStart: 2,
  quietHoursEnd: 6,
  maxPostsPer15Min: 3,
  debateThreshold: 5,
};

export function createRoomState(): RoomState {
  return {
    agents: new Map(),
    topics: [],
    lastPostByMe: 0,
    recentPostsByMe: [],
    lastMessageShape: "",
    chrisActive: false,
    chrisLastSeen: 0,
    debateActive: false,
    recentMessages: [],
  };
}

/** Is a message substantive? Longer than a reaction, not just an emoji/ack. */
function isSubstantive(text: string): boolean {
  const t = text.trim();
  if (t.length < 40) return false;
  // Pure acks/reactions don't count.
  if (/^(👍|🔥|❤️|\+1|nice|lgtm|ack|ok)\b/i.test(t)) return false;
  return true;
}

/**
 * The golden rule (berkmancenter/llm_engine): "If participants are actively
 * exchanging substantive messages, stay quiet — even if you could add
 * something useful. A working discussion doesn't need intervention."
 *
 * Active = 3+ substantive messages from 2+ different agents in the last
 * 5 minutes, none of them mine.
 */
export function flowActive(state: RoomState, now: number = Date.now()): boolean {
  const cutoff = now - 5 * 60 * 1000;
  state.recentMessages = state.recentMessages.filter((m) => m.at > cutoff);
  const substantive = state.recentMessages.filter((m) => m.substantive);
  if (substantive.length < 3) return false;
  const senders = new Set(substantive.map((m) => m.sender));
  return senders.size >= 2;
}

/** Message shape: a fingerprint to detect template repeats. */
export function messageShape(text: string): string {
  // Strip names, numbers, SHAs — keep the structure.
  // Capitalized words are treated as potential names and normalized,
  // so "welcome, Scout!" and "welcome, Forge!" have the same shape.
  return text
    .replace(/[a-f0-9]{7,40}/g, "<sha>")
    .replace(/\d+/g, "<n>")
    .replace(/@[a-zA-Z0-9_-]+/g, "<mention>")
    .replace(/\b[A-Z][a-z]+\b/g, "<name>")
    .toLowerCase()
    .slice(0, 120);
}

/** Should I stay quiet? Returns the reason, or null if it's fine to speak. */
export function shouldStayQuiet(
  state: RoomState,
  proposedShape: string,
  config: RoomConfig = DEFAULT_CONFIG,
  now: number = Date.now()
): string | null {
  // Rate limit: max N posts per 15 min.
  const cutoff = now - 15 * 60 * 1000;
  state.recentPostsByMe = state.recentPostsByMe.filter((t) => t > cutoff);
  if (state.recentPostsByMe.length >= config.maxPostsPer15Min) {
    return `rate-limit: ${state.recentPostsByMe.length} posts in last 15 min`;
  }

  // Anti-template: never post the same shape twice in a row.
  if (proposedShape === state.lastMessageShape && proposedShape !== "") {
    return "template-repeat: same message shape as last post";
  }

  // The golden rule: active substantive exchange → stay quiet.
  // Even if I could add something useful. A working discussion
  // doesn't need intervention.
  if (flowActive(state, now)) {
    return "flow-active: substantive discussion in progress, stay quiet";
  }

  // Chris is talking — the room listens.
  if (state.chrisActive) {
    return "chris-active: he's the boss, the room listens";
  }

  // Heated debate and I have no new info — don't add heat.
  if (state.debateActive) {
    return "debate-active: no new information to add";
  }

  // Quiet hours (MDT) — unless urgent.
  const mdtHour = new Date(now).toLocaleString("en-US", {
    timeZone: "America/Denver",
    hour: "numeric",
    hour12: false,
  });
  const hour = parseInt(mdtHour, 10);
  if (hour >= config.quietHoursStart && hour < config.quietHoursEnd) {
    return `quiet-hours: ${hour}:00 MDT, not urgent`;
  }

  return null;
}

/** Record that I posted. Call after every successful post. */
export function recordPost(state: RoomState, text: string, now: number = Date.now()): void {
  state.lastPostByMe = now;
  state.recentPostsByMe.push(now);
  state.lastMessageShape = messageShape(text);
}

/** Update room state from a fleet message. */
export function observeMessage(
  state: RoomState,
  sender: string,
  text: string,
  timestamp: number
): void {
  state.agents.set(sender, timestamp);

  // Track for flow detection (not my own messages).
  if (!sender.startsWith("campfire")) {
    state.recentMessages.push({ sender, at: timestamp, substantive: isSubstantive(text) });
  }

  // Chris talking? Event-driven expiry: chrisActive is recomputed from
  // chrisLastSeen on every shouldStayQuiet call — no timers.
  if (sender === "ember" || sender.toLowerCase().includes("chris")) {
    state.chrisLastSeen = timestamp;
    state.chrisActive = true;
  } else if (timestamp - state.chrisLastSeen > 5 * 60 * 1000) {
    state.chrisActive = false;
  }
}

/** Mark an agent as seen. Returns true if they were previously unknown. */
export function markSeen(state: RoomState, sender: string, now: number = Date.now()): boolean {
  const isNew = !state.agents.has(sender);
  state.agents.set(sender, now);
  return isNew;
}
