import os, json, sys, traceback
os.makedirs("out25", exist_ok=True)
src = open("fetch_test.py", encoding="utf-8").read()
cut = src.index("\nrun(")
g = {"__name__": "fetchmod"}
rep = {}
try:
    exec(compile(src[:cut], "fetch_test.py", "exec"), g)
except Exception:
    rep["import_err"] = traceback.format_exc()[-1500:]
for name, call in (("corp", lambda: g["p_corp"]()), ("nmi", lambda: g["_ndc_pmi"]("NMI")), ("pmi", lambda: g["_ndc_pmi"]("PMI"))):
    try:
        rep[name] = call()
    except Exception:
        rep[name + "_err"] = traceback.format_exc()[-1500:]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1, default=str)
