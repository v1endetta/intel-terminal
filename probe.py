import os, json, re, requests
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (intel-terminal personal research)"}
rep = {}
r = requests.get("https://www.fao.org/worldfoodsituation/foodpricesindex/en/", headers=H, timeout=60)
links = re.findall(r'href="([^"]+\.(?:csv|xlsx?)[^"]*)"', r.text, re.I)
rep["links"] = links[:20]
for u in links[:6]:
    if not u.startswith("http"):
        u = "https://www.fao.org" + u
    try:
        x = requests.get(u, headers=H, timeout=60)
        rep[u] = {"status": x.status_code, "len": len(x.content), "head": x.content[:800].decode("utf-8-sig", "ignore") if "csv" in u.lower() else None}
    except Exception as e:
        rep[u] = {"err": repr(e)[:200]}
i = r.text.find("icense"); rep["lic_ctx"] = re.sub(r"<[^>]+>", " ", r.text[max(0, i - 400):i + 400]) if i >= 0 else None
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
