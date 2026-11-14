"""E2 v2.1 -- end-to-end MCP calls with tool-issued challenges, four transports, functionally aligned baselines,
three independent runs.  Derived from e2v2.py (left unchanged); changes for the scheme version 2.1 and the reviews:

  * mmpy 2.1: `Authority(..., grace=0)`, `delegate(..., k, ..., epoch)` carving disjoint counter intervals, wallet that
    refuses stale/revoked mandates, tools in STRICT mode (`Verifier(pp, tool, esc, seed, epoch=EPOCH, now=..., tol=300)`):
    the tool's own `challenge` MCP tool returns `v.challenge()` and the tool's clock; the agent uses that tool time;
    the tool checks epoch, |t - now| <= tol and its own single-use nonce (errors are the uniform string "rejected").
  * currency: every canonical call carries `cur` ("EUR"), passed to MM as `cur`; all baselines hash the same call.
  * blind_tokens is now PROOF-OF-POSSESSION bound: the blind-signed token message commits to SHA-256 of a fresh
    per-token Ed25519 public key; at redemption the agent reveals the key and signs (call hash, tool identity, tool
    nonce, tool time) with it; the tool checks RSA-PSS signature, key hash, PoP signature, nonce, token-id seen-set.
    The previous bearer variant is kept as `blind_tokens_bearer`.
  * transport `http_stateless`: a fresh streamable-HTTP connection + MCP ClientSession (initialize) for every
    challenge and every call, so that neither the MCP session id nor the TCP connection links calls.
  * property table: what the ISSUER learns in each mode.
  * three independent runs (fresh processes, different seeds), each started only when the 1-min load <= 3.

Usage:
  RAYON_NUM_THREADS=1 python e2v21.py all RESULTS_DIR                    # 3 runs (fresh processes) + aggregate
  RAYON_NUM_THREADS=1 python e2v21.py run RUN_IDX OUT.json [modes] [transports]   # one run (waits for a quiet machine)
  python e2v21.py aggregate OUT.json SUMMARY.md RUN1.json RUN2.json RUN3.json
  python e2v21.py server MODE TOOL TRANSPORT PORT PUBFILE                (spawned by the client)
  python e2v21.py proxy LISTEN_PORT TARGET_PORT DELAY_MS                 (spawned by the client)
Environment: E2_CALLS (200), E2_WARMUP (15), E2_LOAD_MAX (3.0), E2_LOAD_WAIT_S (1200), E2_MM_DEBUG (0).
"""
import os
os.environ["RAYON_NUM_THREADS"] = "1"  # single-core crypto for the whole run (inherited by servers)
import asyncio, base64, hashlib, json, math, random, secrets, socket, statistics, subprocess, sys, tempfile, time

SEED_BASE = 20261109
SEED = int(os.environ.get("E2_SEED", SEED_BASE))   # per run: SEED_BASE + 1000 * run_idx (exported to the servers)
TOOLS = ["airline", "hotel", "payment"]
CLS = {"airline": 0, "hotel": 1, "payment": 2}
N_CALLS = int(os.environ.get("E2_CALLS", "200"))
WARMUP = int(os.environ.get("E2_WARMUP", "15"))
LOAD_MAX = float(os.environ.get("E2_LOAD_MAX", "3.0"))
LOAD_WAIT_S = int(os.environ.get("E2_LOAD_WAIT_S", "1200"))
MM_DEBUG = os.environ.get("E2_MM_DEBUG", "0") == "1"
EPOCH = 1
NONCE_TTL = 30.0
MM_TOL = 300
CUR = "EUR"
# Two-level delegation, identical semantics in every mode: classes {0,1,2}; per-call amount cap (integer cents); expiry
EXP_ROOT, EXP1, EXP2 = 1893456000, 1861920000, 1830297600       # 2030-01-01, 2029-01-01, 2028-01-01 (unix s)
BUD_ROOT, BUD1, BUD2 = 100000, 50000, 20000                       # cents
K_ROOT, K1, K2 = 100000, 10000, 5000                              # MM counters: root interval size; carved for agent1, agent2
SCOPE1 = SCOPE2 = [0, 1, 2]
MM_CHAINS = int(os.environ.get("E2_MM_CHAINS", "5"))                                                   # two-hop chains timed per (mode, transport, run)
PORT_BASE = int(os.environ.get("E2_PORT_BASE", "18400"))
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


# ======================================================================= helpers
def jcs(v):
    """RFC 8785 JSON Canonicalization Scheme for str/int/bool/None/dict/list (no floats)."""
    if v is None: return "null"
    if v is True: return "true"
    if v is False: return "false"
    if isinstance(v, int):
        assert abs(v) < 2**53, "JCS: integer outside IEEE-754 safe range"
        return str(v)
    if isinstance(v, str):
        out = ['"']
        for ch in v:
            o = ord(ch)
            if ch == '"': out.append('\\"')
            elif ch == '\\': out.append('\\\\')
            elif ch == '\b': out.append('\\b')
            elif ch == '\f': out.append('\\f')
            elif ch == '\n': out.append('\\n')
            elif ch == '\r': out.append('\\r')
            elif ch == '\t': out.append('\\t')
            elif o < 0x20: out.append('\\u%04x' % o)
            else: out.append(ch)
        out.append('"')
        return "".join(out)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        ks = sorted(v.keys(), key=lambda k: k.encode("utf-16-be"))  # sort by UTF-16 code units
        return "{" + ",".join(jcs(k) + ":" + jcs(v[k]) for k in ks) + "}"
    raise TypeError(f"JCS: unsupported type {type(v)} (floats are deliberately excluded)")

def call_json(name, args): return jcs({"name": name, "arguments": args})
def sha(s): return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def ub64(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

class DRBG:
    """Deterministic byte stream (SHA-256 counter mode) for reproducible client-side randomness in the experiment."""
    def __init__(self, label): self.k, self.c = hashlib.sha256(f"{SEED}|{label}".encode()).digest(), 0
    def bytes(self, n):
        out = b""
        while len(out) < n:
            out += hashlib.sha256(self.k + self.c.to_bytes(8, "big")).digest(); self.c += 1
        return out[:n]
    def int_below(self, n):
        return int.from_bytes(self.bytes((n.bit_length() + 7) // 8 + 16), "big") % n

def ed_sk(label):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(f"{SEED}|{label}".encode()).digest())

def ed_raw(pk):
    from cryptography.hazmat.primitives import serialization as s
    return pk.public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)

def ed_pk(raw):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    return Ed25519PublicKey.from_public_bytes(raw)

def jwk(pk): return {"kty": "OKP", "crv": "Ed25519", "x": b64(ed_raw(pk))}

def ms(t0, t1): return (t1 - t0) * 1e3

def gen_args(tool, i):
    amt = 5000 + (i * 37) % 10000          # integer cents, always <= BUD2
    if tool == "airline": return {"dest": f"CDG-JFK-{i}", "date": "2027-01-15", "amt": amt, "cur": CUR}
    if tool == "hotel": return {"city": "Lyon", "nights": 1 + i % 5, "amt": amt, "cur": CUR}
    return {"payee": "acme-travel", "ref": f"inv-{i}", "amt": amt, "cur": CUR}

def pop_msg(H, tool_id, nonce, t):
    """Message signed by a per-token / leaf key at redemption (batch and blind PoP tokens)."""
    return jcs({"call": H, "tool": tool_id, "nonce": nonce, "t": t}).encode()


# ======================================================================= RSA blind signatures (RFC 9474)
# RSABSSA-SHA384-PSS-Randomized: EMSA-PSS (SHA-384, MGF1-SHA-384, sLen=48), 32-byte random message prefix.
# Client blind/finalize and issuer BlindSign are implemented here in pure Python (big-int pow, CRT on the issuer);
# the final signature is a standard RSASSA-PSS signature, verified by tools with OpenSSL via `cryptography`.
SLEN, HLEN = 48, 48

def _is_probable_prime(n, rnd):
    if n < 2: return False
    for p in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47):
        if n % p == 0: return n == p
    d, s = n - 1, 0
    while d % 2 == 0: d //= 2; s += 1
    for _ in range(40):
        a = 2 + rnd.int_below(n - 3)
        x = pow(a, d, n)
        if x in (1, n - 1): continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1: break
        else: return False
    return True

