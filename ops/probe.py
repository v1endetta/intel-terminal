"""暫時探測：TreasuryDirect 標售欄位。用完刪掉。"""
import json, sys
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 dalta-intel/1.0"
rep = {}
for typ in ("Note", "Bond"):
    try:
        r = S.get("https://www.treasurydirect.gov/TA_WS/securities/auctioned", params={"format": "json", "type": typ, "days": "90"}, timeout=60)
        j = r.json()
        rep[typ] = {"status": r.status_code, "n": len(j), "rows": [{k: a.get(k) for k in ("auctionDate", "securityTerm", "originalSecurityTerm", "bidToCoverRatio", "highYield", "competitiveAccepted", "indirectBidderAccepted", "primaryDealerAccepted", "totalAccepted", "inflationIndexSecurity", "floatingRate", "reopening", "type", "securityType")} for a in j[:30]]}
    except Exception as e:
        rep[typ] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
