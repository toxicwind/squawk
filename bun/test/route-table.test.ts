// squawk/bun/test/route-table.test.ts — TDD contract for the table-driven router.
import { describe, expect, test } from "bun:test";
import { ROUTE_TABLE, matchRoute } from "../routes/table.ts";

describe("route table contract", () => {
  test("table is non-empty and every route has method+pattern+handler", () => {
    expect(ROUTE_TABLE.length).toBeGreaterThan(10);
    for (const r of ROUTE_TABLE) {
      expect(typeof r.method).toBe("string");
      expect(["GET", "POST", "PUT"]).toContain(r.method);
      expect(typeof r.pattern).toBe("string");
      expect(typeof r.handler).toBe("function");
    }
  });

  test("every /v1 route requires auth except none — auth flag present on all", () => {
    for (const r of ROUTE_TABLE) {
      expect(typeof r.auth).toBe("boolean");
    }
  });

  test("health is the only non-/v1 route and is auth-free", () => {
    const nonV1 = ROUTE_TABLE.filter((r) => !r.pattern.startsWith("/v1/"));
    expect(nonV1.map((r) => r.pattern)).toEqual(["/health"]);
    expect(nonV1[0].auth).toBe(false);
  });

  test("matchRoute resolves exact paths", () => {
    const m = matchRoute("GET", "/v1/rooms");
    expect(m).not.toBeNull();
    expect(m!.params).toEqual({});
  });

  test("matchRoute extracts params from :named segments", () => {
    const m = matchRoute("POST", "/v1/rooms/fleet/messages");
    expect(m).not.toBeNull();
    expect(m!.params.room_id).toBe("fleet");
  });

  test("matchRoute returns null for unmatched method+path", () => {
    expect(matchRoute("DELETE", "/v1/rooms")).toBeNull();
    expect(matchRoute("GET", "/nope")).toBeNull();
  });

  test("todo done route is parametrized", () => {
    const m = matchRoute("POST", "/v1/todo/some-file.md/done");
    expect(m).not.toBeNull();
    expect(m!.params.file).toBe("some-file.md");
  });

  test("dispatch claim/ack routes are parametrized", () => {
    const claim = matchRoute("POST", "/v1/dispatch/tasks/t1/claim");
    expect(claim!.params.task_id).toBe("t1");
    const ack = matchRoute("POST", "/v1/dispatch/claims/42/ack");
    expect(ack!.params.id).toBe("42");
    expect(ack!.params.op).toBe("ack");
  });
});
