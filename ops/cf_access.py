"""建立或更新 Cloudflare Access：intel.daltatw.com 只讓 ACCESS_EMAIL 登入（一次性信箱驗證碼）；/feed/ 路徑放行給排程。
冪等：已存在就更新，不會重複建立。只用環境變數裡的權杖，不印出任何秘密。"""
import json
import os
import sys
import urllib.request

ACC = os.environ["CLOUDFLARE_ACCOUNT_ID"]
TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
EMAILS = [e.strip() for e in os.environ["ACCESS_EMAIL"].split(",") if e.strip()]
DOMAIN = "intel.daltatw.com"
BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACC}/access"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:300]
        print(f"Access API {method} {path} → {e.code} {msg}")
        sys.exit(1)


apps = call("GET", "/apps")["result"] or []
want = [
    {"name": "intel-terminal", "domain": DOMAIN, "decision": "allow", "include": [{"email": {"email": e}} for e in EMAILS]},
    {"name": "intel-terminal-feed", "domain": f"{DOMAIN}/feed", "decision": "bypass", "include": [{"everyone": {}}]},
]
for w in want:
    body = {"name": w["name"], "domain": w["domain"], "type": "self_hosted", "session_duration": "720h",
            "app_launcher_visible": False, "auto_redirect_to_identity": False,
            "policies": [{"name": f'{w["name"]}-policy', "decision": w["decision"], "include": w["include"], "precedence": 1}]}
    cur = next((a for a in apps if a.get("domain") == w["domain"]), None)
    if cur:
        call("PUT", f'/apps/{cur["id"]}', body)
        print(f'更新 Access：{w["domain"]}（{w["decision"]}）')
    else:
        call("POST", "/apps", body)
        print(f'建立 Access：{w["domain"]}（{w["decision"]}）')
