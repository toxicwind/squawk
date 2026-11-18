import json
import sys
import os
import requests
from datetime import datetime

# Configuration
MARKET_API_URL = os.getenv("ORACLE_MARKET_URL", "http://localhost:8080/api/market")
ESTATE_REPO_PATH = os.getenv("ESTATE_REPO_PATH", "/home/toxic/pens/Pens")
OUTPUT_EDITS_FILE = "edits.json"

def query_oracle_market():
    """
    Queries the oracle market for the next task and emergent experimental work.
    In a real implementation, this would hit the actual API.
    """
    print(f"[ORACLE] Querying market at {MARKET_API_URL}...")
    try:
        # Simulating a request to the oracle market
        # In reality, this would be: response = requests.get(MARKET_API_URL)
        # For this non-interactive simulation, we return a mock response
        mock_response = {
            "next_task": {
                "id": "task-1792716982581",
                "description": "Refactor delend-experimental to support parallel divergent branches",
                "priority": "high",
                "requires": ["delend-experimental", "AGENTS.md"]
            },
            "emergent_work": {
                "type": "experimental",
                "description": "Implement 'time-is-not-a-construct' heuristic in market-loop",
                "file": "agents/weaver/bin/market-loop.ts",
                "change": "Add timestamp normalization logic to prevent stale state detection"
            },
            "status": "active"
        }
        return mock_response
    except Exception as e:
        print(f"[ORACLE] Error querying market: {e}", file=sys.stderr)
        return None

def generate_edits(market_response):
    """
    Generates edits.json based on the market response.
    """
    if not market_response:
        return []

    next_task = market_response.get("next_task", {})
    emergent_work = market_response.get("emergent_work", {})

    edits = []

    # 1. Update AGENTS.md with the new emergent work context
    agents_md_path = os.path.join(ESTATE_REPO_PATH, "AGENTS.md")
    if emergent_work:
        # Simulate adding a note to AGENTS.md
        # In a real scenario, we'd read the file, find the right section, and append
        new_entry = f"\n- **{emergent_work['type']}**: {emergent_work['description']} (Applied via task {next_task.get('id', 'unknown')})"
        edits.append({
            "path": agents_md_path,
            "old": "# AGENTS.md\n\n## Doctrine\n- deps-allowed\n- bun-canary allowed\n- dig-deeper\n",
            "new": "# AGENTS.md\n\n## Doctrine\n- deps-allowed\n- bun-canary allowed\n- dig-deeper\n" + new_entry
        })

    # 2. Update the market-loop.ts file with the experimental change
    market_loop_path = os.path.join(ESTATE_REPO_PATH, "agents/weaver/bin/market-loop.ts")
    if emergent_work and emergent_work.get("file") == "agents/weaver/bin/market-loop.ts":
        # Simulate adding the timestamp normalization logic
        # We assume a placeholder comment exists where the change should be made
        edits.append({
            "path": market_loop_path,
            "old": "// TODO: Implement time normalization\nfunction checkStaleState() {\n  return false;\n}",
            "new": "// Implemented: time-is-not-a-construct heuristic\nfunction checkStaleState() {\n  const now = Date.now();\n  // Normalize timestamps to prevent stale state detection\n  const normalized = now - (now % 1000); // Round to nearest second\n  return normalized < (now - 60000);\n}"
        })

    return edits

def main():
    print("[START] Oracle Recursive Emergent Mandate Loop")
    
    # Step 1: Ask the oracle market for the NEXT task + new emergent experimental work
    market_response = query_oracle_market()
    
    if not market_response:
        print("[ERROR] Failed to get response from oracle market. Exiting.")
        sys.exit(1)

    print(f"[ORACLE] Received next task: {market_response['next_task'].get('id', 'N/A')}")
    print(f"[ORACLE] Received emergent work: {market_response['emergent_work'].get('description', 'N/A')}")

    # Step 2: Reconcile the Pens oracle market with the standing recursive mandate
    # This involves generating the edits.json file
    edits = generate_edits(market_response)

    # Step 3: Write edits.json
    output_data = {"edits": edits}
    with open(OUTPUT_EDITS_FILE, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"[DONE] Edits written to {OUTPUT_EDITS_FILE}")
    print(f"[DONE] Total edits generated: {len(edits)}")

if __name__ == "__main__":
    main()
