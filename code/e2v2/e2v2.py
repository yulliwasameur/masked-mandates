"""E2 v2 -- end-to-end MCP calls with tool-issued challenges, three transports and functionally aligned baselines.

One agent client (holding principal -> agent1 -> agent2 delegation), three MCP tool servers (airline, hotel, payment),
each exposing: its business tool, `challenge` (fresh single-use nonce + tool time, kept server side, 30 s expiry),
and `admin_update` (experiment-only channel used to push a revocation status list / new public parameters).

Transports:  stdio            -- each server is a subprocess speaking MCP over stdio;
             http             -- FastMCP streamable-http on 127.0.0.1:<port> (one port per server), client via
                                 mcp.client.streamable_http.streamable_http_client;
             http_delay10     -- as http, but the client talks to a per-server TCP relay (process `proxy`) that holds
                                 every chunk it forwards for 10 ms in each direction (one-way delay 10 ms per message,
                                 RTT +20 ms; ordering preserved, no bandwidth limit; TCP handshake not delayed because
                                 httpx keeps connections alive).
Modes: none, jwt_chain, biscuit, macaroon, batch_tokens, blind_tokens, mm, mm_esc (see PROPERTIES below).

Usage:  RAYON_NUM_THREADS=1 python e2v2.py client OUT.json [modes,comma,sep] [transports,comma,sep]
        python e2v2.py server MODE TOOL TRANSPORT PORT PUBFILE      (spawned by the client)
        python e2v2.py proxy LISTEN_PORT TARGET_PORT DELAY_MS        (spawned by the client)
"""
import os
os.environ["RAYON_NUM_THREADS"] = "1"  # single-core crypto for the whole run (inherited by servers)
import asyncio, base64, hashlib, json, math, secrets, socket, statistics, subprocess, sys, tempfile, time

SEED = 20261109
TOOLS = ["airline", "hotel", "payment"]
CLS = {"airline": 0, "hotel": 1, "payment": 2}
N_CALLS = int(os.environ.get("E2_CALLS", "200"))
WARMUP = int(os.environ.get("E2_WARMUP", "15"))
EPOCH = 1
NONCE_TTL = 30.0
# Two-level delegation, identical semantics in every mode: classes {0,1,2}; per-call amount cap (integer cents); expiry
EXP_ROOT, EXP1, EXP2 = 1893456000, 1861920000, 1830297600       # 2030-01-01, 2029-01-01, 2028-01-01 (unix s)
BUD_ROOT, BUD1, BUD2 = 100000, 50000, 20000                       # cents
K_ROOT, K1, K2 = 100000, 10000, 5000                              # MM per-tool per-epoch quota
SCOPE1 = SCOPE2 = [0, 1, 2]
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
    if tool == "airline": return {"dest": f"CDG-JFK-{i}", "date": "2027-01-15", "amt": amt}
    if tool == "hotel": return {"city": "Lyon", "nights": 1 + i % 5, "amt": amt}
    return {"payee": "acme-travel", "ref": f"inv-{i}", "amt": amt}


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

