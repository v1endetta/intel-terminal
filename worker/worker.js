// 情報站網站（Cloudflare Worker）：前面由 Cloudflare Access 擋住，只有 Vin 登入得進來。
// /data/*            → 從 Workers KV（binding DATA）讀資料；主迴圈每輪把新資料推進 KV
// /feed/<FEED_KEY>/* → 給晨間判讀排程用的唯讀通道（Access 對這個路徑放行，靠網址裡的長密碼擋人）
// 其他路徑         → 網站靜態檔（index.html 等）
const TYPES = { json: "application/json; charset=utf-8", png: "image/png" };

async function fromKV(key, env) {
  if (!/^[\w\-./%]+$/.test(key) || key.includes("..")) return new Response("bad path", { status: 400 });
  const body = await env.DATA.get(key, { type: "stream", cacheTtl: 60 });
  if (!body) return new Response("not found", { status: 404 });
  const ext = key.split(".").pop();
  return new Response(body, {
    headers: { "content-type": TYPES[ext] || "application/octet-stream", "cache-control": "private, no-store", "x-robots-tag": "noindex, nofollow" },
  });
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
    const res = await env.ASSETS.fetch(req);
    const h = new Headers(res.headers);
    h.set("x-robots-tag", "noindex, nofollow");
    h.set("referrer-policy", "no-referrer");
    return new Response(res.body, { status: res.status, headers: h });
  },
};
