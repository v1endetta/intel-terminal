# 一次性實測（第二輪）：補查出口貨品別、減班休息、資料新舊（結果寫 probe.json）
import json, re, time
import requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 dalta-intel/1.0 (personal non-commercial)"
OUT = {}
def dec(b):
    for enc in ("utf-8-sig", "cp950"):
        try: return b.decode(enc)
        except Exception: pass
    return b.decode("utf-8", "replace")
def note(k, **kw): OUT.setdefault(k, {}).update(kw)
def gov(ds):
    k = f"gov_{ds}"
    try:
        j = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", timeout=40).json()["result"]; d = j.get("distribution") or []
        note(k, title=j.get("title"), freq=j.get("updateFrequency"), modified=j.get("modifiedDate"), nd=len(d), dists=[(x.get("resourceDescription", "")[:60], (x.get("resourceDownloadUrl") or "")[:200]) for x in d[:6]])
        u = next((x.get("resourceDownloadUrl") for x in d if x.get("resourceDownloadUrl")), None)
        if u:
            t = dec(S.get(u, timeout=60).content); L = t.strip().splitlines()
            note(k, head=L[:3], tail=L[-3:], nlines=len(L))
    except Exception as e: note(k, err=repr(e)[:200])
for ds in (8379, 8380, 8381, 8383, 28536, 28537, 28538, 28539, 28540, 28541):
    gov(ds)
for k, u in (("ex_country", "https://service.mof.gov.tw/public/data/statistic/trade/u2010ex.csv"), ("cbc_bounce", "https://www.cbc.gov.tw/public/data/OpenData/經研處/EF70M01.csv"), ("tch_bounce", "https://www.twnch.org.tw/banklist/publicinfo/doc/42/42.csv")):
    try:
        t = dec(S.get(u, timeout=60).content); L = t.strip().splitlines()
        note(k, head0=L[0][:2000], tail=[x[:300] for x in L[-4:]], nlines=len(L))
    except Exception as e: note(k, err=repr(e)[:200])
# 減班休息：勞動部新聞稿
try:
    for pg in ("https://www.mol.gov.tw/1607/1632/1640/", "https://www.mol.gov.tw/1607/1632/1640/?Page=2", "https://www.mol.gov.tw/1607/1632/1640/?Page=3"):
        t = S.get(pg, timeout=40).text
        links = re.findall(r'<a[^>]+href="(/1607/1632/1640/\d+/)"[^>]*title="([^"]+)"', t) or re.findall(r'href="(/1607/1632/1640/\d+/)"[^>]*>\s*([^<]{6,120})', t)
        note("mol_list", **{pg[-7:]: [(a, b.strip()) for a, b in links[:40]]})
    cand = [(a, b) for v in OUT["mol_list"].values() for a, b in v if re.search(r"減班|減少工時|無薪假", b)]
    note("mol_hits", hits=cand[:6])
    if cand:
        t = re.sub(r"<[^>]+>", " ", S.get("https://www.mol.gov.tw" + cand[0][0], timeout=40).text); t = re.sub(r"\s+", " ", t)
        i = t.find("減班"); note("mol_page", url=cand[0][0], text=t[max(0, i - 300):i + 1500], files=re.findall(r'href="([^"]+\.(?:pdf|ods|odt|xlsx?|csv|docx?))"', S.get("https://www.mol.gov.tw" + cand[0][0], timeout=40).text, re.I)[:6])
except Exception as e: note("mol_list", err=repr(e)[:200])
# Freightos FBX：頁面裡有沒有數字
try:
    t = S.get("https://fbx.freightos.com/", timeout=40).text
    note("fbx", hits=re.findall(r".{0,80}FBX.{0,120}\$\s?[\d,]{3,6}.{0,40}", re.sub(r"<[^>]+>", " ", t))[:6], json_urls=list(set(re.findall(r'https?://[^"\']+(?:api|json)[^"\']{0,80}', t)))[:12])
except Exception as e: note("fbx", err=repr(e)[:200])
# Federal Register：抓最新 60 篇，用標題＋摘要在本地篩關鍵字
KW = re.compile(r"Taiwan|semiconductor|Section 232|tariff|export control|Entity List|Mexico|USMCA", re.I)
for ag in ("trade-representative-office-of-united-states", "industry-and-security-bureau", "international-trade-administration"):
    try:
        j = S.get("https://www.federalregister.gov/api/v1/documents.json", params={"conditions[agencies][]": ag, "per_page": 60, "order": "newest", "fields[]": ["title", "publication_date", "type", "abstract"]}, timeout=40).json()
        R = j.get("results", []); m = [(d["publication_date"], d["type"], d["title"][:140]) for d in R if KW.search((d.get("title") or "") + " " + (d.get("abstract") or ""))]
        note("fr_" + ag[:20], span=(R[-1]["publication_date"], R[0]["publication_date"]) if R else None, n=len(R), matched=len(m), sample=m[:8])
    except Exception as e: note("fr_" + ag[:20], err=repr(e)[:200])
json.dump(OUT, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("done")