def blind_kid(cls, tier, epoch): return f"c{cls}-t{tier}-e{epoch}"


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
    """One per (mode, transport) run. setup() builds the two-level delegation (and token batches) and returns costs."""
    def __init__(self, mode, tmpdir, rsa_keys):
        self.mode, self.tmp, self.rsa_keys = mode, tmpdir, rsa_keys
        self.rnd = DRBG(f"client|{mode}")
        self.pub = {}

    # ---------------------------------------------------------------- setup / delegation
    def setup(self, n_tokens_per_class):
        m, cost = self.mode, {}
        if m == "none":
            cost = {"two_hop_total_ms": 0.0}
        elif m in ("jwt_chain", "batch_tokens", "blind_tokens"):
            import jwt
            self.jwt = jwt
            self.jc = JwtChain()
            reps = [self.jc.build()[1] for _ in range(50)]
            self.chain, c = self.jc.build()
            cost = {k: statistics.median([r[k] for r in reps]) for k in reps[0]}
            cost["two_hop_total_ms"] = sum(cost.values())
            cost["reps"] = 50
            self.pub["iss_pub"] = b64(ed_raw(self.jc.iss.public_key()))
            if m == "batch_tokens": cost.update(self.issue_batch(n_tokens_per_class))
            if m == "blind_tokens": cost.update(self.issue_blind(n_tokens_per_class))
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
            self.pub["macaroon_root_key_SHARED_SECRET"] = key
        elif m in ("mm", "mm_esc"):
            import mmpy
            t0 = time.perf_counter()
            self.auth = mmpy.Authority(SEED, uid=42, budget=BUD_ROOT, k=K_ROOT, exp=EXP_ROOT)
            t1 = time.perf_counter()
            reps = []
            for r in range(3):   # r = 0 is the chain used for the calls; r = 1, 2 are extra chains for timing only
                a0 = time.perf_counter()
                i1, pm1, im1 = self.auth.delegate(0, SCOPE1, BUD1, K1, EXP1, EPOCH)
                a1 = time.perf_counter()
                i2, pm2, im2 = self.auth.delegate(i1, SCOPE2, BUD2, K2, EXP2, EPOCH)
                a2 = time.perf_counter()
                if r == 0: self.i1, self.i2 = i1, i2
                reps.append({"hop1_parent_ms": pm1, "hop1_issuer_ms": im1, "hop1_wall_ms": ms(a0, a1),
                             "hop2_parent_ms": pm2, "hop2_issuer_ms": im2, "hop2_wall_ms": ms(a1, a2)})
            cost = {k: statistics.median([r[k] for r in reps]) for k in reps[0]}
            cost["two_hop_total_ms"] = cost["hop1_wall_ms"] + cost["hop2_wall_ms"]
            cost["reps"] = 3; cost["authority_setup_ms"] = ms(t0, t1)
            pp = self.auth.public_params()
            path = os.path.join(self.tmp, f"pp_{m}.bin"); open(path, "wb").write(pp)
            self.pub["mm_pp_path"] = path; self.pub["mm_pp_bytes"] = len(pp)
        self.pubfile = os.path.join(self.tmp, f"pub_{m}.json")
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
                tid = b64(secrets.token_bytes(16))
                body = jcs({"cls": c, "tier": leaf["budget"], "epoch": EPOCH, "tid": tid, "cnf": kpub}).encode()
                tokstr = b64(body) + "." + b64(self.bat_iss.sign(body))
                self.tokens[c].append((tokstr, k)); self.tok_ids_issued.append(tid)
        t3 = time.perf_counter()
        n = n_per_class * len(SCOPE2)
        return {"batch_size": n, "agent_keygen_and_request_ms": ms(t0, t1), "issuer_chain_check_ms": ms(t1, t2),
                "issuer_sign_batch_ms": ms(t2, t3), "issuance_total_ms": ms(t0, t3),
                "per_token_issuance_ms": ms(t0, t3) / n, "per_token_issuer_sign_ms": ms(t2, t3) / n,
                "per_token_agent_keygen_ms": ms(t0, t1) / n}

    def issue_blind(self, n_per_class):
        """RFC 9474 RSABSSA-SHA384-PSS-Randomized. Public metadata (class, tier, epoch) is bound by using one issuer key
        per metadata value (Privacy-Pass style key-per-metadata); the issuer chooses the key after checking the chain
        in the clear, and never sees the token message."""
        tier = BUD2
        for c in SCOPE2:
            self.pub.setdefault("rsa_pub", {})[blind_kid(c, tier, EPOCH)] = [str(self.rsa_keys[c].public_key().public_numbers().n), 65537]
        t0 = time.perf_counter()
        pend = {c: [] for c in SCOPE2}
        for c in SCOPE2:
            pub = self.rsa_keys[c].public_key(); n = pub.public_numbers().n
            for _ in range(n_per_class):
                msg = jcs({"cls": c, "tier": tier, "epoch": EPOCH, "rand": b64(self.rnd.bytes(32))}).encode()
                prefix = self.rnd.bytes(32)
                blinded, inv = rsabssa_blind(n, 65537, prefix + msg, self.rnd)
                pend[c].append((msg, prefix, blinded, inv))
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
            for (msg, prefix, _, inv), bs in zip(pend[c], bsigs[c]):
                sig = rsabssa_finalize(pub, prefix + msg, bs, inv)
                self.tokens[c].append({"kid": blind_kid(c, tier, EPOCH), "msg": msg.decode(), "prefix": b64(prefix), "sig": b64(sig)})
        t4 = time.perf_counter()
        n = n_per_class * len(SCOPE2)
        return {"batch_size": n, "agent_blind_and_request_ms": ms(t0, t1), "issuer_chain_check_ms": ms(t1, t2),
                "issuer_blind_sign_batch_ms": ms(t2, t3), "agent_finalize_batch_ms": ms(t3, t4),
                "issuance_total_ms": ms(t0, t4), "per_token_issuance_ms": ms(t0, t4) / n,
                "per_token_agent_blind_ms": ms(t0, t1) / n, "per_token_issuer_blind_sign_ms": ms(t2, t3) / n,
                "per_token_agent_finalize_ms": ms(t3, t4) / n}

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
            pop = k.sign(jcs({"call": H, "tool": tool_id, "nonce": nonce, "t": t}).encode())
            return {"nonce": nonce, "token": tokstr, "pop": b64(pop)}
        if m == "blind_tokens":
            return {"nonce": nonce, "token": self.tokens[cls].pop(0), "call_hash": H}
        if m in ("mm", "mm_esc"):
            blob = self.auth.present(self.i2, tool_id, call, cls, int(args["amt"]), EPOCH, t, nonce, m == "mm_esc")
            return {"nonce": nonce, "mm": base64.b64encode(bytes(blob)).decode()}
        raise ValueError(m)

    def tamper(self, meta, new_call):
        """What an on-path attacker can rewrite without any key: only unsigned plain fields."""
        meta = json.loads(json.dumps(meta))
        if self.mode == "blind_tokens": meta["call_hash"] = sha(new_call)
        return meta

    def revoke_payload(self):
        """Revoke agent1's delegation (hence agent2's sub-mandate); returns what the issuer pushes to tools."""
        m = self.mode
        if m == "jwt_chain": return json.dumps({"revoked_jti": ["m-root-agent1"]})
        if m == "batch_tokens": return json.dumps({"revoked_tid": self.tok_ids_issued})
        if m == "biscuit": return json.dumps({"revoked_ids": [self.tok.revocation_ids[1]]})
        if m in ("mm", "mm_esc"): return base64.b64encode(bytes(self.auth.revoke(self.i1))).decode()
        return ""   # none / macaroon / blind_tokens: no revocation mechanism in the baseline

