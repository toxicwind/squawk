#!/usr/bin/env python3
"""
Experiment Plan: pylae-flail-resilience-race

This script simulates the emergent experimental work to test the resilience
of the Pens-brain market-loop against simulated network partitions.

It does not interact with the real Pens-brain but provides a plan and
simulation logic for the experiment.
"""

import time
import random
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class NetworkFlap:
    """Represents a simulated network partition."""
    duration: float  # seconds
    type: str  # 'short_drop', 'long_drop', 'asymmetric_latency'
    start_time: float = field(default_factory=time.time)

@dataclass
class AgentState:
    """State of a divergent agent."""
    agent_id: str
    status: str  # 'active', 'flailing', 'healing', 'healed'
    last_heartbeat: float = field(default_factory=time.time)

class FlailResilienceSimulator:
    """Simulates the network flaps and agent responses."""

    def __init__(self, num_agents: int = 5):
        self.agents: List[AgentState] = [
            AgentState(agent_id=f"agent-{i}", status="active")
            for i in range(num_agents)
        ]
        self.flaps: List[NetworkFlap] = []
        self.results: List[Dict[str, Any]] = []

    def generate_flaps(self, num_flaps: int = 10) -> List[NetworkFlap]:
        """Generate random network flaps."""
        flaps = []
        for _ in range(num_flaps):
            flap_type = random.choice(['short_drop', 'long_drop', 'asymmetric_latency'])
            if flap_type == 'short_drop':
                duration = random.uniform(0.1, 1.0)
            elif flap_type == 'long_drop':
                duration = random.uniform(1.0, 5.0)
            else:  # asymmetric_latency
                duration = random.uniform(0.5, 2.0)
            flaps.append(NetworkFlap(duration=duration, type=flap_type))
        return flaps

    def simulate_agent_response(self, agent: AgentState, flap: NetworkFlap) -> str:
        """Simulate how an agent responds to a flap."""
        # Simulate detection time
        detection_time = random.uniform(0.05, 0.5)
        if detection_time > flap.duration:
            # Agent didn't detect the flap in time
            agent.status = "flailing"
            return "FLAIL_DETECTED_LATE"
        
        # Simulate healing time
        healing_time = random.uniform(0.1, 1.0)
        if healing_time > flap.duration:
            # Agent couldn't heal in time
            agent.status = "healing"
            return "HEALING_FAILED"
        
        agent.status = "healed"
        return "HEAL_SUCCESS"

    def run_experiment(self, num_flaps: int = 10) -> List[Dict[str, Any]]:
        """Run the full experiment."""
        self.flaps = self.generate_flaps(num_flaps)
        results = []

        for flap in self.flaps:
            flap_results = []
            for agent in self.agents:
                response = self.simulate_agent_response(agent, flap)
                flap_results.append({
                    "agent_id": agent.agent_id,
                    "response": response,
                    "flap_type": flap.type,
                    "flap_duration": flap.duration
                })
                # Reset agent status for next flap
                agent.status = "active"
            results.append({
                "flap_index": len(results),
                "flap_type": flap.type,
                "flap_duration": flap.duration,
                "agent_responses": flap_results
            })
        return results

    def summarize_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize the experiment results."""
        total_flaps = len(results)
        flail_detected_late = 0
        healing_failed = 0
        heal_success = 0

        for flap_result in results:
            for agent_response in flap_result["agent_responses"]:
                if agent_response["response"] == "FLAIL_DETECTED_LATE":
                    flail_detected_late += 1
                elif agent_response["response"] == "HEALING_FAILED":
                    healing_failed += 1
                elif agent_response["response"] == "HEAL_SUCCESS":
                    heal_success += 1

        return {
            "total_flaps": total_flaps,
            "total_agents": len(self.agents),
            "total_responses": total_flaps * len(self.agents),
            "flail_detected_late": flail_detected_late,
            "healing_failed": healing_failed,
            "heal_success": heal_success,
            "success_rate": heal_success / (total_flaps * len(self.agents)) if (total_flaps * len(self.agents)) > 0 else 0
        }

def main():
    print("Starting pylae-flail-resilience-race simulation...")
    simulator = FlailResilienceSimulator(num_agents=5)
    results = simulator.run_experiment(num_flaps=10)
    summary = simulator.summarize_results(results)

    print("\nExperiment Summary:")
    print(json.dumps(summary, indent=2))

    # Save results to a file
    with open("experiment_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nDetailed results saved to experiment_results.json")

if __name__ == "__main__":
    main()
