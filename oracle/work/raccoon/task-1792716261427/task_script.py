#!/usr/bin/env python3
"""
delend-next-task.py
Simulates the RECURSIVE EMERGENT MANDATE: finding the NEXT task and new emergent experimental work.

This script:
1. Queries the 'oracle market' (simulated here as a structured data source) for pending tasks.
2. Applies the 'standing recursive mandate' (from AGENTS.md) to filter/select tasks.
3. Identifies new emergent experimental work based on 'multi-divergent race' doctrine.
4. Outputs the selected task and experimental work plan.
"""

import json
import sys
import os
from datetime import datetime

# Simulated Oracle Market Data (In a real scenario, this would be an API call)
ORACLE_MARKET_DATA = {
    "pending_tasks": [
        {
            "id": "task-1792716261428",
            "type": "recursive_loop",
            "description": "Reconcile Pens oracle market with standing recursive mandate",
            "priority": "high",
            "status": "open"
        },
        {
            "id": "task-1792716261429",
            "type": "experimental",
            "description": "Implement multi-divergent race for task selection",
            "priority": "medium",
            "status": "open"
        },
        {
            "id": "task-1792716261430",
            "type": "maintenance",
            "description": "Fix reachability re-check for kite-cli keepalive",
            "priority": "low",
            "status": "blocked"
        }
    ],
    "emergent_opportunities": [
        {
            "id": "exp-001",
            "description": "Auto-generate rig scaffolds for new task types",
            "potential_value": 0.85
        },
        {
            "id": "exp-002",
            "description": "Optimize delend-iterate async/await handling",
            "potential_value": 0.72
        }
    ]
}

# Standing Recursive Mandate (from AGENTS.md)
STANDING_MANDATE = {
    "deps_allowed": True,
    "bun_canary_allowed": True,
    "dig_deeper": True,
    "multi_divergent_race": True,
    "rig_auto_populate": True
}

def query_oracle_market():
    """Simulates querying the oracle market for the next task."""
    print("[ORACLE] Querying market for next task...")
    # In reality, this would be an HTTP request to the market API
    return ORACLE_MARKET_DATA

def apply_standing_mandate(tasks, opportunities):
    """Filters tasks and opportunities based on the standing mandate."""
    print("[MANDATE] Applying standing recursive mandate...")
    
    # Filter out blocked tasks unless mandate says otherwise
    active_tasks = [t for t in tasks if t['status'] != 'blocked']
    
    # Prioritize experimental work if multi-divergent race is enabled
    if STANDING_MANDATE.get('multi_divergent_race'):
        # Sort opportunities by potential value
        sorted_opportunities = sorted(opportunities, key=lambda x: x['potential_value'], reverse=True)
        top_opportunity = sorted_opportunities[0] if sorted_opportunities else None
    else:
        top_opportunity = None
        
    return active_tasks, top_opportunity

def select_next_task(active_tasks):
    """Selects the next task based on priority and type."""
    if not active_tasks:
        return None
    
    # Simple heuristic: highest priority, then first in list
    priority_order = {'high': 3, 'medium': 2, 'low': 1}
    sorted_tasks = sorted(active_tasks, key=lambda x: priority_order.get(x['priority'], 0), reverse=True)
    
    return sorted_tasks[0]

def generate_experimental_work(top_opportunity):
    """Generates a plan for new emergent experimental work."""
    if not top_opportunity:
        return None
    
    plan = {
        "opportunity_id": top_opportunity['id'],
        "description": top_opportunity['description'],
        "action": "apply_emergent_experiment",
        "rationale": f"Selected based on multi-divergent race with potential value {top_opportunity['potential_value']}"
    }
    return plan

def main():
    print("=" * 50)
    print("RECURSIVE EMERGENT MANDATE EXECUTION")
    print("=" * 50)
    
    # 1. Query Market
    market_data = query_oracle_market()
    tasks = market_data.get('pending_tasks', [])
    opportunities = market_data.get('emergent_opportunities', [])
    
    # 2. Apply Mandate
    active_tasks, top_opportunity = apply_standing_mandate(tasks, opportunities)
    
    # 3. Select Next Task
    next_task = select_next_task(active_tasks)
    
    # 4. Generate Experimental Work
    experimental_work = generate_experimental_work(top_opportunity)
    
    # 5. Output Results
    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "next_task": next_task,
        "experimental_work": experimental_work,
        "status": "mandate_reconciled"
    }
    
    print("\n[RESULT] Next Task:")
    print(json.dumps(next_task, indent=2))
    
    print("\n[RESULT] New Emergent Experimental Work:")
    print(json.dumps(experimental_work, indent=2))
    
    # Write result to a file for the next loop iteration
    output_file = "next_task_result.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n[OUTPUT] Result written to {output_file}")
    
    return result

if __name__ == "__main__":
    main()
