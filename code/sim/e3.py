"""E3 / E3b — collusion of 50 tools (identifiers, then timing). Exact pair counts.
Model (as stated in the manuscript): U users, 50 tools, 30 days; each user has 3-8 favourite tools and
0-2 sessions a day; a session = 4 calls within 10 minutes, each to one of the user's favourite tools.
Session start times: uniform over 08:00-22:00 (stated in the results file).
Output: results/e3.json
"""
import json, sys
import numpy as np

SEED = 20261109
TOOLS, DAYS = 50, 30

def simulate(U, rng):
    fav = [rng.choice(TOOLS, size=rng.integers(3, 9), replace=False) for _ in range(U)]
    user, tool, day, t, sess = [], [], [], [], []
    sid = 0
    for u in range(U):
        for d in range(DAYS):
            for _ in range(rng.integers(0, 3)):
                start = d * 86400 + rng.uniform(8 * 3600, 22 * 3600 - 600)
                offs = np.sort(rng.uniform(0, 600, size=4))
                for o in offs:
                    user.append(u); tool.append(rng.choice(fav[u])); day.append(d); t.append(start + o); sess.append(sid)
                sid += 1
    return {k: np.array(v) for k, v in dict(user=user, tool=tool, day=day, t=t, sess=sess).items()}

def pairs_same(keys):
    """number of unordered pairs of records sharing all key columns"""
    _, c = np.unique(np.stack(keys, axis=1), axis=0, return_counts=True)
    return int((c * (c - 1) // 2).sum())

def identifier_linkage(R):
    total = pairs_same([R["user"]])
    total_sess = pairs_same([R["sess"]])
    res = {}
    # clear token: carries the principal -> links every same-principal pair
    res["clear"] = (total, total_sess)
    # stable per-tool pseudonym -> links pairs of the same user at the same tool
    res["pertool"] = (pairs_same([R["user"], R["tool"]]), pairs_same([R["sess"], R["tool"]]))
    # per-tool, per-day pseudonym
    res["epoch"] = (pairs_same([R["user"], R["tool"], R["day"]]), pairs_same([R["sess"], R["tool"]]))
    # Masked Mandates: one pseudonym per call -> no identifier links
    res["mm"] = (0, 0)
    return {k: {"linked": a, "linked_sess": b, "recall": a / total, "session_recall": b / total_sess} for k, (a, b) in res.items()}, total, total_sess

def timing(R, delta):
    """link every pair of calls (any tools) closer than delta seconds. Returns (session_recall, precision)."""
    order = np.argsort(R["t"]); t = R["t"][order]; u = R["user"][order]; s = R["sess"][order]
    n = len(t); linked = 0; tp_user = 0; tp_sess = 0
    hi = np.searchsorted(t, t + delta, side="left")  # pairs (i, j) with i<j<hi[i]
    # vectorised over offsets: max window size is small
    w = int((hi - np.arange(n)).max())
    for k in range(1, w):
        idx = np.arange(n - k)
        ok = (idx + k) < hi[: n - k]
        linked += int(ok.sum())
        tp_user += int((ok & (u[idx] == u[idx + k])).sum())
        tp_sess += int((ok & (s[idx] == s[idx + k])).sum())
    total_sess = pairs_same([R["sess"]])
    return {"linked": linked, "tp": tp_user, "precision": tp_user / linked if linked else None, "session_recall": tp_sess / total_sess}

def main():
    out = {"seed": SEED, "tools": TOOLS, "days": DAYS, "session_window_s": 600, "calls_per_session": 4,
           "session_start": "uniform 08:00-22:00", "identifier": {}, "timing": []}
    rng = np.random.default_rng(SEED)
    R = simulate(1000, rng)
    idl, tot, tots = identifier_linkage(R)
    out["identifier"] = {"users": 1000, "calls": int(len(R["t"])), "same_principal_pairs": tot, "same_session_pairs": tots, "formats": idl}
    for U in (100, 1000, 10000):
        RU = simulate(U, np.random.default_rng(SEED + U))
        for J in (0, 600):
            RJ = dict(RU)
            if J:
                RJ["t"] = RU["t"] + np.random.default_rng(SEED + U + J).uniform(0, J, size=len(RU["t"]))
            for d in (10, 60, 600):
                r = timing(RJ, d)
                out["timing"].append({"users": U, "jitter_s": J, "delta_s": d, **r})
                print(U, J, d, r, file=sys.stderr, flush=True)
    json.dump(out, open("results/e3.json", "w"), indent=1)

if __name__ == "__main__":
    main()
