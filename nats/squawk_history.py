#!/usr/bin/env python3
"""squawk-history: paged, compacted history reads over the JetStream stream.

Chris's directive (2026-10-19): "seeing all 15000 is entirely pointless" --
history needs paging plus context deprecation/pruning/compacting. Design from
the code race on the real corpus (~/workspace/paging-research/race-results.md):

- /history: seq-cursor paging over envelope seqs (the boring correct
  primitive). Pages are exact slices of the channel, chronologically ordered.
- /pack: a context pack under a token budget, scored by the race's C1+C3
  hybrid -- TF-IDF relevance x recency decay x importance (C1), weighted by
  Markov transition surprise over sender x topic states (C3, the race winner
  at 16k). No hard prune: low scorers are replaced by episode DIGESTS that
  carry their seq range, so pruned spans stay addressable via /history.
  Raw messages always remain in JetStream; nothing is ever deleted.

Index: envelopes are scanned from the stream at boot; each request first
pulls only the delta (stream seqs newer than the index), so reads are
always current without a background loop. Scoring artifacts (TF-IDF,
episodes, Markov chain) rebuild lazily when the index moved.

Auth: the squawk feed token (Authorization: Bearer ...), same as the feed.
Bind: 127.0.0.1:$SQUAWK_HISTORY_PORT (default 25152; 25149/25150 are the
paper-poller's).
"""
import asyncio
import json
import math
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import squawk_nats_tail as tail  # noqa: E402  (NATS_URL, STREAM, token, channels)
import nats  # noqa: E402

PORT = int(os.environ.get("SQUAWK_HISTORY_PORT", "25152"))
TOKEN = tail._load_token()
CHANNELS = tail.CHANNELS

STOP = set('''a an the and or of to in is it on for as at be by was were are
with from that this his her they their we you he she my our your its not no
but so if then than too very can will just don do does did have has had been
being up out over into down all any more most other some such only own same
both each few also when what who which while where there here how why'''.split())
TOK_RE = re.compile(r'[a-z0-9][a-z0-9\-]{1,30}')
SHA_RE = re.compile(r'\b[0-9a-f]*[a-f][0-9a-f]*\b')
MENTION_RE = re.compile(r'@[\w\-]+')
PATH_RE = re.compile(r'/home/|/tmp/|/usr/|/etc/')


def tokenize(text):
    return [t for t in TOK_RE.findall((text or "").lower())
            if t not in STOP and len(t) > 1]


# --------------------------------------------------------------------------
# per-channel index + scoring artifacts
# --------------------------------------------------------------------------

