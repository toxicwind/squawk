// fleet-ui: squawk fleet web UI + feed proxy on :25136.
// Serves BOTH lanes: funnel /fleet -> 127.0.0.1:25136 and tailnet-direct 100.72.199.93:25136.
// Binds 0.0.0.0 so either lane reaches the same backend; pitchfork supervises (retry=true)
// for correct failover. Moved out of /tmp into the ranch repo 2026-09-30.
//
// WS-aware (2026-09-30): the UI's live sources (squawk-ws push, nats-ws) open a
// WebSocket at the same host+mount as the page (e.g. wss://<funnel>/fleet/squawk-ws).
// A plain fetch() proxy cannot complete the 101 upgrade, so without this the UI
// always degraded to 65s long-polling after every WS attempt 404'd. Upgrade
// requests are now shuttled frame-by-frame to the real backends over loopback.
//
// Server-auth (2026-09-30): the squawk server holds the feed token itself
// (/home/toxic/.fleet-bus/squawk-relay/feed-token) and injects it on proxied
// feed requests and squawk-ws upgrades when the browser sent none (or an empty
// one). Browsers never paste tokens; the token value only travels on loopback.
// The funnel only listens on tailnet addresses, so this is not a public
// exposure. A pasted/magic-link token is still forwarded as-is when present.
//
// Hot-reload (2026-09-30): ui.html is read per request and served with
// window.SERVER_AUTH injected, so UI edits land without a daemon restart.
import { readFileSync, statSync } from "node:fs";

const FEED = "http://127.0.0.1:25135";
const UI_PATH = "/home/toxic/estate/ranch/squawk/ui.html";
const FEED_TOKEN_PATH = "/home/toxic/.fleet-bus/squawk-relay/feed-token";

// websocket upgrade targets: client path -> backend ws url.
const WS_TARGETS: Record<string, string> = {
  "/squawk-ws": "ws://127.0.0.1:25147/squawk-ws",
  "/nats-ws": "ws://127.0.0.1:4223/",
};

// --- server-side feed token: read lazily, refresh when the file changes ---
let feedToken = "";
let feedTokenMtimeMs = 0;
function getFeedToken(): string {
  try {
    const st = statSync(FEED_TOKEN_PATH);
    if (st.mtimeMs !== feedTokenMtimeMs) {
      feedToken = readFileSync(FEED_TOKEN_PATH, "utf8").trim();
      feedTokenMtimeMs = st.mtimeMs;
    }
  } catch {
    /* token file unreadable: keep whatever we have (possibly empty) */
  }
  return feedToken;
}

// copy incoming headers, injecting the server-side feed token when the
// browser sent no usable Authorization header of its own.
function authHeaders(incoming: Headers): Headers {
  const out = new Headers(incoming);
  const auth = out.get("authorization") || "";
  if (!/^bearer\s+\S/i.test(auth)) {
    const t = getFeedToken();
    if (t) out.set("authorization", "Bearer " + t);
  }
  return out;
}

// backend ws url for an upgrade request; injects the server token into
// squawk-ws when the browser's ?token= is missing or empty.
function wsTarget(pathname: string, search: string): string {
  const base = WS_TARGETS[pathname];
  if (!base) return "";
  if (pathname === "/squawk-ws" && !new URLSearchParams(search).get("token")) {
    const t = getFeedToken();
    if (t) return base + "?token=" + encodeURIComponent(t);
  }
  return base + search;
}

// ui.html, read fresh per request (hot-reload) with the server-auth flag injected.
async function uiHtml(): Promise<string> {
  const raw = await Bun.file(UI_PATH).text();
  return raw.replace("<script>", "<script>\nwindow.SERVER_AUTH=true;");
}

type SockData = { target: string; backend?: WebSocket; pending: (string | Buffer)[] };

Bun.serve<SockData>({
  port: 25136,
  hostname: "0.0.0.0",
  async fetch(req, server) {
    const url = new URL(req.url);
    // --- websocket upgrade: shuttle to the real backend, don't fetch-proxy ---
    if (req.headers.get("upgrade")?.toLowerCase() === "websocket") {
      const target = wsTarget(url.pathname, url.search);
      if (target && server.upgrade(req, { data: { target, pending: [] } })) {
        return; // upgraded: the socket now lives in the websocket handlers
      }
      return new Response("no websocket target for " + url.pathname, { status: 404 });
    }
    if (url.pathname === "/" || url.pathname === "/ui") {
      return new Response(await uiHtml(), { headers: { "Content-Type": "text/html" } });
    }
    // proxy everything else to the feed
    // the feed serves everything under /squawk-feed/*; the client speaks
    // bare relative paths, so add the prefix here (unless already present)
    const pfx = url.pathname.startsWith("/squawk-feed/") ? "" : "/squawk-feed";
    const target = FEED + pfx + url.pathname + url.search;
    const resp = await fetch(target, {
      method: req.method,
      headers: authHeaders(req.headers),
      body: req.method === "GET" || req.method === "HEAD" ? undefined : req.body,
    });
    return new Response(resp.body, { status: resp.status, headers: resp.headers });
  },
  websocket: {
    open(ws) {
      let backend: WebSocket;
      try {
        backend = new WebSocket(ws.data.target);
      } catch {
        try { ws.close(1011, "backend dial failed"); } catch {}
        return;
      }
      ws.data.backend = backend;
      backend.onopen = () => {
        for (const m of ws.data.pending.splice(0)) {
          try { backend.send(m); } catch {}
        }
      };
      backend.onmessage = (ev) => {
        try { ws.send(ev.data); } catch {}
      };
      backend.onclose = (ev) => {
        try { ws.close(ev.code || 1000, ev.reason || "backend closed"); } catch {}
      };
      backend.onerror = () => {
        try { ws.close(1011, "backend error"); } catch {}
      };
    },
    message(ws, message) {
      const b = ws.data.backend;
      if (b && b.readyState === WebSocket.OPEN) {
        try { b.send(message); } catch {}
      } else {
        ws.data.pending.push(message); // queue the subscribe frame until dial completes
      }
    },
    close(ws) {
      try { ws.data.backend?.close(); } catch {}
    },
  },
});
console.log("fleet-ui on 0.0.0.0:25136 (funnel /fleet + tailnet-direct), ws-aware, server-auth, hot-reload");
