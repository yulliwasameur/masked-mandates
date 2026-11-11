"""E2 — end-to-end MCP calls (official Python SDK, stdio transport).
One agent client, three MCP tool servers. Modes: none, jwt (mandate JWT + per-call PoP JWT, EdDSA, Agentic-JWT/DPoP style),
biscuit (authority + 2 attenuation blocks + per-call block), macaroon (2 delegation caveats + per-call caveat),
mm (Masked Mandates), mm_esc (Masked Mandates with escrow).
Usage: python e2.py client OUT.json  |  python e2.py server MODE TOOL
"""
import asyncio, base64, hashlib, json, os, sys, time, statistics

SEED = 20261109
TOOLS = ["airline", "hotel", "payment"]
N_CALLS = int(os.environ.get("E2_CALLS", "200"))
WARMUP = 15
EPOCH = 1

def canon(name, args):
    return json.dumps({"arguments": args, "name": name}, sort_keys=True, separators=(",", ":"))

def h(s):
    return hashlib.sha256(s.encode()).hexdigest()

def det_key(label):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(f"{SEED}|{label}".encode()).digest())

def pub_b64(sk):
    from cryptography.hazmat.primitives import serialization as s
    return base64.urlsafe_b64encode(sk.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)).decode()

# ---------------------------------------------------------------- agent side
class Agent:
    def __init__(self, mode):
        self.mode = mode
        self.n = 0
        if mode == "jwt":
            import jwt
            self.jwt = jwt
            iss = det_key("issuer")
            self.a2 = det_key("agent2")
            # two-level delegation chain carried in the mandate (issuer-signed)
            self.mandate = jwt.encode({"iss": "wallet", "sub": "agent2", "act": {"sub": "agent2", "act": {"sub": "agent1"}},
                                       "principal": "alice", "scope": ["search"], "budget": 1000, "cnf": {"okp": pub_b64(self.a2)},
                                       "exp": 4102444800}, iss, algorithm="EdDSA")
        elif mode == "biscuit":
            import biscuit_auth as b
            self.b = b
            root = b.PrivateKey.from_bytes(hashlib.sha256(f"{SEED}|biscuit".encode()).digest(), b.Algorithm.Ed25519)
            tok = b.BiscuitBuilder('user("alice"); right("search");').build(root)
            tok = tok.append(b.BlockBuilder('check if operation("search");'))  # agent1
            tok = tok.append(b.BlockBuilder('check if budget($b), $b <= 1000;'))  # agent2
            self.tok = tok
        elif mode == "macaroon":
            from pymacaroons import Macaroon
            m = Macaroon(location="wallet", identifier="alice-mandate", key=hashlib.sha256(f"{SEED}|mac".encode()).hexdigest())
            m.add_first_party_caveat("delegate = agent1")
            m.add_first_party_caveat("delegate = agent2")
            self.mac = m
        elif mode in ("mm", "mm_esc"):
            import mmpy
            self.w = mmpy.Wallet(SEED)

    def authorize(self, tool, name, args):
        """returns the _meta dict for this call"""
        self.n += 1
        nonce = f"{self.n}-{os.urandom(8).hex()}"
        c = canon(name, args)
        if self.mode == "none":
            return {}
        if self.mode == "jwt":
            pop = self.jwt.encode({"htm": "tools/call", "aud": tool, "call": h(c), "jti": nonce, "iat": int(time.time())}, self.a2, algorithm="EdDSA")
            return {"auth": {"mandate": self.mandate, "pop": pop}}
        if self.mode == "biscuit":
            t = self.tok.append(self.b.BlockBuilder(f'check if call("{h(c)}"); check if tool("{tool}"); check if nonce("{nonce}");'))
            return {"auth": {"biscuit": t.to_base64(), "nonce": nonce}}
        if self.mode == "macaroon":
            m = self.mac.copy()
            m.add_first_party_caveat(f"call = {h(c)}")
            m.add_first_party_caveat(f"tool = {tool}")
            m.add_first_party_caveat(f"nonce = {nonce}")
            return {"auth": {"macaroon": m.serialize(), "nonce": nonce}}
        if self.mode in ("mm", "mm_esc"):
            blob = self.w.present(tool, c, 1, int(args.get("amt", 0)), EPOCH, 1_000_000, nonce, self.mode == "mm_esc")
            return {"mm": {"p": base64.b64encode(bytes(blob)).decode(), "n": nonce}}
        raise ValueError(self.mode)

