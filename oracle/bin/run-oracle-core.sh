#!/bin/bash
# oracle-core daemon entrypoint - started by pitchfork (Pens-scripts/oracle-core)
set -euo pipefail
exec /usr/bin/python3 /home/toxic/pens/Pens/ranch/squawk/oracle/bin/oracle_daemon.py
