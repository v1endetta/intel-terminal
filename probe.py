import os, json, subprocess
os.makedirs("out25", exist_ok=True)
rep = {}
for q in (["dig", "+short", "NS", "daltatw.com"], ["dig", "+short", "A", "daltatw.com"], ["dig", "+short", "CNAME", "intel.daltatw.com"], ["dig", "+short", "A", "intel.daltatw.com"]):
    try:
        rep[" ".join(q)] = subprocess.run(q, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:
        rep[" ".join(q)] = str(e)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