def KeyPairPub(b, priv):
    return b.KeyPair.from_private_key(priv).public_key.to_bytes().hex()


# ======================================================================= tool side (server process)
class Checker:
    def __init__(self, mode, tool_id, tname, pub):
        self.mode, self.tool_id, self.tname, self.cls = mode, tool_id, tname, CLS[tname]
        self.nonces = {}           # nonce -> (tool time t, monotonic expiry)
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
        elif mode == "blind_tokens":
            from cryptography.hazmat.primitives.asymmetric import rsa
            self.rsa = {k: rsa.RSAPublicNumbers(int(v[1]), int(v[0])).public_key() for k, v in pub["rsa_pub"].items()}
        elif mode in ("mm", "mm_esc"):
            import mmpy
            self.v = mmpy.Verifier(open(pub["mm_pp_path"], "rb").read(), tool_id, mode == "mm_esc", SEED)

    def challenge(self):
        n = secrets.token_urlsafe(16)
        t = int(time.time())
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
            ed_pk(ub64(tk["cnf"])).verify(ub64(meta["pop"]), jcs({"call": H, "tool": self.tool_id, "nonce": nonce, "t": t}).encode())
            key = ("tid", tk["tid"])
        elif m == "blind_tokens":
            tok = meta["token"]
            md = json.loads(tok["msg"])
            if tok["kid"] != blind_kid(md["cls"], md["tier"], md["epoch"]) or tok["kid"] not in self.rsa: return False, "key/metadata"
            rsa_pss_verify(self.rsa[tok["kid"]], ub64(tok["prefix"]) + tok["msg"].encode(), ub64(tok["sig"]))
            if md["cls"] != self.cls: return False, "class"
            if amt > md["tier"]: return False, "amount above tier"
            if md["epoch"] != EPOCH: return False, "epoch"
            if meta["call_hash"] != H: return False, "call hash field"
            key = ("rand", md["rand"])
        elif m in ("mm", "mm_esc"):
            ok, why = self.v.verify(call, self.cls, amt, EPOCH, t, nonce, base64.b64decode(meta["mm"]))
            if not ok: return False, why
            key = ("nonce", nonce)
        else:
            raise ValueError(m)
        if key in self.seen: return False, "replay"
        self.seen.add(key)
        return True, ""


