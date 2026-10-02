#!/usr/bin/env python3
"""
oracle-market: event-driven auctioneer loop for the Squawk bid-market.

Watches the bid-market channel dir via inotify (ctypes, stdlib-only).
Deadline wakeups via select() timeout. No polling, no artificial sleeps.

Mechanism (SPEC.md): HMAC-signed bidder profiles (§1) via bin/sealed.py,
Vickrey second-price sealed-bid clearing (§2), stake/slash + ledger-derived
reputation (§3) via bin/mechanism.py. Key separation: HKDF derives distinct
HMAC and AES-GCM keys from each bidder's master secret (never shared).

Message files: NNNN-<from>-<slug>.md
  frontmatter: seq, from, to, msg_type, task_id, channel, ts, status, title,
               lamport, parents, [note]
    bid frontmatter additionally (SPEC §1.2): bidder, key_id, nonce, bid_ts,
               sealed (base64 AES-GCM), bid_sig (hex HMAC-SHA256)
  body: JSON (non-secret bid metadata: tags_matched, cost_ms, eta_ms, class)
  msg_type: task_post | bid | assign | result | reject | no_assign | settle

Auction lifecycle per task:
  task_post -> OPEN (collect bids until posted_ts + bid_window_ms)
  deadline  -> Vickrey clear: highest sealed amount wins, pays
               max(second_highest, reserve) -> assign (+ stake lock)
  assign    -> ASSIGNED (wait for winner's result until timeout_ms)
  result    -> verify (success, duration, artifact hash) -> settle -> CLOSED
               verified: bond released + reward + rep bump
               failed/timeout: bond slashed (objective triggers only)
  exec timeout with no result -> settle FAILED, slash full bond.
               There is NO oracle fallback execution: running arbitrary
               task-post payloads as the oracle was removed 2026-09-20.

Startup (REPLAY-SAFE): the loop reconstructs state from the ledger and
oracle-authored channel history and NEVER re-publishes history. Only
auctions that are genuinely still open are resumed; assigned-but-unsettled
ones get their timers restored without re-publishing the assign; expired
historical auctions are marked closed in memory with a replay_closed log.
A single-instance flock guarantees no two loops ever run at once, which
is the root-cause fix for duplicate seq allocation.
"""
import ctypes
import fcntl
import hashlib
import heapq
import json
import os
import re
import select
import signal
import struct
import sys
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import sealed as sealed_mod          # noqa: E402
import mechanism as mech            # noqa: E402

AGENT_DIR = BIN.parent
# All paths are env-overridable: the staged defaults are hatch-local and MUST
# be set to the yote squawk-root paths on deploy (see RESUME.md). Deploying
# with the defaults on yote watches a nonexistent dir and crashes on startup.
CHANNEL = Path(os.environ.get("ORACLE_CHANNEL",
    "/home/toxic/estate/hatch/agents/ember/squawk-root/bid-market"))
FLEET = Path(os.environ.get("ORACLE_FLEET",
    "/home/toxic/.fleet-bus/squawk-root/fleet"))
WORK = Path(os.environ.get("ORACLE_WORK", str(AGENT_DIR / "work")))
LEDGER = Path(os.environ.get("ORACLE_LEDGER",
                             str(AGENT_DIR / "ledger" / "ledger.jsonl")))
LOCKFILE = Path(os.environ.get("ORACLE_LOCK", str(AGENT_DIR / "oracle.lock")))
BACKLOG = Path(os.environ.get("ORACLE_BACKLOG", str(WORK / "task-backlog.jsonl")))

FROM = "oracle-market"
SELF_FROMS = {"oracle-market", "oracle"}  # "oracle" = legacy identity (history only)
# Control-plane messages (task_post, assign) carry an HMAC under the
# dedicated control key (SPEC §1.5) — the frontmatter `from:` field is a
# string anyone can spoof, so it is never trusted for control messages.
# The old TRUSTED_POSTERS={"ember"} string match is gone: trust is in the
# signature, not the name.
RESERVE = 0.35          # minimum winning amount; below -> no_assign
BID_SKEW_S = 2.0        # accept bids this far past deadline (clock skew)
OUT_CAP = 65536         # captured output cap (informational; oracle never executes)

# Debate chase rule (fleet mechanism, SPEC §9): debates settle at quorum
# (>=2 replies) or at the hard deadline with a recorded chase.
DEBATE_SOFT_MS = 30 * 60 * 1000    # chase (re-nudge) when <2 replies
DEBATE_HARD_MS = 4 * 3600 * 1000   # hard settle (always > soft)
DEBATE_QUORUM = 2                 # replies needed for a quorum settle
KB_SHA_RE = re.compile(r"^[0-9a-f]{40}$")  # knowledgebase commit SHA

# Agentic execution (2026-09-21, oracle-repair): intake TASK/RESEARCH/DIRECT
# requests become Super Ralph prompts (exec_mode="super-ralph") executed by
# the winning bidder. The oracle never executes payloads; it only verifies.
AGENTIC_TIMEOUT_MS = 30 * 60 * 1000   # Super Ralph runs are slow (~11 min
                                      # observed for a trivial run)
AGENTIC_BID_WINDOW_MS = 15000
ACCEPT_REPORT_MARKER = "ACCEPTANCE-REPORT:"

# ---------------- inotify (ctypes, stdlib only) ----------------
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_MOVED_FROM = 0x00000040
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.inotify_init1.argtypes = [ctypes.c_int]
_libc.inotify_init1.restype = ctypes.c_int
_libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
_libc.inotify_add_watch.restype = ctypes.c_int


def inotify_init(path, mask=None):
    """Arm an inotify watch on path. mask defaults to the channel mask
    (IN_CLOSE_WRITE | IN_MOVED_TO); parent-dir watches pass a wider mask
    so dir replacement (delete/recreate) also wakes the select loop.
    (2026-09-20: wider mask + optional param for self-healing watches.)"""
    if mask is None:
        mask = IN_CLOSE_WRITE | IN_MOVED_TO
    fd = _libc.inotify_init1(0)
    if fd < 0:
        raise OSError("inotify_init1 failed")
    wd = _libc.inotify_add_watch(fd, str(path).encode(), mask)
    if wd < 0:
        raise OSError("inotify_add_watch failed")
    return fd


def inotify_names(fd):
    """Non-blocking drain; returns list of filenames with close_write/moved_to."""
    out = []
    while True:
        r, _, _ = select.select([fd], [], [], 0)
        if not r:
            break
        data = os.read(fd, 65536)
        i = 0
        while i + 16 <= len(data):
            wd, mask, cookie, ln = struct.unpack("iIII", data[i:i + 16])
            name = data[i + 16:i + 16 + ln].split(b"\0", 1)[0].decode("utf-8", "replace")
            i += 16 + ln
            if mask & (IN_CLOSE_WRITE | IN_MOVED_TO) and name.endswith(".md"):
                out.append(name)
    return out


# ---------------- message IO ----------------
SEQ_RE = re.compile(r"^(\d+)-")


def parse_msg(path):
    """Returns (frontmatter dict, body) or None."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    fm, body = parts[1], parts[2]
    meta = {}
    for line in fm.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    body = body.strip()
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {"_raw": body}
    return meta, data


class Poster:
    """Atomic message writer for one channel dir.

    Refreshes seq from the directory on every post and bumps past
    collisions, so the oracle and bidders can share a channel safely.
    (Seq races were previously caused by duplicate loop instances; the
    single-instance flock is the root-cause fix, this is belt-and-braces.)
    """

    def __init__(self, channel_dir, channel_name):
        self.dir = Path(channel_dir)
        self.channel = channel_name
        self.lamport = 0
        self.last_hash = ""

    def _refresh(self):
        files = [f for f in os.listdir(self.dir) if SEQ_RE.match(f)]
        self.seq = max([int(SEQ_RE.match(f).group(1)) for f in files] or [0])
        if files:
            latest = sorted(files)[-1]
            parsed = parse_msg(self.dir / latest)
            if parsed:
                meta, _ = parsed
                try:
                    self.lamport = int(meta.get("lamport", 0))
                except ValueError:
                    pass
                self.last_hash = hashlib.sha256(
                    (self.dir / latest).read_bytes()).hexdigest()

    def post(self, msg_type, title, body, task_id="", note="", frm=FROM,
             to="all", raw_body=False, extra_fm=None):
        self._refresh()
        self.seq += 1
        self.lamport += 1
        parents = [self.last_hash] if self.last_hash else []
        ts = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
        fm = (
            f"---\nseq: {self.seq}\nfrom: {frm}\nto: {to}\n"
            f"msg_type: {msg_type}\ntask_id: {task_id}\n"
            f"channel: {self.channel}\nts: {ts}\nstatus: {self.channel}\n"
            f"title: {title}\nlamport: {self.lamport}\nparents: {json.dumps(parents)}\n"
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
            name = f"{self.seq:04d}-{frm}-{slug}.md"
            final = self.dir / name
            try:
                # O_EXCL: atomic no-replace create (see bidder.py SeqPoster
                # for why the old exists()-then-rename was racy). Close
                # raises IN_CLOSE_WRITE, which our inotify watch listens for.
                fd = os.open(final, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                self.seq += 1  # lost the race; bump and retry
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            break
        self.last_hash = hashlib.sha256(text.encode()).hexdigest()
        return name


# ---------------- single instance ----------------
def acquire_lock():
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOCKFILE, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.stderr.write("oracle-market: another instance holds the lock; exiting\n")
        sys.exit(2)
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


# ---------------- auction state ----------------
def _fnum(v, default):
    """Coerce to float; a hostile/malformed message must never crash the loop."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class Auction:
    def __init__(self, task):
        self.task = task
        self.task_id = task["task_id"]
        self.tags = set(task.get("tags", []))
        self.task_class = task.get("task_class", "standard")
        self.deadline = (_fnum(task.get("posted_ts"), time.time())
                         + _fnum(task.get("bid_window_ms"), 8000) / 1000.0)
        self.timeout_ms = _fnum(task.get("timeout_ms"), 30000)
        self.bids = {}          # bidder_id -> bid dict (amount decrypted)
        self.state = "OPEN"     # OPEN -> ASSIGNED -> CLOSED
        self.winner = None
        self.price_paid = None
        self.assign_ts = None


