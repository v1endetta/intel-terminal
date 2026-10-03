import os, json, requests
os.makedirs("out8", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
slugs = ["taichung","taipei","ntpc","newtaipei","taoyuan","tycg","hsinchu","hccg","hsinchucounty","hsinchu_county","zhubei","miaoli","chiayi","chiayicity","chiayicounty","tainan","kaohsiung","kh","pingtung","taitung"]
for s in slugs:
    u = f"https://ybjson02.youbike.com.tw:60008/yb2/{s}/gwjs.json"
    try:
        r = S.get(u, timeout=25)
        rep[s] = {"status": r.status_code, "bytes": len(r.content), "head": r.text[:400]}
    except Exception as e:
        rep[s] = {"err": repr(e)[:160]}
for k,u in {"root":"https://ybjson02.youbike.com.tw:60008/yb2/","yb1":"https://ybjson01.youbike.com.tw:60008/yb2/taoyuan/gwjs.json","tycg_api":"https://opendata.tycg.gov.tw/api/v1/datalist/be75ea89-fe9c-4aa0-befa-82c8575d4d9b"}.items():
    try:
        r = S.get(u, timeout=25); rep[k] = {"status": r.status_code, "bytes": len(r.content), "head": r.text[:600]}
    except Exception as e:
        rep[k] = {"err": repr(e)[:160]}
json.dump(rep, open("out8/report.json", "w"), ensure_ascii=False, indent=1)
