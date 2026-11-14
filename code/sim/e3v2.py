"""E3v2 -- realistic collusion study for anonymous delegation tokens (replaces the analytic E3 row).

Usage:  python sim/e3v2.py [--quick]          (run from code/; writes results/e3v2.json, results/e3v2_summary.md,
                                                results/e3v2_fig_main.png, results/e3v2_fig_sens.png)
Deterministic: master seed 20261109 (every sub-run derives its seed from it).

WHAT IS SIMULATED
-----------------
Population. N users (100 / 1,000 / 10,000), T = 50 MCP tools with Zipf(s) popularity (s = 1.0 by default).
  Tool types (random assignment, independent of popularity): a fraction f_pers (0.30) of "personal" tools
  (half booking-like, half payment-like), 40 % search tools, the rest utility tools.
  Each user: 3-8 favourite tools (drawn without replacement, weighted by popularity, Gumbel-top-k) with
  popularity weights; home city (200 cities, Zipf 1.0); typical party size; three personal constants
  (cabin/room class in 4 values, locale in 10 values Zipf, payment-method kind in 3 values); a budget level
  (log-normal); 3-6 interest topics out of 100 (Zipf 0.8 popularity, Dirichlet(1) weights); a personal
  diurnal shift N(0, 1.5 h) applied to a shared 3-peak diurnal profile (09:30, 14:00, 20:30 + 5 % uniform).
Traffic. 30 days; each day 0-3 agent tasks (uniform integer) starting at a time drawn from the user's diurnal
  profile; a task = burst of 2-6 tool calls (uniform), tools drawn with replacement from the favourites
  (popularity-weighted), consecutive calls separated by gaps drawn from the EMPIRICAL inter-call gap
  distribution measured in E4 (results/e4/*.json, models gpt-oss-20b, qwen2.5-72b-instruct-awq,
  qwen2.5-7b-instruct, successful rows, all three auth modes), resampled with a log-space Gaussian kernel
  (Silverman bandwidth). Tools observe integer-second timestamps.
Call content (quasi-identifiers).
  booking : origin city (= home w.p. .8), party size (= typical w.p. .85), class c1 (present w.p. .7),
            locale c2 (present w.p. .7)
  payment : amount (budget x party x LN(0, .6); observed in 25 log-1.5 bins), payment-method c3 (present
            w.p. .7, the user's own w.p. .9), locale c2 (present w.p. .5)
  search  : 1-3 query topics (from the user's interests w.p. .8, global popularity otherwise), location
            (= home city, present w.p. .3)
  utility : no personal argument.
Token formats (what each tool logs per call, besides the timestamp, tool, action class):
  clear            principal id
  pertool          stable per-(user, tool) pseudonym
  pertool_day      per-(user, tool, day) pseudonym
  mm               Masked Mandates: fresh unlinkable pseudonym per call (counter j hidden); visible: tool,
                   timestamp, action class, amount, accumulator epoch (shared by everyone -> no information),
                   and the full call ARGUMENTS (quasi-identifiers above)
  *_min            "content minimisation": arguments stripped of personal quasi-identifiers (only tool,
                   timestamp, action class and the amount -- which the token itself exposes -- remain).
                   Evaluated for mm, pertool and pertool_day.
Colluding attacker (all 50 tools pool their logs):
  a   identifier linkage: exact pseudonym equality.
  b_d timing (+ identifiers): single-linkage of time-consecutive calls whose gap <= d seconds,
      d in {2, 10, 60, 600}, unioned with identifier links (connected components).
  c   session reconstruction + quasi-identifier clustering over 30 days:
        (1) identifier groups; (2) sessions = time segments with gap <= d_s, where d_s = ceil(99th percentile of
        the calibrated within-task gap) -- fixed from the calibration, NOT tuned on outcomes; a segment is
        "clean" if it has <= 6 calls (max task length, assumed known); identifier groups that co-occur in a
        clean segment are merged if co-occurrence count >= min(2, smaller group size) (for mm this simply makes
        each clean segment one atom; calls of busy, non-clean segments stay singletons); (3) the atoms are
        clustered into K = N clusters (the attacker is assumed to know N) by hard-EM on a multinomial mixture
        (per-field categorical profiles, Dirichlet shrinkage alpha=1 to the global field distribution, equal
        mixing weights -- learned weights caused rich-get-richer merges and halved the attacker's F1 in a pilot), init by K atoms drawn proportionally to their information content, <= 10 iterations (stop when < 0.2 % of atoms move),
        empty clusters reseeded with the worst-fitting atoms. Features: quasi-identifiers + hour of day.
  d   as c, features = tool-set fingerprint (per-call tool tokens) + quasi-identifiers + hour of day.
      d is the combined attacker (identifiers + timing + tool set + content + 30-day aggregation).
  s   (reported as s_session) the stage-1 atoms of c/d alone: identifiers + clean-session co-occurrence, no
      cross-day content clustering.
  e   (e_auxmap) auxiliary-profile linker: every stage-1 atom is assigned to its maximum-likelihood user under
      the TRUE generative profiles (attacker with background knowledge of every user; upper bound for c/d).
Metrics (per format x attacker x N): pairwise precision / recall / F1 over same-user call pairs with absolute TP,
  FP, FN pair counts (exact, from the contingency table); session recall (same-task pairs linked); ARI;
  B-cubed precision / recall / F1; re-identification rate (users whose largest cluster holds >= 50 % of their
  calls and is >= 80 % pure); cluster count.
  Anonymity (Serjantov-Danezis / Diaz et al.): an AUXILIARY-PROFILE attacker that knows every user's
  generative profile (favourites, home, constants, interests, budget, diurnal shift -- e.g. from an earlier
  clear-token period or a data broker; this is an upper bound) computes, for 400 random target calls, the
  posterior over the N users given the evidence = all calls of the attacker cluster containing the target
  (subsampled to 200 calls if larger) restricted to the fields visible in that format. Likelihood: the target
  call is the target user's; every other call of the cluster is the same user's w.p. pi (= the clustering's
  B-cubed precision, i.e. a calibrated attacker) and otherwise from the population marginal; tools enter as a
  presence model (distinct tools vs. favourite set), because per-tool pseudonym clusters are selected by tool and
  a per-call multinomial tool likelihood is then over-confident. We report mean
  entropy H (bits), effective anonymity-set size 2^H, degree of anonymity H/log2 N, mean size of the smallest
  set holding 99 % of the posterior, mean posterior of the true user and top-1 identification accuracy.
  Caveat: for large clusters built by content similarity (c, d, e) the cluster is selected by the same features
  the posterior uses, so the posterior is over-confident (entropy ~0 with top-1 well below 1); entropy is
  calibrated (top-1 ~ mean posterior of the true user) for call_only, a_id and s_session. Always read entropy
  together with top-1 accuracy and p_true. "call_only" = evidence of the target
  call alone (no linkage).
Sensitivity (N = 1,000, one factor at a time around the baseline): favourites range, tasks/day, tool Zipf
  exponent, fraction of tools with personal arguments, gap scale (x10: slower loops / human confirmation),
  and per-call random delay U(0, J) as a timing mitigation (J in {60, 600} s); formats mm, mm_min, pertool_day;
  attackers b_10, d (+ posterior for d).
APPROXIMATIONS: the E4 trace stores no per-call turn index; when a model emitted more calls than tool turns
  (qwen2.5-72b: 4 calls in 3 tool turns), consecutive same-name calls (pay, pay) are assumed to share a turn
  (intra-turn gap = previous call's duration, inter-turn gap = previous call's duration + next LLM latency).
  E4 tools ran locally (no WAN RTT) and tasks were short travel scenarios, so gaps are short (sub-2 s
  median); the x10 gap-scale sensitivity covers slower loops. The attacker's clustering is a heuristic (hard
  EM, K = N known); a stronger attacker can only do better, so linkage numbers are lower bounds for the
  attacker, except the auxiliary-profile posterior which is an upper bound. One population draw per
  configuration (plus 3 replicate seeds for the N=1,000 baseline of mm / mm_min / pertool_day).
"""
import json, math, sys, time, argparse
from pathlib import Path
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.special import ndtr, logsumexp

