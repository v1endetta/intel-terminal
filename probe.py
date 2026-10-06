import os, json, re, io, csv, zipfile, collections, time, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
try:
    j = S.get("https://data.gov.tw/api/v2/rest/dataset/9400", timeout=60).json()
    rep["meta"] = json.dumps(j, ensure_ascii=False)[:3000]
except Exception as e:
    rep["meta_err"] = repr(e)[:300]
urls = ["https://eip.fia.gov.tw/data/BGMOPEN1.zip", "https://eip.fia.gov.tw/data/BGMOPEN1.csv"]
try:
    for d in (j.get("result") or {}).get("distribution") or []:
        u = d.get("resourceDownloadUrl") or d.get("downloadURL")
        if u and u not in urls:
            urls.insert(0, u)
except Exception:
    pass
rep["urls"] = urls
raw = None
for u in urls:
    try:
        t0 = time.time(); r = S.get(u, timeout=300)
        rep[f"get {u}"] = {"status": r.status_code, "len": len(r.content), "ct": r.headers.get("content-type"), "sec": round(time.time() - t0)}
        if r.status_code == 200 and len(r.content) > 1e6:
            raw = r.content; break
    except Exception as e:
        rep[f"get {u}"] = {"err": repr(e)[:200]}
if raw:
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw)); rep["zip"] = [(i.filename, i.file_size) for i in z.infolist()]
        raw = z.read(z.infolist()[0])
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            txt = raw.decode(enc); rep["enc"] = enc; break
        except UnicodeDecodeError:
            continue
    lines = txt.splitlines()
    rep["n_lines"] = len(lines); rep["head"] = lines[:4]
    rd = csv.reader(lines)
    hdr = next(rd)
    # some files have a title row first
    if len(hdr) < 5:
        hdr = next(rd)
    rep["hdr"] = hdr
    ci = {h.strip(): i for i, h in enumerate(hdr)}
    idate = next((i for h, i in ci.items() if "設立日期" in h), None)
    icode = [i for h, i in ci.items() if re.match(r"^行業代號\d?$", h)]
    iname = [i for h, i in ci.items() if re.match(r"^名稱\d?$", h)]
    rep["idx"] = [idate, icode, iname]
    bymonth = collections.Counter(); names = {}; recent = collections.Counter(); ly = collections.Counter(); org = collections.Counter()
    n = 0
    for row in rd:
        n += 1
        if idate is None or len(row) <= max(icode + [idate]):
            continue
        d = row[idate].strip()
        m = re.match(r"^(\d{2,3})(\d{2})(\d{2})$", d)
        if not m:
            continue
        ym = f"{int(m.group(1)) + 1911}-{m.group(2)}"
        bymonth[ym] += 1
        c = row[icode[0]].strip(); nm = row[iname[0]].strip() if iname else ""
        if c:
            names.setdefault(c, nm)
            if ym >= "2026-07": recent[c] += 1
            if "2025-07" <= ym <= "2025-09": ly[c] += 1
        if n < 6:
            rep.setdefault("sample", []).append(row)
    rep["rows"] = n
    rep["bymonth_tail"] = sorted(bymonth.items())[-30:]
    rep["n_codes"] = len(names)
    rep["code_len"] = collections.Counter(len(c) for c in names).most_common()
    rep["top_recent"] = [(c, names[c], recent[c], ly[c]) for c, _ in recent.most_common(60)]
    kw = r"寵物|飲料|咖啡|健身|運動|美容|美甲|二手|舊貨|室內裝|裝潢|長期照|照顧|老人|托育|補習|攝影|服飾|化妝|保健|旅行|民宿|旅館|網路|電子購物|遊戲|玩具|家具|按摩|瑜伽|休閒"
    rep["kw_codes"] = [(c, names[c], recent[c], ly[c]) for c in sorted(names) if re.search(kw, names[c])][:400]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
