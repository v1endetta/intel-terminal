# 暫時實測：台灣內需產業（發票行業對應、新設登記對應）
import json, os, re, tempfile, traceback, subprocess
out = {}
try:
    tmp = tempfile.mkdtemp(); os.environ["INTEL_DATA_DIR"] = tmp
    subprocess.run(["git", "fetch", "-q", "origin", "data"], check=False)
    for fn in ("taxreg_codes.json",):
        b = subprocess.run(["git", "show", f"origin/data:data/{fn}"], capture_output=True).stdout
        open(os.path.join(tmp, fn), "wb").write(b)
    src = open("fetch.py", encoding="utf-8").read(); cut = src.index('\nrun("pulse", p_pulse)\n')
    g = {"__name__": "probe", "__file__": os.path.abspath("fetch.py")}
    exec(compile(src[:cut], "fetch.py", "exec"), g)
    allj = json.loads(subprocess.run(["git", "show", "origin/data:data/all.json"], capture_output=True).stdout)
    g["RESULTS"].update(allj["panels"])
    g["p_consume"]()
    cs = json.load(open(os.path.join(tmp, "consume_series.json")))
    out["inds"] = sorted(cs["s"].keys()); out["last"] = cs["last"]
    out["sectors"] = g["p_sectors"]()
except Exception:
    out["err"] = traceback.format_exc()[-900:]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:600])