SEED = 20261109
ROOT = Path(__file__).resolve().parent.parent
T_TOOLS, DAYS, N_CITIES, N_TOPICS = 50, 30, 200, 100
MAX_TASK = 6
E4_MODELS = ["gpt-oss-20b", "qwen2.5-72b-instruct-awq", "qwen2.5-7b-instruct"]

BASE = dict(fav=(3, 8), tasks=(0, 3), zipf=1.0, f_pers=0.30, f_search=0.40, task_len=(2, 6), gap_scale=1.0, jitter=0)

# vocabulary layout (attacker feature space)
FIELDS = [("tool", T_TOOLS), ("hour", 24), ("origin", N_CITIES), ("party", 6), ("c1", 4), ("c2", 10), ("c3", 3),
          ("topic", N_TOPICS), ("loc", N_CITIES), ("amt", 25)]
OFF = {}
_o = 0
for _f, _n in FIELDS:
    OFF[_f] = (_o, _o + _n); _o += _n
V = _o
QI_FULL = ["origin", "party", "c1", "c2", "c3", "topic", "loc", "amt"]
QI_MIN = ["amt"]
FORMATS = ["clear", "pertool", "pertool_min", "pertool_day", "pertool_day_min", "mm", "mm_min"]
DELTAS = [2, 10, 60, 600]


# ----------------------------------------------------------------------------------------------- calibration
def calibrate():
    gaps, per_model, n_rows = [], {}, {}
    for m in E4_MODELS:
        d = json.load(open(ROOT / "results" / "e4" / f"e4_{m}.json"))
        g_m = []; used = 0
        for r in d["rows"]:
            if not r["success"] or not r["calls"]:
                continue
            calls = r["calls"]; llm = r["llm_ms"]; n_tool_turns = len(llm) - 1
            if n_tool_turns < 1 or len(calls) < n_tool_turns:
                continue
            # assign calls to turns: start one call per turn, then pack consecutive same-name calls together
            turn = list(range(len(calls)))
            extra = len(calls) - n_tool_turns
            i = len(calls) - 1
            while extra > 0 and i > 0:
                if calls[i]["name"] == calls[i - 1]["name"]:
                    extra -= 1; turn[i] = None
                i -= 1
            i = len(calls) - 1
            while extra > 0 and i > 0:       # fallback: pack latest calls into the previous turn
                if turn[i] is not None:
                    turn[i] = None; extra -= 1
                i -= 1
            k = 0; tix = []
            for x in turn:
                if x is None: tix.append(k - 1)
                else: tix.append(k); k += 1
            used += 1
            for j in range(1, len(calls)):
                dur = (calls[j - 1].get("prep_ms", 0) + calls[j - 1].get("rtt_ms", 0)) / 1e3
                gap = dur if tix[j] == tix[j - 1] else dur + llm[tix[j]] / 1e3
                g_m.append(gap)
        gaps += g_m; n_rows[m] = used
        per_model[m] = {"rows_used": used, "gaps": len(g_m), "median_s": float(np.median(g_m)),
                        "p90_s": float(np.quantile(g_m, .9)), "max_s": float(np.max(g_m))}
    g = np.array(gaps)
    lg = np.log(g)
    bw = 1.06 * lg.std() * len(lg) ** (-1 / 5)
    qs = {f"p{int(q * 100)}": float(np.quantile(g, q)) for q in (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99)}
    p99 = float(np.quantile(g, 0.99))
    return {"source": [f"results/e4/e4_{m}.json" for m in E4_MODELS], "per_model": per_model, "n_gaps": len(g),
            "quantiles_s": qs, "mean_s": float(g.mean()), "lognormal_fit": {"mu": float(lg.mean()), "sigma": float(lg.std())},
            "kernel_bw_log": float(bw), "fraction_intra_turn_lt_0.5s": float((g < 0.5).mean()),
            "turn_assignment": "one call per tool turn; extra calls packed with an identical preceding call (pay,pay)",
            "session_delta_s": int(math.ceil(p99))}, lg, bw


# ----------------------------------------------------------------------------------------------- world
def zipf(n, s):
    p = 1.0 / np.arange(1, n + 1) ** s
    return p / p.sum()

def gumbel_topk(rng, logp, k, n_rows):
    keys = logp[None, :] + rng.gumbel(size=(n_rows, len(logp)))
    order = np.argsort(-keys, axis=1)
    kmax = int(k.max())
    sel = order[:, :kmax].copy()
    sel[np.arange(kmax)[None, :] >= k[:, None]] = -1
    return sel

def cat_sample(rng, cum, n):
    """cum: (n, K) row-wise cumulative probabilities -> index per row"""
    u = rng.random(n)[:, None]
    return np.minimum((cum < u).sum(1), cum.shape[1] - 1)

