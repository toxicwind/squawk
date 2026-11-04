// squawk/bun/test/message-fields.test.ts — TDD: room message field conventions.
// The API historically wanted from_agent+body; peers (tau, kilo) naturally send
// agent_id+text. Both must work — the field convention is normalized, not
// discovered by trial and error.
import { beforeAll, afterAll, describe, expect, test } from "bun:test";
import { openStore } from "../store/index.ts";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let dir: string;
let store: ReturnType<typeof openStore>;

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "squawk-fields-"));
  store = openStore({ stateDir: dir });
});

afterAll(() => {
  store.db.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("room message field normalization", () => {
  test("canonical from_agent+body works", () => {
    const m = store.postMessage("fleet", { from_agent: "a1", body: "hello" });
    expect(m.from_agent).toBe("a1");
    expect(m.body).toBe("hello");
  });

  test("peer convention agent_id+text is accepted and normalized", () => {
    const m = store.postMessage("fleet", { agent_id: "a2", text: "world" });
    expect(m.from_agent).toBe("a2");
    expect(m.body).toBe("world");
  });

  test("mixed conventions normalize: agent_id+body, from_agent+text", () => {
    const m1 = store.postMessage("fleet", { agent_id: "a3", body: "x" });
    expect(m1.from_agent).toBe("a3");
    expect(m1.body).toBe("x");
    const m2 = store.postMessage("fleet", { from_agent: "a4", text: "y" });
    expect(m2.from_agent).toBe("a4");
    expect(m2.body).toBe("y");
  });

  test("missing sender entirely → named error, not a silent row", () => {
    expect(() => store.postMessage("fleet", { body: "orphan" })).toThrow();
  });

  test("missing content entirely → named error", () => {
    expect(() => store.postMessage("fleet", { from_agent: "a5" })).toThrow();
  });
});
