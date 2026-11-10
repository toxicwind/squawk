#!/usr/bin/env python3
"""Eval: production hybrid (squawk_page.hybrid_pack) vs the race probe suite,
plus any archive probes appended in probes_archive.json.
Runs on yote. Usage: python3 eval_hybrid.py [extra_probes.json]
"""
import json
import sys
import time

sys.path.insert(0, '/home/toxic/kite/pry-20261019-paging')
import race as R
import squawk_page as SP

idx = SP.load_index('fleet')
probes = list(R.PROBES)
if len(sys.argv) > 1:
    with open(sys.argv[1]) as f:
        probes += [(p['q'], p['seq']) for p in json.load(f)]
print(f'corpus={len(idx["recs"])} probes={len(probes)}')
for budget_tok in (4000, 16000):
    hits, miss = 0, []
    t0 = time.time()
    for qi, (q, aseq) in enumerate(probes):
        res = SP.hybrid_pack(idx, q, budget_tok * 4)
        got = {r['seq'] for r in res['items']}
        if aseq in got:
            hits += 1
        else:
            miss.append(f'Q{qi + 1}({aseq})')
    dt = (time.time() - t0) / len(probes)
    print(f'hybrid @{budget_tok}: {hits}/{len(probes)} '
          f'miss={", ".join(miss) or "none"} avg_s={dt:.3f}')
