# 第一階段：候選訊號池＋記分卡（只用 1990–2018；2019 之後留給最後考試，這裡完全不算）
import json, os, re, io, csv, zipfile, math, traceback, tempfile
from datetime import datetime, timezone
os.environ["INTEL_DATA_DIR"] = tempfile.mkdtemp()
src = open("fetch.py", encoding="utf-8").read(); src = src[:src.index('\nrun("pulse", p_pulse)\n')]
ns = {"__name__": "fetchtest", "__file__": os.path.abspath("fetch.py")}
exec(compile(src, "fetch.py", "exec"), ns)
get, gjson, fred, num, _yahoo_get = ns["get"], ns["gjson"], ns["fred"], ns["num"], ns["_yahoo_get"]
OUT = {"errs": [], "cand": {}}
def err(k): OUT["errs"].append(k + ": " + traceback.format_exc()[-400:])
def dec(b):
    for e in ("utf-8-sig", "cp950"):
        try: return b.decode(e)
        except Exception: pass
    return b.decode("utf-8", "replace")
def ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[4:]); m += k; y += (m - 1) // 12; m = (m - 1) % 12 + 1; return f"{y}{m:02d}"
RAW, LAG, NOTE = {}, {}, {}   # LAG：月底後幾天公布（負數＝當月內就有）
# ---- 目標與國發會 ----
try:
    meta = gjson("https://data.gov.tw/api/v2/rest/dataset/6099", timeout=60)["result"]
    u = next(d["resourceDownloadUrl"] for d in meta["distribution"] if d.get("resourceDownloadUrl"))
    z = zipfile.ZipFile(io.BytesIO(get(u, timeout=90).content)); OUT["ndc_zip"] = z.namelist()
    name = next(n for n in z.namelist() if n.startswith("景氣指標與燈號"))
    rows = [r for r in csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig", "ignore"))) if re.match(r"\d{6}$", r.get("Date") or "")]
    OUT["ndc_cols"] = list(rows[0].keys())
    COIN = {r["Date"]: num(r["同時指標不含趨勢指數"]) for r in rows if num(r.get("同時指標不含趨勢指數"))}
    RAW["ndc_lead"] = {r["Date"]: num(r["領先指標不含趨勢指數"]) for r in rows if num(r.get("領先指標不含趨勢指數"))}; LAG["ndc_lead"] = 27
    for n in z.namelist():   # 其他檔案（可能有構成項目）
        if n != name:
            t = z.read(n).decode("utf-8-sig", "ignore"); OUT.setdefault("ndc_other", {})[n] = t[:600]
except Exception: err("ndc"); COIN = {}
# ---- 台灣 ----
try:
    j = gjson("https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=EF15M01")
    labels = [l.get("data", l) if isinstance(l, dict) else l for l in j["data"]["structure"]["Table1"]]
    rows = [r for r in j["data"]["dataSets"] if r and re.match(r"\d{4}M\d\d", r[0])]
    def col(p):
        fw = p.replace("M", "Ｍ").replace("1", "１").replace("2", "２").replace("B", "Ｂ")
        return 2 + 2 * [k for k, l in enumerate(labels) if str(l).endswith(fw) or str(l).endswith(p)][0]
    c1, c2 = col("M1B"), col("M2")
    RAW["m1b_m2"] = {r[0].replace("M", ""): num(r[c1]) - num(r[c2]) for r in rows if num(r[c1]) is not None and num(r[c2]) is not None}; LAG["m1b_m2"] = 25; NOTE["m1b_m2"] = "level"
    RAW["m1b_yoy"] = {r[0].replace("M", ""): num(r[c1]) for r in rows if num(r[c1]) is not None}; LAG["m1b_yoy"] = 25; NOTE["m1b_yoy"] = "level"
except Exception: err("m1b")
for fn in ("EF03M01", "EF05M01", "EF10M01"):
    try:
        j = gjson(f"https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={fn}")
        OUT.setdefault("cbc_labels", {})[fn] = [l.get("data", l) if isinstance(l, dict) else l for l in j["data"]["structure"]["Table1"]]
        labels = OUT["cbc_labels"][fn]
        rows = [r for r in j["data"]["dataSets"] if r and re.match(r"\d{4}M\d\d", r[0])]
        for i, l in enumerate(labels):
            if "放款" in str(l) and "loans" not in RAW:
                RAW["loans"] = {r[0].replace("M", ""): num(r[2 + 2 * i]) for r in rows if num(r[2 + 2 * i]) is not None}; LAG["loans"] = 25; NOTE["loans"] = "level"; OUT["loans_label"] = [fn, l]
    except Exception: err(fn)
try:
    s = {}
    for r in csv.reader(io.StringIO(dec(get("https://service.moea.gov.tw/EE520/opendata/b.csv", timeout=60).content))):
        if len(r) >= 3 and r[0] == "外銷訂單金額" and re.match(r"\d{5}$", r[1]): s[f"{int(r[1][:3]) + 1911}{r[1][3:]}"] = num(r[2])
    RAW["orders"] = s; LAG["orders"] = 20
except Exception: err("orders")
try:
    ind = {}
    for sid in (256, 236):
        L = list(csv.reader(io.StringIO(dec(get(f"https://www.moeaea.gov.tw/ECW/populace/opendata/wHandOpenData_File.ashx?set_id={sid}", timeout=90).content))))
        h = L[0]; it = next(i for i, c in enumerate(h) if "工業部門_合計" in c); ie = next(i for i, c in enumerate(h) if "工業部門" in c and "電子" in c)
        for r in L[1:]:
            if r and re.match(r"\d{6}$", r[0].strip()) and num(r[it]) and num(r[ie]): ind[r[0].strip()] = num(r[it]) - num(r[ie])
    RAW["elec_other"] = ind; LAG["elec_other"] = 50
except Exception: err("elec")
def yahoo_m(sym):
    j = _yahoo_get(sym, {"range": "max", "interval": "1mo", "includePrePost": "false"}); res = j["chart"]["result"][0]
    out = {}
    for t, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []):
        if c: out[datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y%m")] = c
    return out
for k, sym, lag in (("taiex", "^TWII", -1), ("sox", "^SOX", -1), ("kospi", "^KS11", -1), ("spx", "^GSPC", -1), ("twd", "TWD=X", -1)):
    try: RAW[k] = yahoo_m(sym); LAG[k] = lag
    except Exception: err(k)
# ---- 全球（FRED，月平均）----
FR = [("us_curve", "T10Y3M", 0, "level"), ("us_baa", "BAA10Y", 0, "level"), ("philly_no", "NOCDFSA066MSFRBPHI", -12, "level"), ("philly_gen", "GACDFSA066MSFRBPHI", -12, "level"),
      ("empire", "GACDISA066MSFRBNY", -15, "level"), ("kr_exports", "XTEXVA01KRM667S", 15, None), ("us_capgoods", "NEWORDER", 33, None), ("us_claims", "ICSA", -3, "inv"),
      ("copper", "PCOPPUSDM", 5, None), ("us_sent", "UMCSENT", -2, "level"), ("us_indpro", "INDPRO", 16, None), ("jp_exports", "XTEXVA01JPM667S", 25, None),
      ("cn_exports", "XTEXVA01CNM667S", 15, None), ("us_semis_ip", "IPG3344S", 16, None), ("oil", "DCOILWTICO", 0, None), ("us_hy_mood", "BAMLH0A0HYM2", 0, "level")]
for k, sid, lag, kind in FR:
    try:
        obs = fred(sid, n=20000); m = {}
        for d, v in obs:
            key = d[:4] + d[5:7]; m.setdefault(key, []).append(v)
        RAW[k] = {key: sum(v) / len(v) for key, v in m.items()}; LAG[k] = lag
        if kind: NOTE[k] = kind
    except Exception: err(k)
# ---- 轉換 ----
def yoy(s): return {k: 100 * (v / s[ym_add(k, -12)] - 1) for k, v in s.items() if s.get(ym_add(k, -12))}
def chg6(s): return {k: 100 * (v / s[ym_add(k, -6)] - 1) for k, v in s.items() if s.get(ym_add(k, -6))}
def dif6(s): return {k: v - s[ym_add(k, -6)] for k, v in s.items() if ym_add(k, -6) in s}
def ma3(s): return {k: (s[k] + s[ym_add(k, -1)] + s[ym_add(k, -2)]) / 3 for k in s if ym_add(k, -1) in s and ym_add(k, -2) in s}
def corr(a, b):
    n = len(a)
    if n < 36: return None
    ma, mb = sum(a) / n, sum(b) / n; va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb) if va and vb else None
