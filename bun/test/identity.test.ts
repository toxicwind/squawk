// squawk/bun/test/identity.test.ts
import { describe, expect, test } from "bun:test";
import {
  normalizeIdentity,
  nowISO,
  randomHex,
  type IdentityInput,
} from "../identity/index.ts";

describe("identity", () => {
  test("nowISO returns ISO timestamp", () => {
    const t = nowISO();
    expect(new Date(t).toString()).not.toBe("Invalid Date");
  });

  test("randomHex produces hex of requested length", () => {
    expect(randomHex(6)).toMatch(/^[0-9a-f]{6}$/);
    expect(randomHex(0)).toBe("");
  });

  test("normalizeIdentity requires name", () => {
    expect(() =>
      normalizeIdentity({ name: "", summoner: "s" } as IdentityInput),
    ).toThrow("name is required");
  });

  test("anonymous joins default summoner to anon (architect order 2026-10-28)", () => {
    const id = normalizeIdentity({ name: "wren", summoner: "" } as IdentityInput);
    expect(id.summoner).toBe("anon");
  });

  test("generates agent_id when not provided", () => {
    const id = normalizeIdentity({ name: "wren", summoner: "smith" });
    expect(id.agent_id).toMatch(/^sc-/);
    expect(id.name).toBe("wren");
    expect(id.summoner).toBe("smith");
  });

  test("preserves four-namespace identity fields", () => {
    const id = normalizeIdentity({
      name: "wren",
      summoner: "smith",
      agent_id: "agent-123",
      chat_id: "lane-main",
      host_machine_id: "host-a",
      hostname: "awrawr",
      hatchling_id: "fleet",
      surface: "claude",
      frame_id: "f1",
    });
    expect(id.agent_id).toBe("agent-123");
    expect(id.chat_id).toBe("lane-main");
    expect(id.host_machine_id).toBe("host-a");
    expect(id.hostname).toBe("awrawr");
    expect(id.hatchling_id).toBe("fleet");
    expect(id.surface).toBe("claude");
    expect(id.frame_id).toBe("f1");
  });

  test("clips long chat_id and surface", () => {
    const id = normalizeIdentity({
      name: "wren",
      summoner: "s",
      chat_id: "x".repeat(500),
      surface: "y".repeat(200),
    });
    expect(id.chat_id!.length).toBeLessThanOrEqual(80);
    expect(id.surface!.length).toBeLessThanOrEqual(64);
  });
});
