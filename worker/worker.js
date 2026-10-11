// 情報站網站（Cloudflare Worker）：前面由 Cloudflare Access 擋住，只有名單上的人登入得進來。
// /data/*                → 從 Workers KV（binding DATA）讀資料；主迴圈每輪把新資料推進 KV
// /feed/<FEED_KEY>/*     → 給晨間判讀排程用的唯讀通道（Access 對這個路徑放行，靠網址裡的長密碼擋人）
// /s/<分享金鑰>/          → 分享連結：拿到連結的人不用登入就能看整個網站（Access 放行，金鑰由 FEED_KEY 與 SHARE_VER 推算）
// 其他路徑              → 網站靜態檔（index.html 等）
const TYPES = { json: "application/json; charset=utf-8", png: "image/png" };
const NOINDEX = { "x-robots-tag": "noindex, nofollow", "referrer-policy": "no-referrer" };

async function fromKV(key, env) {
  if (!/^[\w\-./%]+$/.test(key) || key.includes("..")) return new Response("bad path", { status: 400 });
  const body = await env.DATA.get(key, { type: "stream", cacheTtl: 60 });
  if (!body) return new Response("not found", { status: 404 });
  const ext = key.split(".").pop();
  return new Response(body, { headers: { "content-type": TYPES[ext] || "application/octet-stream", "cache-control": "private, no-store", ...NOINDEX } });
}

async function shareKey(env) {
  if (!env.FEED_KEY || !env.SHARE_VER || env.SHARE_VER === "off") return null;
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(env.FEED_KEY), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode("share:" + env.SHARE_VER)));
  return btoa(String.fromCharCode(...sig)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "").slice(0, 32);
}

async function page(req, env, path) {
  const res = await env.ASSETS.fetch(new Request(new URL(path, req.url), req));
  const h = new Headers(res.headers);
  for (const [k, v] of Object.entries(NOINDEX)) h.set(k, v);
  return new Response(res.body, { status: res.status, headers: h });
}

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    if (u.pathname.startsWith("/data/")) return fromKV(decodeURIComponent(u.pathname.slice(6)), env);
    if (u.pathname.startsWith("/feed/")) {
      const [, , key, ...rest] = u.pathname.split("/");
      const p = rest.join("/");
      if (!env.FEED_KEY || key !== env.FEED_KEY || !["all.json", "history.json"].includes(p)) return new Response("not found", { status: 404 });
      return fromKV(p, env);
    }
    if (u.pathname === "/s" || u.pathname.startsWith("/s/")) {
      const [, , key, ...rest] = u.pathname.split("/");
      const want = await shareKey(env);
      if (!want || key !== want) return new Response("not found", { status: 404 });
      if (rest.length === 0) return Response.redirect(`${u.origin}/s/${key}/`, 301);
      const p = rest.join("/");
      if (p === "" || p === "index.html") return page(req, env, "/");
      if (p.startsWith("data/")) return fromKV(decodeURIComponent(p.slice(5)), env);
      return new Response("not found", { status: 404 });
    }
    return page(req, env, u.pathname + u.search);
  },
};
