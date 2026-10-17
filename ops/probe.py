# 暫時實測：日本 10 年公債殖利率來源（財務省 CSV、FRED 月資料）；金鑰一律遮掉
import json, os, re, requests
out = {}
H = {"User-Agent": "Mozilla/5.0 (intel-terminal; personal research)"}
for name, url in [("mof_recent", "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"),
                  ("mof_all", "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv")]:
    try:
        r = requests.get(url, headers=H, timeout=40)
        t = r.content.decode("utf-8", "replace")
        lines = [l for l in t.splitlines() if l.strip()]
        out[name] = {"status": r.status_code, "bytes": len(r.content), "n_lines": len(lines), "head": lines[:3], "tail": lines[-3:]}
    except Exception as e:
        out[name] = {"err": f"{type(e).__name__}: {str(e)[:150]}"}
try:
    k = os.environ.get("FRED_API_KEY", "")
    r = requests.get("https://api.stlouisfed.org/fred/series/observations", params={"series_id": "IRLTLT01JPM156N", "api_key": k, "file_type": "json", "sort_order": "desc", "limit": 6}, timeout=30)
    j = r.json()
    out["fred"] = {"status": r.status_code, "obs": [(o["date"], o["value"]) for o in j.get("observations", [])]}
except Exception as e:
    out["fred"] = {"err": re.sub(r"api_key=[^&\s]+", "api_key=***", f"{type(e).__name__}: {str(e)[:150]}")}
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:2000])
