"""E3 v2.1 -- collusion / linkage study for anonymous delegation tokens (revision of sim/e3v2.py for reviewers R2, R5).

Usage (run from code/):
  python sim/e3v21.py calib  --cal CAL.json                       # E4 v2 gap calibration (reads results/e4v2/*.json)
  python sim/e3v21.py tasks  [--shard i --nshards m]              # list of cell ids (heaviest first)
  python sim/e3v21.py cell   CELL_ID --cal CAL.json --cells DIR   # one (group, setting, N, seed, format) cell -> DIR/CELL_ID.json
  python sim/e3v21.py aggregate --cal CAL.json --cells DIR        # -> results/e3v21.json, results/e3v21_summary.md, results/e3v21_*.png
  python sim/e3v21.py quick  --cal CAL.json --cells DIR           # small local smoke test (N = 300, 1 seed)
Cluster driver: see the summary (Slurm array of whole-node jobs, each running its shard of cells with xargs -P).
Deterministic: master seed 20261109; world seeds SEEDS = SEED + 101 r, r = 0..4, IDENTICAL for every setting and
population size (common random numbers); every random component (world, gaps, jitter, amounts, identities, attacker
initialisation) uses its own stream np.random.default_rng([seed, stream]).

CHANGES W.R.T. E3v2 (see e3v2.py for the unchanged parts of the population model)
1. Timestamps in MILLISECONDS (P['res_ms'] = 1; sensitivity 1000 = old 1-s resolution). New attacker "b_track": an
   online multi-session tracker that de-interleaves overlapping sessions with ms timing: calls are processed in time
   order; a call continues the open session s that maximises  log h(len_s) + log f(t - t_last(s)) [+ log P(dj)]  if
   that beats the new-session intensity log lambda(hour), otherwise it opens a new session. f = density of
   within-task gaps between consecutive VISIBLE calls, h = continuation hazard of visible task lengths, lambda =
   visible task-start intensity per ms by hour, P(dj) = distribution of counter increments (formats revealing j).
   These four population-level distributions are GIVEN to the attacker (estimated from the ground truth of the same
   world; they are 1-D nuisance parameters an attacker could fit by EM -- this favours the attacker). Sessions are
   capped at MAX_TASK = 6 calls (known). b_trackT = timing (+ counter) only; b_trackA = timing + exact amounts.
2. Exact amounts (cents). Every booking/search call returns 1-5 offer prices (cents; half rounded to whole euros);
   each payment amount equals one offer of the latest earlier booking/search call of the same task (w.p. p_quote = 1)
   -- e.g. the hotel price returned by the search equals the payment to the cent. The paying tool sees the amount
   (Masked Mandates reveals amt to tools by design); the quoting tool knows the prices it returned. The tracker joins a
   payment to the open session that holds a quote with exactly that amount (priority over timing). The binned amount
   remains a clustering feature (as in v2). Amounts are visible in every format, including *_min.
3. "Identified tool" attacker. Mode "natural": in every task that contains a payment (else booking) call, the first
   such call legitimately reveals the user's identity (name / card) to that tool. Mode "every": one uniformly chosen
   call of EVERY task reveals it (worst case: every task touches an identifying tool). The coalition then
     id_sess : propagates the name to every call of the stage-1 atom (reconstructed session + identifier merges);
     id_clu  : additionally names each attacker-d content cluster by the majority name of its identified calls;
     id_cls  : additionally trains per-name multinomial profiles on the named atoms (Dirichlet shrinkage alpha=1,
               features tool + hour + visible quasi-identifiers) and assigns every unnamed atom to its maximum-
               likelihood name (2 self-training rounds; forced); id_cls_conf = only atoms with log-likelihood margin
               >= log 100 over the runner-up.
   Reported: fraction of visible calls attributed to the RIGHT name (calls_correct), attributed fraction and
   precision, fraction of tasks whose visible calls are in majority attributed to the right name (tasks_correct),
   fraction of users that are named at all.
4. Partial coalitions: only the top-k tools by popularity (k in {5, 10, 25, 50}) pool their logs; metrics are over
   calls visible to the coalition; an identifying call counts only if its tool is in the coalition.
5. Formats (what each tool logs per call besides tool, ms timestamp, action class, exact amount):
     clear        principal id
     pertool      stable per-(user, tool) pseudonym
     pertool_day  per-(user, tool, day) pseudonym
     mm           Masked Mandates: fresh unlinkable token per call (counter j hidden)
     ott          one-time tokens (batch-issued / blind-signed): a fresh random serial per call. From the tools' view
                  this is IDENTICAL to mm (one unlinkable value per call, same visible fields), so all numbers must
                  coincide with mm; they are computed independently (different token values) to show it. Issuer-side
                  batch linkage is out of scope (the issuer is not in the tool coalition).
     ptej         per-(tool, epoch=day) pseudonym + revealed counter j; one tree per task (mandate per task): j = index
                  of the call in the task's tree (0, 1, 2, ...). The tracker enforces the counter: j = 0 always opens a
                  session, j > 0 can only continue a session whose last visible counter is < j (P(dj) weighted).
     ptejday      same pseudonym, one tree per (user, day): j = number of calls the user made earlier that day. Besides
                  the within-session constraint, the stage-1 atoms (sessions + pseudonym groups) are chained across the
                  day (day_chain): an atom whose smallest counter is m > 0 is linked to an atom holding m-1 but not m,
                  with a disjoint counter set and a merged counter sequence whose times increase; among feasible pairs of
                  each (day, m), a linear assignment on cosine similarity of visible features picks the links; 3 rounds
                  (full coalition only).
     *_min        content minimisation: arguments stripped of personal quasi-identifiers (tool, time, action class
                  and the amount remain).
6. Statistics: 5 world seeds for every cell (main, sensitivity, coalition), the same seeds everywhere; mean, min-max
   and a percentile bootstrap 95 % CI of the mean over seeds (10,000 resamples; with 5 draws this CI is narrow and
   should be read as descriptive). All draws are listed at default settings.
   Stage-1 merge of identifier groups (pseudonyms) through reconstructed sessions: two groups are merged if they
   co-occur in >= min(2, smaller group size) sessions AND in >= 30 % of the sessions of the group seen in fewer
   sessions (MERGE_RATIO). The ratio makes the merge robust to tracker errors, which otherwise chain all per-tool
   groups into giant components (pilot on seed 0, N = 1,000, pertool: profile recovery 0.18 / 0.76 / 0.89 / 0.91 for
   ratio 0 / 0.1 / 0.2 / 0.3; no effect on any other format). Fixed at 0.3 before the main runs.
7. Metrics: "profile recovery" (was "re-identification"): a user's profile is recovered if the attacker cluster that
   holds most of the user's visible calls holds >= 50 % of them and >= 80 % of that cluster's calls are the user's;
   rate over users with >= 10 visible calls. Pairwise / B-cubed / ARI as in v2. "e_oracle" (was e_auxmap) =
   profile-oracle attacker: each stage-1 atom is assigned to its maximum-likelihood user under the TRUE generative
   profiles; it is NOT an upper bound (it cannot merge evidence across atoms the way clustering does and its atoms
   may be impure) -- cells where it is below d_full are flagged. Per-call top-1 identification by the profile-oracle
   posterior (v2 posterior code) from the call alone, from its reconstructed session (b_trackA session), from its
   stage-1 atom, from a_id and d_full clusters.
8. Gap calibration on E4 v2 traces (results/e4v2/e4v2_<model>.json, 5 models; see calibrate()): rows with injected
   latency (cfg latency=True), no harness error, modes mm and mm_esc (the deployment under study; 'none' mode gaps
   are a sensitivity setting). Per row, the run is replayed as a sequential timeline: LLM turns in their recorded
   (chronological) order, each turn of role r ending in tool_calls is followed by the MCP calls assigned to it, each
   call = prep_ms (token preparation / proof) then rtt_ms (request + injected latency + verification + response);
   a main turn immediately followed by sub-agent turns is the delegation turn and adds deleg_ms. Calls are assigned
   to turns per role: one call per turn; if a role has more calls than tool turns, extra calls are packed into the
   previous turn, identical consecutive calls first (parallel tool calls); rows where a role has fewer recorded calls
   than tool turns (turn whose calls were not recorded) are skipped. The tool timestamp of a call = time it is
   sent (end of prep); gaps = differences between consecutive tool timestamps of the same task (main and sub-agent
   calls included). The replay matches the recorded wall time to a median 13-22 ms per model (mm) and < 1 ms (none).
   Payment calls are placed after the task's other calls (search / booking first, then pay).
9. Timing mitigation: before every call but the first of a task the agent waits D ~ U(0, J) (sequential loop: the
   delays accumulate); latency cost = sum of D over a task (reported mean and p95) and J/2 per call.
"""
import json, math, sys, time, argparse, os, hashlib
from collections import Counter
from pathlib import Path
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.special import ndtr, logsumexp
from scipy.optimize import linear_sum_assignment

SEED = 20261109
SEEDS = [SEED + 101 * r for r in range(5)]
ROOT = Path(__file__).resolve().parent.parent
T_TOOLS, DAYS, N_CITIES, N_TOPICS = 50, 30, 200, 100
MAX_TASK = 6
DAY_MS, HOUR_MS = 86_400_000, 3_600_000
MIN_PR_CALLS = 10
MERGE_RATIO = 0.3   # identifier-group merge: co-occurrence in >= 30 % of the smaller group's sessions (see docstring)
E4V2_MODELS = ["gpt-oss-20b", "granite-3.3-8b-instruct", "hermes-3-llama-3.1-8b", "qwen2.5-72b-instruct-awq", "qwen2.5-7b-instruct"]
BASE = dict(fav=(3, 8), tasks=(0, 3), zipf=1.0, f_pers=0.30, f_search=0.40, task_len=(2, 6), gap_scale=1.0,
            gap_source="mm", jitter_ms=0, res_ms=1, p_quote=1.0, offers=(1, 5), k=50)

FIELDS = [("tool", T_TOOLS), ("hour", 24), ("origin", N_CITIES), ("party", 6), ("c1", 4), ("c2", 10), ("c3", 3),
          ("topic", N_TOPICS), ("loc", N_CITIES), ("amt", 25)]
OFF = {}
_o = 0
for _f, _n in FIELDS:
    OFF[_f] = (_o, _o + _n); _o += _n
V = _o
QI_FULL = ["origin", "party", "c1", "c2", "c3", "topic", "loc", "amt"]
QI_MIN = ["amt"]
FORMATS = ["clear", "pertool", "pertool_min", "pertool_day", "pertool_day_min", "mm", "mm_min", "ott", "ott_min",
           "ptej", "ptej_min", "ptejday", "ptejday_min"]
