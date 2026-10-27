#!/usr/bin/env python3
"""Paging + context-deprecation code race on the real squawk fleet corpus.

Runs ON YOTE (awrawr-pc). Corpus: /home/toxic/.fleet-bus/squawk-root/fleet/*.md
(16,103 files). No LLM anywhere; index cache lives in /tmp.

Candidates (all emit a "context pack" under a char budget; tokens ~= chars/4):
  C0 recency baseline: newest messages until budget fills.
  C1 scored pack: TF-IDF relevance x exp recency decay (3d half-life) x
     deterministic importance proxies (mentions, sha/path/code-fence, length)
     -- Generative-Agents-style weighted sum of normalized axes.
  C2 episode pack: time-gap (>30min) + sliding TF-IDF cohesion segmentation;
     pack = per-episode digests + full text of top episodes.
  C3 markov pack: states = sender x topic-cluster (top TF-IDF term);
     first-order transition matrix; prune low-surprise (-log P) messages,
     episode first/last anchors always kept; fill by surprise x relevance.

Probes: 8 factual questions with hard-coded answer seqs (verified by hand
against the corpus before this run).
Metrics: probe hit-rate, pack build latency (median of 3), pack token use,
plus full-corpus preprocessing time per candidate.
Writes /tmp/race_results.md and /tmp/race_summary.json.
"""
import json
import math
import os
import pickle
import re
import statistics
import time
from collections import Counter, defaultdict, deque
from datetime import datetime

CORPUS_DIR = '/home/toxic/.fleet-bus/squawk-root/fleet'
CACHE_DIR = '/tmp/paging_race'
BUDGETS = {'4k': 16000, '16k': 64000}  # token budget -> char budget

STOP = set('''a an the and or of to in is it on for as at be by was were are
with from that this his her they their we you he she my our your its not no
but so if then than too very can will just don do does did have has had been
being up out over into down all any more most other some such only own same
both each few also when what who which while where there here how why'''.split())

TOK_RE = re.compile(r'[a-z0-9][a-z0-9\-]{1,30}')
SHA_RE = re.compile(r'\b[0-9a-f]*[a-f][0-9a-f]*\b')
MENTION_RE = re.compile(r'@[\w\-]+')
PATH_RE = re.compile(r'/home/|/tmp/|/usr/|/etc/')

# (question, answer-bearing seq) -- every seq verified to contain the fact
PROBES = [
    ("What ranch commit landed the full JetStream history migration, and what tool did it add?",
     1791911248722),
    ("Which model won the Oct 19 executor bench?", 1791911248759),
    ("What estate commit restored the squawk live-push today?", 1791911248674),
    ("What stopped duplicate fleet seqs from non-adopter writers?", 1791911248763),
    ("What estate commit did the flock-to-hodos rebrand, and what did it break?",
     1791911248740),
    ("Which commit added per-family reasoning budgets, and which param did the GLM probe validate?",
     1791911248771),
    ("Which key did the key-triage lane tell the owning lane to move to env?",
     1791278155513),
    ("When did the bare-reasoning fallback for the empty-response disease land, and is it proven?",
     1791911248757),
]


def tokenize(text):
    return [t for t in TOK_RE.findall(text.lower()) if t not in STOP and len(t) > 1]


