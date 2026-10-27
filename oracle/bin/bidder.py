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
import shutil
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
import keypool as keypool_mod
import mechanism as mech
import sealed as sealed_mod
import mcp_apply as mcp_mod

CHANNEL = ol.CHANNEL
FLEET = ol.FLEET
SEQ_RE = ol.SEQ_RE
PAYLOAD_CAP_S = 590  # hard ceiling per task execution
RALPH_BIN = Path("/home/toxic/.local/bin/super-ralph")
RALPH_CAP_S = 1740  # 29 min ceiling: Super Ralph runs are slow (~11 min
                    # observed for a trivial run)
# 2026-10-13 (osprey root-cause, verified live): kimi-k3-nim 404s on
# :25193. Default to the verified-working executor model.
RALPH_MODEL = os.environ.get("RALPH_MODEL",
                            "openai/gpt-oss-120b")  # 2026-10-19 live bench winner
RALPH_BASE_URL = os.environ.get("RALPH_BASE_URL",
                                "http://127.0.0.1:25193/v1")  # flock (NIM-backed); 2026-10-13 Chris corrective: do NOT use local herd :25100
def _flock_client_key():
    """Read the flock/hodos client key. The flock->hodos rename
    (2026-10-18) moved the data dir: ~/.flock-data is gone, the live key
    sits under ~/.hodos-data (identical copy at ~/.hodos/.flock).
    Try the live homes first, legacy path last; None if unreadable."""
    for p in ('/home/toxic/.hodos-data/client-key.corral',
              '/home/toxic/.hodos/.flock/client-key.corral',
              '/home/toxic/.flock-data/client-key.corral'):
        try:
            with open(p) as f:
                return f.read().strip()
        except OSError:
            continue
    return None

