# 一次性實測：打開國會後的美國政策源頭面板（結果寫 probe.json；金鑰遮掉）
import json, os, traceback, tempfile
os.environ["INTEL_DATA_DIR"] = tempfile.mkdtemp()
src = open("fetch.py", encoding="utf-8").read(); src = src[:src.index('\nrun("pulse", p_pulse)\n')]
ns = {"__name__": "fetchtest", "__file__": os.path.abspath("fetch.py")}
exec(compile(src, "fetch.py", "exec"), ns)
try:
    d = ns["p_uspolicy"](); out = {"congress": d["congress"], "src": d["src"], "errs": d["errs"], "n_items": len(d["items"]),
         "bills": [(b["kind"], b["tw"], b.get("active"), b["date"], b.get("zh") or b["title"], b.get("action_zh") or b["action"]) for b in d["bills"]]}
except Exception:
    out = {"FAIL": traceback.format_exc()[-1500:]}
s = json.dumps(out, ensure_ascii=False, indent=1)
for k in ("CONGRESS_API_KEY", "GEMINI_API_KEY", "FRED_API_KEY"):
    v = os.environ.get(k)
    if v: s = s.replace(v, "***")
open("probe.json", "w").write(s); print("done")
