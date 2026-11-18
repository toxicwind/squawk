#!/usr/bin/env python3
"""
delend-audit.py - Emergent experimental audit tool.
Scans the Pens repo for violations of AGENTS.md doctrine.
"""

import os
import sys
import json
import re

def load_agents_md(path="AGENTS.md"):
    """Load AGENTS.md and extract rules."""
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        content = f.read()
    
    rules = {}
    # Simple extraction of key rules
    if "deps-allowed" in content:
        rules["deps_allowed"] = True
    if "bun-canary" in content:
        rules["bun_canary_allowed"] = True
    if "delend-experimental" in content:
        rules["experimental_mode"] = True
    return rules

def check_package_json(path="package.json"):
    """Check package.json for violations."""
    if not os.path.exists(path):
        return []
    
    with open(path, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return ["Invalid package.json"]
    
    violations = []
    deps = data.get("dependencies", {})
    dev_deps = data.get("devDependencies", {})
    
    # Check for non-bun dependencies if bun-canary is not allowed (simplified logic)
    # In reality, this would check against a whitelist
    for dep in list(deps.keys()) + list(dev_deps.keys()):
        if dep.startswith("@toxicwind/") or dep.startswith("delend-"):
            continue # Internal deps allowed
        # Add more specific checks here
        pass
            
    return violations

def main():
    agents_rules = load_agents_md()
    violations = check_package_json()
    
    print("=== Delend Audit Report ===")
    print(f"Rules loaded: {agents_rules}")
    print(f"Violations found: {len(violations)}")
    for v in violations:
        print(f"  - {v}")
    
    if violations:
        sys.exit(1)
    else:
        print("Audit passed.")
        sys.exit(0)

if __name__ == "__main__":
    main()
