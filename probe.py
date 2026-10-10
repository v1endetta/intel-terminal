import os, json, traceback, time
os.makedirs("out25", exist_ok=True)
src = open("fetch_test.py", encoding="utf-8").read()
g = {"__name__": "fetchmod", "__file__": os.path.abspath("fetch_test.py")}
rep = {}
exec(compile(src[:src.index("\nrun(")], "fetch_test.py", "exec"), g)
g["DATA"].mkdir(exist_ok=True)
for fn, key in (("p_tech2", "tech2"), ("p_imports", "imports"), ("p_veg", "veg"), ("p_cards", "cards"), ("p_lead", "lead"), ("p_wiki", "wiki"), ("p_elect", "elect"), ("p_ledger", "ledger")):
    try:
        t0 = time.time(); r = g[fn](); g["RESULTS"][key] = r
        rep[fn] = r if fn in ("p_tech2", "p_imports", "p_ledger") else "ok"; rep[fn + "_sec"] = round(time.time() - t0)
    except Exception:
        rep[fn + "_err"] = traceback.format_exc()[-1500:]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1, default=str)