DELTAS_MS = [500, 2000, 10000, 60000]
COAL_K = [5, 10, 25]
COAL_FORMATS = ["pertool", "pertool_day", "mm", "mm_min", "ptej"]
SENS_FORMATS = ["mm", "mm_min", "pertool_day", "ptej"]
SENS = [("favourites", "fav", [(1, 3), (8, 15)]), ("tasks_per_day", "tasks", [(0, 1), (2, 6)]),
        ("tool_zipf_s", "zipf", [0.5, 1.5]), ("frac_personal_tools", "f_pers", [0.0, 0.1, 0.6]),
        ("gap_scale", "gap_scale", [0.1, 10.0]), ("gap_source", "gap_source", ["none"]),
        ("timestamp_res_ms", "res_ms", [1000]), ("p_quote", "p_quote", [0.0]),
        ("jitter_ms", "jitter_ms", [1000, 10000, 60000, 600000])]


def base_fmt(f):
    return f[:-4] if f.endswith("_min") else f

def ctr_kind(f):
    b = base_fmt(f)
    return "task" if b == "ptej" else ("day" if b == "ptejday" else None)


# =============================================================================================== calibration
def _pack(names, n_turns):
    """assign len(names) >= n_turns calls (in order) to n_turns turns; returns turn index per call"""
    n = len(names); extra = n - n_turns
    keep = [True] * n
    i = n - 1
    while extra > 0 and i > 0:                       # identical consecutive calls share a turn (parallel calls)
        if keep[i] and names[i] == names[i - 1]:
            keep[i] = False; extra -= 1
        i -= 1
    i = n - 1
    while extra > 0 and i > 0:                       # fallback: latest calls packed into the previous turn
        if keep[i]:
            keep[i] = False; extra -= 1
        i -= 1
    k, out = -1, []
    for x in keep:
        if x: k += 1
        out.append(max(k, 0))
    return out

def replay(r):
    """sequential timeline of one E4 v2 row -> (tool timestamps ms, end time ms) or None if turns are ambiguous"""
    llm, calls, deleg = r["llm"], r["calls"], r.get("deleg") or []
    turns = {"main": [], "sub": []}; deleg_turns = []
    for k, l in enumerate(llm):
        if l.get("finish") != "tool_calls":
            continue
        nxt = llm[k + 1]["role"] if k + 1 < len(llm) else None
        if l["role"] == "main" and nxt == "sub":
            deleg_turns.append(k); continue
        turns.setdefault(l["role"], []).append(k)
    if len(deleg_turns) != len(deleg):
        return None
    assign = {}
    for role, tt in turns.items():
        ci = [i for i, c in enumerate(calls) if c["role"] == role]
        if not ci:
            continue
        if len(ci) < len(tt) or not tt:
            return None
        tix = _pack([calls[i]["name"] for i in ci], len(tt))
        for i, ti in zip(ci, tix):
            assign.setdefault(tt[ti], []).append(i)
    t, arr, di = 0.0, [], 0
    dset = set(deleg_turns)
    for k, l in enumerate(llm):
        t += float(l["ms"])
        if k in dset:
            t += float(deleg[di].get("deleg_ms", 0) or 0); di += 1
            continue
        for i in assign.get(k, []):
            c = calls[i]
            if "rtt_ms" not in c:                    # unparsed / invalid call: never reached a tool
                continue
            t += float(c.get("prep_ms", 0)); arr.append(t); t += float(c["rtt_ms"])
    return arr, t

def calibrate_modes(modes):
    gaps, per_model = [], {}
    for m in E4V2_MODELS:
        d = json.load(open(ROOT / "results" / "e4v2" / f"e4v2_{m}.json"))
        g_m, used, skip, resid = [], 0, Counter(), []
        for r in d["rows"]:
            if r["mode"] not in modes:
                continue
            if r.get("latency") not in (True, "True"):
                skip["no_injected_latency"] += 1; continue
            if r.get("error") not in (None, "None", ""):
                skip["harness_error"] += 1; continue
            tl = replay(r)
            if tl is None:
                skip["ambiguous_turns"] += 1; continue
            arr, end = tl
            used += 1
            resid.append(float(r["wall_ms"]) - end)
            if len(arr) >= 2:
                g_m += list(np.diff(arr))
        gaps += g_m
        per_model[m] = {"rows_used": used, "rows_skipped": dict(skip), "gaps": len(g_m),
                        "median_ms": float(np.median(g_m)), "p90_ms": float(np.quantile(g_m, .9)),
                        "p99_ms": float(np.quantile(g_m, .99)), "max_ms": float(np.max(g_m)),
                        "replay_minus_wall_ms_median": float(np.median(np.abs(resid)))}
    g = np.maximum(np.array(gaps), 1e-3)
    lg = np.log(g)
    bw = 1.06 * lg.std() * len(lg) ** (-1 / 5)
    qs = {f"p{q * 100:g}": float(np.quantile(g, q)) for q in (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 0.999)}
    return {"modes": list(modes), "per_model": per_model, "n_gaps": int(len(g)), "quantiles_ms": qs,
            "mean_ms": float(g.mean()), "kernel_bw_log": float(bw), "log_gaps_ms": [round(float(x), 6) for x in lg]}

def calibrate():
    out = {"source": [f"results/e4v2/e4v2_{m}.json" for m in E4V2_MODELS],
           "method": "replay of each row as a sequential timeline (LLM ms, prep_ms, rtt_ms, deleg_ms); see module docstring item 8",
           "mm": calibrate_modes(("mm", "mm_esc")), "none": calibrate_modes(("none",)),
           "jwt": calibrate_modes(("jwt",))}
    out["jwt"].pop("log_gaps_ms")
    return out


# =============================================================================================== world
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
    u = rng.random(n)[:, None]
    return np.minimum((cum < u).sum(1), cum.shape[1] - 1)

def amount_eur(rng, budget, party, n):
    return budget * (party + 1) * np.exp(rng.normal(0, .6, n))

def to_cents(rng, eur):
    whole = rng.random(len(eur)) < .5
    return np.where(whole, np.round(eur) * 100, np.round(eur * 100)).astype(np.int64)

