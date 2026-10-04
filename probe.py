import os, json, requests
os.makedirs("out24", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
try:
    tags = S.get("https://gamma-api.polymarket.com/tags", params={"limit": 300}, timeout=30).json()
    rep["tags"] = [(t.get("slug"), t.get("label")) for t in tags][:300]
except Exception as e: rep["tags_err"] = repr(e)[:200]
for slug in ["fed", "fed-rates", "economy", "geopolitics", "ai", "tech", "crypto", "china", "taiwan", "midterms", "elections", "business", "science", "climate", "ukraine", "middle-east", "trade", "tariffs", "recession", "inflation", "big-tech", "openai"]:
    try:
        ev = S.get("https://gamma-api.polymarket.com/events", params={"tag_slug": slug, "active": "true", "closed": "false", "order": "volume24hr", "ascending": "false", "limit": 6}, timeout=30).json()
        rep["ev_" + slug] = [(e.get("title"), round(e.get("volume24hr") or 0), len(e.get("markets") or [])) for e in ev][:6]
    except Exception as e: rep["ev_" + slug] = repr(e)[:120]
for sym in ["2YY=F", "NIY=F", "RTY=F", "YM=F", "^TNX", "TSM", "TWD=X"]:
    try:
        j = S.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"range": "5d", "interval": "1d"}, timeout=20).json()
        m = j["chart"]["result"][0]["meta"]; rep["y_" + sym] = (m.get("regularMarketPrice"), m.get("currency"), m.get("shortName"))
    except Exception as e: rep["y_" + sym] = repr(e)[:120]
open("out24/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
