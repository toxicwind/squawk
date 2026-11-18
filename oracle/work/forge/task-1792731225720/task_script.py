import json
import os
from datetime import datetime

def create_oracle_market_state():
    """
    Creates the initial oracle market state file.
    """
    state = {
        "market_id": "oracle-market-1792731225720",
        "status": "idle",
        "last_updated": datetime.now().isoformat(),
        "open_tasks": [],
        "next_task_schema": {
            "type": "emergent",
            "description": "Task to be generated when market becomes active",
            "dependencies": []
        },
        "experimental_work": {
            "generator_script": "emergent_task_generator.py",
            "status": "initialized"
        }
    }
    with open("oracle_market_state.json", "w") as f:
        json.dump(state, f, indent=2)
    return state

def create_emergent_task_generator():
    """
    Creates the emergent task generator script.
    """
    script_content = '''#!/usr/bin/env python3
"""
Emergent Task Generator for Oracle Market
This script analyzes the oracle market state and proposes new tasks
when the market is idle, fulfilling the recursive mandate to "find more to do."
"""

import json
import sys
from datetime import datetime

def load_market_state(filepath="oracle_market_state.json"):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {filepath} not found. Run initialization first.")
        sys.exit(1)

def analyze_idle_state(market_state):
    """
    Analyzes the idle state and proposes a meta-task.
    """
    if market_state.get("status") != "idle":
        return None

    # Since no tasks are open, we generate a meta-task based on the mandate
    meta_task = {
        "task_id": f"meta-task-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "type": "emergent",
        "title": "Initialize Emergent Experimental Framework",
        "description": "Create the infrastructure for tracking emergent tasks and experimental work in the oracle market.",
        "status": "proposed",
        "created_at": datetime.now().isoformat(),
        "dependencies": [],
        "acceptance_criteria": [
            "Market state file exists and is valid JSON",
            "Emergent task generator script exists",
            "Edits contract is updated"
        ]
    }
    return meta_task

def main():
    market_state = load_market_state()
    proposed_task = analyze_idle_state(market_state)

    if proposed_task:
        print("Market is idle. Proposing emergent meta-task:")
        print(json.dumps(proposed_task, indent=2))
        
        # Update market state with proposed task
        market_state["open_tasks"].append(proposed_task)
        market_state["status"] = "active"
        market_state["last_updated"] = datetime.now().isoformat()
        
        with open("oracle_market_state.json", "w") as f:
            json.dump(market_state, f, indent=2)
        
        print("\\nMarket state updated with proposed task.")
    else:
        print("Market is not idle. No meta-task proposed.")

if __name__ == "__main__":
    main()
'''
    with open("emergent_task_generator.py", "w") as f:
        f.write(script_content)
    os.chmod("emergent_task_generator.py", 0o755)

def create_edits_json():
    """
    Creates the edits.json file for the contract.
    """
    edits = {
        "edits": [
            {
                "path": os.path.abspath("oracle_market_state.json"),
                "old": "",
                "new": json.dumps(create_oracle_market_state(), indent=2)
            },
            {
                "path": os.path.abspath("emergent_task_generator.py"),
                "old": "",
                "new": '''#!/usr/bin/env python3
"""
Emergent Task Generator for Oracle Market
This script analyzes the oracle market state and proposes new tasks
when the market is idle, fulfilling the recursive mandate to "find more to do."
"""

import json
import sys
from datetime import datetime

def load_market_state(filepath="oracle_market_state.json"):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {filepath} not found. Run initialization first.")
        sys.exit(1)

def analyze_idle_state(market_state):
    """
    Analyzes the idle state and proposes a meta-task.
    """
    if market_state.get("status") != "idle":
        return None

    # Since no tasks are open, we generate a meta-task based on the mandate
    meta_task = {
        "task_id": f"meta-task-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "type": "emergent",
        "title": "Initialize Emergent Experimental Framework",
        "description": "Create the infrastructure for tracking emergent tasks and experimental work in the oracle market.",
        "status": "proposed",
        "created_at": datetime.now().isoformat(),
        "dependencies": [],
        "acceptance_criteria": [
            "Market state file exists and is valid JSON",
            "Emergent task generator script exists",
            "Edits contract is updated"
        ]
    }
    return meta_task

def main():
    market_state = load_market_state()
    proposed_task = analyze_idle_state(market_state)

    if proposed_task:
        print("Market is idle. Proposing emergent meta-task:")
        print(json.dumps(proposed_task, indent=2))
        
        # Update market state with proposed task
        market_state["open_tasks"].append(proposed_task)
        market_state["status"] = "active"
        market_state["last_updated"] = datetime.now().isoformat()
        
        with open("oracle_market_state.json", "w") as f:
            json.dump(market_state, f, indent=2)
        
        print("\\nMarket state updated with proposed task.")
    else:
        print("Market is not idle. No meta-task proposed.")

if __name__ == "__main__":
    main()
'''
            }
        ]
    }
    with open("edits.json", "w") as f:
        json.dump(edits, f, indent=2)

if __name__ == "__main__":
    create_oracle_market_state()
    create_emergent_task_generator()
    create_edits_json()
    print("All deliverables created successfully.")
