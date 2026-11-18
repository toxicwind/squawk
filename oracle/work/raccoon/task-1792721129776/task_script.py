#!/usr/bin/env python3
"""
bin/kite-keepalive
Manages the lifecycle of kite-cli, implementing keepalive and reconnect logic.
This script acts as a supervisor for kite-cli, ensuring it remains responsive.
It logs status to the delend ledger.
"""

import subprocess
import sys
import time
import signal
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('kite-keepalive.log')
    ]
)
logger = logging.getLogger('kite-keepalive')

KITE_CLI_PATH = os.path.join(os.path.dirname(__file__), '..', 'kite-cli', 'kite-cli')
if not os.path.exists(KITE_CLI_PATH):
    # Fallback for different directory structures
    KITE_CLI_PATH = 'kite-cli'

KEEPALIVE_INTERVAL = 30  # seconds
RECONNECT_DELAY = 5      # seconds
MAX_RESTARTS = 10        # Max restarts before giving up

def run_kite_cli():
    """Run kite-cli and return the process."""
    logger.info("Starting kite-cli...")
    try:
        process = subprocess.Popen(
            [KITE_CLI_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE
        )
        return process
    except FileNotFoundError:
        logger.error(f"kite-cli not found at {KITE_CLI_PATH}")
        sys.exit(1)

def check_process_health(process):
    """Check if the process is still running."""
    return process.poll() is None

def send_keepalive(process):
    """Send a keepalive signal to kite-cli."""
    if process and process.stdin:
        try:
            # Assuming kite-cli accepts a simple keepalive command or heartbeat
            # This is a placeholder; actual implementation depends on kite-cli protocol
            process.stdin.write(b'KEEPALIVE\n')
            process.stdin.flush()
            logger.debug("Keepalive sent.")
        except Exception as e:
            logger.warning(f"Failed to send keepalive: {e}")

def main():
    logger.info("Kite Keepalive Supervisor starting...")
    restart_count = 0
    
    while restart_count < MAX_RESTARTS:
        process = run_kite_cli()
        last_activity = time.time()
        
        try:
            while check_process_health(process):
                # Check for inactivity
                if time.time() - last_activity > KEEPALIVE_INTERVAL:
                    send_keepalive(process)
                    last_activity = time.time()
                
                # Check for unexpected exit
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    logger.warning(f"kite-cli exited with code {process.returncode}")
                    if stderr:
                        logger.error(f"stderr: {stderr.decode()}")
                    break
                
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interrupted by user. Shutting down.")
            if process:
                process.terminate()
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            if process:
                process.terminate()
            break
        
        # Reconnect logic
        restart_count += 1
        logger.info(f"Reconnecting in {RECONNECT_DELAY} seconds... (Attempt {restart_count}/{MAX_RESTARTS})")
        time.sleep(RECONNECT_DELAY)
    
    if restart_count >= MAX_RESTARTS:
        logger.error("Max restarts reached. Giving up.")
        sys.exit(1)

if __name__ == '__main__':
    main()
