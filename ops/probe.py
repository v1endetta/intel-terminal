# 一次性實測：台灣即時景氣指數與全球先行指數的資料源（結果寫 probe.json；金鑰遮掉）
import json, os, re, io, csv, time, traceback
import requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 dalta-intel/1.0 (personal non-commercial)"
FRED = os.environ.get("FRED_API_KEY", "").strip()
OUT = {}
def note(k, **kw): OUT.setdefault(k, {}).update(kw)
def dec(b):
    for e in ("utf-8-sig", "cp950"):
        try: return b.decode(e)
        except Exception: pass
    return b.decode("utf-8", "replace")
def gov(ds):
    k = f"gov_{ds}"
    try:
        j = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", timeout=40).json()["result"]; d = j.get("distribution") or []
        note(k, title=j.get("title"), freq=j.get("updateFrequency"), modified=j.get("modifiedDate"), nd=len(d), dists=[(x.get("resourceDescription", "")[:50], (x.get("resourceDownloadUrl") or "")[:160]) for x in d[:5]])
        u = next((x.get("resourceDownloadUrl") for x in d if x.get("resourceDownloadUrl")), None)
        if u:
            t = dec(S.get(u, timeout=90).content); L = t.strip().splitlines()
            note(k, head=[x[:300] for x in L[:3]], tail=[x[:300] for x in L[-2:]], nlines=len(L))
    except Exception as e: note(k, err=repr(e)[:200])
for ds in (19995, 103262, 103046, 25850, 8307, 8368, 10197, 8367, 31966, 112650, 161209, 29935, 16955, 122521):
    gov(ds)
# 央行開放資料：掃 EF 代碼，找放款與投資、存款、貨幣總計數
cbc = {}
for i in range(1, 60):
    for suf in ("M01",):
        fn = f"EF{i:02d}{suf}"
        try:
            r = S.get(f"https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={fn}", timeout=20)
            if r.status_code == 200 and len(r.content) > 200:
                try:
                    j = r.json(); cbc[fn] = {"keys": list(j.keys())[:6] if isinstance(j, dict) else type(j).__name__, "head": json.dumps(j, ensure_ascii=False)[:400]}
                except Exception:
                    cbc[fn] = {"text": dec(r.content)[:300]}
        except Exception as e:
            cbc[fn] = {"err": repr(e)[:80]}
OUT["cbc_scan"] = cbc
# FRED：韓國出口、中國信用、全球貿易
for sid in ("XTEXVA01KRM667S", "XTEXVA01KRM664S", "CRDQCNAPABIS", "QCNPAM770A", "CRDQKRAPABIS", "XTEXVA01TWM667S", "KORXTEXVA01CXMLM"):
    try:
        j = S.get("https://api.stlouisfed.org/fred/series/observations", params={"series_id": sid, "api_key": FRED, "file_type": "json", "sort_order": "desc", "limit": 3}, timeout=30).json()
        m = S.get("https://api.stlouisfed.org/fred/series", params={"series_id": sid, "api_key": FRED, "file_type": "json"}, timeout=30).json()
        s = (m.get("seriess") or [{}])[0]
        note("fred_" + sid, title=s.get("title"), freq=s.get("frequency"), start=s.get("observation_start"), end=s.get("observation_end"), last=[(o["date"], o["value"]) for o in j.get("observations", [])][:3], err=j.get("error_message"))
    except Exception as e: note("fred_" + sid, err=repr(e)[:150])
# 韓國前 20 天出口：新聞標題
for q, loc in (('Korea exports "first 20 days"', {"hl": "en-US", "gl": "US", "ceid": "US:en"}), ("수출 20일 관세청", {"hl": "ko", "gl": "KR", "ceid": "KR:ko"})):
    try:
        t = S.get("https://news.google.com/rss/search", params={"q": q + " when:60d", **loc}, timeout=30).text
        note("kr20_" + loc["hl"], titles=re.findall(r"<title>([^<]{10,200})</title>", t)[1:12], dates=re.findall(r"<pubDate>([^<]+)</pubDate>", t)[:6])
    except Exception as e: note("kr20_" + loc["hl"], err=repr(e)[:150])
# 韓國關稅廳／KITA 官方
for k, u in (("kcs", "https://www.customs.go.kr/english/main.do"), ("unipass_tradestat", "https://tradedata.go.kr/cts/index_eng.do"), ("cpb_wtm", "https://www.cpb.nl/en/world-trade-monitor"), ("tdcs_from_github", "https://tisvcloud.freeway.gov.tw/history/TDCS/M03A/")):
    try:
        r = S.get(u, timeout=30); note(k, st=r.status_code, len=len(r.content), head=re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", dec(r.content)))[:300], links=[x for x in re.findall(r'href="([^"]+\.(?:xlsx|csv|xls))"', dec(r.content))][:6])
    except Exception as e: note(k, err=repr(e)[:150])
s = json.dumps(OUT, ensure_ascii=False, indent=1)
if FRED: s = s.replace(FRED, "***")
open("probe.json", "w").write(s); print("done")
