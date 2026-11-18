#!/usr/bin/env python3
"""
delend-self-heal: Emergent self-heal agent for the Pens oracle.
Inspects git status, fixes broken symlinks, and logs to ledger.
"""

import os
import sys
import subprocess
import json
import datetime

def run_cmd(cmd, check=True):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        return e.stdout.strip(), e.stderr.strip()

def get_git_status():
    """Get git status in porcelain format."""
    stdout, stderr = run_cmd("git status --porcelain")
    return stdout

def fix_broken_symlinks(repo_root):
    """Find and fix broken symlinks in the repo."""
    broken = []
    # Find all symlinks
    stdout, _ = run_cmd(f"find {repo_root} -type l")
    symlinks = stdout.split('\n') if stdout else []
    
    for link in symlinks:
        if not link:
            continue
        # Check if target exists
        if not os.path.exists(link):
            broken.append(link)
            
    return broken

def log_action(action, details):
    """Log action to a local ledger file."""
    ledger_path = os.path.join(os.getcwd(), "agents", "ledger.json")
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "details": details
    }
    
    ledger = []
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path, 'r') as f:
                ledger = json.load(f)
        except json.JSONDecodeError:
            ledger = []
            
    ledger.append(entry)
    
    with open(ledger_path, 'w') as f:
        json.dump(ledger, f, indent=2)
        
    print(f"Logged: {action} - {details}")

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"Running self-heal in {repo_root}")
    
    # 1. Check for broken symlinks
    broken_links = fix_broken_symlinks(repo_root)
    if broken_links:
        print(f"Found {len(broken_links)} broken symlinks.")
        for link in broken_links:
            print(f"  Removing broken symlink: {link}")
            os.remove(link)
        log_action("fix_broken_symlink", f"Removed {len(broken_links)} broken symlinks")
    else:
        print("No broken symlinks found.")
        
    # 2. Check git status for uncommitted changes that might be "flails"
    status = get_git_status()
    if status:
        print(f"Git status (potential flails):\n{status}")
        # In a real scenario, we might auto-stage or commit, but for safety, we just log.
        log_action("git_status_check", "Uncommitted changes detected")
    else:
        print("Git status clean.")
        
    print("Self-heal complete.")

if __name__ == "__main__":
    main()
