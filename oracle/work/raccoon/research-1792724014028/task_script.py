#!/usr/bin/env python3
"""
delend-evaluate: Scores experimental outputs and stores insights.
Usage: delend-evaluate <experiment_id> <score> <insight>
"""
import sys
import json
import os
from datetime import datetime

def main():
    if len(sys.argv) < 4:
        print("Usage: delend-evaluate <experiment_id> <score> <insight>")
        sys.exit(1)

    exp_id = sys.argv[1]
    score = float(sys.argv[2])
    insight = sys.argv[3]
    
    # Determine workspace
    workspace = os.environ.get('DELENDAI_WORKSPACE', '/home/toxic/pens/Pens')
    market_file = os.path.join(workspace, 'market_state.json')
    
    # Load or create market state
    if os.path.exists(market_file):
        with open(market_file, 'r') as f:
            market = json.load(f)
    else:
        market = {"insights": [], "priorities": []}
    
    # Create insight record
    record = {
        "timestamp": datetime.now().isoformat(),
        "experiment_id": exp_id,
        "score": score,
        "insight": insight,
        "status": "stored"
    }
    
    market["insights"].append(record)
    
    # Update priorities if score is high
    if score > 0.8:
        market["priorities"].append({
            "source": exp_id,
            "action": "prioritize_related_experiments",
            "reason": insight
        })
        
    # Save back
    with open(market_file, 'w') as f:
        json.dump(market, f, indent=2)
        
    print(f"Insight stored for {exp_id} with score {score}")
    print(f"Market state updated at {market_file}")

if __name__ == "__main__":
    main()
