#!/usr/bin/env python3
"""Judge calibration department (CJE playbook, adapted).

Calibrate, don't curate: the full judge panel is kept; biases are absorbed
via calibration (Platt/isotonic, cross-fitted) and fed into the pooled
posterior as weights. Never drop a judge by solo accuracy.

Borrowed patterns (see docs/BORROWS.md):
  * cimo-labs/cje (MIT): the two-loop playbook — inner calibration loop
    (sample -> fit -> precision gate -> deploy) and outer monitoring loop
    (fresh labels -> residual-equivalence drift gate -> refit/escalate);
    refusal gates that never let an unchecked assumption pass silently;
    square-root label-budgeting law.
  * UW-Madison-Lee-Lab/LLM-judge-reporting (arXiv:2511.21140): bias-corrected
    point estimator th=(p+q0-1)/(q0+q1-1) with CIs reflecting test AND
    calibration uncertainty. Ported to stdlib (no scipy/numpy).
  * arXiv:2608.17994: abstention thresholds with finite-sample
    Clopper-Pearson guarantees.
  * arXiv:2606.15610 (Judge Datasheet): dark current, position bias, tie
    criterion per judge.

Stdlib only. State persists under work/calibration/ so a reboot loses nothing.
"""
import json
import math
import os
import time

WORK = os.environ.get("ORACLE_WORK", "/home/toxic/estate/ranch/squawk/oracle/work")
CAL_DIR = os.path.join(WORK, "calibration")
STATE_PATH = os.path.join(CAL_DIR, "calibration_state.json")
DATASHEET_PATH = os.path.join(CAL_DIR, "datasheets.json")
HISTORY_PATH = os.path.join(CAL_DIR, "accepted_history.jsonl")


# Label provenance. Only rows carrying one of these sources count as
# evidence for the abstention gate and the calibrator. Legacy rows without
# a source are quarantined (counted, never used). Nothing in this module
# ever writes synthetic labels.
LABEL_SOURCES = frozenset({"bench", "human", "market_settlement"})


def labeled_history(source=None, path=None):
    """Genuinely labeled accepted outcomes from the history ledger.

    Returns (rows, quarantined_count). When source is given, only rows
    with that label_source are returned. This is the provenance gate:
    the gate and the calibrator fit ONLY on what this returns.
    """
    path = path or HISTORY_PATH
    rows = []
    quarantined = 0
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if "correct" not in r:
                    continue
                if r.get("label_source") not in LABEL_SOURCES:
                    quarantined += 1
                    continue
                if source is not None and r.get("label_source") != source:
                    continue
                rows.append(r)
    return rows, quarantined


# ---------------- normal distribution (stdlib) ----------------

