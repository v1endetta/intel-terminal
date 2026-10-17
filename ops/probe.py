# 一次性實測（第二輪）：歷史長度與欄位；讀台灣機房的國道 TDCS 測試結果
import json, os, re, io, csv, gzip, traceback
import requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 dalta-intel/1.0 (personal non-commercial)"
OUT = {}
def note(k, **kw): OUT.setdefault(k, {}).update(kw)
def dec(b):
    for e in ("utf-8-sig", "cp950"):
        try: return b.decode(e)
        except Exception: pass
    return b.decode("utf-8", "replace")
for k, u in (("power_daily", "https://service.taipower.com.tw/data/opendata/apply/file/d006005/001.csv"),
             ("elec_month_2018", "https://www.moeaea.gov.tw/ECW/populace/opendata/wHandOpenData_File.ashx?set_id=236"),
             ("elec_month_old", "https://www.moeaea.gov.tw/ECW/populace/opendata/wHandOpenData_File.ashx?set_id=256"),
             ("port_teu", "https://www.twport.com.tw/fapi/opendata?id=13878")):
    try:
        L = dec(S.get(u, timeout=90).content).strip().splitlines()
        note(k, n=len(L), first=[x[:120] for x in L[1:3]], last=[x[:120] for x in L[-2:]], cols=L[0][:900])
    except Exception as e: note(k, err=repr(e)[:200])
for fn in ("EF01M01", "EF03M01", "EF05M01", "EF35M01"):
    try:
        j = S.get(f"https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={fn}", timeout=40).json()
        d = j.get("data") or {}
        note(fn, title=(j.get("meta") or {}).get("title"), data_type=type(d).__name__, data_keys=list(d.keys())[:8] if isinstance(d, dict) else None,
             sample=json.dumps(d, ensure_ascii=False)[:1500])
    except Exception as e: note(fn, err=repr(e)[:200])
try:
    from google.cloud import storage
    raw = storage.Client(project=os.environ["GCP_PROJECT"]).bucket(os.environ["GCP_BUCKET"]).blob("relay/static/probe_tdcs.json.gz").download_as_bytes(timeout=60)
    OUT["tdcs_relay"] = json.loads(gzip.decompress(raw))
except Exception:
    OUT["tdcs_relay"] = {"FAIL": traceback.format_exc()[-600:]}
open("probe.json", "w").write(json.dumps(OUT, ensure_ascii=False, indent=1)); print("done")