class Debate:
    """Debate chase rule (SPEC §9): a debate settles only at quorum
    (>=2 distinct replies) or at the hard deadline with the chase
    recorded. States: OPEN -> CHASED -> SETTLED."""

    def __init__(self, debate_id, question, opener, wanted, soft_ms,
                 hard_ms, opened_ts=None, kind="debate"):
        self.debate_id = debate_id
        self.question = question
        self.opener = opener
        self.wanted = list(wanted)
        self.kind = kind        # "debate" | "petition"
        self.request = question  # petitions: the upgrade request text
        self.replies = {}       # from -> ts
        self.evidence = {}      # from -> reply text (substance, not names)
        self.state = "OPEN"
        self.chased = False
        now = opened_ts or time.time()
        self.opened_ts = now
        self.soft_ts = now + max(1, int(soft_ms or DEBATE_SOFT_MS)) / 1000.0
        self.hard_ts = now + max(1, int(hard_ms or DEBATE_HARD_MS)) / 1000.0
        if self.hard_ts <= self.soft_ts:
            self.hard_ts = self.soft_ts + 60.0


def _parse_acceptance_report(output):
    """Parse the ACCEPTANCE-REPORT section from a result's output.

    Returns (found, all_met, items) where items is a list of
    (criterion, met, note). Tolerant: the section starts at a line whose
    stripped text is ACCEPTANCE-REPORT: (case-insensitive); following
    dash-led lines are items. The oracle parses the SIGNED output itself
    -- the winner's word is the output text, hash-bound to its signature,
    so no separate bidder-supplied field is trusted.
    """
    # Tolerate producers that emit literal "\n" escapes instead of
    # real newlines (observed from Super Ralph headless stdout). The
    # bidder canonicalizes before posting; this is belt-and-braces.
    if output and "\\n" in output and "\n" not in output:
        output = output.replace("\\r\\n", "\n").replace("\\n", "\n")
    items = []
    found = False
    for line in (output or "").splitlines():
        s = line.strip()
        if not found:
            if s.upper() == ACCEPT_REPORT_MARKER:
                found = True
            continue
        if not s.startswith("-"):
            if s:  # non-item, non-empty line ends the section
                break
            continue
        body = s[1:].strip()
        m = re.match(r"(.+?)\s*:\s*(MET|UNMET|NOT MET|NOT-MET)\b\s*-?\s*(.*)$",
                     body, re.I)
        if m:
            crit, status, note = m.group(1), m.group(2).upper(), m.group(3)
            met = (status == "MET")
        else:
            crit, note = body, ""
            up = body.upper()
            met = ("MET" in up and "UNMET" not in up
                   and "NOT MET" not in up and "NOT-MET" not in up)
        items.append((crit.strip()[:200], met, note.strip()[:200]))
    all_met = bool(items) and all(m for _, m, _ in items)
    return found, all_met, items