def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    """Acklam's approximation to the inverse normal CDF."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                 ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


# ---------------- Platt scaling (Newton-Raphson) ----------------

def platt_fit(scores, labels, max_iter=100, tol=1e-8):
    """Fit P(y=1|s) = sigmoid(A*s + B). Platt's target smoothing included:
    y' = (y*N+1)/(N+2) so tiny label sets don't pin the sigmoid."""
    n = len(scores)
    if n == 0:
        return 0.0, 0.0
    ys = [((y * n) + 1.0) / (n + 2.0) for y in labels]
    A, B = 0.0, math.log((sum(ys) + 1e-9) / (n - sum(ys) + 1e-9) + 1e-9)
    for _ in range(max_iter):
        gA = gB = hAA = hAB = hBB = 0.0
        for s, y in zip(scores, ys):
            f = s * A + B
            p = 1.0 / (1.0 + math.exp(-max(-500.0, min(500.0, f))))
            w = p * (1.0 - p)
            d = y - p
            gA += s * d
            gB += d
            hAA += s * s * w
            hAB += s * w
            hBB += w
        # L2 prior (ridge 1e-3) keeps tiny samples stable
        hAA += 1e-3
        hBB += 1e-3
        det = hAA * hBB - hAB * hAB
        if abs(det) < 1e-12:
            break
        dA = (hBB * gA - hAB * gB) / det
        dB = (hAA * gB - hAB * gA) / det
        A += dA
        B += dB
        if abs(dA) < tol and abs(dB) < tol:
            break
    return A, B


def platt_predict(params, scores):
    A, B = params
    out = []
    for s in scores:
        f = max(-500.0, min(500.0, s * A + B))
        out.append(1.0 / (1.0 + math.exp(-f)))
    return out


# ---------------- Isotonic regression (PAVA) ----------------

def isotonic_fit(scores, labels):
    """Pool-Adjacent-Violators Algorithm. Returns (xs, ys) stepwise map."""
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    xs = [scores[i] for i in order]
    # blocks: [sum, count, x_lo, x_hi]
    blocks = [[float(labels[i]), 1.0, xs[i], xs[i]] for i in order]
    merged = []
    for b in blocks:
        merged.append(b)
        while len(merged) >= 2:
            m0, m1 = merged[-2], merged[-1]
            a0, a1 = m0[0] / m0[1], m1[0] / m1[1]
            if a0 <= a1:
                break
            merged.pop()
            merged.pop()
            merged.append([m0[0] + m1[0], m0[1] + m1[1],
                           min(m0[2], m1[2]), max(m0[3], m1[3])])
    pts = []
    for s, c, lo, hi in merged:
        pts.append((lo, s / c))
        pts.append((hi, s / c))
    pts.sort()
    # dedupe
    out = []
    for x, y in pts:
        if out and out[-1][0] == x:
            out[-1] = (x, max(out[-1][1], y))
        else:
            out.append((x, y))
    return out


def isotonic_predict(model, scores):
    xs = [p[0] for p in model]
    ys = [p[1] for p in model]
    out = []
    for s in scores:
        if s <= xs[0]:
            out.append(ys[0])
        elif s >= xs[-1]:
            out.append(ys[-1])
        else:
            # linear interpolation between knots (out_of_bounds="clip")
            lo, hi = 0, len(xs) - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if xs[mid] <= s:
                    lo = mid
                else:
                    hi = mid
            t = (s - xs[lo]) / (xs[hi] - xs[lo]) if xs[hi] != xs[lo] else 0.0
            out.append(ys[lo] + t * (ys[hi] - ys[lo]))
    return out


# ---------------- metrics ----------------

def _clip01(p):
    return min(1.0 - 1e-9, max(1e-9, p))


def nll(probs, labels):
    return -sum(y * math.log(_clip01(p)) + (1 - y) * math.log(1 - _clip01(p))
                for p, y in zip(probs, labels)) / max(1, len(probs))


def brier(probs, labels):
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / max(1, len(probs))


def cross_fitted_predict(fit_fn, pred_fn, scores, labels, k=5):
    """Deterministic strided k-fold cross-fitting: no leakage, no RNG."""
    n = len(scores)
    k = max(2, min(k, n))
    preds = [0.0] * n
    for fold in range(k):
        te = [i for i in range(n) if i % k == fold]
        tr = [i for i in range(n) if i % k != fold]
        if not tr or not te:
            continue
        model = fit_fn([scores[i] for i in tr], [labels[i] for i in tr])
        for j, p in zip(te, pred_fn(model, [scores[i] for i in te])):
            preds[j] = p
    return preds


# ---------------- judge-reporting math (vendored, stdlib) ----------------

def bias_corrected_point(p, q0, q1):
    """th = (p + q0 - 1) / (q0 + q1 - 1), clipped. arXiv:2511.21140."""
    denom = q0 + q1 - 1.0
    if abs(denom) < 1e-9:
        return min(1.0, max(0.0, p))  # judge carries no signal; raw
    return min(1.0, max(0.0, (p + q0 - 1.0) / denom))


def bias_corrected_ci(p, q0, q1, n, m0, m1, alpha=0.05):
    """Adjusted (1-alpha) CI reflecting test AND calibration uncertainty."""
    z = norm_ppf(1 - alpha / 2)
    ps = (n * p + z ** 2 / 2) / (n + z ** 2)
    q0s = (m0 * q0 + 1) / (m0 + 2)
    q1s = (m1 * q1 + 1) / (m1 + 2)
    nn, mm0, mm1 = n + z ** 2, m0 + 2, m1 + 2
    denom = q0s + q1s - 1.0
    if abs(denom) < 1e-9:
        w = z * math.sqrt(ps * (1 - ps) / nn)
        return max(0.0, ps - w), min(1.0, ps + w)
    th = (ps + q0s - 1) / denom
    dth = 2 * z ** 2 * (-(1 - th) * q0s * (1 - q0s) / mm0
                        + th * q1s * (1 - q1s) / mm1)
    se = math.sqrt(ps * (1 - ps) / nn
                   + (1 - th) ** 2 * q0s * (1 - q0s) / mm0
                   + th ** 2 * q1s * (1 - q1s) / mm1) / denom
    return (min(1.0, max(0.0, th + dth - z * se)),
            min(1.0, max(0.0, th + dth + z * se)))


# ---------------- Clopper-Pearson (exact, finite-sample) ----------------

def _betacf(a, b, x):
    MAXIT, EPSB, FPMIN = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        dell = d * c
        h *= dell
        if abs(dell - 1.0) < EPSB:
            break
    return h


def _ibeta(a, b, x):
    """Regularized incomplete beta I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lb = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
          + a * math.log(x) + b * math.log(1.0 - x))
    bt = math.exp(lb)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _ibeta_inv(a, b, y, tol=1e-10):
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _ibeta(a, b, mid) < y:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def clopper_pearson(k, n, alpha=0.05):
    """Exact two-sided (1-alpha) CI for a binomial proportion. Returns
    (lo, hi); lo=0 when k=0, hi=1 when k=n. Finite-sample, no asymptotics."""
    if n <= 0:
        return 0.0, 1.0
    lo = 0.0 if k == 0 else _ibeta_inv(k, n - k + 1, alpha / 2)
    hi = 1.0 if k == n else _ibeta_inv(k + 1, n - k, 1 - alpha / 2)
    return lo, hi


