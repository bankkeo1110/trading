// Đọc/ghi settings.json trên nhánh `data` của repo. Bot đọc file này ở mỗi lượt quét.
// Ghi cần biến môi trường GITHUB_TOKEN (fine-grained PAT, quyền Contents: Read and write cho repo).
const REPO = process.env.GITHUB_REPO || "bankkeo1110/trading";
const URL_ = `https://api.github.com/repos/${REPO}/contents/settings.json`;
const ALLOWED = ["telegram", "zalo", "gmail"];
const DEFAULT = { channels: ["telegram"] };

function headers() {
  const h = { Accept: "application/vnd.github+json", "User-Agent": "trading-dashboard" };
  if (process.env.GITHUB_TOKEN) h.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  return h;
}

async function read() {
  const r = await fetch(`${URL_}?ref=data`, { headers: headers(), cache: "no-store" });
  if (r.status === 404) return { settings: DEFAULT, sha: null };
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const file = await r.json();
  let settings = DEFAULT;
  try {
    const parsed = JSON.parse(Buffer.from(file.content, "base64").toString("utf8"));
    if (Array.isArray(parsed.channels)) settings = parsed;
  } catch (e) { /* file hỏng -> dùng mặc định */ }
  return { settings, sha: file.sha };
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const canWrite = Boolean(process.env.GITHUB_TOKEN);
  try {
    if (req.method === "GET") {
      const { settings } = await read();
      return res.status(200).json({ channels: settings.channels, canWrite });
    }
    if (req.method !== "POST") return res.status(405).json({ error: "Chỉ hỗ trợ GET và POST" });
    if (!canWrite) return res.status(501).json({ error: "Chưa có GITHUB_TOKEN trên Vercel nên chưa lưu được." });
    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    if (!Array.isArray(body.channels) || body.channels.some(c => !ALLOWED.includes(c)))
      return res.status(400).json({ error: "channels phải là danh sách gồm telegram, zalo, gmail" });
    const channels = ALLOWED.filter(c => body.channels.includes(c));
    const { sha } = await read();
    const content = JSON.stringify({ channels, updated: new Date().toISOString() }, null, 1) + "\n";
    const r = await fetch(URL_, {
      method: "PUT",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({
        message: `settings: channels = ${channels.join(", ") || "(tắt)"}`,
        content: Buffer.from(content).toString("base64"),
        branch: "data",
        ...(sha ? { sha } : {}),
      }),
    });
    if (!r.ok) return res.status(502).json({ error: `GitHub từ chối lưu (${r.status}). Kiểm tra quyền của token.` });
    return res.status(200).json({ channels, canWrite });
  } catch (e) {
    return res.status(500).json({ error: String(e.message || e) });
  }
};
