"""E4 -- a real LLM agent in the loop.

An LLM (any OpenAI-compatible chat endpoint with tool calling: llama.cpp llama-server, vLLM, ...) solves
multi-step booking tasks by calling three MCP tool servers (official Python SDK, stdio). Every tool call is
authorised in one of three modes: none, jwt (mandate JWT + per-call PoP JWT, as in E2) and mm (Masked Mandates).
The prompts and the tools seen by the model are identical in every mode: authorisation lives in the MCP _meta
field, which the model never sees. We measure, per task, the time spent in model inference, in authorisation
(agent-side preparation and tool-side verification) and in transport, and whether the task succeeded.

Usage:
  python e4.py run --base-url http://127.0.0.1:8080/v1 --model NAME --out results/e4_NAME.json [--tasks 24] [--reps 1]
  python e4.py server MODE TOOL        (spawned by the client)
"""
import argparse, asyncio, json, os, random, statistics, sys, time
from contextlib import AsyncExitStack

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "e2"))
import e2  # noqa: E402  (Agent, Checker, canon, SEED)

SEED = 20261109
MODES = ["none", "jwt", "mm"]
SERVERS = {"search_flights": "airline", "search_hotels": "hotel", "pay": "payment"}
CITIES = ["Lisbon", "Rome", "Berlin", "Madrid", "Vienna", "Prague", "Athens", "Dublin", "Oslo", "Warsaw", "Budapest", "Porto"]
MAX_TURNS = 12

# ---------------------------------------------------------------- deterministic world
def flights(dest):
    r = random.Random(f"{SEED}|fl|{dest}")
    return [{"flight": f"{dest[:3].upper()}{100 + i}", "airline": a, "price": r.randint(90, 420)}
            for i, a in enumerate(["AirNova", "SkyLine", "EuroJet"])]

def hotels(city, nights):
    r = random.Random(f"{SEED}|ho|{city}")
    return [{"hotel": f"{n} {city}", "price_per_night": r.randint(60, 240), "total": None, "nights": nights}
            for n in ["Hotel Central", "Grand Plaza", "Riverside Inn"]]

def amt_of(name, args):
    return int(round(float(args.get("amount", 0)))) if name == "pay" else 0

def tool_result(name, args):
    if name == "search_flights":
        dest = str(args.get("destination", "")).strip().title()
        mx = float(args.get("max_price", 1e9))
        return {"destination": dest, "flights": [f for f in flights(dest) if f["price"] <= mx]}
    if name == "search_hotels":
        city = str(args.get("city", "")).strip().title()
        nights = int(args.get("nights", 1))
        mx = float(args.get("max_price_per_night", 1e9))
        out = []
        for h in hotels(city, nights):
            if h["price_per_night"] <= mx:
                h = dict(h); h["total"] = h["price_per_night"] * nights; out.append(h)
        return {"city": city, "hotels": out}
    if name == "pay":
        return {"status": "paid", "merchant": args.get("merchant"), "amount": args.get("amount"),
                "receipt": f"R-{abs(hash((args.get('merchant'), args.get('amount')))) % 10**6:06d}"}
    return {"error": f"unknown tool {name}"}

def make_tasks(n):
    r = random.Random(f"{SEED}|tasks")
    tasks = []
    for i in range(n):
        city = CITIES[i % len(CITIES)]
        nights = r.randint(1, 4)
        fmax = r.choice([250, 300, 350, 400])
        hmax = r.choice([120, 160, 200, 240])
        fl = sorted([f for f in flights(city) if f["price"] <= fmax], key=lambda f: f["price"])
        ho = sorted([h for h in hotels(city, nights) if h["price_per_night"] <= hmax], key=lambda h: h["price_per_night"])
        if not fl or not ho:
            fmax, hmax = 420, 240
            fl = sorted(flights(city), key=lambda f: f["price"]); ho = sorted(hotels(city, nights), key=lambda h: h["price_per_night"])
        exp = sorted([(fl[0]["airline"], fl[0]["price"]), (ho[0]["hotel"], ho[0]["price_per_night"] * nights)])
        prompt = (f"Book a trip to {city}: take the cheapest flight that costs at most {fmax} EUR, and the cheapest hotel in {city} "
                  f"for {nights} night(s) at most {hmax} EUR per night. Then pay the airline for the flight and pay the hotel for "
                  f"the whole stay, using the exact merchant names and amounts returned by the tools. Reply 'DONE' when both payments are made.")
        tasks.append({"id": i, "city": city, "nights": nights, "prompt": prompt, "expected_payments": exp})
    return tasks

