#!/usr/bin/env python3
"""Sealed bids + key separation for oracle-market (SPEC.md §1, §2).

One 32-byte master secret per bidder (oracle-held registry, mode 600,
outside the repo). The master is NEVER used directly. Purpose-bound keys
are derived via HKDF-SHA256 (RFC 5869) — this fixes the SPEC draft's
key-separation flaw (one secret casually shared across HMAC and AES-GCM):

  k_hmac = HKDF(master, info="oracle-market/hmac/v1")
  k_seal = HKDF(master, info="oracle-market/seal/v1")

A sealed bid binds (amount, nonce, task_id, bidder_id) — the 1delta-x
binding rule — so bids cannot be lifted across rounds or tasks. task_id
is also the AES-GCM associated data, so the binding is cryptographic,
not just conventional.

Stdlib + `cryptography` (present on yote). No network, no new infra.
"""
import base64
import hashlib
import hmac
import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HMAC_INFO = b"oracle-market/hmac/v1"
SEAL_INFO = b"oracle-market/seal/v1"
BID_TS_TOLERANCE_S = 300  # Stripe-style timestamp window (SPEC §1.2)


def hkdf(master: bytes, info: bytes, length: int = 32) -> bytes:
    """RFC 5869 HKDF-SHA256 (extract with empty salt, then expand)."""
    if len(master) < 16:
        raise ValueError("master secret too short")
    prk = hmac.new(b"\x00" * 32, master, hashlib.sha256).digest()
    okm = b""
    t = b""
    for i in range(1, -(-length // 32) + 1):
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]


def derive_keys(master_hex: str):
    """Return (hmac_key, seal_key) derived from one master secret."""
    master = bytes.fromhex(master_hex.strip())
    return hkdf(master, HMAC_INFO), hkdf(master, SEAL_INFO)


def seal_bid(seal_key: bytes, amount: float, nonce: str,
             task_id: str, bidder_id: str) -> str:
    """AES-GCM-seal one bid. Returns base64(iv || ciphertext+tag)."""
    pt = json.dumps(
        {"amount": amount, "nonce": nonce, "task_id": task_id,
         "bidder_id": bidder_id},
        separators=(",", ":")).encode()
    iv = secrets.token_bytes(12)
    ct = AESGCM(seal_key).encrypt(iv, pt, task_id.encode())
    return base64.b64encode(iv + ct).decode()


def unseal_bid(seal_key: bytes, sealed: str, task_id: str) -> dict:
    """Inverse of seal_bid. Raises on tamper / wrong key / wrong task."""
    raw = base64.b64decode(sealed.encode())
    iv, ct = raw[:12], raw[12:]
    pt = AESGCM(seal_key).decrypt(iv, ct, task_id.encode())
    return json.loads(pt)


def sign_bid(hmac_key: bytes, key_id: str, bid_ts: int,
             task_id: str, nonce: str, sealed: str) -> str:
    """HMAC-SHA256 over the canonical bid envelope (SPEC §1.2)."""
    msg = "\n".join([key_id, str(int(bid_ts)), task_id, nonce, sealed])
    return hmac.new(hmac_key, msg.encode(), hashlib.sha256).hexdigest()


def verify_envelope(hmac_key: bytes, key_id: str, bid_ts,
                    task_id: str, nonce: str, sealed: str,
                    bid_sig: str, now: float):
    """Returns None when the envelope is valid, else a reject reason."""
    try:
        ts = int(bid_ts)
    except (TypeError, ValueError):
        return "bad-bid-ts"
    if abs(now - ts) > BID_TS_TOLERANCE_S:
        return "stale"
    expect = sign_bid(hmac_key, key_id, ts, task_id, nonce, sealed)
    if not hmac.compare_digest(expect, str(bid_sig or "")):
        return "tamper"
    return None


def sign_result(hmac_key: bytes, key_id: str, task_id: str, bidder_id: str,
                result_hash: str, success: bool, duration_ms,
                artifacts=()) -> str:
    """HMAC-SHA256 over the canonical result envelope.

    Results were previously accepted on an unauthenticated body, letting any
    channel writer forge a result as the winner (slash framing via
    success=false, or false settlement via success=true). The signature binds
    (key_id, task_id, bidder_id, result_hash, success, duration_ms,
    artifacts) under the winner's HMAC key; the oracle looks the key up by
    the winner's profile, never from the message. Artifacts are
    verification-affecting (they gate `verified`), so they are bound too:
    without this, anyone who can rewrite a result file could downgrade a
    genuine success into a half-bond slash by appending a bad artifact name.
    """
    art = json.dumps(list(artifacts or []), separators=(",", ":"))
    msg = "\n".join([key_id, task_id, bidder_id, str(result_hash),
                     "1" if success else "0", str(duration_ms), art])
    return hmac.new(hmac_key, msg.encode(), hashlib.sha256).hexdigest()


def verify_result_sig(hmac_key: bytes, key_id: str, task_id: str,
                      bidder_id: str, result_hash, success, duration_ms,
                      artifacts, sig) -> bool:
    """True when the result signature verifies under the winner's HMAC key."""
    expect = sign_result(hmac_key, key_id, task_id, bidder_id,
                         result_hash, success, duration_ms, artifacts)
    return hmac.compare_digest(expect, str(sig or ""))


# ---------------- control-plane authentication (SPEC §1.5) ----------------
# task_post / assign are control-plane messages: whoever can post them can
# mint rewards (self-dealing task_post) or override winners (foreign
# assign). Frontmatter `from:` is a string anyone can spoof, so trust is
# NOT in the from: field — it is in an HMAC under a dedicated control key
# held by the oracle (registry control.key, mode 600, outside the repo).
# The control key is derived into its own purpose-bound key via the same
# HKDF domain separation as bidder keys (SPEC §2.1).
CTL_INFO = b"oracle-market/control/v1"
CTL_TS_TOLERANCE_S = 300  # Stripe-style timestamp window (SPEC §1.2)


def ctl_body_sha256(data: dict) -> str:
    """Canonical digest of the message body. Both poster and verifier
    recompute this from the parsed JSON, so on-disk formatting never
    matters — only the parsed dict does."""
    canon = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def sign_control(ctl_hmac_key: bytes, msg_type: str, task_id: str,
                 body_sha256: str, ctl_ts: int) -> str:
    """HMAC-SHA256 over the canonical control envelope."""
    msg = "\n".join(["oracle-market/control/v1", msg_type, task_id,
                     body_sha256, str(int(ctl_ts))])
    return hmac.new(ctl_hmac_key, msg.encode(), hashlib.sha256).hexdigest()


def verify_control(ctl_hmac_key: bytes, msg_type: str, task_id: str,
                   body_sha256: str, ctl_ts, ctl_sig, now: float) -> bool:
    """True when the control signature is valid and fresh."""
    try:
        ts = int(ctl_ts)
    except (TypeError, ValueError):
        return False
    if abs(now - ts) > CTL_TS_TOLERANCE_S:
        return False
    expect = sign_control(ctl_hmac_key, msg_type, task_id, body_sha256, ts)
    return hmac.compare_digest(expect, str(ctl_sig or ""))