class ChannelIndex:
    def __init__(self, channel):
        self.channel = channel
        self.recs = []            # envelope dicts + stream_seq, sorted by seq
        self._seen = set()        # envelope keys already indexed
        self.last_stream_seq = 0
        self.dirty = True         # scoring artifacts stale
        self.tfidf = None
        self.imp = None
        self.eps = None
        self.digests = None
        self.surprise = None
        self.lock = threading.Lock()

    # -- ingestion ---------------------------------------------------------
    @staticmethod
    def _env_key(env):
        """Canonical message identity (same multiset key as the backfill):
        the same file can be published twice across tailer restarts, so the
        stream can hold duplicate copies of one envelope -- keep the first."""
        import hashlib
        body = env.get("body") or ""
        return (env.get("seq", 0), env.get("from", ""), env.get("ts", ""),
                env.get("title", ""),
                hashlib.sha256(body.encode("utf-8")).hexdigest())

    def merge(self, envs):
        """envs: [(stream_seq, envelope)] newer than last_stream_seq."""
        if not envs:
            return
        for sseq, env in envs:
            self.last_stream_seq = max(self.last_stream_seq, sseq)
            k = self._env_key(env)
            if k in self._seen:
                continue
            self._seen.add(k)
            rec = dict(env)
            rec["stream_seq"] = sseq
            self.recs.append(rec)
        self.recs.sort(key=lambda r: (r.get("seq", 0), r["stream_seq"]))
        self.dirty = True

    # -- scoring artifacts (race code, adapted to envelopes) ---------------
    def ensure_artifacts(self):
        if not self.dirty and self.tfidf is not None:
            return
        recs = self.recs
        # datetimes + ages
        last = None
        for r in recs:
            dt = None
            ts = r.get("ts") or ""
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                dt = None
            if dt is None:
                dt = last
            r["_dt"] = dt
            if dt is not None:
                last = dt
        recs2 = [r for r in recs if r.get("_dt") is not None]
        tmax = max((r["_dt"] for r in recs2), default=None)
        for r in recs2:
            r["_age_days"] = (tmax - r["_dt"]).total_seconds() / 86400.0
        # tfidf
        docs = [tokenize((r.get("from") or "") + " " + (r.get("title") or "")
                          + " " + (r.get("body") or "")) for r in recs2]
        df = Counter()
        tfs = []
        for toks in docs:
            tf = Counter(toks)
            tfs.append(tf)
            df.update(tf.keys())
        N = len(docs) or 1
        idf = {t: math.log((1 + N) / (1 + c)) + 1.0 for t, c in df.items()}
        vecs, norms, inv = [], [], defaultdict(list)
        for i, (tf, toks) in enumerate(zip(tfs, docs)):
            ln = len(toks) or 1
            v = {t: (c / ln) * idf[t] for t, c in tf.items()}
            vecs.append(v)
            norms.append(math.sqrt(sum(x * x for x in v.values())))
            for t, w in v.items():
                inv[t].append((i, w))
        self.tfidf = {"idf": idf, "vecs": vecs, "norms": norms, "inv": inv}
        self._scored_recs = recs2
        # importance
        raw = []
        for r in recs2:
            b = r.get("body") or ""
            m = len(MENTION_RE.findall(b))
            sha = sum(1 for t in SHA_RE.findall(b) if 7 <= len(t) <= 40)
            path = len(PATH_RE.findall(b))
            fence = b.count("```") // 2
            longf = 1.0 if len(b) > 3000 else 0.0
            raw.append(math.log1p(m) + min(sha + path, 4) * 0.4
                       + min(fence, 2) * 0.5 + longf)
        lo, hi = (min(raw), max(raw)) if raw else (0.0, 1.0)
        span = (hi - lo) or 1.0
        self.imp = [(x - lo) / span for x in raw]
        # episodes (gap + cohesion, from the race)
        self.eps = self._segment(recs2)
        self.digests = self._episode_digests(recs2)
        # markov surprise
        self.surprise = self._surprise(recs2)
        self.dirty = False

    def _segment(self, recs, gap_min=30, win=5):
        vecs, norms = self.tfidf["vecs"], self.tfidf["norms"]
        eps, cur = [], [0]
        coh_hist = deque(maxlen=50)

        def centroid_cos(i, members):
            cv = defaultdict(float)
            for j in members[-win:]:
                for t, w in vecs[j].items():
                    cv[t] += w
            cn = math.sqrt(sum(x * x for x in cv.values())) or 1.0
            dot = sum(cv[t] * w for t, w in vecs[i].items() if t in cv)
            return dot / (cn * (norms[i] or 1.0))

        for i in range(1, len(recs)):
            boundary = False
            if (recs[i]["_dt"] - recs[i - 1]["_dt"]).total_seconds() > gap_min * 60:
                boundary = True
            else:
                c = centroid_cos(i, cur)
                if len(coh_hist) == 50:
                    if c < sorted(coh_hist)[7]:
                        boundary = True
                coh_hist.append(c)
            if boundary:
                eps.append(cur)
                cur = [i]
            else:
                cur.append(i)
        if cur:
            eps.append(cur)
        return eps

    def _episode_digests(self, recs):
        out = []
        for ei, ep in enumerate(self.eps):
            tsum = Counter()
            for i in ep:
                for t, w in self.tfidf["vecs"][i].items():
                    tsum[t] += w
            top = [t for t, _ in tsum.most_common(6)]
            senders = Counter(recs[i].get("from") or "?" for i in ep)
            out.append({
                "episode": ei,
                "count": len(ep),
                "seq_first": recs[ep[0]]["seq"],
                "seq_last": recs[ep[-1]]["seq"],
                "senders": dict(senders),
                "terms": top,
            })
        return out

    def _surprise(self, recs):
        vecs = self.tfidf["vecs"]
        topterm = [max(v, key=v.get) if v else "__none__" for v in vecs]
        states = [((r.get("from") or "?"), t) for r, t in zip(recs, topterm)]
        trans = defaultdict(Counter)
        outc = Counter()
        for a, b in zip(states, states[1:]):
            trans[a][b] += 1
            outc[a] += 1
        V = len(set(states)) or 1
        sur = [0.0] * len(recs)
        if recs:
            sur[0] = math.log(V)
            for i in range(1, len(recs)):
                a, b = states[i - 1], states[i]
                c = trans.get(a, {}).get(b, 0)
                sur[i] = -math.log((c + 1) / (outc.get(a, 0) + V))
        return sur

    # -- reads --------------------------------------------------------------
    def page(self, before=None, after=None, limit=100):
        recs = self.recs
        limit = max(1, min(limit, 1000))
        if before is not None:
            cand = [r for r in recs if r["seq"] < before]
            sel = cand[-limit:]
        elif after is not None:
            cand = [r for r in recs if r["seq"] > after]
            sel = cand[:limit]
        else:
            sel = recs[-limit:]
        return {
            "channel": self.channel,
            "total": len(recs),
            "messages": [self._pub(r) for r in sel],
            "next_before": sel[0]["seq"] if sel else None,
            "next_after": sel[-1]["seq"] if sel else None,
        }

    @staticmethod
    def _pub(r):
        return {k: r.get(k) for k in
                ("seq", "channel", "from", "to", "ts", "title", "type",
                 "sealed", "body")}

    def pack(self, query, budget_tokens=16000):
        self.ensure_artifacts()
        recs = self._scored_recs
        n = len(recs)
        if n == 0:
            return {"channel": self.channel, "messages": [], "digests": []}
        budget = max(1000, budget_tokens) * 4  # chars approx
        # C1 relevance
        qtok = [t for t in tokenize(query) if t in self.tfidf["idf"]]
        qv = {t: (qtok.count(t) / max(len(qtok), 1)) * self.tfidf["idf"][t]
              for t in set(qtok)}
        qn = math.sqrt(sum(x * x for x in qv.values())) or 1.0
        acc = defaultdict(float)
        for t, qw in qv.items():
            for i, dw in self.tfidf["inv"].get(t, ()):
                acc[i] += qw * dw
        rel = [0.0] * n
        for i, dot in acc.items():
            rel[i] = dot / (qn * (self.tfidf["norms"][i] or 1.0))
        rmax = max(rel) or 1.0
        smax = max(self.surprise) or 1.0
        scored = []
        for i in range(n):
            rec = 2.0 ** (-recs[i]["_age_days"] / 3.0)
            base = (rel[i] / rmax + rec + self.imp[i]) / 3.0
            score = base * (0.5 + self.surprise[i] / smax)  # C3 hybrid weight
            text = self._text(recs[i])
            scored.append((i, score, text))
        scored.sort(key=lambda x: -x[1])
        chosen, used = [], 0
        for i, s, text in scored:
            if used + len(text) <= budget:
                chosen.append(i)
                used += len(text)
        chosen_set = set(chosen)
        # digests for episodes with NO chosen message (fully pruned spans);
        # most recent first, capped -- the full set can be thousands
        digests = []
        for ei, ep in enumerate(self.eps):
            if not any(i in chosen_set for i in ep):
                digests.append(self.digests[ei])
        digests_total = len(digests)
        digests.sort(key=lambda d: -d["seq_last"])
        digests = digests[:40]
        chosen.sort(key=lambda i: recs[i]["seq"])
        return {
            "channel": self.channel,
            "budget_tokens": budget_tokens,
            "used_tokens_est": used // 4,
            "messages": [self._pub(recs[i]) for i in chosen],
            "digests": digests,
            "digests_total": digests_total,
            "note": "digests cover pruned episodes (40 most recent shown); "
                    "page /history with before/after seq cursors to expand "
                    "any digest range",
        }

    @staticmethod
    def _text(r):
        return (f"[{r['seq']} | {r.get('from')} | {r.get('ts')}]\n"
                f"{r.get('title') or ''}\n{r.get('body') or ''}")


