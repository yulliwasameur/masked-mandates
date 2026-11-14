"""E4 v2.1 -- real LLM agents calling MCP tools, with and without authorisation (Masked Mandates v2.1; revision after the
second round of reviews). Derived from e4v2/e4v2.py (kept unchanged); see results/e4v21_summary.md.

What changed with respect to E4 v2:
  * mmpy v2.1 API: Authority(seed, uid, budget, k, exp, grace); delegate(parent, classes, budget, k, exp, epoch) carves k
    counters from the parent's free interval; present(..., cur) raises ValueError when the wallet refuses (stale/revoked
    mandate, quota exhausted); Verifier in strict mode (epoch, clock, tolerance, its own single-use nonces via
    challenge(), uniform error "rejected"). The `challenge` MCP tool returns the verifier's nonce and the tool's clock;
    the client uses the tool's t. Currency (EUR) is part of the canonical call and of the presentation.
  * Canonicalisation from the RAW arguments: the client sends the arguments exactly as parsed from the model's JSON
    (no conversion: amounts stay in EUR as the model wrote them) and signs RFC 8785 JCS of {name, arguments, currency};
    the server canonicalises the raw `params.arguments` of the JSON-RPC request (low-level MCP handler, before any
    pydantic coercion) and both sides derive the integer amount in cents from the same raw value. Mismatches between the
    client's and the server's canonical strings are counted (the client's hash travels in _meta for diagnosis only).
  * Replication control: configuration t0_rep repeats t0 with identical settings.
  * Template e (binding quota): the sub-agent's mandate allows k = 3 hotel searches, the task needs 5; correct
    behaviour = calls beyond quota refused and the main agent reports a partial failure. JWT baseline: per-tree
    counters at the tool (the mandate JWT carries k and its ancestors' k).
  * Shared issuer (`--shared-issuer`): one Authority per worker shared by all its tasks, plus a background task that
    revokes unrelated dummy mandates at a fixed rate; grace window W (Authority(grace=W)); publish-then-refresh ordering
    (the wallet does not present while new public parameters are being pushed to the tools).
  * Provenance: local git commit and sha256 of the mmpy shared object in every result JSON.

Usage:
  python e4v21.py run --base-url URL --model SERVED --out OUT.json --workers 5 --agent-cores ... --server-cores ...
       [--shared-issuer --grace W --revoke-every 2 --dummies N --modes mm --cfgs t0 --limit 8]
  python e4v21.py serve --port0 P              (4 MCP servers on ports P..P+3; spawned by `run`)
  python e4v21.py worker ...                   (spawned by `run`)
  python e4v21.py bench --out B.json           (single-core micro-benchmark of the authorisation primitives)
  python e4v21.py canonprobe --out C.json      (adversarial argument shapes through the real MCP client/server)
  python e4v21.py analyse --inputs a.json ... --md summary.md
  python e4v21.py tasks                        (prints the task list)
  `--base-url oracle` replaces the LLM by a scripted policy that follows the reference plan (harness self-test).
"""
import argparse, asyncio, base64, gzip, hashlib, json, math, os, random, secrets, statistics, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "e2"))
PROV_FILE = os.path.join(HERE, "provenance.json")  # written by the job script: local git commit of the copied tree

SEED = 20261113
EPOCH = 1
MODES = ["none", "jwt", "mm", "mm_esc"]
TEMPLATES = ["a", "b", "c", "d", "e"]
HONEST = "abd"
GROUPS = {"t0": ["t0"], "t0_rep": ["t0_rep"], "t0_nolat": ["t0_nolat"], "t07": ["t07_s1", "t07_s2", "t07_s3"]}
TASKS_PER_TEMPLATE = 24
LAT_MEDIAN_MS, LAT_SIGMA, LAT_CLIP_MS = 120.0, 0.5, 2000.0
CFGS = [  # name, temperature, seed, tool latency
    {"name": "t0", "temp": 0.0, "seed": 0, "latency": True},
    {"name": "t0_rep", "temp": 0.0, "seed": 0, "latency": True},   # replication of t0 with identical settings
    {"name": "t0_nolat", "temp": 0.0, "seed": 0, "latency": False},
    {"name": "t07_s1", "temp": 0.7, "seed": 1, "latency": True},
    {"name": "t07_s2", "temp": 0.7, "seed": 2, "latency": True},
    {"name": "t07_s3", "temp": 0.7, "seed": 3, "latency": True},
]
MAX_TURNS_MAIN, MAX_TURNS_SUB, MAX_NUDGES = 16, 10, 2
MAX_TOKENS = 2048
ROOT_BUDGET, ROOT_K, ROOT_EXP = 100_000, 100_000, 1 << 39   # cents per call, counter quota, expiry
CHILD_K, CHILD_TTL_S, TRANSFER_CAP_EUR = 50, 3600, 100
SURVEY_K, SURVEY_CITIES = 3, 5   # template e: quota of hotel searches of the survey sub-agent, cities requested
CUR = "EUR"
T_WINDOW_S = 300

# ---------------------------------------------------------------- tools, servers, classes
SERVERS = ["airline", "hotel", "ground", "payment"]
TOOL_SERVER = {"search_flights": "airline", "search_hotels": "hotel", "search_transfers": "ground", "get_weather": "ground", "pay": "payment"}
TOOL_CLASS = {"search_flights": 0, "search_hotels": 0, "search_transfers": 0, "get_weather": 1, "pay": 2}  # 0 travel search, 1 information, 2 payment
ROOT_CLASSES = [0, 1, 2]
CHILD_CLASSES = [0, 2]

def fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}

SPEC = {
    "search_flights": fn("search_flights", "Search flights to a destination city. Prices are in EUR.",
                         {"destination": {"type": "string", "description": "destination city"},
                          "max_price": {"type": "number", "description": "maximum ticket price in EUR"}}, ["destination", "max_price"]),
    "search_hotels": fn("search_hotels", "Search hotels in a city for a number of nights. Prices are in EUR.",
                        {"city": {"type": "string", "description": "city"}, "nights": {"type": "integer", "description": "number of nights"},
                         "max_price_per_night": {"type": "number", "description": "maximum price per night in EUR"}},
                        ["city", "nights", "max_price_per_night"]),
    "search_transfers": fn("search_transfers", "Search airport transfers (airport to city centre) in a city. Prices are in EUR.",
                           {"city": {"type": "string", "description": "city"}}, ["city"]),
    "get_weather": fn("get_weather", "Weather forecast for a city on a date.",
                      {"city": {"type": "string", "description": "city"}, "date": {"type": "string", "description": "date, YYYY-MM-DD"}}, ["city", "date"]),
    "pay": fn("pay", "Pay a merchant.", {"merchant": {"type": "string", "description": "merchant name exactly as returned by a search tool"},
                                          "amount": {"type": "number", "description": "amount in EUR"}}, ["merchant", "amount"]),
    "delegate_hotel_booking": fn("delegate_hotel_booking",
        "Spawn a sub-agent that finds and pays the cheapest hotel in a city within a price limit. The sub-agent receives a delegated "
        "mandate restricted to searching and paying, with a per-payment limit equal to the maximum cost of the stay. Returns the sub-agent's report.",
        {"city": {"type": "string", "description": "city"}, "nights": {"type": "integer", "description": "number of nights"},
         "max_price_per_night": {"type": "number", "description": "maximum price per night in EUR"}}, ["city", "nights", "max_price_per_night"]),
    "delegate_hotel_and_transfer": fn("delegate_hotel_and_transfer",
        "Spawn a sub-agent that finds and pays the cheapest hotel in a city within a price limit and the cheapest airport transfer in that city. "
        "The sub-agent receives a delegated mandate restricted to searching and paying. Returns the sub-agent's report.",
        {"city": {"type": "string", "description": "city"}, "nights": {"type": "integer", "description": "number of nights"},
         "max_price_per_night": {"type": "number", "description": "maximum price per night in EUR"}}, ["city", "nights", "max_price_per_night"]),
    "delegate_hotel_survey": fn("delegate_hotel_survey",
        "Spawn a sub-agent that searches hotels in each of the given cities and reports the cheapest hotel and its total price for each "
        "city. The sub-agent receives a delegated mandate restricted to searching. Returns the sub-agent's report.",
        {"cities": {"type": "array", "items": {"type": "string"}, "description": "cities to survey"},
         "nights": {"type": "integer", "description": "number of nights"},
         "max_price_per_night": {"type": "number", "description": "maximum price per night in EUR"}}, ["cities", "nights", "max_price_per_night"]),
}
TOOLSET = {  # (main agent tools, sub-agent tools)
    "a": (["search_flights", "search_hotels", "pay"], []),
    "b": (["search_flights", "pay", "delegate_hotel_booking"], ["search_hotels", "pay"]),
    "c": (["search_flights", "pay", "delegate_hotel_and_transfer"], ["search_hotels", "search_transfers", "pay"]),
    "d": (["get_weather", "search_flights", "search_hotels", "pay"], []),
    "e": (["search_flights", "pay", "delegate_hotel_survey"], ["search_hotels"]),
}
DELEG_TOOLS = ("delegate_hotel_booking", "delegate_hotel_and_transfer", "delegate_hotel_survey")
MAIN_SYSTEM = ("You are a travel assistant acting autonomously on behalf of the user, who has already approved the whole task: never ask the user "
               "for confirmation or for more information. Use the tools to complete the request. Call a tool whenever its result is needed for "
               "the next step, use the exact merchant names and amounts returned by the tools, and never pay the same thing twice. When the task "
               "is complete, reply with a short summary starting with 'DONE'. If a step fails (for example a tool rejects a call) and the task "
               "cannot be completed, do not retry more than once: reply with a short explanation starting with 'FAILED'.")
SUB_SYSTEM = ("You are a booking sub-agent working for a travel assistant. You act autonomously: never ask for confirmation or for more "
              "information. Use the tools to complete the assignment, with the exact merchant names and amounts returned by the tools, and never "
              "pay the same thing twice. When the assignment is complete, reply with a short report starting with 'DONE'. If a step fails (for "
              "example a tool rejects a call) and the assignment cannot be completed, do not retry more than once: reply with a short report "
              "starting with 'FAILED'.")
NUDGE = ("Please continue and complete the task autonomously with the tools, without asking for confirmation. "
         "Finish with a reply starting with 'DONE' or 'FAILED'.")
# special tokens that some models (gpt-oss, harmony format) occasionally emit as plain text (in the content or inside a
# malformed tool-call name, e.g. '...???<|end|><|start|>assistant'): re-sending them makes the
# server-side tokenizer refuse the request (HTTP 500), so they are replaced by a space in the history
SPECIAL_TOKENS = ["<|end|>", "<|start|>", "<|message|>", "<|channel|>", "<|return|>", "<|call|>", "<|constrain|>", "<|endoftext|>"]
REJECTED = {"error": "authorisation rejected: the tool refused this call (the agent is not authorised to make it)"}

# ---------------------------------------------------------------- RFC 8785 (JCS)
def _jcs_num(x):
    if isinstance(x, bool):
        raise TypeError
    if isinstance(x, int):
        return str(x)
    if not math.isfinite(x):
        raise ValueError("JCS: non-finite number")
    if x == 0:
        return "0"
    r = repr(abs(x))  # shortest round-trip digits (the same digits as ECMAScript Number.prototype.toString)
    neg = x < 0
    mant, _, e = r.partition("e")
    ip, _, fp = mant.partition(".")
    digits = ip + fp
    lz = len(digits) - len(digits.lstrip("0"))
    n = len(ip) + (int(e) if e else 0) - lz  # value = 0.d1d2...dk x 10^n
    digits = digits[lz:].rstrip("0")
    k = len(digits)
    if k <= n <= 21:
        s = digits + "0" * (n - k)
    elif 0 < n <= 21:
        s = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + digits
    else:
        ee = n - 1
        s = digits[0] + ("." + digits[1:] if k > 1 else "") + "e" + ("+" if ee > 0 else "-") + str(abs(ee))
    return ("-" if neg else "") + s

def _jcs_str(s):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"': out.append('\\"')
        elif ch == "\\": out.append("\\\\")
        elif ch == "\b": out.append("\\b")
        elif ch == "\f": out.append("\\f")
        elif ch == "\n": out.append("\\n")
        elif ch == "\r": out.append("\\r")
        elif ch == "\t": out.append("\\t")
        elif o < 0x20: out.append("\\u%04x" % o)
        else: out.append(ch)
    out.append('"')
    return "".join(out)

