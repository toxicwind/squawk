#!/usr/bin/env python3
"""Provider key-pool rotation for the oracle-market (SPEC §8).

Many API keys and subscriptions exist; a down key is a routing signal,
not a death certificate and not a config rewrite. The pool keeps ALL
candidate keys, probes each cheaply before routing (first-valid-wins per
call), and revalidates lazily so recovered keys rejoin automatically.

Routing doctrine (Chris): FREE BEATS LOCAL.
  free cloud (OpenRouter free tier, Pollinations, Gemini free tiers)
    > paid cloud
    > local (herd / beellama / herd-local — fallback only, never default)

Pool location (OUTSIDE the repo, dir 700 / files 600):
  /home/toxic/.openfang/key-pool/<provider>.keys   (one key per line, # comments)
  /home/toxic/.openfang/key-pool/health.json       (fingerprints + status ONLY,
                                                    never key values)

Health semantics (per key):
  ok          -> used directly while fresh (ok_until)
  cooldown    -> skipped until cooldown_until, then re-probed on next access
  401/403     -> 300s cooldown (likely-bad key, still retried later)
  402/429     -> 60s cooldown (billing/rate pressure, transient)
  net error   -> 30s cooldown (infra flake)
  revalidation is lazy (on access): no background timers, no polling.

Stdlib only. Probes are fail-fast (short timeouts, first-valid-wins).
Never log or print key values: CLI output is fingerprints only, except
`keypool.py env` which emits KEY='value' lines for shell sourcing into a
payload's environment (source it, do not log it).
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

POOL_DIR = Path(os.environ.get("ORACLE_KEYPOOL_DIR",
                               "/home/toxic/.openfang/key-pool"))
HEALTH_FILE = POOL_DIR / "health.json"
PROBE_TIMEOUT_S = 8

# tier: "free" | "paid" | "local". Priority order is free > paid > local.
PROVIDERS = {
    "openrouter": {
        "tier": "free",
        "env": "OPENROUTER_API_KEY",
        "probe": ("GET", "https://openrouter.ai/api/v1/auth/key",
                  "Bearer {key}"),
    },
    "pollinations": {
        "tier": "free",
        "env": "POLLINATIONS_API_KEY",
        # anonymous free tier: no key file needed; health = endpoint reachability
        "keyless": "anonymous",
        "probe": ("GET", "https://text.pollinations.ai/openai/models", None),
    },
    "gemini": {
        "tier": "free",
        "env": "GEMINI_API_KEY",
        "probe": ("GET",
                  "https://generativelanguage.googleapis.com/v1beta/models"
                  "?key={key}", None),
    },
    "cerebras": {
        "tier": "free",
        "env": "CEREBRAS_API_KEY",
        "probe": ("GET", "https://api.cerebras.ai/v1/models",
                  "Bearer {key}"),
    },
    "groq": {
        "tier": "paid",
        "env": "GROQ_API_KEY",
        "probe": ("GET", "https://api.groq.com/openai/v1/models",
                  "Bearer {key}"),
    },
    "deepseek": {
        "tier": "paid",
        "env": "DEEPSEEK_API_KEY",
        "probe": ("GET", "https://api.deepseek.com/models",
                  "Bearer {key}"),
    },
    "mistral": {
        "tier": "paid",
        "env": "MISTRAL_API_KEY",
        "probe": ("GET", "https://api.mistral.ai/v1/models",
                  "Bearer {key}"),
    },
    "moonshot": {
        "tier": "paid",
        "env": "MOONSHOT_API_KEY",
        "probe": ("GET", "https://api.moonshot.ai/v1/models",
                  "Bearer {key}"),
    },
    "herd": {
        "tier": "local",
        "env": "HERD_URL",
        "keyless": "http://127.0.0.1:25100",
        "probe": ("GET", "http://127.0.0.1:25100/v1/models", None),
    },
    "beellama": {
        "tier": "local",
        "env": "BEELLAMA_URL",
        "keyless": "http://127.0.0.1:25122",
        "probe": ("GET", "http://127.0.0.1:25122/v1/models", None),
    },
}

TIER_ORDER = ["free", "paid", "local"]
COOLDOWN_S = {401: 300, 403: 300, 402: 60, 429: 60}
OK_FRESH_S = 300


def _fp(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _ensure():
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(POOL_DIR, 0o700)
    if not HEALTH_FILE.exists():
        HEALTH_FILE.write_text("{}\n", encoding="utf-8")
    os.chmod(HEALTH_FILE, 0o600)


def load_pool(provider: str) -> list:
    """All candidate keys for a provider, in file order. Never logged."""
    _ensure()
    p = POOL_DIR / f"{provider}.keys"
    if not p.exists():
        return []
    keys = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return keys


def add_key(provider: str, key: str):
    """Append one key to the pool (value never printed)."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}")
    if not key or len(key.strip()) < 8:
        raise ValueError("key too short")
    _ensure()
    p = POOL_DIR / f"{provider}.keys"
    existing = set(load_pool(provider))
    if key.strip() in existing:
        return False
    with open(p, "a", encoding="utf-8") as f:
        f.write(key.strip() + "\n")
    os.chmod(p, 0o600)
    return True


