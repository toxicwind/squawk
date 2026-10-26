// squawk/bun/test/bus-mirror.test.ts
// Verifies the chat server mirrors posts into the squawk file bus so
// squawk-feed/ws/campfire see them (unifies the two "fleet" surfaces).
import { beforeAll, afterAll, describe, expect, test } from "bun:test";
import {
  mkdtempSync,
  rmSync,
  existsSync,
  readdirSync,
  readFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openStore } from "../store/index.ts";

let dir: string;
let bus: string;
let store: ReturnType<typeof openStore>;

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "squawk-busmirror-"));
  bus = `${dir}/bus-root`;
  store = openStore({
    stateDir: `${dir}/state`,
    busRoot: bus,
    presenceTtlS: 120,
  });
});

afterAll(() => {
  store.db.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("chat -> bus mirror", () => {
  test("createRoom makes a bus channel dir", () => {
    store.createRoom({ room_id: "ops", name: "ops", created_by: "test" });
    expect(existsSync(`${bus}/ops`)).toBe(true);
  });

  test("postMessage writes a native .md to the bus with nanotime seq", () => {
    store.join({ name: "bus-bot", summoner: "t", agent_id: "bus-bot" });
    store.postMessage("fleet", {
      from_agent: "bus-bot",
      body: "hello from chat server (mirrored)",
    });
    // files use nanotime-ms seq convention (sort above channel high-water)
    const files = readdirSync(`${bus}/fleet`).filter((n) =>
      n.endsWith("-bus-bot-chat.md"),
    );
    expect(files.length).toBeGreaterThan(0);
    const latest = files[files.length - 1];
    const content = readFileSync(`${bus}/fleet/${latest}`, "utf-8");
    const seqStr = latest.split("-")[0];
    const seqNum = Number(seqStr);
    expect(seqNum).toBeGreaterThan(1_700_000_000_000); // nanotime-ms, not rowid
    expect(content).toContain(`seq: ${seqStr}`);
    expect(content).toContain("from: bus-bot");
    expect(content).toContain("channel: fleet");
    expect(content).toContain("hello from chat server (mirrored)");
  });

  test("sendTargeted to #channel mirrors to that bus channel", () => {
    store.sendTargeted({ from: "bus-bot", to: "#ops", body: "ops note" });
    const files = readdirSync(`${bus}/ops`).filter((n) =>
      n.endsWith("-bus-bot-chat.md"),
    );
    expect(files.length).toBeGreaterThan(0);
    const latest = files[files.length - 1];
    expect(readFileSync(`${bus}/ops/${latest}`, "utf-8")).toContain("ops note");
  });

  test("sendTargeted to plain target mirrors to fleet", () => {
    store.sendTargeted({ from: "bus-bot", to: "someone", body: "dm-ish" });
    const files = readdirSync(`${bus}/fleet`).filter((n) =>
      n.endsWith("-bus-bot-chat.md"),
    );
    expect(files.length).toBeGreaterThanOrEqual(2); // earlier post + this one
  });

  test("invalid channel name does not write a bus file", () => {
    // room with a space / invalid name -> no dir created, messages still fine
    store.createRoom({ room_id: "bad room!", name: "bad" });
    expect(existsSync(`${bus}/bad room!`)).toBe(false);
  });
});

describe("without busRoot (headless/mcp)", () => {
  test("store works even with no busRoot", () => {
    const headless = openStore({
      stateDir: `${dir}/no-bus`,
      presenceTtlS: 120,
    });
    headless.join({ name: "x", summoner: "t", agent_id: "x" });
    const m = headless.postMessage("fleet", {
      from_agent: "x",
      body: "no bus",
    });
    expect(m.seq).toBeGreaterThan(0);
    expect(existsSync(`${dir}/no-bus`)).toBe(true);
    headless.db.close();
  });

  test("post with empty/whitespace body is rejected", () => {
    expect(() =>
      store.postMessage("fleet", { from_agent: "bus-bot", body: "   " }),
    ).toThrow("body is required");
  });

  test("join twice is idempotent upsert", () => {
    store.join({ name: "bus-bot", summoner: "t", agent_id: "bus-bot" });
    store.join({ name: "bus-bot2", summoner: "t", agent_id: "bus-bot" });
    const live = store.liveAgents();
    const matches = (live.live as any[]).filter(
      (x) => x.agent_id === "bus-bot",
    );
    expect(matches.length).toBe(1);
    expect(matches[0].name).toBe("bus-bot2");
  });
});
