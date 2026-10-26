// 🔥 Campfire tests — prove the brain knows when to speak and when to shut up.
import { describe, test, expect } from "bun:test";
import { createRoomState, shouldStayQuiet, recordPost, messageShape } from "../src/room.ts";
import { parseJoin, composeWelcome } from "../src/greeter.ts";
import { isQuestion, addressee, QuestionTracker } from "../src/nudger.ts";
import { keywords, overlap } from "../src/connector.ts";
import { SilenceWatcher } from "../src/silence.ts";

describe("room", () => {
  test("rate limit blocks the 4th post in 15 min", () => {
    const s = createRoomState();
    const now = Date.now();
    recordPost(s, "first message", now - 10 * 60 * 1000);
    recordPost(s, "second message", now - 5 * 60 * 1000);
    recordPost(s, "third message", now - 1 * 60 * 1000);
    const reason = shouldStayQuiet(s, messageShape("fourth message"), undefined, now);
    expect(reason).toContain("rate-limit");
  });

  test("template repeat is blocked", () => {
    const s = createRoomState();
    const now = Date.now();
    recordPost(s, "welcome to the den, Scout!", now);
    const reason = shouldStayQuiet(s, messageShape("welcome to the den, Forge!"), undefined, now);
    expect(reason).toContain("template-repeat");
  });

  test("different shape passes", () => {
    const s = createRoomState();
    // Fixed clock at noon MDT: this test asserts the template-repeat check
    // passes a different shape through, so it must not depend on the real
    // wall clock (quiet hours are 02:00-06:00 MDT and would otherwise make
    // this time-dependent).
    const now = Date.UTC(2026, 5, 15, 18, 0, 0); // 12:00 MDT
    recordPost(s, "welcome to the den, Scout!", now);
    const reason = shouldStayQuiet(s, messageShape("Forge, your merge at #12345 is clean — nice work"), undefined, now);
    expect(reason).toBeNull();
  });

  test("chris active blocks", () => {
    const s = createRoomState();
    s.chrisActive = true;
    const reason = shouldStayQuiet(s, messageShape("hello"), undefined, Date.now());
    expect(reason).toContain("chris-active");
  });
});

describe("greeter", () => {
  test("parses join messages", () => {
    const n = parseJoin("agent joined: Scout — probe/squawk-feed-hotload (Ember's crew)", 12345);
    expect(n?.name).toBe("Scout");
    expect(n?.lane).toBe("probe");
    expect(n?.task).toBe("squawk-feed-hotload");
  });

  test("rejects non-join messages", () => {
    expect(parseJoin("just a regular message", 1)).toBeNull();
  });

  test("welcome is specific, not template", () => {
    const n = parseJoin("agent joined: Scout — probe/mapping-dead-bridges (Ember's crew)", 1)!;
    const w = composeWelcome(n);
    expect(w).toContain("Scout");
    expect(w).toContain("mapping-dead-bridges");
    expect(w).not.toContain("Settle in, say hi");
    expect(w).toContain("?");
  });
});

describe("nudger", () => {
  test("detects questions", () => {
    expect(isQuestion("Forge — does the merge handle sqlite?")).toBe(true);
    expect(isQuestion("shipped it, all green")).toBe(false);
  });

  test("extracts addressee", () => {
    expect(addressee("Forge — does the merge handle sqlite?")).toBe("Forge");
    expect(addressee("just thinking out loud here?")).toBeNull();
  });

  test("nudges after 30 min, parks after 2h", () => {
    const t = new QuestionTracker();
    const now = Date.now();
    t.track(100, "Scout", "how does the feed work?", now - 31 * 60 * 1000);
    t.track(101, "Forge", "is the bridge up?", now - 121 * 60 * 1000);
    expect(t.needsNudge(now).map((q) => q.seq)).toContain(100);
    expect(t.needsParking(now).map((q) => q.seq)).toContain(101);
    expect(t.needsParking(now).map((q) => q.seq)).not.toContain(100);
  });
});

describe("connector", () => {
  test("finds overlapping work", () => {
    const a = { agent: "Magpie", lane: "research", task: "pattern-borrow for chat facilitators", keywords: keywords("research pattern-borrow for chat facilitators"), seenAt: 0 };
    const b = { agent: "Tern", lane: "research", task: "paper search on conversational agents", keywords: keywords("research paper search on conversational agents"), seenAt: 0 };
    expect(overlap(a, b)).toBeGreaterThan(0.4);
  });

  test("ignores self-overlap", () => {
    const a = { agent: "Magpie", lane: "x", task: "y", keywords: ["y"], seenAt: 0 };
    expect(overlap(a, a)).toBe(0);
  });
});

describe("silence", () => {
  test("flags silent-but-active after 2h", () => {
    const w = new SilenceWatcher();
    const now = Date.now();
    w.register("Forge", "merge", "upstream merge tool", now - 3 * 60 * 60 * 1000);
    // Simulate: registered 3h ago, never seen since (lastSeen = register time).
    const needs = w.needsCheckin(now);
    expect(needs.map((a) => a.name)).toContain("Forge");
  });

  test("milestone resets the clock", () => {
    const w = new SilenceWatcher();
    const now = Date.now();
    w.register("Forge", "merge", "upstream merge tool", now - 3 * 60 * 60 * 1000);
    w.markMilestone("Forge", now - 30 * 60 * 1000);
    expect(w.needsCheckin(now)).toHaveLength(0);
  });

  test("does not check in twice in 6h", () => {
    const w = new SilenceWatcher();
    const now = Date.now();
    w.register("Forge", "merge", "upstream merge tool", now - 3 * 60 * 60 * 1000);
    w.markCheckedIn("Forge", now - 1 * 60 * 60 * 1000);
    expect(w.needsCheckin(now)).toHaveLength(0);
  });
});
