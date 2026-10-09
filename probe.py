import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
r = S.get("https://www.tasker.com.tw/cases", timeout=40); h = r.text
rep["cat_links"] = list(dict.fromkeys(re.findall(r'href="(/cases[^"]*)"', h)))[:80]
m = re.search(r'window\.__NUXT__=(.{0,200})', h); rep["nuxt"] = bool(m)
rep["nuxt_data"] = [s[:200] for s in re.findall(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', h, re.S)][:1]
t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S); t = re.sub(r"<[^>]+>", "\n", t); t = re.sub(r"\n\s*\n+", "\n", t)
i = t.find("最新"); rep["list_text"] = t[i:i+9000]
for u in ["https://www.tasker.com.tw/cases?category=2", "https://www.tasker.com.tw/cases/software", "https://www.pro360.com.tw/case/subgenre/web_and_program", "https://www.pro360.com.tw/case/subgenre/it_service"]:
    try:
        rr = S.get(u, timeout=40); tt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", rr.text, flags=re.S); tt = re.sub(r"<[^>]+>", "\n", tt); tt = re.sub(r"\n\s*\n+", "\n", tt)
        rep[u] = {"status": rr.status_code, "final": rr.url, "text": tt[:3000]}
    except Exception as e:
        rep[u] = {"err": repr(e)[:200]}
r2 = S.get("https://www.pro360.com.tw/case", timeout=40)
rep["pro_links"] = [l for l in dict.fromkeys(re.findall(r'href="(https://www\.pro360\.com\.tw/case/subgenre/[^"]+)"', r2.text)) if re.search(r"web|program|it_|software|app|embedded|system", l)]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
