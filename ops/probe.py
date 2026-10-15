import requests, json, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
out = {}
t = S.get("https://www.mnd.gov.tw/news/plaactlist", timeout=40).text
i = t.find("news/plaact/87995")
out["list_chunk"] = t[i - 1500:i + 2500]
for pid in ("87995", "87985"):
    d = S.get(f"https://www.mnd.gov.tw/news/plaact/{pid}", timeout=40).text
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", d, flags=re.S)
    j = body.find("架次")
    out[pid] = {"text": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))[:200],
                "around": body[max(0, j - 3000):j + 1500], "imgs": re.findall(r'<img[^>]+src="([^"]+)"', d)[:12]}
p = S.get("https://www.mnd.gov.tw/news/plaactlist/2", timeout=40).text
out["p2_links"] = re.findall(r'news/plaact/\d+', p)[:20]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