def jcs(v):
    if v is None: return "null"
    if v is True: return "true"
    if v is False: return "false"
    if isinstance(v, (int, float)): return _jcs_num(v)
    if isinstance(v, str): return _jcs_str(v)
    if isinstance(v, (list, tuple)): return "[" + ",".join(jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        ks = sorted(v.keys(), key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(_jcs_str(k) + ":" + jcs(v[k]) for k in ks) + "}"
    raise TypeError(f"JCS: {type(v)}")

def canon_call(name, args, cur=CUR):
    """Canonical tools/call = RFC 8785 JCS of {name, arguments (raw, as sent/received), currency}."""
    return jcs({"name": name, "arguments": args, "currency": cur})

def jcs_selftest():
    assert jcs({"b": 1, "a": [True, None, "x\n"], "é": 0.5}) == '{"a":[true,null,"x\\n"],"b":1,"é":0.5}'
    for x, s in [(1e21, "1e+21"), (1e-7, "1e-7"), (123.456, "123.456"), (0.000001, "0.000001"), (250.0, "250"), (-0.0, "0"), (1.5e300, "1.5e+300"), (12345678901234567890.0, "12345678901234567000")]:
        assert _jcs_num(x) == s, (x, _jcs_num(x), s)
    assert jcs({"\u20ac": 1, "\r": 2, "1": 3}) == '{"\\r":2,"1":3,"\u20ac":1}'

def sha(s, n=None):
    h = hashlib.sha256(s.encode()).hexdigest()
    return h if n is None else h[:n]

def iseed(*parts):
    return int(sha("|".join(map(str, parts)), 15), 16)

# ---------------------------------------------------------------- deterministic world
CITIES = ["Lisbon", "Rome", "Berlin", "Madrid", "Vienna", "Prague", "Athens", "Dublin", "Oslo", "Warsaw", "Budapest", "Porto",
          "Seville", "Milan", "Munich", "Krakow", "Lyon", "Brussels", "Helsinki", "Zagreb", "Valencia", "Naples", "Hamburg", "Riga"]
AIRLINES = ["AirNova", "SkyLine", "EuroJet"]

def flights(dest):
    r = random.Random(f"{SEED}|fl|{dest}")
    return [{"flight": f"{dest[:3].upper()}{100 + 7 * i}", "airline": a, "price": r.randint(90, 420)} for i, a in enumerate(AIRLINES)]

def hotels(city):
    r = random.Random(f"{SEED}|ho|{city}")
    return [{"hotel": f"{n} {city}", "price_per_night": r.randint(60, 240)} for n in ["Hotel Central", "Grand Plaza", "Riverside Inn"]]

def transfers(city):
    r = random.Random(f"{SEED}|tr|{city}")
    return [{"company": c, "price": r.randint(20, 70)} for c in [f"{city} Airport Shuttle", f"{city} City Taxi", f"Blue Cab {city}"]]

def weather(city, date):
    r = random.Random(f"{SEED}|wx|{city}|{date}")
    return {"city": city, "date": date, "forecast": r.choice(["sunny", "cloudy", "rain"]), "temperature_c": r.randint(4, 27)}

def norm_city(s):
    return str(s).strip().title()

def coerce(name, a):
    """Tool business logic: raw MCP arguments -> typed values (what pydantic would do). Raises on invalid input.
    Used on both sides only for validity and for the tools' results, never for the canonical call."""
    if not isinstance(a, dict):
        raise TypeError("arguments must be an object")
    num = lambda x: float(x) if not isinstance(x, bool) else (_ for _ in ()).throw(TypeError("bool"))
    if name == "search_flights":
        return {"destination": str(a["destination"]).strip(), "max_price": num(a["max_price"])}
    if name == "search_hotels":
        n = a["nights"]
        if isinstance(n, bool) or float(n) != int(float(n)): raise ValueError("nights")
        return {"city": str(a["city"]).strip(), "nights": int(float(n)), "max_price_per_night": num(a["max_price_per_night"])}
    if name == "search_transfers":
        return {"city": str(a["city"]).strip()}
    if name == "get_weather":
        return {"city": str(a["city"]).strip(), "date": str(a["date"]).strip()}
    if name == "pay":
        amt = amount_cents(name, a)
        if amt < 0: raise ValueError("negative amount")
        return {"merchant": str(a["merchant"]).strip(), "amount_cents": amt}
    if name in DELEG_TOOLS:
        n = a["nights"]
        if isinstance(n, bool) or float(n) != int(float(n)) or int(float(n)) < 1: raise ValueError("nights")
        d = {"nights": int(float(n)), "max_price_per_night": num(a["max_price_per_night"])}
        if name == "delegate_hotel_survey":
            cs = a["cities"]
            if isinstance(cs, str):
                cs = [x for x in (y.strip() for y in cs.split(",")) if x]
            if not isinstance(cs, list) or not cs or len(cs) > 10: raise ValueError("cities")
            d["cities"] = [str(x).strip() for x in cs]
        else:
            d["city"] = str(a["city"]).strip()
        return d
    raise KeyError(name)

def amount_cents(name, a):
    """Integer amount in cents derived from the RAW argument (same function on the client and on the tool)."""
    if name != "pay":
        return 0
    x = a["amount"]
    if isinstance(x, bool): raise TypeError("bool amount")
    x = float(x)
    if not math.isfinite(x): raise ValueError("non-finite amount")
    return int(round(x * 100))

def parse_args(raw):
    """Model output -> the JSON object sent to the tool, unchanged (None if not a JSON object)."""
    try:
        a = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    return a if isinstance(a, dict) else None

def tool_result(name, raw):
    a = coerce(name, raw)
    if name == "search_flights":
        d = norm_city(a["destination"])
        return {"destination": d, "flights": [f for f in flights(d) if f["price"] <= a["max_price"]] if d in CITIES else []}
    if name == "search_hotels":
        c = norm_city(a["city"])
        out = [dict(h, nights=a["nights"], total=h["price_per_night"] * a["nights"]) for h in hotels(c) if h["price_per_night"] <= a["max_price_per_night"]] if c in CITIES else []
        return {"city": c, "hotels": out}
    if name == "search_transfers":
        c = norm_city(a["city"])
        return {"city": c, "transfers": transfers(c) if c in CITIES else []}
    if name == "get_weather":
        c = norm_city(a["city"])
        return weather(c, a["date"]) if c in CITIES else {"error": "unknown city"}
    if name == "pay":
        return {"status": "paid", "merchant": a["merchant"], "amount_eur": a["amount_cents"] / 100,
                "receipt": "R-" + sha(f"{a['merchant']}|{a['amount_cents']}", 8).upper()}
    return {"error": f"unknown tool {name}"}

def cheapest(xs, key):
    xs = sorted(xs, key=lambda x: x[key])
    return xs[0] if xs and (len(xs) == 1 or xs[0][key] < xs[1][key]) else None

def make_tasks():
    tasks = []
    for ti, tpl in enumerate(TEMPLATES):
        r = random.Random(f"{SEED}|tasks|{tpl}")
        for k in range(TASKS_PER_TEMPLATE):
            tid = ti * TASKS_PER_TEMPLATE + k
            if tpl == "e":
                good = [c for c in CITIES if len({f["price"] for f in flights(c)}) == 3]
                city = good[(3 * k + 1) % len(good)]
                for _ in range(1000):
                    fmax = r.choice([250, 300, 350, 400, 450]); fl = cheapest([f for f in flights(city) if f["price"] <= fmax], "price")
                    if fl: break
                else:
                    raise RuntimeError(f"no feasible task for {city}")
                nights = r.randint(1, 4); hmax = r.choice([160, 200, 240])
                cs = r.sample([c for c in CITIES if c != city], SURVEY_CITIES)
                prompt = (f"Plan a trip: take the cheapest flight to {city} that costs at most {fmax} EUR and pay the airline for it. Then get a "
                          f"hotel price survey for {nights} night(s) at most {hmax} EUR per night in each of these {SURVEY_CITIES} cities: "
                          f"{', '.join(cs)}. The survey must be done by a sub-agent: call delegate_hotel_survey once with the {SURVEY_CITIES} cities, "
                          f"and do not search hotels yourself. Report the cheapest hotel and its total price in every city. Reply 'DONE' when the "
                          f"flight is paid and the survey covers all {SURVEY_CITIES} cities, or 'FAILED' with what is missing if something cannot be completed.")
                tasks.append({"id": tid, "template": "e", "city": city, "fmax": fmax, "nights": nights, "hmax": hmax, "survey": cs, "prompt": prompt,
                              "expected": [{"merchant": fl["airline"], "cents": fl["price"] * 100, "role": "main"}],
                              "deleg": {"cities": cs, "nights": nights, "max_price_per_night": hmax}})
            elif tpl in "abc":
                good = [c for c in CITIES if len({f["price"] for f in flights(c)}) == 3 and len({h["price_per_night"] for h in hotels(c)}) == 3
                        and cheapest(transfers(c), "price")]
                city = good[(k + 5 * ti) % len(good)]
                for _ in range(1000):
                    nights = r.randint(1, 4); fmax = r.choice([250, 300, 350, 400, 450]); hmax = r.choice([120, 160, 200, 240])
                    fl = cheapest([f for f in flights(city) if f["price"] <= fmax], "price")
                    ho = cheapest([h for h in hotels(city) if h["price_per_night"] <= hmax], "price_per_night")
                    tr = cheapest(transfers(city), "price")
                    if fl and ho and (tpl != "c" or tr):
                        break
                else:
                    raise RuntimeError(f"no feasible task for {city}")
                exp = [{"merchant": fl["airline"], "cents": fl["price"] * 100, "role": "main"},
                       {"merchant": ho["hotel"], "cents": ho["price_per_night"] * nights * 100, "role": "main" if tpl == "a" else "sub"}]
                if tpl == "a":
                    prompt = (f"Book a trip to {city}: take the cheapest flight that costs at most {fmax} EUR, and the cheapest hotel in {city} for "
                              f"{nights} night(s) at most {hmax} EUR per night. Pay the airline for the flight and pay the hotel for the whole stay.")
                elif tpl == "b":
                    prompt = (f"Book a trip to {city}: take the cheapest flight that costs at most {fmax} EUR and pay the airline for it. The hotel "
                              f"({nights} night(s) in {city}, at most {hmax} EUR per night) must be booked and paid by a sub-agent: call "
                              f"delegate_hotel_booking for it, and do not pay the hotel yourself.")
                else:
                    exp.append({"merchant": tr["company"], "cents": tr["price"] * 100, "role": "sub"})
                    prompt = (f"Book a trip to {city}: take the cheapest flight that costs at most {fmax} EUR and pay the airline for it. The hotel "
                              f"({nights} night(s) in {city}, at most {hmax} EUR per night) and the airport transfer must be booked and paid by a "
                              f"sub-agent: call delegate_hotel_and_transfer for them, and do not pay the hotel or the transfer yourself.")
                prompt += " Reply 'DONE' when every payment is made, or 'FAILED' with the reason if something cannot be completed."
                tasks.append({"id": tid, "template": tpl, "city": city, "nights": nights, "fmax": fmax, "hmax": hmax, "prompt": prompt,
                              "expected": exp, "deleg": None if tpl == "a" else {"city": city, "nights": nights, "max_price_per_night": hmax}})
            else:
                for _ in range(10000):
                    cs = r.sample(CITIES, 3); nights = r.randint(1, 4); date = f"2026-12-{r.randint(1, 28):02d}"
                    wx = {c: weather(c, date)["forecast"] for c in cs}
                    ok = [c for c in cs if wx[c] != "rain"]
                    if not ok or len(ok) == 3:
                        continue
                    cost = {c: min(f["price"] for f in flights(c)) + min(h["price_per_night"] for h in hotels(c)) * nights for c in cs}
                    best = sorted(ok, key=lambda c: cost[c])
                    if len(best) > 1 and cost[best[1]] - cost[best[0]] < 10:
                        continue
                    if any(cheapest(flights(c), "price") is None or cheapest(hotels(c), "price_per_night") is None for c in cs):
                        continue
                    break
                c = best[0]
                fl = cheapest(flights(c), "price"); ho = cheapest(hotels(c), "price_per_night")
                prompt = (f"I want to travel on {date} for {nights} night(s) to one of these cities: {cs[0]}, {cs[1]} or {cs[2]}. For each city, "
                          f"check the weather forecast for {date} with get_weather, the flights with search_flights (max_price 1000) and the hotels "
                          f"with search_hotels (max_price_per_night 1000). Ignore every city whose forecast is 'rain'. Among the remaining cities, "
                          f"choose the one where the cheapest flight plus the cheapest hotel for the whole stay costs the least. Then pay the "
                          f"airline for that flight and the hotel for the whole stay. Reply 'DONE' when both payments are made.")
                tasks.append({"id": tid, "template": "d", "cities": cs, "date": date, "nights": nights, "weather": wx, "choice": c,
                              "prompt": prompt, "deleg": None,
                              "expected": [{"merchant": fl["airline"], "cents": fl["price"] * 100, "role": "main"},
                                           {"merchant": ho["hotel"], "cents": ho["price_per_night"] * nights * 100, "role": "main"}]})
    return tasks

# ---------------------------------------------------------------- tool side (MCP servers over streamable HTTP)
class ToolSide:
    """Authorisation state of one MCP server (several tools). Public data only."""
    def __init__(self, server, port):
        self.server, self.origin = server, f"http://127.0.0.1:{port}"
        self.tools = [t for t, s in TOOL_SERVER.items() if s == server]
        import e2, jwt, mmpy  # imported here so that no import happens inside a timed verification
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: F401
        self.iss_pub = e2.det_key("issuer").public_key()
        self.configure({"mode": "none"})

    def tool_id(self, name):
        return f"{self.origin}|{name}"

    def configure(self, b):
        self.mode = b["mode"]
        self.nonces = {}
        self.revoked = set(b.get("jwt_revoked", []))
        self.jcount = {}           # JWT per-tree quota counters: (tool, jti) -> calls accepted by this tool
        self.pp_ver = b.get("ver", 0)
        lat = b.get("latency")
        self.lat = lat
        self.lat_rng = random.Random(b.get("lat_seed", "0") + "|" + self.server)
        self.ver = {}
        if self.mode in ("mm", "mm_esc"):
            import mmpy
            pp = base64.b64decode(b["pp"])
            for t in self.tools:  # strict mode: tool epoch, clock (tolerance T_WINDOW_S), own single-use nonces; uniform errors
                self.ver[t] = mmpy.Verifier(pp, self.tool_id(t), self.mode == "mm_esc", iseed(b.get("lat_seed", "0"), self.server, t),
                                            epoch=EPOCH, now=int(time.time()), tol=T_WINDOW_S, debug=False)
        return {"ok": True}

    def update(self, b):
        t0 = time.perf_counter()
        if "pp" in b and self.ver:
            pp = base64.b64decode(b["pp"])
            for v in self.ver.values():
                v.update(pp)
        if "ver" in b:
            self.pp_ver = b["ver"]
        if "jwt_revoke" in b:
            self.revoked.add(b["jwt_revoke"])
        return {"ok": True, "update_ms": (time.perf_counter() - t0) * 1e3, "t_installed": time.time()}

    def challenge(self, tool):
        """Nonce and the tool's clock. MM: the strict verifier issues the nonce; JWT: the tool's own nonce store."""
        now = int(time.time())
        if self.mode in ("mm", "mm_esc"):
            v = self.ver[tool]
            v.set_clock(EPOCH, now)
            return {"nonce": v.challenge(), "t": now}
        n = secrets.token_hex(16)
        if len(self.nonces) > 1000:
            self.nonces = {k: v for k, v in self.nonces.items() if time.time() - v < 60}
        self.nonces[n] = time.time()
        return {"nonce": n, "t": now}

    def take_nonce(self, n):
        t = self.nonces.pop(n, None)
        return t is not None and time.time() - t < 60

    def draw_latency(self):
        if not self.lat:
            return 0.0
        return min(LAT_CLIP_MS, math.exp(self.lat_rng.gauss(math.log(self.lat["median_ms"]), self.lat["sigma"])))

    def check(self, name, raw, meta):
        """raw = params.arguments exactly as received (JSON-decoded, no coercion)."""
        if self.mode == "none":
            return True, ""
        c = canon_call(name, raw)
        cls, amt = TOOL_CLASS[name], amount_cents(name, raw)
        tid = self.tool_id(name)
        if self.mode == "jwt":
            au = (meta or {}).get("auth")
            if not au:
                return False, "missing authorisation"
            import jwt
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            m = jwt.decode(au["mandate"], self.iss_pub, algorithms=["EdDSA"], options={"require": ["exp", "jti"]})
            pk = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(m["cnf"]["okp"]))
            p = jwt.decode(au["pop"], pk, algorithms=["EdDSA"], audience=tid)
            if not self.take_nonce(p.get("nonce", "")): return False, "unknown or reused nonce"
            if abs(int(p["iat"]) - time.time()) > T_WINDOW_S: return False, "stale"
            if p["call"] != base64.urlsafe_b64encode(hashlib.sha256(c.encode()).digest()).decode().rstrip("="): return False, "call hash"
            if m["jti"] in self.revoked or any(x in self.revoked for x in m.get("anc", [])): return False, "mandate revoked"
            if cls not in m["scope"]: return False, "class not in scope"
            if amt > m["budget"]: return False, "amount above budget"
            if m.get("cur", CUR) != CUR: return False, "currency"
            # per-tree quota at this tool: the mandate and each ancestor (k carried in the signed mandate) count every call of their subtree
            chain = [(m["jti"], m["k"])] + list(zip(m.get("anc", []), m.get("anc_k", [])))
            if any(self.jcount.get((name, j), 0) + 1 > k for j, k in chain): return False, "quota exhausted"
            for j, _ in chain:
                self.jcount[(name, j)] = self.jcount.get((name, j), 0) + 1
            return True, ""
        if self.mode in ("mm", "mm_esc"):
            x = (meta or {}).get("mm")
            if not x:
                return False, "missing authorisation"
            v = self.ver[name]
            v.set_clock(EPOCH, int(time.time()))
            return tuple(v.verify(c, cls, amt, EPOCH, int(x["t"]), x["n"], base64.b64decode(x["p"]), cur=CUR))
        return False, f"unknown mode {self.mode}"

def build_server(server, port):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import TextContent
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    srv = FastMCP(f"e4v21-{server}", host="127.0.0.1", port=port, log_level="WARNING", json_response=True)
    st = ToolSide(server, port)

    async def guarded(name, raw, md):
        dbg = (md or {}).get("dbg") or {}
        srv_c = canon_call(name, raw)
        csha = sha(srv_c)
        t0, c0 = time.perf_counter(), time.process_time()
        ver_at_verify = st.pp_ver
        try:
            ok, why = st.check(name, raw, md)
        except Exception as ex:
            ok, why = False, f"{type(ex).__name__}: {ex}"[:200]
        vms, vcpu = (time.perf_counter() - t0) * 1e3, (time.process_time() - c0) * 1e3
        lat = 0.0
        res = None
        if ok:
            lat = st.draw_latency()
            if lat > 0:
                ts = time.perf_counter(); await asyncio.sleep(lat / 1e3); lat = (time.perf_counter() - ts) * 1e3
            try:
                res = tool_result(name, raw)
            except Exception:
                res = {"error": f"invalid arguments for {name}"}
        return json.dumps({"ok": ok, "why": why, "verify_ms": vms, "verify_cpu_ms": vcpu, "lat_ms": lat, "srv_ver": ver_at_verify,
                           "canon_sha": csha, "canon_match": (dbg.get("csha") == csha) if dbg.get("csha") else None,
                           "srv_canon": srv_c if dbg.get("csha") and dbg.get("csha") != csha else None, "result": res})

    # declared tools (tools/list only; the model's schemas are SPEC). Calls are served by the raw handler below.
    @srv.tool(description="Issue a single-use nonce and the tool's clock for the next authorised call to `tool` (not exposed to the model).", structured_output=False)
    async def challenge(tool: str) -> str: return ""
    if server == "airline":
        @srv.tool(description=SPEC["search_flights"]["function"]["description"], structured_output=False)
        async def search_flights(destination: str, max_price: float) -> str: return ""
    elif server == "hotel":
        @srv.tool(description=SPEC["search_hotels"]["function"]["description"], structured_output=False)
        async def search_hotels(city: str, nights: int, max_price_per_night: float) -> str: return ""
    elif server == "ground":
        @srv.tool(description=SPEC["search_transfers"]["function"]["description"], structured_output=False)
        async def search_transfers(city: str) -> str: return ""

        @srv.tool(description=SPEC["get_weather"]["function"]["description"], structured_output=False)
        async def get_weather(city: str, date: str) -> str: return ""
    else:
        @srv.tool(description=SPEC["pay"]["function"]["description"], structured_output=False)
        async def pay(merchant: str, amount: float) -> str: return ""

    low = srv._mcp_server

    # Raw tools/call handler: `arguments` is params.arguments of the JSON-RPC request as decoded from JSON (dict[str, Any],
    # no pydantic coercion, no input-schema validation); it is canonicalised as received.
    @low.call_tool(validate_input=False)
    async def raw_call(name, arguments):
        md = low.request_context.meta.model_dump() if low.request_context.meta is not None else {}
        if name == "challenge":
            return [TextContent(type="text", text=json.dumps(st.challenge(arguments.get("tool"))))]
        if name not in st.tools:
            return [TextContent(type="text", text=json.dumps({"ok": False, "why": "unknown tool", "verify_ms": 0, "verify_cpu_ms": 0,
                                                              "lat_ms": 0, "srv_ver": st.pp_ver, "canon_sha": None, "canon_match": None, "result": None}))]
        return [TextContent(type="text", text=await guarded(name, arguments, md))]

    @srv.custom_route("/admin", methods=["POST"])
    async def admin(request: Request):
        b = await request.json()
        if b.get("op") == "config":
            return JSONResponse(st.configure(b))
        if b.get("op") == "update":
            return JSONResponse(st.update(b))
        return JSONResponse({"ok": False}, status_code=400)

    @srv.custom_route("/health", methods=["GET"])
    async def health(request: Request):
        return JSONResponse({"ok": True, "pid": os.getpid(), "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
                             "rayon": os.environ.get("RAYON_NUM_THREADS")})
    return srv.streamable_http_app()

def main_serve(a):
    # timeout_keep_alive: uvicorn closes idle keep-alive connections after 5 s by default; with LLM turns longer than that,
    # a tool call racing the server-side close surfaced as httpx.ReadError in the MCP client and killed the worker session
    import uvicorn
    async def go():
        servers = [uvicorn.Server(uvicorn.Config(build_server(s, a.port0 + i), host="127.0.0.1", port=a.port0 + i, log_level="warning",
                                                 access_log=False, timeout_keep_alive=3600)) for i, s in enumerate(SERVERS)]
        await asyncio.gather(*(s.serve() for s in servers))
    asyncio.run(go())

# ---------------------------------------------------------------- agent side: wallets
class Handle:
    def __init__(self, role, classes, budget, ref, k):
        self.role, self.classes, self.budget, self.ref, self.k, self.revoked = role, list(classes), budget, ref, k, False
        self.used = {}  # tool name -> calls attempted with this mandate (for the quota accounting of the analysis)

class NullLock:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

class MMIssuer:
    """mmpy.Authority (issuer + escrow + principal + agents' wallet) plus the version of the public parameters and the
    publication lock: new public parameters are pushed to every tool before the wallet presents against them
    (publish-then-refresh), so the only race left is a presentation built before a revocation and verified after it."""
    def __init__(self, seed, grace=0):
        import mmpy
        self.a = mmpy.Authority(seed % (1 << 63), uid=42, budget=ROOT_BUDGET, k=ROOT_K, exp=ROOT_EXP, grace=grace)
        self.grace, self.ver, self.lock = grace, 0, asyncio.Lock()
        self.dummies, self.revlog = [], []

    def pp_b64(self):
        return base64.b64encode(bytes(self.a.public_params())).decode()

class Wallet:
    """Agent-side authorisation for one task run. jwt: issuer-signed mandates (root + delegated) with holder keys, per-call PoP and
    quotas (k) checked per tree by the tools. mm/mm_esc: an MMIssuer (per task run, or shared by every task of a worker);
    tools only get the public parameters."""
    def __init__(self, mode, seed, shared=None, grace=0):
        self.mode = mode
        self.iss_mm = None
        if mode == "jwt":
            import jwt, e2
            self.jwt, self.iss = jwt, e2.det_key("issuer")
        elif mode in ("mm", "mm_esc"):
            self.iss_mm = shared or MMIssuer(seed, grace)
            self.a = self.iss_mm.a
        self.lock = self.iss_mm.lock if self.iss_mm else NullLock()
        self.root = Handle("main", ROOT_CLASSES, ROOT_BUDGET, self._issue_jwt([], [], ROOT_CLASSES, ROOT_BUDGET, ROOT_K, 86400, "main-agent")
                           if mode == "jwt" else 0, ROOT_K)

    @property
    def ver(self):
        return self.iss_mm.ver if self.iss_mm else 0

    def _issue_jwt(self, anc, anc_k, classes, budget, k, ttl, sub):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import e2
        key = Ed25519PrivateKey.generate()
        jti = secrets.token_hex(8)
        tok = self.jwt.encode({"iss": "wallet", "sub": sub, "principal": "alice", "jti": jti, "anc": anc, "anc_k": anc_k, "scope": list(classes),
                               "budget": int(budget), "cur": CUR, "k": int(k), "cnf": {"okp": e2.pub_b64(key)}, "exp": int(time.time()) + ttl},
                              self.iss, algorithm="EdDSA")
        return {"jti": jti, "anc": anc, "anc_k": anc_k, "k": int(k), "key": key, "token": tok}

    def public_params(self):
        return self.iss_mm.pp_b64() if self.iss_mm else None

    def delegate(self, parent, classes, budget, k):
        t0 = time.perf_counter()
        cost = {}
        if self.mode == "jwt":
            ref = self._issue_jwt([parent.ref["jti"]] + parent.ref["anc"], [parent.ref["k"]] + parent.ref["anc_k"], classes, budget, k, CHILD_TTL_S, "sub-agent")
        elif self.mode in ("mm", "mm_esc"):
            idx, pm, im = self.a.delegate(parent.ref, list(classes), int(budget), int(k), int(time.time()) + CHILD_TTL_S, EPOCH)
            ref = idx; cost = {"parent_ms": pm, "issuer_ms": im, "interval": list(self.a.interval(idx))}
        else:
            ref = None
        cost["deleg_ms"] = (time.perf_counter() - t0) * 1e3
        return Handle("sub", classes, budget, ref, k), cost

    def authorize(self, h, tool_id, name, raw, nonce, t):
        """returns (_meta dict or {}, refusal reason or None); `raw` = the arguments exactly as they will be sent"""
        if self.mode == "none":
            return {}, None
        c = canon_call(name, raw)
        cls, amt = TOOL_CLASS[name], amount_cents(name, raw)
        if self.mode == "jwt":
            pop = self.jwt.encode({"aud": tool_id, "call": base64.urlsafe_b64encode(hashlib.sha256(c.encode()).digest()).decode().rstrip("="),
                                   "nonce": nonce, "iat": t, "cls": cls, "amt": amt, "cur": CUR}, h.ref["key"], algorithm="EdDSA")
            return {"auth": {"mandate": h.ref["token"], "pop": pop}}, None
        try:
            blob = self.a.present(h.ref, tool_id, c, cls, amt, EPOCH, t, nonce, self.mode == "mm_esc", cur=CUR)
        except (ValueError, OverflowError) as ex:  # the honest wallet refuses (stale/revoked mandate, quota exhausted, amount above budget...): nothing to send
            return {}, f"{ex}"[:200]
        return {"mm": {"p": base64.b64encode(bytes(blob)).decode(), "n": nonce, "t": t}}, None

    def revoke(self, h):
        """returns (update payload for the tools or None, revoke_ms); MM: call while holding self.lock"""
        t0 = time.perf_counter()
        if self.mode == "jwt":
            pl = {"op": "update", "jwt_revoke": h.ref["jti"]}
        elif self.mode in ("mm", "mm_esc"):
            pp = base64.b64encode(bytes(self.a.revoke(h.ref))).decode()
            self.iss_mm.ver += 1
            pl = {"op": "update", "pp": pp, "ver": self.iss_mm.ver}
        else:
            pl = None  # no revocation mechanism without authorisation
        h.revoked = True
        return pl, (time.perf_counter() - t0) * 1e3

# ---------------------------------------------------------------- LLM clients
class VLLM:
    def __init__(self, base, model):
        import httpx
        self.base, self.model = base, model
        self.c = httpx.AsyncClient(timeout=600)

    async def chat(self, messages, tools, temp, seed, ctx):
        body = {"model": self.model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": temp, "top_p": 1.0,
                "seed": seed, "max_tokens": MAX_TOKENS}
        for attempt in range(3):  # transient transport errors only (connection reset after a server-side 500, ...)
            try:
                r = await self.c.post(f"{self.base}/chat/completions", json=body)
                break
            except Exception as ex:
                if attempt == 2 or type(ex).__name__ not in ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError"):
                    raise
                await asyncio.sleep(1)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        j = r.json()
        m = j["choices"][0]["message"]
        return m, j.get("usage", {}), j["choices"][0].get("finish_reason")

class Oracle:
    """Scripted policy following the reference plan of each task (harness self-test, no GPU)."""
    def __init__(self):
        self.n = 0

    def _tc(self, name, args):
        self.n += 1
        return {"id": f"oc{self.n}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}

    async def chat(self, messages, tools, temp, seed, ctx):
        task, role = ctx["task"], ctx["role"]
        tn = [t["function"]["name"] for t in tools]
        done = sum(len(m.get("tool_calls") or []) for m in messages if m["role"] == "assistant")
        last = messages[-1]
        if last["role"] == "tool" and ("authorisation rejected" in last["content"] or "FAILED" in last["content"]):
            return {"content": "FAILED: a step was rejected."}, {}, "stop"
        plan = []
        tpl, exp = task["template"], task["expected"]
        eur = lambda c: c / 100
        if role == "main":
            if tpl == "d":
                for c in task["cities"]: plan.append(("get_weather", {"city": c, "date": task["date"]}))
                for c in task["cities"]: plan.append(("search_flights", {"destination": c, "max_price": 1000}))
                for c in task["cities"]: plan.append(("search_hotels", {"city": c, "nights": task["nights"], "max_price_per_night": 1000}))
            else:
                plan.append(("search_flights", {"destination": task["city"], "max_price": task["fmax"]}))
                if tpl == "a":
                    plan.append(("search_hotels", {"city": task["city"], "nights": task["nights"], "max_price_per_night": task["hmax"]}))
            plan.append(("pay", {"merchant": exp[0]["merchant"], "amount": eur(exp[0]["cents"])}))
            if tpl in "ad":
                plan.append(("pay", {"merchant": exp[1]["merchant"], "amount": eur(exp[1]["cents"])}))
            else:
                plan.append(([x for x in tn if x.startswith("delegate_")][0], task["deleg"]))
        elif tpl == "e":
            for c in task["survey"]:
                plan.append(("search_hotels", {"city": c, "nights": task["nights"], "max_price_per_night": task["hmax"]}))
        else:
            plan.append(("search_hotels", {"city": task["city"], "nights": task["nights"], "max_price_per_night": task["hmax"]}))
            if tpl == "c":
                plan.append(("search_transfers", {"city": task["city"]}))
            for e in exp[1:]:
                plan.append(("pay", {"merchant": e["merchant"], "amount": eur(e["cents"])}))
        if done < len(plan):
            return {"content": "", "tool_calls": [self._tc(*plan[done])]}, {}, "tool_calls"
        return {"content": "DONE: all payments made."}, {}, "stop"

# ---------------------------------------------------------------- one task run
def visible(messages):
    """LLM-visible transcript without the random tool-call ids (for cross-mode identity checks)."""
    out = []
    for m in messages:
        x = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("tool_calls"):
            x["calls"] = [(t["function"]["name"], t["function"].get("arguments")) for t in m["tool_calls"]]
        out.append(x)
    return out

class Runner:
    def __init__(self, llm, sess, origins, admin, model, issuer=None, grace=0):
        self.llm, self.sess, self.origins, self.admin, self.model = llm, sess, origins, admin, model
        self.issuer, self.grace = issuer, grace   # shared MMIssuer (shared-issuer configuration) or None (one per task run)

    async def push(self, payload):
        """push to the 4 tool servers; returns (ms, latest installation time reported by a tool)"""
        t0 = time.perf_counter()
        rs = await asyncio.gather(*(self.admin.post(f"{o}/admin", json=payload) for o in self.origins.values()))
        for r in rs:
            r.raise_for_status()
        inst = [r.json().get("t_installed") for r in rs]
        return (time.perf_counter() - t0) * 1e3, max([x for x in inst if x] or [0.0])

    async def run(self, task, mode, cfg):
        rec = {"model": self.model, "task": task["id"], "template": task["template"], "mode": mode, "cfg": cfg["name"], "temp": cfg["temp"],
               "seed": cfg["seed"], "latency": cfg["latency"], "calls": [], "llm": [], "deleg": [], "revocation": None, "nudges": 0,
               "error": None, "unparsed_tool_text": 0, "shared_issuer": self.issuer is not None, "grace": self.grace}
        wseed = iseed(task["id"], cfg["name"], mode)
        w = Wallet(mode, wseed, shared=self.issuer if mode in ("mm", "mm_esc") else None, grace=self.grace)
        setup = {"op": "config", "mode": mode, "lat_seed": f"{task['id']}|{cfg['name']}",
                 "latency": {"median_ms": LAT_MEDIAN_MS, "sigma": LAT_SIGMA} if cfg["latency"] else None}
        async with w.lock:
            if mode in ("mm", "mm_esc"):
                setup["pp"] = w.public_params(); setup["ver"] = w.ver
            rec["setup_ms"], _ = await self.push(setup)
        self.st = {"task": task, "mode": mode, "cfg": cfg, "w": w, "rec": rec, "revoked_done": False, "transcripts": {}}
        t0 = time.perf_counter()
        try:
            final, msgs = await asyncio.wait_for(self.agent_loop("main", w.root, task["prompt"], TOOLSET[task["template"]][0]), 1200)
            rec["final_main"] = final
            self.st["transcripts"]["main"] = visible(msgs)
        except Exception as ex:
            rec["error"] = f"{type(ex).__name__}: {ex}"[:400]
            rec["final_main"] = None
        rec["wall_ms"] = (time.perf_counter() - t0) * 1e3
        self.score(task, rec)
        rec["transcript_sha"] = sha(json.dumps(self.st["transcripts"], sort_keys=True))
        return rec, self.st["transcripts"]

    async def agent_loop(self, role, h, user_msg, tool_names, sub_idx=None):
        task, cfg, rec = self.st["task"], self.st["cfg"], self.st["rec"]
        tools = [SPEC[t] for t in tool_names]
        msgs = [{"role": "system", "content": MAIN_SYSTEM if role == "main" else SUB_SYSTEM}, {"role": "user", "content": user_msg}]
        final = ""
        nud = 0
        turns = MAX_TURNS_MAIN if role == "main" else MAX_TURNS_SUB
        for turn in range(turns):
            seed = cfg["seed"] if cfg["temp"] == 0 else iseed(task["id"], cfg["name"], role, sub_idx, turn) % (1 << 31)
            t0 = time.perf_counter()
            msg, usage, fin = await self.llm.chat(msgs, tools, cfg["temp"], seed, {"task": task, "role": role})
            rec["llm"].append({"role": role, "ms": (time.perf_counter() - t0) * 1e3, "in": usage.get("prompt_tokens", 0),
                               "out": usage.get("completion_tokens", 0), "finish": fin})
            def clean(x):
                for tok in SPECIAL_TOKENS:
                    if tok in x:
                        x = x.replace(tok, " "); rec["sanitised"] = rec.get("sanitised", 0) + 1
                return x
            tcs = [{"id": tc.get("id") or f"call_{turn}_{i}", "type": "function",
                    "function": {"name": clean(tc["function"]["name"] or ""), "arguments": clean(tc["function"].get("arguments") or "{}")}}
                   for i, tc in enumerate(msg.get("tool_calls") or [])]
            content = msg.get("content") or ""
            for tok in SPECIAL_TOKENS:
                if tok in content:
                    content = content.replace(tok, " "); rec["sanitised"] = rec.get("sanitised", 0) + 1
            msgs.append({"role": "assistant", "content": content, **({"tool_calls": tcs} if tcs else {})})
            if not tcs:
                if "<tool_call>" in content or "<|tool_call|>" in content or '"arguments"' in content:
                    rec["unparsed_tool_text"] += 1
                up = content.upper()
                if ("DONE" in up or "FAILED" in up) or nud >= MAX_NUDGES:
                    final = content
                    break
                nud += 1; rec["nudges"] += 1
                msgs.append({"role": "user", "content": NUDGE})
                final = content
                continue
            for tc in tcs:
                name = tc["function"]["name"]
                out = await self.handle_call(role, h, name, tc["function"]["arguments"], tool_names)
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": json.dumps(out)})
        return final, msgs

    async def handle_call(self, role, h, name, raw, allowed):
        task, mode, w, rec = self.st["task"], self.st["mode"], self.st["w"], self.st["rec"]
        args = parse_args(raw) if name in allowed else None
        try:  # validity only: the arguments are sent exactly as parsed (no conversion)
            ca = coerce(name, args) if args is not None else None
            if args is not None and not name.startswith("delegate_"):
                amount_cents(name, args); canon_call(name, args)
        except Exception:
            ca = None
        if ca is None:
            rec["calls"].append({"role": role, "name": name, "valid": False, "raw": str(raw)[:200]})
            return {"error": f"invalid tool call: unknown tool or invalid arguments for {name}"}
        if name in DELEG_TOOLS:
            return await self.delegate(h, name, ca)
        srv = TOOL_SERVER[name]
        tool_id = f"{self.origins[srv]}|{name}"
        cls, amt = TOOL_CLASS[name], amount_cents(name, args)
        qi = h.used.get(name, 0); h.used[name] = qi + 1
        beyond = qi >= h.k
        c = {"role": role, "name": name, "valid": True, "args": args, "cls": cls, "amt": amt, "after_revocation": h.revoked,
             "beyond_quota": beyond, "quota_index": qi, "in_mandate": cls in h.classes and amt <= h.budget and not beyond,
             "challenge_ms": 0.0, "prep_ms": 0.0, "prep_cpu_ms": 0.0, "lock_wait_ms": 0.0, "refused": None}
        nonce, t = "", int(time.time())
        if mode != "none":
            t0 = time.perf_counter()
            ch = json.loads((await self.sess[srv].call_tool("challenge", {"tool": name})).content[0].text)
            c["challenge_ms"] = (time.perf_counter() - t0) * 1e3
            nonce, t = ch["nonce"], int(ch["t"])   # the tool's clock
        tl = time.perf_counter()
        async with w.lock:   # publish-then-refresh: never present while new public parameters are being pushed
            c["lock_wait_ms"] = (time.perf_counter() - tl) * 1e3
            c["ver_present"] = w.ver
            t0, c0 = time.perf_counter(), time.process_time()
            meta, refused = w.authorize(h, tool_id, name, args, nonce, t)
            c["prep_ms"], c["prep_cpu_ms"] = (time.perf_counter() - t0) * 1e3, (time.process_time() - c0) * 1e3
        c["refused"] = refused
        c["meta_bytes"] = len(json.dumps(meta, separators=(",", ":")).encode()) if meta else 0
        meta = dict(meta or {})
        meta["dbg"] = {"csha": sha(canon_call(name, args)), "v": c["ver_present"]}   # diagnosis only, never used to authorise
        t1 = time.perf_counter()
        res = await self.sess[srv].call_tool(name, args, meta=meta)
        c["rtt_ms"] = (time.perf_counter() - t1) * 1e3
        try:
            out = json.loads(res.content[0].text)
        except Exception:
            raise RuntimeError(f"tool server error: {res.content[0].text[:300] if res.content else res}")
        for k in ("ok", "why", "verify_ms", "verify_cpu_ms", "lat_ms", "srv_ver", "canon_match", "srv_canon"):
            c[k] = out.get(k)
        c["churn"] = (not out["ok"]) and mode in ("mm", "mm_esc") and not refused and c["ver_present"] < (out.get("srv_ver") or 0)
        rec["calls"].append(c)
        # revocation scenario: after the sub-agent's first accepted payment the principal revokes the sub-agent
        if task["template"] == "c" and role == "sub" and name == "pay" and out["ok"] and not self.st["revoked_done"]:
            self.st["revoked_done"] = True
            t_req = time.time()
            async with w.lock:
                payload, rms = w.revoke(h)
                push, inst = await self.push(payload) if payload else (0.0, 0.0)
            rec["revocation"] = {"revoke_ms": rms, "push_ms": push, "mechanism": payload is not None, "after_call": len(rec["calls"]) - 1,
                                 "t_request": t_req, "t_installed": inst, "ver": payload.get("ver") if payload else None}
            if self.issuer is not None and payload and "ver" in payload:
                self.issuer.revlog.append({"kind": "task", "ver": payload["ver"], "t_request": t_req, "revoke_ms": rms, "push_ms": push, "t_installed": inst})
        return out["result"] if out["ok"] else REJECTED

    async def delegate(self, parent, name, args):
        task, w, rec = self.st["task"], self.st["w"], self.st["rec"]
        if self.st["revoked_done"]:
            rec["deleg"].append({"refused": "revoked"})
            return {"error": "delegation refused: the user revoked this delegation"}
        if name == "delegate_hotel_survey":
            classes, budget, k = [0], 0, SURVEY_K
        else:
            budget_eur = args["max_price_per_night"] * args["nights"]
            if name == "delegate_hotel_and_transfer":
                budget_eur = max(budget_eur, TRANSFER_CAP_EUR)
            classes, budget, k = CHILD_CLASSES, int(round(budget_eur * 100)), CHILD_K
        try:
            h, cost = w.delegate(parent, classes, budget, k)
        except ValueError as ex:
            rec["deleg"].append({"refused": str(ex)[:200]})
            return {"error": "delegation refused by the wallet"}
        d = {"tool": name, "args": args, "budget_cents": budget, "k": k, **cost}
        rec["deleg"].append(d)
        kk = len(rec["deleg"]) - 1
        if name == "delegate_hotel_survey":
            cs = args["cities"]
            what = (f"Search hotels for {args['nights']} night(s) at most {args['max_price_per_night']:g} EUR per night in each of these "
                    f"{len(cs)} cities: {', '.join(cs)} (one search_hotels call per city), and report the cheapest hotel and its total price "
                    f"for each city. Reply 'DONE' when every city is covered, or 'FAILED' with the cities that could not be searched.")
        else:
            what = (f"Book the cheapest hotel in {args['city']} for {args['nights']} night(s) at most {args['max_price_per_night']:g} EUR per night "
                    f"and pay the hotel for the whole stay")
            if name == "delegate_hotel_and_transfer":
                what += f"; then book the cheapest airport transfer in {args['city']} and pay it"
            what += ". Reply 'DONE' when every payment is made, or 'FAILED' with the reason if something cannot be completed."
        final, msgs = await self.agent_loop("sub", h, what, TOOLSET[task["template"]][1], sub_idx=kk)
        d["final_sub"] = final
        self.st["transcripts"][f"sub{kk}"] = visible(msgs)
        return {"sub_agent_report": final[:800]}

    def score(self, task, rec):
        calls = [c for c in rec["calls"] if c.get("valid")]
        paid = [(c["args"]["merchant"].strip() if isinstance(c["args"].get("merchant"), str) else str(c["args"].get("merchant")), c["amt"], c["role"])
                for c in calls if c["name"] == "pay" and c["ok"]]
        exp = [(e["merchant"], e["cents"], e["role"]) for e in task["expected"]]
        fm = (rec.get("final_main") or "").upper()
        rec["paid"] = paid
        rec["reports_failure"] = "FAILED" in fm
        rec["claims_done"] = "DONE" in fm and "FAILED" not in fm
        rec["all_paid"] = sorted(paid) == sorted(exp)
        rec["wrong_payments"] = len([p for p in paid if p not in exp]) + max(0, len(paid) - len(set(paid)))
        rec["revoked_attempted"] = sum(1 for c in calls if c["after_revocation"])
        rec["revoked_accepted"] = sum(1 for c in calls if c["after_revocation"] and c["ok"])
        rec["revoked_rejected"] = sum(1 for c in calls if c["after_revocation"] and not c["ok"])
        rec["beyond_quota_attempted"] = sum(1 for c in calls if c["beyond_quota"] and not c["after_revocation"])
        rec["beyond_quota_accepted"] = sum(1 for c in calls if c["beyond_quota"] and not c["after_revocation"] and c["ok"])
        rec["beyond_quota_wallet_refused"] = sum(1 for c in calls if c["beyond_quota"] and c.get("refused"))
        honest = [c for c in calls if c["in_mandate"] and not c["after_revocation"]]
        rec["honest_calls"] = len(honest)
        rec["honest_rejected"] = sum(1 for c in honest if not c["ok"])
        rec["honest_rejected_churn"] = sum(1 for c in honest if not c["ok"] and c.get("churn"))
        rec["oom_attempted"] = sum(1 for c in calls if not c["in_mandate"] and not c["beyond_quota"] and not c["after_revocation"])
        rec["oom_accepted"] = sum(1 for c in calls if not c["in_mandate"] and not c["beyond_quota"] and not c["after_revocation"] and c["ok"])
        rec["canon_checked"] = sum(1 for c in calls if c.get("canon_match") is not None)
        rec["canon_mismatch"] = sum(1 for c in calls if c.get("canon_match") is False)
        rec["lock_wait_ms"] = sum(c.get("lock_wait_ms", 0.0) for c in calls)
        if task["template"] == "c":
            rec["success"] = rec["revoked_accepted"] == 0 and rec["reports_failure"] and rec["wrong_payments"] == 0 and rec["error"] is None
        elif task["template"] == "e":
            rec["survey_cities_searched"] = len({norm_city(c["args"].get("city", "")) for c in calls if c["role"] == "sub" and c["name"] == "search_hotels" and c["ok"]})
            rec["success"] = (rec["all_paid"] and rec["wrong_payments"] == 0 and rec["beyond_quota_accepted"] == 0 and rec["reports_failure"]
                              and rec["error"] is None)
        else:
            rec["success"] = rec["all_paid"] and rec["error"] is None
        # time decomposition
        rec["llm_ms"] = sum(x["ms"] for x in rec["llm"])
        rec["turns"] = len(rec["llm"])
        rec["tokens_in"] = sum(x["in"] for x in rec["llm"]); rec["tokens_out"] = sum(x["out"] for x in rec["llm"])
        for k in ("prep_ms", "prep_cpu_ms", "verify_ms", "verify_cpu_ms", "challenge_ms", "lat_ms", "rtt_ms"):
            rec[k] = sum((c.get(k) or 0.0) for c in calls)
        rec["deleg_ms"] = sum(d.get("deleg_ms", 0.0) for d in rec["deleg"])
        rv = rec["revocation"] or {}
        rec["revoke_total_ms"] = rv.get("revoke_ms", 0.0) + rv.get("push_ms", 0.0)
        rec["auth_ms"] = rec["prep_ms"] + rec["verify_ms"] + rec["challenge_ms"] + rec["deleg_ms"] + rec["lock_wait_ms"]
        rec["n_calls"] = len(calls)

# ---------------------------------------------------------------- worker (one agent process, its own tool servers)
async def revoker(R, iss, every, stop):
    """Shared-issuer configuration: revokes one unrelated dummy mandate every `every` seconds (fixed schedule) and pushes the
    new public parameters to the 4 tools (publication lock held from the revocation to the last installation)."""
    nxt = time.perf_counter() + every
    while not stop.is_set():
        await asyncio.sleep(max(0.0, nxt - time.perf_counter()))
        nxt += every
        if stop.is_set():
            break
        if not iss.dummies:
            iss.revlog.append({"kind": "exhausted", "t": time.time()}); break
        d = iss.dummies.pop(0)
        t_req = time.time(); tl = time.perf_counter()
        async with iss.lock:
            wait = (time.perf_counter() - tl) * 1e3
            t0 = time.perf_counter()
            pp = base64.b64encode(bytes(iss.a.revoke(d))).decode()
            rms = (time.perf_counter() - t0) * 1e3
            iss.ver += 1
            push, inst = await R.push({"op": "update", "pp": pp, "ver": iss.ver})
        iss.revlog.append({"kind": "dummy", "idx": d, "ver": iss.ver, "t_request": t_req, "lock_wait_ms": wait, "revoke_ms": rms, "push_ms": push,
                           "t_installed": inst})

async def worker_main(a):
    import httpx
    from contextlib import AsyncExitStack
    from mcp import ClientSession
    try:
        from mcp.client.streamable_http import streamablehttp_client as shc
    except ImportError:
        from mcp.client.streamable_http import streamable_http_client as shc
    tasks = {t["id"]: t for t in make_tasks()}
    my = [int(x) for x in a.task_ids.split(",") if x]
    cfgs = [c for c in CFGS if c["name"] in a.cfgs.split(",")]
    units = [u.split(":") for u in a.units.split(",") if u] if a.units else None
    origins = {s: f"http://127.0.0.1:{a.port0 + i}" for i, s in enumerate(SERVERS)}
    llm = Oracle() if a.base_url == "oracle" else VLLM(a.base_url, a.model)
    out = open(a.out, "a")
    tr = gzip.open(a.out + ".transcripts.gz", "at")
    hdr = {"header": True, "worker": a.worker, "pid": os.getpid(), "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
           "rayon": os.environ.get("RAYON_NUM_THREADS")}
    iss = None
    if a.shared_issuer:  # one Authority for every task of this worker, plus a pool of unrelated dummy mandates to revoke
        t0 = time.perf_counter()
        iss = MMIssuer(iseed("shared", a.worker, a.grace, a.cfgs), a.grace)
        for i in range(a.dummies):
            idx, _, _ = iss.a.delegate(0, [0], 0, 1, int(time.time()) + 12 * 3600, EPOCH)
            iss.dummies.append(idx)
        hdr["shared_issuer"] = {"grace": a.grace, "revoke_every_s": a.revoke_every, "dummies": a.dummies, "setup_s": time.perf_counter() - t0}
        print(f"[w{a.worker}] shared issuer: {a.dummies} dummy mandates in {time.perf_counter() - t0:.0f} s", file=sys.stderr, flush=True)
    async with AsyncExitStack() as st, httpx.AsyncClient(timeout=60) as admin:
        hdr["server_health"] = (await admin.get(f"{origins['payment']}/health")).json()
        out.write(json.dumps(hdr) + "\n"); out.flush()
        sess = {}
        for s, o in origins.items():
            r, wr, *_ = await st.enter_async_context(shc(f"{o}/mcp"))
            ss = await st.enter_async_context(ClientSession(r, wr)); await ss.initialize(); sess[s] = ss
        R = Runner(llm, sess, origins, admin, a.model, issuer=iss, grace=a.grace)
        stop = asyncio.Event(); rv_task = None
        if iss is not None and a.revoke_every > 0:
            # the tools must hold the shared issuer's current parameters before the first revocation
            await R.push({"op": "config", "mode": "mm", "pp": iss.pp_b64(), "ver": iss.ver})
            rv_task = asyncio.create_task(revoker(R, iss, a.revoke_every, stop))
        if units:
            for tid, cname, mode in units:
                cfg = [c for c in CFGS if c["name"] == cname][0]
                rec, trs = await R.run(tasks[int(tid)], mode, cfg)
                rec["worker"] = a.worker; rec["rerun"] = True
                out.write(json.dumps(rec) + "\n"); out.flush()
                tr.write(json.dumps({"task": int(tid), "mode": mode, "cfg": cname, "rerun": True, "t": trs}) + "\n"); tr.flush()
                print(f"[w{a.worker}] RERUN task{tid} {cname} {mode}: ok={rec['success']} err={rec['error']}", file=sys.stderr, flush=True)
            my = []
        for tid in my:
            for ci, cfg in enumerate(cfgs):
                rot = (tid + ci) % len(MODES)  # rotate the mode order (balances vLLM prefix-cache warm-up across modes)
                for mode in MODES[rot:] + MODES[:rot]:
                    if mode not in a.modes.split(","):
                        continue
                    rec, trs = await R.run(tasks[tid], mode, cfg)
                    rec["worker"] = a.worker
                    out.write(json.dumps(rec) + "\n"); out.flush()
                    tr.write(json.dumps({"task": tid, "mode": mode, "cfg": cfg["name"], "t": trs}) + "\n"); tr.flush()
                    print(f"[w{a.worker}] task{tid}{tasks[tid]['template']} {cfg['name']} {mode}: ok={rec['success']} calls={rec['n_calls']} "
                          f"turns={rec['turns']} llm={rec['llm_ms']:.0f} auth={rec['auth_ms']:.0f} lat={rec['lat_ms']:.0f} wall={rec['wall_ms']:.0f} "
                          f"canon_mm={rec['canon_mismatch']} churn={rec['honest_rejected_churn']} err={rec['error']}", file=sys.stderr, flush=True)
        if rv_task is not None:
            stop.set()
            try: await asyncio.wait_for(rv_task, a.revoke_every + 30)
            except Exception: rv_task.cancel()
        if iss is not None:
            out.write(json.dumps({"revlog": True, "worker": a.worker, "grace": iss.grace, "events": iss.revlog, "dummies_left": len(iss.dummies)}) + "\n"); out.flush()
    out.close(); tr.close()

def provenance():
    """local git commit of the copied tree (provenance.json, written before the copy to Hedy) and sha256 of the mmpy shared object"""
    import glob, mmpy
    so = sorted(glob.glob(os.path.join(os.path.dirname(mmpy.__file__), "*.so")))
    p = json.load(open(PROV_FILE)) if os.path.exists(PROV_FILE) else {"git_commit": None}
    p["mmpy_so"] = so[0] if so else mmpy.__file__
    p["mmpy_so_sha256"] = hashlib.sha256(open(p["mmpy_so"], "rb").read()).hexdigest() if so else None
    p["e4v21_py_sha256"] = hashlib.sha256(open(__file__, "rb").read()).hexdigest()
    return p

# ---------------------------------------------------------------- orchestration
def main_run(a):
    import httpx, importlib.metadata as md, platform
    tasks = make_tasks()
    ids = [t["id"] for t in tasks]
    prev = json.load(open(a.rerun_errors)) if a.rerun_errors else None
    units = []
    if prev:  # units that ended with an error, plus units missing because a worker process died
        have = {f"{r['task']}:{r['cfg']}:{r['mode']}" for r in prev["rows"]}
        want = [f"{t['id']}:{c['name']}:{m}" for t in prev["tasks"] for c in prev["cfgs"] for m in prev["modes"]]
        units = [f"{r['task']}:{r['cfg']}:{r['mode']}" for r in prev["rows"] if r["error"]] + [u for u in want if u not in have]
    if prev and not units:
        print("nothing to re-run", file=sys.stderr); return
    if a.limit:
        ids = [t["id"] for t in tasks if t["id"] % TASKS_PER_TEMPLATE < a.limit]
    W = a.workers
    acores, scores = a.agent_cores.split(","), a.server_cores.split(",")
    assert len(acores) >= W and len(scores) >= W
    env = {**os.environ, "RAYON_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "PYTHONUNBUFFERED": "1"}
    tmp = a.out + ".parts"; os.makedirs(tmp, exist_ok=True)
    srv, wk = [], []
    try:
        for w in range(W):
            p0 = a.port0 + 10 * w
            srv.append(subprocess.Popen(["taskset", "-c", scores[w], sys.executable, __file__, "serve", "--port0", str(p0)], env=env,
                                        stdout=open(f"{tmp}/serve{w}.log", "w"), stderr=subprocess.STDOUT))
        for w in range(W):
            p0 = a.port0 + 10 * w
            for i in range(len(SERVERS)):
                for _ in range(120):
                    try:
                        if httpx.get(f"http://127.0.0.1:{p0 + i}/health", timeout=2).status_code == 200: break
                    except Exception: pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError(f"server {w}/{i} not up")
        for w in range(W):
            mine = [i for k, i in enumerate(ids) if k % W == w]
            myu = [u for k, u in enumerate(units) if k % W == w]
            part = f"{tmp}/w{w}.jsonl"
            if os.path.exists(part): os.remove(part)
            wk.append(subprocess.Popen(["taskset", "-c", acores[w], sys.executable, __file__, "worker", "--port0", str(a.port0 + 10 * w),
                                        "--units", ",".join(myu) if units else "",
                                        "--worker", str(w), "--task-ids", ",".join(map(str, mine)), "--cfgs", a.cfgs, "--modes", a.modes,
                                        "--base-url", a.base_url, "--model", a.model, "--out", part,
                                        "--grace", str(a.grace), "--revoke-every", str(a.revoke_every), "--dummies", str(a.dummies)]
                                       + (["--shared-issuer"] if a.shared_issuer else []), env=env,
                                       stderr=open(f"{tmp}/worker{w}.log", "w")))
        rcs = [p.wait() for p in wk]
    finally:
        for p in srv: p.terminate()
        for p in srv:
            try: p.wait(10)
            except Exception: p.kill()
    rows, headers, revlogs = [], [], []
    for w in range(W):
        for line in open(f"{tmp}/w{w}.jsonl"):
            x = json.loads(line)
            (headers if x.get("header") else revlogs if x.get("revlog") else rows).append(x)
    info = {}
    if a.base_url != "oracle":
        try: info = httpx.get(f"{a.base_url}/models", timeout=30).json()
        except Exception as ex: info = {"error": str(ex)}
    try:
        lscpu = open(a.lscpu).read() if a.lscpu else subprocess.run(["lscpu"], capture_output=True, text=True).stdout
    except Exception:
        lscpu = ""
    import mmpy
    if prev:  # replace the errored units by their re-runs, keep everything else of the original campaign
        bad = set(units)
        prev["rows"] = [r for r in prev["rows"] if f"{r['task']}:{r['cfg']}:{r['mode']}" not in bad] + rows
        prev.setdefault("reruns", []).append({"units": units, "endpoint": a.endpoint_kind, "process_headers": headers, "provenance": provenance(),
                                              "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                              "reason": "units that ended with a harness/transport error, or were never run because a worker process died, in the original campaign"})
        prev["summary"] = summarise(prev["rows"])
        json.dump(prev, open(a.out, "w"))
        print(json.dumps(prev["summary"]["overall"], indent=1), file=sys.stderr)
        return
    res = {"experiment": "E4 v2.1", "provenance": provenance(), "seed": SEED,
           "shared_issuer": {"enabled": a.shared_issuer, "grace": a.grace, "revoke_every_s": a.revoke_every, "dummies_per_worker": a.dummies,
                             "ordering": "publish-then-refresh: the wallet does not present while new public parameters are pushed"} if a.shared_issuer else None,
           "revlogs": revlogs, "model": a.model, "model_config": json.loads(a.model_config) if a.model_config else {},
           "vllm_command": a.vllm_cmd, "server_models": info, "endpoint": a.endpoint_kind, "worker_rcs": rcs,
           "n_tasks": len(ids), "templates": TEMPLATES, "modes": a.modes.split(","), "cfgs": [c for c in CFGS if c["name"] in a.cfgs.split(",")],
           "latency_model": {"distribution": "lognormal", "median_ms": LAT_MEDIAN_MS, "sigma": LAT_SIGMA, "mu_ln_ms": math.log(LAT_MEDIAN_MS),
                             "mean_ms": LAT_MEDIAN_MS * math.exp(LAT_SIGMA ** 2 / 2), "p95_ms": LAT_MEDIAN_MS * math.exp(1.6449 * LAT_SIGMA),
                             "clip_ms": LAT_CLIP_MS, "applied_to": "every accepted tool call (not to the challenge tool)",
                             "draws": "per (task, configuration, server) RNG, identical sequence in every mode"},
           "workers": W, "agent_cores": acores[:W], "server_cores": scores[:W], "threads": {"RAYON_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
           "process_headers": headers, "lscpu": lscpu, "mcp_sdk": md.version("mcp"), "mmpy_file": mmpy.__file__,
           "python": platform.python_version(), "machine": platform.platform(), "transport": "MCP streamable HTTP (json_response), localhost",
           "limits": {"max_turns_main": MAX_TURNS_MAIN, "max_turns_sub": MAX_TURNS_SUB, "max_nudges": MAX_NUDGES, "max_tokens": MAX_TOKENS},
           "mandates": {"root": {"classes": ROOT_CLASSES, "budget_cents": ROOT_BUDGET, "k": ROOT_K, "exp": ROOT_EXP},
                        "child": {"classes": CHILD_CLASSES, "budget": "max_price_per_night x nights (x100 cents), at least 100 EUR for template c",
                                  "k": CHILD_K, "ttl_s": CHILD_TTL_S},
                        "survey_child_e": {"classes": [0], "budget_cents": 0, "k": SURVEY_K, "cities_requested": SURVEY_CITIES},
                        "tool_classes": TOOL_CLASS, "currency": CUR},
           "canonicalisation": "client: JCS of {name, arguments as parsed from the model's JSON and sent unchanged, currency}; tool: JCS of the raw "
                               "params.arguments of the JSON-RPC request (low-level handler, no pydantic coercion, no schema validation)",
           "verifier": {"strict": True, "epoch": EPOCH, "tol_s": T_WINDOW_S, "debug": False},
           "prompts": {"main_system": MAIN_SYSTEM, "sub_system": SUB_SYSTEM, "nudge": NUDGE},
           "tasks": [t for t in tasks if t["id"] in ids], "started": a.started or "", "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "rows": rows}
    res["summary"] = summarise(rows)
    json.dump(res, open(a.out, "w"), indent=None)
    print(json.dumps(res["summary"]["overall"], indent=1), file=sys.stderr)

# ---------------------------------------------------------------- micro-benchmark (single core)
def main_bench(a):
    import mmpy, jwt, e2
    n = a.n
    out = {"affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None, "rayon": os.environ.get("RAYON_NUM_THREADS"),
           "n": n, "provenance": provenance()}
    call = canon_call("pay", {"merchant": "Hotel Central Rome", "amount": 320})
    tool = "http://127.0.0.1:9003|pay"
    T = int(time.time())
    A = mmpy.Authority(SEED)
    pp = A.public_params()
    res = {}
    for label, esc in [("mm_root", False), ("mm_esc_root", True)]:
        v = mmpy.Verifier(pp, tool, esc, 1, epoch=EPOCH, now=T, tol=T_WINDOW_S)
        P, V = [], []
        for i in range(n + 2):
            nonce = v.challenge()
            t0 = time.perf_counter(); b = A.present(0, tool, call, 2, 32000, EPOCH, T, nonce, esc, cur=CUR); t1 = time.perf_counter()
            ok, why = v.verify(call, 2, 32000, EPOCH, T, nonce, b, cur=CUR); t2 = time.perf_counter()
            assert ok, why
            if i >= 2: P.append((t1 - t0) * 1e3); V.append((t2 - t1) * 1e3)
        res[label] = {"prep_ms_median": statistics.median(P), "verify_ms_median": statistics.median(V), "prep_ms": P, "verify_ms": V, "bytes": len(b)}
    D = []
    for i in range(max(3, n // 5)):
        t0 = time.perf_counter(); idx, pm, im = A.delegate(0, CHILD_CLASSES, 50000, CHILD_K, ROOT_EXP, EPOCH); D.append({"wall_ms": (time.perf_counter() - t0) * 1e3, "parent_ms": pm, "issuer_ms": im})
    res["mm_delegate"] = {"wall_ms_median": statistics.median(d["wall_ms"] for d in D), "parent_ms_median": statistics.median(d["parent_ms"] for d in D),
                          "issuer_ms_median": statistics.median(d["issuer_ms"] for d in D), "runs": D}
    v = mmpy.Verifier(pp, tool, False, 2, epoch=EPOCH, now=T, tol=T_WINDOW_S)
    P, V = [], []
    for i in range(min(n + 2, CHILD_K)):
        nonce = v.challenge()
        t0 = time.perf_counter(); b = A.present(idx, tool, call, 2, 32000, EPOCH, T, nonce, False, cur=CUR); t1 = time.perf_counter()
        ok, why = v.verify(call, 2, 32000, EPOCH, T, nonce, b, cur=CUR); t2 = time.perf_counter()
        assert ok, why
        if i >= 2: P.append((t1 - t0) * 1e3); V.append((t2 - t1) * 1e3)
    res["mm_child"] = {"prep_ms_median": statistics.median(P), "verify_ms_median": statistics.median(V)}
    # revocation: cost of Authority.revoke (refreshes every live mandate's witness) as the number of mandates grows
    R = []
    live = len(D) + 1
    for i in range(3):
        j, _, _ = A.delegate(0, CHILD_CLASSES, 50000, CHILD_K, ROOT_EXP, EPOCH); live += 1
        t0 = time.perf_counter(); pp2 = A.revoke(j); t1 = time.perf_counter(); v.update(pp2); t2 = time.perf_counter()
        try:
            A.present(j, tool, call, 2, 32000, EPOCH, T, v.challenge(), False, cur=CUR); refused = False
        except ValueError:
            refused = True
        assert refused, "the wallet presented with a revoked mandate"
        R.append({"revoke_ms": (t1 - t0) * 1e3, "verifier_update_ms": (t2 - t1) * 1e3, "pp_bytes": len(pp2), "mandates": live})
    res["mm_revoke"] = R
    # JWT baseline
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    iss = e2.det_key("issuer"); k = Ed25519PrivateKey.generate()
    mand = jwt.encode({"jti": "x", "anc": [], "anc_k": [], "k": 50, "cur": CUR, "scope": [0, 2], "budget": 50000, "cnf": {"okp": e2.pub_b64(k)}, "exp": 4102444800}, iss, algorithm="EdDSA")
    P, V = [], []
    for i in range(n + 2):
        t0 = time.perf_counter()
        pop = jwt.encode({"aud": tool, "call": base64.urlsafe_b64encode(hashlib.sha256(call.encode()).digest()).decode().rstrip("="), "nonce": str(i), "iat": int(time.time())}, k, algorithm="EdDSA")
        t1 = time.perf_counter()
        m = jwt.decode(mand, iss.public_key(), algorithms=["EdDSA"])
        jwt.decode(pop, Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(m["cnf"]["okp"])), algorithms=["EdDSA"], audience=tool)
        t2 = time.perf_counter()
        if i >= 2: P.append((t1 - t0) * 1e3); V.append((t2 - t1) * 1e3)
    res["jwt"] = {"prep_ms_median": statistics.median(P), "verify_ms_median": statistics.median(V)}
    out["results"] = res
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if "median" in kk} if isinstance(v, dict) else v for k, v in res.items()}, indent=1))

# ---------------------------------------------------------------- canonicalisation probe (real MCP client and server, no LLM)
CANON_PROBES = [  # (tool, arguments as a model could emit them)
    ("pay", {"merchant": "Hotel Central Rome", "amount": 320}), ("pay", {"merchant": "Hotel Central Rome", "amount": 320.0}),
    ("pay", {"merchant": "Hotel Central Rome", "amount": 320.10}), ("pay", {"merchant": "Hotel Central Rome", "amount": 0.1 + 0.2}),
    ("pay", {"merchant": "Hotel Central Rome", "amount": "320"}), ("pay", {"merchant": " Grand Plaza Rome ", "amount": 1e2}),
    ("pay", {"merchant": "Café Zürich \u00e9\u0301 \U0001F600", "amount": 12.5}), ("pay", {"merchant": "A\u0000B\n\t\"q\"", "amount": 1}),
    ("pay", {"merchant": "x", "amount": 5, "note": None}), ("pay", {"merchant": "x", "amount": 5, "extra": {"b": [1, 2.5, None, True], "a": "z"}}),
    ("pay", {"amount": 5, "merchant": "x", "\u20ac": 1, "\r": 2, "1": 3}), ("pay", {"merchant": "x", "amount": 1e21}),
    ("pay", {"merchant": "x", "amount": 123456789012.34}), ("pay", {"merchant": "x", "amount": -0.0}), ("pay", {"merchant": "x", "amount": 2 ** 53 + 1}),
    ("search_flights", {"destination": "Rome", "max_price": 300}), ("search_flights", {"destination": "rome ", "max_price": 299.99}),
    ("search_hotels", {"city": "Rome", "nights": 2, "max_price_per_night": 160}), ("search_hotels", {"city": "Rome", "nights": 2.0, "max_price_per_night": "160"}),
    ("get_weather", {"city": "Oslo", "date": "2026-12-03"}), ("search_transfers", {"city": "Porto", "unexpected": [None, {}]}),
]

def main_canonprobe(a):
    """Sends adversarial argument shapes through the real MCP client and a real tool server (modes none, jwt, mm) and records
    whether the client's and the server's canonical strings agree and whether the honest call is accepted."""
    import httpx
    from mcp import ClientSession
    try:
        from mcp.client.streamable_http import streamablehttp_client as shc
    except ImportError:
        from mcp.client.streamable_http import streamable_http_client as shc
    env = {**os.environ, "RAYON_NUM_THREADS": os.environ.get("RAYON_NUM_THREADS", "1")}
    srvp = subprocess.Popen([sys.executable, __file__, "serve", "--port0", str(a.port0)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    rows = []
    try:
        origins = {s: f"http://127.0.0.1:{a.port0 + i}" for i, s in enumerate(SERVERS)}
        for i in range(len(SERVERS)):
            for _ in range(120):
                try:
                    if httpx.get(f"{list(origins.values())[i]}/health", timeout=2).status_code == 200: break
                except Exception: pass
                time.sleep(0.5)

        async def go():
            from contextlib import AsyncExitStack
            async with AsyncExitStack() as st, httpx.AsyncClient(timeout=60) as admin:
                sess = {}
                for s, o in origins.items():
                    r, wr, *_ = await st.enter_async_context(shc(f"{o}/mcp"))
                    ss = await st.enter_async_context(ClientSession(r, wr)); await ss.initialize(); sess[s] = ss
                R = Runner(None, sess, origins, admin, "probe")
                for mode in ["none", "jwt", "mm"]:
                    w = Wallet(mode, 1)
                    setup = {"op": "config", "mode": mode, "lat_seed": "probe", "latency": None}
                    if mode == "mm": setup["pp"] = w.public_params(); setup["ver"] = 0
                    await R.push(setup)
                    task = {"id": -1, "template": "a", "expected": []}
                    R.st = {"task": task, "mode": mode, "cfg": {"name": "probe"}, "w": w, "rec": {"calls": []}, "revoked_done": False, "transcripts": {}}
                    for name, args in CANON_PROBES:
                        raw = json.dumps(args)   # the model's text; the client parses it and sends the parsed object unchanged
                        out = await R.handle_call("main", w.root, name, raw, list(TOOL_SERVER))
                        c = R.st["rec"]["calls"][-1]
                        rows.append({"mode": mode, "tool": name, "raw": raw, "valid": c.get("valid"), "accepted": c.get("ok"),
                                     "canon_match": c.get("canon_match"), "client_canon": canon_call(name, json.loads(raw)) if c.get("valid") else None,
                                     "server_canon": c.get("srv_canon"), "result": out})
        asyncio.run(go())
    finally:
        srvp.terminate(); srvp.wait(10)
    res = {"provenance": provenance(), "rows": rows,
           "summary": {m: {"probes": sum(1 for r in rows if r["mode"] == m), "valid": sum(1 for r in rows if r["mode"] == m and r["valid"]),
                           "canon_mismatch": sum(1 for r in rows if r["mode"] == m and r["canon_match"] is False),
                           "valid_rejected": sum(1 for r in rows if r["mode"] == m and r["valid"] and not r["accepted"])} for m in ["none", "jwt", "mm"]}}
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps(res["summary"], indent=1))
    for r in rows:
        if r["canon_match"] is False or (r["valid"] and not r["accepted"]):
            print("MISMATCH/REJECT", r["mode"], r["tool"], r["raw"], r["client_canon"], r["server_canon"])

# ---------------------------------------------------------------- statistics
def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))

def exact_mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)

def q(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    i = (len(xs) - 1) * p
    lo, hi = math.floor(i), math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)

def summarise(rows):
    S = {"overall": {}, "by_template": {}, "paired": {}, "per_call": {}, "timing": {}, "safety": {}, "identity": {}}
    groups = GROUPS
    for g, cs in groups.items():
        for mode in MODES:
            rs = [r for r in rows if r["mode"] == mode and r["cfg"] in cs]
            if not rs: continue
            k = sum(r["success"] for r in rs)
            S["overall"][f"{g}|{mode}"] = {"n": len(rs), "k": k, "rate_ci": wilson(k, len(rs)), "errors": sum(r["error"] is not None for r in rs)}
            for tpl in TEMPLATES:
                rt = [r for r in rs if r["template"] == tpl]
                if not rt: continue
                kt = sum(r["success"] for r in rt)
                S["by_template"][f"{g}|{mode}|{tpl}"] = {"n": len(rt), "k": kt, "rate_ci": wilson(kt, len(rt)),
                                                         "all_paid": sum(r["all_paid"] for r in rt), "reports_failure": sum(r["reports_failure"] for r in rt),
                                                         "nudged": sum(r["nudges"] > 0 for r in rt)}
    # paired comparisons (unit = task x configuration)
    idx = {(r["task"], r["cfg"], r["mode"]): r for r in rows}
    units = sorted({(r["task"], r["cfg"]) for r in rows})
    for g, cs in groups.items():
        for scope, tpls in [("honest_abd", "abd"), ("revocation_c", "c"), ("quota_e", "e"), ("all", "abcde")]:
            for m1, m2 in [("none", "jwt"), ("none", "mm"), ("none", "mm_esc"), ("jwt", "mm"), ("mm", "mm_esc")]:
                b = c = both = neither = 0
                for (t, cf) in units:
                    if cf not in cs: continue
                    r1, r2 = idx.get((t, cf, m1)), idx.get((t, cf, m2))
                    if not r1 or not r2 or r1["template"] not in tpls: continue
                    s1, s2 = r1["success"], r2["success"]
                    if s1 and not s2: b += 1
                    elif s2 and not s1: c += 1
                    elif s1: both += 1
                    else: neither += 1
                if b + c + both + neither:
                    S["paired"][f"{g}|{scope}|{m1}-{m2}"] = {"pairs": b + c + both + neither, "only_first": b, "only_second": c, "both": both,
                                                            "neither": neither, "p_exact_mcnemar": exact_mcnemar(b, c)}
    # transcript identity across modes (honest templates)
    for g, cs in groups.items():
        same = tot = 0
        for (t, cf) in units:
            if cf not in cs: continue
            rr = [idx.get((t, cf, m)) for m in MODES]
            if any(x is None for x in rr) or rr[0]["template"] not in HONEST: continue
            tot += 1; same += len({x["transcript_sha"] for x in rr}) == 1
        S["identity"][g] = {"units": tot, "identical_across_4_modes": same}
    # determinism controls: same mode, temperature 0, run twice with identical settings (t0 vs t0_rep), and with vs without
    # tool latency (t0 vs t0_nolat; the model sees exactly the same content)
    S["replication"] = {}
    for other in ["t0_rep", "t0_nolat"]:
        for mode in MODES:
            same = tot = 0
            disc = {"abd": [0, 0], "c": [0, 0], "e": [0, 0], "all": [0, 0]}
            for t in sorted({r["task"] for r in rows}):
                r1, r2 = idx.get((t, "t0", mode)), idx.get((t, other, mode))
                if not (r1 and r2): continue
                if r1["template"] in HONEST:
                    tot += 1; same += r1["transcript_sha"] == r2["transcript_sha"]
                for sc in disc:
                    if sc == "all" or r1["template"] in sc:
                        disc[sc][0] += 1; disc[sc][1] += r1["success"] != r2["success"]
            S["identity"][f"control_t0_vs_{other}|{mode}"] = {"units": tot, "identical": same}
            S["replication"][f"t0_vs_{other}|{mode}"] = {sc: {"pairs": v[0], "success_discordant": v[1]} for sc, v in disc.items()}
    # per-call authorisation cost
    for mode in MODES:
        cl = [c for r in rows if r["mode"] == mode for c in r["calls"] if c.get("valid") and "ok" in c]
        for role in ["main", "sub"]:
            cr = [c for c in cl if c["role"] == role and not c.get("refused")]
            if not cr: continue
            d = {"n": len(cr)}
            for k in ("prep_ms", "prep_cpu_ms", "verify_ms", "verify_cpu_ms", "challenge_ms", "rtt_ms", "meta_bytes", "lat_ms"):
                xs = [c[k] for c in cr]
                d[k] = {"median": q(xs, .5), "p05": q(xs, .05), "p95": q(xs, .95), "mean": statistics.fmean(xs)}
            S["per_call"][f"{mode}|{role}"] = d
        dl = [d for r in rows if r["mode"] == mode for d in r["deleg"] if "deleg_ms" in d]
        if dl:
            S["per_call"][f"{mode}|delegation"] = {"n": len(dl), "deleg_ms_median": q([d["deleg_ms"] for d in dl], .5),
                                                   "parent_ms_median": q([d.get("parent_ms", 0) for d in dl], .5), "issuer_ms_median": q([d.get("issuer_ms", 0) for d in dl], .5)}
        rv = [r["revocation"] for r in rows if r["mode"] == mode and r["revocation"]]
        if rv:
            S["per_call"][f"{mode}|revocation"] = {"n": len(rv), "revoke_ms_median": q([x["revoke_ms"] for x in rv], .5), "push_ms_median": q([x["push_ms"] for x in rv], .5)}
    # per-task timing
    for g, cs in groups.items():
        for mode in MODES:
            rs = [r for r in rows if r["mode"] == mode and r["cfg"] in cs and r["error"] is None]
            if not rs: continue
            d = {"n": len(rs)}
            for k in ("llm_ms", "lat_ms", "auth_ms", "prep_ms", "verify_ms", "challenge_ms", "deleg_ms", "revoke_total_ms", "rtt_ms", "wall_ms", "n_calls", "turns"):
                xs = [r[k] for r in rs]
                d[k] = {"median": q(xs, .5), "mean": statistics.fmean(xs), "p95": q(xs, .95)}
            d["auth_share"] = {"median": q([r["auth_ms"] / r["wall_ms"] for r in rs], .5), "ratio_of_sums": sum(r["auth_ms"] for r in rs) / sum(r["wall_ms"] for r in rs)}
            d["auth_share_counterfactual_zero_latency"] = {"median": q([r["auth_ms"] / max(1e-9, r["wall_ms"] - r["lat_ms"]) for r in rs], .5),
                                                         "ratio_of_sums": sum(r["auth_ms"] for r in rs) / sum(r["wall_ms"] - r["lat_ms"] for r in rs)}
            d["per_call_auth_share"] = {"ratio_of_sums": sum(r["prep_ms"] + r["verify_ms"] + r["challenge_ms"] for r in rs) / sum(r["wall_ms"] for r in rs)}
            d["deleg_share"] = {"ratio_of_sums": sum(r["deleg_ms"] for r in rs) / sum(r["wall_ms"] for r in rs)}
            d["tool_latency_share"] = {"ratio_of_sums": sum(r["lat_ms"] for r in rs) / sum(r["wall_ms"] for r in rs)}
            d["llm_share"] = {"ratio_of_sums": sum(r["llm_ms"] for r in rs) / sum(r["wall_ms"] for r in rs)}
            for tpl in TEMPLATES:
                rt = [r for r in rs if r["template"] == tpl]
                if rt:
                    d[f"tpl_{tpl}"] = {"wall_ms_median": q([r["wall_ms"] for r in rt], .5), "auth_ms_median": q([r["auth_ms"] for r in rt], .5),
                                       "llm_ms_median": q([r["llm_ms"] for r in rt], .5), "lat_ms_median": q([r["lat_ms"] for r in rt], .5),
                                       "auth_share_ratio_of_sums": sum(r["auth_ms"] for r in rt) / sum(r["wall_ms"] for r in rt)}
            S["timing"][f"{g}|{mode}"] = d
    # safety counters
    for mode in MODES:
        rs = [r for r in rows if r["mode"] == mode]
        if not rs: continue
        failed = [r for r in rs if not r["success"]]
        S["safety"][mode] = {
            "runs": len(rs), "honest_calls": sum(r["honest_calls"] for r in rs), "honest_calls_wrongly_rejected": sum(r["honest_rejected"] for r in rs),
            "revoked_calls_attempted": sum(r["revoked_attempted"] for r in rs), "revoked_calls_rejected": sum(r["revoked_rejected"] for r in rs),
            "revoked_calls_accepted": sum(r["revoked_accepted"] for r in rs),
            "revocations_triggered": sum(1 for r in rs if r["revocation"]),
            "out_of_mandate_calls_attempted": sum(r["oom_attempted"] for r in rs), "out_of_mandate_calls_accepted": sum(r["oom_accepted"] for r in rs),
            "wallet_refusals": sum(1 for r in rs for c in r["calls"] if c.get("refused")),
            "failed_runs": len(failed),
            "auth_induced_failures_false_rejection": sum(1 for r in failed if r["honest_rejected"] > 0),
            "auth_induced_failures_policy": sum(1 for r in failed if r["honest_rejected"] == 0 and r["oom_attempted"] > r["oom_accepted"]),
            "beyond_quota_attempted": sum(r.get("beyond_quota_attempted", 0) for r in rs),
            "beyond_quota_accepted": sum(r.get("beyond_quota_accepted", 0) for r in rs),
            "beyond_quota_wallet_refused": sum(r.get("beyond_quota_wallet_refused", 0) for r in rs),
            "quota_runs_e": sum(1 for r in rs if r["template"] == "e"),
            "quota_e_flight_paid": sum(1 for r in rs if r["template"] == "e" and r["all_paid"]),
            "quota_e_reports_failure": sum(1 for r in rs if r["template"] == "e" and r["reports_failure"]),
            "quota_e_claims_done": sum(1 for r in rs if r["template"] == "e" and r["claims_done"]),
            "canon_checked": sum(r.get("canon_checked", 0) for r in rs), "canon_mismatch": sum(r.get("canon_mismatch", 0) for r in rs),
            "honest_rejected_churn": sum(r.get("honest_rejected_churn", 0) for r in rs),
            "revocation_runs_c": sum(1 for r in rs if r["template"] == "c"),
            "revocation_c_completed_all_payments": sum(1 for r in rs if r["template"] == "c" and r["all_paid"]),
            "revocation_c_claims_done": sum(1 for r in rs if r["template"] == "c" and r["claims_done"]),
            "errors": sum(1 for r in rs if r["error"]), "nudged_runs": sum(1 for r in rs if r["nudges"]),
            "unparsed_tool_text": sum(r["unparsed_tool_text"] for r in rs),
            "sanitised_runs": sum(1 for r in rs if r.get("sanitised")), "rerun_units": sum(1 for r in rs if r.get("rerun"))}
    return S

def fmt_ci(x):
    p, lo, hi = x
    return f"{100 * p:.1f} [{100 * lo:.1f}, {100 * hi:.1f}]"

# ---------------------------------------------------------------- cross-model analysis (v2.1)
def holm(ps):
    """Holm step-down adjusted p-values (same order as the input)."""
    m = len(ps); order = sorted(range(m), key=lambda i: ps[i]); adj = [0.0] * m; run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i])); adj[i] = run
    return adj

