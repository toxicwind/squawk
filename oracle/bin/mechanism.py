#!/usr/bin/env python3
"""Bidder-profile registry, stake/slash state machine, ledger-derived
reputation for oracle-market (SPEC.md §1.1, §3).

Registry file (oracle-held, OUTSIDE the repo, dir 700 / file 600):
  /home/toxic/.openfang/stake-registry/profiles.toml

Per bidder: key_id (e.g. "forge:v1"), master secret (hex, 32 bytes),
bidder_id, capabilities, max_class, stake, locked bonds.

Slash authority (querais QAIS-25 pattern): slash() takes ONLY task_id and
resolves the assignee from the ledger's assignment row — bidder identity
is never accepted as a parameter, closing "slash the wrong bidder".

Stake lifecycle (MeshBroker §3.2): STAKED -> LOCKED(task_id) -> SETTLED | SLASHED
Slash triggers (§3.3, all objective): no result by deadline; result fails
the verification predicate; committed proof hash != delivered result hash.
Severity tiers (nexaflow decay): abandoning right after assignment slashes
harder (full bond) than a failed attempt (half bond).

Reputation is ledger-derived (§3.4): verified settles minus 2x slashes,
floored at zero. It GATES task classes, never distorts Vickrey clearing
(multiplying confidence by reputation would break strategy-proofness).
"""
import json
import os
import secrets
import time
from pathlib import Path

import tomllib

REGISTRY_DIR = Path(os.environ.get("ORACLE_REGISTRY_DIR",
                                   "/home/toxic/.openfang/stake-registry"))
PROFILES = REGISTRY_DIR / "profiles.toml"
KEYS_DIR = REGISTRY_DIR / "keys"
CONTROL_KEY = REGISTRY_DIR / "control.key"  # control-plane HMAC master (SPEC §1.5)


def control_key_path() -> Path:
    return REGISTRY_DIR / "control.key"


def ensure_control_key() -> str:
    """Return the hex control-plane master secret, creating it once if
    absent. The oracle is the custodian: it calls this at startup; control
    posters (post_task.py) read the same file. Mode 600, outside the repo.
    The master is never used directly — sealed.py derives a purpose-bound
    HMAC key via HKDF (SPEC §2.1)."""
    _ensure_dirs()
    ck = control_key_path()
    if ck.exists():
        master = ck.read_text(encoding="utf-8").strip()
        if len(master) >= 64:
            return master
    master = secrets.token_hex(32)
    ck.write_text(master + "\n", encoding="utf-8")
    os.chmod(ck, 0o600)
    return master

STAKE_DEFAULT = 100.0   # starting collateral per bidder (credits)
BOND = 10.0             # locked per assignment (TrueBit sizing: bond prices
                        # the max extractable value of cheating on one task)
REWARD = 5.0            # released to the winner on verified settle
CLASS_REP = {"low": -10**9, "standard": 0, "high": 5}  # rep gates (§3.4)


def _ensure_dirs():
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(REGISTRY_DIR, 0o700)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(KEYS_DIR, 0o700)


def _toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def provision_bidder(bidder_id: str, capabilities, max_class="standard",
                     stake: float = STAKE_DEFAULT):
    """Create/rotate one bidder profile. Returns (key_id, master_hex)."""
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_-]{1,64}", bidder_id or ""):
        raise ValueError(f"bad bidder_id {bidder_id!r}: [A-Za-z0-9_-] only "
                         f"(registry is hand-written TOML)")
    _ensure_dirs()
    key_id = f"{bidder_id}:v1"
    profiles = load_profiles()
    if bidder_id in profiles:
        # rotation: bump version, old key_id fails closed
        old = profiles[bidder_id].get("key_id", f"{bidder_id}:v1")
        try:
            ver = int(old.rsplit(":v", 1)[1]) + 1
        except (ValueError, IndexError):
            ver = 2
        key_id = f"{bidder_id}:v{ver}"
    master_hex = secrets.token_hex(32)
    key_path = KEYS_DIR / f"{bidder_id}.key"
    key_path.write_text(master_hex + "\n", encoding="utf-8")
    os.chmod(key_path, 0o600)
    profiles[bidder_id] = {
        "key_id": key_id,
        "bidder_id": f"bidder-{bidder_id}",
        "secret": master_hex,
        "capabilities": list(capabilities),
        "max_class": max_class,
        "stake": float(profiles.get(bidder_id, {}).get("stake", stake)),
        "locked": dict(profiles.get(bidder_id, {}).get("locked", {})),
    }
    save_profiles(profiles)
    return key_id, master_hex


_PROFILE_REQUIRED = ("key_id", "bidder_id", "secret")

