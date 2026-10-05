import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
U = {
 "rss": "https://www.mckinsey.com/insights/rss",
 "rss_aspx": "https://www.mckinsey.com/Insights/rss.aspx",
 "tech_page": "https://www.mckinsey.com/capabilities/tech-and-ai/our-insights",
 "featured": "https://www.mckinsey.com/featured-insights",
 "mgi": "https://www.mckinsey.com/mgi/our-research",
 "podcast": "https://www.omnycontent.com/d/playlist/708664bd-6843-4623-8066-aede00ce0c8a/3f6f52af-fba1-496d-b11b-af040139456a/bfe0b44a-082f-495a-952a-af0401394590/podcast.rss",
 "article": "https://www.mckinsey.com/industries/financial-services/our-insights/pause-pivot-or-accelerate-saas-in-the-age-of-agentic-ai",
 "bcg_rss": "https://www.bcg.com/rss",
 "bain_rss": "https://www.bain.com/insights/rss/",
 "deloitte_insights": "https://www2.deloitte.com/us/en/insights.rss.xml",
}
for k, u in U.items():
    try:
        r = S.get(u, timeout=30)
        t = r.text
        rep[k] = {"status": r.status_code, "bytes": len(t), "ct": r.headers.get("content-type", "")[:40],
                  "items": len(re.findall(r"<item[ >]", t)), "head": re.sub(r"\s+", " ", t[:300])}
        if "<item" in t:
            it = t[t.index("<item"):][:2500]
            rep[k]["item0"] = re.sub(r"\s+", " ", it)
            rep[k]["cats"] = sorted(set(re.findall(r"<category[^>]*>(?:<!\[CDATA\[)?([^<\]]+)", t)))[:80]
    except Exception as e:
        rep[k] = {"err": repr(e)[:200]}
open("out25/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
