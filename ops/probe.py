# 一次性實測：Congress.gov 涉台法案＋修正後的四個面板（結果寫 probe.json；所有金鑰遮掉）
import json, os, re, time, traceback, tempfile
import requests
KEYS = [os.environ.get(k) for k in ("FRED_API_KEY", "GEMINI_API_KEY", "CONGRESS_API_KEY") if os.environ.get(k)]
CK = os.environ.get("CONGRESS_API_KEY", "").strip()
OUT = {"congress": {"has_key": bool(CK)}}
S = requests.Session()
def C(path, **p):
    t0 = time.time(); r = S.get("https://api.congress.gov/v3/" + path, params={"api_key": CK, "format": "json", **p}, timeout=40)
    return r, int((time.time() - t0) * 1000)
KW = re.compile(r"Taiwan|semiconductor|chip|CHIPS|export control|tariff|Mexico|USMCA", re.I)
try:
    r, ms = C("bill", limit=250, sort="updateDate+desc")
    OUT["congress"].update(st=r.status_code, ms=ms, rate=r.headers.get("x-ratelimit-remaining"), limit=r.headers.get("x-ratelimit-limit"))
    j = r.json(); bills = j.get("bills") or []
    OUT["congress"]["n"] = len(bills); OUT["congress"]["span"] = [bills[-1].get("updateDate"), bills[0].get("updateDate")] if bills else None
    OUT["congress"]["sample_keys"] = list(bills[0].keys()) if bills else []
    hits = [(b.get("congress"), b.get("type"), b.get("number"), b.get("title")[:150], (b.get("latestAction") or {}).get("actionDate"), (b.get("latestAction") or {}).get("text", "")[:120]) for b in bills if KW.search(b.get("title") or "")]
    OUT["congress"]["hits_250"] = hits
    tw = []
    for off in range(0, 2000, 250):   # 往回翻 2000 筆最近更新的法案，看涉台法案多久出現一次
        r, _ = C("bill", limit=250, offset=off, sort="updateDate+desc"); bs = r.json().get("bills") or []
        tw += [(b.get("congress"), b.get("type"), b.get("number"), b.get("title")[:150], b.get("updateDate"), (b.get("latestAction") or {}).get("actionDate"), (b.get("latestAction") or {}).get("text", "")[:120]) for b in bs if re.search(r"Taiwan", b.get("title") or "", re.I)]
        if bs: OUT["congress"]["span_2000"] = bs[-1].get("updateDate")
    OUT["congress"]["taiwan_2000"] = tw
    if tw:
        c, t, n = tw[0][0], tw[0][1].lower(), tw[0][2]
        r, _ = C(f"bill/{c}/{t}/{n}"); b = r.json().get("bill") or {}
        OUT["congress"]["detail"] = {"title": b.get("title"), "sponsors": [s.get("fullName") for s in b.get("sponsors") or []], "cosponsors": (b.get("cosponsors") or {}).get("count"),
                                    "policyArea": (b.get("policyArea") or {}).get("name"), "introducedDate": b.get("introducedDate"), "latest": b.get("latestAction"), "url_keys": list(b.keys())[:30]}
except Exception:
    OUT["congress"]["FAIL"] = traceback.format_exc()[-800:]
# 修正後的面板再跑一次
os.environ["INTEL_DATA_DIR"] = tempfile.mkdtemp()
src = open("fetch.py", encoding="utf-8").read(); src = src[:src.index('\nrun("pulse", p_pulse)\n')]
ns = {"__name__": "fetchtest", "__file__": os.path.abspath("fetch.py")}
exec(compile(src, "fetch.py", "exec"), ns)
for k in ("p_uspolicy", "p_exports", "p_logistics"):
    try:
        d = ns[k]()
        if k == "p_uspolicy": d = {"n": len(d["items"]), "items": [(x["src"], x["kind"], x["date"], x["hot"], x["tw"], x["zh"][:60] or x["title"][:80]) for x in d["items"]], "errs": d["errs"]}
        if k == "p_exports": d = {"extra": d["extra"], "goods": [(g["name"], g["v"], g["yoy"]) for g in d["goods"]], "mk": [(m["name"], m["v"], m["yoy"]) for m in d["markets"]], "errs": d["errs"]}
        if k == "p_logistics": d = {"lanes": d.get("drewry", {}).get("lanes"), "threat": d.get("threat"), "news": [(n["source"], n["hot"], n["zh"][:50] or n["title"][:60]) for n in d.get("news", [])[:10]], "errs": d["errs"]}
        OUT[k] = d
    except Exception:
        OUT[k] = {"FAIL": traceback.format_exc()[-1200:]}
s = json.dumps(OUT, ensure_ascii=False, indent=1)
for v in KEYS: s = s.replace(v, "***")
open("probe.json", "w").write(s); print("done")
