import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
def text(h):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S); t = re.sub(r"<[^>]+>", "\n", t); return re.sub(r"\n\s*\n+", "\n", t)
rep["robots"] = S.get("https://www.104.com.tw/robots.txt", timeout=30).text[:2500]
cands = ["https://www.104.com.tw/public/rule/member", "https://www.104.com.tw/public/rule/privacy", "https://static.104.com.tw/104i/rule/rule.html",
         "https://www.104.com.tw/jobs/main/", "https://www.104.com.tw/public/rule/term"]
h = S.get("https://www.104.com.tw/jobs/main/", timeout=30).text
rep["footer_links"] = [l for l in dict.fromkeys(re.findall(r'href="([^"]+)"[^>]*>\s*([^<]{0,16})', h)) if re.search("條款|規範|隱私|服務|政策", l[1])][:20]
for href, lab in rep["footer_links"][:8]:
    u = href if href.startswith("http") else "https://www.104.com.tw" + href
    try:
        t = text(S.get(u, timeout=30).text)
        hits = [m.start() for m in re.finditer(r"爬|擷取|抓取|自動化|機器人|robot|crawl|spider|蜘蛛|大量下載|程式.{0,6}(下載|存取|蒐集)", t)]
        rep["T " + u] = {"lab": lab, "len": len(t), "snips": [t[max(0, i-150):i+200].replace("\n", " ") for i in hits[:8]]}
    except Exception as e:
        rep["T " + u] = {"err": repr(e)[:150]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