def make_world(N, P, rng, lg, bw):
    T = T_TOOLS
    pop = zipf(T, P["zipf"])
    n_pers = int(round(P["f_pers"] * T)); n_search = int(round(P["f_search"] * T))
    n_search = min(n_search, T - n_pers)
    perm = rng.permutation(T)
    ttype = np.full(T, 3)  # 0 booking, 1 payment, 2 search, 3 utility
    n_book = (n_pers + 1) // 2
    ttype[perm[:n_book]] = 0; ttype[perm[n_book:n_pers]] = 1; ttype[perm[n_pers:n_pers + n_search]] = 2
    citypop = zipf(N_CITIES, 1.0); topicpop = zipf(N_TOPICS, 0.8); localepop = zipf(10, 1.0)
    party_p = np.array([.35, .30, .15, .12, .05, .03]); c1_p = np.array([.5, .3, .15, .05]); c3_p = np.array([.6, .3, .1])
    # users
    k = rng.integers(P["fav"][0], P["fav"][1] + 1, size=N)
    fav = gumbel_topk(rng, np.log(pop), k, N)
    favw = np.where(fav >= 0, pop[np.maximum(fav, 0)], 0.0)
    favw /= favw.sum(1, keepdims=True)
    U = dict(fav=fav, favw=favw, home=rng.choice(N_CITIES, N, p=citypop), party=rng.choice(6, N, p=party_p),
             c1=rng.choice(4, N, p=c1_p), c2=rng.choice(10, N, p=localepop), c3=rng.choice(3, N, p=c3_p),
             budget=np.exp(rng.normal(np.log(80), 0.5, N)), shift=rng.normal(0, 1.5, N))
    ki = rng.integers(3, 7, size=N)
    U["int"] = gumbel_topk(rng, np.log(topicpop), ki, N)
    iw = rng.dirichlet(np.ones(6), size=N) * (U["int"] >= 0)
    U["intw"] = iw / iw.sum(1, keepdims=True)
    # tasks
    ntask = rng.integers(P["tasks"][0], P["tasks"][1] + 1, size=(N, DAYS))
    t_user = np.repeat(np.repeat(np.arange(N), DAYS), ntask.ravel())
    t_day = np.repeat(np.tile(np.arange(DAYS), N), ntask.ravel())
    M = len(t_user)
    comp = rng.choice(4, M, p=[.3 * .95, .35 * .95, .35 * .95, .05])
    mu = np.array([9.5, 14.0, 20.5, 0]); sd = np.array([1.5, 2.0, 2.0, 0])
    h = np.where(comp == 3, rng.uniform(0, 24, M), rng.normal(mu[comp], np.maximum(sd[comp], 1e-9)) + U["shift"][t_user])
    h = np.mod(h, 24.0)
    t_start = t_day * 86400.0 + h * 3600.0
    L = rng.integers(P["task_len"][0], P["task_len"][1] + 1, size=M)
    c_task = np.repeat(np.arange(M), L)
    C = len(c_task)
    c_user = t_user[c_task]
    first = np.r_[0, np.cumsum(L)[:-1]]
    gaps = np.exp(lg[rng.integers(0, len(lg), C)] + bw * rng.normal(size=C)) * P["gap_scale"]
    gaps[first] = 0.0
    cs = np.cumsum(gaps)
    off = cs - np.repeat(cs[first], L)
    t = t_start[c_task] + off
    if P["jitter"]:
        t = t + rng.uniform(0, P["jitter"], C)
    t = np.floor(t).astype(np.int64)
    tool = fav[c_user, cat_sample(rng, np.cumsum(favw, 1)[c_user], C)]
    ty = ttype[tool]
    F = {f: np.full(C, -1, np.int64) for f in ["origin", "party", "c1", "c2", "c3", "loc", "amt"]}
    topics = np.full((C, 3), -1, np.int64)
    b = ty == 0; nb = int(b.sum()); ub = c_user[b]
    F["origin"][b] = np.where(rng.random(nb) < .8, U["home"][ub], rng.choice(N_CITIES, nb, p=citypop))
    F["party"][b] = np.where(rng.random(nb) < .85, U["party"][ub], rng.integers(0, 6, nb))
    F["c1"][b] = np.where(rng.random(nb) < .7, U["c1"][ub], -1)
    F["c2"][b] = np.where(rng.random(nb) < .7, U["c2"][ub], -1)
    p = ty == 1; npay = int(p.sum()); up = c_user[p]
    amount = U["budget"][up] * (U["party"][up] + 1) * np.exp(rng.normal(0, .6, npay))
    F["amt"][p] = np.clip(np.floor(np.log(np.maximum(amount, 1)) / np.log(1.5)), 0, 24).astype(np.int64)
    F["c3"][p] = np.where(rng.random(npay) < .7, np.where(rng.random(npay) < .9, U["c3"][up], rng.integers(0, 3, npay)), -1)
    F["c2"][p] = np.where(rng.random(npay) < .5, U["c2"][up], -1)
    s = ty == 2; ns = int(s.sum()); us = c_user[s]
    nq = rng.integers(1, 4, ns)
    icum = np.cumsum(U["intw"], 1)
    for j in range(3):
        own = U["int"][us, cat_sample(rng, icum[us], ns)]
        glob = rng.choice(N_TOPICS, ns, p=topicpop)
        v = np.where(rng.random(ns) < .8, own, glob)
        topics[s, j] = np.where(j < nq, v, -1)
    F["loc"][s] = np.where(rng.random(ns) < .3, U["home"][us], -1)
    calls = dict(user=c_user, task=c_task, day=t // 86400, t=t, tool=tool, topics=topics, **F)
    pri = dict(pop=pop, ttype=ttype, citypop=citypop, topicpop=topicpop, localepop=localepop, party_p=party_p, c3_p=c3_p)
    return U, calls, pri


# ----------------------------------------------------------------------------------------------- features
def call_features(C, fields, hour_w):
    """sparse (calls x V) evidence matrix restricted to `fields` (+ 'tool','hour' if listed)"""
    n = len(C["t"]); rows, cols, vals = [], [], []
    def add(mask, col, w=1.0):
        idx = np.nonzero(mask)[0]
        rows.append(idx); cols.append(col[idx]); vals.append(np.full(len(idx), float(w)) if np.ndim(w) == 0 else np.asarray(w, float)[idx])
    allm = np.ones(n, bool)
    if "tool" in fields: add(allm, OFF["tool"][0] + C["tool"])
    if "hour" in fields: add(allm, OFF["hour"][0] + (C["t"] % 86400) // 3600, hour_w)
    for f in ["origin", "party", "c1", "c2", "c3", "loc", "amt"]:
        if f in fields:
            m = C[f] >= 0; add(m, OFF[f][0] + np.maximum(C[f], 0))
    if "topic" in fields:
        for j in range(3):
            m = C["topics"][:, j] >= 0; add(m, OFF["topic"][0] + np.maximum(C["topics"][:, j], 0))
    r = np.concatenate(rows); c = np.concatenate(cols); v = np.concatenate([np.asarray(x, float) for x in vals])
    return sp.csr_matrix((v.astype(np.float32), (r, c)), shape=(n, V))

def visible_fields(fmt):
    return ["tool", "hour"] + (QI_MIN if fmt.endswith("_min") else QI_FULL)

def user_loglik_table(U, pri):
    """attacker's exact generative profile: (N x V) log P(token | user) per field (eps-floored)"""
    N = len(U["home"]); eps = 1e-6
    Lt = np.zeros((N, V))
    def put(f, P):
        a, b = OFF[f]; Lt[:, a:b] = np.log(P * (1 - eps * P.shape[1]) + eps)
    P = np.zeros((N, T_TOOLS)); r = np.repeat(np.arange(N), U["fav"].shape[1]); fv = U["fav"].ravel(); m = fv >= 0
    np.add.at(P, (r[m], fv[m]), U["favw"].ravel()[m]); put("tool", P)
    hh = np.arange(25)[None, :]
    H = np.full((N, 24), .05 / 24)
    for w, mu, s in [(.3, 9.5, 1.5), (.35, 14.0, 2.0), (.35, 20.5, 2.0)]:
        for wrap in (-24, 0, 24):
            c = ndtr((hh - mu - U["shift"][:, None] - wrap) / s)
            H += .95 * w * np.diff(c, axis=1)
    put("hour", H / H.sum(1, keepdims=True))
    oh = lambda v, k: np.eye(k)[v]
    put("origin", .8 * oh(U["home"], N_CITIES) + .2 * pri["citypop"][None, :])
    put("party", .85 * oh(U["party"], 6) + .15 / 6)
    put("c1", oh(U["c1"], 4)); put("c2", oh(U["c2"], 10)); put("c3", .9 * oh(U["c3"], 3) + .1 / 3)
    Tp = np.zeros((N, N_TOPICS)); r = np.repeat(np.arange(N), U["int"].shape[1]); iv = U["int"].ravel(); m = iv >= 0
    np.add.at(Tp, (r[m], iv[m]), U["intw"].ravel()[m]); put("topic", .8 * Tp + .2 * pri["topicpop"][None, :])
    put("loc", oh(U["home"], N_CITIES))
    edges = np.log(1.5) * np.arange(26.0); edges[0] = -np.inf; edges[-1] = np.inf
    mu = np.log(U["budget"] * (U["party"] + 1))[:, None]
    A = np.diff(ndtr((edges[None, :] - mu) / .6), axis=1)
    put("amt", A)
    return Lt.astype(np.float32)


# ----------------------------------------------------------------------------------------------- attacks
def pseudonym(C, fmt):
    u, tl, d = C["user"], C["tool"], C["day"]
    base = fmt.replace("_min", "")
    if base == "clear": return u.copy()
    if base == "pertool": return u * T_TOOLS + tl
    if base == "pertool_day": return (u * T_TOOLS + tl) * DAYS + d
    return np.arange(len(u))  # mm: one fresh pseudonym per call

def compact(x):
    return np.unique(x, return_inverse=True)[1]

def time_segments(C, order, delta):
    t = C["t"][order]
    seg_sorted = np.r_[0, np.cumsum(np.diff(t) > delta)]
    seg = np.empty(len(t), np.int64); seg[order] = seg_sorted
    return seg

def union_labels(n, *label_arrays):
    """connected components of calls linked when they share any label in any of the arrays"""
    rows, cols = [], []
    for lab in label_arrays:
        lab = compact(lab)
        first = np.full(lab.max() + 1, -1); idx = np.arange(n)
        o = np.argsort(lab, kind="stable"); ls = lab[o]
        fi = o[np.r_[0, np.nonzero(np.diff(ls))[0] + 1]]
        first[ls[np.r_[0, np.nonzero(np.diff(ls))[0] + 1]]] = fi
        rows.append(idx); cols.append(first[lab])
    g = sp.csr_matrix((np.ones(sum(len(r) for r in rows), np.int8), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    return connected_components(g, directed=False)[1]

def stage1_atoms(C, fmt, order, d_s):
    """identifier groups merged through co-occurrence in clean (<= MAX_TASK calls) timing segments"""
    n = len(C["t"])
    pid = compact(pseudonym(C, fmt))
    if fmt == "clear":
        return pid, {}
    seg = time_segments(C, order, d_s)
    segsize = np.bincount(seg)
    clean = segsize[seg] <= MAX_TASK
    gsize = np.bincount(pid)
    # pairs of calls within the same clean segment (sorted order, offsets 1..MAX_TASK-1)
    so = order[clean[order]]
    segs = seg[so]; ids = pid[so]
    pa, pb, ps = [], [], []
    for k in range(1, MAX_TASK):
        m = segs[k:] == segs[:-k]
        a, b = ids[:-k][m], ids[k:][m]
        keep = a != b
        pa.append(np.minimum(a, b)[keep]); pb.append(np.maximum(a, b)[keep]); ps.append(segs[:-k][m][keep])
    pa, pb, ps = map(np.concatenate, (pa, pb, ps))
    stats = {"clean_segment_call_fraction": float(clean.mean()), "segments": int(len(segsize)),
             "largest_segment": int(segsize.max())}
    if len(pa) == 0:
        return pid, stats
    # one count per (segment, pair)
    trip = np.unique(np.stack([ps, pa, pb], 1), axis=0)
    pr, cnt = np.unique(trip[:, 1:], axis=0, return_counts=True)
    need = np.minimum(2, np.minimum(gsize[pr[:, 0]], gsize[pr[:, 1]]))
    e = pr[cnt >= need]
    G = len(gsize)
    g = sp.csr_matrix((np.ones(len(e), np.int8), (e[:, 0], e[:, 1])), shape=(G, G))
    comp = connected_components(g, directed=False)[1]
    stats["merge_edges"] = int(len(e))
    return comp[pid], stats

def hard_em(Z, K, rng, fields, max_iter=10, alpha=1.0, chunk=4096):
    """hard-EM multinomial mixture on atom count matrix Z (csr, atoms x V). returns atom->cluster"""
    A = Z.shape[0]
    if A <= K:
        return np.arange(A), {"iterations": 0, "note": "atoms <= K, no clustering"}
    cols = np.concatenate([np.arange(*OFF[f]) for f in fields])
    Zs = Z[:, cols].tocsr().astype(np.float32)
    flds = [(f, OFF[f][1] - OFF[f][0]) for f in fields]
    fslices = []; o = 0
    for f, w in flds:
        fslices.append((o, o + w)); o += w
    glob = np.asarray(Zs.sum(0)).ravel() + 1e-3
    gnorm = np.zeros_like(glob)
    for a, b in fslices:
        gnorm[a:b] = glob[a:b] / glob[a:b].sum()
    weight = np.asarray(Zs.sum(1)).ravel()
    p = (weight + 1e-3) / (weight + 1e-3).sum()
    seeds = rng.choice(A, K, replace=False, p=p)
    def theta(counts):
        lt = np.empty_like(counts, dtype=np.float32)
        for a, b in fslices:
            c = counts[:, a:b]
            lt[:, a:b] = np.log((c + alpha * gnorm[a:b]) / (c.sum(1, keepdims=True) + alpha))
        return lt
    counts = Zs[seeds].toarray()
    assign = np.full(A, -1); hist = []
    for it in range(max_iter):
        lt = theta(counts).T.copy()
        new = np.empty(A, np.int64); best = np.empty(A, np.float32)
        for i in range(0, A, chunk):
            S = Zs[i:i + chunk].toarray() @ lt
            j = S.argmax(1); new[i:i + chunk] = j; best[i:i + chunk] = S[np.arange(len(j)), j]
        changed = float((new != assign).mean()); assign = new; hist.append(changed)
        sizes = np.bincount(assign, minlength=K)
        empty = np.nonzero(sizes == 0)[0]
        if len(empty):
            fit = best / np.maximum(weight, 1e-3)
            worst = np.argsort(fit)[:len(empty)]
            assign[worst] = empty
            sizes = np.bincount(assign, minlength=K)
        R = sp.csr_matrix((np.ones(A, np.float32), (assign, np.arange(A))), shape=(K, A))
        counts = (R @ Zs).toarray()
        if changed < 0.002:
            break
    return assign, {"iterations": len(hist), "changed_fraction": hist}


# ----------------------------------------------------------------------------------------------- metrics
c2 = lambda x: (x.astype(np.int64) * (x.astype(np.int64) - 1)) // 2

def metrics(lab, C):
    user, task = C["user"], C["task"]; n = len(lab)
    lab = compact(lab); NU = int(user.max()) + 1
    key = lab.astype(np.int64) * NU + user
    uk, nij = np.unique(key, return_counts=True)
    ci, uj = uk // NU, uk % NU
    a = np.bincount(lab); b = np.bincount(user, minlength=NU)
    TP = int(c2(nij).sum()); P = int(c2(a).sum()); Tt = int(c2(b).sum()); tot = n * (n - 1) // 2
    prec = TP / P if P else None; rec = TP / Tt
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0.0
    exp = P * Tt / tot
    ari = (TP - exp) / (0.5 * (P + Tt) - exp) if (0.5 * (P + Tt) - exp) else 1.0
    bp = float((nij.astype(float) ** 2 / a[ci]).sum() / n); br = float((nij.astype(float) ** 2 / b[uj]).sum() / n)
    tk = np.unique(task.astype(np.int64) * (lab.max() + 1) + lab, return_counts=True)[1]
    sess_rec = int(c2(tk).sum()) / int(c2(np.bincount(task)).sum())
    o = np.lexsort((-nij, uj)); first = np.r_[True, np.diff(uj[o]) != 0]
    bi = o[first]
    act = b[uj[bi]] > 0
    reid = (nij[bi] >= .5 * b[uj[bi]]) & (nij[bi] / a[ci[bi]] >= .8)
    return {"pairs_pred": P, "pairs_true": Tt, "TP": TP, "FP": P - TP, "FN": Tt - TP, "precision": prec, "recall": rec,
            "f1": f1, "session_recall": sess_rec, "ari": ari, "bcubed_precision": bp, "bcubed_recall": br,
            "bcubed_f1": 2 * bp * br / (bp + br), "reid_rate": float(reid[act].mean()), "reid_users": int(reid[act].sum()),
            "clusters": int(len(a)), "largest_cluster": int(a.max())}

def posterior(lab, Xvis, Lt, targets, true_user, rng, purity, tool, cap=200, tchunk=40):
    """auxiliary-profile attacker posterior over users for each target call given its attacker cluster.
    Contamination-robust likelihood: the target call is from the target user; every other call of the cluster is
    from the same user w.p. `purity` (the attacker's estimate of cluster purity; we give it the true B-cubed
    precision of the clustering) and otherwise from the population marginal. Clusters larger than `cap` calls
    are subsampled to `cap` (target always kept).
    Tools enter as a PRESENCE model (each distinct tool of the cluster once: is it among the user's favourites?)
    rather than as per-call multinomial draws: clusters built from per-tool pseudonyms are selected BY tool, and a
    per-call multinomial tool likelihood is then badly over-confident (pilot: H = 0.7 bits with 7 % top-1)."""
    N = Lt.shape[0]
    a, b = OFF["tool"]
    ind = (Lt[:, a:b] > np.log(1e-5)).astype(np.float64)           # N x T favourite indicator
    q = ind.mean(0)
    log_t_target = np.log(ind * (1 - 1e-6) + 1e-6).T              # T x N
    log_t_member = np.log(purity * ind + (1 - purity) * q[None, :] + 1e-12).T
    Xnt = Xvis.tolil(copy=True); Xnt[:, a:b] = 0; Xnt = Xnt.tocsr()
    has_tool = Xvis[:, a:b].sum() > 0
    Xvis = Xnt
    LtT = np.ascontiguousarray(Lt.T)
    o = np.argsort(lab, kind="stable"); ls = lab[o]
    starts = np.searchsorted(ls, lab[targets], "left"); ends = np.searchsorted(ls, lab[targets], "right")
    lpi = np.log(max(purity, 1e-9)); l1pi = np.log(max(1 - purity, 1e-9)); logN = np.log(N)
    Hs, set99s, pts, top1s, ranks = [], [], [], [], []
    for c0 in range(0, len(targets), tchunk):
        rows_t, rows_o, owner = [], [], []
        for i in range(c0, min(c0 + tchunk, len(targets))):
            mem = o[starts[i]:ends[i]]; mem = mem[mem != targets[i]]
            if len(mem) > cap - 1:
                mem = rng.choice(mem, cap - 1, replace=False)
            rows_o.append(mem); owner.append(np.full(len(mem), i - c0))
        tg = targets[c0:c0 + tchunk]
        LL = (Xvis[tg] @ LtT).astype(np.float64)                 # target call: certainly the target user's
        mem = np.concatenate(rows_o); own = np.concatenate(owner)
        if has_tool:
            LL += log_t_target[tool[tg]]
            if len(mem):
                Pm = np.zeros((len(tg), b - a)); Pm[own, tool[mem]] = 1.0
                Pm[np.arange(len(tg)), tool[tg]] = 0.0
                LL += Pm @ log_t_member
        if len(mem) and purity > 0:
            Lm = (Xvis[mem] @ LtT).astype(np.float64)
            lq = logsumexp(Lm, axis=1, keepdims=True) - logN     # population marginal of each call
            contrib = np.logaddexp(lpi + Lm, l1pi + lq)
            LL += sp.csr_matrix((np.ones(len(own)), (own, np.arange(len(own)))), shape=(len(tg), len(own))) @ contrib
        lp = LL - logsumexp(LL, axis=1, keepdims=True); p = np.exp(lp)
        Hs.append(-(p * lp).sum(1) / np.log(2))
        srt = -np.sort(-p, 1); set99s.append((np.cumsum(srt, 1) < 0.99).sum(1) + 1)
        tu = true_user[c0:c0 + tchunk]; pt = p[np.arange(len(tg)), tu]
        pts.append(pt); top1s.append(p.argmax(1) == tu); ranks.append((p > pt[:, None]).sum(1) + 1)
    H, set99, pt, top1, rank = map(np.concatenate, (Hs, set99s, pts, top1s, ranks))
    return {"targets": int(len(targets)), "purity_used": float(purity), "entropy_bits_mean": float(H.mean()),
            "entropy_bits_median": float(np.median(H)), "eff_anonymity_set_2^H_mean": float((2 ** H).mean()),
            "degree_of_anonymity": float(H.mean() / np.log2(N)), "set99_mean": float(set99.mean()),
            "set99_median": float(np.median(set99)), "p_true_mean": float(pt.mean()), "top1_accuracy": float(top1.mean()),
            "true_rank_median": float(np.median(rank)), "cluster_capped_fraction": float(((ends - starts) > cap).mean())}

def aux_map(Z, Lt, fields, chunk=4096):
    """auxiliary-profile linker: every atom is assigned to its maximum-likelihood user"""
    cols = np.concatenate([np.arange(*OFF[f]) for f in fields])
    Zs = Z[:, cols].tocsr(); LtT = np.ascontiguousarray(Lt[:, cols].T)
    out = np.empty(Z.shape[0], np.int64)
    for i in range(0, Z.shape[0], chunk):
        out[i:i + chunk] = (Zs[i:i + chunk].toarray().astype(np.float32) @ LtT).argmax(1)
    return out


# ----------------------------------------------------------------------------------------------- one run
def run(N, P, seed, lg, bw, d_s_base, formats=FORMATS, strategies=("a", "b", "c", "d", "e"), deltas=DELTAS,
        do_post=True, n_targets=400, log=print):
    t0 = time.time()
    rng = np.random.default_rng(seed)
    U, C, pri = make_world(N, P, rng, lg, bw)
    n = len(C["t"])
    d_s = int(math.ceil(d_s_base * P["gap_scale"]))
    order = np.argsort(C["t"], kind="stable")
    seg_s = time_segments(C, order, d_s)
    hour_w = 1.0 / np.bincount(seg_s)[seg_s]
    world = {"users": N, "calls": n, "tasks": int(C["task"].max() + 1), "same_user_pairs": int(c2(np.bincount(C["user"])).sum()),
             "same_task_pairs": int(c2(np.bincount(C["task"])).sum()), "session_delta_s": d_s,
             "tool_types": {k: int((pri["ttype"] == i).sum()) for i, k in enumerate(["booking", "payment", "search", "utility"])},
             "calls_with_personal_QI": float(((C["origin"] >= 0) | (C["c1"] >= 0) | (C["c2"] >= 0) | (C["c3"] >= 0) | (C["loc"] >= 0) | (C["topics"][:, 0] >= 0)).mean())}
    Lt = user_loglik_table(U, pri) if do_post else None
    trng = np.random.default_rng(seed + 7)
    targets = trng.choice(n, min(n_targets, n), replace=False)
    out = {"world": world, "formats": {}}
    seg_cache = {d: time_segments(C, order, d) for d in deltas}
    for fmt in formats:
        res = {}; tf = time.time()
        vis = visible_fields(fmt)
        Xvis = call_features(C, vis, hour_w) if do_post else None
        pid = pseudonym(C, fmt)
        labs = {}
        if "a" in strategies:
            labs["a_id"] = pid
        if "b" in strategies:
            for d in deltas:
                labs[f"b_time{d}"] = pid if fmt == "clear" else union_labels(n, pid, seg_cache[d])
        if "c" in strategies or "d" in strategies:
            atoms, st = stage1_atoms(C, fmt, order, d_s)
            atoms = compact(atoms)
            A = sp.csr_matrix((np.ones(n, np.float32), (atoms, np.arange(n))), shape=(atoms.max() + 1, n))
            Xall = call_features(C, vis, hour_w)
            Z = (A @ Xall).tocsr()
            res["_stage1"] = {**st, "atoms": int(Z.shape[0])}
            for s, flds in [("c", ["hour"] + [f for f in vis if f in QI_FULL]), ("d", vis)]:
                if s not in strategies: continue
                if s == "c" and fmt.endswith("_min") and N >= 10000:
                    continue  # c on *_min sees only amount + hour; skipped at N = 10,000 for runtime (see N = 1,000)
                ts = time.time()
                asg, info = hard_em(Z, N, np.random.default_rng(seed + 11), flds)
                labs[f"{s}_{'sessQI' if s == 'c' else 'full'}"] = asg[atoms]
                res[f"_{s}_em"] = {**info, "seconds": round(time.time() - ts, 1)}
            if do_post and fmt != "clear" and "e" in strategies:
                labs["e_auxmap"] = aux_map(Z, Lt, vis)[atoms]
            labs["s_session"] = atoms
        for name, lab in labs.items():
            m = metrics(lab, C)
            if do_post:
                if fmt == "clear":
                    m["posterior"] = {"entropy_bits_mean": 0.0, "eff_anonymity_set_2^H_mean": 1.0, "top1_accuracy": 1.0,
                                      "set99_mean": 1.0, "p_true_mean": 1.0, "degree_of_anonymity": 0.0, "note": "principal id visible"}
                else:
                    m["posterior"] = posterior(compact(lab), Xvis, Lt, targets, C["user"][targets], np.random.default_rng(seed + 13), m["bcubed_precision"], C["tool"])
            res[name] = m
        if do_post and fmt != "clear":
            res["call_only"] = {"posterior": posterior(np.arange(n), Xvis, Lt, targets, C["user"][targets], np.random.default_rng(seed + 13), 1.0, C["tool"])}
        res["_seconds"] = round(time.time() - tf, 1)
        out["formats"][fmt] = res
        log(f"  N={N} {fmt:16s} {res['_seconds']:6.1f}s  " + "  ".join(
            f"{k}:F1={v['f1']:.3f},re-id={v['reid_rate']:.3f}" for k, v in res.items() if not k.startswith("_") and "f1" in v))
    out["seconds"] = round(time.time() - t0, 1)
    return out


# ----------------------------------------------------------------------------------------------- report
def fmt_num(x, d=3):
    if x is None: return "n/a"
    if isinstance(x, int): return f"{x:,}"
    return f"{x:.{d}f}"

def summary_md(R):
    L = ["# E3v2 -- realistic collusion study (summary)", "",
         f"Generated by `sim/e3v2.py` (seed {R['seed']}), total runtime {R['runtime_s'] / 60:.1f} min. Full data: `results/e3v2.json`.", "",
         "## Calibration of inter-call gaps (E4 traces)", ""]
    cal = R["calibration"]
    L.append(f"{cal['n_gaps']} within-task gaps from {', '.join(cal['per_model'])}; quantiles (s): " +
             ", ".join(f"{k} {v:.2f}" for k, v in cal["quantiles_s"].items()) +
             f"; log-normal fit mu={cal['lognormal_fit']['mu']:.2f}, sigma={cal['lognormal_fit']['sigma']:.2f}. "
             f"Attacker session gap d_s = {cal['session_delta_s']} s (ceil of p99).")
    L.append("")
    for run in R["main"]:
        N = run["world"]["users"]
        w = run["world"]
        L += [f"## N = {N:,} users ({w['calls']:,} calls, {w['tasks']:,} tasks, {w['same_user_pairs']:,} same-user pairs, "
              f"{w['same_task_pairs']:,} same-task pairs)", "",
              "| format | attacker | precision | recall | F1 | FP pairs | session recall | ARI | B3-F1 | re-id rate | H (bits) | 2^H | top-1 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for fmt, res in run["formats"].items():
            for k, m in res.items():
                if k.startswith("_"): continue
                po = m.get("posterior", {})
                if "f1" not in m:
                    L.append(f"| {fmt} | {k} | | | | | | | | | {fmt_num(po.get('entropy_bits_mean'), 2)} | {fmt_num(po.get('eff_anonymity_set_2^H_mean'), 1)} | {fmt_num(po.get('top1_accuracy'), 2)} |")
                    continue
                L.append(f"| {fmt} | {k} | {fmt_num(m['precision'])} | {fmt_num(m['recall'])} | {fmt_num(m['f1'])} | {m['FP']:,} | "
                         f"{fmt_num(m['session_recall'])} | {fmt_num(m['ari'])} | {fmt_num(m['bcubed_f1'])} | {fmt_num(m['reid_rate'])} | "
                         f"{fmt_num(po.get('entropy_bits_mean'), 2)} | {fmt_num(po.get('eff_anonymity_set_2^H_mean'), 1)} | {fmt_num(po.get('top1_accuracy'), 2)} |")
        L.append("")
    if R.get("replicates"):
        L += ["## Replicates (N = 1,000 baseline, 3 seeds): attacker d", "", "| format | F1 mean (min-max) | re-id mean (min-max) | top-1 mean |", "|---|---|---|---|"]
        for fmt, v in R["replicates"]["summary"].items():
            L.append(f"| {fmt} | {v['f1_mean']:.3f} ({v['f1_min']:.3f}-{v['f1_max']:.3f}) | {v['reid_mean']:.3f} ({v['reid_min']:.3f}-{v['reid_max']:.3f}) | {v['top1_mean']:.2f} |")
        L.append("")
    L += ["## Sensitivity (N = 1,000; one factor at a time)", "",
          "| factor | value | format | b_time10 F1 | b_time10 session recall | d F1 | d FP pairs | d re-id | d H (bits) | d top-1 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for s in R["sensitivity"]:
        for fmt, res in s["result"]["formats"].items():
            b = res.get("b_time10", {}); d = res.get("d_full", {}); po = d.get("posterior", {})
            L.append(f"| {s['factor']} | {s['value']} | {fmt} | {fmt_num(b.get('f1'))} | {fmt_num(b.get('session_recall'))} | {fmt_num(d.get('f1'))} | "
                     f"{d.get('FP', 0):,} | {fmt_num(d.get('reid_rate'))} | {fmt_num(po.get('entropy_bits_mean'), 2)} | {fmt_num(po.get('top1_accuracy'), 2)} |")
    L += ["", "Attackers: a_id = exact pseudonym equality; b_timeD = timing single-linkage at gap <= D s unioned with identifiers; "
          "c_sessQI = sessions + identifier co-occurrence + 30-day clustering on quasi-identifiers and hour; d_full = c + tool-set fingerprint "
          "(combined attacker). H, 2^H, top-1: auxiliary-profile attacker posterior over users for 400 random target calls "
          "(upper bound; over-confident for content-built clusters c/d/e -- compare H with top-1). call_only = target call alone; "
          "s_session = identifier groups + clean-session co-occurrence only; e_auxmap = maximum-likelihood assignment of sessions to users under the true profiles. See the module docstring for all approximations.", ""]
    return "\n".join(L)

def figures(R, outdir):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
    strat = ["a_id", "b_time2", "b_time10", "b_time60", "c_sessQI", "d_full"]
    runs = [r for r in R["main"] if r["world"]["users"] >= 1000]
    fig, axes = plt.subplots(2, len(runs), figsize=(6.2 * len(runs), 7), squeeze=False)
    for j, run in enumerate(runs):
        for i, (metric, lab) in enumerate([("f1", "pairwise F1"), ("reid_rate", "re-identification rate")]):
            ax = axes[i, j]; fm = list(run["formats"]); w = 0.8 / len(strat)
            for k, s in enumerate(strat):
                vals = [run["formats"][f].get(s, {}).get(metric, np.nan) or 0 for f in fm]
                ax.bar(np.arange(len(fm)) + (k - len(strat) / 2 + .5) * w, vals, w * .9, color=cols[k], label=s)
            ax.set_xticks(np.arange(len(fm))); ax.set_xticklabels(fm, rotation=30, ha="right", fontsize=8)
            ax.set_ylim(0, 1.02); ax.set_ylabel(lab); ax.set_title(f"N = {run['world']['users']:,}", fontsize=10)
            ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#ddd", lw=.5)
    axes[0, 0].legend(fontsize=7, ncol=3, frameon=False)
    fig.tight_layout(); fig.savefig(outdir / "e3v2_fig_main.png", dpi=160); plt.close(fig)
    # sensitivity
    sens = R["sensitivity"]; factors = []
    base = [s for s in sens if s["factor"] == "baseline"]
    for s in sens:
        if s["factor"] not in factors and s["factor"] != "baseline": factors.append(s["factor"])
    fig, axes = plt.subplots(1, len(factors), figsize=(2.6 * len(factors), 3.2), sharey=True)
    for ax, fac in zip(np.atleast_1d(axes), factors):
        ss = sorted(base + [s for s in sens if s["factor"] == fac], key=lambda s: str(s["value"]) if s["factor"] != "baseline" else "")
        ss = [{**s, "value": "base"} if s["factor"] == "baseline" else s for s in ss]
        for k, fmt in enumerate(["mm", "mm_min", "pertool_day"]):
            y = [s["result"]["formats"].get(fmt, {}).get("d_full", {}).get("reid_rate", np.nan) for s in ss]
            ax.plot(range(len(ss)), y, "-o", color=cols[k], lw=2, ms=5, label=fmt)
        ax.set_xticks(range(len(ss))); ax.set_xticklabels([str(s["value"]) for s in ss], fontsize=7, rotation=20)
        ax.set_title(fac, fontsize=9); ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#ddd", lw=.5)
    np.atleast_1d(axes)[0].set_ylabel("re-id rate (attacker d)"); np.atleast_1d(axes)[0].legend(fontsize=7, frameon=False)
    fig.tight_layout(); fig.savefig(outdir / "e3v2_fig_sens.png", dpi=160); plt.close(fig)


# ----------------------------------------------------------------------------------------------- main
def regen_figures(outdir=ROOT / "results"):
    """re-draw the figures from an existing results/e3v2.json (no simulation)"""
    figures(json.load(open(outdir / "e3v2.json")), outdir)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--quick", action="store_true"); ap.add_argument("--out", default="results")
    args = ap.parse_args()
    T0 = time.time()
    outdir = ROOT / args.out; outdir.mkdir(exist_ok=True)
    cal, lg, bw = calibrate()
    d_s = cal["session_delta_s"]
    log = lambda *a: print(*a, file=sys.stderr, flush=True)
    log("calibration:", json.dumps({k: cal[k] for k in ("n_gaps", "quantiles_s", "session_delta_s")}))
    sizes = [100, 1000] if args.quick else [100, 1000, 10000]
    R = {"seed": SEED, "description": __doc__, "params": {**BASE, "tools": T_TOOLS, "days": DAYS, "cities": N_CITIES, "topics": N_TOPICS,
         "max_task_len_known_to_attacker": MAX_TASK, "deltas_s": DELTAS, "formats": FORMATS, "posterior_targets": 400, "posterior_cap_calls": 200},
         "calibration": cal, "main": [], "replicates": {}, "sensitivity": []}
    for i, N in enumerate(sizes):
        log(f"== main N={N}")
        R["main"].append(run(N, BASE, SEED + 1000 * (i + 1), lg, bw, d_s, log=log))
    # replicates
    fm3 = ["mm", "mm_min", "pertool_day"]
    reps = []
    for r in range(3):
        log(f"== replicate {r}")
        reps.append(run(1000, BASE, SEED + 50000 + r, lg, bw, d_s, formats=fm3, strategies=("d", "e"), log=log))
    R["replicates"] = {"seeds": [SEED + 50000 + r for r in range(3)], "runs": reps, "summary": {
        f: {"f1_mean": float(np.mean([x["formats"][f]["d_full"]["f1"] for x in reps])),
            "f1_min": float(np.min([x["formats"][f]["d_full"]["f1"] for x in reps])),
            "f1_max": float(np.max([x["formats"][f]["d_full"]["f1"] for x in reps])),
            "reid_mean": float(np.mean([x["formats"][f]["d_full"]["reid_rate"] for x in reps])),
            "reid_min": float(np.min([x["formats"][f]["d_full"]["reid_rate"] for x in reps])),
            "reid_max": float(np.max([x["formats"][f]["d_full"]["reid_rate"] for x in reps])),
            "top1_mean": float(np.mean([x["formats"][f]["d_full"]["posterior"]["top1_accuracy"] for x in reps]))} for f in fm3}}
    # sensitivity
    grid = [("favourites", "fav", [(1, 3), (8, 15)]), ("tasks_per_day", "tasks", [(0, 1), (2, 6)]),
            ("tool_zipf_s", "zipf", [0.5, 1.5]), ("frac_personal_tools", "f_pers", [0.0, 0.1, 0.6]),
            ("gap_scale", "gap_scale", [10.0]), ("timing_jitter_s", "jitter", [60, 600])]
    sens_list = [("baseline", "-", dict(BASE))] + [(name, v, {**BASE, key: v}) for name, key, vals in grid for v in vals]
    for k, (name, v, P) in enumerate(sens_list):
        log(f"== sensitivity {name}={v}")
        res = run(1000, P, SEED + 90000 + k, lg, bw, d_s, formats=fm3, strategies=("b", "d", "e"), deltas=[10], log=log)
        R["sensitivity"].append({"factor": name, "value": list(v) if isinstance(v, tuple) else v, "params": {kk: (list(x) if isinstance(x, tuple) else x) for kk, x in P.items()}, "result": res})
    R["runtime_s"] = round(time.time() - T0, 1)
    json.dump(R, open(outdir / "e3v2.json", "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    (outdir / "e3v2_summary.md").write_text(summary_md(R))
    figures(R, outdir)
    log(f"done in {R['runtime_s'] / 60:.1f} min")

if __name__ == "__main__":
    main()
