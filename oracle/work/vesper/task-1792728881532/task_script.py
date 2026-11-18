"""
Oracle Market Simulator
Generates synthetic tasks and simulates the recursive emergent mandate loop.
"""

import json
import time
import random
from datetime import datetime

class OracleMarketSimulator:
    def __init__(self):
        self.market_state = "idle"
        self.task_queue = []
        self.completed_tasks = []
        self.iteration_count = 0

    def generate_emergent_task(self):
        """Simulates the market generating a new task."""
        task_id = f"task-{int(time.time() * 1000)}"
        task_type = random.choice(["data_analysis", "code_refactor", "market_query"])
        task = {
            "id": task_id,
            "type": task_type,
            "status": "open",
            "created_at": datetime.now().isoformat(),
            "description": f"Simulated {task_type} task for recursive testing."
        }
        self.task_queue.append(task)
        self.market_state = "active"
        return task

    def apply_solution(self, task_id, solution_summary):
        """Simulates applying a solution to a task."""
        for task in self.task_queue:
            if task["id"] == task_id:
                task["status"] = "completed"
                task["solution"] = solution_summary
                self.completed_tasks.append(task)
                self.task_queue.remove(task)
                return True
        return False

    def run_loop(self, iterations=3):
        """Runs the recursive loop for a set number of iterations."""
        for i in range(iterations):
            self.iteration_count += 1
            print(f"[Loop Iter {i+1}] Checking market...")
            
            if not self.task_queue:
                print("  Market idle. Generating emergent task...")
                new_task = self.generate_emergent_task()
                print(f"  Generated task: {new_task['id']}")
                
                # Simulate applying a solution
                print(f"  Applying solution to {new_task['id']}...")
                self.apply_solution(new_task['id'], f"Resolved via emergent protocol iter {i+1}")
                print(f"  Task {new_task['id']} completed.")
            else:
                print(f"  Market active. {len(self.task_queue)} tasks pending.")
            
            time.sleep(0.1) # Simulate processing time

        return {
            "total_iterations": self.iteration_count,
            "tasks_completed": len(self.completed_tasks),
            "final_state": self.market_state
        }

if __name__ == "__main__":
    sim = OracleMarketSimulator()
    results = sim.run_loop(iterations=3)
    print("\nSimulation Results:")
    print(json.dumps(results, indent=2))
