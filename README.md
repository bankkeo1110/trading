# Trading — cảnh báo Bollinger Bands

Bot quét BTC, ETH, SOL, SUI (spot, cặp USDT) trên khung 1h / 4h / 1d. Khi giá gần chạm hoặc chạm/vượt
BB trên/dưới, bot gửi tin về **Telegram** (mặc định), **Zalo** hoặc **Gmail**, đồng thời lưu lại để xem trên dashboard Vercel.

Dashboard: https://trading-kid215.vercel.app

Bot chỉ cảnh báo, không đặt lệnh. Chạm band không phải là tín hiệu vào lệnh chắc chắn.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `bot/` | Bot Python (không cần cài thư viện) |
| `.github/workflows/scan.yml` | Lịch chạy 15 phút/lần trên GitHub Actions |
| `web/` | Dashboard (biểu đồ, lịch sử tín hiệu, chọn kênh gửi), deploy lên Vercel |
| `tests/` | Test: `python -m unittest discover -s tests` |
| nhánh `data` | `state.json` (chống spam) và `signals.json` (lịch sử), bot tự tạo |

## Logic tín hiệu

- BB(20, 2) tính như TradingView, dùng giá hiện tại của nến đang chạy.
- **Gần chạm**: giá nằm trong 10% bề rộng dải tính từ band (`NEAR=0.10`). **Chạm/vượt**: giá tới hoặc qua band.
- Mỗi coin + khung + phía band chỉ báo 1 lần mỗi nến; báo lại khi nâng từ "gần chạm" lên "chạm".
- Kèm RSI(14), đánh dấu quá mua/quá bán khi trùng phía band.
- **Đồng thuận**: nhiều khung cùng ở một phía band thì ghi rõ trong tin.
- **Squeeze**: báo 1 lần khi dải co về mức hẹp nhất trong 120 nến.

## Chọn kênh gửi

Mở dashboard, mục **Kênh gửi cảnh báo**: tick Telegram / Zalo / Gmail rồi bấm **Lưu**. Mặc định chỉ Telegram.
Lựa chọn được lưu vào `settings.json` trên nhánh `data`, bot áp dụng từ lượt quét kế tiếp.

Để nút Lưu hoạt động, Vercel cần một token GitHub (làm 1 lần):
1. GitHub > Settings > Developer settings > Fine-grained tokens > Generate new token.
   Repository access: chỉ repo `trading`. Permissions: **Contents: Read and write**.
2. Vercel > project `trading` > Settings > Environment Variables: thêm `GITHUB_TOKEN` = token đó, rồi Redeploy.

Nên giữ Vercel Authentication bật cho project, vì ai mở được dashboard cũng đổi được lựa chọn kênh.
Nếu chưa lưu gì trên dashboard, bot dùng biến `CHANNELS` (Variables của GitHub Actions), không có thì chỉ Telegram.

## Cài đặt (làm hết trên trình duyệt)

Secrets nằm ở repo > Settings > Secrets and variables > Actions > New repository secret.

**Telegram (mặc định)**
1. Mở Telegram, chat với `@BotFather`, gõ `/newbot`, đặt tên, copy token. Thêm secret `TELEGRAM_BOT_TOKEN`.
2. Mở bot vừa tạo, bấm Start (hoặc nhắn 1 tin bất kỳ).
3. Tab Actions > "Quét Bollinger Bands" > Run workflow > tick "Gửi tin thử". Bot nhắn `TELEGRAM_CHAT_ID`
   vào Telegram của bạn. Thêm secret `TELEGRAM_CHAT_ID` với giá trị đó.
4. Chạy "Gửi tin thử" lần nữa để nhận tin thử. Từ đây bot tự chạy theo lịch.

**Zalo (tuỳ chọn, cần thêm `zalo` vào `CHANNELS`)**
1. Vào https://bot.zaloplatforms.com, tạo bot, copy token. Thêm secret `ZALO_BOT_TOKEN`. Nhắn 1 tin cho bot.
2. Chạy "Gửi tin thử": bot nhắn `ZALO_CHAT_ID` vào Zalo. Thêm secret `ZALO_CHAT_ID`.

**Gmail (tuỳ chọn, cần thêm `gmail` vào `CHANNELS`)**
1. Bật xác minh 2 bước, tạo App Password tại https://myaccount.google.com/apppasswords.
2. Thêm secret `GMAIL_USER`, `GMAIL_APP_PASSWORD`, và `EMAIL_TO` nếu muốn gửi tới địa chỉ khác.

**Dashboard**: đã deploy trên Vercel từ thư mục `web`. (Tuỳ chọn) thêm Variable `DASHBOARD_URL` để tin nhắn kèm link.

## Tuỳ chỉnh

Đặt ở Settings > Secrets and variables > Actions > **Variables**:
`CHANNELS`, `SYMBOLS` (vd `BTCUSDT,ETHUSDT`), `TIMEFRAMES` (vd `1h,4h,1d`), `NEAR` (vd `0.05`).
Nếu đổi coin/khung, sửa thêm 2 dòng `SYMBOLS`, `TIMEFRAMES` ở đầu phần script trong `web/index.html`.

## Lưu ý

- Repo cần ở chế độ **public**: GitHub Actions miễn phí không giới hạn và dashboard đọc được `signals.json`.
  Token và mật khẩu nằm trong Secrets nên không lộ.
- Lịch của GitHub Actions có thể trễ vài phút. GitHub tự tắt lịch nếu repo không có hoạt động trong 60 ngày.
- Nguồn giá: Binance (`data-api.binance.vision`), dự phòng OKX.

## Chạy trên máy (không bắt buộc)

```
cp .env.example .env      # điền token
python -m bot --dry-run   # quét, chỉ in ra
python -m bot --loop 300  # quét 5 phút/lần
```