INDEX = {ch: ChannelIndex(ch) for ch in CHANNELS}
_loop = asyncio.new_event_loop()


async def _scan_channel(js, idx: ChannelIndex):
    """Pull envelopes with stream_seq > idx.last_stream_seq for one channel."""
    info = await js.stream_info(tail.STREAM)
    last = info.state.last_seq
    if idx.last_stream_seq >= last:
        return
    sub = await js.pull_subscribe(
        idx.channel + ".messages", stream=tail.STREAM,
        config=_consumer_cfg(idx.last_stream_seq))
    try:
        while True:
            try:
                msgs = await sub.fetch(batch=500, timeout=2.0)
            except Exception:
                break
            if not msgs:
                break
            envs = []
            for m in msgs:
                try:
                    env = json.loads(m.data.decode("utf-8"))
                    envs.append((m.metadata.sequence.stream, env))
                except Exception:
                    pass
            idx.merge(envs)
    finally:
        try:
            await sub.unsubscribe()
        except Exception:
            pass


def _consumer_cfg(start_seq):
    import nats.js.api as api
    if start_seq <= 0:
        return api.ConsumerConfig(deliver_policy=api.DeliverPolicy.ALL,
                                  ack_policy=api.AckPolicy.NONE)
    return api.ConsumerConfig(
        deliver_policy=api.DeliverPolicy.BY_START_SEQUENCE,
        opt_start_seq=start_seq + 1, ack_policy=api.AckPolicy.NONE)


