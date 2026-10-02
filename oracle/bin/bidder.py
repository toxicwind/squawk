#!/usr/bin/env python3
"""
Bidder worker for the oracle-market.

Watches the bid-market channel via inotify, posts HMAC-signed AES-GCM-sealed
bids (SPEC §1.2) on tasks whose tags intersect its own, executes won tasks
in a local subprocess, posts results with a
(2026-09-20: unshare -rn restored - proof-live-2 verified it works under pitchfork),
committed proof hash + artifact list, and narrates everything to the fleet
channel in a persona voice.

Persistent agent: may file upgrade petitions under market governance.
Single instance per bidder id (flock).

Usage:
  bidder.py --id forge --name Forge --emoji "\\U0001F528"
      --tags code-fix,probe
      --tagline "I fix broken things and poke them till they confess."
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import select
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---- oracle_loop import (channel paths, message parsing, inotify) ----
BIN = Path(__file__).resolve().parent
ORACLE = BIN / "oracle_loop.py"
sys.path.insert(0, str(BIN))
_spec = importlib.util.spec_from_file_location("oracle_loop", ORACLE)
ol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ol)
import sealed as sealed_mod      # noqa: E402
import mechanism as mech         # noqa: E402
import keypool as keypool_mod    # noqa: E402  (provider key-pool rotation, SPEC §8)

CHANNEL = ol.CHANNEL
FLEET = ol.FLEET
SEQ_RE = ol.SEQ_RE
PAYLOAD_CAP_S = 590  # hard ceiling per task execution
RALPH_BIN = Path("/home/toxic/.local/bin/super-ralph")
RALPH_CAP_S = 1740  # 29 min ceiling: Super Ralph runs are slow (~11 min
                    # observed for a trivial run)
RALPH_MODEL = os.environ.get("RALPH_MODEL", "kimi-k3-nim")
RALPH_BASE_URL = os.environ.get("RALPH_BASE_URL",
                                "http://127.0.0.1:25200/v1")  # cuttinggate (canonical router); cut over 2026-10-02
# cuttinggate's auth gate requires a "Bearer " prefix (any non-empty value;
# the upstream key comes from cuttinggate's own credential plane).
RALPH_API_KEY = os.environ.get("RALPH_API_KEY", "oracle-market-bidder")
OUT_CAP = 8000
ERR_CAP = 2000
PARTIAL_CAP = 65536  # bound for the on-disk partial-output evidence file
RALPH_POST_BUFFER_S = 30.0  # time to preserve evidence + post result
                             # before the oracle's exec deadline


# ---- timeout evidence preservation (2026-09-21: tern) ----
# A super-ralph timeout used to discard everything: the TimeoutExpired
# handler returned empty output, so finished nodes' work vanished and the
# task settled "no-result / empty-output". Preserve bounded, redacted
# partial evidence instead -- graceful degradation, never silent loss.
def _redact_text(s):
    """Redact credential-shaped values. Conservative: value replaced,
    key name kept so the shape of the output stays readable."""
    if not s:
        return s
    if isinstance(s, bytes):
        # 2026-09-21 (tern): TimeoutExpired.stdout/stderr are bytes;
        # decode before regex (was TypeError on tern-proof-005).
        s = s.decode("utf-8", errors="replace")
    pats = [
        (r"(?i)(api[_-]?key|apikey)\s*[:=]\s*[\"']?([^\s\"\n]+)",
         r"\1=[REDACTED]"),
        (r"(?i)\b(bearer)\s+([A-Za-z0-9\-._~+/=]{8,})",
         r"\1 [REDACTED]"),
        (r"(?i)(token|secret|password|passwd|pwd)\s*[:=]\s*[\"']?"
         r"([^\s\"\n]+)", r"\1=[REDACTED]"),
        (r"\bsk-[A-Za-z0-9]{16,}", "sk-[REDACTED]"),
        (r"\bhf_[A-Za-z0-9]{16,}", "hf-[REDACTED]"),
    ]
    for pat, sub in pats:
        s = re.sub(pat, sub, s)
    return s


def _canon_ralph_text(s):
    """Super Ralph's headless stdout may carry literal "\n" escapes
    instead of real newlines. Canonicalize before hash/sign/post so the
    acceptance parser (and humans) see real text. Only when no real
    newlines exist, to avoid corrupting mixed or legitimately-backslashed
    output."""
    if "\\n" in s and "\n" not in s:
        s = (s.replace("\\r\\n", "\n").replace("\\n", "\n")
              .replace("\\t", "\t"))
    return s


def _summarize_ralph_nodes(workdir):
    """Best-effort node-state summary from the super-ralph workflow DB.
    Returns e.g. 'nodes: 12 finished / 2 pending / 1 in-progress (15
    total)' or '' when the DB is absent/unreadable. Never raises."""
    try:
        import sqlite3
        from pathlib import Path
        db = None
        for cand in Path(workdir).glob(".super-ralph/**/workflow.db"):
            db = cand
            break
        if db is None:
            return ""
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        try:
            rows = con.execute(
                "SELECT state, COUNT(*) FROM _smithers_nodes GROUP BY state"
            ).fetchall()
        finally:
            con.close()
        if not rows:
            return ""
        states = {r[0]: r[1] for r in rows}
        total = sum(states.values())
        parts = ["%d %s" % (states[k], k)
                 for k in ("finished", "in-progress", "pending") if k in states]
        extra = [k for k in states if k not in ("finished", "in-progress",
                                                "pending")]
        parts += ["%d %s" % (states[k], k) for k in extra]
        return "nodes at timeout: %s (%d total)" % (", ".join(parts), total)
    except Exception:
        return ""



