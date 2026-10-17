# 第二階段：最後考試（規則在跑之前就定好；考完不改）
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

# ================= 第二階段：最後考試 =================
# 規則（跑之前定好）：
# 1. 所有序列都對齊到「月底那一天手上拿得到什麼」：公布延遲超過 0 天的，用上一個月的值（延遲超過 30 天用前兩個月）
# 2. 模型 B＝7 個通過訊號的 z 分數等權平均；z 分數的平均和標準差只用 1990–2018 算；Baa 利差反向
# 3. 國發會領先指標同樣對齊：月底拿得到的是上個月的值
# 4. 考三項：(a) 對同時指標 3～6 個月後的相關 (b) 轉折點：抓到幾個、平均提早幾個月、假警報幾次 (c) 模型 A：提早版國發會方向命中率
def ym_add2(ym, k): return ym_add(ym, k)
def yoy(s): return {k: 100 * (v / s[ym_add(k, -12)] - 1) for k, v in s.items() if s.get(ym_add(k, -12))}
def ma3(s): return {k: (s[k] + s[ym_add(k, -1)] + s[ym_add(k, -2)]) / 3 for k in s if ym_add(k, -1) in s and ym_add(k, -2) in s}
def asof(s, lag_days):
    sh = 0 if lag_days <= 0 else (1 if lag_days <= 30 else 2)
    return {ym_add(k, sh): v for k, v in s.items()}
B_SPEC = [("taiex", "yoy", 1), ("kospi", "yoy", 1), ("m1b_m2", "level", 1), ("empire", "level", 1), ("philly_no", "level", 1), ("sox", "yoy", 1), ("us_baa", "level", -1)]
Z = {}
for k, form, sign in B_SPEC:
    s = RAW.get(k) or {}
    f = ma3(yoy(s)) if form == "yoy" else ma3(s)
    f = asof(f, LAG.get(k, 30))
    base = [v for t, v in f.items() if "199001" <= t <= "201812"]
    m = sum(base) / len(base); sd = math.sqrt(sum((x - m) ** 2 for x in base) / len(base)) or 1
    Z[k] = {t: sign * (v - m) / sd for t, v in f.items()}
months = sorted(set().union(*[set(z) for z in Z.values()]))
B = {}
for t in months:
    vals = [Z[k][t] for k in Z if t in Z[k]]
    if len(vals) >= 4: B[t] = sum(vals) / len(vals)
NDC = asof(RAW["ndc_lead"], 27)
def corr(a, b):
    n = len(a)
    if n < 24: return None
    ma, mb = sum(a) / n, sum(b) / n; va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb), 3) if va and vb else None
def lc(s, k, lo, hi):
    ks = [t for t in s if lo <= t <= hi and ym_add(t, k) in COIN]
    return corr([s[t] for t in ks], [COIN[ym_add(t, k)] for t in ks])
PER = {"insample_1990_2018": ("199001", "201812"), "EXAM_2019_2026": ("201901", "209912")}
OUT["exam_corr"] = {p: {name: {k: lc(S_, k, *rng) for k in range(0, 10)} for name, S_ in (("modelB", B), ("ndc_lead", NDC))} for p, rng in PER.items()}
def turns(s, w=6, amp=None):
    ks = sorted(s); vals = [s[k] for k in ks]
    if amp is None:
        m = sum(vals) / len(vals); amp = 0.6 * math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))
    out = []
    for i in range(w, len(ks) - w):
        v = vals[i]; win = vals[i - w:i + w + 1]
        if v == max(win) and v - min(win) >= amp: out.append((ks[i], "峰"))
        elif v == min(win) and max(win) - v >= amp: out.append((ks[i], "谷"))
    return out
def mi(ym): return int(ym[:4]) * 12 + int(ym[4:])
CT = turns(COIN, 6, 1.5)
def score_turns(sig, lo, hi):
    st = turns(sig); ct = [x for x in CT if lo <= x[0] <= hi]; used = set(); rows = []
    for t, kind in ct:
        cand = [a for a, b in st if b == kind and mi(t) - 12 <= mi(a) <= mi(t) + 3 and a not in used]
        if cand:
            a = max(cand, key=lambda x: mi(x)) if any(mi(x) <= mi(t) for x in cand) else min(cand, key=mi)
            a = min(cand, key=lambda x: abs(mi(t) - mi(x) - 3)); used.add(a); rows.append((t, kind, a, mi(t) - mi(a)))
        else: rows.append((t, kind, None, None))
    false = [a for a, b in st if lo <= a <= hi and a not in used]
    hit = [r for r in rows if r[2]]
    return {"coin_turns": len(ct), "caught": len(hit), "avg_lead_months": round(sum(r[3] for r in hit) / len(hit), 1) if hit else None, "false_alarms": len(false), "false": false, "rows": rows}
OUT["exam_turns"] = {p: {name: score_turns(S_, *rng) for name, S_ in (("modelB", B), ("ndc_lead", NDC))} for p, rng in PER.items()}
OUT["coin_turns_all"] = [x for x in CT if x[0] >= "199001"]
OUT["modelB_latest"] = [(t, round(B[t], 2)) for t in sorted(B)[-8:]]
OUT["modelB_components_latest"] = {k: [(t, round(z[t], 2)) for t in sorted(z)[-3:]] for k, z in Z.items()}
OUT["ndc_latest"] = [(t, round(NDC[t], 2)) for t in sorted(NDC)[-4:]]
# ---- 模型 A：提早版國發會（用比它早公布的成分預測它這個月是升還降）----
try:
    name = next(n for n in z.namelist() if n.startswith("領先指標構成項目"))
    rows = list(csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig", "ignore"))))
    def colser(key):
        c = next(c for c in rows[0].keys() if key in c)
        return {r["Date"]: num(r[c]) for r in rows if re.match(r"\d{6}$", r.get("Date") or "") and num(r.get(c)) is not None}
    stock, semi = colser("股價"), colser("半導體設備")
    L = RAW["ndc_lead"]
    def chg(s, t): return (s[t] / s[ym_add(t, -1)] - 1) if s.get(t) and s.get(ym_add(t, -1)) else None
    res = {}
    for p, (lo, hi) in PER.items():
        n = hit = 0; n2 = hit2 = 0
        for t in sorted(L):
            if not (lo <= t <= hi) or ym_add(t, -1) not in L: continue
            d = L[t] - L[ym_add(t, -1)]
            cs = chg(stock, t)
            if cs is None: continue
            n += 1; hit += (cs > 0) == (d > 0)
            cm = chg(semi, t)
            if cm is not None:   # 股價為主、半導體設備進口加權一半
                n2 += 1; hit2 += ((cs + 0.5 * cm) > 0) == (d > 0)
        prev = sum(1 for t in sorted(L) if lo <= t <= hi and ym_add(t, -1) in L and ym_add(t, -2) in L and ((L[t] - L[ym_add(t, -1)]) > 0) == ((L[ym_add(t, -1)] - L[ym_add(t, -2)]) > 0))
        tot = sum(1 for t in sorted(L) if lo <= t <= hi and ym_add(t, -1) in L and ym_add(t, -2) in L)
        res[p] = {"stock_only_hit": round(hit / n, 3) if n else None, "n": n, "stock_semi_hit": round(hit2 / n2, 3) if n2 else None, "n2": n2,
                  "naive_same_as_last_month": round(prev / tot, 3) if tot else None}
    OUT["modelA"] = res
except Exception: err("modelA")
open("probe.json", "w").write(json.dumps(OUT, ensure_ascii=False, indent=1)); print("done")
