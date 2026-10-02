#!/bin/bash
# oracle-core daemon entrypoint - started by pitchfork (sovereign/oracle-core)
set -euo pipefail
exec /usr/bin/python3 /home/toxic/estate/projects/range/ranch/oracle/bin/oracle_daemon.py
