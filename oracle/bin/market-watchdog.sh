#!/bin/bash
# market-watchdog launcher - started by pitchfork
set -euo pipefail
exec /usr/bin/python3 /home/toxic/estate/ranch/squawk/oracle/bin/market_watchdog.py
