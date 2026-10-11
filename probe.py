import os, json
os.makedirs("out25/d/panels", exist_ok=True)
os.environ["INTEL_DATA_DIR"] = os.path.abspath("out25/d")
src = open("fetch_test.py", encoding="utf-8").read()
src = src[:src.index("\nrun(")]
g = {"__name__": "x", "__file__": os.path.abspath("fetch_test.py")}
exec(compile(src, "fetch_test", "exec"), g)
rep = {}
try:
    hf = g["p_housefc"](); rep["hf"] = {k: v for k, v in hf.items() if "spark" not in k}
    g["RESULTS"]["housefc"] = hf
    bt = g["_backtests"](); rep["bt"] = {k: v for k, v in bt.items() if k.startswith("house")}
    hs = json.load(open("out25/d/house_series.json"))
    rep["n"] = {k: len(v) for k, v in hs.items()}; rep["tpe_first"] = sorted(hs["tpe"])[:2]; rep["vol_first"] = sorted(hs["vol"])[:2]
except Exception as e:
    import traceback; rep["err"] = traceback.format_exc()[-1500:]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
