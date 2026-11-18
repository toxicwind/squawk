import socket
import json
import sys
from datetime import datetime

def probe_endpoint(host, port, service_name):
    """
    Probes a TCP endpoint to check if it is reachable.
    Returns a dict with status and evidence.
    """
    result = {
        "service": service_name,
        "host": host,
        "port": port,
        "status": "RED",
        "evidence": "",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # 5 second timeout
        sock.connect((host, port))
        result["status"] = "GREEN"
        result["evidence"] = f"Successfully connected to {host}:{port}"
        sock.close()
    except socket.timeout:
        result["evidence"] = f"Connection to {host}:{port} timed out"
    except ConnectionRefusedError:
        result["evidence"] = f"Connection to {host}:{port} refused"
    except Exception as e:
        result["evidence"] = f"Error connecting to {host}:{port}: {str(e)}"
    
    return result

def main():
    endpoints = [
        {"host": "cuttinggate", "port": 25200, "name": "cuttinggate"},
        {"host": "hodos", "port": 25193, "name": "hodos"},
        {"host": "herd router", "port": 25100, "name": "herd router"},
        {"host": "squawk fleet bus", "port": 25147, "name": "squawk fleet bus"}
    ]
    
    results = []
    for ep in endpoints:
        print(f"Probing {ep['name']} ({ep['host']}:{ep['port']})...")
        result = probe_endpoint(ep['host'], ep['port'], ep['name'])
        results.append(result)
        print(f"  Status: {result['status']}")
        print(f"  Evidence: {result['evidence']}")
        print()
    
    # Generate summary
    summary = {
        "task": "Post-outage endpoint verification",
        "timestamp": datetime.utcnow().isoformat(),
        "results": results,
        "overall_status": "GREEN" if all(r["status"] == "GREEN" for r in results) else "RED"
    }
    
    # Output JSON summary
    print("Summary:")
    print(json.dumps(summary, indent=2))
    
    # Write to file
    with open("endpoint_verification_results.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print("\nResults written to endpoint_verification_results.json")

if __name__ == "__main__":
    main()
