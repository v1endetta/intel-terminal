import requests, json, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
for u in ("https://statis.moi.gov.tw/micst/webMain.aspx?k=menueg",
          "https://statis.moi.gov.tw/micst/webMain.aspx?k=defjsp",
          "https://statis.moi.gov.tw/micst/webMain.aspx?sys=100&funid=defjsp"):
    try:
        t = S.get(u, timeout=40).text
        hits = []
        for m in re.finditer(r"建造執照|建築執照|使用執照|開工", t):
            hits.append(t[max(0, m.start() - 300): m.end() + 120])
        out[u] = {"len": len(t), "hits": hits[:12], "funids": sorted(set(re.findall(r"funid=([a-z]\d{7})", t)))[:400]}
    except Exception as e:
        out[u] = repr(e)
# 猜幾個常見代碼
for fid in ("c0910101", "c0910102", "c0920101", "c0930101", "m0910101", "c0710101", "c0720101", "c0730101", "c0740101", "c0750101"):
    try:
        url = (f"https://statis.moi.gov.tw/micst/webMain.aspx?sys=220&kind=21&type=1&funid={fid}&cycle=41&outmode=12&utf=1"
               f"&compmode=0&outkind=1&ym=11401&ymt=11512&fldspc=0,30,")
        t = S.get(url, timeout=40).content.decode("utf-8-sig", "replace")
        out[fid] = t[:500]
    except Exception as e:
        out[fid] = repr(e)
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
