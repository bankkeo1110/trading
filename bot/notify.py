"""Gửi thông báo qua Zalo Bot Platform và Gmail SMTP."""
import json
import smtplib
import urllib.request
from email.message import EmailMessage

ZALO_API = "https://bot-api.zaloplatforms.com"
ZALO_LIMIT = 2000


def chunk(text, limit=ZALO_LIMIT):
    """Cắt tin dài theo đoạn (ngăn bởi dòng trống) để mỗi phần <= limit ký tự."""
    parts, cur = [], ""
    for block in text.split("\n\n"):
        while len(block) > limit:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(block[:limit])
            block = block[limit:]
        cand = f"{cur}\n\n{block}" if cur else block
        if len(cand) > limit:
            parts.append(cur)
            cur = block
        else:
            cur = cand
    if cur:
        parts.append(cur)
    return parts


def zalo_call(token, method, body=None, timeout=40):
    req = urllib.request.Request(
        f"{ZALO_API}/bot{token}/{method}",
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    if not data.get("ok"):
        raise RuntimeError(f"Zalo {method} lỗi: {data.get('description') or data}")
    return data.get("result")


def send_zalo(cfg, text):
    for part in chunk(text):
        zalo_call(cfg.zalo_token, "sendMessage", {"chat_id": cfg.zalo_chat_id, "text": part})


def send_gmail(cfg, subject, text):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.gmail_user
    msg["To"] = cfg.email_to or cfg.gmail_user
    msg.set_content(text)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(cfg.gmail_user, cfg.gmail_app_password.replace(" ", ""))
        s.send_message(msg)


def notify(cfg, subject, text):
    """Gửi qua mọi kênh đã cấu hình. Trả về (kênh thành công, {kênh: lỗi})."""
    ok, errors = [], {}
    channels = []
    if cfg.zalo_token and cfg.zalo_chat_id:
        channels.append(("Zalo", lambda: send_zalo(cfg, text)))
    if cfg.gmail_user and cfg.gmail_app_password:
        channels.append(("Gmail", lambda: send_gmail(cfg, subject, text)))
    for name, fn in channels:
        try:
            fn()
            ok.append(name)
        except Exception as e:
            errors[name] = str(e)
    return ok, errors, [n for n, _ in channels]