def rsa_keygen_det(label, bits=2048, e=65537):
    """Deterministic RSA-2048 key (for reproducibility only)."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    rnd = DRBG("rsa|" + label)
    def prime():
        while True:
            c = int.from_bytes(rnd.bytes(bits // 16), "big") | (3 << (bits // 2 - 2)) | 1
            if math.gcd(e, c - 1) == 1 and _is_probable_prime(c, rnd): return c
    p = prime(); q = prime()
    while q == p: q = prime()
    if p < q: p, q = q, p
    n, d = p * q, pow(e, -1, (p - 1) * (q - 1))
    return rsa.RSAPrivateNumbers(p, q, d, d % (p - 1), d % (q - 1), pow(q, -1, p), rsa.RSAPublicNumbers(e, n)).private_key()

def _mgf1(seed, ln):
    out, c = b"", 0
    while len(out) < ln: out += hashlib.sha384(seed + c.to_bytes(4, "big")).digest(); c += 1
    return out[:ln]

def emsa_pss_encode(msg, embits, salt):
    emlen = (embits + 7) // 8
    mh = hashlib.sha384(msg).digest()
    H = hashlib.sha384(b"\x00" * 8 + mh + salt).digest()
    db = b"\x00" * (emlen - SLEN - HLEN - 2) + b"\x01" + salt
    mdb = bytes(a ^ b for a, b in zip(db, _mgf1(H, emlen - HLEN - 1)))
    mdb = bytes([mdb[0] & (0xFF >> (8 * emlen - embits))]) + mdb[1:]
    return mdb + H + b"\xbc"

def rsabssa_blind(n, e, input_msg, rnd):
    kl = (n.bit_length() + 7) // 8
    m = int.from_bytes(emsa_pss_encode(input_msg, n.bit_length() - 1, rnd.bytes(SLEN)), "big")
    if math.gcd(m, n) != 1: raise ValueError("invalid input")
    while True:
        r = 1 + rnd.int_below(n - 1)
        if math.gcd(r, n) == 1: break
    return (m * pow(r, e, n) % n).to_bytes(kl, "big"), pow(r, -1, n)

def rsabssa_blind_sign(priv, blinded):
    pn = priv.private_numbers(); n, e = pn.public_numbers.n, pn.public_numbers.e
    m = int.from_bytes(blinded, "big")
    if m >= n: raise ValueError("message representative out of range")
    s1, s2 = pow(m, pn.dmp1, pn.p), pow(m, pn.dmq1, pn.q)                 # RSASP1 with CRT
    s = s2 + pn.q * ((pn.iqmp * (s1 - s2)) % pn.p)
    if pow(s, e, n) != m: raise ValueError("signing failure")             # RFC 9474 sect. 4.3 step 4
    return s.to_bytes((n.bit_length() + 7) // 8, "big")

def rsabssa_finalize(pub, input_msg, blind_sig, inv):
    pn = pub.public_numbers(); n = pn.n
    sig = (int.from_bytes(blind_sig, "big") * inv % n).to_bytes((n.bit_length() + 7) // 8, "big")
    rsa_pss_verify(pub, input_msg, sig)
    return sig

def rsa_pss_verify(pub, input_msg, sig):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    pub.verify(sig, input_msg, padding.PSS(mgf=padding.MGF1(hashes.SHA384()), salt_length=SLEN), hashes.SHA384())

def blind_variant(mode): return "pop" if mode == "blind_tokens" else "bearer"
def blind_kid(variant, cls, tier, epoch): return f"{variant}-c{cls}-t{tier}-e{epoch}"


# ======================================================================= issuer / agent side (client process)
class JwtChain:
    """Root mandate JWT signed by the issuer (for agent1), delegation JWT signed by agent1 (for agent2)."""
    def __init__(self):
        import jwt
        self.jwt = jwt
        self.iss, self.a1, self.a2 = ed_sk("issuer"), ed_sk("agent1"), ed_sk("agent2")

    def build(self):
        t0 = time.perf_counter()
        root = self.jwt.encode({"iss": "issuer", "sub": "agent1", "jti": "m-root-agent1", "principal": "alice",
                                "scope": SCOPE1, "budget": BUD1, "exp": EXP1, "cnf": {"jwk": jwk(self.a1.public_key())}},
                               self.iss, algorithm="EdDSA")
        t1 = time.perf_counter()
        deleg = self.jwt.encode({"iss": "agent1", "sub": "agent2", "jti": "m-agent1-agent2", "prev": sha(root),
                                 "scope": SCOPE2, "budget": BUD2, "exp": EXP2, "cnf": {"jwk": jwk(self.a2.public_key())}},
                                self.a1, algorithm="EdDSA")
        t2 = time.perf_counter()
        return [root, deleg], {"hop1_issuer_sign_ms": ms(t0, t1), "hop2_agent1_sign_ms": ms(t1, t2)}

def verify_jwt_chain(jwt, iss_pub, chain, revoked):
    """Full chain check in the clear: signatures, linkage, attenuation monotonicity, expiry, status list.
    Returns the leaf claims."""
    root = jwt.decode(chain[0], iss_pub, algorithms=["EdDSA"], options={"require": ["exp", "jti"]})
    if root["iss"] != "issuer": raise ValueError("root issuer")
    parent, prev_tok, jtis = root, chain[0], [root["jti"]]
    for tok in chain[1:]:
        d = jwt.decode(tok, ed_pk(ub64(parent["cnf"]["jwk"]["x"])), algorithms=["EdDSA"], options={"require": ["exp", "jti"]})
        if d["iss"] != parent["sub"]: raise ValueError("chain linkage (iss/sub)")
        if d["prev"] != sha(prev_tok): raise ValueError("chain linkage (prev hash)")
        if not set(d["scope"]) <= set(parent["scope"]): raise ValueError("attenuation: scope")
        if d["budget"] > parent["budget"]: raise ValueError("attenuation: budget")
        if d["exp"] > parent["exp"]: raise ValueError("attenuation: exp")
        parent, prev_tok = d, tok
        jtis.append(d["jti"])
    if any(j in revoked for j in jtis): raise ValueError("revoked (status list)")
    return parent, jtis


class Client:
    """One per (mode, transport, run). setup() builds the two-level delegation (and token batches) and returns costs."""
    def __init__(self, mode, tmpdir, rsa_keys):
        self.mode, self.tmp, self.rsa_keys = mode, tmpdir, rsa_keys
        self.rnd = DRBG(f"client|{mode}")
        self.pub = {}

    # ---------------------------------------------------------------- setup / delegation
    def setup(self, n_tokens_per_class, tag):
        m, cost = self.mode, {}
        if m == "none":
            cost = {"two_hop_total_ms": 0.0}
        elif m in ("jwt_chain", "batch_tokens", "blind_tokens", "blind_tokens_bearer"):
            import jwt
            self.jwt = jwt
            self.jc = JwtChain()
            reps = [self.jc.build()[1] for _ in range(50)]
            self.chain, c = self.jc.build()
            cost = {k: statistics.median([r[k] for r in reps]) for k in reps[0]}
            cost["two_hop_total_ms"] = sum(cost.values())
            cost["reps"] = 50
            cost["two_hop_chains_ms"] = [sum(r.values()) for r in reps]
            self.pub["iss_pub"] = b64(ed_raw(self.jc.iss.public_key()))
            if m == "batch_tokens": cost.update(self.issue_batch(n_tokens_per_class))
            if m in ("blind_tokens", "blind_tokens_bearer"): cost.update(self.issue_blind(n_tokens_per_class, blind_variant(m)))
        elif m == "biscuit":
            import biscuit_auth as b
            self.b = b
            root = b.PrivateKey.from_bytes(hashlib.sha256(f"{SEED}|biscuit".encode()).digest(), b.Algorithm.Ed25519)
            def build():
                t0 = time.perf_counter()
                tok = b.BiscuitBuilder(
                    f'principal("alice"); right(0); right(1); right(2); '
                    f'check if time($t), $t <= {EXP_ROOT}; check if amount($a), $a <= {BUD_ROOT};').build(root)
                t1 = time.perf_counter()
                tok = tok.append(b.BlockBuilder(f'delegate("agent1"); check if class($c), [0, 1, 2].contains($c); '
                                                f'check if amount($a), $a <= {BUD1}; check if time($t), $t <= {EXP1};'))
                t2 = time.perf_counter()
                tok = tok.append(b.BlockBuilder(f'delegate("agent2"); check if class($c), [0, 1, 2].contains($c); '
                                                f'check if amount($a), $a <= {BUD2}; check if time($t), $t <= {EXP2};'))
                t3 = time.perf_counter()
                return tok, {"authority_block_issuer_ms": ms(t0, t1), "hop1_attenuation_block_ms": ms(t1, t2),
                             "hop2_attenuation_block_ms": ms(t2, t3)}
            reps = [build()[1] for _ in range(50)]
            self.tok, _ = build()
            cost = {k: statistics.median([r[k] for r in reps]) for k in reps[0]}
            cost["two_hop_total_ms"] = sum(cost.values()); cost["reps"] = 50
            cost["two_hop_chains_ms"] = [sum(r.values()) for r in reps]
            self.pub["biscuit_root_pub"] = KeyPairPub(b, root)
        elif m == "macaroon":
            from pymacaroons import Macaroon
            key = hashlib.sha256(f"{SEED}|mac".encode()).hexdigest()
            def build():
                t0 = time.perf_counter()
                mac = Macaroon(location="issuer", identifier="alice-root-mandate", key=key)
                t1 = time.perf_counter()
                mac.add_first_party_caveat(f"deleg agent1 classes=0,1,2 budget<={BUD1} exp<={EXP1}")
                t2 = time.perf_counter()
                mac.add_first_party_caveat(f"deleg agent2 classes=0,1,2 budget<={BUD2} exp<={EXP2}")
                t3 = time.perf_counter()
                return mac, {"root_mint_ms": ms(t0, t1), "hop1_caveat_ms": ms(t1, t2), "hop2_caveat_ms": ms(t2, t3)}
            reps = [build()[1] for _ in range(50)]
            self.mac, _ = build()
            cost = {k: statistics.median([r[k] for r in reps]) for k in reps[0]}
            cost["two_hop_total_ms"] = sum(cost.values()); cost["reps"] = 50
            cost["two_hop_chains_ms"] = [sum(r.values()) for r in reps]
            self.pub["macaroon_root_key_SHARED_SECRET"] = key
        elif m in ("mm", "mm_esc"):
            import mmpy
            t0 = time.perf_counter()
            self.auth = mmpy.Authority(SEED, uid=42, budget=BUD_ROOT, k=K_ROOT, exp=EXP_ROOT, grace=0)
            t1 = time.perf_counter()
            reps = []
            for r in range(MM_CHAINS):   # r = 0 is the chain used for the calls; the others are extra chains for timing
                a0 = time.perf_counter()
                i1, pm1, im1 = self.auth.delegate(0, SCOPE1, BUD1, K1, EXP1, EPOCH)
                a1 = time.perf_counter()
                i2, pm2, im2 = self.auth.delegate(i1, SCOPE2, BUD2, K2, EXP2, EPOCH)
                a2 = time.perf_counter()
                if r == 0: self.i1, self.i2 = i1, i2
                reps.append({"hop1_parent_ms": pm1, "hop1_issuer_ms": im1, "hop1_wall_ms": ms(a0, a1),
                             "hop2_parent_ms": pm2, "hop2_issuer_ms": im2, "hop2_wall_ms": ms(a1, a2)})
            cost = {k: statistics.median([r[k] for r in reps]) for k in reps[0]}
            cost["two_hop_total_ms"] = statistics.median([r["hop1_wall_ms"] + r["hop2_wall_ms"] for r in reps])
            cost["two_hop_chains_ms"] = [r["hop1_wall_ms"] + r["hop2_wall_ms"] for r in reps]
            cost["reps"] = MM_CHAINS; cost["authority_setup_ms"] = ms(t0, t1)
            cost["intervals"] = {"root": list(self.auth.interval(0)), "agent1": list(self.auth.interval(self.i1)),
                                 "agent2": list(self.auth.interval(self.i2))}
            pp = self.auth.public_params()
            path = os.path.join(self.tmp, f"pp_{m}_{tag}.bin"); open(path, "wb").write(pp)
            self.pub["mm_pp_path"] = path; self.pub["mm_pp_bytes"] = len(pp)
        self.pubfile = os.path.join(self.tmp, f"pub_{m}_{tag}.json")
        json.dump(self.pub, open(self.pubfile, "w"))
        return cost

    def _issuance_request(self, payload):
        """agent2 -> issuer: chain + request signed with agent2's chain-leaf key (PoP of the delegation)."""
        req = {"chain": self.chain, "payload": payload}
        req["sig"] = b64(self.jc.a2.sign(jcs(payload).encode()))
        return req

    def _issuer_check_request(self, req):
        leaf, _ = verify_jwt_chain(self.jwt, self.jc.iss.public_key(), req["chain"], set())
        ed_pk(ub64(leaf["cnf"]["jwk"]["x"])).verify(ub64(req["sig"]), jcs(req["payload"]).encode())
        return leaf

    def issue_batch(self, n_per_class):
        """SD-JWT/EUDI batch-issuance pattern: issuer checks the chain in the clear, then signs single-use tokens with
        public metadata only (class, budget tier, epoch, random token id, cnf = fresh per-token Ed25519 key)."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.bat_iss = ed_sk("batch-issuer")
        self.pub["batch_issuer_pub"] = b64(ed_raw(self.bat_iss.public_key()))
        t0 = time.perf_counter()
        keys = {c: [Ed25519PrivateKey.from_private_bytes(self.rnd.bytes(32)) for _ in range(n_per_class)] for c in SCOPE2}
        payload = {"epoch": EPOCH, "keys": {str(c): [b64(ed_raw(k.public_key())) for k in keys[c]] for c in SCOPE2}}
        req = self._issuance_request(payload)
        t1 = time.perf_counter()
        leaf = self._issuer_check_request(req)                      # issuer: chain in the clear + request signature
        t2 = time.perf_counter()
        self.tokens = {c: [] for c in SCOPE2}
        self.tok_ids_issued = []
        for c in SCOPE2:
            if c not in leaf["scope"]: raise ValueError("class not in delegated scope")
            for k, kpub in zip(keys[c], payload["keys"][str(c)]):
                tid = b64(self.rnd.bytes(16))
                body = jcs({"cls": c, "tier": leaf["budget"], "epoch": EPOCH, "tid": tid, "cnf": kpub}).encode()
                tokstr = b64(body) + "." + b64(self.bat_iss.sign(body))
                self.tokens[c].append((tokstr, k)); self.tok_ids_issued.append(tid)
        t3 = time.perf_counter()
        n = n_per_class * len(SCOPE2)
        return {"batch_size": n, "agent_keygen_and_request_ms": ms(t0, t1), "issuer_chain_check_ms": ms(t1, t2),
                "issuer_sign_batch_ms": ms(t2, t3), "issuance_total_ms": ms(t0, t3),
                "per_token_issuance_ms": ms(t0, t3) / n, "per_token_issuer_sign_ms": ms(t2, t3) / n,
                "per_token_agent_keygen_ms": ms(t0, t1) / n}

    def issue_blind(self, n_per_class, variant):
        """RFC 9474 RSABSSA-SHA384-PSS-Randomized. Public metadata (class, tier, epoch) is bound by using one issuer key
        per metadata value (Privacy-Pass style key-per-metadata); the issuer chooses the key after checking the chain
        in the clear, and never sees the token message.
        variant 'pop': the token message also commits to pkh = SHA-256(raw Ed25519 public key) of a fresh per-token
        key generated by the agent; the key is revealed only at redemption, with a PoP signature over the call."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        tier = BUD2
        for c in SCOPE2:
            self.pub.setdefault("rsa_pub", {})[blind_kid(variant, c, tier, EPOCH)] = [str(self.rsa_keys[c].public_key().public_numbers().n), 65537]
        t0 = time.perf_counter()
        pend = {c: [] for c in SCOPE2}
        for c in SCOPE2:
            pub = self.rsa_keys[c].public_key(); n = pub.public_numbers().n
            for _ in range(n_per_class):
                body = {"cls": c, "tier": tier, "epoch": EPOCH, "rand": b64(self.rnd.bytes(32))}
                k = None
                if variant == "pop":
                    k = Ed25519PrivateKey.from_private_bytes(self.rnd.bytes(32))
                    body["pkh"] = sha(ed_raw(k.public_key()))
                msg = jcs(body).encode()
                prefix = self.rnd.bytes(32)
                blinded, inv = rsabssa_blind(n, 65537, prefix + msg, self.rnd)
                pend[c].append((msg, prefix, blinded, inv, k))
        payload = {"epoch": EPOCH, "tier": tier, "blinded": {str(c): [sha(x[2]) for x in pend[c]] for c in SCOPE2}}
        req = self._issuance_request(payload)
        t1 = time.perf_counter()
        leaf = self._issuer_check_request(req)
        if leaf["budget"] < tier: raise ValueError("tier above delegated budget")
        t2 = time.perf_counter()
        bsigs = {c: [rsabssa_blind_sign(self.rsa_keys[c], x[2]) for x in pend[c]] for c in SCOPE2}
        t3 = time.perf_counter()
        self.tokens = {c: [] for c in SCOPE2}
        for c in SCOPE2:
            pub = self.rsa_keys[c].public_key()
            for (msg, prefix, _, inv, k), bs in zip(pend[c], bsigs[c]):
                sig = rsabssa_finalize(pub, prefix + msg, bs, inv)
                self.tokens[c].append(({"kid": blind_kid(variant, c, tier, EPOCH), "msg": msg.decode(), "prefix": b64(prefix),
                                        "sig": b64(sig)}, k))
        t4 = time.perf_counter()
        n = n_per_class * len(SCOPE2)
        return {"batch_size": n, "variant": variant, "agent_keygen_blind_and_request_ms": ms(t0, t1),
                "issuer_chain_check_ms": ms(t1, t2), "issuer_blind_sign_batch_ms": ms(t2, t3),
                "agent_finalize_batch_ms": ms(t3, t4), "issuance_total_ms": ms(t0, t4),
                "per_token_issuance_ms": ms(t0, t4) / n, "per_token_agent_keygen_blind_ms": ms(t0, t1) / n,
                "per_token_issuer_blind_sign_ms": ms(t2, t3) / n, "per_token_agent_finalize_ms": ms(t3, t4) / n}

    # ---------------------------------------------------------------- per call
    def authorize(self, tool_id, tname, args, call, nonce, t):
        m, cls, H = self.mode, CLS[tname], sha(call)
        if m == "none": return {}
        if m == "jwt_chain":
            pop = self.jwt.encode({"aud": tool_id, "call": H, "nonce": nonce, "iat": t}, self.jc.a2, algorithm="EdDSA")
            return {"nonce": nonce, "chain": self.chain, "pop": pop}
        if m == "biscuit":
            tok = self.tok.append(self.b.BlockBuilder(
                f'check if call_hash("{H}"), tool_id("{tool_id}"), nonce("{nonce}");'))
            return {"nonce": nonce, "biscuit": tok.to_base64()}
        if m == "macaroon":
            mac = self.mac.copy()
            mac.add_first_party_caveat(f"call = {H}")
            mac.add_first_party_caveat(f"tool = {tool_id}")
            mac.add_first_party_caveat(f"nonce = {nonce}")
            return {"nonce": nonce, "macaroon": mac.serialize()}
        if m == "batch_tokens":
            tokstr, k = self.tokens[cls].pop(0)
            return {"nonce": nonce, "token": tokstr, "pop": b64(k.sign(pop_msg(H, tool_id, nonce, t)))}
        if m == "blind_tokens":
            tok, k = self.tokens[cls].pop(0)
            return {"nonce": nonce, "token": tok, "pk": b64(ed_raw(k.public_key())),
                    "pop": b64(k.sign(pop_msg(H, tool_id, nonce, t)))}
        if m == "blind_tokens_bearer":
            tok, _ = self.tokens[cls].pop(0)
            return {"nonce": nonce, "token": tok, "call_hash": H}
        if m in ("mm", "mm_esc"):
            blob = self.auth.present(self.i2, tool_id, call, cls, int(args["amt"]), EPOCH, t, nonce, m == "mm_esc", cur=args["cur"])
            return {"nonce": nonce, "t": t, "mm": base64.b64encode(bytes(blob)).decode()}
        raise ValueError(m)

    def tamper(self, meta, new_call):
        """What an on-path attacker can rewrite without any key: only unsigned plain fields."""
        meta = json.loads(json.dumps(meta))
        if self.mode == "blind_tokens_bearer": meta["call_hash"] = sha(new_call)
        return meta

    def revoke_payload(self):
        """Revoke agent1's delegation (hence agent2's sub-mandate); returns what the issuer pushes to tools."""
        m = self.mode
        if m == "jwt_chain": return json.dumps({"revoked_jti": ["m-root-agent1"]})
        if m == "batch_tokens": return json.dumps({"revoked_tid": self.tok_ids_issued})
        if m == "biscuit": return json.dumps({"revoked_ids": [self.tok.revocation_ids[1]]})
        if m in ("mm", "mm_esc"): return base64.b64encode(bytes(self.auth.revoke(self.i1))).decode()
        return ""   # none / macaroon / blind tokens: no revocation mechanism in the baseline