def make_world(N, P, seed, cal):
    rs = lambda k: np.random.default_rng([seed, k])
    rng = rs(1)
    T = T_TOOLS
    pop = zipf(T, P["zipf"])
    n_pers = int(round(P["f_pers"] * T)); n_search = min(int(round(P["f_search"] * T)), T - n_pers)
    perm = rs(2).permutation(T)
    ttype = np.full(T, 3)  # 0 booking, 1 payment, 2 search, 3 utility
    n_book = (n_pers + 1) // 2
    ttype[perm[:n_book]] = 0; ttype[perm[n_book:n_pers]] = 1; ttype[perm[n_pers:n_pers + n_search]] = 2
    citypop = zipf(N_CITIES, 1.0); topicpop = zipf(N_TOPICS, 0.8); localepop = zipf(10, 1.0)
    party_p = np.array([.35, .30, .15, .12, .05, .03]); c1_p = np.array([.5, .3, .15, .05]); c3_p = np.array([.6, .3, .1])
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
    rt = rs(3)
    ntask = rt.integers(P["tasks"][0], P["tasks"][1] + 1, size=(N, DAYS))
    t_user = np.repeat(np.repeat(np.arange(N), DAYS), ntask.ravel())
    t_day = np.repeat(np.tile(np.arange(DAYS), N), ntask.ravel())
    M = len(t_user)
    comp = rt.choice(4, M, p=[.3 * .95, .35 * .95, .35 * .95, .05])
    mu = np.array([9.5, 14.0, 20.5, 0]); sd = np.array([1.5, 2.0, 2.0, 0])
    h = np.where(comp == 3, rt.uniform(0, 24, M), rt.normal(mu[comp], np.maximum(sd[comp], 1e-9)) + U["shift"][t_user])
    h = np.mod(h, 24.0)
    t_start = t_day * float(DAY_MS) + h * HOUR_MS
    L = rt.integers(P["task_len"][0], P["task_len"][1] + 1, size=M)
    c_task = np.repeat(np.arange(M), L)
    C = len(c_task)
    c_user = t_user[c_task]
    first = np.r_[0, np.cumsum(L)[:-1]]
    pos = np.arange(C) - np.repeat(first, L)
    # inter-call gaps (ms) from the E4 v2 kernel, + sequential random delays (mitigation)
    lg = np.asarray(cal[P["gap_source"]]["log_gaps_ms"]); bw = cal[P["gap_source"]]["kernel_bw_log"]
    rg = rs(4)
    gaps = np.exp(lg[rg.integers(0, len(lg), C)] + bw * rg.normal(size=C)) * P["gap_scale"]
    gaps[first] = 0.0
    delay = np.zeros(C)
    if P["jitter_ms"]:
        delay = rs(5).uniform(0, P["jitter_ms"], C); delay[first] = 0.0
    cs = np.cumsum(gaps + delay)
    t = t_start[c_task] + cs - np.repeat(cs[first], L)
    res = P["res_ms"]
    t = (np.floor(t / res) * res).astype(np.int64)
    task_delay = np.bincount(c_task, weights=delay, minlength=M)
    # tools and content
    rc = rs(6)
    tool = fav[c_user, cat_sample(rc, np.cumsum(favw, 1)[c_user], C)]
    o = np.lexsort((pos, ttype[tool] == 1, c_task))           # agent loop: payments after the task's other calls
    tool = tool[o]
    ty = ttype[tool]
    F = {f: np.full(C, -1, np.int64) for f in ["origin", "party", "c1", "c2", "c3", "loc", "amt"]}
    topics = np.full((C, 3), -1, np.int64)
    b = ty == 0; nb = int(b.sum()); ub = c_user[b]
    F["origin"][b] = np.where(rc.random(nb) < .8, U["home"][ub], rc.choice(N_CITIES, nb, p=citypop))
    F["party"][b] = np.where(rc.random(nb) < .85, U["party"][ub], rc.integers(0, 6, nb))
    F["c1"][b] = np.where(rc.random(nb) < .7, U["c1"][ub], -1)
    F["c2"][b] = np.where(rc.random(nb) < .7, U["c2"][ub], -1)
    p = ty == 1; npay = int(p.sum()); up = c_user[p]
    ra = rs(7)
    eur = amount_eur(ra, U["budget"][up], U["party"][up], npay)
    amt_c = np.full(C, -1, np.int64); amt_c[p] = to_cents(ra, eur)
    F["amt"][p] = np.clip(np.floor(np.log(np.maximum(amt_c[p] / 100.0, 1)) / np.log(1.5)), 0, 24).astype(np.int64)
    F["c3"][p] = np.where(rc.random(npay) < .7, np.where(rc.random(npay) < .9, U["c3"][up], rc.integers(0, 3, npay)), -1)
    F["c2"][p] = np.where(rc.random(npay) < .5, U["c2"][up], -1)
    s = ty == 2; ns = int(s.sum()); us = c_user[s]
    nq = rc.integers(1, 4, ns)
    icum = np.cumsum(U["intw"], 1)
    for j in range(3):
        own = U["int"][us, cat_sample(rc, icum[us], ns)]
        glob = rc.choice(N_TOPICS, ns, p=topicpop)
        v = np.where(rc.random(ns) < .8, own, glob)
        topics[s, j] = np.where(j < nq, v, -1)
    F["loc"][s] = np.where(rc.random(ns) < .3, U["home"][us], -1)
    # offers returned by booking / search calls; payment amount = one offer of the latest earlier quote call of the task
    isq = (ty == 0) | (ty == 2)
    qidx = np.where(isq, np.arange(C), -1)
    lastq = np.maximum.accumulate(qidx)
    prevq = np.r_[-1, lastq[:-1]]
    task_first = first[c_task]
    pay_idx = np.nonzero(p)[0]
    qcall = prevq[pay_idx]
    has_q = (qcall >= task_first[pay_idx]) & (ra.random(npay) < P["p_quote"])
    nof = ra.integers(P["offers"][0], P["offers"][1] + 1, C)
    qi = np.nonzero(isq)[0]
    n_dec = np.maximum(nof[qi] - np.bincount(qcall[has_q], minlength=C)[qi], 0)
    dec_call = np.repeat(qi, n_dec)
    dec_val = to_cents(ra, amount_eur(ra, U["budget"][c_user[dec_call]], U["party"][c_user[dec_call]], len(dec_call)))
    off_call = np.r_[dec_call, qcall[has_q]]; off_val = np.r_[dec_val, amt_c[pay_idx[has_q]]]
    o = np.argsort(off_call, kind="stable"); off_call, off_val = off_call[o], off_val[o]
    # counters
    rj = np.lexsort((t, c_user * DAYS + t // DAY_MS))
    g = (c_user * DAYS + t // DAY_MS)[rj]
    gstart = np.r_[0, np.nonzero(np.diff(g))[0] + 1]
    jday = np.empty(C, np.int64); jday[rj] = np.arange(C) - np.repeat(gstart, np.diff(np.r_[gstart, C]))
    # identifying calls
    score = np.where(ty == 1, pos, np.where(ty == 0, 100 + pos, 10 ** 9))
    o = np.lexsort((score, c_task)); fo = o[np.r_[0, np.nonzero(np.diff(c_task[o]))[0] + 1]]
    idnat = np.zeros(C, bool); idnat[fo[score[fo] < 10 ** 9]] = True
    idall = np.zeros(C, bool); idall[first + (rs(8).random(M) * L).astype(np.int64)] = True
    calls = dict(user=c_user, task=c_task, day=t // DAY_MS, t=t, tool=tool, ty=ty, topics=topics, amt_c=amt_c,
                 pos=pos, jday=jday, idnat=idnat, idall=idall, off_call=off_call, off_val=off_val, **F)
    pri = dict(pop=pop, ttype=ttype, citypop=citypop, topicpop=topicpop, localepop=localepop, party_p=party_p, c3_p=c3_p)
    lat = {"task_added_latency_ms_mean": float(task_delay.mean()), "task_added_latency_ms_p95": float(np.quantile(task_delay, .95)),
           "call_added_delay_ms_mean": float(delay[pos > 0].mean()) if (pos > 0).any() else 0.0,
           "pay_calls_quoted_fraction": float(has_q.mean()) if npay else 0.0}
    return U, calls, pri, lat

CALL_KEYS = ["user", "task", "day", "t", "tool", "ty", "topics", "amt_c", "pos", "jday", "idnat", "idall",
             "origin", "party", "c1", "c2", "c3", "loc", "amt"]

def restrict(C, mask):
    idx = np.nonzero(mask)[0]
    D = {k: C[k][idx] for k in CALL_KEYS}
    newi = np.full(len(mask), -1); newi[idx] = np.arange(len(idx))
    m = mask[C["off_call"]]
    D["off_call"] = newi[C["off_call"][m]]; D["off_val"] = C["off_val"][m]
    return D


# =============================================================================================== features & profiles
def call_features(C, fields, hour_w):
    n = len(C["t"]); rows, cols, vals = [], [], []
    def add(mask, col, w=1.0):
        idx = np.nonzero(mask)[0]
        rows.append(idx); cols.append(col[idx]); vals.append(np.full(len(idx), float(w)) if np.ndim(w) == 0 else np.asarray(w, float)[idx])
    allm = np.ones(n, bool)
    if "tool" in fields: add(allm, OFF["tool"][0] + C["tool"])
    if "hour" in fields: add(allm, OFF["hour"][0] + (C["t"] % DAY_MS) // HOUR_MS, hour_w)
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
    put("amt", np.diff(ndtr((edges[None, :] - mu) / .6), axis=1))
    return Lt.astype(np.float32)


# =============================================================================================== linkage primitives
def pseudonym(C, fmt, seed):
    u, tl, d = C["user"], C["tool"], C["day"]
    b = base_fmt(fmt)
    if b == "clear": return u.copy()
    if b == "pertool": return u * T_TOOLS + tl
    if b in ("pertool_day", "ptej", "ptejday"): return (u * T_TOOLS + tl) * (DAYS + 2) + d
    if b == "ott":   # one-time token: a fresh 64-bit random serial per call (blind / batch issuance)
        return np.random.default_rng([seed, 99]).integers(0, 2 ** 62, len(u))
    return np.arange(len(u))  # mm: fresh unlinkable token per call

def compact(x):
    return np.unique(x, return_inverse=True)[1].ravel()

def time_segments(t, order, delta):
    ts = t[order]
    seg_sorted = np.r_[0, np.cumsum(np.diff(ts) > delta)]
    seg = np.empty(len(ts), np.int64); seg[order] = seg_sorted
    return seg

def union_labels(n, *label_arrays):
    rows, cols = [], []
    for lab in label_arrays:
        lab = compact(lab)
        first = np.full(lab.max() + 1, -1); idx = np.arange(n)
        o = np.argsort(lab, kind="stable"); ls = lab[o]
        brk = np.r_[0, np.nonzero(np.diff(ls))[0] + 1]
        first[ls[brk]] = o[brk]
        rows.append(idx); cols.append(first[lab])
    g = sp.csr_matrix((np.ones(sum(len(r) for r in rows), np.int8), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    return connected_components(g, directed=False)[1]

def gap_model(C, ctr):
    """population-level timing model of VISIBLE calls given to the attacker (see docstring item 1)"""
    o = np.lexsort((C["t"], C["task"]))
    tk, tt = C["task"][o], C["t"][o]
    same = tk[1:] == tk[:-1]
    g = (tt[1:] - tt[:-1])[same].astype(float)
    lg = np.log(np.maximum(g, 0.5))
    lo = math.log(0.5); hi = float(lg.max()) + 0.25 if len(lg) else 10.0
    nb = 150
    hist, edges = np.histogram(lg, bins=nb, range=(lo, hi))
    k = np.exp(-0.5 * (np.arange(-3, 4) / 1.2) ** 2); k /= k.sum()
    sm = np.convolve(hist.astype(float), k, mode="same") + 0.05
    dens = sm / sm.sum() / np.diff(edges)
    wmax = float(np.quantile(g, .999)) if len(g) else 1e4
    Lv = np.bincount(np.unique(C["task"], return_inverse=True)[1].ravel())
    cnt = np.bincount(np.minimum(Lv, MAX_TASK), minlength=MAX_TASK + 1).astype(float)
    ge = np.cumsum(cnt[::-1])[::-1]
    haz = np.full(MAX_TASK + 1, 1e-9)
    for l in range(1, MAX_TASK):
        haz[l] = max(ge[l + 1] / ge[l], 1e-9) if ge[l] > 0 else 1e-9
    starts = tt[np.r_[True, ~same]]
    hrs = np.bincount((starts % DAY_MS) // HOUR_MS, minlength=24).astype(float) + 1
    span_days = max((C["t"].max() - C["t"].min()) / DAY_MS, 1.0)
    lam = hrs / (span_days * HOUR_MS)
    out = {"lo": lo, "w": (hi - lo) / nb, "nb": nb, "logdens": np.log(dens).tolist(), "wmax": wmax,
           "loghaz": np.log(haz).tolist(), "loglam": np.log(lam).tolist(), "gap_p50_ms": float(np.median(g)) if len(g) else None,
           "gap_p99_ms": float(np.quantile(g, .99)) if len(g) else None}
    if ctr is not None:
        cv = C["pos"] if ctr == "task" else C["jday"]
        dj = (cv[o][1:] - cv[o][:-1])[same]
        pdj = np.bincount(np.clip(dj, 1, 20), minlength=21)[1:].astype(float) + .01
        out["logpdj"] = np.log(pdj / pdj.sum()).tolist()
    return out

def track(C, gm, use_amt, ctr=None, conf_tau=0.9):
    """online greedy multi-session tracker (ms timing, optional counters and exact-amount matches).
    Returns sessions and 'pieces': sessions cut at every link whose posterior among the alternatives (other open
    sessions, new session) is < conf_tau (pieces = confident sub-sessions, used as stage-1 atoms)."""
    n = len(C["t"])
    order = np.argsort(C["t"], kind="stable")
    T = C["t"].tolist(); ispay = (C["ty"] == 1).tolist(); amt = C["amt_c"].tolist()
    cv = None
    if ctr is not None:
        cv = (C["pos"] if ctr == "task" else C["jday"]).tolist()
        lpdj = gm["logpdj"]
    offers = {}
    if use_amt and len(C["off_call"]):
        oc, ov = C["off_call"], C["off_val"]
        brk = np.r_[0, np.nonzero(np.diff(oc))[0] + 1, len(oc)]
        for a, b in zip(brk[:-1], brk[1:]):
            offers[int(oc[a])] = ov[a:b].tolist()
    lo, w, nb = gm["lo"], gm["w"], gm["nb"]; ld = gm["logdens"]; lh = gm["loghaz"]; llam = gm["loglam"]
    wmax = gm["wmax"]; wamt = wmax * MAX_TASK
    log = math.log
    s_last, s_len, s_ctr, s_piece = [], [], [], []
    sess = np.empty(n, np.int64); piece = np.empty(n, np.int64); n_piece = 0; n_unconf = 0
    open_ids = []
    quotes = {}
    n_amt = 0; n_ctr_new = 0
    for step, i in enumerate(order.tolist()):
        ti = T[i]
        open_ids = [s for s in open_ids if ti - s_last[s] <= wmax and s_len[s] < MAX_TASK]
        best = -1
        cj = cv[i] if cv is not None else None
        conf = True
        forced_new = ctr == "task" and cj == 0
        if not forced_new:
            if use_amt and ispay[i]:
                lst = quotes.get(amt[i])
                if lst:
                    for tq, s in reversed(lst):
                        if ti - tq > wamt: break
                        if s_len[s] < MAX_TASK and ti - s_last[s] <= wamt and (cj is None or s_ctr[s] < cj):
                            best = s; n_amt += 1; break
            if best >= 0:
                conf = True
            else:
                bs = -1e300; tot = []
                for s in open_ids:
                    lc = 0.0
                    if cj is not None:
                        d = cj - s_ctr[s]
                        if d <= 0: continue
                        lc = lpdj[min(d, 20) - 1]
                    g = ti - s_last[s]
                    gg = g if g > 0.5 else 0.5
                    k = int((log(gg) - lo) / w)
                    if k >= nb: continue
                    sc = lh[s_len[s]] + ld[k] - log(gg) + lc
                    tot.append(sc)
                    if sc > bs: bs = sc; best = s
                ln = llam[(ti % DAY_MS) // HOUR_MS]
                if best >= 0 and bs < ln:
                    best = -1
                if best >= 0:   # posterior of the chosen link among (open candidates, new session)
                    mx = max(bs, ln)
                    conf = math.exp(bs - mx) / (math.exp(ln - mx) + sum(math.exp(x - mx) for x in tot)) >= conf_tau
        else:
            n_ctr_new += 1
        if best < 0:
            best = len(s_last); s_last.append(ti); s_len.append(1); s_ctr.append(cj if cj is not None else 0)
            open_ids.append(best); s_piece.append(n_piece); n_piece += 1
        else:
            s_last[best] = ti; s_len[best] += 1
            if cj is not None: s_ctr[best] = cj
            if not conf:
                s_piece[best] = n_piece; n_piece += 1; n_unconf += 1
        sess[i] = best; piece[i] = s_piece[best]
        if use_amt and i in offers:
            for v in offers[i]:
                quotes.setdefault(v, []).append((ti, best))
        if step % 200000 == 199999 and use_amt:   # prune old quotes
            quotes = {v: [x for x in l if ti - x[0] <= wamt] for v, l in quotes.items()}
            quotes = {v: l for v, l in quotes.items() if l}
    return sess, piece, {"sessions": len(s_last), "pieces": n_piece, "unconfident_links": n_unconf, "amount_joins": n_amt,
                         "counter_forced_starts": n_ctr_new}

def session_quality(sess, C):
    task = C["task"]
    k1 = np.unique(sess.astype(np.int64) * (task.max() + 1) + task, return_counts=True)[1]
    TP = int(c2(k1).sum()); P = int(c2(np.bincount(sess)).sum()); Tt = int(c2(np.bincount(compact(task))).sum())
    # exact reconstruction: visible calls of the task == one session
    ts = np.unique(np.stack([task, sess], 1), axis=0)
    nt = np.bincount(compact(ts[:, 0])); ns_per_task = nt
    st = np.unique(np.stack([sess, task], 1), axis=0)
    pure_sess = np.bincount(st[:, 0], minlength=sess.max() + 1) == 1
    tk_c = compact(task)
    one_sess = ns_per_task == 1
    # task exact if it maps to one session and that session is pure
    tmap = np.full(tk_c.max() + 1, -1); tmap[tk_c] = sess
    exact = one_sess & pure_sess[tmap]
    return {"pair_precision": TP / P if P else None, "pair_recall": TP / Tt if Tt else None,
            "tasks_exact": float(exact.mean()), "sessions": int(sess.max() + 1), "tasks_visible": int(len(nt))}

def canon(lab):
    """relabel clusters by order of first appearance in time (makes the attacker invariant to token values)"""
    u, first, inv = np.unique(lab, return_index=True, return_inverse=True)
    rank = np.empty(len(u), np.int64); rank[np.argsort(first, kind="stable")] = np.arange(len(u))
    return rank[inv.ravel()]

def day_chain(C, atoms, X, rounds=3):
    """ptejday: chain stage-1 atoms of the same day through the revealed per-(user, day) counter j.
    An atom whose smallest counter is m > 0 must be continued from the atom holding m-1. Candidates must (i) hold
    m-1 but not m, (ii) have a counter set disjoint from the atom's, (iii) give a merged sequence whose times
    increase with the counter. Among feasible pairs of each (day, m) a linear assignment on feature cosine
    similarity picks the links; 3 rounds (merged atoms expose new starts)."""
    n = len(C["t"]); cv = np.minimum(C["jday"], 63); t = C["t"].astype(float); day = C["day"]
    total = 0
    for rd in range(rounds):
        atoms = canon(atoms)
        S = int(atoms.max()) + 1
        Tm = np.full((S, 64), np.nan); Tm[atoms, cv] = t            # counter -> time per atom
        has = ~np.isnan(Tm)
        a_day = np.zeros(S, np.int64); a_day[atoms] = day
        mn = np.where(has.any(1), has.argmax(1), -1)
        A = sp.csr_matrix((np.ones(n, np.float32), (atoms, np.arange(n))), shape=(S, n))
        Zs = (A @ X).tocsr()
        nrm = np.sqrt(np.asarray(Zs.multiply(Zs).sum(1)).ravel()) + 1e-9
        Zs = (sp.diags(1 / nrm) @ Zs).tocsr()
        edges = []
        starts = np.nonzero(mn > 0)[0]
        key_s = a_day[starts] * 64 + mn[starts]
        o = np.argsort(key_s, kind="stable"); starts, key_s = starts[o], key_s[o]
        brk = np.r_[0, np.nonzero(np.diff(key_s))[0] + 1, len(starts)]
        dayidx = {}
        for dd in np.unique(a_day):
            dayidx[dd] = np.nonzero(a_day == dd)[0]
        for x, y in zip(brk[:-1], brk[1:]):
            st = starts[x:y]; m = int(mn[st[0]]); dd = a_day[st[0]]
            cand = dayidx[dd]
            en = cand[has[cand, m - 1] & ~has[cand, m]]
            if len(en) == 0:
                continue
            feas = np.zeros((len(st), len(en)), bool)
            hen, Ten = has[en][None, :, :], Tm[en][None, :, :]
            for q in range(0, len(st), max(1, 2_000_000 // (64 * len(en)))):
                sq = st[q:q + max(1, 2_000_000 // (64 * len(en)))]
                disj = ~(has[sq][:, None, :] & hen).any(2)
                M = np.where(has[sq][:, None, :], Tm[sq][:, None, :], Ten)
                R = np.fmax.accumulate(M, axis=2)
                prev = np.concatenate([np.full(R.shape[:2] + (1,), -np.inf), R[:, :, :-1]], 2)
                with np.errstate(invalid="ignore"):
                    mono = ~(M < prev).any(2)
                feas[q:q + len(sq)] = disj & mono
            if not feas.any():
                continue
            sim = (Zs[st] @ Zs[en].T).toarray()
            cost = np.where(feas, -sim, 1e6)
            r, c = linear_sum_assignment(cost)
            ok = cost[r, c] < 1e5
            edges.append(np.stack([st[r[ok]], en[c[ok]]], 1))
        if not edges:
            break
        e = np.concatenate(edges); total += len(e)
        g = sp.csr_matrix((np.ones(len(e), np.int8), (e[:, 0], e[:, 1])), shape=(S, S))
        atoms = connected_components(g, directed=False)[1][atoms]
    return canon(atoms), total

def stage1_atoms(C, fmt, sess, seed):
    """identifier groups merged through co-occurrence in reconstructed sessions"""
    n = len(C["t"])
    pid = compact(pseudonym(C, fmt, seed))
    if base_fmt(fmt) == "clear":
        return canon(pid), {}
    gsize = np.bincount(pid)
    so = np.lexsort((C["t"], sess))
    segs = sess[so]; ids = pid[so]
    pa, pb, ps = [], [], []
    for k in range(1, MAX_TASK):
        m = segs[k:] == segs[:-k]
        a, b = ids[:-k][m], ids[k:][m]
        keep = a != b
        pa.append(np.minimum(a, b)[keep]); pb.append(np.maximum(a, b)[keep]); ps.append(segs[:-k][m][keep])
    pa, pb, ps = map(np.concatenate, (pa, pb, ps))
    stats = {}
    G = len(gsize)
    if len(pa):
        trip = np.unique(np.stack([ps, pa, pb], 1), axis=0)
        pr, cnt = np.unique(trip[:, 1:], axis=0, return_counts=True)
        need = np.minimum(2, np.minimum(gsize[pr[:, 0]], gsize[pr[:, 1]]))
        if MERGE_RATIO > 0:      # robust to tracker errors: co-occur in a fraction of the smaller group's sessions
            gs = np.unique(np.stack([pid, sess], 1), axis=0)
            nsess = np.bincount(gs[:, 0], minlength=G)
            need = np.maximum(need, np.ceil(MERGE_RATIO * np.minimum(nsess[pr[:, 0]], nsess[pr[:, 1]])))
        e = pr[cnt >= need]
        g = sp.csr_matrix((np.ones(len(e), np.int8), (e[:, 0], e[:, 1])), shape=(G, G))
        comp = connected_components(g, directed=False)[1]
        stats["merge_edges"] = int(len(e))
    else:
        comp = np.arange(G)
    return canon(comp[pid]), stats

def field_slices(fields):
    cols = np.concatenate([np.arange(*OFF[f]) for f in fields])
    fs, o = [], 0
    for f in fields:
        w = OFF[f][1] - OFF[f][0]; fs.append((o, o + w)); o += w
    return cols, fs

def theta(counts, fslices, gnorm, alpha=1.0):
    lt = np.empty_like(counts, dtype=np.float32)
    for a, b in fslices:
        c = counts[:, a:b]
        lt[:, a:b] = np.log((c + alpha * gnorm[a:b]) / (c.sum(1, keepdims=True) + alpha))
    return lt

def hard_em(Z, K, rng, fields, max_iter=10, alpha=1.0, chunk=4096):
    A = Z.shape[0]
    if A <= K:
        return np.arange(A), {"iterations": 0, "note": "atoms <= K, no clustering"}
    cols, fslices = field_slices(fields)
    Zs = Z[:, cols].tocsr().astype(np.float32)
    glob = np.asarray(Zs.sum(0)).ravel() + 1e-3
    gnorm = np.zeros_like(glob)
    for a, b in fslices:
        gnorm[a:b] = glob[a:b] / glob[a:b].sum()
    weight = np.asarray(Zs.sum(1)).ravel()
    p = (weight + 1e-3) / (weight + 1e-3).sum()
    seeds = rng.choice(A, K, replace=False, p=p)
    counts = Zs[seeds].toarray()
    assign = np.full(A, -1); hist = []
    for it in range(max_iter):
        lt = theta(counts, fslices, gnorm, alpha).T.copy()
        new = np.empty(A, np.int64); best = np.empty(A, np.float32)
        for i in range(0, A, chunk):
            S = Zs[i:i + chunk].toarray() @ lt
            j = S.argmax(1); new[i:i + chunk] = j; best[i:i + chunk] = S[np.arange(len(j)), j]
        changed = float((new != assign).mean()); assign = new; hist.append(changed)
        sizes = np.bincount(assign, minlength=K)
        empty = np.nonzero(sizes == 0)[0]
        if len(empty):
            fit = best / np.maximum(weight, 1e-3)
            assign[np.argsort(fit)[:len(empty)]] = empty
        R = sp.csr_matrix((np.ones(A, np.float32), (assign, np.arange(A))), shape=(K, A))
        counts = (R @ Zs).toarray()
        if changed < 0.002:
            break
    return assign, {"iterations": len(hist), "changed_fraction": hist}

def aux_map(Z, Lt, fields, chunk=4096):
    cols = np.concatenate([np.arange(*OFF[f]) for f in fields])
    Zs = Z[:, cols].tocsr(); LtT = np.ascontiguousarray(Lt[:, cols].T)
    out = np.empty(Z.shape[0], np.int64)
    for i in range(0, Z.shape[0], chunk):
        out[i:i + chunk] = (Zs[i:i + chunk].toarray().astype(np.float32) @ LtT).argmax(1)
    return out


# =============================================================================================== metrics
c2 = lambda x: (x.astype(np.int64) * (x.astype(np.int64) - 1)) // 2

def metrics(lab, C):
    user, task = C["user"], C["task"]; n = len(lab)
    lab = compact(lab); NU = int(user.max()) + 1
    key = lab.astype(np.int64) * NU + user
    uk, nij = np.unique(key, return_counts=True)
    ci, uj = uk // NU, uk % NU
    a = np.bincount(lab); b = np.bincount(user, minlength=NU)
    TP = int(c2(nij).sum()); P = int(c2(a).sum()); Tt = int(c2(b).sum()); tot = n * (n - 1) // 2
    prec = TP / P if P else None; rec = TP / Tt if Tt else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0.0
    exp = P * Tt / tot
    ari = (TP - exp) / (0.5 * (P + Tt) - exp) if (0.5 * (P + Tt) - exp) else 1.0
    bp = float((nij.astype(float) ** 2 / a[ci]).sum() / n); br = float((nij.astype(float) ** 2 / b[uj]).sum() / n)
    tk = np.unique(task.astype(np.int64) * (lab.max() + 1) + lab, return_counts=True)[1]
    sess_rec = int(c2(tk).sum()) / max(int(c2(np.bincount(compact(task))).sum()), 1)
    o = np.lexsort((-nij, uj)); first = np.r_[True, np.diff(uj[o]) != 0]
    bi = o[first]
    act = b[uj[bi]] >= MIN_PR_CALLS
    pr = (nij[bi] >= .5 * b[uj[bi]]) & (nij[bi] / a[ci[bi]] >= .8)
    return {"pairs_pred": P, "pairs_true": Tt, "TP": TP, "FP": P - TP, "FN": Tt - TP, "precision": prec, "recall": rec,
            "f1": f1, "session_recall": sess_rec, "ari": ari, "bcubed_precision": bp, "bcubed_recall": br,
            "bcubed_f1": 2 * bp * br / (bp + br), "profile_recovery": float(pr[act].mean()) if act.any() else None,
            "pr_users": int(pr[act].sum()), "pr_denominator_users": int(act.sum()),
            "clusters": int(len(a)), "largest_cluster": int(a.max())}

def posterior(lab, Xvis, Lt, targets, true_user, rng, purity, tool, cap=200, tchunk=40):
    """profile-oracle posterior over users for each target call given its cluster (unchanged from e3v2.py)"""
    N = Lt.shape[0]
    a, b = OFF["tool"]
    ind = (Lt[:, a:b] > np.log(1e-5)).astype(np.float64)
    q = ind.mean(0)
    log_t_target = np.log(ind * (1 - 1e-6) + 1e-6).T
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
        rows_o, owner = [], []
        for i in range(c0, min(c0 + tchunk, len(targets))):
            mem = o[starts[i]:ends[i]]; mem = mem[mem != targets[i]]
            if len(mem) > cap - 1:
                mem = rng.choice(mem, cap - 1, replace=False)
            rows_o.append(mem); owner.append(np.full(len(mem), i - c0))
        tg = targets[c0:c0 + tchunk]
        LL = (Xvis[tg] @ LtT).astype(np.float64)
        mem = np.concatenate(rows_o); own = np.concatenate(owner)
        if has_tool:
            LL += log_t_target[tool[tg]]
            if len(mem):
                Pm = np.zeros((len(tg), b - a)); Pm[own, tool[mem]] = 1.0
                Pm[np.arange(len(tg)), tool[tg]] = 0.0
                LL += Pm @ log_t_member
        if len(mem) and purity > 0:
            Lm = (Xvis[mem] @ LtT).astype(np.float64)
            lq = logsumexp(Lm, axis=1, keepdims=True) - logN
            contrib = np.logaddexp(lpi + Lm, l1pi + lq)
            LL += sp.csr_matrix((np.ones(len(own)), (own, np.arange(len(own)))), shape=(len(tg), len(own))) @ contrib
        lp = LL - logsumexp(LL, axis=1, keepdims=True); p = np.exp(lp)
        Hs.append(-(p * lp).sum(1) / np.log(2))
        srt = -np.sort(-p, 1); set99s.append((np.cumsum(srt, 1) < 0.99).sum(1) + 1)
        tu = true_user[c0:c0 + tchunk]; pt = p[np.arange(len(tg)), tu]
        pts.append(pt); top1s.append(p.argmax(1) == tu); ranks.append((p > pt[:, None]).sum(1) + 1)
    H, set99, pt, top1, rank = map(np.concatenate, (Hs, set99s, pts, top1s, ranks))
    return {"targets": int(len(targets)), "purity_used": float(purity), "entropy_bits_mean": float(H.mean()),
            "eff_anonymity_set_2^H_mean": float((2 ** H).mean()), "degree_of_anonymity": float(H.mean() / np.log2(N)),
            "set99_mean": float(set99.mean()), "p_true_mean": float(pt.mean()), "top1_accuracy": float(top1.mean()),
            "true_rank_median": float(np.median(rank))}

def id_metrics(name, C, idmask):
    user, task = C["user"], C["task"]
    att = name >= 0; cor = name == user
    tc = compact(task)
    nt = np.bincount(tc); ct = np.bincount(tc, weights=cor)
    act_users = np.unique(user)
    named_users = np.unique(user[idmask])
    return {"calls_correct": float(cor.mean()), "attributed": float(att.mean()),
            "precision": float(cor.sum() / att.sum()) if att.any() else None,
            "tasks_correct": float((ct > 0.5 * nt).mean()), "tasks_all_correct": float((ct == nt).mean()),
            "users_named": float(len(named_users) / len(act_users)), "identified_calls": float(idmask.mean())}

def identified_attack(C, atoms, Z, dclu, idmask, fields, rng_seed):
    """name propagation from identifying calls: session/identifier atoms -> d clusters -> supervised profiles"""
    user = C["user"]; NU = int(user.max()) + 1
    A = int(atoms.max()) + 1
    out = {}
    nm = np.nonzero(idmask)[0]
    atom_name = np.full(A, -1, np.int64)
    if len(nm):
        key = atoms[nm].astype(np.int64) * NU + user[nm]
        uk, cnt = np.unique(key, return_counts=True)
        o = np.lexsort((-cnt, uk // NU)); f = np.r_[True, np.diff((uk // NU)[o]) != 0]
        sel = uk[o][f]
        atom_name[sel // NU] = sel % NU
    name_s = atom_name[atoms]
    out["id_sess"] = id_metrics(name_s, C, idmask)
    # d-cluster majority
    if dclu is not None:
        K = int(dclu.max()) + 1
        clu_name = np.full(K, -1, np.int64)
        if len(nm):
            key = dclu[nm].astype(np.int64) * NU + user[nm]
            uk, cnt = np.unique(key, return_counts=True)
            o = np.lexsort((-cnt, uk // NU)); f = np.r_[True, np.diff((uk // NU)[o]) != 0]
            sel = uk[o][f]; clu_name[sel // NU] = sel % NU
        out["id_clu"] = id_metrics(np.where(name_s >= 0, name_s, clu_name[dclu]), C, idmask)
    # supervised profiles
    labeled = atom_name >= 0
    if labeled.sum() == 0:
        z = id_metrics(name_s, C, idmask); out["id_cls"] = z; out["id_cls_conf"] = z
        return out
    cols, fslices = field_slices(fields)
    Zs = Z[:, cols].tocsr().astype(np.float32)
    glob = np.asarray(Zs.sum(0)).ravel() + 1e-3
    gnorm = np.zeros_like(glob)
    for a, b in fslices:
        gnorm[a:b] = glob[a:b] / glob[a:b].sum()
    names, nidx = np.unique(atom_name[labeled], return_inverse=True)
    Kn = len(names)
    lab_atoms = np.nonzero(labeled)[0]; unl = np.nonzero(~labeled)[0]
    cur = np.full(A, -1, np.int64); cur[lab_atoms] = nidx
    margin = np.full(A, np.inf, np.float32)
    for it in range(2):
        m = cur >= 0
        R = sp.csr_matrix((np.ones(int(m.sum()), np.float32), (cur[m], np.nonzero(m)[0])), shape=(Kn, A))
        counts = (R @ Zs).toarray()
        lt = theta(counts, fslices, gnorm).T.copy()
        for i in range(0, len(unl), 4096):
            ch = unl[i:i + 4096]
            S = Zs[ch].toarray() @ lt
            if Kn >= 2:
                top2 = np.argpartition(-S, 1, axis=1)[:, :2]
                v = np.take_along_axis(S, top2, 1)
                bi = np.where(v[:, 0] >= v[:, 1], top2[:, 0], top2[:, 1])
                margin[ch] = np.abs(v[:, 0] - v[:, 1])
            else:
                bi = np.zeros(len(ch), np.int64); margin[ch] = np.inf
            cur[ch] = bi
    name_c = names[cur][atoms]
    out["id_cls"] = id_metrics(name_c, C, idmask)
    conf = margin[atoms] >= np.log(100.0)
    out["id_cls_conf"] = id_metrics(np.where(conf, name_c, -1), C, idmask)
    return out


# =============================================================================================== one cell
def parse_cell(cid):
    g, setting, N, r, fmt, k = cid.split("|")
    return g, setting, int(N), int(r), fmt, int(k)

def setting_params(setting):
    P = dict(BASE)
    if setting == "base":
        return P
    name, val = setting.split("=", 1)
    for fac, key, vals in SENS:
        if fac == name:
            for v in vals:
                if str(v).replace(" ", "") == val:
                    P[key] = v; return P
    raise ValueError(setting)

def run_cell(cid, cal, log=print):
    group, setting, N, r, fmt, k = parse_cell(cid)
    P = setting_params(setting); P["k"] = k
    seed = SEEDS[r]
    t0 = time.time()
    U, Cfull, pri, lat = make_world(N, P, seed, cal)
    vis = Cfull["tool"] < k
    C = restrict(Cfull, vis) if k < T_TOOLS else Cfull
    n = len(C["t"])
    ck = ctr_kind(fmt)
    world = {"users": N, "calls_total": int(len(Cfull["t"])), "calls_visible": n, "tasks_visible": int(len(np.unique(C["task"]))),
             "same_user_pairs": int(c2(np.bincount(C["user"])).sum()), "same_task_pairs": int(c2(np.bincount(compact(C["task"]))).sum()),
             "tool_types_in_coalition": {kk: int((pri["ttype"][:k] == i).sum()) for i, kk in enumerate(["booking", "payment", "search", "utility"])},
             "identified_calls_natural": int(C["idnat"].sum()), "identified_calls_every": int(C["idall"].sum()), **lat}
    heavy = N >= 10000
    gm = gap_model(C, ck)
    world["gap_p50_ms"] = gm["gap_p50_ms"]; world["gap_p99_ms"] = gm["gap_p99_ms"]; world["tracker_window_ms"] = gm["wmax"]
    res = {"cell": cid, "group": group, "setting": setting, "N": N, "seed": seed, "seed_index": r, "format": fmt, "k": k,
           "params": {kk: (list(x) if isinstance(x, tuple) else x) for kk, x in P.items()}, "world": world, "attackers": {}, "posterior": {}, "timing": {}}
    ts = time.time()
    sessA, pieceA, stA = track(C, gm, True, ck)
    res["timing"]["track_s"] = round(time.time() - ts, 1)
    res["tracker"] = {"A": {**stA, **session_quality(sessA, C)}, "A_pieces": session_quality(pieceA, C)}
    pid = pseudonym(C, fmt, seed)
    labs = {}
    full_grp = group == "main"
    if base_fmt(fmt) == "clear":
        sessT = sessA
    else:
        sessT, _, stT = track(C, gm, False, ck)
        res["tracker"]["T"] = {**stT, **session_quality(sessT, C)}
    labs["a_id"] = pid
    deltas = DELTAS_MS if full_grp else [2000, 10000]
    order = np.argsort(C["t"], kind="stable")
    for d in deltas:
        labs[f"b_time{d}"] = pid if base_fmt(fmt) == "clear" else union_labels(n, pid, time_segments(C["t"], order, d))
    labs["b_trackT"] = pid if base_fmt(fmt) == "clear" else union_labels(n, pid, sessT)
    labs["b_trackA"] = pid if base_fmt(fmt) == "clear" else union_labels(n, pid, sessA)
    hour_w = 1.0 / np.bincount(sessA)[sessA]
    visf = visible_fields(fmt)
    Xall = call_features(C, visf, hour_w)
    atoms, st = stage1_atoms(C, fmt, sessA, seed)
    if ck == "day" and k == T_TOOLS:
        ts = time.time()
        atoms, ne = day_chain(C, atoms, Xall)
        st["day_chain_edges"] = ne; res["timing"]["chain_s"] = round(time.time() - ts, 1)
    A = sp.csr_matrix((np.ones(n, np.float32), (atoms, np.arange(n))), shape=(atoms.max() + 1, n))
    Z = (A @ Xall).tocsr()
    res["stage1"] = {**st, "atoms": int(Z.shape[0])}
    labs["s_atoms"] = atoms
    dclu = None
    for s, flds in [("c", ["hour"] + [f for f in visf if f in QI_FULL]), ("d", visf)]:
        if s == "c" and not full_grp:
            continue
        if base_fmt(fmt) == "clear":
            labs[f"{s}_{'sessQI' if s == 'c' else 'full'}"] = pid; continue
        ts = time.time()
        asg, info = hard_em(Z, N, np.random.default_rng([seed, 11]), flds)
        labs[f"{s}_{'sessQI' if s == 'c' else 'full'}"] = asg[atoms]
        res["timing"][f"{s}_em_s"] = round(time.time() - ts, 1); res[f"{s}_em"] = info
        if s == "d": dclu = asg[atoms]
    if dclu is None: dclu = atoms
    Lt = user_loglik_table(U, pri)
    if base_fmt(fmt) != "clear":
        labs["e_oracle"] = aux_map(Z, Lt, visf)[atoms]
    else:
        labs["e_oracle"] = pid
    for name, lab in labs.items():
        res["attackers"][name] = metrics(lab, C)
    # identified-tool attacker
    ts = time.time()
    for mode, key in [("natural", "idnat"), ("every", "idall")]:
        r_ = identified_attack(C, atoms, Z, dclu, C[key], visf, seed)
        for kk, v in r_.items():
            res["attackers"][f"{kk}@{mode}"] = v
    res["timing"]["identified_s"] = round(time.time() - ts, 1)
    # posterior (profile-oracle) top-1
    ts = time.time()
    trng = np.random.default_rng([seed, 7])
    targets = trng.choice(n, min(400, n), replace=False)
    Xvis = call_features(C, visf, hour_w)
    plist = {"call_only": (np.arange(n), 1.0), "session": (compact(sessA), None), "atom": (atoms, None), "a_id": (compact(pid), None),
             "d_full": (compact(labs["d_full"]), None)}
    if not full_grp or heavy:
        plist.pop("atom"); plist.pop("a_id")
    for pn, (lab, pur) in plist.items():
        if base_fmt(fmt) == "clear" and pn != "call_only":
            res["posterior"][pn] = {"top1_accuracy": 1.0, "entropy_bits_mean": 0.0, "note": "principal id visible"}; continue
        if pur is None:
            pur = metrics(lab, C)["bcubed_precision"]
        res["posterior"][pn] = posterior(lab, Xvis, Lt, targets, C["user"][targets], np.random.default_rng([seed, 13]), pur, C["tool"])
    res["timing"]["posterior_s"] = round(time.time() - ts, 1)
    res["timing"]["total_s"] = round(time.time() - t0, 1)
    log(f"{cid}: {res['timing']['total_s']}s  d PR={res['attackers']['d_full']['profile_recovery']}  "
        f"id_cls@nat={res['attackers']['id_cls@natural']['calls_correct']:.3f}  trackA exact={res['tracker']['A']['tasks_exact']:.3f}")
    return res


def all_cells():
    cells = []
    for N in (10000, 1000):
        for r in range(5):
            for f in FORMATS:
                cells.append(f"main|base|{N}|{r}|{f}|50")
    for fac, key, vals in SENS:
        for v in vals:
            for r in range(5):
                for f in SENS_FORMATS:
                    cells.append(f"sens|{fac}={str(v).replace(' ', '')}|1000|{r}|{f}|50")
    for kk in COAL_K:
        for r in range(5):
            for f in COAL_FORMATS:
                cells.append(f"coal|base|1000|{r}|{f}|{kk}")
    return cells

def cell_cost(cid):
    g, s, N, r, f, k = parse_cell(cid)
    c = 30.0 if N >= 10000 else 1.0
    if "jitter_ms=600000" in s or "tasks_per_day=(2,6)" in s: c *= 3
    if "ptejday" in f: c *= 1.5
    return c


# =============================================================================================== aggregation & report
def boot_ci(v, B=10000, seed=0):
    v = np.asarray([x for x in v if x is not None], float)
    if len(v) == 0: return None
    rng = np.random.default_rng(seed)
    m = v[rng.integers(0, len(v), (B, len(v)))].mean(1)
    return [float(np.quantile(m, .025)), float(np.quantile(m, .975))]

def stat(v):
    v = [x for x in v if x is not None]
    if not v: return None
    return {"mean": float(np.mean(v)), "min": float(np.min(v)), "max": float(np.max(v)), "ci95": boot_ci(v), "n": len(v), "draws": [float(x) for x in v]}

def get_metric(cell, att, met):
    if att.startswith("post:"):
        return cell["posterior"].get(att[5:], {}).get(met)
    if att.startswith("track:"):
        return cell["tracker"].get(att[6:], {}).get(met)
    return cell["attackers"].get(att, {}).get(met)

def aggregate(cells):
    """group cells by (group, setting, N, format, k) -> statistics over seeds of every metric"""
    groups = {}
    for c in cells:
        groups.setdefault((c["group"], c["setting"], c["N"], c["format"], c["k"]), []).append(c)
    agg = {}
    for key, cs in groups.items():
        cs = sorted(cs, key=lambda c: c["seed_index"])
        d = {"seeds": [c["seed"] for c in cs], "attackers": {}, "posterior": {}, "tracker": {}, "world": {}}
        for att in cs[0]["attackers"]:
            d["attackers"][att] = {m: stat([c["attackers"][att].get(m) for c in cs]) for m, v in cs[0]["attackers"][att].items() if isinstance(v, (int, float)) or v is None}
        for pn in cs[0]["posterior"]:
            d["posterior"][pn] = {m: stat([c["posterior"][pn].get(m) for c in cs]) for m, v in cs[0]["posterior"][pn].items() if isinstance(v, (int, float))}
        for tn in cs[0]["tracker"]:
            if isinstance(cs[0]["tracker"][tn], dict):
                d["tracker"][tn] = {m: stat([c["tracker"][tn].get(m) for c in cs]) for m, v in cs[0]["tracker"][tn].items() if isinstance(v, (int, float))}
        for m, v in cs[0]["world"].items():
            if isinstance(v, (int, float)): d["world"][m] = stat([c["world"].get(m) for c in cs])
        agg["|".join(map(str, key))] = d
    return agg

def F(s, d=3, ci=True):
    if s is None: return "n/a"
    if ci and s.get("ci95"):
        return f"{s['mean']:.{d}f} [{s['min']:.{d}f}-{s['max']:.{d}f}]"
    return f"{s['mean']:.{d}f}"

def A(agg, key, att, met):
    return agg.get(key, {}).get("attackers", {}).get(att, {}).get(met)

def summary_md(R):
    agg = R["aggregate"]; cal = R["calibration"]
    L = ["# E3 v2.1 -- collusion / linkage study (summary)", "",
         f"Generated by `sim/e3v21.py aggregate` from {R['n_cells']} cells (5 world seeds {SEEDS}, identical in every setting). "
         "Full data incl. every per-seed cell: `results/e3v21.json`. Figures: `results/e3v21_main.png`, `results/e3v21_coalition.png`, "
         "`results/e3v21_sensitivity.png`.", "",
         "Cells are reported as **mean [min-max over the 5 seeds]**; the bootstrap 95 % CI of the mean over seeds is in the JSON "
         "and in the sensitivity table (with 5 draws it is descriptive, not a guarantee).", "",
         "## Definitions", "",
         "* **Profile recovery** (was \"re-identification\" in v2): for a user with >= 10 calls visible to the coalition, take the "
         "attacker cluster that holds the largest number of the user's calls; the profile is recovered if that cluster holds >= 50 % "
         "of the user's visible calls AND >= 80 % of the cluster's calls belong to the user. Rate = recovered users / users with >= 10 "
         "visible calls. It measures linkage of a user's activity into one pure profile, not naming (naming = identified-tool attacker).",
         "* **Attackers** (all tools of the coalition pool their logs): a_id identifier equality; b_timeD naive single-linkage of calls <= D ms "
         "apart unioned with identifiers; b_trackT / b_trackA ms multi-session tracker (timing [+ counter j], / + exact-amount matches) "
         "unioned with identifiers; s_atoms = stage-1 atoms (tracker-A sessions + identifier groups merged by co-occurrence); "
         "c_sessQI / d_full = 30-day hard-EM clustering of the atoms on quasi-identifiers + hour (c) and + tool set (d, combined attacker); "
         "e_oracle = **profile-oracle attacker** (atoms assigned to the max-likelihood user under the TRUE profiles; not an upper bound); "
         "id_* = identified-tool attacker (names from identifying calls; sess / clu / cls stages, see docstring).",
         "* **Per-call top-1**: profile-oracle posterior (v2 code) puts the highest mass on the true user, from the call alone, from its "
         "reconstructed session (tracker A), from its stage-1 atom, from its a_id group and from its d_full cluster.", "",
         "## Gap calibration (E4 v2 traces)", ""]
    for mode in ("mm", "none", "jwt"):
        c = cal[mode]
        L.append(f"* modes {'+'.join(c['modes'])}: {c['n_gaps']:,} within-task gaps; quantiles (ms) " +
                 ", ".join(f"{k} {v:,.0f}" for k, v in c["quantiles_ms"].items()) + f"; mean {c['mean_ms']:,.0f} ms.")
    L.append("")
    L.append("| model (mm+mm_esc) | rows used | rows skipped | gaps | median ms | p90 ms | p99 ms | max ms | |replay - wall| median ms |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for m, v in cal["mm"]["per_model"].items():
        L.append(f"| {m} | {v['rows_used']} | {v['rows_skipped']} | {v['gaps']} | {v['median_ms']:,.0f} | {v['p90_ms']:,.0f} | {v['p99_ms']:,.0f} | {v['max_ms']:,.0f} | {v['replay_minus_wall_ms_median']:.1f} |")
    L += ["", "Method: each row (cfg with injected latency, no harness error) is replayed as a sequential timeline: LLM turns in recorded "
          "order; each tool_calls turn is followed by its MCP calls (prep_ms then rtt_ms); a main turn directly followed by sub-agent "
          "turns is the delegation turn (+ deleg_ms). Calls are assigned to turns per role, one per turn, extra calls packed into the "
          "previous turn (identical consecutive calls first); rows with fewer recorded calls than tool turns are skipped. Tool timestamp "
          "= send time (after prep); gaps = consecutive differences within the task. Default world uses the mm+mm_esc kernel "
          "(log-space Gaussian KDE, Silverman bandwidth); 'none' (no proof generation) is a sensitivity setting.", ""]
    # main tables
    atts = [("a_id", "a"), ("b_time2000", "b 2 s"), ("b_trackA", "b track"), ("c_sessQI", "c"), ("d_full", "d"), ("e_oracle", "oracle")]
    for N in (1000, 10000):
        L += [f"## Main table, N = {N:,} users (all 50 tools collude)", "",
              "Profile recovery by attacker; identified-tool attacker = fraction of visible calls attributed to the right named identity "
              "(natural identification: first payment/booking call of a task; every: one call of every task); tracker = fraction of "
              "tasks whose visible calls are reconstructed exactly as one session (tracker A).", "",
              "| format | " + " | ".join(a[1] for a in atts) + " | id_sess nat | id_cls nat | id_cls every | id tasks nat | tracker exact |",
              "|---|" + "---|" * (len(atts) + 5)]
        for f in FORMATS:
            key = f"main|base|{N}|{f}|50"
            if key not in agg: continue
            row = [F(A(agg, key, a, "profile_recovery"))for a, _ in atts]
            row += [F(A(agg, key, "id_sess@natural", "calls_correct")), F(A(agg, key, "id_cls@natural", "calls_correct")),
                    F(A(agg, key, "id_cls@every", "calls_correct")), F(A(agg, key, "id_cls@natural", "tasks_correct")),
                    F(agg[key]["tracker"].get("A", {}).get("tasks_exact"))]
            L.append(f"| {f} | " + " | ".join(row) + " |")
        L.append("")
        L += [f"### N = {N:,}: pairwise F1, false-positive pairs and per-call top-1 identification", "",
              "| format | b track F1 | d F1 | d FP pairs | oracle F1 | top-1 call alone | top-1 session | top-1 atom | top-1 d cluster | oracle < d (PR)? |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for f in FORMATS:
            key = f"main|base|{N}|{f}|50"
            if key not in agg: continue
            po = agg[key]["posterior"]
            g = lambda pn: F(po.get(pn, {}).get("top1_accuracy"), 2, False) if po.get(pn) else "-"
            e = A(agg, key, "e_oracle", "profile_recovery"); d = A(agg, key, "d_full", "profile_recovery")
            flag = "yes" if (e and d and e["mean"] < d["mean"]) else "no"
            fp = A(agg, key, "d_full", "FP")
            L.append(f"| {f} | {F(A(agg, key, 'b_trackA', 'f1'), 3, False)} | {F(A(agg, key, 'd_full', 'f1'), 3, False)} | "
                     f"{fp['mean']:,.0f} | {F(A(agg, key, 'e_oracle', 'f1'), 3, False)} | {g('call_only')} | {g('session')} | {g('atom')} | {g('d_full')} | {flag} |")
        L.append("")
    # identified-tool detail
    L += ["## Identified-tool attacker (detail, N = 1,000 and 10,000)", "",
          "calls = fraction of visible calls attributed to the right name; attributed / precision = coverage and precision of the "
          "attribution; tasks = fraction of tasks whose visible calls are in majority attributed to the right name; users named = "
          "users with >= 1 identifying call.", "",
          "| N | format | mode | stage | calls | attributed | precision | tasks | users named |", "|---|---|---|---|---|---|---|---|---|"]
    for N in (1000, 10000):
        for f in ["clear", "pertool", "pertool_day", "pertool_day_min", "mm", "mm_min", "ott", "ptej", "ptej_min", "ptejday"]:
            key = f"main|base|{N}|{f}|50"
            if key not in agg: continue
            for mode in ("natural", "every"):
                for stg in ("id_sess", "id_clu", "id_cls", "id_cls_conf"):
                    a = f"{stg}@{mode}"
                    L.append(f"| {N:,} | {f} | {mode} | {stg} | {F(A(agg, key, a, 'calls_correct'), 3, False)} | {F(A(agg, key, a, 'attributed'), 3, False)} | "
                             f"{F(A(agg, key, a, 'precision'), 3, False)} | {F(A(agg, key, a, 'tasks_correct'), 3, False)} | {F(A(agg, key, a, 'users_named'), 3, False)} |")
    L.append("")
    # tracker quality
    L += ["## Session reconstruction (tracker) quality", "",
          "| N | format | tracker | pair precision (same task) | pair recall | tasks exact | amount joins |", "|---|---|---|---|---|---|---|"]
    for N in (1000, 10000):
        for f in ["mm", "pertool_day", "ptej", "ptejday"]:
            key = f"main|base|{N}|{f}|50"
            if key not in agg: continue
            for tn in ("T", "A"):
                tq = agg[key]["tracker"].get(tn)
                if not tq: continue
                L.append(f"| {N:,} | {f} | {tn} | {F(tq.get('pair_precision'))} | {F(tq.get('pair_recall'))} | {F(tq.get('tasks_exact'))} | {F(tq.get('amount_joins'), 0, False)} |")
    L.append("")
    # draws at default
    L += ["## All draws at default settings (profile recovery of d_full / id_cls@natural calls correct / top-1 from session)", "",
          "| N | format | d PR draws | id_cls nat draws | top-1 session draws |", "|---|---|---|---|---|"]
    for N in (1000, 10000):
        for f in FORMATS:
            key = f"main|base|{N}|{f}|50"
            if key not in agg: continue
            dd = A(agg, key, "d_full", "profile_recovery"); ii = A(agg, key, "id_cls@natural", "calls_correct")
            ps = agg[key]["posterior"].get("session", {}).get("top1_accuracy")
            fmtd = lambda s: ", ".join(f"{x:.3f}" for x in s["draws"]) if s else "-"
            L.append(f"| {N:,} | {f} | {fmtd(dd)} | {fmtd(ii)} | {fmtd(ps)} |")
    L.append("")
    # coalition
    L += ["## Partial coalitions (N = 1,000; top-k tools by popularity)", "",
          "| k | format | visible calls | d PR | oracle PR | b track F1 | id_cls nat calls | id_cls every calls | top-1 session |", "|---|---|---|---|---|---|---|---|---|"]
    for f in COAL_FORMATS:
        for kk in COAL_K + [50]:
            key = f"coal|base|1000|{f}|{kk}" if kk < 50 else f"main|base|1000|{f}|50"
            if key not in agg: continue
            w = agg[key]["world"]
            L.append(f"| {kk} | {f} | {w['calls_visible']['mean'] / w['calls_total']['mean']:.2f} | {F(A(agg, key, 'd_full', 'profile_recovery'))} | "
                     f"{F(A(agg, key, 'e_oracle', 'profile_recovery'))} | {F(A(agg, key, 'b_trackA', 'f1'), 3, False)} | "
                     f"{F(A(agg, key, 'id_cls@natural', 'calls_correct'))} | {F(A(agg, key, 'id_cls@every', 'calls_correct'))} | "
                     f"{F(agg[key]['posterior'].get('session', {}).get('top1_accuracy'), 2, False)} |")
    L.append("")
    # sensitivity
    L += ["## Sensitivity (N = 1,000, one factor at a time, same 5 seeds)", "",
          "mean [bootstrap 95 % CI over seeds]; added latency = mean added task latency from the random delays.", "",
          "| factor | value | format | tracker exact | b track F1 | d PR | oracle PR | id_cls nat calls | id_cls every calls | top-1 session | added latency (s/task) |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    def Fci(s, d=3):
        if s is None: return "n/a"
        return f"{s['mean']:.{d}f} [{s['ci95'][0]:.{d}f}, {s['ci95'][1]:.{d}f}]"
    sens_rows = [("baseline", "-", "main|base|1000|{f}|50")]
    for fac, key_, vals in SENS:
        for v in vals:
            sens_rows.append((fac, str(v).replace(" ", ""), f"sens|{fac}={str(v).replace(' ', '')}|1000|{{f}}|50"))
    for fac, v, tmpl in sens_rows:
        for f in SENS_FORMATS:
            key = tmpl.format(f=f)
            if key not in agg: continue
            w = agg[key]["world"]
            L.append(f"| {fac} | {v} | {f} | {Fci(agg[key]['tracker'].get('A', {}).get('tasks_exact'))} | {Fci(A(agg, key, 'b_trackA', 'f1'))} | "
                     f"{Fci(A(agg, key, 'd_full', 'profile_recovery'))} | {Fci(A(agg, key, 'e_oracle', 'profile_recovery'))} | "
                     f"{Fci(A(agg, key, 'id_cls@natural', 'calls_correct'))} | {Fci(A(agg, key, 'id_cls@every', 'calls_correct'))} | "
                     f"{Fci(agg[key]['posterior'].get('session', {}).get('top1_accuracy'), 2)} | {w['task_added_latency_ms_mean']['mean'] / 1000:.1f} |")
    L.append("")
    # mm vs ott identity check
    L += ["## mm vs one-time tokens (ott): identity check", ""]
    diffs = []
    for N in (1000, 10000):
        for suf in ("", "_min"):
            a, b = f"main|base|{N}|mm{suf}|50", f"main|base|{N}|ott{suf}|50"
            if a in agg and b in agg:
                for att, ms in agg[a]["attackers"].items():
                    for m, s in ms.items():
                        s2 = agg[b]["attackers"].get(att, {}).get(m)
                        if s and s2:
                            diffs.append(max(abs(x - y) for x, y in zip(s["draws"], s2["draws"])))
                for pn, ms in agg[a]["posterior"].items():
                    for m, s in ms.items():
                        s2 = agg[b]["posterior"].get(pn, {}).get(m)
                        if s and s2:
                            diffs.append(max(abs(x - y) for x, y in zip(s["draws"], s2["draws"])))
    L.append(f"Max absolute difference between mm and ott over every attacker, metric, posterior, seed and N: {max(diffs) if diffs else 'n/a'} "
             "(0 = identical, as expected: both give the tools one unlinkable value per call and the same visible fields).")
    L.append("")
    return "\n".join(L)

def figures(R, outdir):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    agg = R["aggregate"]
    cols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#008300"]
    # main
    atts = [("a_id", "a id"), ("b_trackA", "b track"), ("d_full", "d combined"), ("e_oracle", "profile oracle"),
            ("id_cls@natural", "identified tool (nat.)"), ("id_cls@every", "identified tool (every)")]
    fig, axes = plt.subplots(1, 2, figsize=(15, 4.6), sharey=True)
    for ax, N in zip(axes, (1000, 10000)):
        fm = [f for f in FORMATS if f"main|base|{N}|{f}|50" in agg]
        w = 0.8 / len(atts)
        for i, (a, lab) in enumerate(atts):
            met = "calls_correct" if a.startswith("id_") else "profile_recovery"
            s = [A(agg, f"main|base|{N}|{f}|50", a, met) for f in fm]
            m = np.array([x["mean"] if x else np.nan for x in s]); lo = np.array([x["min"] if x else np.nan for x in s]); hi = np.array([x["max"] if x else np.nan for x in s])
            xs = np.arange(len(fm)) + (i - len(atts) / 2 + .5) * w
            ax.bar(xs, m, w * .9, color=cols[i], label=lab)
            ax.errorbar(xs, m, yerr=[m - lo, hi - m], fmt="none", ecolor="#333", lw=.6, capsize=1.2)
        ax.set_xticks(np.arange(len(fm))); ax.set_xticklabels(fm, rotation=35, ha="right", fontsize=8)
        ax.set_ylim(0, 1.02); ax.set_title(f"N = {N:,} (bars: mean of 5 seeds, whiskers: min-max)", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#ddd", lw=.5)
    axes[0].set_ylabel("profile recovery  /  calls attributed to right name")
    axes[0].legend(fontsize=7, ncol=3, frameon=False, loc="upper right")
    fig.tight_layout(); fig.savefig(outdir / "e3v21_main.png", dpi=160); plt.close(fig)
    # coalition
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    for i, f in enumerate(COAL_FORMATS):
        for ax, (a, met, lab) in zip(axes, [("d_full", "profile_recovery", "profile recovery (d)"), ("id_cls@natural", "calls_correct", "calls named right (id, natural)"),
                                            ("id_cls@every", "calls_correct", "calls named right (id, every task)")]):
            ks, m, lo, hi = [], [], [], []
            for kk in COAL_K + [50]:
                key = f"coal|base|1000|{f}|{kk}" if kk < 50 else f"main|base|1000|{f}|50"
                s = A(agg, key, a, met)
                if s: ks.append(kk); m.append(s["mean"]); lo.append(s["min"]); hi.append(s["max"])
            ax.plot(ks, m, "-o", color=cols[i], label=f, lw=2, ms=4)
            ax.fill_between(ks, lo, hi, color=cols[i], alpha=.15, lw=0)
            ax.set_title(lab, fontsize=9); ax.set_xlabel("coalition = top-k tools by popularity"); ax.set_xticks(COAL_K + [50])
            ax.set_ylim(0, 1.02); ax.spines[["top", "right"]].set_visible(False); ax.grid(color="#eee", lw=.5)
    axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout(); fig.savefig(outdir / "e3v21_coalition.png", dpi=160); plt.close(fig)
    # sensitivity
    facs = [s[0] for s in SENS]
    fig, axes = plt.subplots(2, len(facs), figsize=(2.3 * len(facs), 5.6), sharey="row")
    for j, (fac, key_, vals) in enumerate(SENS):
        labels = ["base"] + [str(v).replace(" ", "") for v in vals]
        for i, f in enumerate(SENS_FORMATS):
            for row, (a, met) in enumerate([("d_full", "profile_recovery"), ("id_cls@natural", "calls_correct")]):
                m, lo, hi = [], [], []
                for lab in labels:
                    key = f"main|base|1000|{f}|50" if lab == "base" else f"sens|{fac}={lab}|1000|{f}|50"
                    s = A(agg, key, a, met)
                    m.append(s["mean"] if s else np.nan); lo.append(s["ci95"][0] if s else np.nan); hi.append(s["ci95"][1] if s else np.nan)
                ax = axes[row, j]
                ax.errorbar(range(len(labels)), m, yerr=[np.array(m) - np.array(lo), np.array(hi) - np.array(m)], fmt="-o", color=cols[i], ms=3, lw=1.5, capsize=2, label=f)
                ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, fontsize=6, rotation=30)
                ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#eee", lw=.5)
                if row == 0: ax.set_title(fac, fontsize=8)
    axes[0, 0].set_ylabel("profile recovery (d)"); axes[1, 0].set_ylabel("calls named right (id, nat.)")
    axes[0, 0].legend(fontsize=6, frameon=False)
    fig.tight_layout(); fig.savefig(outdir / "e3v21_sensitivity.png", dpi=160); plt.close(fig)


# =============================================================================================== main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd"); ap.add_argument("cell", nargs="?")
    ap.add_argument("--cal", default="e3v21_cal.json"); ap.add_argument("--cells", default="cells")
    ap.add_argument("--shard", type=int, default=0); ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()
    log = lambda *a: print(*a, file=sys.stderr, flush=True)
    if args.cmd == "calib":
        cal = calibrate()
        json.dump(cal, open(args.cal, "w"))
        log(json.dumps({m: {k: cal[m][k] for k in ("n_gaps", "quantiles_ms")} for m in ("mm", "none", "jwt")}, indent=1))
        return
    if args.cmd == "tasks":
        cells = sorted(all_cells(), key=lambda c: -cell_cost(c))
        done = set(p.stem for p in Path(args.cells).glob("*.json")) if Path(args.cells).exists() else set()
        for i, c in enumerate(cells):
            if i % args.nshards == args.shard and fname(c) not in done:
                print(c)
        return
    cal = json.load(open(args.cal))
    if args.cmd == "cell":
        out = Path(args.cells); out.mkdir(parents=True, exist_ok=True)
        p = out / (fname(args.cell) + ".json")
        if p.exists():
            return
        res = run_cell(args.cell, cal, log)
        tmp = p.with_suffix(".tmp"); json.dump(res, open(tmp, "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o)); tmp.rename(p)
        return
    if args.cmd == "quick":
        for f in ["mm", "ott", "ptej", "ptejday", "pertool_day", "clear"]:
            res = run_cell(f"main|base|300|0|{f}|50", cal, log)
        res = run_cell("coal|base|300|0|mm|10", cal, log)
        res = run_cell("sens|jitter_ms=60000|300|0|mm|50", cal, log)
        print(json.dumps(res["attackers"]["id_cls@natural"]), json.dumps(res["world"]))
        return
    if args.cmd == "aggregate":
        cells = [json.load(open(p)) for p in sorted(Path(args.cells).glob("*.json"))]
        calsum = {k: ({kk: vv for kk, vv in v.items() if kk != "log_gaps_ms"} if isinstance(v, dict) else v) for k, v in cal.items()}
        R = {"seed": SEED, "seeds": SEEDS, "description": __doc__, "n_cells": len(cells),
             "params": {**{k: (list(v) if isinstance(v, tuple) else v) for k, v in BASE.items()}, "tools": T_TOOLS, "days": DAYS,
                        "cities": N_CITIES, "topics": N_TOPICS, "max_task_len_known_to_attacker": MAX_TASK, "deltas_ms": DELTAS_MS,
                        "formats": FORMATS, "coalition_k": COAL_K + [50], "coalition_formats": COAL_FORMATS, "sens_formats": SENS_FORMATS,
                        "sensitivity": [[a, b, [list(x) if isinstance(x, tuple) else x for x in c]] for a, b, c in SENS],
                        "posterior_targets": 400, "posterior_cap_calls": 200, "profile_recovery_min_calls": MIN_PR_CALLS},
             "calibration": calsum, "aggregate": aggregate(cells), "cells": cells}
        out = Path(args.out)
        json.dump(R, open(out / "e3v21.json", "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
        (out / "e3v21_summary.md").write_text(summary_md(R))
        figures(R, out)
        log(f"aggregated {len(cells)} cells")
        return
    raise SystemExit("unknown command")

def fname(cid):
    return cid.replace("|", "__").replace("=", "-").replace("(", "").replace(")", "").replace(",", "_")

if __name__ == "__main__":
    main()
