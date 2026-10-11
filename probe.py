import os, json, traceback, requests
os.makedirs("out25/d/panels", exist_ok=True)
os.environ["INTEL_DATA_DIR"] = os.path.abspath("out25/d")
# 帶入領先指標序列（回測 biz_net 用）
r = requests.get("https://raw.githubusercontent.com/v1endetta/intel-terminal/data/data/lead_series.json", timeout=60)
open("out25/d/lead_series.json", "wb").write(r.content)
src = open("fetch_test.py", encoding="utf-8").read(); src = src[:src.index("\nrun(")]
g = {"__name__": "x", "__file__": os.path.abspath("fetch_test.py")}
exec(compile(src, "fetch_test", "exec"), g)
rep = {}
for nm in ("p_demo", "p_bizlife", "p_housefc"):
    try:
        d = g[nm](); g["RESULTS"][nm[2:]] = d
        rep[nm] = {k: v for k, v in d.items() if "spark" not in k and k not in ("cities",)}
    except Exception:
        rep[nm] = traceback.format_exc()[-1200:]
try:
    bt = g["_backtests"](); rep["bt"] = {k: v for k, v in bt.items() if k in ("mort_rate", "biz_net", "house_mom")}
except Exception:
    rep["bt"] = traceback.format_exc()[-800:]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1, default=str)
