#!/usr/bin/env python3
"""
delend-health-race: Emergent experimental work.
Probes cell-side services (sshd, kite-listener) and pylae endpoints.
Applies a race strategy: if local config fixes (pylae) resolve faster than
remote cell restoration, prioritize local. Otherwise, flag for remote intervention.
"""

import asyncio
import subprocess
import sys
import json
import os
import time

# Configuration
CELL_HOST = os.getenv("CELL_HOST", "cell.local")
PYLAE_ENDPOINT = os.getenv("PYLAE_ENDPOINT", "http://localhost:3000/health")
TIMEOUT = 5.0

async def probe_sshd():
    """Probe cell-side sshd."""
    start = time.time()
    try:
        # Attempt a non-interactive ssh connection
        proc = await asyncio.create_subprocess_exec(
            "ssh", "-o", "ConnectTimeout=2", "-o", "BatchMode=yes",
            f"root@{CELL_HOST}", "echo 'SSH_OK'"
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        if proc.returncode == 0:
            return {"service": "sshd", "status": "UP", "latency": time.time() - start}
        else:
            return {"service": "sshd", "status": "DOWN", "error": stderr.decode(), "latency": time.time() - start}
    except asyncio.TimeoutError:
        return {"service": "sshd", "status": "TIMEOUT", "latency": time.time() - start}
    except Exception as e:
        return {"service": "sshd", "status": "ERROR", "error": str(e), "latency": time.time() - start}

async def probe_kite_listener():
    """Probe cell-side kite-listener."""
    start = time.time()
    try:
        # Assuming kite-listener is on a known port, e.g., 8080
        proc = await asyncio.create_subprocess_exec(
            "ssh", "-o", "ConnectTimeout=2", "-o", "BatchMode=yes",
            f"root@{CELL_HOST}", "curl -s http://localhost:8080/health"
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        if proc.returncode == 0:
            return {"service": "kite-listener", "status": "UP", "latency": time.time() - start}
        else:
            return {"service": "kite-listener", "status": "DOWN", "error": stderr.decode(), "latency": time.time() - start}
    except asyncio.TimeoutError:
        return {"service": "kite-listener", "status": "TIMEOUT", "latency": time.time() - start}
    except Exception as e:
        return {"service": "kite-listener", "status": "ERROR", "error": str(e), "latency": time.time() - start}

async def probe_pylae():
    """Probe local pylae health endpoint."""
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            PYLAE_ENDPOINT
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        http_code = stdout.decode().strip()
        if http_code == "200":
            return {"service": "pylae", "status": "UP", "latency": time.time() - start}
        else:
            return {"service": "pylae", "status": "DOWN", "http_code": http_code, "latency": time.time() - start}
    except asyncio.TimeoutError:
        return {"service": "pylae", "status": "TIMEOUT", "latency": time.time() - start}
    except Exception as e:
        return {"service": "pylae", "status": "ERROR", "error": str(e), "latency": time.time() - start}

async def main():
    print("Starting health race...")
    results = await asyncio.gather(
        probe_sshd(),
        probe_kite_listener(),
        probe_pylae()
    )
    
    # Determine winner
    up_services = [r for r in results if r["status"] == "UP"]
    if up_services:
        winner = min(up_services, key=lambda x: x["latency"])
        print(json.dumps({"winner": winner, "all_results": results}, indent=2))
    else:
        print(json.dumps({"winner": None, "all_results": results}, indent=2))
        print("No services UP. Flag for manual intervention.")

if __name__ == "__main__":
    asyncio.run(main())
