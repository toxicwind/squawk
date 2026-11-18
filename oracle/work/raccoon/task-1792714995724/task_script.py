# File: Pens/bin/bidder.py
# Fixed bidder to handle empty responses from the oracle.

import json
import sys
import os

def handle_empty_response(response_text):
    """
    Handles empty or malformed responses from the oracle.
    Returns a default safe action.
    """
    if not response_text or response_text.strip() == '':
        print("[Bidder] Warning: Empty response from oracle. Defaulting to 'WAIT'.")
        return {"action": "WAIT", "reason": "empty_response"}
    
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        print("[Bidder] Warning: Invalid JSON from oracle. Defaulting to 'WAIT'.")
        return {"action": "WAIT", "reason": "invalid_json"}

def main():
    # Simulate reading from stdin or a file
    input_data = sys.stdin.read()
    
    # In a real scenario, this would be the oracle's response
    # For this fix, we ensure the handler is robust
    result = handle_empty_response(input_data)
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()
