import requests, json
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
for a in range(1, 10):
    for b in range(1, 10):
        for c in ("0101", "0201"):
            fid = f"c0{a}{b}{c}"
            try:
                url = (f"https://statis.moi.gov.tw/micst/webMain.aspx?sys=220&kind=21&type=1&funid={fid}&cycle=41&outmode=12&utf=1"
                       f"&compmode=0&outkind=1&ym=11501&ymt=11512&fldspc=0,30,")
                t = S.get(url, timeout=25).content.decode("utf-8-sig", "replace")
                if "不存在" not in t[:40]:
                    out[fid] = t[:160]
            except Exception as e:
                out[fid] = repr(e)[:80]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