# ---------------------------------------------------------------- tool side
class Checker:
    def __init__(self, mode, tool):
        self.mode, self.tool, self.seen = mode, tool, set()
        if mode == "jwt":
            import jwt
            self.jwt = jwt
            self.iss_pub = det_key("issuer").public_key()
        elif mode == "biscuit":
            import biscuit_auth as b
            self.b = b
            self.root_pub = b.KeyPair.from_private_key(b.PrivateKey.from_bytes(hashlib.sha256(f"{SEED}|biscuit".encode()).digest(), b.Algorithm.Ed25519)).public_key
        elif mode == "macaroon":
            self.key = hashlib.sha256(f"{SEED}|mac".encode()).hexdigest()
        elif mode in ("mm", "mm_esc"):
            import mmpy
            self.v = mmpy.Verifier(SEED, tool, mode == "mm_esc")

    def check(self, meta, name, args):
        c = canon(name, args)
        if self.mode == "none":
            return True, ""
        a = (meta or {})
        if self.mode == "jwt":
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            au = a["auth"]
            m = self.jwt.decode(au["mandate"], self.iss_pub, algorithms=["EdDSA"])
            if "search" not in m["scope"]: return False, "scope"
            pk = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(m["cnf"]["okp"]))
            p = self.jwt.decode(au["pop"], pk, algorithms=["EdDSA"], audience=self.tool)
            if p["call"] != h(c): return False, "call hash"
            if p["jti"] in self.seen: return False, "replay"
            self.seen.add(p["jti"]); return True, ""
        if self.mode == "biscuit":
            au = a["auth"]
            tok = self.b.Biscuit.from_base64(au["biscuit"], self.root_pub)
            az = self.b.AuthorizerBuilder(f'operation("search"); budget({int(args.get("amt", 0))}); call("{h(c)}"); tool("{self.tool}"); nonce("{au["nonce"]}"); allow if user($u), right("search");').build(tok)
            az.authorize()
            if au["nonce"] in self.seen: return False, "replay"
            self.seen.add(au["nonce"]); return True, ""
        if self.mode == "macaroon":
            from pymacaroons import Macaroon, Verifier
            au = a["auth"]
            m = Macaroon.deserialize(au["macaroon"])
            v = Verifier()
            v.satisfy_exact("delegate = agent1"); v.satisfy_exact("delegate = agent2")
            v.satisfy_exact(f"call = {h(c)}"); v.satisfy_exact(f"tool = {self.tool}"); v.satisfy_exact(f"nonce = {au['nonce']}")
            v.verify(m, self.key)
            if au["nonce"] in self.seen: return False, "replay"
            self.seen.add(au["nonce"]); return True, ""
        if self.mode in ("mm", "mm_esc"):
            x = a["mm"]
            ok, why = self.v.verify(c, 1, int(args.get("amt", 0)), EPOCH, 1_000_000, x["n"], base64.b64decode(x["p"]))
            return ok, why

def run_server(mode, tool):
    from mcp.server.fastmcp import FastMCP, Context
    srv = FastMCP(f"{tool}-{mode}")
    chk = Checker(mode, tool)

    @srv.tool()
    def search(q: str, amt: int, ctx: Context) -> str:
        meta = ctx.request_context.meta
        md = meta.model_dump() if meta is not None else {}
        t0 = time.perf_counter()
        try:
            ok, why = chk.check(md, "search", {"q": q, "amt": amt})
        except Exception as e:
            ok, why = False, f"{type(e).__name__}: {e}"
        dt = (time.perf_counter() - t0) * 1e3
        return json.dumps({"ok": ok, "why": why, "verify_ms": dt, "result": f"{tool}: 3 offers for {q}" if ok else None})

    srv.run("stdio")

async def run_mode(mode):
    from contextlib import AsyncExitStack
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    agent = Agent(mode)
    rows = []
    async with AsyncExitStack() as st:
        sess = {}
        for t in TOOLS:
            p = StdioServerParameters(command=sys.executable, args=[__file__, "server", mode, t], env={**os.environ})
            r, w = await st.enter_async_context(stdio_client(p))
            s = await st.enter_async_context(ClientSession(r, w))
            await s.initialize()
            sess[t] = s
        last = None
        for i in range(WARMUP + N_CALLS):
            t = TOOLS[i % 3]
            args = {"q": f"paris-{i}", "amt": 100 + i % 50}
            t0 = time.perf_counter()
            meta = agent.authorize(t, "search", args)
            t1 = time.perf_counter()
            res = await sess[t].call_tool("search", args, meta=meta or None)
            t2 = time.perf_counter()
            out = json.loads(res.content[0].text)
            if not out["ok"]:
                raise RuntimeError(f"{mode}: honest call rejected: {out['why']}")
            if i >= WARMUP:
                rows.append({"prep_ms": (t1 - t0) * 1e3, "rtt_ms": (t2 - t1) * 1e3, "verify_ms": out["verify_ms"],
                             "total_ms": (t2 - t0) * 1e3, "meta_bytes": len(json.dumps(meta, separators=(",", ":")).encode()) if meta else 0})
            last = (t, args, meta)
        # negative control: replay the last authorisation at the same tool and at another tool
        t, args, meta = last
        same = json.loads((await sess[t].call_tool("search", args, meta=meta or None)).content[0].text)["ok"]
        other_t = TOOLS[(TOOLS.index(t) + 1) % 3]
        other = json.loads((await sess[other_t].call_tool("search", args, meta=meta or None)).content[0].text)["ok"]
    return {"mode": mode, "calls": rows, "replay_same_accepted": same, "replay_other_accepted": other}

def main_client(out):
    import importlib.metadata as md, platform
    res = {"seed": SEED, "n_calls": N_CALLS, "warmup": WARMUP, "mcp_sdk": md.version("mcp"), "python": platform.python_version(),
           "transport": "stdio", "tools": TOOLS, "modes": []}
    for mode in ["none", "jwt", "biscuit", "macaroon", "mm", "mm_esc"]:
        r = asyncio.run(run_mode(mode))
        med = statistics.median([x["total_ms"] for x in r["calls"]])
        print(mode, f"median total {med:.2f} ms", "replay same/other accepted:", r["replay_same_accepted"], r["replay_other_accepted"], file=sys.stderr, flush=True)
        res["modes"].append(r)
    json.dump(res, open(out, "w"))

if __name__ == "__main__":
    if sys.argv[1] == "server":
        run_server(sys.argv[2], sys.argv[3])
    else:
        main_client(sys.argv[2])
