// 情報站網站（Cloudflare Worker）：前面由 Cloudflare Access 擋住，只有 Vin 登入得進來。
// /data/*            → 從私人 repo v1endetta/intel-data 讀資料（唯讀權杖放在 Worker secret DATA_RO_TOKEN）
// /feed/<FEED_KEY>/* → 給晨間判讀排程用的唯讀通道（Access 對這個路徑放行，靠網址裡的長密碼擋人）
// 其他路徑         → 網站靜態檔（index.html 等）
const REPO = "v1endetta/intel-data";
const BRANCH = "main";

async function fromRepo(path, env, ctx) {
  if (!/^[\w\-./%]+$/.test(path) || path.includes("..")) return new Response("bad path", { status: 400 });
  const url = `https://raw.githubusercontent.com/${REPO}/${BRANCH}/data/${path}`;
  const cache = caches.default;
  const key = new Request(`https://cache.intel/${path}`);
  let res = await cache.match(key);
  if (!res) {
    const r = await fetch(url, { headers: { Authorization: `token ${env.DATA_RO_TOKEN}`, "User-Agent": "intel-terminal-worker" } });
    if (!r.ok) return new Response(`upstream ${r.status}`, { status: r.status === 404 ? 404 : 502 });
    const type = path.endsWith(".json") ? "application/json; charset=utf-8" : path.endsWith(".png") ? "image/png" : r.headers.get("content-type") || "application/octet-stream";
    res = new Response(r.body, { headers: { "content-type": type, "cache-control": "private, max-age=60" } });
    ctx.waitUntil(cache.put(key, res.clone()));
  }
  return res;
}

export default {
  async fetch(req, env, ctx) {
    const u = new URL(req.url);
    if (u.pathname.startsWith("/data/")) return fromRepo(decodeURIComponent(u.pathname.slice(6)), env, ctx);
    if (u.pathname.startsWith("/feed/")) {
      const [, , key, ...rest] = u.pathname.split("/");
      const p = rest.join("/");
      if (!env.FEED_KEY || key !== env.FEED_KEY || !["all.json", "history.json"].includes(p)) return new Response("not found", { status: 404 });
      return fromRepo(p, env, ctx);
    }
    const res = await env.ASSETS.fetch(req);
    const h = new Headers(res.headers);
    h.set("x-robots-tag", "noindex, nofollow");
    h.set("referrer-policy", "no-referrer");
    return new Response(res.body, { status: res.status, headers: h });
  },
};
