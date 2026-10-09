import os, json, re, requests, collections
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
TK = "43b47d07-4795-45d9-819a-9c71c72e4105"
B = "https://cloud.tipo.gov.tw/S220/opdataapi/api/"
for ds in (41664, 15992):
    j = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", timeout=40).json()["result"]
    rep[f"notes{ds}"] = (j.get("notes") or "")[:1500]
def api(ep, **p):
    r = S.get(B + ep, params={"tk": TK, "format": "json", **p}, timeout=120); return r.json()
t = api("TmarkAppl", top=1)["total-count"]; rep["tm_total"] = t
j = api("TmarkAppl", top=1000, skip=t - 1000)
c = j["tmarkappl"]["tmarkcontent"]; rep["tm_n"] = len(c)
rep["tm_dates"] = [c[0].get("appl-date"), c[-1].get("appl-date"), c[0].get("appl-no"), c[-1].get("appl-no")]
rep["tm_months"] = collections.Counter((x.get("appl-date") or "")[:7] for x in c).most_common(6)
rep["tm_sample"] = [{k: x.get(k) for k in ("appl-no", "appl-date", "tmark-name", "tmark-class-desc")} | {"cls": [g.get("goodsclass-code") for g in x.get("goodsclasses") or []][:4], "app": [a.get("chinese-name") for a in ((x.get("parties") or {}).get("applicants") or [])][:2]} for x in c[-6:]]
rep["tm_keys"] = list(c[-1].keys())
try:
    rep["tm_top5000"] = len(api("TmarkAppl", top=5000, skip=t - 5000)["tmarkappl"]["tmarkcontent"])
except Exception as e:
    rep["tm_top5000"] = repr(e)[:150]
tp = api("PatentPub", top=1)["total-count"]; rep["pp_total"] = tp
jp = api("PatentPub", top=500, skip=tp - 500)
pc = jp["tw-patent-pub"]["patentcontent"]; rep["pp_n"] = len(pc)
rep["pp_keys"] = list(pc[-1].keys())
rep["pp_sample"] = json.dumps(pc[-1], ensure_ascii=False)[:2500]
rep["pp_notice_dates"] = collections.Counter(((x.get("publication-reference") or {}).get("notice-date") or "")[:7] for x in pc).most_common(8)
pol = S.get("https://join.gov.tw/toOpenData/ey/policy", timeout=120).json()
ds = sorted([x.get("發佈日期") for x in pol if re.match(r"\d{4}-", x.get("發佈日期") or "")])
rep["pol_n"] = len(pol); rep["pol_latest"] = ds[-5:]
recent = [x for x in pol if (x.get("發佈日期") or "") >= "2026-09-01"]
rep["pol_recent"] = [{k: x.get(k) for k in ("標題", "發佈日期", "下線日期", "關注數量", "留言數量")} for x in recent[:12]]
rep["pol_keys"] = list(pol[-1].keys())
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
