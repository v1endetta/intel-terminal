"""每週走向摘要：讀 data/all.json（主迴圈最新一輪的結果），請 Gemini 寫本週方向，寫回 data/panels/weekly.json。
由 .github/workflows/weekly.yml 執行；共用 fetch.py 的函式（只載入到第一個 run( 之前，不會跑整輪抓取）。"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
src = (ROOT / "fetch.py").read_text(encoding="utf-8")
g = {"__name__": "fetch_lib", "__file__": str(ROOT / "fetch.py")}
exec(compile(src[: src.index("\nrun(")], "fetch.py", "exec"), g)  # noqa: S102

data = g["DATA"]
allj = json.loads((data / "all.json").read_text(encoding="utf-8"))
g["RESULTS"].update(allj.get("panels") or {})
force = os.environ.get("FORCE", "").lower() in ("1", "true", "yes")
pid = "weekly"
prev = g["load_prev"](pid)
try:
    doc = g["p_weekly"](force=force, timeout=240)
    doc["updatedAt"] = g["NOW_ISO"]
    doc.pop("error", None)
    print("weekly ok", doc.get("week"), doc.get("model"), doc.get("headline"))
except Exception as e:  # noqa: BLE001
    print("weekly failed:", g["safe_err"](e))
    if not prev:
        sys.exit(1)
    doc = prev
    doc["error"] = f"{g['NOW_ISO']} {g['safe_err'](e)}"
g["write_json"](g["PANELS"] / f"{pid}.json", doc, indent=1)
