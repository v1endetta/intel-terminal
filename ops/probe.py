# 一次性實測（第三輪）：出口國別×貨品細項、減班休息來源、FRED 授權文字
import json, os, re
import requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 dalta-intel/1.0 (personal non-commercial)"
FRED = os.environ.get("FRED_API_KEY", "").strip()
OUT = {}
def note(k, **kw): OUT.setdefault(k, {}).update(kw)
try:
    m = S.get("https://api.stlouisfed.org/fred/series", params={"series_id": "BAMLH0A0HYM2", "api_key": FRED, "file_type": "json"}, timeout=30).json()
    note("fred_notes", text=((m.get("seriess") or [{}])[0].get("notes") or "")[-900:])
except Exception as e: note("fred_notes", err=repr(e)[:100])
B = "https://web02.mof.gov.tw/njswww/webMain.aspx?sys=220&ym=11400&kind=21&type=4&funid=op8201&cycle=41&outmode=12&compmode=00&outkind=12&{fld}=1&codspc0=0,{nc},&utf=1"
for i in range(1, 26):
    try:
        t = S.get(B.format(fld=f"fld{i}", nc=20), timeout=40).content.decode("utf-8-sig", "replace").strip().splitlines()
        note("op8201", **{f"fld{i}": [t[0][:60] if t else "", t[1][:50] if len(t) > 1 else "", t[-1][:60] if t else "", len(t)]})
    except Exception as e: note("op8201", **{f"fld{i}": repr(e)[:80]})
for nc in (40, 80):
    try:
        t = S.get(B.format(fld="fld2", nc=nc), timeout=40).content.decode("utf-8-sig", "replace").strip().splitlines()
        note("op8201_cols", **{str(nc): t[0][:3000]})
    except Exception as e: note("op8201_cols", **{str(nc): repr(e)[:80]})
try:
    t = S.get("https://www.mol.gov.tw/1607/1632/1640/", timeout=40).text
    note("mol_anchors", a=[x[:200] for x in re.findall(r"<a[^>]{0,300}>[^<]{0,120}", t) if "1640/" in x][:25])
except Exception as e: note("mol_anchors", err=repr(e)[:200])
try:
    t = S.get("https://news.google.com/rss/search", params={"q": "減班休息 勞動部 家數 人數 when:30d", "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}, timeout=40).text
    note("gnews_jb", titles=re.findall(r"<title>([^<]{8,160})</title>", t)[:12])
except Exception as e: note("gnews_jb", err=repr(e)[:200])
json.dump(OUT, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("done")
