import { test, expect } from "bun:test";
import { mkdtempSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { ChatAgent, AsyncQueue, type ChatMessage, type FetchFn } from "./index";

class TestAgent extends ChatAgent {
  override name = "bookworm";
  override laneKeywords = ["paper", "arxiv"];
  override laneDescription =
    "researches academic papers and citation ranking";
}

const msg = (body: string, sender = "someone", seq = 1): ChatMessage => ({
  seq,
  sender,
  body,
});

test("tier 0: self message ignored", () => {
  expect(new TestAgent().classify(msg("@bookworm hi", "bookworm"))).toBe(0);
});

test("tier 1: direct mention", () => {
  expect(new TestAgent().classify(msg("@bookworm check this"))).toBe(1);
});

test("tier 1: bare-name address", () => {
  expect(
    new TestAgent().classify(msg("bookworm, read the new arxiv drop"))
  ).toBe(1);
});

test("tier 1: explicit TASK directive", () => {
  expect(
    new TestAgent().classify(msg("TASK paper-12: rank candidates // by novelty"))
  ).toBe(1);
});

test("tier 1: mention plus task", () => {
  expect(
    new TestAgent().classify(msg("@bookworm TASK paper-9: summarize // why"))
  ).toBe(1);
});

test("tier 1: lane keyword overlap", () => {
  expect(new TestAgent().classify(msg("new arxiv paper on citations"))).toBe(1);
});

test("tier 0: unrelated noise", () => {
  expect(
    new TestAgent().classify(msg("dinner tonight? pizza or tacos"))
  ).toBe(0);
});

test("parseTask extracts id/what/why", () => {
  const t = new TestAgent().parseTask(
    msg("TASK paper-12: rank candidates // by novelty")
  );
  expect(t).not.toBeNull();
  expect(t!.id).toBe("paper-12");
  expect(t!.what).toBe("rank candidates");
  expect(t!.why).toBe("by novelty");
});

test("parseTask strips leading mention", () => {
  const t = new TestAgent().parseTask(
    msg("@bookworm TASK paper-9: summarize // because")
  );
  expect(t).not.toBeNull();
  expect(t!.id).toBe("paper-9");
  expect(t!.what).toBe("summarize");
});

test("AsyncQueue.take blocks until put (no timers)", async () => {
  const q = new AsyncQueue<number>();
  let resolved: number | null = null;
  const p = q.take().then((v) => (resolved = v));
  await new Promise((r) => setImmediate(r)); // let take() park
  expect(resolved).toBeNull();
  q.put(42);
  await p;
  expect(resolved).toBe(42);
});

test("cursor persists to disk and is read on restart", async () => {
  const dir = mkdtempSync(join(tmpdir(), "chat-native-"));
  const fakeFetch: FetchFn = async () =>
    new Response(
      JSON.stringify({ messages: [msg("TASK paper-7: go // x", "ember", 777)] })
    );
  const a1 = new TestAgent({
    fetchFn: fakeFetch,
    channels: ["fleet"],
    cursorDir: dir,
    holdMs: 50,
  });
  a1.start();
  await a1.tasks.take();
  a1.stop();
  await new Promise((r) => setImmediate(r)); // let saveCursor flush
  const path = join(dir, "bookworm.fleet.cursor");
  expect(readFileSync(path, "utf8").trim()).toBe("777");
  // a fresh agent on the same dir would resume at 777
  const a2 = new TestAgent({ fetchFn: fakeFetch, cursorDir: dir });
  expect((a2 as unknown as { cursor: (c: string) => number }).cursor("fleet")).toBe(
    777
  );
});

test("subscribe loop: wakes on message, advances cursor, re-issues", async () => {
  const seenUrls: string[] = [];
  const queued: ChatMessage[] = [];
  const fakeFetch: FetchFn = async (input) => {
    seenUrls.push(String(input));
    if (queued.length === 0) {
      // first wake: deliver a task, second wake: park again forever
      queued.push(msg("TASK paper-1: read // why", "ember", 9001));
      return new Response(JSON.stringify({ messages: [queued[0]] }));
    }
    queued.length = 0;
    return new Response(JSON.stringify({ messages: [] }));
  };
  const agent = new TestAgent({
    fetchFn: fakeFetch,
    channels: ["fleet"],
    maxTransportFailures: 3,
    holdMs: 50,
  });
  agent.start();
  const task = await agent.tasks.take();
  expect(task.id).toBe("paper-1");
  expect(task.what).toBe("read");
  // cursor advanced past the delivered message: next poll uses since=9001
  const urls = seenUrls.join("\n");
  expect(urls).toContain("since=9001");
  // loop re-issued the long-poll (recursive, not timer-driven)
  expect(seenUrls.length).toBeGreaterThan(1);
  agent.stop();
});

test("subscribe loop: fail-fast after max transport failures", async () => {
  let calls = 0;
  const badFetch: FetchFn = async () => {
    calls += 1;
    return new Response("nope", { status: 500 });
  };
  const deaths: unknown[] = [];
  class DyingAgent extends TestAgent {
    override onTransportDead(err: unknown): void {
      deaths.push(err);
    }
  }
  const agent = new DyingAgent({
    fetchFn: badFetch,
    channels: ["fleet"],
    maxTransportFailures: 3,
    holdMs: 10,
  });
  agent.start();
  await new Promise((r) => setTimeout(r, 300));
  expect(calls).toBe(3); // exactly maxTransportFailures, no retry-spin
  expect(deaths.length).toBe(1);
  expect(String(deaths[0])).toContain("transport dead");
});
