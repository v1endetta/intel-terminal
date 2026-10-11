"""Cloudflare API 小工具：只用環境變數 CLOUDFLARE_API_TOKEN，不印出任何秘密。
帳號 ID、KV 空間、登入信箱都用權杖自己查，不需要另外設 secret。"""
import json
import os
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
ZONE = "daltatw.com"
KV_TITLE = "intel-terminal-data"


class CFError(RuntimeError):
    pass


def call(method, path, body=None, raw=None, ctype="application/json", timeout=60):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(API + path, method=method, data=data,
                                 headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}", "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        try:
            msg = "; ".join(f'{x.get("code")} {x.get("message")}' for x in json.loads(txt).get("errors") or [])
        except Exception:  # noqa: BLE001
            msg = " ".join(txt.split())[:300]
        raise CFError(f"{method} {path.split('?')[0]} → {e.code} {msg}") from None


def account_id():
    if os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        return os.environ["CLOUDFLARE_ACCOUNT_ID"]
    z = call("GET", f"/zones?name={ZONE}")["result"] or []
    if not z:
        raise CFError(f"權杖看不到 {ZONE} 這個區域")
    return z[0]["account"]["id"]


def kv_namespace(acc, create=False):
    for ns in call("GET", f"/accounts/{acc}/storage/kv/namespaces?per_page=100")["result"] or []:
        if ns.get("title") == KV_TITLE:
            return ns["id"]
    if not create:
        raise CFError("KV 空間還沒建立（先跑一次 deploy-site）")
    return call("POST", f"/accounts/{acc}/storage/kv/namespaces", {"title": KV_TITLE})["result"]["id"]


def access_emails(acc):
    if os.environ.get("ACCESS_EMAIL"):
        return [e.strip() for e in os.environ["ACCESS_EMAIL"].split(",") if e.strip()]
    ms = call("GET", f"/accounts/{acc}/members?per_page=50")["result"] or []
    em = [m["user"]["email"] for m in ms if (m.get("user") or {}).get("email") and m.get("status") in (None, "accepted")]
    if len(em) != 1:
        raise CFError(f"帳號成員有 {len(em)} 位，無法自動判斷誰能登入；請設 ACCESS_EMAIL secret")
    return em
