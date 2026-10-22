# 暫時實測：台灣隱形冠軍月營收。金鑰一律不輸出
import json, os, re, tempfile, traceback
out = {}
try:
    tmp = tempfile.mkdtemp(); os.environ["INTEL_DATA_DIR"] = tmp
    src = open("fetch.py", encoding="utf-8").read(); cut = src.index('\nrun("pulse", p_pulse)\n')
    g = {"__name__": "probe", "__file__": os.path.abspath("fetch.py")}
    exec(compile(src[:cut], "fetch.py", "exec"), g)
    out["champions"] = g["p_champions"]()
except Exception:
    out["err"] = re.sub(r"(key|token)=[^&\s]+", r"\1=***", traceback.format_exc()[-800:])
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:800])
