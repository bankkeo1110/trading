# Trading — cảnh báo Bollinger Bands

Bot quét BTC, ETH, SOL, SUI (spot, cặp USDT) trên khung 1h / 4h / 1d. Khi giá gần chạm hoặc chạm/vượt
BB trên/dưới, bot gửi tin về **Zalo** và **Gmail**, đồng thời lưu lại để xem trên dashboard Vercel.

Bot chỉ cảnh báo, không đặt lệnh. Chạm band không phải là tín hiệu vào lệnh chắc chắn.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `bot/` | Bot Python (không cần cài thư viện) |
| `.github/workflows/scan.yml` | Lịch chạy 15 phút/lần trên GitHub Actions |
| `web/` | Dashboard tĩnh (biểu đồ + lịch sử tín hiệu), deploy lên Vercel |
| `tests/` | Test: `python -m unittest discover -s tests` |
| nhánh `data` | `state.json` (chống spam) và `signals.json` (lịch sử), bot tự tạo |

## Logic tín hiệu

- BB(20, 2) tính như TradingView, dùng giá hiện tại của nến đang chạy.
- **Gần chạm**: giá nằm trong 10% bề rộng dải tính từ band (`NEAR=0.10`). **Chạm/vượt**: giá tới hoặc qua band.
- Mỗi coin + khung + phía band chỉ báo 1 lần mỗi nến; báo lại khi nâng từ "gần chạm" lên "chạm".
- Kèm RSI(14), đánh dấu quá mua/quá bán khi trùng phía band.
- **Đồng thuận**: nhiều khung cùng ở một phía band thì ghi rõ trong tin.
- **Squeeze**: báo 1 lần khi dải co về mức hẹp nhất trong 120 nến.

## Cài đặt (làm hết trên trình duyệt)

1. **Zalo bot**: vào https://bot.zaloplatforms.com, tạo bot, copy token. Mở Zalo nhắn 1 tin bất kỳ cho bot.
2. **Gmail**: bật xác minh 2 bước, tạo App Password tại https://myaccount.google.com/apppasswords.
3. **Secrets** (repo > Settings > Secrets and variables > Actions > New repository secret):
   - `ZALO_BOT_TOKEN`
   - `GMAIL_USER` (địa chỉ Gmail gửi đi), `GMAIL_APP_PASSWORD`
   - `EMAIL_TO` (tuỳ chọn, mặc định gửi về chính `GMAIL_USER`)
4. **Lấy chat_id Zalo**: tab Actions > "Quét Bollinger Bands" > Run workflow > tick "Gửi tin thử".
   Bot sẽ nhắn `ZALO_CHAT_ID` vào Zalo của bạn. Thêm secret `ZALO_CHAT_ID` với giá trị đó.
5. Chạy lại workflow với "Gửi tin thử" để nhận tin thử ở cả Zalo và Gmail. Từ đây bot tự chạy theo lịch.
6. **Dashboard**: Vercel > Add New Project > chọn repo này > Root Directory = `web`.
   (Tuỳ chọn) thêm Variable `DASHBOARD_URL` trong GitHub để tin nhắn kèm link dashboard.

## Tuỳ chỉnh

Đặt ở Settings > Secrets and variables > Actions > **Variables**:
`SYMBOLS` (vd `BTCUSDT,ETHUSDT`), `TIMEFRAMES` (vd `1h,4h,1d`), `NEAR` (vd `0.05`).
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