def run_server(mode, tname, transport, port, pubfile):
    import logging
    from mcp.server.fastmcp import FastMCP, Context
    origin = f"stdio://e2v2-{tname}" if transport == "stdio" else f"http://127.0.0.1:{port}"
    tool_id = f"{origin}|{tname}"
    pub = json.load(open(pubfile))
    chk = Checker(mode, tool_id, tname, pub)
    srv = FastMCP(f"e2v2-{tname}", host="127.0.0.1", port=port, log_level="WARNING")
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
        def airline(dest: str, date: str, amt: int, ctx: Context) -> str:
            return handle({"dest": dest, "date": date, "amt": amt}, ctx)
    elif tname == "hotel":
        @srv.tool(name="hotel")
        def hotel(city: str, nights: int, amt: int, ctx: Context) -> str:
            return handle({"city": city, "nights": nights, "amt": amt}, ctx)
    else:
        @srv.tool(name="payment")
        def payment(payee: str, ref: str, amt: int, ctx: Context) -> str:
            return handle({"payee": payee, "ref": ref, "amt": amt}, ctx)

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

def summarize(rows, key):
    xs = [r[key] for r in rows]
    return {"median": statistics.median(xs), "p95": pct(xs, 95), "mean": statistics.fmean(xs), "min": min(xs), "max": max(xs)}

async def run_one(mode, transport, run_idx, tmpdir, rsa_keys):
    from contextlib import AsyncExitStack
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client
    cl = Client(mode, tmpdir, rsa_keys)
    n_per_class = math.ceil((WARMUP + N_CALLS) / 3) + 8
    deleg_cost = cl.setup(n_per_class)
    procs, logs = [], []
    rows, controls = [], {}
    env = {**os.environ, "RAYON_NUM_THREADS": "1"}
    async with AsyncExitStack() as st:
        sess, tool_ids = {}, {}
        for k, tname in enumerate(TOOLS):
            if transport == "stdio":
                p = StdioServerParameters(command=PY, args=[__file__, "server", mode, tname, "stdio", "0", cl.pubfile], env=env)
                r, w = await st.enter_async_context(stdio_client(p))
                tool_ids[tname] = f"stdio://e2v2-{tname}|{tname}"
            else:
                port = PORT_BASE + 10 * run_idx + k
                lf = open(os.path.join(tmpdir, f"srv_{mode}_{transport}_{tname}.log"), "w"); logs.append(lf)
                procs.append(subprocess.Popen([PY, __file__, "server", mode, tname, "http", str(port), cl.pubfile], env=env, stdout=lf, stderr=lf))
                wait_port(port)
                cport = port
                if transport == "http_delay10":
                    cport = port + 1000
                    procs.append(subprocess.Popen([PY, __file__, "proxy", str(cport), str(port), "10"], env=env, stdout=lf, stderr=lf))
                    wait_port(cport)
                tool_ids[tname] = f"http://127.0.0.1:{port}|{tname}"
                r, w, _ = await st.enter_async_context(streamable_http_client(f"http://127.0.0.1:{cport}/mcp"))
            s = await st.enter_async_context(ClientSession(r, w))
            await s.initialize()
            sess[tname] = s

        async def challenge(tname):
            res = await sess[tname].call_tool("challenge", {})
            c = json.loads(res.content[0].text)
            return c["nonce"], c["t"]

        async def send(tname, args, meta):
            res = await sess[tname].call_tool(tname, args, meta=meta or None)
            return json.loads(res.content[0].text)

        last = None
        for i in range(WARMUP + N_CALLS):
            tname = TOOLS[i % 3]; args = gen_args(tname, i); call = call_json(tname, args)
            t0 = time.perf_counter()
            nonce, t = (await challenge(tname)) if mode != "none" else (None, None)
            t1 = time.perf_counter()
            meta = cl.authorize(tool_ids[tname], tname, args, call, nonce, t)
            t2 = time.perf_counter()
            out = await send(tname, args, meta)
            t3 = time.perf_counter()
            if not out["ok"]: raise RuntimeError(f"{mode}/{transport}: honest call {i} rejected: {out['why']}")
            if i >= WARMUP:
                rows.append({"tool": tname, "challenge_rtt_ms": ms(t0, t1), "prep_ms": ms(t1, t2), "call_rtt_ms": ms(t2, t3),
                             "verify_ms": out["verify_ms"], "total_ms": ms(t0, t3),
                             "auth_bytes": len(jcs(meta).encode()) if meta else 0})
            last = (tname, args, meta)

        # ---------------- negative controls
        tname, args, meta = last
        other = TOOLS[(TOOLS.index(tname) + 1) % 3]
        oargs = gen_args(other, 10**6)
        r = await send(tname, args, meta); controls["replay_same_tool"] = {"accepted": r["ok"], "why": r["why"]}
        r = await send(other, oargs, meta); controls["replay_other_tool"] = {"accepted": r["ok"], "why": r["why"]}
        # replay the old authorisation at the same tool after fetching a fresh challenge and rewriting the plain nonce field
        if mode != "none":
            n2, _ = await challenge(tname); m2 = dict(meta); m2["nonce"] = n2
            r = await send(tname, args, m2); controls["replay_same_tool_fresh_nonce"] = {"accepted": r["ok"], "why": r["why"]}
            n3, _ = await challenge(other); m3 = dict(meta); m3["nonce"] = n3
            r = await send(other, oargs, m3); controls["replay_other_tool_fresh_nonce"] = {"accepted": r["ok"], "why": r["why"]}
        # call tampering: an on-path attacker intercepts a fresh (unused) authorisation and changes the amount
        tname = TOOLS[0]; i = 10**6 + 1; args = gen_args(tname, i); call = call_json(tname, args)
        nonce, t = (await challenge(tname)) if mode != "none" else (None, None)
        meta = cl.authorize(tool_ids[tname], tname, args, call, nonce, t)
        bad = dict(args, amt=args["amt"] + 1)
        r = await send(tname, bad, cl.tamper(meta, call_json(tname, bad)))
        controls["tampered_call_fresh_auth"] = {"accepted": r["ok"], "why": r["why"]}
        # revocation: authorisation prepared before agent1's delegation is revoked, sent after the status push
        i = 10**6 + 2; args = gen_args(tname, i); call = call_json(tname, args)
        nonce, t = (await challenge(tname)) if mode != "none" else (None, None)
        meta = cl.authorize(tool_ids[tname], tname, args, call, nonce, t)
        payload = cl.revoke_payload()
        adm = (await sess[tname].call_tool("admin_update", {"payload": payload})).content[0].text
        r = await send(tname, args, meta)
        controls["after_revocation_of_agent1"] = {"accepted": r["ok"], "why": r["why"], "admin": adm, "push_bytes": len(payload)}

    for p in procs: p.terminate()
    for p in procs:
        try: p.wait(5)
        except Exception: p.kill()
    for lf in logs: lf.close()
    summ = {k: summarize(rows, k) for k in ("challenge_rtt_ms", "prep_ms", "call_rtt_ms", "verify_ms", "total_ms", "auth_bytes")}
    return {"mode": mode, "transport": transport, "delegation_issuance": deleg_cost, "summary": summ,
            "controls": controls, "calls": rows}


