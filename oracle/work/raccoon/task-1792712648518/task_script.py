#!/usr/bin/env python3
"""
delend-experimental: Emergent Apply Agent
Simulates the multi-divergent race for next task discovery.
"""

import asyncio
import json
import logging
import subprocess
import sys
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('delend-experimental')

class DelendExperimentalAgent:
    def __init__(self, repo_root: str = "/home/toxic/pens/Pens"):
        self.repo_root = repo_root
        self.tasks = [
            "bin/delend-oracle status",
            "bin/delend-code-race find",
            "bin/rig-create scaffold"
        ]

    async def run_task(self, cmd: str) -> Dict[str, Any]:
        """Run a single task in the race."""
        logger.info(f"Running task: {cmd}")
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.repo_root
            )
            stdout, stderr = await process.communicate()
            return {
                "cmd": cmd,
                "code": process.returncode,
                "stdout": stdout.decode('utf-8'),
                "stderr": stderr.decode('utf-8')
            }
        except Exception as e:
            logger.error(f"Error running task {cmd}: {e}")
            return {
                "cmd": cmd,
                "code": -1,
                "stdout": "",
                "stderr": str(e)
            }

    async def run_race(self) -> List[Dict[str, Any]]:
        """Run all tasks in parallel (multi-divergent race)."""
        logger.info("Starting multi-divergent race for next task...")
        tasks = [self.run_task(cmd) for cmd in self.tasks]
        results = await asyncio.gather(*tasks)
        logger.info("Race completed.")
        return list(results)

    def analyze_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze race results to determine the next task."""
        successful_tasks = [r for r in results if r["code"] == 0]
        if successful_tasks:
            # Prefer the first successful task
            best_task = successful_tasks[0]
            logger.info(f"Best task found: {best_task['cmd']}")
            return {
                "status": "success",
                "next_task": best_task["cmd"],
                "output": best_task["stdout"]
            }
        else:
            logger.warning("No tasks succeeded.")
            return {
                "status": "failure",
                "next_task": None,
                "output": "All tasks failed."
            }

    async def execute(self) -> Dict[str, Any]:
        """Main execution loop."""
        results = await self.run_race()
        analysis = self.analyze_results(results)
        return analysis

async def main():
    agent = DelendExperimentalAgent()
    result = await agent.execute()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
