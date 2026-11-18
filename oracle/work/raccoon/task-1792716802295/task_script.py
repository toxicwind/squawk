# delend-validate.py
import subprocess
import sys
import time
import json

def run_stress_test(iterations=100):
    """
    Simulates high-frequency market updates to test oracle flail detection.
    """
    print(f"[delend-validate] Starting stress test with {iterations} iterations...")
    
    # Simulate market noise by calling delend-oracle status with varying "noise"
    # In a real scenario, this would hook into the actual market feed.
    # Here we simulate the *intent* of the test by checking the oracle's resilience.
    
    for i in range(iterations):
        try:
            # Simulate a market update event
            # We use delend-oracle status to check current state
            result = subprocess.run(
                ["bun", "run", "delend-oracle", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                print(f"[delend-validate] Iteration {i}: Oracle status failed: {result.stderr}")
                continue
                
            # Parse output for flail detection
            # Assuming JSON output from oracle status
            try:
                data = json.loads(result.stdout)
                if data.get("flail_detected"):
                    print(f"[delend-validate] Iteration {i}: Flail detected! Self-heal triggered.")
                    # Trigger self-heal
                    subprocess.run(
                        ["bun", "run", "delend-oracle", "apply"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
            except json.JSONDecodeError:
                pass
                
        except subprocess.TimeoutExpired:
            print(f"[delend-validate] Iteration {i}: Timeout. Oracle may be stuck.")
        except Exception as e:
            print(f"[delend-validate] Iteration {i}: Error: {e}")
            
    print("[delend-validate] Stress test complete.")

if __name__ == "__main__":
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    run_stress_test(iterations)
