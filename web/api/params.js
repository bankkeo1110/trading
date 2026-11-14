// Đọc/ghi tham số gợi ý mua/bán (dòng `advice.*` trong settings.properties, nhánh main).
// Dùng chung GITHUB_TOKEN và ADMIN_PASSWORD với /api/settings. Giới hạn lấy từ params-spec.json (bot dùng chung).
const SPEC = require("../params-spec.json");
const { read, headers, passwordOk, FILE_URL } = require("./settings.js");

function parseParams(text) {
  const p = Object.fromEntries(Object.entries(SPEC).map(([k, v]) => [k, v.default]));
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line.startsWith("advice.") || !line.includes("=")) continue;
    const key = line.slice(7, line.indexOf("=")).trim();
    const value = Number(line.slice(line.indexOf("=") + 1).trim());
    if (key in SPEC && line.slice(line.indexOf("=") + 1).trim() !== "" && Number.isFinite(value)) p[key] = value;
  }
  return p;
}

function validate(p) {
  const errors = Object.entries(SPEC)
    .filter(([k, s]) => !(p[k] >= s.min && p[k] <= s.max))
    .map(([k, s]) => `${k}=${p[k]} ngoài khoảng [${s.min}, ${s.max}]`);
  if (!(p.hold < p.weak && p.weak < p.strong)) errors.push("cần hold < weak < strong");
  if (!(p.rsi_low < p.rsi_high)) errors.push("cần rsi_low < rsi_high");
  if (!(p.tp1_atr < p.tp2_atr)) errors.push("cần tp1_atr < tp2_atr");
  return errors;
}

function withParams(text, changes) {
  const lines = text.replace(/\n*$/, "").split(/\r?\n/);
  for (const [k, v] of Object.entries(changes)) {
    const line = `advice.${k}=${v}`;
    const i = lines.findIndex(l => new RegExp(`^\\s*advice\\.${k}\\s*=`).test(l));
    if (i >= 0) lines[i] = line;
    else lines.push(line);
  }
  return lines.join("\n") + "\n";
}

async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const canWrite = Boolean(process.env.GITHUB_TOKEN && process.env.ADMIN_PASSWORD);
  try {
    if (req.method === "GET") {
      const { text } = await read();
      return res.status(200).json({ params: parseParams(text), spec: SPEC, canWrite });
    }
    if (req.method !== "POST") return res.status(405).json({ error: "Chỉ hỗ trợ GET và POST" });
    if (!canWrite)
      return res.status(501).json({ error: "Vercel chưa có GITHUB_TOKEN và ADMIN_PASSWORD nên chưa lưu được." });
    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    if (!passwordOk(body.password)) {
      await new Promise(r => setTimeout(r, 800));
      return res.status(401).json({ error: "Sai mật khẩu." });
    }
    const changes = body.changes && typeof body.changes === "object" ? body.changes : {};
    const keys = Object.keys(changes);
    if (!keys.length) return res.status(400).json({ error: "Không có thay đổi nào." });
    const bad = keys.filter(k => !(k in SPEC) || typeof changes[k] !== "number" || !Number.isFinite(changes[k]));
    if (bad.length) return res.status(400).json({ error: `Tham số không hợp lệ: ${bad.join(", ")}` });
    const { text, sha } = await read();
    const next = { ...parseParams(text), ...changes };
    const errors = validate(next);
    if (errors.length) return res.status(400).json({ error: errors.join("; ") });
    const r = await fetch(FILE_URL, {
      method: "PUT",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({
        message: `settings: áp dụng tham số ${keys.map(k => `${k}=${changes[k]}`).join(", ")}`,
        content: Buffer.from(withParams(text, changes)).toString("base64"),
        branch: "main",
        ...(sha ? { sha } : {}),
      }),
    });
    if (!r.ok) return res.status(502).json({ error: `GitHub từ chối lưu (${r.status}). Kiểm tra quyền của token.` });
    return res.status(200).json({ params: next, spec: SPEC, canWrite });
  } catch (e) {
    return res.status(500).json({ error: String(e.message || e) });
  }
}

module.exports = handler;
module.exports.parseParams = parseParams;
module.exports.validate = validate;
module.exports.withParams = withParams;
