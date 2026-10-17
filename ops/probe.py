# 一次性實測：AI 循環的資料源（雲端資本支出、台積電月營收、HS 細項出口、DRAM、資料中心營建）
import json, os, re, io, csv, time, traceback
import requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 dalta-intel/1.0 (personal non-commercial)"
OUT = {}
def note(k, **kw): OUT.setdefault(k, {}).update(kw)
SEC_UA = {"User-Agent": "dalta-intel personal research " + os.environ.get("SEC_CONTACT", "contact@example.com")}
CIK = {"MSFT": 789019, "GOOGL": 1652044, "AMZN": 1018724, "META": 1326801, "ORCL": 1341439, "NVDA": 1045810}
for tk, cik in CIK.items():
    try:
        r = S.get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment.json", headers=SEC_UA, timeout=40)
        if r.status_code != 200:
            note("sec_" + tk, st=r.status_code); continue
        u = r.json()["units"]["USD"]
        q = [x for x in u if x.get("form") in ("10-Q", "10-K")]
        q.sort(key=lambda x: (x["end"], x["start"]))
        note("sec_" + tk, n=len(u), first=q[0]["end"] if q else None, last=[(x["start"], x["end"], x["val"], x["fp"], x["form"], x.get("frame")) for x in q[-6:]])
    except Exception: note("sec_" + tk, err=traceback.format_exc()[-300:])
try:
    tok = os.environ.get("FINMIND_TOKEN", "")
    r = S.get("https://api.finmindtrade.com/api/v4/data", params={"dataset": "TaiwanStockMonthRevenue", "data_id": "2330", "start_date": "2015-01-01", "token": tok}, timeout=40).json()
    d = r.get("data") or []
    note("tsmc_rev", msg=r.get("msg"), n=len(d), first=d[0] if d else None, last=d[-2:] if d else None)
except Exception: note("tsmc_rev", err=traceback.format_exc()[-300:])
try:
    j = S.get("https://openapi.twse.com.tw/v1/opendata/t187ap05_L", timeout=40).json()
    t = [x for x in j if str(x.get("公司代號")) in ("2330", "2317", "2382", "3231", "6669", "2308")]
    note("twse_rev", n=len(j), sample=t[:6])
except Exception: note("twse_rev", err=traceback.format_exc()[-300:])
for ds in (39052, 6053, 23834, 23828, 32064):
    k = f"gov_{ds}"
    try:
        r = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", timeout=40).json()
        j = r.get("result") or {}
        d = j.get("distribution") or []
        note(k, title=j.get("title"), freq=j.get("updateFrequency"), modified=j.get("modifiedDate"), nd=len(d), dists=[(x.get("resourceDescription", "")[:60], x.get("resourceFormat"), (x.get("resourceDownloadUrl") or "")[:180]) for x in d[:6]], raw=None if j else str(r)[:200])
        u = next((x.get("resourceDownloadUrl") for x in d if x.get("resourceDownloadUrl")), None)
        if u:
            b = S.get(u, timeout=90).content
            for e in ("utf-8-sig", "cp950"):
                try: t = b.decode(e); break
                except Exception: t = None
            t = t or b.decode("utf-8", "replace"); L = t.strip().splitlines()
            note(k, bytes=len(b), head=[x[:300] for x in L[:3]], tail=[x[:200] for x in L[-2:]], nlines=len(L))
    except Exception: note(k, err=traceback.format_exc()[-300:])
for k, u in (("dramx_home", "https://www.dramexchange.com/"), ("dramx_en", "https://www.dramexchange.com/#dram")):
    try:
        r = S.get(u, timeout=40); t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", r.text))
        i = t.find("DDR5"); note(k, st=r.status_code, len=len(r.text), around=t[max(0, i - 200):i + 1500] if i >= 0 else t[:600])
    except Exception: note(k, err=traceback.format_exc()[-300:])
try:
    FK = os.environ.get("FRED_API_KEY", "")
    j = S.get("https://api.stlouisfed.org/fred/series/search", params={"search_text": "data center construction", "api_key": FK, "file_type": "json", "limit": 10}, timeout=40).json()
    note("fred_dc", hits=[(x["id"], x["title"], x["frequency"], x["observation_end"]) for x in j.get("seriess", [])])
except Exception: note("fred_dc", err=traceback.format_exc()[-300:])
for q in ("Microsoft capital expenditures guidance", "Alphabet capex guidance", "Amazon capital expenditures 2026", "Meta capex guidance 2027"):
    try:
        t = S.get("https://news.google.com/rss/search", params={"q": q + " when:120d", "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=30).text
        note("news_" + q.split()[0], titles=re.findall(r"<title>([^<]{10,200})</title>", t)[1:7])
    except Exception: note("news_" + q.split()[0], err=traceback.format_exc()[-200:])
s = json.dumps(OUT, ensure_ascii=False, indent=1)
for v in (os.environ.get("FRED_API_KEY"), os.environ.get("FINMIND_TOKEN"), os.environ.get("SEC_CONTACT")):
    if v: s = s.replace(v, "***")
open("probe.json", "w").write(s); print("done")