def validate_profile(bidder_id, profile) -> list:
    """Return problem strings; empty means valid. Every problem names its
    fix (guider) so the operator is never left guessing."""
    if not isinstance(profile, dict):
        return [f"profile is not a table (got {type(profile).__name__}); "
                f"re-provision: python3 bin/mechanism.py --provision {bidder_id} --tags <caps>"]
    problems = []
    for field in _PROFILE_REQUIRED:
        if not profile.get(field):
            problems.append(
                f"missing '{field}'; re-provision: "
                f"python3 bin/mechanism.py --provision {bidder_id} --tags <capabilities>")
    try:
        float(profile.get("stake", 0.0))
    except (TypeError, ValueError):
        problems.append(f"stake={profile.get('stake')!r} not numeric; set stake to a number")
    return problems


def _quarantine_profiles(bad: dict, where: str):
    """Auto-fixer: move malformed profiles aside as JSON (never silently
    dropped) and return the quarantine path. Loud on stdout with the fix."""
    import os as _os
    ts = time.strftime("%Y%m%dT%H%M%S")
    qp = PROFILES.parent / f"quarantine-malformed-{ts}.json"
    with open(qp, "w", encoding="utf-8") as f:
        json.dump({"quarantined_ts": ts, "where": where,
                   "reason": "missing one of %s" % (list(_PROFILE_REQUIRED),),
                   "profiles": bad}, f, indent=2)
    _os.chmod(qp, 0o600)
    print(f"{where}: quarantined malformed profiles {sorted(bad)} -> {qp}; "
          f"re-provision each with: python3 bin/mechanism.py --provision <bidder_id> --tags <caps>",
          flush=True)
    return qp

def load_profiles() -> dict:
    if not PROFILES.exists():
        return {}
    with open(PROFILES, "rb") as f:
        data = tomllib.load(f)
    # 2026-10-12: a malformed profile (e.g. [warden] with only stake=)
    # used to pass load cleanly and then crash save_profiles with
    # KeyError('key_id'), surfacing as no_assign{stake-lock-failed} on
    # EVERY auction -- one bad entry DoS'd the whole market. Validate on
    # load: quarantine malformed entries (data preserved as JSON, never
    # silently dropped) and keep the market running on the valid ones.
    bad = {bid: prof for bid, prof in data.items()
           if validate_profile(bid, prof)}
    if bad:
        _quarantine_profiles(bad, "load_profiles")
        for bid in bad:
            del data[bid]
    return data


