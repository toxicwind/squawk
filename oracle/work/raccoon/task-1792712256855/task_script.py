import json
import os

def verify_edits(edits_path):
    with open(edits_path, 'r') as f:
        data = json.load(f)
    
    if 'edits' not in data:
        raise ValueError("Missing 'edits' key")
    
    for edit in data['edits']:
        if 'path' not in edit or 'old' not in edit or 'new' not in edit:
            raise ValueError(f"Invalid edit structure: {edit}")
        print(f"Validated edit for: {edit['path']}")
    
    print("All edits validated successfully.")

if __name__ == "__main__":
    verify_edits("edits.json")
