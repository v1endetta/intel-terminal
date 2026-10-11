"""一次性：拆掉 intel.daltatw.com 的 Cloudflare 網站（Worker、自訂網域、KV、Access），
再把 intel.daltatw.com 用 DNS（不經 Cloudflare 代理）指到 GitHub Pages。冪等：重跑不會出事。
只用 CLOUDFLARE_API_TOKEN；log 不印任何 ID、信箱或秘密。"""
import sys

from cfapi import CFError, KV_TITLE, ZONE, account_id, call

HOST = "intel.daltatw.com"
SCRIPT = "intel-terminal"
TARGET = "v1endetta.github.io"


def step(name, fn):
    try:
        print(f"{name}：{fn()}")
        return True
    except CFError as e:
        print(f"::error::{name} 失敗：{e}")
        return False


def drop_domain():
    acc = account_id()
    doms = call("GET", f"/accounts/{acc}/workers/domains?hostname={HOST}")["result"] or []
    for d in doms:
        call("DELETE", f"/accounts/{acc}/workers/domains/{d['id']}")
    return f"解除 {len(doms)} 個網域綁定"


def drop_script():
    acc = account_id()
    try:
        call("DELETE", f"/accounts/{acc}/workers/scripts/{SCRIPT}?force=true")
        return "已刪除"
    except CFError as e:
        if " 404 " in str(e) or "10007" in str(e):
            return "本來就不存在"
        raise


def drop_kv():
    acc = account_id()
    n = 0
    for ns in call("GET", f"/accounts/{acc}/storage/kv/namespaces?per_page=100")["result"] or []:
        if ns.get("title") == KV_TITLE:
            call("DELETE", f"/accounts/{acc}/storage/kv/namespaces/{ns['id']}")
            n += 1
    return f"刪除 {n} 個"


def drop_access():
    acc = account_id()
    n = 0
    try:
        apps = call("GET", f"/accounts/{acc}/access/apps")["result"] or []
    except CFError as e:
        if "not_enabled" in str(e):
            return "Access 未啟用，略過"
        raise
    for a in apps:
        if str(a.get("domain", "")).startswith(HOST):
            call("DELETE", f"/accounts/{acc}/access/apps/{a['id']}")
            n += 1
    return f"刪除 {n} 條"


def point_dns():
    z = call("GET", f"/zones?name={ZONE}")["result"][0]["id"]
    recs = call("GET", f"/zones/{z}/dns_records?name={HOST}")["result"] or []
    ok = [r for r in recs if r["type"] == "CNAME" and r["content"].rstrip(".") == TARGET and not r.get("proxied")]
    for r in recs:
        if r not in ok:
            call("DELETE", f"/zones/{z}/dns_records/{r['id']}")
    if not ok:
        call("POST", f"/zones/{z}/dns_records", {"type": "CNAME", "name": HOST, "content": TARGET, "proxied": False, "ttl": 1,
                                                  "comment": "情報站：GitHub Pages（不經 Cloudflare 代理，不計費）"})
        return f"CNAME → {TARGET}（僅 DNS）已建立"
    return "已經指向 GitHub Pages"


results = [step("Worker 網域", drop_domain), step("Worker", drop_script), step("KV", drop_kv),
           step("Access", drop_access), step("DNS", point_dns)]
sys.exit(0 if all(results) else 1)