def save_profiles(profiles: dict):
    _ensure_dirs()
    # Auto-fixer: one malformed entry must never crash the save and block
    # provisioning for every other bidder. Quarantine the bad ones loudly,
    # persist the valid rest.
    bad = {bid: p for bid, p in profiles.items() if validate_profile(bid, p)}
    if bad:
        _quarantine_profiles(bad, "save_profiles")
        profiles = {bid: p for bid, p in profiles.items() if bid not in bad}
    lines = []
    for bidder_id in sorted(profiles):
        p = profiles[bidder_id]
        lines.append(f"[{bidder_id}]")
        lines.append(f'key_id = "{_toml_escape(p["key_id"])}"')
        lines.append(f'bidder_id = "{_toml_escape(p["bidder_id"])}"')
        lines.append(f'secret = "{_toml_escape(p["secret"])}"')
        caps = ", ".join(f'"{_toml_escape(c)}"' for c in p.get("capabilities", []))
        lines.append(f"capabilities = [{caps}]")
        lines.append(f'max_class = "{_toml_escape(p.get("max_class", "standard"))}"')
        lines.append(f'stake = {float(p.get("stake", STAKE_DEFAULT))}')
        locked = p.get("locked", {}) or {}
        lines.append("locked = {"
                     + ", ".join(f'"{_toml_escape(k)}" = {float(v)}'
                                 for k, v in locked.items()) + "}")
        lines.append("")
    tmp = PROFILES.with_suffix(".toml.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.rename(tmp, PROFILES)


def profile_by_key_id(profiles: dict, key_id: str):
    for p in profiles.values():
        if p.get("key_id") == key_id:
            return p
    return None


# ---------------- stake / slash ----------------

def free_stake(profile: dict) -> float:
    locked = profile.get("locked", {}) or {}
    return float(profile.get("stake", 0.0)) - sum(float(v) for v in locked.values())


def lock_bond(profiles: dict, bidder_id: str, task_id: str, bond: float = BOND):
    p = profiles[bidder_id]
    if free_stake(p) < bond:
        raise ValueError(f"insufficient free stake for {bidder_id}")
    p.setdefault("locked", {})[task_id] = bond
    save_profiles(profiles)


def release_bond(profiles: dict, bidder_id: str, task_id: str,
                 reward: float = REWARD):
    """SETTELED: bond released + task reward, reputation bump via ledger."""
    p = profiles[bidder_id]
    (p.get("locked", {}) or {}).pop(task_id, None)
    p["stake"] = float(p.get("stake", 0.0)) + reward
    save_profiles(profiles)


def slash(profiles: dict, ledger_path: Path, task_id: str,
          reason: str, fraction: float = 1.0):
    """SLASHED: bond -> treasury. Resolves bidder from the ledger's
    assignment row for task_id only (never from a parameter)."""
    assignee = None
    if ledger_path.exists():
        with open(ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("task_id") == task_id and ev.get("event") == "assigned":
                    assignee = (ev.get("winner") or "").removeprefix("bidder-")
    if not assignee or assignee not in profiles:
        return None  # fail closed: no assignment row, no slash
    p = profiles[assignee]
    locked = p.setdefault("locked", {})
    # Fail closed: slash only a bond that was actually locked for this task.
    # Falling back to an unlocked `bond` let anyone slash free stake via a
    # forged assignment/result path (stake framing).
    if task_id not in locked:
        return None
    take = min(float(locked.pop(task_id)) * fraction, float(p.get("stake", 0.0)))
    p["stake"] = float(p.get("stake", 0.0)) - take
    save_profiles(profiles)
    return {"bidder": f"bidder-{assignee}", "task_id": task_id,
            "slashed": round(take, 4), "reason": reason, "ts": time.time()}


# ---------------- reputation (ledger-derived, §3.4) ----------------

def reputation(ledger_path: Path) -> dict:
    """bidder_id -> rep score. Verified settle +1, slash -2, floor 0."""
    rep = {}
    if not ledger_path.exists():
        return rep
    with open(ledger_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            b = ev.get("winner")
            if ev.get("event") == "settled" and b:
                if ev.get("verified"):
                    rep[b] = rep.get(b, 0) + 1
            elif ev.get("event") == "slashed" and ev.get("bidder"):
                b2 = ev["bidder"]
                rep[b2] = max(0, rep.get(b2, 0) - 2)
    return rep


def class_allowed(task_class: str, rep_score: int) -> bool:
    return rep_score >= CLASS_REP.get(task_class, 0)


def audit_registry() -> str:
    """Guider: human-readable registry health report with fix instructions
    for every problem found."""
    lines = ["== oracle bidder registry audit ==",
             f"registry: {PROFILES}"]
    if not PROFILES.exists():
        return "\n".join(lines + [
            "MISSING: no profiles.toml yet.",
            "fix: python3 bin/mechanism.py --provision <bidder_id> --tags probe,research"])
    data = tomllib.load(open(PROFILES, "rb"))
    if not data:
        lines.append("EMPTY: no bidder profiles registered.")
    broken = 0
    for bid in sorted(data):
        problems = validate_profile(bid, data[bid])
        p = data[bid]
        if problems:
            broken += 1
            lines.append(f"BROKEN [{bid}]:")
            for pr in problems:
                lines.append(f"  - {pr}")
        else:
            lines.append(f"OK [{bid}]: key_id={p['key_id']} stake={p.get('stake')} "
                         f"caps={p.get('capabilities')} max_class={p.get('max_class')}")
    qfiles = sorted(PROFILES.parent.glob("quarantine-malformed-*.json"))
    if qfiles:
        lines.append(f"quarantine: {len(qfiles)} file(s), latest {qfiles[-1].name}")
    lines.append("registry healthy." if broken == 0
                 else f"action needed: re-provision the {broken} BROKEN entr(y/ies) above.")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--provision", metavar="BIDDER_ID")
    ap.add_argument("--tags", default="")
    ap.add_argument("--max-class", default="standard")
    ap.add_argument("--reputation", action="store_true")
    ap.add_argument("--provision-control", action="store_true",
                    help="create the control-plane HMAC key if absent "
                         "(SPEC §1.5); prints the key_id fingerprint only, "
                         "never the key")
    ap.add_argument("--ledger", default="")
    ap.add_argument("--audit", action="store_true",
                    help="audit the bidder registry: validate every profile, "
                         "report problems with fix instructions")
    args = ap.parse_args()
    if args.provision_control:
        import hashlib as _h
        master = ensure_control_key()
        print(f"control key ready "
              f"fingerprint={_h.sha256(master.encode()).hexdigest()[:16]}")
    elif args.provision:
        key_id, _ = provision_bidder(
            args.provision,
            [t.strip() for t in args.tags.split(",") if t.strip()],
            max_class=args.max_class)
        print(f"provisioned {args.provision} key_id={key_id}")
    elif args.reputation:
        print(json.dumps(reputation(Path(args.ledger)), indent=1))
    elif args.audit:
        print(audit_registry())
