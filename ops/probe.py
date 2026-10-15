import json, subprocess
r = subprocess.run(["python", "ops/bake_villages.py", "villages.json"], capture_output=True, text=True, timeout=500)
out = {"stdout": r.stdout[-2000:], "stderr": r.stderr[-3000:]}
try:
    d = json.load(open("villages.json", encoding="utf-8")); out["n"] = len(d["v"]); out["sample"] = d["v"][:5]; out["fields"] = d["fields"]
    out["villages"] = d
except Exception as e:
    out["err"] = repr(e)
json.dump(out, open("probe.json", "w"), ensure_ascii=False)
