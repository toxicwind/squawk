#!/usr/bin/env python3
# bin/delend-experimental-resilience
# Tests the resilience of the kite-listener under simulated failure

import subprocess
import time
import sys

def kill_kite_listener():
    """Simulates a failure by killing the kite-listener process."""
    print("Simulating failure: Killing kite-listener...")
    try:
        subprocess.run(["pkill", "-f", "kite-listener"], check=False)
        print("kite-listener killed.")
    except Exception as e:
        print(f"Failed to kill kite-listener: {e}")

def check_kite_listener():
    """Checks if the kite-listener is running."""
    try:
        result = subprocess.run(["pgrep", "-f", "kite-listener"], capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"Error checking kite-listener: {e}")
        return False

def main():
    print("=== Delend Experimental Resilience Test ===")
    
    # Initial state
    if check_kite_listener():
        print("kite-listener is initially running.")
    else:
        print("kite-listener is initially down.")
    
    # Simulate failure
    kill_kite_listener()
    
    # Wait for the delend-oracle loop to potentially recover
    print("Waiting for delend-oracle loop to recover...")
    time.sleep(10)  # Give the oracle loop time to react
    
    # Check if recovered
    if check_kite_listener():
        print("SUCCESS: kite-listener recovered.")
    else:
        print("FAILURE: kite-listener did not recover.")
    
    print("=== Resilience Test Complete ===")

if __name__ == "__main__":
    main()
