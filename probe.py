import os, json, requests
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; https://github.com/v1endetta/intel-terminal)"}
rep = {}
for pkg in ("crewai", "openai"):
    r = requests.get(f"https://pypistats.org/api/packages/{pkg}/overall", params={"mirrors": "false"}, headers=H, timeout=40)
    js = r.json().get("data", [])
    days = sorted((x["date"], x["downloads"], x["category"]) for x in js)
    rep[pkg] = {"n": len(days), "cats": sorted(set(c for _, _, c in days)), "first": days[:3], "last": days[-12:]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
