import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
def text(h):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S); t = re.sub(r"<[^>]+>", "\n", t); return re.sub(r"\n\s*\n+", "\n", t)
# terms pages
r = S.get("https://www.tasker.com.tw/cases", timeout=40); h = r.text
rep["tasker_terms_links"] = [l for l in dict.fromkeys(re.findall(r'href="([^"]+)"[^>]*>\s*([^<]{0,12})', h)) if re.search("條款|隱私|規範", l[1])]
rr = S.get("https://www.pro360.com.tw/case", timeout=40)
rep["pro_terms_links"] = [l for l in dict.fromkeys(re.findall(r'href="([^"]+)"[^>]*>\s*([^<]{0,12})', rr.text)) if re.search("條款|隱私|規範|政策", l[1])]
for name, links, base in (("tasker", rep["tasker_terms_links"], "https://www.tasker.com.tw"), ("pro", rep["pro_terms_links"], "https://www.pro360.com.tw")):
    for href, lab in links[:3]:
        u = href if href.startswith("http") else base + href
        try:
            t = text(S.get(u, timeout=40).text)
            hits = [m.start() for m in re.finditer(r"爬|擷取|抓取|自動化|機器人|程式|robot|crawl|spider|蒐集|收集|重製|複製", t)]
            rep[f"{name}_terms {u}"] = {"len": len(t), "snips": [t[max(0, i-120):i+160].replace("\n", " ") for i in hits[:12]]}
        except Exception as e:
            rep[f"{name}_terms {u}"] = {"err": repr(e)[:150]}
# tasker NUXT data structure and pagination
m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
if m:
    arr = json.loads(m.group(1))
    rep["nuxt_len"] = len(arr)
    # find dicts that look like a case
    cases = [x for x in arr if isinstance(x, dict) and any(k in x for k in ("case_title", "title", "caseTitle")) and any("budget" in k.lower() or "price" in k.lower() for k in x)]
    rep["case_keys"] = [list(c.keys()) for c in cases[:2]]
    def deref(v, depth=0):
        if depth > 3: return v
        if isinstance(v, int) and 0 <= v < len(arr): return deref(arr[v], depth + 1) if not isinstance(arr[v], (dict, list)) else arr[v] if depth > 1 else arr[v]
        return v
    samp = []
    for c in cases[:3]:
        samp.append({k: (arr[v] if isinstance(v, int) and v < len(arr) and not isinstance(arr[v], (dict, list)) else (str(arr[v])[:200] if isinstance(v, int) and v < len(arr) else v)) for k, v in c.items()})
    rep["case_samples"] = samp
    tagd = [x for x in arr if isinstance(x, dict) and "name" in x and ("parent" in x or "lv" in str(list(x.keys())) or "slug" in x)][:5]
    rep["tag_dicts"] = [{k: (arr[v] if isinstance(v, int) and v < len(arr) else v) for k, v in d.items()} for d in tagd]
for u in ("https://www.tasker.com.tw/cases?page=2", "https://www.tasker.com.tw/cases?p=2"):
    t = text(S.get(u, timeout=40).text); i = t.find("最新"); rep[u] = t[i:i+500]
# PRO360 listing structure
t = text(rr.text); i = t.find("輸入關鍵字找案件"); rep["pro_list"] = t[i:i+5000]
rep["pro_case_links"] = list(dict.fromkeys(re.findall(r'href="(https://www\.pro360\.com\.tw/case/[^"]+)"', rr.text)))[40:80]
rep["pro_api"] = list(dict.fromkeys(re.findall(r'(https://api\.pro360\.com\.tw/[^"\'\s]+)', rr.text)))[:20]
for u in ("https://www.pro360.com.tw/case/subgenre/software_development", "https://www.pro360.com.tw/case/subgenre/marketing", "https://www.pro360.com.tw/case?page=2"):
    try:
        x = S.get(u, timeout=40); rep[u] = {"status": x.status_code, "text": text(x.text)[:2500]}
    except Exception as e:
        rep[u] = {"err": repr(e)[:150]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
