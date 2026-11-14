# Trading — cảnh báo Bollinger Bands

Bot quét BTC, ETH, SOL, SUI (spot, cặp USDT) trên khung 1h / 4h / 1d. Khi giá gần chạm hoặc chạm/vượt
BB trên/dưới, bot gửi tin về **Telegram** (mặc định), **Zalo** hoặc **Gmail**, đồng thời lưu lại để xem trên dashboard Vercel.

Dashboard: https://trading-kid215.vercel.app

Bot chỉ cảnh báo, không đặt lệnh. Chạm band không phải là tín hiệu vào lệnh chắc chắn.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `bot/` | Bot Python; `bot/advisor.py` là phần gợi ý mua/bán, `bot/chart.py` vẽ ảnh biểu đồ (cần `matplotlib`) |
| `.github/workflows/scan.yml` | Quét 5 phút/lần trên GitHub Actions (mỗi lượt chạy khoảng 5 giờ rồi tự gọi lượt kế tiếp) |
| `web/` | Dashboard (biểu đồ, lịch sử tín hiệu, chọn kênh gửi) và trang gợi ý mua/bán `signals.html`, deploy lên Vercel |
| `.github/workflows/review.yml` | AI review tín hiệu hằng tuần bằng Claude CLI |
| `tests/` | Test: `python -m unittest discover -s tests` |
| nhánh `data` | `state.json` (chống spam), `signals.json` (lịch sử BB), `advice.json` và `advice_signals.json` (gợi ý mua/bán, kèm kết quả), `stats.json`, `ai_review.json`, bot tự tạo |

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
| ADX/DI 14 | ±15 | Sức mạnh xu hướng. ADX < 20 là đi ngang: điểm xu hướng chỉ tính một nửa |
| RSI 14 | ±15 | Quá bán (≤ 30) cộng điểm mua, quá mua (≥ 70) cộng điểm bán |
| Stochastic RSI | ±10 | K cắt D từ vùng quá bán/quá mua |
| Bollinger %B | ±10 | Giá ở/gần BB dưới (mua) hoặc BB trên (bán) |
| Khối lượng | ±5 | Nến tăng/giảm với khối lượng từ 1.5 lần trung bình 20 nến |
| Xác nhận đảo chiều | ±50 | Sau quá bán/quá mua: nến đảo chiều, RSI quay đầu, phân kỳ giá và RSI (25 điểm mỗi dấu hiệu) |
| Khung 1d | ±8 | Khung 1h, 4h được cộng/trừ theo xu hướng EMA của khung ngày |

Hai kiểu tín hiệu:

- **Thuận xu hướng**: EMA, MACD, ADX cùng chiều thì từ ±20 là **NÊN MUA / NÊN BÁN**, từ ±50 là **mạnh**.
- **Đảo chiều**: khi RSI ≤ 30 (hoặc vừa như vậy trong 6 nến gần nhất), bot **không bao giờ gợi ý bán** mà báo
  **QUÁ BÁN — CANH MUA**, đồng thời điểm xu hướng giảm bị giảm trọng số. Khi có xác nhận giá bật lên
  (nến tăng đóng trên đỉnh nến trước, RSI quay lên, hoặc phân kỳ tăng) thì báo **NÊN MUA**, cắt lỗ đặt dưới đáy gần nhất.
  Quá mua (RSI ≥ 70) thì ngược lại: **QUÁ MUA — CANH BÁN**, có xác nhận mới báo **NÊN BÁN**.

Vì sao quá bán chưa báo mua ngay: trong xu hướng giảm mạnh, RSI có thể nằm dưới 30 rất lâu trong khi giá vẫn rơi.
Chờ thêm một dấu hiệu giá bật lên giúp tránh bắt dao rơi.

- Điểm tổng hợp mỗi coin: 1h ×1, 4h ×2, 1d ×3.
- Bot nhắn khi một coin + khung chuyển sang MUA, BÁN, CANH MUA, CANH BÁN, hoặc nâng lên mức mạnh. Đã ở MUA/BÁN thì giữ
  cho tới khi điểm lùi qua ±10; "canh" chỉ nhắc lại sau 6 nến.
- Tin MUA/BÁN kèm mức tham khảo theo ATR(14): cắt lỗ 1.5 ATR (lệnh đảo chiều: ngoài đáy/đỉnh 10 nến gần nhất 0.5 ATR),
  chốt lời 1.5 và 3 ATR.
