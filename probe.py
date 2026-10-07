import os, json, traceback
os.makedirs("out25", exist_ok=True)
src = open("fetch_test.py", encoding="utf-8").read()
g = {"__name__": "fetchmod", "__file__": os.path.abspath("fetch_test.py")}
rep = {}
try:
    exec(compile(src[:src.index("\nrun(")], "fetch_test.py", "exec"), g)
    rep["lyst"] = g["p_lyst"]()
except Exception:
    rep["err"] = traceback.format_exc()[-1500:]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1, default=str)
