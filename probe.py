import os, json, re, requests
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (intel-terminal research)"}
rep = {}
def text(html):
    html = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
    t = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", t)
for p in ("/", "/tools", "/licenses", "/sources", "/datasets", "/docs", "/en", "/zh-TW/tools", "/llms.txt", "/llms-full.txt", "/sitemap.xml", "/en/playground/company"):
    try:
        r = requests.get("https://hub.twinkleai.tw" + p, headers=H, timeout=60)
        raw = r.text
        rep[p] = {"status": r.status_code, "len": len(raw), "text": text(raw)[:30000] if "html" in (r.headers.get("content-type") or "") else raw[:30000],
                  "tools": sorted(set(re.findall(r"\b((?:tw|us|hk|jp|kr|sg|uk|opendata|twtools|pcc|fred|sec)[_\-][a-z0-9_\-]{3,60})\b", raw)))[:600]}
    except Exception as e:
        rep[p] = {"err": repr(e)[:200]}
try:
    r = requests.get("https://api.twinkleai.tw/mcp/", headers=H, timeout=30)
    rep["mcp_noauth"] = {"status": r.status_code, "head": r.text[:500]}
except Exception as e:
    rep["mcp_noauth"] = {"err": repr(e)[:200]}
for u in ("https://pcc-api.openfun.app/", "https://pcc-api.openfun.app/robots.txt", "https://openfunltd.github.io/pcc-viewer/"):
    try:
        r = requests.get(u, headers=H, timeout=30); rep[u] = {"status": r.status_code, "text": text(r.text)[:3000]}
    except Exception as e:
        rep[u] = {"err": repr(e)[:200]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