def KeyPairPub(b, priv):
    return b.KeyPair.from_private_key(priv).public_key.to_bytes().hex()


# ======================================================================= tool side (server process)
class Checker:
    def __init__(self, mode, tool_id, tname, pub):
        self.mode, self.tool_id, self.tname, self.cls = mode, tool_id, tname, CLS[tname]
        self.nonces = {}           # nonce -> (tool time t, monotonic expiry)   [all modes except MM: Rust strict store]
        self.seen = set()          # replay set (per mode: nonce, token id, ...)
        self.revoked = set()       # status list (jwt_chain: jti; batch_tokens: tid; biscuit: revocation ids)
        if mode in ("jwt_chain",):
            import jwt
            self.jwt, self.iss_pub = jwt, ed_pk(ub64(pub["iss_pub"]))
        elif mode == "biscuit":
            import biscuit_auth as b
            self.b, self.root_pub = b, b.PublicKey.from_bytes(bytes.fromhex(pub["biscuit_root_pub"]), b.Algorithm.Ed25519)
        elif mode == "macaroon":
            self.key = pub["macaroon_root_key_SHARED_SECRET"]
        elif mode == "batch_tokens":
            self.bat_pub = ed_pk(ub64(pub["batch_issuer_pub"]))
        elif mode in ("blind_tokens", "blind_tokens_bearer"):
            from cryptography.hazmat.primitives.asymmetric import rsa
            self.variant = blind_variant(mode)
            self.rsa = {k: rsa.RSAPublicNumbers(int(v[1]), int(v[0])).public_key() for k, v in pub["rsa_pub"].items()}
        elif mode in ("mm", "mm_esc"):
            import mmpy
            self.v = mmpy.Verifier(open(pub["mm_pp_path"], "rb").read(), tool_id, mode == "mm_esc", SEED + 7,
                                   epoch=EPOCH, now=int(time.time()), tol=MM_TOL, debug=MM_DEBUG)

    def challenge(self):
        t = int(time.time())
        if self.mode in ("mm", "mm_esc"):
            self.v.set_clock(EPOCH, t)
            return {"nonce": self.v.challenge(), "t": t, "epoch": EPOCH, "tol_s": MM_TOL}
        n = secrets.token_urlsafe(16)
        now = time.monotonic()
        if len(self.nonces) > 1000:
            self.nonces = {k: v for k, v in self.nonces.items() if v[1] > now}
        self.nonces[n] = (t, now + NONCE_TTL)
        return {"nonce": n, "t": t, "ttl_s": NONCE_TTL}

    def admin(self, payload):
        m = self.mode
        if m in ("mm", "mm_esc"): self.v.update(base64.b64decode(payload)); return "pp updated"
        if not payload: return "no revocation mechanism"
        d = json.loads(payload)
        for k in ("revoked_jti", "revoked_tid", "revoked_ids"): self.revoked.update(d.get(k, []))
        return f"status list: {len(self.revoked)} entries"

    def check(self, meta, tname, args):
        m = self.mode
        if m == "none": return True, ""
        call = call_json(tname, args)
        H, amt = sha(call), int(args["amt"])
        nonce = meta.get("nonce")
        if m in ("mm", "mm_esc"):
            # strict Rust tool: epoch, |t - now| <= tol, own single-use nonce, accumulator value, pseudonym seen-set, proof
            self.v.set_clock(EPOCH, int(time.time()))
            t = meta.get("t")
            if not isinstance(t, int) or not isinstance(nonce, str): return False, "rejected"
            ok, why = self.v.verify(call, self.cls, amt, EPOCH, t, nonce, base64.b64decode(meta["mm"]), cur=args["cur"])
            return ok, why
        ent = self.nonces.pop(nonce, None) if isinstance(nonce, str) else None   # single use: consumed on any attempt
        if ent is None: return False, "unknown or already used tool nonce"
        t, exp = ent
        if time.monotonic() > exp: return False, "expired tool nonce"
        if m == "jwt_chain":
            leaf, jtis = verify_jwt_chain(self.jwt, self.iss_pub, meta["chain"], self.revoked)
            pop = self.jwt.decode(meta["pop"], ed_pk(ub64(leaf["cnf"]["jwk"]["x"])), algorithms=["EdDSA"], audience=self.tool_id)
            if pop["call"] != H: return False, "call hash"
            if pop["nonce"] != nonce or pop["iat"] != t: return False, "nonce/time binding"
            if self.cls not in leaf["scope"]: return False, "class not in scope"
            if amt > leaf["budget"]: return False, "amount above budget"
            if t > leaf["exp"]: return False, "expired"
            key = ("pop", sha(meta["pop"]))
        elif m == "biscuit":
            tok = self.b.Biscuit.from_base64(meta["biscuit"], self.root_pub)
            if any(r in self.revoked for r in tok.revocation_ids): return False, "revoked (revocation id)"
            az = self.b.AuthorizerBuilder(
                f'class({self.cls}); amount({amt}); time({t}); call_hash("{H}"); tool_id("{self.tool_id}"); nonce("{nonce}"); '
                f'allow if right({self.cls});').build(tok)
            az.authorize()
            key = ("nonce", nonce)
        elif m == "macaroon":
            from pymacaroons import Macaroon, Verifier
            mac = Macaroon.deserialize(meta["macaroon"])
            v = Verifier()
            v.satisfy_exact(f"call = {H}"); v.satisfy_exact(f"tool = {self.tool_id}"); v.satisfy_exact(f"nonce = {nonce}")
            def deleg(c):
                p = c.split()
                if len(p) != 5 or p[0] != "deleg" or p[1] not in ("agent1", "agent2"): return False
                kv = dict(x.replace("<=", "=").split("=") for x in p[2:])
                return (str(self.cls) in kv["classes"].split(",") and amt <= int(kv["budget"]) and t <= int(kv["exp"]))
            v.satisfy_general(deleg)
            v.verify(mac, self.key)
            key = ("nonce", nonce)
        elif m == "batch_tokens":
            body_b64, sig_b64 = meta["token"].split(".")
            body = ub64(body_b64)
            self.bat_pub.verify(ub64(sig_b64), body)
            tk = json.loads(body)
            if tk["cls"] != self.cls: return False, "class"
            if amt > tk["tier"]: return False, "amount above tier"
            if tk["epoch"] != EPOCH: return False, "epoch"
            if tk["tid"] in self.revoked: return False, "revoked (status list)"
            ed_pk(ub64(tk["cnf"])).verify(ub64(meta["pop"]), pop_msg(H, self.tool_id, nonce, t))
            key = ("tid", tk["tid"])
        elif m in ("blind_tokens", "blind_tokens_bearer"):
            tok = meta["token"]
            md = json.loads(tok["msg"])
            if tok["kid"] != blind_kid(self.variant, md["cls"], md["tier"], md["epoch"]) or tok["kid"] not in self.rsa:
                return False, "key/metadata"
            rsa_pss_verify(self.rsa[tok["kid"]], ub64(tok["prefix"]) + tok["msg"].encode(), ub64(tok["sig"]))
            if md["cls"] != self.cls: return False, "class"
            if amt > md["tier"]: return False, "amount above tier"
            if md["epoch"] != EPOCH: return False, "epoch"
            if self.variant == "pop":
                pk = ub64(meta["pk"])
                if sha(pk) != md["pkh"]: return False, "PoP key does not match the token's key hash"
                ed_pk(pk).verify(ub64(meta["pop"]), pop_msg(H, self.tool_id, nonce, t))   # raises InvalidSignature
            else:
                if meta["call_hash"] != H: return False, "call hash field"
            key = ("rand", md["rand"])
        else:
            raise ValueError(m)
        if key in self.seen: return False, "replay"
        self.seen.add(key)
        return True, ""


