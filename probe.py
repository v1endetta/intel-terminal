import os, json, requests
os.makedirs("out25", exist_ok=True)
K = os.environ.get("GEMINI_API_KEY", "")
rep = {}
js = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": K, "pageSize": 100}, timeout=30).json()
names = [m["name"].split("/", 1)[1] for m in js.get("models") or [] if "generateContent" in (m.get("supportedGenerationMethods") or [])]
rep["flash"] = [n for n in names if "flash" in n]
lite = [n for n in names if "lite" in n][:3]
base = {"contents": [{"parts": [{"text": "回傳 JSON {\"ok\": true}"}]}]}
variants = {
  "plain": {"generationConfig": {"temperature": 0.2, "maxOutputTokens": 500}},
  "json": {"generationConfig": {"temperature": 0.2, "maxOutputTokens": 500, "responseMimeType": "application/json"}},
  "budget0": {"generationConfig": {"temperature": 0.2, "maxOutputTokens": 500, "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}},
  "levelLow": {"generationConfig": {"temperature": 0.2, "maxOutputTokens": 500, "responseMimeType": "application/json", "thinkingConfig": {"thinkingLevel": "LOW"}}},
  "big": {"generationConfig": {"temperature": 0.2, "maxOutputTokens": 6000, "responseMimeType": "application/json"}},
}
for m in lite:
    for k, v in variants.items():
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", params={"key": K}, json={**base, **v}, timeout=60)
        msg = ""
        try: msg = (r.json().get("error") or {}).get("message", "")[:200]
        except Exception: pass
        rep[f"{m}:{k}"] = [r.status_code, msg]
s = json.dumps(rep, ensure_ascii=False, indent=1)
if K: s = s.replace(K, "***")
open("out25/probe.json", "w").write(s)