MODES = ["none", "jwt_chain", "biscuit", "macaroon", "batch_tokens", "blind_tokens", "mm", "mm_esc"]
TRANSPORTS = ["stdio", "http", "http_delay10"]

Y, N = "yes", "no"
PROPERTIES = {
    "none": {k: N for k in ["signature_chain", "attenuation", "per_call_binding", "replay", "expiry", "revocation_status",
                            "rate_limit", "unlinkable_across_tools", "unlinkable_vs_issuer", "accountability_escrow"]}
            | {"notes": "No authorisation; no challenge fetched."},
    "jwt_chain": {"signature_chain": "yes: issuer-signed root JWT + agent1-signed delegation JWT, cnf-key linkage and prev-hash",
                  "attenuation": "yes: tool checks scope subset, budget and exp monotone along the chain",
                  "per_call_binding": "yes: PoP JWT by the leaf cnf key over SHA-256(JCS call), aud=tool identity, tool nonce, tool time",
                  "replay": "yes: tool nonce single-use + seen-set of PoP hashes",
                  "expiry": "yes: exp of every JWT (pyjwt) and t <= leaf exp",
                  "revocation_status": "yes (added): in-memory status list of mandate jti pushed by the issuer",
                  "rate_limit": "no (not implemented; feasible because calls are linkable)",
                  "unlinkable_across_tools": "no: identical chain shown to every tool",
                  "unlinkable_vs_issuer": "no", "accountability_escrow": "in the clear (tool learns principal and agents)"},
    "biscuit": {"signature_chain": "yes: authority block (issuer root key) + 2 attenuation blocks + per-call block (Ed25519 chain)",
                "attenuation": "yes: every block's checks must hold (class, amount, time)",
                "per_call_binding": "partial: last block binds call hash, tool identity and nonce; bearer token, no PoP: whoever "
                                    "holds the pre-call token can append a block for any call",
                "replay": "yes: tool nonce single-use + seen-set",
                "expiry": "yes: time checks against tool time",
                "revocation_status": "yes (added): revocation_ids of the token checked against a pushed list",
                "rate_limit": "no", "unlinkable_across_tools": "no: same token prefix/revocation ids everywhere",
                "unlinkable_vs_issuer": "no", "accountability_escrow": "in the clear (delegate facts)"},
    "macaroon": {"signature_chain": "HMAC chain only; the tool must hold the issuer's root HMAC key (shared secret, it can mint mandates)",
                 "attenuation": "yes: both delegation caveats checked (class, amount, exp)",
                 "per_call_binding": "partial: caveats on call hash, tool identity, nonce; bearer, no PoP",
                 "replay": "yes: tool nonce single-use + seen-set", "expiry": "yes: exp caveats vs tool time",
                 "revocation_status": "no", "rate_limit": "no", "unlinkable_across_tools": "no: same identifier/signature chain",
                 "unlinkable_vs_issuer": "no", "accountability_escrow": "in the clear (caveats)"},
    "batch_tokens": {"signature_chain": "at issuance only: issuer verifies the JWT chain in the clear; tool checks one issuer Ed25519 signature",
                     "attenuation": "at issuance only (class set and budget tier copied from the chain leaf); tool checks class and amount <= tier",
                     "per_call_binding": "yes: PoP by the per-token cnf key over SHA-256(JCS call), tool identity, tool nonce, tool time",
                     "replay": "yes: tool nonce single-use + seen-set of token ids (per tool; class metadata pins a token to one tool here)",
                     "expiry": "epoch granularity only", "revocation_status": "yes (added): status list of token ids (issuer pushes all ids of the revoked delegation)",
                     "rate_limit": "issuer-side only (batch size per epoch); tools cannot enforce per-agent limits",
                     "unlinkable_across_tools": "yes (fresh token and key per call) unless tools collude with the issuer",
                     "unlinkable_vs_issuer": "no: issuer saw every token id and cnf key with the agent identity",
                     "accountability_escrow": "via issuer log (token id -> agent), not threshold"},
    "blind_tokens": {"signature_chain": "at issuance only: issuer verifies the JWT chain in the clear; tool checks one RSA-PSS signature",
                     "attenuation": "at issuance only via key choice (one key per class/tier/epoch); tool checks class and amount <= tier",
                     "per_call_binding": "weak: bearer token sent next to a plain call_hash field; tool nonce prevents re-use after redemption "
                                         "but an on-path attacker holding an unused token can attach it to any call of that class "
                                         "(demonstrated by the tampered_call control)",
                     "replay": "yes after redemption: tool nonce + seen-set of token randoms (per tool)",
                     "expiry": "epoch granularity (key rotation)", "revocation_status": "no (issued tokens valid until epoch end)",
                     "rate_limit": "issuer-side only (batch size per epoch)",
                     "unlinkable_across_tools": "yes", "unlinkable_vs_issuer": "yes (blind issuance), except public metadata (class, tier, epoch) and batch counts",
                     "accountability_escrow": "no"},
    "mm": {"signature_chain": "yes, hidden: ZK proof of an issuer BBS signature on the sub-agent mandate; parent proofs checked by the issuer at each delegation",
           "attenuation": "enforced by the issuer at delegation (ZK range proofs on the hidden attributes); tool checks class in scope, amt <= budget in ZK",
           "per_call_binding": "yes: proof bound to SHA-256 of (tool identity, JCS call, class, amt, epoch, tool time, tool nonce)",
           "replay": "yes: tool nonce single-use + per-tool pseudonym seen-set", "expiry": "yes: t <= exp proven in ZK with tool time",
           "revocation_status": "yes: accumulator non-membership of the mandate id and its ancestors (public params update)",
           "rate_limit": "yes: per tool per epoch, k calls via Dodis-Yampolskiy pseudonyms",
           "unlinkable_across_tools": "yes", "unlinkable_vs_issuer": "yes", "accountability_escrow": "no"},
}
PROPERTIES["mm_esc"] = {**PROPERTIES["mm"], **{"notes": "as mm, plus verifiable threshold escrow of the principal identity (tool requires the escrow ciphertext)",
               "accountability_escrow": "yes: threshold escrow, verified by the tool"}}