def run_server(mode, tname, transport, port, pubfile):
    import logging
    from mcp.server.fastmcp import FastMCP, Context
    origin = f"stdio://e2v21-{tname}" if transport == "stdio" else f"http://127.0.0.1:{port}"
    tool_id = f"{origin}|{tname}"
    pub = json.load(open(pubfile))
    chk = Checker(mode, tool_id, tname, pub)
    srv = FastMCP(f"e2v21-{tname}", host="127.0.0.1", port=port, log_level="WARNING")
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    def handle(args, ctx):
        meta = ctx.request_context.meta
        md = meta.model_dump() if meta is not None else {}
        t0 = time.perf_counter()
        try:
            ok, why = chk.check(md, tname, args)
        except Exception as e:
            ok, why = False, f"{type(e).__name__}: {e}"
        dt = ms(t0, time.perf_counter())
        return json.dumps({"ok": ok, "why": why, "verify_ms": dt, "tool_id": tool_id,
                           "result": f"{tname}: confirmed {args}" if ok else None})

    if tname == "airline":
        @srv.tool(name="airline")
        def airline(dest: str, date: str, amt: int, cur: str, ctx: Context) -> str:
            return handle({"dest": dest, "date": date, "amt": amt, "cur": cur}, ctx)
    elif tname == "hotel":
        @srv.tool(name="hotel")
        def hotel(city: str, nights: int, amt: int, cur: str, ctx: Context) -> str:
            return handle({"city": city, "nights": nights, "amt": amt, "cur": cur}, ctx)
    else:
        @srv.tool(name="payment")
        def payment(payee: str, ref: str, amt: int, cur: str, ctx: Context) -> str:
            return handle({"payee": payee, "ref": ref, "amt": amt, "cur": cur}, ctx)

    @srv.tool(name="challenge")
    def challenge() -> str:
        return json.dumps(chk.challenge())

    @srv.tool(name="admin_update")
    def admin_update(payload: str) -> str:
        return chk.admin(payload)

    srv.run("stdio" if transport == "stdio" else "streamable-http")


# ======================================================================= delay relay
def run_proxy(lport, tport, delay_ms):
    d = delay_ms / 1e3

    async def pump(reader, writer):
        q = asyncio.Queue()
        async def rx():
            while True:
                data = await reader.read(65536)
                await q.put((time.monotonic() + d, data))
                if not data: return
        async def tx():
            while True:
                due, data = await q.get()
                w = due - time.monotonic()
                if w > 0: await asyncio.sleep(w)
                if not data:
                    try: writer.write_eof()
                    except Exception: pass
                    return
                writer.write(data); await writer.drain()
        try: await asyncio.gather(rx(), tx())
        except Exception: pass
        finally:
            try: writer.close()
            except Exception: pass

    async def on_conn(cr, cw):
        sr, sw = await asyncio.open_connection("127.0.0.1", tport)
        await asyncio.gather(pump(cr, sw), pump(sr, cw))

    async def main():
        s = await asyncio.start_server(on_conn, "127.0.0.1", lport)
        async with s: await s.serve_forever()
    asyncio.run(main())


# ======================================================================= client driver
def wait_port(port, timeout=30):
    t = time.time()
    while time.time() - t < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2): return
        except OSError: time.sleep(0.05)
    raise RuntimeError(f"port {port} not ready")

