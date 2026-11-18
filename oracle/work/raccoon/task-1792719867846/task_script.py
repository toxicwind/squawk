#!/usr/bin/env python3
"""
bidder-v2: Robust bidder with retry logic and empty-response handling.
Replaces the broken bidder.py with a resilient implementation.
"""

import time
import random
import sys
import json

class BidderV2:
    def __init__(self, max_retries=3, base_delay=1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def bid(self, endpoint, payload):
        """
        Send a bid to the endpoint with exponential backoff.
        """
        for attempt in range(self.max_retries):
            try:
                # Simulate HTTP request
                # In real implementation, use requests or httpx
                response = self._simulate_request(endpoint, payload)
                
                if response is None or response == "":
                    raise ValueError("Empty response")
                
                return response
            except Exception as e:
                print(f"[bidder-v2] Attempt {attempt + 1} failed: {e}", file=sys.stderr)
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    print(f"[bidder-v2] Retrying in {delay} seconds...", file=sys.stderr)
                    time.sleep(delay)
                else:
                    print(f"[bidder-v2] Max retries reached. Giving up.", file=sys.stderr)
                    return None

    def _simulate_request(self, endpoint, payload):
        """
        Simulate an HTTP request. Replace with actual HTTP call.
        """
        # Simulate occasional empty responses
        if random.random() < 0.3:
            return ""
        return json.dumps({"status": "success", "payload": payload})

if __name__ == "__main__":
    bidder = BidderV2()
    result = bidder.bid("/api/bid", {"amount": 100})
    if result:
        print(f"[bidder-v2] Bid successful: {result}")
    else:
        print("[bidder-v2] Bid failed.", file=sys.stderr)
        sys.exit(1)
