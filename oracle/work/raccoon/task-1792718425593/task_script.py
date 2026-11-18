#!/usr/bin/env python3
"""
ranch/pylae/identity_gate.py
Zero-trust origin gate for Tailscale node identity.
Asserts that the current node's identity matches the expected ledger state.
"""

import json
import os
import sys
import hashlib
import subprocess

LEDGER_PATH = os.environ.get("DELEND_LEDGER", "/tmp/delend_ledger.json")
TAILSCALE_STATE_PATH = "/var/lib/tailscale/tailscaled.state"

def get_node_id():
    """Retrieve the current Tailscale node ID."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(result.stdout)
        return data.get("Self", {}).get("ID")
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        print(f"ERROR: Failed to retrieve Tailscale node ID: {e}", file=sys.stderr)
        return None

def get_ledger_state():
    """Load the expected node identity from the ledger."""
    if not os.path.exists(LEDGER_PATH):
        print(f"WARNING: Ledger not found at {LEDGER_PATH}. Creating empty ledger.", file=sys.stderr)
        return {}
    try:
        with open(LEDGER_PATH, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid ledger JSON: {e}", file=sys.stderr)
        return {}

def verify_identity():
    """Verify current node identity against the ledger."""
    current_id = get_node_id()
    if not current_id:
        return False

    ledger = get_ledger_state()
    expected_id = ledger.get("node_id")

    if expected_id and current_id != expected_id:
        print(f"SECURITY: Identity mismatch. Expected: {expected_id}, Got: {current_id}", file=sys.stderr)
        return False

    # Update ledger with current state if it was empty or stale
    if not expected_id:
        ledger["node_id"] = current_id
        ledger["last_verified"] = os.popen("date -u +%Y-%m-%dT%H:%M:%SZ").read().strip()
        with open(LEDGER_PATH, 'w') as f:
            json.dump(ledger, f, indent=2)
        print(f"LEDGER: Updated with new node ID: {current_id}")

    return True

if __name__ == "__main__":
    if verify_identity():
        print("OK: Identity verified.")
        sys.exit(0)
    else:
        print("FAIL: Identity verification failed.")
        sys.exit(1)