def pct(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p / 100; f = math.floor(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

METRICS = ("challenge_rtt_ms", "prep_ms", "call_rtt_ms", "verify_ms", "total_ms", "session_setup_ms", "session_close_ms", "auth_bytes")

def summarize(rows, key):
    xs = [r[key] for r in rows]
    return {"median": statistics.median(xs), "p95": pct(xs, 95), "mean": statistics.fmean(xs), "min": min(xs), "max": max(xs)}

async def run_one(mode, transport, cfg_idx, run_idx, tmpdir, rsa_keys):
    from contextlib import AsyncExitStack
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client
    cl = Client(mode, tmpdir, rsa_keys)
    n_per_class = math.ceil((WARMUP + N_CALLS) / 3) + 8
    deleg_cost = cl.setup(n_per_class, f"{transport}")
    stateless = transport == "http_stateless"
    procs, logs = [], []
    rows, controls = [], {}
    env = {**os.environ, "RAYON_NUM_THREADS": "1", "E2_SEED": str(SEED)}
    async with AsyncExitStack() as st:
        sess, tool_ids, urls = {}, {}, {}
        for k, tname in enumerate(TOOLS):
            if transport == "stdio":
                p = StdioServerParameters(command=PY, args=[__file__, "server", mode, tname, "stdio", "0", cl.pubfile], env=env)
                r, w = await st.enter_async_context(stdio_client(p))
                tool_ids[tname] = f"stdio://e2v21-{tname}|{tname}"
            else:
                port = PORT_BASE + 500 * run_idx + 10 * cfg_idx + k
                lf = open(os.path.join(tmpdir, f"srv_{mode}_{transport}_{tname}.log"), "w"); logs.append(lf)
                procs.append(subprocess.Popen([PY, __file__, "server", mode, tname, "http", str(port), cl.pubfile], env=env, stdout=lf, stderr=lf))
                wait_port(port)
                cport = port
                if transport == "http_delay10":
                    cport = port + 5000
                    procs.append(subprocess.Popen([PY, __file__, "proxy", str(cport), str(port), "10"], env=env, stdout=lf, stderr=lf))
                    wait_port(cport)
                tool_ids[tname] = f"http://127.0.0.1:{port}|{tname}"
                urls[tname] = f"http://127.0.0.1:{cport}/mcp"
                if not stateless:
                    r, w, _ = await st.enter_async_context(streamable_http_client(urls[tname]))
            if not stateless:
                s = await st.enter_async_context(ClientSession(r, w))
                await s.initialize()
                sess[tname] = s

        async def rpc(tname, name, args, meta=None):
            """One MCP tools/call. Returns (text, session_setup_ms, session_close_ms). In http_stateless every rpc opens a
            fresh httpx client (new TCP connection), a fresh ClientSession (initialize -> new Mcp-Session-Id) and closes
            it afterwards (session DELETE + connection close)."""
            if not stateless:
                res = await sess[tname].call_tool(name, args, meta=meta or None)
                return res.content[0].text, 0.0, 0.0
            a = time.perf_counter()
            async with streamable_http_client(urls[tname]) as (r, w, _):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    b = time.perf_counter()
                    res = await s.call_tool(name, args, meta=meta or None)
                    c = time.perf_counter()
            d = time.perf_counter()
            return res.content[0].text, ms(a, b), ms(c, d)

        async def challenge(tname):
            txt, su, cl_ = await rpc(tname, "challenge", {})
            c = json.loads(txt)
            return c["nonce"], c["t"], su, cl_

        async def send(tname, args, meta):
            txt, su, cl_ = await rpc(tname, tname, args, meta)
            return json.loads(txt), su, cl_

        for i in range(WARMUP + N_CALLS):
            tname = TOOLS[i % 3]; args = gen_args(tname, i); call = call_json(tname, args)
            t0 = time.perf_counter()
            nonce, t, su1, cl1 = (await challenge(tname)) if mode != "none" else (None, None, 0.0, 0.0)
            t1 = time.perf_counter()
            meta = cl.authorize(tool_ids[tname], tname, args, call, nonce, t)   # t = the tool's time from its challenge
            t2 = time.perf_counter()
            out, su2, cl2 = await send(tname, args, meta)
            t3 = time.perf_counter()
            if not out["ok"]: raise RuntimeError(f"{mode}/{transport}: honest call {i} rejected: {out['why']}")
            if i >= WARMUP:
                rows.append({"tool": tname, "challenge_rtt_ms": ms(t0, t1), "prep_ms": ms(t1, t2), "call_rtt_ms": ms(t2, t3),
                             "verify_ms": out["verify_ms"], "total_ms": ms(t0, t3),
                             "session_setup_ms": su1 + su2, "session_close_ms": cl1 + cl2,
                             "auth_bytes": len(jcs(meta).encode()) if meta else 0})
            last = (tname, args, meta)

        # ---------------- negative controls
        def res(r, **kw): return {"accepted": r[0]["ok"], "why": r[0]["why"], **kw}
        tname, args, meta = last
        other = TOOLS[(TOOLS.index(tname) + 1) % 3]
        oargs = gen_args(other, 10**6)
        controls["replay_same_tool"] = res(await send(tname, args, meta))
        controls["replay_other_tool"] = res(await send(other, oargs, meta))
        # replay the old authorisation after fetching a fresh challenge and rewriting the plain nonce (and t) fields
        if mode != "none":
            n2, t2_, _, _ = await challenge(tname); m2 = dict(meta); m2["nonce"] = n2
            if "t" in m2: m2["t"] = t2_
            controls["replay_same_tool_fresh_nonce"] = res(await send(tname, args, m2))
            n3, t3_, _, _ = await challenge(other); m3 = dict(meta); m3["nonce"] = n3
            if "t" in m3: m3["t"] = t3_
            controls["replay_other_tool_fresh_nonce"] = res(await send(other, oargs, m3))
        # call tampering: an on-path attacker intercepts a fresh (unused) authorisation and changes the amount
        tname = TOOLS[0]; i = 10**6 + 1; args = gen_args(tname, i); call = call_json(tname, args)
        nonce, t, _, _ = (await challenge(tname)) if mode != "none" else (None, None, 0, 0)
        meta = cl.authorize(tool_ids[tname], tname, args, call, nonce, t)
        bad = dict(args, amt=args["amt"] + 1)
        controls["tampered_call_fresh_auth"] = res(await send(tname, bad, cl.tamper(meta, call_json(tname, bad))))
        # call tampering on the currency only (same amount, other currency)
        i = 10**6 + 3; args = gen_args(tname, i); call = call_json(tname, args)
        nonce, t, _, _ = (await challenge(tname)) if mode != "none" else (None, None, 0, 0)
        meta = cl.authorize(tool_ids[tname], tname, args, call, nonce, t)
        bad = dict(args, cur="USD")
        controls["tampered_currency_fresh_auth"] = res(await send(tname, bad, cl.tamper(meta, call_json(tname, bad))))
        # revocation: authorisation prepared before agent1's delegation is revoked, sent after the status push
        i = 10**6 + 2; args = gen_args(tname, i); call = call_json(tname, args)
        nonce, t, _, _ = (await challenge(tname)) if mode != "none" else (None, None, 0, 0)
        meta = cl.authorize(tool_ids[tname], tname, args, call, nonce, t)
        payload = cl.revoke_payload()
        adm, _, _ = await rpc(tname, "admin_update", {"payload": payload})
        controls["after_revocation_of_agent1"] = res(await send(tname, args, meta), admin=adm, push_bytes=len(payload))
        if mode in ("mm", "mm_esc"):
            # the v2.1 wallet must refuse to present with the revoked sub-mandate (stale witnesses)
            nonce, t, _, _ = await challenge(tname)
            try:
                cl.authorize(tool_ids[tname], tname, args, call, nonce, t)
                controls["wallet_presents_after_revocation"] = {"accepted": True, "why": "wallet produced a presentation"}
            except ValueError as e:
                controls["wallet_presents_after_revocation"] = {"accepted": False, "why": f"wallet refused: {e}",
                                                                "stale_agent1": cl.auth.is_stale(cl.i1), "stale_agent2": cl.auth.is_stale(cl.i2)}

    for p in procs: p.terminate()
    for p in procs:
        try: p.wait(5)
        except Exception: p.kill()
    for lf in logs: lf.close()
    summ = {k: summarize(rows, k) for k in METRICS}
    return {"mode": mode, "transport": transport, "delegation_issuance": deleg_cost, "summary": summ,
            "controls": controls, "calls": rows}


MODES = ["none", "jwt_chain", "biscuit", "macaroon", "batch_tokens", "blind_tokens", "blind_tokens_bearer", "mm", "mm_esc"]
TRANSPORTS = ["stdio", "http", "http_delay10", "http_stateless"]
STATELESS_MODES = ["none", "jwt_chain", "batch_tokens", "blind_tokens", "mm"]
TRANSPORT_DESC = {
    "stdio": "MCP stdio, one subprocess per tool server, one long-lived ClientSession per tool",
    "http": "MCP streamable HTTP over 127.0.0.1, one FastMCP server process per tool (distinct ports), one long-lived "
            "ClientSession (one Mcp-Session-Id, keep-alive connection) per tool",
    "http_delay10": "as http, through a per-server TCP relay process adding 10 ms one-way delay to every forwarded chunk "
                    "in each direction (RTT +20 ms per HTTP exchange)",
    "http_stateless": "as http, but a fresh httpx client (new TCP connection), a fresh ClientSession (initialize, new "
                      "Mcp-Session-Id) and a session close for EVERY challenge and EVERY call (4 HTTP exchanges + "
                      "connection setup per rpc); clientInfo is the SDK default, identical for all clients",
}

def configs(modes, transports):
    out = []
    for tr in transports:
        for m in modes:
            if tr == "http_stateless" and m not in STATELESS_MODES: continue
            out.append((tr, m))
    return out

Y, N = "yes", "no"
PROPERTIES = {
    "none": {k: N for k in ["signature_chain", "attenuation", "per_call_binding", "replay", "expiry", "revocation_status",
                            "rate_limit", "unlinkable_across_tools", "unlinkable_vs_issuer", "accountability_escrow"]}
            | {"issuer_learns": "no issuer", "notes": "No authorisation; no challenge fetched."},
    "jwt_chain": {"signature_chain": "yes: issuer-signed root JWT + agent1-signed delegation JWT, cnf-key linkage and prev-hash",
                  "attenuation": "yes: tool checks scope subset, budget and exp monotone along the chain",
                  "per_call_binding": "yes: PoP JWT by the leaf cnf key over SHA-256(JCS call incl. currency), aud=tool identity, tool nonce, tool time",
                  "replay": "yes: tool nonce single-use + seen-set of PoP hashes",
                  "expiry": "yes: exp of every JWT (pyjwt) and t <= leaf exp",
                  "revocation_status": "yes (added): in-memory status list of mandate jti pushed by the issuer",
                  "rate_limit": "no (not implemented; feasible because calls are linkable)",
                  "unlinkable_across_tools": "no: identical chain shown to every tool",
                  "unlinkable_vs_issuer": "no (only if tools share logs with the issuer; see issuer_learns)",
                  "accountability_escrow": "in the clear (tool learns principal and agents)",
                  "issuer_learns": "Directly: only the root it signs (principal, agent1's key, root scope/budget/exp, jti, time). "
                                   "It does NOT see the agent1->agent2 delegation (signed offline by agent1) nor any call. "
                                   "But every tool receives the whole chain in the clear (principal, both agents' keys, jtis), "
                                   "so any tool that shares its logs with the issuer (or with other tools) links every call "
                                   "to the principal and both agents."},
    "biscuit": {"signature_chain": "yes: authority block (issuer root key) + 2 attenuation blocks + per-call block (Ed25519 chain)",
                "attenuation": "yes: every block's checks must hold (class, amount, time)",
                "per_call_binding": "partial: last block binds call hash, tool identity and nonce; bearer token, no PoP: whoever "
                                    "holds the pre-call token can append a block for any call",
                "replay": "yes: tool nonce single-use + seen-set",
                "expiry": "yes: time checks against tool time",
                "revocation_status": "yes (added): revocation_ids of the token checked against a pushed list",
                "rate_limit": "no", "unlinkable_across_tools": "no: same token prefix/revocation ids everywhere",
                "unlinkable_vs_issuer": "no (with tool collusion)", "accountability_escrow": "in the clear (delegate facts)",
                "issuer_learns": "Directly: the authority block it mints (principal, rights, bounds) and when. Attenuation and "
                                 "per-call blocks are appended offline. Tools see all blocks and revocation ids in the clear, so "
                                 "issuer + any tool links every call to the root token and the delegate names."},
    "macaroon": {"signature_chain": "HMAC chain only; the tool must hold the issuer's root HMAC key (shared secret, it can mint mandates)",
                 "attenuation": "yes: both delegation caveats checked (class, amount, exp)",
                 "per_call_binding": "partial: caveats on call hash, tool identity, nonce; bearer, no PoP",
                 "replay": "yes: tool nonce single-use + seen-set", "expiry": "yes: exp caveats vs tool time",
                 "revocation_status": "no", "rate_limit": "no", "unlinkable_across_tools": "no: same identifier/signature chain",
                 "unlinkable_vs_issuer": "no", "accountability_escrow": "in the clear (caveats)",
                 "issuer_learns": "Directly: the root identifier and principal it mints, and when; caveats are added offline. "
                                  "Every tool holds the root key (it is an issuer) and sees the identifier and all caveats, so "
                                  "any tool alone links all calls of the mandate."},
    "batch_tokens": {"signature_chain": "at issuance only: issuer verifies the JWT chain in the clear; tool checks one issuer Ed25519 signature",
                     "attenuation": "at issuance only (class set and budget tier copied from the chain leaf); tool checks class and amount <= tier",
                     "per_call_binding": "yes: PoP by the per-token cnf key over SHA-256(JCS call), tool identity, tool nonce, tool time",
                     "replay": "yes: tool nonce single-use + seen-set of token ids (per tool; class metadata pins a token to one tool here)",
                     "expiry": "epoch granularity only", "revocation_status": "yes (added): status list of token ids (issuer pushes all ids of the revoked delegation)",
                     "rate_limit": "issuer-side only (batch size per epoch); tools cannot enforce per-agent limits",
                     "unlinkable_across_tools": "yes (fresh token and key per call) unless tools collude with the issuer",
                     "unlinkable_vs_issuer": "no: issuer saw every token id and cnf key with the agent identity",
                     "accountability_escrow": "via issuer log (token id -> agent), not threshold",
                     "issuer_learns": "At every issuance: the full delegation chain in the clear (principal, agent1, agent2, "
                                      "scopes, budgets, expiries), the request time, the number of tokens per class and epoch, "
                                      "and every token id and cnf public key. Not the calls themselves; but any token a tool "
                                      "reports back is linked by the issuer to the agent and principal (no unlinkability "
                                      "against issuer + tool collusion)."},
    "blind_tokens": {"signature_chain": "at issuance only: issuer verifies the JWT chain in the clear; tool checks one RSA-PSS signature",
                     "attenuation": "at issuance only via key choice (one key per class/tier/epoch); tool checks class and amount <= tier",
                     "per_call_binding": "yes (PoP, added in v2.1): the blind-signed message commits to SHA-256 of a fresh per-token "
                                         "Ed25519 key; at redemption the agent reveals the key and signs (SHA-256(JCS call), tool "
                                         "identity, tool nonce, tool time); an intercepted unused token cannot be attached to another call",
                     "replay": "yes: tool nonce single-use + seen-set of token randoms (per tool)",
                     "expiry": "epoch granularity (key rotation)", "revocation_status": "no (issued tokens valid until epoch end)",
                     "rate_limit": "issuer-side only (batch size per epoch)",
                     "unlinkable_across_tools": "yes",
                     "unlinkable_vs_issuer": "yes up to public metadata (blind issuance; the PoP key is inside the blinded message)",
                     "accountability_escrow": "no",
                     "issuer_learns": "At every issuance: the full delegation chain in the clear (principal, agents, scope, budget, "
                                      "exp), the request time, and the number of tokens per class/tier/epoch (public metadata, via "
                                      "the key choice). Not the token messages, token ids or PoP keys (blinded), and not the calls. "
                                      "With tool collusion, a redeemed token links back only through its public metadata and "
                                      "timing, i.e. within the set of tokens issued under the same key in that epoch; small "
                                      "anonymity sets or distinctive batch sizes/timing de-anonymise."},
    "mm": {"signature_chain": "yes, hidden: ZK proof of an issuer BBS+ signature on the sub-agent mandate; parent proofs checked by the issuer at each delegation",
           "attenuation": "enforced by the issuer at delegation (ZK range proofs on the hidden attributes); tool checks class in scope, amt <= budget in ZK",
           "per_call_binding": "yes: proof bound to (tool identity, JCS call incl. currency, class, amt, cur, epoch, tool time, tool nonce)",
           "replay": "yes: strict tool (v2.1): own single-use nonce, epoch == tool epoch, |t - now| <= 300 s, per-tool per-epoch pseudonym seen-set",
           "expiry": "yes: t <= exp proven in ZK with the tool's time",
           "revocation_status": "yes: accumulator non-membership of the mandate id and its ancestors (public params update, grace = 0); "
                                "the v2.1 wallet also refuses to present with a revoked/stale mandate",
           "rate_limit": "yes: per tool per epoch via Dodis-Yampolskiy pseudonyms with a hidden counter in the mandate's interval; "
                         "children get disjoint intervals carved from the parent (subtree-wide cap per root)",
           "unlinkable_across_tools": "yes", "unlinkable_vs_issuer": "yes (for calls); see issuer_learns", "accountability_escrow": "no",
           "issuer_learns": "At root issuance: the principal's registered label (uid binding), the root's attributes (classes, "
                            "cap, counter interval, expiry, given in the clear to the issuer), the root id it chooses, and the time. "
                            "At each delegation (src/lib.rs deleg_issue): that a delegation happened in this epoch and when, the "
                            "fresh id it assigns, and a delegation pseudonym (DY PRF of the subtree secret and a hidden counter); "
                            "the parent, its root and the child's attributes stay hidden (committed, attenuation proven in ZK). "
                            "None of the calls. With tool collusion, presentations show only per-tool per-epoch pseudonyms and the "
                            "accumulator value, so calls do not link to root or mandate ids except by timing. When it revokes, the "
                            "issuer knows the revoked id (it assigned it) but not which calls it made."},
}
PROPERTIES["mm_esc"] = {**PROPERTIES["mm"], **{"notes": "as mm, plus verifiable threshold escrow of the principal identity and mandate id (tool requires the escrow ciphertext)",
               "accountability_escrow": "yes: 2-of-3 threshold escrow (g^u, g^id), verified by the tool",
               "issuer_learns": PROPERTIES["mm"]["issuer_learns"] + " Additionally, 2 of the 3 escrow members together can open "
                                "g^u and g^id of any escrowed presentation a tool hands them (accountability by design)."}}
PROPERTIES["blind_tokens_bearer"] = {**PROPERTIES["blind_tokens"], **{
    "per_call_binding": "weak (e2v2 variant, kept for comparison): bearer token next to a plain call_hash field; tool nonce prevents "
                        "re-use after redemption but an on-path attacker holding an unused token can attach it to any call of that "
                        "class (tampered_call control)",
    "unlinkable_vs_issuer": "yes up to public metadata (blind issuance)"}}

NOT_IMPLEMENTED = {
    "ARC (Anonymous Rate-limited Credentials, IETF privacypass draft)": "not implemented, not measured",
    "ACT / anonymous counting tokens": "not implemented, not measured",
}


# ======================================================================= provenance, load, single run
def uptime():
    try: return subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
    except Exception as e: return str(e)

def git_head():
    try:
        return subprocess.run(["git", "-C", os.path.join(HERE, "..", ".."), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception as e: return str(e)

def git_dirty_code():
    try:
        return subprocess.run(["git", "-C", os.path.join(HERE, "..", ".."), "status", "--porcelain", "--", "code"],
                              capture_output=True, text=True).stdout.strip().splitlines()
    except Exception as e: return [str(e)]

def file_sha(path):
    try: return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception as e: return str(e)

def wait_quiet():
    """Wait (up to LOAD_WAIT_S) until the 1-min load average is <= LOAD_MAX. Returns a log of samples."""
    t0 = time.time(); samples = []
    while True:
        l1 = os.getloadavg()[0]
        samples.append({"t_s": round(time.time() - t0, 1), "load1": round(l1, 2), "uptime": uptime()})
        if l1 <= LOAD_MAX: return {"quiet": True, "waited_s": round(time.time() - t0, 1), "samples": samples}
        if time.time() - t0 >= LOAD_WAIT_S:
            return {"quiet": False, "waited_s": round(time.time() - t0, 1), "samples": samples}
        print(f"load1 {l1:.2f} > {LOAD_MAX}: waiting", file=sys.stderr, flush=True)
        time.sleep(30)

def main_run(run_idx, out, modes, transports):
    import importlib.metadata as md, platform, mmpy
    global SEED
    SEED = SEED_BASE + 1000 * run_idx
    os.environ["E2_SEED"] = str(SEED)
    wq = wait_quiet()
    res = {"run_idx": run_idx, "seed": SEED, "n_calls": N_CALLS, "warmup": WARMUP,
           "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"), "load_wait": wq,
           "uptime_start": uptime(), "loadavg_start": os.getloadavg(), "git_head": git_head(),
           "git_status_code": git_dirty_code(), "harness_sha256": file_sha(__file__),
           "mmpy_so_sha256": file_sha(os.path.join(os.path.dirname(mmpy.__file__), [f for f in os.listdir(os.path.dirname(mmpy.__file__)) if f.endswith(".so")][0])),
           "mcp_sdk": md.version("mcp"), "python": platform.python_version(), "platform": platform.platform(),
           "machine": platform.machine(), "pid": os.getpid(), "configs": []}
    tmpdir = tempfile.mkdtemp(prefix=f"e2v21_r{run_idx}_")
    rsa_keys = {}
    t0 = time.perf_counter()
    for variant, m in (("pop", "blind_tokens"), ("bearer", "blind_tokens_bearer")):
        if m in modes: rsa_keys[m] = {c: rsa_keygen_det(blind_kid(variant, c, BUD2, EPOCH)) for c in SCOPE2}
    res["rsa_keygen_ms"] = ms(t0, time.perf_counter())
    for cfg_idx, (transport, mode) in enumerate(configs(modes, transports)):
        r = asyncio.run(run_one(mode, transport, cfg_idx, run_idx, tmpdir, rsa_keys.get(mode)))
        r["loadavg_after"] = os.getloadavg()
        s = r["summary"]
        print(f"run{run_idx} {transport:14s} {mode:19s} total med {s['total_ms']['median']:8.2f} p95 {s['total_ms']['p95']:8.2f} "
              f"chal {s['challenge_rtt_ms']['median']:6.2f} prep {s['prep_ms']['median']:7.2f} verify {s['verify_ms']['median']:7.2f} "
              f"sess {s['session_setup_ms']['median']:6.2f} bytes {s['auth_bytes']['median']:7.0f} load {r['loadavg_after'][0]:.2f} | " +
              " ".join(f"{k}={'ACC' if v['accepted'] else 'rej'}" for k, v in r["controls"].items()), file=sys.stderr, flush=True)
        res["configs"].append(r)
        json.dump(res, open(out, "w"))
    res["uptime_end"] = uptime(); res["loadavg_end"] = os.getloadavg()
    json.dump(res, open(out, "w"))


# ======================================================================= aggregation over runs
def boot_ci(xs, seed, B=10000):
    """Percentile bootstrap 95% CI of the median, resampling the per-run values with replacement."""
    rng = random.Random(seed)
    meds = sorted(statistics.median(rng.choices(xs, k=len(xs))) for _ in range(B))
    return [meds[int(0.025 * B)], meds[int(0.975 * B) - 1]]

def over_runs(xs, seed):
    return {"median": statistics.median(xs), "min": min(xs), "max": max(xs), "ci95_boot": boot_ci(xs, seed), "per_run": xs}

def aggregate(run_files, out, summary_path):
    import importlib.metadata as md
    runs = [json.load(open(f)) for f in run_files]
    agg = {"experiment": "E2 v2.1 -- end-to-end MCP authorisation, 3 independent runs",
           "harness": "code/e2v2/e2v21.py", "seed_base": SEED_BASE, "seeds": [r["seed"] for r in runs],
           "n_calls": runs[0]["n_calls"], "warmup": runs[0]["warmup"], "rayon_num_threads": runs[0]["rayon_num_threads"],
           "git_head": sorted({r["git_head"] for r in runs}), "git_status_code": runs[0]["git_status_code"],
           "harness_sha256": sorted({r["harness_sha256"] for r in runs}), "mmpy_so_sha256": sorted({r["mmpy_so_sha256"] for r in runs}),
           "mcp_sdk": runs[0]["mcp_sdk"], "python": runs[0]["python"], "platform": runs[0]["platform"], "machine": runs[0]["machine"],
           "load_max_threshold": LOAD_MAX,
           "runs_meta": [{"run_idx": r["run_idx"], "seed": r["seed"], "pid": r["pid"], "file": os.path.basename(f), "file_sha256": file_sha(f),
                          "load_wait": {"quiet": r["load_wait"]["quiet"], "waited_s": r["load_wait"]["waited_s"],
                                        "first": r["load_wait"]["samples"][0], "last": r["load_wait"]["samples"][-1]},
                          "uptime_start": r["uptime_start"], "uptime_end": r.get("uptime_end"),
                          "loadavg_start": r["loadavg_start"], "loadavg_end": r.get("loadavg_end"),
                          "rsa_keygen_ms": r.get("rsa_keygen_ms")} for f, r in zip(run_files, runs)],
           "transports": TRANSPORT_DESC, "tools": TOOLS, "tool_classes": CLS, "currency": CUR,
           "delegation": {"root": {"scope": [0, 1, 2], "budget_cents": BUD_ROOT, "exp": EXP_ROOT, "k": K_ROOT},
                          "agent1": {"scope": SCOPE1, "budget_cents": BUD1, "exp": EXP1, "k_carved": K1},
                          "agent2": {"scope": SCOPE2, "budget_cents": BUD2, "exp": EXP2, "k_carved": K2}},
           "mm_tool": {"strict": True, "epoch": EPOCH, "tol_s": MM_TOL, "debug_errors": MM_DEBUG, "grace": 0},
           "properties": PROPERTIES, "not_implemented": NOT_IMPLEMENTED,
           "stats_method": f"per (mode, transport): each run gives the median (and p95) over its {runs[0]['n_calls']} measured calls; we report "
                           "the median of the 3 per-run values, their range [min, max], and a percentile bootstrap 95% CI of "
                           "the median obtained by resampling the 3 per-run values with replacement (10000 resamples; with 3 "
                           "runs this CI can only take values among the run values and is coarse). pooled_p95 = p95 over all "
                           f"{len(runs) * runs[0]['n_calls']} calls.",
           "results": [], "stateless_overhead": [], "delegation_issuance": [], "controls": []}
    keys = []
    for r in runs:
        for c in r["configs"]:
            k = (c["transport"], c["mode"])
            if k not in keys: keys.append(k)
    sidx = 0
    for (tr, m) in keys:
        cs = [c for r in runs for c in r["configs"] if (c["transport"], c["mode"]) == (tr, m)]
        e = {"transport": tr, "mode": m, "n_runs": len(cs)}
        for met in METRICS:
            sidx += 1
            e[met] = {"median": over_runs([c["summary"][met]["median"] for c in cs], sidx),
                      "p95": over_runs([c["summary"][met]["p95"] for c in cs], sidx + 100000)}
        e["total_ms"]["pooled_p95"] = pct([x["total_ms"] for c in cs for x in c["calls"]], 95)
        e["total_ms"]["pooled_median"] = statistics.median([x["total_ms"] for c in cs for x in c["calls"]])
        agg["results"].append(e)
        # controls: consistent across runs?
        ctl = {}
        for c in cs:
            for name, v in c["controls"].items():
                ctl.setdefault(name, []).append(v["accepted"])
        agg["controls"].append({"transport": tr, "mode": m,
                                "outcome": {k: ("ACCEPTED" if all(v) else "rejected" if not any(v) else f"MIXED {v}") for k, v in ctl.items()},
                                "why_run1": {k: v.get("why", "") for k, v in cs[0]["controls"].items()}})
    # stateless overhead vs http (same mode, same run)
    for m in STATELESS_MODES:
        diffs, ratios, setup = [], [], []
        for r in runs:
            a = [c for c in r["configs"] if c["mode"] == m and c["transport"] == "http_stateless"]
            b = [c for c in r["configs"] if c["mode"] == m and c["transport"] == "http"]
            if a and b:
                diffs.append(a[0]["summary"]["total_ms"]["median"] - b[0]["summary"]["total_ms"]["median"])
                ratios.append(a[0]["summary"]["total_ms"]["median"] / b[0]["summary"]["total_ms"]["median"])
                setup.append(a[0]["summary"]["session_setup_ms"]["median"] + a[0]["summary"]["session_close_ms"]["median"])
        if diffs:
            agg["stateless_overhead"].append({"mode": m, "added_total_ms": over_runs(diffs, 7000 + len(agg["stateless_overhead"])),
                                              "ratio_total": over_runs(ratios, 8000 + len(agg["stateless_overhead"])),
                                              "session_setup_plus_close_ms": over_runs(setup, 9000 + len(agg["stateless_overhead"]))})
    # delegation / issuance: pooled over all (transport, run) configs of a mode
    for m in MODES:
        cs = [c for r in runs for c in r["configs"] if c["mode"] == m]
        if not cs: continue
        d0 = cs[0]["delegation_issuance"]
        e = {"mode": m, "n_configs": len(cs)}
        chains = [x for c in cs for x in c["delegation_issuance"].get("two_hop_chains_ms", [c["delegation_issuance"]["two_hop_total_ms"]])]
        e["two_hop_ms_all_chains"] = {"median": statistics.median(chains), "min": min(chains), "max": max(chains), "n_chains": len(chains)}
        per_run = [statistics.median([x for c in r["configs"] if c["mode"] == m
                                      for x in c["delegation_issuance"].get("two_hop_chains_ms", [c["delegation_issuance"]["two_hop_total_ms"]])])
                   for r in runs if any(c["mode"] == m for c in r["configs"])]
        e["two_hop_ms_per_run_median"] = over_runs(per_run, 5000 + MODES.index(m))
        for k, v in d0.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("two_hop_total_ms", "reps", "batch_size"):
                xs = [c["delegation_issuance"][k] for c in cs if k in c["delegation_issuance"]]
                e[k] = {"median": statistics.median(xs), "min": min(xs), "max": max(xs)}
            elif k in ("reps", "batch_size", "variant", "intervals"):
                e[k] = v
        agg["delegation_issuance"].append(e)
    agg["run_summaries"] = [{"run_idx": r["run_idx"], "configs": [{"transport": c["transport"], "mode": c["mode"],
                             "summary": c["summary"], "delegation_issuance": c["delegation_issuance"], "controls": c["controls"],
                             "loadavg_after": c.get("loadavg_after")} for c in r["configs"]]} for r in runs]
    json.dump(agg, open(out, "w"), indent=1)
    write_summary(agg, summary_path)

def f2(x): return f"{x:.2f}"
def rng_s(o, f=f2): return f"{f(o['median'])} [{f(o['min'])}, {f(o['max'])}]"

def write_summary(a, path):
    R = {(e["transport"], e["mode"]): e for e in a["results"]}
    L = ["# E2 v2.1 -- end-to-end MCP authorisation, 3 independent runs (summary)", "",
         f"Harness `code/e2v2/e2v21.py` (sha256 {', '.join(h[:16] for h in a['harness_sha256'])}...); git HEAD "
         f"{', '.join(a['git_head'])} (the harness and results are not committed; `git status code/` at run time: "
         f"{len(a['git_status_code'])} entries); mmpy 2.1 .so sha256 {', '.join(h[:16] for h in a['mmpy_so_sha256'])}...; "
         f"MCP SDK {a['mcp_sdk']}; Python {a['python']}; {a['platform']}; RAYON_NUM_THREADS={a['rayon_num_threads']}.", "",
         f"Per (mode, transport, run): {a['n_calls']} measured calls after {a['warmup']} warm-up calls, round-robin over "
         f"{', '.join(a['tools'])}; canonical call = RFC 8785 JCS of {{name, arguments}} with `cur` = \"{a['currency']}\" in the arguments. "
         f"Three independent runs, each a fresh `python e2v21.py run k` process (fresh servers), seeds {a['seeds']}.", "",
         "## Machine load per run", "",
         f"Each run starts only when the 1-minute load average is <= {a['load_max_threshold']} (polled every 30 s, up to 20 min).", "",
         "| run | seed | quiet at start | waited s | uptime at start | uptime at end |", "|---|---|---|---:|---|---|"]
    for r in a["runs_meta"]:
        L.append(f"| {r['run_idx']} | {r['seed']} | {'yes' if r['load_wait']['quiet'] else 'NO (timeout)'} | {r['load_wait']['waited_s']} | "
                 f"`{r['uptime_start']}` | `{r['uptime_end']}` |")
    L += ["", "## What changed vs e2v2", "",
          "- MM uses mmpy 2.1: `Authority(..., grace=0)`; `delegate(parent, classes, budget, k, exp, epoch)` carves disjoint counter "
          "intervals (root [0,100000), agent1 gets 10000 counters, agent2 5000 of agent1's); the wallet refuses revoked/stale mandates.",
          "- MM tools run in STRICT mode: the tool's `challenge` MCP tool returns `Verifier.challenge()` (single-use nonce held by "
          "the Rust tool) and the tool's own time; the agent proves with that tool time; the tool checks epoch, |t - now| <= 300 s, "
          "nonce issued and unused; errors are the uniform string `rejected`.",
          "- Currency `cur` is part of every canonical call (all modes) and passed to MM `present`/`verify`; new control `tampered currency`.",
          "- `blind_tokens` is now PoP-bound (RFC 9474 token message commits to SHA-256 of a fresh Ed25519 key; redemption reveals "
          "the key and signs call hash, tool identity, tool nonce, tool time). The e2v2 bearer variant is kept as `blind_tokens_bearer`.",
          "- New transport `http_stateless`: new TCP connection + new MCP session (initialize) + session close for every challenge and every call.",
          "- Property table gains `issuer_learns`.",
          "- 3 independent runs with different seeds and fresh processes; per-mode medians with range and bootstrap CI over runs; p95.",
          "- MM delegation cost: median of 5 two-hop chains per (mode, transport, run) instead of 3.",
          "- Ports / server names differ (e2v21-*); tool identities are `stdio://e2v21-<tool>|<tool>` or `http://127.0.0.1:<port>|<tool>`.",
          "", "## Statistics", "", a["stats_method"], "",
          "Cells: median over runs of the per-run medians, then [min, max] over the 3 runs. `CI95` = bootstrap CI of the "
          "median over runs. `p95` = median over runs of per-run p95 [range]. ms unless stated.", ""]
    for tr in a["transports"]:
        rows = [e for e in a["results"] if e["transport"] == tr]
        if not rows: continue
        L += [f"## Transport: {tr}", "", f"_{a['transports'][tr]}_", "",
              "| mode | total median [range] | CI95 | total p95 [range] | pooled p95 | challenge RTT | prep | call RTT | verify (in tool) | session setup+close | bytes |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for e in rows:
            t = e["total_ms"]["median"]
            ss = e["session_setup_ms"]["median"]["median"] + e["session_close_ms"]["median"]["median"]
            L.append(f"| {e['mode']} | {rng_s(t)} | [{f2(t['ci95_boot'][0])}, {f2(t['ci95_boot'][1])}] | {rng_s(e['total_ms']['p95'])} | "
                     f"{f2(e['total_ms']['pooled_p95'])} | {f2(e['challenge_rtt_ms']['median']['median'])} | {f2(e['prep_ms']['median']['median'])} | "
                     f"{f2(e['call_rtt_ms']['median']['median'])} | {f2(e['verify_ms']['median']['median'])} | {f2(ss)} | "
                     f"{e['auth_bytes']['median']['median']:.0f} |")
        L.append("")
    if a["stateless_overhead"]:
        L += ["## Cost of `http_stateless` vs `http` (same mode, same run)", "",
              "Added = median total (stateless) - median total (http), per run; then median [range] and bootstrap CI over the 3 runs.", "",
              "| mode | added ms median [range] | CI95 | ratio stateless/http | session setup+close ms (per call, both rpcs) |",
              "|---|---:|---:|---:|---:|"]
        for e in a["stateless_overhead"]:
            d = e["added_total_ms"]
            L.append(f"| {e['mode']} | {rng_s(d)} | [{f2(d['ci95_boot'][0])}, {f2(d['ci95_boot'][1])}] | {rng_s(e['ratio_total'])} | "
                     f"{rng_s(e['session_setup_plus_close_ms'])} |")
        L.append("")
    L += ["## Delegation / issuance cost before calls (two hops)", "",
          "`all chains` = median [min, max] over every timed two-hop chain of every (transport, run); `per run` = median of per-run medians [range]. "
          "Issuance details: median over all (transport, run) configs.", "",
          "| mode | all chains ms | per run ms | details (median) |", "|---|---:|---:|---|"]
    for e in a["delegation_issuance"]:
        det = ", ".join(f"{k}={v['median']:.3f}" if isinstance(v, dict) and "median" in v else f"{k}={v}"
                        for k, v in e.items() if k not in ("mode", "n_configs", "two_hop_ms_all_chains", "two_hop_ms_per_run_median"))
        ac = e["two_hop_ms_all_chains"]
        L.append(f"| {e['mode']} | {ac['median']:.3f} [{ac['min']:.3f}, {ac['max']:.3f}] (n={ac['n_chains']}) | "
                 f"{rng_s(e['two_hop_ms_per_run_median'], lambda x: f'{x:.3f}')} | {det} |")
    cnames = ["replay_same_tool", "replay_other_tool", "replay_same_tool_fresh_nonce", "replay_other_tool_fresh_nonce",
              "tampered_call_fresh_auth", "tampered_currency_fresh_auth", "after_revocation_of_agent1", "wallet_presents_after_revocation"]
    L += ["", "## Negative controls (accepted? identical in all 3 runs unless marked MIXED)", "",
          "Expected: everything rejected except `none`; `macaroon`, `blind_tokens` and `blind_tokens_bearer` have no revocation "
          "mechanism (ACCEPTED after revocation is the honest, expected outcome); `blind_tokens_bearer` only has bearer-level call "
          "binding (tampered call ACCEPTED expected). `tampered call` = on-path attacker takes a fresh, unused authorisation and "
          "changes `amt` (resp. `cur`), rewriting only unsigned fields. `after revocation` = authorisation prepared, then agent1's "
          "delegation revoked and the status list / new accumulator pushed to the tool, then sent. `wallet after revocation` (MM only) "
          "= the agent tries to produce a new presentation with the revoked sub-mandate.", "",
          "| transport | mode | replay same | replay other | replay same + fresh nonce | replay other + fresh nonce | tampered amt | tampered cur | after revocation | wallet after revocation |",
          "|---|---|" + "---|" * 8]
    for c in a["controls"]:
        L.append(f"| {c['transport']} | {c['mode']} | " + " | ".join(c["outcome"].get(k, "n/a") for k in cnames) + " |")
    L += ["", "## What each tool verifies, and what the issuer learns", "", "| mode | property | value |", "|---|---|---|"]
    for m, props in a["properties"].items():
        for k, v in props.items(): L.append(f"| {m} | {k} | {v} |")
    L += ["", "## Not implemented", "",
          "- ARC (Anonymous Rate-limited Credentials) and anonymous counting tokens (ACT) are NOT implemented in this harness and "
          "were not measured; no numbers in this file refer to them. They are the closest deployed-track designs to MM's "
          "per-tool rate limiting; comparing against them remains future work.", "",
          "## Limitations / deviations", "",
          "- Blind tokens: RFC 9474 RSABSSA-SHA384-PSS-Randomized (2048-bit), client and issuer operations in pure Python "
          "(issuer BlindSign uses CRT big-int pow, no GMP), so issuance is pessimistic; tools verify RSA-PSS with OpenSSL. "
          "Not checked against the RFC test vectors (every finalized token is checked by OpenSSL PSS verification). Public "
          "metadata bound by one issuer key per (variant, class, tier, epoch); RSA keys derived deterministically from the run seed.",
          "- PoP blind tokens follow the standard key-binding pattern (token commits to a key hash; the key signs the call); the "
          "per-token Ed25519 key is generated at issuance time (counted in the agent's issuance cost) and revealed once, at redemption.",
          "- Status lists (jwt_chain, batch_tokens) and biscuit revocation ids are pushed through an unauthenticated experiment-only "
          "`admin_update` tool; MM public parameters (new accumulator) are pushed the same way.",
          "- Macaroon tools hold the issuer's root HMAC key (they could mint mandates).",
          "- Replay seen-sets and nonce stores are per tool, in memory; token double-spend across tools is prevented only because "
          "class metadata maps 1:1 to tools. MM nonces live in the Rust strict tool (no TTL; the 300 s time tolerance bounds use).",
          "- MM strict-mode rejections carry the uniform reason `rejected` (debug off), so the controls table shows only accept/reject for MM.",
          "- http_stateless removes the MCP session id and the TCP connection as linking handles; it does not hide the client's "
          "IP address (all 127.0.0.1 here), TLS session resumption (no TLS here) or timing. The default clientInfo is the same for all clients.",
          "- The 10 ms delay is a userspace TCP relay (per forwarded chunk, each direction), not netem; TCP handshakes are not delayed.",
          "- `none` fetches no challenge. Other-mode delegation timing: median of 50 builds; MM: 5 two-hop chains per (transport, run).",
          "- 3 runs give a coarse between-run CI; all runs on one Mac (Apple Silicon, see platform), other user processes not stopped "
          "(load averages above).",
          ]
    open(path, "w").write("\n".join(L) + "\n")


def main_all(resdir):
    rundir = os.path.join(resdir, "e2v21_runs"); os.makedirs(rundir, exist_ok=True)
    files = []
    for k in (1, 2, 3):
        f = os.path.join(rundir, f"run{k}.json")
        subprocess.run([PY, __file__, "run", str(k), f], check=True, env={**os.environ, "RAYON_NUM_THREADS": "1"})
        files.append(f)
    aggregate(files, os.path.join(resdir, "e2v21.json"), os.path.join(resdir, "e2v21_summary.md"))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "server":
        run_server(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6])
    elif cmd == "proxy":
        run_proxy(int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]))
    elif cmd == "run":
        main_run(int(sys.argv[2]), sys.argv[3], sys.argv[4].split(",") if len(sys.argv) > 4 else MODES,
                 sys.argv[5].split(",") if len(sys.argv) > 5 else TRANSPORTS)
    elif cmd == "aggregate":
        aggregate(sys.argv[4:], sys.argv[2], sys.argv[3])
    elif cmd == "all":
        main_all(sys.argv[2])
    else:
        raise SystemExit(__doc__)