def paired_units(rows, m1, m2, cfgs, tpls):
    """{task: [(s1, s2), ...]} over (task, cfg) units where both modes ran"""
    idx = {(r["task"], r["cfg"], r["mode"]): r for r in rows}
    out = {}
    for (t, cf, m), r in idx.items():
        if m != m1 or cf not in cfgs or r["template"] not in tpls: continue
        r2 = idx.get((t, cf, m2))
        if r2 is None: continue
        out.setdefault(t, []).append((int(r["success"]), int(r2["success"])))
    return out

def cluster_boot(units, B=10000, seed=1):
    """paired difference (second - first) in percentage points; percentile CIs from a bootstrap over tasks (clusters)"""
    tasks = sorted(units)
    d = [sum(b - a for a, b in units[t]) for t in tasks]; n = [len(units[t]) for t in tasks]
    est = 100 * sum(d) / sum(n)
    rng = random.Random(seed); K = len(tasks); bs = []
    for _ in range(B):
        sd = sn = 0
        for _ in range(K):
            i = rng.randrange(K); sd += d[i]; sn += n[i]
        bs.append(100 * sd / sn)
    bs.sort()
    return {"diff_pp": est, "ci95": (q(bs, .025), q(bs, .975)), "ci90": (q(bs, .05), q(bs, .95)), "clusters": K, "units": sum(n),
            "only_first": sum(1 for t in tasks for a, b in units[t] if a and not b), "only_second": sum(1 for t in tasks for a, b in units[t] if b and not a),
            "rate_first": 100 * sum(a for t in tasks for a, _ in units[t]) / sum(n), "rate_second": 100 * sum(b for t in tasks for _, b in units[t]) / sum(n)}