def _cuttinggate_client_key():
    """Read the cuttinggate client key. cuttinggate-serve.sh exports
    CUTTINGGATE_CLIENT_KEY from the vault file /home/toxic/.secrets;
    bidder daemons inherit it in their environment. Fall back to
    parsing that one line out of the vault file (no shell eval) for
    contexts running without the estate env (rig/cron shells).
    None if unreadable."""
    v = os.environ.get("CUTTINGGATE_CLIENT_KEY")
    if v:
        return v.strip()
    try:
        with open("/home/toxic/.secrets") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):].lstrip()
                if line.startswith("CUTTINGGATE_CLIENT_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return None


def _bearer(key):
    """Authorization header value for a raw client key. hodos and
    cuttinggate both require the 'Bearer ' scheme prefix; a bare key
    gets 401 'missing or invalid proxy API key' (route 2 of
    _one_shot_call sent RALPH_API_KEY bare until 2026-10-19)."""
    if not key:
        return ""
    return key if key.startswith("Bearer ") else "Bearer " + key


# cuttinggate's auth gate requires a "Bearer " prefix (any non-empty value;
# the upstream key comes from cuttinggate's own credential plane).
RALPH_API_KEY = os.environ.get("RALPH_API_KEY", "oracle-market-bidder")
# 2026-10-13 (vesper): when routing via flock, use the flock client key.
# Read at startup from the 0600 key file; never hardcoded.
if '127.0.0.1:25193' in RALPH_BASE_URL:
    _k = _flock_client_key()
    if _k:
        RALPH_API_KEY = _k
OUT_CAP = 8000
ERR_CAP = 2000
PARTIAL_CAP = 65536  # bound for the on-disk partial-output evidence file
RALPH_POST_BUFFER_S = 30.0  # time to preserve evidence + post result
CORRAL_CLI = Path("/home/toxic/estate/ranch/corral/src/cli/index.ts")
CORRAL_CAP_S = 1740  # same class as super-ralph: agentic runs are slow

# ---- orphaned smithers worktree sweep (2026-10-19, scout T1) ----
# Smithers <Worktree> uses deterministic paths /tmp/workflow-wt-<ticket-id>
# and ADOPTS an existing dir there. Ticket ids are generic step names reused
# across tasks and days, so when a parent run dir (e.g. ~/.corral/runs/*) is
# cleaned but its /tmp worktree survives, the worktree's .git file dangles:
# it points at a gitdir that no longer exists, git/jj can never resolve it,
# and every later run hitting that ticket id fails all attempts permanently
# (research-1792445323109: settled no-result on BOTH corral and ralph lanes).
# A worktree whose gitdir target is GONE is orphaned by definition -- no
# live run can own it (a live run's gitdir exists). Remove only those, and
# only when untouched for >120s (creation-race guard).
WORKTREE_ORPHAN_AGE_S = 120


def _task_root(p):
    """The oracle task dir (…/oracle/work/<bidder>/<task>) containing
    path p, or None when p is not inside one."""
    parts = Path(p).parts
    for i in range(len(parts) - 1):
        if parts[i] == "oracle" and parts[i + 1] == "work":
            if len(parts) > i + 3:
                return str(Path(*parts[:i + 4]))
            return None
    return None


def sweep_orphaned_worktrees(own_workdir=None):
    """Remove orphaned /tmp/workflow-wt-* dirs; return count removed.

    own_workdir: the task workdir of the run about to start. When
    given, a worktree whose repo pointers resolve into a DIFFERENT
    task's workdir (a satellite of that task's repo) is also
    removed: adopting it gets jj's root-resolution refusal and the
    run stalls (research-1792445323109)."""
    import glob as _glob
    removed = 0
    now = time.time()
    for path in _glob.glob("/tmp/workflow-wt-*"):
        try:
            gitfile = Path(path) / ".git"
            if not gitfile.is_file():
                continue
            lines = gitfile.read_text(encoding="utf-8").splitlines()
            if not lines or not lines[0].startswith("gitdir: "):
                continue
            target = lines[0][len("gitdir: "):].strip()
            if not os.path.exists(target):
                if now - os.path.getmtime(path) < WORKTREE_ORPHAN_AGE_S:
                    continue  # creation-race guard
                shutil.rmtree(path, ignore_errors=True)
                if not os.path.exists(path):
                    removed += 1
                continue
            # Satellite check (finch, 2026-10-19): the dir's repo
            # pointers may resolve into a DIFFERENT task's workdir
            # (observed live: /tmp/workflow-wt-update-progress is a
            # satellite of forge/task-1790943731163's repo). Only the
            # owning task's own runs may keep such a dir.
            if own_workdir is not None:
                _pointers = [target]
                _jjrepo = Path(path) / ".jj" / "repo"
                try:
                    if _jjrepo.is_file():
                        _p = _jjrepo.read_text(encoding="utf-8").strip()
                        if _p:
                            _pointers.append(
                                _p if os.path.isabs(_p)
                                else str(Path(path) / ".jj" / _p))
                except Exception:
                    pass
                _own = _task_root(str(own_workdir))
                _foreign = False
                for _ptr in _pointers:
                    _root = _task_root(os.path.realpath(_ptr))
                    if _root and _own and _root != _own:
                        _foreign = True
                if _foreign:
                    if now - os.path.getmtime(path) < WORKTREE_ORPHAN_AGE_S:
                        continue  # creation-race guard
                    shutil.rmtree(path, ignore_errors=True)
                    if not os.path.exists(path):
                        removed += 1
                    continue
            # Gitdir target exists. One poison shape remains (finch,
            # 2026-10-19, audit Stage A): leftover metadata from
            # another repo/context that git does NOT resolve as this
            # dir's repository root. Smithers refuses to overwrite
            # such metadata, its stall detector kills the run, and
            # BOTH executor lanes adopt the same deterministic path
            # -- one poisoned dir fails every lane permanently
            # (research-1792445323109, TASK_STALLED x2). A dir git
            # itself disowns as a workspace root cannot be a live
            # run's worktree; remove it under the same age guard,
            # and only when git's answer is unambiguous.
            if now - os.path.getmtime(path) < WORKTREE_ORPHAN_AGE_S:
                continue  # creation-race guard
            try:
                _top = subprocess.run(
                    ["git", "-C", path, "rev-parse", "--show-toplevel"],
                    capture_output=True, text=True, timeout=10)
                _root = _top.stdout.strip()
            except Exception:
                continue  # cannot prove poison -- leave it alone
            if _top.returncode == 0 and _root and \
                    os.path.realpath(_root) == os.path.realpath(path):
                continue  # git owns this workspace root -- live/valid
            shutil.rmtree(path, ignore_errors=True)
            if not os.path.exists(path):
                removed += 1
        except Exception:
            continue
    return removed
CORRAL_BASE_URL = os.environ.get("CORRAL_BASE_URL",
                                "http://127.0.0.1:25193/v1")
                             # before the oracle's exec deadline
# 2026-10-13 (osprey runner-overhead): one-shot fast path for trivial
# probe tasks. The corral ticket pipeline (9 tickets x 9 stages, ~110
# model calls) burns 15-28 min on a 10-line script. One-shot does 1-2
# direct model calls (<3 min) and falls back to corral on failure, so
# complex tasks are never short-changed.
ONE_SHOT_BASE_URL = os.environ.get("ONE_SHOT_BASE_URL",
                                   "http://127.0.0.1:25200/v1")
ONE_SHOT_API_KEY = os.environ.get("ONE_SHOT_API_KEY", "oracle-market-bidder")
# 2026-10-19 (finch, Chris approved): the placeholder default above
# authenticates NOTHING -- cuttinggate rejects it 401 auth_invalid
# (reproduced live). Load the real client key from the vault, the
# same source cuttinggate-serve.sh uses. An explicit ONE_SHOT_API_KEY
# env setting still wins; only the default gets replaced.
if "ONE_SHOT_API_KEY" not in os.environ:
    _ck = _cuttinggate_client_key()
    if _ck:
        ONE_SHOT_API_KEY = _ck
ONE_SHOT_CAP_S = 150.0  # hard ceiling: must stay well under 3 min
ONE_SHOT_PROBE_MAX_CHARS = 2500  # gate: longer prompts always take the pipeline


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
    instead of real newlines -- including MIXED with real newlines
    (observed 2026-10-03: banner line real, body escaped). Canonicalize
    before hash/sign/post so the acceptance parser (and humans) see
    real text. A stray converted backslash-n in prose is harmless to
    the dash-led acceptance parser; a missed conversion rejects
    valid work."""
    if "\\n" in s:
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
    # 2026-10-13: gemini-eap-openai/gemini-3.8-flash and google/gemini-3.8-flash
    # are PHANTOMS -- they do not exist on the router, which SILENTLY
    # SUBSTITUTED meta/llama-3.2-11b-vision-instruct (Wraith diagnosis).
    # Never trust a candidate ID without verifying it in /v1/models.
    # 2026-10-13 (osprey root-cause, verified live): openai/gpt-oss-20b
    # is DEAD -- 200-empty or hang on :25193, "no provider returned valid
    # content" on :25200. nvidia/nemotron-3-ultra-550b-a55b verified 200 +
    # non-empty on both routes. Verified-first ordering; the resolver's
    # non-empty probe promotes whatever actually answers.
    # 2026-10-19 live bench (10 models x trivial + hard probes via :25193):
    # gpt-oss-120b perfect score at ~1s; nemotron-3-super-120b perfect but
    # slower; glm-5.3-flash failed the codegen probe (finish=length, text
    # burned in reasoning). gpt-oss-20b REMOVED (Chris: useless; dominated
    # by 120b on every axis) and nemotron-3-ultra REMOVED (failed codegen,
    # 67s length burn). kimi-k2/deepseek-v4/qwen3-coder/llama-3.3 are all
    # 410-EOL on NVIDIA now.
    # 2026-10-23 (scout, verified live): gpt-oss-120b unserved by every
    # provider (cuttinggate 502 no_provider_serves); nemotron-3-super 404s
    # and glm-5.3-flash hangs on hodos :25193. nemotron-3-ultra-550b-a55b
    # verified 200 + non-empty via hodos direct. Leads until the catalog
    # recovers; the resolver promotes whatever actually answers.
    "nvidia/nemotron-3-ultra-550b-a55b",
    "openai/gpt-oss-120b",
    "nvidia/nemotron-3-super-120b-a12b",
    "z-ai/glm-5.3-flash",
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
    # 2026-10-13: validate candidate IDs against /v1/models. A router that
    # silently substitutes a different model for an unknown ID will pass the
    # probe but run the wrong model. Fail the phantom loudly, never accept
    # silent substitution.
    try:
        mreq = urllib.request.Request(
            base + "/models",
            headers={"Authorization": "Bearer " + RALPH_API_KEY,
                     "User-Agent": "oracle-market-bidder"})
        with urllib.request.urlopen(mreq, timeout=timeout) as mr:
            mdata = json.loads(mr.read().decode("utf-8", "replace"))
        live_ids = {m.get("id") for m in mdata.get("data", []) if m.get("id")}
        phantoms = [c for c in candidates if c not in live_ids]
        if phantoms:
            # 2026-10-23 (scout): advisory only, NOT a filter. hodos :25193
            # flaps: its /v1/models list omits models that serve 200
            # (nemotron-3-ultra verified) and lists models that 404.
            # The non-empty probe below is the real gate; a wrong-model
            # substitution still has to produce the exact probe reply.
            print(f"_resolve_ralph_model: model IDs not in /v1/models: {phantoms} "
                  f"(probing anyway; list is unreliable)", flush=True)
    except Exception as e:
        # If /v1/models is unreachable, proceed to probe (which will fail
        # loudly on connection error rather than silently substituting).
        print(f"_resolve_ralph_model: /v1/models check failed ({e}); probing anyway", flush=True)
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
            # 2026-10-03: a model can answer 200 with choices whose
            # content is EMPTY (the :25200 collapse burned 28 min of
            # retries on one). Require non-empty content, not just a
            # choices array.
            choices = payload.get("choices") or []
            content = ""
            if choices:
                msg = choices[0].get("message") or {}
                content = (msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
            if content:
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
KB_COMMITS_API = ("https://api.github.com/repos/toxicwind/estate"
                  "/commits?path=docs/fleet-knowledgebase.md&per_page=1")
KB_RAW_URL = ("https://raw.githubusercontent.com/toxicwind/"
              "estate/main/docs/fleet-knowledgebase.md")
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

    Seq is allocated via oracle_loop.alloc_channel_seq() (chat_core's
    durable .seqhigh mark under the channel lock), shared with squawk-send
    and the oracle -- the 2026-10-17 fix for duplicate seqs when the
    dir-scan allocator raced the mark allocator.
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
            # Unified allocation (2026-10-17): see
            # oracle_loop.alloc_channel_seq.
            self.seq = ol.alloc_channel_seq(self.dir)
            self.lamport += 1
            parents = [self.last_hash] if self.last_hash else []
            ts = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
            while True:
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
                    self.seq = ol.alloc_channel_seq(self.dir)
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


def _reasoning_params(model, budget=1024, effort="low"):
    """Direct reasoning caps per model family (2026-10-19). See
    patch_reasoning history: gpt-oss effort verified live via :25193;
    nemotron-3 budget/kwargs per NVIDIA docs; glm effort=low
    verified live 2026-10-19 (only knob NIM honors). Unknown families: none."""
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": effort}
    if "nemotron-3" in model:
        return {"reasoning_budget": budget,
                "chat_template_kwargs": {"enable_thinking": True,
                                         "low_effort": True}}
    if "glm" in model:
        # GLM verified live 2026-10-19 (sable probe via :25193):
        # reasoning_effort=low is the ONLY knob NIM honors for GLM —
        # codegen probe went 2000 reasoning tokens / 69.9s / finish=length
        # to 0 reasoning tokens / 2.3s / clean content. medium and minimal
        # are silently ignored (full burn); chat_template_kwargs and
        # thinking={type:disabled} are ignored; top-level enable_thinking
        # and reasoning_budget are rejected with HTTP 400.
        return {"reasoning_effort": "low"}
    return {}


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
        _swept = sweep_orphaned_worktrees(own_workdir=workdir)
        if _swept:
            self.say("%s swept %d orphaned workflow worktree(s) before super-ralph on %s."
                     % (self.name, _swept, tid))
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
        # 2026-10-12 (bruteforce, Chris): the 66s ghost kills one model with
        # empty output. Build the retry chain: resolved winner first, then rest.
        _models_to_try = [_resolve_ralph_model(RALPH_BASE_URL)]
        for _cand in RALPH_MODEL_CANDIDATES:
            if _cand and _cand not in _models_to_try:
                _models_to_try.append(_cand)
        ralph_model = _models_to_try[0]
        renv["NIM_MODEL"] = ralph_model
        renv["ANTHROPIC_DEFAULT_OPUS_MODEL"] = ralph_model
        # 2026-10-02 (oracle-settle-2): super-ralph nim-proxy reads
        # FLOCK_* (not NIM_MODEL). Inherited FLOCK pair (nemotron on
        # :25193) is a dead route -> empty stdout, slashed no-result.
        # 2026-10-13 (osprey root-cause): ghost = empty responses after ~66s
        # on direct :25193 (flock). Working chain is cuttinggate:25200 ->
        # flock:25193 -> vans:20128; :25200 is the entry point and works
        # consistently (3/3), :25193 direct is flaky. Use :25200.
        # (2026-10-13 vesper/Chris: do NOT use :25100 herd local models.)
        renv["FLOCK_BASE_URL"] = "http://127.0.0.1:25200"
        # 2026-10-13 (osprey root-cause): the nim-proxy must run the
        # resolver-verified winner, never a hardcoded ID. Hardcoding
        # gpt-oss-20b here stomped the working model and re-armed the
        # ghost on every super-ralph fallback.
        renv["FLOCK_MODEL"] = ralph_model
        _k = _flock_client_key()
        if _k:
            renv["FLOCK_API_KEY"] = _k
        # 2026-09-21 (tern): the oracle's exec deadline is
        # assign_ts + timeout_ms/1000, but the bidder starts the
        # subprocess after assignment. Without a buffer the oracle
        # always wins the race and the TimeoutExpired handler (with
        # partial-evidence preservation) can never fire. Leave room
        # to preserve evidence and post the partial result.
        ceiling = max(10.0, min(timeout_ms / 1000.0, RALPH_CAP_S)
                    - RALPH_POST_BUFFER_S)
        # 2026-10-12 (bruteforce): retry across models on ghost-empty output.
        _attempt_errs = []
        for _attempt_idx, _try_model in enumerate(_models_to_try):
            if _attempt_idx > 0:
                ralph_model = _try_model
                renv["NIM_MODEL"] = ralph_model
                renv["ANTHROPIC_DEFAULT_OPUS_MODEL"] = ralph_model
                # Reset per-attempt state: a timeout on attempt N must not
                # poison the ghost-empty check on attempt N+1.
                timed_out = False
                rc = None
                self.say("%s RETRY %d/%d ghost-empty, trying %s on %s."
                         % (self.name, _attempt_idx + 1, len(_models_to_try),
                            _try_model, tid))
            else:
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
            # 2026-10-12 (bruteforce): ghost-empty = try next model.
            # Non-empty output (even on failure) or timeout-with-partial = keep.
            _is_ghost_empty = not (out or "").strip() and not timed_out
            if _is_ghost_empty and _attempt_idx < len(_models_to_try) - 1:
                _attempt_errs.append("model %s: %s" % (_try_model, err[:200]))
                continue
            if _attempt_errs:
                err = ("all %d models ghost-empty; " % len(_models_to_try)
                       + " | ".join(_attempt_errs) + " || last: " + err)[:2000]
            break

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

    def _is_trivial_probe(self, task):
        """Conservative trivial-task gate for the one-shot fast path.

        Only probe-tagged, short, explicitly PROBE-labeled prompts qualify --
        complex tasks always take the full pipeline. False negatives (a
        trivial task going corral) cost time; false positives (a complex
        task going one-shot) would cost correctness. This gate is biased
        to false negatives.
        """
        if task.get("exec_mode") == "one-shot":
            return True
        if task.get("exec_mode") != "corral":
            return False
        tags = [str(t).lower() for t in (task.get("tags") or [])]
        if "probe" not in tags:
            return False
        prompt = task.get("payload", "") or ""
        if len(prompt) > ONE_SHOT_PROBE_MAX_CHARS:
            return False
        if "PROBE" not in prompt.upper():
            return False
        return True

    def _one_shot_call(self, model, prompt, timeout=60):
        """Single OpenAI-compatible chat call. Tries :25200 (cuttinggate)
        first, falls back to :25193 (flock direct). Returns content or ""."""
        payload = {"model": model,
                   "messages": [{"role": "user", "content": prompt}],
                   "max_tokens": 4096,
                   "temperature": 0.2}
        payload.update(_reasoning_params(model))
        body = json.dumps(payload).encode()
        plain_body = json.dumps({"model": model,
                                 "messages": [{"role": "user", "content": prompt}],
                                 "max_tokens": 4096,
                                 "temperature": 0.2}).encode()
        routes = [(ONE_SHOT_BASE_URL, _bearer(ONE_SHOT_API_KEY)),
                  ("http://127.0.0.1:25193/v1", _bearer(RALPH_API_KEY))]
        errors = []
        for base, auth in routes:
            try:
                req = urllib.request.Request(
                    base.rstrip("/") + "/chat/completions", data=body,
                    headers={"Content-Type": "application/json",
                             "Authorization": auth,
                             "User-Agent": "oracle-market-bidder"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    payload = json.loads(r.read().decode("utf-8", "replace"))
                choices = payload.get("choices") or []
                content = ""
                if choices:
                    msg = choices[0].get("message") or {}
                    content = (msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
                if content:
                    return content
            except Exception as e:
                if isinstance(e, urllib.error.HTTPError):
                    errors.append("%s -> HTTP %s %s" % (base, e.code, e.reason))
                else:
                    errors.append("%s -> %s: %s" % (base, type(e).__name__, str(e)[:200]))
                # 2026-10-19 (osprey/bruteforce, Chris): name the failure
                # instead of swallowing it. A 400 here may be an upstream
                # rejecting a reasoning field: retry the remaining routes
                # with the plain body. Routes, keys, and fallback order
                # unchanged; the failure now lands in stderr evidence.
                if isinstance(e, urllib.error.HTTPError):
                    print(f"_one_shot_call: route {base} HTTP {e.code} "
                          f"{e.reason}; retrying next route", flush=True)
                else:
                    print(f"_one_shot_call: route {base} "
                          f"{type(e).__name__}: {str(e)[:200]}; "
                          f"retrying next route", flush=True)
                body = plain_body
                continue
        self._last_one_shot_errors = errors
        return ""

    def _run_one_shot(self, task, workdir, env, timeout_ms, t0):
        """One-shot fast path for trivial probe tasks: 1-2 direct model
        calls instead of the ~110-call corral ticket pipeline. Writes any
        script to the workdir, executes it locally, and composes the final
        reply ending with ACCEPTANCE-REPORT. Returns (success, out, err,
        dur) like the other runners; the shared result tail is unchanged.
        """
        tid = task["task_id"]
        prompt = task.get("payload", "") or ""
        (workdir / "prompt.md").write_text(prompt, encoding="utf-8")
        model = _resolve_ralph_model(RALPH_BASE_URL)
        cap = min(ONE_SHOT_CAP_S, max(10.0, timeout_ms / 1000.0 - 30.0))
        self.say("%s one-shot on %s (cap %.0fs, model %s)."
                 % (self.name, tid, cap, model))
        script_prompt = ("You are a coding agent. Do this task:\n\n%s\n\n"
                         "If the task needs a script, output the Python script in a "
                         "```python fenced block. Keep any prose brief."
                         % prompt)
        out1 = self._one_shot_call(model, script_prompt, timeout=60)
        if not out1.strip():
            dur = (time.time() - t0) * 1000
            errs = getattr(self, "_last_one_shot_errors", None)
            if errs:
                return False, "", ("one-shot infra error (call 1): %s" % "; ".join(errs)), dur
            return False, "", "one-shot: model returned empty (call 1)", dur
        exec_note = ""
        m = re.search(r"```python\s*(.*?)```", out1, re.DOTALL)
        if m:
            (workdir / "task_script.py").write_text(m.group(1),
                                                   encoding="utf-8")
            try:
                p = subprocess.run(["python3", "task_script.py"],
                                   cwd=str(workdir), capture_output=True,
                                   text=True, timeout=60)
                exec_note = ("Script task_script.py executed: exit %d\n"
                             "stdout:\n%s\nstderr:\n%s"
                             % (p.returncode, (p.stdout or "")[-2000:],
                                (p.stderr or "")[-500:]))
            except subprocess.TimeoutExpired:
                exec_note = "Script task_script.py timed out after 60s"
            except Exception as e:  # noqa: BLE001
                exec_note = "Script execution failed: %s" % e
        remaining = cap - (time.time() - t0)
        out2 = ""
        if remaining > 20:
            final_prompt = ("Task:\n%s\n\nYour draft answer:\n%s\n\n%s\n\n"
                            "Write the final result: summarize what was done, "
                            "include any JSON output, and end with exactly this "
                            "section:\nACCEPTANCE-REPORT:\n"
                            "- criterion 1: MET - <evidence>\n"
                            "- criterion 2: MET - <evidence>\n"
                            "(one line per acceptance criterion in the task above; "
                            "write UNMET with a reason instead of MET if one fails)"
                            % (prompt, out1[:4000], exec_note))
            out2 = self._one_shot_call(
                model, final_prompt,
                timeout=max(15, min(60, remaining - 5)))
        if not out2.strip():
            out2 = out1 + ("\n\n" + exec_note if exec_note else "")
        dur = (time.time() - t0) * 1000
        (workdir / "oneshot-invocation.txt").write_text(
            "model: %s\nbase_url: %s\nduration_ms: %.1f\n"
            % (model, ONE_SHOT_BASE_URL, dur), encoding="utf-8")
        success = bool(out2.strip())
        err = "" if success else "one-shot: empty output after 2 calls"
        return success, out2[-OUT_CAP:], err, dur


    # ----- first-class MCP apply (2026-10-19, osprey) -----
    # On oracle approval, code changes are applied DIRECTLY to the repo
    # through the Gatehouse MCP proxy -- anchored read -> edit -> verify,
    # every tool call recorded as task evidence. This is the market's
    # native apply mechanism, not an opt-in lane.
    def _wants_mcp_apply(self, task):
        """Default True for code-fix tasks (first-class); an explicit
        task['mcp_apply'] overrides either way."""
        if "mcp_apply" in task:
            return bool(task["mcp_apply"])
        tags = [str(t).lower() for t in (task.get("tags") or [])]
        return "code-fix" in tags

    def _mcp_apply_workdir(self, task, workdir):
        """Apply workdir/edits.json (anchored-edits contract) via MCP."""
        evidence = []
        edits_path = workdir / "edits.json"
        if not edits_path.exists():
            evidence.append({"mcp_apply": "no edits.json from runner; "
                                          "output-text settle as before"})
            return evidence
        try:
            obj = json.loads(edits_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            evidence.append({"mcp_apply": "edits.json unreadable",
                             "error": str(e)[:160]})
            return evidence
        edits = obj.get("edits") if isinstance(obj, dict) else obj
        if not isinstance(edits, list) or not edits:
            evidence.append({"mcp_apply": "edits.json has no edits list"})
            return evidence
        applied, failures = mcp_mod.apply_change_set(edits, evidence)
        (workdir / "mcp-apply-evidence.json").write_text(
            json.dumps(evidence, indent=1)[:PARTIAL_CAP], encoding="utf-8")
        evidence.append({"mcp_apply_summary":
                         "%d/%d applied" % (applied, len(edits))})
        return evidence

    def _run_mcp_apply(self, task, workdir, env, timeout_ms, t0):
        """exec_mode mcp-apply: the model emits anchored edits; they are
        applied DIRECTLY via Gatehouse MCP tools. Chosen deliberately by
        a routing marker -- no corral/super-ralph fallback."""
        tid = task["task_id"]
        prompt = task.get("payload", "") or ""
        (workdir / "prompt.md").write_text(prompt, encoding="utf-8")
        model = _resolve_ralph_model(RALPH_BASE_URL)
        self.say("%s mcp-apply on %s (model %s)."
                 % (self.name, tid, model))
        gen_prompt = (
            "You are a coding agent. Do this task:\n\n%s\n\n"
            "Output ONLY a JSON object: {\"edits\": [{\"path\": "
            "\"<absolute repo path>\", \"old\": \"<exact existing text>\", "
            "\"new\": \"<replacement text>\"}], \"summary\": \"<one line>\"}. "
            "One entry per file change; 'old' must match the file's current "
            "content EXACTLY. If no file changes are needed, output "
            "{\"edits\": [], \"summary\": \"<why>\"}." % prompt)
        out1 = self._one_shot_call(model, gen_prompt, timeout=60)
        evidence = []
        edits, perr = mcp_mod.parse_edits_json(out1)
        if perr:
            dur = (time.time() - t0) * 1000
            evidence.append({"mcp_apply": "model emitted no parseable edits",
                             "error": perr[:160]})
            return False, out1[-OUT_CAP:], "mcp-apply: %s" % perr, dur, evidence
        applied, failures = mcp_mod.apply_change_set(edits, evidence)
        (workdir / "mcp-apply-evidence.json").write_text(
            json.dumps(evidence, indent=1)[:PARTIAL_CAP], encoding="utf-8")
        dur = (time.time() - t0) * 1000
        via = "mcp" if any(e.get("via") == "mcp" for e in evidence) \
            else "local-fallback"
        ok = not failures and applied == len(edits)
        out = ("mcp-apply: %d/%d edits applied via %s.\n%s\n\n"
               "ACCEPTANCE-REPORT:\n- apply: %s"
               % (applied, len(edits), via, out1[:2000],
                  "MET - %d edits applied, evidence attached" % applied if ok
                  else "UNMET - %d failures, see mcp-apply-evidence.json"
                  % len(failures)))
        err = "" if ok else "mcp-apply: %d/%d edits failed" % (len(failures),
                                                               len(edits))
        return ok, out[-OUT_CAP:], err, dur, evidence

    def _run_corral(self, task, workdir, env, timeout_ms, t0):
        """Execute an agentic task via the corral CLI (market primary path).

        Corral is the ticket-driven agent orchestrator (Smithers); the task
        payload IS the ticket prompt. Model calls route through the claude
        NIM shim (CORRAL_BASE_URL, default :25104 estate-scripts router --
        verified live 2026-10-12). Headless stdout carries the final reply.
        On corral failure the caller falls back to super-ralph -- a dead
        backend must never no-result a task another backend could run.
        Returns (success, out, err, dur_ms).
        """
        tid = task["task_id"]
        prompt = task.get("payload", "") or ""
        (workdir / "prompt.md").write_text(prompt, encoding="utf-8")
        _swept = sweep_orphaned_worktrees(own_workdir=workdir)
        if _swept:
            self.say("%s swept %d orphaned workflow worktree(s) before corral on %s."
                     % (self.name, _swept, tid))
        if not CORRAL_CLI.exists():
            dur = (time.time() - t0) * 1000
            return (False, "",
                    "corral CLI not found: %s" % CORRAL_CLI, dur)
        cenv = dict(env)
        cenv["NIM_BASE_URL"] = CORRAL_BASE_URL
        cenv["ANTHROPIC_BASE_URL"] = CORRAL_BASE_URL
        cenv["estate-scripts_ROUTER_URL"] = CORRAL_BASE_URL
        # 2026-10-12 (oracle-repair): the oracle's exec deadline is
        # assign_ts + timeout_ms/1000, but the bidder starts the
        # subprocess after assignment. Leave room to preserve evidence
        # and post the partial result instead of racing the deadline.
        ceiling = max(10.0, min(timeout_ms / 1000.0, CORRAL_CAP_S)
                      - RALPH_POST_BUFFER_S)
        self.say("%s invoking corral on %s (ceiling %.0fs)."
                 % (self.name, tid, ceiling))
        try:
            p = subprocess.run(
                ["bun", str(CORRAL_CLI), "--cwd", str(workdir),
                 "--skip-questions", str(workdir / "prompt.md")],
                cwd=str(workdir), capture_output=True, text=True,
                timeout=ceiling, env=cenv)
            dur = (time.time() - t0) * 1000
            out = (p.stdout or "")[-OUT_CAP:]
            err = (p.stderr or "")[-ERR_CAP:]
            success = p.returncode == 0 and bool((p.stdout or "").strip())
            if not success and not err.strip():
                err = "corral exited %d with empty output" % p.returncode
        except subprocess.TimeoutExpired as te:
            dur = (time.time() - t0) * 1000
            out = ((te.stdout or "") if isinstance(te.stdout, str) else "")
            out = out[-OUT_CAP:]
            err = "corral timeout after %.0fs" % ceiling
            success = False
        (workdir / "corral-invocation.txt").write_text(
            "cli: %s\nbase_url: %s\nceiling_s: %.0f\n"
            "exit: %s\nduration_ms: %.1f\n"
            % (CORRAL_CLI, CORRAL_BASE_URL, ceiling,
               p.returncode if "p" in dir() else "timeout", dur),
            encoding="utf-8")
        return success, out, err, dur

    def execute_task(self, task):
        tid = task["task_id"]
        if tid in self.executed:
            return  # catch-up re-drive must never double-execute
        self.executed.add(tid)
        try:
            self._execute_task_inner(task)
        except Exception:
            import traceback
            tb = traceback.format_exc()
            try:
                wd = ol.WORK / self.id / tid
                wd.mkdir(parents=True, exist_ok=True)
                (wd / "thread-crash.txt").write_text(tb, encoding="utf-8")
            except Exception:
                pass
            try:
                self.say(f"{self.emoji} {self.name}: EXEC THREAD CRASH on {tid}: {tb[-300:]}")
            except Exception:
                pass

    def _execute_task_inner(self, task):
        tid = task["task_id"]
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
        mcp_evidence = []
        try:
            if task.get("exec_mode") == "mcp-apply":
                # 2026-10-19 (osprey): first-class MCP apply -- anchored
                # edits land DIRECTLY via Gatehouse MCP tools. No
                # agentic-lane fallback by design.
                success, out, err, dur, mcp_evidence = self._run_mcp_apply(
                    task, workdir, env, timeout_ms, t0)
            elif task.get("exec_mode") == "direct-only":
                # 2026-10-19 (osprey): explicit no-corral route for
                # execution-stack repairs. One-shot runs ONCE; there
                # is deliberately NO fallback to corral or
                # super-ralph -- routing a repair through the
                # component it repairs only burns bidder runs
                # (intake 2638). A failure here is a real failure.
                success, out, err, dur = self._run_one_shot(
                    task, workdir, env, timeout_ms, t0)
            elif (task.get("exec_mode") == "one-shot"
                    or self._is_trivial_probe(task)):
                # One-shot fast path (2026-10-13): trivial probe tasks skip
                # the corral ticket pipeline (~110 model calls, 15-28 min)
                # for 1-2 direct calls (<3 min). Falls back to corral, then
                # super-ralph, so nothing is ever short-changed.
                success, out, err, dur = self._run_one_shot(
                    task, workdir, env, timeout_ms, t0)
                if not success:
                    self.say("%s one-shot failed on %s (%s); falling back "
                             "to corral." % (self.name, tid, err[:120]))
                    success, out, err, dur = self._run_corral(
                        task, workdir, env, timeout_ms, t0)
                    if not success:
                        self.say("%s corral failed on %s (%s); falling back "
                                 "to super-ralph."
                                 % (self.name, tid, err[:120]))
                        success, out, err, dur = self._run_super_ralph(
                            task, workdir, env, timeout_ms, t0)
            elif task.get("exec_mode") == "corral":
                # Primary agentic path (2026-10-12): corral ticket run,
                # with automatic fallback to super-ralph on corral failure.
                success, out, err, dur = self._run_corral(
                    task, workdir, env, timeout_ms, t0)
                if not success:
                    self.say("%s corral failed on %s (%s); falling back "
                             "to super-ralph." % (self.name, tid, err[:120]))
                    success, out, err, dur = self._run_super_ralph(
                        task, workdir, env, timeout_ms, t0)
                if success and self._wants_mcp_apply(task):
                    # First-class: code-fix runs apply their edits.json
                    # change set DIRECTLY via Gatehouse MCP tools.
                    mcp_evidence = self._mcp_apply_workdir(task, workdir)
            elif task.get("exec_mode") == "super-ralph":
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
                "error": err, "posted_ts": now,
                "mcp_evidence": mcp_evidence}
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
