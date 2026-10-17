import json, os, traceback, tempfile
os.environ["INTEL_DATA_DIR"] = tempfile.mkdtemp()
src = open("fetch.py", encoding="utf-8").read(); src = src[:src.index('\nrun("pulse", p_pulse)\n')]
ns = {"__name__": "fetchtest", "__file__": os.path.abspath("fetch.py")}
exec(compile(src, "fetch.py", "exec"), ns)
try: OUT = ns["p_aicycle"]()
except Exception: OUT = {"FAIL": traceback.format_exc()[-2000:]}
s = json.dumps(OUT, ensure_ascii=False)
for k in ("FRED_API_KEY", "FINMIND_TOKEN", "SEC_CONTACT", "GEMINI_API_KEY"):
    v = os.environ.get(k)
    if v: s = s.replace(v, "***")
open("probe.json", "w").write(s); print("done")