def uptime():
    try: return subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
    except Exception as e: return str(e)

def main_client(out, modes, transports):
    import importlib.metadata as md, platform
    res = {"seed": SEED, "n_calls": N_CALLS, "warmup": WARMUP, "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
           "uptime_start": uptime(), "mcp_sdk": md.version("mcp"), "python": platform.python_version(),
           "platform": platform.platform(), "machine": platform.machine(),
           "transports": {"stdio": "MCP stdio, one subprocess per tool server",
                          "http": "MCP streamable HTTP over 127.0.0.1, one FastMCP server process per tool (distinct ports)",
                          "http_delay10": "as http, through a per-server TCP relay process adding 10 ms one-way delay to every forwarded chunk in each direction (RTT +20 ms per HTTP exchange)"},
           "tools": TOOLS, "tool_classes": CLS,
           "delegation": {"root": {"scope": [0, 1, 2], "budget_cents": BUD_ROOT, "exp": EXP_ROOT},
                          "agent1": {"scope": SCOPE1, "budget_cents": BUD1, "exp": EXP1, "k": K1},
                          "agent2": {"scope": SCOPE2, "budget_cents": BUD2, "exp": EXP2, "k": K2}},
           "properties": PROPERTIES, "runs": []}
    tmpdir = tempfile.mkdtemp(prefix="e2v2_")
    rsa_keys = None
    if "blind_tokens" in modes:
        t0 = time.perf_counter()
        rsa_keys = {c: rsa_keygen_det(blind_kid(c, BUD2, EPOCH)) for c in SCOPE2}
        res["rsa_keygen_ms_3_keys"] = ms(t0, time.perf_counter())
    run_idx = 0
    for transport in transports:
        for mode in modes:
            run_idx += 1
            r = asyncio.run(run_one(mode, transport, run_idx, tmpdir, rsa_keys))
            s = r["summary"]
            print(f"{transport:13s} {mode:13s} total med {s['total_ms']['median']:8.2f} p95 {s['total_ms']['p95']:8.2f} "
                  f"chal {s['challenge_rtt_ms']['median']:6.2f} prep {s['prep_ms']['median']:7.2f} verify {s['verify_ms']['median']:7.2f} "
                  f"bytes {s['auth_bytes']['median']:7.0f} | " +
                  " ".join(f"{k}={'ACC' if v['accepted'] else 'rej'}" for k, v in r["controls"].items()), file=sys.stderr, flush=True)
            res["runs"].append(r)
            json.dump(res, open(out, "w"))
    res["uptime_end"] = uptime()
    json.dump(res, open(out, "w"))
    write_summary(res, os.path.join(os.path.dirname(out), "e2v2_summary.md"))

