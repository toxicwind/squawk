import json
import os

def verify_edits(edits_path):
    if not os.path.exists(edits_path):
        print(f"Error: {edits_path} not found.")
        return False
    
    with open(edits_path, 'r') as f:
        try:
            data = json.load(f)
            if 'edits' not in data:
                print("Error: 'edits' key missing in JSON.")
                return False
            
            for edit in data['edits']:
                if 'path' not in edit or 'old' not in edit or 'new' not in edit:
                    print(f"Error: Invalid edit structure in {edit}")
                    return False
                print(f"Verified edit for: {edit['path']}")
            
            print("All edits verified successfully.")
            return True
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {e}")
            return False

if __name__ == "__main__":
    verify_edits("edits.json")