def lc(s, k, lo, hi):
    ks = [t for t in s if lo <= t <= hi and ym_add(t, k) in COIN]
    c = corr([s[t] for t in ks], [COIN[ym_add(t, k)] for t in ks]); return (round(c, 3) if c is not None else None), len(ks)
TR, VA = ("199001", "201212"), ("201301", "201812")
for k, s in RAW.items():
    if not s: continue
    kind = NOTE.get(k)
    forms = {"level": ma3(s), "dif6": ma3(dif6(s))} if kind in ("level", "inv") else {"yoy": ma3(yoy(s)), "chg6": ma3(chg6(s))}
    if k == "ndc_lead": forms = {"level": s}
    best = None
    for fname, f in forms.items():
        for lag in range(0, 13):
            c, n = lc(f, lag, *TR)
            if c is None: continue
            if best is None or abs(c) > abs(best["train"]): best = {"form": fname, "lag": lag, "train": c, "n_train": n}
    if not best:
        OUT["cand"][k] = {"note": "訓練期資料不足", "range": (min(s), max(s))}; continue
    f = forms[best["form"]]
    v, nv = lc(f, best["lag"], *VA)
    eff = round(best["lag"] - LAG.get(k, 30) / 30, 1)
    prof = {lag: lc(f, lag, *TR)[0] for lag in (0, 2, 4, 6, 9, 12)}
    OUT["cand"][k] = {**best, "valid": v, "n_valid": nv, "pub_lag_days": LAG.get(k), "effective_lead_months": eff, "range": (min(s), max(s)), "train_profile": prof,
                      "stable": bool(v is not None and abs(v) >= 0.4 and (v > 0) == (best["train"] > 0))}
open("probe.json", "w").write(json.dumps(OUT, ensure_ascii=False, indent=1)); print("done")
