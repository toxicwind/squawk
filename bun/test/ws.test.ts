// squawk/bun/test/ws.test.ts
import { describe, expect, test } from "bun:test";
import { createWsHub } from "../ws/index.ts";

function fakeWs(topics: string[] = []): any {
  const socket = {
    data: { sub: { topics: new Set(topics) } },
    sent: [] as string[],
    send(m: string) {
      socket.sent.push(m);
    },
  };
  return socket;
}

describe("ws hub", () => {
  test("broadcast delivers to subscribed topic", () => {
    const hub = createWsHub(null as any);
    const ws = fakeWs(["room:fleet"]);
    hub.add(ws);
    hub.broadcast("room:fleet", { type: "message", body: "hi" });
    expect(ws.sent.length).toBe(1);
    const parsed = JSON.parse(ws.sent[0]);
    expect(parsed.topic).toBe("room:fleet");
  });

  test("wildcard * receives all", () => {
    const hub = createWsHub(null as any);
    const ws = fakeWs(["*"]);
    hub.add(ws);
    hub.broadcast("any-topic", { type: "x" });
    expect(ws.sent.length).toBe(1);
  });

  test("unsubscribed topic is dropped", () => {
    const hub = createWsHub(null as any);
    const ws = fakeWs(["room:ops"]);
    hub.add(ws);
    hub.broadcast("room:fleet", {});
    expect(ws.sent.length).toBe(0);
  });

  test("remove stops delivery", () => {
    const hub = createWsHub(null as any);
    const ws = fakeWs(["*"]);
    hub.add(ws);
    hub.remove(ws);
    hub.broadcast("room:fleet", {});
    expect(ws.sent.length).toBe(0);
  });

  test("count tracks live sockets", () => {
    const hub = createWsHub(null as any);
    hub.add(fakeWs());
    hub.add(fakeWs());
    expect(hub.count()).toBe(2);
  });

  test("handlers.open/close register/unregister", () => {
    const hub = createWsHub(null as any);
    const ws = fakeWs();
    hub.handlers.open(ws);
    expect(hub.count()).toBe(1);
    hub.handlers.close(ws);
    expect(hub.count()).toBe(0);
  });

  test("handlers.message subscribes/unsubscribes", () => {
    const hub = createWsHub(null as any);
    const ws = fakeWs([]);
    hub.add(ws);
    hub.handlers.message(ws, JSON.stringify({ subscribe: ["room:new"] }));
    hub.broadcast("room:new", {});
    expect(ws.sent.length).toBeGreaterThanOrEqual(1);
  });
});