TOOL_SPECS = [
    {"type": "function", "function": {"name": "search_flights", "description": "Search flights to a destination city.",
     "parameters": {"type": "object", "properties": {"destination": {"type": "string"}, "max_price": {"type": "number", "description": "maximum price in EUR"}},
                    "required": ["destination", "max_price"]}}},
    {"type": "function", "function": {"name": "search_hotels", "description": "Search hotels in a city for a number of nights.",
     "parameters": {"type": "object", "properties": {"city": {"type": "string"}, "nights": {"type": "integer"},
                    "max_price_per_night": {"type": "number", "description": "maximum price per night in EUR"}},
                    "required": ["city", "nights", "max_price_per_night"]}}},
    {"type": "function", "function": {"name": "pay", "description": "Pay a merchant.",
     "parameters": {"type": "object", "properties": {"merchant": {"type": "string", "description": "airline or hotel name"},
                    "amount": {"type": "number", "description": "amount in EUR"}}, "required": ["merchant", "amount"]}}},
]
SYSTEM = "You are a travel assistant. Use the tools to complete the user's request. Call one tool at a time when results are needed for the next step."

# ---------------------------------------------------------------- tool server
def run_server(mode, server):
    from mcp.server.fastmcp import FastMCP, Context
    srv = FastMCP(f"{server}-{mode}")
    chk = e2.Checker(mode, server)

    def guarded(name, args, ctx):
        meta = ctx.request_context.meta
        md = meta.model_dump() if meta is not None else {}
        full = {**args, "amt": amt_of(name, args)}
        t0 = time.perf_counter()
        try:
            ok, why = chk.check(md, name, full)
        except Exception as ex:
            ok, why = False, f"{type(ex).__name__}: {ex}"
        dt = (time.perf_counter() - t0) * 1e3
        return json.dumps({"ok": ok, "why": why, "verify_ms": dt, "result": tool_result(name, args) if ok else None})

    if server == "airline":
        @srv.tool()
        def search_flights(destination: str, max_price: float, ctx: Context) -> str:
            return guarded("search_flights", {"destination": destination, "max_price": max_price}, ctx)
    elif server == "hotel":
        @srv.tool()
        def search_hotels(city: str, nights: int, max_price_per_night: float, ctx: Context) -> str:
            return guarded("search_hotels", {"city": city, "nights": nights, "max_price_per_night": max_price_per_night}, ctx)
    else:
        @srv.tool()
        def pay(merchant: str, amount: float, ctx: Context) -> str:
            return guarded("pay", {"merchant": merchant, "amount": amount}, ctx)
    srv.run("stdio")

# ---------------------------------------------------------------- agent loop
async def chat(client, base, model, messages):
    t0 = time.perf_counter()
    r = await client.post(f"{base}/chat/completions", json={"model": model, "messages": messages, "tools": TOOL_SPECS,
                                                           "tool_choice": "auto", "temperature": 0, "seed": 0, "max_tokens": 512})
    dt = (time.perf_counter() - t0) * 1e3
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    j = r.json()
    return j["choices"][0]["message"], j.get("usage", {}), dt

def norm_args(name, raw):
    try:
        a = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return None
    # coerce to the declared types, so that the MCP call and the authorisation see the same canonical arguments
    try:
        if name == "search_flights":
            return {"destination": str(a["destination"]), "max_price": float(a["max_price"])}
        if name == "search_hotels":
            return {"city": str(a["city"]), "nights": int(a["nights"]), "max_price_per_night": float(a["max_price_per_night"])}
        if name == "pay":
            return {"merchant": str(a["merchant"]), "amount": float(a["amount"])}
    except Exception:
        return None
    return None

