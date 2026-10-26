#!/usr/bin/env python3
"""squawk_page — production paging + context-pack service for squawk history.

Runs ON YOTE (awrawr-pc). Stdlib only. Two surfaces:

  page  — cursor-paged history over a channel store. Cursor is the envelope
          identity (seq, filename): 804 fleet filename-seqs are shared by
          distinct messages, so seq alone is NOT a key (JetStream migration
          trap, ranch 9692244). Pages are stable under appends: a cursor
          pins an exact message, new arrivals never shift old pages.

  pack  — C1+C3 hybrid v2 context pack (eval record in the hybrid_pack
          comment): age-blind candidate retrieval (top relevance + top
          surprise x relevance + episode anchors), then ranking by
          relevance / markov surprise / importance with recency as a mere
          tiebreak. An episode-digest header (<= budget/4) indexes the
          unpacked spans by seq range so anything not packed stays
          addressable. Raw history is never mutated — packs are derived
          views over the file store.

Index cache: pickle under CACHE_DIR, rebuilt when the channel dir's file
count changes (cheap stat check per call).
"""
import argparse
import json
import os
import pickle
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import race as R  # proven candidate machinery (tfidf, markov, episodes)

ROOT = os.environ.get('SQUAWK_ROOT', '/home/toxic/.squawk-bus/squawk-root')
CACHE_DIR = os.environ.get('SQUAWK_PAGE_CACHE', '/tmp/squawk_page')


# ---------------- corpus with envelope identity ----------------

def parse_channel(channel):
    d = os.path.join(ROOT, channel)
    files = sorted(f for f in os.listdir(d) if f.endswith('.md'))
    recs = []
    for f in files:
        m = re.match(r'(\d+)-', f)
        if not m:
            continue
        seq = int(m.group(1))
        try:
            txt = open(os.path.join(d, f), encoding='utf-8',
                       errors='replace').read()
        except Exception:
            continue
        meta, body = {}, txt
        if txt.startswith('---'):
            parts = txt.split('---', 2)
            if len(parts) == 3:
                for line in parts[1].split('\n'):
                    if ':' in line:
                        k, v = line.split(':', 1)
                        meta[k.strip()] = v.strip()
                body = parts[2]
        recs.append({'seq': seq, 'file': f, 'sender': meta.get('from', '?'),
                     'ts': meta.get('ts', ''), 'title': meta.get('title', ''),
                     'body': body.strip()})
    # envelope order: (seq, filename) — the dedup-safe identity
    recs.sort(key=lambda r: (r['seq'], r['file']))
    last = None
    for r in recs:
        dt = None
        if r['ts']:
            try:
                dt = datetime.fromisoformat(r['ts'])
            except Exception:
                dt = None
        if dt is None:
            dt = last
        r['dt'] = dt
        if dt is not None:
            last = dt
    recs = [r for r in recs if r['dt'] is not None]
    if recs:
        tmax = max(r['dt'] for r in recs)
        for r in recs:
            r['age_days'] = (tmax - r['dt']).total_seconds() / 86400.0
    return recs, len(files)


def load_index(channel):
    os.makedirs(CACHE_DIR, exist_ok=True)
    d = os.path.join(ROOT, channel)
    nfiles = len([f for f in os.listdir(d) if f.endswith('.md')])
    cache = os.path.join(CACHE_DIR, f'{channel}.pkl')
    if os.path.exists(cache):
        with open(cache, 'rb') as f:
            idx = pickle.load(f)
        if idx.get('nfiles') == nfiles:
            return idx
    recs, n = parse_channel(channel)
    tfidf = R.build_tfidf(recs)
    eps = R.segment_episodes(recs, tfidf)
    mk = R.build_markov(recs, tfidf)
    idx = {'nfiles': n, 'recs': recs, 'tfidf': tfidf,
           'imp': R.importance_scores(recs), 'eps': eps,
           'digests': R.episode_digests(recs, tfidf, eps),
           'markov': mk, 'surprise': R.surprise_vec(mk)}
    with open(cache, 'wb') as f:
        pickle.dump(idx, f, protocol=4)
    return idx


# ---------------- paging ----------------

def page(channel, limit=20, before=None, after=None):
    """One page of history, newest-first. `before`/`after` are cursors
    'seq:filename' (envelope identity). Returns (items, next_before_cursor).
    """
    idx = load_index(channel)
    recs = idx['recs']

    def key(r):
        return (r['seq'], r['file'])

    def parse_cursor(c):
        s, fn = c.split(':', 1)
        return (int(s), fn)

    sel = recs
    if before:
        ck = parse_cursor(before)
        sel = [r for r in sel if key(r) < ck]
    if after:
        ck = parse_cursor(after)
        sel = [r for r in sel if key(r) > ck]
        sel = sel[:limit]
        items = sel
        nxt = None
        return items, nxt
    items = sel[-limit:] if limit else sel
    items = list(reversed(items))
    nxt = None
    if items and len(sel) > len(items):
        last = items[-1]
        nxt = f"{last['seq']}:{last['file']}"
    return items, nxt


