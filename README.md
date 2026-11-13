# Trading — cảnh báo Bollinger Bands

Bot quét BTC, ETH, SOL, SUI (spot, cặp USDT) trên khung 1h / 4h / 1d. Khi giá gần chạm hoặc chạm/vượt
BB trên/dưới, bot gửi tin về **Telegram** (mặc định), **Zalo** hoặc **Gmail**, đồng thời lưu lại để xem trên dashboard Vercel.

Dashboard: https://trading-kid215.vercel.app

Bot chỉ cảnh báo, không đặt lệnh. Chạm band không phải là tín hiệu vào lệnh chắc chắn.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `bot/` | Bot Python (không cần cài thư viện); `bot/advisor.py` là phần gợi ý mua/bán |
| `.github/workflows/scan.yml` | Lịch chạy 15 phút/lần trên GitHub Actions |
| `web/` | Dashboard (biểu đồ, lịch sử tín hiệu, chọn kênh gửi) và trang gợi ý mua/bán `signals.html`, deploy lên Vercel |
| `tests/` | Test: `python -m unittest discover -s tests` |
| nhánh `data` | `state.json` (chống spam), `signals.json` (lịch sử BB), `advice.json` và `advice_signals.json` (gợi ý mua/bán), bot tự tạo |

## Logic tín hiệu

- BB(20, 2) tính như TradingView, dùng giá hiện tại của nến đang chạy.
- **Gần chạm**: giá nằm trong 10% bề rộng dải tính từ band (`NEAR=0.10`). **Chạm/vượt**: giá tới hoặc qua band.
- Mỗi coin + khung + phía band chỉ báo 1 lần mỗi nến; báo lại khi nâng từ "gần chạm" lên "chạm".
- Kèm RSI(14), đánh dấu quá mua/quá bán khi trùng phía band.
- **Đồng thuận**: nhiều khung cùng ở một phía band thì ghi rõ trong tin.
- **Squeeze**: báo 1 lần khi dải co về mức hẹp nhất trong 120 nến.

## Gợi ý nên mua / nên bán

Ngoài cảnh báo BB, mỗi lượt quét bot chấm điểm từng coin trên từng khung từ −100 (bán mạnh) đến +100 (mua mạnh),
chỉ dùng **nến đã đóng** để tín hiệu không nhấp nháy. Xem ở trang `/signals.html` của dashboard.

| Chỉ báo | Điểm tối đa | Ý nghĩa |
|---|---|---|
| EMA 20/50/200 | ±30 | Xu hướng: giá so với EMA200, EMA20 so với EMA50, EMA50 so với EMA200 |
| MACD 12/26/9 | ±20 | Động lượng: MACD so với đường tín hiệu, histogram tăng/giảm, MACD so với 0 |
| ADX/DI 14 | ±15 | Sức mạnh xu hướng. ADX < 20 là đi ngang: EMA và MACD chỉ tính nửa điểm |
| RSI 14 | ±15 | Quá bán/quá mua, ngoài ra nghiêng nhẹ theo phía trên/dưới 50 |
| Stochastic RSI | ±10 | K cắt D từ vùng quá bán/quá mua |
| Bollinger %B | ±10 | Giá ở/gần BB dưới (mua) hoặc BB trên (bán) |
| Khối lượng | ±5 | Nến tăng/giảm với khối lượng từ 1.5 lần trung bình 20 nến |

- Khi xu hướng mạnh (ADX ≥ 30), tín hiệu đảo chiều đi ngược xu hướng (RSI, Stoch RSI, BB) chỉ tính 1/3 điểm.
- Từ ±20 là **NÊN MUA / NÊN BÁN**, từ ±50 là **mạnh**. Điểm tổng hợp mỗi coin: 1h ×1, 4h ×2, 1d ×3.
- Bot chỉ nhắn khi một coin + khung chuyển sang MUA hoặc BÁN, hoặc nâng lên mức mạnh. Đã ở MUA/BÁN thì giữ
  cho tới khi điểm lùi qua ±10 nên không báo đi báo lại.
- Tin kèm mức tham khảo theo ATR(14): cắt lỗ 1.5 ATR, chốt lời 1.5 và 3 ATR.
- Tắt chức năng này: đặt Variable `ADVICE=off`.

Đây là gợi ý từ chỉ báo kỹ thuật, không phải lời khuyên đầu tư.

## Chọn kênh gửi

Kênh gửi nằm ở dòng `channels=` trong file `settings.properties` ở gốc repo. Mặc định `channels=telegram`.
Các giá trị: `telegram`, `zalo`, `gmail`, cách nhau bởi dấu phẩy; để trống là tắt hết. Có 2 cách đổi:

- **Sửa file** `settings.properties` ngay trên GitHub rồi commit.
- **Trên dashboard**, mục "Kênh gửi cảnh báo": tick app, nhập mật khẩu, bấm Lưu. Sai mật khẩu thì không lưu.

Để dashboard lưu được, thêm 2 biến ở Vercel > project `trading` > Settings > Environment Variables, rồi Redeploy:
1. `GITHUB_TOKEN`: GitHub > Settings > Developer settings > Fine-grained tokens > Generate new token,
   chỉ chọn repo `trading`, quyền **Contents: Read and write**.
2. `ADMIN_PASSWORD`: mật khẩu bạn tự đặt (nên dài, khó đoán).

Thiếu một trong hai biến thì dashboard chỉ hiển thị, không cho lưu.

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
`CHANNELS`, `SYMBOLS` (vd `BTCUSDT,ETHUSDT`), `TIMEFRAMES` (vd `1h,4h,1d`), `NEAR` (vd `0.05`), `ADVICE` (`off` để tắt gợi ý mua/bán).
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
