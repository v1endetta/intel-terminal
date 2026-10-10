import os, json, traceback, time
os.makedirs("out25", exist_ok=True)
src = open("fetch_test.py", encoding="utf-8").read()
g = {"__name__": "fetchmod", "__file__": os.path.abspath("fetch_test.py")}
rep = {}
exec(compile(src[:src.index("\nrun(")], "fetch_test.py", "exec"), g)
g["DATA"].mkdir(exist_ok=True)
for fn in ("p_wiki",):
    try:
        t0 = time.time(); r = g[fn](); rep[fn] = r; rep[fn + "_sec"] = round(time.time() - t0)
    except Exception:
        rep[fn + "_err"] = traceback.format_exc()[-1500:]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1, default=str)
