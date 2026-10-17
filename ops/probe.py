# 回測：台灣即時景氣指數的各成分，對國發會同時指標（不含趨勢）領先幾個月、相關多高（結果寫 probe.json）
import json, re, io, csv, zipfile, math, traceback
import requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 dalta-intel/1.0 (personal non-commercial)"
OUT = {"errs": []}
def dec(b):
    for e in ("utf-8-sig", "cp950"):
        try: return b.decode(e)
        except Exception: pass
    return b.decode("utf-8", "replace")
def num(x):
    try: return float(str(x).replace(",", "").strip())
    except Exception: return None
def ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[4:]); m += k; y += (m - 1) // 12; m = (m - 1) % 12 + 1; return f"{y}{m:02d}"
SER = {}
# 目標：國發會領先、同時指標（不含趨勢）
try:
    meta = S.get("https://data.gov.tw/api/v2/rest/dataset/6099", timeout=60).json()["result"]
    u = next(d["resourceDownloadUrl"] for d in meta["distribution"] if d.get("resourceDownloadUrl"))
    z = zipfile.ZipFile(io.BytesIO(S.get(u, timeout=90).content)); name = next(n for n in z.namelist() if n.startswith("景氣指標與燈號"))
    rows = [r for r in csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig", "ignore"))) if re.match(r"\d{6}$", r.get("Date") or "")]
    SER["coin"] = {r["Date"]: num(r["同時指標不含趨勢指數"]) for r in rows if num(r.get("同時指標不含趨勢指數"))}
    SER["ndc_lead"] = {r["Date"]: num(r["領先指標不含趨勢指數"]) for r in rows if num(r.get("領先指標不含趨勢指數"))}
except Exception: OUT["errs"].append("ndc " + traceback.format_exc()[-300:])
# 工業用電：電子業、其他工業
try:
    ind, ele = {}, {}
    for sid in (256, 236):
        L = list(csv.reader(io.StringIO(dec(S.get(f"https://www.moeaea.gov.tw/ECW/populace/opendata/wHandOpenData_File.ashx?set_id={sid}", timeout=90).content))))
        h = L[0]; it = next(i for i, c in enumerate(h) if "工業部門_合計" in c); ie = next(i for i, c in enumerate(h) if "工業部門" in c and "電子" in c)
        for r in L[1:]:
            if r and re.match(r"\d{6}$", r[0].strip()):
                t, e = num(r[it]), num(r[ie])
                if t and e: ind[r[0].strip()] = t - e; ele[r[0].strip()] = e
    SER["elec_other"] = ind; SER["elec_electronics"] = ele
except Exception: OUT["errs"].append("elec " + traceback.format_exc()[-300:])
# 港口貨櫃量
try:
    SER["teu"] = {r[0]: num(r[2]) for r in csv.reader(io.StringIO(dec(S.get("https://www.twport.com.tw/fapi/opendata?id=13878", timeout=90).content))) if len(r) > 2 and r[1] == "國際商港" and re.match(r"\d{6}$", r[0])}
except Exception: OUT["errs"].append("teu " + traceback.format_exc()[-300:])
# 出口總值（財政部統計資料庫，百萬美元）
try:
    t = dec(S.get("https://web02.mof.gov.tw/njswww/webMain.aspx?sys=220&ym=9000&kind=21&type=4&funid=i8121&cycle=41&outmode=12&compmode=00&outkind=1&fld0=1&codlst0=1101111010100011110111100111110110100&utf=1", timeout=90).content)
    ex = {}
    for r in csv.reader(io.StringIO(t)):
        m = re.match(r"(\d+)年\s*(\d+)月", (r or [""])[0].strip())
        if m and len(r) > 1 and num(r[1]): ex[f"{int(m.group(1)) + 1911}{int(m.group(2)):02d}"] = num(r[1])
    SER["exports"] = ex
except Exception: OUT["errs"].append("exports " + traceback.format_exc()[-300:])
# 外銷訂單
try:
    s = {}
    for r in csv.reader(io.StringIO(dec(S.get("https://service.moea.gov.tw/EE520/opendata/b.csv", timeout=60).content))):
        if len(r) >= 3 and r[0] == "外銷訂單金額" and re.match(r"\d{5}$", r[1]): s[f"{int(r[1][:3]) + 1911}{r[1][3:]}"] = num(r[2])
    SER["orders"] = s
except Exception: OUT["errs"].append("orders " + traceback.format_exc()[-300:])
# 央行：放款與投資、M1B、M2（年增率直接用央行算的）
def cbc(fn):
    j = S.get(f"https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={fn}", timeout=60).json()
    labels = [l.get("data", l) if isinstance(l, dict) else l for l in j["data"]["structure"]["Table1"]]
    rows = [r for r in j["data"]["dataSets"] if r and re.match(r"\d{4}M\d\d", r[0])]
    return labels, rows
YOY = {}
try:
    labels, rows = cbc("EF01M01"); OUT["ef01_labels"] = labels
    i = next(k for k, l in enumerate(labels) if "放款與投資" in str(l))
    YOY["loans"] = {r[0].replace("M", ""): num(r[2 + 2 * i]) for r in rows if num(r[2 + 2 * i]) is not None}
except Exception: OUT["errs"].append("loans " + traceback.format_exc()[-300:])
try:
    labels, rows = cbc("EF15M01")
    def col(p):
        fw = p.replace("M", "Ｍ").replace("1", "１").replace("2", "２").replace("B", "Ｂ")
        return 2 + 2 * [k for k, l in enumerate(labels) if str(l).endswith(fw) or str(l).endswith(p)][0]
    c1, c2 = col("M1B"), col("M2")
    YOY["m1b_m2"] = {r[0].replace("M", ""): num(r[c1]) - num(r[c2]) for r in rows if num(r[c1]) is not None and num(r[c2]) is not None}
except Exception: OUT["errs"].append("m1b " + traceback.format_exc()[-300:])
# ---------- 轉換：年增率 → 3 個月平均 ----------
def yoy(s):
    return {k: 100 * (v / s[ym_add(k, -12)] - 1) for k, v in s.items() if s.get(ym_add(k, -12))}
def ma3(s):
    return {k: (s[k] + s[ym_add(k, -1)] + s[ym_add(k, -2)]) / 3 for k in s if ym_add(k, -1) in s and ym_add(k, -2) in s}
X = {}
for k in ("elec_other", "elec_electronics", "teu", "exports", "orders"):
    if SER.get(k): X[k] = ma3(yoy(SER[k]))
for k in ("loans", "m1b_m2"):
    if YOY.get(k): X[k] = ma3(YOY[k])
if SER.get("ndc_lead"): X["ndc_lead"] = SER["ndc_lead"]   # 基準：國發會領先指標（已是循環值）
coin = SER.get("coin", {})
def corr(a, b):
    n = len(a)
    if n < 24: return None
    ma, mb = sum(a) / n, sum(b) / n; va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb), 3) if va and vb else None
