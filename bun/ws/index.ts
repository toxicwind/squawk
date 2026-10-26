// squawk/bun/ws — WebSocket fan-out + topic subscription management.
// Used by the Bun server for reactive push (rooms, presence, targets).

export interface Sub {
  topics: Set<string>;
}

export interface WsHub {
  add(ws: any): void;
  remove(ws: any): void;
  /** Wire up a server's websocket handlers. */
  handlers: {
    open(ws: any): void;
    close(ws: any): void;
    message(ws: any, message: any): void;
  };
  /** Broadcast JSON to all sockets subscribed to `topic` (or "*"). */
  broadcast(topic: string, payload: any): void;
  count(): number;
}

export function createWsHub(server: any): WsHub {
  const subs = new Set<any>();

  function broadcast(topic: string, payload: any) {
    const data = JSON.stringify({ topic, ...payload });
    for (const ws of subs) {
      try {
        const s: Sub = ws.data.sub;
        if (s.topics.has(topic) || s.topics.has("*")) ws.send(data);
      } catch {
        // drop dead sockets
      }
    }
  }

  function handleMessage(ws: any, message: any) {
    try {
      const m = JSON.parse(String(message));
      const sub: Sub = ws.data.sub;
      if (Array.isArray(m.subscribe))
        m.subscribe.forEach((t: string) => {
          sub.topics.add(String(t));
        });
      if (Array.isArray(m.unsubscribe))
        m.unsubscribe.forEach((t: string) => {
          sub.topics.delete(String(t));
        });
      ws.send(JSON.stringify({ type: "subscribed", topics: [...sub.topics] }));
    } catch {
      // ignore
    }
  }

  const hub: WsHub = {
    add(ws: any) {
      ws.data = ws.data || {};
      if (!ws.data.sub) ws.data.sub = { topics: new Set<string>() };
      subs.add(ws);
    },
    remove(ws: any) {
      subs.delete(ws);
    },
    handlers: {
      open(ws: any) {
        hub.add(ws);
      },
      close(ws: any) {
        hub.remove(ws);
      },
      message: handleMessage,
    },
    broadcast,
    count: () => subs.size,
  };
  return hub;
}