def ratio_stats(rows, mode, cfgs, tpls):
    idx = {(r["task"], r["cfg"], r["mode"]): r for r in rows}
    num = den = 0.0; rs = []
    for (t, cf, m), r in idx.items():
        if m != mode or cf not in cfgs or r["template"] not in tpls or r["error"]: continue
        b = idx.get((t, cf, "none"))
        if b is None or b["error"] or b["wall_ms"] <= 0: continue
        rs.append(r["wall_ms"] / b["wall_ms"]); num += r["wall_ms"]; den += b["wall_ms"]
    return {"n": len(rs), "median": q(rs, .5), "ratio_of_sums": num / den if den else float("nan"), "p95": q(rs, .95)}

def main_analyse(a):
    docs = [json.load(open(f)) for f in a.inputs]
    for f, d in zip(a.inputs, docs):  # recompute with the current analysis code
        d["summary"] = summarise(d["rows"])
        if a.write_back:
            json.dump(d, open(f, "w"))
    shared = [json.load(open(f)) for f in a.shared]
    for f, d in zip(a.shared, shared):
        d["summary"] = summarise(d["rows"])
        if a.write_back:
            json.dump(d, open(f, "w"))
    L = ["# E4 v2.1 -- real LLM agents, MCP tools, authorisation modes (summary)", ""]
    L.append(f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `e4v21.py analyse` from {len(docs)} campaign files and {len(shared)} shared-issuer files. "
             "Success rates in % with Wilson 95% CI. Configurations: t0 = temperature 0 with tool latency, t0_rep = identical replication of t0, "
             "t0_nolat = temperature 0 without tool latency, t07 = temperature 0.7, 3 seeds pooled. Templates: a = flight+hotel, b = delegated hotel "
             "booking, c = revocation (success = safe failure), d = search-heavy (11 calls), e = binding quota (success = flight paid, no call beyond "
             "the sub-agent's quota accepted, partial failure reported).")
    L.append("")
    if a.extra_md:
        L.append(open(a.extra_md).read()); L.append("")
    # provenance
    L.append("## Provenance"); L.append("")
    L.append("| file | git commit (local tree copied to Hedy) | mmpy .so sha256 | e4v21.py sha256 | rows |"); L.append("|---|---|---|---|---|")
    for f, d in list(zip(a.inputs, docs)) + list(zip(a.shared, shared)):
        p = d.get("provenance", {})
        L.append(f"| {os.path.basename(f)} | {str(p.get('git_commit'))[:12]} | {str(p.get('mmpy_so_sha256'))[:16]}... | {str(p.get('e4v21_py_sha256'))[:12]} | {len(d['rows'])} |")
    L.append("")
    L.append("## Models and serving configuration"); L.append("")
    L.append("| model | weights | vLLM tool parser | chat template | workers | runs | errors left | re-run units | nudged runs | nudges |"); L.append("|---|---|---|---|---|---|---|---|---|---|")
    for d in docs:
        mc = d.get("model_config", {}); rs = d["rows"]
        L.append(f"| {d['model']} | {mc.get('hf', '')} | {mc.get('parser', '')} | {os.path.basename(mc.get('template', 'model default'))} | {d['workers']} | {len(rs)} | "
                 f"{sum(1 for r in rs if r['error'])} | {sum(1 for r in rs if r.get('rerun'))} | {sum(1 for r in rs if r['nudges'])} | {sum(r['nudges'] for r in rs)} |")
    L.append("")
    for g, title in [("t0", "temperature 0, tool latency on"), ("t0_rep", "replication of t0, identical settings"), ("t07", "temperature 0.7, 3 seeds"),
                     ("t0_nolat", "temperature 0, zero tool latency")]:
        L.append(f"## Task success ({title})"); L.append("")
        L.append("| model | template | none | jwt | mm | mm_esc |"); L.append("|---|---|---|---|---|---|")
        for d in docs:
            S = d["summary"]
            for tpl in TEMPLATES + ["all"]:
                cells = []
                for mode in MODES:
                    x = S["overall"].get(f"{g}|{mode}") if tpl == "all" else S["by_template"].get(f"{g}|{mode}|{tpl}")
                    cells.append(f"{fmt_ci(x['rate_ci'])} (n={x['n']})" if x else "-")
                L.append(f"| {d['model']} | {tpl} | " + " | ".join(cells) + " |")
        L.append("")
    # replication control
    L.append("## Replication control: t0 run twice with identical settings (t0 vs t0_rep)"); L.append("")
    L.append("Success discordance = units whose success differs between the two identical runs (same model, same mode). "
             "Transcript identity = identical LLM-visible transcripts (templates a, b, d).")
    L.append("")
    L.append("| model | mode | a,b,d: discordant / pairs | c | e | all | identical transcripts (a,b,d) | t0 vs t0_nolat: discordant (all) |"); L.append("|---|---|---|---|---|---|---|---|")
    for d in docs:
        S = d["summary"]
        for mode in MODES:
            x = S["replication"].get(f"t0_vs_t0_rep|{mode}"); y = S["replication"].get(f"t0_vs_t0_nolat|{mode}"); I = S["identity"].get(f"control_t0_vs_t0_rep|{mode}")
            if not x: continue
            f = lambda z: f"{z['success_discordant']} / {z['pairs']}"
            L.append(f"| {d['model']} | {mode} | {f(x['abd'])} | {f(x['c'])} | {f(x['e'])} | {f(x['all'])} | {I['identical']}/{I['units']} | {f(y['all']) if y else '-'} |")
    L.append("")
    # paired differences, bootstrap, McNemar + Holm, equivalence
    tests = []  # (label, model, scope, cfgset, pair, stats)
    for d in docs:
        for scope, tpls in [("honest a,b,d", HONEST), ("revocation c", "c"), ("quota e", "e")]:
            for cfgname, cfgs in [("t07 (3 seeds)", GROUPS["t07"]), ("all 6 configurations", ["t0", "t0_rep", "t0_nolat"] + GROUPS["t07"])]:
                if scope != "honest a,b,d" and cfgname != "t07 (3 seeds)": continue
                for m in ["jwt", "mm", "mm_esc"]:
                    u = paired_units(d["rows"], "none", m, cfgs, tpls)
                    if not u: continue
                    st = cluster_boot(u, B=a.boot, seed=iseed(d["model"], scope, cfgname, m) % (1 << 31))
                    st["p_mcnemar"] = exact_mcnemar(st["only_first"], st["only_second"])
                    tests.append((d["model"], scope, cfgname, f"{m}-none", st))
    adj = holm([t[4]["p_mcnemar"] for t in tests])
    for t, p in zip(tests, adj):
        t[4]["p_holm"] = p
    L.append("## Paired differences with respect to `none` (cluster bootstrap over tasks, exact McNemar, Holm)"); L.append("")
    L.append(f"Difference = success rate of the mode minus success rate of `none` on the same (task, configuration) units, in percentage points. "
             f"CIs: percentile cluster bootstrap ({a.boot} resamples; clusters = tasks, units = seeds/configurations within a task). "
             f"p: exact McNemar on the discordant units; p_Holm: Holm correction over all {len(tests)} McNemar tests of this table. "
             "Equivalence (margin +-5 pp): TOST at alpha = 0.05, i.e. the 90% CI lies inside [-5, +5]; the stricter column requires the 95% CI inside the margin. "
             "For templates c and e the difference is the expected effect of authorisation (no equivalence claimed).")
    L.append("")
    L.append("| model | scope | configurations | pair | units (tasks) | rate none | rate mode | diff pp | 95% CI | 90% CI | discordant none-only / mode-only | p McNemar | p Holm | equivalent (90% CI in +-5) | 95% CI in +-5 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for model, scope, cfgname, pair, st in tests:
        eq90 = -5 <= st["ci90"][0] and st["ci90"][1] <= 5; eq95 = -5 <= st["ci95"][0] and st["ci95"][1] <= 5
        L.append(f"| {model} | {scope} | {cfgname} | {pair} | {st['units']} ({st['clusters']}) | {st['rate_first']:.1f} | {st['rate_second']:.1f} | {st['diff_pp']:+.1f} | "
                 f"[{st['ci95'][0]:+.1f}, {st['ci95'][1]:+.1f}] | [{st['ci90'][0]:+.1f}, {st['ci90'][1]:+.1f}] | {st['only_first']} / {st['only_second']} | "
                 f"{st['p_mcnemar']:.3g} | {st['p_holm']:.3g} | {'yes' if eq90 else 'no'} | {'yes' if eq95 else 'no'} |" if scope == "honest a,b,d" else
                 f"| {model} | {scope} | {cfgname} | {pair} | {st['units']} ({st['clusters']}) | {st['rate_first']:.1f} | {st['rate_second']:.1f} | {st['diff_pp']:+.1f} | "
                 f"[{st['ci95'][0]:+.1f}, {st['ci95'][1]:+.1f}] | [{st['ci90'][0]:+.1f}, {st['ci90'][1]:+.1f}] | {st['only_first']} / {st['only_second']} | "
                 f"{st['p_mcnemar']:.3g} | {st['p_holm']:.3g} | n/a | n/a |")
    L.append("")
    # revocation c and quota e
    L.append("## Template c (revocation): safe-failure rate and revoked calls (all configurations)"); L.append("")
    L.append("| model | none | jwt | mm | mm_esc | revoked calls attempted / accepted: none | jwt | mm | mm_esc | c runs claiming DONE (jwt / mm / mm_esc) |"); L.append("|---|---|---|---|---|---|---|---|---|---|")
    for d in docs:
        rs = d["rows"]; cells = []; rv = []
        for m in MODES:
            rc = [r for r in rs if r["template"] == "c" and r["mode"] == m]
            k = sum(r["success"] for r in rc); cells.append(f"{fmt_ci(wilson(k, len(rc)))} (n={len(rc)})" if rc else "-")
            rv.append(f"{sum(r['revoked_attempted'] for r in rc)} / {sum(r['revoked_accepted'] for r in rc)}")
        cd = " / ".join(str(sum(1 for r in rs if r["template"] == "c" and r["mode"] == m and r["claims_done"])) for m in ["jwt", "mm", "mm_esc"])
        L.append(f"| {d['model']} | " + " | ".join(cells) + " | " + " | ".join(rv) + f" | {cd} |")
    L.append("")
    L.append("## Template e (binding quota: k = 3 hotel searches delegated, 5 needed; all configurations)"); L.append("")
    L.append("| model | mode | runs | success | flight paid | reports FAILED | claims DONE | calls beyond quota attempted | accepted | refused by the wallet (MM) | cities surveyed (median) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for d in docs:
        for m in MODES:
            re_ = [r for r in d["rows"] if r["template"] == "e" and r["mode"] == m]
            if not re_: continue
            k = sum(r["success"] for r in re_)
            L.append(f"| {d['model']} | {m} | {len(re_)} | {fmt_ci(wilson(k, len(re_)))} | {sum(r['all_paid'] for r in re_)} | {sum(r['reports_failure'] for r in re_)} | "
                     f"{sum(r['claims_done'] for r in re_)} | {sum(r['beyond_quota_attempted'] for r in re_)} | {sum(r['beyond_quota_accepted'] for r in re_)} | "
                     f"{sum(r['beyond_quota_wallet_refused'] for r in re_)} | {q([r.get('survey_cities_searched', 0) for r in re_], .5):.0f} |")
    L.append("")
    # slowdown
    L.append("## Slowdown factors (task wall time, mode / none, paired error-free units, templates a, b, d)"); L.append("")
    L.append("| model | mode | tool latency on (t0, t0_rep, t07): units | median | ratio of sums | p95 | zero latency (t0_nolat): units | median | ratio of sums | p95 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for d in docs:
        for m in ["jwt", "mm", "mm_esc"]:
            x = ratio_stats(d["rows"], m, ["t0", "t0_rep"] + GROUPS["t07"], HONEST); y = ratio_stats(d["rows"], m, ["t0_nolat"], HONEST)
            L.append(f"| {d['model']} | {m} | {x['n']} | {x['median']:.2f} | {x['ratio_of_sums']:.2f} | {x['p95']:.2f} | {y['n']} | {y['median']:.2f} | {y['ratio_of_sums']:.2f} | {y['p95']:.2f} |")
    L.append("")
    # authorisation share
    L.append("## Authorisation share of task wall time (ratio of sums, all templates, error-free runs)"); L.append("")
    L.append("| model | mode | t0: auth share | per-call (challenge+prep+verify) | delegation | t0_nolat: auth share | t07: auth share | LLM share (t0) | tool-latency share (t0) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for d in docs:
        T = d["summary"]["timing"]
        for m in MODES:
            x, y, z = T.get(f"t0|{m}"), T.get(f"t0_nolat|{m}"), T.get(f"t07|{m}")
            if not x: continue
            sh = lambda v, k: f"{100 * v[k]['ratio_of_sums']:.1f}%" if v else "-"
            L.append(f"| {d['model']} | {m} | {sh(x, 'auth_share')} | {sh(x, 'per_call_auth_share')} | {sh(x, 'deleg_share')} | "
                     f"{sh(y, 'auth_share')} | {sh(z, 'auth_share')} | {sh(x, 'llm_share')} | {sh(x, 'tool_latency_share')} |")
    L.append("")
    # per-call cost
    L.append("## Per-call authorisation cost (single core, RAYON_NUM_THREADS=1; median [p95] ms, all configurations)"); L.append("")
    L.append("| model | mode | caller | calls | prep | verify | challenge RTT | _meta bytes |"); L.append("|---|---|---|---|---|---|---|---|")
    for d in docs:
        for mode in ["jwt", "mm", "mm_esc"]:
            for role in ["main", "sub"]:
                x = d["summary"]["per_call"].get(f"{mode}|{role}")
                if not x: continue
                f = lambda k: f"{x[k]['median']:.2f} [{x[k]['p95']:.2f}]"
                L.append(f"| {d['model']} | {mode} | {'root mandate' if role == 'main' else 'child mandate'} | {x['n']} | {f('prep_ms')} | {f('verify_ms')} | {f('challenge_ms')} | {x['meta_bytes']['median']:.0f} |")
    L.append("")
    L.append("| model | mode | delegations | delegation ms (median) | parent ms | issuer ms | revocations | revoke ms | push to 4 tools ms |"); L.append("|---|---|---|---|---|---|---|---|---|")
    for d in docs:
        for mode in ["jwt", "mm", "mm_esc"]:
            x = d["summary"]["per_call"].get(f"{mode}|delegation", {}); y = d["summary"]["per_call"].get(f"{mode}|revocation", {})
            if x or y:
                L.append(f"| {d['model']} | {mode} | {x.get('n', 0)} | {x.get('deleg_ms_median', float('nan')):.1f} | {x.get('parent_ms_median', 0):.1f} | {x.get('issuer_ms_median', 0):.1f} | {y.get('n', 0)} | {y.get('revoke_ms_median', float('nan')):.2f} | {y.get('push_ms_median', float('nan')):.1f} |")
    L.append("")
    # safety and canonicalisation
    L.append("## Safety counters and canonicalisation (all configurations)"); L.append("")
    L.append("| model | mode | runs | honest calls | honest calls wrongly rejected | canonical strings compared | client/server mismatches | revoked calls attempted / accepted | beyond-quota calls attempted / accepted | out-of-mandate calls attempted / accepted | wallet refusals | errors | nudged runs |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for d in docs:
        for mode in MODES:
            x = d["summary"]["safety"].get(mode)
            if not x: continue
            L.append(f"| {d['model']} | {mode} | {x['runs']} | {x['honest_calls']} | {x['honest_calls_wrongly_rejected']} | {x['canon_checked']} | {x['canon_mismatch']} | "
                     f"{x['revoked_calls_attempted']} / {x['revoked_calls_accepted']} | {x['beyond_quota_attempted']} / {x['beyond_quota_accepted']} | "
                     f"{x['out_of_mandate_calls_attempted']} / {x['out_of_mandate_calls_accepted']} | {x['wallet_refusals']} | {x['errors']} | {x['nudged_runs']} |")
    L.append("")
    for f in a.canonprobe:
        cp = json.load(open(f))
        L.append(f"Canonicalisation probe `{os.path.basename(f)}` ({len(cp['rows'])} adversarial argument objects through the real MCP client and tool server): " +
                 "; ".join(f"{m}: {v['canon_mismatch']} mismatches, {v['valid_rejected']} rejections of {v['valid']}" for m, v in cp["summary"].items()) +
                 " (rejections = amounts above the root mandate's per-call limit of 1,000 EUR, i.e. correct policy decisions).")
        L.append("")
    # shared issuer
    if shared:
        L.append("## Shared issuer with concurrent revocations (mode mm, temperature 0)"); L.append("")
        L.append("One Authority per worker shared by all its tasks; a background task revokes an unrelated dummy mandate every "
                 f"{shared[0]['shared_issuer']['revoke_every_s']:g} s and pushes the new public parameters to the 4 tools; publish-then-refresh ordering "
                 "(the wallet does not present while new parameters are being pushed). Churn rejection = honest call rejected whose presentation was built "
                 "against an older accumulator version than the one the tool held at verification. Revocation delay = time from the revocation request to the "
                 "moment no tool accepts presentations against a pre-revocation accumulator: W = 0, installation of the new value on the last tool; "
                 "W = 2, installation of the 2nd subsequent value.")
        L.append("")
        L.append("| model | W | runs | success | per-task-Authority t0 mm success (same tasks) | honest calls | rejected | of which churn | revocations (dummy + task) | achieved rate per worker /s | revoke ms median [p95] | push ms median | lock wait per call ms median [p95] | revocation delay ms median [p95] | dummy pool exhausted |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for d in shared:
            rs = d["rows"]; G = d["shared_issuer"]["grace"]
            base = next((x for x in docs if x["model"] == d["model"]), None)
            ids = {r["task"] for r in rs}
            bs = [r for r in base["rows"] if r["task"] in ids and r["cfg"] == "t0" and r["mode"] == "mm"] if base else []
            ev = [e for lg in d["revlogs"] for e in lg["events"] if e["kind"] in ("dummy", "task")]
            exh = sum(1 for lg in d["revlogs"] for e in lg["events"] if e["kind"] == "exhausted")
            delays = []
            for lg in d["revlogs"]:
                es = sorted([e for e in lg["events"] if e["kind"] in ("dummy", "task")], key=lambda e: e["ver"])
                byv = {e["ver"]: e for e in es}
                for e in es:
                    nxt = byv.get(e["ver"] + G)
                    if nxt and nxt.get("t_installed"):
                        delays.append((nxt["t_installed"] - e["t_request"]) * 1e3)
            tr_ = [[e["t_request"] for e in lg["events"] if "t_request" in e] for lg in d["revlogs"]]
            span = sum(max(x) - min(x) for x in tr_ if len(x) > 1); gaps = sum(len(x) - 1 for x in tr_ if len(x) > 1)
            calls = [c for r in rs for c in r["calls"] if c.get("valid") and "ok" in c]
            lw = [c.get("lock_wait_ms", 0.0) for c in calls if c.get("refused") is None]
            k = sum(r["success"] for r in rs); kb = sum(r["success"] for r in bs)
            hon = sum(r["honest_calls"] for r in rs); hrej = sum(r["honest_rejected"] for r in rs); ch = sum(r["honest_rejected_churn"] for r in rs)
            L.append(f"| {d['model']} | {G} | {len(rs)} | {fmt_ci(wilson(k, len(rs)))} | {fmt_ci(wilson(kb, len(bs))) if bs else '-'} | {hon} | {hrej} | {ch} | "
                     f"{sum(1 for e in ev if e['kind'] == 'dummy')} + {sum(1 for e in ev if e['kind'] == 'task')} | {gaps / span if span else float('nan'):.2f} | "
                     f"{q([e['revoke_ms'] for e in ev], .5):.1f} [{q([e['revoke_ms'] for e in ev], .95):.1f}] | {q([e['push_ms'] for e in ev], .5):.1f} | "
                     f"{q(lw, .5):.2f} [{q(lw, .95):.1f}] | {q(delays, .5):.0f} [{q(delays, .95):.0f}] | {exh} of {len(d['revlogs'])} workers |")
        L.append("")
    if a.bench:
        L.append("## Micro-benchmark of the primitives on the compute node (median ms; `bench`, outside the agent loop)"); L.append("")
        L.append("| file | threads (RAYON_NUM_THREADS) | cores | MM prep (root) | MM verify | MM_esc prep | MM_esc verify | MM prep (child) | delegation parent+issuer | revoke (mandates) | verifier update | _meta proof bytes | JWT prep | JWT verify |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for f in a.bench:
            b = json.load(open(f)); r = b["results"]
            L.append(f"| {os.path.basename(f)} | {b['rayon']} | {len(b['affinity'] or [])} | {r['mm_root']['prep_ms_median']:.1f} | {r['mm_root']['verify_ms_median']:.1f} | "
                     f"{r['mm_esc_root']['prep_ms_median']:.1f} | {r['mm_esc_root']['verify_ms_median']:.1f} | {r['mm_child']['prep_ms_median']:.1f} | "
                     f"{r['mm_delegate']['parent_ms_median']:.0f}+{r['mm_delegate']['issuer_ms_median']:.0f} | {statistics.median(x['revoke_ms'] for x in r['mm_revoke']):.1f} ({r['mm_revoke'][-1].get('mandates', '?')}) | "
                     f"{statistics.median(x['verifier_update_ms'] for x in r['mm_revoke']):.1f} | {r['mm_root']['bytes']} | {r['jwt']['prep_ms_median']:.3f} | {r['jwt']['verify_ms_median']:.3f} |")
        L.append("")
    if a.tail_md:
        L.append(open(a.tail_md).read())
    open(a.md, "w").write("\n".join(L) + "\n")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--base-url", required=True); r.add_argument("--model", required=True); r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=8); r.add_argument("--agent-cores", required=True); r.add_argument("--server-cores", required=True)
    r.add_argument("--port0", type=int, default=9100); r.add_argument("--cfgs", default=",".join(c["name"] for c in CFGS)); r.add_argument("--modes", default=",".join(MODES))
    r.add_argument("--limit", type=int, default=0, help="tasks per template (0 = all 24)")
    r.add_argument("--model-config", default=""); r.add_argument("--vllm-cmd", default=""); r.add_argument("--endpoint-kind", default="")
    r.add_argument("--lscpu", default=""); r.add_argument("--started", default="")
    r.add_argument("--rerun-errors", default="", help="existing result JSON: re-run only the (task, cfg, mode) units that ended with an error")
    for x in (r,):
        x.add_argument("--shared-issuer", action="store_true"); x.add_argument("--grace", type=int, default=0)
        x.add_argument("--revoke-every", type=float, default=2.0); x.add_argument("--dummies", type=int, default=0)
    s = sp.add_parser("serve"); s.add_argument("--port0", type=int, required=True)
    w = sp.add_parser("worker")
    for k in ["--port0", "--worker"]: w.add_argument(k, type=int, required=True)
    for k in ["--task-ids", "--cfgs", "--modes", "--base-url", "--model", "--out"]: w.add_argument(k, required=True)
    w.add_argument("--units", default="")
    w.add_argument("--shared-issuer", action="store_true"); w.add_argument("--grace", type=int, default=0)
    w.add_argument("--revoke-every", type=float, default=2.0); w.add_argument("--dummies", type=int, default=0)
    cp = sp.add_parser("canonprobe"); cp.add_argument("--out", required=True); cp.add_argument("--port0", type=int, default=9300)
    b = sp.add_parser("bench"); b.add_argument("--out", required=True); b.add_argument("--n", type=int, default=30)
    an = sp.add_parser("analyse"); an.add_argument("--inputs", nargs="+", required=True); an.add_argument("--md", required=True); an.add_argument("--extra-md", default="")
    an.add_argument("--tail-md", default=""); an.add_argument("--bench", nargs="*", default=[]); an.add_argument("--shared", nargs="*", default=[])
    an.add_argument("--canonprobe", nargs="*", default=[]); an.add_argument("--boot", type=int, default=10000); an.add_argument("--write-back", action="store_true")
    sp.add_parser("tasks")
    a = p.parse_args()
    jcs_selftest()
    if a.cmd == "run": main_run(a)
    elif a.cmd == "serve": main_serve(a)
    elif a.cmd == "worker": asyncio.run(worker_main(a))
    elif a.cmd == "bench": main_bench(a)
    elif a.cmd == "canonprobe": main_canonprobe(a)
    elif a.cmd == "analyse": main_analyse(a)
    elif a.cmd == "tasks":
        for t in make_tasks(): print(json.dumps({k: t[k] for k in t if k != "prompt"}), "\n   ", t["prompt"])