def lagcorr(s, k, lo, hi):   # s 的 t 月 vs 同時指標 t+k 月
    ks = [t for t in s if lo <= t <= hi and ym_add(t, k) in coin]
    return corr([s[t] for t in ks], [coin[ym_add(t, k)] for t in ks]), len(ks)
TR, TE = ("200701", "201812"), ("201901", "209912")
res = {}
for k, s in X.items():
    rng = (min(s), max(s)) if s else None
    tr = {lag: lagcorr(s, lag, *TR) for lag in range(-6, 13)}
    best = max((lag for lag in tr if tr[lag][0] is not None), key=lambda lag: tr[lag][0], default=None)
    te = {lag: lagcorr(s, lag, *TE) for lag in range(-6, 13)}
    bte = max((lag for lag in te if te[lag][0] is not None), key=lambda lag: te[lag][0], default=None)
    res[k] = {"range": rng, "n": len(s), "train_best_lag": best, "train_corr": tr[best][0] if best is not None else None, "train_lag0": tr[0][0],
              "test_corr_at_train_lag": te[best][0] if best is not None else None, "test_best_lag": bte, "test_best_corr": te[bte][0] if bte is not None else None, "test_lag0": te[0][0],
              "latest": [(t, round(s[t], 2)) for t in sorted(s)[-3:]]}
OUT["components"] = res
# ---------- 合成：通過的成分等權 z 分數 ----------
ok = [k for k, r in res.items() if k != "ndc_lead" and r["train_best_lag"] is not None and r["train_best_lag"] >= 1 and (r["train_corr"] or 0) >= 0.4]
OUT["passed"] = ok
def zs(s, lo, hi):
    v = [s[t] for t in s if lo <= t <= hi]; m = sum(v) / len(v); sd = math.sqrt(sum((x - m) ** 2 for x in v) / len(v)) or 1
    return {t: (x - m) / sd for t, x in s.items()}
for name, keys in (("composite_passed", ok), ("composite_all", [k for k in X if k != "ndc_lead"])):
    if not keys: continue
    Z = {k: zs(X[k], *TR) for k in keys}
    months = sorted(set.intersection(*[set(z) for z in Z.values()]))
    C = {t: sum(Z[k][t] for k in keys) / len(keys) for t in months}
    X[name] = C
    out = {"keys": keys, "n": len(C), "range": (months[0], months[-1]) if months else None}
    for lab, (lo, hi) in (("train", TR), ("test", TE)):
        cc = {lag: lagcorr(C, lag, lo, hi)[0] for lag in range(-3, 10)}
        out[lab] = cc
    out["latest"] = [(t, round(C[t], 2)) for t in months[-6:]]
    OUT[name] = out
# ---------- 轉折點：同時指標 vs 合成指數 vs 國發會領先 ----------
def turns(s, w=6, amp=0.8):
    ks = sorted(s); out = []
    for i in range(w, len(ks) - w):
        v = s[ks[i]]; win = [s[ks[j]] for j in range(i - w, i + w + 1)]
        if v == max(win) and v - min(win) >= amp: out.append((ks[i], "峰"))
        elif v == min(win) and max(win) - v >= amp: out.append((ks[i], "谷"))
    return out
ct = [x for x in turns(coin, 6, 1.5) if x[0] >= "200701"]
OUT["coin_turns"] = ct
for k in ("composite_passed", "composite_all", "ndc_lead"):
    if X.get(k):
        tt = turns(X[k], 6, 0.6 if k != "ndc_lead" else 1.5)
        rows = []
        for t, kind in ct:   # 同時指標每個轉折前後 12 個月內，同方向最近的轉折
            cands = [(abs(int(ym_add(a, 0)) - 0), a) for a, b in tt if b == kind]
            near = [a for a, b in tt if b == kind and ym_add(t, -12) <= a <= ym_add(t, 6)]
            if near:
                a = min(near, key=lambda x: abs((int(x[:4]) * 12 + int(x[4:])) - (int(t[:4]) * 12 + int(t[4:]))))
                rows.append((t, kind, a, (int(t[:4]) * 12 + int(t[4:])) - (int(a[:4]) * 12 + int(a[4:]))))
            else:
                rows.append((t, kind, None, None))
        OUT["turns_" + k] = rows
open("probe.json", "w").write(json.dumps(OUT, ensure_ascii=False, indent=1)); print("done")
