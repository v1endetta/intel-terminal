import os, json, requests, re
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; https://github.com/v1endetta/intel-terminal)"}
rep = {}
u = ("https://statis.moi.gov.tw/micst/webMain.aspx?sys=220&kind=21&type=1&funid=c0510302&cycle=41&outmode=12&utf=1&compmode=0&outkind=3&fldlst=11"
     "&codspc0=0,2,3,2,6,1,9,1,12,1,15,16,&codspc1=0,14,&ym={a}&ymt={b}")
for a, b in (("10101", "11508"), ("11401", "11509")):
    try:
        r = requests.get(u.format(a=a, b=b), headers=H, timeout=90)
        t = r.content.decode("utf-8-sig", "replace"); L = t.strip().splitlines()
        tot = [l for l in L if "區域別總計" in l and ("買賣" in l)]
        rep[a] = {"st": r.status_code, "n": len(L), "tot_n": len(tot), "tot_head": tot[:4], "tot_tail": tot[-3:], "items": sorted(set(re.findall(r"總計/ ([^\"]+)\"", t)))[:20]}
    except Exception as e:
        rep[a] = str(e)[:200]
r = requests.get("https://data.taipei/api/dataset/ce4ea2c6-6334-44f8-945a-5705492b187d/resource/02c7bb70-2113-4daf-81d3-5c14b9ae26df/download", headers=H, timeout=60)
L = r.content.decode("utf-8-sig", "replace").splitlines()
rep["tpe"] = {"cats": sorted(set(l.split(",")[0] for l in L[1:])), "n": len(L)}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
