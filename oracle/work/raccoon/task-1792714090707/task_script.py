#!/usr/bin/env python3
"""
Bidder module for delend-oracle.
Fixes empty response by ensuring DELEND_ environment variables are handled.
"""
import os
import sys
import json

def get_bid_params():
    """
    Retrieve bid parameters from environment variables prefixed with DELEND_.
    Returns a dictionary of parameters.
    """
    params = {}
    # List of expected DELEND_ variables
    expected_vars = [
        "DELEND_BID_AMOUNT",
        "DELEND_BID_STRATEGY",
        "DELEND_MAX_LOSS",
        "DELEND_TARGET_ASSET"
    ]
    
    for var in expected_vars:
        value = os.environ.get(var)
        if value is None:
            # Instead of returning empty or crashing, set a default or log warning
            print(f"Warning: {var} not set. Using default.", file=sys.stderr)
            if var == "DELEND_BID_AMOUNT":
                params[var] = "0"
            elif var == "DELEND_BID_STRATEGY":
                params[var] = "conservative"
            elif var == "DELEND_MAX_LOSS":
                params[var] = "0.1"
            elif var == "DELEND_TARGET_ASSET":
                params[var] = "default"
            else:
                params[var] = ""
        else:
            params[var] = value
            
    return params

def main():
    params = get_bid_params()
    # Simulate a bid response
    response = {
        "status": "ok",
        "params": params,
        "message": "Bid parameters retrieved successfully."
    }
    print(json.dumps(response))

if __name__ == "__main__":
    main()
