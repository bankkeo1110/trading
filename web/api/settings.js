// Đọc/ghi dòng `channels=` trong settings.properties (nhánh main). Bot đọc file này ở mỗi lượt quét.
// Ghi cần 2 biến môi trường trên Vercel:
//   GITHUB_TOKEN    fine-grained PAT, quyền Contents: Read and write cho repo
//   ADMIN_PASSWORD  mật khẩu phải nhập trên dashboard khi bấm Lưu
const crypto = require("crypto");

const REPO = process.env.GITHUB_REPO || "bankkeo1110/trading";
const FILE_URL = `https://api.github.com/repos/${REPO}/contents/settings.properties`;
const ALLOWED = ["telegram", "zalo", "gmail"];

function headers() {
  const h = { Accept: "application/vnd.github+json", "User-Agent": "trading-dashboard" };
  if (process.env.GITHUB_TOKEN) h.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  return h;
}

function parseChannels(text) {
  const line = text.split(/\r?\n/).find(l => /^\s*channels\s*=/.test(l));
  if (line === undefined) return ["telegram"];
  const wanted = line.slice(line.indexOf("=") + 1).split(",").map(s => s.trim().toLowerCase());
  return ALLOWED.filter(c => wanted.includes(c));
}

function withChannels(text, channels) {
  const line = `channels=${channels.join(",")}`;
  const lines = text.split(/\r?\n/);
  const i = lines.findIndex(l => /^\s*channels\s*=/.test(l));
  if (i >= 0) lines[i] = line;
  else lines.push(line);
  return lines.join("\n").replace(/\n*$/, "\n");
}

async function read() {
  const r = await fetch(`${FILE_URL}?ref=main`, { headers: headers(), cache: "no-store" });
  if (r.status === 404) return { text: "", sha: null };
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const file = await r.json();
  return { text: Buffer.from(file.content, "base64").toString("utf8"), sha: file.sha };
}

function passwordOk(given) {
  const a = crypto.createHash("sha256").update(String(given || "")).digest();
  const b = crypto.createHash("sha256").update(process.env.ADMIN_PASSWORD).digest();
  return crypto.timingSafeEqual(a, b);
}

async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const canWrite = Boolean(process.env.GITHUB_TOKEN && process.env.ADMIN_PASSWORD);
  try {
    if (req.method === "GET") {
      const { text } = await read();
      return res.status(200).json({ channels: parseChannels(text), canWrite });
    }
    if (req.method !== "POST") return res.status(405).json({ error: "Chỉ hỗ trợ GET và POST" });
    if (!canWrite)
      return res.status(501).json({ error: "Vercel chưa có GITHUB_TOKEN và ADMIN_PASSWORD nên chưa lưu được." });
    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    if (!passwordOk(body.password)) {
      await new Promise(r => setTimeout(r, 800)); // làm chậm việc dò mật khẩu
      return res.status(401).json({ error: "Sai mật khẩu." });
    }
    if (!Array.isArray(body.channels) || body.channels.some(c => !ALLOWED.includes(c)))
      return res.status(400).json({ error: "channels phải là danh sách gồm telegram, zalo, gmail" });
    const channels = ALLOWED.filter(c => body.channels.includes(c));
    const { text, sha } = await read();
    const r = await fetch(FILE_URL, {
      method: "PUT",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({
        message: `settings: channels=${channels.join(",") || "(tắt)"}`,
        content: Buffer.from(withChannels(text, channels)).toString("base64"),
        branch: "main",
        ...(sha ? { sha } : {}),
      }),
    });
    if (!r.ok) return res.status(502).json({ error: `GitHub từ chối lưu (${r.status}). Kiểm tra quyền của token.` });
    return res.status(200).json({ channels, canWrite });
  } catch (e) {
    return res.status(500).json({ error: String(e.message || e) });
  }
}

module.exports = handler;
module.exports.parseChannels = parseChannels;
module.exports.withChannels = withChannels;
module.exports.read = read;
module.exports.headers = headers;
module.exports.passwordOk = passwordOk;
module.exports.FILE_URL = FILE_URL;
