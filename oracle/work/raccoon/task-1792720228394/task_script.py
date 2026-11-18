#!/usr/bin/env python3
"""
delend-drift-check: Reconciles Pens doctrine with filesystem reality.
Part of the recursive emergent mandate for toxicwind/Pens.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Configuration
ESTATE_ROOT = Path("/home/toxic/pens/Pens") # Assumed root based on context
AGENTS_MD = ESTATE_ROOT / "AGENTS.md"
BIN_DIR = ESTATE_ROOT / "bin"
RANCH_DIR = ESTATE_ROOT / "ranch"

# Known required artifacts from hindsight
REQUIRED_BINARIES = [
    "delend-oracle",
    "delend-iterate",
    "delend-experimental",
    "delend-code-race",
    "rig-create"
]

REQUIRED_DOCTRINES = [
    "deps-allowed",
    "bun-canary",
    "dig-deeper",
    "delend-experimental multi-divergent race"
]

REQUIRED_SCAFFOLDS = [
    "ranch/pylae/README.md"
]

def check_file_exists(path: Path) -> bool:
    return path.exists()

def check_executable(path: Path) -> bool:
    return path.exists() and os.access(path, os.X_OK)

def parse_agents_md(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        content = path.read_text()
        # Simple heuristic: look for lines containing key doctrines
        found = []
        for line in content.splitlines():
            for doctrine in REQUIRED_DOCTRINES:
                if doctrine.lower() in line.lower():
                    found.append(doctrine)
                    break
        return found
    except Exception as e:
        print(f"Error reading {path}: {e}", file=sys.stderr)
        return []

def check_drifts():
    drifts = []
    
    # 1. Check Binaries
    for binary in REQUIRED_BINARIES:
        bin_path = BIN_DIR / binary
        if not check_executable(bin_path):
            drifts.append({
                "type": "MISSING_BINARY",
                "path": str(bin_path),
                "severity": "HIGH",
                "suggestion": f"Run `rig-create` or rebuild {binary} from source."
            })
    
    # 2. Check Doctrines
    found_doctrines = parse_agents_md(AGENTS_MD)
    for doctrine in REQUIRED_DOCTRINES:
        if doctrine not in found_doctrines:
            drifts.append({
                "type": "MISSING_DOCTRINE",
                "path": str(AGENTS_MD),
                "severity": "MEDIUM",
                "suggestion": f"Update AGENTS.md to include '{doctrine}'."
            })
            
    # 3. Check Scaffolds
    for scaffold in REQUIRED_SCAFFOLDS:
        scaffold_path = ESTATE_ROOT / scaffold
        if not check_file_exists(scaffold_path):
            drifts.append({
                "type": "MISSING_SCAFFOLD",
                "path": str(scaffold_path),
                "severity": "LOW",
                "suggestion": f"Initialize {scaffold} scaffold."
            })
            
    return drifts

def main():
    print(">> Oracle Market: Initiating Drift Check...", file=sys.stderr)
    drifts = check_drifts()
    
    if drifts:
        print(json.dumps(drifts, indent=2))
        print(f"\n>> Oracle Market: {len(drifts)} drift(s) detected. Initiating delend-experimental race.", file=sys.stderr)
        # In a real scenario, this would trigger the experimental agent
        sys.exit(1) # Non-zero exit to signal drift
    else:
        print(json.dumps({"status": "CLEAN", "message": "Pens is reconciled."}))
        print(">> Oracle Market: Pens is clean. No emergent work needed.", file=sys.stderr)
        sys.exit(0)

if __name__ == "__main__":
    main()
