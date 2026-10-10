import os, json, re, requests
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; github.com/v1endetta)"}
rep = {}
# Polymarket: taiwan tag events
try:
    r = requests.get("https://gamma-api.polymarket.com/events", params={"tag_slug": "taiwan", "closed": "false", "limit": 100}, headers=H, timeout=40)
    evs = r.json()
    rep["poly_tw"] = [{"title": e.get("title"), "slug": e.get("slug"), "vol": e.get("volume"), "vol24": e.get("volume24hr"), "liq": e.get("liquidity"), "end": e.get("endDate"),
                       "outs": [(m.get("groupItemTitle"), m.get("outcomePrices")) for m in (e.get("markets") or [])][:6]} for e in evs if re.search(r"mayor|local|taiwan", e.get("title") or "", re.I)]
except Exception as e:
    rep["poly_err"] = repr(e)[:300]
# Wikipedia pages
W = "https://zh.wikipedia.org/w/api.php"
for t in ("2026年臺北市長選舉", "2026年新北市長選舉", "2026年臺中市長選舉", "2026年臺南市長選舉", "2026年高雄市長選舉", "2026年中華民國地方公職人員選舉"):
    try:
        js = requests.get(W, params={"action": "parse", "page": t, "prop": "sections|wikitext", "format": "json", "variant": "zh-tw", "redirects": 1}, headers=H, timeout=40).json()
        if "error" in js:
            rep["wiki_" + t] = js["error"].get("info"); continue
        wt = js["parse"]["wikitext"]["*"]
        secs = [s["line"] for s in js["parse"]["sections"]]
        i = wt.find("民意調查"); j = wt.find("民調")
        rep["wiki_" + t] = {"title": js["parse"]["title"], "len": len(wt), "secs": secs[:40],
                            "poll_snip": wt[i:i + 2500] if i >= 0 else (wt[j:j + 2500] if j >= 0 else None)}
    except Exception as e:
        rep["wiki_" + t] = repr(e)[:200]
try:
    js = requests.get("https://en.wikipedia.org/w/api.php", params={"action": "parse", "page": "2026 Taiwanese local elections", "prop": "sections", "format": "json"}, headers=H, timeout=40).json()
    rep["enwiki_secs"] = [s["line"] for s in js["parse"]["sections"]]
except Exception as e:
    rep["enwiki_err"] = repr(e)[:200]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