- Tắt chức năng này: đặt Variable `ADVICE=off`.

Đây là gợi ý từ chỉ báo kỹ thuật, không phải lời khuyên đầu tư.

## Chấm đúng/sai, thống kê và AI review

**Chấm đúng/sai** (`bot/evaluate.py`, mỗi lượt quét): với mỗi gợi ý MUA/BÁN đã gửi, bot xem các nến đã đóng sau đó.
**Đúng** nếu chạm chốt lời 1 trước cắt lỗ trong 24 nến, **Sai** nếu chạm cắt lỗ trước (nến chạm cả hai tính Sai),
**Hết hạn** nếu 24 nến chưa chạm mức nào. CANH MUA/BÁN chấm theo giá sau 12 nến. Cảnh báo BB không được chấm.

**Thống kê** (`stats.json`, trang `/signals.html` mục "Độ chính xác"): tỉ lệ đúng theo khung, coin, loại tín hiệu,
thuận xu hướng / đảo chiều, độ lớn điểm, và theo từng chỉ báo (khi đồng thuận với lệnh và khi ngược chiều).

**AI review** (workflow "AI review tín hiệu", tối Chủ nhật 20:07 giờ VN, chạy tay được trong tab Actions):
Claude CLI đọc thống kê, gửi báo cáo về Telegram và đề xuất chỉnh tham số. Đề xuất chỉ được giữ nếu:
có ít nhất 30 tín hiệu đã chấm, mỗi tham số đổi tối đa ±30%, nằm trong giới hạn và hợp lệ cả bộ.
**Không có gì tự áp dụng**: vào `/signals.html#ai`, nhập mật khẩu admin, bấm **Áp dụng**.
Tham số lưu ở các dòng `advice.*` trong `settings.properties` (giới hạn ở `web/params-spec.json`);
mỗi tín hiệu ghi `params_id` để so sánh trước/sau khi đổi. Không gọi được AI thì vẫn gửi bản thống kê.

Cài đặt AI (một lần):
1. Trên máy có trình duyệt và đã cài Claude Code, chạy `claude setup-token`, đăng nhập bằng tài khoản Claude Pro/Max,
   copy token (bắt đầu bằng `sk-ant-oat01-`). Token có hạn 1 năm.
2. Thêm secret `CLAUDE_CODE_OAUTH_TOKEN` với token đó.
3. Tab Actions > "AI review tín hiệu" > Run workflow để thử.
4. Nếu báo lỗi 401, dùng API key thay thế: tạo key ở https://console.anthropic.com, thêm secret `ANTHROPIC_API_KEY`
   (trả theo lượt dùng). Tuỳ chọn: Variable `CLAUDE_MODEL` để chọn model.

## Ảnh biểu đồ kèm tín hiệu

Mỗi tín hiệu gửi qua Telegram (cảnh báo BB lẫn gợi ý mua/bán) có kèm ảnh biểu đồ của đúng coin + khung đó:
nến, Bollinger Bands, EMA 20/50/200, RSI, và các mức cắt lỗ / chốt lời nếu là gợi ý MUA/BÁN. Nhiều tín hiệu cùng lúc
thì gộp thành 1 album (tối đa 10 ảnh). Ảnh do bot tự vẽ bằng `matplotlib` từ đúng dữ liệu nó dùng để chấm điểm
(`bot/chart.py`), không phải ảnh chụp trang TradingView. Zalo và Gmail chỉ nhận tin chữ.

Chạy trên máy: `pip install -r requirements.txt`. Thiếu thư viện thì bot vẫn chạy và chỉ gửi tin chữ.

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
- Bot quét 5 phút/lần: mỗi lượt chạy của workflow kéo dài khoảng 5 giờ rồi tự gọi lượt kế tiếp, vì lịch của GitHub Actions
  có thể trễ hàng giờ. Nếu thấy tab Actions không có lượt nào đang chạy, bấm Run workflow để khởi động lại.
  GitHub tự tắt lịch nếu repo không có hoạt động trong 60 ngày.
- Nguồn giá: Binance (`data-api.binance.vision`), dự phòng OKX.

## Chạy trên máy (không bắt buộc)

```
cp .env.example .env      # điền token
python -m bot --dry-run   # quét, chỉ in ra
python -m bot --loop 300  # quét 5 phút/lần
```
