# bidder-fix.py
# Fixes empty-response handling in bidder.py

import json
import sys

def handle_response(response: str) -> dict:
    """
    Handles the response from the oracle market.
    Fixes the empty-response bug by returning a default structure if response is empty.
    """
    if not response or response.strip() == '':
        return {
            "status": "empty",
            "data": None,
            "message": "Empty response from oracle market"
        }
    
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "data": None,
            "message": f"Invalid JSON response: {response}"
        }

if __name__ == "__main__":
    # Simulate empty response
    empty_response = ""
    result = handle_response(empty_response)
    print(json.dumps(result, indent=2))
