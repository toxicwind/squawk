import json
import time
import random
import os

class OracleMarketSimulator:
    def __init__(self):
        self.tasks = []
        self.idle_threshold = 5  # seconds
        self.last_task_time = time.time()

    def check_market_status(self):
        """Simulates checking the oracle market for open tasks."""
        # In a real scenario, this would query an external API
        # Here, we simulate an idle market 90% of the time
        if random.random() < 0.9:
            return "IDLE"
        else:
            return "ACTIVE"

    def generate_emergent_task(self):
        """Generates a new emergent task when the market is idle."""
        task_id = f"EMERGENT-{int(time.time())}"
        task_type = random.choice(["OPTIMIZE", "REFLECT", "GENERATE"])
        task_description = f"Self-directed {task_type} task due to market idleness."
        
        new_task = {
            "id": task_id,
            "type": task_type,
            "description": task_description,
            "status": "OPEN",
            "created_at": time.time()
        }
        self.tasks.append(new_task)
        self.last_task_time = time.time()
        return new_task

    def run_loop(self, max_iterations=5):
        """Runs the recursive loop."""
        for i in range(max_iterations):
            status = self.check_market_status()
            if status == "IDLE":
                elapsed = time.time() - self.last_task_time
                if elapsed > self.idle_threshold:
                    print(f"Iteration {i+1}: Market IDLE. Generating emergent task...")
                    new_task = self.generate_emergent_task()
                    print(f"Generated Task: {json.dumps(new_task, indent=2)}")
                    # Simulate processing the task
                    time.sleep(1)
                else:
                    print(f"Iteration {i+1}: Market IDLE (recently active). Waiting...")
                    time.sleep(1)
            else:
                print(f"Iteration {i+1}: Market ACTIVE. Processing external task...")
                time.sleep(1)
        
        print("Loop completed.")
        return self.tasks

if __name__ == "__main__":
    simulator = OracleMarketSimulator()
    tasks = simulator.run_loop()
    
    # Save results to a file
    with open("oracle_results.json", "w") as f:
        json.dump(tasks, f, indent=2)
    print("Results saved to oracle_results.json")
