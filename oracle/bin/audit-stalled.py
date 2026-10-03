#!/usr/bin/env python3
"""Stalled-task audit: reads the canonical ledger, classifies every task."""
import json, time, sys
from collections import defaultdict

LEDGER = '/home/toxic/estate/ranch/squawk/oracle/ledger/ledger.jsonl'
NOW = time.time()
STALL_SECS = 30 * 60  # 30 min without progress = stalled

TERMINAL = {'settled', 'replay_closed', 'exec_timeout'}

tasks = defaultdict(lambda: {'first': None, 'last': None, 'events': [],
                              'assignee': None, 'settled_ok': None,
                              'verified': False, 'notes': []})
order = []
for line in open(LEDGER):
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except Exception:
        continue
    tid = e.get('task_id')
    if not tid:
        continue
    t = tasks[tid]
    if tid not in order:
        order.append(tid)
    ev = e.get('event')
    ts = e.get('ts') or 0
    if t['first'] is None or ts < t['first']:
        t['first'] = ts
    if t['last'] is None or ts > t['last']:
        t['last'] = ts
    t['events'].append(ev)
    if ev == 'assigned':
        t['assignee'] = e.get('winner')
    if ev == 'settled':
        t['settled_ok'] = bool(e.get('success'))
        t['verified'] = bool(e.get('verified'))
        notes = e.get('notes')
        if notes:
            t['notes'] = notes if isinstance(notes, list) else [notes]

def age_str(secs):
    if secs < 0:
        return 'future?'
    m = int(secs // 60)
    if m < 60:
        return f'{m}m'
    h = m // 60
    if h < 48:
        return f'{h}h{m % 60:02d}m'
    return f'{h // 24}d{h % 24}h'

rows = []
for tid in order:
    t = tasks[tid]
    evs = t['events']
    last_ev = evs[-1]
    age = NOW - (t['first'] or NOW)
    idle = NOW - (t['last'] or NOW)
    if last_ev in TERMINAL:
        status = 'SETTLED_OK' if t['settled_ok'] else 'SETTLED_FAIL'
    elif idle > STALL_SECS:
        status = 'STALLED'
    else:
        status = 'IN_FLIGHT'
    rows.append({'task': tid, 'status': status, 'age': age_str(age),
                 'idle': age_str(idle), 'last_event': last_ev,
                 'n_events': len(evs), 'assignee': t['assignee'],
                 'verified': t['verified'],
                 'note': (t['notes'][0][:120] if t['notes'] else '')})

print(f'ledger_events={sum(len(tasks[t]["events"]) for t in tasks)} tasks={len(tasks)}')
print('== STALLED ==')
for r in rows:
    if r['status'] == 'STALLED':
        print(json.dumps(r))
print('== IN_FLIGHT ==')
for r in rows:
    if r['status'] == 'IN_FLIGHT':
        print(json.dumps(r))
print('== SETTLED_FAIL (last 20) ==')
fails = [r for r in rows if r['status'] == 'SETTLED_FAIL'][-20:]
for r in fails:
    print(json.dumps(r))
ok = sum(1 for r in rows if r['status'] == 'SETTLED_OK')
print(f'== SUMMARY == settled_ok={ok} settled_fail={len([r for r in rows if r["status"]=="SETTLED_FAIL"])} stalled={len([r for r in rows if r["status"]=="STALLED"])} inflight={len([r for r in rows if r["status"]=="IN_FLIGHT"])}')
