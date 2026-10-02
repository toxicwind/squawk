#!/bin/bash
# oracle-market daemon entrypoint - started by pitchfork
set -euo pipefail
export ORACLE_INTAKE=1
exec /usr/bin/python3 /home/toxic/estate/projects/range/ranch/oracle/bin/oracle_loop.py