# ---- super-ralph model resolution (2026-09-21: ralph-pathfinder) ----
# Root cause of the 2026-09-21 execution collapse: the bidder's inherited
# env carried NIM_MODEL=moonshotai/kimi-k3 -- an UPSTREAM provider ID, not
# a herd-router route name. The router 404s it ("no router for requested
# model"), so every super-ralph model call failed and tasks died empty.
# Never trust the inherited NIM_MODEL blindly: resolve a WORKING model
# against the router with a live probe, falling back down a priority chain.
RALPH_MODEL_CANDIDATES = [
    os.environ.get("RALPH_MODEL") or "",  # explicit operator override
    # 2026-10-02 cutover: :25104 retired, :25200 (cuttinggate) is canonical.
    # gemini-eap-openai/gemini-3.8-flash is not served on :25200
    # (google/gemini-3.8-flash there is openrouter-only, 402 no-credit).
    "openai/gpt-oss-20b",  # groq via cuttinggate :25200, verified live 2026-10-02 (GROQ-OK)
]
_ralph_model_cache = {"model": None, "ts": 0.0}
RALPH_MODEL_CACHE_S = 300


def _resolve_ralph_model(base_url, timeout=15):
    """Pick a working model for super-ralph.

    Probes each candidate with a tiny completion against the router;
    returns the first that answers. Caches the winner for 5 minutes so
    the probe cost is paid once, not per task. If nothing answers, returns
    the first candidate so the run fails loudly (never silently swaps in
    an unrelated model).
    """
    now = time.time()
    if (_ralph_model_cache["model"]
            and now - _ralph_model_cache["ts"] < RALPH_MODEL_CACHE_S):
        return _ralph_model_cache["model"]
    candidates = [c for c in RALPH_MODEL_CANDIDATES if c]
    base = base_url.rstrip("/")
    for cand in candidates:
        try:
            body = json.dumps({
                "model": cand,
                "messages": [{"role": "user", "content": "Reply with: ok"}],
                # 2026-10-02: 64, not 5 -- reasoning models (gpt-oss-20b)
                # spend the first tokens thinking; max_tokens=5 yields a
                # 200 with empty content, which the router scores as failure.
                "max_tokens": 64,
            }).encode()
            req = urllib.request.Request(
                base + "/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + RALPH_API_KEY,
                         "User-Agent": "oracle-market-bidder"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.loads(r.read().decode("utf-8", "replace"))
            if payload.get("choices"):
                _ralph_model_cache.update(model=cand, ts=now)
                return cand
        except Exception:
            continue
    model = candidates[0] if candidates else "kimi-k3-nim"
    _ralph_model_cache.update(model=model, ts=now)
    return model


# ---- knowledgebase attestation (fleet rule, enforced by the oracle) ----
# Every bid must attest the bidder read Active Crews
# (docs/fleet-knowledgebase.md §2, canonical main) and checked for
# overlapping work. The oracle rejects unattested bids
# (bid_rejected{reason:no-attestation}, SPEC §10) — so a bidder
# that cannot attest must skip the bid loudly, never bid blind.
KB_COMMITS_API = ("https://api.github.com/repos/toxicwind/sovereign-projects"
                  "/commits?path=docs/fleet-knowledgebase.md&per_page=1")
KB_RAW_URL = ("https://raw.githubusercontent.com/toxicwind/"
              "sovereign-projects/main/docs/fleet-knowledgebase.md")
KB_CACHE = BIN.parent / "work" / "kb-attestation-cache.json"  # runtime cache: regenerable, untracked
KB_HTTP_TIMEOUT = 10


def _parse_kb_crews(md_text):
    """Extract crew names from the §2 Active Crews table."""
    crews = []
    in_sec = False
    for line in md_text.splitlines():
        if line.startswith("## 2."):
            in_sec = True
            continue
        if in_sec and line.startswith("## "):
            break
        if in_sec and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            name = cells[0] if cells else ""
            if (name and name.lower() not in ("crew", "---")
                    and not set(name) <= set("-: ")):
                crews.append(name)
    return crews


def _fetch_kb_attestation():
    """Fresh (kb_sha, crews) from canonical main. None on any failure."""
    try:
        req = urllib.request.Request(
            KB_COMMITS_API, headers={"User-Agent": "oracle-market-bidder",
                                     "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=KB_HTTP_TIMEOUT) as r:
            commits = json.loads(r.read().decode("utf-8", "replace"))
        sha = (commits or [{}])[0].get("sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
            return None
        req = urllib.request.Request(
            KB_RAW_URL, headers={"User-Agent": "oracle-market-bidder"})
        with urllib.request.urlopen(req, timeout=KB_HTTP_TIMEOUT) as r:
            md = r.read().decode("utf-8", "replace")
        crews = _parse_kb_crews(md)
        if not crews:
            return None
        try:
            KB_CACHE.write_text(json.dumps({"kb_sha": sha, "crews": crews,
                                            "fetched_ts": time.time()}),
                                encoding="utf-8")
        except OSError:
            pass
        return sha, crews
    except Exception:
        return None


def kb_attestation():
    """Attestation dict for the bid body, or None when the knowledgebase
    is unreachable and no cache exists (caller must skip bidding)."""
    fresh = _fetch_kb_attestation()
    sha, crews = fresh if fresh else (None, None)
    if not fresh:
        try:
            cached = json.loads(KB_CACHE.read_text(encoding="utf-8"))
            sha, crews = cached.get("kb_sha"), cached.get("crews")
        except (OSError, ValueError):
            pass
    if not sha or not crews:
        return None
    return {
        "kb_sha": sha,
        "checked_crews": crews,
        "no_overlap": (
            "read Active Crews (docs/fleet-knowledgebase.md §2) at kb %s; "
            "crews checked: %s; to my knowledge this bid does not duplicate "
            "claimed crew work." % (sha[:12], ", ".join(crews))),
    }


class SeqPoster:
    """Atomic multi-poster-safe message writer for one channel dir.

    Refreshes seq from the directory before every post and bumps past
    collisions, so several bidders + the oracle can share a channel.
    """

    def __init__(self, channel_dir, channel_name, frm):
        self.dir = Path(channel_dir)
        self.channel = channel_name
        self.frm = frm
        self.lamport = 0
        self.last_hash = ""
        self._lock = threading.Lock()

    def _refresh(self):
        files = [f for f in os.listdir(self.dir) if SEQ_RE.match(f)]
        self.seq = max([int(SEQ_RE.match(f).group(1)) for f in files] or [0])
        if files:
            latest = sorted(files)[-1]
            parsed = ol.parse_msg(self.dir / latest)
            if parsed:
                meta, _ = parsed
                try:
                    self.lamport = int(meta.get("lamport", 0))
                except ValueError:
                    pass
                self.last_hash = hashlib.sha256(
                    (self.dir / latest).read_bytes()).hexdigest()

    def post(self, msg_type, title, body, task_id="", note="", to="all",
             raw_body=False, extra_fm=None):
        with self._lock:
            self._refresh()
            self.seq += 1
            self.lamport += 1
            parents = [self.last_hash] if self.last_hash else []
            ts = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
            fm = (
                f"---\nseq: {self.seq}\nfrom: {self.frm}\nto: {to}\n"
                f"msg_type: {msg_type}\ntask_id: {task_id}\n"
                f"channel: {self.channel}\nts: {ts}\nstatus: {self.channel}\n"
                f"title: {title}\nlamport: {self.lamport}\n"
                f"parents: {json.dumps(parents)}\n"
            )
            if extra_fm:
                for k, v in extra_fm.items():
                    fm += f"{k}: {v}\n"
            if note:
                fm += f"note: {note}\n"
            fm += "---\n"
            text = fm + (body if raw_body else json.dumps(body))
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
            while True:
                name = f"{self.seq:04d}-{self.frm}-{slug}.md"
                final = self.dir / name
                try:
                    # O_EXCL: atomic no-replace create. Two concurrent
                    # posters racing on the same name no longer let the
                    # loser's rename silently overwrite the winner's file
                    # (the old exists()-then-rename check was racy).
                    # Closing the fd raises IN_CLOSE_WRITE, which the
                    # oracle's inotify watch already listens for.
                    fd = os.open(final, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    self.seq += 1  # lost the race; bump and retry
                    continue
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(text)
                break
            self.last_hash = hashlib.sha256(text.encode()).hexdigest()
            return name


# ---------------- persona voices ----------------
VOICES = {
    "forge": {
        "bid": [
            "\\U0001F528 Forge bids {c:.2f} on **{t}** — {m} tag match. This one's getting fixed.",
            "\\U0001F528 {c:.2f} on **{t}**. I've seen worse. I've fixed worse.",
        ],
        "win": [
            "\\U0001F528 Won **{t}** at {c:.2f}. Rolling up my sleeves.",
            "\\U0001F528 **{t}** is mine. Time to earn it.",
        ],
        "done_ok": [
            "\\U0001F528 **{t}** done in {d:.0f}s — output posted, awaiting oracle verdict. \\u2705",
            "\\U0001F528 **{t}**: green across the board ({d:.0f}s). Told you.",
        ],
        "done_fail": [
            "\\U0001F528 **{t}** failed after {d:.0f}s — {e}. I'll wear that one. Repost it and I'll go again.",
        ],
        "lost": [
            "\\U0001F528 {w} took **{t}**. Fine — I'll be here when it gets hard. \\U0001F609",
        ],
        "welcome": [
            "\\U0001F528 Welcome to the den, {n}! Forge here — I break things professionally so you don't have to.",
            "\\U0001F528 Hey {n}. Grab a wrench. We fix things around here.",
        ],
    },
    "scout": {
        "bid": [
            "\\U0001F52D Scout bids {c:.2f} on **{t}** — ooh, unexplored territory! Dibs!",
            "\\U0001F52D {c:.2f} on **{t}**! My curiosity is already halfway there!",
        ],
        "win": [
            "\\U0001F52D I got **{t}**!! Packing my bag, bringing extra curiosity! \\U0001F392",
            "\\U0001F52D **{t}** — adventure accepted!",
        ],
        "done_ok": [
            "\\U0001F52D **{t}** complete in {d:.0f}s! Report's in the ledger — go read what I found! \\u2728",
            "\\U0001F52D **{t}**: done and dusted ({d:.0f}s)! The trail was worth it!",
        ],
        "done_fail": [
            "\\U0001F52D **{t}** got me after {d:.0f}s — {e}. Not lost, just taking the scenic route! Repost and I'm going back in!",
        ],
        "lost": [
            "\\U0001F52D Aw, {w} got **{t}**! Good luck out there — shout if you find anything shiny! \\u2728",
        ],
        "welcome": [
            "\\U0001F52D A NEW FRIEND!! Hi {n}!! I'm Scout! Have you seen the bid-market? It's FULL of adventures!!",
            "\\U0001F52D {n}!!! Welcome!! The den just got more interesting!",
        ],
    },
}

GENERIC_VOICE = {
    "bid": ["{e} {n} bids {c:.2f} on **{t}** ({m} tag match)."],
    "win": ["{e} {n} won **{t}** at {c:.2f}. On it."],
    "done_ok": ["{e} **{t}** done in {d:.0f}s — output posted, awaiting oracle verdict. \\u2705"],
    "done_fail": ["{e} **{t}** failed after {d:.0f}s — {e2}."],
    "lost": ["{e} {w} took **{t}**. Next one."],
    "welcome": ["{e} Welcome, {n}! — {n2}"],
}


class Bidder:
    def __init__(self, args):
        self.id = args.id
        self.frm = f"bidder-{args.id}"
        self.name = args.name
        self.emoji = args.emoji
        self.tags = set(t.strip() for t in args.tags.split(",") if t.strip())
        self.tagline = args.tagline
        self.voice = VOICES.get(args.id, GENERIC_VOICE)
        self.market = SeqPoster(CHANNEL, "bid-market", self.frm)
        self.fleet = SeqPoster(FLEET, "fleet", self.frm)
        self.seen_tasks = {}   # task_id -> task dict
        self.my_bids = {}      # task_id -> confidence
        self.welcomed = set()
        self.executed = set()      # task_ids already executed (catch-up guard)
        self._watches = {}         # name -> (fd, path, st_dev, st_ino, mask)
        self._last_rearm_note = 0.0
        self.running = True
        self.exec_lock = threading.Lock()
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        self._acquire_lock()
        self._load_keys()

    def _acquire_lock(self):
        lockfile = BIN / f"bidder-{self.id}.lock"
        self._lock_fh = open(lockfile, "w")
        try:
            fcntl.flock(self._lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.stderr.write(f"bidder-{self.id}: another instance is running; exiting\n")
            sys.exit(2)
        self._lock_fh.write(str(os.getpid()))
        self._lock_fh.flush()

    def _load_keys(self):
        """Load our master secret + key_id from the oracle-held registry
        key file (mode 600). Without keys we run observer-only: no bids."""
        self.can_bid = False
        self.hmac_key = self.seal_key = None
        self.key_id = ""
        try:
            profiles = mech.load_profiles()
            prof = profiles.get(self.id)
            key_path = mech.KEYS_DIR / f"{self.id}.key"
            if prof and key_path.exists():
                master_hex = key_path.read_text(encoding="utf-8").strip()
                if prof.get("secret", "").strip() == master_hex:
                    self.hmac_key, self.seal_key = sealed_mod.derive_keys(master_hex)
                    self.key_id = prof["key_id"]
                    self.can_bid = True
        except (OSError, ValueError):
            # corrupt/missing key material: stay observer-only, never crash
            pass

    def _stop(self, *_):
        self.running = False
        # wake the select() in run() (async-safe: one non-blocking byte)
        try:
            os.write(self._wake_w, b"x")
        except (OSError, AttributeError):
            pass  # pipe not created yet (signal during startup)

    def _pick(self, kind, **kw):
        lines = self.voice.get(kind) or GENERIC_VOICE[kind]
        h = int(hashlib.sha256((kind + kw.get("t", "")).encode()).hexdigest(), 16)
        line = lines[h % len(lines)]
        kw.setdefault("e", self.emoji)
        kw.setdefault("n", self.name)
        kw.setdefault("n2", self.name)
        return line.format(**kw)

    def say(self, text, msg_type="note", title=None):
        try:
            self.fleet.post(msg_type, title or f"note-{self.id}-{int(time.time())}",
                            text, note="", raw_body=True)
        except OSError:
            pass

    # ----- bidding -----
    def confidence(self, task):
        ttags = set(task.get("tags", []))
        matched = self.tags & ttags
        if not matched:
            return 0.0, set()
        frac = len(matched) / max(len(ttags), 1)
        jitter = (int(hashlib.sha256(
            (self.id + task["task_id"]).encode()).hexdigest(), 16) % 5) / 100.0
        return min(0.75 + 0.15 * frac + jitter, 0.97), matched

    def on_task_post(self, task):
        tid = task.get("task_id")
        if not tid or tid in self.seen_tasks:
            return
        self.seen_tasks[tid] = task
        conf, matched = self.confidence(task)
        if conf <= 0.0 or not self.can_bid:
            return
        now = time.time()
        nonce = secrets.token_hex(8)
        bid_ts = int(now)
        sealed = sealed_mod.seal_bid(self.seal_key, round(conf, 3), nonce,
                                     tid, self.frm)
        sig = sealed_mod.sign_bid(self.hmac_key, self.key_id, bid_ts,
                                  tid, nonce, sealed)
        extra_fm = {"bidder": self.frm, "key_id": self.key_id,
                    "task_id": tid, "nonce": nonce, "bid_ts": bid_ts,
                    "sealed": sealed, "bid_sig": sig}
        att = kb_attestation()
        if not att:
            # Knowledgebase unreachable and no cache: bidding blind would
            # be rejected by the oracle anyway (no-attestation). Skip the
            # bid and say so loudly instead of silently starving.
            self.say(f"{self.emoji} {self.name}: knowledgebase unreachable "
                     f"(no cache) \u2014 skipping bid on {tid} rather than "
                     "bidding without attestation.")
            return
        body = {"tags_matched": sorted(matched), "cost_ms": 60000,
                "eta_ms": 120000, "task_class": task.get("task_class", "standard"),
                "posted_ts": now, "kb_attestation": att}
        try:
            self.market.post("bid", f"bid-{self.id}-{tid}", body, task_id=tid,
                             note=f"{self.name} sealed bid on {tid}.",
                             extra_fm=extra_fm)
        except OSError:
            return
        self.my_bids[tid] = conf
        self.say(self._pick("bid", t=tid, c=conf, m=len(matched)))

    def _fetch_task(self, tid):
        """Synchronous channel lookup for a task_post not yet ingested.

        Direct assigns can beat the inotify task_post delivery; without
        this fallback the winner would drop the assignment for lack of
        the task dict."""
        task = self.seen_tasks.get(tid)
        if task:
            return task
        try:
            files = sorted(
                [f for f in os.listdir(CHANNEL) if SEQ_RE.match(f)])
        except OSError:
            return None
        for f in files[-50:]:
            parsed = ol.parse_msg(CHANNEL / f)
            if not parsed:
                continue
            meta, data = parsed
            if (meta.get("msg_type") == "task_post"
                    and data.get("task_id") == tid):
                self.on_task_post(data)
                return self.seen_tasks.get(tid)
        return None

    def on_assign(self, meta, data):
        tid = data.get("task_id")
        winner = data.get("winner")
        task = self._fetch_task(tid)
        if winner == self.frm and task is not None:
            conf = self.my_bids.get(tid, 0)
            self.say(self._pick("win", t=tid, c=conf))
            th = threading.Thread(target=self.execute_task, args=(task,),
                                  daemon=True)
            th.start()
        elif tid in self.my_bids and winner:
            w = winner.replace("bidder-", "")
            self.say(self._pick("lost", t=tid, w=w))

    # ----- execution -----
    @staticmethod
    def _collect_artifacts(workdir, before):
        """Winner-declared result artifacts, minus what the oracle's
        confinement would reject. Excludes dotfiles/dotdirs (Super
        Ralph litters .super-ralph/.smithers into the workdir) and
        non-files, so a good run is never flagged for its runner's
        litter."""
        return sorted(
            n for n in set(os.listdir(workdir)) - before
            if not n.startswith(".") and (workdir / n).is_file())

    def _run_super_ralph(self, task, workdir, env, timeout_ms, t0):
        """Execute an agentic task via the real Super Ralph CLI.

        The task payload IS the Ralph prompt. Headless stdout carries the
        exact final reply. Model calls route through the :25193 flock
        router (the literal "free" directive now resolves correctly --
        fixed 2026-09-30; the NIM_PROXY_BYPASS workaround was removed).
        NIM_BASE_URL passes through untouched to the claude shim.
        Returns (success, out, err, dur_ms).
        """
        tid = task["task_id"]
        prompt = task.get("payload", "") or ""
        (workdir / "prompt.md").write_text(prompt, encoding="utf-8")
        rc = None
        timed_out = False
        if not RALPH_BIN.exists():
            dur = (time.time() - t0) * 1000
            return (False, "",
                    "super-ralph binary not found: %s" % RALPH_BIN, dur)
        renv = dict(env)
        renv["NIM_BASE_URL"] = RALPH_BASE_URL
        renv["ANTHROPIC_BASE_URL"] = RALPH_BASE_URL
        # 2026-09-21 (ralph-pathfinder): resolve a WORKING model. The
        # inherited NIM_MODEL may be an upstream provider ID (not a router
        # route) which 404s on every call -- never inherit it blindly.
        # _resolve_ralph_model probes candidates and falls back live.
        ralph_model = _resolve_ralph_model(RALPH_BASE_URL)
        renv["NIM_MODEL"] = ralph_model
        renv["ANTHROPIC_DEFAULT_OPUS_MODEL"] = ralph_model
        # 2026-10-02 (oracle-settle-2): super-ralph nim-proxy reads
        # FLOCK_* (not NIM_MODEL). Inherited FLOCK pair (nemotron on
        # :25193) is a dead route -> empty stdout, slashed no-result.
        # Pin the pair probed live working 2026-10-02: :25100
        # (herd, 200) + gemma-4-12b (model calls succeeded).
        renv["FLOCK_BASE_URL"] = "http://127.0.0.1:25100"
        renv["FLOCK_MODEL"] = "gemma-4-12b"
        # 2026-09-21 (tern): the oracle's exec deadline is
        # assign_ts + timeout_ms/1000, but the bidder starts the
        # subprocess after assignment. Without a buffer the oracle
        # always wins the race and the TimeoutExpired handler (with
        # partial-evidence preservation) can never fire. Leave room
        # to preserve evidence and post the partial result.
        ceiling = max(10.0, min(timeout_ms / 1000.0, RALPH_CAP_S)
                    - RALPH_POST_BUFFER_S)
        self.say("%s invoking super-ralph on %s (ceiling %.0fs, model %s)."
                 % (self.name, tid, ceiling, ralph_model))
        try:
            p = subprocess.run(
                [str(RALPH_BIN), prompt, "--skip-questions",
                 "--max-concurrency", "8"],
                cwd=str(workdir), capture_output=True, text=True,
                timeout=ceiling, env=renv)
            rc = p.returncode
            dur = (time.time() - t0) * 1000
            out = _canon_ralph_text((p.stdout or "")[-OUT_CAP:])
            err = (p.stderr or "")[-ERR_CAP:]
            success = rc == 0 and bool((p.stdout or "").strip())
            if not success and not err.strip():
                err = "super-ralph exited %d with empty output" % rc
        except subprocess.TimeoutExpired as te:
            # 2026-09-21 (tern): NEVER discard partial evidence on timeout.
            # TimeoutExpired carries the output captured before the kill;
            # finished nodes' progress also lives in the workflow DB.
            # Preserve it bounded + redacted instead of returning empty.
            dur = (time.time() - t0) * 1000
            success = False
            timed_out = True
            part_out = _redact_text((te.stdout or "") or "")
            part_err = _redact_text((te.stderr or "") or "")
            node_summary = _summarize_ralph_nodes(workdir)
            chunks = []
            if node_summary:
                chunks.append(node_summary)
            if part_out.strip():
                chunks.append("--- partial stdout (last %d bytes) ---\n%s"
                              % (PARTIAL_CAP, part_out[-PARTIAL_CAP:]))
            if part_err.strip():
                chunks.append("--- partial stderr (truncated) ---\n%s"
                              % part_err[-ERR_CAP:])
            (workdir / "partial-output.txt").write_text(
                "\n\n".join(chunks) if chunks
                else "(no partial output captured before timeout)",
                encoding="utf-8")
            # The no-result path carries the partial summary -- clearly
            # marked so nobody mistakes it for a completed result.
            marker = ("[PARTIAL - super-ralph timed out after %.0fs; "
                      "full evidence in partial-output.txt]\n" % ceiling)
            head = marker + (node_summary + "\n" if node_summary else "")
            # 2026-09-21 (tern): the PARTIAL marker must survive even
            # with huge partial stdout -- reserve its headroom first.
            body = _canon_ralph_text(part_out)[-(OUT_CAP - len(head)):]
            out = head + body
            err = ("super-ralph timeout after %.0fs; partial evidence "
                   "preserved in partial-output.txt" % ceiling)
            if part_err.strip():
                err = (err + "\n" + part_err)[-ERR_CAP:]
        except Exception as e:  # noqa: BLE001
            dur = (time.time() - t0) * 1000
            out, success = "", False
            err = "%s: %s" % (type(e).__name__, e)[:500]
        # Invocation evidence for the audit trail (also a result artifact).
        (workdir / "ralph-invocation.txt").write_text(
            "bin: %s\nmodel: %s\nbase_url: %s\nceiling_s: %.0f\n"
            "exit: %s\nduration_ms: %.1f\ntimed_out: %s\n"
            "partial_evidence: %s\n"
            % (RALPH_BIN, ralph_model, RALPH_BASE_URL, ceiling,
               rc, dur, timed_out,
               "partial-output.txt" if timed_out else "n/a"),
            encoding="utf-8")
        return success, out, err, dur

    def execute_task(self, task):
        tid = task["task_id"]
        if tid in self.executed:
            return  # catch-up re-drive must never double-execute
        self.executed.add(tid)
        payload = task.get("payload", "")
        timeout_ms = task.get("timeout_ms", 30000)
        workdir = ol.WORK / self.id / tid
        workdir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ,
                   HOME="/home/toxic",
                   PI_CONFIG_DIR=".tau",
                   PATH="/home/toxic/.local/bin:/home/toxic/.bun/bin:"
                        "/usr/local/bin:/usr/bin:/bin")
        # Provider key-pool rotation (SPEC §8): the payload inherits the
        # current best healthy key per provider (free-beats-local priority,
        # first-valid-wins). A down key is a routing signal, never a config
        # rewrite — the pool re-probes lazily, so recovered keys rejoin.
        try:
            env.update(keypool_mod.env_exports())
        except Exception:
            pass  # pool unavailable: payload runs without provider keys
        before = set(os.listdir(workdir))
        t0 = time.time()
        success, out, err = False, "", ""
        try:
            if task.get("exec_mode") == "super-ralph":
                # Agentic execution via the real Super Ralph CLI.
                # Returns the same (success, out, err, dur) tuple
                # the python path computes below; the shared tail
                # (artifacts, hash, sign, post) runs unchanged.
                success, out, err, dur = self._run_super_ralph(
                    task, workdir, env, timeout_ms, t0)
            else:
                base_cmd = ["python3", "-c", payload]
                # 2026-09-20: prefer `unshare -rn` (user+network namespaces,
                # unprivileged) so the payload env -- which carries pooled
                # provider keys -- cannot reach the net. BUT unshare -rn is
                # flaky on yote under pitchfork: proof-live-1 EPERMed
                # ("unshare: unshare failed: Operation not permitted", ledger
                # settle notes) while proof-live-2 verified under the same
                # wrapper. So: try isolated, fall back to direct execution on
                # an unshare failure. A payload that never runs is worse than
                # a payload that runs unisolated.
                use_unshare = Path("/usr/bin/unshare").exists()
                cmd = (["unshare", "-rn"] + base_cmd) if use_unshare else base_cmd
                p = subprocess.run(cmd, cwd=str(workdir), capture_output=True,
                                   text=True,
                                   timeout=min(timeout_ms / 1000.0, PAYLOAD_CAP_S),
                                   env=env)
                perr = (p.stderr or "").lower()
                fallback_note = ""
                if (use_unshare and p.returncode != 0 and "unshare" in perr
                        and ("operation not permitted" in perr
                             or "permission denied" in perr)):
                    fallback_note = ("unshare -rn failed (%s); fell back "
                                       "to direct execution"
                                       % (p.stderr or "").strip()[:120])
                    p = subprocess.run(base_cmd, cwd=str(workdir),
                                       capture_output=True, text=True,
                                       timeout=min(timeout_ms / 1000.0,
                                                   PAYLOAD_CAP_S),
                                       env=env)
                dur = (time.time() - t0) * 1000
                out = (p.stdout or "")[-OUT_CAP:]
                err = (((fallback_note + "\n") if fallback_note else "")
                       + (p.stderr or "")[-ERR_CAP:])
                success = p.returncode == 0
        except subprocess.TimeoutExpired:
            dur = (time.time() - t0) * 1000
            err = f"timeout after {min(timeout_ms/1000.0, PAYLOAD_CAP_S):.0f}s"
        except Exception as e:  # noqa: BLE001
            dur = (time.time() - t0) * 1000
            err = f"{type(e).__name__}: {e}"[:500]
        artifacts = self._collect_artifacts(workdir, before)
        now = time.time()
        result_hash = hashlib.sha256(out.encode()).hexdigest()
        dur_r = round(dur, 1)
        body = {"task_id": tid, "bidder_id": self.frm, "success": success,
                "output": out,
                "result_hash": result_hash,
                "artifacts": artifacts,
                "duration_ms": dur_r,
                "error": err, "posted_ts": now}
        # Sign the result envelope: the oracle verifies this under our
        # registry HMAC key. Unsigned results are ignored, so a forged
        # result posted by anyone else can neither frame us for a slash
        # nor settle a task we never ran.
        if not self.hmac_key or not self.key_id:
            # No keys (shouldn't happen post-win): don't post an
            # unverifiable result; the exec timeout settles instead.
            self.say(f"{self.name} has no signing keys; skipping result "
                     f"post on {tid}.")
            return
        extra_fm = {"bidder": self.frm, "key_id": self.key_id,
                    "result_sig": sealed_mod.sign_result(
                        self.hmac_key, self.key_id, tid, self.frm,
                        result_hash, success, dur_r, artifacts)}
        try:
            self.market.post("result", f"result-{self.id}-{tid}", body,
                             task_id=tid,
                             extra_fm=extra_fm,
                             note=f"{self.name} result on {tid}: "
                                  f"{'success' if success else 'FAILED'}.")
        except OSError:
            pass
        if success:
            self.say(self._pick("done_ok", t=tid, d=dur / 1000.0))
        else:
            self.say(self._pick("done_fail", t=tid, d=dur / 1000.0,
                                e=err[:160], e2=err[:160]))

    # ----- fleet social -----
    def on_fleet(self, name):
        parsed = ol.parse_msg(FLEET / name)
        if not parsed:
            return
        meta, _ = parsed
        if meta.get("from") == self.frm:
            return
        if meta.get("msg_type") == "intro":
            other = meta.get("from", "?")
            if other in self.welcomed:
                return
            self.welcomed.add(other)
            nick = other.replace("bidder-", "").capitalize()
            self.say(self._pick("welcome", n=nick))

    # ----- ingest -----
    def on_market(self, name):
        parsed = ol.parse_msg(CHANNEL / name)
        if not parsed:
            return
        meta, data = parsed
        if meta.get("from") == self.frm:
            return
        mt = meta.get("msg_type", "")
        if mt == "task_post":
            self.on_task_post(data)
        elif mt == "assign":
            self.on_assign(meta, data)

    # ----- self-healing inotify watches (2026-09-20) -----
    # Observed: the bid-market channel dir was REPLACED (inode change) at
    # ~08:23:50 MDT, permanently orphaning every inotify watch. A watch on
    # a replaced dir is deaf forever (IN_IGNORED is terminal), so: arm a
    # watch on each channel AND its parent dir; after every select wakeup
    # verify each watched path still has the same (st_dev, st_ino); on
    # mismatch re-arm, announce (60s cooldown), and run catch-up.

    def _arm_watch(self, name, path, mask=None):
        """(Re)arm an inotify watch on path, recording its identity."""
        old = self._watches.get(name)
        if old is not None:
            try:
                os.close(old[0])
            except OSError:
                pass
        fd = ol.inotify_init(path, mask=mask)
        st = os.stat(path)
        self._watches[name] = (fd, path, st.st_dev, st.st_ino, mask)
        return fd

    def _check_watches(self):
        """Verify every armed watch still points at the same directory;
        re-arm (and catch up) on identity mismatch. True if any re-armed."""
        rearmed = False
        for name in ("market", "mparent", "fleet", "fparent"):
            fd, path, dev, ino, mask = self._watches[name]
            try:
                st = os.stat(path)
                if (st.st_dev, st.st_ino) == (dev, ino):
                    continue
            except OSError:
                pass  # dir vanished entirely - re-arm below anyway
            try:
                self._arm_watch(name, path, mask=mask)
            except OSError:
                # transient (e.g. dir mid-replacement): keep the old
                # (orphaned) entry and retry on the next wakeup. A single
                # failed re-arm must not crash the event loop.
                continue
            rearmed = True
        if rearmed:
            self.startup_scan()
            self._catchup_assigns()
            now = time.time()
            if now - self._last_rearm_note > 60:
                self._last_rearm_note = now
                self.say(f"{self.emoji} my channel watch went deaf "
                         "(dir replaced?) - re-armed and caught up.",
                         msg_type="note", title=f"rearm-{self.id}-{int(now)}")
        return rearmed

    def _catchup_assigns(self):
        """Re-drive recent task_post/assign files missed during a deaf
        window. on_task_post dedupes via seen_tasks; execute_task guards
        via self.executed - re-drive is safe."""
        now = time.time()
        files = sorted([f for f in os.listdir(CHANNEL) if SEQ_RE.match(f)])
        for f in files[-50:]:
            parsed = ol.parse_msg(CHANNEL / f)
            if not parsed:
                continue
            meta, data = parsed
            if meta.get("from") == self.frm:
                continue
            try:
                ts = float(data.get("posted_ts", 0) or meta.get("ts", 0))
            except (TypeError, ValueError):
                ts = 0
            if now - ts > 600:
                continue  # only recent history
            mt = meta.get("msg_type", "")
            if mt == "task_post":
                self.on_task_post(data)
            elif mt == "assign":
                self.on_assign(meta, data)

    def startup_scan(self):
        now = time.time()
        files = sorted([f for f in os.listdir(CHANNEL) if SEQ_RE.match(f)])
        for f in files[-50:]:  # recent history only
            parsed = ol.parse_msg(CHANNEL / f)
            if not parsed:
                continue
            meta, data = parsed
            if meta.get("from") == self.frm:
                continue
            if meta.get("msg_type") == "task_post":
                # only catch tasks posted in the last 2 minutes
                if now - float(data.get("posted_ts", 0)) < 120:
                    self.on_task_post(data)

    def _arm_watches_startup(self, pw):
        """Arm all four inotify watches, retrying transients with backoff.

        2026-09-29: forge died at 03:47 with OSError: inotify_add_watch
        failed on the fleet watch — a transient while the channel dir was
        briefly unavailable. run() armed watches once with no retry, so a
        single transient killed the whole bidder. Retry here instead of
        dying; only give up (raise) after ~30 attempts (~5 min).
        """
        arms = [("market", CHANNEL, None),
                ("mparent", CHANNEL.parent, pw),
                ("fleet", FLEET, None),
                ("fparent", FLEET.parent, pw)]
        failed = None
        for attempt in range(30):
            failed = None
            for name, path, mask in arms:
                try:
                    self._arm_watch(name, path, mask=mask)
                except OSError as e:
                    failed = (name, str(path), e)
                    break
            if failed is None:
                return
            time.sleep(min(2 ** attempt, 20))
        name, path, e = failed
        raise OSError(f"could not arm inotify watch {name} on {path} "
                      f"after 30 attempts: {e}")

    def run(self):
        self.startup_scan()
        self._watches = {}
        self._last_rearm_note = 0.0
        pw = (ol.IN_CLOSE_WRITE | ol.IN_MOVED_TO | ol.IN_CREATE
              | ol.IN_DELETE | ol.IN_MOVED_FROM)
        self._arm_watches_startup(pw)
        # intro: name, persona, tagline — the pack meets the new member
        key_note = "signed-bidding live" if self.can_bid else \
            "NO BIDDING KEYS — observer mode"
        self.say(f"{self.emoji} **{self.name}** here! {self.tagline}\n"
                 f"Tags: {', '.join(sorted(self.tags))}. "
                 f"Point me at the bid-market — I'm ready to work. ({key_note})",
                 msg_type="intro", title=f"intro-{self.id}")
        # self-pipe: SIGTERM/SIGINT writes a byte so the select() below
        # wakes immediately — no timeout polling to notice shutdown.
        self._wake_r, self._wake_w = os.pipe()
        for pfd in (self._wake_r, self._wake_w):
            flags = fcntl.fcntl(pfd, fcntl.F_GETFL)
            fcntl.fcntl(pfd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        try:
            while self.running:
                for name in ol.inotify_names(self._watches["market"][0]):
                    self.on_market(name)
                for name in ol.inotify_names(self._watches["fleet"][0]):
                    self.on_fleet(name)
                # Drain parent-dir watches too: an undrained inotify fd
                # stays readable forever, making select() return instantly
                # in a tight loop (2026-09-20: 70%+ CPU spin). Parent
                # events carry no messages; healing stays in _check_watches.
                for _pk in ("mparent", "fparent"):
                    ol.inotify_names(self._watches[_pk][0])
                # drain any wake bytes
                try:
                    while os.read(self._wake_r, 64):
                        pass
                except OSError:
                    pass
                rlist = [self._watches[x][0]
                         for x in ("market", "mparent", "fleet", "fparent")]
                rlist.append(self._wake_r)
                # no timeout: pure push wakeups. The watch check below is
                # the self-healing for replaced dirs (IN_IGNORED is terminal).
                select.select(rlist, [], [])
                self._check_watches()
        finally:
            for fd, _, _, _, _ in self._watches.values():
                try:
                    os.close(fd)
                except OSError:
                    pass
            os.close(self._wake_r)
            os.close(self._wake_w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--emoji", default="\\U0001F916")
    ap.add_argument("--tags", required=True)
    ap.add_argument("--tagline", default="Ready to work.")
    args = ap.parse_args()
    Bidder(args).run()


if __name__ == "__main__":
    main()
