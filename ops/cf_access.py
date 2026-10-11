"""建立 Cloudflare Access：intel.daltatw.com 只讓名單上的人登入（第一次建立時只有帳號本人，之後在後台加人）；/feed（晨報）與 /s（分享連結）放行，由 Worker 檢查網址裡的金鑰。
冪等：已存在就更新，不會重複建立。只用環境變數裡的權杖，不印出任何秘密或信箱。"""
import sys

from cfapi import CFError, access_emails, account_id, call

DOMAIN = "intel.daltatw.com"

try:
    acc = account_id()
    emails = access_emails(acc)
    base = f"/accounts/{acc}/access"
    apps = call("GET", f"{base}/apps")["result"] or []
    want = [
        {"name": "intel-terminal", "domain": DOMAIN, "decision": "allow", "include": [{"email": {"email": e}} for e in emails]},
        {"name": "intel-terminal-feed", "domain": f"{DOMAIN}/feed", "decision": "bypass", "include": [{"everyone": {}}]},
        {"name": "intel-terminal-share", "domain": f"{DOMAIN}/s", "decision": "bypass", "include": [{"everyone": {}}]},
    ]
    for w in want:
        body = {"name": w["name"], "domain": w["domain"], "type": "self_hosted", "session_duration": "720h",
                "app_launcher_visible": False, "auto_redirect_to_identity": False,
                "policies": [{"name": f'{w["name"]}-policy', "decision": w["decision"], "include": w["include"], "precedence": 1}]}
        cur = next((a for a in apps if a.get("domain") == w["domain"]), None)
        if cur and w["decision"] == "allow":
            # 主站已存在就不動：看的人名單在 Cloudflare 後台管理（Access → 應用程式 → intel-terminal → 原則），部署不會蓋掉
            print(f'Access 已存在：{w["domain"]}（名單沿用後台設定）')
        elif cur:
            call("PUT", f'{base}/apps/{cur["id"]}', body)
            print(f'更新 Access：{w["domain"]}（{w["decision"]}，{len(w["include"])} 條規則）')
        else:
            call("POST", f"{base}/apps", body)
            print(f'建立 Access：{w["domain"]}（{w["decision"]}，{len(w["include"])} 條規則）')
    # 驗證：主站一定要有 Access 設定才放行部署
    apps = call("GET", f"{base}/apps")["result"] or []
    if not any(a.get("domain") == DOMAIN for a in apps):
        raise CFError("建立後查不到主站的 Access 設定")
except CFError as e:
    print(f"::error::Access 設定失敗：{e}")
    sys.exit(1)
