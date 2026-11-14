# Chấm đúng/sai tín hiệu, thống kê và AI review — thiết kế

Ngày: 2026-11-14 · Trạng thái: đã duyệt

## Mục đích
Biết gợi ý mua/bán của bot đúng bao nhiêu, chỉ báo nào giúp hay hại, và dùng AI (Claude CLI) đọc số liệu đó
để giải thích và đề xuất chỉnh tham số. Người dùng duyệt trước khi áp dụng.

## Mục tiêu / không làm / không được xảy ra
- Mục tiêu: chấm tự động mọi gợi ý đã gửi; thống kê theo nhiều chiều; báo cáo AI hằng tuần qua Telegram;
  áp dụng đề xuất bằng 1 nút trên dashboard.
- Không làm: AI tự đổi tham số; AI nhận xét từng tín hiệu; chấm cảnh báo Bollinger (không có mức chốt lời/cắt lỗ).
- Không được xảy ra: thống kê đẹp giả (nến chạm cả 2 mức tính Sai); AI đổi tham số ngoài phạm vi cho phép;
  đề xuất dựa trên quá ít dữ liệu (< 30 tín hiệu đã có kết quả thì không đề xuất).

## Các hướng đã cân nhắc
1. Chấm đúng/sai bằng code, AI chỉ đọc thống kê và đề xuất (chọn): chính xác, rẻ, AI không phải tính toán.
2. Đưa toàn bộ nến cho AI tự chấm: tốn, dễ sai số, không lặp lại được.
3. AI nhận xét từng tín hiệu trước khi gửi: tốn và chậm; người dùng chọn báo cáo định kỳ.

## Quyết định của người dùng
- AI: báo cáo định kỳ + đề xuất, người dùng duyệt trên dashboard.
- Công cụ AI: Claude CLI (`claude -p`), xác thực bằng `CLAUDE_CODE_OAUTH_TOKEN` (gói Pro/Max);
  hỗ trợ thêm `ANTHROPIC_API_KEY` làm dự phòng.
- Đúng = chạm chốt lời 1 trước cắt lỗ trong 24 nến.
- Duyệt: review hằng tuần, giới hạn mỗi lần đổi ±30%.

## Thiết kế
- `bot/evaluate.py`: mỗi lượt quét chấm các gợi ý chưa có kết quả bằng nến đã đóng sau nến tín hiệu.
  MUA/BÁN: win / loss / expired (24 nến), kèm % lãi lỗ và số nến. CANH MUA/BÁN: right / wrong theo giá sau 12 nến.
- `bot/stats.py`: `stats.json` trên nhánh data — tổng, theo coin, khung, loại, kiểu (thuận xu hướng / đảo chiều),
  khoảng điểm, theo bộ tham số; mỗi chỉ báo: tỉ lệ đúng khi đồng thuận / ngược chiều / trung tính.
- Tham số chỉnh được: khai báo một chỗ ở `web/params-spec.json` (mặc định, min, max), lưu ở các dòng `advice.*`
  trong `settings.properties`. Mỗi tín hiệu ghi `params_id` để so sánh trước/sau khi đổi.
- `bot/review.py` + workflow `review.yml` (tối Chủ nhật giờ VN): gọi `claude -p`, nhận JSON {report, changes},
  kiểm tra phạm vi + ±30% + đủ dữ liệu, lưu `ai_review.json`, gửi Telegram. AI lỗi thì vẫn gửi bản thống kê.
- Dashboard `signals.html`: bảng thống kê, kết quả từng tín hiệu, báo cáo AI, nút Áp dụng (mật khẩu admin)
  qua `web/api/params.js` ghi vào `settings.properties`.

## Để người làm tự quyết
Cách trình bày bảng, nội dung prompt, cách tách số liệu gửi cho AI.
