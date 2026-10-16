# 一次性實測：新五個面板的抓取函式實際跑一次（結果寫 probe.json；利差、FBX 只有百分位與變動，不含原始報價）
import json, os, sys, traceback, tempfile
os.environ["INTEL_DATA_DIR"] = tempfile.mkdtemp()
src = open("fetch.py", encoding="utf-8").read()
src = src[:src.index('\nrun("pulse", p_pulse)\n')]
ns = {"__name__": "fetchtest", "__file__": os.path.abspath("fetch.py")}
os.makedirs(os.environ["INTEL_DATA_DIR"], exist_ok=True)
exec(compile(src, "fetch.py", "exec"), ns)
OUT = {}
for k in ("p_credit", "p_uspolicy", "p_exports", "p_stress", "p_logistics"):
    try:
        OUT[k] = ns[k]()
    except Exception:
        OUT[k] = {"FAIL": traceback.format_exc()[-1500:]}
s = json.dumps(OUT, ensure_ascii=False, indent=1)
for v in (os.environ.get("FRED_API_KEY"), os.environ.get("GEMINI_API_KEY")):
    if v: s = s.replace(v, "***")
open("probe.json", "w").write(s)
print("done")