def parse_corpus():
    recs = []
    files = sorted(f for f in os.listdir(CORPUS_DIR) if f.endswith('.md'))
    for f in files:
        m = re.match(r'(\d+)-', f)
        if not m:
            continue
        seq = int(m.group(1))
        try:
            txt = open(os.path.join(CORPUS_DIR, f), encoding='utf-8',
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
        recs.append({'seq': seq, 'sender': meta.get('from', '?'),
                     'ts': meta.get('ts', ''), 'title': meta.get('title', ''),
                     'body': body.strip()})
    recs.sort(key=lambda r: r['seq'])
    # parse datetimes, forward-fill gaps
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
    tmax = max(r['dt'] for r in recs)
    for r in recs:
        r['age_days'] = (tmax - r['dt']).total_seconds() / 86400.0
    return recs


def build_tfidf(recs):
    docs = [tokenize(r['sender'] + ' ' + r['title'] + ' ' + r['body']) for r in recs]
    df = Counter()
    tfs = []
    for toks in docs:
        tf = Counter(toks)
        tfs.append(tf)
        df.update(tf.keys())
    N = len(docs)
    idf = {t: math.log((1 + N) / (1 + c)) + 1.0 for t, c in df.items()}
    vecs, norms, inv = [], [], defaultdict(list)
    for i, (tf, toks) in enumerate(zip(tfs, docs)):
        ln = len(toks) or 1
        v = {t: (c / ln) * idf[t] for t, c in tf.items()}
        vecs.append(v)
        norms.append(math.sqrt(sum(x * x for x in v.values())))
        for t, w in v.items():
            inv[t].append((i, w))
    return {'idf': idf, 'vecs': vecs, 'norms': norms, 'inv': inv}


def relevance_scores(query, tfidf, n):
    qtok = [t for t in tokenize(query) if t in tfidf['idf']]
    qv = {t: (qtok.count(t) / max(len(qtok), 1)) * tfidf['idf'][t] for t in set(qtok)}
    qn = math.sqrt(sum(x * x for x in qv.values())) or 1.0
    acc = defaultdict(float)
    for t, qw in qv.items():
        for i, dw in tfidf['inv'].get(t, ()): 
            acc[i] += qw * dw
    out = [0.0] * n
    norms = tfidf['norms']
    for i, dot in acc.items():
        out[i] = dot / (qn * (norms[i] or 1.0))
    return out


def importance_scores(recs):
    raw = []
    for r in recs:
        b = r['body']
        m = len(MENTION_RE.findall(b))
        sha = sum(1 for t in SHA_RE.findall(b) if 7 <= len(t) <= 40)
        path = len(PATH_RE.findall(b))
        fence = b.count('```') // 2
        longf = 1.0 if len(b) > 3000 else 0.0
        raw.append(math.log1p(m) + min(sha + path, 4) * 0.4 + min(fence, 2) * 0.5 + longf)
    lo, hi = min(raw), max(raw)
    span = (hi - lo) or 1.0
    return [(x - lo) / span for x in raw]


def segment_episodes(recs, tfidf, gap_min=30, win=5):
    """Boundaries on >gap_min time gaps or adaptive TextTiling-style
    cohesion drops (doc vs centroid of previous `win` docs in episode)."""
    n = len(recs)
    vecs, norms = tfidf['vecs'], tfidf['norms']
    eps, cur = [], [0]
    coh_hist = deque(maxlen=50)

    def centroid_cos(i, members):
        cv = defaultdict(float)
        for j in members[-win:]:
            for t, w in vecs[j].items():
                cv[t] += w
        cn = math.sqrt(sum(x * x for x in cv.values())) or 1.0
        dot = sum(cv[t] * w for t, w in vecs[i].items() if t in cv)
        return dot / (cn * (norms[i] or 1.0))

    for i in range(1, n):
        boundary = False
        dt_s = (recs[i]['dt'] - recs[i - 1]['dt']).total_seconds()
        if dt_s > gap_min * 60:
            boundary = True
        else:
            c = centroid_cos(i, cur)
            if len(coh_hist) == 50:
                thr = sorted(coh_hist)[7]  # bottom ~15%
                if c < thr:
                    boundary = True
            coh_hist.append(c)
        if boundary:
            eps.append(cur)
            cur = [i]
        else:
            cur.append(i)
    eps.append(cur)
    return eps


def episode_digests(recs, tfidf, eps):
    digests = []
    for ei, ep in enumerate(eps):
        tsum = Counter()
        for i in ep:
            for t, w in tfidf['vecs'][i].items():
                tsum[t] += w
        top = ', '.join(t for t, _ in tsum.most_common(6))
        senders = Counter(recs[i]['sender'] for i in ep)
        digests.append(
            f"[EP{ei} msgs={len(ep)} seqs={recs[ep[0]]['seq']}-{recs[ep[-1]]['seq']} "
            f"senders={dict(senders)} terms: {top}]")
    return digests


def build_markov(recs, tfidf):
    topterm = []
    for v in tfidf['vecs']:
        topterm.append(max(v, key=v.get) if v else '__none__')
    states = [(r['sender'], t) for r, t in zip(recs, topterm)]
    trans = defaultdict(Counter)
    out = Counter()
    for a, b in zip(states, states[1:]):
        trans[a][b] += 1
        out[a] += 1
    V = len(set(states)) or 1
    return {'states': states, 'trans': dict(trans), 'out': dict(out), 'V': V}


def surprise_vec(mk):
    n = len(mk['states'])
    out = [0.0] * n
    trans, outc, V = mk['trans'], mk['out'], mk['V']
    out[0] = math.log(V)
    for i in range(1, n):
        a, b = mk['states'][i - 1], mk['states'][i]
        c = trans.get(a, {}).get(b, 0)
        out[i] = -math.log((c + 1) / (outc.get(a, 0) + V))
    return out


def msg_text(r):
    return f"[{r['seq']} | {r['sender']} | {r['ts']}]\n{r['title']}\n{r['body']}"


def fill_budget(ranked_texts, budget):
    pack, used = [], 0
    for idx, score, text in ranked_texts:
        if used + len(text) <= budget:
            pack.append(idx)
            used += len(text)
    return pack, used


# ---------------- candidate pack builders ----------------

def pack_c0(recs, texts, budget, query=None, arts=None):
    ranked = [(len(recs) - 1 - k, 1.0, texts[len(recs) - 1 - k])
              for k in range(len(recs))]
    return fill_budget(ranked, budget)


def pack_c1(recs, texts, budget, query, arts):
    n = len(recs)
    rel = relevance_scores(query, arts['tfidf'], n)
    imp = arts['imp']
    rmax = max(rel) or 1.0
    ranked = []
    for i in range(n):
        rec = 2.0 ** (-recs[i]['age_days'] / 3.0)
        score = (rel[i] / rmax + rec + imp[i]) / 3.0
        ranked.append((i, score, texts[i]))
    ranked.sort(key=lambda x: -x[1])
    return fill_budget(ranked, budget)


def pack_c2(recs, texts, budget, query, arts):
    n = len(recs)
    eps, digests = arts['eps'], arts['digests']
    # digest tier: newest-first episode digests, capped at 1/4 of budget
    dig_cap = budget // 4
    dig_lines, dig_used = [], 0
    for d in reversed(digests):  # newest first
        if dig_used + len(d) + 1 <= dig_cap:
            dig_lines.append(d)
            dig_used += len(d) + 1
        else:
            break
    dig_lines.reverse()  # back to chronological
    dig_text = '\n'.join(dig_lines)
    # episode scores: query relevance of episode x recency
    rel = relevance_scores(query, arts['tfidf'], n)
    ep_score = []
    for ei, ep in enumerate(eps):
        r = sum(rel[i] for i in ep) / max(len(ep), 1)
        rec = 2.0 ** (-recs[ep[-1]]['age_days'] / 3.0)
        ep_score.append((ei, (r + rec) / 2.0))
    ep_score.sort(key=lambda x: -x[1])
    msg_ranked = []
    for ei, s in ep_score:
        for i in eps[ei]:
            msg_ranked.append((i, s, texts[i]))
    pack, used = fill_budget(msg_ranked, max(budget - len(dig_text), 0))
    return pack, used + len(dig_text)


def pack_c3(recs, texts, budget, query, arts):
    n = len(recs)
    eps = arts['eps']
    sur = arts['surprise']
    thr = sorted(sur)[int(0.30 * n)]
    anchors = set()
    for ep in eps:
        anchors.add(ep[0])
        anchors.add(ep[-1])
    keep = [i for i in range(n) if i in anchors or sur[i] >= thr]
    rel = relevance_scores(query, arts['tfidf'], n)
    ranked = [(i, sur[i] * (0.2 + rel[i]), texts[i]) for i in keep]
    ranked.sort(key=lambda x: -x[1])
    return fill_budget(ranked, budget)


PACKERS = {'C0': pack_c0, 'C1': pack_c1, 'C2': pack_c2, 'C3': pack_c3}

STAGES = {
    'C0': ['corpus'],
    'C1': ['corpus', 'tfidf'],
    'C2': ['corpus', 'tfidf', 'eps'],
    'C3': ['corpus', 'tfidf', 'eps', 'markov'],
}
STAGE_FILES = {
    'corpus': 'corpus.pkl',
    'tfidf': 'tfidf.pkl',
    'eps': 'eps.pkl',
    'markov': 'markov.pkl',
}


def save(name, obj):
    with open(os.path.join(CACHE_DIR, name), 'wb') as f:
        pickle.dump(obj, f, protocol=4)


def load(name):
    with open(os.path.join(CACHE_DIR, name), 'rb') as f:
        return pickle.load(f)


def preprocess(cid):
    """Cold build of everything candidate `cid` needs. Returns seconds."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    for s in STAGES[cid]:
        p = os.path.join(CACHE_DIR, STAGE_FILES[s])
        if os.path.exists(p):
            os.remove(p)
    t0 = time.time()
    recs = parse_corpus()
    save('corpus.pkl', recs)
    if 'tfidf' in STAGES[cid]:
        tf = build_tfidf(recs)
        save('tfidf.pkl', tf)
    if 'eps' in STAGES[cid]:
        tf = load('tfidf.pkl')
        eps = segment_episodes(recs, tf)
        save('eps.pkl', {'eps': eps, 'digests': episode_digests(recs, tf, eps)})
    if 'markov' in STAGES[cid]:
        tf = load('tfidf.pkl')
        mk = build_markov(recs, tf)
        save('markov.pkl', {'markov': mk, 'surprise': surprise_vec(mk)})
    return time.time() - t0


def load_arts(cid):
    arts = {}
    recs = load('corpus.pkl')
    arts['recs'] = recs
    arts['texts'] = [msg_text(r) for r in recs]
    if 'tfidf' in STAGES[cid]:
        arts['tfidf'] = load('tfidf.pkl')
        arts['imp'] = importance_scores(recs)
    if 'eps' in STAGES[cid]:
        e = load('eps.pkl')
        arts['eps'], arts['digests'] = e['eps'], e['digests']
    if 'markov' in STAGES[cid]:
        mk = load('markov.pkl')
        arts['markov'], arts['surprise'] = mk['markov'], mk['surprise']
    return arts


def run():
    os.makedirs(CACHE_DIR, exist_ok=True)
    results = {}
    for cid in ['C0', 'C1', 'C2', 'C3']:
        t_pre = preprocess(cid)
        arts = load_arts(cid)
        recs, texts = arts['recs'], arts['texts']
        packer = PACKERS[cid]
        row = {'preprocessing_s': round(t_pre, 2), 'budgets': {}}
        print(f'{cid}: preprocessing {t_pre:.1f}s, corpus={len(recs)}',
              flush=True)
        for bname, budget in BUDGETS.items():
            hits, misses, lats, toks = [], [], [], []
            for qi, (q, aseq) in enumerate(PROBES):
                seqs = set()
                used = 0
                for _ in range(3):
                    t0 = time.time()
                    pack, used = packer(recs, texts, budget, q, arts)
                    seqs = {recs[i]['seq'] for i in pack}
                hit = 1 if aseq in seqs else 0
                hits.append(hit)
                if not hit:
                    misses.append(f'P{qi + 1}({aseq})')
                toks.append(used / 4.0)
                # median of 3 latencies (fresh timing runs for cleanliness)
                ds = []
                for _ in range(3):
                    t0 = time.time()
                    packer(recs, texts, budget, q, arts)
                    ds.append(time.time() - t0)
                lats.append(statistics.median(ds))
            row['budgets'][bname] = {
                'hit_rate': f'{sum(hits)}/{len(hits)}',
                'misses': ', '.join(misses) or 'none',
                'median_build_ms': round(statistics.median(lats) * 1000, 1),
                'avg_pack_tokens': round(sum(toks) / len(toks)),
            }
            print(f'  {bname}: hits {sum(hits)}/{len(hits)} '
                  f'miss[{row["budgets"][bname]["misses"]}] '
                  f'build {row["budgets"][bname]["median_build_ms"]}ms '
                  f'pack {row["budgets"][bname]["avg_pack_tokens"]}tok',
                  flush=True)
        results[cid] = row

    with open('/tmp/race_summary.json', 'w') as f:
        json.dump(results, f, indent=1)

    lines = ['# Paging / context-deprecation race — results',
             '', f'Corpus: {len(load("corpus.pkl"))} fleet messages (real)',
             'Token estimate: chars/4. Budgets: 4k and 16k tokens.',
             'Probes: 8 hand-verified factual questions (answer seqs hard-coded).',
             '',
             'Probe key: P1 JetStream-migration commit (9692244) | P2 bench winner (gpt-oss-120b) |',
             'P3 squawk-ws restore (64a81ba) | P4 seq-allocator unification |',
             'P5 flock→hodos rebrand breakage | P6 reasoning budgets | P7 MCPPROXY key triage |',
             'P8 empty-response disease-2 fallback.',
             '',
             '| candidate | preprocess | budget | hit-rate | misses | build ms | pack tok |',
             '|---|---|---|---|---|---|---|']
    for cid in ['C0', 'C1', 'C2', 'C3']:
        r = results[cid]
        for bname in BUDGETS:
            b = r['budgets'][bname]
            lines.append(f"| {cid} | {r['preprocessing_s']}s | {bname} | "
                         f"{b['hit_rate']} | {b['misses']} | {b['median_build_ms']} | "
                         f"{b['avg_pack_tokens']} |")
    lines += ['', '## Winner: see parent report (hit-rate, then latency).',
              '', '## Notes', '- raw JSON: /tmp/race_summary.json']
    with open('/tmp/race_results.md', 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('wrote /tmp/race_results.md', flush=True)


if __name__ == '__main__':
    run()
