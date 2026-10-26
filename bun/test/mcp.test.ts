// squawk/bun/test/mcp.test.ts
import { beforeAll, afterAll, describe, expect, test } from "bun:test";
import { mcpCallTool, MCP_TOOLS } from "../mcp/index.ts";
import { openStore } from "../store/index.ts";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let dir: string;
let store: ReturnType<typeof openStore>;

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "squawk-mcp-"));
  store = openStore({ stateDir: dir });
});

afterAll(() => {
  store.db.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("MCP tools", () => {
  test("MCP_TOOLS has the expected tools", () => {
    const names = MCP_TOOLS.map((t) => t.name);
    expect(names).toContain("join");
    expect(names).toContain("heartbeat");
    expect(names).toContain("post_message");
    expect(names).toContain("read_messages");
    expect(names).toContain("list_presence");
    expect(names).toContain("list_rooms");
    expect(names).toContain("get_state");
  });

  test("join via MCP", () => {
    const r = mcpCallTool(store, "join", {
      name: "mcp-bot",
      summoner: "test",
      agent_id: "mcp-bot-1",
    });
    expect(r.agent_id).toBe("mcp-bot-1");
  });

  test("heartbeat via MCP", () => {
    const r = mcpCallTool(store, "heartbeat", { agent_id: "mcp-bot-1" });
    expect(r.ok).toBe(true);
  });

  test("post_message + read_messages via MCP", () => {
    mcpCallTool(store, "post_message", {
      room_id: "fleet",
      from_agent: "mcp-bot-1",
      body: "mcp hello",
    });
    const msgs = mcpCallTool(store, "read_messages", {
      room_id: "fleet",
      since_seq: 0,
    });
    expect((msgs as any[]).map((m) => m.body)).toContain("mcp hello");
  });

  test("list_presence + list_rooms + get_state via MCP", () => {
    expect(mcpCallTool(store, "list_presence", {}).live_count).toBeGreaterThan(
      0,
    );
    const rooms = mcpCallTool(store, "list_rooms", {});
    expect(Array.isArray(rooms)).toBe(true);
    const state = mcpCallTool(store, "get_state", {});
    expect(state.service.name).toBe("squawk");
  });

  test("unknown tool throws", () => {
    expect(() => mcpCallTool(store, "bogus", {})).toThrow("unknown tool");
  });
});
