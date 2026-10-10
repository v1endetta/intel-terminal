import os, json, re, io, csv, zipfile, requests, collections
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; github.com/v1endetta/intel-terminal)"}
rep = {}
r = requests.get("https://data.gov.tw/datasets/export/csv", headers=H, timeout=180)
rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "ignore"))))
hdr = rows[0]; idx = {h: i for i, h in enumerate(hdr)}
def col(r, nm): return r[idx[nm]] if idx[nm] < len(r) else ""
meta = {col(r, "資料集識別碼"): r for r in rows[1:]}
def urls(i): return [u for u in col(meta[i], "資料下載網址").split(";") if u] if i in meta else []
def peek(name, u, n=1500):
    try:
        x = requests.get(u, headers=H, timeout=120)
        c = x.content
        info = {"status": x.status_code, "len": len(c), "url": u[:200]}
        if c[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(c)); info["zip"] = [(f.filename, f.file_size) for f in z.infolist()][:12]
            big = max(z.infolist(), key=lambda f: f.file_size); c = z.read(big); info["zip_pick"] = big.filename
        s = c.decode("utf-8-sig", "ignore")
        info["head"] = s[:n]; info["tail"] = s[-600:]
        rep[name] = info
        return s
    except Exception as e:
        rep[name] = {"err": repr(e)[:200], "url": u[:200]}
# B 簽帳
for i in ("175018", "38311", "25364"):
    us = urls(i); rep["meta_" + i] = {"title": col(meta[i], "資料集名稱") if i in meta else None, "urls": us[:4], "fields": col(meta[i], "主要欄位說明")[:300] if i in meta else None}
    if us: peek("s_" + i, us[0])
# E 捷運
i = "128506"; us = urls(i); rep["meta_" + i] = {"urls": us[:4], "fields": col(meta[i], "主要欄位說明")[:300], "desc": col(meta[i], "資料集描述")[:300]}
if us: peek("s_128506", us[0], 2500)
# G 銷售額 second link
us = urls("161861"); rep["meta_161861"] = us[:4]
for k, u in enumerate(us[:3]): peek(f"s_161861_{k}", u, 1200)
# H 外銷訂單 tail, I 景氣 zip
peek("s_6845", urls("6845")[0], 300)
peek("s_6099", urls("6099")[0], 1200)
# F 新設立
for i in ("29260", "29254"):
    us = urls(i); rep["meta_" + i] = us[:3]
    if us: peek("s_" + i, us[0], 1200)
# J 農產品進口：彙整品名，找寵物食品、咖啡、茶等
s = peek("s_40331", urls("40331")[0], 300)
if s:
    try:
        js = json.loads(s)
        rep["imp_n"] = len(js)
        rep["imp_dates"] = collections.Counter(x["date"] for x in js).most_common(5)
        names = collections.Counter(x["dname1"] for x in js)
        rep["imp_names_n"] = len(names)
        rep["imp_hits"] = [n for n in names if re.search(r"狗|犬|貓|寵物|咖啡|茶|酪梨|燕麥|乳|起司|乾酪|巧克力|可可|堅果|藍莓|草莓|牛肉|鮭", n)][:80]
    except Exception as e:
        rep["imp_err"] = repr(e)[:200]
# 台北 1999
rep["tp1999"] = [(col(r, "資料集識別碼"), col(r, "資料集名稱")[:50], col(r, "更新頻率"), col(r, "詮釋資料更新時間")[:10]) for r in rows[1:] if re.search(r"1999", col(r, "資料集名稱")) and re.search(r"臺北|台北", col(r, "資料集名稱") + col(r, "提供機關"))][:15]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
