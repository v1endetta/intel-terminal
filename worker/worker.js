// 情報站網站（Cloudflare Worker）：前面由 Cloudflare Access 擋住，只有名單上的人登入得進來。
// /data/*                → 從 Workers KV（binding DATA）讀資料；主迴圈每輪把新資料推進 KV
// /feed/<晨報金鑰>/*     → 給晨間判讀排程用的唯讀通道（Access 對這個路徑放行，靠網址裡的長密碼擋人）
// /s/<分享金鑰>/          → 分享連結：拿到連結的人不用登入就能看整個網站（Access 放行）
// 金鑰只以 SHA-256 雜湊存在 wrangler.toml（FEED_HASH／SHARE_HASH），比對雜湊。
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

async function keyOk(key, hash) {
  if (!key || !hash || hash === "off") return false;
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(key)));
  return [...d].map((x) => x.toString(16).padStart(2, "0")).join("") === hash;
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
      if (!["all.json", "history.json"].includes(p) || !(await keyOk(key, env.FEED_HASH))) return new Response("not found", { status: 404 });
      return fromKV(p, env);
    }
    if (u.pathname === "/s" || u.pathname.startsWith("/s/")) {
      const [, , key, ...rest] = u.pathname.split("/");
      if (!(await keyOk(key, env.SHARE_HASH))) return new Response("not found", { status: 404 });
      if (rest.length === 0) return Response.redirect(`${u.origin}/s/${key}/`, 301);
      const p = rest.join("/");
      if (p === "" || p === "index.html") return page(req, env, "/");
      if (p.startsWith("data/")) return fromKV(decodeURIComponent(p.slice(5)), env);
      return new Response("not found", { status: 404 });
    }
    return page(req, env, u.pathname + u.search);
  },
};