def write_summary(res, path):
    L = ["# E2 v2 -- end-to-end MCP authorisation (summary)", "",
         f"Seed {res['seed']}; {res['n_calls']} measured calls after {res['warmup']} warm-up calls per (mode, transport), "
         f"round-robin over {', '.join(res['tools'])}; RAYON_NUM_THREADS={res['rayon_num_threads']}; MCP SDK {res['mcp_sdk']}; "
         f"Python {res['python']}; {res['platform']}.", "",
         f"Load at start: `{res['uptime_start']}`  ", f"Load at end: `{res.get('uptime_end', '')}`", "",
         "Every authorised call = `challenge` round trip (tool-issued single-use nonce + tool time) + agent preparation + "
         "the tool call. Times in ms (median / p95). `verify` is measured inside the tool server (includes nonce lookup). "
         "`bytes` = JCS-serialised `_meta` authorisation material per call.", ""]
    for tr in res["transports"]:
        rs = [r for r in res["runs"] if r["transport"] == tr]
        if not rs: continue
        L += [f"## Transport: {tr}", "", f"_{res['transports'][tr]}_", "",
              "| mode | total med | total p95 | challenge RTT med | prep med | call RTT med | verify med | verify p95 | bytes |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for r in rs:
            s = r["summary"]
            L.append(f"| {r['mode']} | {s['total_ms']['median']:.2f} | {s['total_ms']['p95']:.2f} | {s['challenge_rtt_ms']['median']:.2f} | "
                     f"{s['prep_ms']['median']:.2f} | {s['call_rtt_ms']['median']:.2f} | {s['verify_ms']['median']:.2f} | "
                     f"{s['verify_ms']['p95']:.2f} | {s['auth_bytes']['median']:.0f} |")
        L.append("")
    L += ["## Delegation / issuance cost before calls (two hops; from the first transport's run)", "",
          "| mode | two-hop delegation ms | issuance details |", "|---|---:|---|"]
    seen = set()
    for r in res["runs"]:
        if r["mode"] in seen: continue
        seen.add(r["mode"]); d = r["delegation_issuance"]
        det = ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in d.items() if k != "two_hop_total_ms")
        L.append(f"| {r['mode']} | {d['two_hop_total_ms']:.3f} | {det} |")
    L += ["", "## Negative controls (accepted?)", "",
          "Expected: everything rejected except `none`; by design `macaroon` and `blind_tokens` have no revocation mechanism and "
          "`blind_tokens` only has bearer-level call binding, so ACCEPTED there is the honest, expected outcome. "
          "`tampered call` = on-path attacker takes a fresh, unused authorisation and changes `amt` (rewriting only unsigned fields). "
          "`after revocation` = authorisation prepared, then agent1's delegation revoked and the status list / new public params "
          "pushed to the tool, then the authorisation is sent.", "",
          "| transport | mode | " + " | ".join(["replay same", "replay other", "replay same + fresh nonce", "replay other + fresh nonce", "tampered call", "after revocation"]) + " |",
          "|---|---|" + "---|" * 6]
    keys = ["replay_same_tool", "replay_other_tool", "replay_same_tool_fresh_nonce", "replay_other_tool_fresh_nonce",
            "tampered_call_fresh_auth", "after_revocation_of_agent1"]
    for r in res["runs"]:
        c = r["controls"]
        L.append(f"| {r['transport']} | {r['mode']} | " + " | ".join(("ACCEPTED" if c[k]["accepted"] else "rejected") if k in c else "n/a" for k in keys) + " |")
    L += ["", "## What each tool actually verifies", "", "| mode | property | verified |", "|---|---|---|"]
    for m, props in res["properties"].items():
        for k, v in props.items(): L.append(f"| {m} | {k} | {v} |")
    L += ["", "## Limitations / deviations", "",
          "- Blind tokens: RFC 9474 RSABSSA-SHA384-PSS-Randomized (2048-bit), client and issuer operations in pure Python "
          "(issuer BlindSign uses CRT big-int pow, no GMP), so issuance is pessimistic; tools verify the final RSA-PSS signature with OpenSSL. "
          "Not checked against the RFC test vectors (correctness checked by OpenSSL PSS verification of every finalized token). "
          "Public metadata bound by one issuer key per (class, tier, epoch); RSA keys are generated deterministically from the seed for reproducibility only.",
          "- Blind tokens are bearer: the call hash travels in a plain field, so binding to the call is only by co-transport (tampered-call control is accepted).",
          "- Status lists (jwt_chain, batch_tokens) and biscuit revocation ids are pushed through an unauthenticated experiment-only `admin_update` tool; "
          "MM public parameters (new accumulator) are pushed the same way.",
          "- Macaroon tools hold the issuer's root HMAC key (they could mint mandates).",
          "- Replay seen-sets and nonce stores are per tool, in memory; double-spend of a token across tools is prevented here only because class metadata maps 1:1 to tools.",
          "- The 10 ms delay is a userspace TCP relay (per forwarded chunk, each direction), not netem; TCP handshakes are not delayed (connections kept alive).",
          "- `none` fetches no challenge. MM delegation timing: median of 3 two-hop chains; other modes median of 50.",
          "- The Mac may be shared with other jobs (see load averages)."]
    open(path, "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "server":
        run_server(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6])
    elif sys.argv[1] == "proxy":
        run_proxy(int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]))
    elif sys.argv[1] == "summary":
        write_summary(json.load(open(sys.argv[2])), sys.argv[3])
    else:
        main_client(sys.argv[2], sys.argv[3].split(",") if len(sys.argv) > 3 else MODES,
                    sys.argv[4].split(",") if len(sys.argv) > 4 else TRANSPORTS)