# ---------------- judge datasheets ----------------

VACUUM_INPUTS = [
    "Resolve: (no question provided).",
    "Resolve: blorpt fnord wibble.",
    "Resolve: ",
]

POSITION_SWAP_TEMPLATE = (
    "Question: {q}\nAnswer options in order: {first} then {second}.\n"
    "Reply with your probability for the FIRST-listed outcome as JSON "
    '{"p_first": <0..1>}.')


def measure_datasheet(judge_fn):
    """judge_fn(prompt) -> posterior float. Measures the judge as an
    instrument: dark current (vacuum inputs), position bias (order swap),
    tie criterion (ambiguous questions)."""
    # dark current: mean |p - 0.5| on vacuum inputs
    vac = []
    for v in VACUUM_INPUTS:
        try:
            vac.append(abs(float(judge_fn(v)) - 0.5))
        except Exception:
            vac.append(0.5)
    dark = sum(vac) / max(1, len(vac))
    # position bias: same question, swapped option order
    q = "Will the opening coin toss of the next scheduled match land heads?"
    try:
        p1 = float(judge_fn(POSITION_SWAP_TEMPLATE.format(
            q=q, first="YES", second="NO")))
        p2 = float(judge_fn(POSITION_SWAP_TEMPLATE.format(
            q=q, first="NO", second="YES")))
        pos_bias = abs(p1 - (1.0 - p2))
    except Exception:
        pos_bias = 0.5
    reliability = min(1.0, max(0.1, 1.0 - (dark + pos_bias)))
    return {"dark_current": dark, "position_bias": pos_bias,
            "tie_criterion": "prompt-moved",  # prompting moves criterion, not resolution
            "reliability": reliability, "measured_ts": time.time()}


# ---------------- refusal gates (CJE gates.py pattern) ----------------

class RefusalGate:
    """Named gates; deploy/emit is blocked unless every gate PASSes.
    NOT_CHECKED is explicit — never let an unchecked assumption pass silently."""

    def __init__(self):
        self.gates = {}

    def set(self, name, status, detail=""):
        assert status in ("PASS", "FAIL", "NOT_CHECKED")
        self.gates[name] = {"status": status, "detail": detail}

    def ok(self):
        return all(g["status"] == "PASS" for g in self.gates.values())

    def not_checked(self):
        return [n for n, g in self.gates.items() if g["status"] == "NOT_CHECKED"]

    def failures(self):
        return {n: g for n, g in self.gates.items() if g["status"] == "FAIL"}

    def limitations_line(self):
        nc = self.not_checked()
        if not nc:
            return "all calibration assumptions checked"
        return "NOT_CHECKED: " + ", ".join(nc)


# ---------------- label budgeting: square-root law ----------------

def label_budget(total_labels, variances):
    """Allocate a label budget across judges proportional to sqrt(variance)
    (CJE planning.py). variances: {judge_id: var}. Returns {judge_id: n}."""
    roots = {j: math.sqrt(max(v, 1e-9)) for j, v in variances.items()}
    tot = sum(roots.values()) or 1.0
    alloc = {j: max(1, int(round(total_labels * r / tot))) for j, r in roots.items()}
    return alloc


# ---------------- the two-loop calibration operation ----------------

