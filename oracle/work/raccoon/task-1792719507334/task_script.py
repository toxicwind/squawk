import json
import sys

def simulate_oracle_query(hindsight_context):
    """
    Simulates querying the 'oracle market' for the next task.
    In reality, this would be an API call or local script execution.
    """
    # Simulated response from the oracle
    oracle_response = {
        "next_task": "Apply delend-code-race to fix a bug in kite-cli",
        "emergent_work": "Scaffold new agent module using rig-create",
        "status": "simulated"
    }
    return oracle_response

def reconcile_mandate(oracle_response, standing_mandate):
    """
    Reconciles the oracle's suggestion with the standing mandate.
    """
    # Check if the suggested task is already done
    if "delend helpers built" in standing_mandate:
        print("Note: Delend helpers are already built. Focusing on application.")
    
    return {
        "reconciled_task": oracle_response["next_task"],
        "action": "Simulate execution"
    }

if __name__ == "__main__":
    hindsight = "# hindsight\n- delend helpers built..."
    oracle = simulate_oracle_query(hindsight)
    reconciliation = reconcile_mandate(oracle, hindsight)
    
    print(json.dumps(reconciliation, indent=2))