class OracleLoop:
    def __init__(self):
        WORK.mkdir(parents=True, exist_ok=True)
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        self.lock_fh = acquire_lock()
        self.market = Poster(CHANNEL, "bid-market")
        self.fleet = Poster(FLEET, "fleet")
        self.auctions = {}
        self.done = set()       # task_ids terminally published this run
        self.timers = []        # heap of (ts, kind, task_id)
        self.debates = {}       # debate_id -> Debate (chase rule)
        self.debate_req_seen = set()  # fingerprints of opened debates
        self.attestation_gate_ts = 0.0  # set in reconstruct()
        self.running = True
        self._watch = None       # (fd, path, st_dev, st_ino, mask)
        self._pwatch = None      # parent-dir watch, same shape
        self._last_rearm_note = 0.0
        self.profiles = mech.load_profiles()
        self.rep = mech.reputation(LEDGER)
        # Control-plane HMAC key (SPEC §1.5): derived from the oracle-held
        # control master via HKDF domain separation (SPEC §2.1). The oracle
        # is the custodian and creates the master on first start.
        ctl_master = mech.ensure_control_key()
        self.ctl_hmac_key = sealed_mod.hkdf(
            bytes.fromhex(ctl_master), sealed_mod.CTL_INFO)
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)

    def _stop(self, *_):
        self.running = False
        # wake the select() in run(): signal handlers must be async-safe,
        # so write one byte to the self-pipe (non-blocking, best effort).
        try:
            os.write(self._wake_w, b"x")
        except (OSError, AttributeError):
            pass  # pipe not created yet (signal during startup)

    def log(self, event, **kw):
        kw.update({"event": event, "ts": time.time()})
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(kw) + "\n")

    def fleet_note(self, text):
        """Fleet narration as oracle-market, markdown body, single write."""
        try:
            self.fleet.post("note", f"oracle-{int(time.time())}", text,
                            frm=FROM, raw_body=True)
        except OSError:
            pass

    def _control_ok(self, meta, data, msg_type):
        """Control-plane authentication (SPEC §1.5): task_post and assign
        are valid only with a fresh HMAC under the control key. The `from:`
        frontmatter field is never consulted — it is spoofable."""
        tid = meta.get("task_id") or data.get("task_id") or ""
        return sealed_mod.verify_control(
            self.ctl_hmac_key, msg_type, tid,
            sealed_mod.ctl_body_sha256(data),
            meta.get("ctl_ts", ""), meta.get("ctl_sig", ""),
            time.time())

    # ----- signed-bid verification (SPEC §1.3) -----
    def verify_bid_envelope(self, meta, tid):
        key_id = meta.get("key_id", "")
        profile = mech.profile_by_key_id(self.profiles, key_id)
        if not profile:
            return None, "unknown_key"
        try:
            hmac_key, seal_key = sealed_mod.derive_keys(profile["secret"])
        except (ValueError, KeyError):
            return None, "bad-profile"
        now = time.time()
        reason = sealed_mod.verify_envelope(
            hmac_key, key_id, meta.get("bid_ts"), tid, meta.get("nonce", ""),
            meta.get("sealed", ""), meta.get("bid_sig", ""), now)
        if reason:
            return None, reason
        try:
            inner = sealed_mod.unseal_bid(seal_key, meta.get("sealed", ""), tid)
        except Exception:
            return None, "seal-fail"
        # binding check (SPEC §2.1): sealed fields must match the envelope
        if (inner.get("task_id") != tid
                or inner.get("nonce") != meta.get("nonce")
                or inner.get("bidder_id") != meta.get("bidder")):
            return None, "tamper"
        try:
            amount = float(inner.get("amount"))
            if not (0.0 <= amount <= 1.0):
                return None, "bad-amount"
        except (TypeError, ValueError):
            return None, "bad-amount"
        return {"amount": amount, "nonce": inner["nonce"],
                "bidder_id": inner["bidder_id"]}, None

    # ----- auction ops -----
    def open_auction(self, task, replay=False):
        tid = task.get("task_id")
        if not tid or tid in self.auctions or tid in self.done:
            return None
        a = Auction(task)
        self.auctions[tid] = a
        heapq.heappush(self.timers, (a.deadline, "bid_close", tid))
        self.log("task_open", task_id=tid, title=task.get("title"),
                 deadline=a.deadline, tags=sorted(a.tags),
                 task_class=a.task_class, replay=replay)
        return a

    # ----- intake task construction (agentic execution) ---------------
    @staticmethod
    def _safe_frm(name):
        return re.sub(r"[^A-Za-z0-9_-]", "-", str(name))[:40] or "intake"

    @staticmethod
    def _research_tags(text):
        try:
            from oracle_intake import _tags_for
            tags = _tags_for(text)
        except ImportError:
            tags = ["probe"]
        return sorted(set(tags) | {"research"})

    def _post_signed_task(self, body, tid, frm, note):
        """Publish a control-signed task_post (SPEC 1.5)."""
        ctl_ts = int(time.time())
        ctl_sig = sealed_mod.sign_control(
            self.ctl_hmac_key, "task_post", tid,
            sealed_mod.ctl_body_sha256(body), ctl_ts)
        canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
        self.market.post("task_post", "task-%s" % tid, canon,
                         task_id=tid, raw_body=True, frm=frm,
                         extra_fm={"ctl_sig": ctl_sig, "ctl_ts": ctl_ts},
                         note=note)

    def _acceptance_for(self, request_text):
        req = (request_text or "").strip()[:300].replace("\n", " ")
        return (
            "1. The request is fully addressed: \"%s\".\n"
            "2. Result output is non-empty and summarizes what was done.\n"
            "3. Deliverable files (if any) are written to the task workdir "
            "and listed as result artifacts.\n"
            "4. The final reply ends with an ACCEPTANCE-REPORT: section, "
            "one '- <criterion>: MET - <evidence>' line per criterion "
            "above (UNMET + reason if one fails)." % req)

    def _agentic_prompt(self, tid, request_text, requester, acceptance):
        return (
            "# Oracle task %s (from %s)\n\n"
            "## Request\n%s\n\n"
            "## Acceptance criteria\n%s\n\n"
            "## Instructions\n"
            "Do the request above as real work. Write any deliverable files "
            "into the current working directory. This run is "
            "non-interactive: do not ask questions. Your final reply must "
            "summarize the outcome against each acceptance criterion and "
            "MUST end with exactly this section:\n"
            "ACCEPTANCE-REPORT:\n"
            "- criterion 1: MET - <evidence>\n"
            "- criterion 2: MET - <evidence>\n"
            "(one line per criterion; write UNMET with a reason instead of "
            "MET if a criterion fails)" % (
                tid, requester, (request_text or "").strip()[:2000],
                acceptance))

    def _agentic_task_body(self, tid, request_text, requester, tags,
                           task_class,
                           bid_window_ms=AGENTIC_BID_WINDOW_MS,
                           timeout_ms=AGENTIC_TIMEOUT_MS):
        acceptance = self._acceptance_for(request_text)
        return {
            "task_id": tid,
            "title": ((request_text or "").strip()[:80] or tid),
            "payload": self._agentic_prompt(tid, request_text, requester,
                                            acceptance),
            "tags": sorted(set(tags or ["probe"])),
            "acceptance": acceptance,
            "task_class": task_class,
            "exec_mode": "super-ralph",
            "posted_ts": time.time(),
            "bid_window_ms": bid_window_ms,
            "timeout_ms": timeout_ms,
        }

    # ----- direct assignment (urgent intake) ---------------------------
    def _pick_direct_worker(self):
        """Least-loaded capable worker: fewest locked (in-flight) tasks;
        alphabetical tiebreak. Every registered bidder runs Super Ralph
        from the shared PATH, so all are capable of agentic tasks."""
        cands = [(len((self.profiles[s].get("locked") or {})), s)
                 for s in sorted(self.profiles)]
        return cands[0][1] if cands else None

    def _assign_direct(self, tid, body, safe_frm):
        """Immediate signed assignment for DIRECT intake: no auction delay,
        but full authentication (control-signed task_post), stake escrow,
        signed-result verification, and settlement. Durable: the assigned
        row + channel assign let reconstruct() resume it exactly like a
        Vickrey assignment."""
        a = self.open_auction(body)
        if not a:
            self.log("direct_assign_failed", task_id=tid,
                     reason="auction-not-opened")
            return None
        short = self._pick_direct_worker()
        if not short:
            self.log("direct_assign_failed", task_id=tid,
                     reason="no-workers")
            a.state = "CLOSED"
            self.done.add(tid)
            return None
        bond = mech.BOND
        try:
            mech.lock_bond(self.profiles, short, tid, bond)
        except (KeyError, ValueError) as e:
            self.log("direct_assign_failed", task_id=tid,
                     reason="stake-lock-failed", detail=str(e)[:200])
            self.fleet_note("intake: DIRECT %s failed (stake lock): %s"
                            % (tid, str(e)[:120]))
            a.state = "CLOSED"
            self.done.add(tid)
            return None
        now = time.time()
        winner = "bidder-" + short
        a.state = "ASSIGNED"
        a.winner, a.price_paid, a.assign_ts = winner, 0.0, now
        # Stake first, publish second -- same crash-window ordering as
        # close_bidding; reconstruct() reconciles exactly once.
        self._publish_assign(a, winner, 0.0, 0.0,
                             {"mode": "direct", "clearing": "direct",
                              "reason": "urgent-intake"},
                             [], bond)
        heapq.heappush(self.timers,
                       (now + a.timeout_ms / 1000.0, "exec_timeout", tid))
        self.log("assigned", task_id=tid, winner=winner, amount=0.0,
                 price_paid=0.0, bond=bond, mode="direct", replay=False)
        self.fleet_note("intake: DIRECT %s assigned to %s immediately "
                        "(urgent; stake escrowed)." % (tid, winner))
        return a

    # ----- oracle intake (front door) ---------------------------------
    def handle_intake(self, meta, data, replay=False):
        # Intake decisions are live-only: replaying an intake_request must
        # not re-append an intake-decision ledger row. The watch re-arm
        # path re-ingests recent channel files with replay=True, and
        # ingest is NOT idempotent for intake (triage appends to the
        # ledger), so bail before triage touches anything.
        if replay:
            return
        try:
            from oracle_intake import triage
        except ImportError as e:
            self.log("intake_error", reason="import: %s" % e)
            return
        req = {"from": meta.get("from", "?"), "text": data.get("text", "")}
        d = triage(req, str(LEDGER))
        route = d.get("route")
        safe_frm = self._safe_frm(req["from"])
        if route in ("TASK", "RESEARCH"):
            # Biddable work: TASK goes to auction; RESEARCH becomes a
            # normally-signed biddable task with research tags and
            # concrete deliverables. Both are real Super Ralph prompts
            # with explicit acceptance criteria -- never print() stubs.
            if route == "RESEARCH":
                tags = self._research_tags(req["text"])
                task_class = "research"
            else:
                tags = d.get("tags", ["probe"])
                task_class = "standard"
            tid = "%s-%d" % (route.lower(), int(time.time() * 1000))
            body = self._agentic_task_body(tid, req["text"], req["from"],
                                           tags, task_class)
            # The oracle vouches for the triaged request by publishing a
            # control-signed task_post (SPEC 1.5): bidders only bid on
            # channel task_posts, so a memory-only open_auction here would
            # silently starve. The normal ingest path opens the auction
            # and reconstruct() resumes it across restarts.
            self._post_signed_task(
                body, tid, safe_frm,
                note=("intake: triaged %s from %s [tags: %s] "
                      "(control-signed)." % (route, req["from"],
                                             ",".join(body["tags"]))))
            self.fleet_note("intake: %s %s opened (tags: %s)"
                            % (route, tid, ",".join(body["tags"])))
        elif route == "DIRECT":
            # Urgent: skip the auction delay, but NOT authentication,
            # stake escrow, result verification, or settlement.
            tid = "direct-%d" % int(time.time() * 1000)
            body = self._agentic_task_body(tid, req["text"], req["from"],
                                           ["direct", "urgent"], "direct",
                                           bid_window_ms=5000)
            self._post_signed_task(
                body, tid, safe_frm,
                note=("intake: DIRECT from %s (control-signed); "
                      "assigning immediately." % req["from"]))
            self.log("intake_direct", frm=req["from"], task_id=tid,
                     request=req["text"][:200])
            self._assign_direct(tid, body, safe_frm)
        elif route == "PETITION":
            # Governance: upgrade petitions get a real debate with named
            # advocates, recorded evidence, and an explicit verdict --
            # not a ledger line and a fleet announcement.
            did = self.open_debate(req["text"], req["from"], wanted=None,
                                   kind="petition")
            if did:
                self.log("intake_petition", frm=req["from"], debate_id=did,
                         request=req["text"][:200])
        elif route == "DEBATE":
            # The debate chase rule owns this: open a real debate
            # (named agents, chase on timeout, quorum-or-hard settle)
            # instead of announcing into the void.
            self.open_debate(req["text"], req["from"], wanted=None)
        elif route == "REJECT":
            self.fleet_note("intake: REJECTED (%s): %s"
                            % (d.get("reason"), req["text"][:200]))
        else:
            self.fleet_note("intake: %s (%s): %s"
                            % (route, d.get("reason"), req["text"][:200]))

    def _attestation_ok(self, att):
        """Knowledgebase attestation gate (SPEC §10). Returns None when
        the bid attestation is well-formed, else the reject reason."""
        if not isinstance(att, dict):
            return "no-attestation"
        if not KB_SHA_RE.match(str(att.get("kb_sha") or "")):
            return "malformed-attestation"
        crews = att.get("checked_crews")
        if (not isinstance(crews, list) or not crews
                or not all(isinstance(c, str) and c.strip()
                           for c in crews)):
            return "malformed-attestation"
        if (not isinstance(att.get("no_overlap"), str)
                or not att["no_overlap"].strip()):
            return "malformed-attestation"
        return None

    # ----- debate chase rule (SPEC §9) -----
    def debate_roster(self):
        """Default named agents for debates opened without an explicit
        wanted list. Committed file beats the builtin fallback."""
        try:
            raw = (AGENT_DIR / "debates" / "roster.json").read_text(
                encoding="utf-8")
            wanted = json.loads(raw).get("wanted")
            if isinstance(wanted, list) and wanted:
                return [str(w).strip() for w in wanted if str(w).strip()]
        except (OSError, ValueError):
            pass
        return ["ember", "kindling"]

    def open_debate(self, question, opener, wanted=None, soft_ms=None,
                    hard_ms=None, kind="debate"):
        question = (question or "").strip()[:500]
        if not question:
            self.log("debate_rejected", reason="empty-question",
                     opener=opener)
            return None
        fp = hashlib.sha256(
            (opener + "\n" + question).encode()).hexdigest()[:16]
        if fp in self.debate_req_seen:
            self.log("debate_duplicate", opener=opener, fp=fp)
            return None
        did = "debate-%d-%s" % (int(time.time() * 1000),
                                os.urandom(2).hex())
        want = [str(w).strip() for w in (wanted or self.debate_roster())
                if str(w).strip()] or self.debate_roster()
        soft_ms = int(soft_ms) if soft_ms else DEBATE_SOFT_MS
        hard_ms = int(hard_ms) if hard_ms else DEBATE_HARD_MS
        d = Debate(did, question, opener, want, soft_ms, hard_ms,
                 kind=kind)
        self.debates[did] = d
        self.debate_req_seen.add(fp)
        self.log("debate_open", debate_id=did, question=question,
                 opener=opener, wanted=want, soft_ms=soft_ms,
                 hard_ms=hard_ms, fp=fp, kind=kind)
        heapq.heappush(self.timers, (d.soft_ts, "debate_chase", did))
        heapq.heappush(self.timers, (d.hard_ts, "debate_hard", did))
        if kind == "petition":
            self.fleet_note(
                "\U0001f5e3\ufe0f PETITION debate opened (%s) by %s: %s\n"
                "wanted advocates: %s \u2014 reply in bid-market as "
                "debate_reply with debate_id=%s. Start your reply with "
                "APPROVE or REJECT and give your evidence; quorum is %d "
                "replies, then the oracle tallies a verdict."
                % (did, opener, question, ", ".join(want), did,
                   DEBATE_QUORUM))
        else:
            self.fleet_note(
                "\U0001f5e3\ufe0f debate opened (%s) by %s: %s\n"
                "wanted replies from: %s \u2014 reply in bid-market as "
                "debate_reply with debate_id=%s (quorum: %d replies; the "
                "oracle chases if it goes quiet)."
                % (did, opener, question, ", ".join(want), did,
                   DEBATE_QUORUM))
        return did

    def handle_debate_reply(self, meta, data):
        did = meta.get("task_id") or data.get("debate_id") or ""
        d = self.debates.get(did)
        frm = meta.get("from", "?")
        if not d or d.state == "SETTLED":
            self.log("debate_reply_orphan", debate_id=did, frm=frm)
            return
        if frm in SELF_FROMS or frm in d.replies:
            return
        d.replies[frm] = time.time()
        d.evidence[frm] = str(data.get("text", ""))[:2000]
        self.log("debate_reply", debate_id=did, frm=frm,
                 text=str(data.get("text", ""))[:300],
                 replies=len(d.replies))
        if len(d.replies) >= DEBATE_QUORUM:
            self._settle_debate(d, "quorum")
        else:
            self.fleet_note(
                "\U0001f5e3\ufe0f debate %s: reply %d/%d (from %s)."
                % (did, len(d.replies), DEBATE_QUORUM, frm))

    def debate_chase(self, did):
        """Soft deadline with <quorum replies: name-and-nudge once."""
        d = self.debates.get(did)
        if not d or d.state != "OPEN":
            return
        if len(d.replies) >= DEBATE_QUORUM:
            return  # settled concurrently; stale timer
        d.state = "CHASED"
        d.chased = True
        missing = [w for w in d.wanted if w not in d.replies]
        self.log("debate_chased", debate_id=did, wanted=d.wanted,
                 replied=sorted(d.replies), missing=missing)
        names = ", ".join(missing) if missing else "anyone watching"
        self.fleet_note(
            "\U0001f514 debate chase (%s): %d/%d replies so far \u2014 "
            "%s, you were named as wanted on this debate and haven\u2019t "
            "replied. Question: %s"
            % (did, len(d.replies), DEBATE_QUORUM, names, d.question))

    def debate_hard(self, did):
        d = self.debates.get(did)
        if not d or d.state == "SETTLED":
            return
        n = len(d.replies)
        self._settle_debate(d, "quorum" if n >= DEBATE_QUORUM
                            else "no_quorum")

    def _settle_debate(self, d, verdict, replay=False):
        """Terminal settle. Invariant: a no_quorum settle ALWAYS has a
        recorded chase \u2014 if the soft timer never fired, the settle
        path fires (and records) the chase first."""
        if d.state == "SETTLED":
            return
        if verdict == "no_quorum" and not d.chased:
            d.chased = True
            d.state = "CHASED"
            missing = [w for w in d.wanted if w not in d.replies]
            self.log("debate_chased", debate_id=d.debate_id,
                     wanted=d.wanted, replied=sorted(d.replies),
                     missing=missing,
                     note="fired by settle path (invariant)", replay=replay)
            self.fleet_note(
                "\U0001f514 debate chase (%s): recorded at settle \u2014 "
                "wanted %s; %d/%d replies. Question: %s"
                % (d.debate_id, ", ".join(d.wanted), len(d.replies),
                   DEBATE_QUORUM, d.question))
        if d.kind == "petition" and verdict == "quorum":
            # Governance verdict tallied from the recorded evidence. The
            # tally is heuristic (explicit APPROVE/REJECT replies, which
            # the petition fleet note asks for); the full evidence text
            # is preserved in the ledger for audit.
            verdict = self._tally_petition(d)
        d.state = "SETTLED"
        self.log("debate_settled", debate_id=d.debate_id, verdict=verdict,
                 kind=d.kind, replies=sorted(d.replies),
                 evidence=d.evidence, chased=d.chased,
                 question=d.question[:200], replay=replay)
        if d.kind == "petition":
            ev_txt = ("; ".join("%s: %s" % (k, v[:120])
                                for k, v in d.evidence.items())[:400]
                      or "none recorded")
            self.fleet_note(
                "\U0001f5e3\ufe0f petition %s VERDICT: %s \u2014 %d/%d "
                "advocates heard. Evidence: %s"
                % (d.debate_id, verdict.upper(), len(d.replies),
                   DEBATE_QUORUM, ev_txt))
            self._on_petition_verdict(d, verdict, replay=replay)
        else:
            self.fleet_note(
                "\U0001f5e3\ufe0f debate settled (%s): %s \u2014 %d/%d "
                "replies%s. %s"
                % (d.debate_id, verdict, len(d.replies), DEBATE_QUORUM,
                   " (chase recorded)" if d.chased else "",
                   d.question[:160]))

    def _tally_petition(self, d):
        """Explicit governance verdict from recorded advocate evidence."""
        approve = reject = 0
        for text in d.evidence.values():
            t = text.lower()
            a = bool(re.search(
                r"(approve|approved|\byes\b|\+1|support|agree|ship it)", t))
            r = bool(re.search(
                r"(reject|rejected|veto|\bno\b|-1|oppose|against|block)", t))
            if a and not r:
                approve += 1
            elif r and not a:
                reject += 1
        if approve > reject:
            return "approved"
        if reject > approve:
            return "rejected"
        return "tied"

    def _on_petition_verdict(self, d, verdict, replay=False):
        """Approved upgrades become market tasks (agent governance)."""
        if verdict != "approved":
            self.log("petition_closed", debate_id=d.debate_id,
                     verdict=verdict, replay=replay)
            return
        if replay:
            # The pre-crash task_post (if any) is re-opened by
            # reconstruct(); never re-publish on replay.
            self.log("petition_approved_replay", debate_id=d.debate_id,
                     replay=True)
            return
        tid = "petition-%d" % int(time.time() * 1000)
        body = self._agentic_task_body(
            tid, d.request, d.opener, ["petition", "upgrade"], "standard")
        self._post_signed_task(
            body, tid, self._safe_frm(d.opener),
            note=("petition %s APPROVED -> market task %s "
                  "(control-signed)." % (d.debate_id, tid)))
        self.log("petition_task_opened", debate_id=d.debate_id, task_id=tid,
                 verdict=verdict)
        self.fleet_note("petition %s approved: upgrade task %s opened "
                        "for bidding." % (d.debate_id, tid))

    def handle_bid(self, meta, data, replay=False):
        tid = meta.get("task_id") or data.get("task_id")
        a = self.auctions.get(tid)
        if not a or a.state != "OPEN":
            return
        bidder = meta.get("bidder") or data.get("bidder_id") or meta.get("from", "?")
        now = time.time()
        # file mtime is the oracle's own observation of arrival; the bid file
        # may vanish between the directory scan and here (concurrent cleanup).
        try:
            mtime = (CHANNEL / meta["_file"]).stat().st_mtime
        except (OSError, KeyError):
            mtime = now
        try:
            bid_ts = int(meta.get("bid_ts"))
        except (TypeError, ValueError):
            bid_ts = 0
        reason = None
        # Knowledgebase attestation gate (fleet rule, SPEC §10): a bid
        # must attest it read Active Crews (docs/fleet-knowledgebase.md
        # §2) and checked for overlapping work. Shape-checked BEFORE
        # the envelope crypto; missing/malformed -> mechanism reject.
        att = data.get("kb_attestation")
        areason = self._attestation_ok(att)
        verified, vreason = None, None
        if areason and mtime >= self.attestation_gate_ts:
            reason = areason
        else:
            if areason:
                # grandfather: bid predates the gate (in flight across the
                # deploy restart). Logged, accepted once, never again.
                self.log("bid_grandfathered", task_id=tid, bidder=bidder,
                         replay=replay)
                att = None
            verified, vreason = self.verify_bid_envelope(meta, tid)
        if reason:
            pass  # attestation gate fired; the envelope chain is skipped
        elif vreason:
            reason = vreason
        elif (mtime > a.deadline
              or bid_ts > a.deadline + BID_SKEW_S):
            # Deadline is enforced on the oracle-observed arrival (mtime,
            # the oracle's own clock: no skew needed) and the HMAC-signed
            # bid_ts (bidder's clock: BID_SKEW_S tolerance). The old check
            # used the bidder-controlled body posted_ts, letting anyone bid
            # up to BID_TS_TOLERANCE_S (300s) late by backdating the body
            # while keeping a fresh envelope timestamp.
            reason = "late"
        elif bidder in a.bids:
            reason = "duplicate-bidder"
        elif not (set(data.get("tags_matched", [])) & a.tags):
            reason = "no-tag-match"
        else:
            # capabilities are registry-side, not self-reported: a bidder can
            # only bid tasks intersecting its provisioned capabilities.
            prof = self.profiles.get(bidder.removeprefix("bidder-"))
            if not prof or not (set(prof.get("capabilities", [])) & a.tags):
                reason = "no-capability-match"
        if reason:
            if not replay:
                self.market.post("reject", f"reject-{bidder}-{tid}",
                                 {"task_id": tid, "bidder_id": bidder,
                                  "reason": reason, "posted_ts": now},
                                 task_id=tid,
                                 note=f"oracle-market: bid from {bidder} rejected ({reason}).")
            self.log("bid_rejected", task_id=tid, bidder=bidder,
                     reason=reason, replay=replay)
            return
        a.bids[bidder] = {
            "amount": verified["amount"],
            "nonce": verified["nonce"],
            "bidder_id": verified["bidder_id"],
            "key_id": meta.get("key_id"),
            "bid_ts": bid_ts,
            "mtime": mtime,
            "tags_matched": sorted(set(data.get("tags_matched", [])) & a.tags),
            "cost_ms": data.get("cost_ms"),
            "eta_ms": data.get("eta_ms"),
            "attestation": att,
        }
        self.log("bid_accepted", task_id=tid, bidder=bidder,
                 amount=verified["amount"], nonce=verified["nonce"],
                 kb_sha=(att or {}).get("kb_sha"),
                 checked_crews=(att or {}).get("checked_crews"),
                 no_overlap=(att or {}).get("no_overlap"),
                 replay=replay)

    def _vickrey(self, a):
        """Pure Vickrey clearing over a.bids.

        Returns (winner, amount, price_paid, reveal, contenders, ties), or
        (None, reason, reveal) when the auction closes unassigned.
        Highest sealed amount wins; ties break on earliest bid-file mtime
        (SPEC §2.2); winner pays max(second_highest, RESERVE). Reputation
        gates eligibility but never distorts the clearing price.
        """
        def eligible(bidder):
            prof = self.profiles.get(bidder.removeprefix("bidder-"))
            if not prof:
                return False
            return mech.class_allowed(a.task_class, self.rep.get(bidder, 0))

        ranked = sorted(a.bids.items(),
                        key=lambda kv: (-kv[1]["amount"], kv[1]["mtime"]))
        reveal = [{"bidder": b, "amount": d["amount"], "nonce": d["nonce"],
                   "eligible": eligible(b),
                   "tags_matched": d["tags_matched"],
                   "kb_attestation": d.get("attestation")}
                  for b, d in ranked]
        contenders = [(b, d) for b, d in ranked if eligible(b)]
        if not contenders:
            return None, ("no-eligible-bids" if ranked else "no-valid-bids"), \
                reveal, None, None, None
        winner, wbid = contenders[0]
        amount = wbid["amount"]
        if amount < RESERVE:
            return None, "reserve-not-met", reveal, None, None, None
        ties = [b for b, d in contenders if d["amount"] == amount]
        second = contenders[1][1]["amount"] if len(contenders) > 1 else RESERVE
        price_paid = round(max(second, RESERVE), 6)
        return winner, amount, price_paid, reveal, contenders, ties

    def _publish_assign(self, a, winner, amount, price_paid, reveal, ties,
                        bond, republished=False):
        """Post the assign message (channel) + fleet note. Publish-only."""
        now = time.time()
        tid = a.task_id
        note = ("oracle-market: Vickrey clearing (highest amount wins, "
                "pays max(second, reserve)). Full reveal embedded; "
                "any agent can re-verify.")
        if republished:
            note += " Re-published once after restart: the assign was logged " \
                    "but never reached the channel (crash recovery)."
        self.market.post("assign", f"assign-{tid}",
                         {"posted_ts": now, "task_id": tid, "winner": winner,
                          "winning_amount": amount, "price_paid": price_paid,
                          "reserve": RESERVE, "clearing": "vickrey",
                          "bond": bond, "judged_by": "oracle-market",
                          "reveal": reveal,
                          "tie": ties if len(ties) > 1 else [],
                          "republished": republished},
                         task_id=tid, note=note)
        self.fleet_note(
            f"oracle-market: auction {tid} assigned to {winner} "
            f"(amount {amount:.3f}, pays {price_paid:.3f}).")

    def close_bidding(self, tid, replay=False):
        """Vickrey clearing (SPEC §2.2). Never re-publishes on replay."""
        a = self.auctions.get(tid)
        if not a or a.state != "OPEN" or tid in self.done:
            return
        now = time.time()
        a.state = "ASSIGNED"  # tentatively; may flip to CLOSED below
        v = self._vickrey(a)
        winner, amount, price_paid, reveal, contenders, ties = v
        if winner is None:
            # _vickrey returns (None, reason, reveal, None, None, None)
            reason = amount
            if not replay:
                body = {"task_id": tid, "reason": reason, "posted_ts": now,
                        "reveal": reveal}
                if reason == "reserve-not-met":
                    body["best_amount"] = max(
                        (d["amount"] for _, d in
                         sorted(a.bids.items(),
                                key=lambda kv: -kv[1]["amount"])),
                        default=0.0)
                self.market.post("no_assign", f"no-assign-{tid}", body,
                                 task_id=tid,
                                 note=f"oracle-market: {reason}; auction closed unassigned.")
                self.fleet_note(f"oracle-market: auction {tid} closed unassigned ({reason}).")
            self.log("no_assign", task_id=tid, reason=reason, reveal=reveal,
                     replay=replay)
            a.state = "CLOSED"
            self.done.add(tid)
            self._maybe_start_next_work(tid)
            return
        a.winner, a.price_paid, a.assign_ts = winner, price_paid, now
        bond = mech.BOND
        try:
            mech.lock_bond(self.profiles, winner.removeprefix("bidder-"),
                           tid, bond)
        except (KeyError, ValueError) as e:
            if not replay:
                self.market.post("no_assign", f"no-assign-{tid}",
                                 {"task_id": tid, "reason": "stake-lock-failed",
                                  "detail": str(e)[:200], "posted_ts": now,
                                  "reveal": reveal},
                                 task_id=tid,
                                 note="oracle-market: winner could not lock stake bond; closed.")
            self.log("no_assign", task_id=tid, reason="stake-lock-failed",
                     detail=str(e)[:200], replay=replay)
            a.state = "CLOSED"
            self.done.add(tid)
            self._maybe_start_next_work(tid)
            return
        if not replay:
            self._publish_assign(a, winner, amount, price_paid, reveal, ties,
                                 bond)
            heapq.heappush(self.timers,
                           (now + a.timeout_ms / 1000.0, "exec_timeout", tid))
        else:
            # replay: restore the exec timer without re-publishing
            heapq.heappush(self.timers,
                           (a.assign_ts + a.timeout_ms / 1000.0, "exec_timeout", tid))
        self.log("assigned", task_id=tid, winner=winner, amount=amount,
                 price_paid=price_paid, bond=bond, reveal=reveal,
                 tie=(ties if len(ties) > 1 else []), replay=replay)
        if replay:
            self.log("replay_resumed_assigned", task_id=tid, winner=winner)

    def handle_assign(self, meta, data, replay=False):
        # Adopt assigns from a trusted foreign auctioneer (manual override
        # path). ingest() only routes these from TRUSTED_POSTERS; anything
        # else is ignored before it gets here.
        tid = data.get("task_id")
        a = self.auctions.get(tid)
        if not a or a.state != "OPEN":
            return
        winner = data.get("winner")
        short = (winner or "").removeprefix("bidder-")
        if not short or short not in self.profiles:
            self.log("assign_adopt_failed", task_id=tid, reason="unknown-winner",
                     by=meta.get("from"), replay=replay)
            return
        # An adopted assign must escrow the bond exactly like a Vickrey
        # assign; otherwise a later timeout would slash free stake (or, with
        # the fail-closed slash, slash nothing while the settle claims a
        # slash happened).
        try:
            mech.lock_bond(self.profiles, short, tid, mech.BOND)
        except (KeyError, ValueError) as e:
            self.log("assign_adopt_failed", task_id=tid,
                     reason="stake-lock-failed", detail=str(e)[:200],
                     by=meta.get("from"), replay=replay)
            return
        a.state = "ASSIGNED"
        a.winner = winner
        a.price_paid = data.get("price_paid")
        a.assign_ts = _fnum(data.get("posted_ts"), time.time())
        heapq.heappush(self.timers, (a.assign_ts + a.timeout_ms / 1000.0,
                                     "exec_timeout", tid))
        # Log as "assigned" (not a sidecar event): slash() resolves the
        # assignee from the ledger's assignment row, and reconstruct resumes
        # assigned-but-unsettled auctions from it.
        self.log("assigned", task_id=tid, winner=winner,
                 price_paid=a.price_paid, bond=mech.BOND, adopted=True,
                 by=meta.get("from"), replay=replay)

    def _verify_result_sig(self, meta, data, tid, bidder):
        """True when the result carries a valid HMAC under the winner's key.

        Results used to be accepted on the unauthenticated body: any channel
        writer could forge a result as the winner — success=false to frame
        them for a full-bond slash, or success=true with a self-consistent
        hash to settle a task as verified without doing the work. The key is
        looked up from the winner's registry profile, never from the message.
        """
        prof = self.profiles.get(bidder.removeprefix("bidder-"))
        if not prof or meta.get("key_id") != prof.get("key_id"):
            return False
        try:
            hmac_key, _ = sealed_mod.derive_keys(prof["secret"])
        except (ValueError, KeyError):
            return False
        return sealed_mod.verify_result_sig(
            hmac_key, meta.get("key_id", ""), tid, bidder,
            data.get("result_hash", ""), data.get("success"),
            data.get("duration_ms", 0), data.get("artifacts") or [],
            meta.get("result_sig", ""))

    def _publish_settle(self, a, success, verified, duration_ms, notes,
                        republished=False):
        """Post the settle message (channel) + fleet note. Publish-only:
        no stake mutation, so it is safe to call exactly once for a
        settle that was decided but never reached the channel."""
        now = time.time()
        tid = a.task_id
        note = ("oracle-market: result from "
                f"{a.winner} {'verified' if verified else 'FLAGGED'}.")
        if republished:
            note += " Re-published once after restart: the settle was decided " \
                    "but never reached the channel (crash recovery)."
        self.market.post("settle", f"settle-{tid}",
                         {"task_id": tid, "winner": a.winner,
                          "success": success, "verified": verified,
                          "duration_ms": duration_ms,
                          "price_paid": a.price_paid,
                          "notes": notes, "posted_ts": now,
                          "republished": republished},
                         task_id=tid, note=note)
        self.fleet_note(
            f"oracle-market: {tid} settled — {a.winner} "
            f"{'verified' if verified else 'FLAGGED'}.")

    def _apply_settle(self, tid, bidder, success, verified, duration_ms,
                        notes, replay, reason=None):
        """Stake + reputation consequences. Idempotent: the locked bond is
        the pending marker — if it is already gone, the transition applied
        (a crash between the profile write and the ledger log only loses the
        ledger mark, which the caller re-adds)."""
        short_id = bidder.removeprefix("bidder-")
        prof = self.profiles.get(short_id)
        if not prof or tid not in (prof.get("locked") or {}):
            self.log("settle_no_lock", task_id=tid, bidder=bidder,
                     verified=verified, replay=replay)
            return False
        if verified:
            mech.release_bond(self.profiles, short_id, tid)
            self.rep[bidder] = self.rep.get(bidder, 0) + 1
            self.log("stake_released", task_id=tid, bidder=bidder,
                     reward=mech.REWARD, replay=replay)
        else:
            # severity tiers (nexaflow decay): no usable result at all ->
            # full bond; failed attempt -> half bond.
            fraction = 1.0 if not success else 0.5
            if reason is None:
                reason = "failed-verification" if success else "no-result"
            sl = mech.slash(self.profiles, LEDGER, tid, reason=reason,
                            fraction=fraction)
            # NOTE: rep is only decremented when the slash actually landed.
            # Updating it unconditionally diverged in-memory rep from the
            # ledger-derived rep on restart whenever slash() failed closed.
            if sl:
                self.log("slashed", **sl, verified=False, replay=replay)
                self.rep[bidder] = max(0, self.rep.get(bidder, 0) - 2)
        # The settled event carries the full decision: reconstruct() can
        # re-publish a settle that was decided but never reached the channel
        # (crash between the stake write and _publish_settle) exactly once.
        self.log("settled", task_id=tid, winner=bidder, verified=verified,
                 success=success, duration_ms=duration_ms,
                 price_paid=self.auctions[tid].price_paid, notes=notes,
                 reason=reason, replay=replay)
        return True

    def handle_result(self, meta, data, replay=False, verify_sig=True):
        """Returns a dict of the settle decision, or None when ignored."""
        tid = data.get("task_id")
        a = self.auctions.get(tid)
        if not a or a.state != "ASSIGNED" or tid in self.done:
            return None
        bidder = data.get("bidder_id") or meta.get("from")
        if not bidder or bidder != a.winner:
            return None
        # Strict schema at the gate: `success` must be a real boolean.
        # bool("false") is True -- coercing would let a tampered envelope
        # flip a failure into a success (or vice versa). A non-boolean
        # cannot be authenticated under the signature scheme, so it is
        # rejected outright rather than coerced.
        sraw = data.get("success")
        if sraw is not True and sraw is not False:
            self.log("result_rejected", task_id=tid, bidder=bidder,
                     reason="bad-success-type", got=repr(sraw)[:60],
                     frm=meta.get("from"), replay=replay)
            return None
        if verify_sig and not self._verify_result_sig(meta, data, tid, bidder):
            # Forged or corrupt result: ignore it. The winner's genuine
            # signed result (or the exec timeout) still settles the task.
            self.log("result_rejected", task_id=tid, bidder=bidder,
                     reason="bad-result-sig", frm=meta.get("from"),
                     replay=replay)
            return None
        success = sraw
        try:
            duration_ok = float(data.get("duration_ms", 0)) <= a.timeout_ms
        except (TypeError, ValueError):
            duration_ok = False  # malformed duration fails objective checks
        # artifact verification: committed proof hash must match delivered
        # output hash (SPEC §3.3); artifacts must exist on disk.
        hash_ok = True
        notes = []
        committed = data.get("result_hash")
        if committed:
            actual = hashlib.sha256(
                (data.get("output") or "").encode()).hexdigest()
            if committed != actual:
                hash_ok = False
                notes.append("proof-hash-mismatch")
        artifacts_ok = True
        for art in data.get("artifacts", []) or []:
            # Artifact names are winner-controlled: confine the existence
            # check to the task workdir (no separators, no traversal), so a
            # hostile winner cannot use it as a filesystem existence oracle.
            if not isinstance(art, str) or ".." in art or "/" in art \
                    or "\\" in art or art.startswith(".") or not art:
                artifacts_ok = False
                notes.append(f"bad-artifact:{str(art)[:60]}")
                continue
            p = WORK / bidder.removeprefix("bidder-") / tid / art
            if not p.is_file():
                artifacts_ok = False
                notes.append(f"missing-artifact:{art}")
        # Explicit acceptance validation (oracle-repair): never trust
        # the bare success flag. Output must be non-empty, and agentic
        # tasks must carry a fully-MET ACCEPTANCE-REPORT parsed from the
        # SIGNED output itself (hash-bound to the winner's signature).
        output_ok = bool((data.get("output") or "").strip())
        acceptance_ok = True
        if (a.task or {}).get("exec_mode") == "super-ralph":
            found, all_met, acc_items = _parse_acceptance_report(
                data.get("output") or "")
            acceptance_ok = found and all_met
            if not found:
                notes.append("acceptance-report-missing")
            elif not all_met:
                bad = ",".join(c for c, m, _ in acc_items if not m)
                notes.append("acceptance-unmet:%s" % bad[:200])
        if not output_ok:
            notes.append("empty-output")
        verified = (success and duration_ok and hash_ok and artifacts_ok
                    and output_ok and acceptance_ok)
        if data.get("error"):
            notes.append(f"error: {str(data['error'])[:200]}")
        duration_ms = data.get("duration_ms")
        if not replay:
            self._publish_settle(a, success, verified, duration_ms, notes)
        # stake + reputation consequences (objective triggers only, SPEC §3.3)
        self._apply_settle(tid, bidder, success, verified, duration_ms,
                           notes, replay)
        a.state = "CLOSED"
        self.done.add(tid)
        self._maybe_start_next_work(tid)
        return {"success": success, "verified": verified,
                "duration_ms": duration_ms, "notes": notes}

    def exec_timeout(self, tid):
        """Winner missed the result deadline: settle FAILED + slash full
        bond. There is deliberately NO fallback execution — the oracle
        never runs task-post payloads (removed 2026-09-20)."""
        a = self.auctions.get(tid)
        if not a or a.state != "ASSIGNED" or tid in self.done:
            return
        notes = ["exec-timeout: no result by deadline"]
        self.log("exec_timeout", task_id=tid, winner=a.winner)
        self.fleet_note(
            f"oracle-market: {a.winner} missed the result deadline on {tid}; "
            f"settling FAILED, bond slashed.")
        # Stake first, publish second. Any crash between the two is
        # reconciled exactly once by reconstruct(): the locked bond is the
        # pending marker for _apply_settle, and a ledger "settled" event
        # without a channel settle is re-published once.
        self._apply_settle(tid, a.winner, False, False, None, notes,
                           replay=False, reason="exec-timeout")
        self._publish_settle(a, False, False, None, notes)
        a.state = "CLOSED"
        self.done.add(tid)
        self._maybe_start_next_work(tid)

    # ----- autonomous next-work selection ------------------------------

    # ----- autonomous backlog pump (2026-09-21, ember) -------------------
    def _pump_backlog(self):
        """Autonomous task supply: when the market is idle and the swarm
        has proposed nothing, pop the next queued task from the backlog
        file and feed it through intake (the front door), so auctions
        launch without waiting on a human. The backlog is JSONL, one task
        per line: {"title","text","added_by","added_ts","status"}.
        Entries are claimed (status -> posted) BEFORE the channel post,
        so a crash can never double-launch a task; a claimed-but-unposted
        task stays visible in the file for manual re-queue. Returns the
        entry dict, or None when there is nothing to pump."""
        try:
            if not BACKLOG.exists():
                return None
            raw = BACKLOG.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            self.log("backlog_read_error", reason=str(e))
            return None
        entries = []
        for ln in raw:
            ln = ln.strip()
            if not ln:
                continue
            try:
                entries.append(json.loads(ln))
            except (json.JSONDecodeError, ValueError):
                continue
        idx = None
        for i, e in enumerate(entries):
            if (isinstance(e, dict) and e.get("status") == "queued"
                    and (e.get("text") or "").strip()):
                idx = i
                break
        if idx is None:
            return None
        # Claim BEFORE posting: crash-safe, never double-launches.
        entries[idx]["status"] = "posted"
        entries[idx]["posted_ts"] = time.time()
        try:
            tmp = BACKLOG.with_name(BACKLOG.name + ".tmp")
            tmp.write_text(
                "\n".join(json.dumps(e) for e in entries) + "\n",
                encoding="utf-8")
            os.replace(tmp, BACKLOG)
        except OSError as e:
            self.log("backlog_claim_error", reason=str(e))
            return None
        text = entries[idx]["text"]
        title = entries[idx].get("title") or "backlog-task"
        # NOTE: frm="backlog-pump", NOT FROM. ingest() ignores the
        # oracle's own posts (SELF_FROMS); a self-from intake_request would
        # never be triaged and no auction would open. backlog-pump is a
        # non-self requester identity, so the normal intake -> task_post
        # -> auction path runs. The task_post stays control-HMAC-signed.
        try:
            name = self.market.post(
                "intake_request",
                "intake-%s" % self._safe_frm(title),
                {"text": text},
                note=("oracle-market: autonomous backlog pump -- no swarm "
                      "proposal arrived; launching next queued task."),
                frm="backlog-pump")
        except Exception as e:
            self.log("backlog_post_error", reason=str(e), title=title)
            return None
        self.log("backlog_pumped", title=title, file=name)
        self.fleet_note(
            "oracle-market: backlog -> intake: %s" % title[:120])
        return entries[idx]

    def _maybe_start_next_work(self, prev_tid):
        """Settlement-driven autonomy: when a task reaches a terminal state
        and nothing else is in flight, invite the swarm to propose the next
        task through intake (the front door). Event-driven: invoked exactly
        at settlement transitions (handle_result, exec_timeout,
        close_bidding terminal paths) -- never a poll loop, never a timer.
        Idempotent per settlement via the done set; replay-safe because
        the trigger points only fire on live transitions."""
        key = ("nextwork", prev_tid)
        if key in self.done:
            return
        self.done.add(key)
        busy = any(a.state in ("OPEN", "ASSIGNED")
                   for a in self.auctions.values())
        if busy:
            # Another task still in flight: its settlement re-triggers.
            return
        self.market.post("next_work", "next-work-%s" % prev_tid,
                         {"prev_task": prev_tid, "idle_ts": time.time(),
                          "note": ("market idle: all auctions terminal. "
                                   "Swarm: propose the next task via "
                                   "intake.")},
                         task_id=prev_tid,
                         note=("oracle-market: %s settled; market idle. "
                               "Next task proposals welcome via intake."
                               % prev_tid))
        self.fleet_note("oracle-market: %s settled and the market is idle "
                        "-- swarm, propose the next task via intake."
                        % prev_tid)
        self.log("next_work_request", prev_task=prev_tid)
        # Autonomous supply: if the swarm proposes nothing, the backlog
        # pump feeds the next queued task through intake. Defensive: a
        # pump failure must never break the settlement path.
        try:
            self._pump_backlog()
        except Exception as e:
            self.log("backlog_pump_error", reason=str(e))

    # ----- ingest -----
    def ingest(self, name, replay=False):
        meta_data = parse_msg(CHANNEL / name)
        if not meta_data:
            return
        meta, data = meta_data
        if not isinstance(data, dict):
            return  # non-object body: nothing to dispatch on
        if meta.get("from") in SELF_FROMS:
            return  # our own posts (current + legacy identity)
        meta["_file"] = name
        mt = meta.get("msg_type", "")
        frm = meta.get("from", "")
        try:
            if mt == "task_post":
                # Control plane (SPEC §1.5): only HMAC-authenticated
                # task_posts open auctions. Anyone else forging a task_post
                # could self-deal (post a task, bid, win, "execute" a
                # trivial payload, mint reward).
                if not self._control_ok(meta, data, "task_post"):
                    self.log("task_post_untrusted",
                             task_id=data.get("task_id"), frm=frm,
                             replay=replay)
                    return
                self.open_auction(data, replay=replay)
            elif mt == "bid":
                self.handle_bid(meta, data, replay=replay)
            elif mt == "assign":
                # Manual-override path (SPEC §1.5): control-HMAC only. An
                # unauthenticated foreign assign used to override the
                # winner with no bond.
                if not self._control_ok(meta, data, "assign"):
                    self.log("assign_untrusted",
                             task_id=data.get("task_id"), frm=frm,
                             replay=replay)
                    return
                self.handle_assign(meta, data, replay=replay)
            elif mt == "intake_request":
                # Oracle intake front door (additive, flag-guarded).
                if os.environ.get("ORACLE_INTAKE") == "1":
                    self.handle_intake(meta, data, replay=replay)
                else:
                    self.log("intake_ignored", reason="flag_off", frm=frm)
            elif mt == "debate_request":
                # Debate chase rule (SPEC §9). Live-only: replay
                # reconstructs debates from the ledger's debate_open
                # events; re-ingesting the request would open a duplicate.
                if not replay:
                    self.open_debate(data.get("question", ""), frm,
                                     wanted=data.get("wanted"),
                                     soft_ms=data.get("soft_ms"),
                                     hard_ms=data.get("hard_ms"))
            elif mt == "debate_reply":
                # Replies are ledger-recorded live; replay rebuilds from
                # debate_reply events.
                if not replay:
                    self.handle_debate_reply(meta, data)
            elif mt == "result":
                self.handle_result(meta, data, replay=replay)
        except Exception as e:
            # One hostile or malformed message must never kill the daemon.
            self.log("ingest_error", file=name, msg_type=mt,
                     error=f"{type(e).__name__}: {e}"[:200], replay=replay)

    # ----- replay-safe startup reconstruction -----
    def reconstruct(self):
        """Rebuild state from ledger + channel history, reconciling crash
        windows exactly once.

        Evidence per task:
          ledger: "assigned" / "settled" / "no_assign" events
          channel (oracle-authored): assign / settle / no_assign messages
          profiles: locked bond for (winner, task) == a pending stake
          transition

        Crash windows (each recovered exactly once, idempotent):
          A. bond locked, assign never published nor logged -> re-run the
             clearing deterministically (bids + _vickrey are deterministic)
             and _publish_assign(republished=True) + log the missed
             "assigned" row once. On clearing/escrow mismatch (rep changed
             under us via another task): abort safely — release the bond,
             log assign_aborted, close the task for re-posting.
          B. assign published, "assigned" row lost -> re-log the row from
             the channel body (which embeds the reveal). Never re-publish.
          C. "settled" logged, channel settle lost -> apply the stake
             transition if the lock is still present, then
             _publish_settle(republished=True) once.
          D. channel settle exists, "settled" never logged -> _apply_settle
             once from the message body (the lock is the pending marker;
             an absent lock means the transition already applied).
        Terminal evidence from EITHER source closes the task in memory.
        Only genuinely-open auctions are resumed; expired historical
        auctions are marked closed in memory with a replay_closed log
        (never re-published).
        """
        terminal = {}    # task_id -> "settled" | "no_assign"
        assign_ev = {}   # task_id -> last ledger "assigned" event
        settle_ev = {}   # task_id -> last ledger "settled" event
        debates_build = {}   # debate_id -> rebuild dict (chase rule)
        debate_req_seen = set()  # request fingerprints (dupe guard)
        gate_ts = 0.0        # attestation_gate_live activation (SPEC §10)
        if LEDGER.exists():
            with open(LEDGER, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    tid = ev.get("task_id")
                    e = ev.get("event")
                    # Debate chase rule + attestation gate: their events
                    # carry debate_id (or no id), not task_id.
                    if e == "attestation_gate_live":
                        gate_ts = max(gate_ts, ev.get("ts", 0) or 0)
                    elif e == "debate_open":
                        did = ev.get("debate_id")
                        if did:
                            debate_req_seen.add(ev.get("fp", ""))
                            debates_build[did] = {
                                "question": ev.get("question", ""),
                                "opener": ev.get("opener", "?"),
                                "wanted": ev.get("wanted", []),
                                "kind": ev.get("kind", "debate"),
                                "evidence": {},
                                "soft_ms": ev.get("soft_ms",
                                                  DEBATE_SOFT_MS),
                                "hard_ms": ev.get("hard_ms",
                                                  DEBATE_HARD_MS),
                                "opened_ts": ev.get("ts", 0),
                                "replies": {},
                                "state": "OPEN",
                                "chased": False,
                                "settled": False,
                            }
                    elif e == "debate_reply":
                        db = debates_build.get(ev.get("debate_id"))
                        if db and not db["settled"]:
                            db["replies"][ev.get("frm", "?")] = \
                                ev.get("ts", 0)
                            db["evidence"][ev.get("frm", "?")] = \
                                ev.get("text", "")
                    elif e == "debate_chased":
                        db = debates_build.get(ev.get("debate_id"))
                        if db:
                            db["state"] = "CHASED"
                            db["chased"] = True
                    elif e == "debate_settled":
                        db = debates_build.get(ev.get("debate_id"))
                        if db:
                            db["settled"] = True
                            db["state"] = "SETTLED"
                    if not tid:
                        continue
                    if e == "settled":
                        terminal[tid] = "settled"
                        settle_ev[tid] = ev
                    elif e == "no_assign":
                        terminal[tid] = "no_assign"
                    elif e == "assigned":
                        assign_ev[tid] = ev
        posts = {}       # task_id -> task dict (trusted posters only)
        assign_msg = {}  # task_id -> oracle/trusted assign body
        settle_msg = {}  # task_id -> (meta, data) oracle-authored settle
        results = {}     # task_id -> (meta, data) latest winner result
        files = sorted([f for f in os.listdir(CHANNEL) if SEQ_RE.match(f)])
        for name in files:
            parsed = parse_msg(CHANNEL / name)
            if not parsed:
                continue
            meta, data = parsed
            if not isinstance(data, dict):
                continue
            frm, mt = meta.get("from"), meta.get("msg_type", "")
            tid = meta.get("task_id") or data.get("task_id")
            if not tid:
                continue
            if mt == "task_post" and self._control_ok(meta, data, "task_post"):
                # control-plane evidence: HMAC-authenticated task_post only
                # (the from: field is spoofable, never consulted)
                posts.setdefault(tid, data)
            elif mt in ("settle", "no_assign") and frm in SELF_FROMS:
                # channel "settle" == ledger "settled" (terminal either way)
                terminal[tid] = "settled" if mt == "settle" else mt
                if mt == "settle":
                    settle_msg[tid] = (meta, data)
            elif mt == "assign" and (frm in SELF_FROMS
                                     or self._control_ok(meta, data, "assign")):
                # oracle-authored, or HMAC-authenticated manual override
                # (same gate as ingest; untrusted foreign assigns are not
                # evidence)
                assign_msg.setdefault(tid, data)
            elif mt == "result":
                # collected regardless of terminal state: window D needs
                # the winner's signed result as independent proof before
                # it will move stake on a settle message. Kept as a list so
                # a shadowing forgery can't hide the genuine result.
                results.setdefault(tid, []).append((meta, data))
        now = time.time()
        resumed = {"open": 0, "assigned": 0, "closed": 0, "expired": 0,
                   "recovered": 0}
        for tid, task in posts.items():
            if terminal.get(tid) == "no_assign":
                self.done.add(tid)
                resumed["closed"] += 1
                self.log("replay_closed", task_id=tid, terminal="no_assign")
                continue
            if terminal.get(tid) == "settled":
                # Window C: decided + logged, channel settle lost ->
                # re-publish once (applying the stake transition first if
                # its lock survived the crash).
                if tid not in settle_msg and tid in settle_ev:
                    evs = settle_ev[tid]
                    winner = evs.get("winner")
                    a = self.open_auction(task, replay=True)
                    if a is not None:
                        a.state = "ASSIGNED"
                        a.winner = winner
                        a.price_paid = evs.get("price_paid")
                        short = (winner or "").removeprefix("bidder-")
                        prof = self.profiles.get(short)
                        if prof and tid in (prof.get("locked") or {}):
                            self._apply_settle(
                                tid, winner, evs.get("success", False),
                                evs.get("verified", False),
                                evs.get("duration_ms"),
                                evs.get("notes") or [], replay=True,
                                reason=evs.get("reason"))
                        self._publish_settle(
                            a, evs.get("success", False),
                            evs.get("verified", False),
                            evs.get("duration_ms"),
                            evs.get("notes") or [], republished=True)
                        resumed["recovered"] += 1
                elif tid in settle_msg and tid not in settle_ev:
                    # Window D: a channel settle exists but the ledger holds
                    # no decision. A bare settle message is NOT proof --
                    # `from:` is frontmatter any channel writer can spoof,
                    # so trusting the body here would let anyone mint bond
                    # releases and rewards (genuine window D is unreachable
                    # in the current write ordering: stake is always applied
                    # before the settle is published). Only re-derive from a
                    # signature-verified winner result; otherwise fail closed
                    # and alert.
                    meta, data = settle_msg[tid]
                    winner = data.get("winner")
                    dec = None
                    for pmeta, pdata in results.get(tid, []):
                        if ((pdata.get("bidder_id") or pmeta.get("from"))
                                != winner):
                            continue
                        if not self._verify_result_sig(pmeta, pdata, tid,
                                                       winner):
                            continue
                        a = self.open_auction(task, replay=True)
                        if a is None:
                            break
                        a.state = "ASSIGNED"
                        a.winner = winner
                        a.price_paid = data.get("price_paid")
                        # replay=True: applies the stake once if the lock
                        # survived, but never re-publishes (the settle
                        # message already exists).
                        dec = self.handle_result(pmeta, pdata, replay=True)
                        if dec:
                            resumed["recovered"] += 1
                        break
                    if dec is None:
                        self.log("settle_unproven", task_id=tid,
                                 winner=winner,
                                 reason="settle message without ledger "
                                        "decision or signed winner result; "
                                        "refusing to move stake")
                self.done.add(tid)
                resumed["closed"] += 1
                self.log("replay_closed", task_id=tid, terminal="settled")
                continue
            a = self.open_auction(task, replay=True)
            if a is None:
                continue
            # rebuild bids from surviving bid files (signatures re-verify
            # deterministically; deadline re-enforced on oracle-observed
            # mtime + signed bid_ts)
            for name in files:
                parsed = parse_msg(CHANNEL / name)
                if not parsed:
                    continue
                meta, data = parsed
                if (isinstance(data, dict)
                        and meta.get("msg_type") == "bid"
                        and (meta.get("task_id") or data.get("task_id")) == tid
                        and meta.get("from") not in SELF_FROMS):
                    meta["_file"] = name
                    self.handle_bid(meta, data, replay=True)
            ev = assign_ev.get(tid)
            msg = assign_msg.get(tid)
            ev_winner = (ev or {}).get("winner")
            msg_winner = (msg or {}).get("winner")
            winner = ev_winner or msg_winner
            short = (winner or "").removeprefix("bidder-")
            locked = bool(short) and tid in (
                (self.profiles.get(short) or {}).get("locked") or {})
            # window A probe: bond locked for SOME bidder, but no assign
            # evidence anywhere
            locked_holder = None
            if not (ev or msg):
                for bshort, prof in self.profiles.items():
                    if tid in (prof.get("locked") or {}):
                        locked_holder = bshort
                        break
            if ev or msg:
                if not ev and msg:
                    # Window B: assign reached the channel but the ledger
                    # row was lost -> re-log it from the channel body
                    # (which embeds the reveal). Never re-publish.
                    try:
                        if not locked:
                            mech.lock_bond(self.profiles, short, tid,
                                           mech.BOND)
                    except (KeyError, ValueError) as e:
                        self.log("assign_recover_failed", task_id=tid,
                                 reason="stake-lock-failed",
                                 detail=str(e)[:200])
                        a.state = "CLOSED"
                        self.done.add(tid)
                        resumed["closed"] += 1
                        continue
                    self.log("assigned", task_id=tid, winner=winner,
                             amount=msg.get("winning_amount"),
                             price_paid=msg.get("price_paid"),
                             bond=msg.get("bond", mech.BOND),
                             reveal=msg.get("reveal", []),
                             tie=msg.get("tie", []),
                             recovered=True, replay=True)
                    resumed["recovered"] += 1
                a.state = "ASSIGNED"
                a.winner = winner
                a.price_paid = ((ev or {}).get("price_paid")
                                or (msg or {}).get("price_paid"))
                a.assign_ts = _fnum((ev or {}).get("ts")
                                    or (msg or {}).get("posted_ts"), now)
                if tid in results:
                    # result arrived but was never settled: complete the
                    # transition exactly once (signature re-verified).
                    # Multiple results are tried in channel order; forgeries
                    # fail verification and the genuine one still settles.
                    # If every result is rejected, the task is NOT done --
                    # fall through to the exec-timeout logic below.
                    for meta, data in results[tid]:
                        if self.handle_result(meta, data, replay=True):
                            break
                if tid in self.done:
                    resumed["closed"] += 1
                elif a.assign_ts + a.timeout_ms / 1000.0 <= now:
                    # exec deadline passed while down: settle the missed
                    # transition once (publishes the missed settle).
                    self.exec_timeout(tid)
                    resumed["closed"] += 1
                else:
                    heapq.heappush(self.timers,
                                   (a.assign_ts + a.timeout_ms / 1000.0,
                                    "exec_timeout", tid))
                    self.log("replay_resumed_assigned", task_id=tid,
                             winner=a.winner)
                    resumed["assigned"] += 1
            elif locked_holder:
                # Window A: bond locked, assign never published nor logged
                # -> re-run the clearing deterministically and publish
                # exactly once.
                v = self._vickrey(a)
                w2, amount2, price2, reveal2, _, ties2 = v
                if w2 != f"bidder-{locked_holder}":
                    # Escrow disagrees with the re-clearing (rep moved via
                    # another task mid-crash). Funds stay safe: release the
                    # bond WITHOUT reward (the task never completed; the
                    # default release_bond would mint an unearned REWARD),
                    # close the task for re-posting, log loudly.
                    mech.release_bond(self.profiles, locked_holder, tid,
                                      reward=0.0)
                    self.log("assign_aborted", task_id=tid,
                             locked_for=f"bidder-{locked_holder}",
                             cleared=w2, replay=True)
                    a.state = "CLOSED"
                    self.done.add(tid)
                    resumed["closed"] += 1
                    continue
                a.winner, a.price_paid = w2, price2
                a.assign_ts = now
                self._publish_assign(a, w2, amount2, price2, reveal2, ties2,
                                     mech.BOND, republished=True)
                self.log("assigned", task_id=tid, winner=w2, amount=amount2,
                         price_paid=price2, bond=mech.BOND, reveal=reveal2,
                         tie=(ties2 if len(ties2) > 1 else []),
                         recovered=True, replay=True)
                heapq.heappush(self.timers,
                               (now + a.timeout_ms / 1000.0,
                                "exec_timeout", tid))
                a.state = "ASSIGNED"
                self.log("replay_resumed_assigned", task_id=tid, winner=w2)
                resumed["assigned"] += 1
                resumed["recovered"] += 1
            elif a.deadline <= now:
                # historical open auction, window long past: close in
                # memory WITHOUT publishing (the replay-burst fix).
                a.state = "CLOSED"
                self.done.add(tid)
                self.log("replay_expired", task_id=tid,
                         bids=len(a.bids))
                resumed["expired"] += 1
            else:
                self.log("replay_resumed_open", task_id=tid,
                         bids=len(a.bids))
                resumed["open"] += 1
        # ----- debate chase rule: rebuild open debates, re-arm timers --
        # ----- attestation gate: record first activation ---------------
        self.attestation_gate_ts = gate_ts
        if self.attestation_gate_ts <= 0:
            # First run with the gate: bids already in flight
            # (mtime < now) are grandfathered exactly once.
            self.attestation_gate_ts = now
            self.log("attestation_gate_live",
                     note="knowledgebase-attestation gate active; bids "
                          "without kb_attestation are rejected (SPEC §10)")
        self.debate_req_seen = debate_req_seen
        for did, db in debates_build.items():
            if db["settled"]:
                continue
            d = Debate(did, db["question"], db["opener"], db["wanted"],
                       db["soft_ms"], db["hard_ms"], db["opened_ts"],
                       kind=db.get("kind", "debate"))
            d.replies.update(db["replies"])
            d.evidence.update(db.get("evidence", {}))
            d.state = db["state"]
            d.chased = db["chased"]
            self.debates[did] = d
            n = len(d.replies)
            if n >= DEBATE_QUORUM:
                # quorum reached while down: settle now, once
                self._settle_debate(d, "quorum", replay=True)
            elif d.hard_ts <= now:
                # hard deadline passed while down: settle once. The chase
                # invariant is enforced inside _settle_debate.
                self._settle_debate(
                    d, "quorum" if n >= DEBATE_QUORUM else "no_quorum",
                    replay=True)
            else:
                if d.state == "OPEN":
                    heapq.heappush(
                        self.timers,
                        (d.soft_ts if d.soft_ts > now else now,
                         "debate_chase", did))
                heapq.heappush(self.timers, (d.hard_ts, "debate_hard",
                                             did))
        self.log("replay_done", **resumed)

    # ----- self-healing channel watch (2026-09-20) -----
    # Same dir-replacement deafness as the bidders (observed 08:23:50 MDT:
    # bid-market dir replaced, all watches orphaned). The oracle arms a
    # watch on CHANNEL and its parent; every select wakeup verifies the
    # watched identity and re-arms on mismatch, then re-ingests recent
    # channel files (ingest is idempotent; replay=True).

    def _arm_channel(self, mask=None):
        old = self._watch
        if old is not None:
            try:
                os.close(old[0])
            except OSError:
                pass
        fd = inotify_init(CHANNEL, mask=mask)
        st = os.stat(CHANNEL)
        self._watch = (fd, CHANNEL, st.st_dev, st.st_ino, mask)

    def _arm_parent(self):
        old = self._pwatch
        if old is not None:
            try:
                os.close(old[0])
            except OSError:
                pass
        parent = CHANNEL.parent
        mask = (IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE | IN_DELETE
                | IN_MOVED_FROM)
        fd = inotify_init(parent, mask=mask)
        st = os.stat(parent)
        self._pwatch = (fd, parent, st.st_dev, st.st_ino, mask)

    def _check_channel(self):
        """Verify the channel + parent watches still point at the same
        directories; re-arm and re-ingest on mismatch. True if re-armed."""
        rearmed = False
        for slot in ("_watch", "_pwatch"):
            entry = getattr(self, slot)
            fd, path, dev, ino, mask = entry
            try:
                st = os.stat(path)
                if (st.st_dev, st.st_ino) == (dev, ino):
                    continue
            except OSError:
                pass  # dir vanished entirely - re-arm below anyway
            if slot == "_watch":
                self._arm_channel(mask=mask)
            else:
                self._arm_parent()
            rearmed = True
        if rearmed:
            self.log("watch_rearm")
            now = time.time()
            for name in sorted(os.listdir(CHANNEL))[-100:]:
                if SEQ_RE.match(name):
                    self.ingest(name, replay=True)
            if now - self._last_rearm_note > 60:
                self._last_rearm_note = now
                self.fleet_note(
                    "oracle-market: channel watch went deaf (dir replaced?) "
                    "- re-armed and re-ingested recent messages.")
        return rearmed

    def run(self):
        self.log("loop_start", pid=os.getpid(), identity=FROM)
        self.reconstruct()
        self._arm_channel()
        self._arm_parent()
        # Startup kick: if the market is idle after replay and the backlog
        # holds queued work, launch the first auction now -- no settlement
        # will ever re-trigger the pump for the current idle state.
        # Defensive: never break startup.
        try:
            if not any(a.state in ("OPEN", "ASSIGNED")
                       for a in self.auctions.values()):
                self._pump_backlog()
        except Exception as e:
            self.log("backlog_startup_pump_error", reason=str(e))
        # self-pipe: SIGTERM/SIGINT writes a byte so the select() below
        # wakes immediately even with no timers and no channel events
        # (no timeout-polling to notice shutdown).
        self._wake_r, self._wake_w = os.pipe()
        for pfd in (self._wake_r, self._wake_w):
            flags = fcntl.fcntl(pfd, fcntl.F_GETFL)
            fcntl.fcntl(pfd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        try:
            while self.running:
                for name in inotify_names(self._watch[0]):
                    self.ingest(name)
                # Drain the parent watch too: an undrained inotify fd stays
                # readable forever -> select() spins at ~97% CPU
                # (2026-09-20). Parent events carry no messages; healing
                # stays in _check_channel().
                inotify_names(self._pwatch[0])
                # drain any wake bytes
                try:
                    while os.read(self._wake_r, 64):
                        pass
                except OSError:
                    pass
                now = time.time()
                while self.timers and self.timers[0][0] <= now:
                    _, kind, tid = heapq.heappop(self.timers)
                    if kind == "bid_close":
                        self.close_bidding(tid)
                    elif kind == "exec_timeout":
                        self.exec_timeout(tid)
                    elif kind == "debate_chase":
                        self.debate_chase(tid)
                    elif kind == "debate_hard":
                        self.debate_hard(tid)
                timeout = self.timers[0][0] - time.time() if self.timers else None
                if timeout is not None and timeout < 0:
                    timeout = 0
                fds = [self._watch[0], self._pwatch[0], self._wake_r]
                # deadline timeout is legitimate (timers), not polling
                select.select(fds, [], [], timeout)
                self._check_channel()
        finally:
            for entry in (self._watch, self._pwatch):
                if entry is not None:
                    try:
                        os.close(entry[0])
                    except OSError:
                        pass
            os.close(self._wake_r)
            os.close(self._wake_w)
            self.log("loop_stop")


def main():
    OracleLoop().run()


if __name__ == "__main__":
    main()
