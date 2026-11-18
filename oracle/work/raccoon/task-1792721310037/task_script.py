#!/usr/bin/env python3
"""
bidder.py: Oracle Market Bidder Agent
Handles response parsing and bid submission to the delend oracle.
"""

import sys
import json
import os

def parse_oracle_response(raw_response: str) -> dict:
    """
    Parses the oracle response, handling empty or malformed inputs.
    """
    if not raw_response or not raw_response.strip():
        # FIX: Handle empty response explicitly
        return {"status": "empty", "data": None, "error": "Empty response from oracle"}
    
    try:
        data = json.loads(raw_response)
        return {"status": "success", "data": data, "error": None}
    except json.JSONDecodeError as e:
        return {"status": "error", "data": None, "error": f"JSON decode error: {e}"}

def submit_bid(task_id: str, bid_amount: float, oracle_url: str = None):
    """
    Submits a bid to the oracle market.
    """
    # Placeholder for actual HTTP request logic
    print(f"Submitting bid for task {task_id}: {bid_amount}")
    # In a real implementation, this would POST to oracle_url
    return {"task_id": task_id, "bid": bid_amount, "status": "submitted"}

def main():
    if len(sys.argv) < 3:
        print("Usage: bidder.py <task_id> <bid_amount> [oracle_response_json]")
        sys.exit(1)
    
    task_id = sys.argv[1]
    bid_amount = float(sys.argv[2])
    raw_response = sys.argv[3] if len(sys.argv) > 3 else ""
    
    # Parse response if provided
    parsed = parse_oracle_response(raw_response)
    
    if parsed["status"] == "empty":
        print("Warning: Oracle returned empty response. Proceeding with default bid.")
    elif parsed["status"] == "error":
        print(f"Error parsing oracle response: {parsed['error']}")
        sys.exit(1)
    
    # Submit bid
    result = submit_bid(task_id, bid_amount)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
