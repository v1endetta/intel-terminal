# 暫時實測：論壇來源（Dcard、Mobile01、巴哈姆特）能不能抓、robots 怎麼寫；民調擷取試跑。金鑰一律不輸出
import json, os, re, sys, tempfile, traceback
out = {}
import requests
from curl_cffi import requests as cffi
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
def tryget(name, url, js=False):
    r0 = {}
    for how in ("requests", "cffi"):
        try:
            r = requests.get(url, headers=UA, timeout=25) if how == "requests" else cffi.get(url, impersonate="chrome", timeout=25)
            t = r.text
            r0[how] = {"status": r.status_code, "bytes": len(r.content), "cf": ("cf-mitigated" in r.headers) or ("Just a moment" in t[:3000]), "head": re.sub(r"\s+", " ", t[:300])}
            if js and r.status_code == 200:
                try:
                    j = r.json(); r0[how]["n"] = len(j) if isinstance(j, list) else len(j.get("data", j) if isinstance(j, dict) else [])
                    r0[how]["sample"] = [x.get("title") for x in j[:5]] if isinstance(j, list) else None
                except Exception as e:
                    r0[how]["json_err"] = str(e)[:80]
        except Exception as e:
            r0[how] = {"err": f"{type(e).__name__}: {str(e)[:120]}"}
    out[name] = r0
def cf(url):
    return cffi.get(url, impersonate="chrome", timeout=25)
try:
    r = cf("https://www.mobile01.com/robots.txt"); out["m01_robots_full"] = r.text[:4000]
    r = cf("https://www.mobile01.com/hottopics.php"); t = r.text
    out["m01_hot"] = {"status": r.status_code, "titles": re.findall(r'<a[^>]+href="(topicdetail\.php\?[^"]+)"[^>]*>([^<]{6,80})</a>', t)[:25]}
except Exception as e:
    out["m01_hot"] = {"err": str(e)[:150]}
for name, url in [("baha_index", "https://forum.gamer.com.tw/"), ("baha_hot", "https://forum.gamer.com.tw/A.php?bsn=0"), ("dcard_sitemap", "https://www.dcard.tw/sitemaps/index.xml"),
                  ("dcard_f", "https://www.dcard.tw/f")]:
    try:
        r = cf(url); t = r.text
        out[name] = {"status": r.status_code, "bytes": len(t), "title": (re.search(r"<title>([^<]*)", t) or [None, ""])[1][:80],
                     "links": re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,60})</a>', t)[:25]}
    except Exception as e:
        out[name] = {"err": str(e)[:150]}
# 民調試跑
try:
    tmp = tempfile.mkdtemp(); os.environ["INTEL_DATA_DIR"] = tmp
    src = open("fetch.py", encoding="utf-8").read(); cut = src.index('\nrun("pulse", p_pulse)\n')
    g = {"__name__": "probe", "__file__": os.path.abspath("fetch.py")}
    exec(compile(src[:cut], "fetch.py", "exec"), g)
    res = g["p_polls"]()
    out["polls"] = {"n_new": res["n_new"], "errs": res["errs"], "latest": [(r["org"], r["subject"], r["metric"], r["value"], r["race"], r["title"][:50], (r["at"] or "")[:10]) for r in res["latest"][:25]],
                    "tracks": [(t["subject"], t["metric"], t["n"]) for t in res["tracks"]], "races": {k: [(r["subject"], r["value"], r["org"]) for r in v] for k, v in res["races"].items()}}
except Exception as e:
    out["polls"] = {"err": re.sub(r"key=[^&\s]+", "key=***", traceback.format_exc()[-800:])}
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:1500])
