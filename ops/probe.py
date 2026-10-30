"""暫時探測：美債殖利率面板要用的來源。用完刪掉。輸出不含任何金鑰值（最後再掃一次）。"""
import json
import os
import sys
import time
from pathlib import Path

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
os.environ["INTEL_DATA_DIR"] = str(OUT / "tmpdata")
ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "fetch.py").read_text(encoding="utf-8")
g = {"__name__": "probe", "__file__": str(ROOT / "fetch.py")}
exec(compile(src[:src.index('\nrun("pulse", p_pulse)\n')], "fetch_pre", "exec"), g)
rep = {}


def t(name, fn):
    try:
        v = fn()
        rep[name] = v
    except Exception as e:  # noqa: BLE001
        rep[name] = {"err": g["safe_err"](e)}
    print(name, json.dumps(rep[name], ensure_ascii=False)[:400], flush=True)
    time.sleep(1)


for sid in ["DFII10", "T10YIE", "THREEFYTP10", "T10Y2Y", "T10Y3M", "DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS3", "DGS5", "DGS7", "DGS10", "DGS20", "DGS30"]:
    t("fred_" + sid, lambda s=sid: (lambda o: {"n": len(o), "first": o[0], "last": o[-1]})(g["fred"](s, n=400)))

t("move", lambda: (lambda q: {"n": len(q["closes"]), "last": q["price"], "asOf": q["asOf"], "src": q["source"]})(g["yahoo_daily"]("^MOVE", "1y")))
for sym in ["^FVX", "^TNX", "^IRX", "^TYX"]:
    t("yh_" + sym, lambda s=sym: (lambda q: {"last": q["price"], "asOf": q["asOf"], "open": q["open"]})(g["yahoo_daily"](s, "5d")))


def treas_csv():
    r = g["get"]("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all",
                 params={"type": "daily_treasury_yield_curve", "field_tdr_date_value": "2026", "page": "", "_format": "csv"}, timeout=60)
    lines = r.text.strip().splitlines()
    (OUT / "treas.csv").write_text("\n".join(lines[:6]), encoding="utf-8")
    return {"rows": len(lines), "head": lines[0][:300], "first": lines[1][:200], "ctype": r.headers.get("content-type", "")}


def treas_real():
    r = g["get"]("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all",
                 params={"type": "daily_treasury_real_yield_curve", "field_tdr_date_value": "2026", "page": "", "_format": "csv"}, timeout=60)
    lines = r.text.strip().splitlines()
    return {"rows": len(lines), "head": lines[0][:200], "first": lines[1][:160]}


def fiscal_auctions():
    j = g["gjson"]("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
                   params={"sort": "-auction_date", "page[size]": "40",
                           "filter": "security_type:in:(Note,Bond),auction_date:gte:2026-08-01"}, timeout=60)
    d = j.get("data") or []
    (OUT / "auctions.json").write_text(json.dumps(d[:3], ensure_ascii=False, indent=1), encoding="utf-8")
    keys = sorted(d[0].keys()) if d else []
    return {"n": len(d), "keys": keys, "sample": {k: d[0].get(k) for k in ("auction_date", "security_term", "security_type", "high_yield", "bid_to_cover_ratio",
                                                                         "indirect_bidder_accepted", "direct_bidder_accepted", "primary_dealer_accepted", "total_accepted", "offering_amt")} if d else None}


def tdirect():
    j = g["gjson"]("https://www.treasurydirect.gov/TA_WS/securities/auctioned", params={"format": "json", "type": "Note", "days": "60"}, timeout=60)
    return {"n": len(j), "keys": sorted(j[0].keys())[:60] if j else []}


t("treas_csv", treas_csv)
t("treas_real", treas_real)
t("fiscal_auctions", fiscal_auctions)
t("tdirect", tdirect)

out = json.dumps(rep, ensure_ascii=False, indent=1)
for k in ("FRED_API_KEY",):
    v = os.environ.get(k, "").strip()
    if v:
        out = out.replace(v, "***")
(OUT / "report.json").write_text(out, encoding="utf-8")
import shutil
shutil.rmtree(OUT / "tmpdata", ignore_errors=True)