async def run_task(client, base, model, sess, agent, task):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["prompt"]}]
    rec = {"task": task["id"], "llm_ms": [], "tokens_in": 0, "tokens_out": 0, "calls": [], "error": None}
    t_start = time.perf_counter()
    for _ in range(MAX_TURNS):
        try:
            msg, usage, dt = await chat(client, base, model, msgs)
        except Exception as ex:
            rec["error"] = f"llm: {type(ex).__name__}: {ex}"[:300]; break
        rec["llm_ms"].append(dt)
        rec["tokens_in"] += usage.get("prompt_tokens", 0); rec["tokens_out"] += usage.get("completion_tokens", 0)
        tcs = msg.get("tool_calls") or []
        msgs.append({"role": "assistant", "content": msg.get("content") or "", **({"tool_calls": tcs} if tcs else {})})
        if not tcs:
            rec["final_text"] = (msg.get("content") or "")[:400]
            break
        for tc in tcs:
            name = tc["function"]["name"]
            args = norm_args(name, tc["function"].get("arguments", "{}"))
            if name not in SERVERS or args is None:
                content = json.dumps({"error": "invalid tool call"})
                rec["calls"].append({"name": name, "args": None, "ok": False})
            else:
                full = {**args, "amt": amt_of(name, args)}
                srv = SERVERS[name]
                t0 = time.perf_counter()
                meta = agent.authorize(srv, name, full)
                t1 = time.perf_counter()
                res = await sess[srv].call_tool(name, args, meta=meta or None)
                t2 = time.perf_counter()
                out = json.loads(res.content[0].text)
                rec["calls"].append({"name": name, "args": args, "ok": out["ok"], "why": out["why"], "prep_ms": (t1 - t0) * 1e3,
                                     "rtt_ms": (t2 - t1) * 1e3, "verify_ms": out["verify_ms"],
                                     "meta_bytes": len(json.dumps(meta, separators=(",", ":")).encode()) if meta else 0})
                content = json.dumps(out["result"]) if out["ok"] else json.dumps({"error": "authorisation rejected"})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "name": name, "content": content})
    rec["wall_ms"] = (time.perf_counter() - t_start) * 1e3
    paid = sorted((c["args"]["merchant"], round(c["args"]["amount"])) for c in rec["calls"] if c["name"] == "pay" and c["ok"] and c["args"])
    rec["paid"] = paid
    rec["success"] = paid == [(m, round(a)) for m, a in task["expected_payments"]]
    rec["rejected_honest_calls"] = sum(1 for c in rec["calls"] if c["args"] is not None and not c["ok"])
    return rec

async def run_mode(base, model, mode, tasks, reps):
    import httpx
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    agent = e2.Agent(mode)
    rows = []
    async with AsyncExitStack() as st, httpx.AsyncClient(timeout=600) as client:
        sess = {}
        for srv in ["airline", "hotel", "payment"]:
            p = StdioServerParameters(command=sys.executable, args=[__file__, "server", mode, srv], env={**os.environ})
            r, w = await st.enter_async_context(stdio_client(p))
            s = await st.enter_async_context(ClientSession(r, w)); await s.initialize(); sess[srv] = s
        for rep in range(reps):
            for t in tasks:
                rec = await run_task(client, base, model, sess, agent, t)
                rec["rep"] = rep; rec["mode"] = mode
                rows.append(rec)
                auth = sum(c.get("prep_ms", 0) + c.get("verify_ms", 0) for c in rec["calls"])
                print(f"[{model}] {mode} rep{rep} task{t['id']}: success={rec['success']} turns={len(rec['llm_ms'])} "
                      f"llm={sum(rec['llm_ms']):.0f}ms auth={auth:.0f}ms wall={rec['wall_ms']:.0f}ms", file=sys.stderr, flush=True)
    return rows

def summarise(rows):
    out = {}
    for mode in MODES:
        rs = [r for r in rows if r["mode"] == mode]
        if not rs: continue
        llm = [sum(r["llm_ms"]) for r in rs]
        auth = [sum(c.get("prep_ms", 0) + c.get("verify_ms", 0) for c in r["calls"]) for r in rs]
        wall = [r["wall_ms"] for r in rs]
        out[mode] = {"tasks": len(rs), "success_rate": sum(r["success"] for r in rs) / len(rs),
                     "median_llm_ms": statistics.median(llm), "median_auth_ms": statistics.median(auth), "median_wall_ms": statistics.median(wall),
                     "auth_share_of_wall": statistics.median([a / w for a, w in zip(auth, wall) if w > 0]),
                     "tool_calls": sum(len(r["calls"]) for r in rs), "rejected_honest_calls": sum(r["rejected_honest_calls"] for r in rs)}
    return out

def main_run(a):
    import importlib.metadata as md, platform, httpx
    tasks = make_tasks(a.tasks)
    info = {}
    try:
        info = httpx.get(f"{a.base_url}/models", timeout=30).json()
    except Exception as ex:
        info = {"error": str(ex)}
    res = {"seed": SEED, "model": a.model, "base_url_kind": a.endpoint_kind, "server_models": info, "tasks": a.tasks, "reps": a.reps,
           "mcp_sdk": md.version("mcp"), "python": platform.python_version(), "machine": platform.platform(), "max_turns": MAX_TURNS,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "modes": MODES, "rows": []}
    for mode in MODES:
        res["rows"] += asyncio.run(run_mode(a.base_url, a.model, mode, tasks, a.reps))
        res["summary"] = summarise(res["rows"])
        json.dump(res, open(a.out, "w"), indent=1)
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps(res["summary"], indent=1), file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        run_server(sys.argv[2], sys.argv[3]); sys.exit(0)
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["run"])
    p.add_argument("--base-url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--endpoint-kind", default="llama.cpp")
    p.add_argument("--out", required=True)
    p.add_argument("--tasks", type=int, default=24)
    p.add_argument("--reps", type=int, default=1)
    main_run(p.parse_args())