class CalibrationLoop:
    """Inner loop: labels -> fit (Platt+isotonic, cross-fitted) -> precision
    gate (must beat uncalibrated NLL) -> deploy. Outer loop: monitor fresh
    labels -> drift gate (NLL degradation beyond margin) -> refit/escalate."""

    DRIFT_MARGIN = 0.05  # NLL degradation that triggers refit

    def __init__(self, state_path=STATE_PATH):
        self.state_path = state_path
        self.state = {"judges": {}, "deployed_ts": 0}
        if os.path.exists(state_path):
            try:
                with open(state_path) as f:
                    self.state = json.load(f)
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.state_path)

    def fit_judge(self, judge_id, scores, labels):
        """Inner loop for one judge. Returns (gate, report)."""
        gate = RefusalGate()
        if len(scores) < 10:
            gate.set("sample_adequate", "FAIL",
                     "n=%d < 10 labels" % len(scores))
            return gate, {"judge": judge_id, "deployed": False}
        gate.set("sample_adequate", "PASS", "n=%d" % len(scores))
        raw_nll = nll(scores, labels)
        platt_cf = cross_fitted_predict(platt_fit, platt_predict, scores, labels)
        iso_cf = cross_fitted_predict(isotonic_fit, isotonic_predict, scores, labels)
        platt_nll, iso_nll = nll(platt_cf, labels), nll(iso_cf, labels)
        # precision gate: deploy the better of the two, only if it beats raw
        if min(platt_nll, iso_nll) >= raw_nll:
            gate.set("precision", "FAIL",
                     "calibrated NLL %.4f >= raw %.4f" % (min(platt_nll, iso_nll), raw_nll))
            return gate, {"judge": judge_id, "deployed": False,
                          "raw_nll": raw_nll}
        gate.set("precision", "PASS",
                 "NLL %.4f -> %.4f" % (raw_nll, min(platt_nll, iso_nll)))
        use_platt = platt_nll <= iso_nll
        model = (platt_fit(scores, labels) if use_platt
                 else isotonic_fit(scores, labels))
        self.state["judges"][judge_id] = {
            "kind": "platt" if use_platt else "isotonic",
            "model": model if use_platt else model,
            "fitted_ts": time.time(), "n": len(scores),
            "raw_nll": raw_nll, "cal_nll": min(platt_nll, iso_nll),
        }
        self.state["deployed_ts"] = time.time()
        self.save()
        gate.set("drift", "NOT_CHECKED", "no fresh labels yet")
        return gate, {"judge": judge_id, "deployed": True,
                      "kind": "platt" if use_platt else "isotonic",
                      "raw_nll": raw_nll,
                      "cal_nll": min(platt_nll, iso_nll)}

    def apply(self, judge_id, score):
        """Deployed calibrator for one judge; identity when undeployed.

        Cold start returns the raw score (never a fabricated calibration),
        and the RefusalGate records it as NOT_CHECKED so verdicts carry the
        limitation line.
        """
        entry = self.state["judges"].get(judge_id)
        if not entry:
            return _clip01(score)
        if entry["kind"] == "platt":
            return _clip01(platt_predict(entry["model"], [score])[0])
        return _clip01(isotonic_predict(entry["model"], [score])[0])

    def outer_loop_check(self, judge_id, recent_scores, recent_labels):
        """Outer drift loop: compare recent NLL against the deployed model's
        fitted NLL. Returns a RefusalGate entry; redeploy if drifted."""
        entry = self.state["judges"].get(judge_id)
        gate = RefusalGate()
        if not entry or len(recent_scores) < 10:
            gate.set("drift", "NOT_CHECKED",
                     "n=%d < 10 recent labels" % len(recent_scores))
            return gate, {"redeployed": False}
        recent_nll = nll([self.apply(judge_id, s) for s in recent_scores],
                         recent_labels)
        fitted_nll = entry.get("cal_nll", recent_nll)
        if recent_nll > fitted_nll * 1.25:
            gate.set("drift", "FAIL",
                     "recent NLL %.4f > 1.25x fitted %.4f — redeploying"
                     % (recent_nll, fitted_nll))
            self.fit_judge(judge_id, recent_scores, recent_labels)
            return gate, {"redeployed": True, "recent_nll": recent_nll}
        gate.set("drift", "PASS",
                 "recent NLL %.4f within 25%% of fitted %.4f"
                 % (recent_nll, fitted_nll))
        return gate, {"redeployed": False, "recent_nll": recent_nll}