# ---------------- hybrid pack v2 (production) ----------------
# Design history (eval-driven, 11 probes = race 8 + 3 archive-era):
#   v1 (C1 composite x surprise multiplier, recency as a full axis):
#     15/22 — the 3d half-life decay let age zero out every archive hit;
#     recency floors (0.15/0.30) rescued only one probe at 16k.
#   v2 (below): TWO STAGES. Candidate retrieval is age-blind (top-200 by
#     pure relevance + top-100 by surprise x relevance + episode anchors),
#     so the archive's best matches are always at the table. Ranking in
#     the candidate set: 0.55 relevance + 0.25 surprise + 0.20 importance,
#     recency demoted to a 0.05 tiebreak — its legitimate role.
#   v2 results: 11/11 @16k, 9/11 @4k (misses Q3/Q5, fresh probes the v1
#     recency axis flattered). Next experiment on file: budget-adaptive
#     decay weight — NOT tuned further against this probe set (overfit).

def hybrid_pack(idx, query, budget_chars, cand_k=200):
    recs = idx['recs']
    n = len(recs)
    texts = [R.msg_text(r) for r in recs]
    rel = R.relevance_scores(query, idx['tfidf'], n)
    rmax = max(rel) or 1.0
    sur = idx['surprise']
    smax = max(sur) or 1.0
    by_rel = sorted(range(n), key=lambda i: -rel[i])[:cand_k]
    by_sr = sorted(range(n),
                   key=lambda i: -(sur[i] * (0.2 + rel[i])))[:100]
    anchors = set()
    for ep in idx['eps']:
        anchors.add(ep[0])
        anchors.add(ep[-1])
    cand = set(by_rel) | set(by_sr) | anchors

    def score(i):
        decay = 2.0 ** (-recs[i]['age_days'] / 3.0)
        return (0.55 * (rel[i] / rmax) + 0.25 * (sur[i] / smax)
                + 0.20 * idx['imp'][i] + 0.05 * decay)

    order = sorted(cand, key=lambda i: -score(i))
    # digest header: newest-first episode digests capped at budget/4 —
    # pruned spans stay addressable by seq range (derived view only)
    dig_cap = budget_chars // 4
    dig_lines, dig_used = [], 0
    for dgtxt in reversed(idx['digests']):
        if dig_used + len(dgtxt) + 1 <= dig_cap:
            dig_lines.append(dgtxt)
            dig_used += len(dgtxt) + 1
        else:
            break
    dig_lines.reverse()
    header = '\n'.join(dig_lines)
    pack, used = [], len(header)
    for i in order:
        t = texts[i]
        if used + len(t) <= budget_chars:
            pack.append(i)
            used += len(t)
    return {'header': header, 'items': [recs[i] for i in pack],
            'used_chars': used, 'candidates': len(cand)}


# ---------------- CLI ----------------

def main():
    ap = argparse.ArgumentParser(prog='squawk_page')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('page')
    p.add_argument('--channel', default='fleet')
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--before', default=None)
    p.add_argument('--after', default=None)
    k = sub.add_parser('pack')
    k.add_argument('--channel', default='fleet')
    k.add_argument('--query', required=True)
    k.add_argument('--budget-tokens', type=int, default=16000)
    a = ap.parse_args()
    t0 = time.time()
    if a.cmd == 'page':
        items, nxt = page(a.channel, a.limit, a.before, a.after)
        out = {'channel': a.channel, 'count': len(items),
               'next_before': nxt,
               'items': [{'seq': r['seq'], 'file': r['file'],
                          'from': r['sender'], 'ts': r['ts'],
                          'title': r['title'],
                          'body': r['body'][:400]} for r in items],
               'ms': round((time.time() - t0) * 1000, 1)}
        print(json.dumps(out, indent=1))
    elif a.cmd == 'pack':
        idx = load_index(a.channel)
        res = hybrid_pack(idx, a.query, a.budget_tokens * 4)
        out = {'channel': a.channel, 'query': a.query,
               'budget_tokens': a.budget_tokens,
               'pack_tokens_est': res['used_chars'] // 4,
               'candidates': res['candidates'],
               'header': res['header'],
               'seqs': [r['seq'] for r in res['items']],
               'ms': round((time.time() - t0) * 1000, 1)}
        print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