async def _refresh_some(channels):
    nc = await nats.connect(tail.NATS_URL, token=TOKEN)
    js = nc.jetstream()
    for ch in channels:
        await _scan_channel(js, INDEX[ch])
    await nc.close()


_last_refresh = {}


def refresh(channel=None):
    """Pull the delta for one channel (or all at boot). A 5s freshness
    cache keeps busy-channel traffic from making every read rescan."""
    now = time.time()
    if channel is not None:
        if now - _last_refresh.get(channel, 0) < 5:
            return
        _last_refresh[channel] = now
        _loop.run_until_complete(_refresh_some([channel]))
    else:
        _loop.run_until_complete(_refresh_some(list(INDEX)))


# --------------------------------------------------------------------------
# HTTP surface
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._json({"ok": False, "error": "unauthorized"}, 401)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        ch = (q.get("channel") or ["fleet"])[0]
        idx = INDEX.get(ch)
        if u.path == "/health":
            return self._json({"ok": True,
                               "channels": {c: len(i.recs)
                                            for c, i in INDEX.items()}})
        if idx is None:
            return self._json({"ok": False, "error": "unknown channel"}, 404)
        refresh(ch)
        if u.path == "/history":
            before = q.get("before", [None])[0]
            after = q.get("after", [None])[0]
            limit = int(q.get("limit", ["100"])[0])
            return self._json({"ok": True, **idx.page(
                before=int(before) if before else None,
                after=int(after) if after else None, limit=limit)})
        if u.path == "/pack":
            query = (q.get("q") or [""])[0]
            budget = int(q.get("budget", ["16000"])[0])
            return self._json({"ok": True, **idx.pack(query, budget)})
        if u.path == "/channels":
            return self._json({"ok": True, "channels": sorted(INDEX)})
        return self._json({"ok": False, "error": "not found"}, 404)


def main():
    print("squawk-history: building index from JetStream...", flush=True)
    t0 = time.time()
    refresh()
    counts = {c: len(i.recs) for c, i in INDEX.items()}
    print(f"squawk-history: index ready {counts} in {time.time()-t0:.1f}s",
          flush=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"squawk-history listening on 127.0.0.1:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
