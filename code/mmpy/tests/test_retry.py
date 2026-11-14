"""mmpy v2.2.0 retry API: `release_counter` allows only an immediate retry of the SAME call.

Case 1 (same call): a presentation rejected by the tool is released; the rebuilt presentation for the same canonical call
reuses its counter (same pseudonym) and is accepted.
Case 2 (another call): after a release, the next presentation is for a different call: the released counter is burned
(fresh counter, new pseudonym), and it is never reused afterwards.

Usage: python code/mmpy/tests/test_retry.py   (with the project venv, after `maturin develop --release` in code/mmpy)
"""
import json
import mmpy

TOOL = "https://hotel.example|search"
EPOCH = 7
T = 1_000_000


def call(q):
    # canonical JSON (RFC 8785 for this simple shape: sorted keys, no spaces)
    return json.dumps({"arguments": {"q": q}, "name": "search"}, sort_keys=True, separators=(",", ":"))


def nym(blob):
    # Presentation bytes: accumulator value (48 bytes, compressed G1), then the pseudonym (48 bytes)
    return bytes(blob[48:96]).hex()


def main():
    a = mmpy.Authority(seed=20261114, k=64)
    v = mmpy.Verifier(a.public_params(), TOOL, False, 1, debug=True)
    out = {}

    # ---- case 1: immediate retry of the same call
    c = call("paris")
    p1 = a.present(0, TOOL, c, 1, 100, EPOCH, T, "n1", False)
    ok1, why1 = v.verify(c, 1, 101, EPOCH, T, "n1", p1)          # the tool sees another amount: rejected
    assert not ok1, "first attempt should be rejected"
    assert a.release_counter(0, TOOL, EPOCH)
    st_rel = a.retry_state(0, TOOL, EPOCH)
    p2 = a.present(0, TOOL, c, 1, 100, EPOCH, T, "n2", False)     # same canonical call, fresh tool nonce
    ok2, why2 = v.verify(c, 1, 100, EPOCH, T, "n2", p2)
    st1 = a.retry_state(0, TOOL, EPOCH)
    assert nym(p1) == nym(p2), "same call: the released counter must be reused"
    assert ok2, f"retry should be accepted: {why2}"
    assert st1 == (1, None, []), st1
    out["case1_same_call"] = {"first_rejected_reason": why1, "state_after_release": st_rel, "same_pseudonym": nym(p1) == nym(p2),
                              "retry_accepted": ok2, "state_after_retry": st1}
    # ---- case 2: after a release, a different call -> the released counter is burned
    a2 = mmpy.Authority(seed=20261115, k=64)
    v2 = mmpy.Verifier(a2.public_params(), TOOL, False, 2, debug=True)
    cA, cB = call("rome"), call("berlin")
    q1 = a2.present(0, TOOL, cA, 1, 100, EPOCH, T, "m1", False)
    okq1, whyq1 = v2.verify(cA, 1, 999, EPOCH, T, "m1", q1)       # rejected
    assert not okq1
    assert a2.release_counter(0, TOOL, EPOCH)
    q2 = a2.present(0, TOOL, cB, 1, 100, EPOCH, T, "m2", False)   # different call: released counter burned
    okq2, _ = v2.verify(cB, 1, 100, EPOCH, T, "m2", q2)
    st2 = a2.retry_state(0, TOOL, EPOCH)
    q3 = a2.present(0, TOOL, cA, 1, 100, EPOCH, T, "m3", False)   # the original call again, later: fresh counter too
    okq3, _ = v2.verify(cA, 1, 100, EPOCH, T, "m3", q3)
    st3 = a2.retry_state(0, TOOL, EPOCH)
    nyms = [nym(q1), nym(q2), nym(q3)]
    assert len(set(nyms)) == 3, "a burned counter must never be reused"
    assert okq2 and okq3
    assert st2 == (2, None, [0]) and st3 == (3, None, [0]), (st2, st3)
    out["case2_other_call"] = {"first_rejected_reason": whyq1, "distinct_pseudonyms": len(set(nyms)) == 3,
                               "other_call_accepted": okq2, "state_after_other_call": st2,
                               "original_call_later_accepted": okq3, "state_after_original_call": st3}
    # ---- release without a preceding presentation
    a3 = mmpy.Authority(seed=20261116, k=64)
    out["release_without_presentation"] = a3.release_counter(0, TOOL, EPOCH)
    assert out["release_without_presentation"] is False
    print(json.dumps(out, indent=1))
    print("test_retry: OK")


if __name__ == "__main__":
    main()