def _health() -> dict:
    _ensure()
    try:
        return json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_health(h: dict):
    tmp = HEALTH_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(h, indent=1) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.rename(tmp, HEALTH_FILE)


def _probe_key(provider: str, key: str):
    """Cheap authenticated probe. Returns (ok: bool, http_status or None)."""
    cfg = PROVIDERS[provider]
    method, url, auth = cfg["probe"][:3]
    url = url.format(key=key)
    headers = {}
    if auth:
        headers["Authorization"] = auth.format(key=key)
    data = None
    if method == "POST":
        payload = cfg["probe"][3]
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_S) as r:
            return r.status < 400, r.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception:
        return False, None


def _record(provider: str, fp: str, ok: bool, status):
    h = _health()
    now = time.time()
    h.setdefault(provider, {})[fp] = {
        "ok": ok,
        "status": status,
        "last_probe": now,
        "ok_until": now + OK_FRESH_S if ok else 0,
        "cooldown_until": 0 if ok else now + COOLDOWN_S.get(status or 0, 30),
    }
    _save_health(h)


def _state(provider: str, fp: str):
    return _health().get(provider, {}).get(fp)


def best_key(provider: str, force_probe: bool = False):
    """First-valid-wins key for one provider, or None.

    Cached-ok keys are used while fresh; stale/cooldown-expired keys are
    re-probed on access, so recovered keys rejoin automatically. A key
    that fails is a routing signal for this call only — never a deletion.
    """
    if provider not in PROVIDERS:
        return None
    cfg = PROVIDERS[provider]
    if cfg.get("keyless") and not load_pool(provider):
        # local/keyless endpoints need no key: health is endpoint
        # reachability, cached like keyed entries (fail-fast on access)
        now = time.time()
        st = None if force_probe else _state(provider, "endpoint")
        if st and st.get("ok") and st.get("ok_until", 0) > now:
            return cfg["keyless"]
        if st and st.get("cooldown_until", 0) > now:
            return None
        ok, status = _probe_key(provider, "")
        _record(provider, "endpoint", ok, status)
        return cfg["keyless"] if ok else None
    now = time.time()
    for key in load_pool(provider):
        fp = _fp(key)
        st = None if force_probe else _state(provider, fp)
        if st and st.get("ok") and st.get("ok_until", 0) > now:
            return key
        if st and st.get("cooldown_until", 0) > now:
            continue  # cooling down; try the next key
        ok, status = _probe_key(provider, key)
        _record(provider, fp, ok, status)
        if ok:
            return key
    return None


def best_any(prefer_tiers=TIER_ORDER):
    """(provider, key_or_url) across all providers by tier priority:
    free cloud > paid cloud > local. None when nothing is healthy."""
    for tier in prefer_tiers:
        for provider, cfg in PROVIDERS.items():
            if cfg["tier"] != tier:
                continue
            k = best_key(provider)
            if k:
                return provider, k
    return None, None


def env_exports() -> dict:
    """Env vars for a payload's environment: each provider's current
    best key under its canonical env name, plus the winning provider.
    Source this into the payload env; do not log it."""
    out = {}
    for provider, cfg in PROVIDERS.items():
        k = best_key(provider)
        if k and not cfg.get("keyless"):
            out[cfg["env"]] = k
        elif k and cfg.get("keyless"):
            out[cfg["env"]] = k
    prov, _ = best_any()
    if prov:
        out["KEYPOOL_BEST_PROVIDER"] = prov
    return out


def probe_all(provider: str = ""):
    """Probe every key; print provider/fingerprint/status (never values)."""
    rows = []
    names = [provider] if provider else list(PROVIDERS)
    for prov in names:
        cfg = PROVIDERS[prov]
        if cfg.get("keyless") and not load_pool(prov):
            ok, status = _probe_key(prov, "")
            rows.append((prov, cfg["tier"], "endpoint", ok, status))
            continue
        for key in load_pool(prov):
            ok, status = _probe_key(prov, key)
            _record(prov, _fp(key), ok, status)
            rows.append((prov, cfg["tier"], _fp(key), ok, status))
    return rows


def main():
    ap_argv = sys.argv[1:]
    if not ap_argv or ap_argv[0] in ("probe", "status"):
        prov = ap_argv[1] if len(ap_argv) > 1 else ""
        for p, tier, fp, ok, status in probe_all(prov):
            print(f"{p:14} {tier:5} {fp:16} "
                  f"{'OK' if ok else 'DOWN'} {status}")
    elif ap_argv[0] == "env":
        # KEY='value' lines for `eval`/`source` into a payload env.
        # Do not log this output.
        for k, v in env_exports().items():
            print(f"{k}='{v}'")
    elif ap_argv[0] == "best":
        prov = ap_argv[1] if len(ap_argv) > 1 else None
        if prov:
            k = best_key(prov)
            print(f"{prov} {_fp(k) if k else 'none'}")
        else:
            p, k = best_any()
            print(f"{p or 'none'} {_fp(k) if k else ''}".strip())
    elif ap_argv[0] == "add" and len(ap_argv) == 3:
        added = add_key(ap_argv[1], ap_argv[2])
        print("added" if added else "already-present")
    else:
        print("usage: keypool.py [probe [provider] | env | best [provider] "
              "| add <provider> <key>]")
        sys.exit(2)


if __name__ == "__main__":
    main()
