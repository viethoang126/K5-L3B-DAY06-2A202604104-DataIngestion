# Manifest dữ liệu

## Corpus

| Trường | Giá trị |
|---|---|
| `source_id` | `blld-2019` |
| Văn bản | Bộ luật Lao động, số 45/2019/QH14, Quốc hội khóa XIV thông qua ngày 20/11/2019, hiệu lực 01/01/2021 |
| File | [starter/data/bo-luat-lao-dong-2019_45-2019-QH14_congbao.pdf](../starter/data/bo-luat-lao-dong-2019_45-2019-QH14_congbao.pdf) |
| Nguồn tải | Công báo Chính phủ: https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2019/11/30232/29070-1-2019993-99445-2019-qh14.pdf |
| Trang thông tin | https://vanban.chinhphu.vn/?pageid=27160&docid=198540 |
| Ngày truy cập | 2026-11-15 |
| SHA-256 | `3c865f3d92ba23604e316360b902297ddbc0d1c394d3c08a466029a9d43b5b6c` |

## Quyền sử dụng

Văn bản quy phạm pháp luật **không thuộc phạm vi bảo hộ quyền tác giả**. Khoản 2 Điều 15 Luật Sở hữu trí tuệ ghi: "Văn bản quy phạm pháp luật, văn bản hành chính, văn bản khác thuộc lĩnh vực tư pháp và bản dịch chính thức của văn bản đó". Đã đối chiếu với bản hợp nhất 155/VBHN-VPQH ngày 09/09/2025. Vì vậy được lưu file PDF trong repo và xử lý bằng embedding model.

## Phiên bản

Dùng **bản gốc đăng Công báo số 993 + 994 ngày 26/12/2019**. Bản này **chưa hợp nhất** các sửa đổi, bổ sung sau năm 2019. Cơ sở dữ liệu vbpl.vn ghi trạng thái "hết hiệu lực một phần". Mọi câu hỏi và đáp án trong benchmark dựa trên đúng bản này. Không tự suy luận điều khoản nào còn hay hết hiệu lực.

## Quy tắc tính trang

- **Đơn vị truy vết:** số trang vật lý trong PDF, đánh từ 1 đến 94. Giá trị này dùng cho `page` và `gold_page`.
- **Số trang in:** Công báo in số trang riêng, từ 3 đến 95. Số này được lưu ở cột `printed_page` để tiện tra cứu, không dùng làm ID.
- **Trang được tính:** trang có ít nhất 200 ký tự sau chuẩn hóa. Kết quả là **93 trang (trang 1–93)**, tổng 196.793 ký tự.
- **Trang bị loại:** trang 94, vì trống (0 ký tự).
- **Trang không phải nội dung luật:** PDF không có trang bìa, mục lục hay tài liệu tham khảo. Trang 1 có phần đầu Công báo nhưng chứa Điều 1–3. Trang 93 có phần chữ ký nhưng chứa Điều 220.
- **Nhân bản:** không có trang nào bị nhân bản.

## Trích xuất và chuẩn hóa

- **Công cụ:** PyMuPDF (`page.get_text()`), sau đó chuẩn hóa Unicode NFC.
- **Đã thử pypdf nhưng không dùng:** với PDF này, pypdf tách sai âm tiết tiếng Việt khoảng 1.495 lần, ví dụ "thỏa thu ận", "tr ường h ợp". PyMuPDF chỉ có khoảng 2 lỗi tương tự. Cách đếm là heuristic regex, không phải đánh giá thủ công đầy đủ.
- **Số ký tự:** `len(text.strip())` sau chuẩn hóa NFC.
- **OCR:** không cần, vì toàn bộ là PDF có lớp text.

## Metadata để lọc

Trường lọc là `chuong`: 17 chương, từ I đến XVII. Giá trị lấy từ dòng tiêu đề `Chương …` trong chính văn bản, không suy đoán.

- **Gán cho chunk:** dùng tiêu đề chương gần nhất phía trên vị trí của chunk. Không gán theo trang, vì 14 trang chứa ranh giới giữa hai chương. Cột `chuong` trong `manifest_pages.csv` liệt kê mọi chương xuất hiện trên trang, ví dụ `I;II`.
- **Chunk vắt qua hai chương** (có thể xảy ra ở cấu hình fixed-size): cách xử lý phải được ghi rõ trong code và báo cáo.

## Các file

| File | Nội dung |
|---|---|
| [manifest.csv](manifest.csv) | Thông tin cấp văn bản: nguồn, quyền, phiên bản, số trang, hash |
| [manifest_pages.csv](manifest_pages.csv) | Mỗi trang: `page`, `printed_page`, `char_count`, `chuong`, Điều đầu/cuối **có tiêu đề** trên trang, `counted` |
| [manifest_chapters.csv](manifest_chapters.csv) | Mỗi chương: tiêu đề, khoảng trang, khoảng Điều |

Các số liệu được tính tự động bằng PyMuPDF trên file có SHA-256 ở trên.
