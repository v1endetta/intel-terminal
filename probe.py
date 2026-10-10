import os, json, re, io, csv, requests, collections
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research)"}
rep = {}
u = "https://web02.mof.gov.tw/njswww/webMain.aspx?sys=220&ym=11500&ymt=11512&kind=21&type=6&funid=i0520&cycle=41&outmode=12&compmode=00&outkind=3&fldspc=23;23;&codspc0=0;358;&utf=1"
try:
    x = requests.get(u, headers=H, timeout=120)
    t = x.content.decode("utf-8-sig", "ignore")
    rep["mof"] = {"status": x.status_code, "len": len(x.content), "head": t[:1500], "lines": t.count("\n"), "tail": t[-800:]}
except Exception as e:
    rep["mof_err"] = repr(e)[:200]
base = "https://data.moa.gov.tw/service/opendata/agrstatUnit.aspx"
allnames = collections.Counter(); latest = collections.Counter()
for sk in range(0, 200000, 9999):
    try:
        x = requests.get(base, params={"item_code": "GA0410", "dimension_group_code_1": "GA01", "dimension_group_code_2": "XX32", "IsTransData": "1", "UnitId": "634", "$top": "9999", "$skip": str(sk)}, headers=H, timeout=120)
        js = x.json() if x.ok and x.content[:1] == b"[" else []
    except Exception as e:
        rep["moa_err"] = repr(e)[:200]; break
    if not js: break
    for j in js:
        allnames[j["dname1"]] += 1
        if j["date"] >= "11501": latest[j["dname1"]] += j["value"] or 0
    rep.setdefault("pages", []).append((sk, len(js), js[0]["dname1"][:20], js[-1]["dname1"][:20]))
    if len(js) < 9999: break
rep["moa_nnames"] = len(allnames)
rep["moa_hits"] = [n for n in allnames if re.search(r"狗|犬|貓|寵物|咖啡|茶|酪梨|燕麥|乳|起司|乾酪|巧克力|可可|堅果|藍莓|草莓|牛肉|鮭|葡萄酒|啤酒|威士忌|蜂蜜|奇亞|藜麥|蛋", n)][:120]
rep["moa_top2026"] = latest.most_common(40)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
