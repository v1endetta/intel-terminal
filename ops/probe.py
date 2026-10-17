# 一次性實測：dalta 領先指標面板（p_lead 先跑寫出 lead_series.json，再跑 p_dlead）
import json, os, traceback, tempfile
os.environ["INTEL_DATA_DIR"] = tempfile.mkdtemp()
src = open("fetch.py", encoding="utf-8").read(); src = src[:src.index('\nrun("pulse", p_pulse)\n')]
ns = {"__name__": "fetchtest", "__file__": os.path.abspath("fetch.py")}
exec(compile(src, "fetch.py", "exec"), ns)
OUT = {}
for k in ("p_lead", "p_dlead"):
    try: OUT[k] = ns[k]()
    except Exception: OUT[k] = {"FAIL": traceback.format_exc()[-1500:]}
s = json.dumps(OUT, ensure_ascii=False)
v = os.environ.get("FRED_API_KEY")
if v: s = s.replace(v, "***")
open("probe.json", "w").write(s); print("done")
